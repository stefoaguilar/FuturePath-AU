
from math import isfinite


def evaluate_condition(condition: dict, profile: dict) -> dict:
    """
    Evaluate one published eligibility condition.

    Returns satisfied, unmet or uncertain.
    Only explicitly supported rules can produce a
    satisfied or unmet result.
    """

    condition_id = condition.get("id")

    # Safe default: never guess.
    status = "uncertain"
    explanation = (
        "This requirement cannot yet be evaluated automatically. "
        "Please review the published conditions."
    )

    # Identity conditions are never automatically evaluated.
    if condition.get("type") == "identity_requirement":
        explanation = (
            "Identity requirements require voluntary user "
            "confirmation and are not automatically assessed."
        )

    # Conditions not marked as checkable stay uncertain.
    elif condition.get("checkable_from_profile") is not True:
        explanation = (
            "This requirement needs additional information "
            "or human review."
        )

    # OPP-003-E2: Australian citizenship required.
    elif (
        condition_id == "OPP-003-E2"
        and condition.get("type") == "citizenship_residency"
    ):
        citizenship = profile.get("citizenship_status")

        if citizenship == "australian_citizen":
            status = "satisfied"
            explanation = (
                "The profile states Australian citizenship, "
                "matching the published requirement."
            )

        elif citizenship in {
            "permanent_resident",
            "nz_citizen",
            "other"
        }:
            status = "unmet"
            explanation = (
                "The stated citizenship status does not meet "
                "this opportunity's Australian citizenship requirement."
            )

        else:
            explanation = (
                "Australian citizenship has not been confirmed "
                "in the profile."
            )

    # OPP-003-E4: Course weighted average at least 50.
    elif (
        condition_id == "OPP-003-E4"
        and condition.get("type") == "education"
    ):
        average = profile.get("weighted_average")

        # Reject missing, boolean and invalid numeric inputs.
        if (
            type(average) in (int, float)
            and isfinite(average)
            and 0 <= average <= 100
        ):
            if average >= 50:
                status = "satisfied"
                explanation = (
                    f"The stated weighted average ({average}) "
                    "meets the published minimum of 50."
                )
            else:
                status = "unmet"
                explanation = (
                    f"The stated weighted average ({average}) "
                    "is below the published minimum of 50."
                )

        else:
            explanation = (
                "A valid course weighted average has not "
                "been supplied."
            )

    # Preserve the source evidence for the frontend.
    return {
        "condition_id": condition_id,
        "status": status,
        "explanation": explanation,
        "requirement": condition.get("text"),
        "evidence_summary": condition.get("evidence_summary"),
        "source_url": condition.get("source_url")
    }
