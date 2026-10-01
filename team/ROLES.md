# UC4 team roles

**Decision:** we are building [UC4: R&D Data Source Unification](../use-cases/uc4/README.md) (chosen 2026-09-29). **Demo:** Fri 2026-10-02, 7 min + 5 min Q&A; submit the demo, deck, one-pager and repo link within 1 hour. [Handbook p. 3][hb3]

## Rules for every role

This page records the original v2 build-role agreement. The current implemented architecture is in [app/ARCHITECTURE.md](../app/ARCHITECTURE.md), and the executed [demo review](../.tasks/uc4-demo-review/task.md) records current evidence and agent reviewers. The app remains a historical v2 demo. The [replacement candidate analysis](../analysis/uc4_eda/report.html) supersedes previous analysis assumptions; a candidate-level runtime migration is still required. Human team-owner cells remain unassigned here.

1. **Evidence first.** Every claim in the app, deck or one-pager cites a CSV row, a brief/handbook page or a test result. If there is no source, label it **proposal** or **inferred**.
2. **AI does not decide.** Plain code sets red/amber/green; AI interprets the question and writes the answer *from the retrieved rows*. The breeder makes the final call. [Recommendation](../use-cases/RECOMMENDATION.md#ai-inside-the-product)
3. **Missing evidence stays visible.** A missing value never passes a criterion. Lab results have no `TRIAL_GUID`, so never attach them to a trial. Trial values cannot be traced to specific lines, so flag that gap rather than hide it. [UC4 guide][uc4]
4. **Log your prompts** in [PROMPT_LOG.md](PROMPT_LOG.md) the same day. It becomes the GenDD proof. [Handbook p. 3][hb3]

## The four roles

Each person owns one role; with fewer than four people, merge **Screen and log** with **AI answers** first.

| Role | Owner | Owns | Done when (checkable) |
| --- | --- | --- | --- |
| **1. Data and rules** | _unassigned_ | Load the 7 v2 CSVs; validation report; evidence model keyed on `TRIAL_GUID` / `MATERIAL_GUID`; the SYNTH_V1 scoring engine; the baseline comparison | Report reproduces the [v2 profile][profile] counts (72 trials, 720 links, 216 operations, 360 lab, 150 lines, 150 genomics, 72 verdicts; 0 orphans). The engine matches **72 of 72** supplied verdicts. Each colour comes with every criterion's value and threshold and the source rows. Thresholds are labelled "inferred" until the SME confirms them |
| **2. AI answers** | _unassigned_ | Question → line resolution → fetch rows → answer with citations, through Portkey; a fixed list of supported questions | 10 or more test questions, each answer checked against the rows it cites. No invented numbers; an ambiguous line name produces a "which one?" prompt. Model and settings are recorded in the repo |
| **3. Screen and log** | _unassigned_ | Trial view (criteria table, its ten lines with genomics / lab / operations), colour and reason, "Record decision" with a required reason; append-only override log | An override without a reason is rejected. The log keeps the original recommendation, the decision, the reason, who and when. Source data and the original recommendation never change |
| **4. Docs and demo** | _unassigned_ | Prompt log upkeep, SME email, 7-min script, deck, one-pager, handover README, baseline timing | Script rehearsed within 7:00. The baseline shows manual cross-file lookup vs. the app (time and correctness) on the same lines. Every slide claim links to evidence |

## Interfaces (agree these first so roles can work in parallel)

Role 1 publishes these shapes on day 1; roles 2 and 3 build against them with a few hand-written sample records until the real data is ready.

| Contract | Fields (minimum) | Producer → consumer |
| --- | --- | --- |
| **Evidence row** | `source_file`, `row_id`, `trial_guid` (null for lab and genomics), `material_guid` (null for trial values), `field`, `value`, `uom`, `date`, `flags[]` | 1 → 2, 3 |
| **Recommendation** | `trial_guid`, `verdict` (PASS/HOLD/FAIL), `colour` (green/amber/red, proposed), `criteria[]` (`field`, `value`, `threshold`, `met`), `knockout`, `reason`, `rule_version`, `supplied_verdict`, `evidence_row_ids[]`, `flags[]` | 1 → 2, 3 |
| **Override record** | `trial_guid`, `material_guid` (optional), `recommendation` (copied, immutable), `decision`, `reason` (required), `user`, `timestamp` | 3 → 4 |

## First task per role (today)

| Role | First task | Time box |
| --- | --- | --- |
| Data and rules | Unzip the v2 archive (`RE__Hatchworks_Hackathon_-_4th_Use_Case.zip`) into `data/raw/` (read-only); port [`rules.py`][rules] into the app and keep its 72/72 test | 1 h |
| AI answers | Draft the supported-question list and a Portkey hello-world call | 1 h |
| Screen and log | Pick the stack and sketch the one screen from the [UC4 guide](../use-cases/uc4/README.md#proposed-hackathon-mvp) | 1 h |
| Docs and demo | Reply to the SME with the [follow-up questions][followups]; keep the prompt log going | 30 min |

## Questions for the SME (Diganta Adhikari)

Answers go to [SME_ANSWERS.md](SME_ANSWERS.md) with the date received. Full list: [UC4 guide][uc4-questions].

1. ~~What are the pass/fail scoring rules, and what does each colour mean?~~ **Answered 2026-09-29** with the v2 archive: per-trial PASS/HOLD/FAIL against fixed targets. Thresholds inferred, to confirm.
2. Are the inferred thresholds right, and why is resistant % missing from the rationale?
3. Is the trial or the line the unit of decision, and which lines make up each trial's aggregates?
4. What do the 4 lab `TRAIT_GUID`s mean?

[hb3]: ../get_started/2026_Participant_Handbook.pdf#page=3
[uc4]: ../use-cases/uc4/README.md
[uc4-questions]: ../use-cases/uc4/README.md#questions-for-the-domain-owner
[profile]: ../analysis/uc4_eda/report.html
[rules]: ../analysis/uc4_eda/rules.py
[followups]: SME_ANSWERS.md#follow-up-questions-to-send
