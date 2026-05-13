#!/usr/bin/env node
/**
 * skillforge — adaptive skill orchestrator for Claude
 *
 * Usage:
 *   skillforge                       # start server + open dashboard
 *   skillforge start                 # start server only
 *   skillforge chat                  # interactive CLI client
 *   skillforge mcp                   # run as an MCP stdio server
 *   skillforge install               # one-time setup (auto-runs on first launch)
 *   skillforge skills add <path>     # add a local skill folder
 *   skillforge skills list           # list catalog
 *   skillforge skills remove <name>  # remove a user-added skill
 *   skillforge pack install <repo>   # install a skill pack from git
 *   skillforge pack list             # list installed packs
 *   skillforge pack update <name>    # update a pack
 *   skillforge pack remove <name>    # uninstall a pack
 *   skillforge auth add <user>       # create a bearer token for a user
 *   skillforge auth list             # list users + tokens
 *   skillforge auth remove <user>    # revoke a token
 *   skillforge reset                 # wipe learned state
 *   skillforge --help
 */

const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const { spawn, spawnSync } = require('child_process');
const os = require('os');
const packs = require('../lib/packs');

const PKG_ROOT = path.resolve(__dirname, '..');
const NPM_PKG_NAME = require(path.join(PKG_ROOT, 'package.json')).name;
const CONFIG_DIR = path.join(os.homedir(), '.skillforge');
const VENV_DIR = path.join(CONFIG_DIR, 'venv');
const DATA_DIR = path.join(CONFIG_DIR, 'data');
const USER_SKILLS_DIR = path.join(CONFIG_DIR, 'skills');
const PACKS_DIR = path.join(CONFIG_DIR, 'packs');
const AUTH_FILE = path.join(CONFIG_DIR, 'auth.json');
const SETUP_MARKER = path.join(CONFIG_DIR, '.setup-complete');

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

function log(...m) { console.log(...m); }
function err(...m) { console.error(c.red('✗'), ...m); }
function ok(...m) { console.log(c.green('✓'), ...m); }
function info(...m) { console.log(c.cyan('▸'), ...m); }

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

  // 2. Create venv
  if (!fs.existsSync(venvPython())) {
    info('Creating Python virtual environment...');
    const r = spawnSync(py.bin, ['-m', 'venv', VENV_DIR], { stdio: 'inherit' });
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
  const pipR = spawnSync(
    venvPip(),
    ['install', '--upgrade', '--quiet', '-r', reqFile],
    { stdio: 'inherit' }
  );
  if (pipR.status !== 0) {
    err('Failed to install Python dependencies.');
    process.exit(1);
  }
  ok('Python dependencies installed');

  // 4. Mark setup complete
  fs.writeFileSync(SETUP_MARKER, new Date().toISOString());
  ok('Setup complete\n');
}

function setupIfNeeded() {
  ensureDirs();
  if (!fs.existsSync(SETUP_MARKER) || !fs.existsSync(venvPython())) {
    runSetup();
  }
}

// ---- API key check ----
function checkApiKey() {
  if (!process.env.ANTHROPIC_API_KEY) {
    err('ANTHROPIC_API_KEY environment variable is not set.');
    log(c.dim('  Get a key at https://console.anthropic.com/'));
    log(c.dim('  Then set it:'));
    log(c.dim('    export ANTHROPIC_API_KEY=sk-ant-...'));
    process.exit(1);
  }
}

// ---- auth management ----
function loadAuth() {
  if (!fs.existsSync(AUTH_FILE)) return {};
  try { return JSON.parse(fs.readFileSync(AUTH_FILE, 'utf8')); } catch { return {}; }
}
function saveAuth(map) {
  ensureDirs();
  fs.writeFileSync(AUTH_FILE, JSON.stringify(map, null, 2), { mode: 0o600 });
}
function authToEnvVar(map) {
  // map is { token: userId }. Convert and inject as JSON env var.
  return JSON.stringify(map);
}

function authAdd(user) {
  if (!user) { err('Usage: skillforge auth add <user-id>'); process.exit(1); }
  const map = loadAuth();
  // Generate a token
  const token = 'sf_' + crypto.randomBytes(24).toString('base64url');
  map[token] = user;
  saveAuth(map);
  ok(`Created token for user "${user}":`);
  log('');
  log('   ' + c.bold(token));
  log('');
  log(c.dim('Use this token in the Authorization header:'));
  log(c.dim(`   Authorization: Bearer ${token}`));
  log(c.dim('Restart the server for the token to take effect.'));
}

function authList() {
  const map = loadAuth();
  const tokens = Object.entries(map);
  if (tokens.length === 0) {
    info('No auth tokens. Server runs in single-user mode.');
    log(c.dim('  Add one with: skillforge auth add <user-id>'));
    return;
  }
  log(c.bold('Auth tokens:'));
  for (const [token, user] of tokens) {
    log(`  ${c.dim(token.slice(0, 16) + '...')} → ${user}`);
  }
}

function authRemove(user) {
  if (!user) { err('Usage: skillforge auth remove <user-id>'); process.exit(1); }
  const map = loadAuth();
  const before = Object.keys(map).length;
  for (const [t, u] of Object.entries(map)) {
    if (u === user) delete map[t];
  }
  const removed = before - Object.keys(map).length;
  saveAuth(map);
  if (removed > 0) ok(`Revoked ${removed} token(s) for "${user}"`);
  else info(`No tokens for "${user}"`);
}

// ---- server lifecycle ----
function buildEnv(extra = {}) {
  const authMap = loadAuth();
  return {
    ...process.env,
    SKILLFORGE_BUNDLED_SKILLS: path.join(PKG_ROOT, 'skills'),
    SKILLFORGE_USER_SKILLS: USER_SKILLS_DIR,
    SKILLFORGE_DB_PATH: path.join(DATA_DIR, 'orchestrator.db'),
    PYTHONPATH: path.join(PKG_ROOT, 'python'),
    PYTHONUNBUFFERED: '1',
    ...(Object.keys(authMap).length > 0 ? { SKILLFORGE_AUTH_TOKENS: authToEnvVar(authMap) } : {}),
    ...extra,
  };
}

function startServer({ port = 8000, openDashboard = false } = {}) {
  setupIfNeeded();
  checkApiKey();

  const env = buildEnv({ SKILLFORGE_PORT: String(port) });
  const authEnabled = Object.keys(loadAuth()).length > 0;

  info(`Starting orchestrator on http://localhost:${port}`);
  log(c.dim(`  Dashboard:  http://localhost:${port}/`));
  log(c.dim(`  Skills dir: ${USER_SKILLS_DIR} (drop folders here to add)`));
  log(c.dim(`  Data dir:   ${DATA_DIR}`));
  log(c.dim(`  Auth:       ${authEnabled ? 'enabled (bearer token required)' : 'disabled (single-user)'}`));
  log('');

  const proc = spawn(
    venvPython(),
    ['-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', String(port)],
    { stdio: 'inherit', env }
  );

  if (openDashboard) {
    setTimeout(() => openUrl(`http://localhost:${port}/`), 3000);
  }

  proc.on('exit', (code) => process.exit(code || 0));
  process.on('SIGINT', () => proc.kill('SIGINT'));
  process.on('SIGTERM', () => proc.kill('SIGTERM'));
}

function runMcpServer() {
  // No api-key check yet — let the MCP client pick up errors via tool calls
  setupIfNeeded();
  if (!process.env.ANTHROPIC_API_KEY) {
    // For MCP, log to stderr — stdout is reserved for protocol
    console.error('[skillforge-mcp] WARNING: ANTHROPIC_API_KEY not set; router calls will fail');
  }
  const env = buildEnv();
  // MCP protocol: speaks JSON-RPC over stdio. No banner on stdout.
  const proc = spawn(venvPython(), ['-m', 'app.mcp_server'], {
    stdio: ['inherit', 'inherit', 'inherit'],
    env,
  });
  proc.on('exit', (code) => process.exit(code || 0));
  process.on('SIGINT', () => proc.kill('SIGINT'));
  process.on('SIGTERM', () => proc.kill('SIGTERM'));
}

function openUrl(url) {
  const opener = isWindows() ? 'start' : (process.platform === 'darwin' ? 'open' : 'xdg-open');
  spawn(opener, [url], { stdio: 'ignore', detached: true, shell: isWindows() }).unref();
}

function runChat() {
  setupIfNeeded();
  checkApiKey();
  const env = buildEnv();
  const proc = spawn(venvPython(), ['-m', 'app.cli'], { stdio: 'inherit', env });
  proc.on('exit', (code) => process.exit(code || 0));
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
  log(c.dim('  Restart the server to pick up the new skill.'));
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
    err(`No user skill named "${name}". Bundled skills cannot be removed (but can be disabled in the dashboard).`);
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

function showHelp() {
  log(`
${c.bold('skillforge')} — adaptive skill orchestrator for Claude

${c.bold('Run modes:')}
  skillforge                       Start HTTP server + open dashboard
  skillforge start [--port=8000]   Start HTTP server only
  skillforge chat                  Interactive chat in this terminal
  skillforge mcp                   Run as an MCP stdio server (for Claude Desktop, etc.)

${c.bold('Skills:')}
  skillforge skills list           List bundled and user skills
  skillforge skills add <path>     Add a local skill folder
  skillforge skills remove <name>  Remove a user-added skill

${c.bold('Skill packs (install from git):')}
  skillforge pack install <repo>   Install pack (e.g. "user/repo" or git URL)
  skillforge pack list             List installed packs
  skillforge pack update <name>    Update a pack
  skillforge pack remove <name>    Uninstall a pack

${c.bold('Auth (multi-user mode):')}
  skillforge auth add <user>       Create a bearer token for a user
  skillforge auth list             List users with tokens
  skillforge auth remove <user>    Revoke all tokens for a user

${c.bold('Maintenance:')}
  skillforge reset                 Wipe learned state and event log
  skillforge install               Re-run setup (auto-runs on first launch)
  skillforge --help                This message

${c.bold('First run:')} set ANTHROPIC_API_KEY, run ${c.cyan('skillforge')} — setup happens automatically.
${c.bold('Config dir:')} ${CONFIG_DIR}

${c.bold('MCP integration:')}
  To use skillforge from Claude Desktop, add this to your config:
    ${JSON.stringify({ mcpServers: { skillforge: { command: 'npx', args: ['-y', NPM_PKG_NAME, 'mcp'] } } })}
`);
}

// ---- main ----
async function main() {
  if (args.includes('--help') || args.includes('-h') || cmd === 'help') {
    showHelp();
    return;
  }

  const portArg = args.find(a => a.startsWith('--port='));
  const port = portArg ? parseInt(portArg.split('=')[1]) : 8000;

  switch (cmd) {
    case undefined:
      startServer({ port, openDashboard: true });
      break;
    case 'start':
      startServer({ port, openDashboard: false });
      break;
    case 'chat':
      runChat();
      break;
    case 'mcp':
      runMcpServer();
      break;
    case 'install':
      runSetup();
      break;
    case 'reset':
      reset();
      break;
    case 'skills': {
      const sub = args[1];
      if (sub === 'list') skillsList();
      else if (sub === 'add') skillsAdd(args[2]);
      else if (sub === 'remove' || sub === 'rm') skillsRemove(args[2]);
      else {
        err(`Unknown skills subcommand: ${sub}`);
        log(c.dim('  Try: list, add, remove'));
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
          log(c.dim('  Restart the server to pick up new skills.'));
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
    case 'auth': {
      const sub = args[1];
      if (sub === 'add') authAdd(args[2]);
      else if (sub === 'list') authList();
      else if (sub === 'remove' || sub === 'rm') authRemove(args[2]);
      else {
        err(`Unknown auth subcommand: ${sub}`);
        log(c.dim('  Try: add, list, remove'));
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
