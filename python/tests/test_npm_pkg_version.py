"""published_package_version resolves package/package.json semver."""
from __future__ import annotations

from app.npm_pkg_version import NPM_PACKAGE_NAME, clear_version_cache_for_tests, published_package_version


def test_published_package_version_matches_repo_package_json(monkeypatch) -> None:
    monkeypatch.delenv("SKILLFORGE_MCP_SERVER_VERSION", raising=False)
    clear_version_cache_for_tests()
    v = published_package_version()
    assert v and len(v.split(".")) == 3


def test_published_package_version_env_override(monkeypatch) -> None:
    monkeypatch.setenv("SKILLFORGE_MCP_SERVER_VERSION", "9.8.7-test")
    clear_version_cache_for_tests()
    assert published_package_version() == "9.8.7-test"


def test_skillforge_package_name_constant() -> None:
    assert "skillforge" in NPM_PACKAGE_NAME
