"""Checks an answer against the tool results it cites: every citation resolves, and every
number appears in a cited result (or in the question).

Citations are ``[<source_file>#<row_id>]`` (a row, as in ``evidence_row_ids``) or
``[tool:<name>]`` (a whole result, for tools without row ids such as ``query_trials``).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any

from uc4_mcp.bridge import ToolTrace

CITATION = re.compile(r"\[((?:[\w.\-]+\.csv#[\w\-]+)|(?:tool:\w+))\]")
# Tokens with digits that are identifiers, not quantities.
NOT_QUANTITIES = re.compile(
    r"SYN-[A-Z]{2}-\d+"
    r"|[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}"
    r"|\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?"
    r"|SYNTH_V\d+", re.IGNORECASE)
# Units may be glued on ("25kg"); the lookbehind still skips identifiers like Q3 or H2O.
NUMBER = re.compile(r"(?<![\w.])(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)")


@dataclass(frozen=True)
class Citation:
    ref: str
    found: bool  # the ref appears in a tool result of this turn


@dataclass(frozen=True)
class Grounding:
    citations: tuple[Citation, ...]
    ungrounded: tuple[str, ...]  # answer numbers in no cited result and not in the question

    @property
    def ok(self) -> bool:
        return not self.ungrounded and all(c.found for c in self.citations)


def quantities(text: str) -> list[str]:
    """Number tokens in ``text`` with thousands separators removed ("1,500" -> "1500").

    Citations, IDs, GUIDs, dates and rule names are ignored.
    """
    found = NUMBER.findall(NOT_QUANTITIES.sub(" ", CITATION.sub(" ", text)))
    return [token.replace(",", "") for token in found]


def _walk(obj: Any) -> Iterator[Any]:
    """Every scalar in a JSON value, plus each list's length (counts such as "16 trials")."""
    if isinstance(obj, dict):
        for value in obj.values():
            yield from _walk(value)
    elif isinstance(obj, list):
        yield len(obj)
        for value in obj:
            yield from _walk(value)
    else:
        yield obj


def numbers_in(obj: Any) -> set[float]:
    """Every number in a tool result: numeric values, list lengths, numbers inside text."""
    out: set[float] = set()
    for value in _walk(obj):
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, int | float):
            out.add(float(value))
        elif isinstance(value, str):
            out.update(float(n) for n in quantities(value))
    return out


def refs_in(obj: Any) -> set[str]:
    """Row refs in a tool result: ``evidence_row_ids`` entries and EvidenceRow objects."""
    out: set[str] = set()
    if isinstance(obj, dict):
        if isinstance(obj.get("source_file"), str) and isinstance(obj.get("row_id"), str):
            out.add(f"{obj['source_file']}#{obj['row_id']}")
        for value in obj.values():
            out |= refs_in(value)
    elif isinstance(obj, list):
        for value in obj:
            out |= refs_in(value)
    elif isinstance(obj, str) and CITATION.fullmatch(f"[{obj}]"):
        out.add(obj)
    return out


def _cites(trace: ToolTrace, ref: str) -> bool:
    if ref.startswith("tool:"):
        return trace.name == ref.removeprefix("tool:") and trace.status == "ok"
    return ref in refs_in(trace.result)


def _matches(token: str, pool: Iterable[float]) -> bool:
    """Equal as written: 10.8 matches 10.79; an integer token must match exactly."""
    value = float(token)
    decimals = len(token.partition(".")[2])
    tolerance = 0.5 * 10 ** -decimals if decimals else 0.0
    return any(abs(v - value) <= tolerance + 1e-9 for v in pool)


def check(answer: str, question: str, traces: Sequence[ToolTrace]) -> Grounding:
    """Ground ``answer`` in the traces it cites; numbers from the question are allowed."""
    citations: list[Citation] = []
    cited: list[ToolTrace] = []
    for ref in dict.fromkeys(CITATION.findall(answer)):
        hits = [t for t in traces if _cites(t, ref)]
        citations.append(Citation(ref, bool(hits)))
        cited += hits
    pool = {float(n) for n in quantities(question)}
    for t in cited:
        pool |= numbers_in(t.result)
    ungrounded = tuple(dict.fromkeys(n for n in quantities(answer) if not _matches(n, pool)))
    return Grounding(tuple(citations), ungrounded)
