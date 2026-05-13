"""materialize_project hosts= cursor | claude_code | both."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.materialize import (
    infer_materialize_hosts_from_mcp_client,
    materialize_project_files,
    normalize_materialize_hosts,
    resolve_materialize_hosts_argument,
)


def test_infer_materialize_hosts_from_mcp_client() -> None:
    assert infer_materialize_hosts_from_mcp_client("cursor-vscode-fork", "") == "cursor"
    assert infer_materialize_hosts_from_mcp_client("", "Claude Code") == "claude_code"
    assert infer_materialize_hosts_from_mcp_client("", "", environ={}) == "both"
    assert infer_materialize_hosts_from_mcp_client("", "", environ={"CURSOR_AGENT": "1"}) == "cursor"


def test_resolve_materialize_hosts_argument_explicit_wins_inference() -> None:
    mode, meta = resolve_materialize_hosts_argument(
        "both",
        client_name="cursor-ai",
        environ={"SKILLFORGE_MATERIALIZE_HOSTS": "claude_code"},
    )
    assert mode == "both"
    assert meta["hosts_resolution"] == "explicit"


def test_resolve_materialize_hosts_argument_auto_infer() -> None:
    mode, meta = resolve_materialize_hosts_argument(
        "auto",
        client_name="Cursor IDE",
    )
    assert mode == "cursor"
    assert meta["hosts_resolution"] == "inferred"


def test_resolve_materialize_hosts_argument_env_when_auto() -> None:
    mode, meta = resolve_materialize_hosts_argument(
        None,
        client_name="",
        environ={"SKILLFORGE_MATERIALIZE_HOSTS": "cursor"},
    )
    assert mode == "cursor"
    assert meta["hosts_resolution"] == "environment"


def test_resolve_infer_beats_blank_env_skillforge_var_not_set_on_client() -> None:
    """Client name wins before falling back when SKILLFORGE_MATERIALIZE_HOSTS absent."""
    mode, meta = resolve_materialize_hosts_argument(
        None,
        client_name="com.anthropic.claude-code-helper",
        client_title="",
        environ={},
    )
    assert mode == "claude_code"
    assert meta["hosts_resolution"] == "inferred"


def test_resolve_environment_overrides_client_inference() -> None:
    mode, meta = resolve_materialize_hosts_argument(
        None,
        client_name="Cursor IDE",
        environ={"SKILLFORGE_MATERIALIZE_HOSTS": "claude_code"},
    )
    assert mode == "claude_code"
    assert meta["hosts_resolution"] == "environment"


def test_normalize_materialize_hosts() -> None:
    assert normalize_materialize_hosts(None) == "both"
    assert normalize_materialize_hosts("  BOTH  ") == "both"
    assert normalize_materialize_hosts("cursor") == "cursor"
    assert normalize_materialize_hosts("claude-code") == "claude_code"
    assert normalize_materialize_hosts("claude") == "claude_code"
    with pytest.raises(ValueError, match="hosts must be"):
        normalize_materialize_hosts("vscode")


def test_hosts_cursor_writes_no_claude_paths(tmp_path) -> None:
    root = tmp_path / "p"
    root.mkdir()
    out = materialize_project_files(str(root), ["x"], {"x": "y"}, hosts="cursor")
    rel = {Path(p).as_posix() for p in out["written"]}
    assert ".cursor/commands/skillforge.md" in rel
    assert ".cursor/rules/skillforge.mdc" in rel
    assert "docs/SKILLFORGE-PRD.md" in rel
    assert ".claude/commands/skillforge.md" not in rel
    assert "CLAUDE.md" not in rel
    assert not (root / ".claude").exists()


def test_hosts_claude_code_writes_no_cursor_paths(tmp_path) -> None:
    root = tmp_path / "p"
    root.mkdir()
    out = materialize_project_files(str(root), ["x"], {"x": "y"}, hosts="claude_code")
    rel = {Path(p).as_posix() for p in out["written"]}
    assert ".claude/commands/skillforge.md" in rel
    assert "CLAUDE.md" in rel
    assert "docs/SKILLFORGE-PRD.md" in rel
    assert ".cursor/commands/skillforge.md" not in rel
    assert ".cursor/rules/skillforge.mdc" not in rel
    assert not (root / ".cursor").exists()
