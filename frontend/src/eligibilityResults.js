// Backend transport and presentation only; no profile inference or eligibility rules.
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

// Decode only the agreed FastAPI envelope. Evidence is checked against the
// published record, never used to replace it or to infer eligibility here.
export function decodeEligibilityResponse(payload, opportunity) {
  const envelopeFields = ['opportunity_id', 'results', 'notice'];
  const resultFields = ['condition_id', 'status', 'explanation', 'requirement', 'evidence_summary', 'source_url'];
  if (!isObject(payload) || Object.keys(payload).some((key) => !envelopeFields.includes(key)) ||
      payload.opportunity_id !== opportunity.id || !Array.isArray(payload.results) ||
      typeof payload.notice !== 'string' || !payload.notice.trim()) throw new Error('Invalid eligibility envelope.');
  const seen = new Set();
  return payload.results.map((result) => {
    if (!isObject(result) || Object.keys(result).some((key) => !resultFields.includes(key)) ||
        !backendStatuses.includes(result.status) || typeof result.explanation !== 'string') {
      throw new Error('Invalid eligibility result.');
    }
    const condition = opportunity.eligibility_conditions.find((item) => item.id === result.condition_id);
    if (!condition || seen.has(result.condition_id)) throw new Error('Invalid condition ID.');
    seen.add(result.condition_id);
    for (const [wire, published] of [['requirement', 'text'], ['evidence_summary', 'evidence_summary'], ['source_url', 'source_url']]) {
      if (Object.hasOwn(result, wire) && result[wire] !== condition[published]) throw new Error('Invalid evidence.');
    }
    return { opportunityId: opportunity.id, conditionId: condition.id, status: result.status, explanation: result.explanation };
  });
}

// One request per opportunity, with a fixed concurrency bound. No partial batch
// is published. Abort/timeout races also settle transports that ignore abort.
export async function evaluateOpportunities(profile, opportunities, { signal, fetchImpl = fetch } = {}) {
  const controller = new AbortController();
  const cancel = () => controller.abort();
  signal?.addEventListener('abort', cancel, { once: true });
  if (signal?.aborted) cancel();
  const safeProfile = Object.fromEntries(Object.entries(profile).filter(([key]) => key !== 'identity_answer'));
  const batches = new Array(opportunities.length);
  const notices = new Array(opportunities.length);
  let next = 0;
  try {
    const worker = async () => {
      while (next < opportunities.length) {
        if (controller.signal.aborted) throw new Error('cancelled');
        const index = next++;
        const opportunity = opportunities[index];
        const request = new AbortController();
        let timer, onAbort;
        const interrupted = new Promise((_, reject) => {
          onAbort = () => { request.abort(); reject(new Error('cancelled')); };
          controller.signal.addEventListener('abort', onAbort, { once: true });
          timer = setTimeout(() => { request.abort(); reject(new Error('timeout')); }, 3500);
        });
        try {
          const payload = await Promise.race([interrupted, (async () => {
            const response = await fetchImpl('http://127.0.0.1:8000/api/eligibility/evaluate', {
              method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: request.signal,
              body: JSON.stringify({ opportunity_id: opportunity.id, profile: safeProfile })
            });
            if (!response.ok) throw new Error('http');
            return response.json();
          })()]);
          const batch = adaptEligibilityResults(payload, [opportunity], (body) => decodeEligibilityResponse(body, opportunity));
          if (batch.state !== 'ready') throw new Error(batch.warning?.startsWith('Identity safeguard') ? 'identity' : 'invalid');
          batches[index] = [...batch.results].map(([conditionId, row]) => ({ ...row, conditionId, explanation: row.explanation ?? '' }));
          notices[index] = payload.notice;
        } finally {
          clearTimeout(timer);
          controller.signal.removeEventListener('abort', onAbort);
        }
      }
    };
    await Promise.all(Array.from({ length: Math.min(3, opportunities.length) }, worker));
    if (controller.signal.aborted) throw new Error('cancelled');
    const batch = adaptEligibilityResults(batches.flat(), opportunities, (rows) => rows);
    return { ...batch, notices: [...new Set(notices)] };
  } catch (error) {
    controller.abort();
    const messages = {
      cancelled: 'Eligibility evaluation was cancelled. Submit the current profile to try again.',
      timeout: 'Eligibility evaluation timed out. Please submit again to retry.',
      http: 'The eligibility service returned an unsuccessful response. Please try again.',
      invalid: 'Eligibility response rejected: invalid, unknown, duplicate or mismatched condition results.',
      identity: 'Identity safeguard violation: automatic identity decisions were rejected. Student confirmation or human review is required.'
    };
    return emptyEligibility('unavailable', messages[error.message] || 'Could not connect to the eligibility service or read its response. Please try again.');
  } finally {
    signal?.removeEventListener('abort', cancel);
  }
}

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
