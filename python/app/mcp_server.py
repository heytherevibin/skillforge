"""
MCP server for skillforge.

Exposes skill routing as MCP tools so MCP-aware clients (Claude Desktop,
Claude Code, Cursor, etc.) can use the orchestrator without running the
HTTP server.

Tools exposed:
  route_skills(prompt) → returns the SKILL.md bodies of routed skills as text.
                         The client injects this into its own context.
  list_skills()        → returns the catalog with descriptions.
  feedback(...)        → reports thumbs up/down for the learning loop.

Run as: python -m app.mcp_server
Speaks MCP over stdio (the protocol's standard transport for local servers).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# Reuse loader/router/db from the main app
from app.main import (
    load_all_skills,
    init_db,
    Router,
    update_skill_stat,
    set_skill_disabled,
    BUNDLED_SKILLS,
    USER_SKILLS,
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
        self.con = None
        self.initialized = False

    async def setup(self):
        # Heavy imports happen here so the process starts fast and MCP
        # initialize handshake completes before we block on model load.
        from anthropic import AsyncAnthropic
        from sentence_transformers import SentenceTransformer

        print("[skillforge-mcp] Loading skills...", file=sys.stderr)
        skills = load_all_skills()
        print(f"[skillforge-mcp] Loaded {len(skills)} skills from "
              f"bundled={BUNDLED_SKILLS} user={USER_SKILLS}", file=sys.stderr)

        embed_model = SentenceTransformer(
            os.getenv("SKILLFORGE_EMBED_MODEL", "all-MiniLM-L6-v2")
        )
        anthropic = AsyncAnthropic()
        self.router = Router(skills, embed_model, anthropic)
        self.skills = {s.name: s for s in skills}
        self.con = init_db()

    # ---- MCP handlers ----

    def handle_initialize(self, params):
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "skillforge", "version": "0.1.0"},
        }

    def handle_tools_list(self, params):
        return {
            "tools": [
                {
                    "name": "route_skills",
                    "description": (
                        "Route the user's prompt to the most relevant skills from the catalog "
                        "and return their full SKILL.md bodies. The client should inject the "
                        "returned content into the LLM's context. Returns up to 7 skills."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "prompt": {"type": "string", "description": "The user's prompt or task description"},
                            "conversation": {
                                "type": "array",
                                "description": "Optional recent messages for context",
                                "items": {"type": "object"},
                            },
                        },
                        "required": ["prompt"],
                    },
                },
                {
                    "name": "list_skills",
                    "description": "List all available skills with their descriptions and usage stats.",
                    "inputSchema": {"type": "object", "properties": {}},
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
                        },
                        "required": ["skill_name", "disabled"],
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
            return self._tool_list_skills()
        if name == "skill_feedback":
            return self._tool_skill_feedback(args)
        if name == "disable_skill":
            return self._tool_disable_skill(args)
        raise ValueError(f"Unknown tool: {name}")

    async def _tool_route_skills(self, args):
        prompt = args.get("prompt", "")
        conversation = args.get("conversation", [])
        if not prompt.strip():
            return {"content": [{"type": "text", "text": "No prompt provided."}]}
        candidates = self.router.shortlist(prompt, self.con)
        picked_names, reasoning = await self.router.pick_final(prompt, conversation, candidates)
        for n in picked_names:
            update_skill_stat(self.con, n, "uses", 1)

        # Build response: a header explaining what was loaded, then the skill bodies
        blocks = [
            f"# Skillforge — routed {len(picked_names)} skill(s)",
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
            "_meta": {"picked": picked_names, "reasoning": reasoning},
        }

    def _tool_list_skills(self):
        out = []
        for name, s in sorted(self.skills.items()):
            cur = self.con.execute(
                "SELECT uses, referenced, thumbs_up, thumbs_down, disabled FROM skill_weights WHERE skill_name = ?",
                (name,),
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
        if name not in self.skills:
            return {"content": [{"type": "text", "text": f"Unknown skill: {name}"}], "isError": True}
        field = "thumbs_up" if thumbs > 0 else "thumbs_down"
        update_skill_stat(self.con, name, field, 1)
        return {"content": [{"type": "text", "text": f"Recorded {'👍' if thumbs > 0 else '👎'} for {name}"}]}

    def _tool_disable_skill(self, args):
        name = args.get("skill_name")
        disabled = args.get("disabled", False)
        if name not in self.skills:
            return {"content": [{"type": "text", "text": f"Unknown skill: {name}"}], "isError": True}
        set_skill_disabled(self.con, name, disabled)
        return {"content": [{"type": "text", "text": f"{'Disabled' if disabled else 'Enabled'} {name}"}]}

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
                result = self.handle_tools_list(params)
            elif method == "tools/call":
                if not self.initialized:
                    await self.setup()
                    self.initialized = True
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
