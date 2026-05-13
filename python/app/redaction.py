"""Best-effort redaction of secrets and user home paths in exported context (defense in depth)."""
from __future__ import annotations

import os
import re
from pathlib import Path

_HOME_RESOLVED: str | None = None


def redaction_enabled() -> bool:
    return os.getenv("SKILLFORGE_REDACT_CONTEXT", "1").strip().lower() not in ("0", "false", "no", "")


def redact_home_in_paths_enabled() -> bool:
    return os.getenv("SKILLFORGE_REDACT_HOME_IN_PATHS", "1").strip().lower() not in ("0", "false", "no", "")


def _home_prefix() -> str | None:
    global _HOME_RESOLVED
    if _HOME_RESOLVED is not None:
        return _HOME_RESOLVED or None
    try:
        _HOME_RESOLVED = str(Path.home().resolve())
    except Exception:
        _HOME_RESOLVED = ""
    return _HOME_RESOLVED or None


COMPILED: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"sk-ant-api\d\d-[A-Za-z0-9_\-]{20,}"), "[REDACTED_ANTHROPIC_KEY]"),
    (re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b"), "[REDACTED_GOOGLE_API_KEY]"),
    (re.compile(r"xox[baprs]-[0-9A-Za-z\-]{10,}"), "[REDACTED_SLACK_TOKEN]"),
    (re.compile(r"gh[pP]_[0-9A-Za-z]{36,}"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"github_pat_[0-9A-Za-z_]{20,}"), "[REDACTED_GITHUB_PAT]"),
    (re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
        re.MULTILINE,
    ), "[REDACTED_PRIVATE_KEY]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_ACCESS_KEY_ID]"),
    (re.compile(r"\bASIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_TEMP_KEY_ID]"),
    # OAuth / Bearer-style (avoid eating normal words — require length)
    (re.compile(r"\bBearer\s+[A-Za-z0-9\-._~+/]{16,}={0,2}\b", re.IGNORECASE), "Bearer [REDACTED]"),
    (re.compile(r"\bBasic\s+[A-Za-z0-9+/]{16,}={0,2}\b", re.IGNORECASE), "Basic [REDACTED]"),
    # Env assignment leaks in pasted logs
    (re.compile(
        r"\b(ANTHROPIC_API_KEY|OPENAI_API_KEY|"
        r"AWS_SECRET_ACCESS_KEY|AWS_SESSION_TOKEN|GITHUB_TOKEN|"
        r"HF_TOKEN|HUGGINGFACE_TOKEN|SLACK_BOT_TOKEN|DATABASE_URL|"
        r"SUPABASE_SERVICE_ROLE_KEY|SUPABASE_JWT_SECRET)\s*=\s*(\S+)",
        re.IGNORECASE,
    ), r"\1=[REDACTED]"),
]


def redact_secret_patterns(text: str) -> tuple[str, int]:
    """Replace known secret shapes; returns ``(new_text, number_of_pattern_matches)``."""
    if not text:
        return text, 0
    hits = 0
    out = text
    for pat, repl in COMPILED:
        found = pat.findall(out)
        if found:
            hits += len(found)
            out = pat.sub(repl, out)
    return out, hits


def redact_home_path_prefix(path: str) -> tuple[str, int]:
    """If ``path`` starts with the resolved home directory, replace that prefix with ``[HOME]``."""
    if not path or not redact_home_in_paths_enabled():
        return path, 0
    home = _home_prefix()
    if not home:
        return path, 0
    # Normalize slashes for comparison
    norm = path.replace("\\", "/")
    home_n = home.replace("\\", "/")
    if norm == home_n or norm.rstrip("/") == home_n.rstrip("/"):
        return "[HOME]", 1
    if norm.startswith(home_n + "/") or norm.startswith(home_n + "\\"):
        rest = path[len(home) :].lstrip("/\\")
        return "[HOME]/" + rest.replace("\\", "/"), 1
    # Windows-style profile (best effort when HOME is /Users/x but path is C:\Users\x)
    if len(path) > 3 and path[1] == ":":
        try:
            from os.path import expanduser

            eu = expanduser("~")
            if eu and path.lower().startswith(eu.lower().replace("/", "\\")):
                return "[HOME]/" + path[len(eu) :].lstrip("\\/").replace("\\", "/"), 1
        except Exception:
            pass
    return path, 0


def redact_context_path_field(path: str | None) -> tuple[str | None, int]:
    if not path:
        return path, 0
    s, n = redact_home_path_prefix(path)
    return s, n


def sanitize_context_items(items: list[dict]) -> tuple[int, int]:
    """Mutate each item's ``text`` / ``path`` in place. Returns ``(secret_hits, path_hits)``."""
    sh = ph = 0
    for c in items:
        t = c.get("text") or ""
        nt, h = redact_secret_patterns(t)
        if h:
            sh += h
            c["text"] = nt
        p = c.get("path")
        if p is not None:
            np, h2 = redact_context_path_field(str(p))
            if h2:
                ph += h2
                c["path"] = np
    return sh, ph


def redact_display_path(p: str | Path) -> str:
    """Single path string safe for logs / ``_meta`` (home prefix only + pattern redaction)."""
    s = str(p)
    s, _ = redact_home_path_prefix(s)
    s, _ = redact_secret_patterns(s)
    return s
