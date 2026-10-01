# Candidate API and MCP reference

| Interface | Purpose |
| --- | --- |
| `GET /candidates` | AND filters, sorted rows, total, total_available, offset/limit and next_offset |
| `GET /candidates.csv` | All matching rows, including snapshot and revision identifiers |
| `GET /candidates/{query}` | Candidate recommendation, source rows, comparisons and histories |
| `POST /decisions` | Explicit action with actor, reason, context, recommendation_id, previous_decision_id and request_id |
| `GET /decisions` | Preserved decision events, optionally filtered by candidate query |
| `GET /enrichment` | Enrichment events, optionally filtered by candidate query |
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

See [setup and breeder workflow](README.md) and [runtime architecture](ARCHITECTURE.md).
