"""Step 8: the server as a separate process, started the way MCP clients start it.

A stray print to stdout corrupts the stdio JSON-RPC stream; only these tests catch it.
The environment is passed explicitly: without ``env`` the mcp stdio client forwards only
a dozen variables, dropping ``UV_PROJECT_ENVIRONMENT`` and ``UC4_ZIP``.
"""

import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp import Client, StdioServerParameters

from uc4_mcp.server import parse_args

REPO = Path(__file__).resolve().parents[2]
BASELINE = {"checked": 72, "matched": 72, "mismatches": []}
TOOLS = {"list_sources", "find_trial", "find_line", "get_trial", "get_line", "score_trial",
         "query_trials", "baseline_check"}


def script() -> str:
    path = shutil.which("uc4-mcp")
    if path is None:
        pytest.fail("uc4-mcp not on PATH; run the tests with `uv run --project app pytest`",
                    pytrace=False)
    return path


def baseline_and_tools(server: StdioServerParameters | str) -> tuple[dict[str, Any], set[str]]:
    async def main() -> tuple[dict[str, Any], set[str]]:
        async with Client(server) as client:
            result = await client.call_tool("baseline_check", {})
            tools = await client.list_tools()
            assert not result.is_error, result.content
            assert result.structured_content is not None
            return result.structured_content, {t.name for t in tools.tools}
    return anyio.run(main)


def check(envelope: dict[str, Any], tools: set[str]) -> None:
    assert envelope["status"] == "ok" and envelope["result"] == BASELINE
    assert tools == TOOLS


def test_console_script_over_stdio() -> None:
    params = StdioServerParameters(command=script(), cwd=REPO, env=dict(os.environ))
    check(*baseline_and_tools(params))


def test_client_command_over_stdio() -> None:
    """The exact command opencode.json and the README give clients."""
    uv = shutil.which("uv")
    assert uv is not None
    params = StdioServerParameters(command=uv, args=["run", "--project", "app", "uc4-mcp"],
                                   cwd=REPO, env=dict(os.environ))
    check(*baseline_and_tools(params))


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_for_port(port: int, proc: subprocess.Popen[bytes], timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            pytest.fail(f"server exited with {proc.returncode} before listening")
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.2)
    pytest.fail(f"server not listening on {port} after {timeout} s")


def test_http_transport() -> None:
    """The streamable-HTTP URL the README gives n8n."""
    port = _free_port()
    proc = subprocess.Popen([script(), "--transport", "http", "--port", str(port)], cwd=REPO,
                            env=dict(os.environ), stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    try:
        _wait_for_port(port, proc)
        check(*baseline_and_tools(f"http://127.0.0.1:{port}/mcp"))
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_parse_args() -> None:
    default = parse_args([])
    assert (default.transport, default.host, default.port) == ("stdio", "127.0.0.1", 8765)
    http = parse_args(["--transport", "http", "--port", "9000", "--host", "0.0.0.0"])
    assert (http.transport, http.host, http.port) == ("http", "0.0.0.0", 9000)
    with pytest.raises(SystemExit):
        parse_args(["--transport", "sse"])
