"""Tests for MMR context fusion (numpy only)."""
from __future__ import annotations

import numpy as np

from app.context_fusion import mmr_select


def test_mmr_prefers_diverse_second_item() -> None:
    """Two near-duplicate high-rel docs: second pick should favor the orthogonal one when lambda < 1."""
    # query-aligned
    e0 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    e1 = np.array([0.99, 0.14, 0.0], dtype=np.float32)  # almost same as e0
    e2 = np.array([0.0, 1.0, 0.0], dtype=np.float32)  # different direction
    emb = np.stack([e0, e1, e2], axis=0)
    rel = np.array([1.0, 0.98, 0.5], dtype=np.float64)
    lens = np.array([10, 10, 10], dtype=np.int64)
    ovh = np.full(3, 8, dtype=np.int64)
    order, trace = mmr_select(
        emb,
        rel,
        lens,
        char_budget=500,
        overhead_per_chunk=ovh,
        lambda_mult=0.5,
    )
    assert order[0] == 0
    assert order[1] == 2
    assert len(trace) == len(order)


def test_mmr_respects_char_budget() -> None:
    emb = np.eye(3, dtype=np.float32)
    rel = np.array([1.0, 0.9, 0.8])
    lens = np.array([100, 100, 100], dtype=np.int64)
    ovh = np.array([10, 10, 10], dtype=np.int64)
    order, _ = mmr_select(
        emb,
        rel,
        lens,
        char_budget=150,
        overhead_per_chunk=ovh,
        lambda_mult=1.0,
    )
    assert len(order) == 1
