# Candidate API and MCP reference

| Interface | Purpose |
| --- | --- |
| `GET /health` | Readiness, candidate count, snapshot/revision identity and configured model (null when unavailable); no live gateway probe |
| `GET /rule` | Read-only provisional policy, gates, knockouts, warnings and rounding behavior |
| `GET /candidates` | AND filters, sorted rows, total, total_available, offset/limit, next_offset, dataset-wide overview, processing details and decision_generation |
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
| `POST /filters/interpret` | Read-only typed filter proposal for the displayed snapshot/revision |
| `POST /filters/validate` | Validate an edited proposal and count matching candidates before Apply |

MCP tools: `list_sources`, `find_candidate`, `get_candidate`, `score_candidate`, `query_candidates`, `get_candidate_rule`, and `baseline_check`. The old `score_trial` and `query_trials` names return explicit migration messages. Resources: `uc4://sources` and `uc4://candidate-rule`. All MCP tools are read-only. `/health` on the MCP port reports source and revision identity; the breeder screen runs on its separate port.

Filter ranges are JSON objects, for example `{"YIELD_VS_CHECK_PCT":{"min":103},"N_TRIALS_USED":{"min":2}}`. API and MCP responses identify pagination explicitly. Invalid filters return an error rather than being silently ignored.

HTTP list and CSV routes accept `review_state=all|reviewed|undecided|latest_override`
(default `all`), independently of the existing `decision` action filter. Filters
combine with AND; invalid review states return 422. Reviewed means a saved latest
event exists, and latest_override uses that event's persisted override flag against
its saved system recommendation. Candidates are counted once; check varieties are excluded.

Every list page includes `overview` with `total`, `rag` (GREEN/AMBER/RED counts),
`reviewed`, `undecided`, and `latest_override`. These totals cover the entire current
dataset regardless of filters. `total` outside overview is the matching count.
Snapshot, revision, ordered latest decisions, counts and rows are captured as one
read view. `decision_generation` is the captured maximum decision row ID (0 before
any decisions); it can change without an evidence revision. Pagination consumers
must compare snapshot, revision and generation across pages before combining them.
The dashboard restarts once on mismatch, then requests an explicit refresh.

CSV exports all matching rows from its own current consistent read view using the
same filters; its existing columns are unchanged. MCP and the typed-filter schema
retain their existing filter interfaces. Typed Reviewed/override queue requests
return clarification directing the user to manual Review state controls; typed
Undecided requests remain supported.

See [setup and breeder workflow](README.md), [process guide](PROCESS.md) and [runtime architecture](ARCHITECTURE.md). The running dashboard also serves generated OpenAPI at `/openapi.json` and interactive route schemas at `/docs`.

## Decision writes and saved context

`POST /decisions` requires `query`, `action`, `actor`, `reason`, `context`,
`recommendation_id` and `request_id`, with optional `previous_decision_id`.
Actions are ADVANCE, HOLD or DISCARD. Context requires nonblank `location` and
`source_channel`; optional trial/site text describes review context rather than
creating an agronomic source relationship. Names are self-declared.

Successful recording returns 201 with the saved event and its recommendation.
Retry the same payload and request ID if a response was lost. A changed payload
under that ID, stale recommendation or changed latest-decision ID returns 409;
invalid content returns 422. A deliberate later event uses a fresh request ID and
the latest decision ID. The browser's Review, saved receipt and Record another
decision states use these existing contracts; they add no server write route.


## Core breeder usability additions

`GET /rule` returns the current provisional policy: existing descriptive criteria,
structured `gates`, `knockouts`, `warnings` (field/test/threshold/unit),
`context_only`, missing-data behavior and rounding policy. It is read-only.

Candidate detail adds `policy` and `assessments`. Each assessment retains the
existing criterion fields and adds `unit`, signed `margin` (observed minus
threshold, null for missing/categorical values) and `status`. Missing evidence
is Unknown; display rounding never changes scoring. Existing recommendation
and decision payloads remain compatible; there is no database migration.

`POST /ask` accepts optional `candidate` (ID/GUID or uniquely resolving fragment)
and `revision_id` alongside `question` and `history`. Invalid revisions return
404; ambiguous candidates return 409. Omitted revision captures the active
revision at request start. All evidence tools use that immutable revision for
the duration of the request, even if another request activates an enrichment.

Answers retain existing fields and add `context` with snapshot ID, revision ID
and selected candidate ID (null for dataset-wide requests). Selected context
resolves phrases such as "this candidate"; explicitly named candidates take
precedence. Context labels describe the request, not a guarantee that every
answer concerns only that candidate. Inspect `tool_calls` and `citations` for
the actual evidence. The browser opens citation results from that same response.

When a configured model fails during orchestration, the route can return HTTP
200 with `status: "error"`; this is a failed Ask, not a successful explanation.
Missing configuration returns 503. Clients must inspect the answer status.
The dashboard shows an unavailable message rather than an answer dialog for an
error, retains the question and allows a later retry. It accepts one Ask request
at a time while keeping manual evidence review available.
## Typed filter proposals

`POST /filters/interpret` accepts `text` (1–2000 characters), `snapshot_id` and
`revision_id` from the displayed `/candidates` response. It returns `status`
(`ready` or `clarification`), `filters` (null for clarification), `clarification`
and the snapshot/revision context. No list state or history is written.

`POST /filters/validate` accepts the same context plus edited `filters`; it returns
validated filters, matching `total`, and context. The browser applies the returned
filters only after an explicit Apply click, using existing `/candidates` and CSV
queries. It replaces filters and preserves sorting.

The proposal fields are `search`, `rag`, `decision`, `marker`, `excluded`,
`include_missing`, and `ranges`. Empty category/search strings mean all;
`excluded` is null/all, true/at least one excluded trial, or false/zero.
`include_missing` defaults false. Each range has inclusive `min` and/or `max`
and a required `unit`. Supported units: YIELD_VS_CHECK_PCT, MOISTURE_PCT_MEAN,
GERMINATION_PCT and COLD_TEST_PCT use `%`; DISEASE_SCORE_MEAN uses `score`;
FUMONISIN_PPM uses `ppm`; N_TRIALS_USED uses `trials`; GENOMIC_BREEDING_VALUE uses
`index`. The browser strips unit metadata when making existing list queries.

Example filter proposal: `{"rag":"AMBER","ranges":{"N_TRIALS_USED":{"min":3,"unit":"trials"}}}`.
Unspecified filters use their empty defaults. Unknown fields, wrong units,
nonfinite/reversed bounds, fractional/negative trial counts and unknown candidate
searches are rejected. Identifier fragments retain the manual search semantics.
Stale context returns 409; invalid inputs return 422; unavailable or malformed
model responses return 503. No new MCP tools, history tables or write adapters
are introduced.

## Guided enrichment preview

`GET /enrichment/{item_id}/preview` retains its existing fields and adds
`snapshot_id` and `source_change`. The latter contains `kind`, `material_id`,
`table`, `row_id`, `field`, `trait_code`, `original`, `current`, `proposed`, `unit`,
`source`, `observed_at`, `reason`, and `supersedes`. Original means the immutable
archive value; current includes the active correction. Notes accumulate and have
no previous scalar value. The source value is distinct from aggregated candidate
metrics in `affected`. Preview is read-only and requires an approved addition.

Draft validation rejects blank author/source/observation date, reasons shorter
than five trimmed characters, booleans/nonfinite numeric measurements, wrong
units and unrelated source rows. Genomic index and delay units may be omitted
by existing callers; supplied units must be `index` or `days`, respectively.
Lab/field measurement units must match the trait dictionary. Replacement requires
`supersedes` to identify the current active addition for the same table/row/field;
notes do not supersede. HTTP values use strict string/number types.

Review and activation endpoints and storage schemas are unchanged. Activation
still requires the exact preview `base_revision`, actor and reason; stale
activation returns 409. The browser provides separate confirmation and reason
entry for review and activation. No MCP write tools or language adapters are added.

Changed-candidate preview entries additionally include `before_reason`,
`after_reason`, `before_warnings`, and `after_warnings` so the interface can show
recommendation explanations and caveats alongside each metric comparison.


## Processing disclosure

Every `GET /candidates` page adds `processing` from the same pinned store as its
counts and rows. It contains `snapshot_id`, `revision_id`, `candidate_count`,
`check_variety_count` (distinct material GUIDs with trial membership CHECK role),
`active_corrections`, `contextual_additions`, and `sources`. Each source family has
`tables` with the table key, original archive `source_file`, and `supplied_rows`.
Counts use original tables; corrections never increase supplied row counts.
Superseded field updates count once; contextual notes count individually.

`measurement` is null when timing is missing or invalid. Otherwise it contains
`elapsed_seconds`, UTC `measured_at`, `scope` =
`reconstruction_scoring_recommendation_creation`, `runtime` = `local_revision_build`,
and the matching snapshot/revision. The monotonic interval begins immediately
before reconstruction and ends after scoring and recommendation record creation.
It excludes archive reading, validation, overlay preparation, persistence, cache
retrieval, browser rendering and Ask. A cache hit retains the measurement.
Activation and rollback publish their built store only after database commit.

Diagnostics remain in memory, outside recommendation payloads and identity.
Restart or cache eviction leads to a new measurement on an actual rebuild; original
historical build time is not recovered. Historical candidate responses have no
processing object. Refresh retrieves the current view and does not imply ingestion.


## Boundary review and captured criterion evidence

List and CSV routes accept optional `boundary` JSON:
`{"field":"MOISTURE_PCT_MEAN","kind":"green_gate","tolerance":1,"side":"both"}`.
The shared query validation also applies to MCP `query_candidates`, which accepts
`boundary`, `sort` and `descending` as structured arguments without a model call.
Allowed kinds are `green_gate` and `red_knockout`; sides are `both`, `meets`, `fails`.
Only numeric fields with that policy boundary are supported. Exactly these four keys
are required; booleans, nonfinite/negative tolerances, unsupported combinations and
fractional `N_TRIALS_USED` tolerances are rejected. Malformed HTTP JSON returns 422.
An omitted boundary disables proximity. `abs(observed-threshold) <= tolerance` uses
unrounded measurements; percentage tolerances are percentage points. Missing values
never match proximity, including with `include_missing=true`; other filters combine
with AND. Side follows the exact comparator (`DISEASE_SCORE_MEAN > 6` is false at 6).
`sort=boundary_distance` requires proximity. Ascending/descending orders distance
while retaining ascending material-ID ties. The scoring rule remains unchanged.

List rows, MCP summaries and detail include derived `review`: `green_counts`
(`meets`, `fails`, `unknown`, totaling seven including the marker), `gates`,
`triggered_knockout_fields`, `knockout_precedence_applies`, `no_usable_field_data`,
and `decisive_assessments`. Zero usable trials still take AMBER precedence.
Active proximity adds `review.boundary` with field/kind/tolerance/side, `test`,
threshold/unit, observed value, signed margin, distance and test outcome. CSV appends
these as `boundary_*` columns only when proximity is active; original columns stay
unchanged otherwise. Review data never enters stored recommendation payloads or IDs.

Detail `criterion_evidence` is keyed by metric, captured from the immutable store.
Each entry identifies candidate/snapshot/revision and selected field, explains its
calculation, and contains scoped source rows, matching dictionary definitions,
trial comparisons/exclusions and relevant correction history. Source rows carry
archive member, primary key, line number, revision and effective values. Corrected
fields include `original_values` and `latest_corrections` with reviewer/source
provenance; superseded history remains accessible. Field rows include explicit
irrigation-exclusion flags. Yield includes CHECK-role observations and means;
disease/moisture include only the candidate and selected trait. Usable trial counts
retain the reconstruction's distinct observed-trial semantics. Lab data has no
supplied trial relationship; genomic evidence identifies the selected field and
context-only metrics. The browser consumes this captured payload without fetching
new evidence on drill-down, with a path to complete original source evidence.

Manual proximity starts off with blank tolerance inside Advanced filters. Clear,
Reset and ordinary typed Apply remove proximity and reset boundary-distance sorting
to candidate ID. Opt-in remembered views retain valid settings and accept older
views without a boundary. Typed proximity requests produce clarification directing
users to the manual controls with no partial proposal and no model call.
