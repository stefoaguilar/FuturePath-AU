import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { DEMO_REFERENCE_DATE, OPPORTUNITY_CATEGORIES, readOpportunities, evaluateDeadline } from '../src/opportunityData.js';
import { harness } from './helpers/app-harness.mjs';

const dataset = JSON.parse(readFileSync(new URL('../../data/opportunities.json', import.meta.url), 'utf8'));
const records = dataset.opportunities;
const cards = (ui) => ui.nodes().filter((node) => node.type === 'article');
const ids = (ui) => cards(ui).map((node) => node.props['data-opportunity-id']);
const response = (data) => async () => ({ ok: true, json: async () => data });
async function refresh(ui) {
  await ui.button('Check API Status').props.onClick();
  ui.render();
}
function descendants(node) {
  if (Array.isArray(node)) return node.flatMap(descendants);
  return node?.props ? [node, ...descendants(node.props.children)] : [];
}

test('local fallback loads all 30 original records without renumbering or mutating them', () => {
  const original = JSON.stringify(dataset);
  assert.strictEqual(readOpportunities(dataset), records);
  const ui = harness();
  assert.equal(cards(ui).length, 30);
  assert.deepEqual(ids(ui), records.map((record) => record.id));
  assert.ok(ids(ui).includes('OPP-032'));
  assert.ok(!ids(ui).includes('OPP-018'));
  assert.match(ui.markup(), /Development fallback: data\/opportunities.json/);
  assert.ok(ui.markup().includes(dataset.dataset_note));
  assert.equal(JSON.stringify(dataset), original);
});

test('all published card fields, 81 nested conditions, evidence and sources render intact', () => {
  const ui = harness();
  for (const record of records) {
    const card = cards(ui).find((node) => node.props['data-opportunity-id'] === record.id);
    const content = ui.text(card);
    for (const text of [record.title, record.provider, record.location, record.summary,
      record.study_level.replaceAll('_', ' '), record.verification.verified_on,
      record.verification.status.replaceAll('_', ' '), record.verification.method, record.data_notes,
      ...(record.skills || [])].filter(Boolean)) assert.ok(content.includes(text), `${record.id}: ${text}`);
    const links = descendants(card).filter((node) => node.type === 'a');
    assert.ok(links.some((node) => node.props.href === record.source_url));
    for (const condition of record.eligibility_conditions) {
      const row = descendants(card).find((node) => node.props['data-condition-id'] === condition.id);
      assert.ok(row, condition.id);
      assert.equal(row.props['data-checkable-from-profile'], condition.checkable_from_profile);
      assert.ok(ui.text(row).includes(condition.text));
      assert.ok(ui.text(row).includes(condition.evidence_summary));
      assert.match(ui.text(row), /Not yet evaluated/);
      assert.ok(descendants(row).some((node) => node.type === 'a' && node.props.href === condition.source_url));
    }
    if (!record.skills?.length) assert.match(content, /No skills published/);
  }
  assert.equal(ui.nodes().filter((node) => node.props['data-condition-id']).length, 81);
  assert.match(ui.markup(), /Verification: conflicting/);
  assert.match(ui.markup(), /Verification: needs recheck/);
});

test('all nine documented categories have working filters, including categories absent locally', async () => {
  assert.deepEqual(OPPORTUNITY_CATEGORIES, [
    'scholarship', 'internship', 'cadetship', 'graduate_program', 'traineeship',
    'course', 'certification', 'mentoring', 'other'
  ]);
  const ui = harness();
  for (const category of OPPORTUNITY_CATEGORIES) {
    ui.button(category.replaceAll('_', ' ')).props.onClick(); ui.render();
    assert.deepEqual(ids(ui), records.filter((record) => record.category === category).map((record) => record.id));
  }
  // API fixtures reuse source records; no fixture is added to the actual dataset.
  const everyCategory = OPPORTUNITY_CATEGORIES.map((category, index) => ({ ...records[index], category }));
  const apiUi = harness({ fetchImpl: response({ opportunities: everyCategory }) });
  await refresh(apiUi);
  for (const [index, category] of OPPORTUNITY_CATEGORIES.entries()) {
    apiUi.button(category.replaceAll('_', ' ')).props.onClick(); apiUi.render();
    assert.deepEqual(ids(apiUi), [everyCategory[index].id]);
  }
});

test('search handles original IDs, skills, location and combined category filters', () => {
  const ui = harness();
  ui.change('searchQuery', ' opp-032 ');
  assert.deepEqual(ids(ui), ['OPP-032']);
  ui.button('internship').props.onClick(); ui.render();
  assert.deepEqual(ids(ui), []);
  ui.button('Clear All Filters').props.onClick(); ui.render();
  assert.equal(cards(ui).length, 30);
  ui.change('searchQuery', 'cybernetics');
  assert.ok(cards(ui).length > 0);
  assert.ok(ui.markup().includes('cybernetics'));
  ui.change('searchQuery', 'Queensland');
  assert.ok(cards(ui).length > 0);
  assert.ok(cards(ui).every((node) => /queensland/i.test(ui.text(node))));
});

test('all four deadline statuses use only the fixed demo reference date', () => {
  assert.equal(DEMO_REFERENCE_DATE, '2026-11-28');
  const today = evaluateDeadline({ status: 'date', date: '2026-11-28' });
  assert.equal(today.status, 'future');
  assert.match(today.displayDate, /Closes today/);
  const soon = evaluateDeadline({ status: 'date', date: '2026-11-30' });
  assert.equal(soon.label, 'Closing soon');
  assert.match(soon.displayDate, /2 days left/);
  const past = evaluateDeadline({ status: 'date', date: '2026-11-27' });
  assert.equal(past.status, 'past');
  assert.equal(past.badgeClass, 'badge-deadline-past');
  assert.equal(evaluateDeadline({ status: 'date', date: '2027-02-26' }).status, 'future');
  const closed = evaluateDeadline({ status: 'closed', date: '2026-03-30' });
  assert.equal(closed.badgeClass, 'badge-deadline-closed');
  assert.match(closed.displayDate, /Previous closing date: 30 Mar 2026/);
  assert.match(evaluateDeadline({ status: 'closed', date: null }).displayDate, /not published/);
  assert.equal(evaluateDeadline({ status: 'rolling', date: null }).label, 'Open all year');
  const unknown = evaluateDeadline({ status: 'unknown', date: null });
  assert.equal(unknown.label, 'Deadline unknown');
  assert.equal(unknown.badgeClass, 'badge-deadline-unknown');
});

test('API envelope, legacy array and valid empty responses are accepted', async () => {
  for (const payload of [dataset, records, { opportunities: records.slice(0, 2), dataset_note: 'API fixture' },
    { opportunities: [] }, []]) {
    let requestedUrl;
    const ui = harness({ fetchImpl: async (url) => {
      requestedUrl = url;
      return { ok: true, json: async () => payload };
    } });
    await refresh(ui);
    assert.equal(requestedUrl, 'http://127.0.0.1:8000/api/opportunities');
    assert.deepEqual(ids(ui), readOpportunities(payload).map((record) => record.id));
    assert.match(ui.markup(), /Source: FastAPI opportunity API/);
    assert.doesNotMatch(ui.markup(), /Development fallback: data\/opportunities.json/);
    if (!Array.isArray(payload) && payload.dataset_note) assert.ok(ui.markup().includes(payload.dataset_note));
  }
});

test('invalid responses, HTTP failures, invalid JSON and network errors use labelled local fallback', async () => {
  const invalid = [null, {}, { opportunities: {} }, { opportunities: [null] },
    { opportunities: [records[0], records[0]] }, { opportunities: [{ ...records[0], deadline: 'rolling' }] },
    { opportunities: [{ ...records[0], eligibility_conditions: [{}] }] },
    { opportunities: [{ ...records[0], source_url: 'javascript:alert(1)' }] }];
  const failures = [
    async () => { throw new Error('Network offline'); },
    async () => ({ ok: false, status: 404, statusText: 'Not Found' }),
    async () => ({ ok: true, json: async () => { throw new Error('Invalid JSON'); } }),
    ...invalid.map(response)
  ];
  for (const fetchImpl of failures) {
    const ui = harness({ fetchImpl });
    await refresh(ui);
    assert.deepEqual(ids(ui), records.map((record) => record.id));
    assert.match(ui.markup(), /Development fallback: data\/opportunities.json/);
    assert.match(ui.markup(), /Opportunity API unavailable or returned invalid data/);
  }
});

test('schema validation checks nested types, dates, optional fields and identity safeguards', () => {
  const mutate = (callback) => {
    const record = structuredClone(records[0]);
    callback(record);
    return [record];
  };
  for (const invalid of [
    mutate((r) => { r.skills = 'ICT'; }),
    mutate((r) => { r.category = 'mentorship'; }),
    mutate((r) => { r.deadline = { status: 'date', date: '2026-02-30' }; }),
    mutate((r) => { r.deadline = { status: 'rolling', date: '2026-12-01' }; }),
    mutate((r) => { r.deadline = { status: 'closed', date: '2027-01-01', note: 'Closed' }; }),
    mutate((r) => { r.verification = null; }),
    mutate((r) => { r.eligibility_conditions[0].checkable_from_profile = 'true'; }),
    mutate((r) => { Object.assign(r.eligibility_conditions[0], { type: 'identity_requirement', checkable_from_profile: true }); })
  ]) assert.throws(() => readOpportunities(invalid), /Invalid opportunity/);
  const optional = mutate((r) => { delete r.skills; delete r.data_notes; });
  assert.strictEqual(readOpportunities(optional), optional);
  assert.throws(() => readOpportunities({ schema_version: 'unsupported', opportunities: [] }), /schema_version/);
});

test('synthetic API fixtures are clearly labelled and never described as verified real records', async () => {
  const synthetic = { ...records[0], record_type: 'synthetic', title: '[SYNTHETIC] UI test fixture',
    verification: { ...records[0].verification, status: 'synthetic' } };
  const ui = harness({ fetchImpl: response({ opportunities: [synthetic] }) });
  await refresh(ui);
  const content = ui.text(cards(ui)[0]);
  assert.match(content, /SYNTHETIC - demonstration only/);
  assert.match(content, /Verification: synthetic/);
  assert.doesNotMatch(content, /Real record|Verification: verified/);
  assert.throws(() => readOpportunities([{ ...synthetic, title: 'Unlabelled fixture' }]), /synthetic/);
});

test('closed, unknown, future and rolling pathways retain editing/approval without fabricated dates', async () => {
  const fixtures = [
    { record: records.find((r) => r.deadline.status === 'closed'), expected: /Watch for the Next Round/, timeline: /Next-round dates: check official source/ },
    { record: records.find((r) => r.deadline.status === 'unknown'), expected: /Check Application Dates/, timeline: /Application dates to be confirmed/ },
    { record: records.find((r) => r.deadline.status === 'date' && r.deadline.date >= DEMO_REFERENCE_DATE), expected: /Check Application Availability/, timeline: /Published closing date/ },
    { record: records.find((r) => r.deadline.status === 'date' && r.deadline.date < DEMO_REFERENCE_DATE), expected: /Watch for the Next Round/, timeline: /Next-round dates: check official source/ },
    { record: { ...records[0], deadline: { status: 'rolling', date: null } }, expected: /Check Application Availability/, timeline: /Open all year/ }
  ];
  for (const { record, expected, timeline } of fixtures) {
    const ui = harness({ fetchImpl: response({ opportunities: [record] }) });
    await refresh(ui);
    ui.button('Plan Pathway').props.onClick(); ui.render();
    assert.match(ui.markup(), expected);
    assert.match(ui.markup(), timeline);
    assert.doesNotMatch(ui.markup(), /\[object Object\]/);
    const statuses = ui.nodes().filter((node) => node.props.className?.startsWith('status-tag'));
    assert.ok(statuses.every((node) => ui.text(node) === 'Not yet evaluated'));
    ui.button('Approve Pathway').props.onClick(); ui.render();
    assert.match(ui.markup(), /Plan Locked & Approved by Student/);
    ui.button('Unlock & Revise Plan').props.onClick(); ui.render();
    assert.match(ui.markup(), /Draft Plan/);
  }
});

test('dataset pathways retain reordering, custom steps, deletion and approval locking', () => {
  const ui = harness();
  ui.button('Plan Pathway').props.onClick(); ui.render();
  const titles = () => ui.nodes().filter((node) => node.props.className === 'milestone-title').map(ui.text);
  const original = titles();
  ui.find((node) => node.props['aria-label'] === 'Move step 1 down').props.onClick(); ui.render();
  assert.deepEqual(titles().slice(0, 2), [original[1], original[0]]);
  ui.find((node) => node.props['aria-label'] === 'Move step 2 up').props.onClick(); ui.render();
  assert.deepEqual(titles(), original);
  ui.button('Add Custom Milestone Step').props.onClick(); ui.render();
  ui.change('new-step-title', 'My portfolio review');
  ui.find((node) => node.type === 'form' && node.props.className === 'add-step-card')
    .props.onSubmit({ preventDefault() {} });
  ui.render();
  assert.equal(titles().at(-1), 'My portfolio review');
  ui.find((node) => node.props['aria-label'] === 'Delete step 5').props.onClick(); ui.render();
  assert.deepEqual(titles(), original);
  ui.button('Approve Pathway').props.onClick(); ui.render();
  assert.ok(!ui.nodes().some((node) => node.props['aria-label'] === 'Edit step 1'));
  ui.button('Unlock & Revise Plan').props.onClick(); ui.render();
  assert.ok(ui.nodes().some((node) => node.props['aria-label'] === 'Edit step 1'));
});
