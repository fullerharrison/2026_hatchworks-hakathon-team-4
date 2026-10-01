"""Candidate migration contracts: baseline, filters, durable decisions and reviewed evidence."""
import json
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anyio
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from uc4_mcp.candidate_api import create_candidate_app
from uc4_mcp.candidate_history import CandidateHistory, Conflict
from uc4_mcp.candidate_core import candidate_rule, reconstruct
from uc4_mcp.candidate_server import create_candidate_server
from uc4_mcp.bridge import open_bridge
from uc4_mcp.agent import ask, CANDIDATE_SYSTEM_PROMPT
from uc4_mcp.evals import load_cases
from fakes import FakeChat, call, say


@pytest.fixture
def history(tmp_path: Path):
    return CandidateHistory(path=tmp_path / "history.sqlite3", legacy_log=tmp_path / "legacy.jsonl")


def test_candidate_baseline_filters_and_source_evidence(history):
    store = history.store()
    rows = store.query()
    assert len(rows) == 150
    assert {rag: sum(r["rag"] == rag for r in rows) for rag in ("GREEN", "AMBER", "RED")} == {
        "GREEN": 32, "AMBER": 53, "RED": 65}
    assert all(r["matches_supplied"] for r in rows)
    assert not any("CHK" in r["material_id"] for r in rows)
    assert len(store.query({"rag": "GREEN", "ranges": {"N_TRIALS_USED": {"min": 2}}})) == 32
    assert store.resolve("SYN-MZ-0001")["status"] == "many"
    detail = store.detail("SYN-MZ-00001")["result"]
    assert detail["evidence"]["observation"]
    assert all(row["source_file"] and row["line_no"] >= 2 for row in detail["evidence"]["observation"])


def test_api_lists_all_filters_exports_and_retires_trial_route(history):
    client = TestClient(create_candidate_app(lambda: None, get_history=lambda: history))
    body = client.get("/candidates").json()
    assert body["total"] == len(body["rows"]) == 150 and body["next_offset"] is None
    page = client.get("/candidates", params={"limit": 20, "offset": 20}).json()
    assert len(page["rows"]) == 20 and page["next_offset"] == 40
    assert client.get("/candidates", params={"rag": "GREEN"}).json()["total"] == 32
    params = {"rag": "RED", "ranges": json.dumps({"N_TRIALS_USED": {"max": 2}})}
    rows = client.get("/candidates", params=params).json()["rows"]
    assert all(r["rag"] == "RED" and r["metrics"]["N_TRIALS_USED"] <= 2 for r in rows)
    assert len(client.get("/candidates.csv", params=params).text.splitlines()) == len(rows) + 1
    assert client.get("/trials/SYN-TR-0001").status_code == 410
    assert client.get("/").status_code == 200


def test_decision_retry_stale_state_and_historical_import(tmp_path):
    log = tmp_path / "legacy.jsonl"
    legacy = {"trial_guid": "old-guid", "decision": "PASS", "recommendation": {"verdict": "HOLD"}}
    log.write_text(json.dumps(legacy) + "\n", encoding="utf-8")
    history = CandidateHistory(path=tmp_path / "history.sqlite3", legacy_log=log)
    assert history.legacy() == [legacy]
    assert history.import_legacy() == 0
    rec = history.store().resolve("SYN-MZ-00001")["result"]
    args = dict(query=rec["material_id"], action="ADVANCE", actor="Ada", reason="Advance after review",
                context={"location": "unknown", "source_channel": "breeder meeting"},
                recommendation_id=rec["recommendation_id"], previous_decision_id=None, request_id="request-1")
    first = history.decide(**args)
    assert history.decide(**args) == first and len(history.decisions()) == 1
    assert first["recommendation"]["snapshot_id"] == history.snapshot_id
    with pytest.raises(Conflict, match="changed"):
        history.decide(**(args | {"request_id": "request-2", "action": "HOLD"}))
    assert history.legacy() == [legacy]


def test_reviewed_lab_correction_creates_revision_and_preserves_decision(history):
    old = history.store()
    rec = old.resolve("SYN-MZ-00001")["result"]
    decision = history.decide(query=rec["material_id"], action="HOLD", actor="Ada",
        reason="Needs more evidence", context={"location": "unknown", "source_channel": "screen"},
        recommendation_id=rec["recommendation_id"], previous_decision_id=None, request_id="request-lab")
    lab = old.tables["lab"]
    row = lab[(lab.MATERIAL_GUID == rec["material_guid"]) & (lab.NUMBER_VALUE.notna())].iloc[0]
    trait = old.tables["dictionary"].set_index("TRAIT_GUID").loc[row.TRAIT_GUID]
    draft = history.draft(query=rec["material_id"], kind="correction", table="lab", row_id=row.ROWGUID,
        field="NUMBER_VALUE", value=float(row.NUMBER_VALUE) + 1, unit=trait.UNIT,
        actor="Ada", reason="Correct lab transcription", observed_at="2026-10-01", source="Lab notebook")
    assert history.store().resolve(rec["material_id"])["result"] == rec
    history.review(draft["id"], "submit", "Ada", "Ready for validation")
    assert history.review(draft["id"], "approve", "Bob", "Checked notebook")["id"] == draft["id"]
    preview = history.preview(draft["id"])
    assert preview["candidate_count"] == 1 and preview["affected"][0]["material_id"] == rec["material_id"]
    changed = history.activate(draft["id"], preview["base_revision"], "Bob", "Activate correction")
    assert changed["revision_id"] != old.revision_id
    assert history.store().resolve(rec["material_id"])["result"]["recommendation_id"] != rec["recommendation_id"]
    assert history.decisions(rec["material_guid"])[0] == decision
    detail = history.store().detail(rec["material_id"])["result"]
    assert next(x for x in detail["evidence"]["lab"] if x["row_id"] == row.ROWGUID)["NUMBER_VALUE"] == row.NUMBER_VALUE
    rollback = history.rollback(old.revision_id, "Bob", "Return to baseline")
    assert rollback["revision_id"] != old.revision_id
    assert history.store().resolve(rec["material_id"])["result"]["metrics"] == rec["metrics"]


def test_shared_check_correction_previews_all_affected_candidates(history):
    store = history.store()
    candidate = store.resolve("SYN-MZ-00001")["result"]
    trial = store.means[store.means.MATERIAL_GUID == candidate["material_guid"]].iloc[0].TRIAL_GUID
    check_entry = store.tables["bridge"][(store.tables["bridge"].TRIAL_GUID == trial) &
                                          (store.tables["bridge"].ENTRY_ROLE_LID == "CHECK")].iloc[0]
    obs = store.tables["observation"][(store.tables["observation"].TRIAL_ENTRY_RELATIONSHIP_GUID == check_entry.TRIAL_ENTRY_GUID) &
                                      (store.tables["observation"].TRAIT_CODE == "YIELD_T_HA")].iloc[0]
    draft = history.draft(query=candidate["material_id"], kind="correction", table="observation",
        row_id=obs.OBSERVATION_UUID, field="NUMBER_VALUE", value=float(obs.NUMBER_VALUE) + 1,
        unit="t/ha", actor="Ada", reason="Correct check plot", observed_at="2026-10-01", source="Field book")
    history.review(draft["id"], "submit", "Ada", "Checked field book")
    history.review(draft["id"], "approve", "Bob", "Validated measurement")
    affected = history.preview(draft["id"])["affected"]
    assert len(affected) > 1


def test_threshold_equality_missing_values_and_no_field_precedence():
    base = dict(YIELD_VS_CHECK_PCT=103., DISEASE_SCORE_MEAN=4., MOISTURE_PCT_MEAN=23.,
                GERMINATION_PCT=90., FUMONISIN_PPM=4., MARKER_DISEASE_RESISTANCE="RESISTANT", N_TRIALS_USED=2)
    cases = [({}, "GREEN"), ({"YIELD_VS_CHECK_PCT": 95}, "AMBER"),
             ({"DISEASE_SCORE_MEAN": 6}, "AMBER"), ({"DISEASE_SCORE_MEAN": 6.0001}, "RED"),
             ({"MOISTURE_PCT_MEAN": 25.01}, "AMBER"), ({"GERMINATION_PCT": 84.99}, "AMBER"),
             ({"N_TRIALS_USED": 0, "FUMONISIN_PPM": 5}, "AMBER"),
             ({"FUMONISIN_PPM": None}, "AMBER"), ({"MARKER_DISEASE_RESISTANCE": "UNKNOWN"}, "AMBER"),
             ({"GENOMIC_BREEDING_VALUE": 0, "COLD_TEST_PCT": 0}, "GREEN")]
    assert candidate_rule(pd.DataFrame([base | change for change, _ in cases])).tolist() == [rag for _, rag in cases]


def test_equal_trial_weighting_with_unbalanced_replicates(history):
    store = history.store()
    candidate = next(r for r in store.query() if r["metrics"]["N_TRIALS_USED"] == 2 and r["excluded_trials"] == 0)
    tables = {k: v.copy() for k, v in store.tables.items()}
    bridge = tables["bridge"]
    trials = sorted(bridge.loc[bridge.MATERIAL_GUID == candidate["material_guid"], "TRIAL_GUID"].unique())
    observations = tables["observation"]
    for trial, value in zip(trials, [10., 20.]):
        entries = bridge[(bridge.TRIAL_GUID == trial) & (bridge.MATERIAL_GUID == candidate["material_guid"])]
        checks = bridge[(bridge.TRIAL_GUID == trial) & (bridge.ENTRY_ROLE_LID == "CHECK")]
        observations.loc[observations.TRIAL_ENTRY_RELATIONSHIP_GUID.isin(entries.TRIAL_ENTRY_GUID) &
                         (observations.TRAIT_CODE == "YIELD_T_HA"), "NUMBER_VALUE"] = value
        observations.loc[observations.TRIAL_ENTRY_RELATIONSHIP_GUID.isin(checks.TRIAL_ENTRY_GUID) &
                         (observations.TRAIT_CODE == "YIELD_T_HA"), "NUMBER_VALUE"] = 10.
    remove = bridge[(bridge.TRIAL_GUID == trials[1]) & (bridge.MATERIAL_GUID == candidate["material_guid"])].iloc[1:].TRIAL_ENTRY_GUID
    tables["observation"] = observations[~observations.TRIAL_ENTRY_RELATIONSHIP_GUID.isin(remove)]
    rec, _, _ = reconstruct(tables)
    result = rec[rec.MATERIAL_GUID == candidate["material_guid"]].iloc[0]
    assert result.REBUILT_YIELD_VS_CHECK_PCT == 150.


def test_concurrent_decisions_one_wins_and_retry_payload_is_bound(history):
    rec = history.store().resolve("SYN-MZ-00001")["result"]
    args = dict(query=rec["material_id"], action="HOLD", actor="Ada", reason="Needs additional evidence",
                context={"location": "unknown", "source_channel": "meeting"},
                recommendation_id=rec["recommendation_id"], previous_decision_id=None)
    def write(request_id):
        try:
            return history.decide(**args, request_id=request_id)
        except Conflict:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, ["concurrent-a", "concurrent-b"]))
    assert sum(r is not None for r in results) == 1
    saved = next(r for r in results if r)
    with pytest.raises(Conflict, match="different decision"):
        history.decide(**(args | {"action": "ADVANCE"}), request_id=saved["request_id"])


def test_rejection_and_stale_activation_preserve_all_review_events(history):
    def approved(text):
        d = history.draft(query="SYN-MZ-00001", kind="metadata", field="NOTE", value=text,
            actor="Ada", reason="Record review context", observed_at="2026-10-01", source="Notebook")
        history.review(d["id"], "submit", "Ada", "Ready for review")
        history.review(d["id"], "approve", "Bob", "Checked review context")
        return d
    a, b = approved("First note"), approved("Second note")
    base = history.preview(a["id"])["base_revision"]
    history.activate(b["id"], base, "Bob", "Publish second note")
    with pytest.raises(Conflict, match="changed"):
        history.activate(a["id"], base, "Bob", "Publish first note")
    b_history = next(x for x in history.enrichment() if x["id"] == b["id"])
    assert [e["action"] for e in b_history["events"]] == ["draft", "submit", "approve", "activate"]
    rejected = history.draft(query="SYN-MZ-00001", kind="metadata", field="NOTE", value="Discard this note",
        actor="Ada", reason="Unverified information", observed_at="2026-10-01", source="Notebook")
    history.review(rejected["id"], "submit", "Ada", "Needs verification")
    history.review(rejected["id"], "reject", "Bob", "Insufficient evidence")
    with pytest.raises(ValueError, match="approved"):
        history.preview(rejected["id"])


def test_new_archive_preserves_old_saved_recommendations(history, tmp_path):
    original = history.store()
    original_rec = original.resolve("SYN-MZ-00001")["result"]
    replacement = tmp_path / "replacement.zip"
    shutil.copyfile(history.archive, replacement)
    with zipfile.ZipFile(replacement, "a") as archive:
        archive.writestr("delivery_note.txt", "A new delivery of the same compatible tables")
    newer = CandidateHistory(path=history.path, archive=replacement, legacy_log=history.legacy_log)
    assert newer.snapshot_id != history.snapshot_id
    assert newer.store().snapshot_id == newer.snapshot_id
    assert newer.store(original.revision_id).resolve("SYN-MZ-00001")["result"] == original_rec


def test_candidate_mcp_agent_and_rule_grounding(history):
    model = FakeChat([call("score_candidate", query="SYN-MZ-00001"),
                      say("SYN-MZ-00001 is AMBER [tool:score_candidate].")])
    async def run():
        async with open_bridge(create_candidate_server(lambda: history)) as bridge:
            answer = await ask("Explain SYN-MZ-00001", model=model, bridge=bridge)
            rule = await bridge.call("get_candidate_rule", {})
            listing = await bridge.call("query_candidates", {"rag": "GREEN", "limit": 10})
            retired = await bridge.call("score_trial", {"query": "SYN-TR-0001"})
            return answer, rule, listing, retired
    answer, rule, listing, retired = anyio.run(run)
    assert answer.status == "answered" and not answer.problems
    assert model.seen[0][0]["content"] == CANDIDATE_SYSTEM_PROMPT
    assert rule.status == "ok" and rule.result["result"]["provisional"]
    assert listing.result["result"]["total"] == 32 and listing.result["result"]["next_offset"] == 10
    assert retired.status == "none" and "retired" in retired.result["message"]


def test_candidate_evaluation_oracles(history):
    async def run():
        async with open_bridge(create_candidate_server(lambda: history)) as bridge:
            for case in load_cases():
                if "oracle" not in case.expect:
                    continue
                oracle = case.expect["oracle"]
                result = await bridge.call(oracle["name"], oracle["args"])
                if case.expect.get("status") == "clarify":
                    assert result.status == "many"
                    assert len(result.result["candidates"]) == case.expect["candidates"]
                elif case.id == "q12-absent":
                    assert result.status == "none"
                else:
                    assert result.status == "ok", (case.id, result.result)
                    for value in case.expect.get("include", []):
                        assert value in json.dumps(result.result), case.id
    anyio.run(run)


def test_irrigation_correction_excludes_trial_and_discloses_source_conflict(history):
    store = history.store()
    candidate = store.resolve("SYN-MZ-00001")["result"]
    field = store.tables["bridge"].loc[store.tables["bridge"].MATERIAL_GUID == candidate["material_guid"], "FIELD_ENTITY_ID"].iloc[0]
    op = store.tables["operations"][(store.tables["operations"].ATTACHED_TO_FIELD_ENTITY_ID == field) &
                                     (store.tables["operations"].OPERATION_TYPE_LID == "IRRIGATION")].iloc[0]
    draft = history.draft(query=candidate["material_id"], kind="correction", table="operations",
        row_id=op.ID, field="STATUS_LID", value="MISSED", actor="Ada", reason="Field book shows missed irrigation",
        observed_at="2026-10-01", source="Field book")
    history.review(draft["id"], "submit", "Ada", "Ready for verification")
    history.review(draft["id"], "approve", "Bob", "Verified field book")
    preview = history.preview(draft["id"])
    assert any("missed operation has actual date" in warning["check"] for warning in preview["source_warnings"])
    changed = next(r for r in preview["affected"] if r["material_id"] == candidate["material_id"])
    assert changed["after_metrics"]["N_TRIALS_USED"] == 0 and changed["after"] == "AMBER"
    history.activate(draft["id"], preview["base_revision"], "Bob", "Publish with disclosed date conflict")
    assert history.store().resolve(candidate["material_id"])["result"]["source_warnings"]
