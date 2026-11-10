
import unittest
import os
import sqlite3
from contextlib import closing

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from database import create_database
from import_data import import_opportunities
from main import app
from pathway_storage import (
    edit_saved_step,
    approve_saved_pathway
)


class TestAPIEndpoints(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Create a temporary folder for the test database.
        cls.temp_dir = TemporaryDirectory()
        cls.addClassCleanup(cls.temp_dir.cleanup)

        test_db_path = (
            Path(cls.temp_dir.name) / "futurepath_test.db"
        )

        # Redirect database operations to the temporary file.
        # The original futurepath.db will not be modified.
        for module_name in ("database", "import_data", "main"):
            database_patch = patch(
                f"{module_name}.DATABASE_PATH",
                test_db_path
            )

            database_patch.start()
            cls.addClassCleanup(database_patch.stop)

        # Create the schema and import Samer's source dataset.
        create_database()
        import_opportunities()

        # Initialise the FastAPI testing client.
        cls.client = TestClient(app)

    # --------------------------------------------------
    # Existing API tests
    # --------------------------------------------------

    def test_health_endpoint(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_opportunities_endpoint(self):
        response = self.client.get("/api/opportunities")

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertIn("opportunities", data)
        self.assertTrue(
            any(
                item["id"] == "OPP-003"
                for item in data["opportunities"]
            )
        )

    def test_valid_eligibility_profile(self):
        response = self.client.post(
            "/api/eligibility/evaluate",
            json={
                "opportunity_id": "OPP-003",
                "profile": {
                    "citizenship_status": "australian_citizen",
                    "weighted_average": 65
                }
            }
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["opportunity_id"], "OPP-003")

        statuses = {
            item["condition_id"]: item["status"]
            for item in data["results"]
        }

        self.assertEqual(len(statuses), 6)

        self.assertEqual(
            statuses["OPP-003-E1"],
            "uncertain"
        )

        self.assertEqual(
            statuses["OPP-003-E2"],
            "satisfied"
        )

        self.assertEqual(
            statuses["OPP-003-E4"],
            "satisfied"
        )

        self.assertIn("informational", data["notice"])

    def test_empty_profile(self):
        response = self.client.post(
            "/api/eligibility/evaluate",
            json={
                "opportunity_id": "OPP-003",
                "profile": {}
            }
        )

        self.assertEqual(response.status_code, 200)

        results = response.json()["results"]

        self.assertEqual(len(results), 6)

        self.assertTrue(
            all(
                item["status"] == "uncertain"
                for item in results
            )
        )

    def test_full_default_profile(self):
        response = self.client.post(
            "/api/eligibility/evaluate",
            json={
                "opportunity_id": "OPP-003",
                "profile": {
                    "education_level": "not_stated",
                    "enrolment_status": "not_stated",
                    "institution": "",
                    "citizenship_status": "not_stated",
                    "state": "not_stated",
                    "field_of_study": "",
                    "weighted_average": None,
                    "skills": [],
                    "experience_notes": "",
                    "preferred_agencies": [],
                    "identity_answer": "not_stated"
                }
            }
        )

        self.assertEqual(response.status_code, 200)

        results = response.json()["results"]

        self.assertEqual(len(results), 6)

        self.assertTrue(
            all(
                item["status"] == "uncertain"
                for item in results
            )
        )

    def test_unmet_citizenship_requirement(self):
        response = self.client.post(
            "/api/eligibility/evaluate",
            json={
                "opportunity_id": "OPP-003",
                "profile": {
                    "citizenship_status": "nz_citizen",
                    "weighted_average": 65
                }
            }
        )

        self.assertEqual(response.status_code, 200)

        statuses = {
            item["condition_id"]: item["status"]
            for item in response.json()["results"]
        }

        self.assertEqual(
            statuses["OPP-003-E2"],
            "unmet"
        )

        self.assertEqual(
            statuses["OPP-003-E4"],
            "satisfied"
        )

    def test_invalid_citizenship_returns_422(self):
        response = self.client.post(
            "/api/eligibility/evaluate",
            json={
                "opportunity_id": "OPP-003",
                "profile": {
                    "citizenship_status": "banana"
                }
            }
        )

        self.assertEqual(response.status_code, 422)

        errors = response.json()["detail"]

        self.assertTrue(
            any(
                error["loc"] == [
                    "body",
                    "profile",
                    "citizenship_status"
                ]
                for error in errors
            )
        )

    def test_invalid_average_returns_422(self):
        response = self.client.post(
            "/api/eligibility/evaluate",
            json={
                "opportunity_id": "OPP-003",
                "profile": {
                    "weighted_average": 150
                }
            }
        )

        self.assertEqual(response.status_code, 422)

        errors = response.json()["detail"]

        self.assertTrue(
            any(
                error["type"] == "less_than_equal"
                for error in errors
            )
        )

    def test_unknown_opportunity_returns_404(self):
        response = self.client.post(
            "/api/eligibility/evaluate",
            json={
                "opportunity_id": "OPP-999",
                "profile": {}
            }
        )

        self.assertEqual(response.status_code, 404)

        self.assertEqual(
            response.json()["detail"],
            "Opportunity not found."
        )

    def test_missing_profile_returns_422(self):
        response = self.client.post(
            "/api/eligibility/evaluate",
            json={
                "opportunity_id": "OPP-003"
            }
        )

        self.assertEqual(response.status_code, 422)

    # --------------------------------------------------
    # STE-05: Gap-analysis API tests
    # --------------------------------------------------

    def test_gap_analysis_valid_profile(self):
        response = self.client.post(
            "/api/gaps/analyse",
            json={
                "opportunity_id": "OPP-003",
                "profile": {
                    "citizenship_status": "nz_citizen",
                    "weighted_average": 65,
                    "skills": ["cyber security"]
                }
            }
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertEqual(
            data["opportunity_id"],
            "OPP-003"
        )

        unmet_ids = [
            item["condition_id"]
            for item in data["confirmed_unmet_requirements"]
        ]

        review_ids = [
            item["condition_id"]
            for item in data["requirements_needing_review"]
        ]

        # The Australian citizenship requirement is unmet.
        self.assertEqual(
            unmet_ids,
            ["OPP-003-E2"]
        )

        # Unsupported conditions must remain uncertain.
        self.assertEqual(
            review_ids,
            [
                "OPP-003-E1",
                "OPP-003-E3",
                "OPP-003-E5",
                "OPP-003-E6"
            ]
        )

        # Cyber security is already reported by the student.
        # Other skill areas are advisory only.
        self.assertEqual(
            data["skills_to_explore"],
            [
                "computing",
                "software engineering",
                "data science",
                "networking"
            ]
        )

        # Preserve the source and advisory disclaimer.
        self.assertIn("source_url", data)

        self.assertIn(
            "not verified missing",
            data["notice"]
        )

    def test_gap_analysis_unknown_opportunity(self):
        response = self.client.post(
            "/api/gaps/analyse",
            json={
                "opportunity_id": "OPP-999",
                "profile": {}
            }
        )

        self.assertEqual(response.status_code, 404)

        self.assertEqual(
            response.json()["detail"],
            "Opportunity not found."
        )

    def test_gap_analysis_invalid_profile(self):
        response = self.client.post(
            "/api/gaps/analyse",
            json={
                "opportunity_id": "OPP-003",
                "profile": {
                    "citizenship_status": "banana",
                    "weighted_average": 150
                }
            }
        )

        self.assertEqual(response.status_code, 422)

        errors = response.json()["detail"]

        invalid_fields = {
            error["loc"][-1]
            for error in errors
        }

        self.assertIn(
            "citizenship_status",
            invalid_fields
        )

        self.assertIn(
            "weighted_average",
            invalid_fields
        )


    # --------------------------------------------------
    # STE-06: Deadline-tracking API tests
    # --------------------------------------------------

    def test_deadline_future(self):
        response = self.client.get(
            "/api/deadlines/OPP-030",
            params={"reference_date": "2026-11-10"}
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertEqual(data["opportunity_id"], "OPP-030")
        self.assertEqual(data["classification"], "deadline_future")
        self.assertEqual(data["deadline_date"], "2026-11-30")
        self.assertEqual(data["days_until_deadline"], 20)
        self.assertEqual(data["reference_date"], "2026-11-10")
        self.assertEqual(data["verification_status"], "verified")
        self.assertIn("Round 2", data["deadline_note"])

    def test_deadline_passed(self):
        response = self.client.get(
            "/api/deadlines/OPP-004",
            params={"reference_date": "2026-11-10"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["classification"],
            "deadline_passed"
        )
        self.assertEqual(
            response.json()["days_until_deadline"],
            -10
        )

    def test_deadline_unknown(self):
        response = self.client.get(
            "/api/deadlines/OPP-001",
            params={"reference_date": "2026-11-10"}
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertEqual(data["classification"], "unknown")
        self.assertIsNone(data["days_until_deadline"])

    def test_deadline_conflicting_verification(self):
        response = self.client.get(
            "/api/deadlines/OPP-002",
            params={"reference_date": "2026-11-10"}
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertEqual(data["classification"], "needs_review")
        self.assertEqual(
            data["verification_status"],
            "conflicting"
        )

    def test_deadline_unknown_opportunity(self):
        response = self.client.get(
            "/api/deadlines/OPP-999",
            params={"reference_date": "2026-11-10"}
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["detail"],
            "Opportunity not found."
        )

    # --------------------------------------------------
    # STE-07: Pathway-generation API tests
    # --------------------------------------------------

    def test_pathway_generate_valid_draft(self):
        response = self.client.post(
            "/api/pathways/generate",
            params={"reference_date": "2026-11-28"},
            json={
                "opportunity_id": "OPP-005",
                "profile": {
                    "education_level": "undergraduate",
                    "citizenship_status": "australian_citizen"
                }
            }
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertEqual(data["opportunity_id"], "OPP-005")
        self.assertEqual(data["reference_date"], "2026-11-28")
        self.assertEqual(data["status"], "draft")
        self.assertFalse(data["approved"])
        self.assertFalse(data["can_export"])
        self.assertEqual(len(data["steps"]), 5)

        step_ids = {
            step["step_id"]
            for step in data["steps"]
        }

        self.assertIn("requirement:OPP-005-E1", step_ids)
        self.assertIn("deadline:review", step_ids)
        self.assertIn("source:verify", step_ids)

    def test_pathway_generate_unknown_opportunity(self):
        response = self.client.post(
            "/api/pathways/generate",
            params={"reference_date": "2026-11-28"},
            json={
                "opportunity_id": "OPP-999",
                "profile": {}
            }
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["detail"],
            "Opportunity not found."
        )

    def test_pathway_generate_invalid_profile(self):
        response = self.client.post(
            "/api/pathways/generate",
            json={
                "opportunity_id": "OPP-005",
                "profile": {
                    "citizenship_status": "invalid_value",
                    "weighted_average": 150
                }
            }
        )

        self.assertEqual(response.status_code, 422)

    def test_pathway_generate_invalid_reference_date(self):
        response = self.client.post(
            "/api/pathways/generate",
            params={"reference_date": "not-a-date"},
            json={
                "opportunity_id": "OPP-005",
                "profile": {}
            }
        )

        self.assertEqual(response.status_code, 422)

    def test_pathway_identity_answer_never_changes_output(self):
        base_request = {
            "opportunity_id": "OPP-005",
            "profile": {
                "education_level": "undergraduate",
                "citizenship_status": "australian_citizen"
            }
        }

        response_yes = self.client.post(
            "/api/pathways/generate",
            params={"reference_date": "2026-11-28"},
            json={
                **base_request,
                "profile": {
                    **base_request["profile"],
                    "identity_answer": "yes"
                }
            }
        )

        response_no = self.client.post(
            "/api/pathways/generate",
            params={"reference_date": "2026-11-28"},
            json={
                **base_request,
                "profile": {
                    **base_request["profile"],
                    "identity_answer": "no"
                }
            }
        )

        self.assertEqual(response_yes.status_code, 200)
        self.assertEqual(response_no.status_code, 200)
        self.assertEqual(
            response_yes.json(),
            response_no.json()
        )

    # --------------------------------------------------
    # STE-07: Protected pathway-saving API tests
    # --------------------------------------------------

    def test_pathway_save_disabled_without_configuration(self):

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": ""}
        ):

            with TestClient(
                app,
                client=("127.0.0.1", 50000)
            ) as local_client:

                response = local_client.post(
                    "/api/pathways/save",
                    json={
                        "opportunity_id": "OPP-005",
                        "profile": {}
                    }
                )

        self.assertEqual(response.status_code, 503)

    def test_pathway_save_rejects_invalid_key(self):

        test_key = "test-only-" + ("A" * 40)

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": test_key}
        ):

            with TestClient(
                app,
                client=("127.0.0.1", 50000)
            ) as local_client:

                response = local_client.post(
                    "/api/pathways/save",
                    headers={
                        "X-FuturePath-Dev-Key": "wrong-key"
                    },
                    json={
                        "opportunity_id": "OPP-005",
                        "profile": {}
                    }
                )

        self.assertEqual(response.status_code, 401)

    def test_pathway_save_rejects_nonlocal_client(self):

        test_key = "test-only-" + ("A" * 40)

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": test_key}
        ):

            # The existing TestClient uses "testclient"
            # as its simulated client address.
            # This must not pass the localhost guard.
            response = self.client.post(
                "/api/pathways/save",
                headers={
                    "X-FuturePath-Dev-Key": test_key
                },
                json={
                    "opportunity_id": "OPP-005",
                    "profile": {}
                }
            )

        self.assertEqual(response.status_code, 403)

    def test_pathway_save_creates_unapproved_database_record(self):

        test_key = "test-only-" + ("A" * 40)

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": test_key}
        ):

            with TestClient(
                app,
                client=("127.0.0.1", 50000)
            ) as local_client:

                response = local_client.post(
                    "/api/pathways/save",
                    params={
                        "reference_date": "2026-11-28"
                    },
                    headers={
                        "X-FuturePath-Dev-Key": test_key
                    },
                    json={
                        "opportunity_id": "OPP-005",
                        "profile": {
                            "education_level": "undergraduate",
                            "citizenship_status": "australian_citizen",
                            "identity_answer": "yes"
                        }
                    }
                )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertTrue(data["pathway_id"])
        self.assertEqual(data["opportunity_id"], "OPP-005")
        self.assertEqual(data["reference_date"], "2026-11-28")
        self.assertEqual(data["revision"], 1)
        self.assertEqual(data["status"], "draft")

        self.assertFalse(data["approved"])
        self.assertFalse(data["can_export"])
        self.assertIsNone(data["approved_revision"])

        self.assertEqual(len(data["steps"]), 5)

        # Verify the pathway was actually persisted
        # in the temporary SQLite database.
        import main

        with closing(
            sqlite3.connect(main.DATABASE_PATH)
        ) as connection:

            record = connection.execute(
                """
                SELECT
                    opportunity_id,
                    revision,
                    approved_revision,
                    source_snapshot_json
                FROM pathways
                WHERE id = ?
                """,
                (data["pathway_id"],)
            ).fetchone()

            step_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM pathway_steps
                WHERE pathway_id = ?
                """,
                (data["pathway_id"],)
            ).fetchone()[0]

        self.assertIsNotNone(record)
        self.assertEqual(record[0], "OPP-005")
        self.assertEqual(record[1], 1)
        self.assertIsNone(record[2])
        self.assertEqual(step_count, 5)

        # The saved opportunity snapshot must not
        # contain the student's profile answers.
        import json

        snapshot = json.loads(record[3])

        self.assertNotIn("profile", snapshot)
        self.assertNotIn("identity_answer", snapshot)

    def test_pathway_save_rejects_unknown_opportunity(self):

        test_key = "test-only-" + ("A" * 40)

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": test_key}
        ):

            with TestClient(
                app,
                client=("127.0.0.1", 50000)
            ) as local_client:

                response = local_client.post(
                    "/api/pathways/save",
                    headers={
                        "X-FuturePath-Dev-Key": test_key
                    },
                    json={
                        "opportunity_id": "OPP-999",
                        "profile": {}
                    }
                )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["detail"],
            "Opportunity not found."
        )

    def test_pathway_save_rejects_invalid_profile(self):

        test_key = "test-only-" + ("A" * 40)

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": test_key}
        ):

            with TestClient(
                app,
                client=("127.0.0.1", 50000)
            ) as local_client:

                response = local_client.post(
                    "/api/pathways/save",
                    headers={
                        "X-FuturePath-Dev-Key": test_key
                    },
                    json={
                        "opportunity_id": "OPP-005",
                        "profile": {
                            "citizenship_status": "invalid_value",
                            "weighted_average": 150
                        }
                    }
                )

        self.assertEqual(response.status_code, 422)

        invalid_fields = {
            error["loc"][-1]
            for error in response.json()["detail"]
        }

        self.assertIn(
            "citizenship_status",
            invalid_fields
        )

        self.assertIn(
            "weighted_average",
            invalid_fields
        )

    # --------------------------------------------------
    # STE-07: Protected pathway retrieval API tests
    # --------------------------------------------------

    def test_pathway_retrieve_disabled_without_key_configuration(self):

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": ""}
        ):

            with TestClient(
                app,
                client=("127.0.0.1", 50000)
            ) as local_client:

                response = local_client.get(
                    "/api/pathways/saved/example-pathway"
                )

        self.assertEqual(response.status_code, 503)

    def test_pathway_retrieve_rejects_incorrect_key(self):

        test_key = "test-only-" + ("A" * 40)

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": test_key}
        ):

            with TestClient(
                app,
                client=("127.0.0.1", 50000)
            ) as local_client:

                response = local_client.get(
                    "/api/pathways/saved/example-pathway",
                    headers={
                        "X-FuturePath-Dev-Key": "incorrect-key"
                    }
                )

        self.assertEqual(response.status_code, 401)

    def test_pathway_retrieve_rejects_nonlocal_client(self):

        test_key = "test-only-" + ("A" * 40)

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": test_key}
        ):

            # Default TestClient uses a non-loopback
            # client name and must be rejected.
            response = self.client.get(
                "/api/pathways/saved/example-pathway",
                headers={
                    "X-FuturePath-Dev-Key": test_key
                }
            )

        self.assertEqual(response.status_code, 403)

    def test_pathway_retrieve_rejects_unknown_pathway(self):

        test_key = "test-only-" + ("A" * 40)

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": test_key}
        ):

            with TestClient(
                app,
                client=("127.0.0.1", 50000)
            ) as local_client:

                response = local_client.get(
                    "/api/pathways/saved/nonexistent-pathway",
                    headers={
                        "X-FuturePath-Dev-Key": test_key
                    }
                )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["detail"],
            "Saved pathway not found."
        )

    def test_pathway_retrieve_returns_saved_draft(self):

        test_key = "test-only-" + ("A" * 40)

        headers = {
            "X-FuturePath-Dev-Key": test_key
        }

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": test_key}
        ):

            with TestClient(
                app,
                client=("127.0.0.1", 50000)
            ) as local_client:

                # First save a pathway through the API.
                save_response = local_client.post(
                    "/api/pathways/save",
                    params={
                        "reference_date": "2026-11-28"
                    },
                    headers=headers,
                    json={
                        "opportunity_id": "OPP-005",
                        "profile": {
                            "education_level": "undergraduate",
                            "citizenship_status": "australian_citizen"
                        }
                    }
                )

                self.assertEqual(
                    save_response.status_code,
                    200
                )

                saved = save_response.json()
                pathway_id = saved["pathway_id"]

                # Retrieve the same record using GET.
                response = local_client.get(
                    f"/api/pathways/saved/{pathway_id}",
                    headers=headers
                )

        self.assertEqual(response.status_code, 200)

        retrieved = response.json()

        self.assertEqual(
            retrieved["pathway_id"],
            pathway_id
        )

        self.assertEqual(
            retrieved["opportunity_id"],
            "OPP-005"
        )

        self.assertEqual(
            retrieved["reference_date"],
            "2026-11-28"
        )

        self.assertEqual(retrieved["revision"], 1)
        self.assertEqual(retrieved["status"], "draft")
        self.assertFalse(retrieved["approved"])
        self.assertFalse(retrieved["can_export"])

        self.assertEqual(len(retrieved["steps"]), 5)

        # Retrieval should preserve the original
        # generated step IDs and action order.
        self.assertEqual(
            [step["id"] for step in retrieved["steps"]],
            [step["id"] for step in saved["steps"]]
        )

        self.assertEqual(
            [step["position"] for step in retrieved["steps"]],
            [1, 2, 3, 4, 5]
        )

    def test_pathway_retrieve_reflects_edits_and_approval(self):

        import main

        test_key = "test-only-" + ("A" * 40)

        headers = {
            "X-FuturePath-Dev-Key": test_key
        }

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": test_key}
        ):

            with TestClient(
                app,
                client=("127.0.0.1", 50000)
            ) as local_client:

                save_response = local_client.post(
                    "/api/pathways/save",
                    params={
                        "reference_date": "2026-11-28"
                    },
                    headers=headers,
                    json={
                        "opportunity_id": "OPP-005",
                        "profile": {}
                    }
                )

                self.assertEqual(
                    save_response.status_code,
                    200
                )

                saved = save_response.json()

                pathway_id = saved["pathway_id"]
                first_step = saved["steps"][0]

                # Modify the saved record through
                # the already-tested storage function.
                edit_saved_step(
                    pathway_id=pathway_id,
                    step_id=first_step["id"],
                    expected_revision=1,
                    title="My updated pathway action",
                    student_note="Contact the provider first.",
                    included=True,
                    database_path=main.DATABASE_PATH
                )

                # Explicitly approve revision 2.
                approve_saved_pathway(
                    pathway_id=pathway_id,
                    expected_revision=2,
                    confirmed=True,
                    database_path=main.DATABASE_PATH
                )

                # GET must return the latest saved
                # revision, not the original draft.
                response = local_client.get(
                    f"/api/pathways/saved/{pathway_id}",
                    headers=headers
                )

        self.assertEqual(response.status_code, 200)

        retrieved = response.json()

        self.assertEqual(retrieved["revision"], 2)
        self.assertEqual(retrieved["approved_revision"], 2)
        self.assertEqual(retrieved["status"], "approved")
        self.assertTrue(retrieved["approved"])
        self.assertTrue(retrieved["can_export"])

        self.assertEqual(
            retrieved["steps"][0]["title"],
            "My updated pathway action"
        )

        self.assertEqual(
            retrieved["steps"][0]["student_note"],
            "Contact the provider first."
        )

        # The original source evidence remains
        # available after changing the display title.
        self.assertEqual(
            retrieved["steps"][0]["source_step"],
            first_step["source_step"]
        )

    def test_pathway_retrieve_rejects_missing_database(self):

        test_key = "test-only-" + ("A" * 40)

        missing_database = (
            Path(self.temp_dir.name)
            / "missing_pathway_database.db"
        )

        self.assertFalse(missing_database.exists())

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": test_key}
        ), patch(
            "main.DATABASE_PATH",
            missing_database
        ):

            with TestClient(
                app,
                client=("127.0.0.1", 50000)
            ) as local_client:

                response = local_client.get(
                    "/api/pathways/saved/example-pathway",
                    headers={
                        "X-FuturePath-Dev-Key": test_key
                    }
                )

        self.assertEqual(response.status_code, 503)

        # Retrieval must never create an empty
        # SQLite database as a side effect.
        self.assertFalse(missing_database.exists())

    # --------------------------------------------------
    # STE-07: Protected pathway editing API tests
    # --------------------------------------------------

    def _make_local_pathway_client(self):
        return TestClient(
            app,
            client=("127.0.0.1", 50000)
        )

    def _save_pathway_for_edit_test(self, client, headers):

        response = client.post(
            "/api/pathways/save",
            params={"reference_date": "2026-11-28"},
            headers=headers,
            json={
                "opportunity_id": "OPP-005",
                "profile": {
                    "education_level": "undergraduate",
                    "citizenship_status": "australian_citizen"
                }
            }
        )

        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_pathway_edit_updates_and_persists_step(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                saved = self._save_pathway_for_edit_test(
                    client, headers
                )

                pathway_id = saved["pathway_id"]
                first_step = saved["steps"][0]
                original_source = first_step["source_step"]

                response = client.put(
                    f"/api/pathways/saved/{pathway_id}/steps/{first_step['id']}",
                    headers=headers,
                    json={
                        "expected_revision": 1,
                        "title": "Contact provider about eligibility",
                        "student_note": "Ask about current requirements.",
                        "included": False
                    }
                )

                self.assertEqual(response.status_code, 200)
                updated = response.json()

                self.assertEqual(updated["revision"], 2)
                self.assertFalse(updated["approved"])
                self.assertFalse(updated["can_export"])

                edited = updated["steps"][0]

                self.assertEqual(
                    edited["title"],
                    "Contact provider about eligibility"
                )
                self.assertEqual(
                    edited["student_note"],
                    "Ask about current requirements."
                )
                self.assertFalse(edited["included"])

                # Original evidence must not change.
                self.assertEqual(
                    edited["source_step"],
                    original_source
                )

                # Retrieve again to prove the edit
                # was persisted in SQLite.
                retrieved = client.get(
                    f"/api/pathways/saved/{pathway_id}",
                    headers=headers
                )

                self.assertEqual(retrieved.status_code, 200)
                self.assertEqual(
                    retrieved.json()["steps"][0]["title"],
                    "Contact provider about eligibility"
                )

    def test_pathway_edit_invalidates_approval(self):

        import main

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                saved = self._save_pathway_for_edit_test(
                    client, headers
                )

                pathway_id = saved["pathway_id"]
                step_id = saved["steps"][0]["id"]

                approve_saved_pathway(
                    pathway_id=pathway_id,
                    expected_revision=1,
                    confirmed=True,
                    database_path=main.DATABASE_PATH
                )

                response = client.put(
                    f"/api/pathways/saved/{pathway_id}/steps/{step_id}",
                    headers=headers,
                    json={
                        "expected_revision": 1,
                        "title": "Updated after approval",
                        "student_note": "Review this new version.",
                        "included": True
                    }
                )

                self.assertEqual(response.status_code, 200)

                data = response.json()

                self.assertEqual(data["revision"], 2)
                self.assertIsNone(data["approved_revision"])
                self.assertEqual(data["status"], "draft")
                self.assertFalse(data["approved"])
                self.assertFalse(data["can_export"])

    def test_pathway_edit_rejects_stale_revision(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                saved = self._save_pathway_for_edit_test(
                    client, headers
                )

                pathway_id = saved["pathway_id"]
                step_id = saved["steps"][0]["id"]

                url = (
                    f"/api/pathways/saved/{pathway_id}"
                    f"/steps/{step_id}"
                )

                first_edit = client.put(
                    url,
                    headers=headers,
                    json={
                        "expected_revision": 1,
                        "title": "First successful edit",
                        "student_note": "",
                        "included": True
                    }
                )

                self.assertEqual(first_edit.status_code, 200)

                # Revision 1 is now outdated.
                stale_edit = client.put(
                    url,
                    headers=headers,
                    json={
                        "expected_revision": 1,
                        "title": "Outdated edit",
                        "student_note": "",
                        "included": False
                    }
                )

                self.assertEqual(stale_edit.status_code, 409)

                retrieved = client.get(
                    f"/api/pathways/saved/{pathway_id}",
                    headers=headers
                ).json()

                self.assertEqual(retrieved["revision"], 2)
                self.assertEqual(
                    retrieved["steps"][0]["title"],
                    "First successful edit"
                )
                self.assertTrue(
                    retrieved["steps"][0]["included"]
                )

    def test_pathway_edit_rejects_unknown_pathway_and_step(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        payload = {
            "expected_revision": 1,
            "title": "Test action",
            "student_note": "",
            "included": True
        }

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                saved = self._save_pathway_for_edit_test(
                    client, headers
                )

                unknown_pathway = client.put(
                    "/api/pathways/saved/missing-pathway/steps/missing-step",
                    headers=headers,
                    json=payload
                )

                self.assertEqual(
                    unknown_pathway.status_code, 404
                )

                unknown_step = client.put(
                    f"/api/pathways/saved/{saved['pathway_id']}/steps/missing-step",
                    headers=headers,
                    json=payload
                )

                self.assertEqual(
                    unknown_step.status_code, 404
                )

                retrieved = client.get(
                    f"/api/pathways/saved/{saved['pathway_id']}",
                    headers=headers
                ).json()

                self.assertEqual(retrieved["revision"], 1)

    def test_pathway_edit_rejects_cross_pathway_step(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                first = self._save_pathway_for_edit_test(
                    client, headers
                )

                second = self._save_pathway_for_edit_test(
                    client, headers
                )

                # Attempt to edit a step belonging
                # to another saved pathway.
                response = client.put(
                    f"/api/pathways/saved/{first['pathway_id']}"
                    f"/steps/{second['steps'][0]['id']}",
                    headers=headers,
                    json={
                        "expected_revision": 1,
                        "title": "Cross-pathway edit",
                        "student_note": "",
                        "included": True
                    }
                )

                self.assertEqual(response.status_code, 404)

                first_after = client.get(
                    f"/api/pathways/saved/{first['pathway_id']}",
                    headers=headers
                ).json()

                second_after = client.get(
                    f"/api/pathways/saved/{second['pathway_id']}",
                    headers=headers
                ).json()

                self.assertEqual(first_after["revision"], 1)
                self.assertEqual(second_after["revision"], 1)

    def test_pathway_edit_rejects_invalid_payloads(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                saved = self._save_pathway_for_edit_test(
                    client, headers
                )

                url = (
                    f"/api/pathways/saved/{saved['pathway_id']}"
                    f"/steps/{saved['steps'][0]['id']}"
                )

                valid = {
                    "expected_revision": 1,
                    "title": "Valid action",
                    "student_note": "",
                    "included": True
                }

                invalid_changes = [
                    {"expected_revision": 0},
                    {"expected_revision": True},
                    {"expected_revision": "1"},
                    {"title": ""},
                    {"title": "   "},
                    {"title": "x" * 201},
                    {"student_note": "x" * 2001},
                    {"included": "yes"},
                    {"included": 1},
                    {"unexpected_field": "not allowed"}
                ]

                for change in invalid_changes:

                    with self.subTest(change=change):

                        response = client.put(
                            url,
                            headers=headers,
                            json={**valid, **change}
                        )

                        self.assertEqual(
                            response.status_code,
                            422
                        )

                # Missing required fields must fail.
                missing_field = client.put(
                    url,
                    headers=headers,
                    json={
                        "expected_revision": 1,
                        "title": "Valid action"
                    }
                )

                self.assertEqual(
                    missing_field.status_code, 422
                )

                retrieved = client.get(
                    f"/api/pathways/saved/{saved['pathway_id']}",
                    headers=headers
                ).json()

                self.assertEqual(retrieved["revision"], 1)
                self.assertEqual(
                    retrieved["steps"][0]["title"],
                    saved["steps"][0]["title"]
                )

    def test_pathway_edit_requires_local_dev_access(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:
                saved = self._save_pathway_for_edit_test(
                    client, headers
                )

        url = (
            f"/api/pathways/saved/{saved['pathway_id']}"
            f"/steps/{saved['steps'][0]['id']}"
        )

        payload = {
            "expected_revision": 1,
            "title": "Should not be saved",
            "student_note": "",
            "included": True
        }

        # Access disabled when no key is configured.
        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": ""}
        ):
            with self._make_local_pathway_client() as client:
                disabled = client.put(
                    url,
                    headers=headers,
                    json=payload
                )

        self.assertEqual(disabled.status_code, 503)

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                # Incorrect key.
                incorrect = client.put(
                    url,
                    headers={
                        "X-FuturePath-Dev-Key": "incorrect"
                    },
                    json=payload
                )

                self.assertEqual(incorrect.status_code, 401)

            # Correct key, but non-local client.
            remote = self.client.put(
                url,
                headers=headers,
                json=payload
            )

            self.assertEqual(remote.status_code, 403)

            # Verify rejected requests caused no edits.
            with self._make_local_pathway_client() as client:
                retrieved = client.get(
                    f"/api/pathways/saved/{saved['pathway_id']}",
                    headers=headers
                ).json()

        self.assertEqual(retrieved["revision"], 1)
        self.assertEqual(
            retrieved["steps"][0]["title"],
            saved["steps"][0]["title"]
        )

    def test_pathway_edit_rejects_missing_database(self):

        key = "test-only-" + ("A" * 40)

        missing_database = (
            Path(self.temp_dir.name)
            / "missing_edit_database.db"
        )

        self.assertFalse(missing_database.exists())

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ), patch(
            "main.DATABASE_PATH",
            missing_database
        ):

            with self._make_local_pathway_client() as client:

                response = client.put(
                    "/api/pathways/saved/example/steps/example",
                    headers={
                        "X-FuturePath-Dev-Key": key
                    },
                    json={
                        "expected_revision": 1,
                        "title": "Test action",
                        "student_note": "",
                        "included": True
                    }
                )

        self.assertEqual(response.status_code, 503)
        self.assertFalse(missing_database.exists())

    # --------------------------------------------------
    # STE-07: Student-created action API tests
    # --------------------------------------------------

    def test_pathway_create_action_persists_and_preserves_source(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                saved = self._save_pathway_for_edit_test(
                    client, headers
                )

                pathway_id = saved["pathway_id"]

                original_sources = {
                    step["id"]: step["source_step"]
                    for step in saved["steps"]
                }

                response = client.post(
                    f"/api/pathways/saved/{pathway_id}/steps",
                    headers=headers,
                    json={
                        "expected_revision": 1,
                        "title": "  Attend a career workshop  ",
                        "student_note": "Register through university.",
                        "included": True
                    }
                )

                self.assertEqual(response.status_code, 200)

                updated = response.json()

                self.assertEqual(updated["revision"], 2)
                self.assertEqual(updated["status"], "draft")
                self.assertFalse(updated["approved"])
                self.assertFalse(updated["can_export"])
                self.assertEqual(len(updated["steps"]), 6)

                new_step = updated["steps"][-1]

                self.assertEqual(new_step["position"], 6)
                self.assertEqual(new_step["origin"], "student")
                self.assertEqual(
                    new_step["title"],
                    "Attend a career workshop"
                )
                self.assertEqual(
                    new_step["student_note"],
                    "Register through university."
                )
                self.assertTrue(new_step["included"])

                # Personal actions must not impersonate
                # published eligibility requirements.
                self.assertIsNone(new_step["source_step_id"])
                self.assertIsNone(new_step["source_step"])

                # Existing generated evidence is unchanged.
                for step in updated["steps"][:-1]:
                    self.assertEqual(
                        step["source_step"],
                        original_sources[step["id"]]
                    )

                # Retrieve the pathway again to verify
                # the new action was persisted in SQLite.
                retrieved_response = client.get(
                    f"/api/pathways/saved/{pathway_id}",
                    headers=headers
                )

                self.assertEqual(
                    retrieved_response.status_code,
                    200
                )

                retrieved = retrieved_response.json()

                self.assertEqual(retrieved["revision"], 2)
                self.assertEqual(len(retrieved["steps"]), 6)
                self.assertEqual(
                    retrieved["steps"][-1]["id"],
                    new_step["id"]
                )

    def test_pathway_create_action_supports_defaults_and_exclusion(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                saved = self._save_pathway_for_edit_test(
                    client, headers
                )

                url = (
                    f"/api/pathways/saved/"
                    f"{saved['pathway_id']}/steps"
                )

                # Optional fields should use defaults.
                first_response = client.post(
                    url,
                    headers=headers,
                    json={
                        "expected_revision": 1,
                        "title": "First personal action"
                    }
                )

                self.assertEqual(
                    first_response.status_code,
                    200
                )

                first = first_response.json()["steps"][-1]

                self.assertEqual(first["student_note"], "")
                self.assertTrue(first["included"])

                # Students can exclude a personal action.
                second_response = client.post(
                    url,
                    headers=headers,
                    json={
                        "expected_revision": 2,
                        "title": "Optional personal action",
                        "student_note": "Keep for later.",
                        "included": False
                    }
                )

                self.assertEqual(
                    second_response.status_code,
                    200
                )

                second_data = second_response.json()

                self.assertEqual(second_data["revision"], 3)
                self.assertEqual(len(second_data["steps"]), 7)

                second = second_data["steps"][-1]

                self.assertEqual(second["origin"], "student")
                self.assertFalse(second["included"])
                self.assertEqual(
                    second["student_note"],
                    "Keep for later."
                )

    def test_pathway_create_action_invalidates_approval(self):

        import main

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                saved = self._save_pathway_for_edit_test(
                    client, headers
                )

                pathway_id = saved["pathway_id"]

                # Approve the original pathway.
                approved = approve_saved_pathway(
                    pathway_id=pathway_id,
                    expected_revision=1,
                    confirmed=True,
                    database_path=main.DATABASE_PATH
                )

                self.assertTrue(approved["approved"])

                # Adding a new action changes the plan.
                response = client.post(
                    f"/api/pathways/saved/{pathway_id}/steps",
                    headers=headers,
                    json={
                        "expected_revision": 1,
                        "title": "Book a careers appointment",
                        "student_note": "Discuss applications."
                    }
                )

                self.assertEqual(response.status_code, 200)

                updated = response.json()

                self.assertEqual(updated["revision"], 2)
                self.assertIsNone(updated["approved_revision"])
                self.assertEqual(updated["status"], "draft")
                self.assertFalse(updated["approved"])
                self.assertFalse(updated["can_export"])

    def test_pathway_create_action_rejects_stale_revision(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                saved = self._save_pathway_for_edit_test(
                    client, headers
                )

                pathway_id = saved["pathway_id"]

                url = (
                    f"/api/pathways/saved/"
                    f"{pathway_id}/steps"
                )

                first_response = client.post(
                    url,
                    headers=headers,
                    json={
                        "expected_revision": 1,
                        "title": "First successful action"
                    }
                )

                self.assertEqual(
                    first_response.status_code,
                    200
                )

                # Revision 1 is now outdated.
                stale_response = client.post(
                    url,
                    headers=headers,
                    json={
                        "expected_revision": 1,
                        "title": "Outdated action"
                    }
                )

                self.assertEqual(
                    stale_response.status_code,
                    409
                )

                retrieved = client.get(
                    f"/api/pathways/saved/{pathway_id}",
                    headers=headers
                ).json()

                self.assertEqual(retrieved["revision"], 2)
                self.assertEqual(len(retrieved["steps"]), 6)
                self.assertEqual(
                    retrieved["steps"][-1]["title"],
                    "First successful action"
                )

    def test_pathway_create_action_rejects_unknown_pathway(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                response = client.post(
                    "/api/pathways/saved/nonexistent-pathway/steps",
                    headers=headers,
                    json={
                        "expected_revision": 1,
                        "title": "Should not be saved"
                    }
                )

        self.assertEqual(response.status_code, 404)

    def test_pathway_create_action_rejects_invalid_payloads(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                saved = self._save_pathway_for_edit_test(
                    client, headers
                )

                url = (
                    f"/api/pathways/saved/"
                    f"{saved['pathway_id']}/steps"
                )

                valid = {
                    "expected_revision": 1,
                    "title": "Valid personal action",
                    "student_note": "",
                    "included": True
                }

                invalid_changes = [
                    {"expected_revision": 0},
                    {"expected_revision": True},
                    {"expected_revision": "1"},
                    {"title": ""},
                    {"title": "   "},
                    {"title": "x" * 201},
                    {"student_note": None},
                    {"student_note": "x" * 2001},
                    {"included": "yes"},
                    {"included": 1},
                    {"unexpected_field": "not allowed"}
                ]

                for change in invalid_changes:

                    with self.subTest(change=change):

                        response = client.post(
                            url,
                            headers=headers,
                            json={**valid, **change}
                        )

                        self.assertEqual(
                            response.status_code,
                            422
                        )

                # Confirm no invalid action was saved.
                retrieved = client.get(
                    f"/api/pathways/saved/{saved['pathway_id']}",
                    headers=headers
                ).json()

                self.assertEqual(retrieved["revision"], 1)
                self.assertEqual(len(retrieved["steps"]), 5)

    def test_pathway_create_action_requires_local_dev_access(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:
                saved = self._save_pathway_for_edit_test(
                    client, headers
                )

        url = (
            f"/api/pathways/saved/"
            f"{saved['pathway_id']}/steps"
        )

        payload = {
            "expected_revision": 1,
            "title": "Unauthorized action"
        }

        # No configured development key.
        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": ""}
        ):
            with self._make_local_pathway_client() as client:

                disabled = client.post(
                    url,
                    headers=headers,
                    json=payload
                )

        self.assertEqual(disabled.status_code, 503)

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                # Incorrect key.
                incorrect = client.post(
                    url,
                    headers={
                        "X-FuturePath-Dev-Key": "incorrect"
                    },
                    json=payload
                )

                self.assertEqual(incorrect.status_code, 401)

            # Correct key from a non-local client.
            remote = self.client.post(
                url,
                headers=headers,
                json=payload
            )

            self.assertEqual(remote.status_code, 403)

            # Confirm rejected requests made no changes.
            with self._make_local_pathway_client() as client:

                retrieved = client.get(
                    f"/api/pathways/saved/{saved['pathway_id']}",
                    headers=headers
                ).json()

        self.assertEqual(retrieved["revision"], 1)
        self.assertEqual(len(retrieved["steps"]), 5)

    def test_pathway_create_action_rejects_missing_database(self):

        key = "test-only-" + ("A" * 40)

        missing_database = (
            Path(self.temp_dir.name)
            / "missing_create_action_database.db"
        )

        self.assertFalse(missing_database.exists())

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ), patch(
            "main.DATABASE_PATH",
            missing_database
        ):

            with self._make_local_pathway_client() as client:

                response = client.post(
                    "/api/pathways/saved/example-pathway/steps",
                    headers={
                        "X-FuturePath-Dev-Key": key
                    },
                    json={
                        "expected_revision": 1,
                        "title": "Test personal action"
                    }
                )

        self.assertEqual(response.status_code, 503)

        # No empty database may be created accidentally.
        self.assertFalse(missing_database.exists())


    # --------------------------------------------------
    # STE-07: Pathway reordering API integration tests
    # --------------------------------------------------

    def test_pathway_reorder_persists_and_preserves_evidence(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                saved = self._save_pathway_for_edit_test(
                    client, headers
                )

                pathway_id = saved["pathway_id"]
                original_steps = saved["steps"]

                original_sources = {
                    step["id"]: step["source_step"]
                    for step in original_steps
                }

                desired_ids = [
                    step["id"]
                    for step in reversed(original_steps)
                ]

                response = client.put(
                    f"/api/pathways/saved/{pathway_id}/reorder",
                    headers=headers,
                    json={
                        "expected_revision": 1,
                        "step_ids": desired_ids
                    }
                )

                self.assertEqual(response.status_code, 200)

                updated = response.json()

                self.assertEqual(updated["revision"], 2)
                self.assertEqual(
                    [step["id"] for step in updated["steps"]],
                    desired_ids
                )
                self.assertEqual(
                    [step["position"] for step in updated["steps"]],
                    list(range(1, len(desired_ids) + 1))
                )

                self.assertFalse(updated["approved"])
                self.assertFalse(updated["can_export"])

                # Reordering must not change source evidence.
                for step in updated["steps"]:
                    self.assertEqual(
                        step["source_step"],
                        original_sources[step["id"]]
                    )

                # Verify the new order is persisted in SQLite.
                retrieved = client.get(
                    f"/api/pathways/saved/{pathway_id}",
                    headers=headers
                )

                self.assertEqual(retrieved.status_code, 200)
                self.assertEqual(
                    [
                        step["id"]
                        for step in retrieved.json()["steps"]
                    ],
                    desired_ids
                )

    def test_pathway_reorder_noop_preserves_approval(self):

        import main

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                saved = self._save_pathway_for_edit_test(
                    client, headers
                )

                pathway_id = saved["pathway_id"]
                original_ids = [
                    step["id"] for step in saved["steps"]
                ]

                approved = approve_saved_pathway(
                    pathway_id=pathway_id,
                    expected_revision=1,
                    confirmed=True,
                    database_path=main.DATABASE_PATH
                )

                self.assertTrue(approved["approved"])

                # Submit exactly the same order.
                response = client.put(
                    f"/api/pathways/saved/{pathway_id}/reorder",
                    headers=headers,
                    json={
                        "expected_revision": 1,
                        "step_ids": original_ids
                    }
                )

                self.assertEqual(response.status_code, 200)

                result = response.json()

                self.assertEqual(result["revision"], 1)
                self.assertEqual(result["approved_revision"], 1)
                self.assertTrue(result["approved"])
                self.assertTrue(result["can_export"])

    def test_pathway_reorder_change_invalidates_approval(self):

        import main

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                saved = self._save_pathway_for_edit_test(
                    client, headers
                )

                pathway_id = saved["pathway_id"]

                approved = approve_saved_pathway(
                    pathway_id=pathway_id,
                    expected_revision=1,
                    confirmed=True,
                    database_path=main.DATABASE_PATH
                )

                self.assertTrue(approved["approved"])

                reversed_ids = [
                    step["id"]
                    for step in reversed(saved["steps"])
                ]

                response = client.put(
                    f"/api/pathways/saved/{pathway_id}/reorder",
                    headers=headers,
                    json={
                        "expected_revision": 1,
                        "step_ids": reversed_ids
                    }
                )

                self.assertEqual(response.status_code, 200)

                result = response.json()

                self.assertEqual(result["revision"], 2)
                self.assertIsNone(result["approved_revision"])
                self.assertEqual(result["status"], "draft")
                self.assertFalse(result["approved"])
                self.assertFalse(result["can_export"])

    def test_pathway_reorder_rejects_stale_revision(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                saved = self._save_pathway_for_edit_test(
                    client, headers
                )

                pathway_id = saved["pathway_id"]

                original_ids = [
                    step["id"] for step in saved["steps"]
                ]

                reversed_ids = list(reversed(original_ids))

                url = (
                    f"/api/pathways/saved/{pathway_id}/reorder"
                )

                first = client.put(
                    url,
                    headers=headers,
                    json={
                        "expected_revision": 1,
                        "step_ids": reversed_ids
                    }
                )

                self.assertEqual(first.status_code, 200)

                # Revision 1 is outdated after the first reorder.
                stale = client.put(
                    url,
                    headers=headers,
                    json={
                        "expected_revision": 1,
                        "step_ids": original_ids
                    }
                )

                self.assertEqual(stale.status_code, 409)

                retrieved = client.get(
                    f"/api/pathways/saved/{pathway_id}",
                    headers=headers
                ).json()

                self.assertEqual(retrieved["revision"], 2)

                self.assertEqual(
                    [step["id"] for step in retrieved["steps"]],
                    reversed_ids
                )

    def test_pathway_reorder_rejects_invalid_step_lists(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                first = self._save_pathway_for_edit_test(
                    client, headers
                )

                second = self._save_pathway_for_edit_test(
                    client, headers
                )

                pathway_id = first["pathway_id"]

                original_ids = [
                    step["id"] for step in first["steps"]
                ]

                foreign_id = second["steps"][0]["id"]

                invalid_lists = [
                    # Missing a required action.
                    original_ids[:-1],

                    # Duplicate an action.
                    original_ids[:-1] + [original_ids[0]],

                    # Include a step from another pathway.
                    original_ids[:-1] + [foreign_id],

                    # Include a nonexistent step.
                    original_ids[:-1] + ["unknown-step"]
                ]

                url = (
                    f"/api/pathways/saved/{pathway_id}/reorder"
                )

                for step_ids in invalid_lists:

                    with self.subTest(step_ids=step_ids):

                        response = client.put(
                            url,
                            headers=headers,
                            json={
                                "expected_revision": 1,
                                "step_ids": step_ids
                            }
                        )

                        self.assertEqual(
                            response.status_code,
                            422
                        )

                # Failed attempts must not change positions.
                retrieved = client.get(
                    f"/api/pathways/saved/{pathway_id}",
                    headers=headers
                ).json()

                self.assertEqual(retrieved["revision"], 1)

                self.assertEqual(
                    [step["id"] for step in retrieved["steps"]],
                    original_ids
                )

    def test_pathway_reorder_rejects_invalid_payloads(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                saved = self._save_pathway_for_edit_test(
                    client, headers
                )

                pathway_id = saved["pathway_id"]

                original_ids = [
                    step["id"] for step in saved["steps"]
                ]

                url = (
                    f"/api/pathways/saved/{pathway_id}/reorder"
                )

                valid = {
                    "expected_revision": 1,
                    "step_ids": original_ids
                }

                invalid_changes = [
                    {"expected_revision": 0},
                    {"expected_revision": True},
                    {"expected_revision": "1"},
                    {"step_ids": []},
                    {"step_ids": None},
                    {"step_ids": "not-a-list"},
                    {"step_ids": [123]},
                    {"unexpected_field": "not allowed"}
                ]

                for change in invalid_changes:

                    with self.subTest(change=change):

                        response = client.put(
                            url,
                            headers=headers,
                            json={**valid, **change}
                        )

                        self.assertEqual(
                            response.status_code,
                            422
                        )

                # A missing required field must fail.
                missing = client.put(
                    url,
                    headers=headers,
                    json={"expected_revision": 1}
                )

                self.assertEqual(missing.status_code, 422)

                retrieved = client.get(
                    f"/api/pathways/saved/{pathway_id}",
                    headers=headers
                ).json()

                self.assertEqual(retrieved["revision"], 1)

    def test_pathway_reorder_requires_local_dev_access(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                saved = self._save_pathway_for_edit_test(
                    client, headers
                )

        pathway_id = saved["pathway_id"]

        original_ids = [
            step["id"] for step in saved["steps"]
        ]

        url = (
            f"/api/pathways/saved/{pathway_id}/reorder"
        )

        payload = {
            "expected_revision": 1,
            "step_ids": list(reversed(original_ids))
        }

        # Endpoint disabled without a configured key.
        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": ""}
        ):
            with self._make_local_pathway_client() as client:

                disabled = client.put(
                    url,
                    headers=headers,
                    json=payload
                )

        self.assertEqual(disabled.status_code, 503)

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                # Wrong development key.
                incorrect = client.put(
                    url,
                    headers={
                        "X-FuturePath-Dev-Key": "incorrect"
                    },
                    json=payload
                )

                self.assertEqual(incorrect.status_code, 401)

            # Non-local clients must be rejected.
            remote = self.client.put(
                url,
                headers=headers,
                json=payload
            )

            self.assertEqual(remote.status_code, 403)

            # Verify none of the rejected calls modified data.
            with self._make_local_pathway_client() as client:

                retrieved = client.get(
                    f"/api/pathways/saved/{pathway_id}",
                    headers=headers
                ).json()

        self.assertEqual(retrieved["revision"], 1)

        self.assertEqual(
            [step["id"] for step in retrieved["steps"]],
            original_ids
        )

    def test_pathway_reorder_handles_missing_resources(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                # An unknown pathway returns HTTP 404.
                unknown = client.put(
                    "/api/pathways/saved/unknown-pathway/reorder",
                    headers=headers,
                    json={
                        "expected_revision": 1,
                        "step_ids": ["unknown-step"]
                    }
                )

                self.assertEqual(unknown.status_code, 404)

            missing_db = (
                Path(self.temp_dir.name)
                / "missing_reorder_database.db"
            )

            self.assertFalse(missing_db.exists())

            # A missing database returns HTTP 503.
            with patch(
                "main.DATABASE_PATH",
                missing_db
            ):
                with self._make_local_pathway_client() as client:

                    unavailable = client.put(
                        "/api/pathways/saved/example/reorder",
                        headers=headers,
                        json={
                            "expected_revision": 1,
                            "step_ids": ["example-step"]
                        }
                    )

                self.assertEqual(
                    unavailable.status_code,
                    503
                )

            # A missing database must not be created.
            self.assertFalse(missing_db.exists())

    def test_pathway_reorder_supports_student_created_actions(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                saved = self._save_pathway_for_edit_test(
                    client, headers
                )

                pathway_id = saved["pathway_id"]

                # Add a student-created action first.
                created = client.post(
                    f"/api/pathways/saved/{pathway_id}/steps",
                    headers=headers,
                    json={
                        "expected_revision": 1,
                        "title": "Attend a networking event"
                    }
                )

                self.assertEqual(created.status_code, 200)

                after_create = created.json()

                self.assertEqual(after_create["revision"], 2)

                personal_step = after_create["steps"][-1]

                self.assertEqual(
                    personal_step["origin"],
                    "student"
                )

                # Move the personal action to the front.
                remaining_ids = [
                    step["id"]
                    for step in after_create["steps"][:-1]
                ]

                desired_ids = [
                    personal_step["id"],
                    *remaining_ids
                ]

                response = client.put(
                    f"/api/pathways/saved/{pathway_id}/reorder",
                    headers=headers,
                    json={
                        "expected_revision": 2,
                        "step_ids": desired_ids
                    }
                )

                self.assertEqual(response.status_code, 200)

                result = response.json()

                self.assertEqual(result["revision"], 3)

                self.assertEqual(
                    [step["id"] for step in result["steps"]],
                    desired_ids
                )

                self.assertEqual(
                    result["steps"][0]["origin"],
                    "student"
                )

                self.assertIsNone(
                    result["steps"][0]["source_step"]
                )

                # Generated actions still retain evidence.
                original_sources = {
                    step["id"]: step["source_step"]
                    for step in saved["steps"]
                }

                for step in result["steps"][1:]:
                    self.assertEqual(
                        step["source_step"],
                        original_sources[step["id"]]
                    )

    # --------------------------------------------------
    # STE-07: Explicit pathway approval API tests
    # --------------------------------------------------

    def test_pathway_approve_persists_current_revision(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                saved = self._save_pathway_for_edit_test(
                    client, headers
                )

                pathway_id = saved["pathway_id"]

                self.assertFalse(saved["approved"])
                self.assertFalse(saved["can_export"])

                response = client.post(
                    f"/api/pathways/saved/{pathway_id}/approve",
                    headers=headers,
                    json={
                        "expected_revision": 1,
                        "confirmed": True
                    }
                )

                self.assertEqual(response.status_code, 200)

                approved = response.json()

                self.assertEqual(approved["revision"], 1)
                self.assertEqual(approved["approved_revision"], 1)
                self.assertEqual(approved["status"], "approved")
                self.assertTrue(approved["approved"])
                self.assertTrue(approved["can_export"])

                # Approval must not modify the original
                # generated pathway actions.
                self.assertEqual(
                    [step["id"] for step in approved["steps"]],
                    [step["id"] for step in saved["steps"]]
                )

                for before, after in zip(
                    saved["steps"],
                    approved["steps"]
                ):
                    self.assertEqual(
                        before["source_step"],
                        after["source_step"]
                    )

                # Retrieve again to confirm SQLite
                # persisted the approval.
                retrieved_response = client.get(
                    f"/api/pathways/saved/{pathway_id}",
                    headers=headers
                )

                self.assertEqual(
                    retrieved_response.status_code,
                    200
                )

                retrieved = retrieved_response.json()

                self.assertEqual(
                    retrieved["approved_revision"],
                    1
                )
                self.assertTrue(retrieved["approved"])
                self.assertTrue(retrieved["can_export"])

    def test_pathway_approve_rejects_unconfirmed_request(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                saved = self._save_pathway_for_edit_test(
                    client, headers
                )

                pathway_id = saved["pathway_id"]

                response = client.post(
                    f"/api/pathways/saved/{pathway_id}/approve",
                    headers=headers,
                    json={
                        "expected_revision": 1,
                        "confirmed": False
                    }
                )

                self.assertEqual(response.status_code, 422)

                retrieved = client.get(
                    f"/api/pathways/saved/{pathway_id}",
                    headers=headers
                ).json()

                self.assertEqual(retrieved["revision"], 1)
                self.assertIsNone(
                    retrieved["approved_revision"]
                )
                self.assertEqual(retrieved["status"], "draft")
                self.assertFalse(retrieved["approved"])
                self.assertFalse(retrieved["can_export"])

    def test_pathway_approve_rejects_no_included_actions(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                saved = self._save_pathway_for_edit_test(
                    client, headers
                )

                pathway_id = saved["pathway_id"]
                current_revision = saved["revision"]

                # Exclude every action through the edit API.
                for step in saved["steps"]:

                    response = client.put(
                        f"/api/pathways/saved/{pathway_id}"
                        f"/steps/{step['id']}",
                        headers=headers,
                        json={
                            "expected_revision": current_revision,
                            "title": step["title"],
                            "student_note": step["student_note"],
                            "included": False
                        }
                    )

                    self.assertEqual(
                        response.status_code,
                        200
                    )

                    current_revision = (
                        response.json()["revision"]
                    )

                # A pathway containing no included actions
                # must never become approved.
                approval_response = client.post(
                    f"/api/pathways/saved/{pathway_id}/approve",
                    headers=headers,
                    json={
                        "expected_revision": current_revision,
                        "confirmed": True
                    }
                )

                self.assertEqual(
                    approval_response.status_code,
                    422
                )

                retrieved = client.get(
                    f"/api/pathways/saved/{pathway_id}",
                    headers=headers
                ).json()

                self.assertEqual(
                    retrieved["revision"],
                    current_revision
                )

                self.assertTrue(
                    all(
                        not step["included"]
                        for step in retrieved["steps"]
                    )
                )

                self.assertFalse(retrieved["approved"])
                self.assertFalse(retrieved["can_export"])

    def test_pathway_approve_rejects_stale_revision(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                saved = self._save_pathway_for_edit_test(
                    client, headers
                )

                pathway_id = saved["pathway_id"]

                # Add an action, advancing revision to 2.
                created = client.post(
                    f"/api/pathways/saved/{pathway_id}/steps",
                    headers=headers,
                    json={
                        "expected_revision": 1,
                        "title": "Review internship applications"
                    }
                )

                self.assertEqual(created.status_code, 200)
                self.assertEqual(
                    created.json()["revision"],
                    2
                )

                # An approval based on revision 1
                # must now be rejected.
                stale = client.post(
                    f"/api/pathways/saved/{pathway_id}/approve",
                    headers=headers,
                    json={
                        "expected_revision": 1,
                        "confirmed": True
                    }
                )

                self.assertEqual(stale.status_code, 409)

                retrieved = client.get(
                    f"/api/pathways/saved/{pathway_id}",
                    headers=headers
                ).json()

                self.assertEqual(retrieved["revision"], 2)
                self.assertFalse(retrieved["approved"])
                self.assertFalse(retrieved["can_export"])

                # Approving the current revision should work.
                current = client.post(
                    f"/api/pathways/saved/{pathway_id}/approve",
                    headers=headers,
                    json={
                        "expected_revision": 2,
                        "confirmed": True
                    }
                )

                self.assertEqual(current.status_code, 200)
                self.assertEqual(
                    current.json()["approved_revision"],
                    2
                )
                self.assertTrue(current.json()["approved"])

    def test_pathway_approve_rejects_unknown_pathway(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                response = client.post(
                    "/api/pathways/saved/"
                    "nonexistent-pathway/approve",
                    headers=headers,
                    json={
                        "expected_revision": 1,
                        "confirmed": True
                    }
                )

        self.assertEqual(response.status_code, 404)

    def test_pathway_approve_rejects_invalid_payloads(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                saved = self._save_pathway_for_edit_test(
                    client, headers
                )

                pathway_id = saved["pathway_id"]

                url = (
                    f"/api/pathways/saved/{pathway_id}/approve"
                )

                valid = {
                    "expected_revision": 1,
                    "confirmed": True
                }

                invalid_changes = [
                    {"expected_revision": 0},
                    {"expected_revision": -1},
                    {"expected_revision": True},
                    {"expected_revision": "1"},
                    {"confirmed": None},
                    {"confirmed": "true"},
                    {"confirmed": 1},
                    {"unexpected_field": "not allowed"}
                ]

                for change in invalid_changes:

                    with self.subTest(change=change):

                        response = client.post(
                            url,
                            headers=headers,
                            json={**valid, **change}
                        )

                        self.assertEqual(
                            response.status_code,
                            422
                        )

                # Confirmation is mandatory.
                missing_confirmation = client.post(
                    url,
                    headers=headers,
                    json={"expected_revision": 1}
                )

                self.assertEqual(
                    missing_confirmation.status_code,
                    422
                )

                # Revision is also mandatory.
                missing_revision = client.post(
                    url,
                    headers=headers,
                    json={"confirmed": True}
                )

                self.assertEqual(
                    missing_revision.status_code,
                    422
                )

                # No invalid request may approve the plan.
                retrieved = client.get(
                    f"/api/pathways/saved/{pathway_id}",
                    headers=headers
                ).json()

                self.assertEqual(retrieved["revision"], 1)
                self.assertIsNone(
                    retrieved["approved_revision"]
                )
                self.assertFalse(retrieved["approved"])

    def test_pathway_approve_requires_local_dev_access(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                saved = self._save_pathway_for_edit_test(
                    client, headers
                )

        pathway_id = saved["pathway_id"]

        url = (
            f"/api/pathways/saved/{pathway_id}/approve"
        )

        payload = {
            "expected_revision": 1,
            "confirmed": True
        }

        # Unconfigured development access.
        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": ""}
        ):
            with self._make_local_pathway_client() as client:

                disabled = client.post(
                    url,
                    headers=headers,
                    json=payload
                )

        self.assertEqual(disabled.status_code, 503)

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                # Incorrect development key.
                incorrect = client.post(
                    url,
                    headers={
                        "X-FuturePath-Dev-Key": "incorrect"
                    },
                    json=payload
                )

                self.assertEqual(incorrect.status_code, 401)

            # Non-local requests must be rejected.
            remote = self.client.post(
                url,
                headers=headers,
                json=payload
            )

            self.assertEqual(remote.status_code, 403)

            # Rejected requests must not approve the plan.
            with self._make_local_pathway_client() as client:

                retrieved = client.get(
                    f"/api/pathways/saved/{pathway_id}",
                    headers=headers
                ).json()

        self.assertEqual(retrieved["revision"], 1)
        self.assertFalse(retrieved["approved"])
        self.assertFalse(retrieved["can_export"])

    def test_pathway_approve_rejects_missing_database(self):

        key = "test-only-" + ("A" * 40)

        missing_database = (
            Path(self.temp_dir.name)
            / "missing_approval_database.db"
        )

        self.assertFalse(missing_database.exists())

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ), patch(
            "main.DATABASE_PATH",
            missing_database
        ):

            with self._make_local_pathway_client() as client:

                response = client.post(
                    "/api/pathways/saved/example-pathway/approve",
                    headers={
                        "X-FuturePath-Dev-Key": key
                    },
                    json={
                        "expected_revision": 1,
                        "confirmed": True
                    }
                )

        self.assertEqual(response.status_code, 503)

        # Failed requests must never create an empty
        # database as a side effect.
        self.assertFalse(missing_database.exists())

    # --------------------------------------------------
    # STE-07: Protected pathway export API tests
    # --------------------------------------------------

    def test_pathway_export_approved_json_is_read_only(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                saved = self._save_pathway_for_edit_test(
                    client, headers
                )
                pathway_id = saved["pathway_id"]

                approval = client.post(
                    f"/api/pathways/saved/{pathway_id}/approve",
                    headers=headers,
                    json={
                        "expected_revision": 1,
                        "confirmed": True
                    }
                )

                self.assertEqual(approval.status_code, 200)
                self.assertTrue(approval.json()["approved"])

                before = client.get(
                    f"/api/pathways/saved/{pathway_id}",
                    headers=headers
                ).json()

                export = client.post(
                    f"/api/pathways/saved/{pathway_id}/export",
                    headers=headers,
                    json={"expected_revision": 1}
                )

                self.assertEqual(export.status_code, 200)

                data = export.json()

                self.assertEqual(
                    data["export_type"],
                    "approved_pathway"
                )
                self.assertEqual(
                    data["pathway_id"],
                    pathway_id
                )
                self.assertEqual(
                    data["opportunity_id"],
                    "OPP-005"
                )
                self.assertEqual(data["revision"], 1)
                self.assertEqual(
                    data["approved_revision"],
                    1
                )
                self.assertEqual(
                    data["status"],
                    "approved"
                )
                self.assertIsNotNone(data["approved_at"])
                self.assertEqual(len(data["steps"]), 5)
                self.assertIn("source_snapshot", data)
                self.assertEqual(
                    data["source_snapshot"]["id"],
                    "OPP-005"
                )
                self.assertIn(
                    "informational",
                    data["notice"]
                )

                # Export is read-only: it must not
                # change the persisted pathway.
                after = client.get(
                    f"/api/pathways/saved/{pathway_id}",
                    headers=headers
                ).json()

                self.assertEqual(after, before)

    def test_pathway_export_blocks_unapproved_draft(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                saved = self._save_pathway_for_edit_test(
                    client, headers
                )

                pathway_id = saved["pathway_id"]

                response = client.post(
                    f"/api/pathways/saved/{pathway_id}/export",
                    headers=headers,
                    json={"expected_revision": 1}
                )

                self.assertEqual(response.status_code, 409)

                retrieved = client.get(
                    f"/api/pathways/saved/{pathway_id}",
                    headers=headers
                ).json()

                self.assertEqual(retrieved["revision"], 1)
                self.assertFalse(retrieved["approved"])
                self.assertFalse(retrieved["can_export"])
                self.assertIsNone(
                    retrieved["approved_revision"]
                )

    def test_pathway_export_rejects_stale_revision(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                saved = self._save_pathway_for_edit_test(
                    client, headers
                )
                pathway_id = saved["pathway_id"]

                created = client.post(
                    f"/api/pathways/saved/{pathway_id}/steps",
                    headers=headers,
                    json={
                        "expected_revision": 1,
                        "title": "Review cybersecurity roles"
                    }
                )

                self.assertEqual(created.status_code, 200)
                self.assertEqual(
                    created.json()["revision"],
                    2
                )

                approved = client.post(
                    f"/api/pathways/saved/{pathway_id}/approve",
                    headers=headers,
                    json={
                        "expected_revision": 2,
                        "confirmed": True
                    }
                )

                self.assertEqual(approved.status_code, 200)

                # Revision 1 cannot be exported,
                # even though revision 2 is approved.
                stale = client.post(
                    f"/api/pathways/saved/{pathway_id}/export",
                    headers=headers,
                    json={"expected_revision": 1}
                )

                self.assertEqual(stale.status_code, 409)

                current = client.post(
                    f"/api/pathways/saved/{pathway_id}/export",
                    headers=headers,
                    json={"expected_revision": 2}
                )

                self.assertEqual(current.status_code, 200)
                self.assertEqual(
                    current.json()["revision"],
                    2
                )

    def test_pathway_export_requires_reapproval_after_edit(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                saved = self._save_pathway_for_edit_test(
                    client, headers
                )

                pathway_id = saved["pathway_id"]
                first_step = saved["steps"][0]
                original_source = first_step["source_step"]

                approved = client.post(
                    f"/api/pathways/saved/{pathway_id}/approve",
                    headers=headers,
                    json={
                        "expected_revision": 1,
                        "confirmed": True
                    }
                )

                self.assertEqual(approved.status_code, 200)

                # Edit the previously approved pathway.
                edited = client.put(
                    f"/api/pathways/saved/{pathway_id}"
                    f"/steps/{first_step['id']}",
                    headers=headers,
                    json={
                        "expected_revision": 1,
                        "title": "Contact the opportunity provider",
                        "student_note": "Verify entry requirements.",
                        "included": True
                    }
                )

                self.assertEqual(edited.status_code, 200)
                self.assertEqual(
                    edited.json()["revision"],
                    2
                )
                self.assertFalse(
                    edited.json()["can_export"]
                )

                # The modified version must be blocked.
                blocked = client.post(
                    f"/api/pathways/saved/{pathway_id}/export",
                    headers=headers,
                    json={"expected_revision": 2}
                )

                self.assertEqual(blocked.status_code, 409)

                # Explicitly approve the new revision.
                reapproved = client.post(
                    f"/api/pathways/saved/{pathway_id}/approve",
                    headers=headers,
                    json={
                        "expected_revision": 2,
                        "confirmed": True
                    }
                )

                self.assertEqual(reapproved.status_code, 200)

                exported = client.post(
                    f"/api/pathways/saved/{pathway_id}/export",
                    headers=headers,
                    json={"expected_revision": 2}
                )

                self.assertEqual(exported.status_code, 200)

                data = exported.json()

                self.assertEqual(data["revision"], 2)
                self.assertEqual(
                    data["approved_revision"],
                    2
                )

                exported_step = data["steps"][0]

                self.assertEqual(
                    exported_step["title"],
                    "Contact the opportunity provider"
                )
                self.assertEqual(
                    exported_step["student_note"],
                    "Verify entry requirements."
                )

                # Original published evidence remains
                # separate from the student's edits.
                self.assertEqual(
                    exported_step["original_source_step"],
                    original_source
                )

    def test_pathway_export_excludes_disabled_actions(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                saved = self._save_pathway_for_edit_test(
                    client, headers
                )

                pathway_id = saved["pathway_id"]
                first_step = saved["steps"][0]

                edited = client.put(
                    f"/api/pathways/saved/{pathway_id}"
                    f"/steps/{first_step['id']}",
                    headers=headers,
                    json={
                        "expected_revision": 1,
                        "title": first_step["title"],
                        "student_note": "Excluded from export.",
                        "included": False
                    }
                )

                self.assertEqual(edited.status_code, 200)

                approved = client.post(
                    f"/api/pathways/saved/{pathway_id}/approve",
                    headers=headers,
                    json={
                        "expected_revision": 2,
                        "confirmed": True
                    }
                )

                self.assertEqual(approved.status_code, 200)

                response = client.post(
                    f"/api/pathways/saved/{pathway_id}/export",
                    headers=headers,
                    json={"expected_revision": 2}
                )

                self.assertEqual(response.status_code, 200)

                exported_steps = response.json()["steps"]

                self.assertEqual(len(exported_steps), 4)
                self.assertEqual(
                    [
                        step["position"]
                        for step in exported_steps
                    ],
                    [1, 2, 3, 4]
                )

                exported_source_ids = {
                    step["original_source_step"]["step_id"]
                    for step in exported_steps
                    if step["original_source_step"] is not None
                }

                self.assertNotIn(
                    first_step["source_step_id"],
                    exported_source_ids
                )

    def test_pathway_export_preserves_student_actions(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                saved = self._save_pathway_for_edit_test(
                    client, headers
                )
                pathway_id = saved["pathway_id"]

                created = client.post(
                    f"/api/pathways/saved/{pathway_id}/steps",
                    headers=headers,
                    json={
                        "expected_revision": 1,
                        "title": "Attend a career workshop",
                        "student_note": "Register next week.",
                        "included": True
                    }
                )

                self.assertEqual(created.status_code, 200)

                approved = client.post(
                    f"/api/pathways/saved/{pathway_id}/approve",
                    headers=headers,
                    json={
                        "expected_revision": 2,
                        "confirmed": True
                    }
                )

                self.assertEqual(approved.status_code, 200)

                response = client.post(
                    f"/api/pathways/saved/{pathway_id}/export",
                    headers=headers,
                    json={"expected_revision": 2}
                )

                self.assertEqual(response.status_code, 200)

                exported_steps = response.json()["steps"]

                self.assertEqual(len(exported_steps), 6)

                personal_step = exported_steps[-1]

                self.assertEqual(
                    personal_step["origin"],
                    "student"
                )
                self.assertEqual(
                    personal_step["title"],
                    "Attend a career workshop"
                )
                self.assertEqual(
                    personal_step["student_note"],
                    "Register next week."
                )
                self.assertIsNone(
                    personal_step["original_source_step"]
                )

                # Generated actions must still carry
                # their original evidence.
                for before, after in zip(
                    saved["steps"],
                    exported_steps[:5]
                ):
                    self.assertEqual(
                        after["origin"],
                        "generated"
                    )
                    self.assertEqual(
                        after["original_source_step"],
                        before["source_step"]
                    )

    def test_pathway_export_rejects_invalid_payloads(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                saved = self._save_pathway_for_edit_test(
                    client, headers
                )

                pathway_id = saved["pathway_id"]

                url = (
                    f"/api/pathways/saved/{pathway_id}/export"
                )

                invalid_payloads = [
                    {"expected_revision": 0},
                    {"expected_revision": -1},
                    {"expected_revision": True},
                    {"expected_revision": "1"},
                    {"expected_revision": None},
                    {"expected_revision": 1.5},
                    {"expected_revision": 1, "extra": "invalid"},
                    {}
                ]

                for payload in invalid_payloads:

                    with self.subTest(payload=payload):

                        response = client.post(
                            url,
                            headers=headers,
                            json=payload
                        )

                        self.assertEqual(
                            response.status_code,
                            422
                        )

                # Invalid export requests must not
                # change or approve the draft.
                retrieved = client.get(
                    f"/api/pathways/saved/{pathway_id}",
                    headers=headers
                ).json()

                self.assertEqual(retrieved["revision"], 1)
                self.assertFalse(retrieved["approved"])
                self.assertFalse(retrieved["can_export"])

    def test_pathway_export_requires_local_dev_access(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                saved = self._save_pathway_for_edit_test(
                    client, headers
                )

                approved = client.post(
                    f"/api/pathways/saved/"
                    f"{saved['pathway_id']}/approve",
                    headers=headers,
                    json={
                        "expected_revision": 1,
                        "confirmed": True
                    }
                )

                self.assertEqual(approved.status_code, 200)

        url = (
            f"/api/pathways/saved/"
            f"{saved['pathway_id']}/export"
        )

        payload = {"expected_revision": 1}

        # No development key configured.
        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": ""}
        ):
            with self._make_local_pathway_client() as client:

                disabled = client.post(
                    url,
                    headers=headers,
                    json=payload
                )

                self.assertEqual(
                    disabled.status_code,
                    503
                )

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                # Wrong development key.
                incorrect = client.post(
                    url,
                    headers={
                        "X-FuturePath-Dev-Key": "incorrect"
                    },
                    json=payload
                )

                self.assertEqual(
                    incorrect.status_code,
                    401
                )

            # Correct key from a non-local client.
            remote = self.client.post(
                url,
                headers=headers,
                json=payload
            )

            self.assertEqual(remote.status_code, 403)

            # Ensure rejected requests did not
            # change the pathway.
            with self._make_local_pathway_client() as client:

                retrieved = client.get(
                    f"/api/pathways/saved/"
                    f"{saved['pathway_id']}",
                    headers=headers
                ).json()

        self.assertEqual(retrieved["revision"], 1)
        self.assertTrue(retrieved["approved"])
        self.assertTrue(retrieved["can_export"])

    def test_pathway_export_handles_missing_resources(self):

        key = "test-only-" + ("A" * 40)
        headers = {"X-FuturePath-Dev-Key": key}

        with patch.dict(
            os.environ,
            {"FUTUREPATH_DEV_API_KEY": key}
        ):
            with self._make_local_pathway_client() as client:

                unknown = client.post(
                    "/api/pathways/saved/"
                    "nonexistent-pathway/export",
                    headers=headers,
                    json={"expected_revision": 1}
                )

                self.assertEqual(
                    unknown.status_code,
                    404
                )

            missing_db = (
                Path(self.temp_dir.name)
                / "missing_export_database.db"
            )

            self.assertFalse(missing_db.exists())

            with patch(
                "main.DATABASE_PATH",
                missing_db
            ):
                with self._make_local_pathway_client() as client:

                    unavailable = client.post(
                        "/api/pathways/saved/"
                        "example-pathway/export",
                        headers=headers,
                        json={"expected_revision": 1}
                    )

                    self.assertEqual(
                        unavailable.status_code,
                        503
                    )

            # Failed export must never create
            # an empty database.
            self.assertFalse(missing_db.exists())

if __name__ == "__main__":
    unittest.main()
