"""Processing diagnostics are runtime context, separate from durable recommendations."""
import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from uc4_mcp import candidates
from uc4_mcp.candidate_api import create_candidate_app
from uc4_mcp.candidate_history import CandidateHistory
from uc4_mcp.candidate_core import FILES


@pytest.fixture
def history(tmp_path):
    return CandidateHistory(path=tmp_path / "processing.sqlite3", legacy_log=tmp_path / "missing.jsonl")


def clock(monkeypatch, values):
    ticks = iter(values)
    monkeypatch.setattr(candidates, "time", SimpleNamespace(perf_counter=lambda: next(ticks)))


def approved(history, kind="correction"):
    store = history.store()
    row = store.tables["lab"].loc[store.tables["lab"].MATERIAL_GUID == store.resolve("SYN-MZ-00001")["result"]["material_guid"]].iloc[0]
    trait = store.tables["dictionary"].set_index("TRAIT_GUID").loc[row.TRAIT_GUID]
    args = dict(kind=kind, field="NOTE", value="New context") if kind == "metadata" else dict(
        kind=kind, table="lab", row_id=row.ROWGUID, field="NUMBER_VALUE", value=float(row.NUMBER_VALUE)+1, unit=trait.UNIT)
    draft = history.draft(query="SYN-MZ-00001", actor="Ada", reason="Correct notebook evidence",
                          observed_at="2026-10-01", source="Notebook", **args)
    for action in ("submit", "approve"):
        history.review(draft["id"], action, "Ada", "Verified notebook evidence")
    return draft


def saved(history):
    with history._db() as db:
        return [tuple(r) for r in db.execute("SELECT * FROM recommendations ORDER BY revision_id,material_guid")]


def test_clock_scope_cache_payloads_and_rebuild(history, monkeypatch):
    payloads = saved(history)
    old = history.store()
    history._stores.clear()
    clock(monkeypatch, [100, 102.25, 200, 203.5])
    store = history.store()
    m = store.processing()["measurement"]
    assert m["elapsed_seconds"] == 2.25
    assert m["scope"] == "reconstruction_scoring_recommendation_creation"
    assert m["runtime"] == "local_revision_build" and m["measured_at"].endswith("+00:00")
    assert history.store() is store and store.by_guid == old.by_guid
    client = TestClient(create_candidate_app(lambda: None, get_history=lambda: history))
    for params in ({}, {"rag":"RED"}, {"offset":20,"limit":20}):
        data = client.get("/candidates", params=params).json()
        assert data["processing"]["measurement"] == m
        assert data["snapshot_id"] == m["snapshot_id"] and data["revision_id"] == m["revision_id"]
    assert "processing" not in client.get(f"/revisions/{store.revision_id}/candidates/SYN-MZ-00001").json()
    restarted = CandidateHistory(path=history.path, legacy_log=history.legacy_log)
    assert restarted.store().processing()["measurement"]["elapsed_seconds"] == 3.5
    assert saved(history) == payloads
    assert {rag:len(store.query({"rag":rag})) for rag in ("GREEN","AMBER","RED")} == {"GREEN":32,"AMBER":53,"RED":65}
    assert all("processing" not in json.loads(row[2]) and "build_diagnostics" not in json.loads(row[2]) for row in payloads)


@pytest.mark.parametrize("end,expected", [(10,0), (10.001,pytest.approx(.001)), (9,None), (float("nan"),None), (float("inf"),None)])
def test_invalid_and_short_measurements(history, monkeypatch, end, expected):
    clock(monkeypatch, [10,end])
    store = candidates.CandidateStore(history.tables, history.snapshot_id, "test")
    assert store.build_diagnostics["elapsed_seconds"] == expected
    assert (store.processing()["measurement"] is None) == (expected is None)
    del store.build_diagnostics
    assert store.processing()["measurement"] is None
    for bad in (True, "0", -1, float("nan"), float("inf")):
        store.build_diagnostics = dict(elapsed_seconds=bad, snapshot_id=store.snapshot_id, revision_id=store.revision_id)
        assert store.processing()["measurement"] is None


def test_sources_activation_preview_rollback_and_committed_cache(history, monkeypatch):
    before = history.store()
    initial = before.processing()
    assert initial["candidate_count"] == 150 and initial["check_variety_count"] == 2
    source_tables = {t["table"]:t for f in initial["sources"] for t in f["tables"]}
    assert len(initial["sources"]) == 7 and len(source_tables) == 8
    for key, (stem, count) in FILES.items():
        assert source_tables[key]["supplied_rows"] == count
        assert stem in source_tables[key]["source_file"] and source_tables[key]["source_file"].endswith(".csv")
    draft = approved(history)
    clock(monkeypatch, [10,11,20,22,30,33,40,44])
    history.preview(draft["id"])
    assert before.processing() == initial
    activated = history.activate(draft["id"], before.revision_id, "Ada", "Activate reviewed correction")
    current = history.store()
    assert current.revision_id == activated["revision_id"]
    p = current.processing()
    assert p["measurement"]["elapsed_seconds"] == 3
    assert p["measurement"]["revision_id"] == current.revision_id
    assert p["sources"] == initial["sources"] and p["active_corrections"] == 1 and p["contextual_additions"] == 0
    assert history.store() is current
    rolled = history.rollback(before.revision_id, "Ada", "Restore original evidence")
    restored = history.store()
    assert restored.revision_id == rolled["revision_id"]
    assert restored.processing()["measurement"]["elapsed_seconds"] == 4
    assert restored.processing()["active_corrections"] == 0
    assert before.processing() == initial
    assert {k:v["metrics"] for k,v in restored.by_guid.items()} == {k:v["metrics"] for k,v in before.by_guid.items()}


def test_contextual_additions_are_separate(history):
    before = history.store()
    draft = approved(history, "metadata")
    history.activate(draft["id"], before.revision_id, "Ada", "Activate contextual note")
    p = history.store().processing()
    assert p["contextual_additions"] == 1 and p["active_corrections"] == 0
    assert p["sources"] == before.processing()["sources"]


@pytest.mark.parametrize("operation", ["activation", "rollback"])
@pytest.mark.parametrize("failure", ["build", "transaction"])
def test_failed_work_never_publishes_diagnostics(history, monkeypatch, operation, failure):
    before = history.store()
    initial = before.processing()
    draft = approved(history)
    payloads = saved(history)
    revisions = history.revisions()
    if failure == "build":
        reconstruct = candidates.reconstruct
        calls = 0
        def fail(*args):
            nonlocal calls
            calls += 1
            if operation == "activation" and calls == 1:
                return reconstruct(*args)  # Allow preview; fail the actual revision build.
            raise RuntimeError("Forced build failure")
        monkeypatch.setattr(candidates, "reconstruct", fail)
    else:
        original_db = history._db
        @contextmanager
        def fail_transaction():
            with original_db() as db:
                yield db
                if db.in_transaction and db.execute("SELECT value FROM state WHERE key='active_revision'").fetchone()[0] != before.revision_id:
                    raise RuntimeError("Forced transaction rollback")
        monkeypatch.setattr(history, "_db", fail_transaction)
    with pytest.raises(RuntimeError, match="Forced"):
        if operation == "activation":
            history.activate(draft["id"], before.revision_id, "Ada", "Activate reviewed evidence")
        else:
            history.rollback(before.revision_id, "Ada", "Restore original evidence")
    assert history.active_revision() == before.revision_id
    assert history.store() is before and before.processing() == initial
    assert history.revisions() == revisions and saved(history) == payloads
    assert set(history._stores) == {before.revision_id}



def test_processing_uses_pinned_view_during_activation(history, monkeypatch):
    before = history.store()
    pinned_processing = before.processing()
    draft = approved(history)
    read_view = history.read_view
    def activate_after_pin():
        view = read_view()
        history.activate(draft["id"], before.revision_id, "Ada", "Activate after view pin")
        return view
    monkeypatch.setattr(history, "read_view", activate_after_pin)
    client = TestClient(create_candidate_app(lambda:None, get_history=lambda:history))
    body = client.get("/candidates").json()
    assert history.active_revision() != body["revision_id"]
    assert body["processing"] == pinned_processing
    assert body["revision_id"] == before.revision_id
    assert all(row["revision_id"] == body["revision_id"] for row in body["rows"])


def test_superseding_correction_counts_effective_fields(history):
    before = history.store()
    draft = approved(history)
    history.activate(draft["id"], before.revision_id, "Ada", "Activate first correction")
    current = history.store()
    second = history.draft(query="SYN-MZ-00001", kind="correction", table=draft["table"],
        row_id=draft["row_id"], field=draft["field"], value=draft["value"]+1, unit=draft["unit"],
        supersedes=draft["id"],actor="Ada",reason="Replace prior transcription",observed_at="2026-10-02",source="Notebook")
    for action in ("submit","approve"):
        history.review(second["id"],action,"Ada","Verified replacement evidence")
    history.activate(second["id"],current.revision_id,"Ada","Activate replacement correction")
    assert len(history.store().overlays) == 2
    assert history.store().processing()["active_corrections"] == 1
    assert history.store().processing()["sources"] == before.processing()["sources"]
