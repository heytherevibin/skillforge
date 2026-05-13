"""Split SKILL.md bodies into line-bounded chunks for RAG-style retrieval."""
from __future__ import annotations

import os
from dataclasses import dataclass


def chunk_max_chars() -> int:
    return max(400, int(os.getenv("SKILLFORGE_CHUNK_MAX_CHARS", "1200")))


def chunk_overlap_chars() -> int:
    return max(0, int(os.getenv("SKILLFORGE_CHUNK_OVERLAP", "200")))


@dataclass
class SkillChunk:
    """One span of a skill body with 1-based inclusive line numbers (within the body text)."""

    text: str
    line_start: int
    line_end: int


def _split_long_segment(text: str, line_start: int, max_chars: int, overlap: int) -> list[SkillChunk]:
    """Character windows with overlap; ``line_start`` is the body line of ``text[0]`` (1-based)."""
    if not text:
        return []
    line_no = line_start
    line_at_idx: list[int] = []
    for ch in text:
        line_at_idx.append(line_no)
        if ch == "\n":
            line_no += 1
    n = len(text)
    out: list[SkillChunk] = []
    i = 0
    while i < n:
        end = min(i + max_chars, n)
        piece = text[i:end].strip()
        if piece:
            ls = line_at_idx[i]
            le = line_at_idx[end - 1]
            out.append(SkillChunk(piece, ls, le))
        if end >= n:
            break
        adv = max(1, end - i - overlap)
        i += adv
    if out:
        return out
    st = text.strip()
    if not st:
        return []
    le_fallback = line_start + max(0, text.count("\n"))
    return [SkillChunk(st, line_start, max(line_start, le_fallback))]


def chunk_skill_body(body: str, *, max_chars: int | None = None, overlap: int | None = None) -> list[SkillChunk]:
    """Chunk by markdown headings (lines starting with ``#``) then hard-split long sections.

    Empty body yields no chunks (caller may treat as single empty).
    """
    mc = max_chars if max_chars is not None else chunk_max_chars()
    ov = overlap if overlap is not None else chunk_overlap_chars()
    b = body or ""
    if not b.strip():
        return []

    lines = b.split("\n")
    sections: list[tuple[str, int, int]] = []
    cur: list[str] = []
    cur_start = 1
    for i, line in enumerate(lines):
        ln = i + 1
        if line.startswith("#") and cur:
            sections.append(("\n".join(cur), cur_start, ln - 1))
            cur = [line]
            cur_start = ln
        else:
            cur.append(line)
    if cur:
        sections.append(("\n".join(cur), cur_start, len(lines)))

    chunks: list[SkillChunk] = []
    for text, ls, le in sections:
        text = text.strip()
        if not text:
            continue
        if len(text) <= mc:
            chunks.append(SkillChunk(text, ls, le))
        else:
            chunks.extend(_split_long_segment(text, ls, mc, ov))
    return chunks if chunks else [SkillChunk(b.strip(), 1, max(1, len(lines)))]


def chunk_raw_document(
    body: str,
    *,
    max_chars: int | None = None,
    overlap: int | None = None,
) -> list[SkillChunk]:
    """Chunk arbitrary file text with line-bounded windows (no markdown section split).

    Line numbers are 1-based within the normalized document (``\\r\\n`` → ``\\n``).
    """
    mc = max_chars if max_chars is not None else chunk_max_chars()
    ov = overlap if overlap is not None else chunk_overlap_chars()
    if not body:
        return []
    normalized = body.replace("\r\n", "\n")
    if not normalized.strip():
        return []
    line_count = normalized.count("\n") + 1
    if len(normalized) <= mc:
        return [SkillChunk(normalized, 1, max(1, line_count))]
    return _split_long_segment(normalized, 1, mc, ov)
