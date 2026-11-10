
import json
import unittest
from pathlib import Path

from gap_analysis import analyse_opportunity_gaps


class TestGapAnalysis(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Read Samer's original opportunity dataset.
        project_root = Path(__file__).resolve().parent.parent
        data_file = project_root / "data" / "opportunities.json"

        with data_file.open("r", encoding="utf-8") as file:
            dataset = json.load(file)

        cls.opportunities = {
            item["id"]: item
            for item in dataset["opportunities"]
        }

    def test_unmet_citizenship_identified(self):
        result = analyse_opportunity_gaps(
            self.opportunities["OPP-003"],
            {
                "citizenship_status": "nz_citizen",
                "weighted_average": 65
            }
        )

        unmet_ids = [
            item["condition_id"]
            for item in result["confirmed_unmet_requirements"]
        ]

        self.assertEqual(unmet_ids, ["OPP-003-E2"])

    def test_uncertain_requirements_preserved(self):
        result = analyse_opportunity_gaps(
            self.opportunities["OPP-003"],
            {}
        )

        review_ids = [
            item["condition_id"]
            for item in result["requirements_needing_review"]
        ]

        self.assertEqual(len(review_ids), 6)
        self.assertIn("OPP-003-E1", review_ids)

    def test_identity_never_automatically_scored(self):
        opportunity = self.opportunities["OPP-003"]

        for answer in ("yes", "no", "not_stated"):
            with self.subTest(answer=answer):
                result = analyse_opportunity_gaps(
                    opportunity,
                    {"identity_answer": answer}
                )

                review_ids = [
                    item["condition_id"]
                    for item in result["requirements_needing_review"]
                ]

                self.assertIn("OPP-003-E1", review_ids)
                self.assertEqual(
                    result["confirmed_unmet_requirements"],
                    []
                )

    def test_unreported_skills_are_advisory(self):
        result = analyse_opportunity_gaps(
            self.opportunities["OPP-001"],
            {"skills": ["ICT"]}
        )

        self.assertEqual(
            result["skills_to_explore"],
            ["cyber security", "digital delivery"]
        )

        self.assertEqual(
            result["confirmed_unmet_requirements"],
            []
        )

    def test_skill_matching_ignores_case(self):
        result = analyse_opportunity_gaps(
            self.opportunities["OPP-001"],
            {"skills": ["  ict  ", "CYBER SECURITY"]}
        )

        self.assertEqual(
            result["skills_to_explore"],
            ["digital delivery"]
        )

    def test_empty_opportunity_skills_handled(self):
        result = analyse_opportunity_gaps(
            self.opportunities["OPP-005"],
            {"skills": ["Python"]}
        )

        self.assertEqual(result["skills_to_explore"], [])

    def test_source_url_preserved(self):
        opportunity = self.opportunities["OPP-003"]

        result = analyse_opportunity_gaps(
            opportunity,
            {}
        )

        self.assertEqual(
            result["source_url"],
            opportunity["source_url"]
        )

    def test_profile_not_modified(self):
        profile = {
            "citizenship_status": "australian_citizen",
            "identity_answer": "yes",
            "skills": ["Python"]
        }

        original_profile = profile.copy()

        analyse_opportunity_gaps(
            self.opportunities["OPP-003"],
            profile
        )

        self.assertEqual(profile, original_profile)


if __name__ == "__main__":
    unittest.main()
