import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { runInNewContext } from 'node:vm';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { transformSync } from 'esbuild';

const require = createRequire(import.meta.url);
const source = readFileSync(new URL('../src/App.jsx', import.meta.url), 'utf8');
const mapping = readFileSync(new URL('../../data/PROFILE_MAPPING.md', import.meta.url), 'utf8');
const code = transformSync(source, { loader: 'jsx', format: 'cjs' }).code;

// Run the actual component handlers against a small state harness without adding
// a browser/test dependency. The SSR check below also uses real React hooks.
function harness() {
  const state = [];
  let cursor = 0;
  let tree;
  let activeProfile;
  const hooks = {
    ...React,
    useState(initial) {
      const index = cursor++;
      if (!(index in state)) state[index] = initial;
      return [state[index], (value) => {
        state[index] = typeof value === 'function' ? value(state[index]) : value;
      }];
    },
    useMemo(fn) {
      const result = fn();
      if (result && 'education_level' in result) activeProfile = result;
      return result;
    },
    useEffect() {}
  };
  const module = { exports: {} };
  runInNewContext(code, {
    module, exports: module.exports,
    require: (name) => name === 'react' ? hooks : require(name),
    fetch: async () => { throw new Error('Offline test'); },
    AbortController, setTimeout, clearTimeout,
    console: { warn() {} },
    window: { confirm: () => true },
    document: { getElementById: () => null }
  });
  const render = () => { cursor = 0; tree = module.exports.default(); };
  const nodes = () => {
    const result = [];
    function visit(node) {
      if (Array.isArray(node)) return node.forEach(visit);
      if (node && typeof node === 'object' && node.props) {
        result.push(node);
        visit(node.props.children);
      }
    }
    visit(tree);
    return result;
  };
  const find = (predicate) => {
    const node = nodes().find(predicate);
    assert.ok(node, 'Expected UI control exists');
    return node;
  };
  const text = (node) => {
    if (Array.isArray(node)) return node.map(text).join('');
    return node?.props ? text(node.props.children) : String(node ?? '');
  };
  const byId = (id) => find((node) => node.props.id === id);
  const button = (label) => find((node) => node.type === 'button' && text(node).includes(label));
  const change = (id, value, extra = {}) => {
    byId(id).props.onChange({ target: { value, ...extra } });
    render();
  };
  const submit = () => {
    find((node) => node.type === 'form' && node.props.className === 'profile-form')
      .props.onSubmit({ preventDefault() {} });
    render();
  };
  render();
  return {
    render, nodes, find, text, byId, button, change, submit,
    profile: () => JSON.parse(JSON.stringify(activeProfile)),
    markup: () => text(tree)
  };
}

test('profile keys, types, options and agreed skill tags match PROFILE_MAPPING.md', () => {
  const ui = harness();
  const rows = [...mapping.matchAll(/^\| `([^`]+)` \| (text|number|list of text) \| (.+) \|$/gm)];
  const profile = ui.profile();
  assert.equal(rows.length, 11);
  assert.deepEqual(Object.keys(profile), rows.map((row) => row[1]));
  for (const [, field, type, allowed] of rows) {
    if (type === 'list of text') assert.ok(Array.isArray(profile[field]));
    else if (type === 'number') assert.equal(profile[field], null);
    else assert.equal(typeof profile[field], 'string');
    if (allowed.includes('`not_stated`')) {
      const options = ui.byId(field).props.children.map((option) => option.props.value);
      assert.deepEqual(Array.from(options), [...allowed.matchAll(/`([^`]+)`/g)].map((match) => match[1]));
    }
  }
  const tags = [...mapping.split('## Skill tags in use')[1].matchAll(/`([^`]+)`/g)].map((match) => match[1]);
  for (const tag of tags) assert.ok(ui.nodes().some((node) => node.type === 'option' && node.props.value === tag));
  assert.ok(ui.byId('careerGoal').props.value.includes('SOC Analyst'));
  assert.ok(!('careerGoal' in profile));
  assert.match(ui.markup(), /validation pending/);
});

test('optional answers submit empty; editing and validation failures preserve data', () => {
  const ui = harness();
  ui.submit();
  assert.match(ui.markup(), /Profile inputs validated/);
  ui.change('institution', 'Curtin University');
  assert.match(ui.markup(), /validation pending/);
  ui.change('careerGoal', '  ');
  ui.submit();
  assert.match(ui.markup(), /Please specify your Cybersecurity Career Goal/);
  assert.equal(ui.profile().institution, 'Curtin University');
  ui.change('careerGoal', 'Incident Responder');
  ui.change('weighted_average', '78.5', { valueAsNumber: 78.5, validity: { badInput: false } });
  ui.submit();
  assert.equal(ui.profile().weighted_average, 78.5);
  assert.match(ui.markup(), /Profile inputs validated/);
  ui.change('weighted_average', '', { valueAsNumber: NaN, validity: { badInput: true } });
  ui.submit();
  assert.match(ui.markup(), /Enter a valid finite number/);
  ui.change('weighted_average', '', { valueAsNumber: NaN, validity: { badInput: false } });
  ui.submit();
  assert.equal(ui.profile().weighted_average, null);
  assert.deepEqual(ui.profile().skills, []);
  assert.deepEqual(ui.profile().preferred_agencies, []);
  assert.match(ui.markup(), /Profile inputs validated/);
});

test('skills and agencies support selection, custom text and removal as string arrays', () => {
  const ui = harness();
  ui.change('skillsDropdown', 'ICT');
  ui.change('skillsDropdown', 'STEM');
  ui.change('customSkill', '  Threat modelling  ');
  ui.button('Add Skill').props.onClick(); ui.render();
  assert.deepEqual(ui.profile().skills, ['ICT', 'STEM', 'Threat modelling']);
  ui.find((node) => node.props['aria-label'] === 'Remove skill ICT').props.onClick(); ui.render();
  assert.deepEqual(ui.profile().skills, ['STEM', 'Threat modelling']);
  ui.button('Clear All').props.onClick(); ui.render();
  ui.change('customAgency', 'Defence');
  ui.button('Add Agency').props.onClick(); ui.render();
  ui.change('customAgency', 'Custom Agency');
  ui.button('Add Agency').props.onClick(); ui.render();
  assert.deepEqual(ui.profile().preferred_agencies, ['Defence', 'Custom Agency']);
  while (ui.profile().preferred_agencies.length > 0) {
    const checkbox = ui.find((node) => node.props.type === 'checkbox' && node.props.checked);
    checkbox.props.onChange({ target: { checked: false } }); ui.render();
  }
  assert.deepEqual(ui.profile().preferred_agencies, []);
  assert.equal(ui.nodes().filter((node) => node.props.type === 'checkbox').length, 2);
  ui.submit();
  assert.match(ui.markup(), /Profile inputs validated/);
});

test('cards, filters, pathway editing and approval run without local eligibility inference', async () => {
  const ui = harness();
  await ui.button('Check API Status').props.onClick(); ui.render();
  assert.equal(ui.nodes().filter((node) => node.type === 'article').length, 6);
  for (const answer of ['yes', 'no', 'prefer_not_to_say', 'not_stated']) {
    ui.change('identity_answer', answer);
    ui.change('skillsDropdown', 'Python');
    ui.submit();
    const statuses = ui.nodes().filter((node) => node.props.className?.startsWith('status-tag'));
    assert.ok(statuses.length > 0);
    assert.ok(statuses.every((node) => ui.text(node) === 'Not yet evaluated'));
  }
  ui.change('searchQuery', 'Telstra');
  assert.equal(ui.nodes().filter((node) => node.type === 'article').length, 1);
  ui.button('Plan Pathway').props.onClick(); ui.render();
  assert.match(ui.markup(), /Review Published Requirements & Plan Foundational Study/);
  ui.button('Edit').props.onClick(); ui.render();
  const title = ui.nodes().find((node) => node.props.id?.startsWith('edit-title-'));
  title.props.onChange({ target: { value: 'My revised study plan' } }); ui.render();
  ui.button('Save').props.onClick(); ui.render();
  assert.match(ui.markup(), /My revised study plan/);
  ui.button('Approve Pathway').props.onClick(); ui.render();
  assert.match(ui.markup(), /Plan Locked & Approved by Student/);
  ui.button('Unlock & Revise Plan').props.onClick(); ui.render();
  assert.match(ui.markup(), /Draft Plan/);
});

test('initial UI renders with React 18 server rendering', () => {
  const module = { exports: {} };
  runInNewContext(code, { module, exports: module.exports, require });
  const html = renderToStaticMarkup(React.createElement(module.exports.default));
  assert.match(html, /FuturePath AU/);
  assert.match(html, /Profile draft: validation pending/);
  assert.match(html, /Answering is voluntary/);
});
