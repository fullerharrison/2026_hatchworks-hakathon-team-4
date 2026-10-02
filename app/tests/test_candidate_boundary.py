"""Boundary eligibility and captured provenance; all history is isolated."""
import copy
import csv
import io
import json

import anyio
import pytest
from fastapi.testclient import TestClient

from uc4_mcp.bridge import open_bridge
from uc4_mcp.candidate_api import create_candidate_app
from uc4_mcp.candidate_history import CandidateHistory
from uc4_mcp.candidate_server import create_candidate_server
from uc4_mcp.candidates import CandidateStore, review_data
from uc4_mcp.filter_intent import unsupported_queue


@pytest.fixture
def history(tmp_path):
    return CandidateHistory(path=tmp_path / "history.sqlite3", legacy_log=tmp_path / "legacy.jsonl")


def boundary(field="MOISTURE_PCT_MEAN", kind="green_gate", tolerance=1, side="both"):
    return dict(field=field, kind=kind, tolerance=tolerance, side=side)


def test_precision_sides_zero_missing_and_ties(history):
    store = history.store()
    template = next(iter(store.by_guid.values()))
    values = [22, 23, 23.77, 24, 24.01, None, 23.00000001]
    store.by_guid = {}
    for i, value in enumerate(values):
        rec = copy.deepcopy(template)
        rec.update(material_guid=str(i), material_id=f"M{i}")
        rec["metrics"]["MOISTURE_PCT_MEAN"] = value
        store.by_guid[str(i)] = rec
    ids = lambda filters: [r["material_id"] for r in store.query(filters)]
    assert ids({"boundary": boundary(), "include_missing": True}) == ["M0", "M1", "M2", "M3", "M6"]
    assert ids({"boundary": boundary(side="meets")}) == ["M0", "M1"]
    assert ids({"boundary": boundary(side="fails")}) == ["M2", "M3", "M6"]
    assert ids({"boundary": boundary(tolerance=0)}) == ["M1"]
    assert ids({"boundary": boundary(), "sort": "boundary_distance"}) == ["M1", "M6", "M2", "M0", "M3"]
    assert ids({"boundary": boundary(), "sort": "boundary_distance", "descending": True}) == ["M0", "M3", "M2", "M6", "M1"]
    assert ids({"boundary": boundary(), "ranges": {"MOISTURE_PCT_MEAN": {"min": 23.8}}}) == ["M3"]
    for rec in store.by_guid.values():
        rec["metrics"]["DISEASE_SCORE_MEAN"] = 6
    assert not store.query({"boundary": boundary("DISEASE_SCORE_MEAN", "red_knockout", 0, "meets")})
    assert len(store.query({"boundary": boundary("DISEASE_SCORE_MEAN", "red_knockout", 0, "fails")})) == 7


@pytest.mark.parametrize("bad", [False, [], {}, "x", boundary(tolerance=True), boundary(tolerance=-1),
    boundary(tolerance=float("nan")), boundary(tolerance=float("inf")), boundary(tolerance="1"),
    boundary(field="MARKER_DISEASE_RESISTANCE"), boundary(field="COLD_TEST_PCT"),
    boundary(kind="bogus"), boundary(side="bogus"), boundary(kind=[]), boundary(field={}),
    boundary(field="N_TRIALS_USED", tolerance=.5), boundary(field="MOISTURE_PCT_MEAN", kind="red_knockout"),
    boundary() | {"extra": 1}])
def test_validation(history, bad):
    client = TestClient(create_candidate_app(lambda: None, get_history=lambda: history))
    for path in ("/candidates", "/candidates.csv"):
        assert client.get(path, params={"boundary": json.dumps(bad)}).status_code == 422


def test_routes_mcp_csv_pagination_identity(history):
    store = history.store()
    saved = copy.deepcopy(store.by_guid)
    filters = {"boundary": boundary(), "sort": "boundary_distance", "rag": "AMBER"}
    expected = store.query(filters)
    client = TestClient(create_candidate_app(lambda: None, get_history=lambda: history))
    params = filters | {"boundary": json.dumps(filters["boundary"])}
    data = client.get("/candidates", params=params).json()
    assert data["rows"] == expected
    assert data["overview"]["rag"] == {"GREEN": 32, "AMBER": 53, "RED": 65}
    assert data["processing"]["revision_id"] == data["revision_id"]
    pages = []
    for offset in range(0, len(expected), 3):
        pages.extend(client.get("/candidates", params=params | {"limit": 3, "offset": offset}).json()["rows"])
    assert pages == expected
    exported = list(csv.DictReader(io.StringIO(client.get("/candidates.csv", params=params).text)))
    assert [r["material_id"] for r in exported] == [r["material_id"] for r in expected]
    assert all(float(x["boundary_distance"]) == r["review"]["boundary"]["distance"] for x, r in zip(exported, expected))
    baseline_header = client.get("/candidates.csv").text.splitlines()[0]
    assert "boundary" not in baseline_header
    async def check():
        async with open_bridge(create_candidate_server(lambda: history)) as bridge:
            result = await bridge.call("query_candidates", filters)
            actual = result.result["result"]["rows"]
            assert [r["material_id"] for r in actual] == [r["material_id"] for r in expected]
            assert [r["review"] for r in actual] == [r["review"] for r in expected]
    anyio.run(check)
    for params in ({"boundary": "{"}, {"boundary": "null"}, {"sort": "boundary_distance"}):
        assert client.get("/candidates", params=params).status_code == 422
    assert store.by_guid == saved
    assert history.decisions() == []


def test_gate_counts_precedence_and_typed_clarification(history):
    store = history.store()
    rec = copy.deepcopy(next(iter(store.by_guid.values())))
    rec["criteria"][0]["value"] = None
    rec["criteria"][1]["value"] = 7
    rec["metrics"]["DISEASE_SCORE_MEAN"] = 7
    rec["metrics"]["N_TRIALS_USED"] = 0
    review = review_data(rec)
    assert review["green_counts"]["unknown"] == 1
    assert sum(review["green_counts"].values()) == 7
    assert "DISEASE_SCORE_MEAN" in review["triggered_knockout_fields"]
    assert review["no_usable_field_data"] and not review["knockout_precedence_applies"]
    assert review["decisive_assessments"][0]["field"] == "N_TRIALS_USED"
    assert len({r["material_guid"] for r in store.query()}) == 150
    assert store.query({"boundary": boundary("N_TRIALS_USED", tolerance=1)})
    for text in ("Near moisture threshold and GREEN", "borderline candidates", "within 1 of the boundary",
                 "closest to GREEN boundaries", "within 1 percentage point of the moisture gate"):
        proposal = unsupported_queue(text)
        assert proposal.status == "clarification" and proposal.filters is None
        assert "Near a rule boundary" in proposal.clarification


def test_provenance_aggregates_scope_and_corrections(history):
    store = history.store()
    rec = store.detail("SYN-MZ-00001")["result"]
    evidence = rec["criterion_evidence"]
    for metric, payload in evidence.items():
        assert payload["revision_id"] == rec["revision_id"] and payload["material_guid"] == rec["material_guid"]
        assert payload["calculation"]
        assert all(row["source_file"] and row["row_id"] and row["line_no"] >= 2 for rows in payload["source_rows"].values() for row in rows)
    for metric, trait in [("DISEASE_SCORE_MEAN", "DISEASE_SCORE"), ("MOISTURE_PCT_MEAN", "MOISTURE_PCT"), ("YIELD_VS_CHECK_PCT", "YIELD_T_HA")]:
        payload = evidence[metric]
        membership = {b["TRIAL_ENTRY_GUID"]: b for b in payload["source_rows"]["bridge"]}
        values = {}
        for row in payload["source_rows"]["observation"]:
            assert row["TRAIT_CODE"] == trait
            b = membership[row["TRIAL_ENTRY_RELATIONSHIP_GUID"]]
            values.setdefault((b["TRIAL_GUID"], b["MATERIAL_GUID"]), []).append(row["NUMBER_VALUE"])
        means = {key: sum(v)/len(v) for key, v in values.items()}
        used = [t for t in rec["trial_comparisons"] if not t["EXCLUDED_IRRIGATION_MISSED"]]
        candidate_mean = sum(means[(t["TRIAL_GUID"], rec["material_guid"])] for t in used)/len(used)
        if metric == "YIELD_VS_CHECK_PCT":
            check_means = []
            for t in used:
                check_ids = {b["MATERIAL_GUID"] for b in membership.values() if b["TRIAL_GUID"] == t["TRIAL_GUID"] and b["ENTRY_ROLE_LID"] == "CHECK"}
                check_means.append(sum(means[(t["TRIAL_GUID"], g)] for g in check_ids)/len(check_ids))
            candidate_mean = 100*candidate_mean/(sum(check_means)/len(check_means))
        assert candidate_mean == pytest.approx(rec["metrics"][metric])
    assert rec["metrics"]["N_TRIALS_USED"] == sum(not t["EXCLUDED_IRRIGATION_MISSED"] for t in evidence["N_TRIALS_USED"]["trial_comparisons"])
    excluded_rec = next(r for r in store.query() if r["excluded_trials"])
    excluded = store.detail(excluded_rec["material_guid"])["result"]["criterion_evidence"]["N_TRIALS_USED"]
    assert any(t["EXCLUDED_IRRIGATION_MISSED"] for t in excluded["trial_comparisons"])
    lab = evidence["GERMINATION_PCT"]
    assert len(lab["source_rows"]["lab"]) == 1 and lab["trial_comparisons"] == []
    assert lab["source_rows"]["lab"][0]["NUMBER_VALUE"] == rec["metrics"]["GERMINATION_PCT"]
    assert "Context only" in evidence["GENOMIC_BREEDING_VALUE"]["calculation"]
    row = lab["source_rows"]["lab"][0]
    overlays = [dict(kind="correction", table="lab", row_id=row["row_id"], field="NUMBER_VALUE", value=v, id=str(i), source="Notebook", observed_at="2026-10-01", actor="Ada") for i, v in enumerate([91, 92])]
    corrected = CandidateStore(store.base_tables, store.snapshot_id, "corrected", overlays).detail(rec["material_guid"])["result"]
    payload = corrected["criterion_evidence"]["GERMINATION_PCT"]
    effective = payload["source_rows"]["lab"][0]
    assert effective["NUMBER_VALUE"] == 92
    assert effective["original_values"]["NUMBER_VALUE"] == row["NUMBER_VALUE"]
    assert effective["latest_corrections"]["NUMBER_VALUE"]["id"] == "1"
    assert len(payload["active_corrections"]) == 2
    assert corrected["criterion_evidence"]["FUMONISIN_PPM"]["active_corrections"] == []


def test_excluded_trial_means_use_effective_observations(history):
    store = history.store()
    selected = next(r for r in store.query() if r["excluded_trials"] and r["metrics"]["N_TRIALS_USED"])
    rec = store.detail(selected["material_guid"])["result"]
    payload = rec["criterion_evidence"]["MOISTURE_PCT_MEAN"]
    obs = payload["source_rows"]["observation"]
    original = next(x for x in obs if not x["EXCLUDED_IRRIGATION_MISSED"])
    correction = dict(kind="correction",table="observation",row_id=original["row_id"],field="NUMBER_VALUE",value=27.123456,id="correct-field",source="Notebook")
    corrected = CandidateStore(store.base_tables, store.snapshot_id, "effective", [correction]).detail(selected["material_guid"])["result"]
    rows = corrected["criterion_evidence"]["MOISTURE_PCT_MEAN"]["source_rows"]["observation"]
    trial_values = {}
    for row in rows:
        if not row["EXCLUDED_IRRIGATION_MISSED"]:
            trial_values.setdefault(row["FIELD_ID"], []).append(row["NUMBER_VALUE"])
    expected = sum(sum(v)/len(v) for v in trial_values.values()) / len(trial_values)
    assert corrected["metrics"]["MOISTURE_PCT_MEAN"] == pytest.approx(expected)
    effective = next(r for r in rows if r["row_id"] == original["row_id"])
    assert effective["original_values"]["NUMBER_VALUE"] == original["NUMBER_VALUE"]
    assert any(r["EXCLUDED_IRRIGATION_MISSED"] for r in rows)
