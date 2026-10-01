# UC4 source selection

**Current analysis and application source:** `candidate_recommendations_synthetic.zip`, received 1 October 2026. The SME instructed the team to use this replacement and erase the previous version to avoid confusion. The team chose to archive/deactivate previous versions rather than delete historical evidence.

| ZIP | Status | Use |
| --- | --- | --- |
| candidate_recommendations_synthetic.zip | Current replacement | Source for current UC4 analysis and candidate app |
| RE__Hatchworks_Hackathon_-_4th_Use_Case_09-30-2026.zip | Superseded v3 | Historical analysis/regression tests |
| RE__Hatchworks_Hackathon_-_4th_Use_Case.zip | Superseded v2 | Historical app demo and regression tests |
| UC4 - R&D Data Source Unification-20260928T220200Z-1-001.zip | Superseded v1 | Historical evidence |

Previous ZIPs remain in place because the explicit historical app mode and legacy tests select their exact filenames. They must not be combined with the replacement dataset or selected for current analysis. The default app expects the candidate schema; incompatible archives are rejected. All ZIPs remain git-ignored; do not commit source archives.

See the [current briefing](../analysis/uc4_eda/report.html), [UC4 guide](../use-cases/uc4/README.md), and [app instructions](../app/README.md).
