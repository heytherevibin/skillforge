#!/usr/bin/env node
/**
 * skillforge — skill orchestrator co-tool for Claude (MCP-first)
 *
 * Usage:
 *   skillforge, skillforge --help   Show help (primary path: MCP, not a web app)
 *   skillforge mcp                   MCP stdio server (Claude / Cursor / …)
 *   skillforge events [--watch] [--limit=N]     Print SQLite routing events
 *   skillforge route [words…] [--prompt=…]     Same routing as MCP route_skills (terminal)
 *   skillforge index --project-root=…            Chunk/embed repo files for project RAG
 *   skillforge install               One-time Python venv + deps
 *   skillforge skills … / pack … / reset
 */

const path = require('path');
const fs = require('fs');
const { spawn, spawnSync } = require('child_process');
const os = require('os');
const packs = require('../lib/packs');

const PKG_ROOT = path.resolve(__dirname, '..');
const NPM_PKG_NAME = require(path.join(PKG_ROOT, 'package.json')).name;
const CONFIG_DIR = path.join(os.homedir(), '.skillforge');
const VENV_DIR = path.join(CONFIG_DIR, 'venv');
const DATA_DIR = path.join(CONFIG_DIR, 'data');
const USER_SKILLS_DIR = path.join(CONFIG_DIR, 'skills');
/** Bearer-token file for the removed HTTP API (<=0.6.x); deleted on first CLI use. */
const LEGACY_AUTH_FILE = path.join(CONFIG_DIR, 'auth.json');
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

function buildEnv(extra = {}) {
  return {
    ...process.env,
    SKILLFORGE_BUNDLED_SKILLS: path.join(PKG_ROOT, 'skills'),
    SKILLFORGE_USER_SKILLS: USER_SKILLS_DIR,
    SKILLFORGE_DB_PATH: path.join(DATA_DIR, 'orchestrator.db'),
    PYTHONPATH: path.join(PKG_ROOT, 'python'),
    PYTHONUNBUFFERED: '1',
    ...extra,
  };
}

function printMcpConfig() {
  setupIfNeeded();
  const useLocal = args.includes('--local');
  const withKey = args.includes('--with-anthropic');
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
    entry.env = { ANTHROPIC_API_KEY: 'sk-ant-…' };
  }
  const out = { mcpServers: { skillforge: entry } };
  process.stdout.write(JSON.stringify(out, null, 2) + '\n');
  process.stderr.write(
    c.dim(
      'Merge into ~/.cursor/mcp.json, Claude Desktop config, etc. --local uses this package checkout; --with-anthropic adds env placeholder for Haiku routing.\n'
    )
  );
}

function runMcpServer() {
  setupIfNeeded();
  const env = buildEnv();
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

function showHelp() {
  log(`
${c.bold('skillforge')} — skill orchestrator co-tool for Claude (MCP-first)

${c.bold('Run modes:')}
  skillforge --help                This message (recommended first step)
  skillforge mcp                   MCP stdio — primary integration for Claude / Cursor
  skillforge mcp config [--local] [--with-anthropic]   Print JSON for MCP host (merge into mcp.json)
  skillforge events [--watch] [--limit=N] [--verbose] [--user=…]   Live routing log + usage (see --help)
  skillforge route [words…] [--project-root=…] [--include-project-rag]   Route a prompt (see skillforge route --help)
  skillforge index --project-root=… [--reset] [--stats-only]   Index repo text for include_project_rag

${c.bold('Skills:')}
  skillforge skills list           List bundled and user skills
  skillforge skills add <path>     Add a local skill folder
  skillforge skills remove <name>  Remove a user-added skill

${c.bold('Skill packs (install from git):')}
  skillforge pack install <repo>   Install pack (e.g. "user/repo" or git URL)
  skillforge pack list             List installed packs
  skillforge pack update <name>    Update a pack
  skillforge pack remove <name>    Uninstall a pack

${c.bold('Maintenance:')}
  skillforge reset                 Wipe learned state and event log
  skillforge install               Re-run setup (auto-runs on first launch)
  skillforge --help                This message

${c.bold('First run:')} ${c.cyan('skillforge install')} (auto on first command). Primary use: add MCP config (below). ${c.cyan('skillforge mcp')} needs no API key for embedding-only routing.
${c.bold('Config dir:')} ${CONFIG_DIR}

${c.bold('MCP integration:')}
  Generate a config snippet: ${c.cyan('skillforge mcp config')} (add ${c.cyan('--local')} for this checkout, ${c.cyan('--with-anthropic')} for a key placeholder)
  Minimal npx example:
    ${JSON.stringify({ mcpServers: { skillforge: { command: 'npx', args: ['-y', NPM_PKG_NAME, 'mcp'] } } })}
`);
}

// ---- main ----
async function main() {
  dropLegacyAuthJsonIfPresent();

  if (args.includes('--help') || args.includes('-h') || cmd === 'help') {
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
    case 'route':
      runRouteCmd();
      break;
    case 'index':
      runIndexCmd();
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
