"""Step 3: contract dataclasses, response envelope, JSON safety and evidence references."""

import dataclasses
import json
import math

import numpy as np
import pandas as pd
import pytest

from uc4_mcp.models import (
    Candidate,
    Criterion,
    EvidenceRow,
    Flag,
    Recommendation,
    evidence_ref,
    many,
    none,
    ok,
    parse_evidence_ref,
    to_json_safe,
)

Tables = dict[str, pd.DataFrame]

CRITERION = Criterion(field="YIELD_T_HA", label="Grain yield", value=np.float64(9.5), test=">=",
                      threshold=9.0, bracket=(8.9, 9.14), kind="pass", passed=True,
                      triggered=False)
FLAG = Flag(code="THRESHOLDS_INFERRED", severity="info", message="SYNTH_V1 is inferred",
            evidence_row_ids=("trial_recommendations_synthetic.csv#G1",))


def _recommendation() -> Recommendation:
    return Recommendation(
        trial_guid="G1", trial_id="SYN-TR-0001", verdict="PASS", colour="green",
        criteria=(CRITERION,), knockout=(), reason="PASS: all five criteria met",
        rule_version="SYNTH_V1 (inferred)", supplied_verdict="PASS", matches_supplied=True,
        supplied_rationale="", rationale_omits=(),
        evidence_row_ids=("trial_recommendations_synthetic.csv#G1",), flags=(FLAG,))


# --- dataclasses ------------------------------------------------------------


@pytest.mark.parametrize("obj, field", [
    (EvidenceRow(source_file="f.csv", row_id="1", line_no=2, trial_guid=None, material_guid=None,
                 field="X", value=1, uom=None, date=None), "value"),
    (CRITERION, "passed"),
    (FLAG, "code"),
    (_recommendation(), "verdict"),
])
def test_contracts_are_frozen(obj: object, field: str) -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(obj, field, "changed")


def test_evidence_row_flags_default_empty() -> None:
    row = EvidenceRow(source_file="f.csv", row_id="1", line_no=2, trial_guid=None,
                      material_guid=None, field="X", value=None, uom=None, date=None)
    assert row.flags == ()


# --- JSON safety ------------------------------------------------------------


@pytest.mark.parametrize("value, expected, kind", [
    (np.int64(2024), 2024, int),
    (np.float64(9.5), 9.5, float),
    (np.bool_(True), True, bool),
    (math.nan, None, type(None)),
    (np.float64("nan"), None, type(None)),
    (pd.NaT, None, type(None)),
    (pd.NA, None, type(None)),
    (np.str_("SYN"), "SYN", str),
])
def test_scalars_convert_to_python(value: object, expected: object, kind: type) -> None:
    out = to_json_safe(value)
    assert out == expected and type(out) is kind


def test_timestamp_becomes_iso_string() -> None:
    assert to_json_safe(pd.Timestamp("2026-09-26 12:00")) == "2026-09-26T12:00:00"


def test_nested_dataclasses_become_plain_json() -> None:
    rec = dataclasses.replace(_recommendation(), criteria=(
        dataclasses.replace(CRITERION, value=math.nan, passed=False),))
    out = to_json_safe({"rec": rec, "years": [np.int64(2024)], "pair": (1, np.float64("nan"))})
    text = json.dumps(out, allow_nan=False)
    back = json.loads(text)
    assert back["rec"]["criteria"][0]["value"] is None
    assert back["rec"]["criteria"][0]["bracket"] == [8.9, 9.14]
    assert back["rec"]["flags"][0]["code"] == "THRESHOLDS_INFERRED"
    assert back["years"] == [2024] and back["pair"] == [1, None]


def test_unknown_types_raise() -> None:
    with pytest.raises(TypeError):
        to_json_safe(object())


# --- envelope ---------------------------------------------------------------


def test_ok_envelope() -> None:
    assert ok({"a": 1}, "found") == {"status": "ok", "result": {"a": 1}, "message": "found"}


def test_many_envelope_lists_candidates() -> None:
    env = many([Candidate(id="SYN-TR-0030", guid="G30", label="SYN-TR-0030 (2024)")], "which?")
    assert env == {"status": "many", "message": "which?",
                   "candidates": [Candidate(id="SYN-TR-0030", guid="G30",
                                            label="SYN-TR-0030 (2024)")]}
    assert json.loads(json.dumps(to_json_safe(env)))["candidates"][0]["id"] == "SYN-TR-0030"


def test_none_envelope() -> None:
    assert none("no trial matches 'XYZ'") == {"status": "none", "message": "no trial matches 'XYZ'"}


# --- evidence references ----------------------------------------------------


def test_evidence_ref_format() -> None:
    row = pd.Series({"_source_file": "trial_synthetic.csv", "_row_id": "G1"})
    assert evidence_ref(row) == "trial_synthetic.csv#G1"


@pytest.mark.parametrize("table", ["germplasm", "trial", "observation", "operations", "lab",
                                   "genomics", "recommendations"])
def test_evidence_ref_round_trips_to_its_row(tables: Tables, table: str) -> None:
    df = tables[table]
    for i in (0, len(df) - 1):
        source_file, row_id = parse_evidence_ref(evidence_ref(df.iloc[i]))
        match = df[(df["_source_file"] == source_file) & (df["_row_id"] == row_id)]
        assert len(match) == 1 and match.index[0] == df.index[i]


def test_trial_and_recommendation_refs_differ(tables: Tables) -> None:
    # Both files key on TRIAL_GUID, so the bare row_id alone is ambiguous.
    t = tables["trial"].iloc[0]
    rec = tables["recommendations"]
    r = rec[rec["_row_id"] == t["_row_id"]].iloc[0]
    assert evidence_ref(t) != evidence_ref(r)


def test_parse_rejects_malformed_refs() -> None:
    with pytest.raises(ValueError):
        parse_evidence_ref("no-separator")
