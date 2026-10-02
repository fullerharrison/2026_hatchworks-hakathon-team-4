"""Verify the current handoff ZIP in a fresh folder without team state or secrets.

Run with the app browser environment. This checks locked clean-folder startup,
the launcher's browser-opening call, actual Chromium navigation, and persistence.
It does not open the user's default desktop browser. Evidence is retained locally.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import time
from urllib.request import ProxyHandler, build_opener
import zipfile

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
OUT = ROOT / "app/data/verification" / ("package-" + STAMP)
OUT.mkdir(parents=True)
SCRATCH = Path(tempfile.mkdtemp(prefix=".test-tmp-wrapup-package-", dir=ROOT))
PACKAGE = max((ROOT / "dist").glob("uc4-candidate-dashboard-*.zip"), key=lambda p: p.stat().st_mtime)
opener = build_opener(ProxyHandler({}))


def get(url):
    with opener.open(url, timeout=2) as response:
        return response.read()


def links(folder, names):
    checked = 0
    for name in names:
        path = folder / name
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text(encoding="utf-8-sig")):
            if "://" in target or target.startswith("#"):
                continue
            relative = target.split("#", 1)[0]
            assert (path.parent / relative).exists(), (name, target)
            checked += 1
    return checked


LAUNCH = '''
import json, os, threading, time
from pathlib import Path
import uc4_mcp.cli as cli
marker = Path(os.environ["UC4_VERIFY_MARKER"])
stop = Path(os.environ["UC4_VERIFY_STOP"])
cli.webbrowser.open = lambda url: marker.write_text(json.dumps({"url":url, "called":True}), encoding="utf-8")
original = cli.DashboardServer
class CheckedServer(original):
    async def startup(self, sockets=None):
        await super().startup(sockets)
        def monitor():
            while not stop.exists():
                time.sleep(.1)
            self.should_exit = True
        threading.Thread(target=monitor, daemon=True).start()
cli.DashboardServer = CheckedServer
cli.main(["serve", "--port", os.environ["UC4_VERIFY_PORT"], "--open-browser"])
'''


def review_launch(folder):
    """Exercise the packaged practice entry point and its browser readiness call."""
    code = '''
import builtins, json, runpy, sys, webbrowser
from pathlib import Path
from urllib.request import ProxyHandler, build_opener
opener = build_opener(ProxyHandler({}))
def opened(url):
    with opener.open(url + "health", timeout=5) as response:
        health = json.load(response)
    assert health["status"] == "ok" and health["candidates"] == 150
    return True
webbrowser.open = opened
builtins.input = lambda prompt: ""
sys.argv = ["scripts/review_session.py", "--participant", "package-check",
            "--condition", "no-defaults", "--offline", "--open-browser"]
runpy.run_path("scripts/review_session.py", run_name="__main__")
reports = list(Path("app/data/reviews").glob("*/session.json"))
assert len(reports) == 1
report = json.loads(reports[0].read_text())
assert report["status"] == "closed" and report["events"] == []
assert Path(report["history_database"]).is_file()
'''
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("UC4_", "PORTKEY_"))
           and k not in ("PYTHONPATH", "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT")}
    result = subprocess.run(["uv", "run", "--offline", "--locked", "--project", "app",
                             "python", "-c", code], cwd=folder, env=env,
                            capture_output=True, text=True, timeout=90)
    (OUT / "review-startup.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    assert result.returncode == 0, "Practice launcher failed; see review-startup.log"
    assert "scripts/review_session.py" in (folder / "Start-Breeder-Review.cmd").read_text()
    assert "uc4-ask serve --open-browser" in (folder / "Start-Dashboard.cmd").read_text()


def launch(folder, cycle, check):
    marker, stop = OUT / f"browser-{cycle}.json", OUT / f"stop-{cycle}"
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    url = f"http://127.0.0.1:{port}/"
    env = {k:v for k,v in os.environ.items() if not k.startswith(("UC4_", "PORTKEY_"))}
    # Prevent inheriting imports or a project environment from the full checkout.
    for key in ("PYTHONPATH", "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"):
        env.pop(key, None)
    env.update(UC4_VERIFY_MARKER=str(marker), UC4_VERIFY_STOP=str(stop), UC4_VERIFY_PORT=str(port))
    with (OUT / f"startup-{cycle}.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(["uv", "run", "--offline", "--locked", "--project", "app",
                                    "python", "-c", LAUNCH], cwd=folder, env=env,
                                   stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"Startup failed; see startup-{cycle}.log")
                try:
                    health = json.loads(get(url + "health"))
                    if health["status"] == "ok" and marker.exists():
                        break
                except (OSError, ValueError):
                    pass
                time.sleep(.1)
            else:
                raise RuntimeError("Package readiness timeout")
            assert json.loads(marker.read_text())["url"] == url
            assert health["candidates"] == 150 and health["model"] is None
            check(url, health)
            return health
        finally:
            stop.write_text("stop", encoding="utf-8")
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=10)
            assert process.returncode == 0, f"Shutdown failed ({process.returncode})"


report = {"package": str(PACKAGE), "scratch": str(SCRATCH), "automated": True}
try:
    digest = hashlib.sha256(PACKAGE.read_bytes()).hexdigest()
    assert digest == PACKAGE.with_suffix(".zip.sha256").read_text().split()[0]
    with zipfile.ZipFile(PACKAGE) as archive:
        manifest = json.loads(archive.read("uc4-dashboard/MANIFEST.json"))
        expected = {"uc4-dashboard/" + name for name in manifest["sha256"]}
        assert set(archive.namelist()) == expected | {"uc4-dashboard/MANIFEST.json"}
        for name, checksum in manifest["sha256"].items():
            assert hashlib.sha256(archive.read("uc4-dashboard/" + name)).hexdigest() == checksum
            parts = Path(name).parts
            assert ".env" not in parts and ".venv" not in parts
            assert not name.startswith(("app/data/", "app/logs/"))
            assert not name.startswith(".tasks/")
            assert (SCRATCH / "uc4-dashboard" / name).resolve().is_relative_to(SCRATCH.resolve())
        assert [name for name in manifest["sha256"] if name.endswith(".zip")] == [
            "get_started/candidate_recommendations_synthetic.zip"]
        for name in ("app/PROCESS.md", "app/tests/fixtures/historical_v2/rule_intervals.csv",
                     "app/tests/fixtures/historical_v2/chronology_checks.csv",
                     "app/tests/fixtures/historical_v2/provenance.json"):
            assert name in manifest["sha256"]
        archive.extractall(SCRATCH)
    folder = SCRATCH / "uc4-dashboard"
    guides = ["SHARE.md", "app/README.md", "app/ARCHITECTURE.md", "app/API.md", "app/PROCESS.md", "app/HUMAN_REVIEW.md", "app/RELEASE_NOTES.md"]
    report.update(sha256=digest, input_count=len(expected), working_tree_dirty=manifest["working_tree_dirty"],
                  package_doc_links=links(folder, guides), repo_doc_links=links(ROOT, ["README.md", *guides]))
    event = {}
    review_launch(folder)
    report["isolated_review_launcher"] = "passed"
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        def first(url, health):
            assert json.loads(get(url + "decisions")) == []
            assert json.loads(get(url + "enrichment")) == []
            rows = json.loads(get(url + "candidates"))["rows"]
            assert Counter(row["rag"] for row in rows) == {"GREEN":32, "AMBER":53, "RED":65}
            html = get(url).decode()
            assets = re.findall(r'(?:src|href)="(/static/[^\"]+)"', html)
            for asset in assets:
                assert get(url.rstrip("/") + asset)
            report["static_assets"] = len(assets)
            page = browser.new_page(viewport={"width":1440, "height":900})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(url)
            expect(page.locator("#rows tr")).to_have_count(150)
            page.locator("#search").fill("SYN-MZ-00001")
            expect(page.locator("#rows tr")).to_have_count(1)
            page.locator("#rows tr").first.click()
            page.locator("#tab-decision").click()
            page.locator("#actor").fill("package-check")
            page.locator("#action").select_option("HOLD")
            page.locator("#reason").fill("Isolated package persistence check")
            page.locator("#review-decision").click()
            page.locator("#record-decision").click()
            expect(page.locator("#decision-saved")).to_be_visible()
            decisions = json.loads(get(url + "decisions"))
            assert len(decisions) == 1
            event.update(decisions[0])
            page.screenshot(path=str(OUT / "package-saved.png"))
            page.reload()
            page.locator("#rows tr").first.click()
            page.locator("#tab-decision").click()
            expect(page.locator("#decision-saved")).to_be_visible()
            assert len(json.loads(get(url + "decisions"))) == 1
            assert not errors, errors
            page.close()
        report["first_health"] = launch(folder, 1, first)
        def second(url, health):
            decisions = json.loads(get(url + "decisions"))
            assert len(decisions) == 1 and decisions[0]["id"] == event["id"]
            original = json.loads(get(url + "revisions/" + event["recommendation"]["revision_id"]
                                      + "/candidates/" + event["material_id"]))
            assert original["recommendation_id"] == event["recommendation"]["recommendation_id"]
            report["persisted_event"] = event["id"]
        report["restart_health"] = launch(folder, 2, second)
        browser.close()
    report["result"] = "passed"
except BaseException as error:
    report.update(result="failed", error=f"{type(error).__name__}: {error}")
    raise
finally:
    (OUT / "run.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"result":report["result"], "report":str(OUT / "run.json")}), flush=True)
