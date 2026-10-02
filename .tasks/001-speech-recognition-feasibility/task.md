# 001 - Speech recognition feasibility for UC4

Created: 2026-10-01 | Status: ✅ Done (closed: no-go; pursuit discontinued) | Priority: **P2** | Size: **L**, split into bounded research phases

Owner: unassigned. Suggested roles: AI answers + Screen and log, with a breeder/SME reviewer and a data/privacy approver. These are proposed responsibilities, not accepted assignments.

## Final Disposition

The user explicitly requested on 2026-10-01 that all findings/artifacts be
documented and committed, temporary files removed afterward, and this pursuit
not continued. [Final decision and archive](results/closure-2026-10-01.md) closes
the approved engineering work as a no-go for the tested configuration. The
original broader research is deliberately discontinued, not completed against
its unrun acceptance criteria. Keep typed/manual workflows. No further ASR
evaluation, recording, Phase 3 spike or product implementation is planned;
reopening requires a new explicit request. Sections below retain historical
scope and evidence; unchecked research gates are not newly approved work.

## Objective

Determine whether a non-technical breeder can use speech to ask grounded UC4 questions, express personal selection criteria, and enter values reliably enough for a hackathon demonstration. Compare native incremental recognition with buffered/chunked recognition and push-to-talk utterance transcription. Deliver a measured recommendation and a separately approvable implementation scope, not a production voice feature.

The initial request authorized this task, plans, and preliminary public-source inspection. The 2026-10-01 request to start implementation within this task additionally authorizes contained preparatory tooling and deterministic tests. It does not explicitly approve installing models, recording people, sending audio to services, changing the app, or running the gated ASR/workflow spikes. Those activities and any later product implementation still need the gates below.

Implementation started: [task-local tooling and rerun guide](README.md), [Phase 1 evidence and open approvals](results/phase-1-2026-10-01.md), and [developer-machine inventory](results/machine-2026-10-01.json). Eight containment tests pass. No ASR performance or workflow-integration result is claimed.

Approval update, 2026-10-01: the user explicitly approved task-local Moonshine
installation/model downloads and synthetic English tests on this Windows CPU,
excluding microphone capture and audio uploads. [Phase 2 engineering evidence](results/phase-2-synthetic-2026-10-01.md)
now records 132 completed trials, unfavorable latency/domain findings and 22
passing focused tests. This bounded approval does not pass the representative
corpus, owner, recording, hosted-audio or Phase 3/product gates. All additions remain
inside this task; no app dependency, preference or database change was made.

Tuning update for the 2026-10-01 request: the bounded, offline SDK-floor comparison
is complete. [Dated tuning report](results/phase-2-tuning-2026-10-01.md) records
396 successful trials across 0.5/1.0/2.0-second floors and 42 passing focused
tests. Native median RTF stayed above one, larger floors delayed first/final
results, and every configuration retained domain and scoped-negation errors.
Recommendation: stop this tiny-model/Windows-CPU configuration for the live demo;
keep typed/manual fallback. Prior evidence/input hashes are intact. The outside
tracked-state guard failed during concurrent app-file changes, which this work
did not touch; the aggregate run is not claimed as a clean exit. Full Phase 1/2
remain In Progress, and no Phase 3 permission or breeder validation is implied.

## Current Evidence And Local Hypothesis

- [Existing voice/NL task](../uc4-breeder-usability/05-voice-nl-input.md) already defers speech and write adapters; this task owns the model/runtime feasibility investigation, not a duplicate typed-filter implementation.
- [API reference](../../app/API.md): `/ask` supports candidate/revision context; `/filters/interpret` and `/filters/validate` produce reviewable filters, applied explicitly. Enrichment uses existing draft, review, preview and activation steps.
- [Filter interpreter](../../app/src/uc4_mcp/filter_intent.py) handles English list-filter requests only. Preference saves, evidence edits, scoring changes and mixed filter/write requests require clarification, not execution.
- [Browser preferences](../../app/src/uc4_mcp/static/preferences.js) save name/location/source channel explicitly and optionally remember view filters and selection. There is no inspected server-side personal scoring-profile API. Applied filters may already persist when remembering the view is enabled; preview-only voice input must not trigger that path.
- [Candidate policy](../../app/src/uc4_mcp/candidate_core.py) is provisional synthetic policy, not validated vegetable-breeding criteria. Voice must not change it or turn user suggestions into biological truth.

**Falsifiable hypothesis:** finalized, editable speech can reuse the existing question/filter/form paths while partial transcripts remain display-only. Recognition and interpretation can be evaluated separately; no new autonomous agent or MCP write tool is needed for the smallest useful slice.

**Cheap discriminating check:** in a disposable fixture, replay an interim threshold that changes from "seventy" to "seventeen", then cancel. Confirm no Ask submission, applied filter, local-storage update or API write occurs. Submit the corrected final text through the existing typed workflow and compare context, proposal and validation results. Failure identifies a missing integration boundary rather than automatically selecting a larger model.

## User Outcomes And Boundaries

| Outcome | Example utterance, illustrative only | Proposed route | Human control |
| --- | --- | --- | --- |
| Extract information | "Why is this candidate amber?" | Final text to existing Ask with selected candidate and revision | Editable transcript; explicit Ask; existing citations remain visible |
| Change current selection criteria | "Show germination at least ninety percent" | Existing filter interpretation and validation | Review values/units, then Apply; clarify filter versus scoring rule |
| Retain personal defaults | "Remember these filters" / "Set my review location to Station A" | Separate, allowlisted browser preference proposal; adapter not yet implemented | Preview exact scope and persistence, then explicit confirmation |
| Input values | "Enter cold test eighty-seven point five percent" | Dictate into a named active field; numeric parsing and existing form validation | Review field, candidate/source row, value and unit before existing form submission |
| Change scoring criteria | "Make ninety percent my minimum for green" | Clarify and reject as unsupported in the minimum slice | No policy mutation; separately approved future scenario/profile work |

In scope: all three supplied candidate families, Windows demo feasibility, supported breeder language/accent discovery, word-by-word-like interim updates, chunk processing, utterance fallback, privacy/licensing, domain accuracy, resource/cost estimates and confirmation behavior.

Out of scope: model training/fine-tuning, always-on listening, autonomous decisions, automatic evidence activation, speaker identification, voice authentication, text-to-speech, production deployment and silently learned preferences. These add data, safety or infrastructure requirements beyond the research question.

Deferred: multilingual production rollout, organization-wide profiles, actual scoring-rule editors and decision-command adapters. Revisit only after a passing feasibility decision and explicit product/data approval. Spoken input does not verify actor identity.

## Initial Source Register And Candidate Matrix

Public documentation inspected on 2026-10-01. Statements below are upstream descriptions, not locally verified performance. Phase 1 must pin model revisions/runtime versions and recheck licenses and support before execution.

| Candidate | Source-described behavior | Local feasibility question | License/support caveat |
| --- | --- | --- | --- |
| NVIDIA Nemotron 3.5 ASR streaming 0.6B | 600M-parameter cache-aware FastConformer/RNNT; native non-overlapping chunks of 80/160/320/560/1120 ms; language conditioning | Compare 320 ms against lower/higher latency settings; assess GPU service, Transformers and documented native C++/GGUF route on available hardware | Model card lists OpenMDW-1.1; NeMo integration lists Linux. Native Windows/CPU support depends on the selected runtime and remains unverified; H100 throughput is not a laptop result |
| lucataco Parakeet CLI | Rust/ONNX wrapper for Parakeet TDT 0.6B v3; ordinary `listen` buffers until VAD speech end; README also describes opt-in daemon/session interim `partial` events | Inspect the exact session protocol and implementation: are partials produced by redecoding buffers, how much context is retained, and can browser audio be supplied? | README targets Apple Silicon; Linux/Intel are untested and Windows support is not established. Code Apache-2.0, weights reported CC-BY-4.0, Silero VAD MIT; verify exact artifacts separately |
| Moonshine Streaming / Moonshine Voice | Transformers describes tiny/small/medium streaming models with incremental audio processing. Moonshine Voice describes on-device streaming and Python, JS/WASM and Windows paths | Compare SDK streaming first on a Windows CPU/browser; treat Transformers as a separate runtime, not proof that file-based `generate()` gives live microphone updates | Repo reports MIT for code/models except enumerated legacy non-English non-streaming models. Verify exact checkpoint, language, WASM assets and wheel compatibility |

Sources:

1. [Nemotron model card](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b).
2. [Parakeet CLI repository and README](https://github.com/lucataco/parakeet-cli).
3. [Parakeet session protocol](https://github.com/lucataco/parakeet-cli/blob/main/docs/session-protocol.md). The initial web fetch did not expose the protocol body; partial-event semantics require verification, not an assumed native-streaming claim.
4. [Transformers Moonshine Streaming documentation](https://huggingface.co/docs/transformers/model_doc/moonshine_streaming).
5. [Moonshine repository](https://github.com/moonshine-ai/moonshine).
6. [Moonshine platform quickstart](https://moonshine-voice.readthedocs.io/en/latest/quickstart/) describes browser `onText` updates and `onLine` results plus a Windows sample; these do not establish browser performance here.

**Starting order, not a winner:** Moonshine SDK on the actual Windows CPU/browser, Nemotron on an available approved runtime, then Parakeet CLI as a portability-gated comparator. If the CLI cannot run on the target machine, record that result. An alternative Parakeet ONNX runtime is a separately labeled configuration, not evidence that this CLI works on Windows.

## Streaming Modes To Compare

| Mode | What the breeder sees | Processing strategy | Main risk |
| --- | --- | --- | --- |
| Native streaming | Revisable words/phrases appear during speech | Keep recognizer/session state between audio chunks; honor model-specific context | Token updates are not necessarily word-aligned or final; cache/session correctness |
| Buffered interim recognition | Revisable text after periodic chunks | Test 1/2/4-second windows and 250/500 ms overlap only where supported; reconcile repeated text | Recompute cost, boundary loss, duplicated words, contradictory numeric revisions |
| Utterance/push-to-talk | Final text after Stop or speech endpoint | VAD or explicit end, then transcribe whole bounded utterance | Endpoint delay, premature cuts during a breeder's pause |

"Live word-by-word" means useful interim transcript updates, not guaranteed finalization of every spoken word. Audio streaming, decoder-token streaming and stable transcript publication must be measured separately. Native streaming also processes chunks; chunk transport alone does not make an offline model incremental.

## Research Acceptance Criteria

- [ ] **Given** the supplied sources, **When** Phase 1 closes, **Then** all three candidates have versioned capability/license/runtime evidence or an explicit unresolved/blocked record.
- [ ] **Given** identical approved audio and target hardware, **When** Phase 2 runs, **Then** supported modes have reproducible latency, domain-slot accuracy, WER, resource and failure results; unsupported modes are not presented as measured.
- [ ] **Given** revising partial transcripts, **When** the sandbox receives them, **Then** no question is submitted and no filter, preference or evidence value is committed.
- [ ] **Given** final speech for a question, filter, personal default or input value, **When** Phase 3 evaluates it, **Then** the correct route, context, editable preview and required human confirmation are demonstrated or the missing adapter is explicitly scoped out.
- [ ] **Given** ambiguous units, candidate identity, language, filter/policy intent or self-correction, **When** interpretation occurs, **Then** clarification/correction is required and no silent substitution or write occurs.
- [ ] **Given** denied permission, silence, timeout, unavailable models or changed context, **When** voice fails, **Then** typed/manual input remains usable, existing drafts remain intact and no mutation occurs.
- [ ] **Given** completed evidence, **When** Phase 4 closes, **Then** the team receives a go, conditional-go or no-go decision per outcome/mode, an explicit fallback and a bounded implementation proposal.

## Phase Plans And Effort

| # | Phase | Size | Status |
| --- | --- | --- | --- |
| 1 | [Requirements, platforms and sources](plan/phase-1-requirements-sources.md) | S | 🧊 Icebox (remaining gates deferred) |
| 2 | [ASR benchmark and streaming comparison](plan/phase-2-asr-benchmark.md) | M | 🧊 Icebox (synthetic slices complete; remaining study deferred) |
| 3 | [Safe workflow integration spike](plan/phase-3-workflow-spike.md) | M | 🧊 Icebox (not run; not approved) |
| 4 | [Feasibility decision and handover](plan/phase-4-decision-handover.md) | S | ✅ Done (negative decision and artifact handover) |

Proposed cap: 16-24 engineering hours across 2-3 working days, excluding hardware provisioning, participant availability and approvals. These are planning estimates, not commitments. Allow at most two hours to unblock installation per candidate before recording a blocker; do not spend the hackathon porting a macOS daemon. Re-scope at each gate rather than promise all models/modes.

## Permission Gates

| Gate | Required approval/evidence |
| --- | --- |
| Start research execution | Named researcher, demo machine/OS/browser, language(s), time cap and approved download/network policy |
| Collect or retain recordings | Participant consent, synthetic/redacted content, access controls, retention/deletion date and data approver |
| Run benchmark dependencies/services | Selected runtime/licenses, hardware access and any hosted-audio route/cost approved; isolated environment, no app dependency churn |
| Start Phase 3 | Passing baseline, reviewed action/confirmation contract and explicit sandbox-spike approval; disposable store and browser profile |
| Implement product feature | Separate user authorization for a bounded slice, accepted targets and implementation plan; passing research alone is not permission |

Local ASR does not mean the whole workflow is local: existing Ask/filter interpretation can send transcripts and context to the configured LLM. Confirm that route and retention before promising privacy. Default to no retained raw audio or transcripts in app logs; collect research audio only under the explicit exception above.

## Deliverables And Completion

Create actual results only when execution is authorized: dated source/capability register, approved utterance manifest and labels, machine/version manifest, per-run metrics/failure log, workflow safety evidence, and a decision report beside this task. Do not create empty evidence files or mark vendor claims as passing tests.

- [ ] Phase gates and actual owners recorded.
- [ ] Benchmarks distinguish reported capabilities, local measurements and unresolved claims.
- [ ] Questions, temporary criteria, saved preferences and value entry each have an outcome and scope decision.
- [ ] No change to scoring, active evidence/history, credentials or unrelated task packs.
- [ ] Demo fallback, licensing/privacy limits and next implementation slice are explicit.

Planning verification on 2026-10-01: repository/API/browser code and public sources inspected; document links and required sections checked after writing. No model installation, ASR benchmark, audio collection, browser spike or breeder validation has been performed. Research completion boxes remain unchecked.
