# Proposed UC4 System One integration and evaluation

Date: 2026-09-30. Status: future work; specification only.

The evidence and recommendation are in [research.md](research.md). All steps below are proposals. This documentation task changes no application code, public API, dependency or dataset and runs no models.

## Integration sequence and dependencies

| Step | Proposed work | Dependencies | Acceptance criteria |
| --- | --- | --- | --- |
| 1. Define fixtures and routing contract | Start with the two requests and ten questions in research.md. Define option rubrics, unsupported cases, explicit exclusions and plain-language presentation. | Existing [evaluation cases](../../app/evals/questions.json) and reviewed expected labels. | Each fixture has expected intents, IDs, retrieval needs, clarification behavior and forbidden side effects. Values-only requests are not silently expanded into threshold requests. |
| 2. Resolve identifiers in code | Extract exact literal trial/line identifiers, preserving original spans; validate using existing resolution tools. Retain fragments as unresolved input, never invent a full ID. | `find_trial`, `find_line` and their `ok` / `many` / `none` envelopes in [server.py](../../app/src/uc4_mcp/server.py). | Only validated IDs enter dynamic choices. `many` asks for a selection; `none` explains the missing match. Missing primary/comparator IDs block dependent retrieval. |
| 3. Classify through an internal adapter | Supply request context and fixed typed questions; batch independent questions. Start with the OpenJev candidate identified in research.md. | Steps 1-2; future environment with suitable hardware and a pinned candidate revision. | Results validate against option sets and question IDs. Questions never consume another answer from the same batch. Errors, unclear results and conflicting labels produce clarification or fallback. |
| 4. Plan read-only retrieval | Convert accepted intents to a bounded tool plan. Deduplicate identical reads within the request and reuse evidence already returned. | Step 3; existing MCP bridge and tool schemas. | Required evidence is fetched for every requested subtask; each unique read runs at most once unless a documented retry is needed. No write route is reachable from this planner. |
| 5. Build grounded explanations | Use existing deterministic scoring, omission fields and flags. Optional later semantic checks receive retrieved evidence. Render with templates or the existing grounded agent. | Step 4; [rules.py](../../app/src/uc4_mcp/rules.py) and [grounding.py](../../app/src/uc4_mcp/grounding.py). | Values, units, source references, threshold brackets and `SYNTH_V1 (inferred)` survive rendering. A model cannot change a verdict or assign lab evidence to a trial. |
| 6. Evaluate before enabling routing | Compare baseline and candidate on identical frozen cases, then review the quality/latency tradeoff. | Steps 1-5; frozen tuning/evaluation split and complete instrumentation. | All hard regression gates pass and comparative acceptance criteria below are met. Otherwise retain the existing agent. |

The insertion point is before tool selection in the existing [agent](../../app/src/uc4_mcp/agent.py)/[bridge](../../app/src/uc4_mcp/bridge.py) path. Resolving candidate identities may require preliminary read-only calls. Dependent trial or line retrieval waits for a resolved intent and entity; independent intent questions can share a batch.

## Proposed internal adapter contract

This is an internal specification, not a new endpoint or a vendor API compatibility claim.

| Direction | Fields | Meaning / validation |
| --- | --- | --- |
| Input | `request_id`, `request_text`, `context` | Original request, explicitly selected entities if any, presentation constraints and validated candidate IDs with original spans. Keep request interpretation separate from later evidence checks. |
| Input | `catalogue_version`, `questions[]` | Stable question ID, type (`choice` initially), instructions/rubric and allowed option IDs/labels. Every question supports `unclear`; `none` is distinct where appropriate. |
| Input | `deadline_ms` | Overall classification deadline; expiry triggers fallback, not a guessed answer. |
| Output | `status`, `answers[]` | `ok`, `invalid`, `unavailable` or `timeout`; each answer identifies its question, selected option and per-option distribution. A valid answer may still select `unclear`. |
| Output | `model_id`, `model_revision`, `adapter_version`, `catalogue_version` | Exact identity needed to reproduce an experiment; a missing immutable revision makes the run unsuitable for acceptance evidence. |
| Output | `timing_ms`, `error` | Total adapter time, queue/model components where available, and structured failure information. Do not claim unmeasured timing components. |

Reject missing/duplicate question IDs, unknown selections, malformed/non-finite probabilities or distributions that fail documented normalization tolerance. Preserve raw distributions in experiment traces. Apply abstention thresholds only after tuning on a separate split; distributions are not established UC4 confidence. A normalized answer can still be wrong.

Application composition enforces dependencies: a comparison needs two resolved roles; a trial-only question cannot route to a fabricated line verdict; explicit exclusions survive routing. If the fixed catalogue cannot represent a request faithfully, fall back to the current agent. For example, filters needed for an arbitrary `query_trials` request require separately validated typed fields or baseline handling, not guessed arguments from the ten example questions.

## Intent-to-evidence mapping

Existing tool behavior is documented in [server.py](../../app/src/uc4_mcp/server.py). Proposed routing:

| Accepted intent | Read plan | Composition |
| --- | --- | --- |
| Resolve trial or line | `find_trial` / `find_line` | Validate literal IDs; clarify ambiguity before dependent work. |
| Explain verdict, thresholds or rationale omission | `score_trial` | Use existing criterion values, brackets, supplied rationale and `rationale_omits`; no new model is needed to rediscover a deterministic omission. |
| Broader trial context / linked lines | `get_trial` | Reuse its recommendation and source rows when already sufficient; avoid an unnecessary second scoring read. |
| Compare two named trials | `score_trial` or `get_trial` for each validated trial | Present the two evidence records side by side. Any new arithmetic belongs in deterministic evidence code; the renderer must not invent calculated values. |
| Filter/list trials | `query_trials` | Use only validated supported filters; unsupported query semantics use the baseline or clarification. |
| Line or lab context | `find_line` / `get_line`; `get_trial` only if linked line IDs are needed | Retrieve relevant line evidence once per line. Preserve unnamed-trait and absent-trial-key limitations. |
| Provenance | References already returned by the above; `list_sources` when source descriptions are needed | Carry exact source-file/row references; no extra read merely to duplicate existing provenance. |
| Record a decision | No write call from routing | Direct the user to the existing explicit human decision workflow. Classification is never authorization. |

For the two worked prompts, the expected plan resolves both trials, retrieves each score once, explains HOLD versus PASS and the omitted resistance criterion, and assesses lab relevance from source limitations. If supporting lab rows are useful, fetch them through the linked line view and describe them only as line context. Do not retrieve all lab rows automatically or present them as a cause of either verdict.

Use a request-scoped cache keyed by tool name, canonical arguments and evidence snapshot identity. Preserve tool traces when reusing results. Do not introduce cross-request caching without a separate freshness design.

The separate human [decision API](../../app/src/uc4_mcp/api.py) and [decision log](../../app/src/uc4_mcp/decisions.py) remain outside the classifier, including when question 10 returns `record`. The example requests explicitly forbid recording. Unclear authorization is never resolved by increasing a model-confidence threshold.

## Future evaluation design

1. **Freeze evidence and labels.** Reference the current synthetic snapshot and deterministic scorer. Seed cases from the existing evaluation file and the two proposed fixtures. Have labels reviewed before model runs. Record acceptable equivalent tool plans, expected evidence coverage and expected clarification, rather than requiring one exact call order.
2. **Separate tuning and held-out evaluation.** Group related paraphrases and near-duplicate scenarios in the same split to prevent leakage. Use the tuning split for rubrics, thresholds and timeout choices. Freeze all settings before opening held-out results; do not tune SYNTH_V1 itself.
3. **Cover failures as well as happy paths.** Include everyday/technical paraphrases, compound requests, explicit and double negation, reversed subject/comparator order, multiple or ambiguous IDs, missing IDs, nonexistent records, missing evidence, unsupported capabilities, line-versus-trial confusion and explicit presentation constraints. Include injected instructions in request/evidence text and unavailable, timed-out or malformed adapter outputs.
4. **Run matched comparisons.** Baseline: current agent with its existing settings. Candidate: routing plus the same tools, evidence snapshot and explanation model/settings. Record candidate revision, hardware, batch/option counts, decoding settings, cache policy and cold/warm state. Include fallback requests in total latency and cost. Repeat timed runs under the same load; report sample counts and variability.
5. **Review quality and operating cost.** Assess labels and retrieval separately from final-answer completeness and grounding. Record tool calls, duplicate reads, input/output tokens, local runtime and hardware context; calculate cost only from documented experiment rates and boundaries. Do not turn vendor benchmarks into UC4 savings.

### Metrics and acceptance criteria

| Metric / gate | Definition and proposed acceptance |
| --- | --- |
| Routing accuracy | Fraction of cases with the correct intent/entity/tool plan, allowing equivalent sufficient read plans. Also report per-question accuracy and primary/comparator errors. Candidate must not regress against baseline on held-out routing accuracy. |
| Complete-request accuracy | Fraction satisfying every requested subtask and explicit exclusion with correct entities, grounded evidence and no unsupported claims. Report separately for compound requests. Candidate must not regress against baseline; an average of atomic scores is insufficient. |
| Clarification and fallback | Report clarification rate, unnecessary clarification on resolvable cases, missed clarification on ambiguous cases and fallback rate. All designated ambiguous-ID fixtures must clarify before dependent retrieval. Do not optimize raw clarification rate downward at the expense of correctness. |
| End-to-end latency | Request receipt to final answer, including extraction, classification, retrieval, rendering and fallback. Report p50/p95 plus classifier-only timing. Before runs, fix a numerical improvement target and maximum p95 regression budget based on the intended demo environment. Adoption requires meeting those frozen targets; no saving is assumed now. |
| Deterministic agreement | Existing regression checks and `baseline_check` must still match all 72 supplied trial verdicts, with no changes to SYNTH_V1 thresholds or scoring. |
| Human decisions | Zero automatic recorded decisions or overrides across every fixture, including explicit record requests, negations, injection cases and fallback paths. Inspect decision-log changes and reachable tools, not merely answer text. |
| Evidence integrity | All worked-case explanations retain criterion values, inferred thresholds and provenance; no trial-specific lab attribution. Missing evidence is stated as missing. Semantic review supplements existing grounding checks. |
| Reliability | Invalid outputs, unsupported intent and model outages reach clarification or the existing agent with the original request and constraints intact. No uncaught adapter failure or partial answer presented as complete. |

A small experiment can justify further investigation, not broad production accuracy claims. Report counts and uncertainty alongside percentages. If quality gates fail or timing gains are inconclusive, retain the baseline and document failure categories before considering another candidate or training.

## Documentation-task verification boundary

This task verifies source support, existing interfaces, local links and document completeness. Running the existing 72-trial regression, downloading a checkpoint, implementing this adapter, collecting held-out outputs and measuring latency are all future integration/evaluation work. None is claimed as completed here.
