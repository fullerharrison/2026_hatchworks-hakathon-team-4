"""LLM access through the Portkey gateway (OpenAI-compatible chat completions).

The agent depends only on ``ChatModel``; ``PortkeyChat`` is the one real implementation
and tests use a scripted fake. Settings come from ``app/agent.toml`` (committed: model and
sampling) and environment variables (secrets, never committed).
"""

from __future__ import annotations

import json
import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx2  # openai 3.x builds on httpx2, not httpx
import openai

SETTINGS_PATH = Path(__file__).resolve().parents[2] / "agent.toml"
DEFAULT_BASE_URL = "https://api.portkey.ai/v1"
# Environment variable -> Portkey header. The API key is required; the rest pick the route.
PORTKEY_HEADERS = {"PORTKEY_API_KEY": "x-portkey-api-key",
                   "PORTKEY_VIRTUAL_KEY": "x-portkey-virtual-key",
                   "PORTKEY_CONFIG": "x-portkey-config",
                   "PORTKEY_PROVIDER": "x-portkey-provider"}
ECHO_TOOL: dict[str, Any] = {"type": "function", "function": {
    "name": "echo", "description": "Echo the text back.",
    "parameters": {"type": "object", "properties": {"text": {"type": "string"}},
                   "required": ["text"]}}}


class LLMError(Exception):
    """The model could not be configured or reached; the message is safe to show."""


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(self.prompt_tokens + other.prompt_tokens,
                     self.completion_tokens + other.completion_tokens)


@dataclass(frozen=True)
class ToolRequest:
    """One tool call the model asked for; ``arguments`` is None when its JSON was invalid."""

    id: str
    name: str
    arguments: dict[str, Any] | None


@dataclass(frozen=True)
class Completion:
    text: str | None
    tool_calls: tuple[ToolRequest, ...] = ()
    usage: Usage = Usage()


class ChatModel(Protocol):
    model: str

    async def complete(self, messages: list[dict[str, Any]],
                       tools: list[dict[str, Any]]) -> Completion: ...


@dataclass(frozen=True)
class LLMSettings:
    base_url: str
    model: str
    headers: Mapping[str, str]
    provider_key: str
    temperature: float | None = 0.0
    max_tokens: int | None = 800
    timeout_s: float = 60.0


def load_settings(path: Path = SETTINGS_PATH,
                  env: Mapping[str, str] = os.environ) -> LLMSettings:
    """Read ``[llm]`` from ``agent.toml`` and the Portkey environment variables.

    ``UC4_LLM_BASE_URL`` and ``UC4_LLM_MODEL`` override the file; a sampling key absent
    from the file is not sent (some models reject ``temperature`` or ``max_tokens``).

    Raises:
        LLMError: No model configured, or ``PORTKEY_API_KEY`` unset.
    """
    cfg = tomllib.loads(path.read_text(encoding="utf-8")).get("llm", {})
    model = env.get("UC4_LLM_MODEL") or cfg.get("model", "")
    if not model:
        raise LLMError(f"No model: set [llm] model in {path.name} or UC4_LLM_MODEL")
    if not env.get("PORTKEY_API_KEY"):
        raise LLMError("PORTKEY_API_KEY is not set; see app/README.md#question-agent")
    return LLMSettings(
        base_url=env.get("UC4_LLM_BASE_URL") or cfg.get("base_url", DEFAULT_BASE_URL),
        model=model,
        headers={h: env[v] for v, h in PORTKEY_HEADERS.items() if env.get(v)},
        provider_key=env.get("UC4_LLM_PROVIDER_KEY", "unused"),
        temperature=cfg.get("temperature"),
        max_tokens=cfg.get("max_tokens"),
        timeout_s=float(cfg.get("timeout_s", 60)),
    )


def _arguments(raw: str | None) -> dict[str, Any] | None:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


class PortkeyChat:
    """``ChatModel`` over Portkey's OpenAI-compatible ``/chat/completions``."""

    def __init__(self, settings: LLMSettings,
                 http_client: httpx2.AsyncClient | None = None) -> None:
        self.model = settings.model
        self._settings = settings
        # With a virtual key or config, Portkey supplies the provider key; api_key is a filler.
        self._client = openai.AsyncOpenAI(
            api_key=settings.provider_key, base_url=settings.base_url,
            default_headers=dict(settings.headers), timeout=settings.timeout_s,
            max_retries=1, http_client=http_client)

    async def complete(self, messages: list[dict[str, Any]],
                       tools: list[dict[str, Any]]) -> Completion:
        """One chat completion; tool calls and token usage are parsed into our types.

        Raises:
            LLMError: The gateway or provider returned an error or could not be reached.
        """
        s = self._settings
        extra: dict[str, Any] = {"tools": tools} if tools else {}
        if s.temperature is not None:
            extra["temperature"] = s.temperature
        if s.max_tokens is not None:
            extra["max_tokens"] = s.max_tokens
        try:
            r = await self._client.chat.completions.create(
                model=s.model, messages=messages, **extra)
        except openai.OpenAIError as e:
            raise LLMError(f"LLM gateway error: {e}") from e
        message = r.choices[0].message
        calls = tuple(ToolRequest(c.id, c.function.name, _arguments(c.function.arguments))
                      for c in message.tool_calls or ())
        usage = Usage(r.usage.prompt_tokens, r.usage.completion_tokens) if r.usage else Usage()
        return Completion(message.content, calls, usage)


async def ping(model: ChatModel) -> str:
    """One round trip that must come back as a tool call; returns a one-line report."""
    c = await model.complete(
        [{"role": "user", "content": "Call the echo tool with the text 'ok'."}], [ECHO_TOOL])
    called = any(t.name == "echo" for t in c.tool_calls)
    return (f"model={model.model} tool_call={'yes' if called else 'NO'} "
            f"tokens={c.usage.prompt_tokens}/{c.usage.completion_tokens}")
