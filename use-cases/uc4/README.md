# UC4: R&D Data Source Unification

The [current data briefing](../../analysis/uc4_eda/report.html) uses **candidate_recommendations_synthetic.zip**, the replacement supplied by the SME on 1 October 2026. It is the fourth local delivery; source remarks call it "integrated V2 (fixed)". Earlier sources and conclusions are superseded for current analysis.

The running [app](../../app/README.md) now uses candidate-level provisional RAG, list filters, contextual breeder decisions and reviewed enrichment. Source snapshots and recommendation revisions preserve historical decision context. See [SME messages](../../team/SME_ANSWERS.md) for delivery history.

## What the breeder can now inspect

The replacement recommends a candidate line, using field performance relative to check varieties, disease, harvest moisture, germination, fumonisin and a disease-resistance marker. It supplies 150 recommendations: **32 GREEN, 53 AMBER, 65 RED**. A recommendation is a system review signal; a breeder makes the final decision. All supplied breeder decision/comment fields are blank.

There are 152 germplasm and genomic records: 150 candidates plus two checks. The explicit trial-germplasm bridge covers 72 trials, 148 candidates and both checks. Two candidates, SYN-MZ-00149 and SYN-MZ-00150, have no field results and remain AMBER.

| Source | Rows | Role |
| --- | ---: | --- |
| Candidate recommendations | 150 | Candidate metrics, RAG, reasons, exclusion caveats; blank breeder decisions |
| Germplasm | 152 | Material GUID/ID, line GUID and display name; pedigree/stage unfilled |
| Genomics | 152 | Marker calls, genomic breeding value and QC |
| Lab observations | 456 | Three dated numeric lab traits per material |
| Field observations | 5,184 | Yield, moisture and disease for 1,728 replicated entries |
| Trial-germplasm bridge | 1,728 | Six candidates and two checks, three replicates per trial |
| Field operation updates | 360 | Planned/actual dates, status, delay and reporting channel |
| Trait dictionary | 6 | Field/lab names, units, scales and better direction |

## Evidence and reconstruction

All 12 audited recorded key relationships resolve, with zero violations across 22 identity/chronology checks. Joins use recorded GUIDs; no previous GUID repairs or positional alignment are used. [Architecture diagrams](DATA_ARCHITECTURE.md) show the keys.

Average replicates within trial/material. Compute each trial's check mean from its two checks. Exclude trials with MISSED irrigation, then average candidate and corresponding check yields across usable trials with equal trial weight. Yield vs checks is **100 × mean candidate yield / mean check yield**; averaging trial-level ratios gives a different result.

All 148 available field metric summaries reproduce within the displayed precision. Counts, exclusion caveats, lab metrics, markers and genomic values also reconcile. Five missed-irrigation trials explain the exclusion caveats on 30 candidates. Eleven other operation updates report delays. The [audit tables](../../analysis/uc4_eda/report.html#downloads) contain original/rebuilt values and source-row references.

These calculations are **inferred from reproduction of supplied outputs**, not an SME-confirmed analysis protocol. No trial master is supplied, so official trial year/status/location is unavailable; no earlier snapshot fills those gaps.

## Candidate scoring audit

An outcome-compatible rule matches all 150 supplied recommendations, using either the supplied rounded summaries or reconstructed source precision:

1. No usable field data → AMBER.
2. RED if yield vs checks <95%, disease >6, or fumonisin >4 ppm.
3. Otherwise GREEN if yield vs checks ≥103%, disease ≤4, moisture ≤23%, germination ≥90%, marker is RESISTANT or INTERMEDIATE, and at least two trials are usable.
4. Otherwise AMBER.

Targets and limits appear in the supplied reasons. The complete conjunction, precedence, inclusive boundaries and no-data priority are **inferred**. Moisture >25% and germination <85% do not act as RED knockouts in this snapshot. Genomic value and cold-test vigour require no gate to reproduce the supplied outcomes; confirm their intended role with the SME. These are synthetic demonstration rules, not a production breeding protocol.

## Reproduce and follow up

From the repository root:

```powershell
python analysis/uc4_eda/uc4_eda.py
python -m pytest -q analysis/uc4_eda -p no:cacheprovider --basetemp analysis/uc4_eda/.test-tmp
```

The Python environment needs pandas, matplotlib and pytest. An alternative is `uv run --no-project --with pandas --with matplotlib --with pytest python` followed by the same script or `-m pytest` arguments. The dedicated workspace temporary directory avoids Windows permissions on the shared pytest temp folder. The current generator reads only the replacement ZIP; legacy regression tests intentionally use historical ZIPs. ZIPs remain git-ignored.

Confirm aggregation, exclusions, threshold equality/rounding, and the role of genomic/cold-test metrics. The coordinated candidate app migration uses the same reconstruction and policy implementation as this analysis. Existing human decisions retain their original recommendation context; historical v2 records remain explicitly trial-scoped.

Retained ZIPs are marked superseded in the [source inventory](../../get_started/README.md); they are not inputs to current analysis.
