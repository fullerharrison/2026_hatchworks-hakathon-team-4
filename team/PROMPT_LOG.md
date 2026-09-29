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
