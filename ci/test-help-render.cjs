'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');

const pkgRoot = path.join(__dirname, '..');
process.chdir(pkgRoot);

const {
  renderHelp,
  parseHelpOptions,
  applyStyleTags,
  wrapPlain,
} = require('../lib/help-render');

const demoCtx = {
  pkgVersion: '9.9.9',
  configDir: '/tmp/.skillforge',
  npmPkgName: '@example/skillforge',
};

test('wrapPlain joins words until width', () => {
  assert.deepEqual(wrapPlain('alpha beta gamma', 120), ['alpha beta gamma']);
  assert.deepEqual(wrapPlain('abcdefghij', 4), ['abcd', 'efgh', 'ij']);
});

test('applyStyleTags strips tags when color off', () => {
  assert.equal(applyStyleTags('{bold}X{/bold}', false), 'X');
  assert.match(applyStyleTags('{cyan}y{/cyan}', true), /\x1b/);
});

test('parseHelpOptions picks --browse and SKILLFORGE_HELP_UI', t => {
  t.after(() => {
    delete process.env.SKILLFORGE_HELP_UI;
  });
  assert.deepEqual(parseHelpOptions(['help', '--browse']), { ui: false, browse: true });
  process.env.SKILLFORGE_HELP_UI = 'panels';
  assert.deepEqual(parseHelpOptions(['--help']), { ui: true, browse: false });
});

test('renderHelp plain is CI-stable (color off)', () => {
  const txt = renderHelp('plain', demoCtx, {
    columns: 100,
    useUnicode: true,
    color: false,
  });
  assert.match(txt, /\bSkillforge\b/);
  assert.match(txt, /skillforge mcp/);
  assert.match(txt, /@example\/skillforge/, 'manifest name in footer');
  assert.ok(!/\x1b\[/.test(txt), 'plain help should omit ANSI escapes when color:false');
});

test('renderHelp panels uses box drawing when unicode on', () => {
  const txt = renderHelp('panels', demoCtx, {
    columns: 100,
    useUnicode: true,
    color: false,
  });
  assert.match(txt, /┌[^\n]*Model Context Protocol[^\n]*┐/, 'boxed section title');
  assert.match(txt, /│[^\n]*skillforge mcp/);
});

test('renderHelp panels uses ASCII fences on Windows-ish unicode=false', () => {
  const txt = renderHelp('panels', demoCtx, {
    columns: 100,
    useUnicode: false,
    color: false,
  });
  const firstBox = txt.split('\n').find(l => l.includes('Model Context Protocol') && l.startsWith('+'));
  assert.ok(firstBox, `expected boxed MCP title line, sample:\n${txt.slice(0, 240)}`);
  assert.ok(txt.includes('|'));
});
