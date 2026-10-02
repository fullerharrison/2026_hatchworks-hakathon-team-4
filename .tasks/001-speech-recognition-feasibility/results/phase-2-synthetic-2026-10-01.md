# Phase 2 Synthetic Engineering Results

Recorded: 2026-10-01 | Status: 🔄 In Progress
Parent: [Speech feasibility](../task.md)

## Approved Scope

The user selected **Yes, local setup and synthetic tests** after being asked
explicitly about task-local Moonshine installation, model downloads and synthetic
English tests on this Windows machine. The confirmed scope is CPU execution,
task-local environment/caches, and a two-hour installation-troubleshooting cap.

No microphone capture, participant recording, audio uploads, hosted inference,
app changes or Phase 3 workflow spike was approved or performed. Public network
requests fetched package metadata, dependencies and model assets; ASR consumed
local synthetic files only. The human research/SME/data owners and production
license/redistribution review remain unresolved. This approval enables a bounded
engineering slice, not blanket completion of Phase 1 or its representative corpus.

## Reproducible Configuration

| Item | Actual configuration |
| --- | --- |
| Runtime | Moonshine Voice 0.1.5, Windows x64 wheel, task-local Python 3.12.11 environment |
| Checkpoint | English `TINY_STREAMING`, asset family `tiny-streaming-en/quantized_26_08_21` |
| Artifacts | Ten downloaded files totaling 46,899,201 bytes, including optional spelling assets; individual hashes in [runtime manifest](moonshine-runtime.json) |
| Dependencies | Hash-locked [requirements.lock.txt](../requirements.lock.txt), installed with `uv pip sync --require-hashes`; no app environment sync |
| TLS | `truststore==0.10.4`, Windows system certificate store for preparation; verification was not disabled |
| Host | Current Windows developer machine from [Phase 1](phase-1-2026-10-01.md); CPU model/RAM still unknown |
| Fixtures | Twelve speech clips across four outcomes, one Microsoft David Desktop en-US voice; ten identical two-second silent waveforms under distinct IDs |
| Audio | Offline Windows System.Speech synthesis, 16 kHz mono PCM16; no microphone or playback |
| Modes | Whole-utterance file baseline and native incremental WAV replay at real-time cadence |
| Replay | 100 ms ingress chunks, requested update interval 500 ms; actual SDK interval is adaptive, not a fixed display cadence |
| Repetitions | Three timing runs per clip/mode; accuracy denominator uses first repetition only |
| Actions | None: no Ask, filter, preference, form, policy or history operation exists in this runner |

The package imports and native library loaded locally. Preparation used an explicit
task-local `cache_root`; measurement does not call a model downloader. All local
model SHA-256 hashes are rechecked before ASR. The SDK's optional spelling files
were fetched by its downloader, but no spelling or identifier-specific evaluation
was performed. No speaker identification was enabled.

## Measurements

Evidence: [all trials and event traces](moonshine-synthetic-3x.json), recorded
2026-10-01T23:49:40 UTC. 132 trials completed: 66 per mode, zero reported SDK
failures. Successful execution does not mean the transcription was correct.

| Metric | Whole Utterance | Native Streaming |
| --- | --- | --- |
| Synthetic speech accuracy denominator | 12 clips, 76 reference words | Same 12 clips, 76 words |
| Raw-reference word errors / WER | 19 / 25.0% | 19 / 25.0% |
| Stop-to-final p50 / p95 | 3.423 / 4.598 s | 2.549 / 4.521 s |
| Stop-to-final timing denominator | 36 speech runs | 36 speech runs |
| Processing real-time factor p50 / p95 | 1.125 / 1.350 | 1.970 / 2.680 |
| First nonempty event from replay-start p50 / p95 | Not applicable | 1.494 / 2.073 s, 36 speech runs |
| Maximum observed replay backlog | Not applicable | 3.972 s |
| Nonempty final output on silence | 0 / 30 runs | 0 / 30 runs |

Model creation took 1.968 seconds with OS caching uncontrolled. It is not a
certified cold-start benchmark. Native replay's longest speech run took 9.637
seconds including finalization. Queueing was measured as missed ingress deadlines
in the synchronous replay loop, not as an internal SDK queue length.

Timing uses one monotonic clock. Whole-utterance Stop is represented by beginning
inference on the complete clip. Native Stop occurs after feeding the final chunk;
input lag can make it later than the clip's nominal end. Speech onset/last-sound
annotations, browser transport/render, confidence calibration, word-aligned lag,
peak RAM/VRAM and a five-minute sustainability run were not measured. First
nonempty text may be wrong, and is not proof of a useful partial.

## Accuracy And Safety Limits

WER normalizes case, punctuation and whitespace only. It deliberately does not
convert number words into digits. Therefore the 25% result includes rendering
differences such as “eighty seven point five” versus `87.5` and must not be read
as a 25% semantic-slot error rate. Formal intent/all-slot scoring remains unrun.
Canonical expected fields/numbers/units remain separate in the [labels](../corpus/synthetic.json).

Observed critical errors, present in both final modes:

- “What is the fumonisin level?” became “What is the few menace in level?”
- “Enter fumonisin zero point eight ppm.” became “Enter few minutes and 0.8 ppm.”
- “Show at least seventeen trials, not seventy.” became “Show at least seventeen
  trials. Not seventeen.” The rejected value was mistranscribed; clarification
  cannot safely rely on the original meaning surviving ASR.

The numeric-revision clip first emitted “You.”, then “Show at least seventeen.”,
then a separate “Not seventeen.” line. This is evidence of revisable interim
content, not a safe executable command. No interpretation or actions were run.

Silence results cover identical digital silence, not ten independent noisy
conditions or an environmental false-activation test. One synthetic voice does
not establish accent, breeder, microphone or background-noise performance.
The corpus is engineering smoke data, not the planned 60-utterance/120-clip
representative tuning/held-out study. No biological evidence was used.

## Failures And Verification

- Initial asset preparation failed certificate verification at `download.moonshine.ai`.
  Using verified Windows system trust via the pinned adapter resolved it;
  `verify=False` and certificate bypasses were not used.
- Multiline terminal setup did not create an interpreter. The contained
  [setup script](../setup.ps1) replaced it, with a dry-run plan and environment
  restoration. It created the task-local environment and hash-locked install.
- A post-run unit-test process crashed with Windows WMI error `0x8007000e` during
  module-level truststore initialization. The exact system cause is unresolved.
  Truststore now initializes only inside preparation; pure metrics aggregation
  does not import native ASR or TLS dependencies.
- After that separation, **22 focused tests passed in 0.67 seconds**, with warnings
  treated as errors, caches disabled and scratch inside the task. This fixes the
  unnecessary test import path; it does not certify Windows WMI stability for
  future preparation/inventory calls.
- The repaired runner imports successfully without initializing truststore.
  Existing runtime-native import and complete 132-trial evidence remain retained;
  ASR was not rerun merely to repeat identical measurements after the import repair.
- Explicit WAV writer typing removed static writer/read warnings. Editor missing
  Moonshine-import warnings can remain when the editor uses the app interpreter;
  the dedicated research interpreter has the installed runtime. No workspace
  settings or app dependencies were changed to silence those warnings.

## Current Decision And Next Gate

**Do not advance this configuration to a live demo or Phase 3 yet.** It runs on
Windows, but the current synthetic smoke slice shows slow finalization, processing
RTF above one, growing replay lag, and domain/negation errors. These observations
are unfavorable against the proposed targets, not a held-out acceptance verdict
or a rejection of every Moonshine configuration.

Retain typed/manual workflows. A bounded next investigation can test documented
CPU-thread/runtime settings or another approved model while holding fixtures and
labels fixed; separate each configuration rather than overwrite this run. Larger
models are not assumed to solve both accuracy and latency. Resolve CPU/RAM and
host WMI behavior before interpreting resource feasibility.

Nemotron remains unrun without an approved runnable Windows/runtime configuration;
the exact Parakeet CLI remains portability-blocked on this target. Buffered interim
mode, browser/WASM execution, actual microphones, consenting representative speakers,
held-out/noise accuracy, domain-slot evaluation and workflow safety remain unrun.
Separate approval is still required for recordings, hosted audio, app integration
and product implementation. Synthetic smoke success is not permission for writes.