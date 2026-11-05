// Presentation only. No endpoint, transport, profile inference or eligibility rules.
// Stefano's wire contract is not defined yet: an explicit decoder must convert it
// to this INTERNAL list: { opportunityId, conditionId, status, explanation? }[].
export const ELIGIBILITY_STATES = Object.freeze({
  satisfied: { label: 'Satisfied', badgeClass: 'badge-satisfied' },
  unmet: { label: 'Unmet', badgeClass: 'badge-unmet' },
  uncertain: { label: 'Uncertain', badgeClass: 'badge-uncertain' },
  not_yet_evaluated: { label: 'Not yet evaluated', badgeClass: 'badge-neutral' }
});

const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const fields = ['opportunityId', 'conditionId', 'status', 'explanation'];
const backendStatuses = ['satisfied', 'unmet', 'uncertain'];
const identityReview = 'Student confirmation or human review is required. Identity is never automatically evaluated or scored.';

export function emptyEligibility(state = 'unavailable', warning = null) {
  return { state, warning, results: new Map() };
}

export function adaptEligibilityResults(payload, opportunities, decodeResponse) {
  if (payload == null) return emptyEligibility();
  if (typeof decodeResponse !== 'function') {
    return emptyEligibility('invalid', 'Eligibility response rejected: the backend response decoder has not been configured.');
  }
  const conditions = new Map(opportunities.map((opportunity) => [opportunity.id,
    new Map(opportunity.eligibility_conditions.map((condition) => [condition.id, condition]))]));
  try {
    const rows = decodeResponse(payload);
    if (!Array.isArray(rows)) throw new Error('Expected a list of condition results.');
    const results = new Map();
    for (const row of rows) {
      if (!isObject(row) || typeof row.opportunityId !== 'string' || typeof row.conditionId !== 'string') {
        throw new Error('Every result needs opportunity and condition IDs.');
      }
      const condition = conditions.get(row.opportunityId)?.get(row.conditionId);
      if (!condition) throw new Error('A result does not match a published opportunity and condition ID.');
      const extraFields = Object.keys(row).filter((field) => !fields.includes(field));
      if (condition.type === 'identity_requirement' &&
          (row.status === 'satisfied' || row.status === 'unmet' || extraFields.length > 0)) {
        return emptyEligibility('invalid', 'Identity safeguard violation: the response attempts an automatic identity decision or includes unsupported scoring data. All eligibility results in this response were rejected; student confirmation or human review is required.');
      }
      if (!backendStatuses.includes(row.status) || extraFields.length > 0 ||
          (row.explanation !== undefined && typeof row.explanation !== 'string')) {
        throw new Error('A result has an unsupported status, explanation or field.');
      }
      if (results.has(row.conditionId)) throw new Error('Duplicate condition results cannot be accepted.');
      // Copy only validated fields. Never mutate the source dataset or response.
      results.set(row.conditionId, {
        opportunityId: row.opportunityId, status: row.status,
        explanation: row.explanation?.trim() || null
      });
    }
    return { state: 'ready', warning: null, results };
  } catch {
    // Atomic rejection: partial/malformed batches must not produce positive or
    // negative decisions. Do not expose raw errors or payloads in the UI/logs.
    return emptyEligibility('invalid', 'Eligibility response rejected: invalid, unknown, duplicate or mismatched condition results. Published opportunity information remains available.');
  }
}

export function presentCondition(batch, opportunityId, condition) {
  const result = batch.results.get(condition.id);
  const valid = result?.opportunityId === opportunityId && backendStatuses.includes(result.status) &&
    (condition.type !== 'identity_requirement' || result.status === 'uncertain');
  const status = valid ? result.status : 'not_yet_evaluated';
  return {
    status, ...ELIGIBILITY_STATES[status],
    reason: condition.type === 'identity_requirement' ? identityReview
      : valid ? 'Condition result supplied by the backend; this is not an overall eligibility decision.'
        : 'No validated backend result is available for this condition. This does not mean satisfied, unmet or uncertain.',
    backendExplanation: valid ? result.explanation : null
  };
}

export function summarizeConditions(conditions) {
  const counts = { satisfied: 0, unmet: 0, uncertain: 0, not_yet_evaluated: 0 };
  for (const condition of conditions) counts[condition.evaluation.status] += 1;
  return counts;
}

// Freshness check only: equality of the local request snapshot, not a comparison
// against opportunity criteria. Missing/not_stated values carry no decision here.
export function matchesProfileSnapshot(snapshot, profile) {
  if (!isObject(snapshot) || Object.keys(snapshot).length !== Object.keys(profile).length) return false;
  return Object.entries(profile).every(([field, value]) => Array.isArray(value)
    ? Array.isArray(snapshot[field]) && value.length === snapshot[field].length &&
      value.every((item, index) => item === snapshot[field][index])
    : Object.hasOwn(snapshot, field) && value === snapshot[field]);
}
