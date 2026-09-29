"""Contracts shared by the MCP tools, the agent (Phase 2) and the screen (Phase 3).

Frozen dataclasses from team/ROLES.md, the response envelope every tool returns,
``to_json_safe()`` for pandas/numpy output, and source-qualified evidence
references (``"<source_file>#<row_id>"``): ``row_id`` alone is ambiguous because
``trial`` and ``recommendations`` both key on ``TRIAL_GUID``.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

REF_SEP = "#"


@dataclass(frozen=True)
class EvidenceRow:
    """One cited value: the file and row it came from, and what it measures."""

    source_file: str
    row_id: str
    line_no: int
    trial_guid: str | None  # None for lab and genomics rows (no trial key)
    material_guid: str | None  # None for trial-level values
    field: str
    value: str | float | int | None
    uom: str | None
    date: str | None
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class Criterion:
    """One SYNTH_V1 test on a trial value; ``field`` is not unique across criteria."""

    field: str
    label: str
    value: float | None
    test: str  # ">=", "<=", "<", ">"
    threshold: float
    bracket: tuple[float, float]
    kind: str  # "pass" | "knockout"
    passed: bool  # pass criterion met, or knockout NOT triggered; a missing value never passes
    triggered: bool  # knockout fired; always False for kind == "pass"


@dataclass(frozen=True)
class Flag:
    """A consistency finding for amber review; never changes a verdict."""

    code: str
    severity: str
    message: str
    evidence_row_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class Recommendation:
    """A trial's SYNTH_V1 verdict, every criterion against its threshold, and its sources."""

    trial_guid: str
    trial_id: str
    verdict: str
    colour: str  # a proposal
    criteria: tuple[Criterion, ...]
    knockout: tuple[str, ...]
    reason: str
    rule_version: str
    supplied_verdict: str
    matches_supplied: bool
    supplied_rationale: str
    rationale_omits: tuple[str, ...]
    evidence_row_ids: tuple[str, ...]
    flags: tuple[Flag, ...]


@dataclass(frozen=True)
class Candidate:
    """One possible match when a query is ambiguous."""

    id: str
    guid: str
    label: str


def ok(result: Any, message: str = "") -> dict[str, Any]:
    """Envelope for a single resolved result."""
    return {"status": "ok", "result": result, "message": message}


def many(candidates: Sequence[Candidate], message: str) -> dict[str, Any]:
    """Envelope for an ambiguous query: the caller must choose, never the server."""
    return {"status": "many", "candidates": list(candidates), "message": message}


def none(message: str) -> dict[str, Any]:
    """Envelope for a query with no match."""
    return {"status": "none", "message": message}


def evidence_ref(row: Mapping[str, Any] | pd.Series) -> str:
    """``"<source_file>#<row_id>"`` for a row loaded by ``sources.load_tables``."""
    return f"{row['_source_file']}{REF_SEP}{row['_row_id']}"


def parse_evidence_ref(ref: str) -> tuple[str, str]:
    """Split an evidence reference into ``(source_file, row_id)``.

    Raises:
        ValueError: If ``ref`` has no separator or an empty part.
    """
    source_file, sep, row_id = ref.rpartition(REF_SEP)
    if not (sep and source_file and row_id):
        raise ValueError(f"Not an evidence reference: {ref!r}")
    return source_file, row_id


def to_json_safe(obj: Any) -> Any:
    """Convert to plain JSON types: dataclasses and mappings to dicts, sequences to lists,
    numpy scalars to Python, NaN/NaT/NA to None, timestamps to ISO strings.

    Raises:
        TypeError: For a type with no JSON form, rather than emitting its repr.
    """
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_json_safe(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, Mapping):
        return {str(k): to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_json_safe(v) for v in obj]
    if obj is None or obj is pd.NaT or obj is pd.NA:
        return None
    if isinstance(obj, np.generic):
        obj = obj.item()
    if isinstance(obj, float):
        return None if math.isnan(obj) else obj
    if isinstance(obj, (str, bool, int)):
        return obj
    if isinstance(obj, (dt.datetime, dt.date)):
        return obj.isoformat()
    raise TypeError(f"No JSON form for {type(obj).__name__}: {obj!r}")
