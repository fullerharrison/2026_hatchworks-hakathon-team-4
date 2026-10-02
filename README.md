# UC4 breeder assistant - HatchWorks / Syngenta hackathon

This repository contains the UC4 R&D Data Source Unification demo for the September 28-October 2, 2026 hackathon. It brings field, lab and genomic evidence together so breeders can inspect candidate recommendations, record ADVANCE/HOLD/DISCARD decisions, and review evidence corrections. The breeder makes the final choice.

## Start here

On Windows, double-click `Start-Dashboard.cmd` to launch the candidate dashboard and open a browser. See [group setup and packaging](SHARE.md) for prerequisites and distribution.

| What you need | Guide |
| --- | --- |
| Run the app, configure Ask, or run tests | [App README](app/README.md) |
| Follow breeder review, development checks and handoff | [Process guide](app/PROCESS.md) |
| Start a separate practice session without commands | [Breeder review guide](app/HUMAN_REVIEW.md) - double-click `Start-Breeder-Review.cmd` |
| Understand the dataset and provisional scoring | [UC4 guide](use-cases/uc4/README.md) |
| Understand components, storage and decision history | [Runtime architecture](app/ARCHITECTURE.md) |
| Understand source relationships and reconstruction | [Data architecture](use-cases/uc4/DATA_ARCHITECTURE.md) |
| Integrate through HTTP or MCP | [API reference](app/API.md) |

The current app and [analysis briefing](analysis/uc4_eda/report.html) use the 1 October candidate delivery: 150 candidates, two checks, and a baseline of **32 GREEN, 53 AMBER and 65 RED**. See the [source inventory](get_started/README.md) for current and superseded archives. The historical v2 app requires an [explicit launch flag](app/README.md#historical-v2-and-limitations).

The dashboard provides source-backed assessments, optional browser preferences, typed filter previews, grounded Ask, reviewed manual decisions with saved receipts and original evidence, and guided enrichment review/activation. Core workflows work without model credentials; Ask and typed interpretation use each user's configured Portkey route. Names are self-declared and scoring is provisional for synthetic maize-like data.

See [release notes](app/RELEASE_NOTES.md) for delivered features, verification and remaining human checks. Human retesting, a spoken team rehearsal and biological validation remain explicit limits.

The breeder review encountered upstream model gateway/provider errors. Manual review remains available. Final preparation verified cited Ask and typed filters on the currently configured route; availability remains dependent on each user's credentials and model service. See the release notes and [troubleshooting](app/PROCESS.md#troubleshooting).

## Team and event references

- [Participant handbook](get_started/2026_Participant_Handbook.pdf): participation, judging and submission rules.
- [Official use-case briefs](get_started/2026_Use_Case_Briefs.pdf): scope and success criteria for all four challenges. UC1-UC3 have no local guides in this checkout; the [architecture index](use-cases/DATA_ARCHITECTURE.md) retains their historical summaries.
- [Team roles](team/ROLES.md), [original build plan](.tasks/uc4-assistant/task.md), and [shared prompt log](team/PROMPT_LOG.md).
- [SME answers](team/SME_ANSWERS.md): delivery history and unresolved domain questions.
- Historical v2 review materials, when retained locally under `.tasks/uc4-demo-review/`, describe the former trial demo. Use the current candidate handoff for readiness. Recordings supplement the required live presentation.
