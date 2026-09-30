"""Task 7: the supported-question set is well formed, true of the data, and scored right."""

import json
from datetime import date
from pathlib import Path

import anyio
import pytest
from fakes import REF_0037, FakeChat, call, say

from uc4_mcp.agent import AgentSettings, Answer
from uc4_mcp.bridge import ToolTrace, open_bridge
from uc4_mcp.evals import Case, CaseResult, load_cases, report, run_cases, score
from uc4_mcp.grounding import NUMBER, Citation, numbers_in
from uc4_mcp.server import create_server
from uc4_mcp.store import EvidenceStore

CASES = load_cases()


def test_question_set_is_well_formed() -> None:
    assert len(CASES) >= 10 and len({c.id for c in CASES}) == len(CASES)
    clarify = [c for c in CASES if c.expect.get("status") == "clarify"]
    assert any("SYN-TR-003" in c.question and c.expect["candidates"] == 10 for c in clarify)


def test_unknown_expect_key_raises(tmp_path: Path) -> None:
    path = tmp_path / "q.json"
    path.write_text(json.dumps([{"id": "x", "question": "q", "expect": {"inclde": []}}]))
    with pytest.raises(ValueError, match="inclde"):
        load_cases(path)


@pytest.mark.parametrize("case", [c for c in CASES if "oracle" in c.expect], ids=lambda c: c.id)
def test_expectations_are_true_of_the_data(store: EvidenceStore, case: Case) -> None:
    oracle = case.expect["oracle"]

    async def main() -> ToolTrace:
        async with open_bridge(create_server(lambda: store)) as bridge:
            return await bridge.call(oracle["name"], oracle["args"])
    t = anyio.run(main)
    if case.expect.get("status") == "clarify":
        assert t.status == "many" and len(t.result["candidates"]) == case.expect["candidates"]
        return
    assert t.status == "ok"
    text = json.dumps(t.result)
    for s in case.expect.get("include", ()):
        if NUMBER.fullmatch(s):
            assert float(s) in numbers_in(t.result), s
        else:
            assert s.lower() in text.lower(), s


def answer(**kw: object) -> Answer:
    base: dict = {"status": "answered", "text": "", "model": "m"}
    return Answer(**{**base, **kw})


def test_score_passes_a_good_answer() -> None:
    case = next(c for c in CASES if c.id == "q01-hold-explained")
    a = answer(text=f"SYN-TR-0037 is HOLD: 30% < 50% [{REF_0037}].",
               citations=(Citation(REF_0037, True),),
               tool_calls=(ToolTrace("score_trial", {"query": "SYN-TR-0037"}, "ok", {}),))
    assert score(case, a) == ()


def test_score_names_each_failure() -> None:
    case = Case("x", "q", {"tools_any": ["get_trial"], "calls": [{"name": "query_trials",
                "args": {"only": True}}], "include": ["16"], "include_any": ["breeder"],
                "exclude": ["advance"], "cite_files": ["a.csv"], "cite_tools": ["query_trials"],
                "candidates": 10})
    a = answer(status="unverified", text="You should advance.",
               tool_calls=(ToolTrace("query_trials", {"only": False}, "ok", {}),))
    failures = " | ".join(score(case, a))
    for part in ("status unverified", "none of ['get_trial']", "no call", "missing '16'",
                 "none of ['breeder']", "contains 'advance'", "a.csv", "[tool:query_trials]",
                 "candidates 0 != 10"):
        assert part in failures, part
    assert score(Case("y", "q", {"no_tools": True}), a) == (
        "status unverified != answered", "tools called: ['query_trials']")


def test_run_cases_and_report(store: EvidenceStore) -> None:
    cases = [c for c in CASES if c.id in ("q01-hold-explained", "q04-ambiguous-trial")]
    chat = FakeChat([call("score_trial", query="SYN-TR-0037"),
                     say(f"SYN-TR-0037 is HOLD: 30% < 50% [{REF_0037}]."),
                     call("find_trial", query="SYN-TR-003")])

    async def main() -> list[CaseResult]:
        async with open_bridge(create_server(lambda: store)) as bridge:
            return await run_cases(cases, chat, bridge, AgentSettings())
    results = anyio.run(main)
    assert [r.passed for r in results] == [True, True]
    md = report(results, "fake-model", date(2026, 9, 30))
    assert "passed 2 of 2" in md and "| q04-ambiguous-trial |" in md and "`fake-model`" in md
