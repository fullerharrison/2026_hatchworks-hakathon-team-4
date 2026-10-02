"""Check real typed-filter interpretation, validation and Apply in an isolated UI."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app/src"))
from uc4_mcp.cli import make_model
from uc4_mcp.config import load_env_file
from uc4_mcp.demo_runtime import candidate_demo_server

stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
out = ROOT / "app/data/verification" / ("live-filters-" + stamp)
out.mkdir(parents=True)
scratch = out / "storage"
report = {"automated":True, "live_model_requested":True, "storage":str(scratch)}
load_env_file()
try:
    with candidate_demo_server(scratch, make_model,
            ROOT / "get_started/candidate_recommendations_synthetic.zip") as runtime:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width":1440, "height":900})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(runtime.url)
            expect(page.locator("#rows tr")).to_have_count(150)
            page.locator("#advanced-filters > summary").click()
            page.locator("#filter-request").fill("Show AMBER candidates with at least three usable trials")
            with page.expect_response(lambda response: response.url.endswith("/filters/interpret"), timeout=90000) as response:
                page.locator("#filter-interpret").click()
            assert response.value.status == 200
            proposal = response.value.json()
            assert proposal["status"] == "ready" and proposal["filters"]["rag"] == "AMBER"
            assert proposal["filters"]["ranges"]["N_TRIALS_USED"]["min"] == 3
            expect(page.locator("#filter-preview")).to_be_visible()
            expect(page.locator("#rows tr")).to_have_count(150)
            with page.expect_response(lambda response: response.url.endswith("/filters/validate")) as validation:
                page.locator("#filter-apply").click()
            assert validation.value.status == 200
            validated = validation.value.json()
            expect(page.locator("#filter-preview")).to_be_hidden()
            expect(page.locator("#rag")).to_have_value("AMBER")
            expect(page.locator("#rows tr")).to_have_count(validated["total"])
            assert validated["total"] > 0
            assert page.request.get(runtime.url + "decisions").json() == []
            assert page.request.get(runtime.url + "enrichment").json() == []
            assert not errors, errors
            page.screenshot(path=str(out / "applied.png"))
            report.update(result="passed", proposal=proposal, matching_total=validated["total"], browser_errors=errors)
            browser.close()
except BaseException as error:
    report.update(result="failed", error=f"{type(error).__name__}: {error}")
    raise
finally:
    (out / "run.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"result":report["result"], "report":str(out / "run.json")}), flush=True)
