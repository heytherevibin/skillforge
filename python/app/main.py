"""
skillforge — adaptive skill orchestrator for Claude.

Architecture:
    Client → /chat → Orchestrator
                       ├─ Embeddings: prompt vs all skills → top 15 candidates
                       ├─ LLM router (Haiku): picks final 3-7
                       ├─ Apply learned bias from past usage
                       ├─ Inject SKILL.md content into system prompt
                       └─ Stream Claude response back
                     ↓
                  SQLite (telemetry + learning state)
                     ↓
                  /dashboard (live observability)
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from anthropic import AsyncAnthropic
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

# ---------- Config (env-driven so the Node wrapper controls paths) ----------
BUNDLED_SKILLS = Path(os.getenv("SKILLFORGE_BUNDLED_SKILLS", "./skills"))
USER_SKILLS = Path(os.getenv("SKILLFORGE_USER_SKILLS", str(Path.home() / ".skillforge" / "skills")))
DB_PATH = Path(os.getenv("SKILLFORGE_DB_PATH", str(Path.home() / ".skillforge" / "data" / "orchestrator.db")))
EMBED_MODEL = os.getenv("SKILLFORGE_EMBED_MODEL", "all-MiniLM-L6-v2")
ROUTER_MODEL = os.getenv("SKILLFORGE_ROUTER_MODEL", "claude-haiku-4-5-20251001")
ANSWER_MODEL = os.getenv("SKILLFORGE_ANSWER_MODEL", "claude-opus-4-7")
TOP_K_CANDIDATES = int(os.getenv("SKILLFORGE_TOP_K", "15"))
MAX_ACTIVE_SKILLS = int(os.getenv("SKILLFORGE_MAX_ACTIVE", "7"))
REROUTE_THRESHOLD = float(os.getenv("SKILLFORGE_REROUTE_THRESHOLD", "0.4"))

STATIC_DIR = Path(__file__).parent.parent / "static"


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
                i += 1
    if not description:
        for chunk in body.split("\n\n"):
            chunk = chunk.strip()
            if chunk and not chunk.startswith("#"):
                description = chunk[:500]
                break
    return Skill(name=name, title=title, description=description, body=body, source=source)


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


# ---------- Database ----------
def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
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
    def __init__(self, skills, embed_model, anthropic):
        self.skills = skills
        self.embed_model = embed_model
        self.anthropic = anthropic
        texts = [f"{s.title}: {s.description}" for s in skills]
        print(f"[skillforge] Embedding {len(skills)} skills...")
        embeddings = embed_model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
        for s, e in zip(skills, embeddings):
            s.embedding = e / np.linalg.norm(e)
        self.matrix = np.stack([s.embedding for s in skills]) if skills else np.zeros((0, 0))
        print(f"[skillforge] Ready. {len(skills)} skills, matrix shape: {self.matrix.shape}")

    def shortlist(self, prompt, con, k=TOP_K_CANDIDATES, user_id=""):
        if len(self.skills) == 0:
            return []
        q = self.embed_model.encode(prompt, convert_to_numpy=True)
        q = q / np.linalg.norm(q)
        sims = self.matrix @ q
        biased = sims.copy()
        for i, s in enumerate(self.skills):
            w, disabled = get_skill_weight(con, s.name, user_id=user_id)
            if disabled:
                biased[i] = -999.0
            else:
                biased[i] += w
        top_idx = np.argsort(-biased)[:k]
        return [(self.skills[i], float(sims[i])) for i in top_idx if biased[i] > -100]

    async def pick_final(self, prompt, conversation, candidates):
        if not candidates:
            return [], "no candidates available"
        catalog = "\n".join(
            f"- {s.name}: {s.description[:200]}" for s, _ in candidates
        )
        recent = ""
        if conversation:
            recent = "\n\nRecent conversation:\n" + "\n".join(
                f"{m['role']}: {m['content'][:200]}" for m in conversation[-4:]
            )
        sys = (
            "You are a skill router. Given a user prompt and a candidate list of skills, "
            f"pick 0 to {MAX_ACTIVE_SKILLS} skills that would genuinely help answer this prompt. "
            "Be ruthless — only include a skill if it directly applies. Empty list is valid. "
            'Respond ONLY in JSON: {"skills": ["name1","name2"], "reasoning": "one sentence"}'
        )
        user = f"User prompt:\n{prompt}{recent}\n\nCandidate skills:\n{catalog}"
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


# ---------- App ----------
app_state: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[skillforge] Loading skills from {BUNDLED_SKILLS} + {USER_SKILLS}")
    skills = load_all_skills()
    print(f"[skillforge] Loaded {len(skills)} skills")
    if not skills:
        print("[skillforge] WARNING: no skills found")
    embed_model = SentenceTransformer(EMBED_MODEL)
    anthropic = AsyncAnthropic()
    router = Router(skills, embed_model, anthropic)
    con = init_db()
    app_state.update(
        skills={s.name: s for s in skills},
        router=router,
        anthropic=anthropic,
        con=con,
        websockets=set(),
    )
    yield
    con.close()


app = FastAPI(lifespan=lifespan, title="skillforge")


class ChatRequest(BaseModel):
    prompt: str
    session_id: str | None = None
    conversation: list[dict] = []


class FeedbackRequest(BaseModel):
    session_id: str
    skill_name: str
    thumbs: int


class DisableRequest(BaseModel):
    skill_name: str
    disabled: bool


async def broadcast(event):
    dead = set()
    for ws in app_state.get("websockets", set()):
        try:
            await ws.send_json(event)
        except Exception:
            dead.add(ws)
    app_state["websockets"] -= dead


@app.post("/chat")
async def chat(req: ChatRequest, request: Request):
    from app.auth import resolve_user
    user_id = resolve_user(request)
    router: Router = app_state["router"]
    con = app_state["con"]
    anthropic: AsyncAnthropic = app_state["anthropic"]
    session_id = req.session_id or str(uuid.uuid4())

    t0 = time.time()
    candidates = router.shortlist(req.prompt, con, user_id=user_id)
    picked_names, reasoning = await router.pick_final(req.prompt, req.conversation, candidates)
    route_ms = (time.time() - t0) * 1000

    prev_active = set()
    cur = con.execute(
        "SELECT active_skills FROM sessions WHERE id = ? AND user_id = ?",
        (session_id, user_id),
    )
    row = cur.fetchone()
    if row and row[0]:
        prev_active = set(json.loads(row[0]))
    change = jaccard_change(prev_active, set(picked_names))
    rerouted = change >= REROUTE_THRESHOLD and bool(prev_active)

    con.execute(
        """INSERT INTO sessions (id, user_id, created_at, active_skills, turn_count) VALUES (?, ?, ?, ?, 1)
           ON CONFLICT(id) DO UPDATE SET active_skills = ?, turn_count = turn_count + 1""",
        (session_id, user_id, time.time(), json.dumps(picked_names), json.dumps(picked_names)),
    )
    con.commit()
    for n in picked_names:
        update_skill_stat(con, n, "uses", 1, user_id=user_id)

    skills_map = app_state["skills"]
    skill_blocks = []
    for n in picked_names:
        s = skills_map.get(n)
        if s:
            skill_blocks.append(f'<skill name="{s.name}">\n{s.body}\n</skill>')
    system_prompt = (
        "You are a helpful assistant. The following skills have been dynamically loaded "
        "for this turn based on the user's request. Use them when relevant; ignore them when not.\n\n"
        + "\n\n".join(skill_blocks)
    ) if skill_blocks else "You are a helpful assistant."

    event = {
        "type": "route",
        "session_id": session_id,
        "user_id": user_id,
        "prompt": req.prompt[:300],
        "candidates": [{"name": s.name, "score": sc} for s, sc in candidates[:10]],
        "picked": picked_names,
        "reasoning": reasoning,
        "rerouted": rerouted,
        "change_pct": round(change * 100, 1),
        "route_ms": round(route_ms, 1),
        "ts": time.time(),
    }
    log_event(con, session_id, "route", event, user_id=user_id)
    await broadcast(event)

    messages = req.conversation + [{"role": "user", "content": req.prompt}]

    async def stream():
        full_text = []
        try:
            async with anthropic.messages.stream(
                model=ANSWER_MODEL,
                max_tokens=4096,
                system=system_prompt,
                messages=messages,
            ) as s:
                async for chunk in s.text_stream:
                    full_text.append(chunk)
                    yield f"data: {json.dumps({'delta': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return
        response_text = "".join(full_text)
        for n in picked_names:
            s = skills_map.get(n)
            if not s:
                continue
            keywords = [w for w in s.body.split()[:50] if len(w) > 6][:5]
            hits = sum(1 for kw in keywords if kw.lower() in response_text.lower())
            if hits >= 2 or s.name in response_text.lower():
                update_skill_stat(con, n, "referenced", 1, user_id=user_id)
        yield f"data: {json.dumps({'done': True, 'session_id': session_id, 'picked': picked_names})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/feedback")
def feedback(req: FeedbackRequest, request: Request):
    from app.auth import resolve_user
    user_id = resolve_user(request)
    con = app_state["con"]
    field = "thumbs_up" if req.thumbs > 0 else "thumbs_down"
    update_skill_stat(con, req.skill_name, field, 1, user_id=user_id)
    log_event(con, req.session_id, "feedback",
              {"skill": req.skill_name, "thumbs": req.thumbs},
              user_id=user_id)
    return {"ok": True}


@app.post("/skills/disable")
def disable(req: DisableRequest, request: Request):
    from app.auth import resolve_user
    user_id = resolve_user(request)
    con = app_state["con"]
    set_skill_disabled(con, req.skill_name, req.disabled, user_id=user_id)
    return {"ok": True}


@app.get("/skills")
def list_skills(request: Request):
    from app.auth import resolve_user
    user_id = resolve_user(request)
    con = app_state["con"]
    skills_map = app_state["skills"]
    out = []
    for name, s in skills_map.items():
        cur = con.execute(
            "SELECT weight, uses, referenced, thumbs_up, thumbs_down, disabled FROM skill_weights WHERE user_id = ? AND skill_name = ?",
            (user_id, name),
        )
        row = cur.fetchone()
        weight, uses, ref, up, down, disabled = row if row else (0.0, 0, 0, 0, 0, 0)
        out.append({
            "name": name,
            "title": s.title,
            "description": s.description[:200],
            "source": s.source,
            "weight": weight,
            "uses": uses,
            "referenced": ref,
            "thumbs_up": up,
            "thumbs_down": down,
            "disabled": bool(disabled),
        })
    out.sort(key=lambda x: -x["uses"])
    return out


@app.get("/events")
def recent_events(request: Request, limit: int = 50):
    from app.auth import resolve_user, auth_enabled
    user_id = resolve_user(request)
    con = app_state["con"]
    if auth_enabled():
        cur = con.execute(
            "SELECT ts, session_id, event_type, payload FROM events WHERE user_id = ? ORDER BY ts DESC LIMIT ?",
            (user_id, limit),
        )
    else:
        cur = con.execute(
            "SELECT ts, session_id, event_type, payload FROM events ORDER BY ts DESC LIMIT ?",
            (limit,),
        )
    return [
        {"ts": ts, "session_id": sid, "type": et, "payload": json.loads(p)}
        for ts, sid, et, p in cur.fetchall()
    ]


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    app_state.setdefault("websockets", set()).add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        app_state["websockets"].discard(ws)


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return (STATIC_DIR / "dashboard.html").read_text(encoding="utf-8")


@app.get("/healthz")
def health():
    return {"skills_loaded": len(app_state.get("skills", {})), "ok": True}
