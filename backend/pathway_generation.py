
from datetime import date

from eligibility import evaluate_condition
from gap_analysis import analyse_opportunity_gaps
from deadline_tracking import analyse_opportunity_deadline


def generate_draft_pathway(
    opportunity: dict,
    profile: dict,
    reference_date: date
) -> dict:
    """
    Generate a source-grounded, unapproved student pathway.

    Suggestions are informational and must be reviewed by
    the student before approval or export.
    """

    # Identity answers are never used for automatic scoring.
    safe_profile = {
        key: value
        for key, value in profile.items()
        if key != "identity_answer"
    }

    opportunity_id = opportunity["id"]
    source_url = opportunity["source_url"]
    steps = []

    # --------------------------------------------------
    # 1. Published requirements requiring attention
    # --------------------------------------------------

    for condition in opportunity["eligibility_conditions"]:

        result = evaluate_condition(
            condition,
            safe_profile
        )

        status = result["status"]

        # Satisfied requirements do not need action steps.
        if status == "satisfied":
            continue

        if condition["type"] == "identity_requirement":
            title = "Review the published identity requirement"
            category = "human_review"
            explanation = (
                "This requirement requires personal review. "
                "The system does not infer or score identity."
            )

        elif status == "unmet":
            title = "Review a potentially unmet requirement"
            category = "requirement_review"
            explanation = (
                "The available profile information does not "
                "meet this published requirement. Review the "
                "source and decide what action, if any, is possible."
            )

        else:
            title = "Check an uncertain requirement"
            category = "human_review"
            explanation = (
                "There is not enough supported information "
                "to confirm whether this requirement is met. "
                "Check the published criteria or provide "
                "additional information."
            )

        steps.append({
            "step_id": f"requirement:{condition['id']}",
            "category": category,
            "title": title,
            "description": condition["text"],
            "explanation": explanation,
            "eligibility_status": status,
            "source_url": (
                condition.get("source_url") or source_url
            ),
            "editable": True
        })

    # --------------------------------------------------
    # 2. Advisory skill-development suggestions
    # --------------------------------------------------

    gap_results = analyse_opportunity_gaps(
        opportunity,
        safe_profile
    )

    for index, skill in enumerate(
        gap_results["skills_to_explore"],
        start=1
    ):

        steps.append({
            "step_id": f"skill:{index}",
            "category": "skill_exploration",
            "title": f"Explore {skill}",
            "description": (
                f"The opportunity lists '{skill}' as a "
                "related skill, but it is not mentioned "
                "in the submitted profile."
            ),
            "explanation": (
                "This is an optional development suggestion, "
                "not a confirmed skills deficiency or "
                "mandatory eligibility requirement."
            ),
            "eligibility_status": None,
            "source_url": source_url,
            "editable": True
        })

    # --------------------------------------------------
    # 3. Application deadline guidance
    # --------------------------------------------------

    deadline_results = analyse_opportunity_deadline(
        opportunity,
        reference_date
    )

    classification = deadline_results["classification"]

    if classification in (
        "deadline_passed",
        "reported_closed"
    ):
        deadline_title = "Check for a future application round"

    elif classification in (
        "deadline_future",
        "deadline_today"
    ):
        deadline_title = "Verify the recorded application deadline"

    elif classification == "needs_review":
        deadline_title = "Recheck the application deadline source"

    else:
        deadline_title = "Check the provider for application dates"

    steps.append({
        "step_id": "deadline:review",
        "category": "deadline_review",
        "title": deadline_title,
        "description": deadline_results["explanation"],
        "explanation": (
            "The deadline information applies to the "
            "recorded application round only. Confirm "
            "current information with the provider."
        ),
        "deadline_classification": classification,
        "deadline_date": deadline_results["deadline_date"],
        "days_until_deadline": (
            deadline_results["days_until_deadline"]
        ),
        "deadline_note": (
            deadline_results["deadline_note"]
        ),
        "source_url": deadline_results["source_url"],
        "editable": True
    })

    # --------------------------------------------------
    # 4. Source verification
    # --------------------------------------------------

    steps.append({
        "step_id": "source:verify",
        "category": "source_verification",
        "title": "Review the official opportunity information",
        "description": (
            "Check the provider's published information "
            "before making an application decision."
        ),
        "explanation": (
            "Eligibility, availability and application "
            "details can change after a dataset "
            "has been verified."
        ),
        "source_url": source_url,
        "editable": True
    })

    # --------------------------------------------------
    # 5. Return an unapproved pathway draft
    # --------------------------------------------------

    return {
        "opportunity_id": opportunity_id,
        "opportunity_title": opportunity["title"],
        "reference_date": reference_date.isoformat(),
        "status": "draft",
        "approved": False,
        "can_export": False,
        "steps": steps,
        "notice": (
            "This pathway contains informational suggestions "
            "only. It is not an official eligibility decision. "
            "The student must review and explicitly approve "
            "the pathway before it can be exported. "
            "Changes after approval require reapproval."
        )
    }
