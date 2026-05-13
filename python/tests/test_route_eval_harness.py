"""Unit tests for route eval fixture matcher (no embedding load)."""
from __future__ import annotations

from types import SimpleNamespace

from app.route_eval_harness import evaluate_case_result, load_eval_fixture


def _cands(names: list[str]) -> list:
    return [(SimpleNamespace(name=n), 0.9) for n in names]


def test_evaluate_case_expect_in_candidates() -> None:
    r = {"candidates": _cands(["a", "b", "python-testing"]), "picked_names": ["a"]}
    case = {"id": "t", "prompt": "x", "expect_in_candidates": ["python-testing"]}
    assert evaluate_case_result(r, case, defaults={"candidate_window": 10}) == []


def test_evaluate_case_missing_candidate() -> None:
    r = {"candidates": _cands(["x", "y"]), "picked_names": ["x"]}
    case = {"id": "t", "prompt": "x", "expect_in_candidates": ["python-testing"]}
    err = evaluate_case_result(r, case, defaults={"candidate_window": 5})
    assert err and "python-testing" in err[0]


def test_evaluate_picked_any() -> None:
    r = {"candidates": _cands(["a", "b"]), "picked_names": ["b"]}
    case = {"id": "t", "expect_picked_any": ["b"]}
    assert evaluate_case_result(r, case) == []


def test_host_shortlist_fails() -> None:
    r = {"host_pick_shortlist": True, "candidates": [], "picked_names": []}
    err = evaluate_case_result(r, {"id": "h"}, defaults={})
    assert any("host shortlist" in e for e in err)


def test_load_fixture(tmp_path) -> None:
    p = tmp_path / "f.json"
    p.write_text(
        '{"version":1,"cases":[{"prompt":"hi","expect_in_candidates":["z"]}]}',
        encoding="utf-8",
    )
    data = load_eval_fixture(p)
    assert len(data["cases"]) == 1
