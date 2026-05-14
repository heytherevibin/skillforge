"""Pluggable backend for Router rerank + final-pick LLM phases.

When ``SKILLFORGE_TRANSPORT=mcp`` (stdio MCP only), only Anthropic-backed clients
are wired from ``build_router_and_skills`` (legacy semantics).

Standalone CLI may set ``SKILLFORGE_ROUTER_LLM_BACKEND=openai_compatible`` targeting
``OPENAI_API_BASE`` (e.g. Ollama ``http://localhost:11434/v1``).
"""
from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar

from anthropic import AsyncAnthropic

T = TypeVar("T")


class RouterLLM(Protocol):
    backend_name: str

    async def complete(self, *, system: str, user: str, max_tokens: int, model: str) -> str: ...


def transport_is_mcp() -> bool:
    return os.getenv("SKILLFORGE_TRANSPORT", "").strip().lower() == "mcp"


def router_llm_max_attempts() -> int:
    raw = os.getenv("SKILLFORGE_ROUTER_LLM_RETRIES", "1").strip() or "1"
    try:
        n = int(raw)
    except ValueError:
        return 1
    return max(1, min(n, 8))


def is_router_llm_retryable(exc: BaseException) -> bool:
    """Heuristic: HTTP status / SDK names that are usually safe to retry once or twice."""
    sc = getattr(exc, "status_code", None)
    if isinstance(sc, int) and sc in (408, 425, 429, 500, 502, 503, 504):
        return True
    resp = getattr(exc, "response", None)
    if resp is not None:
        rsc = getattr(resp, "status_code", None)
        if isinstance(rsc, int) and rsc in (408, 425, 429, 500, 502, 503, 504):
            return True
    mod = getattr(type(exc), "__module__", "")
    name = type(exc).__name__
    if "anthropic" in mod and name in ("RateLimitError", "APIConnectionError", "APITimeoutError"):
        return True
    if "openai" in mod and name in ("RateLimitError", "APIConnectionError", "APITimeoutError"):
        return True
    if "httpx" in mod and name in (
        "ReadTimeout",
        "ConnectTimeout",
        "ConnectError",
        "RemoteProtocolError",
        "WriteError",
    ):
        return True
    return False


async def run_router_llm_attempts(fn: Callable[[], Awaitable[T]]) -> T:
    """Run ``fn`` with exponential backoff on retryable failures."""
    attempts = router_llm_max_attempts()
    for i in range(attempts):
        try:
            return await fn()
        except BaseException as exc:
            if i >= attempts - 1 or not is_router_llm_retryable(exc):
                raise
            await asyncio.sleep(min(8.0, 0.5 * (2**i)))
    raise RuntimeError("run_router_llm_attempts: unreachable")  # pragma: no cover


class AnthropicRouterLLM:
    __slots__ = ("client", "backend_name")

    def __init__(self, client: AsyncAnthropic) -> None:
        self.client = client
        self.backend_name = "anthropic"

    async def complete(self, *, system: str, user: str, max_tokens: int, model: str) -> str:
        async def once() -> str:
            resp = await self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            block = resp.content[0]
            return block.text.strip()  # type: ignore[attr-defined]

        return await run_router_llm_attempts(once)


class OpenAIRouterLLM:
    __slots__ = ("_client", "default_model", "backend_name")

    def __init__(self, *, api_key: str, base_url: str, default_model: str) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key or "ollama", base_url=base_url.rstrip("/"))
        self.default_model = default_model
        self.backend_name = "openai_compatible"

    async def complete(self, *, system: str, user: str, max_tokens: int, model: str) -> str:
        m = model or self.default_model

        async def once() -> str:
            resp = await self._client.chat.completions.create(
                model=m,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0,
            )
            choice = resp.choices[0]
            return (choice.message.content or "").strip()

        return await run_router_llm_attempts(once)


def resolve_openai_router_defaults() -> tuple[str, str, str]:
    base = (
        os.getenv("OPENAI_API_BASE", "").strip()
        or os.getenv("SKILLFORGE_OPENAI_API_BASE", "").strip()
        or "http://localhost:11434/v1"
    )
    api_key = (
        os.getenv("OPENAI_API_KEY", "").strip()
        or os.getenv("SKILLFORGE_OPENAI_API_KEY", "").strip()
    )
    model = (
        os.getenv("SKILLFORGE_OPENAI_ROUTER_MODEL", "").strip()
        or os.getenv("SKILLFORGE_CHAT_MODEL", "").strip()
        or "llama3.2"
    )
    return base, api_key, model
