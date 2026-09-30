# Phase 3: Breeder screen and override log

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Parent:** [task.md](task.md) · **Owner:** Screen and log · **Target:** Wed 2026-09-30 → Thu 2026-10-01 · **Consumers:** Phase 4 (evaluation reads the override log), Phase 5 (demo "Challenge and override" beat).

**Goal:** A breeder opens one trial and sees:

- its colour and a one-line reason
- every criterion against its threshold
- the ten linked lines, the operations and the flags, each value traceable to its source row

The breeder then records a decision (PASS, HOLD or FAIL) with a required reason. The decision is appended to a log that keeps a full copy of the engine's recommendation. The source data and the recommendation are never changed.

**Architecture:** There is one process: `uc4-ask serve` on port 8766, the FastAPI app from Phase 2.

- It gains read routes over `EvidenceStore` (the Phase 1 hand-off allows direct import), one write route and a static page.
- The page is plain HTML with vanilla JS and CSS, shipped inside the package. It has no build step and no CDN, so it works offline.
- The only write in the whole app is `DecisionLog.append`, which adds one JSON line to `app/data/decisions.jsonl`. Nothing in the code can update or delete a line.
- The page calls the existing `POST /ask` for the question box; `/ask` is unchanged.

**Tech Stack:** Python ≥ 3.12, uv, FastAPI and `StaticFiles` (both already dependencies), pydantic v2, pytest with `fastapi.testclient`. No new runtime dependencies. The browser walkthrough uses Claude in Chrome.

**Spec:** [task.md](task.md) (Phase 3 row, non-negotiables), [ROLES.md role 3 and the "Override record" contract](../../team/ROLES.md), [uc4 README "Proposed hackathon MVP" step 5, "Suggested minimal screen" and "Validate the demo"](../../use-cases/uc4/README.md#proposed-hackathon-mvp), [phase-1 hand-off](phase-1-mcp-data-layer.md#hand-off-to-phases-2-and-3), [phase-2 hand-off](phase-2-nl-agent.md#hand-off-to-phase-3).

**Exit criteria (from task.md, made checkable):**

- [x] An override without a reason is rejected, and nothing is written. Tested by `test_blank_or_short_reason_is_rejected_and_nothing_written` (Task 1) and `test_post_without_reason_is_422_and_log_untouched` (Task 2). It is also rejected in the browser (Task 5): scenario 7 in [phase3_walkthrough.md](../../team/phase3_walkthrough.md), log file absent afterwards.
- [x] Each log line keeps the original recommendation (a full copy), the decision, the reason, the user and the timestamp. Tested by `test_record_copies_the_recommendation` (Task 1) and `test_post_then_get_decisions` (Task 2). Walkthrough scenario 8 and the log-file evidence in [phase3_walkthrough.md](../../team/phase3_walkthrough.md).
- [x] The source data and the recommendation never change:
  - `test_store_recommendation_unchanged_by_decisions` (Task 1)
  - `test_earlier_lines_are_never_rewritten` (Task 1)
  - no PUT, PATCH or DELETE routes (`test_no_update_or_delete_routes`, Task 2)
  - the existing `test_zip_unchanged_by_loading`
- [x] The screen shows the trial view described in the uc4 README "Suggested minimal screen": colour and reason, the criteria table, the ten lines with genomics and lab, and the "Record decision" action. The Task 5 walkthrough covers every scenario in "Validate the demo" (11 of 11 observed, see [phase3_walkthrough.md](../../team/phase3_walkthrough.md)); Scenario 11 also has a live cited answer. Six trusted mouse/keyboard checks pass in [test_browser.py](../../app/tests/test_browser.py).
- [x] Six deck screenshots in [team/screenshots](../../team/screenshots/) and the [walkthrough GIF](../../team/screenshots/phase3_walkthrough.gif), reproducible with [capture.py](../../team/screenshots/capture.py). Headless Chrome avoids the minimized-window problem. GIF verified: eight frames, 16 seconds, 297,540 bytes.
- [x] The offline suite is green: `uv run --project app pytest -q app/tests`. 393 passed, 7 deselected on `demo-live-ask` (six browser tests and one live test are opt-in); `uv run --project app --group browser pytest -q -m browser app/tests/test_browser.py`: 6 passed.

## Decisions (made while planning, 2026-09-30)

| Decision | Why |
| --- | --- |
| Static HTML + vanilla JS page served by the Phase 2 FastAPI app | One process and one port. There is no Node toolchain two days before the demo. The page is tested with `TestClient`, and the page itself is checked in a real browser |
| The breeder decides PASS, HOLD or FAIL, and a reason is required every time; `overrides` = decision ≠ engine verdict | The same vocabulary as the engine keeps the before/after comparison readable. A reason on agreement too makes every decision auditable |
| Reason is 5–1000 characters after trimming | Rejects blank, "x" and "." while accepting a short real reason ("resistant % fine in 2026 rep") |
| The log is JSONL at `app/data/decisions.jsonl` (git-ignored; `UC4_DECISION_LOG` overrides it) | Append-only by construction (`open("a")`), easy to show in the demo and to diff. Decisions are personal records and stay out of git, like the data |
| The record copies `to_json_safe(Recommendation)` in full | ROLES.md: "`recommendation` (copied, immutable)". A later rule change cannot rewrite what the breeder saw |
| `user` is a free-text demo alias (1–80 characters) with no authentication | The uc4 README allows "breeder identity (or demo alias)". The app is local-only (CORS allows localhost only) |
| The server sets `timestamp` (UTC, ISO, seconds); the client never sends it | "Who and when" must not be client-editable |
| `material_guid` is optional and must be one of the trial's 10 observation-linked lines | It is in the ROLES.md contract. Verdicts are per trial, so a line only annotates a trial decision |
| Read routes return the Phase 1 envelope with HTTP 200; the write route uses 201 / 404 / 409 / 422 | Reads mirror `/ask` (the screen renders `many` as "which one?"). A failed write needs a status the page can branch on |
| The page uses only `textContent` and `createElement`, never `innerHTML` | Reasons and the data are untrusted text; this is enforced by a test |
| The page uses 18 px base text, and the verdict shows as a word plus a shape, never colour alone | The uc4 README calls for large, readable text for the breeder persona. It also keeps the page accessible |

## Global Constraints

- Run tests from the repo root: `uv run --project app pytest -q app/tests`. `UV_PROJECT_ENVIRONMENT` points outside OneDrive, as in `app/README.md`.
- No new runtime dependency. `fastapi.staticfiles` and pydantic ship with FastAPI.
- Engine code and data never change. `store.py`, `rules.py`, `checks.py` and `sources.py` are read-only for this phase. The zip is never extracted or modified.
- The only file the app writes, apart from logs, is the decision log.
- Match the existing code style: `from __future__ import annotations`, type hints on every signature, Google-style docstrings on public functions, lines ≤ 100 characters.
- Commit after each task. The subject style follows the log (`feat(app): …`, `docs(plan): …`). Every commit message ends with these two lines:

  ```text
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01BrKqpT3s5JdaREVasBh7Mb
  ```

## Review Focus

These inputs are implied by the spec but no happy-path test exercises them; they are the most likely to fail first. Each has a test in the task named.

1. **Whitespace-only reason** (`"     "`) passes a naive `min_length=5`. The fix is to trim first. Covered by Task 1 `test_blank_or_short_reason_is_rejected_and_nothing_written` and Task 2 `test_post_without_reason_is_422_and_log_untouched`.
2. **Double submit** (a double click): the log is append-only, so two records are expected and both are kept. The page disables the button while a request is in flight. Covered by Task 2 `test_double_submit_keeps_both`.
3. **Trial sent by GUID vs ID vs fragment**: all resolve to the same `trial_guid`, and an ambiguous fragment is refused with candidates, never guessed. Covered by Task 1 `test_trial_by_id_guid_or_fragment` and `test_ambiguous_or_unknown_trial_is_refused_with_candidates`.
4. **A reason containing HTML** (`<img src=x onerror=alert(1)>`) is stored verbatim and shown as text. Covered by Task 2 `test_html_in_reason_is_stored_verbatim` and Task 3 `test_app_js_never_uses_inner_html`, and checked in the browser in Task 5.
5. **First write with no `app/data/` directory**: the directory is created. Covered by Task 1 `test_first_append_creates_the_directory`.
6. **`/ask` unavailable (503)**: the rest of the screen works and decisions can still be recorded. Covered by Task 2 `test_reads_and_decisions_work_without_a_model`.

## Layout

```text
app/
  data/decisions.jsonl          # the override log (git-ignored; created on first decision)
  src/uc4_mcp/
    models.py                   # modified: OverrideRecord                        (Task 1)
    decisions.py                # DecisionLog, record_decision, DecisionError      (Task 1)
    api.py                      # modified: read routes, POST /decisions, /       (Tasks 2-3)
    cli.py                      # modified: serve preloads the store, prints URL  (Task 4)
    static/
      index.html  app.js  style.css                                                (Task 3)
  tests/
    test_decisions.py                                                              (Task 1)
    test_api.py                 # extended                                         (Task 2)
    test_screen.py                                                                 (Task 3)
```

---

### Task 1: Override record and append-only log

**Files:**
- Create: `app/src/uc4_mcp/decisions.py`, `app/tests/test_decisions.py`
- Modify: `app/src/uc4_mcp/models.py`, `.gitignore`

**Interfaces:**
- Consumes: `EvidenceStore.resolve_trial`, `.recommendation`, `.trial_view`; `models.to_json_safe`, `Candidate`.
- Produces:
  - `models.DECISIONS = ("PASS", "HOLD", "FAIL")`.
  - `@dataclass(frozen=True) models.OverrideRecord(decision_id: str, trial_guid: str, trial_id: str, material_guid: str | None, recommendation: dict[str, Any], decision: str, overrides: bool, reason: str, user: str, timestamp: str)`.
  - `decisions.DEFAULT_LOG: Path` (`app/data/decisions.jsonl`), `decisions.log_path(env: Mapping[str, str] = os.environ) -> Path`, and `REASON_MIN = 5`, `REASON_MAX = 1000`, `USER_MAX = 80`.
  - `class DecisionError(ValueError)` with `.envelope: dict[str, Any] | None`. When set, it is the Phase 1 `many`/`none` envelope for the trial query.
  - `class DecisionLog(path: Path)` with:
    - `.path`
    - `append(record: OverrideRecord) -> None`
    - `read(trial_guid: str | None = None) -> list[OverrideRecord]`
  - `utcnow() -> str`.
  - `record_decision(store, log, *, trial: str, decision: str, reason: str, user: str, material_guid: str | None = None, now: Callable[[], str] = utcnow) -> OverrideRecord`.

- [ ] **Step 1: Ignore the log.** Append this to `.gitignore`:

```gitignore
# Breeder decisions (Phase 3 override log): personal records, like the data.
app/data/
```

- [ ] **Step 2: Write the failing tests** in `app/tests/test_decisions.py`

```python
"""Task 1: the override record and the append-only decision log."""

import json
from pathlib import Path

import pytest

from uc4_mcp.decisions import DecisionError, DecisionLog, log_path, record_decision
from uc4_mcp.models import OverrideRecord, to_json_safe
from uc4_mcp.store import EvidenceStore

NOW = "2026-10-01T09:00:00+00:00"


def decide(store: EvidenceStore, log: DecisionLog, **kw: object) -> OverrideRecord:
    args = {"trial": "SYN-TR-0037", "decision": "PASS", "user": "breeder-a",
            "reason": "Resistant % acceptable given the 2026 disease pressure"} | kw
    return record_decision(store, log, now=lambda: NOW, **args)


@pytest.fixture
def log(tmp_path: Path) -> DecisionLog:
    return DecisionLog(tmp_path / "data" / "decisions.jsonl")


def test_record_copies_the_recommendation(store: EvidenceStore, log: DecisionLog) -> None:
    r = decide(store, log)
    guid = store.resolve_trial("SYN-TR-0037").guid
    assert (r.trial_guid, r.trial_id, r.decision, r.user, r.timestamp) == (
        guid, "SYN-TR-0037", "PASS", "breeder-a", NOW)
    assert r.recommendation == to_json_safe(store.recommendation(guid))
    assert r.recommendation["verdict"] == "HOLD" and r.overrides is True
    assert len(r.decision_id) == 32 and r.material_guid is None


def test_agreeing_is_not_an_override(store: EvidenceStore, log: DecisionLog) -> None:
    assert decide(store, log, decision="HOLD").overrides is False


@pytest.mark.parametrize("reason", ["", "     ", "abcd", "  ab  "])
def test_blank_or_short_reason_is_rejected_and_nothing_written(
        store: EvidenceStore, log: DecisionLog, reason: str) -> None:
    with pytest.raises(DecisionError, match="reason"):
        decide(store, log, reason=reason)
    assert not log.path.exists()


def test_reason_is_trimmed_and_capped(store: EvidenceStore, log: DecisionLog) -> None:
    assert decide(store, log, reason="  keep it  ").reason == "keep it"
    with pytest.raises(DecisionError, match="reason"):
        decide(store, log, reason="x" * 1001)


@pytest.mark.parametrize("kw,match", [({"decision": "MAYBE"}, "decision"),
                                      ({"user": " "}, "user"),
                                      ({"user": "u" * 81}, "user")])
def test_bad_decision_or_user_is_rejected(store: EvidenceStore, log: DecisionLog,
                                         kw: dict, match: str) -> None:
    with pytest.raises(DecisionError, match=match):
        decide(store, log, **kw)
    assert not log.path.exists()


def test_trial_by_id_guid_or_fragment(store: EvidenceStore, log: DecisionLog) -> None:
    guid = store.resolve_trial("SYN-TR-0037").guid
    got = {decide(store, log, trial=q).trial_guid for q in ("SYN-TR-0037", guid, "0037")}
    assert got == {guid}


@pytest.mark.parametrize("query,status,n", [("SYN-TR-003", "many", 10), ("XYZ", "none", 0)])
def test_ambiguous_or_unknown_trial_is_refused_with_candidates(
        store: EvidenceStore, log: DecisionLog, query: str, status: str, n: int) -> None:
    with pytest.raises(DecisionError) as e:
        decide(store, log, trial=query)
    assert e.value.envelope["status"] == status
    assert len(e.value.envelope.get("candidates", [])) == n
    assert not log.path.exists()


def test_line_must_belong_to_the_trial(store: EvidenceStore, log: DecisionLog) -> None:
    view = store.trial_view(store.resolve_trial("SYN-TR-0037").guid)
    mine = view.lines[0].material_guid
    assert decide(store, log, material_guid=mine).material_guid == mine
    other = next(g for g in store.line_guids if g not in {l.material_guid for l in view.lines})
    with pytest.raises(DecisionError, match="line"):
        decide(store, log, material_guid=other)


def test_earlier_lines_are_never_rewritten(store: EvidenceStore, log: DecisionLog) -> None:
    decide(store, log)
    before = log.path.read_bytes()
    decide(store, log, decision="HOLD")
    after = log.path.read_bytes()
    assert after.startswith(before) and after.count(b"\n") == 2


def test_first_append_creates_the_directory(store: EvidenceStore, log: DecisionLog) -> None:
    assert not log.path.parent.exists()
    decide(store, log)
    assert log.path.is_file()


def test_read_round_trips_in_order_and_filters(store: EvidenceStore,
                                               log: DecisionLog) -> None:
    a = decide(store, log)
    b = decide(store, log, trial="SYN-TR-0003", decision="PASS")
    assert log.read() == [a, b]
    assert log.read(a.trial_guid) == [a]
    for line in log.path.read_text(encoding="utf-8").splitlines():
        json.loads(line)  # one JSON object per line
    json.dumps(to_json_safe(a), allow_nan=False)


def test_malformed_line_names_its_number(store: EvidenceStore, log: DecisionLog) -> None:
    decide(store, log)
    with log.path.open("a", encoding="utf-8") as f:
        f.write("{not json\n")
    with pytest.raises(ValueError, match="line 2"):
        log.read()


def test_missing_log_reads_empty(log: DecisionLog) -> None:
    assert log.read() == []


def test_store_recommendation_unchanged_by_decisions(store: EvidenceStore,
                                                     log: DecisionLog) -> None:
    guid = store.resolve_trial("SYN-TR-0037").guid
    before = to_json_safe(store.recommendation(guid))
    decide(store, log)
    assert to_json_safe(store.recommendation(guid)) == before


def test_log_path_env_override(tmp_path: Path) -> None:
    assert log_path({"UC4_DECISION_LOG": str(tmp_path / "x.jsonl")}) == tmp_path / "x.jsonl"
    assert log_path({}).parts[-2:] == ("data", "decisions.jsonl")
```

- [ ] **Step 3: Run to verify failure.** Run `uv run --project app pytest -q app/tests/test_decisions.py`. Expected: `ModuleNotFoundError: No module named 'uc4_mcp.decisions'`.

- [ ] **Step 4: Add the record** to `app/src/uc4_mcp/models.py`, after `LineView`:

```python
DECISIONS = ("PASS", "HOLD", "FAIL")


@dataclass(frozen=True)
class OverrideRecord:
    """A breeder's decision on a trial; ``recommendation`` is the engine output as shown.

    Verdicts are per trial; ``material_guid`` only annotates which line prompted it.
    """

    decision_id: str
    trial_guid: str
    trial_id: str
    material_guid: str | None
    recommendation: dict[str, Any]  # to_json_safe(Recommendation), copied at decision time
    decision: str  # one of DECISIONS
    overrides: bool  # decision differs from recommendation["verdict"]
    reason: str
    user: str  # demo alias, not authenticated
    timestamp: str  # UTC ISO, set by the server
```

- [ ] **Step 5: Implement** `app/src/uc4_mcp/decisions.py`

```python
"""The breeder's decisions: an append-only JSONL log beside, never inside, the evidence.

The engine's recommendation is copied into each record, so the log shows what the breeder
saw; nothing here can change the source data, the recommendation or an earlier line.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import threading
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from uc4_mcp.models import DECISIONS, OverrideRecord, to_json_safe
from uc4_mcp.store import EvidenceStore

DEFAULT_LOG = Path(__file__).resolve().parents[2] / "data" / "decisions.jsonl"
REASON_MIN, REASON_MAX, USER_MAX = 5, 1000, 80


class DecisionError(ValueError):
    """A decision was refused; the message is safe to show. ``envelope`` is set when the
    trial query was ambiguous or unknown (the Phase 1 ``many``/``none`` envelope)."""

    def __init__(self, message: str, envelope: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.envelope = envelope


def log_path(env: Mapping[str, str] = os.environ) -> Path:
    """``UC4_DECISION_LOG`` if set, else ``app/data/decisions.jsonl``."""
    return Path(env["UC4_DECISION_LOG"]) if env.get("UC4_DECISION_LOG") else DEFAULT_LOG


def utcnow() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


class DecisionLog:
    """One JSON object per line, appended only: there is no update or delete."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def append(self, record: OverrideRecord) -> None:
        line = json.dumps(to_json_safe(record), ensure_ascii=False, allow_nan=False)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="\n") as f:
                f.write(line + "\n")
                f.flush()
                os.fsync(f.fileno())

    def read(self, trial_guid: str | None = None) -> list[OverrideRecord]:
        """Records in the order written, optionally for one trial.

        Raises:
            ValueError: A line is not a record (names the line number; hand edits only).
        """
        if not self.path.exists():
            return []
        out = []
        with self._lock:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        for n, line in enumerate(lines, start=1):
            try:
                record = OverrideRecord(**json.loads(line))
            except (json.JSONDecodeError, TypeError) as e:
                raise ValueError(f"{self.path.name} line {n} is not a decision: {e}") from e
            if trial_guid is None or record.trial_guid == trial_guid:
                out.append(record)
        return out


def _text(value: str, name: str, low: int, high: int) -> str:
    value = value.strip()
    if not low <= len(value) <= high:
        raise DecisionError(f"A {name} of {low}-{high} characters is required")
    return value


def record_decision(store: EvidenceStore, log: DecisionLog, *, trial: str, decision: str,
                    reason: str, user: str, material_guid: str | None = None,
                    now: Callable[[], str] = utcnow) -> OverrideRecord:
    """Validate, copy the recommendation, append one record and return it.

    Raises:
        DecisionError: Reason or user missing or out of range, unknown decision, trial
            ambiguous or not found (``envelope`` set), or a line not in the trial.
    """
    reason = _text(reason, "reason", REASON_MIN, REASON_MAX)
    user = _text(user, "user name", 1, USER_MAX)
    if decision not in DECISIONS:
        raise DecisionError(f"decision must be one of {', '.join(DECISIONS)}")
    res = store.resolve_trial(trial)
    if res.status != "ok":
        envelope = store.find_trial(trial)
        raise DecisionError(res.message, to_json_safe(envelope))
    guid = str(res.guid)
    if material_guid is not None and material_guid not in {
            line.material_guid for line in store.trial_view(guid).lines}:
        raise DecisionError("That line is not one of this trial's 10 linked lines")
    rec = to_json_safe(store.recommendation(guid))
    record = OverrideRecord(
        decision_id=uuid.uuid4().hex, trial_guid=guid, trial_id=rec["trial_id"],
        material_guid=material_guid, recommendation=rec, decision=decision,
        overrides=decision != rec["verdict"], reason=reason, user=user, timestamp=now())
    log.append(record)
    return record
```
- [ ] **Step 6: Run the tests.** Run `uv run --project app pytest -q app/tests/test_decisions.py`, then the full suite. Expected: the new tests pass, and the rest stay at 331 passed and 1 deselected.

- [ ] **Step 7: Commit**

```powershell
git add .gitignore app/src/uc4_mcp/models.py app/src/uc4_mcp/decisions.py app/tests/test_decisions.py
git commit -m "feat(app): append-only override log with the recommendation copied in" -m "<trailer lines>"
```

---

### Task 2: HTTP read and decision routes

**Files:**
- Modify: `app/src/uc4_mcp/api.py`, `app/tests/test_api.py`

**Interfaces:**
- Consumes: Task 1; `EvidenceStore.trial_guids`, `.recommendation`, `.get_trial`, `.get_line`; `server._default_store`.
- Produces:
  - `create_app(make_model, server=None, settings=AgentSettings(), *, get_store: Callable[[], EvidenceStore] | None = None, log: DecisionLog | None = None) -> FastAPI`. The keyword-only additions keep existing callers working. The defaults are `server._default_store` and `DecisionLog(log_path())`.
  - `class DecisionRequest(BaseModel)` with these fields:
    - `trial`: 1–80 characters
    - `decision`: `Literal["PASS", "HOLD", "FAIL"]`
    - `reason`: trimmed, 5–1000 characters
    - `user`: trimmed, 1–80 characters
    - `material_guid`: `str | None`
  - Routes:

| Route | Response |
| --- | --- |
| `GET /trials` | `[{trial_id, trial_guid, verdict, colour, reason, latest_decision}]` (72, sorted by ID; `latest_decision` is the last record for that trial or `null`) |
| `GET /trials/{query}` | The Phase 1 envelope, plus `decisions` (list; present when `ok`), always 200 |
| `GET /lines/{query}` | The Phase 1 envelope, always 200 |
| `POST /decisions` | 201 with the record. 422 for a pydantic or `DecisionError` failure. 409 with the envelope for an ambiguous trial. 404 with the envelope for an unknown trial |
| `GET /decisions?trial=<query>` | Records in the order appended (all when `trial` is absent; the query is resolved like the others) |

- [ ] **Step 1: Write the failing tests.** Add these to `app/tests/test_api.py`, with `from uc4_mcp.decisions import DecisionLog` and `from pathlib import Path` in the imports:

```python
REASON = "Resistant % acceptable given the 2026 disease pressure"


def screen_client(store: EvidenceStore, tmp_path: Path,
                  chat: FakeChat | None = None) -> tuple[TestClient, DecisionLog]:
    log = DecisionLog(tmp_path / "decisions.jsonl")
    app = create_app(lambda: chat or FakeChat([]), create_server(lambda: store),
                     get_store=lambda: store, log=log)
    return TestClient(app), log


def post(client: TestClient, **kw: object):
    body = {"trial": "SYN-TR-0037", "decision": "PASS", "reason": REASON,
            "user": "breeder-a"} | kw
    return client.post("/decisions", json=body)


def test_trials_lists_all_72_with_verdicts(store: EvidenceStore, tmp_path: Path) -> None:
    rows = screen_client(store, tmp_path)[0].get("/trials").json()
    assert len(rows) == 72 and rows[0]["trial_id"] == "SYN-TR-0001"
    counts = {v: sum(r["verdict"] == v for r in rows) for v in ("PASS", "HOLD", "FAIL")}
    assert counts == {"PASS": 7, "HOLD": 35, "FAIL": 30}
    assert {r["colour"] for r in rows} == {"green", "amber", "red"}
    assert all(r["latest_decision"] is None for r in rows)


def test_trial_view_and_ambiguous_query(store: EvidenceStore, tmp_path: Path) -> None:
    client = screen_client(store, tmp_path)[0]
    body = client.get("/trials/SYN-TR-0037").json()
    assert body["status"] == "ok" and body["decisions"] == []
    view = body["result"]
    assert len(view["lines"]) == 10 and len(view["operations"]) == 3
    assert view["recommendation"]["verdict"] == "HOLD"
    many = client.get("/trials/SYN-TR-003").json()
    assert many["status"] == "many" and len(many["candidates"]) == 10
    assert client.get("/trials/XYZ").json()["status"] == "none"


def test_line_view(store: EvidenceStore, tmp_path: Path) -> None:
    body = screen_client(store, tmp_path)[0].get("/lines/SYN-MZ-00001").json()
    assert body["status"] == "ok" and "per trial" in body["result"]["note"]


@pytest.mark.parametrize("kw", [{"reason": ""}, {"reason": "     "}, {"reason": "abcd"},
                                {"decision": "MAYBE"}, {"user": ""}])
def test_post_without_reason_is_422_and_log_untouched(store: EvidenceStore, tmp_path: Path,
                                                      kw: dict) -> None:
    client, log = screen_client(store, tmp_path)
    assert post(client, **kw).status_code == 422 and not log.path.exists()


def test_post_missing_reason_field_is_422(store: EvidenceStore, tmp_path: Path) -> None:
    client, log = screen_client(store, tmp_path)
    r = client.post("/decisions", json={"trial": "SYN-TR-0037", "decision": "PASS",
                                        "user": "breeder-a"})
    assert r.status_code == 422 and not log.path.exists()


def test_post_then_get_decisions(store: EvidenceStore, tmp_path: Path) -> None:
    client, _ = screen_client(store, tmp_path)
    r = post(client)
    assert r.status_code == 201
    rec = r.json()
    assert rec["decision"] == "PASS" and rec["overrides"] is True and rec["reason"] == REASON
    assert rec["recommendation"]["verdict"] == "HOLD" and rec["user"] == "breeder-a"
    assert rec["timestamp"].endswith("+00:00")
    assert client.get("/decisions", params={"trial": "0037"}).json() == [rec]
    assert client.get("/trials/SYN-TR-0037").json()["decisions"] == [rec]
    row = next(t for t in client.get("/trials").json() if t["trial_id"] == "SYN-TR-0037")
    assert row["latest_decision"] == rec and row["verdict"] == "HOLD"  # verdict unchanged


@pytest.mark.parametrize("trial,code,status", [("SYN-TR-003", 409, "many"),
                                               ("XYZ", 404, "none")])
def test_post_ambiguous_or_unknown_trial(store: EvidenceStore, tmp_path: Path, trial: str,
                                         code: int, status: str) -> None:
    client, log = screen_client(store, tmp_path)
    r = post(client, trial=trial)
    assert r.status_code == code and r.json()["status"] == status and not log.path.exists()


def test_double_submit_keeps_both(store: EvidenceStore, tmp_path: Path) -> None:
    client, log = screen_client(store, tmp_path)
    a, b = post(client).json(), post(client).json()
    assert a["decision_id"] != b["decision_id"] and len(log.read()) == 2


def test_html_in_reason_is_stored_verbatim(store: EvidenceStore, tmp_path: Path) -> None:
    reason = "<img src=x onerror=alert(1)> looks fine"
    assert post(screen_client(store, tmp_path)[0], reason=reason).json()["reason"] == reason


@pytest.mark.parametrize("method", ["put", "patch", "delete"])
def test_no_update_or_delete_routes(store: EvidenceStore, tmp_path: Path,
                                    method: str) -> None:
    client, _ = screen_client(store, tmp_path)
    assert getattr(client, method)("/decisions").status_code == 405


def test_reads_and_decisions_work_without_a_model(store: EvidenceStore,
                                                  tmp_path: Path) -> None:
    def fail() -> FakeChat:
        raise LLMError("PORTKEY_API_KEY is not set")
    log = DecisionLog(tmp_path / "decisions.jsonl")
    client = TestClient(create_app(fail, create_server(lambda: store),
                                   get_store=lambda: store, log=log))
    assert client.post("/ask", json={"question": "Why?"}).status_code == 503
    assert client.get("/trials/SYN-TR-0037").json()["status"] == "ok"
    assert post(client).status_code == 201
```

- [ ] **Step 2: Run to verify failure.** Run `uv run --project app pytest -q app/tests/test_api.py`. Expected: `TypeError: create_app() got an unexpected keyword argument 'get_store'`.

- [ ] **Step 3: Implement.** Changes to `app/src/uc4_mcp/api.py`:

```python
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints

from uc4_mcp.decisions import (REASON_MAX, REASON_MIN, USER_MAX, DecisionError, DecisionLog,
                               log_path, record_decision)
from uc4_mcp.models import DECISIONS, to_json_safe
from uc4_mcp.server import _default_store
from uc4_mcp.store import EvidenceStore

Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=REASON_MIN,
                                          max_length=REASON_MAX)]
User = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1,
                                        max_length=USER_MAX)]


class DecisionRequest(BaseModel):
    trial: str = Field(min_length=1, max_length=80)
    decision: Literal["PASS", "HOLD", "FAIL"]
    reason: Reason
    user: User
    material_guid: str | None = Field(default=None, max_length=80)
```

Inside `create_app` (the new keyword-only parameters `get_store` and `log` resolve to `_default_store` and `DecisionLog(log_path())`):

```python
    def decisions_json(trial_guid: str | None) -> list[dict[str, Any]]:
        return [to_json_safe(r) for r in log.read(trial_guid)]

    @app.get("/trials")
    def trials() -> list[dict[str, Any]]:
        store, latest = get_store(), {r.trial_guid: r for r in log.read()}
        out = []
        for guid in store.trial_guids:
            rec = store.recommendation(guid)
            last = latest.get(guid)
            out.append({"trial_id": rec.trial_id, "trial_guid": guid, "verdict": rec.verdict,
                        "colour": rec.colour, "reason": rec.reason,
                        "latest_decision": to_json_safe(last) if last else None})
        return out

    @app.get("/trials/{query}")
    def trial(query: str) -> dict[str, Any]:
        envelope = to_json_safe(get_store().get_trial(query))
        if envelope["status"] == "ok":
            envelope["decisions"] = decisions_json(envelope["result"]["trial_guid"])
        return envelope

    @app.get("/lines/{query}")
    def line(query: str) -> dict[str, Any]:
        return to_json_safe(get_store().get_line(query))

    @app.post("/decisions", status_code=201)
    def decide(body: DecisionRequest) -> JSONResponse:
        try:
            record = record_decision(get_store(), log, **body.model_dump())
        except DecisionError as e:
            if e.envelope is not None:
                code = 409 if e.envelope["status"] == "many" else 404
                return JSONResponse(e.envelope, status_code=code)
            return JSONResponse({"status": "error", "message": str(e)}, status_code=422)
        return JSONResponse(to_json_safe(record), status_code=201)

    @app.get("/decisions")
    def decisions(trial: str | None = None) -> JSONResponse:
        if trial is None:
            return JSONResponse(decisions_json(None))
        res = get_store().resolve_trial(trial)
        if res.status != "ok":
            return JSONResponse(to_json_safe(get_store().find_trial(trial)), status_code=404)
        return JSONResponse(decisions_json(str(res.guid)))
```

`record_decision` still validates on its own, so non-HTTP callers get the same rules. Update the module docstring: "HTTP front for the breeder screen and n8n: the question agent, trial and line reads, and the append-only decision log." `DECISIONS` must equal the `Literal`; a one-line test asserts `set(DECISIONS) == set(DecisionRequest.model_fields["decision"].annotation.__args__)`.

- [ ] **Step 4: Run the tests.** Run `uv run --project app pytest -q app/tests`. Expected: all pass, and the existing `/ask` tests are unchanged.

- [ ] **Step 5: Commit**

```powershell
git add app/src/uc4_mcp/api.py app/tests/test_api.py
git commit -m "feat(app): trial and line reads and POST /decisions for the breeder screen" -m "<trailer lines>"
```

---

### Task 3: The breeder screen

**Files:**
- Create: `app/src/uc4_mcp/static/index.html`, `app.js`, `style.css`, `app/tests/test_screen.py`
- Modify: `app/src/uc4_mcp/api.py` (the `/` route and the `/static` mount)

**Interfaces:**
- Consumes: the Task 2 routes and `POST /ask` (the Phase 2 hand-off: `text`, `citations`, `candidates`, `status`, `disclaimer`).
- Produces: `api.STATIC_DIR`. `GET /` serves `index.html` and `/static/*` serves the assets. The element ids listed below form the contract between `index.html` and `app.js`.

**Element ids.** They are asserted in both files by the test:

| id | What it holds |
| --- | --- |
| `trial-search` | Search box with the `trial-list` datalist (72 entries: `SYN-TR-0037 · HOLD`) |
| `user-alias` | Demo alias, remembered in `localStorage` (wrapped in try/catch) |
| `candidates` | "Which one?" buttons for an ambiguous search, or "No trial matches" |
| `banner` | Verdict word, shape (● PASS, ▲ HOLD, ■ FAIL), colour class, `reason`, "SYNTH_V1 (inferred)", "The breeder decides" |
| `criteria` | Table of 7 rows: label · value and unit · test and threshold · bracket (inferred) · met / not met / knockout triggered; a `null` value reads "missing: not met" |
| `rationale` | Supplied rationale text, plus a warning when `rationale_omits` is not empty ("The supplied text does not mention: Resistant lines %") |
| `aggregates` | GBV mean and resistant %: supplied vs observation-linked (the `AGGREGATE_LINKS_UNVERIFIED` explanation) |
| `flags` | Warnings first, then info; each shows code, message and a `<details>` listing its `evidence_row_ids` |
| `lines` | Table of 10 rows (material ID, GBV, resistance marker); a click opens `line-panel` |
| `line-panel` | `GET /lines/{guid}`: genomics, lab rows "Lab trait …xx" with "lab rows have no trial key: not linked to this trial", the trial verdicts with the `note`, operations and flags |
| `operations` | Table of 3 rows: date · type · status · flag codes |
| `decision-form` | Radio buttons PASS / HOLD / FAIL (none preselected), an optional "about line" select (the 10 lines), `reason` textarea (`minlength=5`, `maxlength=1000`, `required`), submit button |
| `decision-error` | The server's 422, 404 or 409 message, shown inline (`role="alert"`) |
| `history` | This trial's decisions, newest first: time · user · decision (with an "override" badge when `overrides`) · reason · the recommendation verdict it was made against |
| `ask-form`, `ask-question`, `answer` | Question box; the answer text, numbered citations list, `unverified` warning, `clarify` candidate buttons, disclaimer; a 503 reads "Ask unavailable: <text>" |

**Behaviour.** In `app.js` (plain ES2020, no modules needed):

- **DOM helper:** `const byId = (id) => document.getElementById(id)`. `el(tag, props, ...children)` builds nodes with `textContent` and string children as text nodes. Nothing ever assigns `innerHTML`.
- **`loadTrials()`** runs on start. It calls `GET /trials`, fills the datalist, then opens the trial in `location.hash` (`#SYN-TR-0037`) or the first trial.
- **`openTrial(query)`** calls `GET /trials/{query}`:
  - `ok`: renders every section and sets `location.hash`.
  - `many`: renders the candidate buttons.
  - `none`: shows its message.
- **Sources:** each value cell has a `title` (tooltip) with its `source_file#row_id` and a small "source" toggle that reveals it, so a judge can see the provenance.
- **Submit:**
  1. Disable the button while the request is in flight.
  2. `POST /decisions`.
  3. On 201: clear the reason, re-render the history from the response and refresh the datalist entry.
  4. On any other status: show `message` (or the pydantic `detail[0].msg`) in `decision-error`.
  5. Re-enable the button.
- **Ask:**
  1. Keep `history` (the last 10 messages).
  2. `POST /ask`.
  3. On `clarify`, render the candidates as buttons. A click calls `openTrial(id)` and re-asks with the ID as the question and the history attached.
  4. When the answer cites a trial row of the open trial, highlight it.

**Style.** In `style.css`:

- Base font size 18 px, system font, max width 72 rem.
- Colour tokens for green, amber and red with WCAG AA contrast against the text.
- Tables sit in `overflow-x: auto` wrappers.
- Below 700 px the layout becomes one column.
- There is no external font or CDN.

- [ ] **Step 1: Write the failing tests** in `app/tests/test_screen.py`

```python
"""Task 3: the static breeder screen is served, wired by id, and never injects HTML."""

import re
from pathlib import Path

from fakes import FakeChat
from fastapi.testclient import TestClient

from uc4_mcp.api import STATIC_DIR, create_app
from uc4_mcp.decisions import DecisionLog
from uc4_mcp.server import create_server
from uc4_mcp.store import EvidenceStore

IDS = ["trial-search", "trial-list", "user-alias", "candidates", "banner", "criteria",
       "rationale", "aggregates", "flags", "lines", "line-panel", "operations",
       "decision-form", "decision-error", "history", "ask-form", "ask-question", "answer"]


def client(store: EvidenceStore, tmp_path: Path) -> TestClient:
    return TestClient(create_app(lambda: FakeChat([]), create_server(lambda: store),
                                 get_store=lambda: store,
                                 log=DecisionLog(tmp_path / "d.jsonl")))


def test_root_serves_the_screen_and_assets(store: EvidenceStore, tmp_path: Path) -> None:
    c = client(store, tmp_path)
    r = c.get("/")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert c.get("/static/app.js").status_code == 200
    assert c.get("/static/style.css").status_code == 200


def test_every_id_is_in_the_page_and_used_by_the_script() -> None:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    for id_ in IDS:
        assert f'id="{id_}"' in html, id_
    used = set(re.findall(r'byId\("([\w-]+)"\)', js))
    assert used <= set(IDS) and set(IDS) - {"trial-list"} <= used


def test_app_js_never_uses_inner_html() -> None:
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write", js)


def test_page_is_self_contained_and_states_the_rules() -> None:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    assert "http://" not in html and "https://" not in html  # no CDN
    assert "SYNTH_V1 (inferred)" in html and "breeder decides" in html
```

- [ ] **Step 2: Run to verify failure.** Run `uv run --project app pytest -q app/tests/test_screen.py`. Expected: `ImportError: cannot import name 'STATIC_DIR'`.

- [ ] **Step 3: Serve the static files** in `api.py`:

```python
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).resolve().parent / "static"
# in create_app:
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def screen() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")
```

- [ ] **Step 4: Write** `index.html`, `app.js` and `style.css` as specified above. Keep `app.js` to one file of about 300 lines, with one render function per section (`renderBanner`, `renderCriteria`, `renderRationale`, `renderAggregates`, `renderFlags`, `renderLines`, `renderLinePanel`, `renderOperations`, `renderHistory`, `renderAnswer`).

- [ ] **Step 5: Run the tests, then check the wheel contents**

```powershell
uv run --project app pytest -q app/tests
uv build --project app --wheel --out-dir "$env:TEMP\uc4-wheel"
uv run --project app python -c "import zipfile,glob,os; print([n for n in zipfile.ZipFile(glob.glob(os.path.expandvars(r'$TEMP\uc4-wheel\*.whl'))[0]).namelist() if 'static' in n])"
```

Expected: all tests pass, and the listing shows `uc4_mcp/static/index.html`, `app.js` and `style.css`. If they are missing, add them via `[tool.uv.build-backend]` in `pyproject.toml`.

- [ ] **Step 6: Commit**

```powershell
git add app/src/uc4_mcp/static app/src/uc4_mcp/api.py app/tests/test_screen.py
git commit -m "feat(app): breeder screen with criteria, lines, flags, decisions and ask" -m "<trailer lines>"
```

---

### Task 4: Serve, docs

**Files:**
- Modify: `app/src/uc4_mcp/cli.py`, `app/tests/test_cli.py`, `app/README.md`

- [ ] **Step 1: `cmd_serve` preloads the store and names the screen.** It calls `_default_store()` before `uvicorn.run`, so a missing zip exits at start with the `find_zip` message (exit code 1, as `uc4-mcp` does). It then prints `Breeder screen: http://<host>:<port>/  (decisions: <log path>)`, and passes `get_store=_default_store` and `log=DecisionLog(log_path())` to `create_app`. Update the `serve` help to `"HTTP: breeder screen at /, POST /ask, /trials, /decisions"`.

- [ ] **Step 2: Test it.** In `test_cli.py`, monkeypatch `uvicorn.run` and `_default_store` and assert:
  - the printed URL and log path
  - that `uvicorn.run` got an app whose routes include `/decisions`
  - that a `FileNotFoundError` from `_default_store` exits with code 1 and prints the message to stderr

- [ ] **Step 3: README.** Add a section `## Breeder screen` after "Question agent" covering:
  - the start command (`uv run --project app uc4-ask serve`, then open http://127.0.0.1:8766/)
  - what the screen shows
  - where decisions go (`app/data/decisions.jsonl`, git-ignored, `UC4_DECISION_LOG` to move it)
  - that the log is append-only and copies the recommendation
  - that `user` is a demo alias with no authentication
  - that `/ask` needs the Portkey variables but the rest of the screen does not

  Add a table of the routes.

- [ ] **Step 4: Run the tests and commit**

```powershell
uv run --project app pytest -q app/tests
git add app/src/uc4_mcp/cli.py app/tests/test_cli.py app/README.md
git commit -m "feat(app): uc4-ask serve opens the breeder screen; README section" -m "<trailer lines>"
```

---

### Task 5: Walkthrough of "Validate the demo" in a real browser

**Files:**
- Create: `team/screenshots/phase3_*.png`, a GIF
- Modify: `team/PROMPT_LOG.md`, this file (exit criteria), `task.md`

Setup:

1. Start the server with `$env:UC4_DECISION_LOG = "$env:TEMP\uc4-walkthrough.jsonl"; uv run --project app uc4-ask serve`. This keeps demo rehearsal decisions out of the real log.
2. Open http://127.0.0.1:8766/ with Claude in Chrome and record a GIF (`phase3_walkthrough.gif`).
3. The yield-knockout trial is SYN-TR-0009, the first of the 10 returned by `query_trials knockout=yield only=true` (checked 2026-09-30).

| # | Scenario | Expect | Screenshot |
| --- | --- | --- | --- |
| 1 | SYN-TR-0003 | Green ● PASS; all 5 PASS criteria met; neither knockout triggered | `phase3_1_pass_0003.png` |
| 2 | SYN-TR-0037 | Amber ▲ HOLD; only resistant 30 % < 50 % unmet; rationale warning "does not mention: Resistant…"; `RATIONALE_READS_AS_PASS` flag | `phase3_2_hold_0037.png` |
| 3 | SYN-TR-0001 | Red ■ FAIL; disease 7.7 > 7 knockout triggered; GBV supplied 105.4 vs linked 105.05 | `phase3_3_fail_disease_0001.png` |
| 4 | SYN-TR-0009 (first yield-only knockout) | Red ■ FAIL; yield knockout triggered, disease not | `phase3_4_fail_yield_0009.png` |
| 5 | SYN-TR-0002 | `OPS_OUTSIDE_TRIAL_YEAR` on its operations (warning) | `phase3_5_ops_0002.png` |
| 6 | Search `SYN-TR-003` | "Which one?" with 10 buttons; nothing opened | `phase3_6_ambiguous.png` |
| 7 | On 0037, pick PASS with an empty reason, then `"    "` | Rejected inline; the history is still empty; the log file is absent or unchanged | `phase3_7_no_reason.png` |
| 8 | On 0037, PASS with a real reason as `breeder-a` | The history shows the "override" badge and "against HOLD"; the banner still reads HOLD | `phase3_8_override.png` |
| 9 | A reason containing `<b>bold</b>` | Shown literally, not bold | (in the GIF) |
| 10 | Click a line in 0037 | Line panel with lab "not linked to this trial" and "verdicts are per trial" | `phase3_10_line.png` |
| 11 | With Portkey variables set: "Why is SYN-TR-0037 amber?" | Answer with numbered citations and disclaimer. Without them: "Ask unavailable", and everything else still works | `phase3_11_ask.png` |

Finish:

- Run `Get-Content "$env:TEMP\uc4-walkthrough.jsonl"`. Expect one line per accepted decision, each with the full `recommendation`.
- Run `uv run --project app pytest -q app/tests` once more.

Then:

- [x] Log the session in [team/PROMPT_LOG.md](../../team/PROMPT_LOG.md) in its existing format.
- [x] Tick this file's exit criteria with the evidence (test names, screenshot paths).
- [x] Update the [task.md](task.md) status line: Phase 3 done, screenshots and live Ask verified.
- [x] Include the walkthrough close-out in one commit on `demo-live-ask`.

If a scenario fails, fix it in the task that owns the code, with a regression test, before ticking the box.

---

## Estimates

| Task | Time |
| --- | --- |
| 1 Override record and log | 60 min |
| 2 HTTP routes | 60 min |
| 3 Screen | 2 h 30 min |
| 4 Serve and docs | 30 min |
| 5 Browser walkthrough | 45 min |
| **Total** | **≈ 5 h 45 min** |

## Hand-off to Phases 4 and 5

- Phase 4 reads `app/data/decisions.jsonl` (or `GET /decisions`) for the before/after audit. Each line is a full `OverrideRecord`.
- Phase 5's demo beat: open 0037, show the criteria and the rationale warning, challenge it with "Ask", record an override with a reason, and show the log line.
- The engine and the evidence are unchanged by this phase. `baseline_check` stays at 72/72.
