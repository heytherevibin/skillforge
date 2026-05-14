"""Tests for optional learned-weight half-life (read-time decay)."""
from __future__ import annotations

import pytest

from app.feedback_meta import build_feedback_effect, get_skill_weight_detail
from app.main import get_skill_weight, init_db, update_skill_stat
from app.weight_semantics import freshness_multiplier, weight_half_life_days


def test_weight_half_life_unset(monkeypatch) -> None:
    monkeypatch.delenv("SKILLFORGE_WEIGHT_HALF_LIFE_DAYS", raising=False)
    assert weight_half_life_days() is None
    assert freshness_multiplier(updated_at=1.0, now=1.0 + 86400 * 365) == 1.0


def test_weight_half_life_invalid_is_off(monkeypatch) -> None:
    monkeypatch.setenv("SKILLFORGE_WEIGHT_HALF_LIFE_DAYS", "0")
    assert weight_half_life_days() is None


def test_freshness_multiplier_one_half_life(monkeypatch) -> None:
    monkeypatch.setenv("SKILLFORGE_WEIGHT_HALF_LIFE_DAYS", "30")
    m = freshness_multiplier(updated_at=1000.0, now=1000.0 + 30 * 86400)
    assert abs(m - 0.5) < 1e-9


def test_get_skill_weight_applies_decay(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SKILLFORGE_WEIGHT_HALF_LIFE_DAYS", "30")
    db = tmp_path / "d.db"
    con = init_db(db)

    monkeypatch.setattr("app.main.time.time", lambda: 1_000_000.0)
    update_skill_stat(con, "s1", "uses", 10, user_id="")
    update_skill_stat(con, "s1", "referenced", 10, user_id="")
    con.commit()

    w0, _ = get_skill_weight(con, "s1", user_id="")

    monkeypatch.setattr("app.main.time.time", lambda: 1_000_000.0 + 30 * 86400)
    w1, _ = get_skill_weight(con, "s1", user_id="")
    assert w0 > 1e-9
    assert abs(w1 - w0 * 0.5) < 1e-5


def test_get_skill_weight_disabled_skips_decay(monkeypatch, tmp_path) -> None:
    """Disabled path returns stored weight without decay multiplier."""
    monkeypatch.setenv("SKILLFORGE_WEIGHT_HALF_LIFE_DAYS", "1")
    con = init_db(tmp_path / "e.db")
    monkeypatch.setattr("app.main.time.time", lambda: 1_000_000.0)
    update_skill_stat(con, "s2", "uses", 5, user_id="")
    con.execute(
        "UPDATE skill_weights SET disabled = 1 WHERE user_id = ? AND skill_name = ?",
        ("", "s2"),
    )
    con.commit()
    monkeypatch.setattr("app.main.time.time", lambda: 2_000_000.0)
    raw = con.execute(
        "SELECT weight FROM skill_weights WHERE user_id = ? AND skill_name = ?",
        ("", "s2"),
    ).fetchone()[0]
    wg, dis = get_skill_weight(con, "s2", user_id="")
    assert dis is True
    assert abs(float(raw) - float(wg)) < 1e-9

def test_get_skill_weight_detail_decay_fields(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SKILLFORGE_WEIGHT_HALF_LIFE_DAYS", "30")
    con = init_db(tmp_path / "f.db")
    monkeypatch.setattr("app.feedback_meta.time.time", lambda: 1_000_000.0)
    update_skill_stat(con, "sx", "uses", 10, user_id="")
    update_skill_stat(con, "sx", "referenced", 5, user_id="")

    monkeypatch.setattr("app.feedback_meta.time.time", lambda: 1_000_000.0 + 30 * 86400)
    det = get_skill_weight_detail(con, "sx", user_id="")
    assert det is not None
    assert "stored_learned_weight" in det
    assert "decay_freshness_multiplier" in det
    assert abs(det["decay_freshness_multiplier"] - 0.5) < 1e-5
    assert abs(det["learned_weight"] - det["stored_learned_weight"] * 0.5) < 1e-3


def test_build_feedback_effect_formula_mentions_decay(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SKILLFORGE_WEIGHT_HALF_LIFE_DAYS", "14")
    con = init_db(tmp_path / "g.db")
    update_skill_stat(con, "z", "uses", 1, user_id="")
    fe = build_feedback_effect(con, ["z"], user_id="")
    assert "14" in fe["weight_formula"] or "SKILLFORGE_WEIGHT_HALF_LIFE" in fe["weight_formula"]
