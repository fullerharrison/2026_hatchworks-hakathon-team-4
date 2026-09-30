# Phase 3 walkthrough: breeder screen and override log

**Date:** 2026-09-30 · **Run by:** controller, Claude in Chrome · **Branch:** `phase-3-breeder-screen` at `9aec632` (commits after it, up to the final-review fixes, were docs and EDA only; the fixes below change `app.js` and `api.py`) · **Plan:** [phase-3-breeder-screen.md](../.tasks/uc4-assistant/phase-3-breeder-screen.md) (Task 5, "Validate the demo")

## Setup

- Server: `uc4-ask serve` on http://127.0.0.1:8766/.
- `UC4_ZIP` pinned to `get_started/RE__Hatchworks_Hackathon_-_4th_Use_Case.zip` (the original v2 archive). A second archive, `..._09-30-2026.zip`, now sits in `get_started/` and makes `find_zip` ambiguous without the variable.
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
| 11 | Ask "Why is SYN-TR-0037 amber?" without Portkey configuration | "Ask unavailable: No model: set [llm] model in agent.toml or UC4_LLM_MODEL"; banner and decision form still work | pass for the no-model path; live answer pending Portkey credentials (Phase 2 open item) |

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

Scenario 6 re-check: to be re-checked by the controller.

## Open

- **Screenshots and GIF** (`team/screenshots/phase3_*.png`, `phase3_walkthrough.gif`): still to be taken by a human with the browser window visible.
- **Live `/ask` answer** (scenario 11 with numbered citations and disclaimer): pending Portkey credentials. Only the "Ask unavailable" path is verified.
- **Finding 1, stale trial after failed search:** after an ambiguous or unknown search the previous trial's banner and decision form remain visible, and the form still targets the previous trial. Demo risk: a decision could be recorded against the wrong trial. Already deferred as a Task 3 minor.
- **Finding 2, generic 422 text:** Pydantic's "String should have at least 5 characters" is shown for a blank reason. A breeder-facing message ("A reason of 5-1000 characters is required") would read better.
- **Finding 3, repeated verdict word:** the line panel shows "▲ HOLD: HOLD: …" (verdict word repeated from `reason`).
