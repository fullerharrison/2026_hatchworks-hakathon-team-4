"""Task 4: the question agent. The model is scripted; tools run on the real store."""

import json
import logging

import pytest
from fakes import REF_0037, FakeChat, call, run_ask, say

from uc4_mcp.agent import DISCLAIMER, SYSTEM_PROMPT, AgentSettings, load_agent_settings
from uc4_mcp.grounding import Citation
from uc4_mcp.llm import Completion, LLMError, ToolRequest, Usage
from uc4_mcp.models import to_json_safe
from uc4_mcp.store import EvidenceStore

GOOD = (f"SYN-TR-0037 is HOLD (amber): resistant lines 30% < 50%, "
        f"an inferred threshold [{REF_0037}].")
TOOLS = {"list_sources", "find_trial", "find_line", "get_trial", "get_line", "score_trial",
         "query_trials", "baseline_check"}


def test_answers_from_the_cited_tool_result(store: EvidenceStore) -> None:
    chat = FakeChat([call("score_trial", query="SYN-TR-0037"), say(GOOD)])
    a = run_ask(store, chat, "Why is SYN-TR-0037 amber?")
    assert a.status == "answered" and a.text == GOOD and a.ungrounded == ()
    assert a.citations == (Citation(REF_0037, True),)
    assert [(t.name, t.status) for t in a.tool_calls] == [("score_trial", "ok")]
    assert a.usage == Usage(20, 10) and a.model == "fake-model" and a.disclaimer == DISCLAIMER
    json.dumps(to_json_safe(a), allow_nan=False)


def test_model_sees_the_8_tools_and_each_tool_result(store: EvidenceStore) -> None:
    chat = FakeChat([call("score_trial", query="SYN-TR-0037"), say(GOOD)])
    run_ask(store, chat, "Why is SYN-TR-0037 amber?")
    assert {t["function"]["name"] for t in chat.tools[0]} == TOOLS
    first, second = chat.seen
    assert [m["role"] for m in first] == ["system", "user"]
    assert first[0]["content"] == SYSTEM_PROMPT
    assert second[-2]["tool_calls"][0]["function"]["name"] == "score_trial"
    assert second[-1]["role"] == "tool"
    assert json.loads(second[-1]["content"])["result"]["verdict"] == "HOLD"


@pytest.mark.parametrize("name,query", [("find_trial", "SYN-TR-003"),
                                        ("score_trial", "SYN-TR-003"),
                                        ("get_line", "SYN-MZ-0001")])
def test_ambiguous_id_ends_turn_with_candidates(store: EvidenceStore, name: str,
                                                query: str) -> None:
    chat = FakeChat([call(name, query=query), say("I picked the first one.")])
    a = run_ask(store, chat, f"Tell me about {query}")
    assert a.status == "clarify" and len(a.candidates) == 10
    assert "which one?" in a.text and a.candidates[0]["id"] in a.text
    assert len(chat.seen) == 1  # the model never got to pick


def test_too_many_matches_asks_to_refine(store: EvidenceStore) -> None:
    a = run_ask(store, FakeChat([call("find_line", query="1")]), "Tell me about line 1")
    assert a.status == "clarify" and len(a.candidates) == 20
    assert "70" in a.text and "refine" in a.text


def test_calculated_number_gets_one_repair(store: EvidenceStore) -> None:
    chat = FakeChat([call("score_trial", query="SYN-TR-0037"),
                     say(f"SYN-TR-0037 is 20 points short on resistant lines [{REF_0037}]."),
                     say(GOOD)])
    a = run_ask(store, chat, "Why is SYN-TR-0037 amber?")
    assert a.status == "answered" and a.text == GOOD
    repair = chat.seen[2][-1]
    assert repair["role"] == "user" and "20" in repair["content"]


def test_uncited_answer_is_repaired(store: EvidenceStore) -> None:
    chat = FakeChat([call("score_trial", query="SYN-TR-0037"),
                     say("SYN-TR-0037 is HOLD (amber)."), say(GOOD)])
    a = run_ask(store, chat, "Why is SYN-TR-0037 amber?")
    assert a.status == "answered" and "cites no tool result" in chat.seen[2][-1]["content"]


def test_unsupported_verdict_is_repaired_then_unverified(store: EvidenceStore) -> None:
    bad = f"SYN-TR-0037 is green [{REF_0037}]."
    chat = FakeChat([call("score_trial", query="SYN-TR-0037"), say(bad), say(bad)])
    a = run_ask(store, chat, "Is SYN-TR-0037 fine?")
    repair = chat.seen[2][-1]["content"]
    assert "verdict or colour words" in repair and "green" in repair
    assert a.status == "unverified" and a.problems == ("verdict green not in cited results",)


def test_an_exception_becomes_an_error_answer(store: EvidenceStore,
                                              caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="uc4_agent")
    a = run_ask(store, FakeChat([RuntimeError("boom")]), "Why?")
    assert a.status == "error" and "uc4_agent.log" in a.text
    lines = [r for r in caplog.records if r.name == "uc4_agent" and r.levelno == logging.INFO]
    assert len(lines) == 1 and json.loads(lines[0].getMessage())["status"] == "error"


def test_empty_model_reply_is_an_error(store: EvidenceStore) -> None:
    a = run_ask(store, FakeChat([say("")]), "Why?")
    assert a.status == "error" and "empty" in a.text


def test_still_ungrounded_after_repair_is_unverified(store: EvidenceStore) -> None:
    bad = f"SYN-TR-0037 is 20 points short [{REF_0037}]."
    chat = FakeChat([call("score_trial", query="SYN-TR-0037"), say(bad), say(bad)])
    a = run_ask(store, chat, "Why is SYN-TR-0037 amber?")
    assert a.status == "unverified" and a.ungrounded == ("20",) and a.text == bad


def test_unknown_citation_is_repaired(store: EvidenceStore) -> None:
    chat = FakeChat([call("score_trial", query="SYN-TR-0037"),
                     say("HOLD [trial_recommendations_synthetic.csv#NOPE]."), say(GOOD)])
    a = run_ask(store, chat, "Why is SYN-TR-0037 amber?")
    assert a.status == "answered" and "NOPE" in chat.seen[2][-1]["content"]


def test_gateway_error_is_an_error_answer(store: EvidenceStore) -> None:
    a = run_ask(store, FakeChat([LLMError("LLM gateway error: 401 bad key")]), "Why?")
    assert a.status == "error" and "401" in a.text and a.disclaimer == DISCLAIMER


def test_gateway_error_after_a_tool_keeps_the_trace(store: EvidenceStore) -> None:
    chat = FakeChat([call("score_trial", query="SYN-TR-0037"),
                     LLMError("LLM gateway error: timeout")])
    a = run_ask(store, chat, "Why is SYN-TR-0037 amber?")
    assert a.status == "error" and [t.name for t in a.tool_calls] == ["score_trial"]


def test_stops_after_max_rounds(store: EvidenceStore) -> None:
    chat = FakeChat([call("baseline_check") for _ in range(3)])
    a = run_ask(store, chat, "Check", settings=AgentSettings(max_rounds=3))
    assert a.status == "error" and "3 model rounds" in a.text and len(a.tool_calls) == 3


def test_follow_up_uses_history(store: EvidenceStore) -> None:
    history = [{"role": "user", "content": "Tell me about SYN-TR-003"},
               {"role": "assistant", "content": "10 trials match 'SYN-TR-003'; which one?"}]
    chat = FakeChat([call("score_trial", query="SYN-TR-0037"), say(GOOD)])
    a = run_ask(store, chat, "0037", history=history)
    assert a.status == "answered"
    assert [m["role"] for m in chat.seen[0]] == ["system", "user", "assistant", "user"]
    assert chat.seen[0][1:3] == history and chat.seen[0][3]["content"] == "0037"


def test_bad_tool_input_is_reported_to_the_model(store: EvidenceStore) -> None:
    chat = FakeChat([Completion(None, (ToolRequest("c1", "find_trial", None),)),
                     call("nope"), call("find_trial", query=5), say("I could not look that up.")])
    a = run_ask(store, chat, "Find trial five")
    assert [t.status for t in a.tool_calls] == ["error", "error", "error"]
    assert "not valid JSON" in json.loads(chat.seen[1][-1]["content"])["message"]
    assert a.status == "answered"


def test_out_of_scope_answer_needs_no_tools(store: EvidenceStore) -> None:
    text = "I can only answer questions about the UC4 trial data."
    a = run_ask(store, FakeChat([say(text)]), "What will the weather be tomorrow?")
    assert a.status == "answered" and a.tool_calls == ()


def test_empty_question_does_not_call_the_model(store: EvidenceStore) -> None:
    chat = FakeChat([])
    a = run_ask(store, chat, "   ")
    assert a.status == "error" and chat.seen == []


def test_system_prompt_states_the_rules() -> None:
    for phrase in ("[tool:", "[source_file#row_id]", "Verdicts are per trial",
                   "breeder", "inferred", "Lab results have no trial key",
                   "call the tools again", "Do not calculate"):
        assert phrase in SYSTEM_PROMPT, phrase


def test_committed_agent_settings() -> None:
    assert load_agent_settings() == AgentSettings(max_rounds=6, repair_rounds=1)


def test_each_ask_logs_one_json_line(store: EvidenceStore,
                                     caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="uc4_agent")
    run_ask(store, FakeChat([call("score_trial", query="SYN-TR-0037"), say(GOOD)]), "Why?")
    records = [r for r in caplog.records if r.name == "uc4_agent"]
    assert len(records) == 1
    entry = json.loads(records[0].getMessage())
    assert entry["status"] == "answered" and entry["model"] == "fake-model"
    assert entry["tools"] == [{"name": "score_trial", "arguments": {"query": "SYN-TR-0037"},
                               "status": "ok"}]
    assert (entry["prompt_tokens"], entry["completion_tokens"]) == (20, 10)
