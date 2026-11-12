import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { adaptEligibilityResults, decodeEligibilityResponse, evaluateOpportunities, emptyEligibility, matchesProfileSnapshot, presentCondition, summarizeConditions } from '../src/eligibilityResults.js';
import { harness, renderInitialApp, loadAllOpportunities } from './helpers/app-harness.mjs';

const records = JSON.parse(readFileSync(new URL('../../data/opportunities.json', import.meta.url), 'utf8')).opportunities;
const opportunity = records.find((r) => r.eligibility_conditions.filter((c) => c.type !== 'identity_requirement').length >= 3);
const ordinary = opportunity.eligibility_conditions.filter((c) => c.type !== 'identity_requirement');
const identityOpportunity = records.find((r) => r.eligibility_conditions.some((c) => c.type === 'identity_requirement'));
const identity = identityOpportunity.eligibility_conditions.find((c) => c.type === 'identity_requirement');

// Keep the internal presentation seam separate from FastAPI transport fixtures.
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

// Find and click the evaluation button inside a specific opportunity card.
function evaluateCard(ui, owner = opportunity) {
  const descendants = (node) => {
    if (Array.isArray(node)) return node.flatMap(descendants);
    if (!node || !node.props) return [];
    return [node, ...descendants(node.props.children)];
  };

  const buttons = descendants(cardNode(ui, owner)).filter(
    (node) =>
      node.type === 'button' &&
      ui.text(node).includes('Evaluate Eligibility Conditions')
  );

  assert.equal(buttons.length, 1);
  buttons[0].props.onClick();
  ui.render();
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
  loadAllOpportunities(ui);
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
  loadAllOpportunities(ui);
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
  loadAllOpportunities(ui);
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

const wireResponse = (owner, status = 'uncertain') => ({
  opportunity_id: owner.id,
  results: owner.eligibility_conditions.map((condition) => ({
    condition_id: condition.id,
    status: condition.type === 'identity_requirement' ? 'uncertain' : status,
    explanation: 'Backend comparison for this profile.',
    requirement: condition.text, evidence_summary: condition.evidence_summary, source_url: condition.source_url
  })),
  notice: 'These comparisons are informational only. They do not represent an official eligibility or admission decision.'
});
const ok = (payload) => ({ ok: true, json: async () => payload });
const settle = () => new Promise((resolve) => setImmediate(resolve));
const deferred = () => {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
};

test('strict FastAPI decoder converts verified IDs and accepts only documented fields and evidence', () => {
  const payload = wireResponse(opportunity, 'satisfied');
  const before = JSON.stringify(payload);
  const rows = decodeEligibilityResponse(payload, opportunity);
  assert.equal(rows[0].opportunityId, opportunity.id);
  assert.equal(rows[0].conditionId, payload.results[0].condition_id);
  assert.equal(adaptEligibilityResults(payload, [opportunity], (body) => decodeEligibilityResponse(body, opportunity)).state, 'ready');
  assert.equal(JSON.stringify(payload), before);
  const minimal = { ...payload, results: [{ condition_id: ordinary[0].id, status: 'uncertain', explanation: '' }] };
  assert.equal(decodeEligibilityResponse(minimal, opportunity).length, 1);
  for (const change of [
    (p) => { p.opportunity_id = identityOpportunity.id === opportunity.id ? 'OPP-999' : identityOpportunity.id; },
    (p) => { p.score = 100; }, (p) => { delete p.notice; }, (p) => { p.notice = {}; },
    (p) => { p.results = {}; }, (p) => { p.results.push(p.results[0]); },
    (p) => { p.results[0].condition_id = 'OPP-999-E1'; },
    (p) => { p.results[0].condition_id = 1; },
    (p) => { p.results[0].status = 'eligible'; },
    (p) => { p.results[0].status = 'not_yet_evaluated'; },
    (p) => { p.results[0].score = 1; },
    (p) => { p.results[0].explanation = null; },
    (p) => { p.results[0].source_url = 'https://untrusted.example'; },
    (p) => { p.results[0].requirement = {}; },
    (p) => { p.results[0].evidence_summary = 'Changed evidence'; }
  ]) {
    const invalid = structuredClone(payload); change(invalid);
    assert.throws(() => decodeEligibilityResponse(invalid, opportunity));
  }
});

test('transport sends one POST per loaded opportunity, excludes identity, and limits concurrency to three', async () => {
  const pending = [], requests = [];
  let active = 0, maximum = 0;
  const profile = harness().profile();
  profile.identity_answer = 'yes';
  const original = JSON.stringify(profile);
  const evaluation = evaluateOpportunities(profile, records, { fetchImpl: (url, options) => {
    const body = JSON.parse(options.body);
    requests.push(body);
    assert.equal(url, 'http://127.0.0.1:8000/api/eligibility/evaluate');
    assert.equal(options.method, 'POST');
    assert.equal(options.headers['Content-Type'], 'application/json');
    assert.ok(!Object.hasOwn(body.profile, 'identity_answer'));
    assert.equal(body.profile.citizenship_status, profile.citizenship_status);
    maximum = Math.max(maximum, ++active);
    return new Promise((resolve) => pending.push(() => {
      active--;
      resolve(ok(wireResponse(records.find((r) => r.id === body.opportunity_id))));
    }));
  } });
  assert.equal(pending.length, 3);
  while (requests.length < records.length || pending.length) {
    pending.splice(0).forEach((resolve) => resolve());
    await settle();
  }
  const result = await evaluation;
  assert.equal(maximum, 3);
  assert.equal(result.state, 'ready');
  assert.equal(result.results.size, 81);
  assert.equal(result.notices.length, 1);
  assert.deepEqual(requests.map((body) => body.opportunity_id), records.map((r) => r.id));
  assert.equal(JSON.stringify(profile), original);
});

test('selected opportunity displays validated backend decisions without changing published evidence', async () => {
  const requests = [];

  const ui = harness({
    fetchImpl: async (url, options) => {
      const body = JSON.parse(options.body);
      requests.push(body);

      assert.equal(
        url,
        'http://127.0.0.1:8000/api/eligibility/evaluate'
      );

      return ok(
        wireResponse(
          records.find((r) => r.id === body.opportunity_id),
          'satisfied'
        )
      );
    }
  });

  ui.change('citizenship_status', 'australian_citizen');
  ui.change('weighted_average', '65', {
    validity: { badInput: false },
    valueAsNumber: 65
  });
  ui.change('identity_answer', 'yes');

  // Profile submission must not evaluate opportunities automatically.
  ui.submit();
  assert.equal(requests.length, 0);

  // Click Evaluate Eligibility Conditions for OPP-003 only.
  evaluateCard(ui, opportunity);

  assert.match(ui.markup(), /Evaluating published conditions/);

  assert.equal(
    conditionNode(ui).props['data-eligibility-status'],
    'not_yet_evaluated'
  );

  await settle();
  ui.render();

  // Exactly one POST request for the selected opportunity.
  assert.equal(requests.length, 1);
  assert.equal(requests[0].opportunity_id, opportunity.id);
  assert.equal(requests[0].profile.weighted_average, 65);

  // Identity information must never be sent to the backend.
  assert.equal(
    Object.hasOwn(requests[0].profile, 'identity_answer'),
    false
  );

  // Ordinary conditions display accepted backend results.
  assert.equal(
    conditionNode(ui).props['data-eligibility-status'],
    'satisfied'
  );

  // The selected opportunity's identity condition remains uncertain.
  const selectedIdentity = opportunity.eligibility_conditions.find(
    (condition) => condition.type === 'identity_requirement'
  );

  assert.ok(selectedIdentity);

  assert.equal(
    conditionNode(ui, selectedIdentity).props['data-eligibility-status'],
    'uncertain'
  );

  // Another opportunity must remain unevaluated.
  assert.equal(
    conditionNode(ui, identity).props['data-eligibility-status'],
    'not_yet_evaluated'
  );

  // Backend explanations and original evidence must remain intact.
  assert.match(
    ui.text(conditionNode(ui)),
    /Backend comparison for this profile/
  );

  assert.ok(
    ui.text(conditionNode(ui)).includes(ordinary[0].evidence_summary)
  );

  assert.match(
    ui.markup(),
    /These comparisons are informational only/
  );
});

test('network, HTTP, invalid JSON and malformed batches stay neutral and do not leak private errors', async () => {
  for (const fetchImpl of [
    async () => { throw new Error('PRIVATE_NETWORK_DETAILS'); },
    async () => ({ ok: false, status: 422 }),
    async () => ({
      ok: true,
      json: async () => {
        throw new Error('PRIVATE_JSON_DETAILS');
      }
    }),
    async () => ok({
      opportunity_id: 'OPP-999',
      results: [],
      notice: 'Test'
    })
  ]) {
    let requests = 0;

    const ui = harness({
      fetchImpl: async (...args) => {
        requests++;
        return fetchImpl(...args);
      }
    });

    // Profile validation alone must not send API requests.
    ui.submit();
    assert.equal(requests, 0);

    // Request eligibility for the selected opportunity only.
    evaluateCard(ui, opportunity);

    await settle();
    ui.render();

    assert.equal(requests, 1);

    // Failed evaluations must remain neutral.
    assert.equal(
      conditionNode(ui).props['data-eligibility-status'],
      'not_yet_evaluated'
    );

    // Display safe error messages without private details.
    assert.match(
      ui.markup(),
      /Could not connect|unsuccessful response|Eligibility response rejected/
    );

    assert.doesNotMatch(ui.markup(), /PRIVATE_/);
  }

  // Duplicate condition results must reject the entire response.
  const result = await evaluateOpportunities(
    harness().profile(),
    [opportunity],
    {
      fetchImpl: async () => {
        const payload = wireResponse(opportunity, 'satisfied');
        payload.results.push(payload.results[0]);
        return ok(payload);
      }
    }
  );

  assert.equal(result.results.size, 0);
  assert.match(result.warning, /rejected/);
});

test('wire identity decisions and unsupported scores are rejected atomically', async () => {
  for (const status of ['satisfied', 'unmet', 'score']) {
    const payload = wireResponse(identityOpportunity);
    const result = payload.results.find((r) => r.condition_id === identity.id);
    if (status === 'score') result.score = 1;
    else result.status = status;
    const batch = await evaluateOpportunities(harness().profile(), [identityOpportunity], { fetchImpl: async () => ok(payload) });
    assert.equal(batch.results.size, 0);
    assert.match(batch.warning, /Identity safeguard|rejected/);
  }
});

test('timeout settles even an uncooperative transport and aborts active requests', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const signals = [];
  const evaluation = evaluateOpportunities(harness().profile(), records, { fetchImpl: (_url, { signal }) => {
    signals.push(signal); return new Promise(() => {});
  } });
  t.mock.timers.tick(3500);
  const batch = await evaluation;
  assert.equal(signals.length, 3);
  assert.ok(signals.every((signal) => signal.aborted));
  assert.equal(batch.results.size, 0);
  assert.match(batch.warning, /timed out/);
});

test('cancellation during JSON decoding rejects late results and stops queued requests', async () => {
  const controller = new AbortController();
  const body = deferred();
  let requests = 0;
  const signals = [];
  const evaluation = evaluateOpportunities(harness().profile(), records, { signal: controller.signal,
    fetchImpl: async (_url, { signal }) => {
      requests++; signals.push(signal); return { ok: true, json: () => body.promise };
    }
  });
  await settle(); controller.abort();
  const batch = await evaluation;
  assert.equal(requests, 3);
  assert.ok(signals.every((signal) => signal.aborted));
  assert.equal(batch.results.size, 0);
  assert.match(batch.warning, /cancelled/);
  body.resolve(wireResponse(records[0], 'satisfied'));
  await settle();
  assert.equal(batch.results.size, 0);
  const alreadyCancelled = await evaluateOpportunities(harness().profile(), records, { signal: controller.signal,
    fetchImpl: () => { throw new Error('Must not send'); } });
  assert.equal(alreadyCancelled.results.size, 0);
});

test('profile edits, including identity changes and alternate profiles, cancel requests and clear results', async () => {
  for (const edit of [
    (ui) => ui.change('citizenship_status', 'other'),
    (ui) => ui.change('identity_answer', 'no'),
    (ui) => {
      ui.button('Load Alternate Test Profile').props.onClick();
      ui.render();
    }
  ]) {
    const pending = [];
    const signals = [];

    const ui = harness({
      fetchImpl: (_url, options) => {
        const owner = records.find(
          (r) => r.id === JSON.parse(options.body).opportunity_id
        );

        signals.push(options.signal);

        return new Promise((resolve) => {
          pending.push(() => resolve(ok(wireResponse(owner, 'satisfied'))));
        });
      }
    });

    // Validate the profile without automatically evaluating opportunities.
    ui.submit();
    assert.equal(signals.length, 0);

    // Start one request for the selected opportunity.
    evaluateCard(ui, opportunity);
    assert.equal(signals.length, 1);

    // Editing the profile must cancel that request.
    edit(ui);

    assert.equal(signals[0].aborted, true);

    // Even if the old request completes, its result must not appear.
    pending.forEach((resolve) => resolve());

    await settle();
    ui.render();

    assert.equal(
      conditionNode(ui).props['data-eligibility-status'],
      'not_yet_evaluated'
    );
  }
});

test('newer selected evaluations and dataset refreshes cannot be overwritten by old responses', async () => {
  const older = [];
  const signals = [];
  let first = true;
  let evaluationRequests = 0;

  const ui = harness({
    fetchImpl: async (url, options) => {
      if (!url.endsWith('/evaluate')) {
        return ok({ opportunities: records.slice(0, 2) });
      }

      const owner = records.find(
        (r) => r.id === JSON.parse(options.body).opportunity_id
      );

      signals.push(options.signal);
      evaluationRequests++;

      if (first) {
        return new Promise((resolve) => {
          older.push(() => resolve(ok(wireResponse(owner, 'unmet'))));
        });
      }

      return ok(wireResponse(owner, 'satisfied'));
    }
  });

  // Profile submission must not initiate an evaluation.
  ui.submit();
  assert.equal(evaluationRequests, 0);

  // First evaluation remains pending.
  evaluateCard(ui, opportunity);
  assert.equal(evaluationRequests, 1);

  // A second evaluation cancels the first.
  first = false;
  evaluateCard(ui, opportunity);

  assert.equal(evaluationRequests, 2);
  assert.equal(signals[0].aborted, true);

  await settle();
  ui.render();

  // The newer successful result must be displayed.
  assert.equal(
    conditionNode(ui).props['data-eligibility-status'],
    'satisfied'
  );

  // Completing the old request must not overwrite the new result.
  older.forEach((resolve) => resolve());

  await settle();
  ui.render();

  assert.equal(
    conditionNode(ui).props['data-eligibility-status'],
    'satisfied'
  );

  // Refreshing the dataset invalidates previous eligibility results.
  await ui.button('Check API Status').props.onClick();
  ui.render();

  assert.ok(
    ui.nodes()
      .filter((node) => node.props['data-condition-id'])
      .every(
        (node) =>
          node.props['data-eligibility-status'] === 'not_yet_evaluated'
      )
  );
});

test('dataset changes and component cleanup abort pending eligibility requests', async () => {
  const pending = [], signals = [];
  const ui = harness({ fetchImpl: async (url, options) => {
    if (!url.endsWith('/evaluate')) return ok({ opportunities: records });
    const owner = records.find((r) => r.id === JSON.parse(options.body).opportunity_id);
    signals.push(options.signal);
    return new Promise((resolve) => pending.push(() => resolve(ok(wireResponse(owner, 'satisfied')))));
  } });
  const cleanup = ui.runEffects(); await settle(); ui.render();
  ui.submit();
  await ui.button('Check API Status').props.onClick(); ui.render();
  assert.ok(signals.every((signal) => signal.aborted));
  ui.submit(); cleanup();
  assert.ok(signals.every((signal) => signal.aborted));
  pending.forEach((resolve) => resolve()); await settle(); ui.render();
  assert.equal(conditionNode(ui).props['data-eligibility-status'], 'not_yet_evaluated');
});

test('invalid profile inputs send no evaluation requests', () => {
  let requests = 0;
  const ui = harness({ fetchImpl: () => { requests++; throw new Error('Must not send'); } });
  ui.change('careerGoal', ''); ui.submit();
  assert.equal(requests, 0);
  ui.change('careerGoal', 'SOC Analyst');
  ui.change('weighted_average', '', { validity: { badInput: true }, valueAsNumber: NaN }); ui.submit();
  assert.equal(requests, 0);
});

test('a failed retry clears previously validated results instead of retaining old decisions', async () => {
  let fail = false;
  let requests = 0;

  const ui = harness({
    fetchImpl: async (_url, options) => {
      requests++;

      if (fail) {
        throw new Error('PRIVATE_FAILURE');
      }

      const owner = records.find(
        (r) => r.id === JSON.parse(options.body).opportunity_id
      );

      return ok(wireResponse(owner, 'satisfied'));
    }
  });

  // Profile validation does not trigger an eligibility request.
  ui.submit();
  assert.equal(requests, 0);

  // First evaluation succeeds for the selected opportunity.
  evaluateCard(ui, opportunity);

  await settle();
  ui.render();

  assert.equal(requests, 1);

  assert.equal(
    conditionNode(ui).props['data-eligibility-status'],
    'satisfied'
  );

  // Simulate backend failure during a second evaluation.
  fail = true;
  evaluateCard(ui, opportunity);

  // Previous results must disappear immediately.
  assert.equal(
    conditionNode(ui).props['data-eligibility-status'],
    'not_yet_evaluated'
  );

  await settle();
  ui.render();

  assert.equal(requests, 2);

  // Failed requests must not restore previous decisions.
  assert.equal(
    conditionNode(ui).props['data-eligibility-status'],
    'not_yet_evaluated'
  );

  // Display a safe message without exposing private error details.
  assert.match(ui.markup(), /Could not connect/);
  assert.doesNotMatch(ui.markup(), /PRIVATE_FAILURE/);
});

test('selected evaluation waits for opportunity loading before requesting backend', async () => {
  const dataset = deferred();
  let requests = 0;

  const ui = harness({
    fetchImpl: async (url, options) => {
      if (!url.endsWith('/evaluate')) {
        return dataset.promise;
      }

      requests++;

      const owner = records.find(
        (r) => r.id === JSON.parse(options.body).opportunity_id
      );

      return ok(wireResponse(owner));
    }
  });

  const cleanup = ui.runEffects();

  // Profile validation must not trigger eligibility evaluation.
  ui.submit();
  assert.equal(requests, 0);

  // Opportunity cards are unavailable while the dataset is loading.
  assert.match(
    ui.markup(),
    /Fetching opportunities from FastAPI/
  );

  const evaluationButtons = ui.nodes().filter(
    (node) =>
      node.type === 'button' &&
      ui.text(node).includes('Evaluate Eligibility Conditions')
  );

  assert.equal(evaluationButtons.length, 0);

  // Complete the opportunity dataset request.
  dataset.resolve(ok({ opportunities: records }));

  await settle();
  ui.render();

  // Loading the dataset must not automatically trigger evaluation.
  assert.equal(requests, 0);

  // The student can now evaluate one selected opportunity.
  evaluateCard(ui, opportunity);

  await settle();
  ui.render();

  assert.equal(requests, 1);

  assert.equal(
    conditionNode(ui).props['data-eligibility-status'],
    'uncertain'
  );

  cleanup();
});
