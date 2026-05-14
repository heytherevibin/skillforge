"""Learned routing weight: baseline formula + optional read-time half-life decay."""

from __future__ import annotations

import os
from typing import Final

_BASE_FORMULA: Final[str] = (
    "weight_stored = (referenced/uses - 0.5) * 0.3 + (thumbs_up - thumbs_down) * 0.1; "
    "reference_rate=referenced/uses if uses>0 else 0"
)


def weight_half_life_days() -> float | None:
    """Half-life in days for read-time decay; None when disabled (legacy behavior)."""
    raw = os.getenv("SKILLFORGE_WEIGHT_HALF_LIFE_DAYS", "").strip()
    if not raw:
        return None
    try:
        h = float(raw)
    except ValueError:
        return None
    if h <= 0:
        return None
    return h


def freshness_multiplier(*, updated_at: float | None, now: float) -> float:
    """``2^(-age_days / H)`` where H is half-life; 1.0 when decay off or missing timestamp."""
    h = weight_half_life_days()
    if h is None:
        return 1.0
    if updated_at is None:
        return 1.0
    age_days = max(0.0, (float(now) - float(updated_at)) / 86400.0)
    return 2.0 ** (-age_days / h)


def effective_learned_weight(stored_weight: float, *, updated_at: float | None, now: float) -> float:
    return float(stored_weight) * freshness_multiplier(updated_at=updated_at, now=now)


def feedback_weight_formula_documentation() -> str:
    """Human-readable formula string for MCP/CLI transparency."""
    base = _BASE_FORMULA + "; routing applies rank_score += effective_learned_weight"
    if weight_half_life_days() is None:
        return base + " (effective_learned_weight = weight_stored when SKILLFORGE_WEIGHT_HALF_LIFE_DAYS unset)"
    h = weight_half_life_days()
    return (
        base
        + f"; effective_learned_weight = weight_stored * 2^(-age_days/{h:g}) "
        "where age_days from updated_at (SKILLFORGE_WEIGHT_HALF_LIFE_DAYS)"
    )


def routing_applies_documentation() -> str:
    return "rank_score += effective_learned_weight (disabled skills get large negative score)"
