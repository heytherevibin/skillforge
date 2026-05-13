"""Orchestrator SQLite path resolution (stdlib only — safe for lightweight tests)."""

from __future__ import annotations

import os
from pathlib import Path


def global_db_path() -> Path:
    return Path(
        os.getenv("SKILLFORGE_DB_PATH", str(Path.home() / ".skillforge" / "data" / "orchestrator.db"))
    )


def resolve_orchestrator_db(project_root: str | None) -> Path:
    """SQLite file: ``<project>/.skillforge/orchestrator.db`` when project_root is set, else global path.

    If ``project_root`` is empty, falls back to env ``SKILLFORGE_PROJECT_ROOT``, then global.
    """
    pr = (project_root or "").strip()
    if not pr:
        pr = os.getenv("SKILLFORGE_PROJECT_ROOT", "").strip()
    if pr:
        root = Path(pr).expanduser().resolve()
        return root / ".skillforge" / "orchestrator.db"
    return global_db_path()
