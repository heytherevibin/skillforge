"""Optional post-pick diversification (cap skills per source before policy merge)."""
from __future__ import annotations

import os
from typing import Any, Mapping


def _env_truthy_pick_diversify() -> bool:
    return os.getenv("SKILLFORGE_PICK_DIVERSIFY", "").strip().lower() in ("1", "true", "yes")


def diversify_picked_names(
    names: list[str],
    by_name: Mapping[str, Any],
    *,
    max_per_source: int | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """Drop excess picks from the same skill ``source`` while preserving order.

    Returns ``(names_out, meta)``. When disabled, ``meta.applied`` is False and names are unchanged.
    """
    meta: dict[str, Any] = {
        "applied": False,
        "dropped": [],
        "max_per_source": max_per_source,
    }
    if not _env_truthy_pick_diversify():
        return list(names), meta

    mps = max_per_source
    if mps is None:
        raw = os.getenv("SKILLFORGE_PICK_MAX_PER_SOURCE", "2").strip()
        try:
            mps = int(raw)
        except ValueError:
            mps = 2
    mps = max(1, int(mps))
    meta["applied"] = True
    meta["max_per_source"] = mps

    counts: dict[str, int] = {}
    out: list[str] = []
    for n in names:
        sk = by_name.get(n)
        src = getattr(sk, "source", None) or "unknown"
        if counts.get(src, 0) >= mps:
            meta["dropped"].append(n)
            continue
        counts[src] = counts.get(src, 0) + 1
        out.append(n)
    return out, meta
