"""
skillforge — skill orchestrator co-tool for Claude (MCP-first).

Primary surface: MCP stdio — route_skills and related tools for hosts
(Claude Desktop, Cursor, Claude Code).

Live usage: `skillforge events --watch` (terminal).
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np
from anthropic import AsyncAnthropic
from sentence_transformers import SentenceTransformer

from app.db_paths import global_db_path, resolve_orchestrator_db
from app.chunking import SkillChunk, chunk_max_chars, chunk_overlap_chars, chunk_skill_body
from app.context_fusion import mmr_select
from app.project_index import (
    ensure_project_index_schema,
    load_project_fusion_pool,
    project_rag_max_chars,
    retrieve_project_context_items,
)
from app.redaction import redaction_enabled, redact_secret_patterns, sanitize_context_items
from app.route_policies import load_route_policies_config, merge_policy_includes
from app.routing_signals import (
    build_route_query_text,
    keyword_overlap_scores,
    normalize_minmax,
    skill_routing_card,
    tokenize_skills_query,
)

# ---------- Config (env-driven so the Node wrapper controls paths) ----------
BUNDLED_SKILLS = Path(os.getenv("SKILLFORGE_BUNDLED_SKILLS", "./skills"))
USER_SKILLS = Path(os.getenv("SKILLFORGE_USER_SKILLS", str(Path.home() / ".skillforge" / "skills")))


DB_PATH = global_db_path()


EMBED_MODEL = os.getenv("SKILLFORGE_EMBED_MODEL", "all-MiniLM-L6-v2")
ROUTER_MODEL = os.getenv("SKILLFORGE_ROUTER_MODEL", "claude-haiku-4-5-20251001")
TOP_K_CANDIDATES = int(os.getenv("SKILLFORGE_TOP_K", "15"))
MAX_ACTIVE_SKILLS = int(os.getenv("SKILLFORGE_MAX_ACTIVE", "7"))
REROUTE_THRESHOLD = float(os.getenv("SKILLFORGE_REROUTE_THRESHOLD", "0.4"))
# "" | "full" | "embedding" — embedding skips Haiku and takes top skills from the shortlist only.
SKILLFORGE_ROUTER_MODE = os.getenv("SKILLFORGE_ROUTER_MODE", "").strip().lower()
# chunks: RAG-style line-bounded chunks from picked skills. full_body: inject entire SKILL.md per pick (legacy).
SKILLFORGE_CONTEXT_MODE = os.getenv("SKILLFORGE_CONTEXT_MODE", "chunks").strip().lower()
ROUTE_MAX_CONTEXT_CHARS = int(os.getenv("SKILLFORGE_ROUTE_MAX_CHARS", "60000"))
CONTEXT_FUSION = os.getenv("SKILLFORGE_CONTEXT_FUSION", "1").strip().lower() not in ("0", "false", "no", "")
CONTEXT_MMR_LAMBDA = max(0.0, min(1.0, float(os.getenv("SKILLFORGE_CONTEXT_MMR_LAMBDA", "0.7"))))
FUSION_POOL_SKILL = max(8, int(os.getenv("SKILLFORGE_FUSION_POOL_SKILL", "96")))
FUSION_POOL_PROJECT = max(8, int(os.getenv("SKILLFORGE_FUSION_POOL_PROJECT", "96")))
FUSION_FULL_BODY_PREVIEW_CHARS = max(400, int(os.getenv("SKILLFORGE_FUSION_FULL_BODY_PREVIEW_CHARS", "4000")))
CONTEXT_OVERHEAD_SKILL = 48
CONTEXT_OVERHEAD_FILE = 56

ROUTER_HYBRID_MODE = os.getenv("SKILLFORGE_ROUTER_HYBRID", "off").strip().lower()
ROUTER_HYBRID_ALPHA = max(0.0, min(1.0, float(os.getenv("SKILLFORGE_ROUTER_HYBRID_ALPHA", "0.72"))))
ROUTER_PROMPT_HISTORY_MSGS = max(1, int(os.getenv("SKILLFORGE_ROUTER_PROMPT_HISTORY_MSGS", "8")))
ROUTER_PROMPT_HISTORY_CHARS = max(80, int(os.getenv("SKILLFORGE_ROUTER_PROMPT_HISTORY_CHARS", "360")))
ROUTER_CATALOG_PREVIEW_CHARS = max(80, int(os.getenv("SKILLFORGE_ROUTER_CATALOG_PREVIEW_CHARS", "280")))
HAIKU_RERANK_MAX = max(3, int(os.getenv("SKILLFORGE_HAIKU_RERANK_MAX", str(TOP_K_CANDIDATES))))


def _hybrid_mode_active(mode: str) -> bool:
    return mode not in ("", "off", "0", "false", "no")


def _env_truthy(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() not in ("0", "false", "no", "")


def _context_budget_unified() -> int:
    raw = os.getenv("SKILLFORGE_CONTEXT_BUDGET_CHARS", "").strip()
    if raw:
        return max(4000, int(raw))
    return ROUTE_MAX_CONTEXT_CHARS + int(project_rag_max_chars())


def build_router_and_skills(
    *,
    log: bool = True,
    log_prefix: str = "[skillforge]",
) -> tuple[Router, dict[str, Skill]]:
    """Load embedding model, skill catalog, and Router (shared by MCP and ``skillforge route`` CLI)."""
    if log:
        print(f"{log_prefix} Loading skills...", file=sys.stderr)
    skills = load_all_skills()
    embed_model = SentenceTransformer(os.getenv("SKILLFORGE_EMBED_MODEL", "all-MiniLM-L6-v2"))
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    mode = SKILLFORGE_ROUTER_MODE
    if mode == "embedding":
        anthropic = None
        router_note = "embedding-only (SKILLFORGE_ROUTER_MODE=embedding)"
    elif mode == "full":
        if key:
            anthropic = AsyncAnthropic()
            router_note = "full Haiku router (SKILLFORGE_ROUTER_MODE=full)"
        else:
            anthropic = None
            router_note = (
                "embedding-only (SKILLFORGE_ROUTER_MODE=full but no ANTHROPIC_API_KEY — "
                "Haiku routing skipped)"
            )
    elif key:
        anthropic = AsyncAnthropic()
        router_note = "full Haiku router (default; ANTHROPIC_API_KEY set)"
    else:
        anthropic = None
        router_note = (
            "embedding-only (no ANTHROPIC_API_KEY — keyless. "
            "Set ANTHROPIC_API_KEY for Haiku routing.)"
        )
    if log:
        print(f"{log_prefix} {router_note}", file=sys.stderr)
        print(
            f"{log_prefix} Loaded {len(skills)} skills from bundled={BUNDLED_SKILLS} user={USER_SKILLS}",
            file=sys.stderr,
        )
    router = Router(skills, embed_model, anthropic)
    skmap = {s.name: s for s in skills}
    return router, skmap


# ---------- Skill loading ----------
@dataclass
class Skill:
    name: str
    title: str
    description: str
    body: str
    source: str  # "bundled" | "user"
    disabled: bool = False
    embedding: np.ndarray | None = None
    triggers: str = ""
    anti_triggers: str = ""


def parse_skill_md(path: Path, source: str) -> Skill | None:
    """Parse a SKILL.md: extract frontmatter name/description + body.

    Handles YAML block scalars (>, |) where description spans multiple
    indented lines after the key.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None
    name = path.parent.name
    title = name.replace("-", " ").title()
    description = ""
    triggers = ""
    anti_triggers = ""
    body = text
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            fm = text[3:end]
            body = text[end + 3:].strip()
            lines = fm.splitlines()
            i = 0
            while i < len(lines):
                line = lines[i]
                if ":" in line and not line.startswith(" ") and not line.startswith("\t"):
                    k, _, v = line.partition(":")
                    k = k.strip().lower()
                    v = v.strip()
                    # YAML block scalar: collect subsequent indented lines
                    if v in (">", "|", ">-", "|-", ">+", "|+"):
                        collected = []
                        j = i + 1
                        while j < len(lines) and (lines[j].startswith(" ") or lines[j].startswith("\t") or lines[j].strip() == ""):
                            collected.append(lines[j].strip())
                            j += 1
                        v = " ".join(s for s in collected if s)
                        i = j - 1
                    else:
                        v = v.strip('"').strip("'")
                    if k == "name":
                        title = v
                    elif k == "description":
                        description = v
                    elif k in ("triggers", "trigger"):
                        triggers = v
                    elif k in ("anti_triggers", "anti-triggers"):
                        anti_triggers = v
                i += 1
    if not description:
        for chunk in body.split("\n\n"):
            chunk = chunk.strip()
            if chunk and not chunk.startswith("#"):
                description = chunk[:500]
                break
    return Skill(
        name=name,
        title=title,
        description=description,
        body=body,
        source=source,
        triggers=triggers,
        anti_triggers=anti_triggers,
    )


def load_all_skills() -> list[Skill]:
    """Load from bundled dir first, then user dir (user overrides bundled by name)."""
    by_name: dict[str, Skill] = {}
    for src_dir, label in [(BUNDLED_SKILLS, "bundled"), (USER_SKILLS, "user")]:
        if not src_dir.exists():
            continue
        for skill_md in sorted(src_dir.glob("*/SKILL.md")):
            s = parse_skill_md(skill_md, label)
            if s:
                by_name[s.name] = s  # later sources override
    return list(by_name.values())


def iter_skill_md_paths() -> list[Path]:
    """All discovered SKILL.md paths in load order (bundled, then user overrides)."""
    paths: list[Path] = []
    for src_dir in (BUNDLED_SKILLS, USER_SKILLS):
        if not src_dir.exists():
            continue
        for skill_md in sorted(src_dir.glob("*/SKILL.md")):
            paths.append(skill_md)
    return paths


def skill_catalog_manifest() -> tuple[tuple[str, int], ...]:
    """Stable on-disk fingerprint for MCP hot-reload (resolved path + mtime_ns)."""
    rows: list[tuple[str, int]] = []
    for skill_md in iter_skill_md_paths():
        try:
            mtime_ns = int(skill_md.stat().st_mtime_ns)
        except OSError:
            mtime_ns = 0
        rows.append((str(skill_md.resolve()), mtime_ns))
    return tuple(rows)


# ---------- Database ----------
def init_db(db_file: Path | None = None):
    path = global_db_path() if db_file is None else db_file
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            ts REAL NOT NULL,
            user_id TEXT DEFAULT '',
            session_id TEXT,
            event_type TEXT,
            payload TEXT
        );
        CREATE TABLE IF NOT EXISTS skill_weights (
            user_id TEXT DEFAULT '',
            skill_name TEXT,
            weight REAL DEFAULT 0.0,
            uses INTEGER DEFAULT 0,
            referenced INTEGER DEFAULT 0,
            thumbs_up INTEGER DEFAULT 0,
            thumbs_down INTEGER DEFAULT 0,
            disabled INTEGER DEFAULT 0,
            updated_at REAL,
            PRIMARY KEY (user_id, skill_name)
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT DEFAULT '',
            created_at REAL,
            active_skills TEXT,
            turn_count INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts DESC);
        CREATE INDEX IF NOT EXISTS idx_events_user ON events(user_id, ts DESC);
    """)
    # Backward-compat: if upgrading from 0.1.0 schema, add user_id column where missing.
    for table in ("events", "sessions"):
        try:
            con.execute(f"ALTER TABLE {table} ADD COLUMN user_id TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # already exists
    ensure_project_index_schema(con)
    con.commit()
    return con


def log_event(con, session_id, event_type, payload, user_id=""):
    con.execute(
        "INSERT INTO events (id, ts, user_id, session_id, event_type, payload) VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), time.time(), user_id, session_id, event_type, json.dumps(payload)),
    )
    con.commit()


def get_skill_weight(con, name, user_id=""):
    cur = con.execute(
        "SELECT weight, disabled FROM skill_weights WHERE user_id = ? AND skill_name = ?",
        (user_id, name),
    )
    row = cur.fetchone()
    if not row:
        return 0.0, False
    return row[0], bool(row[1])


def update_skill_stat(con, name, field, delta=1, user_id=""):
    con.execute(
        f"""INSERT INTO skill_weights (user_id, skill_name, {field}, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, skill_name) DO UPDATE SET
                {field} = {field} + ?,
                updated_at = ?""",
        (user_id, name, delta, time.time(), delta, time.time()),
    )
    cur = con.execute(
        "SELECT uses, referenced, thumbs_up, thumbs_down FROM skill_weights WHERE user_id = ? AND skill_name = ?",
        (user_id, name),
    )
    row = cur.fetchone()
    if row:
        uses, referenced, up, down = row
        ref_rate = (referenced / uses) if uses > 0 else 0.0
        thumbs_score = (up - down) * 0.1
        weight = (ref_rate - 0.5) * 0.3 + thumbs_score
        con.execute(
            "UPDATE skill_weights SET weight = ? WHERE user_id = ? AND skill_name = ?",
            (weight, user_id, name),
        )
    con.commit()


def set_skill_disabled(con, name, disabled: bool, user_id=""):
    con.execute(
        """INSERT INTO skill_weights (user_id, skill_name, disabled, updated_at) VALUES (?, ?, ?, ?)
           ON CONFLICT(user_id, skill_name) DO UPDATE SET disabled = ?, updated_at = ?""",
        (user_id, name, int(disabled), time.time(), int(disabled), time.time()),
    )
    con.commit()


# ---------- Router ----------
class Router:
    def __init__(self, skills, embed_model, anthropic: Optional[AsyncAnthropic]):
        self.skills = skills
        self.embed_model = embed_model
        self.anthropic = anthropic
        self.context_mode = SKILLFORGE_CONTEXT_MODE if SKILLFORGE_CONTEXT_MODE in (
            "chunks",
            "full_body",
        ) else "chunks"
        self._by_name: dict[str, Skill] = {s.name: s for s in skills}
        self._hybrid_mode = ROUTER_HYBRID_MODE
        self._hybrid_alpha = ROUTER_HYBRID_ALPHA
        self._routing_cards = [skill_routing_card(s) for s in skills]
        self._bm25 = None
        if self._hybrid_mode == "bm25" and skills:
            try:
                from rank_bm25 import BM25Okapi

                toks = [tokenize_skills_query(c) for c in self._routing_cards]
                if any(toks):
                    self._bm25 = BM25Okapi(toks)
            except ImportError:
                print(
                    "[skillforge] SKILLFORGE_ROUTER_HYBRID=bm25 but rank-bm25 is not installed; "
                    "using keyword overlap for sparse signal.",
                    file=sys.stderr,
                )

        texts = self._routing_cards
        print(f"[skillforge] Embedding {len(skills)} skills (summary cards)...", file=sys.stderr)
        embeddings = embed_model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
        for s, e in zip(skills, embeddings):
            s.embedding = e / np.linalg.norm(e)
        self.matrix = np.stack([s.embedding for s in skills]) if skills else np.zeros((0, 0))

        # Chunk index for CONTEXT_MODE=chunks
        self._chunk_meta: list[tuple[str, SkillChunk]] = []
        edim = int(embed_model.get_sentence_embedding_dimension())
        self._chunk_embeddings: np.ndarray = np.zeros((0, edim))
        if self.context_mode == "chunks" and skills:
            flat_texts: list[str] = []
            self._chunk_meta = []
            mc = chunk_max_chars()
            oc = chunk_overlap_chars()
            for s in skills:
                for ch in chunk_skill_body(s.body, max_chars=mc, overlap=oc):
                    # Embed with in-chunk disambiguation
                    flat_texts.append(f"{s.title} — {s.name}\n{ch.text}")
                    self._chunk_meta.append((s.name, ch))
            if flat_texts:
                print(f"[skillforge] Embedding {len(flat_texts)} skill chunks...", file=sys.stderr)
                ce = embed_model.encode(
                    flat_texts, show_progress_bar=False, convert_to_numpy=True
                )
                ce = ce / np.linalg.norm(ce, axis=1, keepdims=True)
                self._chunk_embeddings = ce
            print(
                f"[skillforge] Ready. {len(skills)} skills; chunk matrix {self._chunk_embeddings.shape}; "
                f"context_mode={self.context_mode}; router_hybrid={self._hybrid_mode}",
                file=sys.stderr,
            )
        else:
            print(
                f"[skillforge] Ready. {len(skills)} skills, matrix shape: {self.matrix.shape}; "
                f"context_mode={self.context_mode}; router_hybrid={self._hybrid_mode}",
                file=sys.stderr,
            )

    def _sparse_scores(self, route_query: str) -> np.ndarray:
        if not _hybrid_mode_active(self._hybrid_mode):
            return np.zeros(len(self.skills), dtype=np.float64)
        if self._hybrid_mode == "keyword":
            return keyword_overlap_scores(route_query, self._routing_cards)
        if self._hybrid_mode == "bm25":
            if self._bm25 is not None:
                q = tokenize_skills_query(route_query)
                if not q:
                    return np.zeros(len(self.skills), dtype=np.float64)
                return np.asarray(self._bm25.get_scores(q), dtype=np.float64)
            return keyword_overlap_scores(route_query, self._routing_cards)
        return keyword_overlap_scores(route_query, self._routing_cards)

    def _base_routing_scores(self, route_query: str, q: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Dense cosine similarities and fused ranking scores (or dense-only if hybrid off)."""
        sims = (self.matrix @ q).flatten()
        if not _hybrid_mode_active(self._hybrid_mode):
            return sims, sims
        sparse = self._sparse_scores(route_query)
        d_norm = normalize_minmax(sims)
        s_norm = normalize_minmax(sparse)
        fused = self._hybrid_alpha * d_norm + (1.0 - self._hybrid_alpha) * s_norm
        return sims, fused

    def shortlist(self, route_query, con, k=TOP_K_CANDIDATES, user_id=""):
        if len(self.skills) == 0:
            return []
        q = self.embed_model.encode(route_query, convert_to_numpy=True)
        q = q / np.linalg.norm(q)
        sims, rank_scores = self._base_routing_scores(route_query, q)
        biased = rank_scores.copy()
        for i, s in enumerate(self.skills):
            w, disabled = get_skill_weight(con, s.name, user_id=user_id)
            if disabled:
                biased[i] = -999.0
            else:
                biased[i] += w
        top_idx = np.argsort(-biased)[:k]
        return [(self.skills[i], float(sims[i])) for i in top_idx if biased[i] > -100]

    def shortlist_with_facets(
        self,
        route_query: str,
        con: sqlite3.Connection,
        *,
        k: int | None = None,
        user_id: str = "",
    ) -> list[dict[str, Any]]:
        """Embedding shortlist with cosine sim, learned weight, and routing score (no LLM)."""
        limit = k if k is not None else TOP_K_CANDIDATES
        if len(self.skills) == 0:
            return []
        q = self.embed_model.encode(route_query, convert_to_numpy=True)
        q = q / np.linalg.norm(q)
        sims, rank_scores = self._base_routing_scores(route_query, q)
        sparse_full = (
            self._sparse_scores(route_query) if _hybrid_mode_active(self._hybrid_mode) else np.zeros(
                len(self.skills), dtype=np.float64
            )
        )
        biased = rank_scores.copy()
        for i, s in enumerate(self.skills):
            w, disabled = get_skill_weight(con, s.name, user_id=user_id)
            if disabled:
                biased[i] = -999.0
            else:
                biased[i] += w
        top_idx = np.argsort(-biased)[:limit]
        out: list[dict[str, Any]] = []
        for i in top_idx:
            if biased[i] <= -100:
                continue
            s = self.skills[i]
            w, _dis = get_skill_weight(con, s.name, user_id=user_id)
            out.append({
                "name": s.name,
                "title": s.title,
                "description_preview": (s.description or "")[:280],
                "cosine_similarity": round(float(sims[i]), 6),
                "sparse_signal": round(float(sparse_full[i]), 6),
                "learned_weight": round(float(w), 4),
                "routing_score": round(float(biased[i]), 6),
                "source": s.source,
                "router_hybrid": self._hybrid_mode,
            })
        return out

    def build_context_items(
        self,
        prompt: str,
        skill_names: list[str],
        max_total_chars: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return ordered context dicts: skill, line_start, line_end, text, score."""
        cap = max_total_chars if max_total_chars is not None else ROUTE_MAX_CONTEXT_CHARS
        if self.context_mode == "full_body":
            out: list[dict[str, Any]] = []
            for n in skill_names:
                s = self._by_name.get(n)
                if not s:
                    continue
                out.append({
                    "skill": n,
                    "path": None,
                    "line_start": None,
                    "line_end": None,
                    "text": s.body,
                    "score": 1.0,
                })
            return out
        if not skill_names or self._chunk_embeddings.shape[0] == 0:
            return []
        allowed = set(skill_names)
        indices = [i for i, (sn, _) in enumerate(self._chunk_meta) if sn in allowed]
        if not indices:
            return []
        qv = self.embed_model.encode(prompt, convert_to_numpy=True)
        qv = qv / np.linalg.norm(qv)
        sub = self._chunk_embeddings[indices]
        scores = (sub @ qv).flatten()
        order = np.argsort(-scores)
        out = []
        total = 0
        overhead = CONTEXT_OVERHEAD_SKILL
        for o in order:
            idx = indices[int(o)]
            sn, ch = self._chunk_meta[idx]
            piece_len = len(ch.text) + overhead
            if total + piece_len > cap:
                continue
            out.append({
                "skill": sn,
                "path": None,
                "line_start": ch.line_start,
                "line_end": ch.line_end,
                "text": ch.text,
                "score": float(scores[int(o)]),
            })
            total += piece_len
        return out

    def build_fusion_skill_pool(
        self,
        prompt: str,
        skill_names: list[str],
        pool_limit: int,
    ) -> tuple[list[dict[str, Any]], np.ndarray, np.ndarray]:
        """Candidate skill chunks (or one row per skill in full_body) with embeddings for MMR."""
        edim = int(self.embed_model.get_sentence_embedding_dimension())
        if not skill_names:
            return [], np.zeros((0, edim)), np.array([], dtype=np.float32)
        qv = self.embed_model.encode(prompt, convert_to_numpy=True)
        qv = np.asarray(qv, dtype=np.float32).reshape(-1)
        qv = qv / max(float(np.linalg.norm(qv)), 1e-12)

        if self.context_mode == "full_body":
            ordered = [n for n in skill_names if n in self._by_name]
            if not ordered:
                return [], np.zeros((0, edim)), np.array([], dtype=np.float32)
            texts = [
                f"{self._by_name[n].title} — {n}\n{(self._by_name[n].body or '')[:FUSION_FULL_BODY_PREVIEW_CHARS]}"
                for n in ordered
            ]
            em = self.embed_model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
            em = np.asarray(em, dtype=np.float32)
            em = em / np.maximum(np.linalg.norm(em, axis=1, keepdims=True), 1e-12)
            rel = (em @ qv).flatten()
            order = np.argsort(-rel)[: min(pool_limit, em.shape[0])]
            items: list[dict[str, Any]] = []
            em_rows: list[np.ndarray] = []
            rel_out: list[float] = []
            for o in order:
                i = int(o)
                n = ordered[i]
                s = self._by_name[n]
                items.append({
                    "skill": n,
                    "path": None,
                    "line_start": None,
                    "line_end": None,
                    "text": s.body,
                    "score": float(rel[i]),
                    "source": "skill",
                })
                em_rows.append(em[i])
                rel_out.append(float(rel[i]))
            return items, np.stack(em_rows), np.asarray(rel_out, dtype=np.float32)

        if self._chunk_embeddings.shape[0] == 0:
            return self._fusion_skill_pool_fallback_bodies(skill_names, qv, pool_limit)

        allowed = set(skill_names)
        indices = [i for i, (sn, _) in enumerate(self._chunk_meta) if sn in allowed]
        if not indices:
            return self._fusion_skill_pool_fallback_bodies(skill_names, qv, pool_limit)
        sub = self._chunk_embeddings[indices]
        scores = (sub @ qv).flatten()
        order = np.argsort(-scores)[: min(pool_limit, len(indices))]
        items = []
        em_rows = []
        rel_out = []
        for o in order:
            pos = int(o)
            idx = indices[pos]
            sn, ch = self._chunk_meta[idx]
            items.append({
                "skill": sn,
                "path": None,
                "line_start": ch.line_start,
                "line_end": ch.line_end,
                "text": ch.text,
                "score": float(scores[pos]),
                "source": "skill",
            })
            em_rows.append(sub[pos])
            rel_out.append(float(scores[pos]))
        return items, np.stack(em_rows), np.asarray(rel_out, dtype=np.float32)

    def _fusion_skill_pool_fallback_bodies(
        self,
        skill_names: list[str],
        qv: np.ndarray,
        pool_limit: int,
    ) -> tuple[list[dict[str, Any]], np.ndarray, np.ndarray]:
        ordered = [n for n in skill_names if n in self._by_name]
        edim = int(self.embed_model.get_sentence_embedding_dimension())
        if not ordered:
            return [], np.zeros((0, edim)), np.array([], dtype=np.float32)
        texts = [
            f"{self._by_name[n].title} — {n}\n{(self._by_name[n].body or '')[:FUSION_FULL_BODY_PREVIEW_CHARS]}"
            for n in ordered
        ]
        em = self.embed_model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
        em = np.asarray(em, dtype=np.float32)
        em = em / np.maximum(np.linalg.norm(em, axis=1, keepdims=True), 1e-12)
        rel = (em @ qv).flatten()
        order = np.argsort(-rel)[: min(pool_limit, em.shape[0])]
        items = []
        em_rows = []
        rel_out = []
        for o in order:
            i = int(o)
            n = ordered[i]
            s = self._by_name[n]
            items.append({
                "skill": n,
                "path": None,
                "line_start": None,
                "line_end": None,
                "text": s.body,
                "score": float(rel[i]),
                "source": "skill",
            })
            em_rows.append(em[i])
            rel_out.append(float(rel[i]))
        return items, np.stack(em_rows), np.asarray(rel_out, dtype=np.float32)

    async def rerank_candidates_haiku(
        self,
        route_query: str,
        conversation: list | None,
        candidates: list[tuple[Skill, float]],
    ) -> list[tuple[Skill, float]]:
        if (
            not candidates
            or self.anthropic is None
            or not _env_truthy("SKILLFORGE_HAIKU_RERANK", "0")
        ):
            return candidates
        cap = max(3, min(HAIKU_RERANK_MAX, len(candidates)))
        head = candidates[:cap]
        tail = candidates[cap:]
        by_name = {s.name: (s, sc) for s, sc in head}
        lines: list[str] = []
        for idx, (s, _sc) in enumerate(head, start=1):
            card = skill_routing_card(s)
            preview = card[:220].replace("\n", " ")
            lines.append(f"{idx}. {s.name} — {preview}")
        hist = ""
        if conversation:
            msgs = conversation[-ROUTER_PROMPT_HISTORY_MSGS:]
            parts: list[str] = []
            for m in msgs:
                if not isinstance(m, dict):
                    continue
                role = str(m.get("role") or "user")
                c = str(m.get("content") or "").strip()
                if not c:
                    continue
                parts.append(f"{role}: {c[:ROUTER_PROMPT_HISTORY_CHARS]}")
            if parts:
                hist = "\n\nConversation (recent):\n" + "\n".join(parts)
        sys = (
            "You reorder skill candidates by relevance to the user's task. "
            "Output ONLY JSON: {\"order\": [\"skill_name\", ...]} with each candidate "
            "skill name appearing exactly once, best match first. No extra keys."
        )
        user = (
            f"Routing focus:\n{route_query}{hist}\n\nCandidates:\n" + "\n".join(lines)
        )
        try:
            rerank_model = os.getenv("SKILLFORGE_HAIKU_RERANK_MODEL", "").strip() or ROUTER_MODEL
            resp = await self.anthropic.messages.create(
                model=rerank_model,
                max_tokens=500,
                system=sys,
                messages=[{"role": "user", "content": user}],
            )
            text = resp.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text.strip())
            order = data.get("order") or []
            ordered: list[tuple[Skill, float]] = []
            seen: set[str] = set()
            for n in order:
                if isinstance(n, str) and n in by_name and n not in seen:
                    ordered.append(by_name[n])
                    seen.add(n)
            for s, sc in head:
                if s.name not in seen:
                    ordered.append((s, sc))
            return ordered + tail
        except Exception:
            return candidates

    def pick_final_embedding_only(self, candidates):
        """Pick up to MAX_ACTIVE_SKILLS from the shortlist order (similarity + weights). No LLM call."""
        if not candidates:
            return [], "no candidates available"
        names = [s.name for s, _ in candidates[:MAX_ACTIVE_SKILLS]]
        return names, (
            "embedding-only: top candidates by similarity and learned weights"
        )

    async def pick_final(
        self,
        prompt,
        conversation,
        candidates,
        route_query: str | None = None,
    ):
        rq = (route_query if route_query is not None else prompt) or ""
        if self.anthropic is None:
            return self.pick_final_embedding_only(candidates)
        if not candidates:
            return [], "no candidates available"
        catalog = "\n".join(
            f"- {s.name}: {skill_routing_card(s)[:ROUTER_CATALOG_PREVIEW_CHARS]}"
            for s, _ in candidates
        )
        recent = ""
        if conversation:
            msgs = conversation[-ROUTER_PROMPT_HISTORY_MSGS:]
            parts: list[str] = []
            for m in msgs:
                if not isinstance(m, dict):
                    continue
                role = str(m.get("role") or "user")
                c = str(m.get("content") or "").strip()
                if not c:
                    continue
                parts.append(f"{role}: {c[:ROUTER_PROMPT_HISTORY_CHARS]}")
            if parts:
                recent = "\n\nRecent conversation:\n" + "\n".join(parts)
        sys = (
            "You are a skill router. Given a user prompt and a candidate list of skills, "
            f"pick 0 to {MAX_ACTIVE_SKILLS} skills that would genuinely help answer this prompt. "
            "Be ruthless — only include a skill if it directly applies. Empty list is valid. "
            'Respond ONLY in JSON: {"skills": ["name1","name2"], "reasoning": "one sentence"}'
        )
        user = (
            f"User prompt:\n{prompt}\n\nRouting context (retrieval query):\n{rq}{recent}"
            f"\n\nCandidate skills:\n{catalog}"
        )
        try:
            resp = await self.anthropic.messages.create(
                model=ROUTER_MODEL,
                max_tokens=400,
                system=sys,
                messages=[{"role": "user", "content": user}],
            )
            text = resp.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text.strip())
            picked = [n for n in data.get("skills", []) if any(s.name == n for s, _ in candidates)]
            return picked[:MAX_ACTIVE_SKILLS], data.get("reasoning", "")
        except Exception as e:
            return [s.name for s, _ in candidates[:3]], f"router-fallback: {e}"


def jaccard_change(old, new):
    if not old and not new:
        return 0.0
    if not old or not new:
        return 1.0
    inter = len(old & new)
    union = len(old | new)
    return 1.0 - (inter / union)


def format_context_items_markdown(context_items: list[dict[str, Any]]) -> str:
    """Human-readable block list for MCP / CLI from context items (skills + optional project files)."""
    blocks = []
    for c in context_items:
        ls, le = c.get("line_start"), c.get("line_end")
        if ls is not None and le is not None:
            loc = f" (lines {ls}-{le})"
        else:
            loc = " (full document)"
        path = c.get("path")
        if path:
            blocks.append(f"### File: `{path}`{loc}\n\n{c['text']}\n")
        else:
            blocks.append(f"### Skill: {c['skill']}{loc}\n\n{c['text']}\n")
    return "\n".join(blocks)


async def run_route_turn(
    con: sqlite3.Connection,
    router: Router,
    prompt: str,
    conversation: list,
    user_id: str = "",
    session_id: str | None = None,
    *,
    project_root: str | None = None,
    include_project_rag: bool = False,
) -> dict[str, Any]:
    """Shared routing + session + telemetry for MCP route_skills and ``skillforge route``.

    Updates sessions, skill usage stats, and writes a route row to events.
    """
    sid = session_id or str(uuid.uuid4())
    t0 = time.time()
    route_query = build_route_query_text(prompt, conversation)
    candidates = router.shortlist(route_query, con, user_id=user_id)
    candidates = await router.rerank_candidates_haiku(route_query, conversation, candidates)
    picked_names, reasoning = await router.pick_final(
        prompt, conversation, candidates, route_query=route_query
    )
    pr = (project_root or "").strip()
    policies_cfg = load_route_policies_config(pr or None)
    picked_names, policy_audit = merge_policy_includes(
        prompt,
        picked_names,
        policies_cfg,
        router._by_name,
        con,
        user_id,
        max_active=MAX_ACTIVE_SKILLS,
    )
    route_ms = (time.time() - t0) * 1000

    prev_active: set[str] = set()
    cur = con.execute(
        "SELECT active_skills FROM sessions WHERE id = ? AND user_id = ?",
        (sid, user_id),
    )
    row = cur.fetchone()
    if row and row[0]:
        prev_active = set(json.loads(row[0]))
    change = jaccard_change(prev_active, set(picked_names))
    rerouted = change >= REROUTE_THRESHOLD and bool(prev_active)

    want_fusion = CONTEXT_FUSION and include_project_rag and bool(pr)
    context_fusion: dict[str, Any] | None = None
    context_items: list[dict[str, Any]] = []

    proj_pool: list[dict[str, Any]] = []
    proj_emb = np.zeros((0, int(router.embed_model.get_sentence_embedding_dimension())))
    proj_rel = np.array([], dtype=np.float32)

    if want_fusion:
        try:
            proj_pool, proj_emb, proj_rel = load_project_fusion_pool(
                con, router.embed_model, prompt, FUSION_POOL_PROJECT
            )
        except Exception:
            proj_pool = []
            proj_emb = np.zeros((0, int(router.embed_model.get_sentence_embedding_dimension())))
            proj_rel = np.array([], dtype=np.float32)

    if want_fusion and proj_pool:
        skill_pool, skill_emb, skill_rel = router.build_fusion_skill_pool(
            prompt, picked_names, FUSION_POOL_SKILL
        )
        n_skill = len(skill_pool)
        n_proj = len(proj_pool)
        pool = skill_pool + proj_pool
        if n_skill and n_proj:
            em = np.vstack([skill_emb, proj_emb])
            rel = np.concatenate([skill_rel, proj_rel])
        elif n_skill:
            em = skill_emb
            rel = skill_rel
        else:
            em = proj_emb
            rel = proj_rel
        lens = np.array([len(c["text"]) for c in pool], dtype=np.int64)
        ovh = np.array([
            CONTEXT_OVERHEAD_SKILL if not c.get("path") else CONTEXT_OVERHEAD_FILE
            for c in pool
        ], dtype=np.int64)
        budget = _context_budget_unified()
        order, mmr_trace = mmr_select(
            em,
            rel,
            lens,
            char_budget=budget,
            overhead_per_chunk=ovh,
            lambda_mult=CONTEXT_MMR_LAMBDA,
        )
        for rank, idx in enumerate(order, start=1):
            item = dict(pool[idx])
            item.pop("source", None)
            tr = mmr_trace[rank - 1]
            item["mmr_rank"] = rank
            item["mmr_score"] = tr["mmr"]
            item["retrieval_relevance"] = tr["relevance"]
            item["max_sim_to_prior"] = tr["max_sim_to_selected"]
            context_items.append(item)
        context_fusion = {
            "enabled": True,
            "lambda": CONTEXT_MMR_LAMBDA,
            "budget_chars": budget,
            "pool_skill": n_skill,
            "pool_project": n_proj,
            "selected_count": len(context_items),
            "mmr_trace": mmr_trace,
        }
    else:
        context_items = router.build_context_items(prompt, picked_names)
        if picked_names and not context_items:
            context_items = [
                {
                    "skill": n,
                    "path": None,
                    "line_start": None,
                    "line_end": None,
                    "text": router._by_name[n].body,
                    "score": 1.0,
                }
                for n in picked_names
                if n in router._by_name
            ]
        project_add: list[dict[str, Any]] = []
        if include_project_rag and pr:
            try:
                project_add = retrieve_project_context_items(con, router.embed_model, prompt)
            except Exception:
                project_add = []
        context_items = [*context_items, *project_add]
        context_fusion = {"enabled": False}

    project_rag_items_count = sum(1 for c in context_items if c.get("path"))

    reasoning_out = reasoning
    safe_prompt_snip = prompt[:300]
    context_redaction_stats: dict[str, Any] = {"enabled": False, "secret_hits": 0, "path_hits": 0}
    if redaction_enabled():
        safe_prompt_snip, _ = redact_secret_patterns(prompt[:300])
        sh, ph = sanitize_context_items(context_items)
        context_redaction_stats = {"enabled": True, "secret_hits": sh, "path_hits": ph}
        if reasoning_out:
            reasoning_out, _ = redact_secret_patterns(reasoning_out)

    con.execute(
        """INSERT INTO sessions (id, user_id, created_at, active_skills, turn_count) VALUES (?, ?, ?, ?, 1)
           ON CONFLICT(id) DO UPDATE SET active_skills = ?, turn_count = turn_count + 1""",
        (sid, user_id, time.time(), json.dumps(picked_names), json.dumps(picked_names)),
    )
    con.commit()
    for n in picked_names:
        update_skill_stat(con, n, "uses", 1, user_id=user_id)

    event = {
        "type": "route",
        "session_id": sid,
        "user_id": user_id,
        "prompt": safe_prompt_snip,
        "candidates": [{"name": s.name, "score": sc} for s, sc in candidates[:10]],
        "picked": picked_names,
        "reasoning": reasoning_out,
        "rerouted": rerouted,
        "change_pct": round(change * 100, 1),
        "route_ms": round(route_ms, 1),
        "ts": time.time(),
        "context_mode": router.context_mode,
        "context_items_count": len(context_items),
        "project_rag_items_count": project_rag_items_count,
        "include_project_rag": bool(include_project_rag and pr),
        "context_fusion": context_fusion,
        "context_redaction": context_redaction_stats,
        "policy": {
            "rules_loaded": len(policies_cfg.get("rules") or []) if isinstance(policies_cfg.get("rules"), list) else 0,
            "audit": policy_audit,
        },
        "chunk_sources_preview": [
            {
                "skill": c.get("skill"),
                "path": c.get("path"),
                "line_start": c.get("line_start"),
                "line_end": c.get("line_end"),
                "mmr_rank": c.get("mmr_rank"),
            }
            for c in context_items[:24]
        ],
    }
    log_event(con, sid, "route", event, user_id=user_id)
    return {
        "session_id": sid,
        "picked_names": picked_names,
        "reasoning": reasoning_out,
        "candidates": candidates,
        "route_ms": route_ms,
        "rerouted": rerouted,
        "change": change,
        "event": event,
        "context_items": context_items,
    }
