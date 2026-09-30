"""Task 1: settings, the Portkey chat adapter (offline, via httpx2 MockTransport) and ping."""

import json
import tomllib
from pathlib import Path
from typing import Any

import anyio
import httpx2
import pytest

from uc4_mcp.llm import (DEFAULT_BASE_URL, ECHO_TOOL, SETTINGS_PATH, LLMError, LLMSettings,
                         PortkeyChat, ToolRequest, Usage, load_settings, ping)

ENV = {"PORTKEY_API_KEY": "pk", "PORTKEY_VIRTUAL_KEY": "vk"}


def toml(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "agent.toml"
    path.write_text(body, encoding="utf-8")
    return path


def test_load_settings_reads_file_and_env(tmp_path: Path) -> None:
    path = toml(tmp_path, '[llm]\nmodel = "gpt-x"\ntemperature = 0\nmax_tokens = 500\n')
    s = load_settings(path, ENV)
    assert s.model == "gpt-x" and s.base_url == DEFAULT_BASE_URL
    assert dict(s.headers) == {"x-portkey-api-key": "pk", "x-portkey-virtual-key": "vk"}
    assert s.temperature == 0 and s.max_tokens == 500 and s.provider_key == "pk"


def test_env_overrides_model_and_url(tmp_path: Path) -> None:
    path = toml(tmp_path, '[llm]\nmodel = "gpt-x"\n')
    s = load_settings(path, {**ENV, "UC4_LLM_MODEL": "other", "UC4_LLM_BASE_URL": "http://gw/v1"})
    assert s.model == "other" and s.base_url == "http://gw/v1"
    assert s.temperature is None and s.max_tokens is None  # absent keys are not sent


@pytest.mark.parametrize("body,env,match", [
    ('[llm]\nmodel = ""\n', ENV, "No model"),
    ('[llm]\nmodel = "gpt-x"\n', {"PORTKEY_VIRTUAL_KEY": "vk"}, "PORTKEY_API_KEY"),
])
def test_missing_model_or_key_raises(tmp_path: Path, body: str, env: dict[str, str],
                                     match: str) -> None:
    with pytest.raises(LLMError, match=match):
        load_settings(toml(tmp_path, body), env)


def test_committed_settings_parse() -> None:
    cfg = tomllib.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    assert cfg["llm"]["base_url"].startswith("https://")
    assert cfg["agent"] == {"max_rounds": 6, "repair_rounds": 1}


def response(message: dict[str, Any]) -> dict[str, Any]:
    return {"id": "r1", "object": "chat.completion", "created": 0, "model": "gpt-x",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", **message}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15}}


def chat_with(handler: Any, **overrides: Any) -> PortkeyChat:
    settings = LLMSettings(base_url="http://gw.test/v1", model="gpt-x",
                           headers={"x-portkey-api-key": "pk"}, provider_key="unused",
                           **overrides)
    return PortkeyChat(settings, http_client=httpx2.AsyncClient(
        transport=httpx2.MockTransport(handler)))


def test_empty_choices_is_an_llm_error() -> None:
    body = {**response({"content": "x"}), "choices": []}
    chat = chat_with(lambda request: httpx2.Response(200, json=body))
    with pytest.raises(LLMError, match="no choices"):
        anyio.run(chat.complete, [{"role": "user", "content": "hi"}], [])


def tool_call_message(arguments: str) -> dict[str, Any]:
    return {"content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {
        "name": "echo", "arguments": arguments}}]}


def test_sends_model_headers_and_tools_and_parses_tool_calls() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.update(url=str(request.url), key=request.headers["x-portkey-api-key"],
                    body=json.loads(request.content))
        return httpx2.Response(200, json=response(tool_call_message('{"text": "ok"}')))

    c = anyio.run(chat_with(handler).complete, [{"role": "user", "content": "hi"}], [ECHO_TOOL])
    assert seen["url"] == "http://gw.test/v1/chat/completions" and seen["key"] == "pk"
    assert seen["body"]["model"] == "gpt-x" and seen["body"]["tools"] == [ECHO_TOOL]
    assert seen["body"]["temperature"] == 0.0 and seen["body"]["max_tokens"] == 800
    assert c.tool_calls == (ToolRequest("c1", "echo", {"text": "ok"}),)
    assert c.text is None and c.usage == Usage(12, 3)


def test_invalid_tool_arguments_become_none() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=response(tool_call_message("{not json")))

    c = anyio.run(chat_with(handler).complete, [{"role": "user", "content": "hi"}], [ECHO_TOOL])
    assert c.tool_calls == (ToolRequest("c1", "echo", None),)


def test_omits_tools_and_unset_sampling() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.update(json.loads(request.content))
        return httpx2.Response(200, json=response({"content": "hello"}))

    chat = chat_with(handler, temperature=None, max_tokens=None)
    c = anyio.run(chat.complete, [{"role": "user", "content": "hi"}], [])
    assert c.text == "hello" and c.tool_calls == ()
    assert not {"tools", "temperature", "max_tokens"} & set(seen)


def test_gateway_error_becomes_llm_error() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(401, json={"error": {"message": "bad key"}})

    with pytest.raises(LLMError, match="LLM gateway error"):
        anyio.run(chat_with(handler).complete, [{"role": "user", "content": "hi"}], [])


def test_provider_key_overrides_the_portkey_key(tmp_path: Path) -> None:
    path = toml(tmp_path, '[llm]\nmodel = "@openai-prod/gpt-x"\n')
    s = load_settings(path, {**ENV, "UC4_LLM_PROVIDER_KEY": "sk-raw"})
    assert s.provider_key == "sk-raw" and s.model == "@openai-prod/gpt-x"


def test_portkey_key_is_sent_as_bearer() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["auth"] = request.headers["authorization"]
        return httpx2.Response(200, json=response({"content": "hi"}))

    settings = LLMSettings(base_url="http://gw.test/v1", model="gpt-x",
                           headers={"x-portkey-api-key": "pk"}, provider_key="pk")
    chat = PortkeyChat(settings, http_client=httpx2.AsyncClient(
        transport=httpx2.MockTransport(handler)))
    anyio.run(chat.complete, [{"role": "user", "content": "hi"}], [])
    assert seen["auth"] == "Bearer pk"


def test_ping_reports_the_tool_call() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=response(tool_call_message('{"text": "ok"}')))

    assert anyio.run(ping, chat_with(handler)) == "model=gpt-x tool_call=yes tokens=12/3"
