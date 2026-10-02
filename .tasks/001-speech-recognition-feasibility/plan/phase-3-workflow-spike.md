# Phase 3 - Safe Workflow Integration Spike

Parent: [001-speech-recognition-feasibility](../task.md) | Status: 🧊 Icebox | Size: **M** | Proposed timebox: 5-8 hours

Deferred without execution by the user's stop decision, 2026-10-01. No recognizer
passed the evaluated gates, no sandbox approval was given, and no product/voice
integration was performed. See [final disposition](../results/closure-2026-10-01.md).
The proposed work below is retained as reference, not an active implementation plan.

## Goal And Entry Gate

Test whether the shortlisted recognizer can serve useful breeder actions without bypassing UC4 validation and human control. Entry requires [Phase 2](phase-2-asr-benchmark.md) evidence and explicit sandbox-spike permission. Use a disposable snapshot/history database and isolated browser profile. Do not alter team evidence, saved preferences or candidate scoring policy.

## Integration Hypothesis And First Check

Use speech as an input adapter, not a decision maker: capture -> ASR draft -> editable final transcript -> selected action -> existing validator -> human confirmation. Start with read-only Ask because it offers the smallest end-to-end slice. Partial ASR events never submit Ask or call a mutation path.

First replay "seventy" -> "seventeen" partial replacements and Cancel. Compare network requests, list state, form drafts, local storage and disposable history before/after. Then submit corrected final text through the existing typed workflow. Stop and repair this boundary if interim/canceled text changes anything; do not proceed to write-capable demonstrations.

## Work Plan

1. Choose either browser-local recognition or browser capture to an approved ASR sidecar from Phase 2. Keep heavy inference off the UI thread and FastAPI request loop. Never require a microphone physically connected to the server for a remote breeder browser.
2. Define a minimal session contract: session/utterance ID, sequence number, replaceable transcript, partial/final/error state and optional timestamps. Reject out-of-order, duplicate and previous-session events. Cap utterance duration, payload size and queued audio; define cancel/timeout and stop/flush behavior.
3. For server streaming, verify WebSocket versus bounded chunk HTTP, origin/auth/session checks, backpressure and session-isolated decoder caches. For browser-local inference, verify worker/WASM/thread requirements and model asset caching. No public unauthenticated audio upload service is part of the spike.
4. Capture with explicit user permission. Normalize actual device input to the chosen model's required mono/sample format with a proven audio pipeline; test 44.1/48 kHz microphones and chunk-boundary resampling. MediaRecorder WebM/Opus chunks are not necessarily independent WAV files; use a supported decoder/container strategy or PCM capture, not extension renaming.
5. Complete the four bounded outcome slices below. Keep action choice explicit rather than assume a general natural-language command router exists. If an adapter is absent or outside the spike approval, record a gap and a separate implementation estimate instead of faking an end-to-end success.
6. Reuse existing API/browser tests where appropriate, adding only tests for the approved speech boundary. Validate before proceeding from one outcome slice to the next. Keep live ASR/LLM evidence distinct from deterministic replay tests.
7. Compare voice with the current typed/manual workflow on the same tasks, recording correct completion, corrections, elapsed time, failed attempts and participant feedback. At least three consenting representative users is exploratory usability evidence, not proof of general adoption.

## Bounded Outcome Slices

| Slice | Behavior to test | Safety/persistence contract |
| --- | --- | --- |
| Ask | Final transcript placed in existing Ask input; explicit submit; selected candidate/revision and cited evidence preserved | No Ask per word/chunk; model timeout retains editable text; separately measure ASR, Ask and total latency |
| Current criteria | Final transcript to `/filters/interpret`, editable proposal to `/filters/validate`, explicit Apply | Typed constraints remain authoritative; strict/ambiguous requests clarify; revalidate stale context; note existing remember-view persistence |
| Personal defaults | Propose allowlisted name/location/channel or a confirmed remember-view preference | New adapter only under approval; exact before/after and browser-only scope shown; no scoring thresholds/weights persisted |
| Input values | Dictate into an explicitly chosen supported form field, including an approved enrichment draft field | Deterministic number/unit validation; selected candidate/source row visible; existing Submit/Review/Preview/Activate confirmations remain distinct |

Do not collapse "input a value" into "activate an evidence correction". Form population can be feasible even when voice-driven submission is deliberately excluded. No new MCP write tools, general DOM automation or unrestricted model-generated endpoint calls.

## Focused Behavioral Checks

- [ ] **Given** a partial threshold that is revised, **When** events arrive, **Then** only draft text changes and no Ask, filter application, preference save or write occurs.
- [ ] **Given** remembering the view is enabled, **When** a voice proposal is previewed or canceled, **Then** saved filters/selection remain unchanged; explicit Apply follows existing persistence semantics.
- [ ] **Given** a final grounded question, **When** the breeder selects Ask, **Then** one request uses the intended candidate/revision and citations remain inspectable.
- [ ] **Given** a personal-default request, **When** the breeder reviews it, **Then** the exact browser-local scope is visible and only explicit confirmation can save allowlisted fields.
- [ ] **Given** a dictated decimal and unit, **When** the breeder edits and submits the form, **Then** validation uses the corrected displayed value, not the original ASR hypothesis.
- [ ] **Given** candidate/revision/field context changes, **When** an old transcript is submitted, **Then** stale work is blocked or explicitly revalidated for the new context.
- [ ] **Given** "make ninety percent my green rule" or a mixed filter/write request, **When** interpretation runs, **Then** the unsupported change clarifies and the policy remains unchanged.
- [ ] **Given** Cancel, Stop, permission denial, disconnect, tab closure or model timeout, **When** cleanup finishes, **Then** capture stops, late results are ignored and typed/manual drafts remain usable.
- [ ] **Given** silence, unrelated background speech or instructions embedded in retrieved notes, **When** processing occurs, **Then** no action bypasses explicit confirmation or the allowed action schema.
- [ ] **Given** two simultaneous sessions, **When** audio/transcripts interleave, **Then** candidates, decoder state and transcript events do not cross sessions.

Numbers, units and candidate identity must be inspected even with high ASR confidence. Model proposals are untrusted input; validation and existing approval boundaries remain authoritative. Speech itself cannot authenticate the actor.

## Usability And Evidence

Verify actual listening, loading, partial, final, correction, error and canceled states on the approved desktop browser; include a mobile viewport check if mobile is in scope. Microphone controls require accessible names and keyboard operation. No interface mockup or product UI is created by this planning document.

Measure voice-versus-typed outcomes separately for questions, filters, defaults and value entry. Proposed usability gate: at least 90% correct task completion with no more than one correction per successful task; confirm this target in Phase 1. Do not claim time savings unless counterbalanced same-task measurements support them. Record whether non-technical users understand temporary versus saved changes.

## Deliverable And Exit Check

A small sandbox demonstration, actual behavior-test evidence, redacted event/network/write traces, workflow/latency results and the adapter gap list. Require zero unconfirmed mutations in all executed safety cases; one violation blocks any write-capable recommendation until repaired and retested.

Continue to [Phase 4](phase-4-decision-handover.md) even if the result is negative. A successful spike is research evidence, not permission to merge a product feature.
