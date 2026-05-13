"""Pure helpers for route evaluation fixtures (embedding-first, no LLM)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_eval_fixture(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("fixture root must be a JSON object")
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("fixture must contain a non-empty cases array")
    return data


def _window(case: dict[str, Any], defaults: dict[str, Any]) -> int:
    w = case.get("candidate_window")
    if w is None:
        w = defaults.get("candidate_window", 25)
    return max(1, int(w))


def evaluate_case_result(
    result: dict[str, Any],
    case: dict[str, Any],
    *,
    defaults: dict[str, Any] | None = None,
) -> list[str]:
    """Return human-readable error strings; empty means pass."""
    defaults = defaults or {}
    errs: list[str] = []
    case_id = case.get("id") or case.get("name") or "?"

    if result.get("host_pick_shortlist"):
        errs.append(f"{case_id}: host shortlist result — use embedding router mode for eval")
        return errs

    cands = result.get("candidates") or []
    cand_names: list[str] = []
    for item in cands:
        if isinstance(item, tuple) and len(item) >= 1:
            sk = item[0]
            name = getattr(sk, "name", None)
            if name:
                cand_names.append(str(name))
        elif isinstance(item, dict) and item.get("name"):
            cand_names.append(str(item["name"]))

    window = _window(case, defaults)
    head = cand_names[:window]
    head_set = set(head)

    for label in (
        "expect_in_candidates",
        "expect_candidates_contain",
    ):
        need = case.get(label)
        if not need:
            continue
        if not isinstance(need, list):
            errs.append(f"{case_id}: {label} must be a list")
            continue
        for skill_id in need:
            sid = str(skill_id)
            if sid not in head_set:
                errs.append(
                    f"{case_id}: expected {sid!r} in first {window} candidates "
                    f"(have {head[:8]}{'…' if len(head) > 8 else ''})"
                )

    picked = list(result.get("picked_names") or [])
    picked_set = set(picked)

    if case.get("expect_picked_any"):
        need = case["expect_picked_any"]
        if not isinstance(need, list):
            errs.append(f"{case_id}: expect_picked_any must be a list")
        elif not (picked_set & {str(x) for x in need}):
            errs.append(
                f"{case_id}: expected at least one of {need!r} in picked_names {picked!r}"
            )

    if case.get("expect_picked_all"):
        need = case["expect_picked_all"]
        if not isinstance(need, list):
            errs.append(f"{case_id}: expect_picked_all must be a list")
        else:
            for sid in need:
                if str(sid) not in picked_set:
                    errs.append(
                        f"{case_id}: expected picked_names to include {sid!r} (have {picked!r})"
                    )

    return errs
