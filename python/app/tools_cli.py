"""
CLI parity for MCP tools (non-MCP callers: scripts, terminals, CI).

Dispatches through the same MCPServer tool handlers after a one-time router load.
Does not speak JSON-RPC; use ``skillforge mcp`` for MCP hosts.

Examples:
  skillforge tools search \"refactor typescript\"
  skillforge tools explain --prompt=\"debug routing\" --project-root \"$PWD\"
  skillforge tools get --skill-name my_skill --format card
  skillforge tools catalog
  skillforge tools capabilities --json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from app.mcp_server import MCPServer


def _die(msg: str, code: int = 2) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def _base_payload(ns: argparse.Namespace) -> dict[str, Any]:
    d: dict[str, Any] = {}
    if getattr(ns, "project_root", None) and str(ns.project_root).strip():
        d["project_root"] = str(ns.project_root).strip()
    if getattr(ns, "user_id", None) and str(ns.user_id).strip():
        d["user_id"] = str(ns.user_id).strip()
    return d


def _merged(ns: argparse.Namespace, extra: dict[str, Any]) -> dict[str, Any]:
    return {**_base_payload(ns), **extra}


async def _run_tool(server: MCPServer, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return await server.handle_tools_call({"name": tool, "arguments": arguments})


def _emit(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        blocks = payload.get("content") or []
        text = ""
        if blocks and isinstance(blocks[0], dict) and blocks[0].get("type") == "text":
            text = str(blocks[0].get("text") or "")
        sys.stdout.write(text)
        if text and not text.endswith("\n"):
            sys.stdout.write("\n")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="skillforge tools",
        description=(
            "Invoke MCP-equivalent Skillforge tools from the shell. "
            "Uses the same Python handlers as ``skillforge mcp`` (shared router + DB)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "CLI mapping: MCP route_skills → ``skillforge route`` "
            "(``tools`` exposes the remaining published tools verbatim)."
        ),
    )
    p.add_argument(
        "--project-root",
        metavar="PATH",
        help="Workspace root (per-repo ~/.skillforge); else SKILLFORGE_PROJECT_ROOT",
    )
    p.add_argument("--user-id", metavar="ID", help="Namespace for weights / events (matches MCP user_id)")
    p.add_argument(
        "--json",
        action="store_true",
        help="Print full MCP tool payload (content + _meta) as JSON on stdout",
    )
    sub = p.add_subparsers(dest="tool", metavar="COMMAND", required=True)

    sp = sub.add_parser("search", help="Embedding shortlist for a query (MCP: search_skills)")
    sp.add_argument("query", nargs="+", help="Search text")
    sp.add_argument("--limit", type=int, metavar="N", help="Max skills (default server TOP_K; cap 50)")

    ep = sub.add_parser("explain", help="Routing diagnostics without session writes (MCP: explain_route)")
    ep.add_argument("--prompt", required=True, help="Task text")
    ep.add_argument("--limit", type=int, metavar="N")
    ep.add_argument(
        "--conversation",
        metavar="FILE.json",
        help="Optional JSON array of message objects (same shape as MCP conversation)",
    )

    gp = sub.add_parser("get", help="Fetch one catalog skill by id (MCP: get_skill)")
    gp.add_argument("--skill-name", required=True, metavar="NAME")
    gp.add_argument("--format", choices=("card", "summary", "full"), default="full")
    gp.add_argument("--max-chars", type=int, default=0, metavar="N")

    sub.add_parser("catalog", help="Skills + usage stats (MCP: list_skills)")

    fb = sub.add_parser("feedback", help="Thumb up/down (MCP: skill_feedback)")
    fb.add_argument("--skill-name", required=True)
    fb.add_argument("--thumbs", type=int, choices=(-1, 1), required=True)
    fb.add_argument("--session-id", default="", metavar="ID")

    dis = sub.add_parser("disable", help="Exclude or restore a catalog skill from routing (MCP: disable_skill)")
    dis.add_argument("--skill-name", required=True)
    g = dis.add_mutually_exclusive_group(required=True)
    g.add_argument("--off", dest="disabled", action="store_true", help="Disable routing to this skill")
    g.add_argument("--on", dest="disabled", action="store_false", help="Re-enable routing")

    ref = sub.add_parser("referenced", help="Increment reference/stat count (MCP: skill_referenced)")
    ref.add_argument("--skill-name", required=True)

    mp = sub.add_parser("materialize", help="Write project-local skillforge stubs (MCP: materialize_project)")
    mp.add_argument("--root", dest="mat_root", required=True, metavar="PATH", help="Project root directory")
    mp.add_argument("--names", required=True, metavar="CSV", help="Comma-separated skill ids from routing")
    mp.add_argument(
        "--hosts",
        choices=("auto", "both", "cursor", "claude_code"),
        default="auto",
        help="Which host trees to write (same as MCP)",
    )
    mp.add_argument(
        "--no-merge",
        action="store_true",
        help="If set, refuse to overwrite existing managed files where applicable",
    )

    bp = sub.add_parser(
        "bootstrap",
        help="route_skills then materialize (blocked when ROUTER_MODE=host; MCP: skillforge_bootstrap)",
    )
    bp.add_argument("--prompt", required=True)
    bp.add_argument("--root", dest="bootstrap_root", required=True, metavar="PATH")
    bp.add_argument("--conversation", metavar="FILE.json")
    bp.add_argument("--session-id", default="", metavar="ID")
    bp.add_argument(
        "--hosts",
        choices=("auto", "both", "cursor", "claude_code"),
        default="auto",
    )
    bp.add_argument("--no-merge", action="store_true")
    bp.add_argument(
        "--include-project-rag",
        action="store_true",
        help="Attach indexed project chunks (requires index + project root)",
    )

    sub.add_parser("capabilities", help="Bootstrap bundle + tool list JSON (MCP: capabilities)")
    sub.add_parser("router-status", help="Read-only router/env snapshot (MCP: get_router_status)")

    ip = sub.add_parser("index-status", help="Project index stats from orchestrator DB (MCP: project_index_status)")
    ip.add_argument("--root", dest="idx_root", required=True, metavar="PATH")

    sub.add_parser("weights-snapshot", help="skill_weights rows as JSON (MCP: weights_snapshot)")

    ev = sub.add_parser("events-recent", help="Recent SQLite events (MCP: events_recent)")
    ev.add_argument("--limit", type=int, default=25, metavar="N")
    ev.add_argument("--event-type", default="", metavar="TYPE")

    return p


def _parse_conversation(path: str) -> list[Any]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        _die("--conversation JSON must be an array")
    return data


async def _async_main(raw: list[str]) -> int:
    parser = build_parser()
    ns = parser.parse_args(raw)

    server = MCPServer()
    await server.setup()

    if ns.tool == "search":
        q = " ".join(ns.query).strip()
        args = _merged(ns, {"query": q})
        if ns.limit is not None:
            args["limit"] = ns.limit
        payload = await _run_tool(server, "search_skills", args)
    elif ns.tool == "explain":
        args = _merged(ns, {"prompt": ns.prompt.strip()})
        if ns.limit is not None:
            args["limit"] = ns.limit
        if ns.conversation:
            args["conversation"] = _parse_conversation(ns.conversation)
        payload = await _run_tool(server, "explain_route", args)
    elif ns.tool == "get":
        args = _merged(
            ns,
            {"skill_name": ns.skill_name, "format": ns.format, "max_chars": ns.max_chars},
        )
        payload = await _run_tool(server, "get_skill", args)
    elif ns.tool == "catalog":
        payload = await _run_tool(server, "list_skills", _merged(ns, {}))
    elif ns.tool == "feedback":
        args = _merged(
            ns,
            {"skill_name": ns.skill_name, "thumbs": ns.thumbs, "session_id": ns.session_id or ""},
        )
        payload = await _run_tool(server, "skill_feedback", args)
    elif ns.tool == "disable":
        args = _merged(ns, {"skill_name": ns.skill_name, "disabled": bool(ns.disabled)})
        payload = await _run_tool(server, "disable_skill", args)
    elif ns.tool == "referenced":
        args = _merged(ns, {"skill_name": ns.skill_name})
        payload = await _run_tool(server, "skill_referenced", args)
    elif ns.tool == "materialize":
        names = [n.strip() for n in ns.names.replace(",", " ").split() if n.strip()]
        args_m = _merged(
            ns,
            {
                "project_root": str(ns.mat_root).strip(),
                "skill_names": names,
                "merge": not ns.no_merge,
                "hosts": ns.hosts,
            },
        )
        payload = await server.handle_tools_call({"name": "materialize_project", "arguments": args_m})
    elif ns.tool == "bootstrap":
        conv: list[Any] = []
        if ns.conversation:
            conv = _parse_conversation(ns.conversation)
        sid = str(ns.session_id).strip()
        args_b = _merged(
            ns,
            {
                "prompt": ns.prompt,
                "project_root": str(ns.bootstrap_root).strip(),
                "conversation": conv,
                "session_id": sid if sid else None,
                "merge": not ns.no_merge,
                "hosts": ns.hosts,
                "include_project_rag": bool(ns.include_project_rag),
            },
        )
        payload = await server.handle_tools_call({"name": "skillforge_bootstrap", "arguments": args_b})
    elif ns.tool == "capabilities":
        payload = await server.handle_tools_call({"name": "capabilities", "arguments": _merged(ns, {})})
    elif ns.tool == "router-status":
        payload = await server.handle_tools_call({"name": "get_router_status", "arguments": _merged(ns, {})})
    elif ns.tool == "index-status":
        args_i = _merged(ns, {"project_root": str(ns.idx_root).strip()})
        payload = await server.handle_tools_call({"name": "project_index_status", "arguments": args_i})
    elif ns.tool == "weights-snapshot":
        payload = await server.handle_tools_call({"name": "weights_snapshot", "arguments": _merged(ns, {})})
    elif ns.tool == "events-recent":
        et = str(ns.event_type).strip()
        args_e = _merged(ns, {"limit": ns.limit, **({"event_type": et} if et else {})})
        payload = await server.handle_tools_call({"name": "events_recent", "arguments": args_e})
    else:  # pragma: no cover
        parser.error(f"unknown tool: {ns.tool}")

    _emit(payload, as_json=ns.json)
    if payload.get("isError"):
        return 2
    return 0


def main() -> None:
    code = asyncio.run(_async_main(sys.argv[1:]))
    raise SystemExit(code)


if __name__ == "__main__":
    main()