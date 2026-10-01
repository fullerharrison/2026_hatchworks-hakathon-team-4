"""HTTP routes for current candidate recommendations and auditable breeder work."""
from __future__ import annotations

import csv
import io
import json
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from uc4_mcp.agent import AgentSettings, ask
from uc4_mcp.bridge import open_bridge
from uc4_mcp.candidate_history import CandidateHistory, Conflict
from uc4_mcp.candidate_server import default_history, create_candidate_server
from uc4_mcp.llm import ChatModel, LLMError
from uc4_mcp.models import to_json_safe

from uc4_mcp.api import LOCAL_ORIGINS, STATIC_DIR


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[Turn] = Field(default_factory=list, max_length=20)


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
    value: str | float | None = None
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
    server = server or create_candidate_server(get_history)
    app.add_middleware(CORSMiddleware, allow_origin_regex=LOCAL_ORIGINS,
                       allow_methods=["GET", "POST"], allow_headers=["*"])

    def history() -> CandidateHistory:
        return get_history()

    def filters(search=None, rag=None, decision=None, marker=None, excluded=None,
                ranges=None, include_missing=False, sort="material_id", descending=False):
        try:
            parsed = json.loads(ranges) if ranges else {}
        except json.JSONDecodeError as exc:
            raise HTTPException(422, f"Invalid ranges: {exc}") from exc
        return {k: v for k, v in dict(search=search, rag=rag, decision=decision,
                marker=marker, excluded=excluded, ranges=parsed,
                include_missing=include_missing, sort=sort,
                descending=descending).items() if v is not None}

    def matching(**kwargs):
        try:
            h = history()
            store = h.store()
            return store, store.query(filters(**kwargs), h.latest())
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

    @app.get("/candidates")
    def candidates(search: str | None = None, rag: str | None = None,
                   decision: str | None = None, marker: str | None = None,
                   excluded: bool | None = None, ranges: str | None = None,
                   include_missing: bool = False, sort: str = "material_id",
                   descending: bool = False, offset: int = Query(0, ge=0),
                   limit: int = Query(150, ge=1, le=500)):
        store, rows = matching(search=search, rag=rag, decision=decision, marker=marker,
                        excluded=excluded, ranges=ranges, include_missing=include_missing,
                        sort=sort, descending=descending)
        return dict(total=len(rows), total_available=len(store.by_guid), offset=offset, limit=limit,
                    next_offset=offset + limit if offset + limit < len(rows) else None,
                    snapshot_id=store.snapshot_id, revision_id=store.revision_id,
                    rows=rows[offset:offset + limit])

    @app.get("/candidates.csv")
    def export(search: str | None = None, rag: str | None = None,
               decision: str | None = None, marker: str | None = None,
               excluded: bool | None = None, ranges: str | None = None,
               include_missing: bool = False, sort: str = "material_id", descending: bool = False):
        store, rows = matching(search=search, rag=rag, decision=decision, marker=marker,
                        excluded=excluded, ranges=ranges, include_missing=include_missing,
                        sort=sort, descending=descending)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["material_id", "material_guid", "rag", "latest_decision",
                         "yield_vs_check_pct", "disease_score_mean", "moisture_pct_mean",
                         "germination_pct", "fumonisin_ppm", "n_trials_used",
                         "excluded_trials", "snapshot_id", "revision_id"])
        for r in rows:
            m = r["metrics"]
            writer.writerow([r["material_id"], r["material_guid"], r["rag"],
                             (r["latest_decision"] or {}).get("action"),
                             *[m[k] for k in ["YIELD_VS_CHECK_PCT", "DISEASE_SCORE_MEAN",
                                "MOISTURE_PCT_MEAN", "GERMINATION_PCT", "FUMONISIN_PPM", "N_TRIALS_USED"]],
                             r["excluded_trials"], r["snapshot_id"], r["revision_id"]])
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
            model = make_model()
        except LLMError as exc:
            raise HTTPException(503, str(exc)) from exc
        async with open_bridge(server) as bridge:
            answer = await ask(body.question, model=model, bridge=bridge,
                               history=[t.model_dump() for t in body.history], settings=settings)
        return to_json_safe(answer)

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
