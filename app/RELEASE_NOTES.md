# UC4 breeder assistant v0.1.0

Prepared 2 October 2026 for private team review. This is a local application using synthetic candidate data and provisional scoring. The breeder makes the final decision.

The approved build includes evidence and criteria views, candidate filtering and CSV export, optional browser preferences, decision review and recording, saved receipts, original evidence and persistent history. Evidence additions and corrections have draft, review, preview and activation steps. Ask answers use source tools and citations; typed filters must be reviewed before Apply. Neither AI workflow records breeder decisions.

Windows users can double-click `Start-Dashboard.cmd` for normal use or `Start-Breeder-Review.cmd` for an isolated practice session. See [team setup](../SHARE.md), [human review](HUMAN_REVIEW.md), [process](PROCESS.md), [architecture](ARCHITECTURE.md) and [API](API.md). Practice reports and storage stay under ignored `app/data/reviews/`; automated reports stay under `app/data/verification/`.

The candidate source contains 150 candidates and two checks. Its baseline is 32 GREEN, 53 AMBER and 65 RED. The team ZIP includes the reviewed synthetic candidate archive, locked dependencies, scripts, tests and documentation. Git excludes source ZIPs. Credentials, existing breeder decisions, runtime databases and review reports are excluded from the package.

## Verification and limits

Final preparation passed 473 offline tests and 43 candidate browser tests. The candidate-only package subset previously passed 69 tests and is repeated in the fresh-clone check. An extracted-package check verified checksums, source totals, static assets, both launch paths, browser launch after readiness, decision saving and persistence after restart. Exact final distribution and fresh-clone results are recorded with the local handoff.

Earlier live checks verified grounded Ask citations and 14 typed-filter cases. A later breeder review encountered HTTP 500/provider errors and timeouts on the configured Portkey route. On 2 October at 15:19 UTC, the current privately configured route (`@bedrock-aifoundry-use1-001/us.moonshotai.kimi-k3`) passed a live tool call, a grounded candidate Ask walkthrough with citation navigation, and all 14 typed-filter evaluation cases. This verifies that route at the test time; it does not establish recovery of the earlier failing route. Model availability can change. Ask displays an unavailable message, retains the question and allows another attempt. Manual evidence, filtering, decisions and enrichment work without AI. Each user supplies their own private model credentials; the package contains none.

Human review confirmed saving and reopening a decision. Remaining checks include deliberate second-decision retesting, broader breeder comprehension, a spoken team rehearsal and biological validation of the provisional policy. Automated timing is not a human task measurement. Names are self-declared; this demo has no production identity or access-control system.

Publication and team invitations remain the repository owner's responsibility. This preparation does not publish a repository or release.
