"""
Bearer-token auth and per-user namespacing.

Single-user mode (default): no token required, all state goes to user_id=''.
Multi-user mode: set SKILLFORGE_AUTH_TOKENS env var to a JSON map of
{"token-value": "user-id"}. Requests must send Authorization: Bearer <token>.
The resolved user_id is then used to scope sessions, weights, and events.

This keeps the architecture single-process (one SQLite, one router instance)
while letting each user have isolated learning state.
"""
from __future__ import annotations

import json
import os
from typing import Optional

from fastapi import HTTPException, Request


# ---- Token registry ----

def _load_tokens() -> dict[str, str]:
    """Read SKILLFORGE_AUTH_TOKENS env (JSON: {token: user_id})."""
    raw = os.getenv("SKILLFORGE_AUTH_TOKENS", "").strip()
    if not raw:
        return {}
    try:
        m = json.loads(raw)
        if not isinstance(m, dict):
            print("[skillforge] SKILLFORGE_AUTH_TOKENS must be a JSON object")
            return {}
        return {str(k): str(v) for k, v in m.items()}
    except json.JSONDecodeError:
        print("[skillforge] SKILLFORGE_AUTH_TOKENS is not valid JSON, ignoring")
        return {}


_TOKENS = _load_tokens()
_AUTH_REQUIRED = bool(_TOKENS)


def auth_enabled() -> bool:
    return _AUTH_REQUIRED


def resolve_user(request: Request) -> str:
    """Get user_id from a request.

    - If auth is not configured (single-user mode): returns ''.
    - If auth is configured: extracts bearer token, returns mapped user_id,
      or raises 401.
    """
    if not _AUTH_REQUIRED:
        return ""
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = header[7:].strip()
    user_id = _TOKENS.get(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user_id
