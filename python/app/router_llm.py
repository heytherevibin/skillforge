"""Pluggable backend for Router rerank + final-pick LLM phases.

When ``SKILLFORGE_TRANSPORT=mcp`` (stdio MCP only), only Anthropic-backed clients
are wired from ``build_router_and_skills`` (legacy semantics).

Standalone CLI may set ``SKILLFORGE_ROUTER_LLM_BACKEND=openai_compatible`` targeting
``OPENAI_API_BASE`` (e.g. Ollama ``http://localhost:11434/v1``).
"""
from __future__ import annotations

import os
from typing import Protocol

from anthropic import AsyncAnthropic


class RouterLLM(Protocol):
    backend_name: str

    async def complete(self, *, system: str, user: str, max_tokens: int, model: str) -> str: ...


def transport_is_mcp() -> bool:
    return os.getenv("SKILLFORGE_TRANSPORT", "").strip().lower() == "mcp"


class AnthropicRouterLLM:
    __slots__ = ("client", "backend_name")

    def __init__(self, client: AsyncAnthropic) -> None:
        self.client = client
        self.backend_name = "anthropic"

    async def complete(self, *, system: str, user: str, max_tokens: int, model: str) -> str:
        resp = await self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        block = resp.content[0]
        return block.text.strip()  # type: ignore[attr-defined]


class OpenAIRouterLLM:
    __slots__ = ("_client", "default_model", "backend_name")

    def __init__(self, *, api_key: str, base_url: str, default_model: str) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key or "ollama", base_url=base_url.rstrip("/"))
        self.default_model = default_model
        self.backend_name = "openai_compatible"

    async def complete(self, *, system: str, user: str, max_tokens: int, model: str) -> str:
        m = model or self.default_model
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
