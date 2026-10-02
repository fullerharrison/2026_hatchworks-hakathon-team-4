# Phase 4 - Feasibility Decision And Handover

Parent: [001-speech-recognition-feasibility](../task.md) | Status: ✅ Done | Size: **S** | Proposed timebox: 3-4 hours

Closed with a negative scoped decision, 2026-10-01:
[final decision and archive](../results/closure-2026-10-01.md). The user chose to
retain artifacts and discontinue the pursuit. Outcome/mode decisions, tested
configuration, unrun gates, typed/manual fallback and post-commit cleanup are
documented there. No positive implementation scope, breeder endorsement or full
research completion is claimed. The original decision method below is historical.

## Goal And Entry Gate

Give the hackathon team an evidence-based decision and an implementable next slice. Entry requires the actual completed/blocked outcomes from [Phase 2](phase-2-asr-benchmark.md) and [Phase 3](phase-3-workflow-spike.md). A no-go or narrower result is valid; unavailable hardware and missing approvals must remain visible.

## Decision Method

1. Apply hard gates first: permitted license/data handling, runnable demo platform, resource envelope, correct context/validation and zero unconfirmed mutations. Do not average these failures away using an accuracy score.
2. Compare survivors by held-out domain-slot accuracy, latency, real-time sustainability, usability, packaging/startup burden and deployment cost. Use paired clips and show per-outcome/condition denominators. Explain hardware/runtime differences and uncertainty rather than declare a universal best model.
3. Decide independently for live interim transcription, buffered interim transcription and utterance fallback. Then decide for questions, current filters, saved defaults and value entry. A partial go is acceptable: for example, question/filter dictation can proceed while persistent preferences require another adapter.
4. Separate pretrained-model feasibility from downstream intent capability. If speech is recognized but a settings request is rejected by the current interpreter, scope a settings adapter or defer it; do not conclude the recognizer failed or change the filter contract silently.
5. Present the minimum useful implementation slice, permission request, owner proposal, dependency list, verification gates and rough effort based on the spike. No automatic policy updates or new database profile schema without a separate approved task.

## Required Decision Report

Write a dated report beside the parent task when evidence exists. It must contain:

- Selected exact model/checkpoint/runtime/precision/hardware, and alternatives rejected with evidence.
- A compact result matrix: supported/blocked modes, first partial/final p50/p95, domain-slot and intent accuracy, WER by condition, peak resources, cold load, install/startup burden and cost.
- Source-versus-measurement distinction, sample counts, failure examples, unrun gates and remaining unknowns.
- Outcome decision for Ask, current criteria, browser-local defaults and numeric/text field entry; distinguish dictation, proposal and committed action.
- Approved processing/retention boundaries, licenses/attribution, dependency redistribution and downstream LLM data flow.
- Browser/native/service placement, transport and typed/manual fallback; required packaging changes and reproducible run/test instructions for the chosen configuration.
- A breeder/SME review summary with actual participants/roles and limitations, without invented endorsement.
- Proposed implementation scope and effort, not a retrospective claim that a voice feature is already delivered.

## Go / Conditional-Go / No-Go

| Decision | Required evidence | Next action |
| --- | --- | --- |
| Go for a bounded voice slice | Target hardware and accepted accuracy/latency gates pass; controls/validation safe; data/license approvals recorded | Request explicit product implementation permission for the named slice |
| Conditional go | Utterance fallback passes but interim mode fails, or questions/filters pass while settings/value adapters remain gaps | Offer the passing subset with precise limitations and gated follow-up work |
| No-go for this hackathon | No approved runnable configuration, unacceptable numeric/entity errors, unsafe behavior, excess provisioning/porting cost or missing data approval | Keep current typed/manual workflows; record the blocker and what evidence would justify revisiting |

Do not label a model "Windows ready" because its weights load elsewhere. Do not label the full workflow "offline/private" when Ask or interpretation uses a remote configured LLM. Do not present uploaded-file/token-streamer output as proven live word-by-word audio recognition.

## Demo And Handover Plan

If approved for implementation, propose a 60-90-second voice segment within the existing team demo: ask one grounded question, inspect a citation, dictate one selection criterion, correct a deliberate ambiguity, and explicitly Apply. Add a personal-default or value-entry example only if that exact outcome was verified and fits the slot. Source evidence remains transparently synthetic/provisional.

Rehearse on the actual demo machine/browser/microphone with model assets cached and a documented cold-start path. Keep typed/manual input immediately available if recognition, microphone permission, network or LLM fails. Do not misrepresent a recording or cached transcript as live recognition. Record actual rehearsal latency and failures.

Suggested first implementation order after permission: read-only question dictation; current-filter dictation with preview; active-field dictation; then separately approved saved-default proposals. Choose between interim display and utterance-only capture using the measured result, not aesthetics.

## Exit Criteria

- [ ] **Given** benchmark and spike evidence, **When** the report is reviewed, **Then** every requested outcome and streaming mode has a go/conditional-go/no-go result or an explicit unrun blocker.
- [ ] **Given** a recommended implementation slice, **When** handover is complete, **Then** its owners, scope, dependencies, approvals, effort, tests and fallback are explicit.
- [ ] **Given** unresolved safety, privacy or license issues, **When** the decision is published, **Then** the affected slice is blocked rather than described as pilot-ready.
- [ ] **Given** an authorized research corpus, **When** research ends, **Then** retained data follows the agreed deletion/access policy and evidence contains no secrets.
- [ ] **Given** a positive research decision, **When** the task closes, **Then** no production implementation is claimed or started without separate authorization.

Update phase statuses only against real completed evidence. Research completion is not model certification, biological validation or product delivery.
