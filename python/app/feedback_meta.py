"""Transparency for per-user learning: how feedback stats affect routing scores."""
from __future__ import annotations

import sqlite3
import time
from typing import Any

from app.weight_semantics import (
    effective_learned_weight,
    feedback_weight_formula_documentation,
    freshness_multiplier,
    routing_applies_documentation,
    weight_half_life_days,
)


def get_skill_weight_detail(con: sqlite3.Connection, skill_name: str, user_id: str = "") -> dict[str, Any] | None:
    cur = con.execute(
        """
        SELECT weight, uses, referenced, thumbs_up, thumbs_down, disabled, updated_at
        FROM skill_weights WHERE user_id = ? AND skill_name = ?
        """,
        (user_id, skill_name),
    )
    row = cur.fetchone()
    if not row:
        return None
    w, uses, ref, up, down, dis, ts = row
    uses_i, ref_i = int(uses), int(ref)
    up_i, down_i = int(up), int(down)
    ref_rate = (ref_i / uses_i) if uses_i > 0 else 0.0
    stored = float(w)
    now = time.time()
    ts_f = float(ts) if ts is not None else None
    eff = stored if bool(dis) else effective_learned_weight(stored, updated_at=ts_f, now=now)
    out: dict[str, Any] = {
        "learned_weight": round(eff, 4),
        "uses": uses_i,
        "referenced": ref_i,
        "thumbs_up": up_i,
        "thumbs_down": down_i,
        "net_thumbs": up_i - down_i,
        "reference_rate": round(float(ref_rate), 4),
        "disabled": bool(dis),
        "updated_at": ts_f,
    }
    if weight_half_life_days() is not None and not bool(dis):
        out["stored_learned_weight"] = round(stored, 4)
        out["decay_freshness_multiplier"] = round(
            freshness_multiplier(updated_at=ts_f, now=now), 6
        )
    return out


def build_feedback_effect(
    con: sqlite3.Connection,
    picked_names: list[str],
    user_id: str = "",
) -> dict[str, Any]:
    """JSON-serializable snapshot of learning stats for picked skills (after this route's use counts)."""
    seen: set[str] = set()
    ordered: list[str] = []
    for n in picked_names:
        if n not in seen:
            seen.add(n)
            ordered.append(n)

    picked_out: list[dict[str, Any]] = []
    nonzero = 0
    max_abs = 0.0

    for name in ordered:
        row = get_skill_weight_detail(con, name, user_id=user_id)
        if row is None:
            picked_out.append({
                "skill": name,
                "has_db_row": False,
                "learned_weight": 0.0,
                "uses": 0,
                "referenced": 0,
                "thumbs_up": 0,
                "thumbs_down": 0,
                "net_thumbs": 0,
                "reference_rate": None,
                "disabled": False,
            })
            continue
        lw = float(row["learned_weight"])
        if abs(lw) > 1e-9:
            nonzero += 1
        max_abs = max(max_abs, abs(lw))
        entry: dict[str, Any] = {
            "skill": name,
            "has_db_row": True,
            "learned_weight": row["learned_weight"],
            "uses": row["uses"],
            "referenced": row["referenced"],
            "thumbs_up": row["thumbs_up"],
            "thumbs_down": row["thumbs_down"],
            "net_thumbs": row["net_thumbs"],
            "reference_rate": row["reference_rate"],
            "disabled": row["disabled"],
        }
        if "stored_learned_weight" in row:
            entry["stored_learned_weight"] = row["stored_learned_weight"]
        if "decay_freshness_multiplier" in row:
            entry["decay_freshness_multiplier"] = row["decay_freshness_multiplier"]
        picked_out.append(entry)

    return {
        "schema": "feedback_effect/1",
        "weight_formula": feedback_weight_formula_documentation(),
        "routing_applies": routing_applies_documentation(),
        "picked": picked_out,
        "summary": {
            "picked_count": len(ordered),
            "picked_with_nonzero_learned_weight": nonzero,
            "max_abs_learned_weight": round(float(max_abs), 4),
        },
    }
