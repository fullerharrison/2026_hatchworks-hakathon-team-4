# Phase 2 - ASR Benchmark And Streaming Comparison

Parent: [001-speech-recognition-feasibility](../task.md) | Status: 🧊 Icebox | Size: **M** | Proposed timebox: 5-8 hours

Archived by the user's stop decision, 2026-10-01. The approved synthetic benchmark
and bounded cadence comparison are complete; the larger representative study and
other candidates are deferred, not passed. See [final disposition](../results/closure-2026-10-01.md).
No further benchmark, model download or recording is planned. The work plan below
is historical and is not an instruction to continue.

## Goal And Entry Gate

Measure recognition and latency on the approved hardware/corpus, separately from LLM interpretation. Entry requires [Phase 1](phase-1-requirements-sources.md) approval, model/runtime/license clearance and any recording/service approval. Use an isolated research environment; do not edit the app dependency set or active database.

Bounded engineering-slice approval on 2026-10-01 covers task-local Moonshine
install/model downloads and synthetic English tests on this Windows CPU only.
[Actual results](../results/phase-2-synthetic-2026-10-01.md) include asset hashes,
three repetitions of utterance/native replay, silence trials and failed requirements.
The planned representative corpus, other runtimes, recording approvals and full
exit gates remain unmet. No Phase 3 permission is implied by this smoke slice.

The separately requested 60-minute tuning slice is complete:
[comparison report](../results/phase-2-tuning-2026-10-01.md), three supported SDK
floors, unchanged tiny model/WAVs, three repetitions and 396 successful trials.
No public CPU-thread option was found in the inspected parser; none was guessed.
Higher floors did not resolve fidelity failures and worsened first/final latency.
Stop this configuration for a live demo; retain typed/manual input. Execution
took 19.08 minutes; full-slice elapsed time was not instrumented. Prior evidence
is preserved, but concurrent outside tracked-file changes failed the worktree
guard. The complete phase and its held-out/resource/integration gates remain open.

## Bounded Execution Order

1. Establish utterance-end/push-to-talk baselines on the same recordings before tuning streaming. Record cold model load, warmed inference, install problems and exact artifact versions. Cap install troubleshooting at two hours per candidate.
2. Start with a Moonshine Streaming checkpoint using Moonshine Voice on the actual Windows CPU; try browser/WASM if supported within the timebox. Compare tiny then a larger model only if needed. Label Transformers separately and verify actual incremental input APIs rather than equating generated text-token streaming with live audio processing.
3. Run Nemotron 3.5 ASR on the approved available runtime. Compare 320 ms with one lower and one higher context/chunk setting, expanding to 80/160/320/560/1120 ms only if practical. Preserve recognizer state; do not add overlap to its native non-overlapping cached path. Test supplied language versus automatic detection only for approved languages. Distinguish NeMo GPU, Transformers and native C++/quantized results.
4. Run the exact Parakeet CLI only on a supported/approved host. Compare ordinary VAD `listen`/file output with versioned session partials where available. Inspect whether partials reprocess accumulated audio; measure that extra cost. If Windows blocks it, record "not runnable on target". A substitute ONNX runner needs separate approval and labeling.
5. For buffered modes, test 1/2/4-second windows with 250/500 ms overlap where the model permits it. Define stable-prefix/replacement handling, deduplication and long-utterance bounds. These are hypotheses to tune, not model-supported settings by default. Include an explicit Stop flush and VAD endpoint sweep around 400/800/1500 ms silence.
6. Replay identical audio at real-time cadence, not as instant file uploads, to measure incremental behavior. Then verify at least one real microphone run per shortlisted runtime. Use identical audio/labels for comparable runs and note hardware differences rather than hide them.
7. Hold tuning choices fixed for held-out runs. Repeat timing runs three times, retaining each result; repeated clips are not additional independent accuracy samples. Report failures/timeouts, not just successful runs.

## Metrics And Measurement Definitions

| Metric | Definition/report |
| --- | --- |
| First useful partial | Speech onset to first nonempty displayed hypothesis; exclude prerecorded file-loading shortcuts |
| Update lag/cadence | Annotated spoken word/phrase end to corresponding rendered interim text; distribution of update gaps and replacement churn |
| Finalization latency | Last spoken sound to final accepted ASR transcript; includes endpoint silence, processing, transport and render |
| WER | Substitutions + deletions + insertions divided by reference words; report normalization, condition/language/speaker and raw examples |
| Domain slots | Exact intent, candidate/field, comparator, numeric value and unit matches; strict numeric/entity scoring, not WER alone |
| Real-time factor | ASR wall-clock processing time divided by audio duration; report full-stream recomputation and queue growth, not only final decode |
| Resources/cost | Peak RAM/VRAM, download/disk size, cold load, CPU/GPU utilization, session concurrency and any hourly/service/egress cost |
| Failure behavior | Silence hallucinations, boundary loss, duplicate words, premature endpoint, dropped chunks, canceled-session late results |

Measure local capture/ASR/render clocks monotonically. Do not subtract unsynchronized browser/server clocks for network latency. Record sample counts and p50/p95; small-sample p95 is directional, not a production SLA. For runtimes without confidence scores or word times, mark them unavailable instead of inventing them.

## Proposed Gates, Pending Phase 1 Approval

These are research targets, not observed performance or agreed production requirements.

| Gate | Proposed pass condition |
| --- | --- |
| Live interim option | Warmed first useful partial p95 <= 1 second and interim update-gap p95 <= 1 second on representative commands |
| Native/interim finalization | Warmed p95 <= 1.5 seconds after speech ends, including endpoint and render |
| Utterance fallback | Warmed p95 <= 3 seconds after explicit Stop; report VAD endpoint latency separately |
| Sustainable local execution | Real-time factor < 1, no continuously growing queue during a five-minute session, and fits the approved RAM/VRAM/disk envelope |
| Transcript usefulness | Held-out WER <= 15% quiet and <= 25% representative noise; also report domain errors even when WER passes |
| Semantic fidelity | Critical numeric/unit/comparator/entity slots >= 95% exact and supported utterances >= 90% exact intent-and-all-slots; report counts and each outcome separately |
| No-speech behavior | No submitted action or persisted value during at least ten silence/noise-only trials |

If only the utterance fallback passes, recommend it explicitly rather than describe it as word-by-word streaming. A passed ASR gate does not authorize unreviewed numeric entry. Confidence thresholds, if available, need observed calibration; high confidence alone never authorizes a mutation.

## Domain And Boundary Cases

Cover germination, cold test, fumonisin, yield-versus-check, marker/RAG wording, literal candidate ID fragments, decimals, percentages, ppm and trial counts. Include "seventeen" versus "seventy", "zero point eight", "not below ninety", "change eighty-five to ninety", long pauses around a decimal/unit, numbers split across chunks, mixed-language numbers, missing field context and "change my green rule".

The current filter interpreter supports inclusive bounds only: strict comparisons, OR and unclear units should clarify even if ASR transcribes them perfectly. Report ASR fidelity separately from that downstream limitation. No unit conversion or nearest-match candidate substitution without explicit review.

## Deliverable And Exit Check

A versioned run manifest, configuration matrix, per-clip transcripts/partial timeline, aggregate metrics with denominators, failure examples and shortlist/fallback. Store recordings only under approved policy; results can retain redacted IDs and hashes rather than raw audio in git.

- [ ] **Given** identical held-out clips, **When** comparisons finish, **Then** measured configurations/modes and blocked configurations are clearly separated.
- [ ] **Given** misleading partial numbers or chunk boundaries, **When** replay runs, **Then** revisions, duplicate handling and final slot errors are retained as evidence.
- [ ] **Given** the accepted gates, **When** a shortlist is proposed, **Then** it names the exact model/runtime/hardware and failed requirements, not just a model brand.

Request sandbox approval before [Phase 3](phase-3-workflow-spike.md). No app implementation is authorized by these results.
