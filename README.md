# 2026 HatchWorks AI and Syngenta hackathon

This workspace holds the source materials and working documentation for the September 28 to October 2, 2026 hackathon. Teams choose one of four vegetable-seed business challenges and present a live proof of concept. The [participant handbook](get_started/2026_Participant_Handbook.pdf#page=1) is the authority for participation and submission rules; the [use-case briefs](get_started/2026_Use_Case_Briefs.pdf#page=1) are the authority for problem scope and success criteria.

## Start here

For the runnable group handoff, see [packaging and launch instructions](SHARE.md).
On Windows, `Start-Dashboard.cmd` launches the candidate dashboard and opens a browser.

0. New to this? Read the [team recommendation](use-cases/RECOMMENDATION.md) first: which use case to build and how to use AI for both the product and the work.
1. Read the [participant handbook](get_started/2026_Participant_Handbook.pdf) for dates, judging, and submission requirements.
2. Read the [use-case briefs](get_started/2026_Use_Case_Briefs.pdf) for the four official challenges; the [kickoff deck](get_started/2026_Kickoff_Deck.pdf) provides a quick overview.
3. Read the chosen [UC4 guide](use-cases/uc4/README.md), [implemented architecture](app/ARCHITECTURE.md), and [app run instructions](app/README.md). The supplied data remains in `get_started/`. UC1-UC3 are described in the official briefs; their local guides are not present in this checkout.

## Team (UC4 chosen 2026-09-29)

- [Team roles](team/ROLES.md): four roles, done-when checks, interface contracts and first tasks.
- [Build task and phase plans](.tasks/uc4-assistant/task.md): five phases to the demo, each with a checkable exit criterion; [Phase 1](.tasks/uc4-assistant/phase-1-mcp-data-layer.md) is the read-only MCP data-unification layer.
- [Shared prompt log](team/PROMPT_LOG.md): log every AI prompt we keep; it is our GenDD evidence.
- [SME answers](team/SME_ANSWERS.md): the 1 October replacement introduces candidate-level GREEN/AMBER/RED, check varieties, an explicit membership bridge and named lab traits. Previous deliveries are superseded for current analysis.
- [UC4 data briefing](analysis/uc4_eda/report.html): current replacement analysis, with 150 candidates (32 GREEN, 53 AMBER, 65 RED), source reconstruction and scoring audit. Regenerate with `python analysis/uc4_eda/uc4_eda.py`. Superseded profiles: [v1](analysis/uc4_eda/v1/report_v1.html), [v2](analysis/uc4_eda/v2/report_v2.html), [v3](analysis/uc4_eda/v3/report_v3.html). The app now uses candidate-level RAG and versioned decision history; [source inventory](get_started/README.md).

## Use cases

| Use case | Documentation | Data architecture |
| --- | --- | --- |
| UC1: Plant Capacity Utilization | Official briefs only | Not in this checkout |
| UC2: Market Intelligence and Demand Capture | Official briefs only | Not in this checkout |
| UC3: Commercial Data Integrity Agent | Official briefs only | Not in this checkout |
| UC4: R&D Data Source Unification | [Guide](use-cases/uc4/README.md) | [Diagrams](use-cases/uc4/DATA_ARCHITECTURE.md) |

The [data architecture index](use-cases/DATA_ARCHITECTURE.md) explains the two-level (novice and expert) diagrams and the shared colour legend. It also lists new evidence from the supplied data.

The implemented UC4 app now uses the replacement candidate dataset, shared reconstruction and provisional GREEN/AMBER/RED scoring. Breeders can browse or filter all candidates, inspect evidence, record ADVANCE/HOLD/DISCARD decisions with context, and review enrichment before activating new evidence revisions. Original source snapshots and decision context are retained. The breeder makes the final choice; historical v2 remains available through an explicit launch option.

- [Historical v2 demo review and readiness](.tasks/uc4-demo-review/task.md): source-to-screen checks, findings, and rechecks for that snapshot.
- [Current process and decision records](app/ARCHITECTURE.md): runtime architecture, stack, assumptions, and storage.
- [Demo and process recordings](.tasks/uc4-demo-review/evidence/20260930T225928Z-bbd0c0b/videos/index.md): supplementary narrated examples; the hackathon still requires a live presentation.
