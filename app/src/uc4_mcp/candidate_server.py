"""Read-only MCP surface for the current candidate dataset."""
from __future__ import annotations

import functools
import json
import threading
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from starlette.requests import Request
from starlette.responses import JSONResponse

from uc4_mcp.candidate_history import CandidateHistory

READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True)


_history_lock = threading.Lock()


@functools.cache
def _cached_history():
    return CandidateHistory()


def default_history():
    # The rule and shortlist requests can arrive together on first page load.
    with _history_lock:
        return _cached_history()


def create_candidate_server(get_history=default_history, *, pinned_store=None):
    server = MCPServer("uc4-candidates")

    def evidence_store():
        return pinned_store if pinned_store is not None else get_history().store()

    @server.custom_route("/health", methods=["GET"])
    async def health(_request: Request) -> JSONResponse:
        try:
            store = evidence_store()
            return JSONResponse(dict(status="ok", server="uc4-candidates", candidates=len(store.by_guid),
                                     sources=len(store.tables), snapshot_id=store.snapshot_id, revision_id=store.revision_id))
        except Exception as exc:
            return JSONResponse(dict(status="error", message=str(exc)), status_code=500)

    @server.tool(description="List the eight CSV source members, row counts and archive SHA-256 for the synthetic maize-like candidate dataset.", annotations=READ_ONLY)
    def list_sources() -> dict[str, Any]:
        history = get_history()
        store = evidence_store()
        return {"status": "ok", "result": {"snapshot_id": store.snapshot_id,
                "revision_id": store.revision_id,
                "files": [{"table": key, "source_file": frame._source_file.iloc[0], "rows": len(frame)}
                          for key, frame in store.tables.items()]}}

    @server.tool(description="Find a candidate by material ID or GUID, or a fragment. An ambiguous match returns candidates to choose from.", annotations=READ_ONLY)
    def find_candidate(query: str) -> dict[str, Any]:
        return evidence_store().resolve(query)

    @server.tool(description="Get one candidate's provisional GREEN/AMBER/RED recommendation, raw and reconstructed evidence, trials, checks, lab and genomics. Cite evidence_row_ids or [tool:get_candidate].", annotations=READ_ONLY)
    def get_candidate(query: str) -> dict[str, Any]:
        h = get_history()
        envelope = evidence_store().detail(query)
        if envelope["status"] == "ok":
            envelope["result"]["decisions"] = h.decisions(envelope["result"]["material_guid"])
        return envelope

    @server.tool(description="Score one candidate with provisional candidate rule; returns criteria, unrounded metrics, knockouts, warnings and source citation.", annotations=READ_ONLY)
    def score_candidate(query: str) -> dict[str, Any]:
        return evidence_store().resolve(query)

    @server.tool(description="List all matching candidates by optional RAG or search text. Returns total and rows; the default includes every candidate. Cite [tool:query_candidates].", annotations=READ_ONLY)
    def query_candidates(rag: str | None = None, search: str | None = None,
                         marker: str | None = None, decision: str | None = None,
                         ranges: dict[str, dict[str, float]] | None = None,
                         include_missing: bool = False, excluded: bool | None = None,
                         boundary: dict[str, Any] | None = None, sort: str = "material_id",
                         descending: bool = False,
                         offset: int = 0, limit: int = 150) -> dict[str, Any]:
        history = get_history()
        try:
            if offset < 0 or not 1 <= limit <= 500:
                raise ValueError("Use offset >=0 and limit between 1 and 500")
            store = evidence_store()
            rows = store.query({k: v for k, v in dict(rag=rag, search=search,
                      marker=marker, decision=decision, ranges=ranges,
                      include_missing=include_missing, excluded=excluded, boundary=boundary,
                      sort=sort, descending=descending).items() if v is not None}, history.latest())
        except ValueError as exc:
            return {"status": "none", "message": str(exc)}
        summaries = [{k: r[k] for k in ("material_id", "material_guid", "rag", "reason", "metrics",
                     "excluded_trials", "latest_decision", "review")} for r in rows[offset:offset + limit]]
        return {"status": "ok", "result": {"total": len(rows), "rows": summaries,
                "snapshot_id": store.snapshot_id, "revision_id": store.revision_id,
                "next_offset": offset + limit if offset + limit < len(rows) else None}}

    @server.tool(description="Read the complete provisional candidate scoring policy, warning thresholds, no-field-data precedence and rounding policy. Cite [tool:get_candidate_rule].", annotations=READ_ONLY)
    def get_candidate_rule() -> dict[str, Any]:
        return {"status": "ok", "result": evidence_store().rule()}

    @server.tool(description="Retired trial scoring contract. Candidate data requires score_candidate with a material ID.", annotations=READ_ONLY)
    def score_trial(query: str) -> dict[str, Any]:
        return {"status": "none", "message": "Trial scoring was retired; use score_candidate with a material ID"}

    @server.tool(description="Retired trial recommendation list. Use query_candidates for candidate-level RAG.", annotations=READ_ONLY)
    def query_trials() -> dict[str, Any]:
        return {"status": "none", "message": "Trial recommendation lists were retired; use query_candidates"}

    @server.tool(description="Compare provisional recommendations to the supplied RAG for every candidate, without claiming the biological rule is confirmed.", annotations=READ_ONLY)
    def baseline_check() -> dict[str, Any]:
        rows = list(evidence_store().by_guid.values())
        return {"status": "ok", "result": {"checked": len(rows),
                "matched": sum(r["matches_supplied"] for r in rows),
                "mismatches": [r["material_id"] for r in rows if not r["matches_supplied"]]}}

    @server.resource("uc4://candidate-rule", name="candidate-rule", mime_type="application/json",
                     description="Current provisional candidate scoring policy and thresholds.")
    def rule_resource() -> str:
        return json.dumps(evidence_store().rule(), allow_nan=False)

    @server.resource("uc4://sources", name="sources", mime_type="application/json",
                     description="Current candidate archive identity and source members.")
    def sources_resource() -> str:
        return json.dumps(list_sources()["result"], allow_nan=False)

    return server


server = create_candidate_server()
