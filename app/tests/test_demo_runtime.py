"""Exercise real HTTP readiness, cleanup and isolation across repeated runs."""
import json
import socket
from urllib.request import ProxyHandler, Request, build_opener
from urllib.parse import urlparse

from uc4_mcp.candidate_core import ZIP_PATH
from uc4_mcp.demo_runtime import candidate_demo_server


def test_repeated_demo_servers_are_ready_isolated_and_stopped(tmp_path, monkeypatch):
    active = tmp_path / "active.sqlite3"
    active.write_bytes(b"Do not open this active-store sentinel")
    monkeypatch.setenv("UC4_CANDIDATE_DB", str(active))
    client = build_opener(ProxyHandler({}))

    def read(url):
        with client.open(url, timeout=10) as response:
            return json.load(response)

    for index in range(3):
        storage = tmp_path / f"run-{index}"
        with candidate_demo_server(storage, archive=ZIP_PATH) as runtime:
            health = read(runtime.url + "health")
            assert health["status"] == "ok" and health["candidates"] == 150
            assert health["model"] is None
            assert read(runtime.url + "decisions") == []
            rec = read(runtime.url + "candidates/SYN-MZ-00001")
            payload = dict(query=rec["material_guid"], action="HOLD", actor="Test reviewer",
                           reason="Wait for further trials", context=dict(location="Unknown", source_channel="Breeder review"),
                           recommendation_id=rec["recommendation_id"], previous_decision_id=None,
                           request_id="one-confirmation")
            with client.open(Request(runtime.url + "decisions", data=json.dumps(payload).encode(),
                                     headers={"Content-Type":"application/json"}), timeout=10) as response:
                event = json.load(response)
            assert read(runtime.url + "decisions")[0]["id"] == event["id"]
            assert runtime.history.path == storage / "history.sqlite3"
        with socket.socket() as probe:
            probe.settimeout(1)
            assert probe.connect_ex(("127.0.0.1", urlparse(runtime.url).port)) != 0
    assert active.read_bytes() == b"Do not open this active-store sentinel"
