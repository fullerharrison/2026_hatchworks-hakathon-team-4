> **Superseded historical guide.** See the [current candidate analysis guide](README.md). This document records the v2 demo and earlier analysis context.

# UC4: R&D Data Source Unification

**Current implementation:** [app run instructions](../../app/README.md) and [runtime architecture](../../app/ARCHITECTURE.md). This guide's source inventory and scoring examples describe **v2**, the chosen demo snapshot. Its original MVP section is historical build guidance, not a claim that no app exists. The [historical v3 briefing](../../analysis/uc4_eda/v3/report_v3.html) is a separate analysis with different schemas and explicitly inferred GUID alignment. See [review evidence](../../.tasks/uc4-demo-review/task.md).


**Status:** Build guide, not an implemented assistant. The [official brief, p. 5][brief] defines the breeder persona, success criteria and scope; the [participant handbook][handbook] governs judging and submission. On 2026-09-29 the UC4 SME sent a **v2 archive** of seven synthetic CSVs that includes pre-configured trial recommendations ([SME answer][sme]). It supersedes the [kickoff archive][data-v1]. **Proposal** marks our design choice; **inferred** marks a rule we read from the data, not one the SME stated. A human breeder makes the final advancement decision.

## The problem, in everyday language

A breeder deciding whether a candidate line should advance has to piece together field-trial results, lab results, genomics, operations and pedigree information from separate sources. The brief describes a senior breeder who works mainly with spreadsheets and paper and wants one place to ask questions, see a red/amber/green recommendation and understand its reasons. The current fragmentation and repeated entry are described as roughly doubling the breeding cycle length; that is a problem statement, **not** a measured improvement a prototype can claim. The requested demo must let the breeder challenge and override a flagged recommendation and retain a log of that override. [Brief, p. 5][brief]

**Worked example (real rows from the v2 archive, inferred rule):**

- **SYN-TR-0003 → PASS (green).** Yield 10.79 t/ha, moisture 16.8%, disease 3.3, GBV mean 106.8, resistant lines 70%. Every criterion is met.
- **SYN-TR-0037 → HOLD (amber).** The rationale reads "yield meets threshold; moisture meets threshold; disease score acceptable; genomic value favourable". Only 30% of its lines are resistant, below the 50% the rule needs, and the rationale never says so. The assistant must name this reason.
- **SYN-TR-0001 → FAIL (red).** Yield 10.05 t/ha passes, but disease 7.7 exceeds the knockout at 7.

A breeder could still choose to advance a line from SYN-TR-0037 and record why. The thresholds are inferred and must be confirmed with the SME.

### Terms for a newcomer

| Term | Meaning here |
| --- | --- |
| Candidate line / germplasm | Breeding material under consideration (`MATERIAL_GUID`, `MATERIAL_ID` such as `SYN-MZ-00001`). v2 germplasm holds IDs only: no pedigree, stage or past decision. |
| Trial | A field trial of ten lines at one site and year. **The supplied recommendation is per trial**, not per line. |
| Trial recommendation | `TRIAL_RECOMMENDATION` in `trial_recommendations_synthetic.csv`: PASS, HOLD or FAIL, with a text rationale and `RULE_VERSION = SYNTH_V1`. |
| Knockout | A single failing value that forces FAIL regardless of the rest: low yield or high disease. |
| Genomic breeding value (GBV) | A per-line genomic prediction of breeding merit (`genomics_synthetic.csv`); the trial file uses its mean per trial. |
| Red / amber / green | Our proposed display of FAIL / HOLD / PASS. It is a review priority, not an automatic advance/reject decision. |
| Override | A breeder's explicit final choice and reason, saved alongside the original recommendation and its evidence. |
| MCP | The brief suggests a data-unification (MCP) layer; a particular protocol is an implementation option, not a substitute for reliable joins and traceable answers. |

## What is in the archive

The v2 archive has seven CSVs, all **synthetic** (`IS_SYNTHETIC` or a `SYNTHETIC` remark on every row). Row counts, headers and values were measured in memory from the zip. Five member names carry a ` 1` download suffix, which the loader ignores. Treat the archive as read-only.

| Entry | Rows | Relevant fields and role |
| --- | ---: | --- |
| `trial_recommendations_synthetic.csv` **(new)** | 72 | `TRIAL_GUID`, `TRIAL_ID`, `YIELD_T_HA`, `MOISTURE_PCT`, `DISEASE_SCORE`, `PLANT_HEIGHT_CM`, `FLOWERING_DAYS`, `GENOMIC_BREEDING_VALUE_MEAN`, `RESISTANT_MATERIAL_PCT`, `GENOMICS_QC_PASS_PCT`, `TRIAL_RECOMMENDATION`, `RECOMMENDATION_RATIONALE`, `RULE_VERSION`: the scoring output, one verdict per trial. |
| `genomics_synthetic.csv` **(new)** | 150 | `MATERIAL_GUID`, four `MARKER_*` calls, `GENOMIC_BREEDING_VALUE` (76.6 to 128.3), `QC_CALL_RATE_PCT`, `QC_STATUS_LID` (all PASS): one sample per line. |
| `trial_synthetic 1.csv` | 72 | `TRIAL_GUID`, `TRIAL_ID`, `STATUS_LID` (all COMPLETE), `START_YEAR` (24 per year, 2024 to 2026), `LOCATION_GUID` (6). Most of the 56 columns are empty. |
| `observation_synthetic 1.csv` | 720 | `ATTACHED_TO_FIELD_ENTITY_ID` (= trial), `GID` (= line), `FIELD_ID` (= location), `REPLICATION_NO`: **links only, no trait values, units or quality flags.** |
| `operations_synthetic 1.csv` | 216 | `TRIAL_GUID`, `MATERIAL_GUID`, `OPERATION_TYPE_LID` (PLANTING 68, IRRIGATION 73, HARVEST 75), `OPERATION_STATUS_LID`, `OPERATION_DATE`, `PLOT_NO`. No quantities. |
| `lab_observations_synthetic 1.csv` | 360 | `MATERIAL_GUID`, `TRAIT_GUID` (4), `NUMBER_VALUE`: 2 to 3 results for each of the 150 lines. No trial key, dates or trait names. |
| `germplasm_pedigree_synthetic 1.csv` | 150 | `MATERIAL_GUID`, `MATERIAL_ID`, `LINE_GUID`, `CROP_GUID` (1): IDs only. |

**What v2 removed.** v1 had pedigree and parents, breeding stage, an `ADVANCEMENT_DECISION` per line, field trait values with quality flags, and lab dates. None of these remain. Guidance built on them (the `ADVANCEMENT_DECISION` baseline, "16 lines without lab data", "81 REVIEW rows", "one trait per line") no longer applies. The v1 profile is kept in [`analysis/uc4_eda/v1/`][profile-v1].

## Scoring rule SYNTH_V1

The SME pre-configured the scoring ([answer][sme]), but the file states **outcomes, not cut-points**. The rule below is inferred. It is the simplest fixed-threshold rule that reproduces **72 of 72** supplied verdicts ([`rules.py`][rules], tested in `test_rules.py`).

1. **FAIL** if `YIELD_T_HA` < 7 **or** `DISEASE_SCORE` > 7 (knockouts).
2. **PASS** if yield ≥ 9, moisture ≤ 22%, disease ≤ 5, GBV mean ≥ ~102 **and** resistant lines ≥ 50%.
3. **HOLD** otherwise.

- **Comparison basis:** a fixed target per trait. No check variety or trial average is needed to explain any verdict.
- **Precision:** the data only brackets each cut-point, for example yield target 8.90 to 9.14 and GBV 101.0 to 103.4. The v2 list is in `analysis/uc4_eda/v2/tables/rule_intervals.csv`.
- **Unused values:** plant height, days to flowering and `GENOMICS_QC_PASS_PCT` (always 100) never change a verdict.
- **Hidden criterion:** the rationale names four criteria but not resistant %. Four trials whose rationale reads "all met" are HOLD.
- **Why trials land where they do:** FAIL comes from disease alone in 16 trials, yield alone in 10, and both in 4. HOLD trials most often miss moisture (16) or resistant % (16).

## Data profile: what the archive supports

The [UC4 v2 data profile][profile] (a self-contained HTML page) was generated by [`analysis/uc4_eda/uc4_eda.py`][eda], which reads the zip without extracting it. Findings are measured on the synthetic data, not confirmed with the domain owner.

- **Clean keys.** Every trial, line and location GUID resolves across the seven files. Each trial links to exactly 10 lines; each line to 4 or 5 trials.
- **Trial-level evidence only.** Yield, moisture, disease, height and flowering exist only as one value per trial. No line-level measurement backs them.
- **Aggregates do not follow the recorded links.** The trial GBV mean matches the observation-linked lines in 0 of 72 trials, and resistant % in 10 of 72. Grouping lines in consecutive blocks of ten by ID reproduces all 72. No file records that mapping. Until the SME explains it, show line-level genomics as context, not as the evidence behind the trial verdict.
- **Operations ignore the trial calendar.** Every operation is dated April to September 2026. 144 of 216 fall outside their trial's start year. All 114 PLANNED operations are dated before the extract (26 Sep 2026), and 60 of 72 COMPLETE trials still have planned work.
- **Lab results are uninformative.** Four unnamed traits, each spread evenly over roughly 1 to 20, with no dates or units. The recommendation does not use them.
- **Crop.** Line IDs still read `SYN-MZ` (maize), but the trial descriptions no longer say maize. The briefs describe a vegetable-seed business.

The full consistency-check list, with one example per rule, is in `analysis/uc4_eda/v2/tables/chronology_checks.csv`. Surface these contradictions as consistency flags; they do not change the deterministic SYNTH_V1 verdict. Do not treat inconsistent dates as proof of completed activity.

The archived v2 profile above is historical output. The v3 outputs are now archived in `analysis/uc4_eda/v3/`; the current generator produces the replacement candidate analysis. Follow the [current guide](README.md#reproduce-and-follow-up) for regeneration and tests. Keep analysis and app tests separate.

## Proposed hackathon MVP

**Historical proposal (now implemented as documented in app/ARCHITECTURE.md):** Build a read-only, local snapshot of the seven files, a trial-and-line evidence view, and a question interface over a fixed set of supported questions. A deterministic engine applies SYNTH_V1 and must reproduce the supplied verdicts. A language model only interprets a question or phrases an answer **from retrieved records and rule outputs**. The breeder can inspect evidence, challenge a result, and record a separate human decision. Do not connect to live research systems. [Brief, p. 5][brief]

1. **Confirm the decision contract.** Send the [follow-up questions][sme-followups]: exact cut-points, the unstated resistant criterion, trial vs line as the unit of decision, and which lines make up each trial. Until answered, label thresholds "inferred from SYNTH_V1".
2. **Build a traceable evidence model.** Key trials on `TRIAL_GUID` and lines on `MATERIAL_GUID`. Link them through the observation file (`ATTACHED_TO_FIELD_ENTITY_ID`, `GID`). Attach genomics and lab to lines. Keep each source file, row ID and original value in the evidence shown to the breeder.
3. **Score with the engine, not the file.** Recompute PASS/HOLD/FAIL from the trial values and **show the numbers against each threshold**, because the supplied rationale gives none. The supplied `TRIAL_RECOMMENDATION` is the **baseline**: the engine must match it for all 72 trials, and any mismatch is a bug.
4. **Serve a limited set of useful questions.** For example: "Why is trial SYN-TR-0037 on hold?" or "Which trials fail on disease alone?" Resolve the ID to one trial or line and return compact results with file and row references. When several records match, ask the breeder to choose; when evidence is absent or contradictory, say so.
5. **Explain triage and capture a human override.** Show a colour plus a one-line reason, every criterion with its value and threshold (including resistant %), the rule version, the source rows, and any consistency flags. Keep the recommendation immutable; separately record breeder identity (or demo alias), decision, reason and timestamp.

**Suggested minimal screen:** trial or line selector and question box; the trial's criteria table (value, threshold, met or not); the ten linked lines with genomics and lab values; a colour and short explanation; and an explicit "Record decision" action with reason. Large readable text and visible units suit the stated breeder persona.

## Validate the demo

- Run the engine against all 72 supplied verdicts and show 72 of 72 agree. Hand-check a few trials against the CSV rows.
- Exercise one explained PASS, one HOLD on the unstated resistant criterion (SYN-TR-0037), one FAIL on each knockout, a trial with contradictory operation dates, an ambiguous ID, and an attempted override without a reason. Confirm no recommendation becomes a final decision on its own and that an override leaves an auditable before/after record.
- Demo one natural-language question, show the cited rows behind a flagged trial, let the breeder challenge the reason and record an override. Compare evidence retrieval with manual cross-file lookup (time and correctness); do not claim a shorter breeding cycle.
- The [handbook rubric, pp. 2-3][rubric] asks for actionable value, an end-to-end live demo checked against a baseline, and AI use across the lifecycle. The [presentation rules, p. 3][demo] allow seven minutes plus five minutes for Q&A and require a working demo, deck, one-pager and repo link within an hour afterward.

**Optional later:** approved trait and lab ontologies, line-level measurements once supplied, cross-trial comparisons, or a secured MCP service after the read-only evidence path works.

## Questions for the domain owner

Answered on 2026-09-29: the scoring logic and comparison basis ([SME answer][sme]). Still open:

- Are the inferred cut-points (yield 7 / 9 t/ha, disease 5 / 7, moisture 22%, GBV ~102, resistant ≥ 50%) right, and which bounds are inclusive?
- Should the rationale mention the resistant-material criterion?
- Is the trial the unit of decision? If the breeder decides per line, how does a trial verdict carry to each of its ten lines?
- Which lines make up each trial's aggregates: the observation links, or the consecutive blocks the genomics values imply?
- Does v2 fully replace the kickoff archive, and is the loss of `ADVANCEMENT_DECISION` and pedigree intended?
- What do the four lab `TRAIT_GUID`s mean, and should lab results affect scoring?
- Should the demo present maize (the `SYN-MZ` IDs) or a stand-in for a vegetable crop?
- Are the synthetic files cleared for a shared demo repository? Is a real MCP interface required or merely an option?

The [brief, p. 5][brief] names Diganta Adhikari as the UC4 subject-matter expert. The scope boundary is firm: no live research-system connection, no autonomous advancement, and no verdict without its reasoning.

[brief]: ../../get_started/2026_Use_Case_Briefs.pdf#page=5
[handbook]: ../../get_started/2026_Participant_Handbook.pdf
[rubric]: ../../get_started/2026_Participant_Handbook.pdf#page=2
[demo]: ../../get_started/2026_Participant_Handbook.pdf#page=3
[data-v1]: ../../get_started/UC4%20-%20R%26D%20Data%20Source%20Unification-20260928T220200Z-1-001.zip
[sme]: ../../team/SME_ANSWERS.md
[sme-followups]: ../../team/SME_ANSWERS.md#follow-up-questions-to-send
[profile]: ../../analysis/uc4_eda/v2/report_v2.html
[profile-v1]: ../../analysis/uc4_eda/v1/report_v1.html
[rules]: ../../analysis/uc4_eda/rules.py
[eda]: ../../analysis/uc4_eda/uc4_eda.py
