"""Lightweight tests (stdlib + app.db_paths only)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.db_paths import global_db_path, resolve_orchestrator_db


def test_resolve_orchestrator_db_empty_uses_global(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    global_db = tmp_path / "global.db"
    monkeypatch.delenv("SKILLFORGE_PROJECT_ROOT", raising=False)
    monkeypatch.setenv("SKILLFORGE_DB_PATH", str(global_db))
    assert resolve_orchestrator_db("") == global_db
    assert resolve_orchestrator_db(None) == global_db
    assert resolve_orchestrator_db("  ") == global_db


def test_resolve_orchestrator_db_project_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("SKILLFORGE_PROJECT_ROOT", raising=False)
    monkeypatch.setenv("SKILLFORGE_DB_PATH", str(tmp_path / "ignored.db"))
    proj = tmp_path / "myrepo"
    proj.mkdir()
    expected = proj / ".skillforge" / "orchestrator.db"
    assert resolve_orchestrator_db(str(proj)) == expected


def test_resolve_orchestrator_db_env_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SKILLFORGE_DB_PATH", str(tmp_path / "global.db"))
    proj = tmp_path / "w"
    proj.mkdir()
    monkeypatch.setenv("SKILLFORGE_PROJECT_ROOT", str(proj))
    assert resolve_orchestrator_db("") == proj / ".skillforge" / "orchestrator.db"


def test_global_db_path_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    p = tmp_path / "x.db"
    monkeypatch.setenv("SKILLFORGE_DB_PATH", str(p))
    assert global_db_path() == p
