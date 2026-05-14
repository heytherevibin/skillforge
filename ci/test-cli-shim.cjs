'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');
const { spawnSync } = require('child_process');
const test = require('node:test');
const assert = require('node:assert/strict');

const repoRoot = path.join(__dirname, '..');
const cliJs = path.join(repoRoot, 'bin', 'cli.js');

test('runToolsCmd forwards argv with args.slice(1)', () => {
  const src = fs.readFileSync(cliJs, 'utf8');
  const m = src.match(/function runToolsCmd\(\) \{[\s\S]*?\n\}/);
  assert.ok(m, 'runToolsCmd not found');
  assert.match(m[0], /const sub = args\.slice\(1\)/);
  assert.ok(!/\bargs\.slice\(2\)/.test(m[0]), 'must not slice(2) in runToolsCmd');
});

test('skillforge mcp config works without venv (no implicit install)', () => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'skillforge-home-'));
  const env = {
    ...process.env,
    HOME: home,
    USERPROFILE: home,
    APPDATA: path.join(home, 'AppData', 'Roaming'),
  };
  const r = spawnSync(process.execPath, [cliJs, 'mcp', 'config'], {
    cwd: repoRoot,
    env,
    encoding: 'utf8',
  });
  assert.equal(r.status, 0, `stderr:\n${r.stderr}`);
  const parsed = JSON.parse(r.stdout.trim());
  assert.ok(parsed.mcpServers?.skillforge, 'expects mcpServers.skillforge');

  assert.ok(fs.existsSync(path.join(home, '.skillforge')), 'creates ~/.skillforge for operator paths');
});

test('skillforge mcp config --companion emits conversation routing env', () => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'skillforge-home-'));
  const env = {
    ...process.env,
    HOME: home,
    USERPROFILE: home,
    APPDATA: path.join(home, 'AppData', 'Roaming'),
  };
  const r = spawnSync(process.execPath, [cliJs, 'mcp', 'config', '--companion'], {
    cwd: repoRoot,
    env,
    encoding: 'utf8',
  });
  assert.equal(r.status, 0, `stderr:\n${r.stderr}`);
  const parsed = JSON.parse(r.stdout.trim());
  const e = parsed.mcpServers.skillforge.env;
  assert.ok(e, 'expects entry.env');
  assert.equal(e.SKILLFORGE_ROUTER_CONV_MAX_TURNS, '6');
  assert.equal(e.SKILLFORGE_ROUTER_CONV_MSG_CHARS, '400');
  assert.equal(e.SKILLFORGE_ROUTER_MODE, 'host');
});

test('skillforge mcp config --with-anthropic --companion merges conversation env', () => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'skillforge-home-'));
  const env = {
    ...process.env,
    HOME: home,
    USERPROFILE: home,
    APPDATA: path.join(home, 'AppData', 'Roaming'),
  };
  const r = spawnSync(process.execPath, [cliJs, 'mcp', 'config', '--with-anthropic', '--companion'], {
    cwd: repoRoot,
    env,
    encoding: 'utf8',
  });
  assert.equal(r.status, 0, `stderr:\n${r.stderr}`);
  const parsed = JSON.parse(r.stdout.trim());
  const e = parsed.mcpServers.skillforge.env;
  assert.equal(e.SKILLFORGE_ROUTER_MODE, 'auto');
  assert.ok(String(e.ANTHROPIC_API_KEY || '').length > 0);
  assert.equal(e.SKILLFORGE_ROUTER_CONV_MAX_TURNS, '6');
});
