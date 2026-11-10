
import sqlite3
from pathlib import Path


# Store the database inside our backend folder.
DATABASE_PATH = Path(__file__).resolve().parent / "futurepath.db"


def create_database():
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        # Enforce relationships between database tables.
        connection.execute("PRAGMA foreign_keys = ON")

        # Create tables without deleting existing records.
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS dataset_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS opportunities (
                id TEXT PRIMARY KEY,
                position INTEGER NOT NULL UNIQUE,
                record_type TEXT NOT NULL,
                title TEXT NOT NULL,
                provider TEXT NOT NULL,
                category TEXT NOT NULL,
                location TEXT NOT NULL,
                study_level TEXT NOT NULL,
                summary TEXT NOT NULL,
                skills_json TEXT NOT NULL,
                source_url TEXT NOT NULL,
                deadline_json TEXT NOT NULL,
                verification_json TEXT NOT NULL,
                data_notes TEXT
            );

            CREATE TABLE IF NOT EXISTS eligibility_conditions (
                id TEXT PRIMARY KEY,
                opportunity_id TEXT NOT NULL,
                position INTEGER NOT NULL,
                type TEXT NOT NULL,
                text TEXT NOT NULL,
                evidence_summary TEXT NOT NULL,
                source_url TEXT NOT NULL,
                checkable_from_profile INTEGER NOT NULL
                    CHECK (checkable_from_profile IN (0, 1)),

                FOREIGN KEY (opportunity_id)
                    REFERENCES opportunities(id)
                    ON DELETE CASCADE,

                UNIQUE (opportunity_id, position)
            );

            -- -------------------------------------------
            -- STE-07: Saved student pathways
            -- -------------------------------------------

            CREATE TABLE IF NOT EXISTS pathways (
                id TEXT PRIMARY KEY,

                -- Catalogue ID is informational, not a
                -- foreign key. Catalogue reimports must
                -- not delete saved pathways.
                opportunity_id TEXT NOT NULL,
                opportunity_title TEXT NOT NULL,

                reference_date TEXT NOT NULL,

                -- Snapshot of original source information.
                source_snapshot_json TEXT NOT NULL,

                -- Every edit creates a new revision.
                revision INTEGER NOT NULL DEFAULT 1
                    CHECK (revision >= 1),

                -- Approval applies to a specific revision.
                approved_revision INTEGER,
                approved_at TEXT,

                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,

                CHECK (
                    approved_revision IS NULL
                    OR (
                        approved_revision >= 1
                        AND approved_revision <= revision
                    )
                ),

                CHECK (
                    (
                        approved_revision IS NULL
                        AND approved_at IS NULL
                    )
                    OR
                    (
                        approved_revision IS NOT NULL
                        AND approved_at IS NOT NULL
                    )
                )
            );

            -- -------------------------------------------
            -- STE-07: Editable pathway steps
            -- -------------------------------------------

            CREATE TABLE IF NOT EXISTS pathway_steps (
                id TEXT PRIMARY KEY,
                pathway_id TEXT NOT NULL,

                position INTEGER NOT NULL
                    CHECK (position >= 1),

                -- Generated steps retain their source.
                -- Student-created steps are separate.
                origin TEXT NOT NULL
                    CHECK (
                        origin IN ('generated', 'student')
                    ),

                source_step_id TEXT,
                source_step_json TEXT,

                -- Student-editable information.
                title_override TEXT,
                student_title TEXT,
                student_note TEXT NOT NULL DEFAULT '',

                is_included INTEGER NOT NULL DEFAULT 1
                    CHECK (is_included IN (0, 1)),

                FOREIGN KEY (pathway_id)
                    REFERENCES pathways(id)
                    ON DELETE CASCADE,

                -- A step must have the correct structure
                -- for its origin.
                CHECK (
                    (
                        origin = 'generated'
                        AND source_step_id IS NOT NULL
                        AND source_step_json IS NOT NULL
                        AND student_title IS NULL
                    )
                    OR
                    (
                        origin = 'student'
                        AND source_step_id IS NULL
                        AND source_step_json IS NULL
                        AND student_title IS NOT NULL
                    )
                ),

                UNIQUE (pathway_id, position),
                UNIQUE (pathway_id, source_step_id)
            );

            CREATE INDEX IF NOT EXISTS
                idx_pathways_opportunity
                ON pathways(opportunity_id);

            CREATE INDEX IF NOT EXISTS
                idx_pathway_steps_pathway
                ON pathway_steps(pathway_id);
        """)

        connection.commit()

        # Display the tables created in SQLite.
        tables = connection.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """).fetchall()

        print("FuturePath AU database created successfully!")
        print(f"Database location: {DATABASE_PATH}")
        print("Database tables:")

        for table in tables:
            print(f" - {table[0]}")

    finally:
        connection.close()


if __name__ == "__main__":
    create_database()
