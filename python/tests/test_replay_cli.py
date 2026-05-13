"""Replay CLI row helpers."""

from __future__ import annotations

import sqlite3

from app.replay_cli import _replay_rows


def test_replay_filters_session(tmp_path) -> None:
    db = tmp_path / "t.db"
    con = sqlite3.connect(str(db))
    con.execute(
        """CREATE TABLE events (
            id TEXT PRIMARY KEY, ts REAL, user_id TEXT, session_id TEXT, event_type TEXT, payload TEXT
        )"""
    )
    con.execute(
        "INSERT INTO events VALUES (?,?,?,?,?,?)",
        ("1", 1.0, "u", "sess-a", "route", "{}"),
    )
    con.execute(
        "INSERT INTO events VALUES (?,?,?,?,?,?)",
        ("2", 2.0, "u", "sess-b", "route", "{}"),
    )
    con.commit()
    rows = _replay_rows(con, session_id="sess-a", user_id="u", newest_first_snapshot=False, limit=50)
    con.close()
    assert len(rows) == 1
    assert rows[0][2] == "route"

