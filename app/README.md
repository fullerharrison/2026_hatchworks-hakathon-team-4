# uc4-mcp

Read-only MCP server over the UC4 v2 data files. Plan: [phase-1-mcp-data-layer.md](../.tasks/uc4-assistant/phase-1-mcp-data-layer.md).

## Environment

The repo lives in OneDrive, so keep the virtual environment outside it (avoids sync churn and file locks). Set this once per shell before any `uv` command:

```powershell
$env:UV_PROJECT_ENVIRONMENT = "$env:LOCALAPPDATA\uc4-mcp\.venv"
```

To make it permanent for your user (so MCP clients launched from anywhere inherit it):

```powershell
[Environment]::SetEnvironmentVariable("UV_PROJECT_ENVIRONMENT", "$env:LOCALAPPDATA\uc4-mcp\.venv", "User")
```

Run tests from the repo root. Keep the `app/tests` path: without it pytest also collects `analysis/uc4_eda/`, whose test modules share basenames with ours.

```powershell
uv run --project app pytest -q app/tests
```

## Data

The tests and server read `get_started/RE__Hatchworks_Hackathon_-_4th_Use_Case*.zip`, which is git-ignored (data clearance is still open), so copy it there after cloning. Exactly one archive may match; otherwise, or to use a copy elsewhere, set `UC4_ZIP` to its full path.

## Connect OpenCode (stdio)

The repo-root [opencode.json](../opencode.json) already registers the server as `uc4`. Start OpenCode from the repo root in a shell where `UV_PROJECT_ENVIRONMENT` is set, then check:

```powershell
opencode mcp list        # expect: ✓ uc4 connected
```

Verified 2026-09-29 with OpenCode 1.18.32 and `mcp` 2.2.0: `opencode run "Call the uc4 ping tool…"` returned `pong`.

Do not add an `environment` block with `{env:LOCALAPPDATA}` to `opencode.json`: OpenCode substitutes the value before parsing, and the Windows backslashes make the JSON invalid.

## MCP Inspector

Needs Node. `mcp dev` is still the 2.x command:

```powershell
uv run --project app mcp dev app/src/uc4_mcp/server.py
```
