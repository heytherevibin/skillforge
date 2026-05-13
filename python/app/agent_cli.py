"""
``skillforge agent`` — OpenAI-compatible chat completions + Skillforge MCP tool handlers.

Requires ``openai`` and a reachable ``/v1`` API (Ollama, LiteLLM, OpenAI, etc.).
Read-only MCP tools only (no writes) for v1.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any


TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "route_skills",
            "description": "Route prompts to SKILL.md snippets (MCP parity). Supports host-mode two-step if ROUTER_MODE=host.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "project_root": {"type": "string"},
                    "session_id": {"type": "string"},
                    "user_id": {"type": "string"},
                    "picked_names": {"type": "array", "items": {"type": "string"}},
                    "include_project_rag": {"type": "boolean"},
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_skills",
            "description": "Embedding-only similarity shortlist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                    "project_root": {"type": "string"},
                    "user_id": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explain_route",
            "description": "Routing diagnostics without session commits.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "limit": {"type": "integer"},
                    "project_root": {"type": "string"},
                    "user_id": {"type": "string"},
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_skill",
            "description": "Fetch one SKILL by catalog id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string"},
                    "format": {"type": "string", "enum": ["card", "summary", "full"]},
                    "max_chars": {"type": "integer"},
                },
                "required": ["skill_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_skills",
            "description": "List catalog skills plus usage weights.",
            "parameters": {"type": "object", "properties": {"project_root": {"type": "string"}, "user_id": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "capabilities",
            "description": "Package + MCP semver + advertised tools bundle.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_router_status",
            "description": "Read-only routing env snapshot.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "project_index_status",
            "description": "Project RAG sqlite stats.",
            "parameters": {
                "type": "object",
                "properties": {"project_root": {"type": "string"}},
                "required": ["project_root"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "events_recent",
            "description": "Recent orchestrator SQLite events.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer"},
                    "event_type": {"type": "string"},
                    "project_root": {"type": "string"},
                    "user_id": {"type": "string"},
                },
            },
        },
    },
]


def _tool_payload_text(payload: dict[str, Any], *, limit: int) -> str:
    parts: list[str] = []
    for b in payload.get("content") or []:
        if isinstance(b, dict) and b.get("type") == "text":
            parts.append(str(b.get("text") or ""))
    txt = "\n".join(parts).strip()
    if payload.get("isError"):
        txt = "(tool_error)\n" + txt
    if len(txt) > limit:
        return txt[: limit - 80] + "\n… [truncated for context budget]"
    return txt


def _assistant_message_dict(msg: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"role": "assistant"}
    if msg.content:
        out["content"] = msg.content
    if getattr(msg, "tool_calls", None):
        tc_list = []
        for tc in msg.tool_calls:
            fn = getattr(tc, "function", None)
            if fn:
                tc_list.append({
                    "id": getattr(tc, "id", ""),
                    "type": "function",
                    "function": {
                        "name": getattr(fn, "name", "") or "",
                        "arguments": getattr(fn, "arguments", "") or "",
                    },
                })
        out["tool_calls"] = tc_list
    return out


def _inject_project_root(args_dict: dict[str, Any], pr: str) -> dict[str, Any]:
    merged = dict(args_dict)
    existing = merged.get("project_root")
    if isinstance(existing, str):
        stripped = existing.strip()
        merged["project_root"] = (stripped or pr) if pr else stripped
        return merged
    if pr:
        merged["project_root"] = pr
    return merged

async def run_agent_round(
    *,
    server: MCPServer,
    client: Any,
    model: str,
    messages: list[dict[str, Any]],
    default_project_root: str,
    inner_cap: int,
    max_rounds: int = 14,
) -> tuple[str | None, list[dict[str, Any]]]:
    reply: str | None = None
    for _ in range(max_rounds):
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.2,
        )
        msg = resp.choices[0].message
        messages.append(_assistant_message_dict(msg))

        tc_list = getattr(msg, "tool_calls", None)
        if not tc_list:
            reply = msg.content if msg.content else None
            return reply, messages

        for tc in tc_list:
            fn = getattr(tc, "function", None)
            name = (getattr(fn, "name", None) or "").strip()
            raw_args = getattr(fn, "arguments", None) if fn else "{}"
            try:
                parsed = json.loads(raw_args or "{}")
            except json.JSONDecodeError:
                parsed = {}
            merged = _inject_project_root(parsed, default_project_root)
            payload = await server.handle_tools_call({"name": name, "arguments": merged})
            text = _tool_payload_text(payload, limit=inner_cap)
            messages.append({
                "role": "tool",
                "tool_call_id": getattr(tc, "id", "") or "",
                "content": text,
            })
    reply = "(max_tool_rounds_reached)"
    return reply, messages


async def async_main() -> int:
    p = argparse.ArgumentParser(description="Skillforge standalone agent · OpenAI-compatible tools surface.")
    p.add_argument("--model", metavar="MODEL", default=os.getenv("SKILLFORGE_AGENT_MODEL", "").strip() or "")
    p.add_argument("--base-url", metavar="URL", default=os.getenv("OPENAI_API_BASE", "").strip() or "")
    p.add_argument(
        "--api-key",
        metavar="KEY",
        default=os.getenv("SKILLFORGE_AGENT_API_KEY") or os.getenv("OPENAI_API_KEY", ""),
    )
    p.add_argument("--project-root", metavar="PATH", default=os.getenv("SKILLFORGE_PROJECT_ROOT", "").strip() or "")
    p.add_argument("--prompt", metavar="TEXT", default="", help="One-shot user message then exit.")
    ns = p.parse_args()

    try:
        from openai import AsyncOpenAI
    except ImportError:
        sys.stderr.write(
            "Missing `openai` package — run `skillforge install` to refresh ~/.skillforge/venv deps, "
            "or pip install `openai` into that venv.\n",
        )
        return 2

    base = ns.base_url or os.getenv("SKILLFORGE_AGENT_API_BASE") or os.getenv("OPENAI_API_BASE", "").strip() or "http://localhost:11434/v1"
    api_key = (ns.api_key or "").strip() or "ollama"
    model = (ns.model or "").strip() or os.getenv("SKILLFORGE_AGENT_MODEL", "").strip() or os.getenv(
        "SKILLFORGE_OPENAI_ROUTER_MODEL", "").strip() or "llama3.2"

    inner_cap = max(2048, int(os.getenv("SKILLFORGE_AGENT_TOOL_CHAR_CAP", "12000")))
    proj = ns.project_root.strip()

    sys.stderr.write("[skillforge-agent] Starting MCP-backed tool runtime...\n")
    sys.stderr.flush()
    server = MCPServer()
    await server.setup()

    system = (
        "You are the Skillforge terminal agent.\n"
        "Use MCP tools (`route_skills`, `search_skills`, …) instead of hallucinating SKILL content.\n"
        "Prefer `route_skills` after `search_skills` when narrowing which skills matter.\n"
        "Honor host-mode Skillforge: repeat `route_skills` with `picked_names` when the UI lists a shortlist.\n"
        "Keep answers actionable and cite retrieved skill excerpts only after calling tools.\n"
    )
    messages: list[dict[str, Any]] = [{"role": "system", "content": system}]

    client = AsyncOpenAI(api_key=api_key, base_url=base.rstrip("/"))

    if ns.prompt.strip():
        user_line = ns.prompt.strip()
        messages.append({"role": "user", "content": user_line})
        reply, messages = await run_agent_round(
            server=server,
            client=client,
            model=model,
            messages=messages,
            default_project_root=proj,
            inner_cap=inner_cap,
        )
        if reply:
            sys.stdout.write(reply.strip() + "\n")
            sys.stdout.flush()
        return 0

    if not sys.stdin.isatty():  # pragma: no cover
        sys.stderr.write("Interactive mode requires a TTY (pipe --prompt=… instead).\n")
        return 2

    while True:
        try:
            line = input("\nYou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        if line.lower() in ("quit", "/quit", ":q", "/exit"):
            return 0
        messages.append({"role": "user", "content": line})
        reply, messages = await run_agent_round(
            server=server,
            client=client,
            model=model,
            messages=messages,
            default_project_root=proj,
            inner_cap=inner_cap,
        )
        if reply:
            print("\nAssistant>\n", reply.strip(), sep="")
        else:
            print("\nAssistant> (empty)")
        if len(messages) > 140:
            trim = [{"role": "system", "content": system}]
            trim.extend(messages[-120:])
            messages = trim


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
