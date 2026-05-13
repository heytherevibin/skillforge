"""Parse interactive host-pick tokens (numbers ↔ skill ids)."""
from __future__ import annotations

from typing import Any


def parse_interactive_skill_pick(line: str, host_pick_rows: list[dict[str, Any]]) -> list[str]:
    """Map user input (`1`, `2,3`, `foo-skill`) onto catalog ids using ``rank`` from rows."""
    raw = (line or "").strip()
    if not raw or raw.lower() in ("q", "quit", "exit"):
        return []
    seen: dict[str, None] = {}
    by_rank: dict[int, str] = {}
    for r in host_pick_rows:
        rk = r.get("rank")
        nid = str(r.get("name") or r.get("id") or "").strip()
        if rk is None or not nid:
            continue
        try:
            ir = int(rk)
        except (TypeError, ValueError):
            continue
        by_rank[ir] = nid

    for part in raw.replace(";", ",").split(","):
        chunk = part.strip().strip("`").strip()
        if not chunk:
            continue
        if chunk.isdigit():
            name = by_rank.get(int(chunk))
            if name:
                seen.setdefault(name, None)
        else:
            seen.setdefault(chunk, None)
    return list(seen.keys())
