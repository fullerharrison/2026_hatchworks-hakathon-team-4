"""Task 5: uc4-ask ask / chat, with a scripted model over the session store."""

import builtins
import json
import logging
from collections.abc import Iterator

import pytest
from fakes import REF_0037, FakeChat, call, say

from uc4_mcp import cli
from uc4_mcp.agent import DISCLAIMER, Answer
from uc4_mcp.grounding import Citation
from uc4_mcp.llm import LLMError
from uc4_mcp.server import create_server
from uc4_mcp.store import EvidenceStore

GOOD = f"SYN-TR-0037 is HOLD: resistant lines 30% < 50% (inferred) [{REF_0037}]."


@pytest.fixture
def use(store: EvidenceStore, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(cli, "server", create_server(lambda: store))
    monkeypatch.setattr(cli, "configure_cli_logging", lambda: None)  # keep app/logs clean
    yield


def run(argv: list[str]) -> int:
    with pytest.raises(SystemExit) as exc:
        cli.main(argv)
    return int(exc.value.code)


def test_render_numbers_citations_and_lists_sources() -> None:
    a = Answer("answered", f"HOLD [{REF_0037}]. 16 trials [tool:query_trials].", "m",
               citations=(Citation(REF_0037, True), Citation("tool:query_trials", True)))
    out = cli.render(a)
    assert out.startswith("HOLD [1]. 16 trials [2].")
    assert f"[1] {REF_0037}" in out and "[2] tool:query_trials" in out
    assert out.rstrip().endswith(DISCLAIMER)


def test_render_warns_when_unverified() -> None:
    out = cli.render(Answer("unverified", "20 points short.", "m", ungrounded=("20",)))
    assert "Warning" in out and "20" in out


def test_ask_prints_the_rendered_answer(use: None, monkeypatch: pytest.MonkeyPatch,
                                        capsys: pytest.CaptureFixture[str]) -> None:
    chat = FakeChat([call("score_trial", query="SYN-TR-0037"), say(GOOD)])
    monkeypatch.setattr(cli, "make_model", lambda: chat)
    assert run(["ask", "Why is SYN-TR-0037 amber?"]) == 0
    out = capsys.readouterr().out
    assert "HOLD" in out and "[1]" in out and "Sources:" in out


def test_ask_json(use: None, monkeypatch: pytest.MonkeyPatch,
                  capsys: pytest.CaptureFixture[str]) -> None:
    chat = FakeChat([call("find_trial", query="SYN-TR-003")])
    monkeypatch.setattr(cli, "make_model", lambda: chat)
    assert run(["ask", "--json", "Tell me about SYN-TR-003"]) == 0
    body = json.loads(capsys.readouterr().out)
    assert body["status"] == "clarify" and len(body["candidates"]) == 10


def test_missing_configuration_exits_2(use: None, monkeypatch: pytest.MonkeyPatch,
                                       capsys: pytest.CaptureFixture[str]) -> None:
    def fail() -> None:
        raise LLMError("PORTKEY_API_KEY is not set")
    monkeypatch.setattr(cli, "make_model", fail)
    assert run(["ask", "Why?"]) == 2
    assert "PORTKEY_API_KEY" in capsys.readouterr().err


def test_chat_keeps_history(use: None, monkeypatch: pytest.MonkeyPatch,
                            capsys: pytest.CaptureFixture[str]) -> None:
    chat = FakeChat([call("find_trial", query="SYN-TR-003"),
                     call("score_trial", query="SYN-TR-0037"), say(GOOD)])
    monkeypatch.setattr(cli, "make_model", lambda: chat)
    lines = iter(["Tell me about SYN-TR-003", "0037"])

    def fake_input(prompt: str = "") -> str:
        try:
            return next(lines)
        except StopIteration:
            raise EOFError from None
    monkeypatch.setattr(builtins, "input", fake_input)
    assert run(["chat"]) == 0
    second_question = chat.seen[1]
    assert [m["role"] for m in second_question[1:]] == ["user", "assistant", "user"]
    assert "which one?" in second_question[2]["content"]
    assert "HOLD" in capsys.readouterr().out


def test_quiet_sdk_logging() -> None:
    cli.quiet_sdk_logging()
    assert logging.getLogger("mcp.server.mcpserver").getEffectiveLevel() >= logging.WARNING
