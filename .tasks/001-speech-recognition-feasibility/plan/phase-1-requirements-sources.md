# Phase 1 - Requirements, Platforms And Sources

Parent: [001-speech-recognition-feasibility](../task.md) | Status: 🧊 Icebox | Size: **S** | Proposed timebox: 3-4 hours

Archived by the user's stop decision, 2026-10-01. Source/preflight evidence is
retained; remaining owners, representative-corpus, governance and platform gates
are deferred, not passed. See [final disposition](../results/closure-2026-10-01.md).
The work plan below is historical and is not an instruction to continue.

## Goal And Entry Gate

Agree the actual breeder workflow and supported deployment envelope before downloading or selecting a model. Entry requires permission for research execution and a named researcher. Recording, hosted audio and runtime installs have separate approvals; desk research alone grants none of them.

Preparation started on 2026-10-01 under the task-contained implementation request:
[offline tooling](../README.md), [machine inventory](../results/machine-2026-10-01.json)
and [source/capability findings](../results/phase-1-2026-10-01.md). Accountable owners,
runtime/data approvals, target requirements and the evaluation corpus remain open.
No model installation, audio collection, ASR benchmark or product change was performed.

## Work Plan

1. Record the demo machine: Windows version, CPU architecture/cores, RAM, available GPU/VRAM and drivers, Python version, Edge/Chrome version, microphones, network and disk budget. Include mobile only if explicitly selected for the demonstration. Do not assume the developer machine is the breeder's deployment target.
2. Confirm primary language, accents and noise environment with a breeder/SME; English is a provisional first test because the existing filter interpreter accepts English only. Multilingual ASR does not make the downstream interpreter multilingual. Record whether explicit language selection is acceptable.
3. Review the [existing voice/NL scope](../../uc4-breeder-usability/05-voice-nl-input.md), [API](../../../app/API.md), [preference behavior](../../../app/src/uc4_mcp/static/preferences.js) and [filter interpreter](../../../app/src/uc4_mcp/filter_intent.py). Define question, current-filter, saved-default and active-field dictation routes. List unavailable personal scoring-profile functionality separately.
4. Pin exact checkpoints, model hashes/revisions, runtime versions and documentation commit/release for Nemotron, Parakeet CLI and Moonshine. Complete the capability matrix below. Inspect Parakeet's session protocol/source before classifying interim behavior; ordinary `listen` is an utterance-end baseline.
5. Verify code, weight, VAD and redistributed-asset licenses independently. Record attribution/redistribution requirements and exceptions; verify that the chosen model/runtime pair is usable under project policy. Do not infer license terms from the product name.
6. Compare browser-local WASM versus browser capture to a Python/native sidecar versus an approved hosted/GPU service. Identify network, asset download, packaging, cross-origin, threading and dependency risks. Explicitly test/document secure-context microphone requirements: localhost is different from a plain-HTTP LAN address.
7. Agree the corpus, latency/accuracy targets, consent/retention, allowed endpoints and the safe confirmation contract. Write findings with source date, short paraphrase, link and confidence/evidence type. No unsupported benchmark claim becomes an acceptance result.

## Capability Matrix To Complete

For each model/runtime configuration, record:

| Dimension | Required evidence |
| --- | --- |
| Recognition | Exact language coverage/checkpoint, sample rate/channels, punctuation, numeric rendering, timestamps/confidence availability |
| Streaming | Incremental/cache API or buffered redecoding, partial replacement/final events, endpoint/VAD ownership, supported chunk/context sizes |
| Platform | Windows wheel/native build or browser/WASM path, CPU/GPU providers, dependencies and maintenance/release status |
| Resources | Weight/download size, expected runtime RAM/VRAM, cold start; published benchmark hardware clearly identified |
| Integration | Browser audio input versus host microphone, event/backpressure interface, cancellation and concurrent-session isolation |
| Governance | Code/weights/assets license, local versus external processing, telemetry, transcript/audio retention and redistribution |

Use "documented", "locally verified", "inferred" or "unknown" for each cell. Published results cannot fill a locally measured field. If a candidate needs an unapproved host or unsupported OS, preserve that blocker rather than substitute another runtime silently.

## Proposed Evaluation Set

Prepare 60 distinct labeled utterances: 15 each for questions, current criteria, personal defaults and value entry. At least 20 include ambiguity, negation, self-correction, unsupported actions or wrong units. Use actual current schema and synthetic/redacted candidate references; do not import production breeder evidence.

Recruit at least three consenting speakers with relevant accents. Balance utterances across speakers and record each in quiet and representative background noise, producing at least 120 paired-condition clips. Each speaker must cover all four outcomes. Preserve speaker/condition identifiers without real names. TTS clips may aid engineering smoke tests but cannot substitute for breeder/accent validation.

Split phrase families into tuning and held-out sets before runtime tuning; alternate phrasings of the same phrase family stay in the same split. Labels include spoken reference, intent, candidate/field, comparator, numeric value, unit, correction and expected clarification. Keep raw spoken-reference labels separate from canonical numeric/intent labels.

## Safety And Privacy Contract

- Explicit microphone Start/Stop and a visible listening state; no background capture or implicit permission reuse as consent.
- Interim text is revisable draft content only. A spoken "save", "apply" or "yes" is not authorization in the minimum slice.
- Save-default requests must say what persists and where. Remember-view behavior can persist applied filters; previewing never calls it.
- Dictation targets an explicitly selected field/form, not arbitrary DOM fields or a model-selected write endpoint.
- Do not log raw audio, full transcripts, names or sensitive source values by default. Approved research files need restricted access and a deletion date; cancellation/closure releases capture buffers.
- Audit the downstream LLM route separately. No credentials or environment-file contents enter evidence.

## Deliverable And Exit Check

A dated requirements/capability/source record, named owners/approvers, approved corpus specification and a hardware/runtime shortlist. Record unresolved items and rejected alternatives with reasons.

- [ ] **Given** all three candidates, **When** source review ends, **Then** each has pinned evidence or a documented platform/license blocker.
- [ ] **Given** breeder tasks, **When** the action contract is reviewed, **Then** filters, preference persistence and policy edits cannot be confused.
- [ ] **Given** the target platform and language, **When** Phase 2 is authorized, **Then** runnable configurations, data policy and proposed gates are accepted explicitly.

Continue to [Phase 2](phase-2-asr-benchmark.md) only after that approval. No product code is changed in this phase.
