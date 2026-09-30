"""HTTP front for the breeder screen and n8n: the question agent, trial and line reads, and
the append-only decision log.

``POST /ask`` returns the ``Answer`` as JSON with status 200 whatever its ``status``
(answered, clarify, unverified, error); only a missing model configuration is 503.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any, Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field, StringConstraints

from uc4_mcp.agent import AgentSettings, ask
from uc4_mcp.bridge import open_bridge
from uc4_mcp.decisions import (REASON_MAX, REASON_MIN, USER_MAX, DecisionError, DecisionLog,
                               log_path, record_decision)
from uc4_mcp.llm import ChatModel, LLMError
from uc4_mcp.models import to_json_safe
from uc4_mcp.server import _default_store
from uc4_mcp.store import EvidenceStore

LOCAL_ORIGINS = r"http://(localhost|127\.0\.0\.1)(:\d+)?"


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[Turn] = Field(default_factory=list, max_length=20)


Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=REASON_MIN,
                                          max_length=REASON_MAX)]
User = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1,
                                        max_length=USER_MAX)]


class DecisionRequest(BaseModel):
    trial: str = Field(min_length=1, max_length=80)
    decision: Literal["PASS", "HOLD", "FAIL"]
    reason: Reason
    user: User
    material_guid: str | None = Field(default=None, max_length=80)


def create_app(make_model: Callable[[], ChatModel], server: MCPServer | None = None,
               settings: AgentSettings = AgentSettings(), *,
               get_store: Callable[[], EvidenceStore] | None = None,
               log: DecisionLog | None = None) -> FastAPI:
    """Build the API.

    Args:
        make_model: Called per request, so a missing key fails that request (503), not
            startup; tests pass a fake.
        server: The MCP server the agent calls in-process (None: the uc4 server over the zip).
        settings: Round limits for ``ask``.
        get_store: Evidence store for the read and decision routes (None: the default zip).
        log: Decision log (None: the file named by ``log_path()``).
    """
    get_store = get_store or _default_store
    log = log or DecisionLog(log_path())
    app = FastAPI(title="uc4 question agent")
    app.add_middleware(CORSMiddleware, allow_origin_regex=LOCAL_ORIGINS,
                       allow_methods=["GET", "POST"], allow_headers=["*"])

    @app.get("/health")
    def health() -> dict[str, Any]:
        try:
            return {"status": "ok", "model": make_model().model}
        except LLMError as e:
            return {"status": "degraded", "llm": str(e)}

    @app.post("/ask")
    async def ask_endpoint(body: AskRequest) -> JSONResponse:
        try:
            model = make_model()
        except LLMError as e:
            return JSONResponse({"status": "error", "text": str(e)}, status_code=503)
        async with open_bridge(server) as bridge:
            answer = await ask(body.question, model=model, bridge=bridge,
                               history=[t.model_dump() for t in body.history],
                               settings=settings)
        return JSONResponse(to_json_safe(answer))

    def decisions_json(trial_guid: str | None) -> list[dict[str, Any]]:
        return [to_json_safe(r) for r in log.read(trial_guid)]

    @app.get("/trials")
    def trials() -> list[dict[str, Any]]:
        store, latest = get_store(), {r.trial_guid: r for r in log.read()}
        out = []
        for guid in store.trial_guids:
            rec = store.recommendation(guid)
            last = latest.get(guid)
            out.append({"trial_id": rec.trial_id, "trial_guid": guid, "verdict": rec.verdict,
                        "colour": rec.colour, "reason": rec.reason,
                        "latest_decision": to_json_safe(last) if last else None})
        return out

    @app.get("/trials/{query}")
    def trial(query: str) -> dict[str, Any]:
        envelope = to_json_safe(get_store().get_trial(query))
        if envelope["status"] == "ok":
            envelope["decisions"] = decisions_json(envelope["result"]["trial_guid"])
        return envelope

    @app.get("/lines/{query}")
    def line(query: str) -> dict[str, Any]:
        return to_json_safe(get_store().get_line(query))

    @app.post("/decisions", status_code=201)
    def decide(body: DecisionRequest) -> JSONResponse:
        try:
            record = record_decision(get_store(), log, **body.model_dump())
        except DecisionError as e:
            if e.envelope is not None:
                code = 409 if e.envelope["status"] == "many" else 404
                return JSONResponse(e.envelope, status_code=code)
            return JSONResponse({"status": "error", "message": str(e)}, status_code=422)
        return JSONResponse(to_json_safe(record), status_code=201)

    @app.get("/decisions")
    def decisions(trial: str | None = None) -> JSONResponse:
        if trial is None:
            return JSONResponse(decisions_json(None))
        res = get_store().resolve_trial(trial)
        if res.status != "ok":
            return JSONResponse(to_json_safe(get_store().find_trial(trial)), status_code=404)
        return JSONResponse(decisions_json(str(res.guid)))

    return app
