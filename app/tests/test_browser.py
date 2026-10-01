"""The breeder screen driven with real mouse and keyboard input in the installed Chrome.

Playwright sends input through the browser (CDP ``Input.dispatch*``), so events arrive with
``isTrusted`` true and follow the browser's own focus, click and form rules: unlike the
earlier walkthrough, which called ``element.click()`` and ``form.requestSubmit()``.
The server runs without Portkey variables, so Ask exercises only the no-model path.

Run: ``uv run --project app --group browser pytest -q -m browser app/tests/test_browser.py``
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

playwright_api = pytest.importorskip("playwright.sync_api")
Browser = playwright_api.Browser
Page = playwright_api.Page

pytestmark = pytest.mark.browser

REPO = Path(__file__).resolve().parents[2]
SECRETS = ("PORTKEY_API_KEY", "PORTKEY_VIRTUAL_KEY", "PORTKEY_CONFIG", "PORTKEY_PROVIDER",
           "UC4_LLM_MODEL", "UC4_LLM_BASE_URL", "UC4_LLM_PROVIDER_KEY")
# Records whether every click and key event came from real input, not from script.
TRUST_PROBE = """
window.__untrusted = 0;
for (const type of ["click", "keydown", "mousedown"]) {
  document.addEventListener(type, (e) => { if (!e.isTrusted) window.__untrusted++; }, true);
}
"""
ROW = "#lines tbody tr"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_for_port(port: int, proc: subprocess.Popen[bytes], timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            pytest.fail(f"server exited with {proc.returncode} before listening")
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.2)
    pytest.fail(f"server not listening on {port} after {timeout} s")


@pytest.fixture(scope="module")
def decision_log(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("browser") / "decisions.jsonl"


@pytest.fixture(scope="module")
def base_url(decision_log: Path) -> Iterator[str]:
    """``uc4-ask serve`` on a free port, with no model configured."""
    exe = shutil.which("uc4-ask") or str(Path(sys.executable).with_name("uc4-ask.exe"))
    if exe is None:
        pytest.fail("uc4-ask not on PATH; run with `uv run --project app`", pytrace=False)
    env = {k: v for k, v in os.environ.items() if k not in SECRETS}
    env.update({k: "" for k in SECRETS})
    env["UC4_DECISION_LOG"] = str(decision_log)
    env["UC4_ZIP"] = str(REPO / "get_started" / "RE__Hatchworks_Hackathon_-_4th_Use_Case.zip")
    port = _free_port()
    proc = subprocess.Popen([exe, "serve", "--historical-v2", "--port", str(port)], cwd=REPO, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        _wait_for_port(port, proc)
        yield f"http://127.0.0.1:{port}/"
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with playwright_api.sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome")
        except playwright_api.Error as e:
            pytest.skip(f"Chrome could not be launched: {e}")
        yield b
        b.close()


@pytest.fixture
def page(browser: Browser, base_url: str) -> Iterator[Page]:
    """A fresh page on SYN-TR-0037 (HOLD); fails the test if any input was synthetic."""
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = context.new_page()
    pg.add_init_script(TRUST_PROBE)
    pg.goto(base_url + "#SYN-TR-0037")
    pg.wait_for_selector(ROW)
    yield pg
    assert pg.evaluate("window.__untrusted") == 0
    context.close()


def tab_until(page: Page, is_target: str, limit: int = 300) -> None:
    """Press Tab until the JS predicate over ``document.activeElement`` (``a``) holds."""
    for _ in range(limit):
        page.keyboard.press("Tab")
        if page.evaluate(f"(() => {{ const a = document.activeElement; return {is_target}; }})()"):
            return
    pytest.fail(f"focus never reached: {is_target}")


def panel_title(page: Page) -> str:
    title = page.locator("#line-panel h3")
    return title.inner_text() if title.count() else ""


def wait_panel(page: Page, line: str) -> None:
    page.wait_for_function("t => (document.querySelector('#line-panel h3') || {}).textContent === t",
                           arg=f"Line {line}")


def test_mouse_click_on_line_row_opens_the_line(page: Page) -> None:
    page.locator(ROW).nth(2).locator("td").first.click()
    wait_panel(page, "SYN-MZ-00025")


def test_late_line_response_is_discarded_after_trial_switch(page: Page) -> None:
    held = []
    page.route("**/lines/*", lambda route: held.append(route))
    page.locator(ROW).first.locator("td").first.click()
    page.wait_for_timeout(200)
    assert held
    response = held[0].fetch()
    page.locator("#trial-search").fill("SYN-TR-0003")
    page.locator("#trial-search").press("Tab")
    page.wait_for_function("document.querySelector('#banner').textContent.includes('SYN-TR-0003')")
    held[0].fulfill(response=response)
    page.wait_for_timeout(200)
    assert page.locator("#line-panel").inner_text() == ""


def test_genomic_value_sources_cite_genomic_rows(page: Page) -> None:
    row = page.locator(ROW).first
    for cell in (row.locator("td").nth(1), row.locator("td").nth(2)):
        cell.locator("button.src").click()
        assert "genomics_synthetic" in cell.locator(".src-detail").inner_text()


def test_enter_and_space_on_focused_line_rows_open_them(page: Page) -> None:
    first_row = "a.matches('#lines tbody tr:nth-child(1)')"
    tab_until(page, first_row)
    page.keyboard.press("Enter")
    wait_panel(page, "SYN-MZ-00013")

    tab_until(page, "a.matches('#lines tbody tr:nth-child(2)')")
    # Bubble-phase listener runs after the row's handler: Space must not also page-scroll.
    page.evaluate("""document.addEventListener("keydown", (e) => {
      if (e.key === " ") window.__spacePrevented = e.defaultPrevented; })""")
    page.keyboard.press(" ")
    wait_panel(page, "SYN-MZ-00019")
    assert page.evaluate("window.__spacePrevented") is True


def test_source_toggle_does_not_open_the_row(page: Page) -> None:
    tab_until(page, "a.matches('#lines tbody tr:nth-child(1) button.src')")
    button = page.locator(ROW).nth(0).locator("button.src").first
    page.keyboard.press("Enter")
    assert button.get_attribute("aria-expanded") == "true"
    assert page.locator(ROW).nth(0).locator(".src-detail").first.is_visible()
    page.keyboard.press(" ")
    assert button.get_attribute("aria-expanded") == "false"

    page.locator(ROW).nth(1).locator("button.src").first.click()
    assert page.locator(ROW).nth(1).locator("button.src").first.get_attribute("aria-expanded") == "true"
    page.wait_for_timeout(300)  # give a wrongly bubbled open() time to render
    assert panel_title(page) == ""


def test_typed_trial_search_opens_the_trial(page: Page) -> None:
    page.locator("#trial-search").click()
    page.keyboard.press("Control+A")
    page.keyboard.type("SYN-TR-0001")
    page.keyboard.press("Enter")
    page.wait_for_function("document.querySelector('#banner').textContent.includes('FAIL')")
    assert "SYN-TR-0001" in page.locator("#banner").inner_text()


def test_decision_recorded_with_keyboard_only(page: Page, decision_log: Path) -> None:
    before = len(decision_log.read_text(encoding="utf-8").splitlines()) if decision_log.exists() else 0
    tab_until(page, "a.id === 'user-alias'")
    page.keyboard.type("breeder-k")
    tab_until(page, "a.name === 'decision'")
    page.keyboard.press(" ")  # checks the focused radio (PASS)
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowRight")
    assert page.locator("input[name=decision]:checked").get_attribute("value") == "FAIL"
    tab_until(page, "a.id === 'decision-reason'")
    page.keyboard.type("Keyboard-only check: knockout risk on resistance.")
    tab_until(page, "a.matches('#decision-form button[type=submit]')")
    page.keyboard.press("Enter")

    page.wait_for_selector("#history .hist-item")
    entry = page.locator("#history .hist-item").first.inner_text()
    assert "FAIL" in entry and "override" in entry and "breeder-k" in entry
    assert len(decision_log.read_text(encoding="utf-8").splitlines()) == before + 1


def test_ask_submitted_with_enter_reports_no_model(page: Page) -> None:
    page.locator("#ask-question").click()
    page.keyboard.type("Why is SYN-TR-0037 amber?")
    page.keyboard.press("Enter")
    page.wait_for_selector("#answer .warn")
    assert page.locator("#answer").inner_text().startswith("Ask unavailable:")
