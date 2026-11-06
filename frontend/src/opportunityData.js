// Shared presentation/validation rules for data/SCHEMA.md. No eligibility logic.
// Read calendar components locally; ISO timestamps would shift dates near midnight.
export function localCalendarDate(date = new Date()) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}
export const OPPORTUNITY_CATEGORIES = [
  'scholarship', 'internship', 'cadetship', 'graduate_program', 'traineeship',
  'course', 'certification', 'mentoring', 'other'
];
const STUDY_LEVELS = ['undergraduate', 'postgraduate', 'vocational', 'school_leaver', 'graduate', 'any', 'unknown'];
const CONDITION_TYPES = ['education', 'enrolment', 'field_of_study', 'citizenship_residency', 'identity_requirement', 'skill', 'experience', 'age', 'location', 'other', 'unknown'];
const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const isText = (value) => typeof value === 'string' && value.trim().length > 0;
const isStringList = (value) => Array.isArray(value) && value.every(isText);
const isSourceUrl = (value) => {
  if (!isText(value)) return false;
  try { return ['https:', 'http:'].includes(new URL(value).protocol); }
  catch { return false; }
};
const isDate = (value) => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) &&
  Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value;

// Accept the documented { opportunities, schema_version?, dataset_note? } envelope
// and a legacy raw array. Keep original IDs, fields and nested objects unchanged.
// Reject the whole response rather than silently hiding malformed records.
export function readOpportunities(payload) {
  const envelope = isObject(payload);
  const records = Array.isArray(payload) ? payload : envelope ? payload.opportunities : null;
  if (!Array.isArray(records)) throw new Error('Expected an opportunities array or an object containing opportunities.');
  if (envelope && payload.schema_version !== undefined && payload.schema_version !== '0.1-draft') {
    throw new Error('Unsupported opportunity schema_version. Expected 0.1-draft.');
  }
  if (envelope && payload.dataset_note !== undefined && typeof payload.dataset_note !== 'string') {
    throw new Error('dataset_note must be text.');
  }
  const ids = new Set();
  const conditionIds = new Set();
  for (const record of records) {
    const fail = (field) => { throw new Error(`Invalid opportunity ${record?.id ?? '(missing ID)'}: ${field}.`); };
    if (!isObject(record)) fail('record must be an object');
    if (!isText(record.id) || !/^OPP-\d+$/.test(record.id) || ids.has(record.id)) fail('id must be a unique OPP identifier');
    ids.add(record.id);
    for (const field of ['title', 'provider', 'location', 'summary']) {
      if (!isText(record[field])) fail(`${field} must be text`);
    }
    if (!['real', 'synthetic'].includes(record.record_type)) fail('record_type');
    if (!OPPORTUNITY_CATEGORIES.includes(record.category)) fail('category');
    if (!STUDY_LEVELS.includes(record.study_level)) fail('study_level');
    if (!isSourceUrl(record.source_url)) fail('source_url must be an HTTP(S) URL');
    if (record.skills !== undefined && !isStringList(record.skills)) fail('skills must be a list of text');
    if (record.data_notes !== undefined && typeof record.data_notes !== 'string') fail('data_notes must be text');
    if (!Array.isArray(record.eligibility_conditions) || !record.eligibility_conditions.length) fail('eligibility_conditions must be a nonempty list');
    for (const condition of record.eligibility_conditions) {
      if (!isObject(condition) || !isText(condition.id) || !condition.id.startsWith(`${record.id}-E`) || conditionIds.has(condition.id)) fail('condition id');
      conditionIds.add(condition.id);
      if (!CONDITION_TYPES.includes(condition.type) || !isText(condition.text) ||
          !isText(condition.evidence_summary) || !isSourceUrl(condition.source_url) ||
          typeof condition.checkable_from_profile !== 'boolean') fail(`condition ${condition.id}`);
      if (condition.type === 'identity_requirement' && condition.checkable_from_profile) fail('identity conditions cannot be checked from profile');
    }
    const deadline = record.deadline;
    if (!isObject(deadline) || !['date', 'rolling', 'closed', 'unknown'].includes(deadline.status)) fail('deadline status');
    if (deadline.note !== undefined && typeof deadline.note !== 'string') fail('deadline note must be text');
    if (deadline.status === 'date' && !isDate(deadline.date)) fail('deadline date');
    if (['rolling', 'unknown'].includes(deadline.status) && deadline.date !== null) fail('rolling/unknown deadline date must be null');
    if (deadline.status === 'closed' && (!isText(deadline.note) ||
        (deadline.date != null && !isDate(deadline.date)))) fail('closed deadline needs a note and an optional previous date');
    const verification = record.verification;
    if (!isObject(verification) || !isDate(verification.verified_on) || !isText(verification.method) ||
        !['verified', 'needs_recheck', 'conflicting', 'synthetic'].includes(verification.status)) fail('verification');
    // A published previous closing date cannot be later than its verification.
    // Validate against recorded evidence, so acceptance never depends on the clock.
    if (deadline.status === 'closed' && deadline.date != null && deadline.date > verification.verified_on) {
      fail('closed deadline cannot be after its verification date');
    }
    if (record.record_type === 'synthetic' &&
        (!record.title.toLowerCase().includes('synthetic') || verification.status !== 'synthetic')) fail('synthetic record must be labelled in title and verification');
    if (record.record_type === 'real' && verification.status === 'synthetic') fail('real record cannot have synthetic verification');
  }
  return records;
}

export function formatDate(value) {
  return new Date(`${value}T00:00:00Z`).toLocaleDateString('en-AU', {
    day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'
  });
}

// Deadline presentation only, never confirmation of application availability or
// student eligibility. Compare date-only values in UTC to avoid DST-length days,
// after selecting today's date locally. Tests can supply an explicit YYYY-MM-DD.
export function evaluateDeadline(deadline, referenceDate = localCalendarDate()) {
  if (!isDate(referenceDate)) throw new Error('Expected a valid reference date (YYYY-MM-DD).');
  if (deadline.status === 'rolling') return {
    status: 'rolling', label: 'Rolling applications – no fixed closing date', displayDate: 'Rolling applications – no fixed closing date',
    badgeClass: 'badge-rolling'
  };
  if (deadline.status === 'unknown') return {
    status: 'unknown', label: 'Deadline unknown', displayDate: 'Deadline unknown',
    badgeClass: 'badge-deadline-unknown'
  };
  if (deadline.status === 'closed') return {
    status: 'past', label: 'Closed round',
    displayDate: deadline.date ? `Previous closing date: ${formatDate(deadline.date)}` : 'Closed round; previous closing date not published',
    badgeClass: 'badge-deadline-closed'
  };
  const days = Math.round((Date.parse(deadline.date) - Date.parse(referenceDate)) / 86400000);
  if (days < 0) return {
    status: 'past', label: 'Past deadline', displayDate: `Closing date elapsed: ${formatDate(deadline.date)}`,
    badgeClass: 'badge-deadline-past'
  };
  return {
    status: 'future', label: days <= 7 ? 'Closing soon' : 'Future deadline',
    displayDate: `${formatDate(deadline.date)} (${days === 0 ? 'Closes today' : `${days} day${days === 1 ? '' : 's'} left`})`,
    badgeClass: 'badge-upcoming'
  };
}

export const displayValue = (value) => value.replaceAll('_', ' ');
