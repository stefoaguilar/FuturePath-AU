import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { harness } from './helpers/app-harness.mjs';

const records = JSON.parse(readFileSync(new URL('../../data/opportunities.json', import.meta.url), 'utf8')).opportunities;
const cards = (ui) => ui.nodes().filter((node) => node.type === 'article');
const ids = (ui) => cards(ui).map((node) => node.props['data-opportunity-id']);
const counter = (ui) => ui.text(ui.find((node) => node.props.className === 'results-count'));
const more = (ui) => ui.nodes().find((node) => node.type === 'button' && ui.text(node) === 'Load More Opportunities');
const click = (ui, label) => { ui.button(label).props.onClick(); ui.render(); };

test('initial pagination shows six original cards and an accessible native Load More button', () => {
  const ui = harness();
  assert.deepEqual(ids(ui), records.slice(0, 6).map((record) => record.id));
  assert.equal(counter(ui), 'Showing 6 of 30 opportunities');
  assert.equal(more(ui).props.type, 'button');
  assert.equal(more(ui).props['aria-controls'], 'opportunities-grid');
  assert.notEqual(more(ui).props.tabIndex, -1);
  assert.equal(ui.byId('opportunities-grid').props.children.length, 6);
  const announcement = ui.find((node) => node.props.className === 'results-count');
  assert.equal(announcement.props['aria-live'], 'polite');
});

test('each click appends six in source order and the final batch removes the button', () => {
  const ui = harness();
  for (const expected of [12, 18, 24, 30]) {
    click(ui, 'Load More Opportunities');
    assert.deepEqual(ids(ui), records.slice(0, expected).map((record) => record.id));
    assert.equal(counter(ui), `Showing ${expected} of 30 opportunities`);
    assert.equal(new Set(ids(ui)).size, expected);
  }
  assert.equal(more(ui), undefined);
  assert.equal(ui.nodes().filter((node) => node.props['data-condition-id']).length, 81);
});

test('changing or clearing search resets the batch and reports matching totals', () => {
  const ui = harness();
  click(ui, 'Load More Opportunities');
  ui.change('searchQuery', 'OPP-032');
  assert.deepEqual(ids(ui), ['OPP-032']);
  assert.equal(counter(ui), 'Showing 1 of 1 opportunities');
  assert.equal(more(ui), undefined);
  ui.find((node) => node.props['aria-label'] === 'Clear search text').props.onClick(); ui.render();
  assert.equal(cards(ui).length, 6);
  assert.equal(counter(ui), 'Showing 6 of 30 opportunities');
  click(ui, 'Load More Opportunities');
  ui.change('searchQuery', 'not-a-matching-opportunity');
  assert.equal(counter(ui), 'Showing 0 of 0 opportunities');
  assert.equal(cards(ui).length, 0);
  assert.equal(more(ui), undefined);
  click(ui, 'Clear All Filters');
  assert.equal(cards(ui).length, 6);
  assert.equal(counter(ui), 'Showing 6 of 30 opportunities');
});

test('category filtering happens before slicing, resets pagination and handles a partial final batch', () => {
  const ui = harness();
  click(ui, 'Load More Opportunities');
  click(ui, 'scholarship');
  const scholarships = records.filter((record) => record.category === 'scholarship');
  assert.equal(scholarships.length, 10);
  assert.deepEqual(ids(ui), scholarships.slice(0, 6).map((record) => record.id));
  assert.equal(counter(ui), 'Showing 6 of 10 opportunities');
  click(ui, 'Load More Opportunities');
  assert.deepEqual(ids(ui), scholarships.map((record) => record.id));
  assert.equal(counter(ui), 'Showing 10 of 10 opportunities');
  assert.equal(more(ui), undefined);
  click(ui, 'All Opportunities');
  assert.equal(counter(ui), 'Showing 6 of 30 opportunities');
  click(ui, 'Load More Opportunities');
  click(ui, 'cadetship');
  assert.deepEqual(ids(ui), records.filter((record) => record.category === 'cadetship').map((record) => record.id));
  assert.equal(counter(ui), 'Showing 2 of 2 opportunities');
  assert.equal(more(ui), undefined);
  ui.change('searchQuery', 'OPP-032');
  assert.equal(counter(ui), 'Showing 0 of 0 opportunities');
});

test('an opportunity from a later batch can generate and approve a pathway without pagination changing it', () => {
  const ui = harness();
  click(ui, 'Load More Opportunities');
  const later = cards(ui)[7];
  function findAction(node) {
    if (Array.isArray(node)) return node.map(findAction).find(Boolean);
    if (!node?.props) return undefined;
    if (node.type === 'button' && ui.text(node).includes('Plan Pathway')) return node;
    return findAction(node.props.children);
  }
  findAction(later).props.onClick(); ui.render();
  click(ui, 'Approve Pathway');
  const approved = ui.text(ui.byId('pathway-planner-section'));
  assert.ok(approved.includes(records[7].title));
  assert.match(approved, /Plan Locked & Approved by Student/);
  click(ui, 'Load More Opportunities');
  ui.change('searchQuery', 'OPP-032');
  assert.equal(ui.text(ui.byId('pathway-planner-section')), approved);
});
