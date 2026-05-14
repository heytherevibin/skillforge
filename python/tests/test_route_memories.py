"""Tests for SQLite route memories and routing-query fusion."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.main import init_db
from app.route_memories import (
    compact_route_memory_for_event,
    merge_operator_memories_into_route_query,
    memory_append,
    memory_list,
    memory_delete,
)


def test_fusion_off_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("SKILLFORGE_ROUTE_MEMORY", raising=False)
    con = init_db(tmp_path / "a.db")
    memory_append(con, user_id="u", project_root=None, body="note", importance=1)
    q, meta = merge_operator_memories_into_route_query("task text", con, user_id="u", project_root=None)
    assert q == "task text"
    assert meta["enabled"] is False


def test_fusion_prefixes_query(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SKILLFORGE_ROUTE_MEMORY", "1")
    monkeypatch.setenv("SKILLFORGE_ROUTE_MEMORY_MAX_CHARS", "800")
    con = init_db(tmp_path / "b.db")
    _, _ = memory_append(con, user_id="u", project_root=None, body="Always prefer pytest patterns", importance=5)
    q, meta = merge_operator_memories_into_route_query("fix flaky test", con, user_id="u", project_root=None, now=1_700_000_000.0)
    assert q.startswith("Operator routing memories:\n")
    assert "pytest" in q
    assert "fix flaky test" in q
    assert meta["applied"] is True
    assert meta["rows_used"] >= 1


def test_project_scoped_not_visible_without_root(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SKILLFORGE_ROUTE_MEMORY", "1")
    con = init_db(tmp_path / "c.db")
    proj = tmp_path / "repo"
    proj.mkdir()
    _, _ = memory_append(con, user_id="u", project_root=str(proj), body="repo-local hint", importance=9)
    q, meta = merge_operator_memories_into_route_query("x", con, user_id="u", project_root=None, now=1_700_000_000.0)
    assert meta["applied"] is False
    assert "repo-local" not in q


def test_ttl_expiry_excluded_from_merge(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SKILLFORGE_ROUTE_MEMORY", "1")
    con = init_db(tmp_path / "d.db")
    t0 = 1_000_000_000.0
    memory_append(
        con,
        user_id="u",
        project_root=None,
        body="expires",
        ttl_days=1.0 / 86400,
        now=t0,
    )[0]
    rows = memory_list(con, user_id="u", project_root=None, now=t0 + 10.0, include_expired=False)
    assert rows == []
    q, meta = merge_operator_memories_into_route_query("z", con, user_id="u", project_root=None, now=t0 + 10.0)
    assert meta["applied"] is False


def test_memory_delete(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SKILLFORGE_ROUTE_MEMORY", "1")
    con = init_db(tmp_path / "e.db")
    mid, _ = memory_append(con, user_id="u", project_root=None, body="x", importance=0)
    assert memory_delete(con, user_id="u", memory_id=mid) is True
    assert memory_delete(con, user_id="u", memory_id=mid) is False


def test_dedup_updates_row(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SKILLFORGE_ROUTE_MEMORY_DEDUP", "1")
    con = init_db(tmp_path / "f.db")
    a, _ = memory_append(con, user_id="u", project_root=None, body="hello  world\n", importance=1)
    b, m2 = memory_append(con, user_id="u", project_root=None, body="hello world", importance=9)
    assert a == b
    assert m2["dedup"] is True
    rows = memory_list(con, user_id="u", project_root=None)
    assert len(rows) == 1
    assert rows[0]["importance"] == 9


def test_compact_route_memory_for_event_truncates_ids() -> None:
    many = [str(i) for i in range(40)]
    c = compact_route_memory_for_event({"enabled": True, "applied": True, "rows_used": 2, "chars": 3, "truncated": False, "memory_ids": many, "importance_decay_active": False}, max_ids=5)
    assert c["schema"] == "route_memory_event/1"
    assert len(c["memory_ids"]) == 5


def test_half_life_orders_newer_before_stale(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SKILLFORGE_ROUTE_MEMORY", "1")
    monkeypatch.setenv("SKILLFORGE_ROUTE_MEMORY_IMPORTANCE_HALF_LIFE_DAYS", "5")
    con = init_db(tmp_path / "g.db")
    t0 = 2_000_000_000.0
    mid_old, _ = memory_append(con, user_id="u", project_root=None, body="old-heavy", importance=100, now=t0)
    mid_new, _ = memory_append(
        con, user_id="u", project_root=None, body="new-light", importance=40, now=t0 + 41 * 86400
    )
    fuse_t = t0 + 42 * 86400
    _, stub = merge_operator_memories_into_route_query("q", con, user_id="u", project_root=None, now=fuse_t)
    assert stub["importance_decay_active"] is True
    assert stub["memory_ids"][0] == mid_new
    assert mid_old in stub["memory_ids"]
