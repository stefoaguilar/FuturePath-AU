
from datetime import date


def analyse_opportunity_deadline(
    opportunity: dict,
    reference_date: date
) -> dict:
    """
    Classify a recorded application deadline.

    This does not confirm whether applications are
    currently open or whether newer rounds exist.
    """

    deadline = opportunity["deadline"]
    verification = opportunity["verification"]

    deadline_status = deadline.get("status")
    recorded_date = deadline.get("date")
    verification_status = verification.get("status")

    classification = "unknown"
    explanation = (
        "Insufficient structured deadline information "
        "is available."
    )
    days_until_deadline = None

    # Parse only a complete ISO-format date.
    parsed_date = None
    invalid_date = False

    if recorded_date is not None:
        if not isinstance(recorded_date, str):
            invalid_date = True
        else:
            try:
                parsed_date = date.fromisoformat(
                    recorded_date
                )

                if parsed_date.isoformat() != recorded_date:
                    invalid_date = True

            except ValueError:
                invalid_date = True

    # Conflicting or unverified records require review.
    if verification_status != "verified":
        classification = "needs_review"
        explanation = (
            "The source record is conflicting, "
            "unverified or requires rechecking."
        )

    elif invalid_date:
        classification = "needs_review"
        explanation = (
            "The recorded deadline is not a valid "
            "YYYY-MM-DD date."
        )

    elif deadline_status == "closed":
        if (
            parsed_date is not None
            and parsed_date > reference_date
        ):
            classification = "needs_review"
            explanation = (
                "The record reports a closed round, "
                "but its closing date is in the future."
            )
        else:
            classification = "reported_closed"
            explanation = (
                "The source record reports this "
                "application round as closed."
            )

    elif deadline_status == "date":
        if parsed_date is None:
            classification = "needs_review"
            explanation = (
                "The record specifies a dated deadline "
                "but does not contain a valid date."
            )
        else:
            days_until_deadline = (
                parsed_date - reference_date
            ).days

            if days_until_deadline < 0:
                classification = "deadline_passed"
                explanation = (
                    "The recorded application deadline "
                    "has passed."
                )

            elif days_until_deadline == 0:
                classification = "deadline_today"
                explanation = (
                    "The recorded application deadline "
                    "is today. Check the source for "
                    "the exact closing time."
                )

            else:
                classification = "deadline_future"
                explanation = (
                    "The recorded application deadline "
                    "is in the future. This does not "
                    "confirm applications are open."
                )

    elif deadline_status == "unknown":
        if parsed_date is not None:
            classification = "needs_review"
            explanation = (
                "The deadline is marked unknown but "
                "also contains a recorded date."
            )

    else:
        classification = "needs_review"
        explanation = (
            "The record has an unsupported "
            "deadline status."
        )

    return {
        "opportunity_id": opportunity["id"],
        "classification": classification,
        "deadline_date": recorded_date,
        "days_until_deadline": days_until_deadline,
        "reference_date": reference_date.isoformat(),
        "explanation": explanation,
        "deadline_note": deadline.get("note", ""),
        "verification_status": verification_status,
        "verified_on": verification.get("verified_on"),
        "source_url": opportunity["source_url"],
        "notice": (
            "This result describes only the recorded "
            "application round and source information. "
            "It does not verify current application "
            "availability or rule out newer rounds. "
            "Always confirm dates with the provider."
        )
    }
