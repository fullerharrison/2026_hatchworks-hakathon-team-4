"""The agent's view of the uc4 MCP tools: OpenAI function schemas and calls, in-process.

The agent goes through the same MCP server as OpenCode and n8n, so the tool descriptions
(the agent's instructions) and the envelopes are defined once, in ``server.py``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from mcp import Client
from mcp.server.mcpserver import MCPServer

from uc4_mcp.candidate_server import server as default_server


@dataclass(frozen=True)
class ToolTrace:
    """One tool call and its envelope; ``status`` is the envelope status or "error"."""

    name: str
    arguments: dict[str, Any]
    status: str
    result: dict[str, Any]


def _error(name: str, arguments: dict[str, Any], message: str) -> ToolTrace:
    return ToolTrace(name, arguments, "error", {"status": "error", "message": message})


class ToolBridge:
    """Lists and calls the tools of one connected MCP client."""

    def __init__(self, client: Client) -> None:
        self._client = client
        self._schemas: list[dict[str, Any]] | None = None

    async def function_schemas(self) -> list[dict[str, Any]]:
        """The MCP tools as OpenAI ``tools`` entries (name, description, input schema)."""
        if self._schemas is None:
            tools = (await self._client.list_tools()).tools
            self._schemas = [{"type": "function", "function": {
                "name": t.name, "description": t.description or "",
                "parameters": t.input_schema}} for t in tools]
        return self._schemas

    async def call(self, name: str, arguments: dict[str, Any] | None) -> ToolTrace:
        """Call one tool. Bad input comes back as an "error" trace the model can read."""
        if arguments is None:
            return _error(name, {}, "Tool arguments were not valid JSON; call the tool again")
        result = await self._client.call_tool(name, arguments)
        if result.is_error or result.structured_content is None:
            text = " ".join(getattr(c, "text", "") for c in result.content).strip()
            return _error(name, arguments, text or f"Tool {name} failed")
        envelope = result.structured_content
        return ToolTrace(name, arguments, str(envelope["status"]), envelope)


@asynccontextmanager
async def open_bridge(server: MCPServer | None = None) -> AsyncIterator[ToolBridge]:
    """Connect in-process to ``server`` (default: the uc4 server over the zip)."""
    async with Client(server or default_server) as client:
        yield ToolBridge(client)
