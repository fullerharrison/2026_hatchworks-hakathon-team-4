"""The supported-question set and its checks (task.md Phase 2 exit criterion: ≥ 10
questions, each answer's numbers in the tool output it cites, "SYN-TR-003" → which one?).

``oracle`` in a case is not used for scoring: tests run it offline to prove the case's
expectations are true of the data.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from uc4_mcp.agent import AgentSettings, Answer, ask
from uc4_mcp.bridge import ToolBridge
from uc4_mcp.llm import ChatModel

EVALS_DIR = Path(__file__).resolve().parents[2] / "evals"
CASES_PATH = EVALS_DIR / "questions.json"
RESULTS_DIR = EVALS_DIR / "results"
EXPECT_KEYS = frozenset({"status", "tools_any", "calls", "no_tools", "include", "include_any",
                         "exclude", "cite_files", "cite_tools", "candidates", "oracle"})


@dataclass(frozen=True)
class Case:
    id: str
    question: str
    expect: dict[str, Any]
    history: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    question: str
    failures: tuple[str, ...]
    answer: Answer
    seconds: float

    @property
    def passed(self) -> bool:
        return not self.failures


def load_cases(path: Path = CASES_PATH) -> list[Case]:
    """Read the question set.

    Raises:
        ValueError: A case has an expectation key not in ``EXPECT_KEYS`` (a typo would
            otherwise silently check nothing).
    """
    cases = [Case(c["id"], c["question"], c["expect"], tuple(c.get("history", ())))
             for c in json.loads(path.read_text(encoding="utf-8"))]
    for case in cases:
        if unknown := sorted(set(case.expect) - EXPECT_KEYS):
            raise ValueError(f"{case.id}: unknown expect keys {unknown}")
    return cases


def _tool_checks(e: dict[str, Any], a: Answer) -> list[str]:
    called = [t.name for t in a.tool_calls]
    fails = []
    if e.get("tools_any") and not set(e["tools_any"]) & set(called):
        fails.append(f"none of {e['tools_any']} called (called {called})")
    for want in e.get("calls", ()):
        args = want.get("args", {})
        if not any(t.name == want["name"] and args.items() <= t.arguments.items()
                   for t in a.tool_calls):
            fails.append(f"no call {want['name']}({args})")
    if e.get("no_tools") and called:
        fails.append(f"tools called: {called}")
    return fails


def _text_checks(e: dict[str, Any], a: Answer) -> list[str]:
    text = a.text.lower()
    fails = [f"missing '{s}'" for s in e.get("include", ()) if s.lower() not in text]
    if e.get("include_any") and not any(s.lower() in text for s in e["include_any"]):
        fails.append(f"none of {e['include_any']} in the answer")
    fails += [f"contains '{s}'" for s in e.get("exclude", ()) if s.lower() in text]
    return fails


def _citation_checks(e: dict[str, Any], a: Answer) -> list[str]:
    refs = [c.ref for c in a.citations]
    fails = [f"no citation into {f}" for f in e.get("cite_files", ())
             if not any(r.startswith(f + "#") for r in refs)]
    fails += [f"no [tool:{t}] citation" for t in e.get("cite_tools", ())
              if f"tool:{t}" not in refs]
    if "candidates" in e and len(a.candidates) != e["candidates"]:
        fails.append(f"candidates {len(a.candidates)} != {e['candidates']}")
    return fails


def score(case: Case, answer: Answer) -> tuple[str, ...]:
    """Failures of ``answer`` against ``case.expect``; empty means the case passes.

    An "unverified" answer fails on status: its numbers were not all in the cited results.
    """
    e = case.expect
    want = e.get("status", "answered")
    fails = [] if answer.status == want else [f"status {answer.status} != {want}"]
    fails += _tool_checks(e, answer) + _text_checks(e, answer) + _citation_checks(e, answer)
    return tuple(fails)


async def run_cases(cases: Sequence[Case], model: ChatModel, bridge: ToolBridge,
                    settings: AgentSettings) -> list[CaseResult]:
    """Ask every case in order and score it."""
    results = []
    for case in cases:
        started = time.monotonic()
        answer = await ask(case.question, model=model, bridge=bridge,
                           history=case.history, settings=settings)
        results.append(CaseResult(case.id, case.question, score(case, answer), answer,
                                  round(time.monotonic() - started, 2)))
    return results


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def report(results: Sequence[CaseResult], model: str, day: date) -> str:
    """Markdown report: one row per case, then every answer in full."""
    tokens_in = sum(r.answer.usage.prompt_tokens for r in results)
    tokens_out = sum(r.answer.usage.completion_tokens for r in results)
    lines = [f"# Question-agent evaluation {day.isoformat()}", "",
             f"Model `{model}` · settings `app/agent.toml` · passed "
             f"{sum(r.passed for r in results)} of {len(results)} · tokens {tokens_in} in / "
             f"{tokens_out} out", "",
             "| Case | Question | Status | Tools | Result | Seconds | Tokens in/out |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in results:
        tools = ", ".join(t.name for t in r.answer.tool_calls) or "none"
        result = "pass" if r.passed else "FAIL: " + "; ".join(r.failures)
        u = r.answer.usage
        lines.append(f"| {r.case_id} | {_cell(r.question)} | {r.answer.status} | {tools} | "
                     f"{_cell(result)} | {r.seconds} | {u.prompt_tokens}/{u.completion_tokens} |")
    lines += ["", "## Answers", ""]
    for r in results:
        lines += [f"### {r.case_id}: {r.question}", "", r.answer.text, ""]
    return "\n".join(lines)


def result_stem(model: str, day: date) -> str:
    """File stem for a report, e.g. ``2026-09-30-gpt-4o``."""
    return f"{day.isoformat()}-{re.sub(r'[^A-Za-z0-9.]+', '-', model).strip('-')}"
