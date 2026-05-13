/**
 * Parses Skillforge ~/.skillforge/env (dotenv-style) for merge + validation.
 * Shell-free: no ${VAR} expansion.
 */
'use strict';

const fs = require('fs');

/**
 * @typedef {{ level: 'error'|'warning', line: number, message: string }} UserEnvIssue
 */
/**
 * @param {string} raw
 * @returns {{ vars: Record<string, string>, issues: UserEnvIssue[] }}
 */
function parseUserEnvProfileText(raw) {
  /** @type {Record<string, string>} */
  const vars = {};
  /** @type {UserEnvIssue[]} */
  const issues = [];

  /** @type {Set<string>} */
  const declared = new Set();

  const lines = raw.split(/\r?\n/);
  const keyOk = /^[A-Za-z_][A-Za-z0-9_]*$/;

  for (let i = 0; i < lines.length; i++) {
    const lineNum = i + 1;
    const rawLine = lines[i];
    const t = rawLine.trim();
    if (!t || t.startsWith('#')) {
      continue;
    }

    let s = t;
    if (s.startsWith('export ')) {
      s = s.slice(7).trim();
    }

    const ix = s.indexOf('=');
    if (ix < 0) {
      issues.push({
        level: 'warning',
        line: lineNum,
        message:
          'line has no "=" — expected KEY=value (dotenv syntax); skipped when loading',
      });
      continue;
    }

    if (ix === 0) {
      issues.push({
        level: 'error',
        line: lineNum,
        message: 'missing variable name before "="',
      });
      continue;
    }

    const k = s.slice(0, ix).trim();
    let v = s.slice(ix + 1).trim();
    if (v.startsWith('"')) {
      if (v.length < 2 || !v.endsWith('"')) {
        issues.push({
          level: 'warning',
          line: lineNum,
          message: 'value starts with " but closing quote missing or malformed',
        });
      }
    } else if (v.startsWith("'")) {
      if (v.length < 2 || !v.endsWith("'")) {
        issues.push({
          level: 'warning',
          line: lineNum,
          message: "value starts with ' but closing quote missing or malformed",
        });
      }
    }

    if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) {
      v = v.slice(1, -1);
    }

    if (!keyOk.test(k)) {
      issues.push({
        level: 'error',
        line: lineNum,
        message:
          `invalid KEY "${k}" — use ASCII letters, digits, underscore (must match [A-Za-z_][A-Za-z0-9_]*)`,
      });
      continue;
    }

    if (declared.has(k)) {
      issues.push({
        level: 'warning',
        line: lineNum,
        message: `duplicate "${k}" — last assignment wins`,
      });
    }
    declared.add(k);
    vars[k] = v;
  }

  return { vars, issues };
}

/**
 * Read and parse ~/.skillforge/env. Missing file ⇒ empty vars & issues only if caller treats missing.
 * @param {string} absPath
 * @returns {{
 *   vars: Record<string, string>,
 *   issues: UserEnvIssue[],
 *   missingFile?: boolean,
 *   readErr?: boolean,
 * }}
 */
function readUserEnvProfileFromFile(absPath) {
  if (!fs.existsSync(absPath)) {
    return { vars: {}, issues: [], missingFile: true };
  }
  let raw;
  try {
    raw = fs.readFileSync(absPath, 'utf8');
  } catch (e) {
    const msg = /** @type {Error} */ (e).message;
    return {
      vars: {},
      issues: [{ level: 'error', line: 0, message: `cannot read ${absPath}: ${msg}` }],
      readErr: true,
    };
  }
  const { vars, issues } = parseUserEnvProfileText(raw);
  return { vars, issues };
}

module.exports = {
  parseUserEnvProfileText,
  readUserEnvProfileFromFile,
};
