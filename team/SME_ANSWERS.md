# UC4 SME answers

Answers from the UC4 subject-matter expert, Diganta ("Dig") Adhikari, with the date received. Numbers in the 2026-09-29 entry were measured in the [v2 data profile](../analysis/uc4_eda/v2/report_v2.html); numbers in the 2026-09-30 entry in the current [v3 data profile](../analysis/uc4_eda/report.html) (`analysis/uc4_eda/`). **Inferred** marks our reading of the data, not something the SME stated.

## 2026-09-29: scoring logic and comparison basis

**Question** (Carlos Diego Gomes, 29 Sep, cc Jim Shilo, Harrison Fuller, Matheus Carvalho): the brief lists pass/fail scoring logic, but the archive had only five mock tables. (1) Which trait decides the call, which traits are knockouts, and what separates red, amber and green? (2) Is a candidate judged against a check variety, the trial average, or a fixed target per breeding goal?

**Answer** (Dig, same day, by email):

- Participants were originally meant to define their own red/amber/green rules. Because many participants lack a breeding background, the SME team has **pre-configured the scoring logic and comparison criteria** in the attached file.
- The file was emailed because Dig has no upload access to the Google Drive folder yet. The Hatchworks team has been asked to update the shared files for everyone.
- Dig asked us to confirm whether the file answers both questions.

**What was attached:** `get_started/RE__Hatchworks_Hackathon_-_4th_Use_Case.zip`. It is a **complete v2 dataset**, not only a rule file: seven CSVs, with the four original tables regenerated under new GUIDs and slimmer contents, plus two new files.

| File | Rows | What it holds |
| --- | ---: | --- |
| `trial_recommendations_synthetic.csv` (new) | 72 | One row per trial: seven trial-level values, `TRIAL_RECOMMENDATION` (PASS 7, HOLD 35, FAIL 30), a text `RECOMMENDATION_RATIONALE` and `RULE_VERSION = SYNTH_V1` |
| `genomics_synthetic.csv` (new) | 150 | One genotyped sample per line: four marker calls, `GENOMIC_BREEDING_VALUE`, QC (all PASS) |
| `trial`, `observation`, `operations`, `lab`, `germplasm` (regenerated) | 72, 720, 216, 360, 150 | Same row counts as v1, different content. See the [UC4 guide](../use-cases/uc4/README.md#what-is-in-the-archive) |

## What the file answers

The file gives **outcomes and reasons in words, not thresholds**. We reverse-engineered the rule from the 72 outcomes. One set of fixed cut-points reproduces **all 72** (test: `analysis/uc4_eda/test_rules.py`).

| Step | Inferred rule (SYNTH_V1) | Data allows the cut-point anywhere in |
| --- | --- | --- |
| 1. Knockout → **FAIL** | `YIELD_T_HA` < 7 | 6.72 to 7.13 |
| 1. Knockout → **FAIL** | `DISEASE_SCORE` > 7 | 7.0 to 7.2 |
| 2. All five met → **PASS** | `YIELD_T_HA` ≥ 9 | 8.90 to 9.14 |
| | `MOISTURE_PCT` ≤ 22 | 21.8 to 22.1 |
| | `DISEASE_SCORE` ≤ 5 | 4.9 to 5.2 |
| | `GENOMIC_BREEDING_VALUE_MEAN` ≥ ~102 | 101.0 to 103.4 |
| | `RESISTANT_MATERIAL_PCT` ≥ 50 | 30 to 50 |
| 3. Otherwise → **HOLD** | | |

- **Q1, deciding traits and knockouts:** answered by inference. Yield and disease are knockouts. PASS needs all five criteria. `PLANT_HEIGHT_CM`, `FLOWERING_DAYS` and `GENOMICS_QC_PASS_PCT` (always 100) never change an outcome.
- **Q1, colours:** the file uses PASS / HOLD / FAIL, not red / amber / green. Mapping PASS → green, HOLD → amber, FAIL → red is **our proposal**.
- **Q2, comparison basis:** a **fixed target** per trait. Fixed thresholds explain every outcome, so no check variety or trial average is needed. There is one breeding goal, so "per breeding goal" cannot be tested.

## What the file does not answer, or changes

1. **Exact cut-points and inequality direction.** Only the brackets above are known.
2. **A criterion the rationale never mentions.** Resistant % gates PASS, but the rationale names only yield, moisture, disease and genomic value. Four trials (SYN-TR-0037, 0038, 0046, 0052) read "all four met" and are HOLD.
3. **The grain is the trial, not the line.** Verdicts are per trial. The brief's persona decides on *lines*, so the demo must explain how a trial verdict applies to the ten lines in it.
4. **Trial values do not trace back to lines.** v2 observations carry no trait values. Yield, moisture and disease therefore exist only as trial aggregates. The genomics aggregates match none of the 72 trials through the observation links. They match all 72 when trial *k* takes the ten lines `SYN-MZ` block ((*k* − 1) mod 15), a mapping no file records.
5. **v1 content is gone.** Pedigree, parents, breeding stage and `ADVANCEMENT_DECISION` (the v1 baseline), trait values with quality flags, and lab dates are all absent. The v1 profile is kept in [`analysis/uc4_eda/v1/`](../analysis/uc4_eda/v1/report_v1.html).

## Follow-up questions (to send)

1. Can you confirm the cut-points (yield 7 / 9 t/ha, disease 5 / 7, moisture 22%, GBV ~102, resistant ≥ 50%) and whether each bound is inclusive?
2. Should the rationale mention the resistant-material criterion, or is its omission intended?
3. Is the trial the unit the breeder decides on? If lines are, how does a trial verdict carry to each line?
4. Which lines make up each trial's aggregates: the observation links, or the ten consecutive lines the genomics values imply?
5. Does v2 replace the kickoff archive entirely? Is the loss of `ADVANCEMENT_DECISION` and pedigree intended?
6. What do the four lab `TRAIT_GUID`s mean, and should lab results affect the recommendation?

## 2026-09-30: corrected archive (v3)

**Message** (Dig, 30 Sep, to all): "few attributes were reported to be not interconnected in the batch I sent yesterday, here is a corrected one which will be loaded to the google drive too, sending you while you wait for those to be updated by HW team."

**What was attached:** `get_started/RE__Hatchworks_Hackathon_-_4th_Use_Case_09-30-2026.zip`, seven CSVs with the same names and row counts as v2. The EDA reads it by exact name; the app stays on v2 until it is migrated.

**What changed** (full table: [`tables/version_diff.csv`](../analysis/uc4_eda/tables/version_diff.csv)):

- **Five files were regenerated** under new GUIDs and now link to each other: plots, operations and lab resolve to lines and trials, and parents resolve to lines (all 100%).
- **Line content is back.** Pedigree, parents, breeding stage, generation and `ADVANCEMENT_DECISION` (ADVANCE 35, HOLD 58, DISCARD 57) are filled. Observations are now per-plot trait values with unit, date, replicate and quality flag (624 ACCEPTED, 81 REVIEW, 15 REJECTED). Lab results are dated; 16 lines have none. These match the v1 counts the [UC4 guide](../use-cases/uc4/README.md) recorded.
- **Two files were resent unchanged:** `genomics_synthetic.csv` and `trial_recommendations_synthetic.csv` are byte-identical to v2. Their keys therefore point at v2 records: genomics lines resolve 0/150, recommendation trial GUIDs 0/72. Recommendations join by `TRIAL_ID` (72/72). Genomics joins only by the last GUID block, which is **inferred** and positional.

**What still does not reconcile:**

1. Trial trait values are not the mean of the trial's plots: 354 of 360 trial × trait pairs differ.
2. Trial GBV mean differs from the observed lines in 71 of 72 trials. The v2 block-of-10 mapping no longer reproduces any.
3. 47 of 72 trials with a verdict are PLANNED or ACTIVE in the trial file, not COMPLETE.
4. A line's `ADVANCEMENT_DECISION` does not follow its trials' verdicts: ADVANCE lines are 23% of lines in PASS trials and 23% in FAIL trials.
5. 148 of 216 operations fall outside their trial's start year; quantity units vary within an operation type. Plot observations are all in the right year.
6. One lab trait (`...04`) is categorical: `EVENT_A/B/C` or `NONE` in `ALPHA_VALUE`.

The inferred SYNTH_V1 rule still reproduces 72/72, as it must with an unchanged recommendation file.

## Follow-up questions (30 Sep, to send)

1. Were `genomics_synthetic.csv` and `trial_recommendations_synthetic.csv` meant to be regenerated with the other five? If so, can you resend them keyed to the corrected lines and trials?
2. How is a trial's value computed from its plots: which quality flags and replicates count?
3. How should a line's `ADVANCEMENT_DECISION` relate to the verdicts of the trials it was in?
4. Should a PLANNED or ACTIVE trial carry a verdict?
5. What do lab trait `...04`'s `EVENT_*` values mean, and the operation quantity units?
