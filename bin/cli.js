#!/usr/bin/env node
/**
 * skillforge — skill orchestrator co-tool for Claude (MCP-first)
 *
 * Usage:
 *   skillforge, skillforge --help   Show help (primary path: MCP, not a web app)
 *   skillforge mcp                   MCP stdio server (Claude / Cursor / …)
 *   skillforge events [--watch] [--limit=N]     Print SQLite routing events
 *   skillforge replay [--session-id]             Chronological SQLite event replay
 *   skillforge tools <cmd> [--json]               MCP tool parity (see skillforge tools -h)
 *   skillforge tips                             Short MCP + terminal cheatsheet
 *   skillforge agent [--prompt=…]              Terminal chat agent (OpenAI-compatible API tools)
 *   skillforge route [words…] [--prompt=…]     Same routing as MCP route_skills (terminal)
 *   skillforge index --project-root=…            Chunk/embed repo files for project RAG
 *   skillforge health [--quick] [--json]         Preflight: paths, catalog, optional router load
 *   skillforge route-eval --fixture=…            Embedding-only regression cases (CI-friendly)
 *   skillforge weights export|import             Snapshot learned weights (JSON)
 *   skillforge install               One-time Python venv + deps (+ Cursor /skillforge when detected)
 *   skillforge config path|init|validate …  ~/.skillforge/env (dotenv-style profile + linter)
 *   skillforge hosts init [--force]  Install global /skillforge for Cursor + Claude Code (no Python setup)
 *   skillforge cursor init [--force]  Same as hosts init (alias)
 *   skillforge skills list|add|remove|init|lint … ; pack … ; reset
 */

const path = require('path');
const fs = require('fs');
const { spawn, spawnSync } = require('child_process');
const os = require('os');
const packs = require('../lib/packs');
const userEnvProfile = require('../lib/user-env-profile');

const PKG_ROOT = path.resolve(__dirname, '..');
const PKG = require(path.join(PKG_ROOT, 'package.json'));
const NPM_PKG_NAME = PKG.name;
const PKG_VERSION = PKG.version || '0.0.0';
const CONFIG_DIR = path.join(os.homedir(), '.skillforge');
const VENV_DIR = path.join(CONFIG_DIR, 'venv');
const DATA_DIR = path.join(CONFIG_DIR, 'data');
const USER_SKILLS_DIR = path.join(CONFIG_DIR, 'skills');
/** Bearer-token file for the removed HTTP API (<=0.6.x); deleted on first CLI use. */
const LEGACY_AUTH_FILE = path.join(CONFIG_DIR, 'auth.json');
const SETUP_MARKER = path.join(CONFIG_DIR, '.setup-complete');
/** User-owned KEY=VALUE profile (merged before process.env — shell / MCP host overrides). */
const USER_ENV_PATH = path.join(CONFIG_DIR, 'env');

const args = process.argv.slice(2);
const cmd = args[0];

// ---- styling ----
const c = {
  dim: (s) => `\x1b[2m${s}\x1b[0m`,
  bold: (s) => `\x1b[1m${s}\x1b[0m`,
  green: (s) => `\x1b[32m${s}\x1b[0m`,
  red: (s) => `\x1b[31m${s}\x1b[0m`,
  yellow: (s) => `\x1b[33m${s}\x1b[0m`,
  cyan: (s) => `\x1b[36m${s}\x1b[0m`,
};

function log(...m) { console.error(...m); }
function err(...m) { console.error(c.red('✗'), ...m); }
function ok(...m) { console.error(c.green('✓'), ...m); }
function info(...m) { console.error(c.cyan('▸'), ...m); }

// ---- platform helpers ----
function isWindows() { return process.platform === 'win32'; }
function venvPython() {
  return isWindows()
    ? path.join(VENV_DIR, 'Scripts', 'python.exe')
    : path.join(VENV_DIR, 'bin', 'python');
}
function venvPip() {
  return isWindows()
    ? path.join(VENV_DIR, 'Scripts', 'pip.exe')
    : path.join(VENV_DIR, 'bin', 'pip');
}

function findSystemPython() {
  // Try a few candidates in preference order
  const candidates = isWindows()
    ? ['python', 'python3', 'py']
    : ['python3.12', 'python3.11', 'python3.10', 'python3', 'python'];
  for (const c of candidates) {
    const r = spawnSync(c, ['--version'], { stdio: 'pipe' });
    if (r.status === 0) {
      const ver = (r.stdout.toString() + r.stderr.toString()).trim();
      // require Python 3.10+
      const m = ver.match(/Python (\d+)\.(\d+)/);
      if (m && (parseInt(m[1]) > 3 || (parseInt(m[1]) === 3 && parseInt(m[2]) >= 10))) {
        return { bin: c, version: ver };
      }
    }
  }
  return null;
}

// ---- setup ----
function ensureDirs() {
  for (const d of [CONFIG_DIR, DATA_DIR, USER_SKILLS_DIR]) {
    fs.mkdirSync(d, { recursive: true });
  }
}

/** v0.7.0 removed HTTP + `skillforge auth`; leftover tokens file is misleading — remove once. */
function dropLegacyAuthJsonIfPresent() {
  try {
    if (fs.existsSync(LEGACY_AUTH_FILE)) {
      fs.rmSync(LEGACY_AUTH_FILE);
      info('Removed legacy ~/.skillforge/auth.json (HTTP API was removed in v0.7).');
    }
  } catch (e) {
    err(`Could not remove legacy auth.json: ${e.message}`);
  }
}

function runSetup() {
  info('First-time setup — this happens once and takes ~2 minutes');
  ensureDirs();

  // 1. Find Python
  const py = findSystemPython();
  if (!py) {
    err('Python 3.10+ not found on your system.');
    log(c.dim('  Install Python from https://www.python.org/ and re-run.'));
    process.exit(1);
  }
  ok(`Found ${py.version}`);

  // 2. Create venv (never write child's stdout to process.stdout — MCP needs a clean JSON-RPC stream)
  if (!fs.existsSync(venvPython())) {
    info('Creating Python virtual environment...');
    const r = spawnSync(py.bin, ['-m', 'venv', VENV_DIR], {
      encoding: 'utf8',
      stdio: ['inherit', 'pipe', 'pipe'],
    });
    if (r.stdout) process.stderr.write(r.stdout);
    if (r.stderr) process.stderr.write(r.stderr);
    if (r.status !== 0) {
      err('Failed to create venv.');
      process.exit(1);
    }
    ok('Virtualenv created');
  } else {
    ok('Virtualenv already exists');
  }

  // 3. Install Python deps
  info('Installing Python dependencies (this is the slow part)...');
  const reqFile = path.join(PKG_ROOT, 'python', 'requirements.txt');
  const pipR = spawnSync(venvPip(), ['install', '--upgrade', '--quiet', '-r', reqFile], {
    encoding: 'utf8',
    stdio: ['inherit', 'pipe', 'pipe'],
  });
  if (pipR.stdout) process.stderr.write(pipR.stdout);
  if (pipR.stderr) process.stderr.write(pipR.stderr);
  if (pipR.status !== 0) {
    err('Failed to install Python dependencies.');
    process.exit(1);
  }
  ok('Python dependencies installed');

  // 4. Cursor / MCP host hooks (no Python required)
  try {
    const hostSetup = require('../lib/host-setup');
    hostSetup.reportHostsAndInstallAgentCommands({
      force: process.argv.includes('--force-cursor'),
      pkgRoot: PKG_ROOT,
      pkgVersion: PKG_VERSION,
      log,
      ok,
      err,
      dim: s => log(c.dim(s)),
    });
  } catch (e) {
    err(`Host integration failed: ${/** @type {Error} */ (e).message}`);
  }

  // 5. Mark setup complete
  fs.writeFileSync(SETUP_MARKER, new Date().toISOString());
  ok('Setup complete\n');
}

function setupIfNeeded() {
  ensureDirs();
  if (!fs.existsSync(SETUP_MARKER) || !fs.existsSync(venvPython())) {
    runSetup();
  }
}

function buildEnv(extra = {}) {
  const { vars: profile } = userEnvProfile.readUserEnvProfileFromFile(USER_ENV_PATH);
  return {
    ...profile,
    ...process.env,
    SKILLFORGE_BUNDLED_SKILLS: path.join(PKG_ROOT, 'skills'),
    SKILLFORGE_USER_SKILLS: USER_SKILLS_DIR,
    SKILLFORGE_DB_PATH: path.join(DATA_DIR, 'orchestrator.db'),
    PYTHONPATH: path.join(PKG_ROOT, 'python'),
    PYTHONUNBUFFERED: '1',
    ...extra,
  };
}

function printUserEnvProfilePathLine() {
  process.stdout.write(USER_ENV_PATH + '\n');
}

function runInitUserEnv(templateForce) {
  ensureDirs();
  if (fs.existsSync(USER_ENV_PATH) && !templateForce) {
    err(`${USER_ENV_PATH} already exists.`);
    log(c.dim('  Use --force to replace it with the template (you will lose current contents).'));
    process.exit(1);
  }
  const template =
    '# Skillforge user environment profile (~/.skillforge/env).\n' +
    '# Loaded for every Skillforge subprocess (CLI and `skillforge mcp`).\n' +
    '# Merge order: entries here first, then process/MCP host env overwrites duplicates; SKILLFORGE_BUNDLED_SKILLS,\n' +
    '# SKILLFORGE_USER_SKILLS, SKILLFORGE_DB_PATH, and PYTHONPATH are always finalized by Skillforge.\n' +
    '# Omit secrets from VCS; chmod 600 is recommended.\n#\n' +
    '# Examples (uncomment and set):\n' +
    '# ANTHROPIC_API_KEY=\n' +
    '# SKILLFORGE_ROUTER_MODE=host\n' +
    '# OPENAI_API_BASE=http://127.0.0.1:11434/v1\n' +
    '# SKILLFORGE_ROUTER_LLM_BACKEND=openai_compatible\n' +
    '# SKILLFORGE_AGENT_MODEL=llama3.2\n' +
    '\n';
  fs.writeFileSync(USER_ENV_PATH, template, 'utf8');
  if (!isWindows()) {
    try {
      fs.chmodSync(USER_ENV_PATH, 0o600);
    } catch (_) {
      /* chmod optional */
    }
  }
  ok(`Wrote commented template:\n${c.dim(`  ${USER_ENV_PATH}`)}`);
}

function runValidateEnvProfileCmd() {
  const r = userEnvProfile.readUserEnvProfileFromFile(USER_ENV_PATH);
  if (r.missingFile) {
    info('Optional profile file not created yet.');
    log(c.dim(`  Path: ${USER_ENV_PATH}`));
    log(c.dim('  scaffold: skillforge config init'));
    process.exit(0);
  }

  let nErr = 0;
  let nWarn = 0;
  for (const issue of r.issues) {
    const loc = issue.line ? ` ${c.dim(`(line ${issue.line})`)}` : '';
    if (issue.level === 'error') {
      nErr += 1;
      err(`${issue.message}${loc}`);
    } else {
      nWarn += 1;
      log(c.yellow('⚠'), `${issue.message}${loc}`);
    }
  }

  if (nErr === 0 && nWarn === 0) {
    ok(`Profile syntax OK — ${USER_ENV_PATH}`);
    process.exit(0);
  }
  if (nErr === 0) {
    ok(`Validated — ${nWarn} warning(s) only.`);
    process.exit(0);
  }
  log(c.dim(`  Correct ${USER_ENV_PATH}, then run skillforge config validate again.`));
  process.exit(1);
}

function runConfigCmd() {
  const sub = args[1];
  if (
    sub === undefined ||
    sub === '--help' ||
    sub === '-h'
  ) {
    log(c.bold('Usage'));
    log(c.dim('  skillforge config path'));
    log(c.dim('  skillforge config init [--force]'));
    log(c.dim('  skillforge config validate\n'));
    log(c.bold('Description'));
    log(
      c.dim(
        '  path      Print ~/.skillforge/env (dotenv KEY=value; optional export; # comments).\n' +
          '  init      Create a commented template (--force replaces an existing profile).\n' +
          '  validate  Lint the profile — errors exit 1; missing file exits 0 (optional).',
      ),
    );
    process.exit(sub === undefined ? 1 : 0);
  }
  if (sub === 'path') {
    printUserEnvProfilePathLine();
    return;
  }
  if (sub === 'init') {
    const templateForce =
      args.includes('--force');
    runInitUserEnv(templateForce);
    log(c.dim('  Run skillforge config validate after editing.'));
    return;
  }
  if (sub === 'validate') {
    runValidateEnvProfileCmd();
    return;
  }
  err(`Unknown config subcommand: ${sub}`);
  log(c.dim('  Try: path, init, validate'));
  process.exit(1);
}

function printMcpConfig() {
  setupIfNeeded();
  const useLocal = args.includes('--local');
  const withKey = args.includes('--with-anthropic');
  const withEnv = args.includes('--with-env');
  const cliJs = path.join(PKG_ROOT, 'bin', 'cli.js');
  /** @type {Record<string, unknown>} */
  const entry = useLocal
    ? {
        command: process.execPath,
        args: [cliJs, 'mcp'],
      }
    : {
        command: 'npx',
        args: ['-y', NPM_PKG_NAME, 'mcp'],
      };
  if (withKey) {
    entry.env = {
      SKILLFORGE_ROUTER_MODE: 'auto',
      ANTHROPIC_API_KEY: 'sk-ant-…',
    };
  } else if (withEnv) {
    entry.env = {
      SKILLFORGE_ROUTER_MODE: 'host',
    };
  }
  const out = { mcpServers: { skillforge: entry } };
  process.stdout.write(JSON.stringify(out, null, 2) + '\n');
  let note =
    'Merge into ~/.cursor/mcp.json, Claude Desktop config, etc. --local uses this package checkout. ' +
    'Routing: default host (two-step picked_names); --with-anthropic ⇒ SKILLFORGE_ROUTER_MODE=auto plus ANTHROPIC_API_KEY placeholder. ' +
    '--with-env adds server.env SKILLFORGE_ROUTER_MODE=host explicitly (combine with ~/.skillforge/env for secrets).';
  if (withKey && withEnv) {
    note += ' When both --with-env and --with-anthropic are passed, the emitted env matches --with-anthropic only.';
  }
  process.stderr.write(c.dim(`${note}\n`));
}

function runMcpServer() {
  setupIfNeeded();
  const env = buildEnv({
    SKILLFORGE_TRANSPORT: 'mcp',
  });
  // MCP JSON-RPC must own stdout. This process must not log to stdout after this point.
  const proc = spawn(venvPython(), ['-m', 'app.mcp_server'], {
    stdio: ['inherit', 'inherit', 'inherit'],
    env,
  });
  proc.on('exit', (code) => process.exit(code || 0));
  process.on('SIGINT', () => proc.kill('SIGINT'));
  process.on('SIGTERM', () => proc.kill('SIGTERM'));
}

function runEventsCmd() {
  setupIfNeeded();
  const sub = args.slice(1);
  const proc = spawn(venvPython(), ['-m', 'app.events_cli', ...sub], {
    stdio: 'inherit',
    env: buildEnv(),
  });
  proc.on('exit', (code) => process.exit(code ?? 0));
}

function runReplayCmd() {
  setupIfNeeded();
  const sub = args.slice(1);
  const proc = spawn(venvPython(), ['-m', 'app.replay_cli', ...sub], {
    stdio: 'inherit',
    env: buildEnv(),
  });
  proc.on('exit', (code) => process.exit(code ?? 0));
}

function runTipsCmd() {
  setupIfNeeded();
  const proc = spawn(venvPython(), ['-m', 'app.tips_cli'], {
    stdio: 'inherit',
    env: buildEnv(),
  });
  proc.on('exit', (code) => process.exit(code ?? 0));
}

function runToolsCmd() {
  setupIfNeeded();
  const sub = args.slice(2);
  const proc = spawn(venvPython(), ['-m', 'app.tools_cli', ...sub], {
    stdio: 'inherit',
    env: buildEnv(),
  });
  proc.on('exit', (code) => process.exit(code ?? 0));
}

function runAgentCmd() {
  setupIfNeeded();
  // args = argv after 'skillforge' — ["agent", ...], same pattern as route (slice after subcommand).
  const sub = args.slice(1);
  const proc = spawn(venvPython(), ['-m', 'app.agent_cli', ...sub], {
    stdio: 'inherit',
    env: buildEnv(),
  });
  proc.on('exit', (code) => process.exit(code ?? 0));
}

function runSkillsAuthorCmd(mode, argv) {
  setupIfNeeded();
  const proc = spawn(venvPython(), ['-m', 'app.skills_author_cli', mode, ...argv], {
    stdio: 'inherit',
    env: buildEnv(),
  });
  proc.on('exit', (code) => process.exit(code ?? 0));
}

function runRouteCmd() {
  setupIfNeeded();
  const sub = args.slice(1);
  const proc = spawn(venvPython(), ['-m', 'app.route_cli', ...sub], {
    stdio: 'inherit',
    env: buildEnv(),
  });
  proc.on('exit', (code) => process.exit(code ?? 0));
}

function runIndexCmd() {
  setupIfNeeded();
  const sub = args.slice(1);
  const proc = spawn(venvPython(), ['-m', 'app.index_cli', ...sub], {
    stdio: 'inherit',
    env: buildEnv(),
  });
  proc.on('exit', (code) => process.exit(code ?? 0));
}

function runHealthCmd() {
  setupIfNeeded();
  const sub = args.slice(1);
  const proc = spawn(venvPython(), ['-m', 'app.health_cli', ...sub], {
    stdio: 'inherit',
    env: buildEnv(),
  });
  proc.on('exit', (code) => process.exit(code ?? 0));
}

function runRouteEvalCmd() {
  setupIfNeeded();
  const sub = args.slice(1);
  const proc = spawn(venvPython(), ['-m', 'app.eval_cli', ...sub], {
    stdio: 'inherit',
    env: buildEnv(),
  });
  proc.on('exit', (code) => process.exit(code ?? 0));
}

function runWeightsCmd() {
  setupIfNeeded();
  const sub = args.slice(1);
  if (sub.length === 0 || sub[0] === '--help' || sub[0] === '-h') {
    log(c.dim('Usage: skillforge weights export [-o file] [--user-id=] [--project-root=]'));
    log(c.dim('       skillforge weights import <file.json> [--user-id=] [--replace-user] [--project-root=]'));
    process.exit(sub.length === 0 ? 1 : 0);
  }
  const proc = spawn(venvPython(), ['-m', 'app.weights_cli', ...sub], {
    stdio: 'inherit',
    env: buildEnv(),
  });
  proc.on('exit', (code) => process.exit(code ?? 0));
}

// ---- skill management ----
function skillsAdd(srcPath) {
  if (!srcPath) {
    err('Usage: skillforge skills add <path-to-skill-folder>');
    process.exit(1);
  }
  const src = path.resolve(srcPath);
  if (!fs.existsSync(src) || !fs.statSync(src).isDirectory()) {
    err(`Not a directory: ${src}`);
    process.exit(1);
  }
  if (!fs.existsSync(path.join(src, 'SKILL.md'))) {
    err(`No SKILL.md in ${src}`);
    process.exit(1);
  }
  ensureDirs();
  const name = path.basename(src);
  const dest = path.join(USER_SKILLS_DIR, name);
  fs.cpSync(src, dest, { recursive: true });
  ok(`Added skill "${name}" → ${dest}`);
  log(c.dim('  Restart skillforge mcp (or trigger catalog reload) to pick up the new skill.'));
}

function skillsList() {
  ensureDirs();
  const bundled = fs.readdirSync(path.join(PKG_ROOT, 'skills')).filter(f =>
    fs.existsSync(path.join(PKG_ROOT, 'skills', f, 'SKILL.md'))
  );
  const user = fs.existsSync(USER_SKILLS_DIR)
    ? fs.readdirSync(USER_SKILLS_DIR).filter(f =>
        fs.existsSync(path.join(USER_SKILLS_DIR, f, 'SKILL.md'))
      )
    : [];

  log(c.bold(`Bundled skills (${bundled.length}):`));
  bundled.forEach(n => log('  ' + c.dim('•'), n));
  log('');
  log(c.bold(`Your skills (${user.length}):`));
  if (user.length === 0) {
    log(c.dim('  none yet — add one with `skillforge skills add <path>`'));
  } else {
    user.forEach(n => log('  ' + c.dim('•'), n));
  }
}

function skillsRemove(name) {
  if (!name) {
    err('Usage: skillforge skills remove <name>');
    process.exit(1);
  }
  const target = path.join(USER_SKILLS_DIR, name);
  if (!fs.existsSync(target)) {
    err(`No user skill named "${name}". Bundled skills cannot be removed (use disable_skill via MCP).`);
    process.exit(1);
  }
  fs.rmSync(target, { recursive: true, force: true });
  ok(`Removed "${name}"`);
}

function reset() {
  const dbPath = path.join(DATA_DIR, 'orchestrator.db');
  if (fs.existsSync(dbPath)) {
    fs.rmSync(dbPath);
    ok('Wiped learned weights and event history.');
  } else {
    info('No state to reset.');
  }
}

function runHostsInit() {
  const hostSetup = require('../lib/host-setup');
  hostSetup.reportHostsAndInstallAgentCommands({
    force: args.includes('--force') || args.includes('--force-cursor'),
    pkgRoot: PKG_ROOT,
    pkgVersion: PKG_VERSION,
    log,
    ok,
    err,
    dim: s => log(c.dim(s)),
  });
}

function showHelp() {
  const colW = 48;
  const row = (cmd, desc) => {
    const s = `${cmd}`;
    const padLen = Math.max(2, colW - s.length);
    const pad = ' '.repeat(padLen);
    return `  ${c.cyan(s)}${pad}${desc}`;
  };
  const sec = title => `\n${c.bold(title)}\n${c.dim('  ' + '─'.repeat(72))}`;
  log('');
  log(c.bold(`Skillforge`) + `  ${c.dim('local SKILL.md orchestration')}`);
  log(
    `${c.dim('Version')} ${PKG_VERSION}${c.dim('  ·  ')}Enterprise automation and MCP hosts share the same Python engine.`,
  );
  log(`${c.dim('State directory')}  ${CONFIG_DIR}`);
  log(
    `\n${c.dim('PRIMARY INTEGRATION (production workloads):')} ${c.bold('stdio MCP')} — ${c.dim('configure')} ${c.cyan('skillforge mcp config')} ${c.dim(', then restart the IDE / agent.')}`,
  );
  log(
    `${c.dim('TERMINAL (operators, scripting, CI):')} ${c.dim('routing, observability, and')} ${c.cyan('skillforge tools')} ${c.dim('(MCP tool parity).')}`,
  );

  log(sec('Model Context Protocol'));
  log(row('skillforge mcp', 'Start JSON-RPC MCP server over stdio (Cursor, Claude Desktop, compatible hosts)'));
  log(
    row(
      'skillforge mcp config [--local] [--with-anthropic] [--with-env]',
      'Emit MCP host JSON (--with-env adds SKILLFORGE_ROUTER_MODE=host)',
    ),
  );
  log(`  ${c.dim('Default routing')}  SKILLFORGE_ROUTER_MODE=host · two-step shortlist then picked_names`);
  log(
    `  ${c.dim('Minimal npx host entry')}  ${JSON.stringify({
      mcpServers: {
        skillforge: { command: 'npx', args: ['-y', NPM_PKG_NAME, 'mcp'] },
      },
    })}`,
  );

  log(sec('Routing & context'));
  log(row('skillforge agent [--prompt TEXT]', 'Standalone chat agent · OpenAI-compatible API + MCP tool handlers'));
  log(row('skillforge route [TEXT…]', 'Interactive / scripted routing · --json · -i · --explain (see route --help)'));
  log(row('skillforge index --project-root=…', 'Project text index RAG chunks (SQLite project_chunks)'));
  log(row('skillforge tips', 'Short operator reference (routing, env, MCP host mode)'));

  log(sec('MCP tool parity (CLI)'));
  log(row('skillforge tools …', 'Subcommands mirror MCP tools (same handlers)'));
  log(
    row(
      'skillforge tools --help',
      'search · explain · get · catalog · feedback · disable · referenced',
    ),
  );
  log(
    `  ${c.dim('└')} ${c.dim('materialize · bootstrap · capabilities · router-status · index-status · weights-snapshot · events-recent')}`,
  );
  log(row('skillforge tools … --json', 'Raw tool envelope (content + _meta) for automation'));

  log(sec('Observability & diagnostics'));
  log(row('skillforge events …', '--watch routing / usage SQLite tail'));
  log(row('skillforge replay …', 'Chronological event timeline (--session-id, --json)'));
  log(row('skillforge health …', 'Preflight: paths · catalog (--quick skips embed load)'));
  log(row('skillforge route-eval …', 'Fixture embedding regression harness (CI)'));
  log(row('skillforge weights export|import …', 'Portable learned weights snapshot'));

  log(sec('Catalog & authoring'));
  log(row('skillforge skills list|add|remove|init|lint …', 'Filesystem skill trees + scaffold + manifest lint'));
  log(row('skillforge pack install|list|update|remove …', 'Git-hosted skill bundles'));

  log(sec('Setup & lifecycle'));
  log(row('skillforge install [--force-cursor]', 'Python venv + deps + optional Cursor / Claude Code slash templates'));
  log(row('skillforge config path|init|validate …', 'Stable ~/.skillforge/env (dotenv linter: config validate · README)'));
  log(row('skillforge hosts init · skillforge cursor init', 'Rewrite managed /skillforge host commands (--force)'));
  log(row('skillforge reset', 'Drop SQLite learning + event history'));

  log(`\n${c.bold('First run')}  ${c.cyan('skillforge install')} ${c.dim('or')} ${c.cyan(`npx -y ${NPM_PKG_NAME} install`)}`);
  log(
    c.dim(
      '  Auto-provisions ~/.skillforge/venv · optional Cursor + Claude Code /skillforge commands ' +
        '(SKILLFORGE_SKIP_CURSOR_SETUP, SKILLFORGE_SKIP_CLAUDE_CODE_SETUP).',
    ),
  );
  log(`\n${c.bold('Documentation')}  README.md + docs/ · npm/GitHub (${NPM_PKG_NAME})`);
}

// ---- main ----
async function main() {
  dropLegacyAuthJsonIfPresent();

  if (cmd === 'help') {
    showHelp();
    return;
  }

  const wantsCliHelp = args.includes('--help') || args.includes('-h');
  if (wantsCliHelp && (cmd === undefined || cmd === '--help' || cmd === '-h')) {
    showHelp();
    return;
  }

  switch (cmd) {
    case undefined:
      showHelp();
      break;
    case 'events':
      runEventsCmd();
      break;
    case 'replay':
      runReplayCmd();
      break;
    case 'tips':
      runTipsCmd();
      break;
    case 'tools':
      runToolsCmd();
      break;
    case 'agent':
      runAgentCmd();
      break;
    case 'route':
      runRouteCmd();
      break;
    case 'index':
      runIndexCmd();
      break;
    case 'health':
      runHealthCmd();
      break;
    case 'route-eval':
      runRouteEvalCmd();
      break;
    case 'weights':
      runWeightsCmd();
      break;
    case 'mcp':
      if (args[1] === 'config') {
        printMcpConfig();
        break;
      }
      runMcpServer();
      break;
    case 'install':
      runSetup();
      break;
    case 'hosts': {
      const sub = args[1];
      if (sub === 'init') {
        runHostsInit();
        break;
      }
      err('Unknown hosts subcommand.');
      log(c.dim('  Try: skillforge hosts init [--force]'));
      process.exit(1);
    }
    case 'cursor': {
      const sub = args[1];
      if (sub === 'init') {
        runHostsInit();
        break;
      }
      err('Unknown cursor subcommand.');
      log(c.dim('  Try: skillforge cursor init [--force] (alias: hosts init)'));
      process.exit(1);
    }
    case 'reset':
      reset();
      break;
    case 'config':
      runConfigCmd();
      break;
    case 'skills': {
      const sub = args[1];
      if (sub === 'list') skillsList();
      else if (sub === 'add') skillsAdd(args[2]);
      else if (sub === 'remove' || sub === 'rm') skillsRemove(args[2]);
      else if (sub === 'init') runSkillsAuthorCmd('init', args.slice(2));
      else if (sub === 'lint') runSkillsAuthorCmd('lint', args.slice(2));
      else {
        err(`Unknown skills subcommand: ${sub}`);
        log(c.dim('  Try: list, add, remove, init, lint'));
        process.exit(1);
      }
      break;
    }
    case 'pack': {
      const sub = args[1];
      try {
        if (sub === 'install' || sub === 'add') {
          const result = packs.installPack(args[2]);
          ok(`Installed pack "${result.name}" (${result.version}) with ${result.skills.length} skill(s):`);
          result.skills.forEach(s => log('  ' + c.dim('•'), s));
          log(c.dim('  Restart skillforge mcp (or trigger catalog reload) to pick up new skills.'));
        } else if (sub === 'list') {
          const list = packs.listPacks();
          if (list.length === 0) {
            info('No installed packs.');
            log(c.dim('  Install one with: skillforge pack install <user/repo>'));
          } else {
            log(c.bold(`Installed packs (${list.length}):`));
            list.forEach(p => {
              log(`  ${c.bold(p.name)} ${c.dim(p.version)} ${c.dim('— ' + p.source)}`);
              log(c.dim(`    skills: ${p.skills.join(', ')}`));
            });
          }
        } else if (sub === 'update') {
          const result = packs.updatePack(args[2]);
          ok(`Updated "${result.name}" → ${result.version}`);
        } else if (sub === 'remove' || sub === 'rm' || sub === 'uninstall') {
          const result = packs.uninstallPack(args[2]);
          ok(`Removed pack "${result.name}" (${result.removed.length} skills unlinked)`);
        } else {
          err(`Unknown pack subcommand: ${sub}`);
          log(c.dim('  Try: install, list, update, remove'));
          process.exit(1);
        }
      } catch (e) {
        err(e.message);
        process.exit(1);
      }
      break;
    }
    default:
      err(`Unknown command: ${cmd}`);
      showHelp();
      process.exit(1);
  }
}

main().catch(e => {
  err(e.message || e);
  process.exit(1);
});
