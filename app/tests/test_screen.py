"""Task 3: the static breeder screen is served, wired by id, and never injects HTML."""

from __future__ import annotations

import re
from pathlib import Path

from fakes import FakeChat
from fastapi.testclient import TestClient

from uc4_mcp.api import STATIC_DIR, create_app
from uc4_mcp.decisions import DecisionLog
from uc4_mcp.server import create_server
from uc4_mcp.store import EvidenceStore

IDS = ["trial-search", "trial-list", "user-alias", "candidates", "banner", "criteria",
       "rationale", "aggregates", "flags", "lines", "line-panel", "operations",
       "decision-form", "decision-error", "history", "ask-form", "ask-question", "answer"]


def client(store: EvidenceStore, tmp_path: Path) -> TestClient:
    return TestClient(create_app(lambda: FakeChat([]), create_server(lambda: store),
                                 get_store=lambda: store,
                                 log=DecisionLog(tmp_path / "d.jsonl")))


def test_root_serves_the_screen_and_assets(store: EvidenceStore, tmp_path: Path) -> None:
    c = client(store, tmp_path)
    r = c.get("/")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert c.get("/static/app.js").status_code == 200
    assert c.get("/static/style.css").status_code == 200


def test_every_id_is_in_the_page_and_used_by_the_script() -> None:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    for id_ in IDS:
        assert f'id="{id_}"' in html, id_
    used = set(re.findall(r'byId\("([\w-]+)"\)', js))
    assert used <= set(IDS) and set(IDS) - {"trial-list"} <= used


def test_app_js_never_uses_inner_html() -> None:
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write", js)


def test_page_is_self_contained_and_states_the_rules() -> None:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    assert "http://" not in html and "https://" not in html  # no CDN
    assert "SYNTH_V1 (inferred)" in html and "breeder decides" in html
