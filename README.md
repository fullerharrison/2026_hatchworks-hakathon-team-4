# 2026 HatchWorks AI and Syngenta hackathon

This workspace holds the source materials and working documentation for the September 28 to October 2, 2026 hackathon. Teams choose one of four vegetable-seed business challenges and present a live proof of concept. The [participant handbook](get_started/2026_Participant_Handbook.pdf#page=1) is the authority for participation and submission rules; the [use-case briefs](get_started/2026_Use_Case_Briefs.pdf#page=1) are the authority for problem scope and success criteria.

## Start here

0. New to this? Read the [team recommendation](use-cases/RECOMMENDATION.md) first: which use case to build and how to use AI for both the product and the work.
1. Read the [participant handbook](get_started/2026_Participant_Handbook.pdf) for dates, judging, and submission requirements.
2. Read the [use-case briefs](get_started/2026_Use_Case_Briefs.pdf) for the four official challenges; the [kickoff deck](get_started/2026_Kickoff_Deck.pdf) provides a quick overview.
3. Choose the [UC1: Plant Capacity Utilization guide](use-cases/uc1/README.md), [UC2: Market Intelligence and Demand Capture guide](use-cases/uc2/README.md), [UC3: Commercial Data Integrity Agent guide](use-cases/uc3/README.md), or [UC4: R&D Data Source Unification guide](use-cases/uc4/README.md). Each explains the problem for a newcomer and proposes a source-grounded way to build and evaluate a prototype. The supplied data remains in `get_started/`.

## Team (UC4 chosen 2026-09-29)

- [Team roles](team/ROLES.md): four roles, done-when checks, interface contracts and first tasks.
- [Build task and phase plans](.tasks/uc4-assistant/task.md): five phases to the demo, each with a checkable exit criterion; [Phase 1](.tasks/uc4-assistant/phase-1-mcp-data-layer.md) is the read-only MCP data-unification layer.
- [Shared prompt log](team/PROMPT_LOG.md): log every AI prompt we keep; it is our GenDD evidence.
- [SME answers](team/SME_ANSWERS.md): on 2026-09-29 the UC4 expert sent a v2 data archive with a pass/hold/fail verdict per trial; our inferred threshold rule reproduces all 72.
- [UC4 data briefing](analysis/uc4_eda/report.html): start with the plain-language overview, then use the expert evidence audit, inferred scoring rule and consistency checks. Regenerate with `analysis/uc4_eda/uc4_eda.py`. The kickoff (v1) profile is kept in [`analysis/uc4_eda/v1/`](analysis/uc4_eda/v1/report_v1.html).

## Use cases

| Use case | Documentation | Data architecture |
| --- | --- | --- |
| UC1: Plant Capacity Utilization | [Guide](use-cases/uc1/README.md) | [Diagrams](use-cases/uc1/DATA_ARCHITECTURE.md) |
| UC2: Market Intelligence and Demand Capture | [Guide](use-cases/uc2/README.md) | [Diagrams](use-cases/uc2/DATA_ARCHITECTURE.md) |
| UC3: Commercial Data Integrity Agent | [Guide](use-cases/uc3/README.md) | [Diagrams](use-cases/uc3/DATA_ARCHITECTURE.md) |
| UC4: R&D Data Source Unification | [Guide](use-cases/uc4/README.md) | [Diagrams](use-cases/uc4/DATA_ARCHITECTURE.md) |

The [data architecture index](use-cases/DATA_ARCHITECTURE.md) explains the two-level (novice and expert) diagrams and the shared colour legend. It also lists new evidence from the supplied data.

All four use cases have guides from separate passes. The guides distinguish facts in the supplied materials from proposals and questions for the respective business experts. No application has been implemented yet. The one piece of code is a read-only data profile for UC4 in [`analysis/uc4_eda/`](analysis/uc4_eda/uc4_eda.py): it writes a [report](analysis/uc4_eda/report.html), figures and summary tables, and holds the inferred SYNTH_V1 scoring rule ([`rules.py`](analysis/uc4_eda/rules.py)) with its tests. Its findings are summarised in the [UC4 guide](use-cases/uc4/README.md#data-profile-what-the-archive-supports).
