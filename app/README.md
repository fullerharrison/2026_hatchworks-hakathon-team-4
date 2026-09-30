# uc4-mcp

Read-only MCP server over the UC4 v2 data files. Plan: [phase-1-mcp-data-layer.md](../.tasks/uc4-assistant/phase-1-mcp-data-layer.md).

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 and the dependencies).
- The v2 zip in `get_started/` (see [Data](#data)).
- Node, only for the MCP Inspector.

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

## Run

From the repo root:

```powershell
uv run --project app uc4-mcp                                   # stdio (what MCP clients launch)
uv run --project app uc4-mcp --transport http --port 8765      # streamable HTTP at http://127.0.0.1:8765/mcp
```

- The server loads the zip at startup; a missing zip exits with code 1 and a message naming `UC4_ZIP`.
- Logs go to `app/logs/uc4_mcp.log`, never stdout (stdout carries the stdio protocol).
- `--host 0.0.0.0` is only for clients in Docker (see [n8n](#connect-n8n-http)).

## Tools and resources

Every tool returns `{"status": "ok" | "many" | "none", "result" | "candidates", "message"}`, and every value cites `source_file` and `row_id`. Verdicts are per trial; thresholds are SYNTH_V1 (inferred).

| Tool | Example input | Returns |
| --- | --- | --- |
| `list_sources` | none | the 7 files: rows, key, grain, synthetic marker, what each lacks; extract date |
| `find_trial` | `query="0037"` | the trial, or up to 20 candidates |
| `find_line` | `query="SYN-MZ-00001"` | the line, or up to 20 candidates |
| `get_trial` | `query="SYN-TR-0037"` | values, verdict, 10 linked lines, 3 operations, flags |
| `get_line` | `query="SYN-MZ-00001"` | genomics, lab, the trials it is in with each trial's verdict, flags |
| `score_trial` | `query="SYN-TR-0001"` | verdict, 7 criteria with thresholds and brackets, reason |
| `query_trials` | `knockout="disease", only=true` | matching trials with verdict and reason |
| `baseline_check` | none | `{checked: 72, matched: 72, mismatches: []}` |

Resources: `uc4://sources` and `uc4://rule/SYNTH_V1` (criteria, thresholds, brackets, flag codes), both JSON.

## Connect OpenCode (stdio)

The repo-root [opencode.json](../opencode.json) already registers the server as `uc4`. Start OpenCode from the repo root in a shell where `UV_PROJECT_ENVIRONMENT` is set, then check:

```powershell
opencode mcp list        # expect: ✓ uc4 connected
```

Verified 2026-09-29 with OpenCode 1.18.32 and `mcp` 2.2.0 against the 8-tool server.

Do not add an `environment` block with `{env:LOCALAPPDATA}` to `opencode.json`: OpenCode substitutes the value before parsing, and the Windows backslashes make the JSON invalid.

## Connect Claude Code (stdio)

MCP clients pass only a few environment variables to the server, so give it `UV_PROJECT_ENVIRONMENT` explicitly (otherwise `uv` builds a venv inside OneDrive). Use an absolute `--project` path, since Claude Code may start in another directory:

```powershell
claude mcp add uc4 --env UV_PROJECT_ENVIRONMENT="$env:LOCALAPPDATA\uc4-mcp\.venv" -- uv run --project "C:\path\to\2026_hatchworks-hakathon\app" uc4-mcp
```

## Connect n8n (HTTP)

Start the server with `--transport http --port 8765`, then point an **MCP Client** node (HTTP streamable) at:

- `http://127.0.0.1:8765/mcp` when n8n runs on the same machine.
- `http://host.docker.internal:8765/mcp` when n8n runs in Docker. Start the server with `--host 0.0.0.0` for this: bound to 127.0.0.1 it rejects any Host header other than localhost. `0.0.0.0` exposes the server, which has no authentication, to your network, so use it only on a trusted one.

## MCP Inspector

Needs Node and the venv (any `uv run --project app …` creates it). Start the Inspector with the server's console script, from any directory:

```powershell
npx.cmd @modelcontextprotocol/inspector "$env:LOCALAPPDATA\uc4-mcp\.venv\Scripts\uc4-mcp.exe"
```

Open the `http://127.0.0.1:6274?MCP_INSPECTOR_API_TOKEN=…` URL it prints, click **Connect**, then **Tools → List Tools** (8 tools). Smoke test: `score_trial` with `SYN-TR-0037` returns HOLD, `resistant lines 30% < 50%`. In a writable session, the same setting by hand is: Transport STDIO, Command `C:\Users\<you>\AppData\Local\uc4-mcp\.venv\Scripts\uc4-mcp.exe`, no arguments, no env vars. The editable install lets the server find `get_started/*.zip` from its own files.

Do not use `mcp dev app/src/uc4_mcp/server.py`. It pre-fills `uv run --with mcp==2.2.0 mcp run app/src/uc4_mcp/server.py`, which builds a throwaway env with only `mcp` and uses a relative path, so Connect fails ("Failed to connect"). The session it opens is read-only ("Read-only session"), so the command can't be fixed in the UI either.

If Connect fails, read the end of `app/logs/uc4_mcp.log`: a new `uc4-mcp starting over stdio` line means the server started and the fault is on the Inspector side; no new line means the launch failed.

## Question agent

`uc4-ask` answers plain-English questions from the 8 tools above, citing a row
(`[file#row_id]`) or a whole tool result (`[tool:query_trials]`) for every number. An
ambiguous ID gets a "which one?" list; an answer with no citation, numbers or verdict/colour
words that are not in the cited results is rewritten once and otherwise marked unverified.
Settings: `app/agent.toml` (model, sampling, round limits; committed). Secrets come from the
environment only.

Portkey setup: `PORTKEY_API_KEY` is required. The model is a Model Catalog id
`@<provider-slug>/<model>`, set as `model` in `agent.toml` or in `UC4_LLM_MODEL`.
`PORTKEY_VIRTUAL_KEY`, `PORTKEY_CONFIG` and `PORTKEY_PROVIDER` are optional older routes;
`UC4_LLM_PROVIDER_KEY` is only for routes that need a raw provider key. If the model rejects
`temperature` or `max_tokens` (some reasoning models), delete that key from `agent.toml`.

```powershell
$env:PORTKEY_API_KEY = "<key>"                    # required
$env:UC4_LLM_MODEL = "@<provider-slug>/<model>"   # or model in agent.toml
# optional: UC4_LLM_BASE_URL (company gateway), PORTKEY_VIRTUAL_KEY / PORTKEY_CONFIG
uv run --project app uc4-ask ping
uv run --project app uc4-ask ask "Why is SYN-TR-0037 amber?"
uv run --project app uc4-ask chat
uv run --project app uc4-ask eval    # the supported questions; report -> app/evals/results/
```

`chat` quits on an empty line, `quit`, `exit` or Ctrl+Z/EOF. Exit codes: 0 answered or
clarify, 1 unverified or error, 2 configuration error.

Each question is logged as one JSON line (question, tools, status, tokens, seconds) in
`app/logs/uc4_agent.log`; tool calls also go to `app/logs/uc4_mcp.log`.

### HTTP (Phase 3 screen, n8n)

```powershell
uv run --project app uc4-ask serve            # http://127.0.0.1:8766
```

`POST /ask` with `{"question": "...", "history": [{"role": "user"|"assistant", "content": "..."}]}`
returns the answer JSON (`status`: answered | clarify | unverified | error; `text`; `model`;
`citations`; `ungrounded`; `problems`; `candidates`; `tool_calls` with each envelope;
`usage`; `disclaimer`), always HTTP 200. 503 means the model is not configured;
`GET /health` says why. CORS allows `localhost` pages only. For n8n in Docker use
`--host 0.0.0.0`.

> **Warning:** there is no authentication. Use `--host 0.0.0.0` on a trusted network only:
> anyone who can reach the port can query the data and spend the Portkey quota.

## Breeder screen

```powershell
uv run --project app uc4-ask serve            # then open http://127.0.0.1:8766/
```

The server loads the zip first, so a missing archive exits with code 1 and the message from
the [Data](#data) section; if `get_started/` holds more than one matching archive, set
`UC4_ZIP` to the one to use (see [Environment](#environment)). It then prints the screen URL
and the decision log path.

The screen lists the trials with their verdict and reason. Selecting a trial shows the seven
criteria with thresholds and brackets, the linked lines, the flags, and the recorded
decisions, and lets the breeder accept or override the recommendation and ask the agent a
question about the trial.

Decisions are appended to `app/data/decisions.jsonl` (git-ignored); set `UC4_DECISION_LOG` to
move it. The log is append-only, and each line copies the recommendation shown at the time, so
a later rule change never rewrites what the breeder saw. `user` is a demo alias: there is no
authentication. Only `/ask` needs the Portkey variables; the rest of the screen works
without them.

| Route | Purpose |
| --- | --- |
| `GET /` | the breeder screen; `/static/*` holds its files |
| `GET /trials` | all trials with verdict and reason |
| `GET /trials/{query}` | one trial: criteria, linked lines, flags |
| `GET /lines/{query}` | one line: genomics, lab, its trials |
| `POST /decisions` | append a decision to the log |
| `GET /decisions?trial=` | the decisions recorded for a trial |
| `POST /ask` | the question agent (needs Portkey) |
| `GET /health` | status, and why the model is not configured |
