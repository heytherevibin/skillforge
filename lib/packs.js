/**
 * Skill pack installer.
 *
 * A "pack" is any git repo containing a skillforge.json manifest at the root:
 *   {
 *     "name": "my-pack",
 *     "version": "1.0.0",
 *     "skills": ["skill-one", "skill-two"]   // folder names relative to repo root
 *   }
 *
 * Packs are git-cloned to ~/.skillforge/packs/<source-hash>/ and their
 * declared skill folders are symlinked into ~/.skillforge/skills/.
 * This means uninstall just removes the symlinks + the cached clone,
 * and updates are a single `git pull`.
 */
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const { spawnSync } = require('child_process');
const os = require('os');

const CONFIG_DIR = path.join(os.homedir(), '.skillforge');
const PACKS_DIR = path.join(CONFIG_DIR, 'packs');
const USER_SKILLS_DIR = path.join(CONFIG_DIR, 'skills');
const PACK_REGISTRY = path.join(CONFIG_DIR, 'packs.json');

function ensureDirs() {
  fs.mkdirSync(PACKS_DIR, { recursive: true });
  fs.mkdirSync(USER_SKILLS_DIR, { recursive: true });
}

function loadRegistry() {
  if (!fs.existsSync(PACK_REGISTRY)) return {};
  try { return JSON.parse(fs.readFileSync(PACK_REGISTRY, 'utf8')); }
  catch { return {}; }
}

function saveRegistry(reg) {
  fs.writeFileSync(PACK_REGISTRY, JSON.stringify(reg, null, 2));
}

function normalizeSource(source) {
  // Accept "user/repo", "https://github.com/user/repo", "git@github.com:user/repo.git", or a local path
  if (source.startsWith('http://') || source.startsWith('https://') || source.startsWith('git@')) {
    return { type: 'git', url: source };
  }
  if (source.startsWith('./') || source.startsWith('/') || source.startsWith('~')) {
    return { type: 'local', path: source.replace(/^~/, os.homedir()) };
  }
  // user/repo shorthand → github
  if (/^[\w.-]+\/[\w.-]+$/.test(source)) {
    return { type: 'git', url: `https://github.com/${source}` };
  }
  throw new Error(`Cannot interpret source: ${source}`);
}

function sourceKey(src) {
  return crypto.createHash('sha1').update(JSON.stringify(src)).digest('hex').slice(0, 10);
}

function readManifest(packDir) {
  const mf = path.join(packDir, 'skillforge.json');
  if (!fs.existsSync(mf)) {
    throw new Error(`No skillforge.json found at ${packDir}. A skill pack must have a manifest at its root.`);
  }
  const m = JSON.parse(fs.readFileSync(mf, 'utf8'));
  if (!m.name || !Array.isArray(m.skills)) {
    throw new Error('skillforge.json must have "name" (string) and "skills" (array of folder names)');
  }
  return m;
}

function validateSkills(packDir, manifest) {
  const errors = [];
  for (const s of manifest.skills) {
    const skillPath = path.join(packDir, s);
    if (!fs.existsSync(skillPath)) errors.push(`Listed skill "${s}" not found in pack`);
    else if (!fs.existsSync(path.join(skillPath, 'SKILL.md'))) errors.push(`"${s}" has no SKILL.md`);
  }
  if (errors.length) throw new Error('Pack validation failed:\n  - ' + errors.join('\n  - '));
}

function linkSkills(packDir, manifest, packKey) {
  const linked = [];
  for (const s of manifest.skills) {
    const target = path.join(USER_SKILLS_DIR, s);
    if (fs.existsSync(target)) {
      const stat = fs.lstatSync(target);
      if (stat.isSymbolicLink()) {
        // Existing pack symlink — overwrite (re-install case)
        fs.unlinkSync(target);
      } else {
        throw new Error(`A skill folder named "${s}" already exists in user skills (not from a pack). Remove it first or rename your pack's skill.`);
      }
    }
    fs.symlinkSync(path.join(packDir, s), target, 'dir');
    linked.push(s);
  }
  return linked;
}

function unlinkSkills(skills) {
  const removed = [];
  for (const s of skills) {
    const target = path.join(USER_SKILLS_DIR, s);
    if (fs.existsSync(target)) {
      const stat = fs.lstatSync(target);
      if (stat.isSymbolicLink()) {
        fs.unlinkSync(target);
        removed.push(s);
      }
    }
  }
  return removed;
}

function installPack(source) {
  ensureDirs();
  const src = normalizeSource(source);
  const key = sourceKey(src);
  const packDir = path.join(PACKS_DIR, key);

  if (src.type === 'git') {
    if (fs.existsSync(packDir)) {
      // Already cloned — update instead
      const r = spawnSync('git', ['-C', packDir, 'pull', '--ff-only', '--quiet'], { stdio: 'inherit' });
      if (r.status !== 0) throw new Error('git pull failed');
    } else {
      const r = spawnSync('git', ['clone', '--depth', '1', '--quiet', src.url, packDir], { stdio: 'inherit' });
      if (r.status !== 0) throw new Error(`git clone failed for ${src.url}`);
    }
  } else {
    // Local path — symlink the pack dir itself
    if (fs.existsSync(packDir)) fs.rmSync(packDir, { recursive: true, force: true });
    fs.symlinkSync(src.path, packDir, 'dir');
  }

  const manifest = readManifest(packDir);
  validateSkills(packDir, manifest);
  const linked = linkSkills(packDir, manifest, key);

  const reg = loadRegistry();
  reg[manifest.name] = {
    source,
    key,
    version: manifest.version || 'unknown',
    skills: linked,
    installed_at: new Date().toISOString(),
  };
  saveRegistry(reg);
  return { name: manifest.name, skills: linked, version: manifest.version };
}

function uninstallPack(name) {
  ensureDirs();
  const reg = loadRegistry();
  const entry = reg[name];
  if (!entry) throw new Error(`No installed pack named "${name}"`);
  const removed = unlinkSkills(entry.skills);
  const packDir = path.join(PACKS_DIR, entry.key);
  if (fs.existsSync(packDir)) {
    const stat = fs.lstatSync(packDir);
    if (stat.isSymbolicLink()) fs.unlinkSync(packDir);
    else fs.rmSync(packDir, { recursive: true, force: true });
  }
  delete reg[name];
  saveRegistry(reg);
  return { name, removed };
}

function listPacks() {
  ensureDirs();
  const reg = loadRegistry();
  return Object.entries(reg).map(([name, e]) => ({ name, ...e }));
}

function updatePack(name) {
  const reg = loadRegistry();
  const entry = reg[name];
  if (!entry) throw new Error(`No installed pack named "${name}"`);
  return installPack(entry.source);  // re-runs git pull + relinks
}

module.exports = { installPack, uninstallPack, listPacks, updatePack };
