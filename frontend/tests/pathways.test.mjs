import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { harness } from './helpers/app-harness.mjs';

const records = JSON.parse(readFileSync(new URL('../../data/opportunities.json', import.meta.url), 'utf8')).opportunities;
const titles = (ui) => ui.nodes().filter((node) => node.props.className === 'milestone-title').map(ui.text);
const editField = (ui, prefix) => ui.find((node) => node.props.id?.startsWith(prefix));
const editValue = (ui, prefix, value) => {
  editField(ui, prefix).props.onChange({ target: { value } }); ui.render();
};
const click = (ui, label) => { ui.button(label).props.onClick(); ui.render(); };
const planText = (ui) => ui.text(ui.byId('pathway-planner-section'));
const customForm = (ui) => ui.find((node) => node.type === 'form' && node.props.className === 'add-step-card');
const submitCustom = (ui) => { customForm(ui).props.onSubmit({ preventDefault() {} }); ui.render(); };
function plan(ui, id) {
  ui.change('searchQuery', id);
  click(ui, 'Plan Pathway');
}

test('editing all milestone fields saves changes; cancellation discards the draft', () => {
  const ui = harness();
  plan(ui, records[0].id);
  const original = titles(ui)[0];
  click(ui, 'Edit');
  editValue(ui, 'edit-title-', 'Cancelled title');
  editValue(ui, 'edit-desc-', 'Cancelled description');
  click(ui, 'Cancel');
  assert.equal(titles(ui)[0], original);
  assert.doesNotMatch(planText(ui), /Cancelled title|Cancelled description/);
  click(ui, 'Edit');
  assert.equal(editField(ui, 'edit-title-').props.value, original);
  editValue(ui, 'edit-title-', 'My reviewed milestone');
  editValue(ui, 'edit-desc-', 'My own study notes');
  editValue(ui, 'edit-timeline-', 'At my own pace');
  click(ui, 'Save Step Changes');
  assert.equal(titles(ui)[0], 'My reviewed milestone');
  assert.match(planText(ui), /My own study notes/);
  assert.match(planText(ui), /At my own pace/);
});

test('invalid edits preserve user input and custom-step cancellation resets its form', () => {
  const alerts = [];
  const ui = harness({ alertImpl: (message) => alerts.push(message) });
  click(ui, 'Edit');
  editValue(ui, 'edit-title-', '   ');
  click(ui, 'Save Step Changes');
  assert.equal(editField(ui, 'edit-title-').props.value, '   ');
  assert.match(alerts[0], /title cannot be empty/);
  click(ui, 'Cancel');
  click(ui, 'Add Custom Milestone Step');
  ui.change('new-step-title', 'Unfinished custom step');
  ui.change('new-step-desc', 'Private draft notes');
  click(ui, 'Cancel');
  click(ui, 'Add Custom Milestone Step');
  assert.equal(ui.byId('new-step-title').props.value, '');
  assert.equal(ui.byId('new-step-desc').props.value, '');
  submitCustom(ui);
  assert.match(alerts.at(-1), /enter a milestone title/);
  ui.change('new-step-title', 'Custom study step');
  submitCustom(ui);
  assert.equal(titles(ui).at(-1), 'Custom study step');
});

test('rejected approval keeps the plan editable, retains drafts and creates no timestamp', () => {
  const confirmations = [];
  const ui = harness({ confirmImpl: (message) => { confirmations.push(message); return false; } });
  const original = titles(ui);
  click(ui, 'Add Custom Milestone Step');
  ui.change('new-step-title', 'Still a draft');
  click(ui, 'Approve Pathway');
  assert.deepEqual(titles(ui), original);
  assert.match(planText(ui), /Draft Plan/);
  assert.equal(ui.byId('new-step-title').props.value, 'Still a draft');
  assert.doesNotMatch(planText(ui), /Locked on:|Plan choices approved by student on/);
  assert.match(confirmations[0], /does not confirm eligibility/);
  assert.match(confirmations[0], /NOT submit any applications/);
});

test('unlock clears the stored approval timestamp; reapproval records a new action time', () => {
  let now = '2026-11-05T10:00:00Z';
  class ActionDate extends Date {
    constructor(...args) { super(...(args.length ? args : [now])); }
  }
  const ui = harness({ dateImpl: ActionDate });
  click(ui, 'Approve Pathway');
  const timestamp = ui.text(ui.find((node) => node.props.className === 'approval-time')).replace('Locked on: ', '');
  assert.ok(ui.hasStateValue(timestamp));
  assert.match(planText(ui), /does not establish eligibility/);
  click(ui, 'Unlock & Revise Plan');
  assert.equal(ui.hasStateValue(timestamp), false);
  assert.doesNotMatch(planText(ui), /Locked on:/);
  click(ui, 'Edit');
  editValue(ui, 'edit-title-', 'Editable after unlocking');
  click(ui, 'Save Step Changes');
  now = '2026-11-06T11:00:00Z';
  click(ui, 'Approve Pathway');
  const nextTimestamp = ui.text(ui.find((node) => node.props.className === 'approval-time')).replace('Locked on: ', '');
  assert.notEqual(nextTimestamp, timestamp);
  assert.equal(titles(ui)[0], 'Editable after unlocking');
});

test('approval blocks stale edit, save, reorder, delete, add and form-change handlers immediately', () => {
  const ui = harness();
  plan(ui, records[0].id);
  const staleControls = ui.nodes().filter((node) => node.props.className?.startsWith('control-btn')).map((node) => node.props.onClick);
  const staleOpenCustom = ui.button('Add Custom Milestone Step').props.onClick;
  click(ui, 'Edit');
  editValue(ui, 'edit-title-', 'Unsaved edit');
  const staleChangeEdit = editField(ui, 'edit-title-').props.onChange;
  const staleSave = ui.button('Save Step Changes').props.onClick;
  click(ui, 'Add Custom Milestone Step');
  ui.change('new-step-title', 'Unsaved custom step');
  const staleChangeCustom = ui.byId('new-step-title').props.onChange;
  const staleSubmit = customForm(ui).props.onSubmit;
  const staleCancel = ui.button('Cancel').props.onClick;
  ui.button('Approve Pathway').props.onClick();
  // Intentionally invoke stale callbacks before React has rendered the lock.
  for (const handler of staleControls) handler();
  staleSave(); staleOpenCustom(); staleCancel();
  staleChangeEdit({ target: { value: 'Must not be stored' } });
  staleChangeCustom({ target: { value: 'Must not be stored' } });
  staleSubmit({ preventDefault() {} });
  ui.render();
  assert.equal(titles(ui).length, 4);
  assert.doesNotMatch(planText(ui), /Unsaved edit|Unsaved custom step|Must not be stored/);
  assert.match(planText(ui), /Plan Locked & Approved by Student/);
  assert.ok(!ui.nodes().some((node) => node.props.id?.startsWith('edit-title-')));
  click(ui, 'Unlock & Revise Plan');
  const unlocked = titles(ui);
  // Old callbacks cannot revive a previous editing session after unlocking.
  for (const handler of staleControls) handler();
  staleSave(); staleOpenCustom(); staleSubmit({ preventDefault() {} }); ui.render();
  assert.deepEqual(titles(ui), unlocked);
  click(ui, 'Add Custom Milestone Step');
  assert.equal(ui.byId('new-step-title').props.value, '');
});

test('replacement clears active editing and unfinished custom forms, and rejects old plan handlers', () => {
  const ui = harness();
  plan(ui, records[0].id);
  click(ui, 'Edit');
  editValue(ui, 'edit-title-', 'Old edit draft');
  const staleSave = ui.button('Save Step Changes').props.onClick;
  click(ui, 'Add Custom Milestone Step');
  ui.change('new-step-title', 'Old custom draft');
  ui.change('new-step-desc', 'Old custom description');
  const staleSubmit = customForm(ui).props.onSubmit;
  plan(ui, records[1].id);
  assert.match(planText(ui), new RegExp(records[1].provider.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  assert.doesNotMatch(planText(ui), /Old edit draft|Old custom draft|Old custom description/);
  assert.ok(!ui.nodes().some((node) => node.props.id?.startsWith('edit-title-')));
  staleSave(); staleSubmit({ preventDefault() {} }); ui.render();
  assert.equal(titles(ui).length, 4);
  click(ui, 'Add Custom Milestone Step');
  assert.equal(ui.byId('new-step-title').props.value, '');
  assert.equal(ui.byId('new-step-desc').props.value, '');
  assert.equal(ui.byId('new-step-timeline').props.value, 'Weeks 5 - 6');
});

test('replacement of an approved plan requires confirmation and clears approval only when accepted', () => {
  let accept = true;
  const ui = harness({ confirmImpl: () => accept });
  plan(ui, records[0].id);
  click(ui, 'Approve Pathway');
  const oldPlan = planText(ui);
  const timestamp = ui.text(ui.find((node) => node.props.className === 'approval-time')).replace('Locked on: ', '');
  accept = false;
  plan(ui, records[1].id);
  assert.equal(planText(ui), oldPlan);
  assert.ok(ui.hasStateValue(timestamp));
  accept = true;
  click(ui, 'Plan Pathway');
  assert.match(planText(ui), /Draft Plan/);
  assert.equal(ui.hasStateValue(timestamp), false);
  assert.equal(titles(ui).length, 4);
});

test('documentation guidance retains exact published conditions, evidence and official sources', () => {
  const ui = harness();
  for (const record of records) {
    plan(ui, record.id);
    const evidence = ui.find((node) => node.type === 'details' && node.props.className === 'pathway-evidence');
    const content = ui.text(evidence);
    for (const condition of record.eligibility_conditions) {
      assert.ok(content.includes(condition.text), condition.id);
      assert.ok(content.includes(condition.evidence_summary), condition.id);
      assert.ok(ui.nodes().some((node) => node.type === 'a' && node.props.href === condition.source_url));
    }
    assert.match(planText(ui), /Prepare only evidence explicitly requested/);
    assert.doesNotMatch(planText(ui), /Assemble official transcripts, proof of citizenship|background check references/);
    assert.match(planText(ui), /does not establish eligibility/);
  }
});

test('deleting the final milestone is blocked, while custom steps remain reorderable and deletable', () => {
  const alerts = [];
  const ui = harness({ alertImpl: (message) => alerts.push(message) });
  click(ui, 'Add Custom Milestone Step');
  ui.change('new-step-title', 'My custom step');
  submitCustom(ui);
  ui.find((node) => node.props['aria-label'] === 'Move step 5 up').props.onClick(); ui.render();
  assert.equal(titles(ui)[3], 'My custom step');
  while (titles(ui).length > 1) {
    ui.find((node) => node.props['aria-label'] === 'Delete step 1').props.onClick(); ui.render();
  }
  const last = titles(ui);
  ui.find((node) => node.props['aria-label'] === 'Delete step 1').props.onClick(); ui.render();
  assert.deepEqual(titles(ui), last);
  assert.match(alerts.at(-1), /at least one milestone/);
});
