
import json
import unittest
from datetime import date
from pathlib import Path

from pathway_generation import generate_draft_pathway


class TestPathwayGeneration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Load Samer's original opportunity dataset.
        dataset_path = (
            Path(__file__).resolve().parent.parent
            / "data"
            / "opportunities.json"
        )

        with dataset_path.open(
            "r",
            encoding="utf-8"
        ) as file:
            dataset = json.load(file)

        cls.opportunities = {
            opportunity["id"]: opportunity
            for opportunity in dataset["opportunities"]
        }

        # Use a fixed date for reproducible tests.
        cls.reference_date = date(2026, 11, 28)

    def make_pathway(self, opportunity_id, profile=None):
        if profile is None:
            profile = {}

        return generate_draft_pathway(
            self.opportunities[opportunity_id],
            profile,
            self.reference_date
        )

    # --------------------------------------------------
    # 1. Draft approval and export safeguards
    # --------------------------------------------------

    def test_pathway_starts_as_unapproved_draft(self):
        pathway = self.make_pathway("OPP-003")

        self.assertEqual(pathway["status"], "draft")
        self.assertFalse(pathway["approved"])
        self.assertFalse(pathway["can_export"])
        self.assertEqual(
            pathway["reference_date"],
            "2026-11-28"
        )
        self.assertTrue(pathway["steps"])

    # --------------------------------------------------
    # 2. Unmet published requirements
    # --------------------------------------------------

    def test_unmet_requirement_generates_review_step(self):
        pathway = self.make_pathway(
            "OPP-003",
            {
                "citizenship_status": "nz_citizen",
                "weighted_average": 65
            }
        )

        steps = {
            step["step_id"]: step
            for step in pathway["steps"]
        }

        citizenship = steps["requirement:OPP-003-E2"]

        self.assertEqual(
            citizenship["eligibility_status"],
            "unmet"
        )
        self.assertEqual(
            citizenship["category"],
            "requirement_review"
        )

    # --------------------------------------------------
    # 3. Satisfied requirements
    # --------------------------------------------------

    def test_satisfied_requirements_do_not_generate_steps(self):
        pathway = self.make_pathway(
            "OPP-003",
            {
                "citizenship_status": "australian_citizen",
                "weighted_average": 65
            }
        )

        step_ids = {
            step["step_id"]
            for step in pathway["steps"]
        }

        self.assertNotIn(
            "requirement:OPP-003-E2",
            step_ids
        )
        self.assertNotIn(
            "requirement:OPP-003-E4",
            step_ids
        )

    # --------------------------------------------------
    # 4. Missing information remains uncertain
    # --------------------------------------------------

    def test_empty_profile_does_not_create_unmet_results(self):
        pathway = self.make_pathway(
            "OPP-003",
            {}
        )

        requirement_steps = [
            step
            for step in pathway["steps"]
            if step["step_id"].startswith("requirement:")
        ]

        self.assertTrue(requirement_steps)

        self.assertTrue(
            all(
                step["eligibility_status"] == "uncertain"
                for step in requirement_steps
            )
        )

    # --------------------------------------------------
    # 5. Identity requires human review
    # --------------------------------------------------

    def test_identity_requirement_needs_human_review(self):
        pathway = self.make_pathway(
            "OPP-001",
            {"identity_answer": "yes"}
        )

        steps = {
            step["step_id"]: step
            for step in pathway["steps"]
        }

        identity_step = steps["requirement:OPP-001-E1"]

        self.assertEqual(
            identity_step["category"],
            "human_review"
        )
        self.assertEqual(
            identity_step["eligibility_status"],
            "uncertain"
        )

    # --------------------------------------------------
    # 6. Advisory skill exploration
    # --------------------------------------------------

    def test_unreported_skills_are_advisory(self):
        pathway = self.make_pathway(
            "OPP-001",
            {
                "skills": [
                    "writing",
                    "customer service"
                ]
            }
        )

        skill_steps = [
            step
            for step in pathway["steps"]
            if step["category"] == "skill_exploration"
        ]

        titles = {
            step["title"]
            for step in skill_steps
        }

        self.assertEqual(
            titles,
            {
                "Explore ICT",
                "Explore cyber security",
                "Explore digital delivery"
            }
        )

        for step in skill_steps:
            self.assertIsNone(
                step["eligibility_status"]
            )
            self.assertIn(
                "optional",
                step["explanation"]
            )

    # --------------------------------------------------
    # 7. Reported skills are not suggested again
    # --------------------------------------------------

    def test_reported_skills_are_not_recommended_again(self):
        pathway = self.make_pathway(
            "OPP-001",
            {
                "skills": [
                    "ICT",
                    "cyber security"
                ]
            }
        )

        skill_titles = {
            step["title"]
            for step in pathway["steps"]
            if step["category"] == "skill_exploration"
        }

        self.assertEqual(
            skill_titles,
            {"Explore digital delivery"}
        )

    # --------------------------------------------------
    # 8. Future application deadline
    # --------------------------------------------------

    def test_future_deadline_generates_verification_step(self):
        pathway = self.make_pathway(
            "OPP-030"
        )

        deadline_step = next(
            step
            for step in pathway["steps"]
            if step["category"] == "deadline_review"
        )

        self.assertEqual(
            deadline_step["deadline_classification"],
            "deadline_future"
        )
        self.assertEqual(
            deadline_step["deadline_date"],
            "2026-11-30"
        )
        self.assertEqual(
            deadline_step["days_until_deadline"],
            2
        )

    # --------------------------------------------------
    # 9. Passed application deadline
    # --------------------------------------------------

    def test_passed_deadline_suggests_future_round_check(self):
        pathway = self.make_pathway(
            "OPP-004"
        )

        deadline_step = next(
            step
            for step in pathway["steps"]
            if step["category"] == "deadline_review"
        )

        self.assertEqual(
            deadline_step["deadline_classification"],
            "deadline_passed"
        )
        self.assertEqual(
            deadline_step["title"],
            "Check for a future application round"
        )

    # --------------------------------------------------
    # 10. Unknown application deadline
    # --------------------------------------------------

    def test_unknown_deadline_does_not_invent_date(self):
        pathway = self.make_pathway(
            "OPP-001"
        )

        deadline_step = next(
            step
            for step in pathway["steps"]
            if step["category"] == "deadline_review"
        )

        self.assertEqual(
            deadline_step["deadline_classification"],
            "unknown"
        )
        self.assertIsNone(
            deadline_step["deadline_date"]
        )
        self.assertIsNone(
            deadline_step["days_until_deadline"]
        )

    # --------------------------------------------------
    # 11. Conflicting source information
    # --------------------------------------------------

    def test_conflicting_source_requires_rechecking(self):
        pathway = self.make_pathway(
            "OPP-002"
        )

        deadline_step = next(
            step
            for step in pathway["steps"]
            if step["category"] == "deadline_review"
        )

        self.assertEqual(
            deadline_step["deadline_classification"],
            "needs_review"
        )
        self.assertEqual(
            deadline_step["title"],
            "Recheck the application deadline source"
        )

    # --------------------------------------------------
    # 12. Identity answer does not change automatic output
    # --------------------------------------------------

    def test_identity_answer_does_not_affect_pathway(self):
        profile_yes = {
            "citizenship_status": "australian_citizen",
            "identity_answer": "yes"
        }

        profile_no = {
            "citizenship_status": "australian_citizen",
            "identity_answer": "no"
        }

        pathway_yes = self.make_pathway(
            "OPP-001",
            profile_yes
        )

        pathway_no = self.make_pathway(
            "OPP-001",
            profile_no
        )

        self.assertEqual(
            pathway_yes,
            pathway_no
        )

        # Confirm original profile data was not changed.
        self.assertEqual(
            profile_yes["identity_answer"],
            "yes"
        )


if __name__ == "__main__":
    unittest.main()
