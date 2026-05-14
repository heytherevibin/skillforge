"""Router LLM transient retry policy."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app import router_llm as rl


def test_is_router_llm_retryable_http_status() -> None:
    class E(Exception):
        status_code = 503

    assert rl.is_router_llm_retryable(E()) is True

    class F(Exception):
        status_code = 400

    assert rl.is_router_llm_retryable(F()) is False


def _openai_stub() -> rl.OpenAIRouterLLM:
    llm = object.__new__(rl.OpenAIRouterLLM)
    llm._client = MagicMock()
    llm._client.chat = MagicMock()
    llm._client.chat.completions = MagicMock()
    llm.default_model = "m"
    llm.backend_name = "openai_compatible"
    return llm


def test_openai_complete_retries_then_ok(monkeypatch) -> None:
    monkeypatch.setenv("SKILLFORGE_ROUTER_LLM_RETRIES", "3")
    monkeypatch.setattr(rl.asyncio, "sleep", AsyncMock())

    async def body() -> None:
        llm = _openai_stub()
        ok = MagicMock()
        ok.choices = [MagicMock(message=MagicMock(content=" ok "))]
        err = type("Err", (Exception,), {})()
        err.status_code = 503
        llm._client.chat.completions.create = AsyncMock(side_effect=[err, ok])
        text = await rl.OpenAIRouterLLM.complete(llm, system="s", user="u", max_tokens=5, model="m")
        assert text == "ok"
        assert llm._client.chat.completions.create.await_count == 2

    asyncio.run(body())


def test_openai_no_retry_when_attempts_one(monkeypatch) -> None:
    monkeypatch.setenv("SKILLFORGE_ROUTER_LLM_RETRIES", "1")
    monkeypatch.setattr(rl.asyncio, "sleep", AsyncMock())

    async def body() -> None:
        llm = _openai_stub()
        err = type("Err", (Exception,), {})()
        err.status_code = 503
        llm._client.chat.completions.create = AsyncMock(side_effect=err)
        with pytest.raises(Exception) as ei:
            await rl.OpenAIRouterLLM.complete(llm, system="s", user="u", max_tokens=5, model="m")
        assert getattr(ei.value, "status_code", None) == 503
        assert llm._client.chat.completions.create.await_count == 1

    asyncio.run(body())
