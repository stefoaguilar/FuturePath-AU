
from eligibility import evaluate_condition


def analyse_opportunity_gaps(
    opportunity: dict,
    profile: dict
) -> dict:

    # Never use identity answers for automated evaluation.
    safe_profile = {
        key: value
        for key, value in profile.items()
        if key != "identity_answer"
    }

    # Reuse the existing eligibility engine.
    evaluations = [
        evaluate_condition(condition, safe_profile)
        for condition in opportunity["eligibility_conditions"]
    ]

    # Only genuinely unmet supported requirements
    # are reported as confirmed unmet.
    confirmed_unmet = [
        result
        for result in evaluations
        if result["status"] == "unmet"
    ]

    # Unresolved conditions require user/provider review.
    needs_review = [
        result
        for result in evaluations
        if result["status"] == "uncertain"
    ]

    # Compare reported skill names without assuming
    # that opportunity skill tags are mandatory.
    reported_skills = safe_profile.get("skills", [])

    if not isinstance(reported_skills, list):
        reported_skills = []

    normalised_skills = {
        skill.strip().casefold()
        for skill in reported_skills
        if isinstance(skill, str) and skill.strip()
    }

    skills_to_explore = [
        skill
        for skill in opportunity.get("skills", [])
        if isinstance(skill, str)
        and skill.strip()
        and skill.strip().casefold() not in normalised_skills
    ]

    return {
        "opportunity_id": opportunity["id"],
        "confirmed_unmet_requirements": confirmed_unmet,
        "requirements_needing_review": needs_review,
        "skills_to_explore": skills_to_explore,
        "source_url": opportunity["source_url"],
        "notice": (
            "Unmet results refer only to supported "
            "published eligibility comparisons. "
            "Skills to explore are opportunity-related "
            "areas not confirmed in the submitted profile. "
            "They are not verified missing qualifications "
            "or grounds for ineligibility."
        )
    }
