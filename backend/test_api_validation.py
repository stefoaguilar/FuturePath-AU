
import unittest

from pydantic import ValidationError

from main import EligibilityRequest


class TestAPIValidation(unittest.TestCase):

    def test_valid_profile_accepted(self):
        request = EligibilityRequest.model_validate({
            "opportunity_id": "OPP-003",
            "profile": {
                "citizenship_status": "australian_citizen",
                "weighted_average": 65
            }
        })

        self.assertEqual(
            request.profile.citizenship_status,
            "australian_citizen"
        )
        self.assertEqual(
            request.profile.weighted_average,
            65
        )

    def test_empty_profile_accepted(self):
        request = EligibilityRequest.model_validate({
            "opportunity_id": "OPP-003",
            "profile": {}
        })

        self.assertEqual(
            request.profile.model_dump(exclude_unset=True),
            {}
        )

    def test_full_default_profile_accepted(self):
        profile = {
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

        request = EligibilityRequest.model_validate({
            "opportunity_id": "OPP-003",
            "profile": profile
        })

        self.assertEqual(
            request.profile.model_dump(exclude_unset=True),
            profile
        )

    def test_invalid_citizenship_rejected(self):
        with self.assertRaises(ValidationError):
            EligibilityRequest.model_validate({
                "opportunity_id": "OPP-003",
                "profile": {
                    "citizenship_status": "banana"
                }
            })

    def test_average_above_100_rejected(self):
        with self.assertRaises(ValidationError):
            EligibilityRequest.model_validate({
                "opportunity_id": "OPP-003",
                "profile": {
                    "weighted_average": 150
                }
            })

    def test_negative_average_rejected(self):
        with self.assertRaises(ValidationError):
            EligibilityRequest.model_validate({
                "opportunity_id": "OPP-003",
                "profile": {
                    "weighted_average": -5
                }
            })

    def test_average_as_string_rejected(self):
        with self.assertRaises(ValidationError):
            EligibilityRequest.model_validate({
                "opportunity_id": "OPP-003",
                "profile": {
                    "weighted_average": "65"
                }
            })

    def test_invalid_skills_type_rejected(self):
        with self.assertRaises(ValidationError):
            EligibilityRequest.model_validate({
                "opportunity_id": "OPP-003",
                "profile": {
                    "skills": "Python"
                }
            })

    def test_unexpected_profile_field_rejected(self):
        with self.assertRaises(ValidationError):
            EligibilityRequest.model_validate({
                "opportunity_id": "OPP-003",
                "profile": {
                    "unknown_field": "unexpected"
                }
            })

    def test_missing_profile_rejected(self):
        with self.assertRaises(ValidationError):
            EligibilityRequest.model_validate({
                "opportunity_id": "OPP-003"
            })

    def test_identity_excluded_from_evaluation(self):
        request = EligibilityRequest.model_validate({
            "opportunity_id": "OPP-003",
            "profile": {
                "identity_answer": "yes",
                "citizenship_status": "australian_citizen"
            }
        })

        profile_data = request.profile.model_dump(
            exclude_unset=True,
            exclude={"identity_answer"}
        )

        self.assertNotIn(
            "identity_answer",
            profile_data
        )
        self.assertEqual(
            profile_data["citizenship_status"],
            "australian_citizen"
        )


if __name__ == "__main__":
    unittest.main()
