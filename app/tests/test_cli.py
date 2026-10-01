"""Task 5: uc4-ask ask / chat, with a scripted model over the session store."""

import builtins
import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

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
    monkeypatch.setattr(cli, "ensure_env", lambda: [])  # no dependency on a real .env
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
    problems = ("number 20 not in cited results", "no citation")
    out = cli.render(Answer("unverified", "20 points short.", "m", ungrounded=("20",),
                            problems=problems))
    assert "Warning: number 20 not in cited results; no citation" in out


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


def test_serve_preloads_the_store_and_names_the_screen(
        use: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
        capsys: pytest.CaptureFixture[str]) -> None:
    log = tmp_path / "decisions.jsonl"
    monkeypatch.setenv("UC4_DECISION_LOG", str(log))
    loaded: list[bool] = []
    monkeypatch.setattr(cli, "_default_store", lambda: loaded.append(True))
    started: dict[str, Any] = {}

    def fake_run(app: Any, **kwargs: Any) -> None:
        started.update(app=app, loaded=list(loaded), **kwargs)
    monkeypatch.setattr(cli.uvicorn, "run", fake_run)
    assert run(["serve", "--port", "9123"]) == 0
    out = capsys.readouterr().out
    assert f"Breeder screen: http://127.0.0.1:9123/  (decisions: {log})" in out
    assert started["loaded"] == [True] and started["port"] == 9123
    assert "/decisions" in {getattr(r, "path", None) for r in started["app"].routes}


def test_serve_exits_1_when_the_zip_is_missing(
        use: None, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    def missing() -> None:
        raise FileNotFoundError("no archive; set UC4_ZIP")
    monkeypatch.setattr(cli, "_default_store", missing)
    monkeypatch.setattr(cli.uvicorn, "run", lambda *a, **k: pytest.fail("server started"))
    assert run(["serve"]) == 1
    assert "set UC4_ZIP" in capsys.readouterr().err


def test_quiet_sdk_logging() -> None:
    names = ("mcp", "openai", "httpx2", "httpx")
    before = {n: logging.getLogger(n).level for n in names}
    try:
        for n in names:
            logging.getLogger(n).setLevel(logging.INFO)
        cli.quiet_sdk_logging()
        assert all(logging.getLogger(n).level == logging.WARNING for n in names)
        assert logging.getLogger("mcp.server.mcpserver").getEffectiveLevel() >= logging.WARNING
    finally:
        for n, level in before.items():
            logging.getLogger(n).setLevel(level)


def test_ctrl_c_exits_130_quietly(use: None, monkeypatch: pytest.MonkeyPatch) -> None:
    def interrupt(args: object) -> int:
        raise KeyboardInterrupt
    monkeypatch.setattr(cli, "cmd_ping", interrupt)
    assert run(["ping"]) == 130


def test_eval_writes_md_and_json_reports(use: None, monkeypatch: pytest.MonkeyPatch,
                                         tmp_path: Path) -> None:
    all_cases = json.loads(cli.CASES_PATH.read_text(encoding="utf-8"))
    keep = {"q01-hold-explained", "q04-ambiguous-trial"}
    cases = tmp_path / "questions.json"
    cases.write_text(json.dumps([c for c in all_cases if c["id"] in keep]), encoding="utf-8")
    chat = FakeChat([call("score_trial", query="SYN-TR-0037"), say(GOOD),
                     call("find_trial", query="SYN-TR-003")])
    monkeypatch.setattr(cli, "make_model", lambda: chat)
    out = tmp_path / "out"
    assert run(["eval", "--cases", str(cases), "--out", str(out)]) == 0
    md, js = list(out.glob("*.md")), list(out.glob("*.json"))
    assert len(md) == 1 and len(js) == 1
    assert len(json.loads(js[0].read_text(encoding="utf-8"))) == 2
    assert "passed 2 of 2" in md[0].read_text(encoding="utf-8")
