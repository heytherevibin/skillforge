"""Conversation-aware routing text, skill routing cards, and sparse retrieval signals."""
from __future__ import annotations

import os
import re
from typing import Any, Protocol

import numpy as np

from app.route_quality import coerce_route_float

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_\-./]{2,}", re.I)


def host_pick_max_candidates(*, top_k_cap: int) -> int:
    """Caps host-mode numbered shortlist size (parity with ``run_route_turn``)."""
    return max(3, min(top_k_cap, int(os.getenv("SKILLFORGE_HOST_PICK_MAX", "12"))))


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


def host_pick_shortlist_lines(
    *,
    prompt: str,
    route_query: str,
    facet_rows: list[dict[str, Any]],
    max_candidates: int | None = None,
    line_chars: int | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Tight numbered list + structured rows for MCP host-pick phase (no in-process LLM)."""
    mc = max_candidates
    if mc is None:
        top_k_cap = int(os.getenv("SKILLFORGE_TOP_K", "15"))
        mc = host_pick_max_candidates(top_k_cap=top_k_cap)
    lc = line_chars if line_chars is not None else int(os.getenv("SKILLFORGE_HOST_PICK_LINE_CHARS", "120"))
    prompt_one = (prompt or "").strip().replace("\n", " ")
    if len(prompt_one) > 160:
        prompt_one = prompt_one[:157] + "…"
    rows_out: list[dict[str, Any]] = []
    lines: list[str] = [
        "# Host pick — choose skill names only from this list",
        "",
        f"Task: {prompt_one}",
        "",
        "Reply with JSON only:",
        '{"picked": ["exact-skill-id", ...], "reasoning": "one line"}',
        f"Use 0–{mc} names from the numbered lines only (empty picked is allowed). Copy names exactly.",
        "",
        "```",
    ]
    for i, f in enumerate(facet_rows[:mc], start=1):
        name = str(f.get("name") or "")
        cos = coerce_route_float(f.get("cosine_similarity"))
        card = f"{f.get('title') or name}: {(f.get('description_preview') or '')[:lc]}".replace("\n", " ").strip()
        if len(card) > lc:
            card = card[: lc - 1] + "…"
        line = f"{i:>2}. {name} | cos={cos:.3f} | {card}"
        lines.append(line)
        rows_out.append({
            "id": name,
            "rank": i,
            "name": name,
            "cosine_similarity": round(cos, 6),
            "routing_score": f.get("routing_score"),
            "sparse_signal": f.get("sparse_signal"),
            "learned_weight": f.get("learned_weight"),
            "router_hybrid": f.get("router_hybrid"),
            "source": f.get("source"),
            "one_liner": card,
            "rationale_one_liner": card,
        })
    lines.append("```")
    rq = (route_query or "").strip()
    if len(rq) > 400:
        rq = rq[:397] + "…"
    if rq:
        lines.extend(["", f"_Retrieval query:_ {rq}"])
    return "\n".join(lines), rows_out
