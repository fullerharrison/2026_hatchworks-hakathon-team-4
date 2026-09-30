"""Task 2: the agent's view of the 8 MCP tools, in-process."""

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import anyio
import pytest

from uc4_mcp.bridge import ToolBridge, open_bridge
from uc4_mcp.models import to_json_safe
from uc4_mcp.server import SCORE_TRIAL, create_server
from uc4_mcp.store import EvidenceStore

T = TypeVar("T")
TOOLS = {"list_sources", "find_trial", "find_line", "get_trial", "get_line", "score_trial",
         "query_trials", "baseline_check"}


def with_bridge(store: EvidenceStore, fn: Callable[[ToolBridge], Awaitable[T]]) -> T:
    async def main() -> T:
        async with open_bridge(create_server(lambda: store)) as bridge:
            return await fn(bridge)
    return anyio.run(main)


def test_schemas_are_the_8_tools_with_their_descriptions(store: EvidenceStore) -> None:
    schemas = with_bridge(store, lambda b: b.function_schemas())
    assert all(s["type"] == "function" for s in schemas)
    by_name = {s["function"]["name"]: s["function"] for s in schemas}
    assert set(by_name) == TOOLS
    assert by_name["score_trial"]["description"] == SCORE_TRIAL
    params = by_name["query_trials"]["parameters"]
    assert params["type"] == "object" and "flag" in params["properties"]


def test_call_returns_the_envelope(store: EvidenceStore) -> None:
    t = with_bridge(store, lambda b: b.call("score_trial", {"query": "SYN-TR-0037"}))
    assert (t.name, t.arguments, t.status) == ("score_trial", {"query": "SYN-TR-0037"}, "ok")
    assert t.result == to_json_safe(store.score_trial("SYN-TR-0037"))


@pytest.mark.parametrize("query,status", [("SYN-TR-003", "many"), ("XYZ", "none")])
def test_many_and_none_pass_through(store: EvidenceStore, query: str, status: str) -> None:
    t = with_bridge(store, lambda b: b.call("find_trial", {"query": query}))
    assert t.status == status and t.result["status"] == status


@pytest.mark.parametrize("name,arguments,text", [
    ("find_trial", None, "not valid JSON"),
    ("nope", {}, "Unknown tool"),
    ("find_trial", {"query": 5}, "valid string"),
    ("find_trial", {}, "Field required"),
])
def test_bad_calls_become_error_traces(store: EvidenceStore, name: str,
                                       arguments: dict[str, Any] | None, text: str) -> None:
    t = with_bridge(store, lambda b: b.call(name, arguments))
    assert t.status == "error" and t.result["status"] == "error"
    assert text in t.result["message"]
