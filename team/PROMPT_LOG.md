# Shared prompt log

**Why:** judges score "AI used across the lifecycle, not just for coding" and ask teams to disclose their tools; token and spend discipline is part of the event. [Handbook pp. 3-4](../get_started/2026_Participant_Handbook.pdf#page=3) This log is the source for the "how we worked" slide.

## How to log (under 1 minute per entry)

- Add a row **the same day**, newest at the bottom. Log prompts that produced something we kept *or* taught us something, including failures.
- **Phase:** `requirements` · `stories` · `data` · `prototype` · `code` · `test` · `docs` · `demo`. Aim for entries in every phase by Thursday.
- **Prompt:** the gist in one line; link the full text or transcript if it's long.
- **Output / evidence:** a file path, commit or PR, not a description of it.
- **Kept?** `yes` / `edited` / `no`, plus why when it's `edited` or `no`. Human corrections are good evidence.
- **Cost:** tokens or $ if the tool shows it (Portkey logs do); otherwise leave it blank. Don't guess.
- Never paste secrets, API keys or non-synthetic data.

## Log

| Date | Who | Role | Phase | Tool / model | Prompt (gist) | Output / evidence | Kept? | Cost |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-09-29 | Harrison Fuller | _unassigned_ | requirements | Claude Code (Opus 5.5) | "We are choosing UC4. Create initial documentation to guide the group: split roles (data and rules, AI answers, screen and log, docs and demo) and start the shared prompt log. Be concise, evidence-based." | [ROLES.md](ROLES.md), this file | yes | |
| 2026-09-29 | Harrison Fuller | Data and rules | data | Claude Code (Opus 5.5) | "We have new information [SME email + v2 zip with the scoring file]. Make evidence-based changes to documents." Reverse-engineered the PASS/HOLD/FAIL thresholds from the 72 verdicts and rebuilt the EDA for v2 | [SME_ANSWERS.md](SME_ANSWERS.md), [rules.py](../analysis/uc4_eda/rules.py), [report](../analysis/uc4_eda/report.html), [UC4 guide](../use-cases/uc4/README.md) | yes | |
| 2026-09-29 | Harrison Fuller | Data and rules | requirements | Claude Code (Opus 5.5) | "Create evidence-based task and plans for building the application for use case 4; start with a data-unification (MCP) layer over the mock sources." Re-measured every cited number from the v2 zip before writing | [task.md](../.tasks/uc4-assistant/task.md), [phase-1-mcp-data-layer.md](../.tasks/uc4-assistant/phase-1-mcp-data-layer.md) | yes | |
| 2026-09-29 | Harrison Fuller | Data and rules | code | Claude Code (Opus 5.5); OpenCode 1.18.32 (gpt-6-luna) for the client check | "Execute Phase 1 of phase-1-mcp-data-layer.md, starting at step 0. Test first, commit after each step; stop after step 1 and report whether OpenCode connected to the ping tool." Steps 0-1: `git init`, uv package, `ping` on `MCPServer` (mcp 2.2.0), in-process smoke test, OpenCode stdio connection (`uc4_ping` → `pong`). Finding: OpenCode's `{env:…}` substitution breaks JSON on Windows paths, so the venv path is inherited from the shell instead | [server.py](../app/src/uc4_mcp/server.py), [test_smoke.py](../app/tests/test_smoke.py), [opencode.json](../opencode.json), [app/README.md](../app/README.md) | yes | |
| 2026-09-29 | Harrison Fuller | Data and rules | code | Claude Code (Opus 5.5) | "review-phase for step 2", then "adopt 1–8 into step 2 (and note 9 against step 4)" and "go ahead with step 2". Review probed the zip and found observation `ID` loads as int, a pytest basename clash with the EDA tests, silent zip/member picking, a zip-unchanged test that could not fail, and ambiguous evidence IDs (trial and recommendations share `TRIAL_GUID`). Step 2 ported the loader with provenance columns; a circular `_line_no` test was replaced by a check against the member's real line count | [plan update](../.tasks/uc4-assistant/phase-1-mcp-data-layer.md), [sources.py](../app/src/uc4_mcp/sources.py), [test_sources.py](../app/tests/test_sources.py) | yes | |
| 2026-09-29 | Harrison Fuller | Data and rules | code | Claude Code (Opus 5.5) | "Continue Phase 1: execute step 3 (Models), then step 4 (Rules and lifecycle); test first, commit after each; stop before step 5 for phase-review." Contract dataclasses, envelope, `to_json_safe`, `"<source_file>#<row_id>"` refs; SYNTH_V1 and lifecycle ported unchanged, plus `explain()` with 7 criteria, brackets and a one-line reason. Real-data tests reproduce `rule_intervals.csv` and `chronology_checks.csv` exactly; 44 → 125 tests | [models.py](../app/src/uc4_mcp/models.py), [rules.py](../app/src/uc4_mcp/rules.py), [lifecycle.py](../app/src/uc4_mcp/lifecycle.py), commits `d313702`, `baa231b` | yes | |
| 2026-09-29 | Harrison Fuller | Data and rules | code | Claude Code (Opus 5.5) | "Implement step 5 (Checks) … test first, as the plan now specifies." `lifecycle.operation_checks()` (one row per operation, NaN = not checkable) now feeds both `chronology_checks()` and the flags; `checks.py` adds 8 flag codes with a `FLAG_CODES` catalogue, fixed-template messages and cited rows, combined in a frozen `FlagIndex`. Every count equals the plan: 72, 72 (GBV 72, resistant 62), 4, 144 (48 trials), 114 (60 trials), 60, 131 (72 trials, 96 lines), 150; `chronology_checks.csv` still reproduced; 125 → 156 tests | [checks.py](../app/src/uc4_mcp/checks.py), [lifecycle.py](../app/src/uc4_mcp/lifecycle.py), [test_checks.py](../app/tests/test_checks.py), commit `a6342e4` | yes | |
| 2026-09-29 | Harrison Fuller | Data and rules | code | Claude Code (Opus 5.5) | "review phase step 6", adopted all 13 findings (query semantics, empty/broad queries, value fields, resolution order, linked aggregates, view flags), then "continue". `EvidenceStore` builds once from the tables: resolution (exact GUID → exact ID → fragment, max 20 candidates), trial and line views citing every value as an `EvidenceRow`, `query_trials` with `flag=`, `baseline` 72/72. Every tool-table count reproduced, including the no-verdict `missed` counts; 156 → 207 tests | [store.py](../app/src/uc4_mcp/store.py), [models.py](../app/src/uc4_mcp/models.py), [test_store.py](../app/tests/test_store.py), commits `5fb7457`, `6096faa`, `061a7fc` | yes | |
| 2026-09-29 | Harrison Fuller | Data and rules | code | Claude Code (Opus 5.5) | "review phase for step 7" (probed `mcp` 2.2.0 in-process), "adopt all 12", then "continue". `create_server(get_store)` with a lazily loaded store; 8 read-only tools as one-line wrappers over new store envelope methods; `uc4://sources` and `uc4://rule/SYNTH_V1` as JSON; tool descriptions carry grain, units, "SYNTH_V1 (inferred)", the flag codes and an example; file logging, nothing on stdout. Findings: in `mcp` 2.x an enum-typed filter would turn a bad value into a generic tool error, so filters stay strings; a missing zip now fails at startup. `ping` removed; 207 → 240 tests | [server.py](../app/src/uc4_mcp/server.py), [store.py](../app/src/uc4_mcp/store.py), [test_server.py](../app/tests/test_server.py), commits `6a86a0d`, `3cbe49c` | yes | |
| 2026-09-29 | Harrison Fuller | Data and rules | code | Claude Code (Opus 5.5); OpenCode 1.18.32 for the connection check | "continue" (step 8, planned in plan mode, then approved). `uc4-mcp --transport stdio|http --host --port`; subprocess tests over stdio (console script and the exact `uv run --project app uc4-mcp` client command) and over HTTP (`/mcp`, the n8n URL), each calling `baseline_check` → 72/72; README gains run commands, a tool table, and Claude Code and n8n instructions. Findings: the mcp stdio client forwards only a dozen env vars (drops `UV_PROJECT_ENVIRONMENT`), and HTTP bound to 127.0.0.1 rejects non-localhost Host headers, so n8n in Docker needs `--host 0.0.0.0`. `opencode mcp list` → `uc4 connected`; 240 → 244 tests | [server.py](../app/src/uc4_mcp/server.py), [test_stdio.py](../app/tests/test_stdio.py), [app/README.md](../app/README.md), commit `a27464f` | yes | |
| 2026-09-29 | Harrison Fuller | Data and rules | test | Claude Code (Opus 5.5); MCP Inspector | Step 9 manual check. Claude pre-ran every call over stdio to fix exact expected values (it corrected three that the handoff prompt had garbled), launched the Inspector, and wrote click-through steps; the human ran `score_trial SYN-TR-0037` (HOLD, rationale omits resistant %: the deck case), `find_trial SYN-TR-003` (10 candidates), `query_trials knockout=disease only=true` (16 FAIL), plus baseline 72/72, `get_trial`, `get_line`, the 60-trial flag query and both resources, all matching. Not run by hand: `flag=NOT_A_CODE` and the tool-list count (both covered by tests). Finding: `mcp dev` opens a read-only Inspector session whose preset `uv run --with mcp …` command cannot connect; `npx @modelcontextprotocol/inspector <venv>\Scripts\uc4-mcp.exe` works. 9 of 10 exit criteria ticked; the README 5-minute test needs a teammate | [app/README.md](../app/README.md#mcp-inspector), [phase plan](../.tasks/uc4-assistant/phase-1-mcp-data-layer.md#exit-criteria), `app/logs/uc4_mcp.log` (22:44-22:53), commit `9abb356` | yes | |
| 2026-09-29 | Harrison Fuller | Data and rules | test | Claude Code (Opus 5.5); Claude in Chrome; OpenCode | Phase 1 close-out. (1) Timed dry run of the README's OpenCode steps as a new teammate: clean clone outside OneDrive, fresh venv, `opencode mcp list` → `uc4 connected` in 0.4 min, and 0.3 min again with an empty uv cache (121 MB downloaded); no README step failed, but it never says where to get the git-ignored zip. The criterion stays unticked until a teammate runs it. (2) Deck screenshots of `score_trial SYN-TR-0037` captured by Claude driving the Inspector in Chrome. The page had to be zoomed to 0.67 to fit the 858 px viewport; code folding and several captures failed, so the result is 3 scrolled shots. (3) Fast-forward merge of the branch into `main` | [verdict](screenshots/step9_score_trial_0037_1_verdict.jpg), [resistant % fails](screenshots/step9_score_trial_0037_2_resistant_fails.jpg), [rationale flag](screenshots/step9_score_trial_0037_3_rationale_flag.jpg), [phase plan](../.tasks/uc4-assistant/phase-1-mcp-data-layer.md#exit-criteria) | edited: small text, fine for a backup slide; retake at full width for the main deck | |
| 2026-09-30 | Harrison Fuller | Screen and log | code | Claude Code (Opus 5.5 planner and controller; Sonnet implementers and reviewers via subagent-driven development); Claude in Chrome | Planned Phase 3, then executed it task by task with a Sonnet implementer and reviewer per task. Built: append-only override log with the full recommendation copied in, trial and line reads plus `POST /decisions`, the static breeder screen (criteria, lines, flags, decisions, ask), and `uc4-ask serve` opening it. Walkthrough of the 11 "Validate the demo" scenarios in Chrome: all 11 pass (scenario 11 only for the no-model path). Full suite 392 passed, 1 deselected. Open: screenshots and GIF (window was minimized), live `/ask` answer pending Portkey credentials, three minor findings (stale trial after a failed search, generic 422 text, repeated verdict word) | [phase plan](../.tasks/uc4-assistant/phase-3-breeder-screen.md), [walkthrough](phase3_walkthrough.md), commits `6ce282c`, `704201f`, `b371ccb`, `ab311cd`, `9aec632` | yes | |
| 2026-09-30 | Harrison Fuller | Screen and log | demo | Claude Code (Opus 5.5); Playwright with installed Chrome; model `@bedrock-aifoundry-use1-001/global.openai.gpt-6-sol` via Portkey | "Still open for the demo: deck screenshots … and a live Ask answer; use PORTKEY_API_KEY, UC4_LLM_BASE_URL and UC4_LLM_MODEL from .env." No code change: `uv run --env-file .env`. `ping` → `tool_call=yes tokens=50/17`; "Why is SYN-TR-0037 amber?" → answered, cited the recommendation row, 13 432/777 tokens; `/health` ok. Six deck screenshots captured by a Playwright script (headless Chrome, 2×) instead of Claude in Chrome, which needed a visible window. Finding: the model calls `score_trial` twice for this question | [walkthrough](phase3_walkthrough.md#live-ask-and-deck-screenshots-2026-09-30), [live answer](screenshots/phase3_3_ask_live.png) | yes | |

| 2026-09-30 | Harrison Fuller | Screen and log | demo | GitHub Copilot; Playwright with installed Chrome; Pillow | "Finish the stopped agent's open demo items; start implementation." Verified six trusted mouse/keyboard checks and the unchanged 393-test default suite; recovered the scratch capture script into a self-contained uv command; regenerated six PNGs and an eight-scene, 16-second GIF (297,540 bytes), with two live Ask answers and rehearsal overrides isolated in a temporary log; closed the task evidence | [browser tests](../app/tests/test_browser.py), [capture script](screenshots/capture.py), [GIF](screenshots/phase3_walkthrough.gif), [walkthrough](phase3_walkthrough.md#real-input-checks-2026-09-30) | yes | |

## 2026-09-30 evidence-driven demo review

Retained user requests: "Write tasks and plans to .tasks ... Be evidence driven", "Implement the plan", and "Use sub agents to complete .tasks/uc4-demo-review". Codex root coordinated data_review, app_review and screen_video sub-agents across data, application/MCP, live agent, screen, documentation, videos and rehearsal. Reproduced source/grounding/UI/documentation defects were fixed and rechecked; failed attempts remain in the evidence record.

Results and exact scope: [review index](../.tasks/uc4-demo-review/task.md), [findings](../.tasks/uc4-demo-review/evidence/20260930T225928Z-bbd0c0b/findings.md), [reviewed identity](../.tasks/uc4-demo-review/evidence/20260930T225928Z-bbd0c0b/manifest.md), and [two narrated recordings](../.tasks/uc4-demo-review/evidence/20260930T225928Z-bbd0c0b/videos/index.md). Synthetic v2 remains the app/demo baseline; v3 is separately audited. Numeric/citation guards have disclosed semantic limits, and human live presentation timing remains unmeasured. Local Windows speech supplies disclosed synthetic narration; live Ask answers in the recordings are actual gateway responses.

## Weekly roll-up (fill in Thursday for the deck)

| Phase | # entries | Best example (link) | Lesson |
| --- | ---: | --- | --- |
| requirements | | | |
| stories | | | |
| data | | | |
| prototype | | | |
| code | | | |
| test | | | |
| docs | | | |
| demo | | | |

## 2026-10-01 replacement UC4 analysis

Retained user requests: "There has been another change from the SME for use-case 4 ... We need new analysis on ... candidate_recommendations_synthetic.zip", "Implement the plan", and "continue". User selected analysis/documentation scope and archive/deactivate of previous versions. Codex inspected the ZIP in memory, preserved v3 outputs and historical guides, switched the current generator to the replacement alone, and produced a standalone HTML briefing, four figures and 15 audit tables. No runtime source-code migration was performed by this task; concurrent workspace changes were preserved.

Measured: 150 recommendations (32 GREEN, 53 AMBER, 65 RED); all 12 audited key relationships resolve; zero violations across 22 consistency checks. All 148 available field summaries reproduce within displayed precision with ratio-of-means yield comparison; counts, lab/genomic values, markers and exclusions also reconcile. Five missed-irrigation trials explain caveats on 30 candidates; two lines have no field data. The compatible RAG rule reproduces 150/150 from both supplied rounded summaries and reconstructed precision. One printed warning rounds disease to 6.0 while its numeric record is above 6.0; all 154 numeric warning comparisons agree with summary and reconstructed values. Aggregation and full scoring policy remain labelled inferred pending SME confirmation.

Validation: `python analysis/uc4_eda/uc4_eda.py`; `python -m pytest -q analysis/uc4_eda -p no:cacheprovider --basetemp analysis/uc4_eda/.test-tmp-20261001/final-check` -> **82 passed**. Current and archived-v3 report links, current guide/source/SME links, embedded figures and source SHA-256 checked; `git diff --check` passed. Initial validation found one test's overly loose alternative-ratio tolerance, corrected to source precision. Two attempts hit Windows temp permissions (shared temp and existing .pytest_cache); final validation used a writable dedicated analysis temp directory. Historical app tests were outside this task's scope.

Evidence: [current briefing](../analysis/uc4_eda/report.html), [replacement analysis](../analysis/uc4_eda/candidate_analysis.py), [tests](../analysis/uc4_eda/test_candidates.py), [source selection](../get_started/README.md). Source ZIPs remain git-ignored. SHA-256: `c195330223d0e3bb334dc9c2e1f338a37f058f5cb3b564d9d2140c7a5011da46`.


## 2026-10-01: candidate application migration

User intent: modify the application for the replacement candidate analysis; show complete recommendation lists with individual input filters; record who, what, when, where and why a decision was overridden; enrich evidence for future decisions. The user approved provisional scoring, filters that do not change scores, reviewed enrichment, self-declared local identities, ADVANCE/HOLD/DISCARD actions and the labelled maize-like synthetic dataset. Execution prompts included ?Implement the plan?, ?continue work using /fast? and ?Continue?.

Implemented a shared analysis/runtime reconstruction module, candidate HTTP/MCP contracts and browser flow, SQLite decision/recommendation/evidence revisions, immutable review events, source snapshots, idempotent/stale-safe decision writes, legacy JSONL import, previewed enrichment activation and rollback. Current default uses the candidate archive; explicit `--historical-v2` preserves the old demo. Biological policy remains inferred and requires SME confirmation.

Validation: full offline application suite **416 passed, 10 deselected**; full analysis suite **82 passed**; combined candidate/historical browser suite **9 passed**; candidate browser rerun **1 passed** after UI refinements. The final source-audit refinement was checked with **13 candidate migration tests passed** and JavaScript syntax validation. Analysis regeneration reports **150/150** matches using supplied and source precision. MCP stdio, uv client launch and HTTP transport pass. `git diff --check` passes. Live-model evaluation was not run; the candidate evaluation set and its offline tool oracles were updated and checked. Tests use isolated databases/logs and workspace temporary directories. Original archives and historical decision payloads were retained.

Evidence: [current app guide](../app/README.md), [architecture](../app/ARCHITECTURE.md), [candidate migration tests](../app/tests/test_candidate_migration.py), [browser workflow](../app/tests/test_candidate_browser.py), and [current analysis](../analysis/uc4_eda/report.html).

## 2026-10-01: core breeder usability implementation

User selected core usability first (01/03, read-only 02, manual 06, 08), sticky
desktop Ask/mobile launcher, and opt-in tab-session alias; then explicitly
requested implementation. Codex inspected source/API/UI contracts, produced the
plan, implemented the core, designed regression checks and independently
recomputed four source cases. Human SME and breeder usability review remain
pending. Deferred scenarios, full preferences, voice/NL, enrichment redesign and
pilot discovery remain outside this implementation.

Source comparison confirms all 150 recommendation records equal pre-change
HEAD. Targeted checks passed (64); four usability contracts passed after final
backend refinements. Final browser run: **5 passed**, including retry-after-lost-response and
revision/candidate context isolation. Full offline suite: 411 passed; nine
failures/errors reference missing historical-v2 generated CSVs. A live Ask
retry returned a grounded answer with three resolved citations. Retained
failures include sandbox connection failure, first-load initialization race
(fixed), and an incorrect no-data test expectation (corrected against source).

See [implementation record and evidence](../.tasks/uc4-breeder-usability/implementation.md).
No human approval, measured time saving or vegetable policy validation is claimed.


## 2026-10-01: AMBER workflow review, fixture repair and timed rehearsal

User requested review of one AMBER candidate through source inspection, live
Ask and HOLD; repair of missing historical test fixtures; and a seven-minute
rehearsal using isolated history. Codex performed the browser actions against
fresh SQLite stores, noted usability friction, recovered independent historical
CSV oracles byte-for-byte from Git, and ran the full default and browser suites.
No application/UI changes were bundled into this follow-up.

Results: 421 offline tests passed; 13 browser tests passed. Both live AMBER
workflows returned grounded answers and recorded exactly one HOLD per isolated
store, retaining the original AMBER recommendation. The timed automated
rehearsal completed at 420.00 seconds with scheduled narration pauses. This is
not human breeder feedback, measured time savings or a spoken team rehearsal.

Observed friction: dense source JSON; signed-margin direction; original versus
display precision; tall Ask answers with literal Markdown markers; selection
reset after reload. These remain proposals for follow-up, not implemented fixes.
The original missing-fixture failures are retained in the earlier evidence;
restored fixtures carry Git/source hashes rather than regenerated app outputs.

See [review results and evidence](../.tasks/uc4-breeder-usability/review-and-rehearsal.md)
and [operator script](../.tasks/uc4-breeder-usability/demo-script.md).


## 2026-10-01: readable evidence dialogs

User requested popup/page detail navigation and no pure JSON in application
views. Codex replaced inline JSON with trait-filtered source tables and labeled
record views, moved full Ask answers/citations into dialogs, added Back/Close
focus restoration and clarified margin direction. Data/API/scoring behavior
remains unchanged. The browser tests verify safe text rendering, source scope,
full precision, preserved decision drafts and original answer context.

Validation: 421 offline tests passed; 7 candidate browser tests passed. Desktop
and mobile source dialogs were visually inspected. The existing rehearsal
harness was adapted to the new controls without claiming another live/timed
rehearsal. See [popup verification](../.tasks/uc4-breeder-usability/popup-update.md).


## 2026-10-01: task 04 saved preferences

The user requested explicit opt-in name/context defaults, restored filters and
selection, Reset and Forget, while keeping decisions/reasons/scoring separate.
After inspecting the existing tab alias and decision reset behavior, Codex
proposed browser-local storage rather than extending the decision database.
The user selected one browser profile, explicit Save for defaults plus a separate
resume opt-in, and Reset of the view only, then instructed "execute plan".
Multi-profile and policy-setting persistence from the earlier task preview were
deferred by that choice.

Codex added the preference panel, versioned local storage, source compatibility
checks, reset/forget request invalidation and browser tests. No backend or scoring
changes were needed. Saved preferences remain self-declared conveniences, not
identity verification. Tests use isolated histories and synthetic evidence.

Validation: 421 offline tests passed; all 22 browser scenarios passed across the
suite and targeted reruns, including an actual browser close/reopen. Initial
Playwright setup failures and their fixes are recorded, along with desktop/mobile
screenshots, in [task 04 verification](../.tasks/uc4-breeder-usability/preferences-update.md).
Human breeder timing and biological review were not performed.
## 2026-10-01 — Task 05 typed natural-language filters

The user requested typed filter interpretation before voice, with an editable
preview and explicit Apply, excluding decision recording and scoring changes.
After repository inspection, the user chose the existing model connection,
replacement of active filters with sorting retained, and direct preview editing,
then instructed “Implement the plan.”

Codex added narrowly typed interpretation/validation routes and the candidate
filter preview, preserving selected-candidate/manual drafts and opt-in view
persistence. Tests compare the AMBER / usable-trial request with manual filtering
and CSV, reject invalid bounds/units and stale context, and exercise desktop/mobile
confirmation and cancellation. No source-note retrieval or write tool is exposed.

AI-assisted review found and fixed a nonfinite-number error serialization issue.
The first network-enabled model evaluation matched 13/14 cases; it exposed an
underspecified excluded-trial field. Adding its definition produced 14/14 on the
same set, recorded as a regression rerun rather than fresh held-out accuracy.
Screenshot inspection led to collapsing unused range editors on mobile.

Actual commands, counts, failed attempts and limitations are recorded in
[task 05 verification](../.tasks/uc4-breeder-usability/task05-evidence/verification.md).
Human breeder validation and independent review are pending; voice remains deferred.

## 2026-10-01 - Task 07 guided manual evidence enrichment

User request: implement the approved task 07 plan after a short task 05
walkthrough. The user confirmed Interpret/edit/Apply behavior was clear and
selected coverage of all existing evidence types plus the local self-review model.

Codex traced source-row selection, review states, supersession, revision activation
and historical decisions; implemented typed manual controls, field definitions,
provenance validation, source/current/proposed comparisons and explicit action
confirmations. Voice and natural-language writes remain deferred. No agents were
delegated and no model-generated evidence was supplied as real measurements.

AI-assisted verification included lifecycle/API cases, browser walkthroughs,
mobile screenshot review, stale activation and deliberately delayed responses.
Inspection identified a compressed mobile table, a stale-button cleanup bug and
a response-order refresh race; these were corrected and covered by checks.
Synthetic 92.25% and 93.25% corrections are labeled hypothetical. Human confirmation
applies to the task 05 walkthrough and task 07 scope, not independent code review,
biological validation or a measured breeder productivity study.

See [task 07 verification and screenshots](../.tasks/uc4-breeder-usability/task07-evidence/verification.md)
for actual commands, results, source identity, limitations and implementation details.

### 2026-10-01 - Task 06 manual confirmation and history

- User: manual breeder decision flow with fewer inputs, clear confirmation and
  traceable history; keep voice and natural-language writes deferred.
- Codex inspected the existing compact form, saved preferences and transactional
  decision contract. User selected inline review and requested implementation.
- Implemented an immutable confirmation snapshot, explicit final write, retry and
  conflict handling, saved receipts, and original recommendation/evidence access.
- Retained existing validation/defaults; rejected automatic reuse of reasons or
  choices and any natural-language write integration for this slice.
- Verification and limitations: [.tasks task 06 record](../.tasks/uc4-breeder-usability/task06-evidence/verification.md).
  No human breeder measurement or biological validation is claimed.

### 2026-10-01 - Demo-readiness and self-guided breeder review

- User requested the updated rehearsal, full workflow, reliable browser startup
  and breeder timing/error review; selected a self-guided pack when asked.
- Rehearsal now reviews before writing and reopens original evidence after reload.
  A shared isolated runtime replaces cold per-case subprocesses and verifies HTTP
  readiness. Browser contexts and history databases remain separate per test.
- Full candidate browser suite: 31 passed. Fresh-process repeat: six passed.
  Lifecycle test verified three starts/stops and active-store isolation.
- Live synthetic workflow passed with three resolved citations; offline fallback
  passed separately. The initial connection-reset failure is retained in evidence.
- Prepared a session launcher, blank worksheets, task cards and feedback prompts.
  Actual human measurements remain pending; automated timings are not substituted.
- [Verification and evidence](../.tasks/uc4-breeder-usability/demo-readiness.md).


## P01 follow-up implementation - 2026-10-02 UTC

User approved explicit Record another decision gating and candidate section tabs,
then requested implementation. Added saved-state handling across navigation and
reload, preserved retry/conflict semantics, shortened initial Ask presentation
with expandable detail, and made Recorded by prominent. API/schema, scoring and
historical events remain unchanged; voice/NL writes remain deferred.

Verification: 40 candidate browser cases, 64 relevant agent/grounding/API cases,
and six final navigation/viewport checks passed. Offline and live rehearsals
passed; live Ask had three verified citations and no grounding problems. Original
extra-save trigger remains unknown. A fresh targeted breeder retest is prepared,
not claimed complete. See ../.tasks/uc4-breeder-usability/followup-evidence/verification.md.


## 2026-10-02 - Local team handoff wrap-up

User requested functional readiness and updated process, architecture and README documentation, using the saved breeder-usability handoff. Selected local team handoff, both breeder/developer process guides and fresh live AI checks; then instructed Continue with plan.

Restored credential-free .env.example, consolidated README/setup guidance, updated runtime architecture/API docs and added app/PROCESS.md. Packaging now includes the process guide and historical regression fixtures/provenance. Full offline suite: 473 passed; candidate browser suite: 40 passed; live filter evaluation: 14/14 cases; live Ask walkthrough: three verified citations and no grounding/browser errors. Real browser filter interpretation/validation/application passed without history writes. A fresh extracted locked package passed checksum/manifest, static assets, documentation links and single-event restart persistence; its documented candidate subset passed 69 tests.

Evidence and remaining human/domain checks are recorded in .tasks/uc4-breeder-usability/wrap-up-verification.md and handoff.md. A local dirty-working-tree ZIP was generated; no commit, deployment, publication or external distribution occurred. Human retest gaps, spoken team rehearsal and biological validation remain explicit.


### Nontechnical breeder review launcher

User asked how to run human review as a nontechnical breeder. Added Start-Breeder-Review.cmd, a plain-language app/HUMAN_REVIEW.md, and browser opening after readiness in the isolated session launcher. Smoke check passed; regenerated the package with 86 inputs and repeated clean-folder checksum/manifest, startup, assets, links and restart-persistence verification successfully. No actual human completion is claimed.


### Gateway failure during human review

User reported model HTTP 500 errors in session 20261002T140233Z-402f06. Read-only session health was OK. A tiny model call timed out; a plain-text request without tools/candidate data returned a Bedrock unexpected-error 500; the exact SYN-MZ-00099 Ask in isolated storage timed out. The current live route has not recovered in verification. Improved Ask failure presentation and prevented overlapping submissions while retaining question/context and allowing later retry. 43 browser tests and 60 offline agent/gateway tests passed. Updated package passed clean-folder manifest/checksum, assets, links, startup and persistence checks. Active review records were preserved. See .tasks/uc4-breeder-usability/gateway-issue.md for evidence and remaining external-service recovery requirement.
