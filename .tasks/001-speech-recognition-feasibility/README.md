# Speech Feasibility Research Workspace

**Closed; no further pursuit.** See the [final decision and archive](results/closure-2026-10-01.md).
The user requested preservation and a task-only commit, followed by temporary
file cleanup. Synthetic WAVs, labels, hashes, raw results, logs, reports and
research tooling are retained. Installed dependencies, model downloads, caches
and pytest scratch files were removed after artifact commit `475c736`.
The [cleanup receipt](results/closure-2026-10-01.md#cleanup-receipt) records 16
removed directories, 55 unchanged artifact hashes and zero task temp residue.
Commands below are historical reconstruction guidance, not authorized next steps;
the archived environment/model paths need not exist after cleanup.

Phase 1 preparation and an approved Phase 2 synthetic engineering slice have run.
Everything created by this work stays in this task directory.
This work does not modify the UC4 app, its dependencies, stores, browser preferences
or other task packs. Concurrent outside changes are recorded in the tuning report;
the whole repository is not claimed unchanged. This is not a delivered voice
feature or a representative ASR study.

## Implemented

- [preflight.py](preflight.py): standard-library-only, offline machine inventory.
  Records OS, architecture, interpreter, logical CPUs, bounded Windows hardware
  probes, browser file versions, free disk space and installed ASR distribution
  metadata. It does not import/load recognizers, open microphones or read secrets.
- [test_preflight.py](test_preflight.py): output containment, traversal and linked
  directory rejection, valid JSON and preservation of existing evidence.
- [Phase 1 results](results/phase-1-2026-10-01.md): dated source pins, capability
  matrix, local observations, verification and outstanding approvals.
- [Machine inventory](results/machine-2026-10-01.json): the developer machine,
  explicitly not an approved demo target or performance result.
- [Phase 2 synthetic results](results/phase-2-synthetic-2026-10-01.md): 132 local
  trials, limitations, observed domain errors and remaining gates.
- [run_moonshine.py](run_moonshine.py): separate task-local asset preparation and
  offline utterance/native-streaming measurements on the synthetic corpus.
- [benchmark.py](benchmark.py): bounded WAV input, provenance, jiwer word scoring
  and nearest-rank timing summaries; no numeric-word normalization or intent execution.
- [compare_moonshine.py](compare_moonshine.py): deadline-bounded offline interval
  comparisons, fixed-rubric fidelity diagnostics, separate outputs and preservation
  checks for prior evidence, input WAVs and tracked changes outside this task.

## Run From Repository Root

These commands reuse the existing interpreter without installing, synchronizing
or changing anything in the app environment. The preflight itself needs only
Python 3.12+; tests additionally need the already-installed pytest.

```powershell
$task = '.tasks/001-speech-recognition-feasibility'
& .\app\.venv\Scripts\python.exe -B -W error "$task/preflight.py" --output results/machine-next-run.json
```

Use a fresh evidence filename for each run. Existing files are never overwritten.
Output must be under this task's `results/` directory. Hardware queries are bounded
to 15 seconds each; unavailable probes are recorded as unknown, not inferred.
GPU `AdapterRAM` is not verified VRAM. Browser versions are installed file versions,
not evidence of a selected, launched or microphone-tested browser.

```powershell
$task = '.tasks/001-speech-recognition-feasibility'
& .\app\.venv\Scripts\python.exe -B -W error -m pytest -q "$task/test_preflight.py" -p no:cacheprovider "--basetemp=$task/pytest-tmp-rerun"
```

Bytecode and pytest caches are disabled. Scratch files remain within the task and
are ignored by its local [.gitignore](.gitignore). Pytest replaces its own named
scratch directory on rerun; do not point `--basetemp` at research evidence.

## Approved Phase 2 Smoke Slice

Approval covers local Moonshine installs/model downloads and synthetic English
tests on this Windows CPU. No microphone, audio upload or app integration was
approved. Results are engineering smoke evidence from one synthetic voice.

From the repository root:

```powershell
& ./.tasks/001-speech-recognition-feasibility/setup.ps1 -DryRun
& ./.tasks/001-speech-recognition-feasibility/setup.ps1
```

Setup uses the existing interpreter only to create a separate task-local environment;
all installs, uv cache and temporary paths stay in this task. It generates and
installs the hash-locked [requirements.lock.txt](requirements.lock.txt), restoring
process environment settings afterward. Windows system trust is used for model
downloads; TLS verification is never disabled.

The speech WAVs already exist locally and must not be overwritten. On a clean copy
without WAVs, generate them with the offline Windows synthesizer:

```powershell
& ./.tasks/001-speech-recognition-feasibility/synthesize.ps1 -ValidateOnly
& ./.tasks/001-speech-recognition-feasibility/synthesize.ps1
```

Silence WAVs are created by the runner. Both scripts use only the fixed synthetic
[manifest](corpus/synthetic.json); no speech is played or captured. Large downloaded
assets, caches and environments are git-ignored within this task. The 22 original
synthetic/silence WAVs are retained as committed evidence artifacts, not temp files.

Prepare assets on a clean copy, using a new result filename when one already exists:

```powershell
$task = '.tasks/001-speech-recognition-feasibility'
& "$task/.venv/Scripts/python.exe" -B "$task/run_moonshine.py" --prepare --output results/moonshine-runtime.json
```

Run offline measurement against the saved, hash-checked asset manifest:

```powershell
$task = '.tasks/001-speech-recognition-feasibility'
& "$task/.venv/Scripts/python.exe" -B "$task/run_moonshine.py" --runtime results/moonshine-runtime.json --output results/moonshine-rerun.json --repetitions 3
```

Use a new output filename; existing evidence is preserved. Final evidence is
[moonshine-synthetic-3x.json](results/moonshine-synthetic-3x.json), with first-repetition
accuracy and all timing repetitions. It shows unfavorable latency/realtime factor
and domain errors; no live-demo readiness is claimed.

Run all contained tests with the research interpreter:

```powershell
$task = '.tasks/001-speech-recognition-feasibility'
& "$task/.venv/Scripts/python.exe" -B -W error -m pytest -q "$task/test_preflight.py" "$task/test_benchmark.py" -p no:cacheprovider "--basetemp=$task/pytest-tmp-research"
```

If the editor still uses the app interpreter, Moonshine imports may appear missing.
Use the dedicated research interpreter for these scripts; the app environment and
workspace settings have deliberately not been changed.

## Bounded Cadence Comparison

The installed SDK documents `create_stream(update_interval=...)` and an adaptive
update floor. The inspected native option parser does not expose a public CPU
thread-count setting; no thread, affinity, environment or execution-provider flags
were guessed or changed. This slice compares only 0.5, 1.0 and 2.0-second SDK floors
using the existing model, identical WAVs and three repetitions in fresh processes.

```powershell
$task = '.tasks/001-speech-recognition-feasibility'
& "$task/.venv/Scripts/python.exe" -B -W error "$task/compare_moonshine.py" --dry-run
& "$task/.venv/Scripts/python.exe" -B -W error "$task/compare_moonshine.py" --prefix moonshine-tuning-rerun --budget-seconds 2400
```

Use a new prefix each time. Each child is capped at 15 minutes, and the comparison
at 40 minutes, reserving time for analysis within the requested 60-minute slice.
The driver does not download assets or regenerate speech. Existing evidence and
audio are hashed before execution and checked after it. Timed metadata uses
`sys.platform` rather than the previously unstable Windows WMI path.

Raw-reference WER is unchanged. Separate [fixture fidelity checks](corpus/fidelity-rubric.json)
accept only declared number-word/digit forms, case-insensitive domain terms and
the explicitly scoped negation. They never rewrite hypotheses and are not a
general intent/slot parser. Failed first trials remain in fidelity denominators;
repeated runs are timing samples, not independent speakers or accuracy examples.

Live interim cadence excludes `started`/`completed` duplicates and partials emitted
during Stop flushing. Historical traces without a Stop timestamp cannot provide
that comparable cadence measurement. Missing live partials remain visible.

[Completed comparison and recommendation](results/phase-2-tuning-2026-10-01.md):
396 successful trials; stop this tiny-model/Windows-CPU configuration for the live
demo. Larger floors delayed interim/final output without fixing domain or negation
errors. Prior evidence and inputs are preserved. The outside tracked-state guard
failed on concurrent app-file changes; no clean overall exit is claimed. The full
Phase 2 and representative breeder/resource gates remain open.

## Remaining Gate

Representative language/accent/noise scope, microphone consent/access/retention,
formal license/redistribution review, other candidate runtimes and benchmark targets
were not resolved. The full [Phase 2](plan/phase-2-asr-benchmark.md) study is deferred,
and [Phase 3](plan/phase-3-workflow-spike.md) was not authorized or run. The task is
closed by the explicit stop decision, not by claiming these gates passed.

Public endpoints received documentation/package/model requests only. No audio,
transcripts, company datasets or credentials were uploaded. During execution the
research environment/model cache were task-local; they are disposable after
artifact preservation. The app interpreter is not the ASR runtime.
