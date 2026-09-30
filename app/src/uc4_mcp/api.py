"""HTTP front of the question agent for the Phase 3 screen and n8n.

``POST /ask`` returns the ``Answer`` as JSON with status 200 whatever its ``status``
(answered, clarify, unverified, error); only a missing model configuration is 503.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from uc4_mcp.agent import AgentSettings, ask
from uc4_mcp.bridge import open_bridge
from uc4_mcp.llm import ChatModel, LLMError
from uc4_mcp.models import to_json_safe

LOCAL_ORIGINS = r"http://(localhost|127\.0\.0\.1)(:\d+)?"


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[Turn] = Field(default_factory=list, max_length=20)


def create_app(make_model: Callable[[], ChatModel], server: MCPServer | None = None,
               settings: AgentSettings = AgentSettings()) -> FastAPI:
    """Build the API.

    Args:
        make_model: Called per request, so a missing key fails that request (503), not
            startup; tests pass a fake.
        server: The MCP server the agent calls in-process (None: the uc4 server over the zip).
        settings: Round limits for ``ask``.
    """
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

    return app
