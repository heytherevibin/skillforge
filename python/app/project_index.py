"""Project-local RAG: walk a repo, chunk text files, store embeddings in per-project SQLite."""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable, Iterator

import numpy as np

from app.chunking import SkillChunk, chunk_max_chars, chunk_overlap_chars, chunk_raw_document

# Basenames to skip entirely (noise / vendor / artifacts).
DEFAULT_IGNORE_DIR_NAMES: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        ".tox",
        "dist",
        "build",
        ".next",
        ".nuxt",
        "target",
        "coverage",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".terraform",
        ".parcel-cache",
        ".cache",
        ".skillforge",
    }
)

# Suffixes we never try to read as UTF-8 text.
SKIP_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".pdf",
        ".zip",
        ".tar",
        ".gz",
        ".tgz",
        ".bz2",
        ".xz",
        ".7z",
        ".rar",
        ".mp3",
        ".mp4",
        ".mov",
        ".wav",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".db",
        ".sqlite",
        ".sqlite3",
        ".bin",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".o",
        ".a",
        ".class",
        ".jar",
        ".pyc",
        ".pyo",
        ".pyd",
        ".lock",
    }
)

TEXT_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".md",
        ".mdx",
        ".txt",
        ".rst",
        ".py",
        ".pyi",
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".ts",
        ".tsx",
        ".json",
        ".jsonc",
        ".yaml",
        ".yml",
        ".toml",
        ".rs",
        ".go",
        ".java",
        ".kt",
        ".kts",
        ".rb",
        ".php",
        ".cs",
        ".swift",
        ".m",
        ".mm",
        ".h",
        ".hpp",
        ".c",
        ".cc",
        ".cpp",
        ".cxx",
        ".scss",
        ".sass",
        ".css",
        ".less",
        ".html",
        ".htm",
        ".vue",
        ".svelte",
        ".sql",
        ".graphql",
        ".sh",
        ".bash",
        ".zsh",
        ".fish",
        ".ps1",
        ".env",
        ".ini",
        ".cfg",
        ".conf",
        ".properties",
        ".xml",
        ".gradle",
        ".cmake",
        ".clj",
        ".cljs",
        ".ex",
        ".exs",
        ".erl",
        ".hrl",
        ".lua",
        ".nim",
        ".dart",
        ".scala",
        ".sol",
        ".r",
        ".R",
        ".jl",
        ".pl",
        ".pm",
        ".proto",
        ".tex",
        ".liquid",
    }
)

SPECIAL_FILENAMES: frozenset[str] = frozenset(
    {
        "dockerfile",
        "makefile",
        "gemfile",
        "rakefile",
        "procfile",
        "jenkinsfile",
        "licence",
        "license",
        "readme",
        "changelog",
        "contributing",
        "code_of_conduct",
    }
)

# Approximate cap for rows loaded into memory during retrieval.
PROJECT_RAG_MAX_ROWS_DEFAULT = int(os.getenv("SKILLFORGE_PROJECT_RAG_MAX_CHUNKS", "20000"))


def index_max_file_bytes() -> int:
    return max(4096, int(os.getenv("SKILLFORGE_INDEX_MAX_FILE_BYTES", "524288")))


def project_rag_max_chars() -> int:
    return max(0, int(os.getenv("SKILLFORGE_PROJECT_RAG_MAX_CHARS", "24000")))


def extra_ignore_dir_names() -> frozenset[str]:
    raw = os.getenv("SKILLFORGE_INDEX_IGNORE_DIRS", "").strip()
    if not raw:
        return frozenset()
    parts = {p.strip() for p in raw.replace(";", ",").split(",") if p.strip()}
    return frozenset(parts)


def should_skip_dir(name: str) -> bool:
    if name in DEFAULT_IGNORE_DIR_NAMES or name in extra_ignore_dir_names():
        return True
    # Skip symlink loops / common junk starting with heavy hidden dirs not listed above.
    if name == ".DS_Store":
        return True
    return False


def is_indexable_file(path: Path) -> bool:
    name_l = path.name.lower()
    ext = path.suffix.lower()
    if ext in SKIP_EXTENSIONS:
        return False
    if ext in TEXT_EXTENSIONS:
        return True
    stem = path.stem.lower()
    if stem in SPECIAL_FILENAMES and ext in ("", ".md", ".txt"):
        return True
    base = path.name.lower()
    if base in ("dockerfile", "makefile", "gemfile", "rakefile", "jenkinsfile"):
        return True
    return False


def iter_project_files(root: Path) -> Iterator[Path]:
    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        dp = Path(dirpath)
        # Prune directories in-place.
        dirnames[:] = sorted(
            d for d in dirnames if not should_skip_dir(d)
        )
        for fn in sorted(filenames):
            p = dp / fn
            try:
                if not p.is_file():
                    continue
            except OSError:
                continue
            if not is_indexable_file(p):
                continue
            yield p


def ensure_project_index_schema(con: sqlite3.Connection) -> None:
    con.executescript("""
        CREATE TABLE IF NOT EXISTS project_index_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS project_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL,
            line_start INTEGER NOT NULL,
            line_end INTEGER NOT NULL,
            mtime REAL NOT NULL,
            file_size INTEGER NOT NULL,
            content TEXT NOT NULL,
            embedding BLOB NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_project_chunks_path ON project_chunks(path);
    """)
    con.commit()


def _meta_get(con: sqlite3.Connection, key: str) -> str | None:
    cur = con.execute("SELECT value FROM project_index_meta WHERE key = ?", (key,))
    row = cur.fetchone()
    return str(row[0]) if row else None


def _meta_set(con: sqlite3.Connection, key: str, value: str) -> None:
    con.execute(
        "INSERT INTO project_index_meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def _delete_chunks_for_path(con: sqlite3.Connection, relpath: str) -> None:
    con.execute("DELETE FROM project_chunks WHERE path = ?", (relpath,))


def _blob_from_vec(vec: np.ndarray) -> bytes:
    v = np.asarray(vec, dtype=np.float32).reshape(-1)
    return v.tobytes()


def _vec_from_blob(blob: bytes, dim: int) -> np.ndarray:
    arr = np.frombuffer(blob, dtype=np.float32)
    if arr.size != dim:
        raise ValueError(f"embedding size mismatch: got {arr.size}, expected {dim}")
    return arr


def index_project(
    con: sqlite3.Connection,
    project_root: str | Path,
    embed_model,
    *,
    reset: bool = False,
    now: Callable[[], float] | None = None,
) -> dict[str, Any]:
    """Chunk text files under ``project_root`` and store rows in ``project_chunks``.

    Uses the same chunking window env vars as skills (``SKILLFORGE_CHUNK_*``).
    """
    ensure_project_index_schema(con)
    t0 = time.time()
    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"project_root is not a directory: {root}")

    embed_model_name = os.getenv("SKILLFORGE_EMBED_MODEL", "all-MiniLM-L6-v2")
    edim = int(embed_model.get_sentence_embedding_dimension())
    mc = chunk_max_chars()
    oc = chunk_overlap_chars()
    max_bytes = index_max_file_bytes()

    if reset:
        con.execute("DELETE FROM project_chunks")
        con.commit()

    files_seen = 0
    chunks_written = 0
    files_skipped_size = 0
    errors: list[str] = []

    for abs_path in iter_project_files(root):
        try:
            rel = abs_path.relative_to(root).as_posix()
        except ValueError:
            continue
        try:
            st = abs_path.stat()
        except OSError as e:
            errors.append(f"{rel}: stat {e}")
            continue
        if st.st_size > max_bytes:
            files_skipped_size += 1
            continue
        try:
            text = abs_path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            errors.append(f"{rel}: read {e}")
            continue

        chunks: list[SkillChunk] = chunk_raw_document(text, max_chars=mc, overlap=oc)
        if not chunks:
            _delete_chunks_for_path(con, rel)
            continue

        files_seen += 1
        _delete_chunks_for_path(con, rel)
        flat_texts: list[str] = []
        rows: list[tuple[Any, ...]] = []
        mtime = float(st.st_mtime)
        fsize = int(st.st_size)
        for ch in chunks:
            embed_in = f"{rel}\n{ch.text}"
            flat_texts.append(embed_in)
        try:
            emb = embed_model.encode(flat_texts, show_progress_bar=False, convert_to_numpy=True)
        except Exception as e:
            errors.append(f"{rel}: embed {e}")
            con.rollback()
            continue
        emb = np.asarray(emb, dtype=np.float32)
        if emb.ndim == 1:
            emb = emb.reshape(1, -1)
        norms = np.linalg.norm(emb, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        emb = emb / norms
        if emb.shape[1] != edim:
            errors.append(f"{rel}: unexpected embed dim {emb.shape[1]}")
            con.rollback()
            continue

        for ch, row_emb in zip(chunks, emb):
            rows.append(
                (rel, ch.line_start, ch.line_end, mtime, fsize, ch.text, _blob_from_vec(row_emb))
            )
        con.executemany(
            "INSERT INTO project_chunks (path, line_start, line_end, mtime, file_size, content, embedding) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        chunks_written += len(rows)

    con.commit()
    _meta_set(con, "embed_model", embed_model_name)
    _meta_set(con, "embedding_dim", str(edim))
    _meta_set(con, "last_index_ts", str(time.time() if now is None else now()))
    _meta_set(
        con,
        "last_index_stats",
        json.dumps({
            "root": str(root),
            "files_indexed": files_seen,
            "chunks_written": chunks_written,
            "files_skipped_oversize": files_skipped_size,
            "reset": reset,
            "elapsed_sec": round(time.time() - t0, 3),
            "errors": errors[:50],
            "chunk_max_chars": mc,
            "chunk_overlap": oc,
        }),
    )
    con.commit()

    return {
        "root": str(root),
        "files_indexed": files_seen,
        "chunks_written": chunks_written,
        "files_skipped_oversize": files_skipped_size,
        "elapsed_sec": round(time.time() - t0, 3),
        "errors": errors,
    }


def retrieve_project_context_items(
    con: sqlite3.Connection,
    embed_model,
    prompt: str,
    max_total_chars: int | None = None,
    *,
    max_rows: int | None = None,
    overhead_per_chunk: int = 56,
) -> list[dict[str, Any]]:
    """Return ranked project file chunks (same shape as skill context items + ``path``)."""
    cap = project_rag_max_chars() if max_total_chars is None else max_total_chars
    if cap <= 0 or not prompt.strip():
        return []

    ensure_project_index_schema(con)
    store_model = _meta_get(con, "embed_model")
    want_model = os.getenv("SKILLFORGE_EMBED_MODEL", "all-MiniLM-L6-v2")
    if store_model and store_model != want_model:
        return []

    dim_s = _meta_get(con, "embedding_dim")
    edim = int(dim_s) if dim_s else int(embed_model.get_sentence_embedding_dimension())
    if dim_s and int(dim_s) != int(embed_model.get_sentence_embedding_dimension()):
        return []

    row_limit = max_rows if max_rows is not None else PROJECT_RAG_MAX_ROWS_DEFAULT
    cur = con.execute(
        "SELECT path, line_start, line_end, content, embedding FROM project_chunks LIMIT ?",
        (row_limit,),
    )
    fetch = cur.fetchall()
    if not fetch:
        return []

    paths: list[str] = []
    ls: list[int] = []
    le: list[int] = []
    texts: list[str] = []
    mat_list: list[np.ndarray] = []
    for path, line_start, line_end, content, blob in fetch:
        try:
            v = _vec_from_blob(blob, edim)
        except ValueError:
            continue
        paths.append(str(path))
        ls.append(int(line_start))
        le.append(int(line_end))
        texts.append(str(content))
        mat_list.append(v)
    if not mat_list:
        return []

    mat = np.stack(mat_list, axis=0)
    qv = embed_model.encode(prompt, convert_to_numpy=True)
    qv = np.asarray(qv, dtype=np.float32).reshape(-1)
    qv = qv / max(float(np.linalg.norm(qv)), 1e-12)
    scores = (mat @ qv).flatten()
    order = np.argsort(-scores)

    out: list[dict[str, Any]] = []
    total = 0
    for o in order:
        i = int(o)
        piece_len = len(texts[i]) + overhead_per_chunk
        if total + piece_len > cap:
            continue
        out.append({
            "skill": None,
            "path": paths[i],
            "line_start": ls[i],
            "line_end": le[i],
            "text": texts[i],
            "score": float(scores[i]),
        })
        total += piece_len
    return out


def load_project_fusion_pool(
    con: sqlite3.Connection,
    embed_model,
    prompt: str,
    pool_limit: int,
    *,
    max_rows: int | None = None,
) -> tuple[list[dict[str, Any]], np.ndarray, np.ndarray]:
    """Top-``pool_limit`` project chunks by query similarity with embeddings (no char budget)."""
    if pool_limit <= 0 or not prompt.strip():
        return [], np.zeros((0, int(embed_model.get_sentence_embedding_dimension()))), np.array([])

    ensure_project_index_schema(con)
    store_model = _meta_get(con, "embed_model")
    want_model = os.getenv("SKILLFORGE_EMBED_MODEL", "all-MiniLM-L6-v2")
    if store_model and store_model != want_model:
        return [], np.zeros((0, int(embed_model.get_sentence_embedding_dimension()))), np.array([])

    dim_s = _meta_get(con, "embedding_dim")
    edim = int(dim_s) if dim_s else int(embed_model.get_sentence_embedding_dimension())
    if dim_s and int(dim_s) != int(embed_model.get_sentence_embedding_dimension()):
        return [], np.zeros((0, int(embed_model.get_sentence_embedding_dimension()))), np.array([])

    row_cap = max_rows if max_rows is not None else PROJECT_RAG_MAX_ROWS_DEFAULT
    cur = con.execute(
        "SELECT path, line_start, line_end, content, embedding FROM project_chunks LIMIT ?",
        (row_cap,),
    )
    fetch = cur.fetchall()
    if not fetch:
        return [], np.zeros((0, edim)), np.array([])

    paths: list[str] = []
    ls: list[int] = []
    le: list[int] = []
    texts: list[str] = []
    mat_list: list[np.ndarray] = []
    for path, line_start, line_end, content, blob in fetch:
        try:
            v = _vec_from_blob(blob, edim)
        except ValueError:
            continue
        paths.append(str(path))
        ls.append(int(line_start))
        le.append(int(line_end))
        texts.append(str(content))
        mat_list.append(v)
    if not mat_list:
        return [], np.zeros((0, edim)), np.array([])

    mat = np.stack(mat_list, axis=0)
    qv = embed_model.encode(prompt, convert_to_numpy=True)
    qv = np.asarray(qv, dtype=np.float32).reshape(-1)
    qv = qv / max(float(np.linalg.norm(qv)), 1e-12)
    scores = (mat @ qv).flatten()
    take = min(int(pool_limit), scores.shape[0])
    order = np.argsort(-scores)[:take]

    items: list[dict[str, Any]] = []
    rows: list[np.ndarray] = []
    rels: list[float] = []
    for o in order:
        i = int(o)
        items.append({
            "skill": None,
            "path": paths[i],
            "line_start": ls[i],
            "line_end": le[i],
            "text": texts[i],
            "score": float(scores[i]),
            "source": "file",
        })
        rows.append(mat[i])
        rels.append(float(scores[i]))
    if not rows:
        return [], np.zeros((0, edim)), np.array([])
    return items, np.stack(rows, axis=0), np.asarray(rels, dtype=np.float32)


def project_index_stats(con: sqlite3.Connection) -> dict[str, Any]:
    ensure_project_index_schema(con)
    cur = con.execute("SELECT COUNT(*) FROM project_chunks")
    n = int(cur.fetchone()[0])
    raw_stats = _meta_get(con, "last_index_stats")
    parsed: Any = None
    if raw_stats:
        try:
            parsed = json.loads(raw_stats)
        except json.JSONDecodeError:
            parsed = raw_stats
    return {
        "chunk_rows": n,
        "embed_model": _meta_get(con, "embed_model"),
        "embedding_dim": _meta_get(con, "embedding_dim"),
        "last_index_ts": _meta_get(con, "last_index_ts"),
        "last_index": parsed,
    }
