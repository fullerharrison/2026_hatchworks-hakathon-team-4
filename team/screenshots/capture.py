# /// script
# requires-python = ">=3.12"
# dependencies = ["playwright>=1.50,<2", "pillow>=11,<13"]
# ///
r"""Retake the six Phase 3 deck PNGs and a step-by-step walkthrough GIF.

Prerequisites: installed Google Chrome and a running breeder-screen server.
From the repo root, start the server with:
    $env:UC4_DECISION_LOG = "$env:TEMP\uc4-capture.jsonl"
    uv run --project app --env-file .env uc4-ask serve
Then run:
    uv run team/screenshots/capture.py [--base URL] [--out DIR] [--no-gif]

Set UC4_DECISION_LOG on the SERVER before starting it: each capture records a
PASS override (two with the GIF), which must not go into the real decision log.
The git-ignored .env enables the live Ask shot; without a model the script
captures the unavailable warning and reports that the Ask evidence is offline.

Outputs default to this directory: phase3_1_trial_0003_pass.png,
phase3_2_trial_0037_hold.png, phase3_2b_0037_flags.png, phase3_3_ask_live.png,
phase3_4_override.png, phase3_5_line_panel.png and phase3_walkthrough.gif.
The PNGs use 1440x900 at 2x; the GIF uses 1280x800 at 1x, two seconds per scene.
"""

from __future__ import annotations

import argparse
from io import BytesIO
from pathlib import Path

from PIL import Image
from playwright.sync_api import Page, sync_playwright

QUESTION = "Why is SYN-TR-0037 amber?"
REASON = (
    "Resistance screen from the 2026 nursery is pending; "
    "advance to PASS for the next cycle."
)
GIF_LIMIT = 8_000_000


def _open_trial(page: Page, base: str, trial: str, verdict: str) -> None:
    page.goto(f"{base}#{trial}")
    page.wait_for_function(
        "([trial, verdict]) => { const text = "
        "document.querySelector('#banner').textContent; "
        "return text.includes(trial) && text.includes(verdict); }",
        arg=[trial, verdict],
    )
    page.wait_for_selector("#lines tbody tr")
    page.locator("#trial-search").blur()


def _scroll_to(page: Page, selector: str) -> None:
    page.locator(selector).evaluate(
        "node => node.scrollIntoView({block: 'start', behavior: 'instant'})"
    )


def _shot(page: Page, out: Path, name: str, selector: str | None = None) -> None:
    path = out / name
    if selector:
        page.locator(selector).screenshot(path=path, animations="disabled")
    else:
        page.screenshot(path=path, full_page=False, animations="disabled")
    print(f"Saved {path}")


def _submit_ask(page: Page) -> None:
    page.locator("#ask-question").fill(QUESTION)
    page.locator("#ask-question").press("Enter")


def _wait_answer(page: Page) -> None:
    page.wait_for_selector(
        "#answer .answer-text, #answer .warn, #answer .error",
        timeout=180_000,
    )
    if page.locator("#answer .error").count():
        raise RuntimeError(page.locator("#answer").inner_text())
    if not page.locator("#answer .answer-text").count():
        print("Ask unavailable: captured offline warning, not a live answer.")


def _record_override(page: Page) -> None:
    before = page.locator("#history .hist-item").count()
    page.locator("#user-alias").fill("breeder-a")
    page.locator("input[name=decision][value=PASS]").check()
    page.locator("#decision-reason").fill(REASON)
    page.locator("#decision-form button[type=submit]").click()
    page.wait_for_function(
        "before => document.querySelectorAll('#history .hist-item').length "
        "> before || document.querySelector('#decision-error').textContent",
        arg=before,
    )
    error = page.locator("#decision-error").inner_text()
    if error:
        raise RuntimeError(f"Decision rejected: {error}")


def _open_line(page: Page) -> None:
    page.locator("#lines tbody tr").first.locator("td").first.click()
    page.wait_for_selector("#line-panel h3")


def _capture_pngs(page: Page, base: str, out: Path) -> None:
    _open_trial(page, base, "SYN-TR-0003", "PASS")
    _shot(page, out, "phase3_1_trial_0003_pass.png")
    page.locator("#trial-search").fill("SYN-TR-0037")
    page.locator("#trial-search").press("Tab")
    page.wait_for_function(
        "document.querySelector('#banner').textContent.includes('HOLD')"
    )
    page.wait_for_selector("#flags strong")
    page.locator("#trial-search").blur()
    page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
    _shot(page, out, "phase3_2_trial_0037_hold.png")
    _shot(page, out, "phase3_2b_0037_flags.png", "section[aria-labelledby=h-flags]")

    _submit_ask(page)
    _wait_answer(page)
    _shot(page, out, "phase3_3_ask_live.png", "section[aria-labelledby=h-ask]")
    _record_override(page)
    _shot(page, out, "phase3_4_override.png", "section[aria-labelledby=h-decide]")
    _open_line(page)
    _shot(page, out, "phase3_5_line_panel.png", "section[aria-labelledby=h-lines]")


def _frame(page: Page, selector: str) -> Image.Image:
    _scroll_to(page, selector)
    data = page.screenshot(full_page=False, animations="disabled")
    with Image.open(BytesIO(data)) as image:
        return image.convert("RGB")


def _capture_frames(page: Page, base: str) -> list[Image.Image]:
    _open_trial(page, base, "SYN-TR-0037", "HOLD")
    frames = [_frame(page, "header")]
    frames.append(_frame(page, "section[aria-labelledby=h-criteria]"))
    frames.append(_frame(page, "section[aria-labelledby=h-flags]"))
    page.locator("#ask-question").fill(QUESTION)
    frames.append(_frame(page, "section[aria-labelledby=h-ask]"))
    page.locator("#ask-question").press("Enter")
    _wait_answer(page)
    frames.append(_frame(page, "section[aria-labelledby=h-ask]"))
    page.locator("#user-alias").fill("breeder-a")
    page.locator("input[name=decision][value=PASS]").check()
    page.locator("#decision-reason").fill(REASON)
    frames.append(_frame(page, "section[aria-labelledby=h-decide]"))
    _record_override(page)
    frames.append(_frame(page, "#history"))
    _open_line(page)
    frames.append(_frame(page, "#line-panel"))
    return frames


def _write_gif(frames: list[Image.Image], out: Path) -> None:
    path = out / "phase3_walkthrough.gif"
    for width in (1280, 1024):
        palette_frames = [
            frame.resize(
                (width, round(frame.height * width / frame.width)),
                Image.Resampling.LANCZOS,
            ).quantize(colors=256)
            for frame in frames
        ]
        palette_frames[0].save(
            path,
            save_all=True,
            append_images=palette_frames[1:],
            duration=2000,
            loop=0,
            optimize=True,
            disposal=2,
        )
        if path.stat().st_size < GIF_LIMIT:
            with Image.open(path) as gif:
                print(
                    f"Saved {path}: {gif.n_frames} frames, "
                    f"{width}px wide, {path.stat().st_size:,} bytes"
                )
            return
    raise RuntimeError(f"GIF exceeds {GIF_LIMIT:,} bytes even at 1024px: {path}")


def main() -> None:
    """Parse capture options and write artifacts; propagate browser/file errors."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8766/")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--no-gif", action="store_true")
    args = parser.parse_args()
    base = args.base.rstrip("/") + "/"
    args.out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        try:
            with browser.new_context(
                viewport={"width": 1440, "height": 900}, device_scale_factor=2,
            ) as context:
                _capture_pngs(context.new_page(), base, args.out)
            if not args.no_gif:
                with browser.new_context(
                    viewport={"width": 1280, "height": 800}, device_scale_factor=1,
                ) as context:
                    _write_gif(_capture_frames(context.new_page(), base), args.out)
        finally:
            browser.close()


if __name__ == "__main__":
    main()