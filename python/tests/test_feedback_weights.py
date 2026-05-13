"""Tests for feedback_effect snapshot and weights export/import."""
from __future__ import annotations

from app.feedback_meta import build_feedback_effect, get_skill_weight_detail
from app.main import init_db, update_skill_stat
from app.weights_cli import export_weights, import_weights


def test_get_skill_weight_detail_missing(tmp_path) -> None:
    con = init_db(tmp_path / "a.db")
    assert get_skill_weight_detail(con, "nope", "") is None


def test_build_feedback_effect_after_use(tmp_path) -> None:
    con = init_db(tmp_path / "b.db")
    update_skill_stat(con, "alpha", "uses", 1, user_id="")
    update_skill_stat(con, "alpha", "thumbs_up", 1, user_id="")
    fe = build_feedback_effect(con, ["alpha", "beta"], user_id="")
    assert fe["schema"] == "feedback_effect/1"
    assert len(fe["picked"]) == 2
    alpha = next(p for p in fe["picked"] if p["skill"] == "alpha")
    assert alpha["has_db_row"] is True
    assert alpha["uses"] >= 1
    beta = next(p for p in fe["picked"] if p["skill"] == "beta")
    assert beta["has_db_row"] is False


def test_weights_export_import_roundtrip(tmp_path) -> None:
    db1 = tmp_path / "w1.db"
    db2 = tmp_path / "w2.db"
    con = init_db(db1)
    update_skill_stat(con, "x-skill", "uses", 2, user_id="u1")
    update_skill_stat(con, "x-skill", "referenced", 1, user_id="u1")
    con.close()

    con = init_db(db1)
    blob = export_weights(con, "u1")
    con.close()
    assert any(r["skill_name"] == "x-skill" for r in blob["rows"])

    con2 = init_db(db2)
    n = import_weights(con2, blob, user_id_override=None, replace_user=False)
    con2.close()
    assert n >= 1

    con2 = init_db(db2)
    cur = con2.execute(
        "SELECT uses, referenced FROM skill_weights WHERE user_id = ? AND skill_name = ?",
        ("u1", "x-skill"),
    )
    row = cur.fetchone()
    con2.close()
    assert row is not None
    assert int(row[0]) == 2


def test_weights_import_replace_user(tmp_path) -> None:
    db = tmp_path / "w3.db"
    con = init_db(db)
    update_skill_stat(con, "a", "uses", 1, user_id="")
    update_skill_stat(con, "b", "uses", 1, user_id="")
    con.close()

    payload = {
        "version": 1,
        "user_id": "",
        "rows": [{"skill_name": "only", "weight": 0.0, "uses": 1, "referenced": 0, "thumbs_up": 0, "thumbs_down": 0, "disabled": 0}],
    }
    con = init_db(db)
    import_weights(con, payload, user_id_override="", replace_user=True)
    con.close()

    con = init_db(db)
    cur = con.execute("SELECT skill_name FROM skill_weights WHERE user_id = '' ORDER BY skill_name")
    names = [r[0] for r in cur.fetchall()]
    con.close()
    assert names == ["only"]
