
const PATHWAY_API_URL = 'http://127.0.0.1:8000/api/pathways/generate';

const isObject = (value) =>
  value !== null && typeof value === 'object' && !Array.isArray(value);

const isText = (value) =>
  typeof value === 'string' && value.trim() !== '';

const CATEGORIES = new Set([
  'human_review',
  'requirement_review',
  'skill_exploration',
  'deadline_review',
  'source_verification'
]);

export async function requestDraftPathway(
  opportunity,
  profile,
  { signal, fetchImpl = fetch } = {}
) {
  // Never submit voluntary identity answers for automatic assessment.
  const safeProfile = Object.fromEntries(
    Object.entries(profile).filter(
      ([key]) => key !== 'identity_answer'
    )
  );

  const response = await fetchImpl(PATHWAY_API_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal,
    body: JSON.stringify({
      opportunity_id: opportunity.id,
      profile: safeProfile
    })
  });

  if (!response.ok) {
    throw new Error('Pathway service unavailable.');
  }

  const data = await response.json();

  if (
    !isObject(data) ||
    data.opportunity_id !== opportunity.id ||
    data.opportunity_title !== opportunity.title ||
    data.status !== 'draft' ||
    data.approved !== false ||
    data.can_export !== false ||
    !/^\d{4}-\d{2}-\d{2}$/.test(data.reference_date ?? '') ||
    !isText(data.notice) ||
    !Array.isArray(data.steps) ||
    data.steps.length < 2
  ) {
    throw new Error('Invalid pathway response.');
  }

  const conditions = new Map(
    opportunity.eligibility_conditions.map(
      (item) => [item.id, item]
    )
  );

  const approvedSources = new Set([
    opportunity.source_url,
    ...opportunity.eligibility_conditions.map(
      (item) => item.source_url
    )
  ]);

  const seenIds = new Set();

  for (const step of data.steps) {
    if (
      !isObject(step) ||
      !isText(step.step_id) ||
      seenIds.has(step.step_id) ||
      !CATEGORIES.has(step.category) ||
      !isText(step.title) ||
      !isText(step.description) ||
      !isText(step.explanation) ||
      !approvedSources.has(step.source_url) ||
      step.editable !== true
    ) {
      throw new Error('Invalid pathway step.');
    }

    seenIds.add(step.step_id);

    if (step.step_id.startsWith('requirement:')) {
      const condition = conditions.get(
        step.step_id.slice('requirement:'.length)
      );

      if (
        !condition ||
        step.description !== condition.text ||
        step.source_url !== (
          condition.source_url || opportunity.source_url
        ) ||
        !['unmet', 'uncertain'].includes(step.eligibility_status) ||
        (
          condition.type === 'identity_requirement' &&
          (
            step.eligibility_status !== 'uncertain' ||
            step.category !== 'human_review'
          )
        ) ||
        (
          step.eligibility_status === 'unmet' &&
          step.category !== 'requirement_review'
        ) ||
        (
          step.eligibility_status === 'uncertain' &&
          step.category !== 'human_review'
        )
      ) {
        throw new Error('Invalid requirement step.');
      }
    } else if (step.category === 'skill_exploration') {
      if (
        !/^skill:[1-9]\d*$/.test(step.step_id) ||
        step.eligibility_status !== null ||
        !step.title.startsWith('Explore ') ||
        !(opportunity.skills || []).includes(
          step.title.slice('Explore '.length)
        ) ||
        step.source_url !== opportunity.source_url
      ) {
        throw new Error('Invalid skill step.');
      }
    } else if (step.step_id === 'deadline:review') {
      if (
        step.category !== 'deadline_review' ||
        ![
          'deadline_passed',
          'reported_closed',
          'deadline_future',
          'deadline_today',
          'needs_review',
          'unknown'
        ].includes(step.deadline_classification) ||
        step.source_url !== opportunity.source_url
      ) {
        throw new Error('Invalid deadline step.');
      }
    } else if (step.step_id === 'source:verify') {
      if (
        step.category !== 'source_verification' ||
        step.source_url !== opportunity.source_url
      ) {
        throw new Error('Invalid source-verification step.');
      }
    } else {
      throw new Error('Unrecognized pathway step.');
    }
  }

  if (
    !seenIds.has('deadline:review') ||
    !seenIds.has('source:verify')
  ) {
    throw new Error('Incomplete pathway response.');
  }

  return data;
}
