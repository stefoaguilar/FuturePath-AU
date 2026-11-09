

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from database import create_database
from import_data import import_opportunities
from main import app




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
            statuses["OPP-003-E1"], "uncertain"
        )
        self.assertEqual(
            statuses["OPP-003-E2"], "satisfied"
        )
        self.assertEqual(
            statuses["OPP-003-E4"], "satisfied"
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
            statuses["OPP-003-E2"], "unmet"
        )
        self.assertEqual(
            statuses["OPP-003-E4"], "satisfied"
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
                    "body", "profile", "citizenship_status"
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


if __name__ == "__main__":
    unittest.main()
