/**
 * Skillforge CLI help renderer: plain (--help), boxed (--ui), readline browse (--browse).
 */

const readline = require('node:readline/promises');
const { stdin, stdout } = require('node:process');
const {
  buildHelpModel,
  buildBannerLines,
  buildTopSummaryLines,
  buildFooterLines,
} = require('./help-content');

/** @typedef {{ pkgVersion: string, configDir: string, npmPkgName: string }} HelpContext */

const ANSI = {
  bold: '\x1b[1m',
  boldOff: '\x1b[22m',
  dim: '\x1b[2m',
  dimOff: '\x1b[22m',
  cyan: '\x1b[36m',
  reset: '\x1b[0m',
};

/**
 * @param {string} line
 * @param {boolean} useColor
 */
function applyStyleTags(line, useColor) {
  if (!useColor) {
    return line.replace(/\{(?:bold|dim|cyan|\/?bold|\/?dim|\/?cyan)\}/g, '');
  }
  return line
    .replace(/\{bold\}/g, ANSI.bold)
    .replace(/\{\/bold\}/g, ANSI.boldOff)
    .replace(/\{dim\}/g, ANSI.dim)
    .replace(/\{\/dim\}/g, ANSI.dimOff)
    .replace(/\{cyan\}/g, ANSI.cyan)
    .replace(/\{\/cyan\}/g, ANSI.reset);
}

/**
 * @param {string[]} lines
 * @param {boolean} useColor
 */
function joinLines(lines, useColor) {
  return lines.map(l => applyStyleTags(l, useColor)).join('\n');
}

/**
 * @param {string} text
 * @param {number} width
 */
function wrapPlain(text, width) {
  const words = String(text).trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return [];
  /** @type {string[]} */
  const out = [];
  let line = '';
  for (const w of words) {
    const next = line ? `${line} ${w}` : w;
    if (next.length <= width) line = next;
    else {
      if (line) out.push(line);
      if (w.length > width) {
        let rest = w;
        while (rest.length > width) {
          out.push(rest.slice(0, width));
          rest = rest.slice(width);
        }
        line = rest;
      } else line = w;
    }
  }
  if (line) out.push(line);
  return out;
}

/**
 * @param {import('./help-content').HelpSection} sec
 * @param {HelpContext} _ctx
 * @param {{ columns: number, color: boolean, useUnicode: boolean }} o
 */
function renderSectionPanel(sec, _ctx, o) {
  const { columns, color, useUnicode } = o;
  const innerW = Math.min(76, columns - 4);
  const L = useUnicode ? '┌' : '+';
  const R = useUnicode ? '┐' : '+';
  const V = useUnicode ? '│' : '|';
  const BL = useUnicode ? '└' : '+';
  const BR = useUnicode ? '┘' : '+';
  const H = useUnicode ? '─' : '-';

  const title = ` ${sec.title} `;
  const barInner = Math.max(0, innerW - 2 - title.length);
  const top = `${L}${H}${title}${H.repeat(barInner)}${R}`;

  /** @type {string[]} */
  const body = [];
  const cmdW = Math.min(36, Math.floor(innerW * 0.45));
  const descW = Math.max(16, innerW - cmdW - 3);

  for (const row of sec.rows || []) {
    const cmdLine = row.cmd.length > cmdW ? row.cmd.slice(0, cmdW - 1) + '…' : row.cmd;
    const cmdPadded = cmdLine.padEnd(cmdW);
    const cmdStyled = applyStyleTags(`{cyan}${cmdPadded}{/cyan}`, color);
    const descLines = wrapPlain(row.desc, descW);
    if (descLines.length === 0) {
      body.push(`${V} ${cmdStyled}`);
    } else {
      body.push(`${V} ${cmdStyled} ${descLines[0]}`);
      const indent = 2 + cmdW + 1;
      const contPad = `${V}${' '.repeat(indent)}`;
      for (let i = 1; i < descLines.length; i += 1) {
        body.push(`${contPad}${descLines[i]}`);
      }
    }
  }
  for (const ln of sec.lines || []) {
    for (const wline of wrapPlain(ln, innerW - 2)) {
      body.push(`${V} ${applyStyleTags(`{dim}${wline}{/dim}`, color)}`);
    }
  }

  const bottom = `${BL}${H.repeat(innerW)}${BR}`;
  return [applyStyleTags(top, color), ...body, applyStyleTags(bottom, color)].join('\n');
}

function getStderrColumns() {
  try {
    return process.stderr.columns && process.stderr.columns > 0 ? process.stderr.columns : 80;
  } catch {
    return 80;
  }
}

function hasColorStderr() {
  if (process.env.NO_COLOR !== undefined && process.env.NO_COLOR !== '') return false;
  if (process.env.FORCE_COLOR !== undefined && String(process.env.FORCE_COLOR) === '1') return true;
  try {
    return process.stderr.isTTY === true;
  } catch {
    return false;
  }
}

/**
 * @param {'plain'|'panels'} mode
 * @param {HelpContext} ctx
 * @param {{ columns?: number, useUnicode?: boolean, color?: boolean }} [options]
 */
function renderHelp(mode, ctx, options = {}) {
  const color = options.color !== false && hasColorStderr();
  const columns = Math.max(
    40,
    typeof options.columns === 'number' ? options.columns : getStderrColumns(),
  );
  const useUnicode = options.useUnicode !== false && process.platform !== 'win32';

  const { sections } = buildHelpModel({ npmPkgName: ctx.npmPkgName });
  const banner = buildBannerLines(ctx);
  const top = buildTopSummaryLines();
  const footer = buildFooterLines(ctx);

  const parts = [];
  parts.push(joinLines(banner, color));
  parts.push('');
  parts.push(joinLines(top, color));

  for (const sec of sections) {
    if (mode === 'plain') {
      parts.push('');
      parts.push(applyStyleTags(`{bold}${sec.title}{/bold}`, color));
      parts.push(applyStyleTags(`{dim}  ${'─'.repeat(72)}{/dim}`, color));
      const colW = 48;
      for (const row of sec.rows || []) {
        const s = row.cmd;
        const padLen = Math.max(2, colW - s.length);
        const pad = ' '.repeat(padLen);
        parts.push(applyStyleTags(`  {cyan}${s}{/cyan}${pad}`, color) + row.desc);
      }
      for (const ln of sec.lines || []) {
        parts.push(applyStyleTags(`  {dim}${ln}{/dim}`, color));
      }
    } else {
      parts.push('');
      parts.push(renderSectionPanel(sec, ctx, { columns, color, useUnicode }));
    }
  }

  parts.push('');
  parts.push(joinLines(footer, color));
  return parts.join('\n');
}

function parseHelpOptions(argv) {
  const a = Array.isArray(argv) ? argv : process.argv.slice(2);
  const envUi = String(process.env.SKILLFORGE_HELP_UI || '').toLowerCase();
  return {
    ui: a.includes('--ui') || envUi === 'panels' || envUi === '1' || envUi === 'true',
    browse: a.includes('--browse'),
  };
}

/**
 * @param {HelpContext} ctx
 * @param {{ stderrIsTTY?: boolean }} [_o]
 */
async function runHelpBrowse(ctx, _o = {}) {
  const stderrIsTTY = _o.stderrIsTTY !== undefined ? _o.stderrIsTTY : !!process.stderr.isTTY;
  if (!stdin.isTTY || !stdout.isTTY || !stderrIsTTY) {
    return (
      applyStyleTags('{dim}(help --browse needs an interactive terminal)\n{/dim}', hasColorStderr()) +
      renderHelp('plain', ctx, {})
    );
  }

  const { sections } = buildHelpModel({ npmPkgName: ctx.npmPkgName });
  const color = hasColorStderr();
  const rl = readline.createInterface({ input: stdin, output: stdout, terminal: true });

  /** @type {(s: string) => void} */
  const werr = s => process.stderr.write(s);

  try {
    werr(joinLines([`{bold}Skillforge help{/bold}`, '{dim}Section number, 0 = full plain help, q = quit{/dim}'], color));
    werr('\n\n');
    sections.forEach((s, i) => {
      werr(`  ${i + 1}. ${s.title}\n`);
    });
    werr('\n');

    for (;;) {
      const ans = (await rl.question('Section [1-' + sections.length + '], 0, q: ')).trim().toLowerCase();
      if (ans === 'q') {
        werr(joinLines(['{dim}bye{/dim}'], color) + '\n');
        break;
      }
      if (ans === '') continue;
      const n = parseInt(ans, 10);
      if (ans === '0') {
        werr(renderHelp('plain', ctx, {}) + '\n');
        continue;
      }
      if (!Number.isFinite(n) || n < 1 || n > sections.length) {
        werr(joinLines([`{dim}Try 1-${sections.length}, 0, or q{/dim}`], color) + '\n');
        continue;
      }
      const sec = sections[n - 1];
      werr('\n');
      werr(
        renderSectionPanel(sec, ctx, {
          columns: getStderrColumns(),
          color,
          useUnicode: process.platform !== 'win32',
        }) + '\n\n',
      );
    }
  } finally {
    rl.close();
  }
  return '';
}

module.exports = {
  renderHelp,
  parseHelpOptions,
  runHelpBrowse,
  applyStyleTags,
  wrapPlain,
  renderSectionPanel,
};
