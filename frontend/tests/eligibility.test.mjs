import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { adaptEligibilityResults, emptyEligibility, matchesProfileSnapshot, presentCondition, summarizeConditions } from '../src/eligibilityResults.js';
import { harness, renderInitialApp } from './helpers/app-harness.mjs';

const records = JSON.parse(readFileSync(new URL('../../data/opportunities.json', import.meta.url), 'utf8')).opportunities;
const opportunity = records.find((r) => r.eligibility_conditions.filter((c) => c.type !== 'identity_requirement').length >= 3);
const ordinary = opportunity.eligibility_conditions.filter((c) => c.type !== 'identity_requirement');
const identityOpportunity = records.find((r) => r.eligibility_conditions.some((c) => c.type === 'identity_requirement'));
const identity = identityOpportunity.eligibility_conditions.find((c) => c.type === 'identity_requirement');

// Presentation fixtures only. This envelope is intentionally test-local and is
// NOT an agreed backend contract. No running app imports fixtures or this decoder.
const decodeFixture = (payload) => payload.fixtureResults;
const row = (status, condition = ordinary[0], owner = opportunity) => ({
  opportunityId: owner.id, conditionId: condition.id, status,
  explanation: `Test backend explanation: ${status}`
});
const adapt = (rows) => adaptEligibilityResults({ fixtureResults: rows }, records, decodeFixture);
const conditionNode = (ui, condition = ordinary[0]) => ui.find((node) => node.props['data-condition-id'] === condition.id);
function supply(ui, rows) {
  const eligibilityInput = {
    payload: { fixtureResults: rows }, decodeResponse: decodeFixture,
    profileSnapshot: ui.profile()
  };
  ui.setProps({ eligibilityInput });
  return eligibilityInput;
}
function cardNode(ui, owner = opportunity) {
  return ui.find((node) => node.props['data-opportunity-id'] === owner.id);
}

for (const status of ['satisfied', 'unmet', 'uncertain']) {
  test(`validated ${status} result maps to its label, styling and backend explanation`, () => {
    const result = adapt([row(status)]);
    const display = presentCondition(result, opportunity.id, ordinary[0]);
    assert.equal(result.state, 'ready');
    assert.equal(display.status, status);
    assert.equal(display.badgeClass, `badge-${status}`);
    assert.equal(display.backendExplanation, `Test backend explanation: ${status}`);
    const ui = harness();
    supply(ui, [row(status)]);
    const condition = conditionNode(ui);
    assert.equal(condition.props['data-eligibility-status'], status);
    assert.ok(ui.text(condition).includes(ordinary[0].text));
    assert.ok(ui.text(condition).includes(ordinary[0].evidence_summary));
    assert.match(ui.text(condition), /Backend explanation: Test backend explanation/);
    assert.match(ui.text(cardNode(ui)), /1 of \d+ conditions have validated backend results/);
  });
}

test('missing results stay neutral and distinct from explicit backend uncertainty', () => {
  for (const result of [emptyEligibility(), adapt([]), adaptEligibilityResults(null, records, decodeFixture)]) {
    const display = presentCondition(result, opportunity.id, ordinary[0]);
    assert.equal(display.status, 'not_yet_evaluated');
    assert.equal(display.badgeClass, 'badge-neutral');
    assert.equal(display.backendExplanation, null);
  }
  const ui = harness();
  const text = ui.text(cardNode(ui));
  assert.match(text, /No validated backend results for this opportunity/);
  assert.doesNotMatch(text, /0 Satisfied|0 Unmet|0 Uncertain/);
  assert.match(ui.markup(), /Eligibility evaluation is unavailable/);
  assert.match(ui.markup(), /Uncertain is an explicit backend outcome/);
  const conditions = ui.nodes().filter((node) => node.props['data-condition-id']);
  assert.equal(conditions.length, 81);
  assert.ok(conditions.every((node) => node.props['data-eligibility-status'] === 'not_yet_evaluated'));
});

test('summary counts reflect validated results only, including partial evaluation', () => {
  const batch = adapt([row('satisfied', ordinary[0]), row('unmet', ordinary[1]), row('uncertain', ordinary[2])]);
  const conditions = opportunity.eligibility_conditions.map((condition) => ({
    ...condition, evaluation: presentCondition(batch, opportunity.id, condition)
  }));
  assert.deepEqual(summarizeConditions(conditions), {
    satisfied: 1, unmet: 1, uncertain: 1,
    not_yet_evaluated: opportunity.eligibility_conditions.length - 3
  });
  const ui = harness();
  supply(ui, [row('satisfied', ordinary[0]), row('unmet', ordinary[1]), row('uncertain', ordinary[2])]);
  const text = ui.text(cardNode(ui));
  assert.match(text, /1 Satisfied/);
  assert.match(text, /1 Unmet/);
  assert.match(text, /1 Uncertain/);
  assert.match(text, /not an overall eligibility decision/);
});

test('unknown statuses, malformed responses, decoder errors and duplicate results reject the whole batch', () => {
  const valid = row('satisfied');
  for (const invalid of [null, {}, 'satisfied', true, [null], [false],
    [{ ...valid, status: 'eligible' }], [{ ...valid, status: 'not_yet_evaluated' }],
    [{ ...valid, explanation: { text: 'Not text' } }], [{ ...valid, explanation: 42 }],
    [{ ...valid, score: 100 }], [valid, valid], [valid, { ...row('unmet', ordinary[1]), status: 'unknown' }]]) {
    const batch = adapt(invalid);
    assert.equal(batch.state, 'invalid');
    assert.equal(batch.results.size, 0);
    assert.ok(batch.warning);
    assert.equal(presentCondition(batch, opportunity.id, ordinary[0]).status, 'not_yet_evaluated');
  }
  const noDecoder = adaptEligibilityResults({ fixtureResults: [valid] }, records);
  assert.equal(noDecoder.state, 'invalid');
  assert.match(noDecoder.warning, /decoder has not been configured/);
  const thrown = adaptEligibilityResults({}, records, () => { throw new Error('Private response data'); });
  assert.equal(thrown.results.size, 0);
  assert.ok(!thrown.warning.includes('Private response data'));
  const ui = harness();
  supply(ui, [valid]);
  supply(ui, [{ ...valid, status: 'unknown' }]);
  assert.equal(conditionNode(ui).props['data-eligibility-status'], 'not_yet_evaluated');
  assert.match(ui.markup(), /Eligibility response rejected/);
  assert.equal(ui.nodes().filter((node) => node.type === 'article').length, 30);
});

test('opportunity and condition IDs must match the same published pair', () => {
  for (const invalid of [
    { ...row('satisfied'), opportunityId: 'OPP-NOT-FOUND' },
    { ...row('satisfied'), conditionId: `${opportunity.id}-E999` },
    { ...row('satisfied'), opportunityId: records.find((r) => r.id !== opportunity.id).id },
    { ...row('satisfied'), conditionId: 1 },
    { ...row('satisfied'), opportunityId: null }
  ]) {
    const batch = adapt([invalid]);
    assert.equal(batch.state, 'invalid');
    assert.equal(batch.results.size, 0);
  }
});

test('identity decisions and scores are rejected with a safeguard warning', () => {
  for (const invalid of [row('satisfied', identity, identityOpportunity), row('unmet', identity, identityOpportunity),
    { ...row('uncertain', identity, identityOpportunity), score: 0.9 }]) {
    const batch = adapt([row('satisfied'), invalid]);
    assert.equal(batch.results.size, 0);
    assert.match(batch.warning, /Identity safeguard violation/);
    const ui = harness();
    supply(ui, [invalid]);
    assert.match(ui.markup(), /Identity safeguard violation/);
    const condition = conditionNode(ui, identity);
    assert.equal(condition.props['data-eligibility-status'], 'not_yet_evaluated');
    assert.match(ui.text(condition), /student confirmation|human review/i);
  }
  const uncertain = adapt([row('uncertain', identity, identityOpportunity)]);
  assert.equal(presentCondition(uncertain, identityOpportunity.id, identity).status, 'uncertain');
  assert.match(presentCondition(uncertain, identityOpportunity.id, identity).reason, /Student confirmation or human review/);
});

test('empty profile answers do not create outcomes or override explicit backend uncertainty', () => {
  const ui = harness();
  assert.equal(ui.profile().citizenship_status, 'not_stated');
  assert.equal(ui.profile().weighted_average, null);
  assert.deepEqual(ui.profile().skills, []);
  ui.submit();
  assert.equal(conditionNode(ui).props['data-eligibility-status'], 'not_yet_evaluated');
  supply(ui, [{ ...row('uncertain'), explanation: 'Citizenship information was not supplied.' }]);
  assert.equal(conditionNode(ui).props['data-eligibility-status'], 'uncertain');
  assert.match(ui.text(conditionNode(ui)), /Citizenship information was not supplied/);
  ui.change('citizenship_status', 'australian_citizen');
  assert.equal(conditionNode(ui).props['data-eligibility-status'], 'not_yet_evaluated');
  assert.match(ui.markup(), /do not match the current profile/);
  ui.submit();
  assert.equal(conditionNode(ui).props['data-eligibility-status'], 'not_yet_evaluated');
});

test('changing identity never creates eligibility results', () => {
  const ui = harness();
  for (const value of ['yes', 'no', 'prefer_not_to_say', 'not_stated']) {
    ui.change('identity_answer', value);
    ui.submit();
    assert.equal(conditionNode(ui, identity).props['data-eligibility-status'], 'not_yet_evaluated');
  }
});

test('freshness checks validate the exact profile snapshot without using criteria', () => {
  const ui = harness();
  const profile = ui.profile();
  assert.equal(matchesProfileSnapshot(structuredClone(profile), profile), true);
  for (const snapshot of [null, {}, { ...profile, extra: 'field' }, { ...profile, skills: ['ICT'] },
    { ...profile, institution: 'A different institution' }]) assert.equal(matchesProfileSnapshot(snapshot, profile), false);
  const input = supply(ui, [row('satisfied')]);
  ui.change('skillsDropdown', 'ICT');
  assert.equal(conditionNode(ui).props['data-eligibility-status'], 'not_yet_evaluated');
  supply(ui, [row('uncertain')]);
  assert.equal(conditionNode(ui).props['data-eligibility-status'], 'uncertain');
  ui.setProps({ eligibilityInput: input });
  assert.equal(conditionNode(ui).props['data-eligibility-status'], 'not_yet_evaluated');
});

test('evaluation service failures and opportunity connection failures clear results and keep fallback', async () => {
  const requests = [];
  const ui = harness({ fetchImpl: async (url, options) => { requests.push({ url, options }); throw new Error('Offline'); } });
  const input = supply(ui, [row('satisfied')]);
  ui.setProps({ eligibilityInput: { ...input, unavailable: true } });
  assert.equal(conditionNode(ui).props['data-eligibility-status'], 'not_yet_evaluated');
  assert.match(ui.markup(), /Eligibility evaluation is unavailable/);
  ui.setProps({ eligibilityInput: input });
  await ui.button('Check API Status').props.onClick(); ui.render();
  assert.equal(ui.nodes().filter((node) => node.type === 'article').length, 30);
  assert.equal(conditionNode(ui).props['data-eligibility-status'], 'not_yet_evaluated');
  assert.match(ui.markup(), /Development fallback/);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, 'http://127.0.0.1:8000/api/opportunities');
  assert.equal(requests[0].options.body, undefined);
});

test('opportunity API responses never implicitly supply eligibility results', async () => {
  const ui = harness({ fetchImpl: async () => ({ ok: true, json: async () => ({
    opportunities: records, eligibility_results: [row('satisfied')], fixtureResults: [row('unmet')]
  }) }) });
  await ui.button('Check API Status').props.onClick(); ui.render();
  assert.match(ui.markup(), /Source: FastAPI opportunity API/);
  assert.equal(conditionNode(ui).props['data-eligibility-status'], 'not_yet_evaluated');
});

test('explanations render as escaped text and never replace published evidence', () => {
  const snapshot = harness().profile();
  const maliciousText = '<script>alert("fixture")</script>';
  const html = renderInitialApp({ eligibilityInput: {
    payload: { fixtureResults: [{ ...row('uncertain'), explanation: maliciousText }] },
    decodeResponse: decodeFixture, profileSnapshot: snapshot
  } });
  assert.match(html, /&lt;script&gt;/);
  assert.ok(!html.includes(maliciousText));
  assert.match(html, /Condition source/);
  assert.match(html, /Evidence:/);
});
