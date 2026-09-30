# Task: UC4 breeder assistant (R&D Data Source Unification)

**Created:** 2026-09-29 · **Demo:** Fri 2026-10-02, 7 min + 5 min Q&A; submit demo, deck, one-pager and repo link within 1 hour ([handbook p. 3][hb3]) · **Status:** planning; Phase 1 detailed in [phase-1-mcp-data-layer.md](phase-1-mcp-data-layer.md); Phase 2 detailed in [phase-2-nl-agent.md](phase-2-nl-agent.md); Phase 3 done on branch `demo-live-ask` ([phase-3-breeder-screen.md](phase-3-breeder-screen.md), evidence in [phase3_walkthrough.md](../../team/phase3_walkthrough.md)): six deck screenshots, live `/ask`, walkthrough GIF and trusted browser input checks verified.

Every number below was re-measured on 2026-09-29 from the v2 archive (`get_started/RE__Hatchworks_Hackathon_-_4th_Use_Case.zip`) using `analysis/uc4_eda/load.py` and `rules.py`; the existing EDA suite passes (40 tests). **Inferred** marks our reading of the data, **proposal** marks a design choice.

## Goal

Build an assistant that "unifies the mock sources behind a natural-language interface and triages candidates red/amber/green with an explanation, always deferring the final call to the breeder" ([brief p. 5][brief]). Demo-ready means: a flagged candidate with a one-line explanation that the breeder can challenge and override, and the override is logged (same page).

The brief lists three buildable pieces: (1) a data-unification (MCP) layer over the mock sources, (2) a natural-language query interface, (3) red/amber/green triage with an explained recommendation and override loop. We build them in that order.

## Non-negotiables

| Rule | Source |
| --- | --- |
| A human makes the final call; the tool is an assistant, not a replacement | [Brief p. 5][brief] |
| Every recommendation shows its reasoning, never a bare verdict | [Brief p. 5][brief] |
| No connection to a live research system | [Brief p. 5][brief] |
| Plain code sets the colour; the LLM only interprets the question and phrases answers from retrieved rows | [RECOMMENDATION.md][ai] |
| Missing evidence never passes a criterion; lab rows are never attached to a trial (no `TRIAL_GUID`) | [ROLES.md rule 3][roles] |
| Every claim in app, deck and one-pager cites a CSV row, a document page or a test | [ROLES.md rule 1][roles] |

## Evidence register

| Claim | Measured value | Source |
| --- | --- | --- |
| Rows per file | germplasm 150, trial 72, observation 720, operations 216, lab 360, genomics 150, recommendations 72 | `load.EXPECTED_ROWS`, re-run |
| Orphan GUIDs | 0 | [DATA_ARCHITECTURE Part C][arch-c] |
| Lines per trial / trials per line | 10 in all 72 trials / 4 (30 lines) or 5 (120 lines) | re-run; Part C |
| Operations per trial | 3 in all 72 trials | re-run |
| Lab rows per line | 2 (90 lines) or 3 (60 lines); no trial key, no dates, 4 unnamed traits | re-run; Part C |
| Supplied verdicts | PASS 7, HOLD 35, FAIL 30; `RULE_VERSION = SYNTH_V1` | re-run |
| Inferred rule reproduces verdicts | 72 of 72 | `rules.apply_rule`, re-run |
| Cut-point brackets | `analysis/uc4_eda/tables/rule_intervals.csv` | [SME_ANSWERS][sme] |
| FAIL triggers | disease only 16, yield only 10, both 4 | re-run |
| HOLD trials missing each criterion (any / sole reason) | moisture 16 / 5, resistant 16 / 4, disease 14 / 4, GBV 12 / 1, yield 6 / 2 | re-run |
| Extract date | 2026-09-26 12:00 (latest `LAST_CHG_DATE` in any table) | `lifecycle.snapshot_date` |
| Rationale says "all four met" but not PASS | 4 of 11 (SYN-TR-0037, 0038, 0046, 0052) | `tables/chronology_checks.csv` |
| Trial GBV mean via observation links | matches 0 of 72; block-of-10 mapping 72 of 72 | `rules.genomics_reconciliation`, re-run |
| Trial resistant % via observation links | matches 10 of 72 | same |
| Operations outside their trial's start year | 144 of 216 | `tables/chronology_checks.csv` |
| PLANNED operations dated before the extract | 114 of 114 | same |
| COMPLETE trials with planned operations | 60 of 72 | same |
| Operation's trial + line not in observation links | 131 of 216 | same |
| Worked examples | 0003 PASS (10.79 t/ha, 16.8 %, 3.3, GBV 106.8, 70 %); 0037 HOLD (resistant 30 % < 50); 0001 FAIL (disease 7.7 > 7) | re-run |

## Phases

| # | Phase | Owner role ([ROLES.md][roles]) | Target | Exit criterion (checkable) |
| --- | --- | --- | --- | --- |
| 1 | **MCP data-unification layer**: read-only tools over the seven files with row provenance, SYNTH_V1 scoring and consistency flags | Data and rules | Tue 29 → Wed 30 AM | See [phase 1](phase-1-mcp-data-layer.md): tests green, `baseline_check` 72/72, three worked examples correct with source rows, ambiguous IDs return candidates |
| 2 | **Natural-language question agent**: LLM via Portkey calls the Phase 1 tools and answers with citations | AI answers | Wed 30 | ≥ 10 test questions; each answer's numbers appear in the tool output it cites; "SYN-TR-003" triggers a "which one?" reply; model and settings committed |
| 3 | **Breeder screen and override log**: trial view (criteria table, 10 lines, flags, colour + reason), "Record decision" with required reason, append-only log | Screen and log | Wed 30 → Thu 1 | Override without reason rejected; log keeps original recommendation, decision, reason, user, timestamp; source data and recommendation unchanged |
| 4 | **Baseline and evaluation** | All | Thu 1 | Engine 72/72 in CI; manual cross-file lookup vs app (time and correctness) on the same trials; every scenario in [uc4 README "Validate the demo"][validate] exercised |
| 5 | **Demo, deck, one-pager, handover** | Docs and demo | Thu 1 → Fri 2 | Script rehearsed within 7:00; every slide claim links to evidence; prompt log rolled up |

Phases 2 and 3 build against Phase 1's tool outputs (the [ROLES.md contracts][contracts]); they can start on day 1 with hand-written sample records and swap to the live tools once step 7 of Phase 1 lands.

## Decisions

| Decision | Why |
| --- | --- |
| Python package in `app/`, managed with `uv` | The EDA loader and rule are Python and tested; porting them keeps the 72/72 evidence |
| Official `mcp` Python SDK, pinned `>=2.2,<3` (`MCPServer`; 2.x renamed `FastMCP`) | The brief names MCP; OpenCode and Claude clients consume MCP over stdio, and n8n's MCP Client node over HTTP. 2.2.0 is what `uv` resolves today |
| Git repo at the workspace root; supplied zips git-ignored; venv outside OneDrive | The workspace was not under version control; data clearance is open; OneDrive sync locks venv files |
| Read the zip in place, never extract or modify | Same as the EDA; the archive is read-only evidence |
| Phase 1 tools are read-only | Brief p. 5: no autonomous decisions; the only write (override log) belongs to Phase 3 |
| Verdict grain is the trial | The supplied file holds one verdict per trial ([SME_ANSWERS][sme]) |
| Observation links are the recorded trial-line evidence; the block-of-10 mapping is reported only as a flagged inference | Neither mapping is confirmed; observation links are what the files record |
| Colour mapping PASS→green, HOLD→amber, FAIL→red (**proposal**) | The file uses PASS/HOLD/FAIL only |
| Thresholds labelled `SYNTH_V1 (inferred)` everywhere | Cut-points are bracketed, not supplied |

## Open SME questions and interim handling

Full list: [SME_ANSWERS follow-ups][followups].

| Question | Until answered |
| --- | --- |
| Exact cut-points and inclusive bounds | Use `rules.SYNTH_V1`; show the bracket from `rule_intervals.csv` beside each threshold |
| Resistant % missing from the rationale | Engine explanation, not supplied text, is shown; `Recommendation.rationale_omits` names the omitted criterion (33 trials); flag `RATIONALE_READS_AS_PASS` where the text says all four met but the verdict is not PASS (4) |
| Trial vs line as the unit of decision | Score trials; a line view lists its 4-5 trial verdicts without combining them |
| Which lines make up each trial's aggregates | Flag `AGGREGATE_LINKS_UNVERIFIED` on every trial |
| Lab trait meanings | Label "Lab trait …xx"; never used in scoring |
| Real MCP required or optional; data cleared for a shared repo | Build MCP (low cost); keep data in `get_started/` untracked until cleared |

## Risks

| Risk | Mitigation |
| --- | --- |
| SME changes thresholds | `Rule` is a versioned dataclass; the 72/72 test fails loudly on any drift |
| Judges read a trial verdict as a line verdict | Every line view states "verdicts are per trial" |
| `mcp` SDK API changes (1.x → 2.x already renamed the server class) | Pin the major version; keep tools thin over a pure `EvidenceStore` that is tested without MCP |
| Clients (OpenCode, n8n) fail to negotiate with an `mcp` 2.x server | Phase 1 step 1 connects OpenCode to a ping tool before any real work |
| stdio server corrupted by stray prints | Log to `app/logs/uc4_mcp.log`; a subprocess stdio test calls a tool end to end |
| LLM invents numbers (Phase 2) | Tools return every value with its source row; Phase 2 test checks each cited number exists in the tool output |

[hb3]: ../../get_started/2026_Participant_Handbook.pdf#page=3
[brief]: ../../get_started/2026_Use_Case_Briefs.pdf#page=5
[ai]: ../../use-cases/RECOMMENDATION.md#ai-inside-the-product
[roles]: ../../team/ROLES.md
[contracts]: ../../team/ROLES.md#interfaces-agree-these-first-so-roles-can-work-in-parallel
[arch-c]: ../../use-cases/uc4/DATA_ARCHITECTURE.md#part-c-evidence
[sme]: ../../team/SME_ANSWERS.md
[followups]: ../../team/SME_ANSWERS.md#follow-up-questions-to-send
[validate]: ../../use-cases/uc4/README.md#validate-the-demo
