"""Step 6: the evidence store (resolution, trial and line views, queries, baseline)."""

import dataclasses
import json
from collections.abc import Iterator
from typing import Any

import pandas as pd
import pytest
from test_lifecycle import EDA_TABLES

from uc4_mcp.checks import FLAG_CODES
from uc4_mcp.sources import EXPECTED_ROWS, ROW_KEYS
from uc4_mcp.models import EvidenceRow, LineView, TrialView, to_json_safe
from uc4_mcp.rules import explain, threshold_intervals
from uc4_mcp.store import MAX_CANDIDATES, VALUE_FIELDS, EvidenceStore, resolve

Tables = dict[str, pd.DataFrame]
TRIAL = "620A7637-3BE2-7307-0000-{:012X}"  # trial n (hex suffix)


@pytest.fixture(scope="module")
def trial_views(store: EvidenceStore) -> list[TrialView]:
    return [store.trial_view(g) for g in store.trial_guids]


@pytest.fixture(scope="module")
def line_views(store: EvidenceStore) -> list[LineView]:
    return [store.line_view(g) for g in store.line_guids]


def evidence_rows(obj: Any) -> Iterator[EvidenceRow]:
    """Every EvidenceRow inside a view, however deeply nested."""
    if isinstance(obj, EvidenceRow):
        yield obj
    elif dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        for f in dataclasses.fields(obj):
            yield from evidence_rows(getattr(obj, f.name))
    elif isinstance(obj, tuple):
        for v in obj:
            yield from evidence_rows(v)


def trial_ids(envelope: dict[str, Any]) -> list[str]:
    assert envelope["status"] == "ok", envelope["message"]
    return [r["trial_id"] for r in envelope["result"]]


# --- resolution -----------------------------------------------------------------


@pytest.mark.parametrize("query, trial_id", [
    ("SYN-TR-0037", "SYN-TR-0037"), ("syn-tr-0037", "SYN-TR-0037"), ("0037", "SYN-TR-0037"),
    (" 0037 ", "SYN-TR-0037"), (TRIAL.format(37), "SYN-TR-0037"),
    (TRIAL.format(37).lower(), "SYN-TR-0037"),
])
def test_resolve_trial_ok(store: EvidenceStore, query: str, trial_id: str) -> None:
    r = store.resolve_trial(query)
    assert r.status == "ok" and r.guid == TRIAL.format(int(trial_id[-4:]))
    assert r.candidates == ()


def test_resolve_trial_fragment_lists_candidates(store: EvidenceStore) -> None:
    r = store.resolve_trial("SYN-TR-003")
    assert r.status == "many" and r.guid is None
    assert [c.id for c in r.candidates] == [f"SYN-TR-{n:04d}" for n in range(30, 40)]
    assert "10 trials match 'SYN-TR-003'" in r.message


def test_resolve_line_cases(store: EvidenceStore) -> None:
    assert store.resolve_line("SYN-MZ-00001").status == "ok"
    many = store.resolve_line("SYN-MZ-0001")
    assert [c.id for c in many.candidates] == [f"SYN-MZ-{n:05d}" for n in range(10, 20)]
    ids = [c.id for c in store.resolve_line("003").candidates]
    assert ids == ["SYN-MZ-00003"] + [f"SYN-MZ-{n:05d}" for n in range(30, 40)]  # not GUIDs


@pytest.mark.parametrize("query", ["", "  ", "XYZ", "620A7637"])
def test_resolve_none(store: EvidenceStore, query: str) -> None:
    r = store.resolve_trial(query)
    assert r.status == "none" and r.guid is None and r.candidates == () and r.message


def test_candidates_capped_with_total_in_message(store: EvidenceStore) -> None:
    r = store.resolve_line("1")
    assert r.status == "many" and len(r.candidates) == MAX_CANDIDATES == 20
    assert "70 lines match '1'" in r.message
    assert [c.id for c in r.candidates] == sorted(c.id for c in r.candidates)


def test_exact_id_wins_over_fragment() -> None:
    keys = pd.DataFrame({"id": ["TR-10", "TR-1", "TR-100"], "guid": ["G10", "G1", "G100"],
                         "label": ["a", "b", "c"]})
    assert resolve("tr-1", keys, "trial").guid == "G1"
    assert resolve("g10", keys, "trial").guid == "G10"
    assert [c.id for c in resolve("TR-", keys, "trial").candidates] == ["TR-1", "TR-10", "TR-100"]


# --- trial views ------------------------------------------------------------------


def test_every_trial_view_has_10_lines_and_3_operations(trial_views: list[TrialView]) -> None:
    assert len(trial_views) == 72
    for v in trial_views:
        assert len(v.lines) == 10 and len(v.operations) == 3
        assert len({ln.material_guid for ln in v.lines}) == 10


def test_operations_sorted_by_date_then_guid(trial_views: list[TrialView],
                                              line_views: list[LineView]) -> None:
    for v in [*trial_views, *line_views]:
        keys = [(o.date or "", o.operation_guid) for o in v.operations]
        assert keys == sorted(keys)


def test_linked_aggregates_beside_supplied(store: EvidenceStore) -> None:
    v = store.trial_view(TRIAL.format(1))
    assert v.supplied_gbv_mean == 105.4 and v.linked_gbv_mean == 105.05
    assert v.supplied_resistant_pct == 30.0 and v.linked_resistant_pct == 30.0


def test_trial_view_flags(trial_views: list[TrialView], store: EvidenceStore) -> None:
    for v in trial_views:
        assert len(v.flags) >= 4
        trial_flags = store.flags.by_trial[v.trial_guid]
        op_flags = tuple(f for o in v.operations
                         for f in store.flags.by_operation.get(o.operation_guid, ()))
        assert v.flags == trial_flags + op_flags
        assert v.recommendation.flags == trial_flags
        for o in v.operations:
            codes = tuple(f.code for f in store.flags.by_operation.get(o.operation_guid, ()))
            assert all(e.flags == codes for e in o.evidence)


# --- line views -------------------------------------------------------------------


def test_line_views(line_views: list[LineView], store: EvidenceStore) -> None:
    assert len(line_views) == 150
    for v in line_views:
        assert len(v.trials) in (4, 5)
        assert len(v.lab) in (2, 3)
        assert len(v.operations) in (1, 2)
        assert "per trial" in v.note
        assert [t.trial_id for t in v.trials] == sorted(t.trial_id for t in v.trials)
        for t in v.trials:
            assert t.verdict == store.recommendation(t.trial_guid).verdict
        codes = ("LAB_NOT_TRIAL_LINKED",)
        assert all(e.flags == codes for e in v.lab)
        assert v.flags[0].code == "LAB_NOT_TRIAL_LINKED"
        op_flags = tuple(f for o in v.operations
                         for f in store.flags.by_operation.get(o.operation_guid, ()))
        assert v.flags == store.flags.by_line[v.material_guid] + op_flags


# --- evidence rows ----------------------------------------------------------------


def test_every_evidence_row_resolves_back(trial_views: list[TrialView],
                                          line_views: list[LineView], tables: Tables) -> None:
    by_file = {df["_source_file"].iloc[0]: (k, df.set_index("_row_id")) for k, df in tables.items()}
    n = 0
    for ev in (e for v in [*trial_views, *line_views] for e in evidence_rows(v)):
        key, df = by_file[ev.source_file]
        row = df.loc[ev.row_id]
        column = "NUMBER_VALUE" if key == "lab" else ev.field
        assert ev.line_no == row["_line_no"]
        assert ev.value == to_json_safe(row[column])
        if key == "lab":
            assert ev.field.startswith("Lab trait") and ev.uom is None
            assert ev.trial_guid is None and ev.date is None
        else:
            assert (ev.field, ev.uom) in VALUE_FIELDS[key]
        if key == "genomics":
            assert ev.trial_guid is None
        n += 1
    assert n > 72 * 30


def test_value_fields_follow_the_plan() -> None:
    assert dict(VALUE_FIELDS["recommendations"]) == {
        "YIELD_T_HA": "t/ha", "MOISTURE_PCT": "%", "DISEASE_SCORE": "score",
        "PLANT_HEIGHT_CM": "cm", "FLOWERING_DAYS": "days",
        "GENOMIC_BREEDING_VALUE_MEAN": None, "RESISTANT_MATERIAL_PCT": "%",
        "GENOMICS_QC_PASS_PCT": "%"}
    assert VALUE_FIELDS["lab"] == (("NUMBER_VALUE", None),)


def test_views_and_recommendations_are_json_safe(trial_views: list[TrialView],
                                                 line_views: list[LineView],
                                                 store: EvidenceStore) -> None:
    recs = [store.recommendation(g) for g in store.trial_guids]
    for obj in [*trial_views, *line_views, *recs]:
        json.dumps(to_json_safe(obj), allow_nan=False)


# --- recommendations and baseline ---------------------------------------------------


def test_stored_recommendation_equals_explain(store: EvidenceStore, tables: Tables) -> None:
    rec = tables["recommendations"]
    intervals = threshold_intervals(rec)
    for _, row in rec.iterrows():
        stored = store.recommendation(row["TRIAL_GUID"])
        assert dataclasses.replace(stored, flags=()) == explain(row, intervals)
        assert stored.flags == store.flags.by_trial[row["TRIAL_GUID"]]


def test_baseline(store: EvidenceStore) -> None:
    assert store.baseline() == {"checked": 72, "matched": 72, "mismatches": []}


# --- query_trials -------------------------------------------------------------------


def test_query_by_verdict(store: EvidenceStore) -> None:
    counts = {v: len(trial_ids(store.query_trials(verdict=v))) for v in ("FAIL", "HOLD", "PASS")}
    assert counts == {"FAIL": 30, "HOLD": 35, "PASS": 7}
    result = store.query_trials(verdict="HOLD")["result"]
    assert set(result[0]) == {"trial_id", "verdict", "reason"}
    assert [r["trial_id"] for r in result] == sorted(r["trial_id"] for r in result)


@pytest.mark.parametrize("knockout, only, n", [
    ("disease", True, 16), ("yield", True, 10), ("both", False, 4), ("disease", False, 20),
    ("yield", False, 14)])
def test_query_by_knockout(store: EvidenceStore, knockout: str, only: bool, n: int) -> None:
    assert len(trial_ids(store.query_trials(knockout=knockout, only=only))) == n


@pytest.mark.parametrize("field, hold_any, hold_sole, all_any, all_sole", [
    ("MOISTURE_PCT", 16, 5, 24, 5), ("RESISTANT_MATERIAL_PCT", 16, 4, 33, 4),
    ("DISEASE_SCORE", 14, 4, 39, 8), ("GENOMIC_BREEDING_VALUE_MEAN", 12, 1, 23, 1),
    ("YIELD_T_HA", 6, 2, 25, 2)])
def test_query_by_missed(store: EvidenceStore, field: str, hold_any: int, hold_sole: int,
                         all_any: int, all_sole: int) -> None:
    q = store.query_trials
    assert len(trial_ids(q(verdict="HOLD", missed=field))) == hold_any
    assert len(trial_ids(q(verdict="HOLD", missed=field, only=True))) == hold_sole
    assert len(trial_ids(q(missed=field))) == all_any
    assert len(trial_ids(q(missed=field, only=True))) == all_sole


@pytest.mark.parametrize("code, n", [
    ("THRESHOLDS_INFERRED", 72), ("AGGREGATE_LINKS_UNVERIFIED", 72),
    ("RATIONALE_READS_AS_PASS", 4), ("OPS_OUTSIDE_TRIAL_YEAR", 48),
    ("PLANNED_OPS_PAST_EXTRACT", 60), ("COMPLETE_TRIAL_HAS_PLANNED_OPS", 60),
    ("OP_LINE_NOT_IN_TRIAL", 72)])
def test_query_by_flag(store: EvidenceStore, trial_views: list[TrialView], code: str,
                       n: int) -> None:
    got = trial_ids(store.query_trials(flag=code))
    assert len(got) == len(set(got)) == n
    from_index = {g for g, fs in store.flags.by_trial.items() if any(f.code == code for f in fs)}
    from_index |= {store.operation_trial[g] for g, fs in store.flags.by_operation.items()
                   if any(f.code == code for f in fs)}
    from_views = {v.trial_id for v in trial_views if any(f.code == code for f in v.flags)}
    assert set(got) == from_views == {store.trial_view(g).trial_id for g in from_index}


@pytest.mark.parametrize("code", ["COMPLETE_TRIAL_HAS_PLANNED_OPS", "OPS_OUTSIDE_TRIAL_YEAR"])
def test_flag_and_verdict_is_the_intersection(store: EvidenceStore, code: str) -> None:
    both = set(trial_ids(store.query_trials(flag=code, verdict="HOLD")))
    assert both == set(trial_ids(store.query_trials(flag=code))) & set(
        trial_ids(store.query_trials(verdict="HOLD")))


def test_query_with_no_match_is_ok_and_empty(store: EvidenceStore) -> None:
    env = store.query_trials(verdict="PASS", knockout="disease")
    assert env == {"status": "ok", "result": [], "message": "0 trials"}


@pytest.mark.parametrize("kwargs, valid", [
    ({"flag": "LAB_NOT_TRIAL_LINKED"}, list(c for c, s in FLAG_CODES.items()
                                            if s.scope != "line")),
    ({"flag": "NOT_A_CODE"}, ["THRESHOLDS_INFERRED", "OP_LINE_NOT_IN_TRIAL"]),
    ({"verdict": "MAYBE"}, ["PASS", "HOLD", "FAIL"]),
    ({"knockout": "moisture"}, ["yield", "disease", "both"]),
    ({"missed": "NOT_A_FIELD"}, ["YIELD_T_HA", "RESISTANT_MATERIAL_PCT"]),
    ({"only": True}, ["missed", "knockout"]),
])
def test_invalid_filters_give_none_listing_valid_values(store: EvidenceStore,
                                                        kwargs: dict[str, Any],
                                                        valid: list[str]) -> None:
    env = store.query_trials(**kwargs)
    assert env["status"] == "none" and "result" not in env
    assert all(v in env["message"] for v in valid)


# --- envelopes for the tools (step 7) ------------------------------------------------


def test_find_envelopes(store: EvidenceStore) -> None:
    env = store.find_trial("0037")
    assert env["status"] == "ok"
    assert (env["result"].id, env["result"].guid) == ("SYN-TR-0037", TRIAL.format(37))
    env = store.find_trial("SYN-TR-003")
    assert env["status"] == "many" and len(env["candidates"]) == 10 and "result" not in env
    assert store.find_trial("XYZ") == {"status": "none", "message": "No trial matches 'XYZ'"}
    assert store.find_line("SYN-MZ-00001")["result"].id == "SYN-MZ-00001"
    assert len(store.find_line("003")["candidates"]) == 11


def test_get_and_score_envelopes(store: EvidenceStore) -> None:
    trial = store.get_trial("SYN-TR-0037")
    assert trial["status"] == "ok" and trial["result"] == store.trial_view(TRIAL.format(37))
    line = store.get_line("SYN-MZ-00001")
    assert line["status"] == "ok" and line["result"].material_id == "SYN-MZ-00001"
    score = store.score_trial("0037")
    assert score["result"] == store.recommendation(TRIAL.format(37))
    assert store.get_trial("SYN-TR-003")["status"] == "many"
    assert store.get_line("")["status"] == "none"
    assert store.score_trial("XYZ")["status"] == "none"


def test_list_sources(store: EvidenceStore, tables: Tables) -> None:
    env = store.list_sources()
    assert env["status"] == "ok"
    result = env["result"]
    assert result["extract_date"] == "2026-09-26 12:00"
    files = {f["table"]: f for f in result["files"]}
    assert len(files) == 7
    for key, f in files.items():
        assert f["rows"] == EXPECTED_ROWS[key] == len(tables[key])
        assert f["member"] == tables[key]["_source_file"].iloc[0]
        assert f["key"] == ROW_KEYS[key] and f["lacks"] and f["grain"]
        assert set(f["synthetic_marker"]) == {"column", "value"}
    assert files["observation"]["grain"] == "trial-line links"
    assert files["trial"]["grain"] == "trials"


def test_rule_brackets_equal_the_eda_table(store: EvidenceStore) -> None:
    rule = store.rule()
    assert rule["rule_version"] == "SYNTH_V1 (inferred)" and "inferred" in rule["note"]
    assert rule["extract_date"] == "2026-09-26 12:00"
    assert [f["code"] for f in rule["flags"]] == list(FLAG_CODES)
    expected = pd.read_csv(EDA_TABLES / "rule_intervals.csv")
    got = {c["name"]: c for c in rule["criteria"]}
    assert len(got) == len(expected) == 7
    for row in expected.to_dict("records"):
        c = got[row["criterion"]]
        assert c["bracket"] == (row["bracket_low"], row["bracket_high"])
        assert c["threshold"] == row["used"] and c["field"] == row["column"]
