"""Published npm semver for MCP ``serverInfo`` (keeps MCP in sync with ``package/package.json``)."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

NPM_PACKAGE_NAME = "@heytherevibin/skillforge"


@lru_cache(maxsize=1)
def published_package_version() -> str:
    """Return ``version`` from the nearest ancestor ``package.json`` for this npm package.

    Fallback ``0.0.0`` when the file tree does not contain the manifest (e.g. partial copy).
    Optional override: ``SKILLFORGE_MCP_SERVER_VERSION`` for operators embedding a custom string.
    """
    override = os.getenv("SKILLFORGE_MCP_SERVER_VERSION", "").strip()
    if override:
        return override
    here = Path(__file__).resolve()
    for d in here.parents:
        pj = d / "package.json"
        if not pj.is_file():
            continue
        try:
            data = json.loads(pj.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            continue
        if data.get("name") == NPM_PACKAGE_NAME:
            v = str(data.get("version") or "").strip()
            return v or "0.0.0"
    return "0.0.0"


def clear_version_cache_for_tests() -> None:
    published_package_version.cache_clear()
