"""Step 4: consistency checks. Ported from analysis/uc4_eda/test_lifecycle.py, plus the
comparison with the EDA's chronology_checks.csv and stage_counts."""

import math
from pathlib import Path

import pandas as pd
import pytest

from uc4_mcp.lifecycle import before, chronology_checks, snapshot_date, stage_counts

Tables = dict[str, pd.DataFrame]
EDA_TABLES = Path(__file__).resolve().parents[2] / "analysis" / "uc4_eda" / "tables"
ALL_MET = ("yield meets threshold; moisture meets threshold; disease score acceptable; "
           "genomic value favourable")


def synthetic_tables() -> Tables:
    """Two complete trials. T1's rationale claims all four criteria met, but its GBV of
    100 misses the target, so it is (correctly) HOLD. T2 fails on yield. The extract
    date is the latest LAST_CHG_DATE: 2026-01-01."""
    germplasm = pd.DataFrame({"MATERIAL_GUID": ["M1", "M2"], "MATERIAL_ID": ["L-001", "L-002"]})
    trial = pd.DataFrame({
        "TRIAL_GUID": ["T1", "T2"], "TRIAL_ID": ["TR-0001", "TR-0002"],
        "START_YEAR": [2025, 2026], "STATUS_LID": ["COMPLETE", "COMPLETE"],
    })
    observation = pd.DataFrame({"ATTACHED_TO_FIELD_ENTITY_ID": ["T1", "T2"], "GID": ["M1", "M2"]})
    operations = pd.DataFrame({
        "OPERATION_GUID": ["P1", "P2", "P3"], "TRIAL_GUID": ["T1", "T1", "T2"],
        "MATERIAL_GUID": ["M1", "M2", "M2"],
        "OPERATION_TYPE_LID": ["PLANTING", "HARVEST", "PLANTING"],
        "OPERATION_STATUS_LID": ["COMPLETED", "PLANNED", "COMPLETED"],
        "OPERATION_DATE": ["2025-05-01", "2025-04-01", "2027-01-01"],
    })
    genomics = pd.DataFrame({
        "MATERIAL_GUID": ["M1", "M2"], "SAMPLE_ID": ["S1", "S2"],
        "GENOMIC_BREEDING_VALUE": [100.0, 110.0],
        "MARKER_DISEASE_RESISTANCE": ["RESISTANT", "SUSCEPTIBLE"],
        "GENOTYPING_DATE": ["2025-01-01", "2026-06-01"],
        "CREATE_DATE": ["2025-01-01", "2026-02-01"], "LAST_CHG_DATE": ["2026-01-01"] * 2,
    })
    recommendations = pd.DataFrame({
        "TRIAL_GUID": ["T1", "T2"], "TRIAL_ID": ["TR-0001", "TR-0002"],
        "YIELD_T_HA": [10.0, 5.0], "MOISTURE_PCT": [18.0, 18.0], "DISEASE_SCORE": [3.0, 3.0],
        "GENOMIC_BREEDING_VALUE_MEAN": [100.0, 105.0], "RESISTANT_MATERIAL_PCT": [100.0, 0.0],
        "TRIAL_RECOMMENDATION": ["HOLD", "FAIL"],
        "RECOMMENDATION_RATIONALE": [ALL_MET, "yield below target; moisture meets threshold"],
    })
    return {"germplasm": germplasm, "trial": trial, "observation": observation,
            "operations": operations, "genomics": genomics, "recommendations": recommendations}


@pytest.fixture(scope="module")
def checks() -> pd.DataFrame:
    return chronology_checks(synthetic_tables()).set_index("rule")


# --- ported from the EDA (synthetic tables cover "not checkable") -----------


def test_before_is_nan_when_a_date_is_missing() -> None:
    out = before(pd.Series(["2020-01-01", None]), pd.Series(["2021-01-01", "2021-01-01"]))
    assert out.iloc[0] == 1.0 and math.isnan(out.iloc[1])


@pytest.mark.parametrize("rule, checked, violations", [
    ("Operation dated outside its trial's start year", 3, 1),
    ("Completed trial still has planned operations", 2, 1),
    ("Planned operation dated before the extract", 1, 1),
    ("Completed operation dated after the extract", 2, 1),
    ("Trial's first harvest dated before its first planting", 1, 1),
    ("Operation's trial + material not linked in observations", 3, 1),
    ("Trial GBV mean differs from its observation-linked materials", 2, 1),
    ("Trial resistant % differs from its observation-linked materials", 2, 0),
    ("Rationale reports all four criteria met, yet not PASS", 1, 1),
    ("Supplied recommendation differs from the inferred rule", 2, 0),
    ("Genotyping dated after the extract", 2, 1),
    ("Genomics record last changed before it was created", 2, 1),
])
def test_each_rule_counts_checked_and_violations(checks: pd.DataFrame, rule: str, checked: int,
                                                 violations: int) -> None:
    assert checks.loc[rule, "checked"] == checked
    assert checks.loc[rule, "violations"] == violations


def test_missing_side_is_not_checkable_rather_than_passing(checks: pd.DataFrame) -> None:
    # T2 has a planting but no harvest, so its order cannot be judged.
    assert checks.loc["Trial's first harvest dated before its first planting", "not_checkable"] == 1


def test_example_points_at_a_violating_record(checks: pd.DataFrame) -> None:
    assert checks.loc["Completed operation dated after the extract", "example"] == "P3"
    assert checks.loc["Trial GBV mean differs from its observation-linked materials",
                      "example"] == "TR-0002"
    assert checks.loc["Rationale reports all four criteria met, yet not PASS",
                      "example"] == "TR-0001"


# --- real data --------------------------------------------------------------


def test_chronology_checks_equal_the_eda_table(tables: Tables) -> None:
    cols = ["rule", "checked", "violations", "not_checkable", "example"]
    expected = pd.read_csv(EDA_TABLES / "chronology_checks.csv", keep_default_na=False)[cols]
    got = chronology_checks(tables)[cols]
    assert got.astype(str).values.tolist() == expected.astype(str).values.tolist()


def test_snapshot_date_is_the_latest_change(tables: Tables) -> None:
    assert snapshot_date(tables) == pd.Timestamp("2026-09-26 12:00")


def test_stage_counts_cover_every_source(tables: Tables) -> None:
    counts = stage_counts(tables)
    assert {k: v["n"] for k, v in counts.items()} == {
        "germplasm": 150, "genomics": 150, "lab": 360, "trials": 72, "observations": 720,
        "operations": 216, "recommendations": 72}
    assert counts["germplasm"]["detail"] == "IDs only: no pedigree, stage or decision"
