"""MMR-based selection to fuse skill + project chunks under one character budget."""
from __future__ import annotations

from typing import Any

import numpy as np


def mmr_select(
    embeddings: np.ndarray,
    relevance: np.ndarray,
    text_lengths: np.ndarray,
    *,
    char_budget: int,
    overhead_per_chunk: int | np.ndarray,
    lambda_mult: float,
) -> tuple[list[int], list[dict[str, Any]]]:
    """Greedy MMR over normalized row embeddings.

    Each step maximizes ``lambda_mult * rel[i] - (1 - lambda_mult) * max_{j in selected} sim(i, j)``.

    Returns selected **indices** in pick order and a trace row per pick (for telemetry).
    """
    n = int(embeddings.shape[0])
    if n == 0 or char_budget <= 0:
        return [], []

    lam = float(lambda_mult)
    lam = max(0.0, min(1.0, lam))
    rel = np.asarray(relevance, dtype=np.float64).reshape(-1)
    lens = np.asarray(text_lengths, dtype=np.int64).reshape(-1)
    emb = np.asarray(embeddings, dtype=np.float32)
    if isinstance(overhead_per_chunk, int):
        ovh = np.full(n, int(overhead_per_chunk), dtype=np.int64)
    else:
        ovh = np.asarray(overhead_per_chunk, dtype=np.int64).reshape(-1)
    if emb.shape[0] != n or rel.shape[0] != n or lens.shape[0] != n or ovh.shape[0] != n:
        raise ValueError("embeddings, relevance, text_lengths, and overheads must align")

    selected: list[int] = []
    trace: list[dict[str, Any]] = []
    used = 0
    remaining = set(range(n))

    while remaining:
        best_i: int | None = None
        best_mmr = -1e18
        for i in remaining:
            need = int(lens[i]) + int(ovh[i])
            if need <= 0 or used + need > char_budget:
                continue
            if not selected:
                div = 0.0
            else:
                sims = emb[i] @ emb[np.array(selected, dtype=np.int64)].T
                div = float(np.max(sims))
            mmr = lam * float(rel[i]) - (1.0 - lam) * div
            if mmr > best_mmr:
                best_mmr = mmr
                best_i = i
        if best_i is None:
            break
        if selected:
            sims = emb[best_i] @ emb[np.array(selected, dtype=np.int64)].T
            div_used = float(np.max(sims))
        else:
            div_used = 0.0
        selected.append(best_i)
        used += int(lens[best_i]) + int(ovh[best_i])
        remaining.remove(best_i)
        trace.append({
            "pool_index": best_i,
            "mmr": round(float(best_mmr), 6),
            "relevance": round(float(rel[best_i]), 6),
            "max_sim_to_selected": round(div_used, 6),
        })
    return selected, trace
