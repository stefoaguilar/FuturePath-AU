
const GAP_API_URL = 'http://127.0.0.1:8000/api/gaps/analyse';

const isObject = (value) =>
  value !== null && typeof value === 'object' && !Array.isArray(value);

export async function requestGapAnalysis(
  opportunity,
  profile,
  { signal, fetchImpl = fetch } = {}
) {
  // Never send voluntary identity answers for automated analysis.
  const safeProfile = Object.fromEntries(
    Object.entries(profile).filter(([key]) => key !== 'identity_answer')
  );

  const response = await fetchImpl(GAP_API_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal,
    body: JSON.stringify({
      opportunity_id: opportunity.id,
      profile: safeProfile
    })
  });

  if (!response.ok) {
    throw new Error('Gap-analysis service unavailable.');
  }

  const data = await response.json();

  if (
    !isObject(data) ||
    data.opportunity_id !== opportunity.id ||
    data.source_url !== opportunity.source_url ||
    typeof data.notice !== 'string' ||
    !data.notice.trim() ||
    !Array.isArray(data.confirmed_unmet_requirements) ||
    !Array.isArray(data.requirements_needing_review) ||
    !Array.isArray(data.skills_to_explore)
  ) {
    throw new Error('Invalid gap-analysis response.');
  }

  const publishedConditions = new Map(
    opportunity.eligibility_conditions.map((condition) => [
      condition.id, condition
    ])
  );

  const seen = new Set();

  const validateResults = (results, expectedStatus) => {
    for (const result of results) {
      const condition = publishedConditions.get(result?.condition_id);

      if (
        !condition ||
        seen.has(result.condition_id) ||
        result.status !== expectedStatus ||
        (condition.type === 'identity_requirement' &&
          result.status !== 'uncertain') ||
        result.requirement !== condition.text ||
        result.evidence_summary !== condition.evidence_summary ||
        result.source_url !== condition.source_url ||
        typeof result.explanation !== 'string' ||
        Object.keys(result).some((key) =>
          ![
            'condition_id', 'status', 'explanation',
            'requirement', 'evidence_summary', 'source_url'
          ].includes(key)
        )
      ) {
        throw new Error('Invalid gap-analysis condition.');
      }

      seen.add(result.condition_id);
    }
  };

  validateResults(data.confirmed_unmet_requirements, 'unmet');
  validateResults(data.requirements_needing_review, 'uncertain');

  const publishedSkills = new Set(opportunity.skills);

  if (
    data.skills_to_explore.some(
      (skill) => typeof skill !== 'string' ||
        !publishedSkills.has(skill)
    )
  ) {
    throw new Error('Invalid advisory skills.');
  }

  return data;
}
