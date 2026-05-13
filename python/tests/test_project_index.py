"""Project index: DB + retrieval (lightweight fake embedder)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np

from app.project_index import (
    ensure_project_index_schema,
    index_project,
    is_indexable_file,
    retrieve_project_context_items,
    should_skip_dir,
)


class _FakeEmbed:
    dim = 16

    def encode(self, texts, **kwargs):
        if isinstance(texts, str):
            texts = [texts]
        out = []
        for t in texts:
            seed = sum(ord(c) for c in t[:120]) % (2**31)
            rng = np.random.RandomState(seed)
            v = rng.randn(self.dim).astype(np.float32)
            nrm = float(np.linalg.norm(v)) or 1.0
            v /= nrm
            out.append(v)
        return np.stack(out, axis=0)

    def get_sentence_embedding_dimension(self):
        return self.dim


def test_should_skip_dir() -> None:
    assert should_skip_dir("node_modules")
    assert not should_skip_dir("src")


def test_is_indexable_file() -> None:
    assert is_indexable_file(Path("foo.py"))
    assert not is_indexable_file(Path("image.png"))


def test_index_and_retrieve_roundtrip(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SKILLFORGE_EMBED_MODEL", "fake-for-test")
    monkeypatch.setenv("SKILLFORGE_PROJECT_RAG_MAX_CHARS", "8000")

    root = tmp_path / "proj"
    root.mkdir()
    (root / "src").mkdir()
    (root / "src" / "hello.py").write_text(
        "def hello():\n    return 42\n\n# explanation\n",
        encoding="utf-8",
    )

    db_path = tmp_path / "orchestrator.db"
    con = sqlite3.connect(str(db_path))
    ensure_project_index_schema(con)
    try:
        fake = _FakeEmbed()
        stats = index_project(con, root, fake, reset=True)
        assert stats["chunks_written"] >= 1
        cur = con.execute("SELECT COUNT(*) FROM project_chunks")
        assert int(cur.fetchone()[0]) >= 1

        items = retrieve_project_context_items(con, fake, "hello function return", max_total_chars=5000)
        assert items
        assert items[0]["path"] == "src/hello.py"
        assert items[0]["line_start"] >= 1
        assert "42" in items[0]["text"] or "hello" in items[0]["text"]
    finally:
        con.close()
