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
