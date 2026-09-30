import math

import pandas as pd
import pytest

from plant_lifecycle import (
    PHASES,
    classify_operation,
    lifecycle_coverage,
    phase_map,
    trial_timeline,
)


def tables() -> dict[str, pd.DataFrame]:
    """T1 has a normal season (PASS). T2 has no planting (FAIL on yield). T3 is
    harvested before it was planted (HOLD on GBV). All flower at day 60."""
    trial = pd.DataFrame({
        "TRIAL_GUID": ["T1", "T2", "T3"], "TRIAL_ID": ["TR-1", "TR-2", "TR-3"],
        "START_YEAR": [2026, 2026, 2025], "STATUS_LID": ["COMPLETE"] * 3,
        "BEGIN_DATE": [None] * 3,
    })
    operations = pd.DataFrame({
        "OPERATION_GUID": [f"P{i}" for i in range(7)],
        "TRIAL_GUID": ["T1", "T1", "T1", "T2", "T2", "T3", "T3"],
        "MATERIAL_GUID": ["M1"] * 7,
        "OPERATION_TYPE_LID": ["PLANTING", "IRRIGATION", "HARVEST", "IRRIGATION", "HARVEST",
                               "PLANTING", "HARVEST"],
        "OPERATION_STATUS_LID": ["COMPLETED"] * 7,
        "OPERATION_DATE": ["2026-04-01", "2026-04-20", "2026-08-30", "2026-05-01",
                           "2026-06-01", "2026-06-01", "2026-04-01"],
    })
    recommendations = pd.DataFrame({
        "TRIAL_GUID": ["T1", "T2", "T3"], "TRIAL_ID": ["TR-1", "TR-2", "TR-3"],
        "START_YEAR": [2026, 2026, 2025], "FLOWERING_DAYS": [60, 60, 60],
        "YIELD_T_HA": [10.0, 5.0, 10.0], "MOISTURE_PCT": [18.0] * 3, "DISEASE_SCORE": [3.0] * 3,
        "GENOMIC_BREEDING_VALUE_MEAN": [105.0, 105.0, 100.0],
        "RESISTANT_MATERIAL_PCT": [60.0] * 3, "TRIAL_RECOMMENDATION": ["PASS", "FAIL", "HOLD"],
    })
    return {"trial": trial, "operations": operations, "recommendations": recommendations}


@pytest.fixture(scope="module")
def timeline() -> pd.DataFrame:
    return trial_timeline(tables()).set_index("TRIAL_ID")


@pytest.mark.parametrize("dap, harvest_dap, phase", [
    (0, math.nan, "vegetative"),
    (45, math.nan, "vegetative"),
    (46, math.nan, "flowering"),
    (74, math.nan, "flowering"),
    (75, math.nan, "grain_fill"),
    (130, 120, "after_harvest"),
    (-3, math.nan, "before_planting"),
    (math.nan, math.nan, "unplaced"),
])
def test_classify_operation_uses_flowering_window(dap: float, harvest_dap: float,
                                                  phase: str) -> None:
    assert classify_operation(dap, 60, harvest_dap) == phase


def test_flowering_is_placed_from_planting(timeline: pd.DataFrame) -> None:
    t1 = timeline.loc["TR-1"]
    assert t1["flowering_date"] == pd.Timestamp("2026-05-31")
    assert t1["season_days"] == 151
    assert t1["irrigation_vegetative"] == 1


def test_trial_without_planting_gets_no_inferred_dates(timeline: pd.DataFrame) -> None:
    t2 = timeline.loc["TR-2"]
    assert t2["no_planting"] and pd.isna(t2["flowering_date"])
    assert "planting not recorded" in t2["narrative"]
    assert "Verdict FAIL: yield below 7 t/ha" in t2["narrative"]


def test_harvest_before_planting_is_flagged(timeline: pd.DataFrame) -> None:
    t3 = timeline.loc["TR-3"]
    assert t3["harvest_before_planting"] and t3["date_outside_start_year"]
    assert "before planting ⚠" in t3["narrative"]
    assert "operations dated in another year ⚠" in t3["narrative"]
    assert "misses the GBV target" in t3["narrative"]


def test_coverage_counts_only_plausible_seasons(timeline: pd.DataFrame) -> None:
    assert lifecycle_coverage(timeline) == {"trials": 3, "placed": 2, "planting_and_harvest": 2,
                                            "in_order": 1}


def test_phase_map_counts_trials_with_each_operation_type() -> None:
    germplasm = pd.DataFrame({"MATERIAL_ID": ["L1"], "PEDIGREE": ["A/B"], "STAGE_CODE_LID": ["S1"],
                              "ADVANCEMENT_DECISION": ["ADVANCE"]})
    observation = pd.DataFrame({"TRIAL_GUID": ["T1", "T1", "T2"],
                                "TRAIT_CODE": ["YIELD_T_HA", "YIELD_T_HA", "DISEASE_SCORE"],
                                "OBSERVATION_VALUE": [10.0, None, 3.0]})
    pm = phase_map({**tables(), "germplasm": germplasm, "observation": observation,
                    "genomics": pd.DataFrame(columns=["GENOTYPING_DATE", "GENOMIC_BREEDING_VALUE",
                                                      "MARKER_DROUGHT_TOLERANCE", "MARKER_MATURITY",
                                                      "MARKER_DISEASE_RESISTANCE",
                                                      "MARKER_YIELD_POTENTIAL"]),
                    "lab": pd.DataFrame(columns=["NUMBER_VALUE", "OBSERVATION_DATE"]),
                    "recommendations": tables()["recommendations"].assign(
                        PLANT_HEIGHT_CM=200.0, RECOMMENDATION_RATIONALE="x", RULE_VERSION="V1")})
    planting = pm[pm["column"] == "OPERATION_DATE (planting)"].iloc[0]
    assert (planting["present"], planting["total"]) == (2, 3)
    plot_yield = pm[pm["column"] == "OBSERVATION_VALUE (yield_t_ha)"].iloc[0]
    assert (plot_yield["present"], plot_yield["total"]) == (1, 3)
    assert pm["phase"].unique().tolist() == [p.name for p in PHASES]
