"""Step 1 spike: prove an in-process mcp 2.x client can call a tool on our MCPServer."""

import anyio
from mcp import Client

from uc4_mcp.server import server


def test_ping_round_trip() -> None:
    async def call() -> tuple[list[str], str]:
        async with Client(server) as client:
            tools = await client.list_tools()
            result = await client.call_tool("ping", {})
            return [t.name for t in tools.tools], result.content[0].text

    names, text = anyio.run(call)
    assert "ping" in names
    assert text == "pong"
