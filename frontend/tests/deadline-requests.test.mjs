import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { DEMO_REFERENCE_DATE, evaluateDeadline } from '../src/opportunityData.js';
import { harness } from './helpers/app-harness.mjs';

const dataset = JSON.parse(readFileSync(new URL('../../data/opportunities.json', import.meta.url), 'utf8'));
const records = dataset.opportunities;
const ids = (ui) => ui.nodes().filter((node) => node.type === 'article').map((node) => node.props['data-opportunity-id']);
const response = (items, note = '') => ({ ok: true, json: async () => ({ opportunities: items, dataset_note: note }) });
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
};
function manualTimers() {
  const pending = new Map();
  let nextId = 0;
  return {
    setTimeout: (callback, delay) => { pending.set(++nextId, { callback, delay }); return nextId; },
    clearTimeout: (id) => pending.delete(id),
    fire: () => {
      const callbacks = [...pending.values()]; pending.clear();
      callbacks.forEach(({ callback, delay }) => { assert.equal(delay, 3500); callback(); });
    },
    count: () => pending.size
  };
}

test('deadline badges describe all four source statuses without implying a passed assessment', async () => {
  const cases = [
    { deadline: { status: 'unknown', date: null }, label: 'Deadline unknown', badge: 'badge-deadline-unknown' },
    { deadline: { status: 'closed', date: null, note: 'Round closed. No next date published.' }, label: 'Closed round', badge: 'badge-deadline-closed' },
    { deadline: { status: 'date', date: '2026-11-27' }, label: 'Past deadline', badge: 'badge-deadline-past' },
    { deadline: { status: 'date', date: '2026-11-30' }, label: 'Closing soon', badge: 'badge-upcoming' },
    { deadline: { status: 'rolling', date: null }, label: 'Open all year', badge: 'badge-rolling' }
  ];
  for (const { deadline, label, badge } of cases) {
    const result = evaluateDeadline(deadline);
    assert.equal(result.label, label);
    assert.equal(result.badgeClass, badge);
    assert.ok(!('canApplyNow' in result));
    assert.doesNotMatch(result.label + result.badgeClass, /passed/i);
    const ui = harness({ fetchImpl: async () => response([{ ...records[0], deadline }]) });
    await ui.button('Check API Status').props.onClick(); ui.render();
    assert.ok(ui.nodes().some((node) => node.props.className === `badge ${badge}` && ui.text(node) === label));
    assert.match(ui.markup(), /does not confirm that applications are currently open/);
  }
});

test('deadline boundaries remain anchored to 28 November 2026 across month and year boundaries', () => {
  assert.equal(DEMO_REFERENCE_DATE, '2026-11-28');
  for (const [date, status, label, text] of [
    ['2026-11-27', 'past', 'Past deadline', '27 Nov 2026'],
    ['2026-11-28', 'future', 'Closing soon', 'Closes today'],
    ['2026-11-29', 'future', 'Closing soon', '1 day left'],
    ['2026-12-01', 'future', 'Closing soon', '3 days left'],
    ['2026-12-05', 'future', 'Closing soon', '7 days left'],
    ['2026-12-06', 'future', 'Future deadline', '8 days left'],
    ['2027-01-01', 'future', 'Future deadline', '34 days left']
  ]) {
    const result = evaluateDeadline({ status: 'date', date });
    assert.equal(result.status, status);
    assert.equal(result.label, label);
    assert.ok(result.displayDate.includes(text));
  }
  const closed = evaluateDeadline({ status: 'closed', date: '2026-03-30' });
  assert.match(closed.displayDate, /Previous closing date: 30 Mar 2026/);
  assert.match(evaluateDeadline({ status: 'closed', date: null }).displayDate, /not published/);
  assert.equal(evaluateDeadline({ status: 'unknown', date: null }).displayDate, 'Deadline unknown');
});

test('network, HTTP, invalid JSON and invalid schema failures use safe, distinct fallback messages', async () => {
  const privateText = 'PRIVATE_ERROR_DETAILS /private/server/path <script>fixture</script>';
  for (const [fetchImpl, message] of [
    [async () => { throw new Error(privateText); }, /Could not connect/],
    [async () => ({ ok: false, status: 500, statusText: privateText }), /unsuccessful response/],
    [async () => ({ ok: true, json: async () => { throw new Error(privateText); } }), /data that could not be used safely/],
    [async () => ({ ok: true, json: async () => ({ opportunities: [{ id: privateText }] }) }), /data that could not be used safely/]
  ]) {
    const timers = manualTimers();
    const ui = harness({ fetchImpl, timers });
    await ui.button('Check API Status').props.onClick(); ui.render();
    assert.match(ui.markup(), message);
    assert.doesNotMatch(ui.markup(), /PRIVATE_ERROR_DETAILS|private\/server\/path/);
    assert.deepEqual(ids(ui), records.map((r) => r.id));
    assert.match(ui.markup(), /Development fallback: data\/opportunities.json/);
    assert.equal(ui.button('Retry Connection').props.disabled, false);
    assert.equal(timers.count(), 0);
  }
});

test('timeout aborts the active request and restores fallback without exposing raw errors', async () => {
  const timers = manualTimers();
  const ui = harness({ timers, fetchImpl: (_url, { signal }) => new Promise((_resolve, reject) => {
    signal.addEventListener('abort', () => reject(new Error('PRIVATE_ABORT_DETAILS')), { once: true });
  }) });
  const pending = ui.button('Check API Status').props.onClick(); ui.render();
  assert.equal(ui.button('Checking...').props.disabled, true);
  timers.fire();
  await pending; ui.render();
  assert.match(ui.markup(), /took too long to respond/);
  assert.doesNotMatch(ui.markup(), /PRIVATE_ABORT_DETAILS/);
  assert.equal(ids(ui).length, 30);
  assert.equal(timers.count(), 0);
});

test('a response finishing after its timeout cannot be accepted even when transport ignores abort', async () => {
  const timers = manualTimers();
  const body = deferred();
  const bodyStarted = deferred();
  const ui = harness({ timers, fetchImpl: async () => ({ ok: true, json: () => { bodyStarted.resolve(); return body.promise; } }) });
  const pending = ui.button('Check API Status').props.onClick();
  await bodyStarted.promise;
  timers.fire();
  body.resolve({ opportunities: [records[0]] });
  await pending; ui.render();
  assert.equal(ids(ui).length, 30);
  assert.match(ui.markup(), /took too long to respond/);
});

test('older successes and failures cannot overwrite a newer success', async () => {
  for (const oldFails of [false, true]) {
    const older = deferred(), newer = deferred();
    const signals = [];
    const timers = manualTimers();
    const ui = harness({ timers, fetchImpl: (_url, { signal }) => {
      signals.push(signal); return signals.length === 1 ? older.promise : newer.promise;
    } });
    const start = ui.button('Check API Status').props.onClick;
    const first = start(); ui.render();
    const second = start(); ui.render();
    assert.equal(signals[0].aborted, true);
    assert.equal(timers.count(), 1);
    newer.resolve(response([records[1]], 'Newer dataset note'));
    await second; ui.render();
    assert.deepEqual(ids(ui), [records[1].id]);
    if (oldFails) older.reject(new Error('Older private failure'));
    else older.resolve(response([records[0]], 'Older dataset note'));
    await first; ui.render();
    assert.deepEqual(ids(ui), [records[1].id]);
    assert.match(ui.markup(), /Newer dataset note/);
    assert.doesNotMatch(ui.markup(), /Older dataset note|Opportunity API unavailable/);
    assert.match(ui.markup(), /Source: FastAPI opportunity API/);
    assert.equal(timers.count(), 0);
  }
});

test('an older completion cannot clear the newer request loading state', async () => {
  const older = deferred(), newer = deferred();
  let calls = 0;
  const ui = harness({ fetchImpl: () => ++calls === 1 ? older.promise : newer.promise });
  const start = ui.button('Check API Status').props.onClick;
  const first = start();
  const second = start();
  older.resolve(response([records[0]]));
  await first; ui.render();
  assert.equal(ui.button('Checking...').props.disabled, true);
  assert.match(ui.markup(), /Fetching opportunities/);
  newer.resolve(response([records[1]]));
  await second; ui.render();
  assert.deepEqual(ids(ui), [records[1].id]);
  assert.equal(ui.button('Check API Status').props.disabled, false);
});

test('an older JSON body cannot replace the newest fallback or its error message', async () => {
  const oldBody = deferred(), newer = deferred();
  const bodyStarted = deferred();
  let calls = 0;
  const ui = harness({ fetchImpl: async () => ++calls === 1 ? {
    ok: true, json: () => { bodyStarted.resolve(); return oldBody.promise; }
  } : newer.promise });
  const start = ui.button('Check API Status').props.onClick;
  const first = start();
  await bodyStarted.promise;
  const second = start();
  newer.reject(new Error('New request network failure'));
  await second; ui.render();
  assert.equal(ids(ui).length, 30);
  oldBody.resolve({ opportunities: [records[0]], dataset_note: 'Stale body' });
  await first; ui.render();
  assert.equal(ids(ui).length, 30);
  assert.match(ui.markup(), /Could not connect/);
  assert.doesNotMatch(ui.markup(), /Stale body/);
});

test('effect cleanup cancels requests and a subsequent mount accepts only its own response', async () => {
  const older = deferred(), newer = deferred();
  const timers = manualTimers();
  const signals = [];
  const ui = harness({ timers, fetchImpl: (_url, { signal }) => {
    signals.push(signal); return signals.length === 1 ? older.promise : newer.promise;
  } });
  const cleanup = ui.runEffects();
  cleanup();
  assert.equal(signals[0].aborted, true);
  assert.equal(timers.count(), 0);
  const newCleanup = ui.runEffects();
  newer.resolve(response([records[1]]));
  await new Promise((resolve) => setImmediate(resolve)); ui.render();
  assert.deepEqual(ids(ui), [records[1].id]);
  older.resolve(response([records[0]]));
  await new Promise((resolve) => setImmediate(resolve)); ui.render();
  assert.deepEqual(ids(ui), [records[1].id]);
  newCleanup();
  assert.equal(timers.count(), 0);
});

test('retry recovers from fallback, preserves filters and accepts a valid empty API list', async () => {
  let attempts = 0;
  const ui = harness({ fetchImpl: async () => {
    if (++attempts === 1) throw new Error('Offline');
    return response(attempts === 2 ? records : []);
  } });
  ui.change('searchQuery', 'OPP-032');
  await ui.button('Check API Status').props.onClick(); ui.render();
  assert.deepEqual(ids(ui), ['OPP-032']);
  const retry = ui.button('Retry Connection').props.onClick(); ui.render();
  assert.match(ui.markup(), /Fetching opportunities/);
  await retry; ui.render();
  assert.deepEqual(ids(ui), ['OPP-032']);
  assert.match(ui.markup(), /Source: FastAPI opportunity API/);
  assert.doesNotMatch(ui.markup(), /Opportunity API unavailable/);
  await ui.button('Check API Status').props.onClick(); ui.render();
  assert.deepEqual(ids(ui), []);
  assert.match(ui.markup(), /Source: FastAPI opportunity API/);
  assert.doesNotMatch(ui.markup(), /Development fallback: data/);
});
