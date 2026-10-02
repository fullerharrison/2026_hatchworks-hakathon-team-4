# Phase 2 - Bounded Moonshine Cadence Comparison

Request date: 2026-10-01. Measurement window: **2026-10-02 00:24:50.832263
to 00:43:55.994541 UTC**. The report filename follows the request date, not the
UTC measurement day. This synthetic engineering slice is complete; full Phase 2
remains In Progress and Phase 3 is not approved.

## Recommendation

**Stop this English tiny-streaming / Moonshine Voice 0.1.5 / Windows CPU
configuration as a live-demo candidate.** Increasing the supported SDK interval
did not fix domain or negation errors. Median processing cost decreased, but
first-partial and Stop-to-final latency worsened and processing remained slower
than real time. Keep typed/manual input as the fallback; no voice integration
or further tuning is authorized by this result.

This is not a rejection of every Moonshine model/runtime. Further evaluation
would require a separately approved configuration and representative breeder
corpus, hardware/resource targets and data permissions. No larger-model download,
microphone test or Phase 3 spike was performed. These synthetic results are not
held-out breeder validation.

## Supported Controls And Method

- Installed runtime: `moonshine-voice==0.1.5`, CPython 3.12.11, Windows CPU;
  English `TINY_STREAMING`, existing `quantized_26_08_21` assets. The same runtime
  manifest and all per-trial WAV hashes match across the three configurations.
- Installed SDK `transcriber.py` documents `create_stream(update_interval=...)`.
  `Stream.add_audio()` adapts its update floor using the previous inference
  duration, capped at ten times the configured interval. An interval is not a
  promised display cadence. `stop()` flushes the stream.
- The [pinned native option parser](https://github.com/moonshine-ai/moonshine/blob/234f60faa0eb388b01cdf7e60aca232af37aefda/core/moonshine-c-api.cpp)
  recognizes transcription interval, VAD, decoding, context/keyterms, diarization,
  spelling and provider controls. No public CPU thread-count option was found in
  that parser. No guessed thread/affinity/environment flags or provider override
  were used. Those other controls were inspected, not experimentally tuned.
- Only the SDK floor changed: fresh matched control 0.5 seconds, then 1.0 and
  2.0 seconds, fixed order, fresh child process per configuration. Ingress stayed
  at 100 ms and `identify_speakers` stayed `false`.
- Reused 12 speech WAVs from offline Microsoft David Desktop en-US synthesis and
  ten two-second silence WAVs. Each configuration ran both whole-utterance and
  native replay modes, three repetitions: **132 trials each, 396 total**. All
  trials succeeded; each child returned zero. No audio was regenerated.
- Timing is warmed and monotonic. Each mode/configuration has 36 speech timing
  observations. Percentiles are nearest-rank; repeated clips are timing samples,
  not additional accuracy examples. Model load and OS caches are uncontrolled.
- Stop-to-final is the duration of explicit Stop/flush (or whole-file inference),
  not last-spoken-sound latency. RTF is time spent in ASR calls, including flush,
  divided by clip duration, excluding replay waits. Backlog is lateness at chunk
  ingress against the nominal audio deadline, not a measured product queue.
- Live partials are nonempty `partial` events before explicit Stop, excluding
  started/completed duplicates and Stop-flush events. First partial is relative
  to replay start, not annotated speech onset. Consecutive event gaps are not
  word-aligned lag or browser-render cadence.

Execution took **1145.069 seconds (19.08 minutes)** within the 2400-second
comparison cap; every child was below its 900-second cap. The requested tuning
slice was bounded to 60 minutes, with execution capped at 40 minutes to reserve
reporting time. There is no complete end-to-end slice timer in the evidence;
only the execution duration is asserted. No further ASR runs were launched.

## Native Replay Results

Values are **p50 / p95**; seconds except dimensionless RTF. Each pair has n=36
unless the gap count is shown. All 36 speech replays per configuration produced
at least one live partial.

| SDK floor | Stop-to-final (s) | RTF | First live partial (s) | Live-update gaps (s; n) | Per-run max backlog (s) |
| --- | --- | --- | --- | --- | --- |
| 0.5 s matched control | 0.901 / 1.815 | 1.454 / 1.796 | 1.200 / 1.414 | 1.626 / 2.960; 67 | 1.780 / 3.306 |
| 1.0 s | 1.193 / 2.754 | 1.351 / 1.608 | 2.476 / 3.271 | 2.214 / 2.952; 30 | 2.063 / 2.786 |
| 2.0 s | 1.725 / 3.017 | 1.212 / 1.795 | 4.321 / 4.960 | unavailable; 0 | 2.221 / 2.860 |

At 2.0 seconds, **all 36 speech replays had exactly one live partial**. Zero
observed gaps does not mean zero latency or perfect cadence; there were no pairs
to measure. The 1.0-second floor had seven one-partial replays; the control had
at least two live partials in every speech replay.

Median native RTF fell by about 7.1% at 1.0 seconds and 16.7% at 2.0 seconds
relative to the matched control, but every median remained above one. Median
backlog rose while p95 backlog decreased; the experiment does not show queue
elimination or five-minute sustainability. The 2.0-second RTF tail was nearly
unchanged from control. Delaying work shifts cost into finalization and reduces
useful interim feedback rather than providing an acceptable live experience.

Even the fresh control exceeds the provisional 1-second first-partial/update-gap
targets and 1.5-second native Stop finalization proxy. None establishes the
actual speech-end/render or representative-command gates defined in the plan.

## Whole-Utterance And Historical Controls

| SDK floor label | Whole-utterance Stop-to-final p50 / p95 (s) | RTF p50 / p95 |
| --- | --- | --- |
| 0.5 s matched control | 2.756 / 4.023 | 0.838 / 1.214 |
| 1.0 s | 3.429 / 4.720 | 1.047 / 1.749 |
| 2.0 s | 2.872 / 3.617 | 0.838 / 1.219 |

The SDK floor does not affect whole-utterance inference. Its timing variation
therefore cautions against assigning all between-process differences to tuning.
All three whole-utterance p95 values exceed the provisional 3-second fallback
target. Host workload, fixed order, caches and short samples are uncontrolled.

The [earlier default baseline](moonshine-synthetic-3x.json) had native
Stop-to-final 2.549 / 4.521 seconds and RTF 1.970 / 2.680; its whole-utterance
values were 3.423 / 4.598 seconds and 1.125 / 1.350. These are historical context,
not the matched denominator for tuning gains. The fresh default was already
faster, without changing its SDK floor. Historical traces lack a Stop timestamp,
so an equivalent live-partial/gap comparison cannot be reconstructed reliably.

## Raw WER And Component Fidelity

Accuracy uses only repetition one: **12 speech clips and 76 reference words
per mode/configuration**. jiwer lowercases and removes punctuation/extra spaces;
it does not convert spoken numbers to digits. The separate fixed
[rubric](../corpus/fidelity-rubric.json) permits explicitly declared digit/word
equivalences and checks domain terms, units and one scoped negation without
changing the original transcript. It is fixture-specific diagnostics, not an
intent parser or exact intent-and-all-slots score.

| Configuration/mode | Raw word errors / words (WER) | Numeric | Unit | Domain term | Negation |
| --- | --- | --- | --- | --- | --- |
| All three, whole utterance | 19 / 76 (25.00%) | 6 / 7 | 7 / 7 | 9 / 11 | 0 / 1 |
| All three, native replay | 20 / 76 (26.32%) | 6 / 7 | 7 / 7 | 9 / 11 | 0 / 1 |
| Historical baseline, either mode | 19 / 76 (25.00%) | 6 / 7 | 7 / 7 | 9 / 11 | 0 / 1 |

Rendering `87.5` instead of "eighty seven point five", or `85`/`90` instead of
their spoken forms, contributes to raw WER but can pass declared numeric checks.
This distinction does not repair the safety-critical errors below. Each appears
unchanged in the first repetition of both modes in every tested configuration:

| Clip | Verbatim spoken reference | Verbatim ASR hypothesis | Diagnostic failure |
| --- | --- | --- | --- |
| question-03 | What is the fumonisin level? | What is the few menace in level? | Domain term |
| filter-03 | Show at least seventeen trials, not seventy. | Show at least seventeen trials. Not seventeen. | Numeric and scoped negation |
| value-02 | Enter fumonisin zero point eight ppm. | Enter few minutes and 0.8 ppm. | Domain term, despite correct number and unit |

Units passed seven fixtures, not a general unit-accuracy gate. The sole negation
fixture failed: preserving the word "not" is insufficient when its rejected
value changes. Partial and final hypotheses remain verbatim in per-run evidence;
no nearest-domain-term substitution, number repair or action submission occurred.
All silence outputs were empty: 30 trials per mode/configuration, **180 total**.
These are repeated digital silence, not noise or permission-denial tests.

## Evidence, Validation And Containment

- [Aggregate comparison](moonshine-tuning-comparison.json) contains exact metrics,
  rubric hash, per-component cases, timestamps and preservation snapshots.
- Raw results and captured child logs: [0.5 s JSON](moonshine-tuning-control-0500ms.json),
  [0.5 s log](moonshine-tuning-control-0500ms.log),
  [1.0 s JSON](moonshine-tuning-floor-1000ms.json), [1.0 s log](moonshine-tuning-floor-1000ms.log),
  [2.0 s JSON](moonshine-tuning-floor-2000ms.json), [2.0 s log](moonshine-tuning-floor-2000ms.log).
- The existing focused suites have **42 passing tests**, covering containment,
  evidence preservation, interval allowlisting, live-versus-flush cadence, raw
  WER and independent fidelity checks, including reversed negation and decimal
  boundaries. Document links and aggregate/per-trial consistency are checked
  separately. No additional model run is needed for verification.
- All 30 preexisting evidence/input/lock files retained their SHA-256 hashes.
  Every configuration used identical clip IDs/WAV hashes and runtime metadata;
  all 396 trials were successful and `actions_submitted` was zero throughout.
- **The whole-worktree unchanged check did not pass.** During execution, tracked
  contents changed outside this task in `app/README.md` and
  `app/tests/test_candidate_browser.py`; `app/pyproject.toml` newly appeared in the
  dirty-path snapshot. No action in this tuning slice targeted those files;
  they were left untouched. The check detects concurrent worktree changes but
  does not attribute them. It covers unstaged tracked dirty paths, not all staged,
  untracked or ignored files. Do not claim a globally unchanged repository.
- The terminal notification reported exit 1, despite all children returning 0
  and the complete aggregate being saved. With its recorded outside-state
  failure, the driver source's normal return is 2. The outer notification's
  1-versus-2 discrepancy is unresolved; the overall run is **not reported as a
  clean exit**. The saved evidence establishes complete measurements and a
  failed outside-state guard, not an ASR subprocess failure.
- All edits, generated evidence, dependencies, assets and scratch files from
  this work remain in this task. No microphone capture, audio/transcript uploads,
  additional model downloads, app changes or integration were performed in
  this slice. Existing historical evidence was not overwritten.

## Remaining Gates

Phase 1/2 remain open for owners, approved demo hardware, representative
languages/accents/noise and held-out breeder corpus, resource/sustainability
measurements, formal license/retention review and other candidate runtimes.
True speech-onset/end, word-aligned lag, browser rendering and workflow safety
were not measured. No proposed numeric or overall semantic target can be
accepted from these small fixture denominators. This report completes only the
authorized interval comparison, not the full feasibility study or a voice feature.
