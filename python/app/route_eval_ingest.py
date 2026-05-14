"""Build route-eval fixtures from persisted SQLite ``events`` rows (offline operator workflow)."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

PROMPT_TELEMETRY_MAX = 300


def parse_event_types_arg(raw: str) -> tuple[str, ...]:
    bits = tuple(
        x.strip().lower()
        for x in (raw or "").split(",")
        if x.strip()
    )
    allowed = frozenset({"route", "host_shortlist"})
    out = tuple(x for x in bits if x in allowed)
    return out if out else ("route",)


def fetch_route_like_events(
    con: sqlite3.Connection,
    *,
    user_id: str,
    session_id: str | None,
    limit: int,
    event_types: tuple[str, ...],
    newest_first: bool,
) -> list[tuple[float, str | None, str, str | None]]:
    """Return rows (ts, session_id, event_type, payload_json)."""
    uid = (user_id or "").strip()
    lim = max(1, min(int(limit), 5000))
    placeholders = ",".join("?" * len(event_types))

    cur: sqlite3.Cursor
    if session_id and session_id.strip():
        sid = session_id.strip()
        cur = con.execute(
            f"""
            SELECT ts, session_id, event_type, payload
            FROM events
            WHERE user_id = ? AND session_id = ?
              AND event_type IN ({placeholders})
            ORDER BY ts ASC
            LIMIT ?
            """,
            (uid, sid, *event_types, lim),
        )
    elif newest_first:
        cur = con.execute(
            f"""
            SELECT ts, session_id, event_type, payload
            FROM events
            WHERE user_id = ?
              AND event_type IN ({placeholders})
            ORDER BY ts DESC
            LIMIT ?
            """,
            (uid, *event_types, lim),
        )
        rows_rev = [(float(ts), sid, str(et or ""), payload) for ts, sid, et, payload in cur.fetchall()]
        return list(reversed(rows_rev))

    cur = con.execute(
        f"""
            SELECT ts, session_id, event_type, payload
            FROM events
            WHERE user_id = ?
              AND event_type IN ({placeholders})
            ORDER BY ts ASC
            LIMIT ?
            """,
        (uid, *event_types, lim),
    )
    return [(float(ts), sid, str(et or ""), payload) for ts, sid, et, payload in cur.fetchall()]


def _candidate_names(payload: dict[str, Any], cap: int) -> list[str]:
    out: list[str] = []
    for row in payload.get("candidates") or []:
        if not isinstance(row, dict):
            continue
        nm = row.get("name")
        if nm is None:
            continue
        s = str(nm)
        if s not in out:
            out.append(s)
        if len(out) >= cap:
            break
    return out


def _picked_names(payload: dict[str, Any]) -> list[str]:
    picked = payload.get("picked") or payload.get("picked_names")
    if not isinstance(picked, list):
        return []
    return [str(x) for x in picked if x is not None and str(x).strip()]


def sqlite_row_to_case(
    payload_raw: str | None,
    *,
    seq: int,
    event_ts: float,
    event_type: str,
    session_row: str | None,
    expect_from: str,
    preview_cap: int,
) -> dict[str, Any] | None:
    if not payload_raw:
        return None
    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None

    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        return None

    corr_raw = str(payload.get("routing_correlation_id") or "").strip()

    corr_part = corr_raw.replace("-", "")[:8] if corr_raw else f"n{seq:04d}"
    case_id = f"ingest-{corr_part}-{seq}"

    cand_preview = _candidate_names(payload, max(preview_cap, 25))

    case: dict[str, Any] = {
        "id": case_id,
        "prompt": prompt,
        "_audit": {
            "source_event_type": event_type,
            "event_ts": event_ts,
            "session_id": session_row,
            "routing_correlation_id": corr_raw or None,
            "prompt_chars": len(prompt),
            "telemetry_prompt_max": PROMPT_TELEMETRY_MAX,
        },
    }

    want_picked = expect_from in ("picked", "both")
    want_cands = expect_from in ("top_candidates", "both")

    pn = _picked_names(payload)
    if want_picked and pn:
        case["expect_picked_all"] = pn

    if want_cands and cand_preview:
        case["expect_in_candidates"] = cand_preview[:preview_cap]

    return case


def strip_case_audit(case: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy omitting underscore-prefixed keys (used for tidy published fixtures)."""
    return {k: v for k, v in case.items() if not k.startswith("_")}


def build_ingested_fixture_document(
    *,
    cases: list[dict[str, Any]],
    candidate_window: int,
    orchestrator_db: Path,
    user_id: str,
    session_id: str | None,
    event_types: tuple[str, ...],
    include_audit_fields: bool,
) -> dict[str, Any]:
    meta = {
        "version": "route_eval_sqlite_ingest/1",
        "generated_at_unix": round(time.time(), 6),
        "orchestrator_db": str(orchestrator_db),
        "user_id": user_id,
        "session_id_filter": session_id,
        "event_types": list(event_types),
        "prompt_note": (
            f"Prompt strings come from persisted route snippets (typically at most "
            f"{PROMPT_TELEMETRY_MAX} chars). Long prompts are truncated vs the live invocation."
        ),
    }
    if include_audit_fields:
        body_cases = cases
    else:
        body_cases = [strip_case_audit(c) for c in cases]
    return {
        "version": 1,
        "defaults": {"candidate_window": max(1, int(candidate_window))},
        "_ingested_from": meta,
        "cases": body_cases,
    }
