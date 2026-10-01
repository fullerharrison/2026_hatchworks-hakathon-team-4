# UC4 breeder assistant - HatchWorks / Syngenta hackathon

This repository contains the UC4 R&D Data Source Unification demo for the September 28-October 2, 2026 hackathon. It brings field, lab and genomic evidence together so breeders can inspect candidate recommendations, record ADVANCE/HOLD/DISCARD decisions, and review evidence corrections. The breeder makes the final choice.

## Start here

On Windows, double-click `Start-Dashboard.cmd` to launch the candidate dashboard and open a browser. See [group setup and packaging](SHARE.md) for prerequisites and distribution.

| What you need | Guide |
| --- | --- |
| Run the app, configure Ask, or run tests | [App README](app/README.md) |
| Understand the dataset and provisional scoring | [UC4 guide](use-cases/uc4/README.md) |
| Understand components, storage and decision history | [Runtime architecture](app/ARCHITECTURE.md) |
| Understand source relationships and reconstruction | [Data architecture](use-cases/uc4/DATA_ARCHITECTURE.md) |
| Integrate through HTTP or MCP | [API reference](app/API.md) |

The current app and [analysis briefing](analysis/uc4_eda/report.html) use the 1 October candidate delivery. See the [source inventory](get_started/README.md) for current and superseded archives. The historical v2 app requires an [explicit launch flag](app/README.md#historical-v2).

## Team and event references

- [Participant handbook](get_started/2026_Participant_Handbook.pdf): participation, judging and submission rules.
- [Official use-case briefs](get_started/2026_Use_Case_Briefs.pdf): scope and success criteria for all four challenges. UC1-UC3 have no local guides in this checkout; the [architecture index](use-cases/DATA_ARCHITECTURE.md) retains their historical summaries.
- [Team roles](team/ROLES.md), [original build plan](.tasks/uc4-assistant/task.md), and [shared prompt log](team/PROMPT_LOG.md).
- [SME answers](team/SME_ANSWERS.md): delivery history and unresolved domain questions.
- [Historical v2 review](.tasks/uc4-demo-review/task.md) and [recordings](.tasks/uc4-demo-review/evidence/20260930T225928Z-bbd0c0b/videos/index.md): dated evidence for the former demo. Recordings supplement the required live presentation.
