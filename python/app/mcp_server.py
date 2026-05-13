"""
MCP server for skillforge.

Exposes skill routing as MCP tools so MCP-aware clients (Claude Desktop,
Claude Code, Cursor, etc.) can use the orchestrator locally.

Tools exposed:
  route_skills / skillforge_bootstrap — routing (+ optional project materialize).
  search_skills / explain_route / get_skill — retrieval, debugging, deterministic fetch.
  materialize_project — .cursor/rules, docs/SKILLFORGE-PRD.md, CLAUDE.md block.
  list_skills, skill_feedback, skill_referenced, disable_skill.
  capabilities — bundled snapshot (semver, MCP schema version, tool names, user_env_profile commands, router_snapshot) for session start.
  get_router_status, project_index_status, weights_snapshot, events_recent — read-only operator introspection.

Run as: python -m app.mcp_server
Speaks MCP over stdio (the protocol's standard transport for local servers).
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

from app.db_paths import resolve_orchestrator_db
from app.main import (
    TOP_K_CANDIDATES,
    SKILLFORGE_ROUTER_MODE,
    build_router_and_skills,
    format_context_items_markdown,
    init_db,
    load_all_skills,
    log_event,
    run_route_turn,
    set_skill_disabled,
    skill_catalog_manifest,
    update_skill_stat,
    Router,
)
from app.explain_route import compute_explain_route
from app.materialize import materialize_project_files, resolve_materialize_hosts_argument
from app.mcp_contract import MCP_RESPONSE_SCHEMA_VERSION, build_route_skills_meta
from app.mcp_operator import (
    EVENTS_META_ROW_CAP,
    build_capabilities_bundle,
    build_router_status_dict,
    events_recent_rows,
    format_capabilities_markdown,
    format_events_markdown,
    format_project_index_markdown,
    format_router_status_markdown,
    project_index_status_dict,
)
from app.npm_pkg_version import published_package_version
from app.redaction import redaction_enabled, redact_display_path
from app.route_policies import (
    load_route_policies_config,
    merge_project_notes_into_route_query,
    parse_routing_overlay,
)
from app.routing_signals import build_route_query_text, skill_routing_card


def _env_truthy(name: str, default: str = "1") -> bool:
    return os.getenv(name, default).strip().lower() not in ("0", "false", "no", "")


def _hot_reload_enabled() -> bool:
    return _env_truthy("SKILLFORGE_SKILL_HOT_RELOAD", "1")


def _watch_interval_sec() -> float:
    raw = os.getenv("SKILLFORGE_WATCH_SKILLS_INTERVAL", "30")
    try:
        return float(raw)
    except ValueError:
        return 30.0


def _mcp_tools_list_changed_capability() -> bool:
    """Advertise listChanged only when we run a background poll that may emit notifications."""
    return (
        _hot_reload_enabled()
        and _env_truthy("SKILLFORGE_MCP_LIST_CHANGED", "1")
        and _watch_interval_sec() > 0
    )


class MCPServer:
    """Minimal MCP server speaking JSON-RPC 2.0 over stdio.

    Implements just the methods needed for a tool server:
      - initialize
      - tools/list
      - tools/call
      - notifications/initialized (no-op)
    """

    def __init__(self):
        self.skills = None
        self.router = None
        self.initialized = False
        self._catalog_manifest: tuple[tuple[str, int], ...] | None = None
        self._reload_lock: asyncio.Lock | None = None
        self._db_cache: dict[str, sqlite3.Connection] = {}
        self._mcp_client_name = ""
        self._mcp_client_title = ""

    def _mcp_user_id(self, args: dict) -> str:
        """Per-tool user namespace for weights/sessions/events."""
        raw = (
            args.get("user_id")
            or os.getenv("SKILLFORGE_MCP_USER_ID", "")
            or ""
        )
        return str(raw).strip()

    def _project_root_from_args(self, args: dict) -> str | None:
        raw = args.get("project_root")
        if raw is not None and str(raw).strip():
            return str(raw).strip()
        env = os.getenv("SKILLFORGE_PROJECT_ROOT", "").strip()
        return env or None

    @staticmethod
    def _include_project_rag_from_args(args: dict) -> bool:
        v = args.get("include_project_rag")
        if v is True:
            return True
        if isinstance(v, str) and v.strip().lower() in ("1", "true", "yes"):
            return True
        return False

    def _get_con(self, args: dict):
        path = resolve_orchestrator_db(self._project_root_from_args(args))
        key = str(path)
        if key not in self._db_cache:
            self._db_cache[key] = init_db(path)
        return self._db_cache[key]

    async def setup(self):
        if self._reload_lock is None:
            self._reload_lock = asyncio.Lock()

        self.router, self.skills = await asyncio.to_thread(
            build_router_and_skills, log=True, log_prefix="[skillforge-mcp]"
        )
        self._catalog_manifest = skill_catalog_manifest()
        if _hot_reload_enabled():
            interval = _watch_interval_sec()
            if interval > 0:
                asyncio.create_task(self._watch_skills_poll_loop(interval))

    def _reload_catalog_sync(self):
        skills = load_all_skills(manifest_log_prefix="[skillforge-mcp]")
        embed_model = self.router.embed_model
        router_llm = self.router.router_llm
        self.router = Router(skills, embed_model, router_llm)
        self.skills = {s.name: s for s in skills}
        print(f"[skillforge-mcp] Hot-reloaded {len(skills)} skills", file=sys.stderr)

    def _emit_tools_list_changed(self):
        if not _mcp_tools_list_changed_capability():
            return
        note = {
            "jsonrpc": "2.0",
            "method": "notifications/tools/list_changed",
            "params": {},
        }
        sys.stdout.write(json.dumps(note) + "\n")
        sys.stdout.flush()

    async def _reload_if_stale(self, *, emit_notification: bool) -> bool:
        if not _hot_reload_enabled() or self.router is None:
            return False
        m = skill_catalog_manifest()
        if m == self._catalog_manifest:
            return False
        if self._reload_lock is None:
            self._reload_lock = asyncio.Lock()
        async with self._reload_lock:
            m2 = skill_catalog_manifest()
            if m2 == self._catalog_manifest:
                return False
            await asyncio.to_thread(self._reload_catalog_sync)
            self._catalog_manifest = skill_catalog_manifest()
        if emit_notification:
            self._emit_tools_list_changed()
        return True

    async def _watch_skills_poll_loop(self, interval: float):
        while True:
            await asyncio.sleep(interval)
            try:
                if not _hot_reload_enabled():
                    return
                await self._reload_if_stale(emit_notification=True)
            except Exception as e:
                print(f"[skillforge-mcp] watch skills: {e}", file=sys.stderr)

    # ---- MCP handlers ----

    def handle_initialize(self, params):
        ci = params.get("clientInfo")
        if isinstance(ci, dict):
            self._mcp_client_name = str(ci.get("name") or "").strip()
            self._mcp_client_title = str(ci.get("title") or "").strip()
        else:
            self._mcp_client_name = ""
            self._mcp_client_title = ""
        caps: dict = {"tools": {}}
        if _mcp_tools_list_changed_capability():
            caps["tools"]["listChanged"] = True
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": caps,
            "serverInfo": {"name": "skillforge", "version": published_package_version()},
        }

    def handle_tools_list(self, params):
        return {
            "tools": [
                {
                    "name": "route_skills",
                    "description": (
                        "Default SKILLFORGE_ROUTER_MODE=host (two-step, no in-process router LLM): (1) call with prompt "
                        "only — returns a tight numbered shortlist + session_id; (2) call again with the same prompt "
                        "and picked_names (JSON array of exact catalog ids from the list) to load SKILL.md chunks. "
                        "Set SKILLFORGE_ROUTER_MODE=auto (or embedding/full) for one-call routing when configured. "
                        "Optional conversation, project_root, include_project_rag. picked_names may also be passed "
                        "in embedding/full/auto to skip auto-pick and use the host-provided list."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "prompt": {"type": "string", "description": "The user's prompt or task description"},
                            "picked_names": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": (
                                    "Host-chosen skill ids from the shortlist (same prompt as step 1). "
                                    "Omit on first host-mode call; required for finalize after shortlist."
                                ),
                            },
                            "project_root": {
                                "type": "string",
                                "description": "Repo/workspace root — stores orchestrator state in .skillforge/",
                            },
                            "include_project_rag": {
                                "type": "boolean",
                                "description": (
                                    "If true, append top chunks from the project index in the same DB "
                                    "(see skillforge index). Requires project_root."
                                ),
                                "default": False,
                            },
                            "conversation": {
                                "type": "array",
                                "description": "Optional recent messages for context",
                                "items": {"type": "object"},
                            },
                            "session_id": {
                                "type": "string",
                                "description": "Stable id for this chat; reuse across turns for reroute detection",
                            },
                            "user_id": {
                                "type": "string",
                                "description": "Logical user id for weights/sessions/events",
                            },
                        },
                        "required": ["prompt"],
                    },
                },
                {
                    "name": "search_skills",
                    "description": (
                        "Embedding-only retrieval: top skills for a query with similarity scores "
                        "and descriptions (no Haiku, no full route). Use to explore the catalog."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query or task text"},
                            "limit": {
                                "type": "integer",
                                "description": f"Max skills to return (default {TOP_K_CANDIDATES})",
                            },
                            "project_root": {"type": "string"},
                            "user_id": {"type": "string"},
                        },
                        "required": ["query"],
                    },
                },
                {
                    "name": "explain_route",
                    "description": (
                        "Debug routing: embedding facets for the shortlist (same query text as route_skills when "
                        "`conversation` is passed — conversation-aware when SKILLFORGE_ROUTER_CONV_MAX_TURNS > 0), "
                        "optional Haiku rerank, Haiku/embedding-only pick with reasoning, and policy merge audit. "
                        "Does not write sessions or increment uses."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "prompt": {"type": "string"},
                            "conversation": {"type": "array", "items": {"type": "object"}},
                            "limit": {
                                "type": "integer",
                                "description": "Max shortlist rows in facets (default TOP_K)",
                            },
                            "project_root": {"type": "string"},
                            "user_id": {"type": "string"},
                        },
                        "required": ["prompt"],
                    },
                },
                {
                    "name": "get_skill",
                    "description": (
                        "Load one skill by name: full SKILL.md body, short summary (~8k opener), "
                        "or routing `card` (title/description/triggers only). "
                        "Use for deterministic workflows when you already know the skill name."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "skill_name": {"type": "string"},
                            "format": {
                                "type": "string",
                                "enum": ["card", "summary", "full"],
                                "description": (
                                    "card = routing-style card (minimal tokens); summary = description + first ~8k of body; "
                                    "full = entire SKILL.md body"
                                ),
                                "default": "full",
                            },
                            "max_chars": {
                                "type": "integer",
                                "description": "If > 0, truncate body to this many characters",
                                "default": 0,
                            },
                        },
                        "required": ["skill_name"],
                    },
                },
                {
                    "name": "list_skills",
                    "description": (
                        "List all available skills with descriptions and usage stats. "
                        "Optional project_root (or SKILLFORGE_PROJECT_ROOT) selects per-repo DB; else global."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "project_root": {"type": "string"},
                            "user_id": {"type": "string"},
                        },
                    },
                },
                {
                    "name": "skill_feedback",
                    "description": (
                        "Report thumbs up (+1) or down (-1) for a skill, feeding the learning loop. "
                        "Use after observing whether a routed skill actually helped."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "skill_name": {"type": "string"},
                            "thumbs": {"type": "integer", "enum": [-1, 1]},
                            "project_root": {"type": "string"},
                            "user_id": {"type": "string"},
                            "session_id": {"type": "string", "description": "Optional; stored in events when set"},
                        },
                        "required": ["skill_name", "thumbs"],
                    },
                },
                {
                    "name": "disable_skill",
                    "description": "Disable (or re-enable) a skill from being routed to.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "skill_name": {"type": "string"},
                            "disabled": {"type": "boolean"},
                            "project_root": {"type": "string"},
                            "user_id": {"type": "string"},
                        },
                        "required": ["skill_name", "disabled"],
                    },
                },
                {
                    "name": "skill_referenced",
                    "description": (
                        "Record that a routed skill was used in the model output (updates referenced count + weight). "
                        "Call when the assistant clearly applied a skill returned by route_skills."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "skill_name": {"type": "string"},
                            "project_root": {"type": "string"},
                            "user_id": {"type": "string"},
                        },
                        "required": ["skill_name"],
                    },
                },
                {
                    "name": "materialize_project",
                    "description": (
                        "Write project-local Skillforge files under project_root. Default hosts=auto: SKILLFORGE_MATERIALIZE_HOSTS "
                        "if set, else infer Cursor vs Claude from MCP initialize clientInfo, else both. Cursor "
                        "(.cursor/rules + .cursor/commands), Claude Code (.claude/commands), docs/SKILLFORGE-PRD.md, "
                        "and CLAUDE.md markers. hosts=cursor: Cursor + docs only. hosts=claude_code: Claude + docs + CLAUDE.md "
                        "(no .cursor/). hosts=both: write all host trees. With hosts=auto, SKILLFORGE_MATERIALIZE_HOSTS overrides "
                        "client inference when set. Pass skill_names from route_skills."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "project_root": {"type": "string", "description": "Absolute or relative path to the repo root"},
                            "skill_names": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Skill names from the last route_skills result",
                            },
                            "hosts": {
                                "type": "string",
                                "enum": ["auto", "both", "cursor", "claude_code"],
                                "default": "auto",
                                "description": (
                                    "`auto`: SKILLFORGE_MATERIALIZE_HOSTS if set (both|cursor|claude_code), else MCP clientInfo "
                                    "name/title (cursor / claude), else both."
                                ),
                            },
                            "merge": {
                                "type": "boolean",
                                "description": (
                                "If false and a targeted file already exists (.cursor/rules/skillforge.mdc, "
                                ".cursor/commands/skillforge.md, or .claude/commands/skillforge.md), skip overwriting it "
                                "for hosts that apply."
                                ),
                                "default": True,
                            },
                        },
                        "required": ["project_root", "skill_names"],
                    },
                },
                {
                    "name": "skillforge_bootstrap",
                    "description": (
                        "One-shot: route_skills for the prompt, then materialize_project into project_root. "
                        "Same args as route_skills plus project_root and optional merge."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "prompt": {"type": "string"},
                            "project_root": {"type": "string"},
                            "conversation": {"type": "array", "items": {"type": "object"}},
                            "session_id": {"type": "string"},
                            "user_id": {"type": "string"},
                            "merge": {"type": "boolean", "default": True},
                            "include_project_rag": {
                                "type": "boolean",
                                "description": "Same as route_skills: merge indexed project file chunks into context.",
                                "default": False,
                            },
                            "hosts": {
                                "type": "string",
                                "enum": ["auto", "both", "cursor", "claude_code"],
                                "default": "auto",
                                "description": "Passed to materialize_project after route (same semantics as materialize_project).",
                            },
                        },
                        "required": ["prompt", "project_root"],
                    },
                },
                {
                    "name": "capabilities",
                    "description": (
                        "Session bootstrap: MCP response schema version, package semver from package.json (or env override), "
                        "ordered MCP tool names, progressive loading hints (`get_skill` formats), manifest/replay/`user_env_profile` "
                        "CLI pointers (~/.skillforge/env `config path|init|validate`), and router_snapshot matching get_router_status. Read-only."
                    ),
                    "inputSchema": {"type": "object", "properties": {}},
                },
                {
                    "name": "get_router_status",
                    "description": (
                        "Read-only: effective SKILLFORGE_ROUTER_MODE, hybrid + rerank toggles from env, embed/router "
                        "model ids, shortlist/active caps, and whether Anthropic routing is wired (depends on MCP "
                        "process env)."
                    ),
                    "inputSchema": {"type": "object", "properties": {}},
                },
                {
                    "name": "project_index_status",
                    "description": (
                        "Read-only: counts and last index metadata from the project orchestrator DB "
                        "(requires project_root or SKILLFORGE_PROJECT_ROOT). No network."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "project_root": {
                                "type": "string",
                                "description": "Workspace root that owns .skillforge/orchestrator.db",
                            },
                        },
                    },
                },
                {
                    "name": "weights_snapshot",
                    "description": (
                        "Read-only: export learned skill_weights for this user_id + DB (same shape as "
                        "`skillforge weights export`). Optional project_root / user_id."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "project_root": {"type": "string"},
                            "user_id": {"type": "string"},
                        },
                    },
                },
                {
                    "name": "events_recent",
                    "description": (
                        "Read-only: recent SQLite events (route, host_shortlist, feedback, …) for user_id, "
                        "newest first. Markdown lists at most 150 rows; `_meta.rows` JSON payloads cap at 100. "
                        "Optional event_type filter."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "project_root": {"type": "string"},
                            "user_id": {"type": "string"},
                            "limit": {
                                "type": "integer",
                                "description": "Max rows fetched from SQLite (default 25, max 500). Preview/Meta caps apply separately.",
                                "default": 25,
                            },
                            "event_type": {
                                "type": "string",
                                "description": "Optional exact event_type filter (e.g. route, host_shortlist)",
                            },
                        },
                    },
                },
            ]
        }

    async def handle_tools_call(self, params):
        name = params.get("name")
        args = params.get("arguments", {})

        if name == "route_skills":
            return await self._tool_route_skills(args)
        if name == "search_skills":
            return self._tool_search_skills(args)
        if name == "explain_route":
            return await self._tool_explain_route(args)
        if name == "get_skill":
            return self._tool_get_skill(args)
        if name == "list_skills":
            return self._tool_list_skills(args)
        if name == "skill_feedback":
            return self._tool_skill_feedback(args)
        if name == "disable_skill":
            return self._tool_disable_skill(args)
        if name == "skill_referenced":
            return self._tool_skill_referenced(args)
        if name == "materialize_project":
            return self._tool_materialize_project(args)
        if name == "skillforge_bootstrap":
            return await self._tool_skillforge_bootstrap(args)
        if name == "capabilities":
            return self._tool_capabilities(args)
        if name == "get_router_status":
            return self._tool_get_router_status(args)
        if name == "project_index_status":
            return self._tool_project_index_status(args)
        if name == "weights_snapshot":
            return self._tool_weights_snapshot(args)
        if name == "events_recent":
            return self._tool_events_recent(args)
        raise ValueError(f"Unknown tool: {name}")

    async def _tool_route_skills(self, args):
        prompt = args.get("prompt", "")
        conversation = args.get("conversation", [])
        session_id = args.get("session_id") or None
        user_id = self._mcp_user_id(args)
        pr = self._project_root_from_args(args)
        db_path = resolve_orchestrator_db(pr)

        if not prompt.strip():
            err_text = "No prompt provided."
            return {
                "content": [{"type": "text", "text": err_text}],
                "isError": True,
                "_meta": build_route_skills_meta(
                    result={"candidates": []},
                    picked_names=[],
                    user_id=user_id,
                    db_path=db_path,
                    skills_map=self.skills or {},
                    response_text=err_text,
                    error="empty_prompt",
                ),
            }

        picked_names_from_host_supplied = "picked_names" in args
        if picked_names_from_host_supplied:
            raw_pn = args.get("picked_names")
            if isinstance(raw_pn, list):
                picked_names_from_host = [str(x) for x in raw_pn if x is not None]
            else:
                picked_names_from_host = []
        else:
            picked_names_from_host = None

        con = self._get_con(args)
        result = await run_route_turn(
            con,
            self.router,
            prompt,
            conversation,
            user_id=user_id,
            session_id=session_id,
            project_root=pr,
            include_project_rag=self._include_project_rag_from_args(args),
            picked_names_from_host=picked_names_from_host,
            picked_names_from_host_supplied=picked_names_from_host_supplied,
        )
        picked_names = result["picked_names"]
        reasoning = result["reasoning"]
        context_items = result.get("context_items") or []
        if pr:
            try:
                d = Path(pr).expanduser().resolve() / ".skillforge"
                d.mkdir(parents=True, exist_ok=True)
                snap = {
                    "ts": time.time(),
                    "session_id": result["session_id"],
                    "picked": picked_names,
                    "reasoning": reasoning,
                    "route_ms": round(result["route_ms"], 1),
                    "user_id": user_id,
                    "schema_version": MCP_RESPONSE_SCHEMA_VERSION,
                    "context_mode": self.router.context_mode,
                    "context_items_count": len(context_items),
                    "project_rag_items_count": (result.get("event") or {}).get("project_rag_items_count", 0),
                    "host_pick_shortlist": bool(result.get("host_pick_shortlist")),
                }
                (d / "last_route.json").write_text(json.dumps(snap, indent=2), encoding="utf-8")
            except OSError:
                pass

        db_disp = redact_display_path(db_path) if redaction_enabled() else str(db_path)
        if result.get("host_pick_shortlist"):
            response_text = (result.get("host_pick_markdown") or "").strip() + (
                f"\n\n---\n_session_id:_ `{result['session_id']}` · _orchestrator:_ `{db_disp}`"
            )
            blocks = [response_text]
        else:
            blocks = [
                f"# Skillforge — routed {len(picked_names)} skill(s); context=`{self.router.context_mode}`",
                f"_DB:_ `{db_disp}`",
                f"_Reasoning: {reasoning}_" if reasoning else "",
                "",
            ]
            if context_items:
                blocks.append(format_context_items_markdown(context_items))
            elif not picked_names:
                blocks.append("_No skills matched this prompt closely enough to load._")
        response_text = "\n".join(b for b in blocks if b is not None)
        meta = build_route_skills_meta(
            result=result,
            picked_names=picked_names,
            user_id=user_id,
            db_path=db_path,
            skills_map=self.skills,
            response_text=response_text,
            context_items=context_items,
            fusion=(result.get("event") or {}).get("context_fusion"),
            context_redaction=(result.get("event") or {}).get("context_redaction"),
        )
        if result.get("host_pick_shortlist"):
            meta["host_pick_shortlist"] = True
            meta["host_pick_candidates"] = result.get("host_pick_candidates") or []
        return {
            "content": [{"type": "text", "text": response_text}],
            "_meta": meta,
        }

    def _tool_search_skills(self, args):
        query = (args.get("query") or "").strip()
        user_id = self._mcp_user_id(args)
        pr = self._project_root_from_args(args)
        db_path = resolve_orchestrator_db(pr)
        if not query:
            return {
                "content": [{"type": "text", "text": "query is required."}],
                "isError": True,
            }
        try:
            limit = int(args.get("limit") or TOP_K_CANDIDATES)
        except (TypeError, ValueError):
            limit = TOP_K_CANDIDATES
        limit = max(1, min(limit, 50))
        con = self._get_con(args)
        policies_cfg = load_route_policies_config(pr)
        overlay_audit = []
        exclude_skills, routing_boosts, project_notes = parse_routing_overlay(
            policies_cfg,
            by_name=self.router._by_name,
            audit_out=overlay_audit,
        )
        q2 = merge_project_notes_into_route_query(query, project_notes, pr)
        facets = self.router.shortlist_with_facets(
            q2,
            con,
            k=limit,
            user_id=user_id,
            exclude_skills=exclude_skills,
            routing_boosts=routing_boosts,
        )
        lines = ["# search_skills — embedding shortlist", ""]
        for f in facets:
            lines.append(
                f"- **{f['name']}** (cos {f['cosine_similarity']}, score {f['routing_score']}): "
                f"{(f.get('description_preview') or '')[:220]}"
            )
        text = "\n".join(lines)
        return {
            "content": [{"type": "text", "text": text}],
            "_meta": {
                "schema_version": MCP_RESPONSE_SCHEMA_VERSION,
                "tool": "search_skills",
                "orchestrator_db": redact_display_path(db_path) if redaction_enabled() else str(db_path),
                "results": facets,
                "count": len(facets),
            },
        }

    async def _tool_explain_route(self, args):
        prompt = (args.get("prompt") or "").strip()
        conversation = args.get("conversation") or []
        user_id = self._mcp_user_id(args)
        pr = self._project_root_from_args(args)
        db_path = resolve_orchestrator_db(pr)
        if not prompt:
            return {
                "content": [{"type": "text", "text": "prompt is required."}],
                "isError": True,
            }
        try:
            limit = int(args.get("limit") or TOP_K_CANDIDATES)
        except (TypeError, ValueError):
            limit = TOP_K_CANDIDATES
        limit = max(1, min(limit, 50))
        con = self._get_con(args)
        body, explain = await compute_explain_route(
            self.router,
            con,
            prompt=prompt,
            conversation=conversation,
            limit=limit,
            user_id=user_id,
            project_root=pr,
            db_path=db_path,
        )
        return {"content": [{"type": "text", "text": body}], "_meta": explain}

    def _tool_get_skill(self, args):
        name = (args.get("skill_name") or "").strip()
        fmt_raw = (args.get("format") or "full").strip().lower()
        if fmt_raw in ("card", "minimal"):
            fmt = "card"
        elif fmt_raw == "summary":
            fmt = "summary"
        else:
            fmt = "full"
        max_chars = args.get("max_chars")
        try:
            mc = int(max_chars) if max_chars is not None else 0
        except (TypeError, ValueError):
            mc = 0
        if not name or name not in self.skills:
            return {
                "content": [{"type": "text", "text": f"Unknown skill: {name or '(empty)'}"}],
                "isError": True,
            }
        s = self.skills[name]
        if fmt == "card":
            body = skill_routing_card(s)
        elif fmt == "summary":
            body = f"{s.description}\n\n---\n\n{(s.body or '')[:8000]}"
        else:
            body = s.body or ""
        if mc > 0:
            body = body[:mc]
        header = f"# get_skill: `{name}`\n**Source:** {s.source} · **format:** {fmt}\n\n"
        text = header + body
        return {
            "content": [{"type": "text", "text": text}],
            "_meta": {
                "schema_version": MCP_RESPONSE_SCHEMA_VERSION,
                "tool": "get_skill",
                "skill_name": name,
                "source": s.source,
                "format": fmt,
                "chars": len(body),
            },
        }

    def _tool_list_skills(self, args):
        user_id = self._mcp_user_id(args)
        con = self._get_con(args)
        out = []
        for name, s in sorted(self.skills.items()):
            cur = con.execute(
                "SELECT uses, referenced, thumbs_up, thumbs_down, disabled FROM skill_weights "
                "WHERE user_id = ? AND skill_name = ?",
                (user_id, name),
            )
            row = cur.fetchone()
            uses, ref, up, down, disabled = row if row else (0, 0, 0, 0, 0)
            out.append({
                "name": name,
                "description": s.description[:200],
                "source": s.source,
                "uses": uses,
                "thumbs": up - down,
                "disabled": bool(disabled),
            })
        # Format as readable text for MCP clients
        lines = [f"# Skills ({len(out)} total)\n"]
        for sk in out:
            flag = " [DISABLED]" if sk["disabled"] else ""
            lines.append(f"**{sk['name']}**{flag} ({sk['source']}, used {sk['uses']}x): {sk['description']}")
        return {"content": [{"type": "text", "text": "\n".join(lines)}]}

    def _tool_skill_feedback(self, args):
        name = args.get("skill_name")
        thumbs = args.get("thumbs", 0)
        user_id = self._mcp_user_id(args)
        session_id = args.get("session_id") or ""
        con = self._get_con(args)
        if name not in self.skills:
            return {"content": [{"type": "text", "text": f"Unknown skill: {name}"}], "isError": True}
        field = "thumbs_up" if thumbs > 0 else "thumbs_down"
        update_skill_stat(con, name, field, 1, user_id=user_id)
        if session_id:
            log_event(
                con,
                session_id,
                "feedback",
                {"skill": name, "thumbs": thumbs},
                user_id=user_id,
            )
        return {"content": [{"type": "text", "text": f"Recorded {'👍' if thumbs > 0 else '👎'} for {name}"}]}

    def _tool_disable_skill(self, args):
        name = args.get("skill_name")
        disabled = args.get("disabled", False)
        user_id = self._mcp_user_id(args)
        con = self._get_con(args)
        if name not in self.skills:
            return {"content": [{"type": "text", "text": f"Unknown skill: {name}"}], "isError": True}
        set_skill_disabled(con, name, disabled, user_id=user_id)
        return {"content": [{"type": "text", "text": f"{'Disabled' if disabled else 'Enabled'} {name}"}]}

    def _tool_skill_referenced(self, args):
        name = args.get("skill_name")
        user_id = self._mcp_user_id(args)
        con = self._get_con(args)
        if name not in self.skills:
            return {"content": [{"type": "text", "text": f"Unknown skill: {name}"}], "isError": True}
        update_skill_stat(con, name, "referenced", 1, user_id=user_id)
        return {"content": [{"type": "text", "text": f"Recorded reference for {name}"}]}

    def _tool_materialize_project(self, args):
        root = (args.get("project_root") or "").strip()
        names_raw = args.get("skill_names") or []
        merge = args.get("merge", True)
        if not root:
            return {
                "content": [{"type": "text", "text": "project_root is required."}],
                "isError": True,
            }
        if not isinstance(names_raw, list):
            names_raw = []
        valid = [n for n in names_raw if isinstance(n, str) and n in self.skills]
        desc = {n: self.skills[n].description for n in valid}
        try:
            mh = args.get("hosts")
            if mh is None:
                mh_arg: str | None = None
            elif isinstance(mh, str):
                mh_arg = mh.strip() or None
            else:
                mh_arg = str(mh).strip() or None
            hosts_arg, hres = resolve_materialize_hosts_argument(
                mh_arg,
                client_name=getattr(self, "_mcp_client_name", ""),
                client_title=getattr(self, "_mcp_client_title", ""),
            )
            out = materialize_project_files(root, valid, desc, merge=bool(merge), hosts=hosts_arg)
            out.update(hres)
        except ValueError as e:
            return {"content": [{"type": "text", "text": str(e)}], "isError": True}
        lines = ["# Skillforge — materialized project files", "", "Written:", *[f"- {p}" for p in out["written"]], ""]
        return {"content": [{"type": "text", "text": "\n".join(lines)}], "_meta": out}

    async def _tool_skillforge_bootstrap(self, args):
        prompt = args.get("prompt", "")
        root = (args.get("project_root") or "").strip()
        conversation = args.get("conversation", [])
        session_id = args.get("session_id") or None
        user_id = self._mcp_user_id(args)
        merge = args.get("merge", True)
        if SKILLFORGE_ROUTER_MODE == "host":
            msg = (
                "skillforge_bootstrap does not support host routing (SKILLFORGE_ROUTER_MODE=host, the default). "
                "Set SKILLFORGE_ROUTER_MODE=embedding or auto for one-shot bootstrap, or call route_skills twice "
                "(shortlist then picked_names) and materialize_project yourself."
            )
            return {"content": [{"type": "text", "text": msg}], "isError": True}
        if not prompt.strip():
            return {"content": [{"type": "text", "text": "No prompt provided."}], "isError": True}
        if not root:
            return {
                "content": [{"type": "text", "text": "project_root is required."}],
                "isError": True,
            }
        route = await self._tool_route_skills(
            {
                "prompt": prompt,
                "project_root": root,
                "conversation": conversation,
                "session_id": session_id,
                "user_id": user_id,
                "include_project_rag": self._include_project_rag_from_args(args),
            }
        )
        if route.get("isError"):
            return route
        picked = (route.get("_meta") or {}).get("picked") or []
        mat = self._tool_materialize_project(
            {
                "project_root": root,
                "skill_names": picked,
                "merge": merge,
                "hosts": args.get("hosts"),
            }
        )
        if mat.get("isError"):
            return mat
        body = [
            route["content"][0]["text"],
            "---",
            mat["content"][0]["text"],
        ]
        return {
            "content": [{"type": "text", "text": "\n".join(body)}],
            "_meta": {
                "route": route.get("_meta"),
                "materialize": mat.get("_meta"),
            },
        }

    def _tool_capabilities(self, args):
        sc = len(self.skills) if self.skills else 0
        bundle = build_capabilities_bundle(self.router, skill_count=sc)
        text = format_capabilities_markdown(bundle)
        db_path = resolve_orchestrator_db(self._project_root_from_args(args))
        return {
            "content": [{"type": "text", "text": text}],
            "_meta": {
                "tool": "capabilities",
                "schema_version": MCP_RESPONSE_SCHEMA_VERSION,
                "bundle": bundle,
                "orchestrator_db": redact_display_path(db_path) if redaction_enabled() else str(db_path),
            },
        }

    def _tool_get_router_status(self, args):
        sc = len(self.skills) if self.skills else 0
        snap = build_router_status_dict(self.router, skill_count=sc)
        text = format_router_status_markdown(snap)
        db_path = resolve_orchestrator_db(self._project_root_from_args(args))
        return {
            "content": [{"type": "text", "text": text}],
            "_meta": {
                "tool": "get_router_status",
                "schema_version": MCP_RESPONSE_SCHEMA_VERSION,
                "snapshot": snap,
                "orchestrator_db": redact_display_path(db_path) if redaction_enabled() else str(db_path),
            },
        }

    def _tool_project_index_status(self, args):
        pr = self._project_root_from_args(args)
        if not pr:
            return {
                "content": [{
                    "type": "text",
                    "text": "project_root argument or SKILLFORGE_PROJECT_ROOT is required.",
                }],
                "isError": True,
            }
        con = self._get_con(args)
        stats = project_index_status_dict(con)
        root_path = Path(pr).expanduser().resolve()
        text = format_project_index_markdown(stats, root_path)
        db_path = resolve_orchestrator_db(pr)
        return {
            "content": [{"type": "text", "text": text}],
            "_meta": {
                "tool": "project_index_status",
                "schema_version": MCP_RESPONSE_SCHEMA_VERSION,
                "project_root": str(root_path),
                "orchestrator_db": redact_display_path(db_path) if redaction_enabled() else str(db_path),
                **stats,
            },
        }

    def _tool_weights_snapshot(self, args):
        from app.weights_cli import export_weights

        user_id = self._mcp_user_id(args)
        con = self._get_con(args)
        snap = export_weights(con, user_id)
        blob = json.dumps(snap, indent=2)
        db_path = resolve_orchestrator_db(self._project_root_from_args(args))
        return {
            "content": [{"type": "text", "text": f"# Skillforge — weights_snapshot\n\n```json\n{blob}\n```"}],
            "_meta": {
                "tool": "weights_snapshot",
                "schema_version": MCP_RESPONSE_SCHEMA_VERSION,
                "user_id": user_id,
                "row_count": len(snap.get("rows") or []),
                "orchestrator_db": redact_display_path(db_path) if redaction_enabled() else str(db_path),
            },
        }

    def _tool_events_recent(self, args):
        raw_lim = args.get("limit")
        try:
            limit = int(raw_lim) if raw_lim is not None else 25
        except (TypeError, ValueError):
            limit = 25
        et_raw = args.get("event_type")
        et = str(et_raw).strip() if isinstance(et_raw, str) and et_raw.strip() else None
        user_id = self._mcp_user_id(args)
        con = self._get_con(args)
        rows = events_recent_rows(con, limit=limit, user_id=user_id, event_type=et)
        text = format_events_markdown(rows)
        db_path = resolve_orchestrator_db(self._project_root_from_args(args))
        meta_cap = EVENTS_META_ROW_CAP
        meta_rows = rows[:meta_cap]
        return {
            "content": [{"type": "text", "text": text}],
            "_meta": {
                "tool": "events_recent",
                "schema_version": MCP_RESPONSE_SCHEMA_VERSION,
                "requested_limit": limit,
                "returned_count": len(rows),
                "user_id": user_id,
                "event_type_filter": et,
                "truncated_meta_rows": len(rows) > meta_cap,
                "rows": meta_rows,
                "orchestrator_db": redact_display_path(db_path) if redaction_enabled() else str(db_path),
            },
        }

    # ---- JSON-RPC dispatcher ----

    async def dispatch(self, request):
        method = request.get("method")
        params = request.get("params", {})
        req_id = request.get("id")

        try:
            if method == "initialize":
                result = self.handle_initialize(params)
            elif method == "notifications/initialized":
                # Notification, no response expected. Now finish heavy setup.
                if not self.initialized:
                    self.initialized = True
                    await self.setup()
                return None
            elif method == "tools/list":
                if not self.initialized:
                    await self.setup()
                    self.initialized = True
                await self._reload_if_stale(emit_notification=False)
                result = self.handle_tools_list(params)
            elif method == "tools/call":
                if not self.initialized:
                    await self.setup()
                    self.initialized = True
                await self._reload_if_stale(emit_notification=False)
                result = await self.handle_tools_call(params)
            else:
                if req_id is None:
                    return None
                return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}

            if req_id is None:
                return None  # notification
            return {"jsonrpc": "2.0", "id": req_id, "result": result}
        except Exception as e:
            if req_id is None:
                return None
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32603, "message": str(e)}}


async def main():
    server = MCPServer()
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        try:
            line = await reader.readline()
        except Exception:
            break
        if not line:
            break
        try:
            request = json.loads(line.decode().strip())
        except json.JSONDecodeError:
            continue
        response = await server.dispatch(request)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
