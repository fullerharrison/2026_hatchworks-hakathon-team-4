# UC4 candidate breeder assistant

The default app now uses `get_started/candidate_recommendations_synthetic.zip`: 150 candidate recommendations, two check varieties and eight source tables. The synthetic baseline is **32 GREEN, 53 AMBER and 65 RED**. Scoring is provisional; the breeder records ADVANCE, HOLD or DISCARD.

## Run

From the repository root, with Python 3.12+ and uv:

```powershell
uv run --project app uc4-ask serve
```

Keep that terminal open: the command runs continuously while serving the dashboard. Open
[the breeder dashboard](http://127.0.0.1:8766/) in your browser using **http**, or run this in a second PowerShell window:

```powershell
Start-Process 'http://127.0.0.1:8766/'
```

The terminal reports `Application startup complete` and logs incoming requests. To check connectivity from a second terminal, run `Invoke-RestMethod http://127.0.0.1:8766/health`; a running candidate app returns `status: ok` and `candidates: 150` for the supplied baseline. Press Ctrl+C in the server terminal to stop it.

For MCP clients, use these separate commands:

```powershell
uv run --project app uc4-mcp
uv run --project app uc4-mcp --transport http --port 8765
```

The screen, filtering, evidence, decisions and enrichment work without a model key. Ask and the terminal question commands use the existing Portkey configuration (`PORTKEY_API_KEY` and `app/agent.toml`). Both commands load the repository `.env`; existing shell settings win.

For each new user, copy the root `.env.example` to `.env`, fill in their own
`PORTKEY_API_KEY` and an accessible `UC4_LLM_MODEL` route, then restart the server.
Leave optional fields blank unless required by their Portkey configuration. Never
share the completed `.env`; see [group setup instructions](../SHARE.md).

`UC4_ZIP` selects a compatible candidate archive. `UC4_CANDIDATE_DB` selects the SQLite history file, defaulting to `app/data/candidate_history.sqlite3`. Source archives are copied under the database directory's `snapshots/`, named by SHA-256. Keep the database and snapshot directory together when backing up or moving the app. Configuring a different compatible archive selects its baseline on restart and preserves earlier revisions and decisions.

## Breeder workflow

- Start with the entire candidate list. Combine RAG, identifier, marker, breeder decision, excluded-trial and trait-range filters. Ranges use AND; missing values are included only when selected. Download CSV exports every matching result.
- Select a candidate to inspect criteria, raw source rows, calculated trial comparisons, exclusions, lab/genomic evidence and previous decisions. Calculation precision is retained in the evidence.
- Record a choice with name, reason, location or meeting, and source channel. Enter `unknown` when location is unavailable. Names are self-declared and unverified. A choice captures the exact recommendation and evidence revision shown; stale choices are rejected for refresh.
- Add notes or metadata, or propose a measurement/operation correction by source row. Supply observation time, source and rationale. Submit the draft, approve or reject it, then preview all changed measurements and recommendations before activation. A reviewer may be the author in this local demo.
- Source inconsistencies introduced by a correction are displayed in the preview and candidate evidence. For an actual-date correction, enter `unknown` to explicitly clear the date. Review records preserve each submission, approval/rejection and activation.
- Activate an approved change to create a new evidence/recommendation revision. Changes to check observations can affect several candidates. Earlier choices remain tied to their original recommendation. A further correction must explicitly supersede the prior correction; notes can accumulate.

No-data candidates stay AMBER. Moisture >25% and germination <85% are warnings, not independent RED knockouts. Genomic breeding value and cold-test vigour are contextual. Pedigree, stage and location are unknown unless separately enriched. The data remain a maize-like synthetic demonstration for the vegetable-seed challenge.

## Interfaces

| Interface | Purpose |
| --- | --- |
| `GET /candidates` | AND filters, sorted rows, total, total_available, offset/limit and next_offset |
| `GET /candidates.csv` | All matching rows, including snapshot and revision identifiers |
| `GET /candidates/{query}` | Candidate recommendation, source rows, comparisons and histories |
| `POST /decisions` | Explicit action with actor, reason, context, recommendation_id, previous_decision_id and request_id |
| `GET /decisions` | Preserved decision events, optionally filtered by candidate query |
| `POST /enrichment` | Create a contextual or correction draft |
| `POST /enrichment/{id}/review` | Submit, approve or reject with named actor and reason |
| `GET /enrichment/{id}/preview` | All affected candidates and before/after measurements |
| `POST /enrichment/{id}/activate` | Activate against the previewed base_revision |
| `GET /revisions` | Evidence revision history |
| `GET /revisions/{id}/candidates/{query}` | Read a candidate in an earlier revision |
| `POST /revisions/rollback` | Create a new revision copying an earlier revision of the configured archive |
| `GET /historical-decisions` | Original imported v2 JSONL payloads |
| `POST /ask` | Grounded candidate questions; 503 when no model is configured |

MCP tools: `list_sources`, `find_candidate`, `get_candidate`, `score_candidate`, `query_candidates`, `get_candidate_rule`, and `baseline_check`. The old `score_trial` and `query_trials` names return explicit migration messages. Resources: `uc4://sources` and `uc4://candidate-rule`. All MCP tools are read-only. `/health` on the MCP port reports source and revision identity; the breeder screen runs on its separate port.

Filter ranges are JSON objects, for example `{"YIELD_VS_CHECK_PCT":{"min":103},"N_TRIALS_USED":{"min":2}}`. API and MCP responses identify pagination explicitly. Invalid filters return an error rather than being silently ignored.

## Historical v2

```powershell
uv run --project app uc4-ask serve --historical-v2 --port 8767
uv run --project app uc4-mcp --historical-v2
```

Historical mode requires the original v2 archive. If `UC4_ZIP` is set, point it at `get_started/RE__Hatchworks_Hackathon_-_4th_Use_Case.zip` for that process. Original source files and JSONL logs are preserved. The current app imports `UC4_DECISION_LOG` (default `app/data/decisions.jsonl`) idempotently; it does not invent missing v2 snapshot identity or turn old trial decisions into candidate decisions. [Historical instructions](README_v2.md) and [architecture](ARCHITECTURE_v2.md) describe that version.

## Verification

```powershell
uv run --project app pytest -q app/tests
uv run --project app --group browser pytest -q -m browser app/tests/test_candidate_browser.py
python -m pytest -q analysis/uc4_eda/test_candidates.py
python analysis/uc4_eda/uc4_eda.py
```

Analysis requires pandas and matplotlib. On Windows, pass a fresh writable `--basetemp` directory and `-p no:cacheprovider` if the shared pytest temporary directory is inaccessible. Browser checks use installed Chrome. Live-model evaluations are opt-in: `uc4-ask eval` uses the candidate questions; `app/evals/questions_v2.json` retains historical questions.

See [current architecture](ARCHITECTURE.md), [analysis](../analysis/uc4_eda/report.html) and [SME questions](../team/SME_ANSWERS.md). Dataset reproduction confirms implementation consistency, not biological policy approval.
