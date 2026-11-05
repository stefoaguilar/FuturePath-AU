import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { runInNewContext } from 'node:vm';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { buildSync } from 'esbuild';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const code = buildSync({
  entryPoints: [fileURLToPath(new URL('../../src/App.jsx', import.meta.url))],
  bundle: true, write: false, format: 'cjs', platform: 'node', external: ['react']
}).outputFiles[0].text;

// Dataset/eligibility regressions inspect the full list through the public UI.
export function loadAllOpportunities(ui) {
  let button;
  while ((button = ui.nodes().find((node) => node.type === 'button' && ui.text(node) === 'Load More Opportunities'))) {
    button.props.onClick();
    ui.render();
  }
}

export function renderInitialApp(props = {}) {
  const module = { exports: {} };
  runInNewContext(code, { module, exports: module.exports, require, URL });
  return renderToStaticMarkup(React.createElement(module.exports.default, props));
}

// Run the actual component handlers against a small state harness without adding
// a browser/test dependency. The SSR check below also uses real React hooks.
export function harness({ fetchImpl = async () => { throw new Error('Offline test'); }, appProps = {}, timers = { setTimeout, clearTimeout }, confirmImpl = () => true, alertImpl = () => {}, dateImpl = Date } = {}) {
  const state = [];
  let cursor = 0;
  let tree;
  let activeProfile;
  let effects = [];
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
    useRef(initial) {
      const index = cursor++;
      if (!(index in state)) state[index] = { current: initial };
      return state[index];
    },
    useEffect(callback) { effects.push(callback); }
  };
  const module = { exports: {} };
  runInNewContext(code, {
    module, exports: module.exports,
    require: (name) => name === 'react' ? hooks : require(name),
    fetch: fetchImpl,
    URL, AbortController, Date: dateImpl, setTimeout: timers.setTimeout, clearTimeout: timers.clearTimeout,
    console: { warn() {} },
    window: { confirm: confirmImpl, alert: alertImpl },
    document: { getElementById: () => null }
  });
  const render = () => { cursor = 0; effects = []; tree = module.exports.default(appProps); };
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
    setProps: (props) => { appProps = props; render(); },
    runEffects: () => {
      const cleanups = effects.map((callback) => callback());
      return () => cleanups.forEach((cleanup) => cleanup?.());
    },
    profile: () => JSON.parse(JSON.stringify(activeProfile)),
    hasStateValue: (value) => state.includes(value),
    markup: () => text(tree)
  };
}

