/**
 * Structured Skillforge CLI help (rendered via lib/help-render.js).
 */

/** @typedef {{ cmd: string, desc: string }} HelpRow */

/** @typedef {{ id: string, title: string, rows?: HelpRow[], lines?: string[] }} HelpSection */

/**
 * @param {{ npmPkgName: string }} opts
 * @returns {{ sections: HelpSection[], NPM_PKG_NAME: string }}
 */
function buildHelpModel(opts) {
  const NPM_PKG_NAME = opts.npmPkgName;
  const minimalNpx = JSON.stringify({
    mcpServers: {
      skillforge: { command: 'npx', args: ['-y', NPM_PKG_NAME, 'mcp'] },
    },
  });

  /** @type {HelpSection[]} */
  const sections = [
    {
      id: 'mcp',
      title: 'Model Context Protocol',
      rows: [
        { cmd: 'skillforge mcp', desc: 'Start JSON-RPC MCP server over stdio (Cursor, Claude Desktop, compatible hosts)' },
        {
          cmd: 'skillforge mcp config [--local] [--with-anthropic] [--with-env] [--companion]',
          desc: 'Emit MCP host JSON (--with-env adds SKILLFORGE_ROUTER_MODE=host; --companion enables conversation-aware routing env)',
        },
      ],
      lines: [
        'Default routing  SKILLFORGE_ROUTER_MODE=host · two-step shortlist then picked_names',
        `Minimal npx host entry  ${minimalNpx}`,
      ],
    },
    {
      id: 'routing',
      title: 'Routing & context',
      rows: [
        { cmd: 'skillforge agent [--prompt TEXT]', desc: 'Standalone chat agent · OpenAI-compatible API + MCP tool handlers' },
        {
          cmd: 'skillforge route [TEXT…]',
          desc: 'Interactive / scripted routing · --json · -i · --explain (see route --help)',
        },
        { cmd: 'skillforge index --project-root=…', desc: 'Project text index RAG chunks (SQLite project_chunks)' },
        { cmd: 'skillforge tips', desc: 'Short operator reference (routing, env, MCP host mode)' },
      ],
    },
    {
      id: 'tools',
      title: 'MCP tool parity (CLI)',
      rows: [
        { cmd: 'skillforge tools …', desc: 'Subcommands mirror MCP tools (same handlers)' },
        {
          cmd: 'skillforge tools --help',
          desc: 'search · explain · get · catalog · feedback · disable · referenced',
        },
        {
          cmd: '  └',
          desc: 'materialize · bootstrap · capabilities · router-status · index-status · weights-snapshot · events-recent · memory-append|list|delete|prune-expired',
        },
        { cmd: 'skillforge tools … --json', desc: 'Raw tool envelope (content + _meta) for automation' },
      ],
    },
    {
      id: 'observe',
      title: 'Observability & diagnostics',
      rows: [
        { cmd: 'skillforge events …', desc: '--watch tail · prune --execute (purge old SQLite rows)' },
        { cmd: 'skillforge replay …', desc: 'Event timeline (--session-id, filters, --json export)' },
        { cmd: 'skillforge health …', desc: 'Preflight: paths · catalog (--quick skips embed load)' },
        { cmd: 'skillforge route-eval … · route-eval ingest', desc: 'Fixture regression (CI); ingest persists route/host_shortlist → JSON' },
        { cmd: 'skillforge weights export|import …', desc: 'Portable learned weights snapshot' },
      ],
    },
    {
      id: 'catalog',
      title: 'Catalog & authoring',
      rows: [
        {
          cmd: 'skillforge skills list|add|remove|init|lint …',
          desc: 'Filesystem skill trees + scaffold + manifest lint',
        },
        { cmd: 'skillforge pack install|list|update|remove …', desc: 'Git-hosted skill bundles' },
      ],
    },
    {
      id: 'setup',
      title: 'Setup & lifecycle',
      rows: [
        {
          cmd:
            'skillforge install [--force] [--hosts=cursor|claude-code|all] [--force-cursor|--force-claude|--only-*]',
          desc:
            'Python venv + deps · --force-cursor = Cursor-only + overwrite · --force-claude = Claude-only + overwrite · both ⇒ all hosts',
        },
        { cmd: 'skillforge config path|init|validate …', desc: 'Stable ~/.skillforge/env (dotenv linter: config validate · README)' },
        {
          cmd: 'skillforge hosts init · skillforge cursor init',
          desc: 'Rewrite managed /skillforge (--force · same host flags as install)',
        },
        { cmd: 'skillforge reset', desc: 'Drop SQLite learning + event history' },
      ],
    },
  ];

  return { sections, NPM_PKG_NAME };
}

/**
 * @typedef {{ pkgVersion: string, configDir: string, npmPkgName: string }} HelpContext
 */

/**
 * @param {HelpContext} ctx
 * @returns {string[]}
 */
function buildBannerLines(ctx) {
  return [
    `{bold}Skillforge{/bold}  {dim}local SKILL.md orchestration{/dim}`,
    `{dim}Version{/dim} ${ctx.pkgVersion}{dim}  ·  Enterprise automation and MCP hosts share the same Python engine.{/dim}`,
    `{dim}State directory{/dim}  ${ctx.configDir}`,
  ];
}

/**
 * @param {HelpContext} ctx
 * @returns {string[]}
 */
function buildTopSummaryLines() {
  return [
    `{dim}PRIMARY INTEGRATION (production workloads):{/dim} {bold}stdio MCP{/bold} — {dim}configure{/dim} {cyan}skillforge mcp config{/cyan} {dim}, then restart the IDE / agent.{/dim}`,
    `{dim}TERMINAL (operators, scripting, CI):{/dim} {dim}routing, observability, and{/dim} {cyan}skillforge tools{/cyan} {dim}(MCP tool parity).{/dim}`,
  ];
}

/**
 * @param {HelpContext} ctx
 * @returns {string[]}
 */
function buildFooterLines(ctx) {
  return [
    `{bold}First run{/bold}  {cyan}skillforge install{/cyan} {dim}or{/dim} {cyan}npx -y ${ctx.npmPkgName} install{/cyan}`,
    `{dim}  Auto-provisions ~/.skillforge/venv · optional Cursor + Claude Code /skillforge commands ` +
      '(SKILLFORGE_SKIP_CURSOR_SETUP, SKILLFORGE_SKIP_CLAUDE_CODE_SETUP).{/dim}',
    `{bold}Documentation{/bold}  README.md + docs/ · npm/GitHub (${ctx.npmPkgName})`,
    '{dim}Richer layout: skillforge help --ui  ·  section menu: skillforge help --browse{/dim}',
  ];
}

module.exports = {
  buildHelpModel,
  buildBannerLines,
  buildTopSummaryLines,
  buildFooterLines,
};
