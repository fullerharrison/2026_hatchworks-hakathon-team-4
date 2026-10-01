"""Step 7: the MCP surface, called in-process through the mcp 2.x client."""

import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar

import anyio
import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer
from starlette.testclient import TestClient

from uc4_mcp.checks import FLAG_CODES
from uc4_mcp.models import to_json_safe
from uc4_mcp.server import configure_logging, create_server
from uc4_mcp.store import QUERY_FLAGS, EvidenceStore

T = TypeVar("T")
TOOLS = {"list_sources", "find_trial", "find_line", "get_trial", "get_line", "score_trial",
         "query_trials", "baseline_check"}
RESOURCES = {"uc4://sources", "uc4://rule/SYNTH_V1"}


@pytest.fixture(scope="module")
def server(store: EvidenceStore) -> MCPServer:
    return create_server(lambda: store)


def run(server: MCPServer, fn: Callable[[Client], Awaitable[T]]) -> T:
    async def main() -> T:
        async with Client(server) as client:
            return await fn(client)
    return anyio.run(main)


def call(server: MCPServer, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call one tool; returns its structured result (the envelope)."""
    async def fn(client: Client) -> dict[str, Any]:
        result = await client.call_tool(name, args or {})
        assert not result.is_error, result.content
        assert result.structured_content is not None
        return result.structured_content
    return run(server, fn)


def check_envelope(env: dict[str, Any]) -> None:
    assert env["status"] in ("ok", "many", "none") and isinstance(env["message"], str)
    assert ("result" in env) == (env["status"] == "ok")
    assert ("candidates" in env) == (env["status"] == "many")


# --- listing ------------------------------------------------------------------------


def test_lists_the_8_tools_read_only(server: MCPServer) -> None:
    tools = run(server, lambda c: c.list_tools()).tools
    assert {t.name for t in tools} == TOOLS  # no ping
    for t in tools:
        assert t.annotations is not None
        assert t.annotations.read_only_hint and t.annotations.idempotent_hint


def test_lists_the_2_json_resources(server: MCPServer) -> None:
    resources = run(server, lambda c: c.list_resources()).resources
    assert {str(r.uri) for r in resources} == RESOURCES
    assert all(r.mime_type == "application/json" for r in resources)


def test_filters_are_plain_strings(server: MCPServer) -> None:
    (tool,) = [t for t in run(server, lambda c: c.list_tools()).tools if t.name == "query_trials"]
    props = tool.input_schema["properties"]
    for name in ("verdict", "knockout", "missed", "flag"):
        assert "enum" not in json.dumps(props[name])
    assert props["only"]["type"] == "boolean"


# --- descriptions (the Phase 2 agent's instructions) ---------------------------------------


def descriptions(server: MCPServer) -> dict[str, str]:
    return {t.name: t.description or "" for t in run(server, lambda c: c.list_tools()).tools}


def test_descriptions_state_grain_inference_and_an_example(server: MCPServer) -> None:
    d = descriptions(server)
    assert all("Example:" in text for text in d.values())
    for name in ("get_trial", "score_trial", "query_trials", "find_trial", "baseline_check"):
        assert "per trial" in d[name], name
    assert "verdicts are per trial" in d["get_line"]
    for name in ("score_trial", "query_trials", "get_trial"):
        assert "SYNTH_V1 (inferred)" in d[name], name
    assert "t/ha" in d["get_trial"]


def test_query_trials_description_lists_the_flag_codes(server: MCPServer) -> None:
    text = descriptions(server)["query_trials"]
    assert len(QUERY_FLAGS) == 7
    assert all(code in text for code in QUERY_FLAGS)
    assert "LAB_NOT_TRIAL_LINKED is a line flag" in text


# --- acceptance inputs from the tool table ------------------------------------------------


def test_list_sources(server: MCPServer, store: EvidenceStore) -> None:
    env = call(server, "list_sources")
    check_envelope(env)
    assert env == to_json_safe(store.list_sources())
    assert len(env["result"]["files"]) == 7


@pytest.mark.parametrize("tool, query, status, n", [
    ("find_trial", "0037", "ok", None), ("find_trial", "SYN-TR-003", "many", 10),
    ("find_trial", "XYZ", "none", None), ("find_line", "SYN-MZ-00001", "ok", None),
    ("find_line", "SYN-MZ-0001", "many", 10), ("find_line", "003", "many", 11)])
def test_find(server: MCPServer, tool: str, query: str, status: str, n: int | None) -> None:
    env = call(server, tool, {"query": query})
    check_envelope(env)
    assert env["status"] == status
    if n is not None:
        assert len(env["candidates"]) == n
    if query == "0037":
        assert env["result"]["id"] == "SYN-TR-0037"


def test_get_trial(server: MCPServer) -> None:
    env = call(server, "get_trial", {"query": "SYN-TR-0037"})
    check_envelope(env)
    view = env["result"]
    assert len(view["lines"]) == 10 and len(view["operations"]) == 3
    assert view["recommendation"]["verdict"] == "HOLD"


def test_get_line(server: MCPServer) -> None:
    env = call(server, "get_line", {"query": "SYN-MZ-00001"})
    check_envelope(env)
    view = env["result"]
    assert len(view["trials"]) in (4, 5) and len(view["lab"]) in (2, 3)
    assert "LAB_NOT_TRIAL_LINKED" in {f["code"] for f in view["flags"]}


def test_score_trial_worked_examples(server: MCPServer) -> None:
    passed = call(server, "score_trial", {"query": "SYN-TR-0003"})["result"]
    assert passed["verdict"] == "PASS"
    assert all(c["passed"] for c in passed["criteria"] if c["kind"] == "pass")
    hold = call(server, "score_trial", {"query": "SYN-TR-0037"})["result"]
    unmet = [c["field"] for c in hold["criteria"] if c["kind"] == "pass" and not c["passed"]]
    assert hold["verdict"] == "HOLD" and unmet == ["RESISTANT_MATERIAL_PCT"]
    assert hold["rationale_omits"] == ["RESISTANT_MATERIAL_PCT"]
    fail = call(server, "score_trial", {"query": "SYN-TR-0001"})["result"]
    assert fail["verdict"] == "FAIL" and fail["knockout"] == ["DISEASE_SCORE"]
    assert all(c["bracket"] and c["threshold"] is not None for c in fail["criteria"])
    assert fail["evidence_row_ids"]


def test_query_trials(server: MCPServer) -> None:
    env = call(server, "query_trials", {"flag": "COMPLETE_TRIAL_HAS_PLANNED_OPS"})
    check_envelope(env)
    assert len(env["result"]) == 60
    assert len(call(server, "query_trials", {"knockout": "disease", "only": True})["result"]) == 16


def test_unknown_flag_is_an_envelope_not_an_error(server: MCPServer) -> None:
    env = call(server, "query_trials", {"flag": "NOT_A_CODE"})  # call() asserts not is_error
    check_envelope(env)
    assert env["status"] == "none" and "OP_LINE_NOT_IN_TRIAL" in env["message"]


def test_baseline_check(server: MCPServer) -> None:
    env = call(server, "baseline_check")
    check_envelope(env)
    assert env["result"] == {"checked": 72, "matched": 72, "mismatches": []}


# --- resources --------------------------------------------------------------------------


def read(server: MCPServer, uri: str) -> Any:
    async def fn(client: Client) -> Any:
        (content,) = (await client.read_resource(uri)).contents
        assert content.mime_type == "application/json"
        return json.loads(content.text)  # type: ignore[union-attr]
    return run(server, fn)


def test_sources_resource_is_the_list_sources_result(server: MCPServer,
                                                     store: EvidenceStore) -> None:
    assert read(server, "uc4://sources") == to_json_safe(store.list_sources()["result"])


def test_rule_resource(server: MCPServer, store: EvidenceStore) -> None:
    rule = read(server, "uc4://rule/SYNTH_V1")
    assert rule == to_json_safe(store.rule())
    assert [f["code"] for f in rule["flags"]] == list(FLAG_CODES)
    assert rule["extract_date"] == "2026-09-26 12:00"


# --- stdout and logging -------------------------------------------------------------------


def test_nothing_on_stdout(server: MCPServer, capsys: pytest.CaptureFixture[str]) -> None:
    call(server, "baseline_check")
    call(server, "get_trial", {"query": "0037"})
    assert capsys.readouterr().out == ""


def test_one_log_line_per_call(server: MCPServer, tmp_path: Path) -> None:
    log = tmp_path / "logs" / "uc4_mcp.log"
    handler = configure_logging(log)
    try:
        call(server, "find_trial", {"query": "0037"})
        call(server, "query_trials", {"flag": "NOT_A_CODE"})
    finally:
        logging.getLogger("uc4_mcp").removeHandler(handler)
        handler.close()
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert "find_trial" in lines[0] and "ok" in lines[0]
    assert "query_trials" in lines[1] and "none" in lines[1]


# --- the HTTP transport's /health probe ------------------------------------------------


def test_health_route_reports_the_loaded_store(server: MCPServer,
                                               store: EvidenceStore) -> None:
    """``GET /health``: the JSON a probe sees without an MCP client; ``/`` stays 404."""
    client = TestClient(server.streamable_http_app())
    assert client.get("/").status_code == 404
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "server": "uc4-mcp",
                        "trials": len(store.trial_guids),
                        "sources": len(store.list_sources()["result"]["files"]),
                        "extract_date": "2026-09-26 12:00"}


def test_health_route_reports_a_store_failure() -> None:
    """A store that cannot load fails the probe (500) instead of the server."""
    def fail() -> EvidenceStore:
        raise RuntimeError("zip missing")
    r = TestClient(create_server(fail).streamable_http_app()).get("/health")
    assert r.status_code == 500
    assert r.json() == {"status": "error", "error": "zip missing"}
