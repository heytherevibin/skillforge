"""Tests for SQLite → route-eval fixture ingest helpers."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.main import init_db
from app.route_eval_harness import load_eval_fixture
from app.route_eval_ingest import (
    build_ingested_fixture_document,
    fetch_route_like_events,
    sqlite_row_to_case,
    strip_case_audit,
)


def test_sqlite_row_to_case_picked() -> None:
    payload = json.dumps(
        {
            "prompt": "hello world test",
            "picked": ["a", "b"],
            "routing_correlation_id": "550e8400-e29b-41d4-a716-446655440000",
            "candidates": [{"name": "a"}, {"name": "c"}],
        }
    )
    c = sqlite_row_to_case(
        payload,
        seq=1,
        event_ts=1.25,
        event_type="route",
        session_row="sid",
        expect_from="picked",
        preview_cap=10,
    )
    assert c is not None
    assert c["expect_picked_all"] == ["a", "b"]
    assert "expect_in_candidates" not in c


def test_sqlite_row_to_case_top_candidates() -> None:
    payload = json.dumps(
        {"prompt": "x", "candidates": [{"name": "n1"}, {"name": "n2"}], "picked": [], "routing_correlation_id": ""}
    )
    c = sqlite_row_to_case(
        payload,
        seq=2,
        event_ts=1.0,
        event_type="host_shortlist",
        session_row=None,
        expect_from="top_candidates",
        preview_cap=1,
    )
    assert c is not None and c["expect_in_candidates"] == ["n1"]


def test_strip_case_audit_removes_audits() -> None:
    stripped = strip_case_audit({"id": "1", "_audit": {"x": 1}, "_x": 2})
    assert stripped == {"id": "1"}


def test_fetch_route_like_events_order(tmp_path: Path) -> None:
    db = tmp_path / "o.sqlite"
    con = init_db(db)
    con.execute(
        "INSERT INTO events (id, ts, user_id, session_id, event_type, payload) VALUES (?,?,?,?,?,?)",
        ("e1", 10.0, "", None, "route", "{}"),
    )
    con.execute(
        "INSERT INTO events (id, ts, user_id, session_id, event_type, payload) VALUES (?,?,?,?,?,?)",
        ("e2", 20.0, "", None, "route", "{}"),
    )
    con.commit()
    rows = fetch_route_like_events(con, user_id="", session_id=None, limit=10, event_types=("route",), newest_first=False)
    assert len(rows) == 2 and rows[0][0] < rows[1][0]
    rows_nf = fetch_route_like_events(con, user_id="", session_id=None, limit=10, event_types=("route",), newest_first=True)
    assert len(rows_nf) == 2 and rows_nf[0][0] < rows_nf[1][0]
    con.close()


def test_generated_fixture_round_trip_via_load_fixture(tmp_path: Path) -> None:
    payload = {"prompt": "eval me", "picked": ["p1"], "candidates": [{"name": "p1"}], "routing_correlation_id": "r1"}
    c = sqlite_row_to_case(json.dumps(payload), seq=1, event_ts=0.5, event_type="route", session_row="z", expect_from="both", preview_cap=5)
    assert c is not None
    fp = tmp_path / "out.json"
    doc = build_ingested_fixture_document(
        cases=[c],
        candidate_window=22,
        orchestrator_db=Path("/tmp/x.sqlite"),
        user_id="u",
        session_id=None,
        event_types=("route",),
        include_audit_fields=False,
    )
    fp.write_text(json.dumps(doc), encoding="utf-8")
    loaded = load_eval_fixture(fp)
    assert loaded["_ingested_from"]["user_id"] == "u"
    assert loaded["cases"][0]["id"].startswith("ingest-")
