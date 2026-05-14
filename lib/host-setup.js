/**
 * Detect MCP-friendly editors and install global slash-command files (Cursor, Claude Code).
 */
const fs = require('fs');
const path = require('path');
const os = require('os');
const { spawnSync } = require('child_process');

const MANAGED_SUBSTRING = 'skillforge-managed';

/** @typedef {'all' | 'cursor' | 'claude-code'} HostScope */

/**
 * Parse host integration scope from CLI args (after `node`/`skillforge`), e.g. ["install","--force-cursor"].
 * **`--force-cursor`** → Cursor-only + overwrite managed **`~/.cursor/commands/skillforge.md`** (skips Claude Code).
 * **`--force-claude-code`** / **`--force-claude`** → Claude Code–only + overwrite **`~/.claude/commands/skillforge.md`** (skips Cursor).
 * **Both** Cursor and Claude **`--force-*`** flags → **`hosts=all`** + **`force`** (refresh both).
 *
 * @param {string[]} cliArgs
 * @returns {{ hostScope: HostScope, force: boolean }}
 */
function resolveHostInstallScope(cliArgs) {
  const has = /** @param {string} f */ f => cliArgs.includes(f);
  /** @type {HostScope} */
  let hostScope = 'all';

  const hostsEq = cliArgs.find(a => String(a).startsWith('--hosts='));
  if (hostsEq) {
    const v = String(hostsEq)
      .slice('--hosts='.length)
      .trim()
      .toLowerCase();
    if (v === 'cursor') hostScope = 'cursor';
    else if (v === 'claude-code' || v === 'claude') hostScope = 'claude-code';
    else if (v === 'all') hostScope = 'all';
  } else {
    const fc = has('--force-cursor');
    const fcClaude = has('--force-claude-code') || has('--force-claude');
    if (fc && fcClaude) {
      hostScope = 'all';
    } else if (fc) {
      hostScope = 'cursor';
    } else if (fcClaude) {
      hostScope = 'claude-code';
    } else if (has('--only-cursor') && has('--only-claude-code')) {
      hostScope = 'all';
    } else if (has('--only-cursor')) {
      hostScope = 'cursor';
    } else if (has('--only-claude-code')) {
      hostScope = 'claude-code';
    }
  }

  const force =
    has('--force') ||
    has('--force-cursor') ||
    has('--force-claude-code') ||
    has('--force-claude');

  return { hostScope, force };
}

/** @returns {string} */
function homeDir() {
  return os.homedir();
}

/** @returns {string} */
function claudeConfigBase() {
  const override = process.env.CLAUDE_CONFIG_DIR;
  if (override && String(override).trim()) {
    return String(override).trim();
  }
  return path.join(homeDir(), '.claude');
}

function claudeCliOnPath() {
  try {
    const isWin = process.platform === 'win32';
    const bin = isWin ? 'where' : 'which';
    const r = spawnSync(bin, ['claude'], { encoding: 'utf8', stdio: 'pipe', timeout: 4000 });
    return r.status === 0;
  } catch {
    return false;
  }
}

/**
 * @returns {{ id: string, label: string, detail: string }[]}
 */
function detectMcpFriendlyHosts() {
  const h = homeDir();
  /** @type {{ id: string, label: string, detail: string }[]} */
  const out = [];

  const cursorDir = path.join(h, '.cursor');
  if (fs.existsSync(cursorDir)) {
    out.push({
      id: 'cursor',
      label: 'Cursor',
      detail: `~/.cursor (mcp.json, commands/)`,
    });
  }

  const claudeJson = path.join(h, '.claude.json');
  const ccSettings = path.join(claudeConfigBase(), 'settings.json');
  if (fs.existsSync(claudeJson) || fs.existsSync(ccSettings) || claudeCliOnPath()) {
    out.push({
      id: 'claude-code',
      label: 'Claude Code',
      detail: fs.existsSync(claudeJson)
        ? '~/.claude.json + ~/.claude/'
        : '~/.claude/ (add MCP via claude mcp or .mcp.json)',
    });
  }

  if (process.platform === 'darwin') {
    const claude = path.join(h, 'Library', 'Application Support', 'Claude', 'claude_desktop_config.json');
    if (fs.existsSync(claude)) {
      out.push({
        id: 'claude-desktop',
        label: 'Claude Desktop',
        detail: '~/Library/Application Support/Claude/',
      });
    }
    const cursorApp = path.join('/Applications', 'Cursor.app');
    const cursorAppUser = path.join(h, 'Applications', 'Cursor.app');
    if (fs.existsSync(cursorApp) || fs.existsSync(cursorAppUser)) {
      if (!out.some(x => x.id === 'cursor' || x.id === 'cursor-app')) {
        out.push({
          id: 'cursor-app',
          label: 'Cursor (app)',
          detail: 'Cursor.app installed — use Cursor MCP settings if ~/.cursor is missing',
        });
      }
    }
  } else if (process.platform === 'win32') {
    const appData = process.env.APPDATA || path.join(h, 'AppData', 'Roaming');
    const claudeWin = path.join(appData, 'Claude', 'claude_desktop_config.json');
    if (fs.existsSync(claudeWin)) {
      out.push({
        id: 'claude-desktop',
        label: 'Claude Desktop',
        detail: path.join(appData, 'Claude'),
      });
    }
  }

  return out;
}

/**
 * @returns {boolean}
 */
function looksLikeCursorEnvironment() {
  const h = homeDir();
  if (fs.existsSync(path.join(h, '.cursor'))) return true;
  if (process.platform === 'darwin') {
    if (fs.existsSync(path.join('/Applications', 'Cursor.app'))) return true;
    if (fs.existsSync(path.join(h, 'Applications', 'Cursor.app'))) return true;
  }
  if (process.env.SKILLFORGE_CURSOR_GLOBAL_COMMAND === '1' || process.env.SKILLFORGE_CURSOR_GLOBAL_COMMAND === 'true') {
    return true;
  }
  return false;
}

/**
 * @returns {boolean}
 */
function looksLikeClaudeCodeEnvironment() {
  const h = homeDir();
  if (fs.existsSync(path.join(h, '.claude.json'))) return true;
  const base = claudeConfigBase();
  if (fs.existsSync(path.join(base, 'settings.json'))) return true;
  if (claudeCliOnPath()) return true;
  if (process.env.SKILLFORGE_CLAUDE_CODE_GLOBAL_COMMAND === '1' || process.env.SKILLFORGE_CLAUDE_CODE_GLOBAL_COMMAND === 'true') {
    return true;
  }
  return false;
}

/**
 * @param {{ force?: boolean, log?: (msg: string) => void, err?: (msg: string) => void, pkgRoot: string, pkgVersion: string }} opts
 * @returns {{ wrote: boolean, path: string | null, skippedReason: string | null }}
 */
function installGlobalCursorSkillforgeCommand(opts) {
  const log = opts.log || (() => {});
  const errFn = opts.err || log;
  const force = !!opts.force;
  const skip = process.env.SKILLFORGE_SKIP_CURSOR_SETUP === '1' || process.env.SKILLFORGE_SKIP_CURSOR_SETUP === 'true';
  if (skip) {
    return { wrote: false, path: null, skippedReason: 'SKILLFORGE_SKIP_CURSOR_SETUP' };
  }

  if (!looksLikeCursorEnvironment()) {
    return { wrote: false, path: null, skippedReason: 'cursor_not_detected' };
  }

  const cmdDir = path.join(homeDir(), '.cursor', 'commands');
  const cmdFile = path.join(cmdDir, 'skillforge.md');

  try {
    if (fs.existsSync(cmdFile) && !force) {
      const prev = fs.readFileSync(cmdFile, 'utf8');
      if (!prev.includes(MANAGED_SUBSTRING)) {
        log(
          `Cursor: left ${cmdFile} unchanged (custom file; not skillforge-managed). Replace with: skillforge hosts init --force`
        );
        return { wrote: false, path: cmdFile, skippedReason: 'custom_file' };
      }
    }

    const tplPath = path.join(opts.pkgRoot, 'lib', 'templates', 'cursor-skillforge-global.md');
    if (!fs.existsSync(tplPath)) {
      errFn(`Cursor: template missing at ${tplPath}`);
      return { wrote: false, path: null, skippedReason: 'no_template' };
    }
    let body = fs.readFileSync(tplPath, 'utf8');
    body = body.replace(/PACKAGE_VERSION/g, opts.pkgVersion);

    fs.mkdirSync(cmdDir, { recursive: true });
    fs.writeFileSync(cmdFile, body, 'utf8');
    return { wrote: true, path: cmdFile, skippedReason: null };
  } catch (e) {
    errFn(`Cursor: could not write ${cmdFile}: ${/** @type {Error} */ (e).message}`);
    return { wrote: false, path: cmdFile, skippedReason: 'write_error' };
  }
}

/**
 * @param {{ force?: boolean, log?: (msg: string) => void, err?: (msg: string) => void, pkgRoot: string, pkgVersion: string }} opts
 * @returns {{ wrote: boolean, path: string | null, skippedReason: string | null }}
 */
function installGlobalClaudeCodeSkillforgeCommand(opts) {
  const log = opts.log || (() => {});
  const errFn = opts.err || log;
  const force = !!opts.force;
  const skip = process.env.SKILLFORGE_SKIP_CLAUDE_CODE_SETUP === '1' || process.env.SKILLFORGE_SKIP_CLAUDE_CODE_SETUP === 'true';
  if (skip) {
    return { wrote: false, path: null, skippedReason: 'SKILLFORGE_SKIP_CLAUDE_CODE_SETUP' };
  }

  if (!looksLikeClaudeCodeEnvironment()) {
    return { wrote: false, path: null, skippedReason: 'claude_code_not_detected' };
  }

  const base = claudeConfigBase();
  const cmdDir = path.join(base, 'commands');
  const cmdFile = path.join(cmdDir, 'skillforge.md');

  try {
    if (fs.existsSync(cmdFile) && !force) {
      const prev = fs.readFileSync(cmdFile, 'utf8');
      if (!prev.includes(MANAGED_SUBSTRING)) {
        log(
          `Claude Code: left ${cmdFile} unchanged (custom file; not skillforge-managed). Replace with: skillforge hosts init --force`
        );
        return { wrote: false, path: cmdFile, skippedReason: 'custom_file' };
      }
    }

    const tplPath = path.join(opts.pkgRoot, 'lib', 'templates', 'claude-code-skillforge-global.md');
    if (!fs.existsSync(tplPath)) {
      errFn(`Claude Code: template missing at ${tplPath}`);
      return { wrote: false, path: null, skippedReason: 'no_template' };
    }
    let body = fs.readFileSync(tplPath, 'utf8');
    body = body.replace(/PACKAGE_VERSION/g, opts.pkgVersion);

    fs.mkdirSync(cmdDir, { recursive: true });
    fs.writeFileSync(cmdFile, body, 'utf8');
    return { wrote: true, path: cmdFile, skippedReason: null };
  } catch (e) {
    errFn(`Claude Code: could not write ${cmdFile}: ${/** @type {Error} */ (e).message}`);
    return { wrote: false, path: cmdFile, skippedReason: 'write_error' };
  }
}

/**
 * @param {{ force?: boolean, log?: typeof console.error, ok?: typeof console.error, err?: typeof console.error, dim?: (s: string) => void, pkgRoot: string, pkgVersion: string }} opts
 */
function reportHostsAndInstallAgentCommands(opts) {
  const log = opts.log || console.error;
  const ok = opts.ok || console.error;
  const errLine = opts.err || log;
  const dim =
    opts.dim ||
    ((s) => {
      console.error(s);
    });

  /** @type {HostScope} */
  const hostScope = opts.hostScope ?? 'all';
  const wantCursor = hostScope === 'all' || hostScope === 'cursor';
  const wantClaudeCode = hostScope === 'all' || hostScope === 'claude-code';

  const hosts = detectMcpFriendlyHosts();
  if (hosts.length > 0) {
    log('');
    ok(`Detected MCP-friendly environment(s): ${hosts.map(h => h.label).join(', ')}`);
    hosts.forEach(h => dim(`  • ${h.label}: ${h.detail}`));
  }
  if (hosts.some(h => h.id === 'claude-desktop')) {
    dim('  Tip (Claude Desktop): merge `skillforge mcp config` into claude_desktop_config.json');
  }
  if (hosts.some(h => h.id === 'claude-code')) {
    dim(
      '  Tip (Claude Code): add skillforge MCP (`skillforge mcp config`, project `.mcp.json`, or `claude mcp`). Global `/skillforge` → ~/.claude/commands/skillforge.md'
    );
  }

  const rCur = wantCursor
    ? installGlobalCursorSkillforgeCommand({
        force: opts.force,
        log,
        err: errLine,
        pkgRoot: opts.pkgRoot,
        pkgVersion: opts.pkgVersion,
      })
    : { wrote: false, path: null, skippedReason: 'host_scope' };

  const rCc = wantClaudeCode
    ? installGlobalClaudeCodeSkillforgeCommand({
        force: opts.force,
        log,
        err: errLine,
        pkgRoot: opts.pkgRoot,
        pkgVersion: opts.pkgVersion,
      })
    : { wrote: false, path: null, skippedReason: 'host_scope' };

  if (hostScope === 'cursor') {
    dim(
      'Skipping Claude Code /skillforge install (cursor-only scope). For both hosts: omit --force-cursor or use `--hosts=all`. Env: SKILLFORGE_SKIP_CLAUDE_CODE_SETUP=1 for future runs.',
    );
  }
  if (hostScope === 'claude-code') {
    dim('Skipping Cursor /skillforge install (claude-code-only scope). Env: SKILLFORGE_SKIP_CURSOR_SETUP=1 for future runs.');
  }
  if (rCur.skippedReason === 'cursor_not_detected') {
    dim('');
    dim(
      'Cursor: ~/.cursor not found. For global /skillforge: SKILLFORGE_CURSOR_GLOBAL_COMMAND=1 skillforge install  (or skillforge hosts init)'
    );
  } else if (rCur.skippedReason === 'SKILLFORGE_SKIP_CURSOR_SETUP') {
    dim('Cursor integration skipped (SKILLFORGE_SKIP_CURSOR_SETUP).');
  }
  if (rCur.wrote && rCur.path) {
    ok(`Wrote Cursor command: ${rCur.path} (use /skillforge in chat)`);
  }

  if (rCc.skippedReason === 'claude_code_not_detected') {
    dim('');
    dim(
      'Claude Code not detected (~/.claude.json, ~/.claude/settings.json, or `claude` on PATH). For global /skillforge: SKILLFORGE_CLAUDE_CODE_GLOBAL_COMMAND=1 skillforge install  (or skillforge hosts init)'
    );
  } else if (rCc.skippedReason === 'SKILLFORGE_SKIP_CLAUDE_CODE_SETUP') {
    dim('Claude Code integration skipped (SKILLFORGE_SKIP_CLAUDE_CODE_SETUP).');
  }
  if (rCc.wrote && rCc.path) {
    ok(`Wrote Claude Code command/skill: ${rCc.path} (use /skillforge in Terminal/IDE)`);
  }
}

/** @deprecated use reportHostsAndInstallAgentCommands */
function reportHostsAndInstallCursorCommand(opts) {
  reportHostsAndInstallAgentCommands(opts);
}

module.exports = {
  detectMcpFriendlyHosts,
  claudeConfigBase,
  looksLikeCursorEnvironment,
  looksLikeClaudeCodeEnvironment,
  installGlobalCursorSkillforgeCommand,
  installGlobalClaudeCodeSkillforgeCommand,
  resolveHostInstallScope,
  reportHostsAndInstallAgentCommands,
  reportHostsAndInstallCursorCommand,
  MANAGED_SUBSTRING,
};
