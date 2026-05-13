"""Conversation-aware routing text, skill routing cards, and sparse retrieval signals."""
from __future__ import annotations

import os
import re
from typing import Any, Protocol

import numpy as np

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_\-./]{2,}", re.I)


class _SkillCard(Protocol):
    title: str
    description: str
    triggers: str
    anti_triggers: str


def build_route_query_text(
    prompt: str,
    conversation: list[Any] | None,
    *,
    max_turns: int | None = None,
    max_chars_per_msg: int | None = None,
) -> str:
    """Merge recent turns with the current user message for embedding shortlist / hybrid scores.

    When ``SKILLFORGE_ROUTER_CONV_MAX_TURNS`` is 0 (default), returns ``prompt`` only (legacy behavior).
    """
    conv = conversation or []
    mt = max_turns
    if mt is None:
        mt = int(os.getenv("SKILLFORGE_ROUTER_CONV_MAX_TURNS", "0"))
    mc = max_chars_per_msg
    if mc is None:
        mc = int(os.getenv("SKILLFORGE_ROUTER_CONV_MSG_CHARS", "320"))
    prompt = (prompt or "").strip()
    if mt <= 0 or not conv:
        return prompt
    tail = conv[-mt:]
    parts: list[str] = []
    for m in tail:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "user")
        content = str(m.get("content") or "").strip()
        if not content:
            continue
        if len(content) > mc:
            content = content[:mc] + "…"
        parts.append(f"{role}: {content}")
    if not parts:
        return prompt
    return "Conversation context:\n" + "\n".join(parts) + "\n\nCurrent user message:\n" + prompt


def skill_routing_card(s: _SkillCard) -> str:
    """Text embedded for each skill + used in hybrid / router prompts."""
    title = (s.title or "").strip()
    desc = (s.description or "").strip()
    tr = (getattr(s, "triggers", None) or "").strip()
    anti = (getattr(s, "anti_triggers", None) or "").strip()
    parts = [f"{title}: {desc}"]
    if tr:
        parts.append(f"Triggers: {tr}")
    if anti:
        parts.append(f"Anti-triggers: {anti}")
    return "\n".join(parts)


def tokenize_skills_query(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def normalize_minmax(arr: np.ndarray) -> np.ndarray:
    a = np.asarray(arr, dtype=np.float64).reshape(-1)
    if a.size == 0:
        return a
    lo, hi = float(a.min()), float(a.max())
    if hi <= lo:
        return np.zeros_like(a)
    return (a - lo) / (hi - lo)


def keyword_overlap_scores(route_query: str, skill_cards: list[str]) -> np.ndarray:
    """Per-skill overlap counts (unnormalized); combine with dense via hybrid alpha."""
    qt = set(tokenize_skills_query(route_query))
    if not qt:
        return np.zeros(len(skill_cards), dtype=np.float64)
    out: list[float] = []
    for card in skill_cards:
        ct = set(tokenize_skills_query(card))
        out.append(float(len(qt & ct)))
    return np.array(out, dtype=np.float64)
