"""Tests for events prune and replay filters."""
from __future__ import annotations

import json
import time
import uuid

from app.events_cli import prune_main
from app.events_query import fetch_events_for_replay, parse_replay_event_types
from app.main import init_db, log_event


def test_parse_replay_event_types() -> None:
    assert parse_replay_event_types("") is None
    assert parse_replay_event_types("route, feedback") == ("route", "feedback")


def test_fetch_events_for_replay_bounds_and_types(tmp_path) -> None:
    con = init_db(tmp_path / "r.db")
    uid = "u1"
    base = 1_800_000_000.0
    for i, et in enumerate(["route", "feedback", "route"]):
        con.execute(
            """INSERT INTO events (id, ts, user_id, session_id, event_type, payload)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), base + i, uid, "s1", et, json.dumps({"i": i})),
        )
    con.commit()

    rows = fetch_events_for_replay(
        con,
        user_id=uid,
        session_id=None,
        newest_first_snapshot=False,
        limit=50,
        event_types=("route",),
        min_ts=base + 0.5,
        max_ts=base + 2.5,
    )
    con.close()
    assert len(rows) == 1
    assert rows[0][2] == "route"


def test_prune_dry_run_then_execute(tmp_path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("SKILLFORGE_DB_PATH", str(tmp_path / "solo.db"))
    monkeypatch.delenv("SKILLFORGE_PROJECT_ROOT", raising=False)
    db = tmp_path / "solo.db"
    con = init_db(db)
    old_ts = 1_000.0
    con.execute(
        """INSERT INTO events (id, ts, user_id, session_id, event_type, payload)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (str(uuid.uuid4()), old_ts, "", None, "route", json.dumps({})),
    )
    con.commit()
    con.close()

    prune_main(["--before-ts", "2000"])
    out = capsys.readouterr().out
    assert "Rows to delete: 1" in out
    assert "dry-run" in out

    con = init_db(db)
    n = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    con.close()
    assert n == 1

    prune_main(["--before-ts", "2000", "--execute"])
    con = init_db(db)
    n2 = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    con.close()
    assert n2 == 0


def test_prune_log_event_path(tmp_path) -> None:
    """Prune against DB created via init_db + log_event (project_root resolution)."""
    db = tmp_path / "proj/.skillforge/orchestrator.db"
    db.parent.mkdir(parents=True)
    con = init_db(db)
    log_event(con, "sid", "route", {"picked": []}, user_id="")
    con.close()

    prune_main(["--before-ts", str(time.time() + 3600.0), "--project-root", str(tmp_path / "proj"), "--execute"])
    con = init_db(db)
    assert con.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    con.close()
