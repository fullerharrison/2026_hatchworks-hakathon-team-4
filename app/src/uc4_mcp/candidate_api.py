"""HTTP routes for current candidate recommendations and auditable breeder work."""
from __future__ import annotations

import csv
import io
import json
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field, StrictFloat, StrictStr

from uc4_mcp.agent import AgentSettings, ask
from uc4_mcp.bridge import open_bridge
from uc4_mcp.candidate_history import CandidateHistory, Conflict
from uc4_mcp.candidate_server import default_history, create_candidate_server
from uc4_mcp.llm import ChatModel, LLMError
from uc4_mcp.models import to_json_safe
from uc4_mcp.filter_intent import InterpretRequest, ValidateRequest, interpret, unsupported_queue

from uc4_mcp.api import LOCAL_ORIGINS, STATIC_DIR


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[Turn] = Field(default_factory=list, max_length=20)
    candidate: str | None = None
    revision_id: str | None = None


class DecisionRequest(BaseModel):
    query: str
    action: str
    actor: str
    reason: str
    context: dict[str, Any]
    recommendation_id: str
    previous_decision_id: str | None = None
    request_id: str


class EnrichmentDraft(BaseModel):
    query: str
    kind: str
    table: str | None = None
    row_id: str | None = None
    field: str | None = None
    value: StrictStr | StrictFloat | None = None
    unit: str | None = None
    actor: str
    reason: str
    observed_at: str
    source: str
    supersedes: str | None = None


class ReviewRequest(BaseModel):
    action: str
    actor: str
    reason: str


class ActivateRequest(BaseModel):
    base_revision: str
    actor: str
    reason: str


class RollbackRequest(BaseModel):
    target_revision: str
    actor: str
    reason: str


def create_candidate_app(make_model, server: MCPServer | None = None,
                         settings: AgentSettings = AgentSettings(),
                         get_history=default_history) -> FastAPI:
    app = FastAPI(title="UC4 candidate breeder assistant")

    @app.exception_handler(RequestValidationError)
    async def filter_validation_error(request, exc):
        if request.url.path in {"/filters/interpret", "/filters/validate"}:
            # Never echo raw inputs (including nonfinite numbers) into an error response.
            return JSONResponse(status_code=422, content={"detail": [
                {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
                for error in exc.errors()]})
        return await request_validation_exception_handler(request, exc)
    server = server or create_candidate_server(get_history)
    app.add_middleware(CORSMiddleware, allow_origin_regex=LOCAL_ORIGINS,
                       allow_methods=["GET", "POST"], allow_headers=["*"])

    def history() -> CandidateHistory:
        return get_history()

    def filters(search=None, rag=None, decision=None, review_state="all", marker=None, excluded=None,
                ranges=None, boundary=None, include_missing=False, sort="material_id", descending=False):
        try:
            parsed = json.loads(ranges) if ranges else {}
            proximity = json.loads(boundary) if boundary is not None else None
            if boundary is not None and proximity is None:
                raise ValueError("Boundary must be an object")
        except json.JSONDecodeError as exc:
            raise HTTPException(422, f"Invalid filter JSON: {exc}") from exc
        return {k: v for k, v in dict(search=search, rag=rag, decision=decision, review_state=review_state,
                marker=marker, excluded=excluded, ranges=parsed, boundary=proximity,
                include_missing=include_missing, sort=sort,
                descending=descending).items() if v is not None}

    def matching(**kwargs):
        try:
            h = history()
            store, latest, generation = h.read_view()
            all_rows = store.query(latest=latest)
            overview = dict(total=len(all_rows),
                rag={rag: sum(r["rag"] == rag for r in all_rows) for rag in ("GREEN", "AMBER", "RED")},
                reviewed=sum(r["latest_decision"] is not None for r in all_rows),
                undecided=sum(r["latest_decision"] is None for r in all_rows),
                latest_override=sum(bool(r["latest_decision"] and r["latest_decision"]["overrides"]) for r in all_rows))
            return store, store.query(filters(**kwargs), latest), overview, generation
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    def result_or_http(envelope):
        if envelope["status"] == "none":
            raise HTTPException(404, envelope["message"])
        if envelope["status"] == "many":
            raise HTTPException(409, envelope)
        return envelope["result"]

    @app.get("/health")
    def health():
        h = history()
        try:
            model = make_model().model
        except LLMError:
            model = None
        return dict(status="ok", candidates=len(h.store().by_guid), snapshot_id=h.snapshot_id,
                    revision_id=h.active_revision(), model=model)

    def filter_context(body):
        store = history().store()
        if (body.snapshot_id, body.revision_id) != (store.snapshot_id, store.revision_id):
            raise HTTPException(409, "Evidence changed. Refresh the list and interpret again.")
        return store

    def validate_filters(store, filters):
        if filters.search and not any(filters.search.lower() in
                (r["material_id"] + r["material_guid"]).lower() for r in store.by_guid.values()):
            raise HTTPException(422, "Unknown candidate ID or GUID. Edit the candidate filter.")
        return len(store.query(filters.query(), history().latest()))

    @app.post("/filters/interpret")
    async def interpret_filters(body: InterpretRequest):
        store = filter_context(body)
        if not body.text.strip():
            raise HTTPException(422, "Enter a filter request.")
        try:
            proposal = unsupported_queue(body.text) or await interpret(body.text, make_model())
        except LLMError as exc:
            raise HTTPException(503, str(exc)) from exc
        filter_context(body)
        if proposal.filters is not None:
            validate_filters(store, proposal.filters)
        return dict(**proposal.model_dump(), snapshot_id=store.snapshot_id, revision_id=store.revision_id)

    @app.post("/filters/validate")
    def validate_filter_proposal(body: ValidateRequest):
        store = filter_context(body)
        count = validate_filters(store, body.filters)
        return dict(filters=body.filters.model_dump(), total=count,
                    snapshot_id=store.snapshot_id, revision_id=store.revision_id)

    @app.get("/rule")
    def rule():
        return history().store().rule()

    @app.get("/candidates")
    def candidates(search: str | None = None, rag: str | None = None,
                   decision: str | None = None, review_state: str = "all", marker: str | None = None,
                   excluded: bool | None = None, ranges: str | None = None, boundary: str | None = None,
                   include_missing: bool = False, sort: str = "material_id",
                   descending: bool = False, offset: int = Query(0, ge=0),
                   limit: int = Query(150, ge=1, le=500)):
        store, rows, overview, generation = matching(search=search, rag=rag, decision=decision, review_state=review_state, marker=marker,
                        excluded=excluded, ranges=ranges, boundary=boundary, include_missing=include_missing,
                        sort=sort, descending=descending)
        return dict(total=len(rows), total_available=len(store.by_guid), offset=offset, limit=limit,
                    next_offset=offset + limit if offset + limit < len(rows) else None,
                    snapshot_id=store.snapshot_id, revision_id=store.revision_id,
                    overview=overview, processing=store.processing(), decision_generation=generation, rows=rows[offset:offset + limit])

    @app.get("/candidates.csv")
    def export(search: str | None = None, rag: str | None = None,
               decision: str | None = None, review_state: str = "all", marker: str | None = None,
               excluded: bool | None = None, ranges: str | None = None, boundary: str | None = None,
               include_missing: bool = False, sort: str = "material_id", descending: bool = False):
        store, rows, overview, generation = matching(search=search, rag=rag, decision=decision, review_state=review_state, marker=marker,
                        excluded=excluded, ranges=ranges, boundary=boundary, include_missing=include_missing,
                        sort=sort, descending=descending)
        output = io.StringIO()
        writer = csv.writer(output)
        boundary_columns = ["field", "kind", "tolerance", "side", "test", "threshold", "unit", "observed", "signed_margin", "distance", "test_outcome"] if boundary is not None else []
        writer.writerow(["material_id", "material_guid", "rag", "latest_decision",
                         "yield_vs_check_pct", "disease_score_mean", "moisture_pct_mean",
                         "germination_pct", "fumonisin_ppm", "n_trials_used",
                         "excluded_trials", "snapshot_id", "revision_id"] + ["boundary_" + k for k in boundary_columns])
        for r in rows:
            m = r["metrics"]
            writer.writerow([r["material_id"], r["material_guid"], r["rag"],
                             (r["latest_decision"] or {}).get("action"),
                             *[m[k] for k in ["YIELD_VS_CHECK_PCT", "DISEASE_SCORE_MEAN",
                                "MOISTURE_PCT_MEAN", "GERMINATION_PCT", "FUMONISIN_PPM", "N_TRIALS_USED"]],
                             r["excluded_trials"], r["snapshot_id"], r["revision_id"]] + [r["review"]["boundary"][k] for k in boundary_columns])
        return Response(output.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=uc4-candidates.csv"})

    @app.get("/candidates/{query}")
    def candidate(query: str):
        rec = result_or_http(history().store().detail(query))
        rec["decisions"] = history().decisions(rec["material_guid"])
        rec["enrichment_history"] = history().enrichment(rec["material_guid"])
        return rec

    @app.get("/decisions")
    def decisions(query: str | None = None):
        guid = result_or_http(history().store().resolve(query))["material_guid"] if query else None
        return history().decisions(guid)

    @app.post("/decisions", status_code=201)
    def decide(body: DecisionRequest):
        try:
            return history().decide(**body.model_dump())
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/historical-decisions")
    def historical_decisions():
        return history().legacy()

    @app.get("/enrichment")
    def enrichment(query: str | None = None):
        guid = result_or_http(history().store().resolve(query))["material_guid"] if query else None
        return history().enrichment(guid)

    @app.post("/enrichment", status_code=201)
    def draft(body: EnrichmentDraft):
        try:
            return history().draft(**body.model_dump())
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/enrichment/{item_id}/review")
    def review(item_id: str, body: ReviewRequest):
        try:
            return history().review(item_id, **body.model_dump())
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/enrichment/{item_id}/preview")
    def preview(item_id: str):
        try:
            return history().preview(item_id)
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/enrichment/{item_id}/activate")
    def activate(item_id: str, body: ActivateRequest):
        try:
            return history().activate(item_id, **body.model_dump())
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/revisions/rollback")
    def rollback(body: RollbackRequest):
        try:
            return history().rollback(**body.model_dump())
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/revisions")
    def revisions():
        return dict(active_revision=history().active_revision(), revisions=history().revisions())

    @app.get("/revisions/{revision_id}/candidates/{query}")
    def historical_candidate(revision_id: str, query: str):
        try:
            return result_or_http(history().store(revision_id).detail(query))
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/ask")
    async def ask_endpoint(body: AskRequest):
        try:
            store = history().store(body.revision_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        selected = result_or_http(store.resolve(body.candidate)) if body.candidate else None
        context = dict(snapshot_id=store.snapshot_id, revision_id=store.revision_id,
                       candidate=selected["material_id"] if selected else None)
        question = body.question
        if selected:
            question = (f"Selected candidate context: {selected['material_id']}. "
                        "Use this for 'this candidate'; explicit references to other candidates take precedence. "
                        "Identify the candidates actually used in your answer.\nQuestion: " + question)
        try:
            model = make_model()
        except LLMError as exc:
            raise HTTPException(503, str(exc)) from exc
        request_server = create_candidate_server(get_history, pinned_store=store)
        async with open_bridge(request_server) as bridge:
            answer = await ask(question, model=model, bridge=bridge,
                               history=[t.model_dump() for t in body.history], settings=settings)
        result = to_json_safe(answer)
        result["context"] = context
        return result

    @app.get("/trials/{query}")
    @app.get("/lines/{query}")
    def historical_interface(query: str):
        raise HTTPException(410, "Trial/line scoring was retired; use /candidates/{material_id}")

    @app.get("/trials")
    def historical_list():
        raise HTTPException(410, "Trial scoring was retired; use /candidates")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def screen():
        return FileResponse(STATIC_DIR / "candidate.html")

    return app
