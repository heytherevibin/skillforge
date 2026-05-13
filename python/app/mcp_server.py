"""
MCP server for skillforge.

Exposes skill routing as MCP tools so MCP-aware clients (Claude Desktop,
Claude Code, Cursor, etc.) can use the orchestrator without running the
HTTP server.

Tools exposed:
  route_skills / skillforge_bootstrap — routing (+ optional project materialize).
  materialize_project — .cursor/rules, docs/SKILLFORGE-PRD.md, CLAUDE.md block.
  list_skills, skill_feedback, skill_referenced, disable_skill.

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
    build_router_and_skills,
    init_db,
    load_all_skills,
    log_event,
    run_route_turn,
    set_skill_disabled,
    skill_catalog_manifest,
    update_skill_stat,
    Router,
)
from app.materialize import materialize_project_files


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

    def _mcp_user_id(self, args: dict) -> str:
        """Per-tool user namespace for weights/sessions/events (aligned with HTTP bearer user id)."""
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
        skills = load_all_skills()
        embed_model = self.router.embed_model
        anthropic = self.router.anthropic
        self.router = Router(skills, embed_model, anthropic)
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
        caps: dict = {"tools": {}}
        if _mcp_tools_list_changed_capability():
            caps["tools"]["listChanged"] = True
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": caps,
            "serverInfo": {"name": "skillforge", "version": "0.2.0"},
        }

    def handle_tools_list(self, params):
        return {
            "tools": [
                {
                    "name": "route_skills",
                    "description": (
                        "Route the user's prompt to the most relevant skills from the catalog "
                        "and return their full SKILL.md bodies. The client should inject the "
                        "returned content into the LLM's context. Returns up to 7 skills. "
                        "Pass project_root (workspace path) for per-repo SQLite in .skillforge/ "
                        "and learning; else use env SKILLFORGE_PROJECT_ROOT or global data dir. "
                        "Optional session_id for reroute stats; optional user_id for multi-user."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "prompt": {"type": "string", "description": "The user's prompt or task description"},
                            "project_root": {
                                "type": "string",
                                "description": "Repo/workspace root — stores orchestrator state in .skillforge/",
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
                                "description": "Logical user id for weights/sessions/events (same as HTTP user id string)",
                            },
                        },
                        "required": ["prompt"],
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
                        "Write project-local Skillforge files: .cursor/rules/skillforge.mdc, "
                        "docs/SKILLFORGE-PRD.md, and a CLAUDE.md section. "
                        "Pass project_root (workspace path) and skill_names from route_skills. "
                        "Hosts must supply project_root; MCP does not infer cwd."
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
                            "merge": {
                                "type": "boolean",
                                "description": "If false and .cursor/rules/skillforge.mdc exists, skip overwriting that file",
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
                        },
                        "required": ["prompt", "project_root"],
                    },
                },
            ]
        }

    async def handle_tools_call(self, params):
        name = params.get("name")
        args = params.get("arguments", {})

        if name == "route_skills":
            return await self._tool_route_skills(args)
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
        raise ValueError(f"Unknown tool: {name}")

    async def _tool_route_skills(self, args):
        prompt = args.get("prompt", "")
        conversation = args.get("conversation", [])
        session_id = args.get("session_id") or None
        user_id = self._mcp_user_id(args)
        if not prompt.strip():
            return {"content": [{"type": "text", "text": "No prompt provided."}]}
        con = self._get_con(args)
        result = await run_route_turn(
            con,
            self.router,
            prompt,
            conversation,
            user_id=user_id,
            session_id=session_id,
        )
        picked_names = result["picked_names"]
        reasoning = result["reasoning"]
        pr = self._project_root_from_args(args)
        db_path = resolve_orchestrator_db(pr)
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
                }
                (d / "last_route.json").write_text(json.dumps(snap, indent=2), encoding="utf-8")
            except OSError:
                pass

        # Build response: a header explaining what was loaded, then the skill bodies
        blocks = [
            f"# Skillforge — routed {len(picked_names)} skill(s)",
            f"_DB:_ `{db_path}`",
            f"_Reasoning: {reasoning}_" if reasoning else "",
            "",
        ]
        for n in picked_names:
            s = self.skills.get(n)
            if s:
                blocks.append(f"---\n## Skill: {s.name}\n\n{s.body}\n")
        if not picked_names:
            blocks.append("_No skills matched this prompt closely enough to load._")
        return {
            "content": [{"type": "text", "text": "\n".join(b for b in blocks if b is not None)}],
            "_meta": {
                "picked": picked_names,
                "reasoning": reasoning,
                "session_id": result["session_id"],
                "user_id": user_id,
                "rerouted": result["rerouted"],
                "change_pct": round(result["change"] * 100, 1),
                "route_ms": round(result["route_ms"], 1),
                "orchestrator_db": str(db_path),
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
            out = materialize_project_files(root, valid, desc, merge=bool(merge))
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
            }
        )
        if route.get("isError"):
            return route
        picked = (route.get("_meta") or {}).get("picked") or []
        mat = self._tool_materialize_project(
            {"project_root": root, "skill_names": picked, "merge": merge}
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
