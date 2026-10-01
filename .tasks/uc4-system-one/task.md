# Evaluate System One models for UC4

Date: 2026-09-30. Status: complete (research and planning only).

Assess whether typed decision models can interpret compound breeding requests and route them to the existing UC4 evidence tools. Deliver a sourced recommendation and a reviewable future experiment; do not implement the integration.

System One models are a plausible request interpretation layer. Their UC4 accuracy, latency and cost benefits remain unmeasured. The recommendation is a small future OpenJev experiment against the current assistant baseline, with deterministic scoring and the separate human decision workflow preserved.

## Scope

All new artifacts for this task belong in `.tasks/uc4-system-one/`. Reference repository evidence without copying datasets. No application or public API changes, dependencies, model downloads, training, infrastructure installation, or live-model evaluation are included. The implementation steps in [plan.md](plan.md) are future work, not completed work.

## Deliverables and completion criteria

- [x] [research.md](research.md): dated public-source register and capability comparison, with source claims separated from repository findings and proposals.
- [x] Both everyday and technical example requests, with ten typed questions and expected answers explicitly identified as untested evaluation labels.
- [x] Repository evidence for the worked trial comparison, inferred thresholds, rationale omission, lab limitations and existing tool/agent boundaries.
- [x] [plan.md](plan.md): integration sequence, internal adapter contract, dependencies, fallback behavior and evaluation acceptance criteria.
- [x] Evaluation design covers paraphrases, compound requests, negation, ambiguous identifiers, missing evidence and unsupported requests; separates tuning from held-out evaluation.
- [x] Future regression gates require agreement with all 72 supplied trial verdicts and no automatic decision recording.
- [x] Verify cited local paths and document structure; review factual claims against linked sources; confirm this task adds only the three Markdown documents.

## Verification record

Public sources and relevant repository files were read on 2026-09-30. Documentation checks cover local link targets, the ten expected-label rows, required deliverables, and whitespace. Existing application tests and model benchmarks were not run for this documentation-only change. The 72/72 result is an existing repository finding and a future regression requirement, not a new measurement from this task.
