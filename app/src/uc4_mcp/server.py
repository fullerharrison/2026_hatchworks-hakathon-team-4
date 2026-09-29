"""MCP server for the UC4 evidence layer. Never print to stdout: it carries the stdio protocol."""

from mcp.server.mcpserver import MCPServer

server = MCPServer("uc4-mcp")


# Step 1 spike only; removed once the real tools land in step 7.
@server.tool()
def ping() -> str:
    """Health check. Returns "pong"."""
    return "pong"


def main() -> None:
    """Run the server over stdio."""
    server.run("stdio")
