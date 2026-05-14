'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { resolveHostInstallScope } = require('../lib/host-setup');

test('defaults: all hosts, no force', () => {
  const r = resolveHostInstallScope(['install']);
  assert.equal(r.hostScope, 'all');
  assert.equal(r.force, false);
});

test('--force-cursor: cursor only + force', () => {
  const r = resolveHostInstallScope(['install', '--force-cursor']);
  assert.equal(r.hostScope, 'cursor');
  assert.equal(r.force, true);
});

test('--force-claude: claude-code only + force', () => {
  const r = resolveHostInstallScope(['install', '--force-claude']);
  assert.equal(r.hostScope, 'claude-code');
  assert.equal(r.force, true);
});

test('--force-claude-code: same scope', () => {
  const r = resolveHostInstallScope(['install', '--force-claude-code']);
  assert.equal(r.hostScope, 'claude-code');
  assert.equal(r.force, true);
});

test('--force-cursor and --force-claude: all hosts + force', () => {
  const r = resolveHostInstallScope(['install', '--force-cursor', '--force-claude']);
  assert.equal(r.hostScope, 'all');
  assert.equal(r.force, true);
});

test('--hosts=cursor overrides', () => {
  const r = resolveHostInstallScope(['hosts', 'init', '--hosts=cursor']);
  assert.equal(r.hostScope, 'cursor');
});

test('--only-cursor without force', () => {
  const r = resolveHostInstallScope(['install', '--only-cursor']);
  assert.equal(r.hostScope, 'cursor');
  assert.equal(r.force, false);
});

test('--hosts=all explicit', () => {
  const r = resolveHostInstallScope(['install', '--hosts=all', '--force']);
  assert.equal(r.hostScope, 'all');
  assert.equal(r.force, true);
});
