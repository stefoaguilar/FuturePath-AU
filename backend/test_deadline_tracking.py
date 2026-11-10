
import json
import unittest
from copy import deepcopy
from datetime import date
from pathlib import Path

from deadline_tracking import analyse_opportunity_deadline


class TestDeadlineTracking(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Load Samer's original opportunity dataset.
        project_root = Path(__file__).resolve().parent.parent
        data_file = project_root / "data" / "opportunities.json"

        with data_file.open("r", encoding="utf-8") as file:
            dataset = json.load(file)

        cls.opportunities = {
            item["id"]: item
            for item in dataset["opportunities"]
        }

        # Fixed date keeps tests reproducible.
        cls.reference_date = date(2026, 11, 10)

    def test_passed_deadline(self):
        result = analyse_opportunity_deadline(
            self.opportunities["OPP-004"],
            self.reference_date
        )

        self.assertEqual(
            result["classification"],
            "deadline_passed"
        )
        self.assertEqual(result["days_until_deadline"], -10)

    def test_future_deadline(self):
        result = analyse_opportunity_deadline(
            self.opportunities["OPP-030"],
            self.reference_date
        )

        self.assertEqual(
            result["classification"],
            "deadline_future"
        )
        self.assertEqual(result["days_until_deadline"], 20)

    def test_deadline_today(self):
        result = analyse_opportunity_deadline(
            self.opportunities["OPP-030"],
            date(2026, 11, 30)
        )

        self.assertEqual(
            result["classification"],
            "deadline_today"
        )
        self.assertEqual(result["days_until_deadline"], 0)

    def test_reported_closed_with_date(self):
        result = analyse_opportunity_deadline(
            self.opportunities["OPP-003"],
            self.reference_date
        )

        self.assertEqual(
            result["classification"],
            "reported_closed"
        )

    def test_reported_closed_without_date(self):
        result = analyse_opportunity_deadline(
            self.opportunities["OPP-007"],
            self.reference_date
        )

        self.assertEqual(
            result["classification"],
            "reported_closed"
        )
        self.assertIsNone(result["deadline_date"])

    def test_unknown_deadline(self):
        result = analyse_opportunity_deadline(
            self.opportunities["OPP-001"],
            self.reference_date
        )

        self.assertEqual(
            result["classification"],
            "unknown"
        )
        self.assertIsNone(result["days_until_deadline"])

    def test_opening_date_note_does_not_imply_open(self):
        # OPP-008 mentions an opening date in its note,
        # but has no structured application closing date.
        result = analyse_opportunity_deadline(
            self.opportunities["OPP-008"],
            self.reference_date
        )

        self.assertEqual(
            result["classification"],
            "unknown"
        )

    def test_conflicting_verification(self):
        result = analyse_opportunity_deadline(
            self.opportunities["OPP-002"],
            self.reference_date
        )

        self.assertEqual(
            result["classification"],
            "needs_review"
        )

    def test_needs_recheck_verification(self):
        result = analyse_opportunity_deadline(
            self.opportunities["OPP-005"],
            self.reference_date
        )

        self.assertEqual(
            result["classification"],
            "needs_review"
        )

    def test_invalid_recorded_date(self):
        opportunity = deepcopy(
            self.opportunities["OPP-030"]
        )

        opportunity["deadline"]["date"] = "2026-02-30"

        result = analyse_opportunity_deadline(
            opportunity,
            self.reference_date
        )

        self.assertEqual(
            result["classification"],
            "needs_review"
        )

    def test_date_status_without_date(self):
        opportunity = deepcopy(
            self.opportunities["OPP-030"]
        )

        opportunity["deadline"]["date"] = None

        result = analyse_opportunity_deadline(
            opportunity,
            self.reference_date
        )

        self.assertEqual(
            result["classification"],
            "needs_review"
        )

    def test_unknown_status_with_recorded_date(self):
        opportunity = deepcopy(
            self.opportunities["OPP-030"]
        )

        opportunity["deadline"]["status"] = "unknown"

        result = analyse_opportunity_deadline(
            opportunity,
            self.reference_date
        )

        self.assertEqual(
            result["classification"],
            "needs_review"
        )

    def test_closed_status_with_future_date(self):
        opportunity = deepcopy(
            self.opportunities["OPP-030"]
        )

        opportunity["deadline"]["status"] = "closed"

        result = analyse_opportunity_deadline(
            opportunity,
            self.reference_date
        )

        self.assertEqual(
            result["classification"],
            "needs_review"
        )

    def test_source_and_round_notes_preserved(self):
        opportunity = self.opportunities["OPP-030"]

        result = analyse_opportunity_deadline(
            opportunity,
            self.reference_date
        )

        self.assertEqual(
            result["source_url"],
            opportunity["source_url"]
        )
        self.assertEqual(
            result["verified_on"],
            "2026-10-27"
        )
        self.assertEqual(
            result["reference_date"],
            "2026-11-10"
        )
        self.assertIn(
            "Round 2",
            result["deadline_note"]
        )
        self.assertIn(
            "newer rounds",
            result["notice"]
        )


if __name__ == "__main__":
    unittest.main()
