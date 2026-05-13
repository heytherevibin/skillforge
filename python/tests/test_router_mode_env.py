"""SKILLFORGE_ROUTER_MODE normalization (default host vs explicit auto)."""
from __future__ import annotations

from app.router_mode import normalise_skillforge_router_mode


def test_normalise_defaults_to_literal_host_from_value() -> None:
    assert normalise_skillforge_router_mode("host") == "host"
    assert normalise_skillforge_router_mode("HOST") == "host"


def test_normalise_auto_aliases() -> None:
    assert normalise_skillforge_router_mode("") == ""
    assert normalise_skillforge_router_mode("   ") == ""
    assert normalise_skillforge_router_mode("auto") == ""
    assert normalise_skillforge_router_mode("AuTo") == ""


def test_normalise_embedding_full() -> None:
    assert normalise_skillforge_router_mode("embedding") == "embedding"
    assert normalise_skillforge_router_mode("full") == "full"
