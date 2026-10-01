"""Replacement snapshot evidence, plus failure cases that prevent unsafe joins."""
import zipfile

import pandas as pd
import pytest

from candidate_analysis import (ZIP_PATH, load_current, audit_links,
                                consistency, reconstruct, candidate_rule, reason_precision_audit)


@pytest.fixture(scope="module")
def current():
    return load_current()


def test_recorded_relationships_and_identities_resolve(current):
    links = audit_links(current)
    assert (links.resolved == links.distinct).all()
    assert links.missing_rows.sum() == 0
    assert consistency(current).violations.sum() == 0
    bridge = current["bridge"]
    assert bridge.TRIAL_GUID.nunique() == 72
    assert bridge.groupby("TRIAL_GUID").size().eq(24).all()
    assert bridge.ENTRY_ROLE_LID.value_counts().to_dict() == {"TRIAL_ENTRY": 1296, "CHECK": 432}
    assert current["germplasm"].MATERIAL_GUID.nunique() == 152


def test_candidate_aggregates_reconstruct_and_checks_are_not_candidates(current):
    rec, means, audit = reconstruct(current)
    assert audit.matches.sum() == audit.compared.sum()
    assert audit.missing_disagreement.sum() == 0
    assert len(rec) == 150
    assert not rec.MATERIAL_ID.str.contains("CHK").any()
    assert means[means.EXCLUDED_IRRIGATION_MISSED].TRIAL_GUID.nunique() == 5
    assert (rec.REBUILT_EXCLUDED_TRIALS > 0).sum() == 30
    assert rec.CAVEAT_MATCH.all()
    no_field = rec[rec.N_TRIALS_USED == 0]
    assert set(no_field.MATERIAL_ID) == {"SYN-MZ-00149", "SYN-MZ-00150"}
    assert no_field.YIELD_VS_CHECK_PCT.isna().all()
    alternative_delta = (rec.YIELD_VS_CHECK_PCT - rec.MEAN_TRIAL_RATIOS).abs()
    assert (alternative_delta <= .05 + 1e-9).sum() == 68
    assert candidate_rule(rec).equals(rec.SYSTEM_RAG.rename("INFERRED_RAG"))
    source = rec.copy()
    for col in ["YIELD_VS_CHECK_PCT", "DISEASE_SCORE_MEAN", "MOISTURE_PCT_MEAN",
                "GERMINATION_PCT", "FUMONISIN_PPM", "N_TRIALS_USED"]:
        source[col] = rec[f"REBUILT_{col}"]
    assert (candidate_rule(source) == rec.SYSTEM_RAG).all()
    reasons = reason_precision_audit(rec)
    assert reasons.rebuilt_warning_agrees.all()


def test_reason_printed_value_does_not_override_numeric_evidence():
    rec = pd.DataFrame([dict(MATERIAL_ID="example", DISEASE_SCORE_MEAN=6.02,
                            REBUILT_DISEASE_SCORE_MEAN=6.023,
                            SYSTEM_REASON="Fails must-pass: disease score 6.0 (above limit 6.0)",
                            _source_file="example.csv", _line_no=2)])
    audit = reason_precision_audit(rec)
    assert audit.reason_printed_value.iloc[0] == 6.0
    assert not audit.printed_warning_agrees.iloc[0]
    assert audit.supplied_warning_agrees.all() and audit.rebuilt_warning_agrees.all()


def test_identity_conflict_is_reported_without_repair(current):
    changed = {k: v.copy() for k, v in current.items()}
    changed["bridge"].loc[0, "MATERIAL_ID"] = "WRONG-ID"
    audit = consistency(changed).set_index("check")
    assert audit.loc["bridge: material GUID agrees with material ID", "violations"] == 1
    assert changed["bridge"].loc[0, "MATERIAL_ID"] == "WRONG-ID"


def test_duplicate_bridge_key_cannot_multiply_observations(current):
    changed = dict(current)
    changed["bridge"] = pd.concat([current["bridge"], current["bridge"].iloc[:1]])
    with pytest.raises(pd.errors.MergeError):
        reconstruct(changed)


def test_missing_reference_is_audited(current):
    changed = {k: v.copy() for k, v in current.items()}
    changed["observation"].loc[0, "TRIAL_ENTRY_RELATIONSHIP_GUID"] = "MISSING"
    links = audit_links(changed).set_index("source")
    assert links.loc["observation.TRIAL_ENTRY_RELATIONSHIP_GUID", "unresolved"] == "MISSING"
    assert consistency(changed).violations.sum() >= 1


def test_archive_rejects_ambiguous_members(tmp_path):
    copy = tmp_path / "ambiguous.zip"
    with zipfile.ZipFile(ZIP_PATH) as source, zipfile.ZipFile(copy, "w") as target:
        for name in source.namelist():
            target.writestr(name, source.read(name))
        member = "candidate_recommendations_synthetic.csv"
        target.writestr("candidate_recommendations_synthetic 1.csv", source.read(member))
    with pytest.raises(ValueError, match="expected one member"):
        load_current(copy)


def test_rule_boundaries_and_missing_data():
    base = dict(YIELD_VS_CHECK_PCT=103., DISEASE_SCORE_MEAN=4., MOISTURE_PCT_MEAN=23.,
                GERMINATION_PCT=90., FUMONISIN_PPM=4., MARKER_DISEASE_RESISTANCE="RESISTANT", N_TRIALS_USED=2)
    scenarios = [({}, "GREEN"), ({"YIELD_VS_CHECK_PCT": 94.99}, "RED"),
                 ({"DISEASE_SCORE_MEAN": 6.01}, "RED"), ({"FUMONISIN_PPM": 4.01}, "RED"),
                 ({"MOISTURE_PCT_MEAN": 26.}, "AMBER"), ({"GERMINATION_PCT": 80.}, "AMBER"),
                 ({"MARKER_DISEASE_RESISTANCE": "SUSCEPTIBLE"}, "AMBER"),
                 ({"MARKER_DISEASE_RESISTANCE": None}, "AMBER"),
                 ({"N_TRIALS_USED": 1}, "AMBER"), ({"N_TRIALS_USED": 0}, "AMBER"),
                 ({"YIELD_VS_CHECK_PCT": float("nan")}, "AMBER")]
    frame = pd.DataFrame([{**base, **change} for change, _ in scenarios])
    assert candidate_rule(frame).tolist() == [expected for _, expected in scenarios]
