# System One models for UC4: research

Reviewed: 2026-09-30. Scope: research and plans only; no model execution.

## Recommendation (proposal)

Yes, UC4 could benefit from a typed request interpretation and routing layer. Application code supplies bounded questions and options, resolves identifiers, retrieves evidence and computes verdicts. Templates or the existing grounded language-model agent explain the results. This is an architectural fit, not an established improvement in UC4 accuracy, latency or cost.

Specify a small future local experiment with `AlexWortega/openjev`, retaining the existing assistant as the baseline. Use NanoJev as an architectural reference. Do not train it or install experimental vLLM infrastructure as part of this task. The proposed evaluation and integration are in [plan.md](plan.md).

## Public-source register and comparison (source claims)

All five sources below were accessed on 2026-09-30. These are mutable pages, not pinned experiment dependencies. Reported capabilities and benchmarks belong to their authors; none of the reviewed sources establishes performance on these UC4 requests.

| Source | Verified claim / version context | Implication for UC4 (our assessment) |
| --- | --- | --- |
| [System One Models directory](https://systemonemodels.org/) | Describes typed decision models and identifies itself as independent of TypeSafe and model vendors. | Discovery source only; implementation claims below use primary sources. |
| [TypeSafe introduction](https://docs.typesafe.ai/introduction) | Describes Choice, Score and Noul outputs. Questions in a call are evaluated independently against the same state; the application decomposes complex questions and combines results. | Supports a fixed catalogue of atomic intent questions. Parallel evaluation does not resolve dependencies between answers. |
| [NanoJev repository](https://github.com/TianyuCodings/NanoJev) | Documents Qwen3-0.6B with decision heads, parallel questions and dynamic candidates. Its published evaluation covers Maze, Snake and two ViZDoom tasks. | Useful architecture, but game performance does not demonstrate breeding-request understanding. |
| [vLLM PR #57250](https://github.com/vllm-project/vllm/pull/57250) | Merged on 2026-09-22 as commit `1b3b88e`. Adds DiffusionGemma structured reads and a prototype example server for `/v1/systemone`; explicitly does not add a standard vLLM endpoint. | Experimental serving path, not a ready-made UC4 assistant. Merge status alone does not establish a supported production interface. |
| [AlexWortega/openjev model card](https://huggingface.co/AlexWortega/openjev) | Text entailment classifier. The card recommends `qwen3.5-4b-nli-v5` for typed decisions over supplied options and rubrics, with one forward pass per option. It discloses prompt-injection weaknesses. | First candidate for text-routing evaluation; measure option-count effects and do not treat probabilities as proven UC4 confidence or action authorization. |

The TypeSafe decomposition guidance supports the application pattern; it does not prove that every candidate shares the same inference cost or calibration. In particular, a batch of ten application questions must not be described as a single OpenJev forward pass. [TypeSafe introduction](https://docs.typesafe.ai/introduction), [OpenJev model card](https://huggingface.co/AlexWortega/openjev).

## Repository findings (existing implementation and evidence)

The [UC4 guide](../../use-cases/uc4/README.md) is framed as a v2 build guide. For present implementation behavior, use the code and tests below rather than its older implementation-status banner.

| Finding | Repository evidence |
| --- | --- |
| MCP exposes read-only resolution, trial and line retrieval, scoring, filtered queries and a baseline check. Resources include source metadata and the inferred rule. | [server.py](../../app/src/uc4_mcp/server.py), [store.py](../../app/src/uc4_mcp/store.py) |
| The current question agent selects tools through an MCP bridge; it handles ambiguous results and checks answers against retrieved citations, numbers and verdicts. These checks do not prove full semantic correctness. | [agent.py](../../app/src/uc4_mcp/agent.py), [bridge.py](../../app/src/uc4_mcp/bridge.py), [grounding.py](../../app/src/uc4_mcp/grounding.py) |
| SYNTH_V1 thresholds are inferred from supplied outcomes. Scoring and rationale-omission detection already exist in code. | [rules.py](../../app/src/uc4_mcp/rules.py), [rule tests](../../app/tests/test_rules.py) |
| A separate API route and decision log capture human decisions; recording is not an MCP question-agent tool. | [api.py](../../app/src/uc4_mcp/api.py), [decisions.py](../../app/src/uc4_mcp/decisions.py), [server.py](../../app/src/uc4_mcp/server.py) |
| Existing evaluations include explained HOLD/PASS requests and ambiguous IDs; the store test asserts 72 checked, 72 matched, no mismatches. | [questions.json](../../app/evals/questions.json), [test_store.py](../../app/tests/test_store.py) |

### What evidence says about the example trials

The guide reports SYN-TR-0037 as HOLD: resistant material is 30%, below the inferred 50% requirement. Its supplied rationale describes yield, moisture, disease and genomic value favorably but omits resistance. SYN-TR-0003 is PASS, with yield 10.79 t/ha, moisture 16.8%, disease score 3.3, GBV mean 106.8 and resistant material 70%. The server's worked-example test checks both verdicts and the omitted resistance field. [UC4 guide](../../use-cases/uc4/README.md), [test_server.py](../../app/tests/test_server.py).

The implemented inferred rule first returns FAIL for yield < 7 t/ha or disease > 7. Otherwise PASS requires yield >= 9 t/ha, moisture <= 22%, disease <= 5, GBV mean >= 102 and resistant material >= 50%; remaining cases are HOLD. Matching supplied outcomes does not uniquely establish the true thresholds. Preserve the code's inferred label and threshold brackets. [rules.py](../../app/src/uc4_mcp/rules.py).

Lab rows have no trial key and their traits are unnamed. Line retrieval can supply lab context, but those rows cannot establish a trial-specific explanation. Do not infer a trial association merely because a line appears in that trial. The agent already instructs against attaching lab results to trials. [UC4 guide](../../use-cases/uc4/README.md), [server.py](../../app/src/uc4_mcp/server.py), [agent.py](../../app/src/uc4_mcp/agent.py).

These are repository-supported application answers, not facts recoverable from the user's request alone. A deployed answer must retrieve the records and retain the source-file/row references returned by the evidence layer; this documentation does not invent row IDs.

## Equivalent evaluation requests (proposed fixtures)

**Everyday wording:**

> Explain in plain language why trial SYN-TR-0037 is amber. Compare it with green trial SYN-TR-0003, show the numbers and where they came from, and check whether the written reason leaves anything out. Include lab information if it helps. Don't record a decision.

**Technical wording:**

> For SYN-TR-0037, explain HOLD versus PASS for SYN-TR-0003. Return criterion values, SYNTH_V1 thresholds and provenance; assess rationale completeness and lab relevance. Use a plain-language summary. Read-only; no override.

### Ten atomic questions and expected answers

**These are expected labels for evaluation, not measured model outputs.** Code extracts literal IDs and validates candidates before populating option lists. Both example requests should produce the same labels. Questions and rubrics come from application templates; the decision model need not generate questions.

| # | Atomic question | Type / allowed answers | Expected answer for both requests |
| --- | --- | --- | --- |
| 1 | What entity type is being discussed? | Choice: trial / line / both / unclear | trial |
| 2 | Which mentioned trial is the primary subject? | Choice: extracted IDs / unclear | SYN-TR-0037 |
| 3 | Is a comparison requested? | Choice: yes / no / unclear | yes |
| 4 | Which mentioned trial is the comparator? | Choice: extracted IDs / none / unclear | SYN-TR-0003 |
| 5 | Does the user want the recommendation explained? | Choice: yes / no / unclear | yes |
| 6 | Does the user want criterion values and thresholds? | Choice: yes / no / unclear | yes |
| 7 | Does the user want source provenance? | Choice: yes / no / unclear | yes |
| 8 | Does the user want the supplied rationale checked for omissions? | Choice: yes / no / unclear | yes |
| 9 | How should lab evidence be handled? | Choice: assess relevance / retrieve without relevance assessment / omit / unclear | assess relevance |
| 10 | Is the user requesting a recorded decision? | Choice: record / explicitly do not record / unspecified / unclear | explicitly do not record |

For questions 2 and 4 in these examples, the dynamic ID choices are `SYN-TR-0037` and `SYN-TR-0003`, with the listed sentinel choices added. Application logic ignores a comparator when no comparison is requested and rejects contradictory or unresolved combinations. Both prompts explicitly request plain language: presentation follows that instruction, without inferring the user's technical ability.

Question 6 intentionally tests a combined output bundle. The everyday fixture's expected `yes` assumes that explaining a verdict and showing its numbers includes their thresholds. Its annotation rubric must state that convention. A future request asking for values but explicitly excluding thresholds must preserve that exclusion or fall back; these ten questions are not a complete grammar of all UC4 requests.

## Unresolved questions (future measurements)

- Does the candidate handle breeding vocabulary, negation, partial requests and multiple IDs as accurately as the existing agent?
- Does a routing stage reduce total latency or tool calls once classification, evidence retrieval, explanation and fallback costs are included?
- Are option distributions useful for abstention after separate tuning on UC4 examples?
- Can semantic checks add value beyond existing deterministic rationale checks without inventing evidence links?

No model output, UC4 confidence estimate, latency saving or cost saving was measured in this task.
