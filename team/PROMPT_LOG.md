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
