"""Step 4: the SYNTH_V1 rule. Ported from analysis/uc4_eda/test_rules.py, plus explain()."""

import math
from pathlib import Path

import pandas as pd
import pytest

from uc4_mcp.models import Recommendation, evidence_ref
from uc4_mcp.rules import (
    RATIONALE_OK,
    RATIONALE_UNMET,
    SYNTH_V1,
    apply_rule,
    criteria_flags,
    explain,
    genomics_reconciliation,
    rationale_flags,
    threshold_intervals,
)

Tables = dict[str, pd.DataFrame]
# Historical regression cases use frozen v2 EDA outputs, independent of current analysis.
EDA_TABLES = Path(__file__).resolve().parent / "fixtures" / "historical_v2"

PASSING = {"YIELD_T_HA": 10.0, "MOISTURE_PCT": 18.0, "DISEASE_SCORE": 3.0,
           "GENOMIC_BREEDING_VALUE_MEAN": 106.0, "RESISTANT_MATERIAL_PCT": 50.0}
ORDER = [("YIELD_T_HA", ">=", "pass"), ("MOISTURE_PCT", "<=", "pass"),
         ("DISEASE_SCORE", "<=", "pass"), ("GENOMIC_BREEDING_VALUE_MEAN", ">=", "pass"),
         ("RESISTANT_MATERIAL_PCT", ">=", "pass"), ("YIELD_T_HA", "<", "knockout"),
         ("DISEASE_SCORE", ">", "knockout")]


def verdict(**overrides: float) -> str:
    return str(apply_rule(pd.DataFrame([{**PASSING, **overrides}])).iloc[0])


# --- ported from the EDA ----------------------------------------------------


@pytest.mark.parametrize("overrides, expected", [
    ({}, "PASS"),
    ({"YIELD_T_HA": 6.9}, "FAIL"),
    ({"YIELD_T_HA": 7.0}, "HOLD"),
    ({"YIELD_T_HA": 8.9}, "HOLD"),
    ({"DISEASE_SCORE": 7.0}, "HOLD"),
    ({"DISEASE_SCORE": 7.2}, "FAIL"),
    ({"DISEASE_SCORE": 5.1}, "HOLD"),
    ({"MOISTURE_PCT": 22.1}, "HOLD"),
    ({"GENOMIC_BREEDING_VALUE_MEAN": 101.0}, "HOLD"),
    ({"RESISTANT_MATERIAL_PCT": 30.0}, "HOLD"),
    # A knockout wins even when every PASS criterion but one is met.
    ({"YIELD_T_HA": 12.0, "DISEASE_SCORE": 7.5}, "FAIL"),
])
def test_boundaries(overrides: dict[str, float], expected: str) -> None:
    assert verdict(**overrides) == expected


@pytest.mark.parametrize("column", list(PASSING))
def test_missing_value_is_never_a_pass(column: str) -> None:
    assert verdict(**{column: math.nan}) == "HOLD"


def test_rule_reproduces_every_supplied_recommendation(tables: Tables) -> None:
    rec = tables["recommendations"]
    assert (apply_rule(rec) == rec["TRIAL_RECOMMENDATION"]).all()


def test_used_thresholds_sit_inside_the_data_brackets(tables: Tables) -> None:
    iv = threshold_intervals(tables["recommendations"])
    assert (iv["bracket_low"] < iv["bracket_high"]).all()
    assert ((iv["used"] >= iv["bracket_low"]) & (iv["used"] <= iv["bracket_high"])).all()


def test_only_the_block_mapping_reproduces_genomics_aggregates(tables: Tables) -> None:
    rec = genomics_reconciliation(tables)
    assert rec["gbv_match_block"].all() and rec["resistant_match_block"].all()
    assert not rec["gbv_match_observation"].any()
    assert not rec["gbv_match_operations"].any()


# --- new in the app ---------------------------------------------------------


def test_every_supplied_rule_version_is_synth_v1(tables: Tables) -> None:
    # A new supplied rule must fail loudly, not be scored with SYNTH_V1.
    assert set(tables["recommendations"]["RULE_VERSION"]) == {"SYNTH_V1"}


def test_intervals_equal_the_eda_table(tables: Tables) -> None:
    expected = pd.read_csv(EDA_TABLES / "rule_intervals.csv")
    pd.testing.assert_frame_equal(threshold_intervals(tables["recommendations"]), expected)


def test_rationale_phrases_are_the_eight_in_the_file(tables: Tables) -> None:
    text = tables["recommendations"]["RECOMMENDATION_RATIONALE"].str.lower()
    phrases = set(text.str.split(";").explode().str.strip())
    assert phrases == set(RATIONALE_OK.values()) | set(RATIONALE_UNMET.values())


def test_no_rationale_contradicts_the_rule(tables: Tables) -> None:
    rec = tables["recommendations"]
    ok = criteria_flags(rec)
    met = rationale_flags(rec)
    text = rec["RECOMMENDATION_RATIONALE"].str.lower()
    for col, flag in [("YIELD_T_HA", "yield_ok"), ("MOISTURE_PCT", "moisture_ok"),
                      ("DISEASE_SCORE", "disease_ok"), ("GENOMIC_BREEDING_VALUE_MEAN", "gbv_ok")]:
        unmet = text.str.contains(RATIONALE_UNMET[col], regex=False)
        assert not (met[col] & ~ok[flag]).any(), col
        assert not (unmet & ok[flag]).any(), col


@pytest.fixture(scope="module")
def recs(tables: Tables) -> dict[str, Recommendation]:
    rec = tables["recommendations"]
    iv = threshold_intervals(rec)
    return {str(row["TRIAL_ID"]): explain(row, iv) for _, row in rec.iterrows()}


def test_explain_matches_rule_and_supplied_for_all_72(recs: dict[str, Recommendation],
                                                      tables: Tables) -> None:
    rec = tables["recommendations"].set_index("TRIAL_ID")
    assert len(recs) == 72
    assert all(r.verdict == apply_rule(rec).loc[k] for k, r in recs.items())
    assert all(r.matches_supplied and r.verdict == r.supplied_verdict for r in recs.values())


def test_explain_returns_seven_criteria_in_order(recs: dict[str, Recommendation]) -> None:
    for r in recs.values():
        assert [(c.field, c.test, c.kind) for c in r.criteria] == ORDER


def test_explain_metadata(recs: dict[str, Recommendation], tables: Tables) -> None:
    r = recs["SYN-TR-0037"]
    row = tables["recommendations"].set_index("TRIAL_ID").loc["SYN-TR-0037"]
    assert r.rule_version == SYNTH_V1.version == "SYNTH_V1 (inferred)"
    assert r.trial_guid == row["TRIAL_GUID"] and r.flags == ()
    assert r.evidence_row_ids == (f"{row['_source_file']}#{row['_row_id']}",)
    assert r.supplied_rationale == row["RECOMMENDATION_RATIONALE"]
    assert {x.colour for x in recs.values()} == {"green", "amber", "red"}


def _states(r: Recommendation) -> list[tuple[float | None, bool, bool]]:
    return [(c.value, c.passed, c.triggered) for c in r.criteria]


def test_worked_example_0003_pass(recs: dict[str, Recommendation]) -> None:
    r = recs["SYN-TR-0003"]
    assert r.verdict == "PASS" and r.colour == "green" and r.knockout == ()
    assert _states(r) == [(10.79, True, False), (16.8, True, False), (3.3, True, False),
                          (106.8, True, False), (70.0, True, False),
                          (10.79, True, False), (3.3, True, False)]
    assert r.reason == "PASS: all five criteria met (inferred thresholds)"
    assert r.rationale_omits == ()


def test_worked_example_0037_hold(recs: dict[str, Recommendation]) -> None:
    r = recs["SYN-TR-0037"]
    assert r.verdict == "HOLD" and r.colour == "amber" and r.knockout == ()
    assert _states(r) == [(12.58, True, False), (16.2, True, False), (4.2, True, False),
                          (105.2, True, False), (30.0, False, False),
                          (12.58, True, False), (4.2, True, False)]
    assert r.reason == "HOLD: resistant lines 30% < 50% (inferred threshold)"
    assert r.rationale_omits == ("RESISTANT_MATERIAL_PCT",)


def test_worked_example_0001_fail(recs: dict[str, Recommendation]) -> None:
    r = recs["SYN-TR-0001"]
    assert r.verdict == "FAIL" and r.colour == "red" and r.knockout == ("DISEASE_SCORE",)
    assert _states(r) == [(10.05, True, False), (15.4, True, False), (7.7, False, False),
                          (105.4, True, False), (30.0, False, False),
                          (10.05, True, False), (7.7, False, True)]
    assert r.reason == "FAIL: disease score 7.7 > 7 (knockout, inferred threshold)"
    assert r.rationale_omits == ("RESISTANT_MATERIAL_PCT",)


def test_criteria_carry_threshold_and_bracket(recs: dict[str, Recommendation],
                                              tables: Tables) -> None:
    iv = threshold_intervals(tables["recommendations"])
    got = [(c.threshold, c.bracket) for c in recs["SYN-TR-0001"].criteria]
    assert got == [(u, (lo, hi)) for u, lo, hi in
                   zip(iv["used"], iv["bracket_low"], iv["bracket_high"])]


def test_hold_reason_lists_every_unmet_criterion_in_order(tables: Tables) -> None:
    rec = tables["recommendations"]
    row = rec.iloc[0].copy()
    row[list(PASSING)] = [8.5, 23.0, 3.0, 106.0, 30.0]
    r = explain(row, threshold_intervals(rec))
    assert r.verdict == "HOLD"
    assert r.reason == ("HOLD: yield 8.5 t/ha < 9 t/ha; moisture 23% > 22%; "
                        "resistant lines 30% < 50% (inferred thresholds)")


def test_missing_disease_score_is_hold_with_no_value(tables: Tables) -> None:
    rec = tables["recommendations"]
    row = rec[rec["TRIAL_ID"] == "SYN-TR-0003"].iloc[0].copy()
    row["DISEASE_SCORE"] = math.nan
    r = explain(row, threshold_intervals(rec))
    assert r.verdict == "HOLD" and not r.matches_supplied
    disease = [c for c in r.criteria if c.field == "DISEASE_SCORE"]
    assert [(c.value, c.passed, c.triggered) for c in disease] == [(None, False, False)] * 2
    assert r.reason == "HOLD: disease score missing (inferred threshold)"


def test_rationale_omits_resistant_for_33_trials(recs: dict[str, Recommendation]) -> None:
    omits = {k: r.rationale_omits for k, r in recs.items() if r.rationale_omits}
    assert len(omits) == 33
    assert set(omits.values()) == {("RESISTANT_MATERIAL_PCT",)}
    verdicts = [recs[k].verdict for k in omits]
    assert (verdicts.count("HOLD"), verdicts.count("FAIL")) == (16, 17)


def test_evidence_ref_is_the_recommendation_row(recs: dict[str, Recommendation],
                                                tables: Tables) -> None:
    rec = tables["recommendations"]
    assert {r.evidence_row_ids[0] for r in recs.values()} == {
        evidence_ref(row) for _, row in rec.iterrows()}
