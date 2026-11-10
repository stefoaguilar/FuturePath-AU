
import json
import sqlite3

from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

import database
from pathway_generation import generate_draft_pathway


# --------------------------------------------------
# STE-07: Database connection
# --------------------------------------------------

def open_pathway_database(database_path=None):
    """
    Open an existing SQLite database.

    A missing database must not be created accidentally.
    """

    path = (
        Path(database_path)
        if database_path is not None
        else database.DATABASE_PATH
    )

    if not path.is_file():
        raise FileNotFoundError(
            "Pathway database is unavailable."
        )

    connection = sqlite3.connect(path)

    connection.row_factory = sqlite3.Row

    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    return connection


# --------------------------------------------------
# STE-07: Save a generated draft pathway
# --------------------------------------------------

def save_draft_pathway(
    opportunity: dict,
    profile: dict,
    reference_date: date,
    database_path=None
) -> dict:

    # Generate suggestions using the existing,
    # tested deterministic pathway generator.
    draft = generate_draft_pathway(
        opportunity,
        profile,
        reference_date
    )

    # Only unapproved drafts can enter this workflow.
    if (
        draft["status"] != "draft"
        or draft["approved"] is not False
        or draft["can_export"] is not False
    ):
        raise ValueError(
            "Only unapproved pathway drafts can be saved."
        )

    # Give each saved pathway a unique ID.
    pathway_id = str(uuid4())

    # Use timezone-aware UTC timestamps.
    timestamp = datetime.now(
        timezone.utc
    ).isoformat(timespec="seconds")

    # Open the existing database.
    with closing(
        open_pathway_database(database_path)
    ) as connection:

        # Save the pathway and all steps in one transaction.
        # Any insertion failure rolls back the operation.
        with connection:

            connection.execute(
                """
                INSERT INTO pathways (
                    id,
                    opportunity_id,
                    opportunity_title,
                    reference_date,
                    source_snapshot_json,
                    revision,
                    approved_revision,
                    approved_at,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pathway_id,
                    draft["opportunity_id"],
                    draft["opportunity_title"],
                    draft["reference_date"],

                    # Preserve original opportunity information,
                    # including published eligibility evidence.
                    json.dumps(
                        opportunity,
                        ensure_ascii=False
                    ),

                    1,
                    None,
                    None,
                    timestamp,
                    timestamp
                )
            )

            # Store each generated action separately.
            for position, step in enumerate(
                draft["steps"],
                start=1
            ):

                connection.execute(
                    """
                    INSERT INTO pathway_steps (
                        id,
                        pathway_id,
                        position,
                        origin,
                        source_step_id,
                        source_step_json,
                        title_override,
                        student_title,
                        student_note,
                        is_included
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid4()),
                        pathway_id,
                        position,
                        "generated",
                        step["step_id"],

                        # Preserve the generated source step.
                        # Future edits must not overwrite this.
                        json.dumps(
                            step,
                            ensure_ascii=False
                        ),

                        None,
                        None,
                        "",
                        1
                    )
                )

    # Return the newly saved pathway.
    return get_saved_pathway(
        pathway_id,
        database_path
    )


# --------------------------------------------------
# STE-07: Retrieve a saved pathway
# --------------------------------------------------

def get_saved_pathway(
    pathway_id: str,
    database_path=None
) -> dict | None:

    with closing(
        open_pathway_database(database_path)
    ) as connection:

        # Retrieve the saved pathway.
        pathway = connection.execute(
            """
            SELECT *
            FROM pathways
            WHERE id = ?
            """,
            (pathway_id,)
        ).fetchone()

        if pathway is None:
            return None

        # Retrieve actions in their saved order.
        step_rows = connection.execute(
            """
            SELECT *
            FROM pathway_steps
            WHERE pathway_id = ?
            ORDER BY position
            """,
            (pathway_id,)
        ).fetchall()

        steps = []

        for row in step_rows:

            # Original generated information is immutable
            # through the planned student editing API.
            source_step = (
                json.loads(row["source_step_json"])
                if row["source_step_json"] is not None
                else None
            )

            # Determine the displayed action title.
            if row["origin"] == "generated":

                title = (
                    row["title_override"]
                    if row["title_override"] is not None
                    else source_step["title"]
                )

            else:
                title = row["student_title"]

            steps.append({
                "id": row["id"],
                "position": row["position"],
                "origin": row["origin"],
                "source_step_id": row["source_step_id"],
                "source_step": source_step,
                "title": title,
                "student_note": row["student_note"],
                "included": bool(row["is_included"])
            })

        # Approval is valid only when it applies
        # to the pathway's current revision.
        approved = (
            pathway["approved_revision"] is not None
            and pathway["approved_revision"]
            == pathway["revision"]
            and pathway["approved_at"] is not None
        )

        return {
            "pathway_id": pathway["id"],
            "opportunity_id": pathway["opportunity_id"],
            "opportunity_title": pathway["opportunity_title"],
            "reference_date": pathway["reference_date"],
            "revision": pathway["revision"],
            "approved_revision": (
                pathway["approved_revision"]
            ),
            "status": (
                "approved" if approved else "draft"
            ),
            "approved": approved,
            "can_export": approved,
            "created_at": pathway["created_at"],
            "updated_at": pathway["updated_at"],
            "steps": steps,
            "notice": (
                "This is a student-controlled pathway. "
                "Published requirements and source evidence "
                "are preserved separately from editable actions. "
                "Export is permitted only for the currently "
                "approved revision."
            )
        }

# --------------------------------------------------
# STE-07: Pathway editing safeguards
# --------------------------------------------------

class PathwayRevisionConflict(Exception):
    """
    Raised when a pathway has changed since the
    student last retrieved it.
    """
    pass


def edit_saved_step(
    pathway_id: str,
    step_id: str,
    expected_revision: int,
    title: str,
    student_note: str,
    included: bool,
    database_path=None
) -> dict:
    """
    Edit student-controlled action fields.

    Original published requirements, generated source
    information and evidence are never overwritten.

    Every successful edit creates a new pathway revision
    and invalidates any previous approval.
    """

    # Validate the supplied revision number.
    if (
        type(expected_revision) is not int
        or expected_revision < 1
    ):
        raise ValueError(
            "Expected revision must be a positive integer."
        )

    # Validate editable text.
    if (
        not isinstance(title, str)
        or not title.strip()
        or len(title) > 200
    ):
        raise ValueError(
            "Title must contain 1 to 200 characters."
        )

    if (
        not isinstance(student_note, str)
        or len(student_note) > 2000
    ):
        raise ValueError(
            "Student note must contain at most 2000 characters."
        )

    if type(included) is not bool:
        raise ValueError(
            "Included must be a boolean."
        )

    timestamp = datetime.now(
        timezone.utc
    ).isoformat(timespec="seconds")

    with closing(
        open_pathway_database(database_path)
    ) as connection:

        # Lock the database for this write operation.
        # This prevents simultaneous edits from both
        # being accepted against the same revision.
        connection.execute("BEGIN IMMEDIATE")

        try:
            pathway = connection.execute(
                """
                SELECT revision
                FROM pathways
                WHERE id = ?
                """,
                (pathway_id,)
            ).fetchone()

            if pathway is None:
                raise LookupError(
                    "Pathway not found."
                )

            # Reject changes based on an outdated copy.
            if pathway["revision"] != expected_revision:
                raise PathwayRevisionConflict(
                    "Pathway revision has changed. "
                    "Retrieve the latest version before editing."
                )

            step = connection.execute(
                """
                SELECT origin
                FROM pathway_steps
                WHERE id = ?
                  AND pathway_id = ?
                """,
                (step_id, pathway_id)
            ).fetchone()

            if step is None:
                raise LookupError(
                    "Pathway step not found."
                )

            # Generated steps: edit the display override,
            # not the preserved source JSON.
            if step["origin"] == "generated":

                connection.execute(
                    """
                    UPDATE pathway_steps
                    SET title_override = ?,
                        student_note = ?,
                        is_included = ?
                    WHERE id = ?
                      AND pathway_id = ?
                    """,
                    (
                        title.strip(),
                        student_note,
                        int(included),
                        step_id,
                        pathway_id
                    )
                )

            # Student-created steps use their own title.
            elif step["origin"] == "student":

                connection.execute(
                    """
                    UPDATE pathway_steps
                    SET student_title = ?,
                        student_note = ?,
                        is_included = ?
                    WHERE id = ?
                      AND pathway_id = ?
                    """,
                    (
                        title.strip(),
                        student_note,
                        int(included),
                        step_id,
                        pathway_id
                    )
                )

            else:
                raise ValueError(
                    "Unsupported pathway step origin."
                )

            # Increment the revision and invalidate
            # any approval of a previous version.
            connection.execute(
                """
                UPDATE pathways
                SET revision = revision + 1,
                    approved_revision = NULL,
                    approved_at = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    timestamp,
                    pathway_id
                )
            )

            connection.commit()

        except Exception:
            # Leave the pathway unchanged if the edit
            # fails at any point.
            connection.rollback()
            raise

    # Retrieve the updated pathway from SQLite.
    return get_saved_pathway(
        pathway_id,
        database_path
    )

# --------------------------------------------------
# STE-07: Explicit pathway approval
# --------------------------------------------------

def approve_saved_pathway(
    pathway_id: str,
    expected_revision: int,
    confirmed: bool,
    database_path=None
) -> dict:
    """
    Approve the current saved pathway revision only
    after an explicit confirmation.

    Approval is rejected if the pathway has changed,
    contains no included steps, or the student has
    not explicitly confirmed their review.
    """

    # Require a valid revision number.
    if (
        type(expected_revision) is not int
        or expected_revision < 1
    ):
        raise ValueError(
            "Expected revision must be a positive integer."
        )

    # Do not interpret strings or other truthy values
    # as approval. Confirmation must be exactly True.
    if confirmed is not True:
        raise ValueError(
            "Explicit pathway approval is required."
        )

    timestamp = datetime.now(
        timezone.utc
    ).isoformat(timespec="seconds")

    with closing(
        open_pathway_database(database_path)
    ) as connection:

        # Lock the database while validating and
        # recording approval to prevent stale approval.
        connection.execute("BEGIN IMMEDIATE")

        try:
            pathway = connection.execute(
                """
                SELECT revision
                FROM pathways
                WHERE id = ?
                """,
                (pathway_id,)
            ).fetchone()

            if pathway is None:
                raise LookupError(
                    "Pathway not found."
                )

            # Approval must apply to the exact version
            # the student reviewed.
            if pathway["revision"] != expected_revision:
                raise PathwayRevisionConflict(
                    "Pathway revision has changed. "
                    "Retrieve and review the latest "
                    "version before approving."
                )

            # A pathway with no included actions
            # must not be approved.
            included_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM pathway_steps
                WHERE pathway_id = ?
                  AND is_included = 1
                """,
                (pathway_id,)
            ).fetchone()[0]

            if included_count == 0:
                raise ValueError(
                    "Cannot approve a pathway with "
                    "no included steps."
                )

            # Record approval for the current revision.
            # Export permission is calculated from
            # this saved approval record.
            cursor = connection.execute(
                """
                UPDATE pathways
                SET approved_revision = revision,
                    approved_at = ?,
                    updated_at = ?
                WHERE id = ?
                  AND revision = ?
                """,
                (
                    timestamp,
                    timestamp,
                    pathway_id,
                    expected_revision
                )
            )

            if cursor.rowcount != 1:
                raise PathwayRevisionConflict(
                    "Pathway changed during approval."
                )

            connection.commit()

        except Exception:
            # Never leave behind partial approval.
            connection.rollback()
            raise

    # Retrieve the approved state from SQLite.
    return get_saved_pathway(
        pathway_id,
        database_path
    )

# --------------------------------------------------
# STE-07: Protected pathway export
# --------------------------------------------------

def export_approved_pathway(
    pathway_id: str,
    expected_revision: int,
    database_path=None
) -> dict:
    """
    Prepare an approved pathway for JSON export.

    Export is rejected unless the saved approval
    applies to the current pathway revision.

    All approval checks and exported content are
    read from one consistent SQLite transaction.
    """

    # Validate the requested pathway revision.
    if (
        type(expected_revision) is not int
        or expected_revision < 1
    ):
        raise ValueError(
            "Expected revision must be a positive integer."
        )

    with closing(
        open_pathway_database(database_path)
    ) as connection:

        # This operation must never modify the database.
        connection.execute("PRAGMA query_only = ON")

        # Keep approval and step reads in one snapshot.
        connection.execute("BEGIN")

        try:
            pathway = connection.execute(
                """
                SELECT *
                FROM pathways
                WHERE id = ?
                """,
                (pathway_id,)
            ).fetchone()

            if pathway is None:
                raise LookupError(
                    "Pathway not found."
                )

            # Reject requests based on outdated versions.
            if pathway["revision"] != expected_revision:
                raise PathwayRevisionConflict(
                    "Pathway revision has changed. "
                    "Retrieve the latest version before exporting."
                )

            # Require a saved approval for the exact
            # version being exported.
            approved = (
                pathway["approved_revision"] is not None
                and pathway["approved_revision"]
                == pathway["revision"]
                and pathway["approved_at"] is not None
            )

            if not approved:
                raise PermissionError(
                    "Export blocked. The current pathway "
                    "revision has not been approved."
                )

            # Export only actions included in the plan.
            step_rows = connection.execute(
                """
                SELECT *
                FROM pathway_steps
                WHERE pathway_id = ?
                  AND is_included = 1
                ORDER BY position
                """,
                (pathway_id,)
            ).fetchall()

            if not step_rows:
                raise PermissionError(
                    "Export blocked. The pathway contains "
                    "no included actions."
                )

            exported_steps = []

            for position, row in enumerate(
                step_rows,
                start=1
            ):

                # Keep original generated information
                # separate from student-edited content.
                original_step = (
                    json.loads(row["source_step_json"])
                    if row["source_step_json"] is not None
                    else None
                )

                if row["origin"] == "generated":

                    display_title = (
                        row["title_override"]
                        if row["title_override"] is not None
                        else original_step["title"]
                    )

                elif row["origin"] == "student":

                    display_title = row["student_title"]

                else:
                    raise ValueError(
                        "Unsupported pathway step origin."
                    )

                exported_steps.append({
                    "position": position,
                    "origin": row["origin"],
                    "title": display_title,
                    "student_note": row["student_note"],
                    "original_source_step": original_step
                })

            # Preserve the original catalogue snapshot
            # for transparency and source traceability.
            source_snapshot = json.loads(
                pathway["source_snapshot_json"]
            )

            result = {
                "export_type": "approved_pathway",
                "pathway_id": pathway["id"],
                "opportunity_id": pathway["opportunity_id"],
                "opportunity_title": pathway["opportunity_title"],
                "reference_date": pathway["reference_date"],
                "revision": pathway["revision"],
                "approved_revision": (
                    pathway["approved_revision"]
                ),
                "approved_at": pathway["approved_at"],
                "status": "approved",
                "steps": exported_steps,
                "source_snapshot": source_snapshot,
                "notice": (
                    "This student-approved pathway is "
                    "informational only. It does not "
                    "represent an official eligibility "
                    "or admission decision. Verify "
                    "current requirements and deadlines "
                    "with the opportunity provider."
                )
            }

            return result

        finally:
            # End the read-only snapshot transaction.
            connection.rollback()

# --------------------------------------------------
# STE-07: Add student-created pathway actions
# --------------------------------------------------

def add_student_step(
    pathway_id: str,
    expected_revision: int,
    title: str,
    student_note: str = "",
    included: bool = True,
    database_path=None
) -> dict:
    """
    Add a student-created action to a saved pathway.

    Student-created actions are kept separate from
    generated requirements and source evidence.

    Adding an action increments the pathway revision
    and invalidates any previous approval.
    """

    # Validate the expected revision.
    if (
        type(expected_revision) is not int
        or expected_revision < 1
    ):
        raise ValueError(
            "Expected revision must be a positive integer."
        )

    # Validate the action title.
    if not isinstance(title, str):
        raise ValueError(
            "Title must be a string."
        )

    clean_title = title.strip()

    if not clean_title or len(clean_title) > 200:
        raise ValueError(
            "Title must contain 1 to 200 characters."
        )

    # Validate the student note.
    if (
        not isinstance(student_note, str)
        or len(student_note) > 2000
    ):
        raise ValueError(
            "Student note must contain at most 2000 characters."
        )

    if type(included) is not bool:
        raise ValueError(
            "Included must be a boolean."
        )

    timestamp = datetime.now(
        timezone.utc
    ).isoformat(timespec="seconds")

    step_id = str(uuid4())

    with closing(
        open_pathway_database(database_path)
    ) as connection:

        # Lock the database to prevent simultaneous
        # additions from using the same position.
        connection.execute("BEGIN IMMEDIATE")

        try:

            pathway = connection.execute(
                """
                SELECT revision
                FROM pathways
                WHERE id = ?
                """,
                (pathway_id,)
            ).fetchone()

            if pathway is None:
                raise LookupError(
                    "Pathway not found."
                )

            # Refuse edits based on an outdated version.
            if pathway["revision"] != expected_revision:
                raise PathwayRevisionConflict(
                    "Pathway revision has changed. "
                    "Retrieve the latest version "
                    "before adding an action."
                )

            # Append the new action after existing steps.
            next_position = connection.execute(
                """
                SELECT COALESCE(MAX(position), 0) + 1
                FROM pathway_steps
                WHERE pathway_id = ?
                """,
                (pathway_id,)
            ).fetchone()[0]

            # A student-created action does not
            # impersonate a generated requirement.
            connection.execute(
                """
                INSERT INTO pathway_steps (
                    id,
                    pathway_id,
                    position,
                    origin,
                    source_step_id,
                    source_step_json,
                    title_override,
                    student_title,
                    student_note,
                    is_included
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    step_id,
                    pathway_id,
                    next_position,
                    "student",
                    None,
                    None,
                    None,
                    clean_title,
                    student_note,
                    int(included)
                )
            )

            # Any change to pathway content must
            # invalidate the previously approved version.
            connection.execute(
                """
                UPDATE pathways
                SET revision = revision + 1,
                    approved_revision = NULL,
                    approved_at = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    timestamp,
                    pathway_id
                )
            )

            connection.commit()

        except Exception:

            # Prevent partially saved student actions.
            connection.rollback()
            raise

    return get_saved_pathway(
        pathway_id,
        database_path
    )

# --------------------------------------------------
# STE-07: Reorder saved pathway actions
# --------------------------------------------------

def reorder_saved_steps(
    pathway_id: str,
    expected_revision: int,
    step_ids: list[str],
    database_path=None
) -> dict:
    """
    Reorder every action in a saved pathway.

    The supplied IDs must contain every existing step
    exactly once, without additional or missing IDs.

    Actual changes increment the pathway revision
    and invalidate approval.

    An unchanged order does not create a new revision.
    """

    # Validate revision.
    if (
        type(expected_revision) is not int
        or expected_revision < 1
    ):
        raise ValueError(
            "Expected revision must be a positive integer."
        )

    # Require an ordered list of valid step IDs.
    if (
        type(step_ids) is not list
        or not step_ids
    ):
        raise ValueError(
            "Step IDs must be a non-empty list."
        )

    if any(
        type(step_id) is not str
        or not step_id
        or step_id != step_id.strip()
        for step_id in step_ids
    ):
        raise ValueError(
            "Every step ID must be a non-empty string."
        )

    if len(set(step_ids)) != len(step_ids):
        raise ValueError(
            "Step IDs must not contain duplicates."
        )

    timestamp = datetime.now(
        timezone.utc
    ).isoformat(timespec="seconds")

    with closing(
        open_pathway_database(database_path)
    ) as connection:

        # Prevent another write from changing the
        # pathway while we validate and reorder it.
        connection.execute("BEGIN IMMEDIATE")

        try:
            pathway = connection.execute(
                """
                SELECT revision
                FROM pathways
                WHERE id = ?
                """,
                (pathway_id,)
            ).fetchone()

            if pathway is None:
                raise LookupError(
                    "Pathway not found."
                )

            if pathway["revision"] != expected_revision:
                raise PathwayRevisionConflict(
                    "Pathway revision has changed. "
                    "Retrieve the latest version "
                    "before reordering."
                )

            # Read all current steps in their saved order.
            existing_steps = connection.execute(
                """
                SELECT id, position
                FROM pathway_steps
                WHERE pathway_id = ?
                ORDER BY position
                """,
                (pathway_id,)
            ).fetchall()

            current_ids = [
                row["id"]
                for row in existing_steps
            ]

            # Prevent missing, duplicated or foreign
            # pathway steps from entering the new order.
            if (
                len(step_ids) != len(current_ids)
                or set(step_ids) != set(current_ids)
            ):
                raise ValueError(
                    "The new order must contain every "
                    "step from this pathway exactly once."
                )

            # An unchanged order should not revoke
            # an otherwise valid approval.
            if step_ids != current_ids:

                # SQLite requires each pathway position
                # to be unique. Move every step into a
                # temporary position above the current
                # maximum before assigning final values.
                temporary_base = max(
                    row["position"]
                    for row in existing_steps
                )

                # Phase 1: Assign unique temporary
                # positions outside the existing range.
                for index, step_id in enumerate(
                    step_ids,
                    start=1
                ):
                    connection.execute(
                        """
                        UPDATE pathway_steps
                        SET position = ?
                        WHERE id = ?
                          AND pathway_id = ?
                        """,
                        (
                            temporary_base + index,
                            step_id,
                            pathway_id
                        )
                    )

                # Phase 2: Assign final sequential
                # positions, starting from 1.
                for index, step_id in enumerate(
                    step_ids,
                    start=1
                ):
                    connection.execute(
                        """
                        UPDATE pathway_steps
                        SET position = ?
                        WHERE id = ?
                          AND pathway_id = ?
                        """,
                        (
                            index,
                            step_id,
                            pathway_id
                        )
                    )

                # A genuine order change invalidates
                # the previously approved revision.
                connection.execute(
                    """
                    UPDATE pathways
                    SET revision = revision + 1,
                        approved_revision = NULL,
                        approved_at = NULL,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        timestamp,
                        pathway_id
                    )
                )

            # Commit the complete reorder atomically.
            connection.commit()

        except Exception:
            # Leave all original positions and approval
            # unchanged if any operation fails.
            connection.rollback()
            raise

    return get_saved_pathway(
        pathway_id,
        database_path
    )
