
import json
import unittest
from pathlib import Path

from eligibility import evaluate_condition


# Use Samer's actual opportunity dataset.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = PROJECT_ROOT / "data" / "opportunities.json"


class TestEligibility(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        dataset = json.loads(
            DATA_FILE.read_text(encoding="utf-8")
        )

        cls.conditions = {
            condition["id"]: condition
            for opportunity in dataset["opportunities"]
            for condition in opportunity["eligibility_conditions"]
        }

    def check_status(self, condition_id, profile):
        condition = self.conditions[condition_id]
        result = evaluate_condition(condition, profile)
        return result["status"]

    # Australian citizenship requirement

    def test_citizenship_satisfied(self):
        profile = {
            "citizenship_status": "australian_citizen"
        }
        self.assertEqual(
            self.check_status("OPP-003-E2", profile),
            "satisfied"
        )

    def test_citizenship_unmet(self):
        profile = {
            "citizenship_status": "nz_citizen"
        }
        self.assertEqual(
            self.check_status("OPP-003-E2", profile),
            "unmet"
        )

    def test_citizenship_missing(self):
        self.assertEqual(
            self.check_status("OPP-003-E2", {}),
            "uncertain"
        )

    # Course weighted average requirement

    def test_average_satisfied(self):
        self.assertEqual(
            self.check_status(
                "OPP-003-E4",
                {"weighted_average": 65}
            ),
            "satisfied"
        )

    def test_average_unmet(self):
        self.assertEqual(
            self.check_status(
                "OPP-003-E4",
                {"weighted_average": 45}
            ),
            "unmet"
        )

    def test_average_missing(self):
        self.assertEqual(
            self.check_status("OPP-003-E4", {}),
            "uncertain"
        )

    def test_average_invalid(self):
        self.assertEqual(
            self.check_status(
                "OPP-003-E4",
                {"weighted_average": "invalid"}
            ),
            "uncertain"
        )

    def test_average_boolean_rejected(self):
        self.assertEqual(
            self.check_status(
                "OPP-003-E4",
                {"weighted_average": True}
            ),
            "uncertain"
        )

    # Safety and unsupported-condition checks

    def test_identity_never_automatically_evaluated(self):
        self.assertEqual(
            self.check_status(
                "OPP-003-E1",
                {"identity_answer": "yes"}
            ),
            "uncertain"
        )

    def test_human_review_condition(self):
        self.assertEqual(
            self.check_status("OPP-003-E6", {}),
            "uncertain"
        )

    def test_unsupported_condition_stays_uncertain(self):
        self.assertEqual(
            self.check_status(
                "OPP-003-E3",
                {"enrolment_status": "enrolled_full_time"}
            ),
            "uncertain"
        )


if __name__ == "__main__":
    unittest.main()
