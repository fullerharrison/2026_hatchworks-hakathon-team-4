# Use-case guide verification

**Date:** 2026-09-28. **Method:** read-only. The four zips in `get_started/` were opened in memory with `zipfile` + `openpyxl`/`pandas`. The briefs, handbook and kickoff deck were read page by page. UC3 checks printed counts only, never cell values, because the sheet contains PII. Scripts: `data.py` (structure) and `detail.py` (values), kept in the session scratchpad and not committed.

**Legend:** ✅ verified · ⚠️ partly true, imprecise or incomplete · ❌ wrong · ➖ not verifiable from the supplied files

## Summary

| Guide | ✅ | ⚠️ | ❌ | Most important finding |
|---|---:|---:|---:|---|
| Root README | 3 | 0 | 0 | — |
| Shared handbook claims (all four guides) | 4 | 3 | 0 | Rubric and AI-mandate page cites are off by one; the presentation deck is left out of the submission list |
| UC1 | 9 | 3 | 1 | `Excel SAP data` `Hours`/`Capacity` are packaging-only formulas that evaluate blank. **There is no conditioning capacity** |
| UC2 | 9 | 3 | 0 | The `Sales` sheet is a **year-by-year series from 2024 to 2030** (SharePoint list `Syngenta5YrsSales`), which the guide missed |
| UC3 | 10 | 2 | 0 | **Real** possible-duplicate candidates exist (6 rows share Name + Street), so synthetic duplicates aren't needed |
| UC4 | 11 | 2 | 0 | `EXCLUDE_FROM_ANALYSIS` and `PEGASYS_PURGED` are never set, so the "excluded/purged" demo case can't happen with the supplied data |

No claim changes a guide's scope or conclusions. The ❌ and ⚠️ items are imprecise or incomplete descriptions of the data.

## Root `README.md`

| Claim | Verdict | Evidence |
|---|---|---|
| Hackathon runs Sep 28 – Oct 2, 2026 | ✅ | Handbook p. 1 |
| The handbook is the authority for rules; the briefs are the authority for scope | ✅ | Handbook p. 1 calls itself the "single source of truth"; p. 2 says to "treat the briefs document as the source of truth" for use-case detail |
| Four use cases; teams pick one | ✅ | Handbook p. 1 ("no own-proposal backup") |

## Handbook claims repeated across the guides

| Claim | Verdict | Evidence |
|---|---|---|
| The rubric values business value, a live end-to-end result checked against a baseline, AI across the lifecycle, and the demo | ✅ | Handbook pp. 2-3; kickoff p. 5 |
| Rubric cited as "p. 2" (UC1 l.63, UC2, UC4 l.53) | ⚠️ | Business Value and Technical are on p. 2; **GenDD and Demo are on p. 3** |
| Generative AI is mandatory across requirements, stories, prototyping, code and docs, cited as "pp. 1-2" (UC1 l.63) | ⚠️ | This is on **p. 2 only** |
| Teams must disclose the tools they used | ✅ | Handbook p. 4 FAQ ("Disclose what you used in your presentation") |
| 7 min presentation + 5 min Q&A (p. 3) | ✅ | Handbook p. 3; kickoff p. 5 |
| Submit within 1 h: working demo, one-pager, repo link (p. 3) | ⚠️ | True as far as it goes, but the list is **incomplete**: the handbook p. 4 FAQ and kickoff p. 5 also require the **presentation deck** |
| Syngenta receives the code | ✅ | Handbook p. 3 (implied by the guides' "handover" wording) |

## UC1: Plant Capacity Utilization

| Claim | Verdict | Evidence |
|---|---|---|
| The archive holds one workbook, `Pasco LSV and SSV Conditioning sheets and data.xlsx` | ✅ | Zip listing |
| Brief p. 2: persona, success criteria, supplementing data allowed, "not optimal schedule", scope boundaries, SMEs Brumley and Young | ✅ | Brief p. 2 |
| `Schedule Updating!B3:B16` describes the SAP COISPI export of active non-complete orders, excludes completed/locked orders, and ends with a Smartsheet Data Shuttle refresh | ✅ | Text runs B3 to B16 exactly |
| The tabs the guide lists exist | ✅ | 16 tabs present |
| The guide's tab list is complete | ⚠️ | It omits `SAP Coispi report` and `Data Shuttle interface image`, which contain only images |
| All schedule tabs contain a `Run Order` variant (l.30) | ⚠️ | `Colorsort Schedule` has **no `Run Order` column** (it has `Equipment ID` instead). Every other schedule tab has one |
| `LSV Conditioning Logs` fields | ✅ | All listed fields present (1,899 rows, dates 2023-06-26 to 2026-09-24, no negative hours) |
| `SSV Conditioning Logs` fields, including `Species` and defect comments | ✅ | 2,230 rows |
| `LSV Pass_Fail Log` fields | ✅ | 3,142 rows: 2,293 Pass, **812 Fail**, 37 blank |
| `Excel SAP data` fields, including `Hours`/`Capacity`, "semantics unverified" (l.34) | ❌ | Both columns are formulas with **no cached values**. `Hours` looks up an external `'[1]Packaging Rates'` workbook that isn't supplied, and `Capacity` returns `8`, but both apply only when `Department` is `SSV/LSV TREATPACK`. Every row is `SSV Conditioning` (82), `LSV Conditioning` (77) or `Seed Health` (43), so both evaluate to `""`. They define packaging capacity, not conditioning capacity, and are out of UC1 scope. Every `PO Status` is `NEW` |
| `Large/Small Seed Conditioning!B2` hold only a heading, no machine-readable series | ✅ | One non-empty row per tab, plus 3 embedded images each |
| No customer-order table, availability calendar, changeover rules or line qualification | ✅ | No such tab or header; a keyword search found nothing |
| "Excel dates must be interpreted as dates, not serials" | ⚠️ | This caution doesn't apply: every date cell is stored as a real `datetime` |

**Not covered by the guide:** `Line 1 Schedule` is 97% `COMPLETE` (464 of 476 rows), so the schedules are mostly history, not an open queue. `Equipment ID` values in the logs (for example `Line 1 Gravity`, `Colorsorter Line 2`, `Handpick`, `VMEK`) don't map one-to-one onto the schedule tab names. The brief (p. 2) mentions packaging logs and a UC1 reference sketch; neither is in the archive.

## UC2: Market Intelligence and Demand Capture

| Claim | Verdict | Evidence |
|---|---|---|
| The archive has seven entries: 6 xlsx + `UI sketch.jpeg` | ✅ | Zip listing |
| Brief p. 3: persona, MVP, "implausibility flag", scope boundaries, synthetic sales, SMEs | ✅ | Brief p. 3 |
| `MV360 Market` headers (`Year`, `Market Qty (KS)`, price and segment fields) | ✅ | 3,553 rows. `Year` runs 2024 to **2030**, so it includes projections. There is 1 `Territory` value and 34 species |
| `MV360 Sales` headers, including `Created`/`Modified` and no demand month | ✅ | `Created` spans Feb to Apr 2026 only |
| "Headers do not identify … an annual plan" (l.28) | ⚠️ | The `Title` column holds the **year** (2024 to 2030, about 385 rows each), and the SharePoint path is `Syngenta5YrsSales`. This is almost certainly an **annual 5-year sales series by species**, which could supply the baseline annual quantity. Confirm with the SME |
| `Grower Potential` headers, including the source spelling `Hecatres Info.` | ✅ | 8,998 rows. `SP Season` is always `ES_VE2026`. `UoM` is mixed (`Country Land UoM`, `Hectares`, `Kilo Seeds`), which supports the unit warning |
| `Competitors`: year columns 2024 to 2030 plus matching % columns | ✅ | Present |
| `Prod Hierarchy` tabs listed as `prod hierarchy`, `5yrSales`, `MAPS`, `MAPS (2)` (l.31) | ⚠️ | Incomplete: the workbook also has an `examples` tab |
| `5yrSales` headers | ✅ | Present, including trailing spaces in `Species Adjusted ` and `Mega Segment ` |
| `Spain Geo` has `City` and `Pincode` tabs with street/postal fields | ✅ | Present |
| No monthly-demand workbook or month column | ✅ | Keyword search over every header found none |
| The UI sketch exists | ✅ | Present; its content wasn't evaluated |
| Market and sales can be aligned at crop level | ⚠️ | The guide calls this unverified; all 34 species appear in both files, so a species-level join looks feasible |

## UC3: Commercial Data Integrity Agent

| Claim | Verdict | Evidence |
|---|---|---|
| Brief p. 4 marks the use case "provisional"; teams pick data quality or hierarchy; no writes to master data; SME Zagade | ✅ | Brief p. 4 |
| One workbook with one tab, `Existing VE and MDG TR Accounts` | ✅ | Zip and workbook |
| Row 1 blank, header on row 2 | ✅ | First non-empty row is 2 |
| 545 non-empty data rows, 24 columns | ✅ | 545 × 24 (plus one trailing blank row) |
| Column labels as listed, with whitespace trimmed | ✅ | Raw labels include `Account Sub-Type\n`, `Phone `, ` Veg Owner Name`; the double space in `Proposed  Veg Owner FND ID` is confirmed |
| `MDMi BPID`, `FNDG ID`, `Salesforce Id` have no blanks and no repeats | ✅ | 545 unique values each |
| All four owner fields are populated | ✅ | 0 blanks. 27 distinct owners, consistent across the three owner-name/ID fields |
| The sheet contains contact and address PII | ✅ | `Phone`, `Email`, `Street`, `Address (Postal Code)` |
| "Segment checks by account class" (l.25) | ⚠️ | `Account category` has **one value** (`Transactional Account`), as do `Sales Organization`, `Country` and `SFDC BU`. Checks that vary by class have little to work with |
| MVP may need a synthetic possible-duplicate pair (l.48) | ⚠️ | Not needed. **6 rows share a normalized Name + Street** and 7 names repeat, so real review candidates exist |
| Brief pp. 1 and 4 mention duplicates, missing attributes and orphans | ✅ | Brief p. 1 (no territory owner) and p. 4 |

**Findings the guide missed:** `Email` is blank in 276 rows, `Phone` in 27, and `Veg Segmentation Type (SFDC)` in 540. These are genuine missing-attribute findings, subject to the steward confirming which fields are required.

## UC4: R&D Data Source Unification

| Claim | Verdict | Evidence |
|---|---|---|
| Brief p. 5: persona, four mock sources, RAG + override logged, "plus the pass/fail scoring logic", human in the loop, SME Adhikari | ✅ | Brief p. 5 |
| The archive has five synthetic CSVs | ✅ | `IS_SYNTHETIC=TRUE` in observations and operations |
| Row counts 72 / 720 / 216 / 360 / 150 | ✅ | Exact |
| Listed headers exist in each file | ✅ | All present (the files are wider: 56, 20, 18, 16 and 64 columns) |
| The lab table has no trial key | ✅ | No `TRIAL_GUID`; keyed by `MATERIAL_GUID` + `TRAIT_GUID` |
| `OBSERVATION_UOM` records units | ✅ | One unit per trait (t/ha, %, cm, days, score) |
| A trait dictionary is needed to interpret lab results | ✅ | 4 opaque `TRAIT_GUID`s. `ALPHA_VALUE` holds `EVENT_A/B/C` and `NONE` |
| No scoring-rules file, even though the brief promises one | ✅ | Only the 5 CSVs |
| Four sources in the brief vs. five CSVs in the archive | ✅ | Brief p. 5 vs. zip |
| `MATERIAL_GUID` and `TRIAL_GUID` work as join keys | ✅ | **Zero orphans**: every observation, operation and lab `MATERIAL_GUID` exists in germplasm, and every `TRIAL_GUID` exists in trials. No duplicate observations at trial/material/plot/rep/trait; all values numeric |
| The existing `ADVANCEMENT_DECISION` needs a defined meaning | ✅ | Values: HOLD 58, DISCARD 57, ADVANCE 35 |
| Validation should cover `EXCLUDE_FROM_ANALYSIS` and `PEGASYS_PURGED`; the demo should include "excluded or purged data" (l.42, l.51) | ⚠️ | The columns exist, but every value is `0`/`FALSE`. That demo case needs a synthetic edit |
| The problem statement says the cycle roughly doubles; this is not a measured gain | ✅ | Brief p. 1 and p. 5 |

**Useful for the demo, not in the guide:** 16 of the 150 materials have **no lab results**, giving natural "amber: evidence incomplete" cases. `QUALITY_FLAG_LID` has 81 `REVIEW` and 15 `REJECTED` rows. `ADVANCEMENT_DECISION` could serve as a **baseline** to compare the RAG output against.

### UC4 v2 archive (2026-09-29)

The UC4 SME answered the missing-rules question with a new archive, `RE__Hatchworks_Hackathon_-_4th_Use_Case.zip` ([SME answer](../team/SME_ANSWERS.md)). It replaces all five tables and adds two. The v1 claims above are re-checked against it here. Evidence: the [v2 profile](../analysis/uc4_eda/report.html) and its tests.

| v1 claim | Verdict on v2 | Evidence |
|---|---|---|
| No scoring-rules file | ❌ Superseded | `trial_recommendations_synthetic.csv`: PASS 7 / HOLD 35 / FAIL 30 per trial, `RULE_VERSION` SYNTH_V1. Outcomes only; an inferred fixed-threshold rule reproduces 72 of 72 |
| Five CSVs; rows 72 / 720 / 216 / 360 / 150 | ⚠️ | Same five row counts, plus genomics (150) and recommendations (72). New GUIDs and contents |
| `MATERIAL_GUID` and `TRIAL_GUID` join with zero orphans | ✅ | Still true across all seven files |
| The lab table has no trial key | ✅ | Still true. Lab now also has no dates and no `ALPHA_VALUE` |
| Observations carry values in one unit per trait | ❌ | v2 observations are trial-line links only: no values, units or flags |
| 16 materials without lab; 81 REVIEW / 15 REJECTED | ❌ | Every line has 2-3 lab rows; no quality flags exist |
| `ADVANCEMENT_DECISION` as a baseline | ❌ | Column is empty in v2. The supplied trial verdicts are the new baseline |
| `EXCLUDE_FROM_ANALYSIS` / `PEGASYS_PURGED` never set | ✅ | Still never set |
| Data is internally consistent enough to demo | ⚠️ | Trial genomics aggregates match the observation-linked lines in 0 of 72 trials; 144 of 216 operations fall outside their trial's year |

**UC4 remains the recommendation.** The main gap (scoring logic) is closed, and the supplied verdicts give a built-in regression test. The new risks are that verdicts are per trial rather than per line, and that trial numbers cannot be traced to specific lines.

## What this means for the use-case recommendation

| Earlier statement | Status after verification |
|---|---|
| UC1 would need "4+ synthetic tables" | Still true. The only capacity columns are packaging formulas and there are no customer orders or changeover rules. However, the historical data (4,100+ log rows, 812 failed tests) is **richer** than I implied |
| UC2's core inputs are missing | Mostly still true: no monthly history. An **annual 2024-2030 sales series** does exist, which softens the gap somewhat |
| UC3: "you'd mostly be demoing errors you injected yourself" | **Wrong.** There are real duplicate candidates and substantial missing attributes. The single-valued category fields do limit rule variety |
| UC4 has clean keys, and scoring rules are the only real gap | **Confirmed and strengthened**: zero orphans, consistent units, a built-in baseline (`ADVANCEMENT_DECISION`) and natural missing-lab cases |

**UC4 remains the recommendation.** One more fact from the handbook (p. 2) and kickoff deck (p. 7): **Diganta Adhikari, the UC4 SME, is also a Syngenta judge**, which is relevant to the Syngenta Choice Award and the "Syngenta Pull" bonus. **UC3 moves up** as a close second.

## README corrections (applied 2026-09-28)

The verdict tables above record the state of the guides **before** these corrections. The following changes have since been made to `uc1`-`uc4/README.md`:

1. All guides: cite the rubric as pp. 2-3 and the AI mandate as p. 2, and add the presentation deck to the submission list.
2. UC1: `Hours`/`Capacity` are packaging-only formulas (blank for every conditioning row, and dependent on an unsupplied `Packaging Rates` workbook); `Colorsort Schedule` has no `Run Order`; list the two image-only tabs; dates are already stored as datetimes.
3. UC2: identify `Sales` `Title` as the year (5-year sales list); add the `examples` tab; note that all 34 species appear in both market and sales.
4. UC3: category and organization fields are single-valued; real Name + Street duplicates and missing-contact findings exist.
5. UC4: exclusion and purge flags are never set; note the 16 materials without lab data and the `ADVANCEMENT_DECISION` baseline.
