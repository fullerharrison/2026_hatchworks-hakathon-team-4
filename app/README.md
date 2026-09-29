# uc4-mcp

Read-only MCP server over the UC4 v2 data files. Plan: [phase-1-mcp-data-layer.md](../.tasks/uc4-assistant/phase-1-mcp-data-layer.md).

## Environment

The repo lives in OneDrive, so keep the virtual environment outside it (avoids sync churn and file locks). Set this once per shell before any `uv` command:

```powershell
$env:UV_PROJECT_ENVIRONMENT = "$env:LOCALAPPDATA\uc4-mcp\.venv"
```

Run tests from the repo root:

```powershell
uv run --project app pytest -q
```
