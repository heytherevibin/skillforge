"""Unit tests for MCP operator helpers (no MCP server lifecycle)."""

from __future__ import annotations

import json
import sqlite3

from app.mcp_operator import (
    EVENTS_MARKDOWN_PREVIEW_MAX_LINES,
    build_router_status_dict,
    events_recent_rows,
    format_events_markdown,
    project_index_status_dict,
)
from app.npm_pkg_version import clear_version_cache_for_tests
from app.project_index import ensure_project_index_schema


def test_build_router_status_dict_without_router(monkeypatch) -> None:
    monkeypatch.delenv("SKILLFORGE_MCP_SERVER_VERSION", raising=False)
    clear_version_cache_for_tests()
    snap = build_router_status_dict(None, skill_count=0)
    assert snap["skills_loaded_count"] == 0
    assert snap["anthropic_available"] is False
    assert "skillforge_router_mode" in snap
    assert "mcp_server_semver" in snap
    semver = snap["mcp_server_semver"]
    assert isinstance(semver, str) and len(semver.split(".")) == 3


def test_format_events_markdown_truncation_notice() -> None:
    many = [{"ts": 1.0, "session_id": "sess", "event_type": "route", "payload": {}}]
    md = format_events_markdown(many * (EVENTS_MARKDOWN_PREVIEW_MAX_LINES + 10))
    assert "_meta.rows" in md
    assert "truncated" in md.lower()


def test_project_index_status_counts(tmp_path, monkeypatch) -> None:
    db = tmp_path / "orch.db"
    con = sqlite3.connect(str(db))
    ensure_project_index_schema(con)
    con.execute(
        "INSERT INTO project_chunks (path,line_start,line_end,mtime,file_size,content,embedding) "
        "VALUES (?,?,?,?,?,?,?)",
        ("a.py", 1, 2, 0.0, 10, "x", b"\0\0\0\0"),
    )
    con.execute(
        "INSERT INTO project_chunks (path,line_start,line_end,mtime,file_size,content,embedding) "
        "VALUES (?,?,?,?,?,?,?)",
        ("b.py", 1, 2, 0.0, 10, "y", b"\0\0\0\0"),
    )
    con.commit()
    m = project_index_status_dict(con)
    assert m["chunk_count"] == 2
    assert m["distinct_paths"] == 2
    con.close()


def test_events_recent_rows_filter_user_and_type(tmp_path) -> None:
    db = tmp_path / "e.db"
    con = sqlite3.connect(str(db))
    con.execute(
        """CREATE TABLE events (
            id TEXT PRIMARY KEY, ts REAL, user_id TEXT, session_id TEXT, event_type TEXT, payload TEXT
        )"""
    )
    con.execute(
        "INSERT INTO events VALUES (?,?,?,?,?,?)",
        ("1", 10.0, "u", "s", "route", json.dumps({"picked": ["a"]})),
    )
    con.execute(
        "INSERT INTO events VALUES (?,?,?,?,?,?)",
        ("2", 20.0, "u", "s", "feedback", json.dumps({"skill": "b"})),
    )
    con.execute(
        "INSERT INTO events VALUES (?,?,?,?,?,?)",
        ("3", 30.0, "other", "s", "route", "{}"),
    )
    con.commit()
    rows = events_recent_rows(con, limit=10, user_id="u", event_type="route")
    assert len(rows) == 1
    assert rows[0]["event_type"] == "route"
    assert rows[0]["payload"]["picked"] == ["a"]
    con.close()
