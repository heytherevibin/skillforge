"""Tests for context redaction (stdlib)."""
from __future__ import annotations

import app.redaction as R
from app.redaction import (
    redact_context_path_field,
    redact_home_path_prefix,
    redact_secret_patterns,
    sanitize_context_items,
)


def test_redact_anthropic_key_shape() -> None:
    t, n = redact_secret_patterns(
        "token sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"
    )
    assert n >= 1
    assert "sk-ant-api" not in t
    assert "[REDACTED_ANTHROPIC_KEY]" in t


def test_redact_assignment_line() -> None:
    t, n = redact_secret_patterns("export ANTHROPIC_API_KEY=sk-not-real-value-here")
    assert n >= 1
    assert "sk-not-real" not in t


def test_redact_home_path_prefix() -> None:
    R._HOME_RESOLVED = "/Users/testuser"
    s, n = redact_home_path_prefix("/Users/testuser/repos/app/main.py")
    assert n == 1
    assert s == "[HOME]/repos/app/main.py"
    R._HOME_RESOLVED = None  # reset for other tests


def test_sanitize_context_mutates_text_and_path() -> None:
    R._HOME_RESOLVED = "/Users/x"
    items = [
        {"skill": "s", "path": "/Users/x/p/a.py", "text": "k sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAAAAAAAA", "line_start": 1, "line_end": 2},
    ]
    sh, ph = sanitize_context_items(items)
    assert sh >= 1
    assert ph >= 1
    assert "sk-ant" not in items[0]["text"]
    assert str(items[0]["path"]).startswith("[HOME]/")
    R._HOME_RESOLVED = None


def test_redact_context_path_none() -> None:
    s, n = redact_context_path_field(None)
    assert s is None and n == 0
