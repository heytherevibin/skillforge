"""Schema + planner guardrails for ``events`` indexes."""

from __future__ import annotations

import json
import uuid

from app.main import init_db


def test_events_has_user_type_ts_index(tmp_path) -> None:
    """Ensure composite ``(user_id, event_type, ts)`` index exists after ``init_db``."""
    db_path = tmp_path / "orc.db"
    con = init_db(db_path)
    names = [
        ((r[1] or "").lower()) for r in con.execute("PRAGMA index_list('events')").fetchall()
    ]
    assert any("idx_events_user_type_ts" in n for n in names), names


def test_events_filtered_query_plan_uses_index_scan(tmp_path) -> None:
    """Planner must not full-scan ``events`` for a typical user/type/limit replay shape."""
    db_path = tmp_path / "orc2.db"
    con = init_db(db_path)
    uid = ""
    ts = 1_700_000_000.0
    lim = ("route", "host_shortlist")
    for i in range(12):
        con.execute(
            """INSERT INTO events (id, ts, user_id, session_id, event_type, payload)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), ts + i, uid, None, lim[i % 2], json.dumps({"i": i})),
        )
    con.commit()

    placeholders = ",".join("?" * len(lim))
    sql = f"""
EXPLAIN QUERY PLAN
SELECT ts, session_id, event_type, payload
FROM events
WHERE user_id = ?
  AND event_type IN ({placeholders})
ORDER BY ts DESC
LIMIT ?
"""
    plan_rows = con.execute(sql, (uid, *lim, 10)).fetchall()
    con.close()
    blob = " ".join(str(r) for r in plan_rows).lower()
    assert "using index idx_events_" in blob
    assert "scan table events using" not in blob
