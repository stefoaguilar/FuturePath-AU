
const PHASES = {
  human_review: 'Milestone 1: Requirement Verification',
  requirement_review: 'Milestone 1: Requirement Verification',
  skill_exploration: 'Milestone 2: Optional Skill Development',
  deadline_review: 'Milestone 3: Application Date Review',
  source_verification: 'Milestone 3: Official Source Verification'
};

export function toEditableMilestones(opportunity, draft, planVersion) {
  if (
    draft.opportunity_id !== opportunity.id ||
    draft.status !== 'draft' ||
    draft.approved !== false ||
    draft.can_export !== false ||
    !Array.isArray(draft.steps)
  ) {
    throw new Error('Cannot convert an invalid pathway draft.');
  }

  const conditions = new Map(
    opportunity.eligibility_conditions.map((condition) => [
      condition.id,
      condition
    ])
  );

  return draft.steps.map((step, index) => {
    const conditionId = step.step_id.startsWith('requirement:')
      ? step.step_id.slice('requirement:'.length)
      : null;

    const publishedCondition = conditionId
      ? conditions.get(conditionId)
      : null;

    const descriptionParts = [
      step.description,
      step.explanation
    ];

    if (step.category === 'deadline_review' && step.deadline_note) {
      descriptionParts.push(`Published deadline note: ${step.deadline_note}`);
    }

    return {
      id: `backend-${planVersion}-${index + 1}`,
      phase: PHASES[step.category],
      title: step.title,
      description: descriptionParts.join('\n\n'),
      timeline: step.category === 'deadline_review'
        ? 'Verify dates with provider'
        : 'Student-selected timing',
      status: 'pending',

      // Store official evidence separately from editable guidance.
      sourceUrl: step.source_url,
      sourceStepId: step.step_id,
      sourceCategory: step.category,
      eligibilityStatus: step.eligibility_status ?? null,

      sourceConditions: publishedCondition
        ? [{ ...publishedCondition }]
        : undefined,

      // Do not incorrectly label advisory steps as application submissions.
      actionableUrl: ''
    };
  });
}
