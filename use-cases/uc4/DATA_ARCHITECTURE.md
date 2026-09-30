# UC4 data architecture: R&D Data Source Unification

This page explains how the supplied UC4 data fits together, first in plain language (Part A) and then at column, key and pipeline level (Part B). Every number comes from the **v2 archive** the UC4 SME sent on 2026-09-29 ([SME answer][sme]; see [Part C](#part-c-evidence)). All seven files are **synthetic**. The target design is the **Proposal** in the [UC4 guide](README.md#proposed-hackathon-mvp). Colour legend: see [the index](../DATA_ARCHITECTURE.md#legend).

---

## Part A: For a novice

### The story in four sentences

A breeder wants to know whether plant lines tested together in a **field trial** should move forward. The SME has already scored every trial **pass, hold or fail** from its yield, moisture, disease and genomics results, but the file says only *that* a trial passed, not the numbers it had to beat. The tool recomputes each verdict with fixed thresholds, shows every value against its threshold, and links the trial to its ten plant lines, their genomics, lab tests and field operations. It shows a green, amber or red signal with its reasons, and the breeder makes the final call, which is recorded.

### Where the data goes

```mermaid
flowchart LR
    A["Plant lines"]:::supplied
    B["Field trials and their line lists"]:::supplied
    C["Genomics and lab tests"]:::supplied
    D["Field operations"]:::supplied
    R["SME verdict per trial: pass, hold, fail"]:::supplied
    E["Exact thresholds behind the verdict"]:::missing
    F["Tool gathers all evidence for a trial and its lines"]:::proposed
    G["Green, amber or red, with every number and reason"]:::proposed
    H["Breeder agrees or overrides"]:::human
    A --> F
    B --> F
    C --> F
    D --> F
    R --> G
    E -.-> G
    F --> G --> H
    classDef supplied fill:#d9f2d9,stroke:#2e7d32,color:#000
    classDef proposed fill:#fff4cc,stroke:#b8860b,color:#000
    classDef missing fill:#eeeeee,stroke:#888888,stroke-dasharray: 5 5,color:#000
    classDef human fill:#dbe9ff,stroke:#1f5fbf,color:#000
```

### What connects to what

```mermaid
flowchart TB
    P["Plant lines: 150"]:::supplied
    T["Field trials: 72"]:::supplied
    V["Trial verdicts: 72"]:::supplied
    O["Trial-line links: 720"]:::supplied
    G["Genomics: 150"]:::supplied
    L["Lab tests: 360"]:::supplied
    OP["Field operations: 216"]:::supplied
    DICT["Lab test dictionary"]:::missing
    MAP["Which lines the verdict numbers came from"]:::missing
    V -- "trial ID" --> T
    O -- "trial ID" --> T
    O -- "plant ID" --> P
    G -- "plant ID" --> P
    L -- "plant ID only, no trial" --> P
    OP -- "trial ID + plant ID" --> T
    MAP -.-> V
    DICT -.-> L
    classDef supplied fill:#d9f2d9,stroke:#2e7d32,color:#000
    classDef missing fill:#eeeeee,stroke:#888888,stroke-dasharray: 5 5,color:#000
```

**What to remember:** the IDs join perfectly, with no broken links. The verdict belongs to a **trial**, not a plant. Yield, moisture and disease exist only as one number per trial. The trial's genomics numbers do not match the plants the files link to it. So the tool can explain *why a trial* passed, but cannot yet prove which plants' results produced that verdict.

---

## Part B: For an expert

### Entity-relationship model (as supplied)

Relationship labels show the join key and the measured coverage.

```mermaid
erDiagram
    TRIAL ||--|| TRIAL_RECOMMENDATION : "TRIAL_GUID: 72 of 72"
    TRIAL ||--|{ OBSERVATION : "ATTACHED_TO_FIELD_ENTITY_ID: 10 lines per trial"
    GERMPLASM ||--|{ OBSERVATION : "GID: 4-5 trials per line"
    GERMPLASM ||--|| GENOMICS : "MATERIAL_GUID: 150 of 150"
    GERMPLASM ||--|{ LAB_OBSERVATION : "MATERIAL_GUID: 150 of 150, 2-3 each"
    GERMPLASM ||--|{ OPERATION : "MATERIAL_GUID"
    TRIAL ||--|{ OPERATION : "TRIAL_GUID: 3 per trial"
    GERMPLASM {
        guid MATERIAL_GUID PK "150 unique"
        string MATERIAL_ID "SYN-MZ-00001 to 00150"
        string STATUS_LID "ACT only"
        guid CROP_GUID "1 crop"
    }
    TRIAL {
        guid TRIAL_GUID PK "72 unique"
        string TRIAL_ID "SYN-TR-0001 to 0072"
        string STATUS_LID "COMPLETE only"
        int START_YEAR "24 each 2024-2026"
        guid LOCATION_GUID "6 locations"
    }
    TRIAL_RECOMMENDATION {
        guid TRIAL_GUID PK
        float YIELD_T_HA "5.52-13.45"
        float MOISTURE_PCT "13.2-26.5"
        float DISEASE_SCORE "1.1-8.4"
        float PLANT_HEIGHT_CM "not used by rule"
        int FLOWERING_DAYS "not used by rule"
        float GENOMIC_BREEDING_VALUE_MEAN "13 distinct values"
        float RESISTANT_MATERIAL_PCT "10-70"
        float GENOMICS_QC_PASS_PCT "always 100"
        string TRIAL_RECOMMENDATION "PASS 7, HOLD 35, FAIL 30"
        string RECOMMENDATION_RATIONALE "15 variants, no numbers"
        string RULE_VERSION "SYNTH_V1"
    }
    OBSERVATION {
        int ID PK
        guid ATTACHED_TO_FIELD_ENTITY_ID FK "= TRIAL_GUID"
        guid GID FK "= MATERIAL_GUID"
        guid FIELD_ID "= trial LOCATION_GUID"
        int REPLICATION_NO "1-3"
    }
    GENOMICS {
        guid GENOMIC_SAMPLE_GUID PK
        guid MATERIAL_GUID FK
        string MARKER_DISEASE_RESISTANCE "R 63, I 51, S 36"
        string MARKER_YIELD_POTENTIAL "3 levels"
        string MARKER_DROUGHT_TOLERANCE "3 levels"
        string MARKER_MATURITY "3 levels"
        float GENOMIC_BREEDING_VALUE "76.6-128.3"
        string QC_STATUS_LID "PASS only"
    }
    LAB_OBSERVATION {
        guid ROWGUID PK
        guid MATERIAL_GUID FK
        guid TRAIT_GUID "4 opaque GUIDs"
        float NUMBER_VALUE "about 1-20"
    }
    OPERATION {
        guid OPERATION_GUID PK
        guid TRIAL_GUID FK
        guid MATERIAL_GUID FK
        string OPERATION_TYPE_LID "PLANTING 68, IRRIGATION 73, HARVEST 75"
        string OPERATION_STATUS_LID "COMPLETED 102, PLANNED 114"
        date OPERATION_DATE "Apr-Sep 2026 only"
    }
```

**Key findings that shape the model**

| Finding | Consequence for the design |
| --- | --- |
| Zero orphans across all seven files; every GUID resolves. | Joins are safe. |
| The verdict grain is the **trial**: one PASS/HOLD/FAIL per trial, 10 lines per trial, 4-5 trials per line. | Score trials. A line inherits 4-5 trial verdicts; how to combine them is an SME question. |
| An inferred fixed-threshold rule reproduces **72 of 72** verdicts. Cut-points are bracketed only (e.g. yield target 8.90-9.14). | Implement it as a versioned engine ("SYNTH_V1, inferred"). Use the supplied verdict as the regression baseline. |
| The rationale omits the resistant-% criterion; 4 "all met" trials are HOLD. | The engine's explanation, not the supplied text, must be what the breeder sees. |
| Observations carry **no values**. Yield, moisture, disease, height and flowering exist only per trial. | No line-level field evidence can be shown. Say so rather than invent it. |
| Trial GBV mean matches the observation-linked lines in **0 of 72** trials, resistant % in 10 of 72. Consecutive blocks of 10 lines by ID reproduce all 72. | The trial-to-line link used for evidence differs from the one behind the numbers. Flag it on every trial view until the SME resolves it. |
| Operations: 144 of 216 outside their trial's start year; all 114 PLANNED already past; 60 of 72 COMPLETE trials still have planned work. | Show operations as context with a "dates inconsistent" flag; never use them as proof of what happened in the trial. |
| Lab: 4 unnamed traits, roughly uniform values, no dates; not used by the rule. | Show as unexplained line-level context. |
| v1's `ADVANCEMENT_DECISION`, pedigree, stage and quality flags are gone. | The v1 baseline and the "missing lab" / "REVIEW" amber cases no longer exist. |

### Target data architecture (proposal)

```mermaid
flowchart TB
    subgraph SRC["Sources: seven synthetic CSVs"]
        X1["trial, observation links, germplasm, genomics, lab, operations"]:::supplied
        X2["Trial recommendations SYNTH_V1"]:::supplied
        X3["Exact thresholds, lab dictionary, line mapping"]:::missing
    end
    subgraph ING["Ingest and validate"]
        N1["Typed load, GUID keys, source file and row id kept"]:::proposed
        N2["Checks: orphans, calendar, aggregate reconciliation"]:::proposed
        N3["Evidence store: trial view plus its lines"]:::proposed
    end
    subgraph CORE["Deterministic scoring"]
        S1["Knockouts: yield below 7, disease above 7"]:::proposed
        S2["PASS criteria: yield, moisture, disease, GBV, resistant pct"]:::proposed
        S3["RAG plus criterion table plus rule version"]:::proposed
        S4["Regression: 72 of 72 match supplied verdicts"]:::proposed
    end
    subgraph TOOLS["Read-only tool layer, MCP optional"]
        T1["find_trial and find_line"]:::proposed
        T2["get_evidence"]:::proposed
        T3["explain_score"]:::proposed
    end
    subgraph OUT["Ask, explain, decide"]
        O1["LLM answers from tool results with citations"]:::proposed
        O2["Evidence view: criteria, lines, flags"]:::proposed
        O3["Breeder agrees or overrides with reason"]:::human
        O4[("Override log: immutable recommendation plus decision")]:::proposed
    end
    X1 --> N1 --> N2 --> N3
    X2 --> N1
    N3 --> S1 --> S2 --> S3
    X3 -.-> S2
    X2 --> S4
    S3 --> S4
    N3 --> T1
    N3 --> T2
    S3 --> T3
    T1 --> O1
    T2 --> O1
    T3 --> O1
    O1 --> O2 --> O3 --> O4
    classDef supplied fill:#d9f2d9,stroke:#2e7d32,color:#000
    classDef proposed fill:#fff4cc,stroke:#b8860b,color:#000
    classDef missing fill:#eeeeee,stroke:#888888,stroke-dasharray: 5 5,color:#000
    classDef human fill:#dbe9ff,stroke:#1f5fbf,color:#000
```

### Headline interaction: ask, see the reasons, override

```mermaid
sequenceDiagram
    actor B as Breeder
    participant UI as Assistant UI
    participant LLM as Language model
    participant T as Read-only tools
    participant S as Scoring engine
    participant L as Override log
    B->>UI: Why is trial SYN-TR-0037 on hold?
    UI->>LLM: Question plus tool list
    LLM->>T: find_trial SYN-TR-0037
    alt Several matches
        T-->>UI: Ask the breeder to choose
    else One match
        T-->>LLM: TRIAL_GUID
    end
    LLM->>T: get_evidence and explain_score
    T->>S: Score with SYNTH_V1 (inferred)
    S-->>T: Amber: resistant lines 30 pct, needs 50
    T-->>LLM: Criterion table, source rows, flags
    LLM-->>UI: Answer that cites the source rows
    B->>UI: Override to Advance, with a reason
    UI->>L: Original recommendation, decision, reason, actor, time
    Note over UI,L: A reason is required and source data is never changed
```

### Recommendation and override lifecycle

```mermaid
stateDiagram-v2
    [*] --> Scored: rule applied to trial values
    Scored --> Green: all five PASS criteria met
    Scored --> Amber: no knockout, a criterion missed
    Scored --> Red: yield or disease knockout
    Green --> Decided
    Amber --> Decided
    Red --> Decided
    Amber --> Rechecked: breeder challenges
    Red --> Rechecked: breeder challenges
    Rechecked --> Scored: new evidence or rule version
    Decided --> [*]: agree or override, reason logged
```

### Data gaps to close before any operational claim

| Needed | Supplied? | Stop-gap for the demo |
| --- | --- | --- |
| Pass/fail scoring logic | **Yes, as outcomes** (`SYNTH_V1`), no thresholds | Inferred thresholds that reproduce 72/72, labelled "inferred" |
| Colour meaning | PASS / HOLD / FAIL | Proposed mapping to green / amber / red |
| Line-level field measurements | No: observations hold links only | Show trial values; state that line values are not supplied |
| Which lines produced each trial aggregate | No: observation links do not reproduce them | Flag the mismatch; ask the SME |
| Lab trait dictionary | No | Label as Lab trait 1-4 |
| Past decision baseline per line | Removed in v2 | Use the supplied trial verdicts as the baseline |

Open questions for the SME are in the [UC4 guide](README.md#questions-for-the-domain-owner).

---

## Part C: Evidence

Method: the v2 zip was opened in memory with `zipfile` + `pandas.read_csv` (read-only, 2026-09-29) by [`analysis/uc4_eda/`](../../analysis/uc4_eda/uc4_eda.py); the tables it writes are in `analysis/uc4_eda/tables/`.

| Claim | Source | Measured value |
| --- | --- | --- |
| Row × column counts | 7 CSVs | recommendations 72×18, genomics 150×19, trial 72×56, observation 720×17, operations 216×10, lab 360×16, germplasm 150×64 |
| Orphan keys | all GUID joins | none |
| Lines per trial; trials per line | observation | 10 in every trial; 4 (30 lines) or 5 (120 lines) |
| Observation location = trial location | `FIELD_ID` vs `LOCATION_GUID` | 100% |
| Verdicts | `TRIAL_RECOMMENDATION` | PASS 7, HOLD 35, FAIL 30; `RULE_VERSION` SYNTH_V1 |
| Inferred rule reproduces verdicts | `rules.apply_rule` | 72 of 72 |
| Cut-point brackets | `tables/rule_intervals.csv` | yield target 8.90-9.14; moisture 21.8-22.1; disease 4.9-5.2; GBV 101.0-103.4; resistant 30-50; yield KO 6.72-7.13; disease KO 7.0-7.2 |
| "All four met" but not PASS | rationale vs verdict | 4 of 11 |
| FAIL triggers | knockouts | disease only 16, yield only 10, both 4 |
| Genomics aggregates via observation links | `tables/genomics_reconciliation.csv` | GBV 0 of 72, resistant 10 of 72 |
| Genomics aggregates via blocks of 10 lines | same | 72 of 72 each |
| Operations outside trial start year | operations vs trial | 144 of 216 |
| Planned operations before the extract (26 Sep 2026) | operations | 114 of 114 |
| COMPLETE trials with planned operations | operations | 60 of 72 |
| Operations sharing trial + line with an observation link | operations vs observation | 85 of 216 |
| Lab coverage | lab | 150 lines, 2-3 rows each; 4 traits × 90 rows; no dates |
| Genomics QC | `QC_STATUS_LID` | PASS 150 |

The kickoff (v1) archive evidence is superseded; its profile remains in [`analysis/uc4_eda/v1/`](../../analysis/uc4_eda/v1/report_v1.html).

[sme]: ../../team/SME_ANSWERS.md
