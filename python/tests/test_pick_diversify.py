"""Tests for SKILLFORGE_PICK_DIVERSIFY trimming."""
from __future__ import annotations

from dataclasses import dataclass

import pytest


@dataclass
class _Sk:
    name: str
    source: str


def test_diversify_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("SKILLFORGE_PICK_DIVERSIFY", raising=False)
    from app.pick_diversify import diversify_picked_names

    by = {"a": _Sk("a", "bundled"), "b": _Sk("b", "bundled")}
    out, meta = diversify_picked_names(["a", "b", "c"], by)
    assert out == ["a", "b", "c"]
    assert meta["applied"] is False


def test_diversify_caps_per_source(monkeypatch) -> None:
    monkeypatch.setenv("SKILLFORGE_PICK_DIVERSIFY", "1")
    monkeypatch.setenv("SKILLFORGE_PICK_MAX_PER_SOURCE", "2")
    from app.pick_diversify import diversify_picked_names

    by = {f"s{i}": _Sk(f"s{i}", "bundled") for i in range(5)}
    names = ["s0", "s1", "s2", "s3"]
    out, meta = diversify_picked_names(names, by)
    assert out == ["s0", "s1"]
    assert meta["dropped"] == ["s2", "s3"]
    assert meta["applied"] is True


@pytest.mark.parametrize("truthy", ["1", "true", "yes"])
def test_diversify_env_truthy(monkeypatch, truthy) -> None:
    monkeypatch.setenv("SKILLFORGE_PICK_DIVERSIFY", truthy)
    monkeypatch.setenv("SKILLFORGE_PICK_MAX_PER_SOURCE", "1")
    from app.pick_diversify import diversify_picked_names

    by = {"x": _Sk("x", "user"), "y": _Sk("y", "user")}
    out, meta = diversify_picked_names(["x", "y"], by)
    assert out == ["x"]
    assert "y" in meta["dropped"]
