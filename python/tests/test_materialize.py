"""Tests for project bootstrap file writes."""

from __future__ import annotations

from pathlib import Path

from app.materialize import materialize_project_files


def test_materialize_writes_cursor_command(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    out = materialize_project_files(
        str(root),
        ["alpha"],
        {"alpha": "desc"},
        merge=True,
    )
    rel = {Path(p).as_posix() for p in out["written"]}
    assert ".cursor/commands/skillforge.md" in rel
    assert ".claude/commands/skillforge.md" in rel
    cc = root / ".claude" / "commands" / "skillforge.md"
    assert cc.is_file()
    cct = cc.read_text(encoding="utf-8")
    assert "route_skills" in cct
    assert "alpha" in cct
    cur = root / ".cursor" / "commands" / "skillforge.md"
    assert "alpha" in cur.read_text(encoding="utf-8")


def test_materialize_merge_false_skips_existing_command(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    cmd = root / ".cursor" / "commands" / "skillforge.md"
    cmd.parent.mkdir(parents=True)
    cmd.write_text("keep-me", encoding="utf-8")
    rule = root / ".cursor" / "rules" / "skillforge.mdc"
    rule.parent.mkdir(parents=True, exist_ok=True)
    rule.write_text("keep-rule", encoding="utf-8")
    ccmd = root / ".claude" / "commands" / "skillforge.md"
    ccmd.parent.mkdir(parents=True, exist_ok=True)
    ccmd.write_text("keep-cc", encoding="utf-8")
    materialize_project_files(
        str(root),
        ["b"],
        {},
        merge=False,
    )
    assert cmd.read_text(encoding="utf-8") == "keep-me"
    assert rule.read_text(encoding="utf-8") == "keep-rule"
    assert ccmd.read_text(encoding="utf-8") == "keep-cc"
