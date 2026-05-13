'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');
const test = require('node:test');
const assert = require('node:assert/strict');

const {
  parseUserEnvProfileText,
  readUserEnvProfileFromFile,
} = require('../lib/user-env-profile');

test('parse basic KEY=value pairs', () => {
  const { vars, issues } = parseUserEnvProfileText('A=1\nB=two');
  assert.equal(vars.A, '1');
  assert.equal(vars.B, 'two');
  assert.equal(issues.length, 0);
});

test('export prefix and stripping quotes', () => {
  const { vars, issues } = parseUserEnvProfileText(`export Z="quoted"\nQ='single'`);
  assert.equal(vars.Z, 'quoted');
  assert.equal(vars.Q, 'single');
  assert.equal(issues.length, 0);
});

test('duplicate KEY warns last wins', () => {
  const { vars, issues } = parseUserEnvProfileText('A=1\nA=2\n');
  assert.equal(vars.A, '2');
  assert.ok(issues.some(i => i.message.includes('duplicate')));
});

test('invalid KEY name error does not bind', () => {
  const { vars, issues } = parseUserEnvProfileText('1BAD=x');
  assert.equal(vars['1BAD'], undefined);
  assert.ok(issues.some(i => i.level === 'error'));
});

test('bare line warns', () => {
  const { issues } = parseUserEnvProfileText('not-a-pair');
  assert.ok(issues.some(i => i.level === 'warning' && i.message.includes('dotenv')));
});

test('readUserEnvProfileFromFile missing yields missingFile', () => {
  const p = path.join(os.tmpdir(), `sf-env-missing-${Math.random().toString(36).slice(2)}`);
  fs.rmSync(p, { force: true });
  const r = readUserEnvProfileFromFile(p);
  assert.equal(r.missingFile, true);
  assert.deepEqual(r.vars, {});
  assert.deepEqual(r.issues, []);
});

test('readUserEnvProfileFromFile parses file', () => {
  const p = path.join(os.tmpdir(), `sf-env-ok-${Math.random().toString(36).slice(2)}`);
  fs.writeFileSync(p, 'HELLO_CI=world\n', 'utf8');
  try {
    const r = readUserEnvProfileFromFile(p);
    assert.ok(!r.missingFile);
    assert.equal(r.vars.HELLO_CI, 'world');
    assert.equal(r.issues.length, 0);
  } finally {
    fs.unlinkSync(p);
  }
});
