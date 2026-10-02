# UC4 candidate breeder assistant

The dashboard combines field, operation, lab and genomic evidence for breeder review. The supplied archive contains **150 candidates, two check varieties and eight source tables**. Its baseline is **32 GREEN, 53 AMBER and 65 RED**. System recommendations use provisional deterministic rules; breeders independently record ADVANCE, HOLD or DISCARD.

The data are a maize-like synthetic demonstration for the vegetable-seed challenge. Crop thresholds still require biological validation.

## Start the dashboard

On Windows, double-click **Start-Dashboard.cmd** in the repository or extracted package root. Install uv first if needed; see [team setup](../SHARE.md). The launcher installs locked dependencies, starts the server and opens the browser after startup.

From that root folder:

```powershell
uv run --locked --project app uc4-ask serve --open-browser
```

Use [http://127.0.0.1:8766/](http://127.0.0.1:8766/). Keep the terminal open; Ctrl+C stops the server. If the port is occupied, stop the previous server or add `--port 8767`. In a second terminal, check readiness:

```powershell
Invoke-RestMethod http://127.0.0.1:8766/health
```

The supplied baseline returns `status: ok`, `candidates: 150`, a snapshot hash and a revision ID. The `model` field reports configuration, not a successful gateway request. Browsing, manual filters, CSV export, decisions and enrichment work without model credentials.

## Visual guidance

Both screens use the Syngenta Vegetables palette: Plant Green headings, Air Blue actions and selected controls, and light blue information surfaces. Existing GREEN, AMBER and RED recommendation, warning and error colors retain their meanings.

A completed, grounded Ask response shows a blue **Answered** label alongside the submitted question and its captured context. On mobile, the closed Ask launcher also indicates an available answered response. Submitting another question clears completion immediately. Clarification, unverified, unavailable and failed responses have their own labels and never receive the Answered cue. Answer completion is separate from a breeder decision or a GREEN recommendation.

## Question agent

Ask and typed filter interpretation use the configured Portkey gateway. Each user supplies their own token and accessible model route:

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Set `PORTKEY_API_KEY` and `UC4_LLM_MODEL`; leave optional routing fields blank unless required. Restart after editing. Both application commands load the root `.env`, and existing shell variables take precedence. Keep credentials private.

```powershell
uv run --locked --project app uc4-ask ping
uv run --locked --project app uc4-ask ask "Why is SYN-MZ-00001 AMBER? Cite the evidence."
```

Ask stays above the desktop workspace and opens from a persistent launcher on mobile. It captures the selected candidate and evidence revision, or dataset-wide scope. **View answer** opens a short answer, **More detail** expands it, and citations open the evidence captured with that response. Back returns to the answer. Request context and verification warnings remain visible. Ask accepts one request at a time; the question remains editable and you can review evidence while waiting. A model/gateway failure shows a plain-language unavailable message, keeps your question and re-enables Ask for a later retry. A failed request is not presented as an answer.

## Breeder workflow

For a separate practice session, double-click **Start-Breeder-Review.cmd** in the main folder. Follow the [short breeder review guide](HUMAN_REVIEW.md); the launcher opens your browser and keeps practice decisions separate from the team's records.

1. Use the dataset-wide overview to filter by system RAG or review queue. Reviewed means a saved decision exists; Latest decision is an override is a subset of Reviewed and uses the latest event's saved recommendation. Overview counts stay dataset-wide while the list shows the matching count. RAG and review controls change only their respective filter; Reset clears the view. Open **Advanced filters and preferences** for breeder action, marker, exclusions, sorting, inclusive trait ranges and typed requests. All filters combine with AND. Missing values enter range results only when selected. Download CSV exports every matching candidate. **Refresh** reloads counts, results and selected-candidate history; loading failures mark retained results as potentially stale.
2. Select a candidate. Use **Evidence**, **Decision**, **History** and **Enrichment** tabs. Field help is available by hover, keyboard focus or tap. Open **Provisional rules** and criterion evidence to inspect thresholds, signed margins, original source rows and trial comparisons. Displayed measurements use two decimals; calculations retain full precision.
3. In **Decision**, enter your self-declared name, choice and reason. Check the editable review context, initially **Unknown / Breeder review**. Choose **Review decision**, inspect the proposed event and evidence revision, then **Record decision**. **Edit** returns to the form without saving.
4. The saved receipt replaces the entry form. A summary above all detail tabs shows the latest saved breeder action, override, name, time, reason and saved system recommendation. Long reasons expand on demand. List rows identify latest overrides. **View saved recommendation** opens the original recommendation and evidence; an earlier-evidence notice appears when the current recommendation differs. History identifies **Recorded by** and retains every event. **Record another decision** explicitly starts a later entry and shows the previous decision during review. If a response is lost, retry the same confirmation; it retains its request ID. A confirmed save remains visible in the summary and History if refresh fails; use **Retry history refresh** to recover without saving again. A changed recommendation or latest decision requires fresh review.
5. For new context or a correction, use the guided **Enrichment** form: save draft, submit, approve or reject with a review reason, preview impact, then explicitly activate with a separate name and reason. Activation creates an evidence revision; earlier decisions retain their original evidence.

See [process guide](PROCESS.md) for enrichment details, persistence and maintainer checks.

### Saved preferences

Open **Advanced filters and preferences**, then **Preferences**, and choose **Save preferences** to store your name and default location/meeting and source channel. Separately opt into **Remember filters and selected candidate** to restore filters (including Review state), ranges, sorting and selection. Preferences are local to that browser and app address, across restarts; names are unverified. Older saved views without Review state restore with All review states.

**Reset** clears the current and saved view while retaining saved identity/context. **Forget my preferences** removes both, clears the view and turns remembering off. Use it when finished on a shared browser. Recorded history remains intact. A different source dataset clears the saved view with a notice, and restored candidates load current evidence. Storage errors do not block manual review.

Decision choices/reasons, trial/site context, evidence drafts, filter requests and AI previews are never saved as preferences. Unsaved decision input is not restored after reload.

### Typed filters

In **Find candidates**, enter a request such as "Show AMBER candidates with at least three usable trials" and choose **Interpret**. Review and optionally edit the proposal, then choose **Apply filters**. Apply replaces filters and retains sorting, selection and unsaved decision/evidence drafts; **Cancel** leaves the view unchanged.

Typed requests are inside **Advanced filters and preferences**. Reviewed and latest-override queues require manual controls; these typed requests return guidance rather than a partial proposal. Typed Undecided requests remain supported. Applying a supported proposal resets Review state to All review states, consistently replacing the current filters.

The model receives the request and filter definitions and has no tools. Unsupported or ambiguous conditions require a revised request. Strict greater/less comparisons, OR, category negation and unit conversions are outside the supported slice. Manual filters remain available after model errors. Editing the request, changing manual filters, Reset or an observed evidence revision change invalidates the pending proposal; the server also rejects stale context.

## Storage and configuration

| Setting | Default / purpose |
| --- | --- |
| `UC4_ZIP` | `get_started/candidate_recommendations_synthetic.zip`; a compatible source archive |
| `UC4_CANDIDATE_DB` | `app/data/candidate_history.sqlite3`; decisions, enrichment, recommendations and revisions |
| `UC4_DECISION_LOG` | `app/data/decisions.jsonl`; legacy import input, or historical-mode decision log |
| `app/agent.toml` | Gateway defaults and question-agent limits; environment overrides model/base URL |

Source copies live in `snapshots/` beside the SQLite database and are named by SHA-256. Back up the database and snapshots together while the server is stopped. Restarting with another compatible archive selects its baseline and preserves earlier revisions and decisions. See [backup and restore](PROCESS.md#backup-and-restore).

## Interfaces

The dashboard/API uses port 8766. Start a separate read-only MCP interface for clients:

```powershell
uv run --locked --project app uc4-mcp
uv run --locked --project app uc4-mcp --transport http --port 8765
```

MCP exposes candidate lookup, policy, scoring and source evidence. Decisions and enrichment require explicit HTTP writes. See [API reference](API.md) and [runtime architecture](ARCHITECTURE.md).

## Verification

Run from the repository root:

```powershell
uv run --locked --project app pytest -q app/tests -p no:cacheprovider --basetemp .test-tmp-local-offline
uv run --locked --project app --group browser python -m playwright install chromium
uv run --locked --project app --group browser pytest -q -m browser app/tests/test_candidate_browser.py -p no:cacheprovider --basetemp .test-tmp-local-browser
uv run --locked --project app pytest -q -s -m live app/tests/test_filter_intent_live.py -p no:cacheprovider --basetemp .test-tmp-local-live
```

Use a fresh writable basetemp directory for each run. The default suite excludes browser and live tests; the full suite also requires the original v2 archive for legacy regressions. The handoff ZIP contains only the current source archive. In that package, use the candidate checks described in [developer verification](PROCESS.md#developer-verification).

Candidate browser tests use matching Playwright Chromium, a fresh browser context per test, isolated history and an independent loopback server. Set `UC4_BROWSER_CHANNEL=chrome` to check installed Chrome separately. Live tests use the configured gateway and spend model tokens; skipped tests do not establish live readiness.

The repository and team ZIP provide `scripts/rehearse.py` for isolated offline/live walkthroughs. See [human review](HUMAN_REVIEW.md) and [release notes](RELEASE_NOTES.md) for review instructions and readiness limits.

## Historical v2 and limitations

Historical trial mode requires the original v2 source archive, available only in the full repository/source delivery:

```powershell
uv run --locked --project app uc4-ask serve --historical-v2 --port 8767
uv run --locked --project app uc4-mcp --historical-v2
```

If `UC4_ZIP` is set, point it at `get_started/RE__Hatchworks_Hackathon_-_4th_Use_Case.zip` for that process. Legacy JSONL imports are idempotent, preserve original payloads and do not turn trial decisions into candidate decisions. Frozen historical regression oracles and provenance live in `app/tests/fixtures/historical_v2/`.

No-data candidates remain AMBER. Moisture above 25% and germination below 85% are warnings; GREEN requires its separate gates. Genomic breeding value and cold-test vigour are contextual. Lab evidence remains material-level; trial geography and pedigree/stage are unknown unless separately supported. Names and reviews are self-declared; an author may review their own addition in this local demo. Voice, natural-language writes and editable scoring policy remain deferred. Automated checks do not establish breeder comprehension, team presentation readiness or biological validity.

**Processing details** beneath the overview controls opens a compact source summary, supplied table counts, candidate/check totals, active corrections and contextual additions. Its measured local reconstruction and recommendation-creation duration excludes archive reading and validation. Refresh reuses a cached build measurement; restart or eviction measures an actual rebuild. Failed refreshes mark retained information stale. See [the API scope](API.md#processing-disclosure).


Near a rule boundary in Advanced filters focuses review on an explicit numeric
GREEN gate or RED knockout tolerance. Enter the tolerance (percentage points for
percent metrics), choose a side and Apply. Distance sorting, a removable chip and
CSV boundary context follow the same full-precision eligibility as the list.
Candidate Evidence leads with decisive assessments and one-action criterion sources;
all criteria and context metrics remain available in a disclosure. Criterion dialogs
retain their captured candidate/revision and show effective/original corrections,
trial exclusions and calculation lineage. These review aids preserve the provisional
policy, saved recommendations and decision drafts. Typed proximity requests direct
you to the manual controls; ordinary typed Apply replaces proximity as well.
