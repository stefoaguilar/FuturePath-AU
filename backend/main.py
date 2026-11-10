
import json
import sqlite3
from contextlib import closing
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware

from database import DATABASE_PATH
from eligibility import evaluate_condition
from gap_analysis import analyse_opportunity_gaps
from deadline_tracking import analyse_opportunity_deadline

from pathway_generation import generate_draft_pathway
from pathway_access import require_pathway_dev_access
from pathway_storage import (
    save_draft_pathway,
    get_saved_pathway,
    edit_saved_step,
    add_student_step,
    reorder_saved_steps,
    approve_saved_pathway,
    export_approved_pathway,
    PathwayRevisionConflict
)

# Create the FuturePath AU backend application.
app = FastAPI(
    title="FuturePath AU API",
    description="Backend API for the FuturePath AU cybersecurity pathway navigator.",
    version="0.1.0"
)


# Allow Hakm's React frontend to communicate with FastAPI.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["*"]
)


# --------------------------------------------------
# Basic API endpoints
# --------------------------------------------------

# Existing homepage endpoint.
@app.get("/")
def home():
    return {
        "message": "FuturePath AU backend is running!",
        "application": "FuturePath AU",
        "version": "0.1.0"
    }


# Existing health-check endpoint.
@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "message": "FuturePath AU API is operational"
    }


# --------------------------------------------------
# STE-03: SQLite opportunity retrieval
# --------------------------------------------------

# Retrieve opportunity records from SQLite.
@app.get("/api/opportunities")
def get_opportunities():

    # Avoid creating an empty database accidentally.
    if not DATABASE_PATH.is_file():
        raise HTTPException(
            status_code=500,
            detail="Opportunity database is unavailable."
        )

    try:
        # Open the existing database in read-only mode.
        database_uri = DATABASE_PATH.as_uri() + "?mode=ro"

        with closing(
            sqlite3.connect(database_uri, uri=True)
        ) as connection:

            connection.row_factory = sqlite3.Row

            # Retrieve the original dataset metadata.
            metadata_rows = connection.execute(
                "SELECT key, value FROM dataset_metadata"
            ).fetchall()

            metadata = {
                row["key"]: row["value"]
                for row in metadata_rows
            }

            # Retrieve opportunities in their original order.
            opportunity_rows = connection.execute("""
                SELECT
                    id, record_type, title, provider,
                    category, location, study_level,
                    summary, skills_json, source_url,
                    deadline_json, verification_json,
                    data_notes
                FROM opportunities
                ORDER BY position
            """).fetchall()

            opportunities = []

            for row in opportunity_rows:

                # Retrieve conditions for this opportunity.
                condition_rows = connection.execute("""
                    SELECT
                        id, type, text, evidence_summary,
                        source_url, checkable_from_profile
                    FROM eligibility_conditions
                    WHERE opportunity_id = ?
                    ORDER BY position
                """, (row["id"],)).fetchall()

                conditions = []

                for condition in condition_rows:
                    conditions.append({
                        "id": condition["id"],
                        "type": condition["type"],
                        "text": condition["text"],
                        "evidence_summary": condition["evidence_summary"],
                        "source_url": condition["source_url"],
                        "checkable_from_profile": bool(
                            condition["checkable_from_profile"]
                        )
                    })

                # Reconstruct Samer's original JSON format.
                opportunity = {
                    "id": row["id"],
                    "record_type": row["record_type"],
                    "title": row["title"],
                    "provider": row["provider"],
                    "category": row["category"],
                    "location": row["location"],
                    "study_level": row["study_level"],
                    "summary": row["summary"],
                    "skills": json.loads(row["skills_json"]),
                    "source_url": row["source_url"],
                    "eligibility_conditions": conditions,
                    "deadline": json.loads(row["deadline_json"]),
                    "verification": json.loads(
                        row["verification_json"]
                    ),
                    "data_notes": row["data_notes"]
                }

                opportunities.append(opportunity)

            # Return the same response format as before.
            return {
                "schema_version": metadata.get(
                    "schema_version", ""
                ),
                "dataset_note": metadata.get(
                    "dataset_note", ""
                ),
                "opportunities": opportunities
            }

    except (sqlite3.Error, json.JSONDecodeError) as error:
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve opportunity records."
        ) from error


# --------------------------------------------------
# STE-04: Student profile validation
# --------------------------------------------------

# Define the validated student profile shared by
# the eligibility and gap-analysis endpoints.
class ProfileInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True
    )

    education_level: Literal[
        "undergraduate",
        "postgraduate",
        "vocational",
        "school_leaver",
        "graduate",
        "not_stated"
    ] = "not_stated"

    enrolment_status: Literal[
        "enrolled_full_time",
        "enrolled_part_time",
        "commencing",
        "not_enrolled",
        "not_stated"
    ] = "not_stated"

    institution: str = ""

    citizenship_status: Literal[
        "australian_citizen",
        "permanent_resident",
        "nz_citizen",
        "other",
        "not_stated"
    ] = "not_stated"

    state: Literal[
        "ACT",
        "NSW",
        "NT",
        "QLD",
        "SA",
        "TAS",
        "VIC",
        "WA",
        "not_stated"
    ] = "not_stated"

    field_of_study: str = ""

    weighted_average: float | None = Field(
        default=None,
        ge=0,
        le=100,
        allow_inf_nan=False
    )

    skills: list[str] = Field(
        default_factory=list
    )

    experience_notes: str = ""

    preferred_agencies: list[str] = Field(
        default_factory=list
    )

    identity_answer: Literal[
        "yes",
        "no",
        "prefer_not_to_say",
        "not_stated"
    ] = "not_stated"


# Define the information accepted by the eligibility API.
# Existing request format is preserved for compatibility.
class EligibilityRequest(BaseModel):
    opportunity_id: str
    profile: ProfileInput


# --------------------------------------------------
# STE-07: Saved pathway step editing request
# --------------------------------------------------

class PathwayStepEditRequest(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
        strict=True
    )

    # The version last retrieved by the student.
    expected_revision: int = Field(gt=0)

    # A student-editable display title (never source evidence).
    title: str = Field(min_length=1, max_length=200)

    # Student-controlled notes and inclusion preference.
    student_note: str = Field(max_length=2000)
    included: bool


# --------------------------------------------------
# STE-07: Student-created pathway action request
# --------------------------------------------------

class PathwayStepCreateRequest(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
        strict=True
    )

    # The pathway revision the student last viewed.
    expected_revision: int = Field(gt=0)

    # Title of the student's personal action.
    title: str = Field(min_length=1, max_length=200)

    # Optional personal planning note.
    student_note: str = Field(
        default="",
        max_length=2000
    )

    # Include the action by default.
    included: bool = True


# --------------------------------------------------
# STE-07: Pathway reordering request
# --------------------------------------------------

class PathwayStepsReorderRequest(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
        strict=True
    )

    # Reject outdated pathway revisions.
    expected_revision: int = Field(gt=0)

    # Every existing step ID, exactly once, in the new order.
    step_ids: list[str] = Field(min_length=1)


# --------------------------------------------------
# STE-07: Explicit student approval request
# --------------------------------------------------

class PathwayApprovalRequest(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
        strict=True
    )

    # Approval must target the current pathway revision.
    expected_revision: int = Field(gt=0)

    # Approval is never implicit.
    confirmed: bool


# --------------------------------------------------
# STE-07: Protected pathway export request
# --------------------------------------------------

class PathwayExportRequest(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
        strict=True
    )

    # Export the exact currently approved revision.
    expected_revision: int = Field(gt=0)


# --------------------------------------------------
# STE-04: Eligibility evaluation
# --------------------------------------------------

# Evaluate published conditions against a submitted profile.
@app.post("/api/eligibility/evaluate")
def evaluate_eligibility(request: EligibilityRequest):

    # Reuse our existing SQLite-backed opportunity reader.
    dataset = get_opportunities()

    # Find the selected opportunity using its original ID.
    opportunity = next(
        (
            item for item in dataset["opportunities"]
            if item["id"] == request.opportunity_id
        ),
        None
    )

    if opportunity is None:
        raise HTTPException(
            status_code=404,
            detail="Opportunity not found."
        )

    # Convert the validated profile into a dictionary.
    # Preserve only fields explicitly supplied by the student.
    # Identity answers are never used for automatic scoring.
    profile_data = request.profile.model_dump(
        exclude_unset=True,
        exclude={"identity_answer"}
    )

    # Evaluate each published requirement independently.
    results = [
        evaluate_condition(condition, profile_data)
        for condition in opportunity["eligibility_conditions"]
    ]

    return {
        "opportunity_id": opportunity["id"],
        "results": results,
        "notice": (
            "These comparisons are informational only. "
            "They do not represent an official eligibility "
            "or admission decision."
        )
    }


# --------------------------------------------------
# STE-05: Prerequisite gap analysis
# --------------------------------------------------

# Analyse published requirements and advisory skill areas.
@app.post("/api/gaps/analyse")
def analyse_gaps(request: EligibilityRequest):

    # Retrieve opportunities from our existing SQLite database.
    dataset = get_opportunities()

    opportunity = next(
        (
            item for item in dataset["opportunities"]
            if item["id"] == request.opportunity_id
        ),
        None
    )

    # Reject unknown opportunity IDs.
    if opportunity is None:
        raise HTTPException(
            status_code=404,
            detail="Opportunity not found."
        )

    # Use the existing validated student profile.
    # Never send identity answers to automatic evaluation.
    profile_data = request.profile.model_dump(
        exclude_unset=True,
        exclude={"identity_answer"}
    )

    # Reuse the tested gap-analysis module.
    return analyse_opportunity_gaps(
        opportunity,
        profile_data
    )


# --------------------------------------------------
# STE-06: Deadline tracking
# --------------------------------------------------

# Retrieve deadline information for a selected opportunity.
@app.get("/api/deadlines/{opportunity_id}")
def get_opportunity_deadline(
    opportunity_id: str,
    reference_date: date | None = None
):

    # Retrieve the existing SQLite-backed catalogue.
    dataset = get_opportunities()

    # Find the requested opportunity.
    opportunity = next(
        (
            item for item in dataset["opportunities"]
            if item["id"] == opportunity_id
        ),
        None
    )

    # Reject unknown opportunity IDs.
    if opportunity is None:
        raise HTTPException(
            status_code=404,
            detail="Opportunity not found."
        )

    # Use the server's current local date unless a
    # reference date is explicitly supplied.
    # A supplied date allows reproducible testing.
    evaluation_date = (
        reference_date
        if reference_date is not None
        else date.today()
    )

    # Reuse the tested deadline-tracking module.
    return analyse_opportunity_deadline(
        opportunity,
        evaluation_date
    )


# --------------------------------------------------
# STE-07: Editable pathway generation
# --------------------------------------------------

# Generate an unapproved student pathway from
# published opportunity data and a validated profile.
@app.post("/api/pathways/generate")
def generate_pathway(
    request: EligibilityRequest,
    reference_date: date | None = None
):

    # Retrieve the existing SQLite-backed opportunities.
    dataset = get_opportunities()

    # Find the opportunity selected by the student.
    opportunity = next(
        (
            item for item in dataset["opportunities"]
            if item["id"] == request.opportunity_id
        ),
        None
    )

    # Reject unknown opportunity IDs.
    if opportunity is None:
        raise HTTPException(
            status_code=404,
            detail="Opportunity not found."
        )

    # Use the existing validated profile.
    # Identity answers are not used for automatic scoring.
    profile_data = request.profile.model_dump(
        exclude_unset=True,
        exclude={"identity_answer"}
    )

    # Use the current server date unless a reference
    # date is supplied for reproducible testing.
    evaluation_date = (
        reference_date
        if reference_date is not None
        else date.today()
    )

    # Return a new, unapproved pathway draft.
    # This endpoint does not approve or export plans.
    return generate_draft_pathway(
        opportunity,
        profile_data,
        evaluation_date
    )


# --------------------------------------------------
# STE-07: Save a student pathway draft
# --------------------------------------------------

@app.post(
    "/api/pathways/save",
    dependencies=[
        Depends(require_pathway_dev_access)
    ]
)
def save_pathway(
    request: EligibilityRequest,
    reference_date: date | None = None
):
    """
    Save an unapproved pathway draft to SQLite.

    Local-development access is required.
    This endpoint cannot approve or export a pathway.
    """

    # Reuse the existing SQLite-backed opportunity
    # retrieval and validation workflow.
    dataset = get_opportunities()

    opportunity = next(
        (
            item
            for item in dataset["opportunities"]
            if item["id"] == request.opportunity_id
        ),
        None
    )

    if opportunity is None:
        raise HTTPException(
            status_code=404,
            detail="Opportunity not found."
        )

    # Use only explicitly supplied validated fields.
    # Identity answers must not be used for scoring
    # or stored as part of the pathway.
    profile_data = request.profile.model_dump(
        exclude_unset=True,
        exclude={"identity_answer"}
    )

    # Support reproducible testing with a supplied date.
    evaluation_date = (
        reference_date
        if reference_date is not None
        else date.today()
    )

    # Save the generated steps and original opportunity
    # evidence as an unapproved SQLite pathway.
    return save_draft_pathway(
        opportunity=opportunity,
        profile=profile_data,
        reference_date=evaluation_date,
        database_path=DATABASE_PATH
    )


# --------------------------------------------------
# STE-07: Retrieve a saved student pathway
# --------------------------------------------------

@app.get(
    "/api/pathways/saved/{pathway_id}",
    dependencies=[
        Depends(require_pathway_dev_access)
    ]
)
def retrieve_saved_pathway(pathway_id: str):
    """
    Retrieve a saved pathway from SQLite.

    This operation requires controlled local-development
    access and does not modify pathway approval.
    """

    try:
        # Retrieve the saved pathway and its actions.
        pathway = get_saved_pathway(
            pathway_id=pathway_id,
            database_path=DATABASE_PATH
        )

    except FileNotFoundError as error:
        raise HTTPException(
            status_code=503,
            detail="Pathway database is unavailable."
        ) from error

    except sqlite3.Error as error:
        raise HTTPException(
            status_code=503,
            detail="Unable to retrieve the saved pathway."
        ) from error

    # An unknown pathway should return HTTP 404.
    if pathway is None:
        raise HTTPException(
            status_code=404,
            detail="Saved pathway not found."
        )

    # Approval and export eligibility are calculated
    # from the persisted database revision.
    return pathway


# --------------------------------------------------
# STE-07: Edit a saved pathway action
# --------------------------------------------------

@app.put(
    "/api/pathways/saved/{pathway_id}/steps/{step_id}",
    dependencies=[
        Depends(require_pathway_dev_access)
    ]
)
def update_saved_pathway_step(
    pathway_id: str,
    step_id: str,
    request: PathwayStepEditRequest
):
    """
    Update only the student-editable fields of a saved action.

    Original source evidence is preserved by pathway_storage.
    Successful edits advance the revision and revoke approval.
    """

    try:
        return edit_saved_step(
            pathway_id=pathway_id,
            step_id=step_id,
            expected_revision=request.expected_revision,
            title=request.title,
            student_note=request.student_note,
            included=request.included,
            database_path=DATABASE_PATH
        )

    except PathwayRevisionConflict as error:
        raise HTTPException(
            status_code=409,
            detail=str(error)
        ) from error

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error)
        ) from error

    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error)
        ) from error

    except FileNotFoundError as error:
        raise HTTPException(
            status_code=503,
            detail="Pathway database is unavailable."
        ) from error

    except sqlite3.Error as error:
        raise HTTPException(
            status_code=503,
            detail="Unable to update the saved pathway."
        ) from error


# --------------------------------------------------
# STE-07: Add a student-created pathway action
# --------------------------------------------------

@app.post(
    "/api/pathways/saved/{pathway_id}/steps",
    dependencies=[
        Depends(require_pathway_dev_access)
    ]
)
def create_saved_pathway_step(
    pathway_id: str,
    request: PathwayStepCreateRequest
):
    """
    Add a personal action to an existing saved pathway.

    The new action is marked as student-created.
    Original opportunity evidence is not modified.

    A successful addition increases the pathway
    revision and invalidates previous approval.
    """

    try:
        return add_student_step(
            pathway_id=pathway_id,
            expected_revision=request.expected_revision,
            title=request.title,
            student_note=request.student_note,
            included=request.included,
            database_path=DATABASE_PATH
        )

    except PathwayRevisionConflict as error:
        raise HTTPException(
            status_code=409,
            detail=str(error)
        ) from error

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error)
        ) from error

    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error)
        ) from error

    except FileNotFoundError as error:
        raise HTTPException(
            status_code=503,
            detail="Pathway database is unavailable."
        ) from error

    except sqlite3.Error as error:
        raise HTTPException(
            status_code=503,
            detail="Unable to add the student pathway action."
        ) from error


# --------------------------------------------------
# STE-07: Reorder saved pathway actions
# --------------------------------------------------

@app.put(
    "/api/pathways/saved/{pathway_id}/reorder",
    dependencies=[
        Depends(require_pathway_dev_access)
    ]
)
def reorder_saved_pathway(
    pathway_id: str,
    request: PathwayStepsReorderRequest
):
    """
    Rearrange all actions in a saved pathway.

    Original source evidence remains unchanged.
    A real order change revokes any previous approval;
    submitting the same order preserves the revision.
    """

    try:
        return reorder_saved_steps(
            pathway_id=pathway_id,
            expected_revision=request.expected_revision,
            step_ids=request.step_ids,
            database_path=DATABASE_PATH
        )

    except PathwayRevisionConflict as error:
        raise HTTPException(
            status_code=409,
            detail=str(error)
        ) from error

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error)
        ) from error

    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error)
        ) from error

    except FileNotFoundError as error:
        raise HTTPException(
            status_code=503,
            detail="Pathway database is unavailable."
        ) from error

    except sqlite3.Error as error:
        raise HTTPException(
            status_code=503,
            detail="Unable to reorder the saved pathway."
        ) from error


# --------------------------------------------------
# STE-07: Explicitly approve a saved pathway
# --------------------------------------------------

@app.post(
    "/api/pathways/saved/{pathway_id}/approve",
    dependencies=[
        Depends(require_pathway_dev_access)
    ]
)
def approve_pathway(
    pathway_id: str,
    request: PathwayApprovalRequest
):
    """
    Approve only the current saved pathway revision.

    Requires explicit confirmation and at least one
    included action. This is not an eligibility decision.

    Local-development access only.
    """

    try:
        return approve_saved_pathway(
            pathway_id=pathway_id,
            expected_revision=request.expected_revision,
            confirmed=request.confirmed,
            database_path=DATABASE_PATH
        )

    except PathwayRevisionConflict as error:
        raise HTTPException(
            status_code=409,
            detail=str(error)
        ) from error

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error)
        ) from error

    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error)
        ) from error

    except FileNotFoundError as error:
        raise HTTPException(
            status_code=503,
            detail="Pathway database is unavailable."
        ) from error

    except sqlite3.Error as error:
        raise HTTPException(
            status_code=503,
            detail="Unable to approve the saved pathway."
        ) from error


# --------------------------------------------------
# STE-07: Export an approved saved pathway
# --------------------------------------------------

@app.post(
    "/api/pathways/saved/{pathway_id}/export",
    dependencies=[
        Depends(require_pathway_dev_access)
    ]
)
def export_saved_pathway(
    pathway_id: str,
    request: PathwayExportRequest
):
    """
    Return the approved current pathway revision as JSON.

    Exports only included actions, preserving original
    source evidence separately from student edits.

    Local-development access only; not student authentication.
    """

    try:
        return export_approved_pathway(
            pathway_id=pathway_id,
            expected_revision=request.expected_revision,
            database_path=DATABASE_PATH
        )

    except PathwayRevisionConflict as error:
        raise HTTPException(
            status_code=409,
            detail=str(error)
        ) from error

    except PermissionError as error:
        # A draft or invalidated approval cannot be exported.
        raise HTTPException(
            status_code=409,
            detail=str(error)
        ) from error

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error)
        ) from error

    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error)
        ) from error

    except FileNotFoundError as error:
        raise HTTPException(
            status_code=503,
            detail="Pathway database is unavailable."
        ) from error

    except sqlite3.Error as error:
        raise HTTPException(
            status_code=503,
            detail="Unable to export the saved pathway."
        ) from error
