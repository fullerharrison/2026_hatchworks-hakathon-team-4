"""The question agent: the model picks uc4 tools; code checks its answer against them.

Code, not the model, decides three things: an ambiguous ID ends the turn with a "which
one?" built from the tool's candidates; an answer whose numbers or citations are not in the
cited tool results gets ``repair_rounds`` rewrites and is otherwise returned "unverified";
every answer carries the fixed disclaimer that the breeder makes the final call.
"""

from __future__ import annotations

import json
import logging
import time
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from uc4_mcp.bridge import ToolBridge, ToolTrace
from uc4_mcp.grounding import Citation, Grounding, check
from uc4_mcp.llm import SETTINGS_PATH, ChatModel, Completion, LLMError, Usage

logger = logging.getLogger("uc4_agent")
AGENT_LOG = Path(__file__).resolve().parents[2] / "logs" / "uc4_agent.log"
RESOLVING_TOOLS = frozenset({"find_candidate", "get_candidate", "score_candidate",
                             "find_trial", "find_line", "get_trial", "get_line", "score_trial"})
DISCLAIMER = ("Recommendation only: scoring uses provisional inferred thresholds. "
              "The breeder makes the final call.")
CANDIDATE_SYSTEM_PROMPT = """\
You are the UC4 breeder assistant. Answer questions about synthetic maize-like breeding \
candidates (IDs like SYN-MZ-00001) using only the current candidate tools.

Rules:
1. Every number you state must appear in a tool result from this question. Do not \
calculate, estimate, average or subtract. If no tool gives a number, say it is not in \
the data.
2. Cite every fact right after the sentence that uses it, in square brackets: a row as \
[source_file#row_id], exactly as in the tool result, or a whole result as \
[tool:<tool name>] for derived facts, lists, revisions and aggregate values.
3. System recommendations are GREEN, AMBER or RED per candidate. Breeder decisions \
are ADVANCE, HOLD or DISCARD. Never call a trial verdict a candidate recommendation. \
Thresholds are provisional inferences, not confirmed by Syngenta.
4. Explain excluded missed-irrigation trials and check comparisons from current evidence. \
Yield comparison is a ratio of equally weighted trial means, not a mean of ratios.
5. Lab results have no trial key. Never attach a lab result to a trial.
6. A missing value never meets a criterion; say it is missing.
7. If a tool returns status "none", say what was not found and what input works. If an \
ID matches several records, the app asks the user which one; do not pick.
8. You recommend; the breeder decides. If asked whether to advance, select or drop \
material, give the evidence and say the decision is the breeder's.
9. Only answer questions about this data. Otherwise say you can only answer questions \
about the UC4 candidate data.
10. Tool results from earlier questions are not kept: call the tools again for any value \
you need, even if it was discussed before.
11. Keep explanations concise. When a whole list is requested, include every matching \
candidate and follow next_offset until complete. If incomplete, explicitly say so. \
Name candidates by ID. Filters change the list, not the recommendation.
12. Distinguish supplied source RAG from calculated RAG and preserve revision context.
13. For an unknown ID cite [tool:find_candidate] for the absence result.
14. A citation must support the particular fact. Cite [tool:get_candidate] or \
[tool:score_candidate] for reconstructed values and comparison flags; raw CSV rows \
support only their own values. The dataset is synthetic maize-like demo data.
"""

SYSTEM_PROMPT = """\
You are the UC4 breeder assistant. You answer questions about synthetic maize breeding \
trials (IDs like SYN-TR-0037) and lines (IDs like SYN-MZ-00001) using only the uc4 tools.

Rules:
1. Every number you state must appear in a tool result from this question. Do not \
calculate, estimate, average or subtract. If no tool gives a number, say it is not in \
the data.
2. Cite every fact right after the sentence that uses it, in square brackets: a row as \
[source_file#row_id], written exactly as in the tool result (an evidence_row_ids entry, \
or source_file and row_id joined by #); or a whole result as [tool:<tool name>] when it \
has no row ids (query_trials, baseline_check, list_sources).
3. Verdicts (PASS, HOLD, FAIL) and colours come from score_trial, get_trial or \
query_trials. Never set or change one. SYNTH_V1 thresholds are inferred from the \
supplied verdicts, not confirmed by Syngenta: say so whenever you state a threshold.
4. Verdicts are per trial. A line has no verdict of its own: list the verdicts of the \
trials it appears in without combining them.
5. Lab results have no trial key. Never attach a lab result to a trial.
6. A missing value never meets a criterion; say it is missing.
7. If a tool returns status "none", say what was not found and what input works. If an \
ID matches several records, the app asks the user which one; do not pick.
8. You recommend; the breeder decides. If asked whether to advance, select or drop \
material, give the evidence and say the decision is the breeder's.
9. Only answer questions about this data. Otherwise say you can only answer questions \
about the UC4 trial data.
10. Tool results from earlier questions are not kept: call the tools again for any value \
you need, even if it was discussed before.
11. Keep answers to at most five sentences, or a short list when several trials match. \
Outside citations, name trials and lines by ID, never by GUID.
12. When asked whether a trial meets every criterion, list the five measured criterion \
values and explain whether each meets its inferred threshold. When describing a HOLD \
or FAIL trial, call them criteria rather than using PASS as a generic adjective.
13. A line answer must explicitly say verdicts are per trial, not combined. For an \
unknown ID, cite [tool:find_trial] or [tool:find_line] for the absence result.
14. A citation must support the particular fact in the original source: observation \
rows support line-trial membership, not trial verdicts. Cite recommendation \
evidence_row_ids for verdicts. Cite [tool:get_trial], [tool:get_line] or \
[tool:score_trial] for computed reconciliation/flags rather than claiming they are \
stored in a single raw CSV row.
"""


@dataclass(frozen=True)
class AgentSettings:
    max_rounds: int = 6
    repair_rounds: int = 1


def load_agent_settings(path: Path = SETTINGS_PATH) -> AgentSettings:
    """``[agent]`` from ``agent.toml``; defaults for absent keys."""
    cfg = tomllib.loads(path.read_text(encoding="utf-8")).get("agent", {})
    return AgentSettings(**{k: int(v) for k, v in cfg.items()})


@dataclass(frozen=True)
class Answer:
    """One reply. ``status``: answered, clarify (pick a candidate), unverified (failed the
    evidence check after repair) or error (model or configuration failure)."""

    status: str
    text: str
    model: str
    citations: tuple[Citation, ...] = ()
    ungrounded: tuple[str, ...] = ()
    problems: tuple[str, ...] = ()  # why an unverified answer failed the evidence check
    candidates: tuple[dict[str, Any], ...] = ()
    tool_calls: tuple[ToolTrace, ...] = ()
    usage: Usage = Usage()
    disclaimer: str = DISCLAIMER


@dataclass
class _Turn:
    model: str
    messages: list[dict[str, Any]]
    traces: list[ToolTrace] = field(default_factory=list)
    usage: Usage = Usage()

    def answer(self, status: str, text: str, **extra: Any) -> Answer:
        return Answer(status=status, text=text, model=self.model,
                      tool_calls=tuple(self.traces), usage=self.usage, **extra)


async def ask(question: str, *, model: ChatModel, bridge: ToolBridge,
              history: Sequence[dict[str, str]] = (),
              settings: AgentSettings = AgentSettings()) -> Answer:
    """Answer one question from uc4 tool results.

    Args:
        question: The breeder's question.
        model: The chat model (Portkey in the app, a scripted fake in tests).
        bridge: The uc4 tools.
        history: Earlier turns as ``{"role": "user" | "assistant", "content": str}``.
        settings: Round limits.

    Returns:
        An ``Answer``. Model and tool failures come back as status "error", not exceptions.
    """
    started = time.monotonic()
    try:
        answer = await _run(question.strip(), model, bridge, history, settings)
    except Exception:  # last-resort boundary between the model/tool stack and the breeder
        logger.exception("ask failed")
        answer = Answer("error", "Internal error; see app/logs/uc4_agent.log", model.model)
    _log(question, answer, time.monotonic() - started)
    return answer


async def _run(question: str, model: ChatModel, bridge: ToolBridge,
               history: Sequence[dict[str, str]], settings: AgentSettings) -> Answer:
    if not question:
        return Answer("error", "Ask a question about the UC4 trials or lines.", model.model)
    tools = await bridge.function_schemas()
    names = {t["function"]["name"] for t in tools}
    prompt = CANDIDATE_SYSTEM_PROMPT if "score_candidate" in names else SYSTEM_PROMPT
    turn = _Turn(model.model, [{"role": "system", "content": prompt}, *history,
                               {"role": "user", "content": question}])
    repairs = 0
    for _ in range(settings.max_rounds):
        try:
            completion = await model.complete(turn.messages, tools)
        except LLMError as e:
            return turn.answer("error", str(e))
        turn.usage += completion.usage
        if completion.tool_calls:
            ambiguous = await _run_tools(turn, completion, bridge)
            if ambiguous:
                return turn.answer("clarify", _clarify(ambiguous),
                                   candidates=tuple(ambiguous.result["candidates"]))
            continue
        text = completion.text or ""
        if not text.strip():
            return turn.answer("error", "The model returned an empty answer.")
        grounding = check(text, question, turn.traces)
        if grounding.ok or repairs >= settings.repair_rounds:
            return turn.answer("answered" if grounding.ok else "unverified", text,
                               citations=grounding.citations, ungrounded=grounding.ungrounded,
                               problems=_problems(grounding))
        repairs += 1
        turn.messages += [{"role": "assistant", "content": text},
                          {"role": "user", "content": _repair_prompt(grounding)}]
    return turn.answer("error",
                       f"Stopped after {settings.max_rounds} model rounds without an answer.")


async def _run_tools(turn: _Turn, completion: Completion,
                     bridge: ToolBridge) -> ToolTrace | None:
    """Run the requested tools; returns the first ambiguous resolution (it ends the turn)."""
    turn.messages.append({"role": "assistant", "content": completion.text, "tool_calls": [
        {"id": r.id, "type": "function",
         "function": {"name": r.name, "arguments": json.dumps(r.arguments or {})}}
        for r in completion.tool_calls]})
    for request in completion.tool_calls:
        trace = await bridge.call(request.name, request.arguments)
        turn.traces.append(trace)
        turn.messages.append({"role": "tool", "tool_call_id": request.id,
                              "content": json.dumps(trace.result, allow_nan=False)})
        if request.name in RESOLVING_TOOLS and trace.status == "many":
            return trace
    return None


def _clarify(trace: ToolTrace) -> str:
    lines = [trace.result["message"]]
    lines += [f"- {c['id']}: {c['label']}" for c in trace.result["candidates"]]
    return "\n".join(lines)


def _repair_prompt(g: Grounding) -> str:
    problems = []
    if g.ungrounded:
        problems.append("these numbers are not in the tool results you cited: "
                        + ", ".join(g.ungrounded))
    missing = [c.ref for c in g.citations if not c.found]
    if missing:
        problems.append("these citations match no tool result: " + ", ".join(missing))
    if g.uncited:
        problems.append("the answer cites no tool result; cite the rows or [tool:<name>] "
                        "results you used")
    if g.verdicts:
        problems.append("these verdict or colour words are not in the results you cited: "
                        + ", ".join(g.verdicts))
    return ("Your answer failed the evidence check: " + "; ".join(problems) + ". Rewrite it "
            "using only values that appear in tool results, cite each one, and drop any "
            "number you calculated. Call a tool if you need a value.")


def _problems(g: Grounding) -> tuple[str, ...]:
    """Human-readable evidence-check failures, shown next to an unverified answer."""
    out = [f"number {n} not in cited results" for n in g.ungrounded]
    out += [f"citation {c.ref} not found" for c in g.citations if not c.found]
    out += ["no citation"] * g.uncited
    out += [f"verdict {v} not in cited results" for v in g.verdicts]
    return tuple(out)


def _log(question: str, answer: Answer, seconds: float) -> None:
    logger.info(json.dumps({
        "question": question, "status": answer.status, "model": answer.model,
        "tools": [{"name": t.name, "arguments": t.arguments, "status": t.status}
                  for t in answer.tool_calls],
        "prompt_tokens": answer.usage.prompt_tokens,
        "completion_tokens": answer.usage.completion_tokens,
        "seconds": round(seconds, 2), "ungrounded": list(answer.ungrounded)}))
