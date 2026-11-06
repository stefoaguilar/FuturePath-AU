
import json
import sqlite3
from pathlib import Path

from database import DATABASE_PATH


# Find the source dataset in the shared project.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = PROJECT_ROOT / "data" / "opportunities.json"


def import_opportunities():
    # Read Samer's original dataset.
    with DATA_FILE.open("r", encoding="utf-8") as file:
        dataset = json.load(file)

    opportunities = dataset["opportunities"]

    if not isinstance(opportunities, list) or not opportunities:
        raise ValueError("Expected a non-empty opportunities list.")

    # Check IDs before making any database changes.
    opportunity_ids = [item["id"] for item in opportunities]

    condition_ids = [
        condition["id"]
        for item in opportunities
        for condition in item["eligibility_conditions"]
    ]

    if len(opportunity_ids) != len(set(opportunity_ids)):
        raise ValueError("Duplicate opportunity IDs detected.")

    if len(condition_ids) != len(set(condition_ids)):
        raise ValueError("Duplicate eligibility condition IDs detected.")

    # The database must already have the Part 1 tables.
    if not DATABASE_PATH.is_file():
        raise FileNotFoundError(
            "Database not found. Run database.py first."
        )

    connection = sqlite3.connect(DATABASE_PATH)
    connection.execute("PRAGMA foreign_keys = ON")

    try:
        # All changes are committed together.
        # If an error occurs, this transaction rolls back.
        with connection:

            # Rebuild only the development catalogue tables.
            # Samer's JSON remains the source of truth.
            connection.execute("DELETE FROM eligibility_conditions")
            connection.execute("DELETE FROM opportunities")
            connection.execute("DELETE FROM dataset_metadata")

            # Preserve the dataset's original metadata.
            connection.executemany(
                """
                INSERT INTO dataset_metadata (key, value)
                VALUES (?, ?)
                """,
                [
                    ("schema_version", dataset.get("schema_version", "")),
                    ("dataset_note", dataset.get("dataset_note", ""))
                ]
            )

            # Import each opportunity in its original order.
            for position, item in enumerate(opportunities, start=1):

                connection.execute(
                    """
                    INSERT INTO opportunities (
                        id, position, record_type, title,
                        provider, category, location, study_level,
                        summary, skills_json, source_url,
                        deadline_json, verification_json, data_notes
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["id"],
                        position,
                        item["record_type"],
                        item["title"],
                        item["provider"],
                        item["category"],
                        item["location"],
                        item["study_level"],
                        item["summary"],
                        json.dumps(item.get("skills", []), ensure_ascii=False),
                        item["source_url"],
                        json.dumps(item["deadline"], ensure_ascii=False),
                        json.dumps(item["verification"], ensure_ascii=False),
                        item.get("data_notes", "")
                    )
                )

                # Import conditions belonging to this opportunity.
                for condition_position, condition in enumerate(
                    item["eligibility_conditions"], start=1
                ):
                    if not isinstance(
                        condition["checkable_from_profile"], bool
                    ):
                        raise ValueError(
                            f"Invalid checkable_from_profile: {condition['id']}"
                        )

                    connection.execute(
                        """
                        INSERT INTO eligibility_conditions (
                            id, opportunity_id, position, type,
                            text, evidence_summary, source_url,
                            checkable_from_profile
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            condition["id"],
                            item["id"],
                            condition_position,
                            condition["type"],
                            condition["text"],
                            condition["evidence_summary"],
                            condition["source_url"],
                            int(condition["checkable_from_profile"])
                        )
                    )

        # Confirm how much data is now stored.
        opportunity_count = connection.execute(
            "SELECT COUNT(*) FROM opportunities"
        ).fetchone()[0]

        condition_count = connection.execute(
            "SELECT COUNT(*) FROM eligibility_conditions"
        ).fetchone()[0]

        foreign_key_issues = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        print("FuturePath AU import completed successfully!")
        print(f"Opportunities imported: {opportunity_count}")
        print(f"Eligibility conditions imported: {condition_count}")
        print(f"Foreign-key issues: {len(foreign_key_issues)}")

    finally:
        connection.close()


if __name__ == "__main__":
    import_opportunities()
