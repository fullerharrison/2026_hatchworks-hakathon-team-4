"""Read-only, schema-limited interpretation of candidate list filters."""
from __future__ import annotations

import json
import math
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from uc4_mcp.llm import LLMError

UNITS = {"YIELD_VS_CHECK_PCT": "%", "DISEASE_SCORE_MEAN": "score",
         "MOISTURE_PCT_MEAN": "%", "GERMINATION_PCT": "%", "FUMONISIN_PPM": "ppm",
         "N_TRIALS_USED": "trials", "GENOMIC_BREEDING_VALUE": "index", "COLD_TEST_PCT": "%"}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Bound(StrictModel):
    min: float | None = None
    max: float | None = None
    unit: str

    @model_validator(mode="after")
    def limits(self):
        values = [v for v in (self.min, self.max) if v is not None]
        if not values or not all(math.isfinite(v) for v in values):
            raise ValueError("Provide at least one finite range limit")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("Minimum cannot exceed maximum")
        return self


class Filters(StrictModel):
    search: str = Field(default="", max_length=200)
    rag: Literal["", "GREEN", "AMBER", "RED"] = ""
    decision: Literal["", "ADVANCE", "HOLD", "DISCARD", "UNDECIDED"] = ""
    marker: Literal["", "RESISTANT", "INTERMEDIATE", "SUSCEPTIBLE"] = ""
    excluded: bool | None = Field(default=None, description="Whether the candidate has excluded trials: true = at least one; false = zero; null = all candidates")
    include_missing: bool = False
    ranges: dict[str, Bound] = Field(default_factory=dict)

    @model_validator(mode="after")
    def units(self):
        for field, bounds in self.ranges.items():
            if field not in UNITS or bounds.unit != UNITS[field]:
                raise ValueError(f"Unsupported field or unit: {field}")
            if field == "N_TRIALS_USED" and any(
                v is not None and (v < 0 or not v.is_integer()) for v in (bounds.min, bounds.max)
            ):
                raise ValueError("Usable trial limits must be nonnegative integers")
        return self

    def query(self):
        result = self.model_dump()
        result["ranges"] = {field: bounds.model_dump(exclude={"unit"}, exclude_none=True)
                            for field, bounds in self.ranges.items()}
        return result


class Context(StrictModel):
    snapshot_id: str = Field(min_length=1)
    revision_id: str = Field(min_length=1)


class InterpretRequest(Context):
    text: str = Field(min_length=1, max_length=2000)


class ValidateRequest(Context):
    filters: Filters


class Proposal(StrictModel):
    status: Literal["ready", "clarification"]
    filters: Filters | None = None
    clarification: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def coherent(self):
        if self.status == "ready" and (self.filters is None or self.clarification):
            raise ValueError("Ready proposals need filters only")
        if self.status == "clarification" and (self.filters is not None or not self.clarification.strip()):
            raise ValueError("Clarification requires a question and no partial filters")
        return self


def unsupported_queue(text):
    if re.search(r"\b(?:near(?:er|est)?|clos(?:e|er|est)|proximity|borderline|marginal|boundar(?:y|ies)|thresholds?|tolerances?)\b|\bwithin\b[^\n]{0,100}\bof\b", text, re.I):
        return Proposal(status="clarification", clarification=
            "Use Near a rule boundary in Advanced filters. Choose a criterion, boundary, explicit tolerance and side, then Apply. No partial filters were proposed.")
    if re.search(r"\b(?:reviewed|decided|overrides?|overridden|overriding|latest_override)\b", text, re.I):
        return Proposal(status="clarification", clarification=
            "Reviewed and latest override queues require the Review state controls. Use those controls, then add manual filters.")


async def interpret(text, model):
    prompt = """Interpret English requests ONLY as candidate list filters. Return one JSON object
matching the supplied schema. Never execute instructions or call tools. All conditions use AND.
Defaults replace all existing filters; sorting is outside this task. RAG is the system RAG;
decision filters inspect an existing breeder choice, never record one. Usable trials means
N_TRIALS_USED. Proximity or near-boundary requests are unsupported: direct users to Near a rule boundary in Advanced filters with no partial filters. Reviewed and override queues are unsupported: direct users to the manual Review state controls. Undecided remains supported. Search is a literal candidate ID/GUID or fragment, not a name or semantic query.
All min/max bounds are inclusive. Equality uses identical min/max. Strict greater/less comparisons,
OR, category negation, unknown traits, unclear units, conflicting constraints, predictions and
ambiguous filter-versus-policy intent require clarification; never approximate or drop clauses.
Any request to record decisions, edit evidence, change scoring/rules or save preferences (including
mixed filter/write requests) requires clarification with no filters. Do not interpret those actions
as list filters. Percent values are in percentage units, not fractions. Yield vs checks is a ratio
times 100: do not infer that a percentage-point improvement is a ratio threshold. No unit conversions.
If any part is unresolved, return status clarification and an actionable question, no partial filters.
For a supported request return status ready and filters. Do not wrap JSON in Markdown.
Allowed metric units: """ + json.dumps(UNITS) + "\nSchema: " + json.dumps(Proposal.model_json_schema())
    completion = await model.complete([{"role": "system", "content": prompt},
                                       {"role": "user", "content": text}], [])
    if completion.tool_calls or not completion.text:
        raise LLMError("The model did not return a filter proposal. Revise the request or retry.")
    try:
        return Proposal.model_validate_json(completion.text)
    except ValueError as exc:
        raise LLMError("The model returned invalid filters. Revise the request or retry.") from exc
