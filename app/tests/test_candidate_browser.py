"""Candidate workflows with real browser input and an isolated history database."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")
pytestmark = pytest.mark.browser
REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def screen(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = dict(os.environ, UC4_CANDIDATE_DB=str(tmp_path / "history.sqlite3"),
               UC4_DECISION_LOG=str(tmp_path / "legacy.jsonl"),
               UC4_ZIP=str(REPO / "get_started" / "candidate_recommendations_synthetic.zip"))
    code = ("from uc4_mcp.candidate_api import create_candidate_app\n"
            "from uc4_mcp.llm import LLMError\nimport uvicorn\n"
            "def no_model():\n    raise LLMError('Model is not configured for this test')\n"
            f"uvicorn.run(create_candidate_app(no_model),host='127.0.0.1',port={port},log_level='warning')\n")
    with (tmp_path / "server.log").open("w", encoding="utf-8") as log:
        proc = subprocess.Popen([sys.executable, "-c", code], cwd=REPO, env=env, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    pytest.fail((tmp_path / "server.log").read_text(encoding="utf-8"))
                with socket.socket() as sock:
                    if sock.connect_ex(("127.0.0.1", port)) == 0:
                        break
                time.sleep(.1)
            else:
                pytest.fail("Candidate server did not start")
            with playwright.sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome")
                page = browser.new_page(viewport={"width": 1440, "height": 1100})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{port}/")
                yield page, tmp_path
                assert not errors, errors
                browser.close()
        finally:
            proc.terminate()
            proc.wait(timeout=10)


def test_candidate_filter_decision_review_and_history(screen):
    page, folder = screen
    expect = playwright.expect
    expect(page.locator("#rows tr")).to_have_count(150)
    page.locator("#rag").select_option("GREEN")
    expect(page.locator("#rows tr")).to_have_count(32)
    page.locator("#metric").select_option("N_TRIALS_USED")
    page.locator("#min").fill("2")
    page.locator("#add-range").click()
    expect(page.locator("#ranges")).to_contain_text("Usable trials")
    expect(page.locator("#rows tr")).to_have_count(32)
    with page.expect_download() as download:
        page.locator("#export").click()
    downloaded = download.value
    downloaded.save_as(folder / "filtered.csv")
    assert len((folder / "filtered.csv").read_text().splitlines()) == 33
    page.locator("#reset").click()
    expect(page.locator("#rows tr")).to_have_count(150)
    page.locator("#search").fill("SYN-MZ-00001")
    expect(page.locator("#rows tr")).to_have_count(1)
    page.locator("#rows tr").click()
    expect(page.locator("#detail")).to_be_visible()
    expect(page.locator("#recommendation")).to_contain_text("AMBER")
    page.locator("#actor").fill("Breeder Ada")
    page.locator("#action").select_option("ADVANCE")
    page.locator("#location").fill("Research review meeting")
    page.locator("#source-channel").fill("Breeder screen")
    page.locator("#reason").fill("Advance after reviewing the field evidence")
    page.locator("#decision-form button").click()
    expect(page.locator("#decision-history")).to_contain_text("ADVANCE by Breeder Ada")
    expect(page.locator("#decision-history")).to_contain_text("override yes")
    page.locator("#enrich-value").fill("Repeat cold test before the next review")
    page.locator("#observed-at").fill("2026-10-01T09:30")
    page.locator("#enrich-source").fill("Breeder notebook")
    page.locator("#enrich-reason").fill("Capture follow-up for the next decision")
    page.locator("#enrichment-form button").click()
    expect(page.locator("#enrichment-history")).to_contain_text("DRAFT")
    page.get_by_role("button", name="Submit for review", exact=True).click()
    expect(page.locator("#enrichment-history")).to_contain_text("SUBMITTED")
    page.get_by_role("button", name="Approve", exact=True).click()
    expect(page.locator("#enrichment-history")).to_contain_text("APPROVED")
    page.get_by_role("button", name="Preview impact and activate", exact=True).click()
    expect(page.locator("#enrichment-message")).to_contain_text("0 candidates")
    page.get_by_role("button", name="Activate reviewed change", exact=True).click()
    expect(page.locator("#enrichment-history")).to_contain_text("ACTIVATED")
    expect(page.locator("#decision-history")).to_contain_text("baseline:")
    page.locator("#historical-panel summary").click()
    expect(page.locator("#historical-records")).to_contain_text("Original source archive")
    page.locator("#question").fill("Why is this candidate amber?")
    page.locator("#ask-form button").click()
    expect(page.locator("#answer")).to_contain_text("Model is not configured")
    page.screenshot(path=str(folder / "candidate-workflow.png"), full_page=True)
