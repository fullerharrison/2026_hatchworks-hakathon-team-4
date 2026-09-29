import math

import pandas as pd
import pytest

from load import find_zip, load_tables
from rules import apply_rule, genomics_reconciliation, threshold_intervals

PASSING = {"YIELD_T_HA": 10.0, "MOISTURE_PCT": 18.0, "DISEASE_SCORE": 3.0,
           "GENOMIC_BREEDING_VALUE_MEAN": 106.0, "RESISTANT_MATERIAL_PCT": 50.0}


def verdict(**overrides: float) -> str:
    return str(apply_rule(pd.DataFrame([{**PASSING, **overrides}])).iloc[0])


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


@pytest.fixture(scope="module")
def tables() -> dict[str, pd.DataFrame]:
    return load_tables(find_zip())


def test_rule_reproduces_every_supplied_recommendation(tables: dict[str, pd.DataFrame]) -> None:
    rec = tables["recommendations"]
    assert (apply_rule(rec) == rec["TRIAL_RECOMMENDATION"]).all()


def test_used_thresholds_sit_inside_the_data_brackets(tables: dict[str, pd.DataFrame]) -> None:
    iv = threshold_intervals(tables["recommendations"])
    assert (iv["bracket_low"] < iv["bracket_high"]).all()
    assert ((iv["used"] >= iv["bracket_low"]) & (iv["used"] <= iv["bracket_high"])).all()


def test_only_the_block_mapping_reproduces_genomics_aggregates(
        tables: dict[str, pd.DataFrame]) -> None:
    rec = genomics_reconciliation(tables)
    assert rec["gbv_match_block"].all() and rec["resistant_match_block"].all()
    assert not rec["gbv_match_observation"].any()
    assert not rec["gbv_match_operations"].any()
