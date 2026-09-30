# Phase 3 walkthrough: breeder screen and override log

**Date:** 2026-09-30 · **Run by:** controller, Claude in Chrome · **Branch:** `phase-3-breeder-screen` at `9aec632` (commits after it, up to the final-review fixes, were docs and EDA only; the fixes below change `app.js` and `api.py`) · **Plan:** [phase-3-breeder-screen.md](../.tasks/uc4-assistant/phase-3-breeder-screen.md) (Task 5, "Validate the demo")

## Setup

- Server: `uc4-ask serve` on http://127.0.0.1:8766/.
- `UC4_ZIP` pinned to `get_started/RE__Hatchworks_Hackathon_-_4th_Use_Case.zip` (the original v2 archive). A second archive, `..._09-30-2026.zip`, now sits in `get_started/` and makes `find_zip` ambiguous without the variable. Since ba94b9f the loader picks the v2 archive by exact name, so `UC4_ZIP` is optional.
- `UC4_DECISION_LOG` = `%TEMP%\uc4-walkthrough.jsonl`, so rehearsal decisions stay out of the real log.
- Method: DOM text read back through the page (`get_page_text` and JavaScript). The Chrome window was minimized, so screenshots and GIF frames could not be captured ("Cannot take screenshot with 0 width") and real mouse and keyboard events were not delivered. Controls were driven with `form_input`, `element.click()` and `form.requestSubmit()`. Real pointer and keyboard behaviour (clicking rows, Enter/Space on line rows, tabbing) was not exercised: only DOM-simulated.

## Scenarios

| # | Scenario | Observed | Result |
| --- | --- | --- | --- |
| 1 | SYN-TR-0003 | "● PASS"; "PASS: all five criteria met (inferred thresholds)"; yield 10.79 t/ha, moisture 16.8 %, disease 3.3, GBV 106.8, resistant 70 % all "met"; both knockouts "not triggered"; banner "Rule set: SYNTH_V1 (inferred)" and "The breeder decides" | pass |
| 2 | SYN-TR-0037 | "▲ HOLD"; "HOLD: resistant lines 30% < 50% (inferred threshold)"; only "Resistant lines for PASS 30 %" not met; "The supplied text does not mention: Resistant lines for PASS"; flag `RATIONALE_READS_AS_PASS`; aggregates GBV 105.2 vs 104.89, resistant 30 vs 60 | pass |
| 3 | SYN-TR-0001 | "■ FAIL"; disease knockout 7.7 > 7 "knockout triggered"; yield knockout "not triggered" | pass |
| 4 | SYN-TR-0009 | "■ FAIL"; yield knockout 6.04 < 7 "knockout triggered"; disease knockout (7) "not triggered" | pass |
| 5 | SYN-TR-0002 | Operations: 2026-05-01 PLANTING, 2026-08-26 HARVEST, 2026-09-21 PLANTING, each `OPS_OUTSIDE_TRIAL_YEAR` (harvest dated before the second planting) | pass |
| 6 | Search "SYN-TR-003" | "10 trials match 'SYN-TR-003'; which one?" with 10 buttons SYN-TR-0030..0039 (year, verdict); nothing opened. Note: the previous trial's banner and decision form stay visible below | pass (see note) |
| 7 | 0037, PASS, empty reason; then six spaces | Empty: browser validation blocks (form invalid, no request). Spaces: server 422 shown inline "String should have at least 5 characters"; history still "No decisions recorded yet."; log file absent (`Test-Path` False) | pass |
| 8 | 0037, PASS, real reason, user `breeder-a` | History "● PASS override by breeder-a at 2026-09-30T19:02:37+00:00 … Made against recommendation: HOLD"; banner still "▲ HOLD" | pass |
| 9 | Reason `<b>bold</b> <img src=x onerror=console.log('XSS')> looks fine` (FAIL) | Shown literally; 0 `<b>`/`<img>` elements in `#history`; no XSS console message; newest entry first | pass |
| 10 | Click first line of 0037 (SYN-MZ-00013) | Panel: "Verdicts are per trial …" note; genomics; "Lab trait …01 / …03 / …01" with "lab rows have no trial key: not linked to this trial"; 5 trial verdicts (0013, 0019, 0025, 0031, 0037); operations | pass (cosmetic: "▲ HOLD: HOLD: …" repeats the verdict word) |
| 11 | Ask "Why is SYN-TR-0037 amber?" without Portkey configuration | "Ask unavailable: No model: set [llm] model in agent.toml or UC4_LLM_MODEL"; banner and decision form still work | pass for the no-model path; live answer also passes (see [Live Ask](#live-ask-and-deck-screenshots-2026-09-30)) |

## Log-file evidence

Decision log after the walkthrough: 2 lines, one per accepted decision.

```text
SYN-TR-0037 PASS overrides=True breeder-a 2026-09-30T19:02:37+00:00 | recommendation verdict HOLD, 7 criteria, 4 flags
SYN-TR-0037 FAIL overrides=True breeder-a 2026-09-30T19:03:16+00:00 | recommendation verdict HOLD, 7 criteria, 4 flags
```

The rejected blank-reason attempts (scenario 7) left no line.

## Fixes after final review

1. **Stale trial after ambiguous or unknown search:** a failed search now clears the trial (banner, criteria, flags, lines, operations, history) and disables the decision form; submit is blocked with "Open a trial first."
2. **Decision draft carried across trials:** opening a different trial resets the reason, the PASS/HOLD/FAIL choice and the line select.
3. **In-flight submit race:** the submit captures its trial before the request; history is updated only if that trial is still open.

Also: blank-reason client check, buttons re-enabled in `finally`, line-row keyboard and source-toggle bubbling, duplicated verdict word in the line panel, `GET /decisions?trial=` returns 409 for an ambiguous query.

Re-check (2026-09-30, Claude in Chrome, commit 1f6078a, server started without `UC4_ZIP`; the evidence layer is pinned to the v2 archive by exact name since ba94b9f):

- Scenario 6 again: typed a PASS draft on SYN-TR-0037, then searched "SYN-TR-003" and got 10 candidate buttons. Banner, criteria and history cleared, "Record decision" was disabled, and a forced form submit wrote nothing (decision log file absent afterwards).
- Picking SYN-TR-0033 from the candidates opened "● PASS" with the draft reset (reason empty, no decision selected).
- The line panel no longer repeats the verdict word (e.g. "SYN-TR-0009 ■ FAIL: yield 6.04 t/ha < 7 t/ha (knockout, inferred threshold)").
- A whitespace-only reason shows "A reason of 5 to 1000 characters is required." inline, with no request.
- Full suite without `UC4_ZIP`: 393 passed, 1 deselected.
- Keyboard behaviour on line rows and the source toggle was not exercised in that DOM-driven re-check; the trusted-input run below closes that gap.

## Live Ask and deck screenshots (2026-09-30)

Portkey credentials come from the git-ignored repo-root `.env`, loaded with
`uv run --project app --env-file .env …`. Model: `@bedrock-aifoundry-use1-001/global.openai.gpt-6-sol`.

- `uc4-ask ping`: `tool_call=yes tokens=50/17`.
- `uc4-ask ask "Why is SYN-TR-0037 amber?"`: exit 0, `answered`. The answer gives HOLD because resistant material is 30 % < 50 % (inferred threshold), notes that the supplied rationale omits resistant material, cites `trial_recommendations_synthetic.csv#620A7637-3BE2-7307-0000-000000000025`, and ends with the disclaimer. 13 432 prompt / 777 completion tokens, 3–4 s. The model called `score_trial` twice with the same query (harmless, but it costs a round).
- `GET /health`: `status: ok` with the model. Scenario 11 on the screen returned the same cited answer: **pass**.

Screenshots were captured by a Playwright script driving the installed Chrome (headless, 1440×900 at 2×), which avoids the minimized-window problem. Decisions went to `%TEMP%\uc4-demo.jsonl`, not the real log.

| File | Scene |
| --- | --- |
| [phase3_1_trial_0003_pass.png](screenshots/phase3_1_trial_0003_pass.png) | SYN-TR-0003 ● PASS, criteria, aggregates |
| [phase3_2_trial_0037_hold.png](screenshots/phase3_2_trial_0037_hold.png) | SYN-TR-0037 ▲ HOLD, resistant lines "not met", rationale omission |
| [phase3_2b_0037_flags.png](screenshots/phase3_2b_0037_flags.png) | SYN-TR-0037 flags, `RATIONALE_READS_AS_PASS` first |
| [phase3_3_ask_live.png](screenshots/phase3_3_ask_live.png) | live Ask answer with citation and disclaimer |
| [phase3_4_override.png](screenshots/phase3_4_override.png) | PASS override by `breeder-a` against HOLD |
| [phase3_5_line_panel.png](screenshots/phase3_5_line_panel.png) | line SYN-MZ-00013: genomics, lab, per-trial verdicts, flags |

## Real input checks (2026-09-30)

[test_browser.py](../app/tests/test_browser.py) starts its own server with model credentials
removed and a temporary decision log. Playwright drives installed Chrome through real
mouse/keyboard input; a page-level probe rejects untrusted click, mousedown and keydown
events. No DOM-dispatched input is used.

```powershell
uv run --project app --group browser pytest -q -m browser app/tests/test_browser.py
```

Result: **6 passed**, no skips. All six checks assert rendered DOM state:

| Input | Observed | Result |
| --- | --- | --- |
| Mouse click on third line row | Panel names SYN-MZ-00025 | pass |
| Tab to rows, Enter on first and Space on second | Panels name SYN-MZ-00013 and SYN-MZ-00019; Space default is prevented | pass |
| Tab to nested source, Enter/Space; mouse click another source | Details expand/collapse with matching aria-expanded; no line panel opens | pass |
| Type SYN-TR-0001 in search and press Enter | FAIL banner for SYN-TR-0001, replacing the initial HOLD trial | pass |
| Keyboard-only alias, radio arrows, reason and submit | FAIL override by breeder-k appears in history; exactly one decision appended | pass |
| Type Ask question and press Enter, no model | Ask unavailable warning; no Portkey request | pass |

Default regression command: `uv run --project app pytest -q app/tests`:
**393 passed, 7 deselected** (six browser checks and one live check).
The browser tests and live tests remain opt-in.

## Reproducible capture and GIF (2026-09-30)

The recovered scratchpad script is now [capture.py](screenshots/capture.py), a
self-contained uv script with Playwright and Pillow. Run with a server already started
with `.env` loaded and `UC4_DECISION_LOG` pointing to a fresh temporary path; see the
[retake commands](../app/README.md#browser-input-checks-and-demo-capture).

```powershell
uv run team/screenshots/capture.py --base http://127.0.0.1:8876/
```

This run regenerated all six PNGs listed above (1440x900 viewport at 2x, four section
crops). Both Ask requests returned live answers; the two rehearsal PASS overrides were
written only to the temporary log, each preserving the original HOLD recommendation.
The search box is blurred before the trial shots.

**[Walkthrough GIF](screenshots/phase3_walkthrough.gif):** eight distinct nonblank frames,
1280x800, two seconds per frame, 16 seconds total, looping; **297,540 bytes**, below 8 MB.
Scenes: HOLD trial, criteria, flags, Ask question, live answer, override draft, recorded
history, line panel. Pillow checks verified every PNG, every GIF frame and its timing;
the PNGs and GIF frame contact sheet were reopened for visual review.

Options: `--out DIR` to change the output directory, `--no-gif` to retake only the PNGs.
Chrome runs headlessly, so a minimized desktop window cannot block capture. There are
no remaining items from the stopped agent's demo close-out list.
