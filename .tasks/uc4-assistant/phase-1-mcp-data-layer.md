# Phase 1: MCP data-unification layer

**Parent:** [task.md](task.md) · **Owner:** Data and rules · **Target:** Tue 2026-09-29 → Wed 2026-09-30 AM · **Consumers:** Phase 2 (NL agent), Phase 3 (screen), n8n workflows.

## Goal

One read-only service that answers "what does the data say about this trial or line?" across all seven v2 files, and returns every value with the file and row it came from, the SYNTH_V1 recommendation with each criterion against its threshold, and the consistency flags the data profile found. It is exposed as MCP tools so any MCP client (OpenCode, Claude, n8n) and our own UI use the same evidence path.

**Out of scope for Phase 1:** LLM calls, UI, override writes, any data not in the v2 zip.

## Environment facts (checked 2026-09-29)

| Fact | Consequence |
| --- | --- |
| `uv` resolves `mcp` to **2.2.0**. In 2.x `FastMCP` is renamed `MCPServer` (`from mcp.server.mcpserver import MCPServer`); `from mcp.server.fastmcp import FastMCP` raises. | Pin `mcp[cli]>=2.2,<3`; write against `MCPServer`. Tests use `mcp.Client(server)`, which connects in-process to an `MCPServer` instance, or `mcp.Client(StdioServerParameters(...))` for a subprocess. |
| The workspace is **not a git repository**. | Step 0 runs `git init` before anything else. |
| The workspace is inside **OneDrive**. | Keep the venv outside it: set `UV_PROJECT_ENVIRONMENT` to a local path (e.g. `$env:LOCALAPPDATA\uc4-mcp\.venv`) to avoid sync churn and file locks. |
| Node is installed (`C:\Program Files\nodejs`). | `mcp dev` (MCP Inspector) works on this machine; teammates need Node too. |

## Layout

```text
app/
  pyproject.toml          # uv project "uc4-mcp"; deps: mcp[cli]>=2.2,<3, pandas; dev: pytest
  README.md               # run commands + MCP client config snippets
  src/uc4_mcp/
    __init__.py
    sources.py            # port of analysis/uc4_eda/load.py + provenance columns
    rules.py              # port of analysis/uc4_eda/rules.py + explain()
    lifecycle.py          # port of analysis/uc4_eda/lifecycle.py (snapshot_date, chronology_checks)
    models.py             # frozen dataclasses for the ROLES.md contracts + to_json_safe()
    checks.py             # consistency flags (FlagIndex, FLAG_CODES), built on lifecycle.py + rules.py
    store.py              # EvidenceStore: indexes, resolution, trial/line assembly
    server.py             # MCPServer tools and resources; main()
  tests/
    conftest.py           # session-scoped store fixture (load once)
    test_sources.py  test_rules.py  test_lifecycle.py  test_models.py
    test_checks.py  test_store.py  test_server.py  test_stdio.py
  logs/                   # uc4_mcp.log (git-ignored)
```

`analysis/uc4_eda/` is **not** imported or changed: it is the evidence record. The port copies its functions and keeps their tests.

**Locating the zip:** `sources.find_zip()` reads the env var `UC4_ZIP` if set, otherwise walks up from the package to the first directory containing `get_started/` and globs `RE__Hatchworks_Hackathon_-_4th_Use_Case*.zip` there. (The EDA's `parents[2]` does not hold from `app/src/uc4_mcp/`.)

## Provenance: what a "source row" is

Each loaded row gets `_source_file` (the zip member name) and `_line_no` (CSV line, header = 1, so first data row = 2). `row_id` is the file's own key:

| Table | `row_id` column |
| --- | --- |
| germplasm | `MATERIAL_GUID` |
| trial | `TRIAL_GUID` |
| observation | `ID` |
| operations | `OPERATION_GUID` |
| lab | `ROWGUID` |
| genomics | `GENOMIC_SAMPLE_GUID` |
| recommendations | `TRIAL_GUID` |

All seven columns exist, are non-null and are unique in the v2 archive (checked 2026-09-29). Step 2 keeps that as a test.

## Contracts (`models.py`, from [ROLES.md](../../team/ROLES.md#interfaces-agree-these-first-so-roles-can-work-in-parallel))

```python
@dataclass(frozen=True)
class EvidenceRow:
    source_file: str; row_id: str; line_no: int
    trial_guid: str | None      # None for lab and genomics rows (no trial key)
    material_guid: str | None   # None for trial-level values
    field: str; value: str | float | int | None; uom: str | None; date: str | None
    flags: tuple[str, ...] = ()

@dataclass(frozen=True)
class Criterion:
    field: str; label: str; value: float | None; test: str   # ">=", "<=", "<", ">"; field not unique (7 criteria, see step 4)
    threshold: float; bracket: tuple[float, float]
    kind: str        # "pass" | "knockout"
    passed: bool     # pass criterion met, or knockout NOT triggered; a missing value never passes
    triggered: bool  # knockout fired; always False for kind == "pass"

@dataclass(frozen=True)
class Flag:
    code: str; severity: str; message: str; evidence_row_ids: tuple[str, ...] = ()

@dataclass(frozen=True)
class Recommendation:
    trial_guid: str; trial_id: str; verdict: str; colour: str   # colour is a proposal
    criteria: tuple[Criterion, ...]; knockout: tuple[str, ...]; reason: str
    rule_version: str; supplied_verdict: str; matches_supplied: bool
    supplied_rationale: str; rationale_omits: tuple[str, ...]
    evidence_row_ids: tuple[str, ...]; flags: tuple[Flag, ...]
# evidence_row_ids entries are "<source_file>#<row_id>" (Recommendation and Flag).
```

`reason` is one line built by code, e.g. `"HOLD: resistant lines 30% < 50% (inferred threshold)"`.

**JSON safety.** pandas yields `numpy.int64` (e.g. `START_YEAR`, `REPLICATION_NO`), which `json.dumps` rejects, and `NaN`, which is invalid JSON. `models.to_json_safe()` converts numpy scalars to Python `int`/`float`/`str` and `NaN`/`NaT` to `None`; every tool returns its output through it.

**Response envelope.** Every tool returns the same outer shape so the Phase 2 agent never guesses:

```python
{"status": "ok" | "many" | "none",
 "result": ...,            # present when status == "ok"
 "candidates": [...],      # present when status == "many": [{id, guid, label}]
 "message": str}           # e.g. "10 trials match 'SYN-TR-003'; which one?"
```

## MCP surface (`server.py`)

| Tool | Input | Returns | Acceptance (from the evidence register) |
| --- | --- | --- | --- |
| `list_sources` | none | per file: member name, rows, key, grain, synthetic marker, what it lacks | 7 files; rows = `EXPECTED_ROWS` |
| `find_trial` | `query` (ID, GUID, or ID fragment) | envelope; `result` = the trial | `"0037"` → ok, SYN-TR-0037 (listed once, not also via its GUID); `"SYN-TR-003"` → many, 10 candidates 0030-0039; `"XYZ"` → none |
| `find_line` | `query` | same | `"SYN-MZ-00001"` → ok; `"SYN-MZ-0001"` → many, 10 candidates 00010-00019; `"003"` → many, 11 candidates by ID (00003, 00030-00039), not the 17 GUIDs containing "003" |
| `get_trial` | trial ID/GUID | trial meta (year, location, status), trial values as `EvidenceRow`s from recommendations, 10 linked lines with GBV + resistance marker, 3 operations, flags | 10 lines and 3 operations for every trial |
| `get_line` | line ID/GUID | identity, genomics, lab rows ("Lab trait …xx"), trials it appears in with each trial verdict, operations, flags | 4 or 5 trials; 2 or 3 lab rows; `LAB_NOT_TRIAL_LINKED` present |
| `score_trial` | trial ID/GUID | `Recommendation` | 0003 PASS all 5 met; 0037 HOLD, only `RESISTANT_MATERIAL_PCT` unmet (30 < 50), `rationale_omits` = resistant; 0001 FAIL, knockout disease 7.7 > 7 |
| `query_trials` | `verdict?`, `knockout?` (`yield`/`disease`/`both`), `missed?` (criterion field), `only?` (bool: sole reason) | list of `{trial_id, verdict, reason}` | FAIL 30, HOLD 35, PASS 7; disease-only 16, yield-only 10, both 4. HOLD trials missing each criterion (any / sole reason): moisture 16 / 5, resistant 16 / 4, disease 14 / 4, GBV 12 / 1, yield 6 / 2 |
| `baseline_check` | none | `{checked, matched, mismatches[]}` | 72, 72, `[]` |

Resources: `uc4://sources` (same as `list_sources`), `uc4://rule/SYNTH_V1` (thresholds, test direction, "inferred" note, and brackets computed at startup by the ported `threshold_intervals()`; a test asserts they equal `analysis/uc4_eda/tables/rule_intervals.csv`).

**Resolution rule.** GUIDs match exactly only (case-insensitive). Fragments match against `TRIAL_ID` / `MATERIAL_ID` only, because GUIDs end in a sequence number (`…-000000000037`) and would add false hits. Candidates are de-duplicated by key. Unresolved or ambiguous input to `get_*`/`score_trial` returns status `many` or `none` with candidates instead of guessing.

**Tool descriptions are the Phase 2 agent's instructions.** Each tool docstring states the grain ("verdicts are per trial"), units, that thresholds are "SYNTH_V1 (inferred)", and one example input.

## Flags (`checks.py`)

| Code | Scope (key) | Severity | Condition (not checkable → no flag) | Cites (`evidence_row_ids`) | Expected count (denominator; spread) |
| --- | --- | --- | --- | --- | --- |
| `THRESHOLDS_INFERRED` | trial (`TRIAL_GUID`) | info | every recommendation | recommendations row | 72 of 72 |
| `AGGREGATE_LINKS_UNVERIFIED` | trial (`TRIAL_GUID`) | info | supplied GBV mean ≠ mean over observation-linked lines (±0.051) **or** supplied resistant % ≠ observation-linked % (< 0.01); needs both sides present | recommendations row + the trial's observation rows + those lines' genomics rows (21 today) | 72 of 72 (GBV 72, resistant 62) |
| `RATIONALE_READS_AS_PASS` | trial (`TRIAL_GUID`) | warning | rationale is text and reports all four met; verdict not PASS | recommendations row | 4 of 11 checkable (0037, 0038, 0046, 0052) |
| `OPS_OUTSIDE_TRIAL_YEAR` | operation (`OPERATION_GUID`) | warning | year(`OPERATION_DATE`) ≠ trial `START_YEAR`; needs both | operation row + trial row | 144 of 216; 48 trials (all 3 ops each: every op is dated 2026, those trials started 2024/2025) |
| `PLANNED_OPS_PAST_EXTRACT` | operation (`OPERATION_GUID`) | warning | PLANNED and dated before the extract (`lifecycle.snapshot_date`, 2026-09-26 12:00); needs a date | operation row | 114 of 114 PLANNED; 60 trials |
| `COMPLETE_TRIAL_HAS_PLANNED_OPS` | trial (`TRIAL_GUID`) | warning | trial COMPLETE with ≥ 1 PLANNED op | trial row + its PLANNED operation rows | 60 of 72 (all 72 are COMPLETE) |
| `OP_LINE_NOT_IN_TRIAL` | operation (`OPERATION_GUID`) | warning | op's (trial, line) not in observation links; needs both GUIDs | operation row (an absent link can't be cited) | 131 of 216; 72 trials, 96 lines |
| `LAB_NOT_TRIAL_LINKED` | line (`MATERIAL_GUID`) | info | line has ≥ 1 lab row (lab has no trial key) | the line's lab rows (2 or 3) | 150 of 150 lines (lab covers all germplasm) |

Adopted from the step 5 review (2026-09-29; counts re-measured on the v2 zip):

- **Output shape.** Each per-code function returns `dict[GUID, tuple[Flag, ...]]` keyed as in the table. `all_flags(t) -> FlagIndex` (frozen: `by_trial`, `by_operation`, `by_line`) combines them; the store calls it once at build. Flags are ordered by catalogue order, then evidence.
- **Catalogue.** `FLAG_CODES`: code → scope, severity, one-line meaning; tool docstrings and `uc4://rule/SYNTH_V1` list codes from it. `models.SEVERITIES = ("info", "warning")`; there is no "error", because flags never change a verdict.
- **Messages** are fixed templates with values formatted by `rules._num` (no numpy reprs, no `nan`), e.g. `"PLANTING on 2026-09-21 is outside trial start year 2025"`, `"Supplied GBV mean 105.4 ≠ 105.05 over the 10 observation-linked lines; resistant % 30 = 30"`, `"Trial is COMPLETE but 2 operations are still PLANNED"`.
- **Extract date** is dataset metadata (150 genomics rows share the latest `LAST_CHG_DATE`), exposed by `list_sources` and the rule resource, not cited as a row.
- **Reuse.** `lifecycle.py` gains a public `operation_checks(t) -> DataFrame`: one row per operation with `OPERATION_GUID`, `TRIAL_GUID`, `MATERIAL_GUID` and float `wrong_year`, `planned_past_extract`, `unlinked` (NaN = not checkable: missing date, `START_YEAR` or GUID). `_operation_rows` summarises it, so the extract date and each operation check are defined once and `chronology_checks.csv` still matches. The aggregate and rationale flags use `rules.genomics_reconciliation` and `rules.rationale_flags`, masking rows where either side is NaN (today a missing side reads as a mismatch). "Harvest before planting" (13 of 36) and the two extract checks with 0 violations are deliberately not flags.
- **`RATIONALE_READS_AS_PASS`** (4) is a subset of `Recommendation.rationale_omits` (33 trials, resistant % never mentioned). Both are kept: the field answers "what does the text leave out", the flag "where the text reads as a PASS".
- **Attachment (step 6).** `Recommendation.flags` = trial-scope flags only (Phase 3 copies it into the override log). `trial_view` adds the flags of its 3 operations; `line_view` adds `LAB_NOT_TRIAL_LINKED` and the flags of the line's 1-2 operations (`OP_LINE_NOT_IN_TRIAL` explains an operation whose trial is not among the line's observation-linked trials). Operation and lab `EvidenceRow.flags` carry their codes.

Flags never change the SYNTH_V1 verdict or colour (the supplied verdicts ignore them, and the engine must still match 72/72). Every trial carries at least 4 flags, so severity, not flag presence, marks what needs review.

## Steps (test first; commit after each)

Run tests with `uv run --project app pytest -q app/tests` from the repo root. The path matters: without it pytest also collects `analysis/uc4_eda/`, whose `test_rules.py` and `test_lifecycle.py` share basenames with ours (no `__init__.py`, so collection fails with "import file mismatch"). The EDA suite keeps its own command.

0. **Repo and environment (15 min).** `git init` at the repo root. `.gitignore`: `get_started/*.zip` (data clearance is still an open SME question), `.venv/`, `app/logs/`, `__pycache__/`. Set `UV_PROJECT_ENVIRONMENT` to a path outside OneDrive and note it in `app/README.md`. First commit: existing docs and EDA.
1. **Scaffold and client spike (30 min).** `uv init --package --name uc4-mcp app`; add `mcp[cli]>=2.2,<3`, `pandas`, dev `pytest`. A throwaway `ping` tool on `MCPServer`; `tests/test_smoke.py` calls it via `mcp.Client(server)`. Connect OpenCode to it over stdio once, to prove protocol compatibility with an `mcp` 2.x server now rather than at step 8. Record the working client config.
2. **Sources (45 min).** Port `member_stem`, `load_tables`, constants and `lab_trait_label`; rewrite `find_zip` (env var `UC4_ZIP`, then repo-root lookup). Add `_source_file`, `_line_no`, `ROW_KEYS`. Adopted from the step 2 review (2026-09-29):
   - **Keys as strings.** `load_tables` reads each `ROW_KEYS` column with `dtype=str` (observation `ID` otherwise loads as `int64`) and adds `_row_id` (str), so later steps read one column.
   - **Test scope.** `app/pyproject.toml` gets `[tool.pytest.ini_options] testpaths = ["tests"]`, `addopts = "--import-mode=importlib"`; run with `app/tests` (see above).
   - **`find_zip`.** `UC4_ZIP` wins; otherwise walk up from the current directory, then from `__file__`, to the first directory containing `get_started/`. More than one glob match without `UC4_ZIP` raises (no silent `sorted()[-1]`). Not found raises `FileNotFoundError` naming `UC4_ZIP`.
   - **Loader hardening.** Two CSV members with the same `member_stem` raise.
   - **`conftest.py`.** Session-scoped `tables` fixture; a missing zip fails with the `find_zip` message (the zip is git-ignored, so fresh clones need it).

   Tests: row counts; each `row_id` unique, non-null and a `str`; `_line_no` of first row = 2 and of last row = the member's physical line count (proves no record spans lines); every observation `GID` and operations/lab/genomics `MATERIAL_GUID` in germplasm; every trial GUID in recommendations and vice versa; every observation `ATTACHED_TO_FIELD_ENTITY_ID` and operations `TRIAL_GUID` in trial; no string cell contains U+FFFD; `UC4_ZIP` overrides lookup; missing zip and ambiguous glob raise; duplicate member stems raise; zip unchanged (SHA-256 taken *before* the test itself calls `load_tables`, not after the session fixture).
3. **Models (30 min).** *(Swapped with rules in the step 3 review: `explain()` returns these types.)* Dataclasses, envelope and `to_json_safe()`. `evidence_row_ids` (on `Recommendation` and `Flag`) are source-qualified, `"<source_file>#<row_id>"`, because `row_id` alone is ambiguous (`recommendations` and `trial` both key on `TRIAL_GUID`); add a helper that builds one from a table row. Tests: frozen; `numpy.int64`, `numpy.float64`, `NaN`, `NaT` convert to `int`, `float`, `None`, `None`; `json.dumps(..., allow_nan=False)` succeeds; the evidence-reference helper round-trips (step 6's "every EvidenceRow resolves back" test covers these references too).
4. **Rules and lifecycle (60 min).** Port `Rule`, `SYNTH_V1`, `criteria_flags`, `apply_rule`, `rationale_flags`, `threshold_intervals`, `trial_material_links`, `genomics_reconciliation` with `test_rules.py`; port `lifecycle.py` (including `stage_counts`, the per-file "what it lacks" text `list_sources` reuses in step 7) with `test_lifecycle.py`. Imports become `uc4_mcp.*`; ported tests use the session `tables` fixture instead of their module-level `load_tables(find_zip())`; the synthetic `tables()` in `test_lifecycle.py` stays (it covers "not checkable" cases the real data lacks). Add `explain(row, intervals) -> Recommendation` without flags (intervals precomputed from all 72 trials; the store fills flags later with `dataclasses.replace`). Adopted from the step 3 review (2026-09-29):
   - **Seven criteria, fixed order:** PASS `YIELD_T_HA >= 9`, `MOISTURE_PCT <= 22`, `DISEASE_SCORE <= 5`, `GENOMIC_BREEDING_VALUE_MEAN >= 102`, `RESISTANT_MATERIAL_PCT >= 50`; knockout `YIELD_T_HA < 7`, `DISEASE_SCORE > 7`. `field` is not unique, so brackets map by the criterion name in `rule_intervals.csv`, not by column. `query_trials missed=<field>` means the PASS criterion; knockouts are queried with `knockout=`.
   - **`rationale_omits`** = criteria the rule finds unmet (PASS criterion not met, or knockout triggered) that the text reports neither as met nor as unmet. Port an unmet-phrase map beside `RATIONALE_OK`: "yield below target", "moisture above target", "disease risk elevated", "genomic value below target" (with the four met phrases, the only eight phrases in the file). Resistant % is never mentioned, so `rationale_omits == ("RESISTANT_MATERIAL_PCT",)` for the 33 trials missing it (16 HOLD, 17 FAIL). The `RATIONALE_READS_AS_PASS` flag (renamed from `RATIONALE_OMITS_CRITERION` in the step 5 review) stays narrower (text says all four met, verdict not PASS: 4), because only there does the text read as a PASS.
   - **`reason`:** a FAIL names only its triggered knockouts, e.g. `"FAIL: disease score 7.7 > 7 (knockout, inferred threshold)"`; a HOLD lists every unmet PASS criterion in the fixed order; a PASS says all five met.
   - **`rule_version`** = `Rule.version` (`"SYNTH_V1 (inferred)"`); the file's `RULE_VERSION` is `"SYNTH_V1"`.
   - **Missing values** give `Criterion.value is None` (never `NaN`), `passed False`, `triggered False`.

   Tests: 72/72; every supplied `RULE_VERSION == "SYNTH_V1"` (a new rule fails loudly); `explain()` returns the 7 criteria in order; the three worked examples with exact values, all 7 `passed`/`triggered` and the exact `reason` (0001 is FAIL on the disease knockout 7.7 > 7 and also misses disease ≤ 5 and resistant 30 < 50; yield, moisture, GBV met; yield knockout not triggered); a row with `DISEASE_SCORE = NaN` is HOLD, never PASS, both disease criteria `value None`, `passed False`, `triggered False`; `rationale_omits` non-empty for 33 trials, `("RESISTANT_MATERIAL_PCT",)` for 0037; no rationale contradicts the rule (0 today); `threshold_intervals()` equals `rule_intervals.csv` (`pd.testing.assert_frame_equal`); `chronology_checks()` equals `chronology_checks.csv` on `checked`, `violations`, `not_checkable` and `example`.
5. **Checks (75 min).** Refactor `lifecycle.py` (add `operation_checks`, `_operation_rows` summarises it; update the "ported unchanged" docstring), then `checks.py` as in the Flags section: per-code functions, `all_flags() -> FlagIndex`, `FLAG_CODES`; `SEVERITIES` in `models.py`. Tests:
   - **Counts against the evidence record:** the five flags with a `chronology_checks.csv` row match its `violations`, and the flagged keys include its `example` (SYN-TR-0002, op `…000000000003`, SYN-TR-0001, op `…000000000001`, SYN-TR-0037). Hard-coded where the CSV has nothing: 72 (`THRESHOLDS_INFERRED`), 72 (`AGGREGATE_LINKS_UNVERIFIED`: GBV 72, resistant 62), 150 (`LAB_NOT_TRIAL_LINKED`), and the spread (48, 60, 72 trials; 96 lines).
   - **Denominators:** 72 trials COMPLETE; lab lines = germplasm lines = 150. A data change then fails loudly instead of changing what 60/72 means.
   - **Not checkable → no flag:** extend the synthetic tables in `test_lifecycle.py` with a `lab` table; one case per flag: `START_YEAR` NaN, `OPERATION_DATE` NaN, op `MATERIAL_GUID` None, trial with no observation links, supplied GBV NaN, rationale NaN, line with no lab rows, trial not COMPLETE.
   - **Output:** every `Flag` passes `json.dumps(to_json_safe(...), allow_nan=False)`; no message contains `np.` or `nan`; severity in `SEVERITIES`; every `evidence_row_ids` entry parses with `parse_evidence_ref`; order is deterministic; `rules.py` does not import `checks`.
   - `chronology_checks()` still equals `chronology_checks.csv` after the refactor.
6. **Store (60 min).** `EvidenceStore.from_zip()` builds indexes once. `resolve_trial/line(query) -> Resolution`; `trial_view`, `line_view`, `recommendation`, `query_trials`, `baseline`. Tests: resolution cases from the tool table (exact ID, exact GUID, case-insensitive, `"0037"` listed once, ID fragment → many, `"003"` not matching GUIDs, none); `trial_view` for every trial has 10 lines and 3 ops; every `EvidenceRow` resolves back to a real row (`source_file` + `row_id` found in its table); lab rows never carry a `trial_guid`; `json.dumps(to_json_safe(...), allow_nan=False)` succeeds for all 72 trial views, 72 recommendations and 150 line views; `query_trials` counts equal the tool table; for every trial the stored `Recommendation` equals `explain()` in every field except `flags`, and `baseline` is still 72/72 with flags attached; trial and line views carry the flags described in the Flags section (attachment).
7. **Server (45 min).** `MCPServer` tools as thin wrappers over the store (no logic in `server.py`), each with the docstring content above. Logging goes to `app/logs/uc4_mcp.log`, never stdout. Tests: `mcp.Client(server)` in-process lists the 8 tools and 2 resources and calls each with the acceptance inputs; every response has the envelope shape.
8. **Stdio test, run commands, docs (45 min).** `[project.scripts] uc4-mcp = "uc4_mcp.server:main"`; `--transport stdio` (default) or `http --port 8765`. `tests/test_stdio.py` launches `uc4-mcp` as a subprocess via `mcp.Client(StdioServerParameters(...))` and calls `baseline_check`; a stray print would break this. `app/README.md`: prerequisites (uv, Node for the Inspector), `UV_PROJECT_ENVIRONMENT`, run commands, the OpenCode `opencode.json` entry from step 1, the Claude Code `claude mcp add` line, and the n8n MCP Client URL.
9. **Manual check (15 min).** MCP Inspector (`uv run --project app mcp dev app/src/uc4_mcp/server.py`; confirm the 2.x CLI command in step 1): call `score_trial SYN-TR-0037`, `find_trial SYN-TR-003`, `query_trials knockout=disease only=true`. Save a screenshot for the deck, log the session in [PROMPT_LOG.md](../../team/PROMPT_LOG.md).

Estimated total: about 7 hours.

## Exit criteria

- [ ] `uv run --project app pytest -q app/tests` passes, including the ported 72/72 test.
- [ ] `baseline_check` returns 72 matched, 0 mismatches.
- [ ] `score_trial` for 0003, 0037 and 0001 returns the verdict, every criterion with value, threshold and bracket, and source row IDs.
- [ ] `find_trial "SYN-TR-003"` returns 10 candidates, not a guess.
- [ ] Every flag count and every `query_trials` count equals the tables above.
- [ ] Every tool output is valid JSON (`allow_nan=False`) and uses the envelope.
- [ ] The stdio subprocess test passes, and OpenCode has connected to the server.
- [ ] Every tool docstring states grain, units, "inferred" and an example input.
- [ ] No tool writes to disk except the log; the zip is unchanged.
- [ ] `app/README.md` lets a teammate connect OpenCode to the server in under 5 minutes.

## Hand-off to Phases 2 and 3

- Phase 2 system prompt lists the 8 tools and requires the answer to cite `source_file` + `row_id` for every number.
- Phase 3 reads `Recommendation` and trial/line views directly from `EvidenceStore` (import) or over HTTP MCP; the override record copies `Recommendation` unchanged.
