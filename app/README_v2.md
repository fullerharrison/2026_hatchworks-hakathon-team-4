> Archived v2 documentation. Use the explicit `--historical-v2` launch flag described in [current instructions](README.md); the default launch now uses candidate data.

# uc4-mcp

> **Current data notice (1 October 2026):** This app is a historical v2 demo. The SME replacement introduces candidate-level GREEN/AMBER/RED and different source schemas. [Current analysis](../analysis/uc4_eda/report.html) describes it; setting UC4_ZIP alone does not migrate this app.

UC4 v2 evidence app: read-only MCP, natural-language answers, breeder screen and explicit human decision log. See [implemented architecture](ARCHITECTURE.md) and [review/readiness](../.tasks/uc4-demo-review/task.md). Original build plan: [phase-1-mcp-data-layer.md](../.tasks/uc4-assistant/phase-1-mcp-data-layer.md).

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

Run tests from the repo root. Keep the `app/tests` path: without it pytest also collects `analysis/uc4_eda/`, whose test modules share basenames with ours. The default suite excludes browser and live-model checks; run those separately as documented below and in the review tasks.

```powershell
uv run --project app pytest -q app/tests
```

## Data

The tests and server default to the exact **v2** filename `get_started/RE__Hatchworks_Hackathon_-_4th_Use_Case.zip`, which is git-ignored. Obtain it from the supplied hackathon materials or an authorized teammate and copy it there after cloning. Other archives in the folder do not change the default. `UC4_ZIP` overrides this path explicitly; it does not migrate the app to the replacement candidate schema or historical v3. Incompatible schemas are rejected. The [current candidate analysis](../analysis/uc4_eda/report.html) is not the runtime data source; [v3](../analysis/uc4_eda/v3/report_v3.html) is superseded historical analysis.

## Run

From the repo root:

```powershell
uv run --project app uc4-mcp                                   # stdio (what MCP clients launch)
uv run --project app uc4-mcp --transport http --port 8765      # streamable HTTP at http://127.0.0.1:8765/mcp
```

- Both entry points load the git-ignored repo-root `.env` at startup (a shell export wins);
  `uc4-mcp` has no required variables, `uc4-ask` needs `PORTKEY_API_KEY`.
- The server loads the zip at startup; a missing zip exits with code 1 and a message naming `UC4_ZIP`.
- Logs go to `app/logs/uc4_mcp.log`, never stdout (stdout carries the stdio protocol).
- `--host 0.0.0.0` is only for clients in Docker (see [n8n](#connect-n8n-http)).
- HTTP serves two routes: the MCP endpoint at `/mcp` and `GET /health` for probes, returning
  `{"status", "server", "trials", "sources", "extract_date"}` (500 with `{"status": "error"}` if
  the store cannot load). `/` is 404 by design; there is no screen on this port — the breeder
  screen is `uc4-ask serve` on 8766.

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
ambiguous ID gets a "which one?" list; an answer with no citation, quantities or verdict/colour
words unsupported by cited results is rewritten once and otherwise marked unverified.
Numbers copied from a question do not count as factual evidence. These checks do not
prove semantic attribution or completeness; the review also checks answers against source rows.
Settings: `app/agent.toml` (model, sampling, round limits; committed). Secrets come from the
environment only.

Portkey setup: `PORTKEY_API_KEY` is required. The model is a Model Catalog id
`@<provider-slug>/<model>`, set as `model` in `agent.toml` or in `UC4_LLM_MODEL`.
`PORTKEY_VIRTUAL_KEY`, `PORTKEY_CONFIG` and `PORTKEY_PROVIDER` are optional older routes;
`UC4_LLM_PROVIDER_KEY` is only for routes that need a raw provider key. If the model rejects
`temperature` or `max_tokens` (some reasoning models), delete that key from `agent.toml`.

Keep the variables in the git-ignored repo-root `.env`; `uc4-ask` loads it at startup, so no
`--env-file` is needed (a shell export wins over the file):

```
PORTKEY_API_KEY=<key>                                   # required
UC4_LLM_MODEL=@<provider-slug>/<model>                   # or model in agent.toml
UC4_LLM_BASE_URL=https://portkey.syngenta.com/v1         # optional (company gateway)
```

If `PORTKEY_API_KEY` is missing, `uc4-ask` prints the variable name and the `.env` path and
exits 2 before running; the model is validated the same way (exit 2, or HTTP 503 per request
on `serve`).

```powershell
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
the [Data](#data) section; other archives in `get_started/` do not affect the exact v2 default. To use a copy
elsewhere, set `UC4_ZIP` explicitly (see [Data](#data)). It then prints the screen URL
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

### Browser input checks and demo capture

The opt-in browser suite uses trusted Chrome mouse and keyboard input, starts its own
server without model credentials, and writes decisions to a temporary log:

```powershell
uv run --project app --group browser pytest -q -m browser app/tests/test_browser.py
```

It needs installed Google Chrome (otherwise the tests skip). The default suite excludes
both `browser` and `live`; its dependencies and token usage are unchanged.

To retake the six deck PNGs and the walkthrough GIF, start a separate rehearsal server:

```powershell
$env:UC4_DECISION_LOG = Join-Path "$env:TEMP" ("uc4-capture-" + [guid]::NewGuid().ToString() + ".jsonl")
uv run --project app --env-file .env uc4-ask serve
```

In another terminal, from the repo root:

```powershell
uv run team/screenshots/capture.py
```

[capture.py](../team/screenshots/capture.py) installs Playwright and Pillow in an isolated
uv script environment, not the app environment. It uses installed Chrome headlessly;
outputs default to [team/screenshots](../team/screenshots/). Options: `--base URL` for
another port, `--out DIR` for another destination, `--no-gif` for PNGs only.
The PNGs use 1440x900 at 2x; the GIF has eight 1280x800 scenes at two seconds each and is
resized to 1024px if needed to stay below 8 MB.

A full capture makes two live Ask requests and records two PASS overrides against HOLD
(one of each with `--no-gif`), so set `UC4_DECISION_LOG` on the server before starting it.
Without a configured model the script captures and reports the unavailable warning,
which is not live-answer evidence even though the PNG filename remains the same.
Results: [walkthrough](../team/phase3_walkthrough.md),
[GIF](../team/screenshots/phase3_walkthrough.gif).

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

## Current demo review and videos

Follow the [review task index](../.tasks/uc4-demo-review/task.md) for current evidence, source limitations and readiness. The [implemented architecture](ARCHITECTURE.md) describes the actual stack and data flow. The [two narrated recordings](../.tasks/uc4-demo-review/evidence/20260930T225928Z-bbd0c0b/videos/index.md) supplement the required live event presentation.

Breeder history uses local JSONL. The entered actor is an unauthenticated demo alias; append-only API behavior does not make the file tamper-proof. Technical choices are recorded separately in dated review decisions. Run rehearsals with a fresh `UC4_DECISION_LOG`; do not overwrite the normal history.
