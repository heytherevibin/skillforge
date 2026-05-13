"""SKILL manifest validation rules."""

from __future__ import annotations

from app.main import load_all_skills, parse_skill_md
from app.skill_manifest import validate_skill_manifest


def test_validate_manifest_warns_without_frontmatter(tmp_path) -> None:
    d = tmp_path / "my-skill"
    d.mkdir()
    md = d / "SKILL.md"
    md.write_text("# Hello\n\nBody text here " * 20, encoding="utf-8")
    s = parse_skill_md(md, "user")
    assert s is not None
    errs, warns = validate_skill_manifest(s, md)
    assert errs == []
    assert any("frontmatter" in w for w in warns)


def test_load_all_skills_skips_bad_manifest_only_when_strict(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SKILLFORGE_BUNDLED_SKILLS", str(tmp_path / "bundled"))
    monkeypatch.setenv("SKILLFORGE_USER_SKILLS", str(tmp_path / "user"))

    bundled = tmp_path / "bundled" / "ok-skill"
    bundled.mkdir(parents=True)
    (bundled / "SKILL.md").write_text(
        "---\nname: OK\ndescription: " + ("x" * 50) + "\n---\n\n# OK\nbody " * 30,
        encoding="utf-8",
    )
    weird = tmp_path / "bundled" / "Weird_Case_Skill"
    weird.mkdir(parents=True)
    (weird / "SKILL.md").write_text(
        "---\nname: Weird\ndescription: " + ("y" * 50) + "\n---\n\nbody " * 30,
        encoding="utf-8",
    )

    monkeypatch.setenv("SKILLFORGE_SKILL_MANIFEST_STRICT", "0")
    lax = load_all_skills(manifest_log_prefix="[test]")
    lax_names = {x.name for x in lax}
    assert "ok-skill" in lax_names
    assert "Weird_Case_Skill" in lax_names

    monkeypatch.setenv("SKILLFORGE_SKILL_MANIFEST_STRICT", "1")
    strict = load_all_skills(manifest_log_prefix="[test]")
    names = {x.name for x in strict}
    assert "ok-skill" in names
    assert "Weird_Case_Skill" not in names
