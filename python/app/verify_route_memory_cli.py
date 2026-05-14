"""Smoke-check route memory fusion (no embed model). For operators / RELEASING.

Run: ``cd package/python && PYTHONPATH=. python3 -m app.verify_route_memory_cli``
Or with a temp DB (default): merges a memory into a dummy route query and prints JSON.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


def main() -> int:
    os.environ.setdefault("SKILLFORGE_ROUTE_MEMORY", "1")

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)

    try:
        from app.main import init_db
        from app.route_memories import memory_append, merge_operator_memories_into_route_query

        con = init_db(db_path)
        uid = "__verify_route_memory__"
        mid, am = memory_append(
            con,
            user_id=uid,
            project_root=None,
            body="Smoke: prefer deterministic routing diagnostics when testing Skillforge.",
            importance=7,
        )
        q, fuse = merge_operator_memories_into_route_query(
            "verify prompt line",
            con,
            user_id=uid,
            project_root=None,
        )
        out = {
            "ok": fuse.get("applied") is True,
            "memory_id": mid,
            "append_meta": am,
            "fuse_meta": fuse,
            "route_query_has_prefix": q.startswith("Operator routing memories:\n"),
        }
        print(json.dumps(out, indent=2))
        return 0 if out["ok"] and out["route_query_has_prefix"] else 2
    finally:
        db_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
