
import json
import sqlite3
from contextlib import closing
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from eligibility import evaluate_condition
from gap_analysis import analyse_opportunity_gaps
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from database import DATABASE_PATH


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
    allow_methods=["GET", "POST"],
    allow_headers=["*"]
)


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
                    "verification": json.loads(row["verification_json"]),
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


# Define the student profile fields and accepted values.
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

# Analyse published requirements and advisory skill areas.
@app.post("/api/gaps/analyse")
def analyse_gaps(request: EligibilityRequest):

    # Retrieve opportunities from our existing SQLite database.
    dataset = get_opportunities()

    # Find the opportunity selected by the student.
    opportunity = next(
        (
            item for item in dataset["opportunities"]
            if item["id"] == request.opportunity_id
        ),
        None
    )

    # Reject opportunity IDs that do not exist.
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
