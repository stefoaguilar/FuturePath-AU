
import sqlite3
from pathlib import Path


# Store the database inside our backend folder.
DATABASE_PATH = Path(__file__).resolve().parent / "futurepath.db"


def create_database():
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        # Enforce relationships between database tables.
        connection.execute("PRAGMA foreign_keys = ON")

        # Create the tables if they do not already exist.
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
        """)

        connection.commit()

        # Display the tables created in SQLite.
        tables = connection.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
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
