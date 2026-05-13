"""Unit tests for skill body chunking (no ML)."""
from __future__ import annotations

from app.chunking import chunk_raw_document, chunk_skill_body


def test_chunk_respects_headings() -> None:
    body = "# Title\n\nintro\n\n## A\n\none\n\n## B\n\ntwo three"
    chunks = chunk_skill_body(body, max_chars=500, overlap=50)
    assert len(chunks) >= 2
    names = [c.text for c in chunks]
    assert any("one" in t for t in names)
    assert any("two three" in t for t in names)


def test_chunk_line_numbers_monotonic() -> None:
    body = "a\nb\nc\nd"
    chunks = chunk_skill_body(body, max_chars=5, overlap=0)
    assert chunks
    for c in chunks:
        assert c.line_start <= c.line_end
        assert c.line_start >= 1


def test_empty_body() -> None:
    assert chunk_skill_body("", max_chars=100, overlap=0) == []


def test_chunk_raw_document_small_file() -> None:
    body = "line1\nline2\nline3"
    chunks = chunk_raw_document(body, max_chars=100, overlap=0)
    assert len(chunks) == 1
    assert chunks[0].line_start == 1
    assert "line1" in chunks[0].text
