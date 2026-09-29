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
    checks.py             # consistency flags, built on lifecycle.py
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
    field: str; label: str; value: float | None; test: str   # ">=", "<=", "<", ">"
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

| Code | Scope | Condition | Expected count |
| --- | --- | --- | --- |
| `THRESHOLDS_INFERRED` | every recommendation | always | 72 |
| `AGGREGATE_LINKS_UNVERIFIED` | trial | supplied GBV mean ≠ mean over observation-linked lines (±0.051) | 72 |
| `RATIONALE_OMITS_CRITERION` | trial | rationale says all four met, verdict not PASS | 4 (0037, 0038, 0046, 0052) |
| `OPS_OUTSIDE_TRIAL_YEAR` | operation | year(`OPERATION_DATE`) ≠ trial `START_YEAR` | 144 of 216 |
| `PLANNED_OPS_PAST_EXTRACT` | operation | PLANNED and dated before the extract (`lifecycle.snapshot_date`: latest `LAST_CHG_DATE` in any table, 2026-09-26 12:00) | 114 of 114 |
| `COMPLETE_TRIAL_HAS_PLANNED_OPS` | trial | trial COMPLETE with ≥ 1 PLANNED op | 60 of 72 |
| `OP_LINE_NOT_IN_TRIAL` | operation | op's (trial, line) not in observation links | 131 of 216 |
| `LAB_NOT_TRIAL_LINKED` | line | always (lab has no trial key) | 150 |

Expected counts come from `analysis/uc4_eda/tables/chronology_checks.csv` and `genomics_reconciliation.csv`. The operation flags reuse the ported `lifecycle.py` logic (`snapshot_date`, `operations_with_trial`, `before`) rather than re-deriving it, so the extract date is defined once. Flags are information for amber review; they never change the SYNTH_V1 verdict (the supplied verdicts ignore them, and the engine must still match 72/72).

## Steps (test first; commit after each)

Run tests with `uv run --project app pytest -q` from the repo root.

0. **Repo and environment (15 min).** `git init` at the repo root. `.gitignore`: `get_started/*.zip` (data clearance is still an open SME question), `.venv/`, `app/logs/`, `__pycache__/`. Set `UV_PROJECT_ENVIRONMENT` to a path outside OneDrive and note it in `app/README.md`. First commit: existing docs and EDA.
1. **Scaffold and client spike (30 min).** `uv init --package --name uc4-mcp app`; add `mcp[cli]>=2.2,<3`, `pandas`, dev `pytest`. A throwaway `ping` tool on `MCPServer`; `tests/test_smoke.py` calls it via `mcp.Client(server)`. Connect OpenCode to it over stdio once, to prove protocol compatibility with an `mcp` 2.x server now rather than at step 8. Record the working client config.
2. **Sources (45 min).** Port `member_stem`, `load_tables`, constants and `lab_trait_label`; rewrite `find_zip` (env var `UC4_ZIP`, then repo-root lookup). Add `_source_file`, `_line_no`, `ROW_KEYS`. Tests: row counts; each `row_id` unique and non-null; `_line_no` of first row = 2; every observation `GID` and operations/lab/genomics `MATERIAL_GUID` in germplasm; every trial GUID in recommendations; zip file unchanged (mtime + size before and after).
3. **Rules and lifecycle (60 min).** Port `Rule`, `SYNTH_V1`, `criteria_flags`, `apply_rule`, `rationale_flags`, `threshold_intervals`, `trial_material_links`, `genomics_reconciliation` with `test_rules.py`; port `lifecycle.py` with `test_lifecycle.py`. Add `explain(row) -> Recommendation` without flags. Tests: 72/72; the three worked examples (exact values, `passed`/`triggered` per criterion); a row with `DISEASE_SCORE = NaN` is HOLD, never PASS, with no knockout triggered; `threshold_intervals()` equals `rule_intervals.csv`; `chronology_checks()` equals `chronology_checks.csv` counts.
4. **Models (30 min).** Dataclasses, envelope and `to_json_safe()`. Tests: frozen; `numpy.int64`, `numpy.float64`, `NaN`, `NaT` convert to `int`, `float`, `None`, `None`; `json.dumps(..., allow_nan=False)` succeeds.
5. **Checks (45 min).** One function per flag returning `dict[key, list[Flag]]`, built on the ported lifecycle helpers. Tests assert each expected count in the table above.
6. **Store (60 min).** `EvidenceStore.from_zip()` builds indexes once. `resolve_trial/line(query) -> Resolution`; `trial_view`, `line_view`, `recommendation`, `query_trials`, `baseline`. Tests: resolution cases from the tool table (exact ID, exact GUID, case-insensitive, `"0037"` listed once, ID fragment → many, `"003"` not matching GUIDs, none); `trial_view` for every trial has 10 lines and 3 ops; every `EvidenceRow` resolves back to a real row (`source_file` + `row_id` found in its table); lab rows never carry a `trial_guid`; `json.dumps(to_json_safe(...), allow_nan=False)` succeeds for all 72 trial views, 72 recommendations and 150 line views; `query_trials` counts equal the tool table.
7. **Server (45 min).** `MCPServer` tools as thin wrappers over the store (no logic in `server.py`), each with the docstring content above. Logging goes to `app/logs/uc4_mcp.log`, never stdout. Tests: `mcp.Client(server)` in-process lists the 8 tools and 2 resources and calls each with the acceptance inputs; every response has the envelope shape.
8. **Stdio test, run commands, docs (45 min).** `[project.scripts] uc4-mcp = "uc4_mcp.server:main"`; `--transport stdio` (default) or `http --port 8765`. `tests/test_stdio.py` launches `uc4-mcp` as a subprocess via `mcp.Client(StdioServerParameters(...))` and calls `baseline_check`; a stray print would break this. `app/README.md`: prerequisites (uv, Node for the Inspector), `UV_PROJECT_ENVIRONMENT`, run commands, the OpenCode `opencode.json` entry from step 1, the Claude Code `claude mcp add` line, and the n8n MCP Client URL.
9. **Manual check (15 min).** MCP Inspector (`uv run --project app mcp dev app/src/uc4_mcp/server.py`; confirm the 2.x CLI command in step 1): call `score_trial SYN-TR-0037`, `find_trial SYN-TR-003`, `query_trials knockout=disease only=true`. Save a screenshot for the deck, log the session in [PROMPT_LOG.md](../../team/PROMPT_LOG.md).

Estimated total: about 6.5 hours.

## Exit criteria

- [ ] `uv run --project app pytest -q` passes, including the ported 72/72 test.
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
