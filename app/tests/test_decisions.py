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


def test_reason_with_unicode_line_separators_round_trips(store: EvidenceStore,
                                                        log: DecisionLog) -> None:
    reason = "pasted from Word text\u0085more"
    r = decide(store, log, reason=reason)
    assert log.path.read_bytes().count(b"\n") == 1
    assert log.read() == [r] and log.read()[0].reason == reason


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
