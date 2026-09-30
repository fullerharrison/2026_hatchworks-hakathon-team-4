# Which use case should we build?

**For:** the whole team, including anyone new to AI. **Date:** 2026-09-28. **Reading time:** about 6 minutes.

Every fact below links to its source: the [participant handbook][hb], the [use-case briefs][brief], the four guides in `use-cases/`, or the [data check][ver] in which we opened every supplied file and counted what is actually there.

## The answer in 30 seconds

**Build UC4: R&D Data Source Unification.** If we want the lowest technical risk instead, **UC3** is a close second.

1. **The data works as supplied.** UC4's files link together cleanly, and since 29 September the expert has supplied the scoring outcomes too. [UC4 guide][uc4] · [SME answer][sme]
2. **AI does real work in it.** A breeder asks a question in plain English and gets an answer that points to the exact rows behind it. The other use cases are mostly calculators.
3. **It is safe to show.** The data is synthetic, so we can put it on screen and in our repo without hiding anything.

## How we are scored

| Criterion | In plain words | Source |
| --- | --- | --- |
| Business value | Does it solve Syngenta's real problem, on realistic data, with a useful output? | [Handbook p. 2][hb2] |
| Technical | Does it work live from start to finish? Did we compare it with the old way (a *baseline*)? Could Syngenta take over the code? | [Handbook p. 2][hb2] |
| GenDD / agentic dev | Did we use AI throughout the work, not only to write code? | [Handbook p. 3][hb3] |
| Demo | A live demo, not slides; a clear story in 7 minutes; everyone visibly contributed. | [Handbook p. 3][hb3] |
| Bonus: Syngenta Pull | Would Syngenta actually pilot it? (Scored by Syngenta judges only.) | [Handbook p. 3][hb3] |
| Bonus: HW Leverage | Could HatchWorks reuse it? (Scored by HatchWorks judges only.) | [Handbook p. 3][hb3] |

**What we hand in:** within one hour of presenting, a working demo (shown live), the slide deck, a one-pager and a link to the repo. [Handbook pp. 3-4][hb3]

## The four options side by side

| | UC1 Plant capacity | UC2 Demand capture | UC3 Data integrity | UC4 R&D unification |
| --- | --- | --- | --- | --- |
| **Is the data usable?** | Partly. Plenty of history, but **no conditioning capacity data at all**; the only "capacity" columns are for packaging and come out blank. | Partly. **No monthly demand history.** A yearly 2024-2030 sales series helps a little. | Yes. One clean sheet of 545 accounts. | **Yes.** Seven files (v2) with **zero broken links** between them. |
| **How much must we invent?** | A lot: orders, machine hours, changeover rules. | A lot, and it is the core of the demo. | A little: which fields are required. | **Very little:** the expert supplied the verdicts; only the exact thresholds are inferred. |
| **Safe to show on screen?** | Permissions unclear. | Sales figures must stay synthetic. | No: names, phones, emails and addresses must be masked. | **Yes:** already synthetic. |
| **What AI adds** | Little; scheduling is maths. | Little; it is a calculator. | Some: explaining each problem found. | **A lot:** answers plain-English questions with cited evidence. |
| **Is the brief final?** | Yes | Yes | **No, marked "provisional"** | Yes |

**Why UC3 is still a good fallback:** it has real problems to find, for example 276 accounts with no email and 6 likely duplicate accounts. It is the simplest build. Its weaknesses are the "provisional" brief, the personal data that must be masked, and several category columns that hold only one value, which leaves few rules to test.

## Why UC4, with evidence

**The user.** A senior breeder decides which plant lines move forward. Today they piece together trial, lab, operations and pedigree data from spreadsheets and paper. They want one place to ask questions, see a red/amber/green signal with reasons, and overrule it with a logged reason. [Brief p. 5][brief5]

**Update, 2026-09-29.** The expert answered our scoring question with a new (v2) set of files that includes a pass/hold/fail verdict for every trial. It replaces the kickoff files, so some facts below changed. [SME answer][sme]

**What the data gives us** ([UC4 guide][uc4]):

- **Clean links.** Every record points to a real plant line (`MATERIAL_GUID`) and a real trial (`TRIAL_GUID`). No orphans.
- **The expert's own scoring, as a baseline.** All 72 trials carry the expert's verdict: 7 pass, 35 hold, 30 fail. A simple fixed-threshold rule reproduces all 72. Our assistant must match them, which gives a ready-made test.
- **Built-in "amber" cases.** The 35 hold trials. Four of them look like passes in the expert's own explanation text; the hidden reason (too few disease-resistant lines) is exactly what an explaining assistant should surface.
- **The right audience.** The UC4 expert, Diganta Adhikari, is also a Syngenta judge. [Handbook p. 2][hb2]

**What to be honest about:**

- The verdict file gives outcomes, not the numbers behind them. Our thresholds are **inferred** until the expert confirms them. [SME answer][sme]
- Verdicts are per **trial**, while the brief's breeder decides on **lines**. Ask how one maps to the other. [UC4 guide][uc4]
- The trial numbers cannot be traced to specific lines: the files hold no line-level field values, and the trial's genomics figures do not match the lines linked to it. [UC4 guide][uc4]
- The kickoff files' past decisions and "missing lab" cases are gone in v2.
- The brief says fragmentation roughly doubles the breeding cycle. That describes the problem; our prototype cannot claim to fix it. Measure time and accuracy instead.

## AI inside the product

```text
Breeder asks (example): "Why is trial SYN-TR-0037 amber?"
   1. AI reads the question and works out which line and what is being asked
   2. Plain code fetches the matching rows from the five files
   3. Fixed rules (not AI) set red / amber / green
   4. AI writes a short answer and cites every row it used
   5. Breeder accepts, or overrides with a reason; the app logs both
```

This pattern is called **RAG** (retrieval-augmented generation): the AI *retrieves* real records first and then *generates* an answer from them only.

| AI does | AI must not do |
| --- | --- |
| Understand plain-English questions | Make up numbers or thresholds |
| Explain a colour in one or two sentences | Decide on advancement by itself |
| Point to the exact source rows | Turn missing evidence into a pass; it stays **amber** |
| Ask "which one?" when a name matches several lines | Change the source data or the original recommendation |

## AI for building the product

The handbook makes AI mandatory for **requirements, stories, prototyping, code and docs**, and judges score it separately. [Handbook pp. 2-3][hb2] Plan to use it at every step and keep proof.

The tools below are the ones every teammate can use all week: **OpenCode**, **GitHub Copilot**, **Portkey** (our gateway to AI models) and **n8n** (workflow automation). [Team prep notes](../preperation.md)

| Step | How AI helps | Tools | Proof for the judges |
| --- | --- | --- | --- |
| Understand the brief | Summarise the PDFs; explain breeding terms | Copilot Chat, OpenCode | Saved prompts and summaries |
| Questions for the expert | Draft and rank the questions | Copilot Chat | The email we sent |
| User stories and tests | Turn the brief into stories with "given / when / then" checks | OpenCode, Copilot Chat | Stories file in the repo |
| Understand the data | Write scripts that count rows, find gaps and check links | OpenCode, Copilot | Data profile report |
| Build the app | Write, explain and fix code | OpenCode, Copilot | Commit history |
| Answer questions inside the app | The app calls an AI model | Portkey | Model and settings listed in the repo |
| Test against the baseline | Generate test questions; compare answers with the past decisions | OpenCode, Portkey | Results table: our answer vs. baseline |
| Automate | Chain steps, e.g. ask a question, fetch rows, log an override | n8n | Workflow screenshot |
| Docs, one-pager, deck | Draft from the repo and our notes | Copilot Chat, OpenCode | Final documents |

**Two habits:** keep a shared prompt log for the "how we worked" slide, and watch token spend, which the handbook counts as part of the spirit of the event. [Handbook p. 4][hb4] Say which tools we used in the presentation. [Handbook p. 4][hb4]

## The 7-minute demo story

1. **Problem (1 min):** the breeder juggles five data sources on paper and in spreadsheets.
2. **Ask (1.5 min):** type a question live and get an answer with cited rows.
3. **Flag (1.5 min):** open an amber trial and show why: its explanation text says every criterion is met, but only 30% of its lines are disease-resistant.
4. **Override (1 min):** the breeder disagrees, records a reason, and the log shows before and after.
5. **Proof (2 min):** manual cross-file lookup vs. the assistant, in time and correctness; then how AI built it.

## First moves

- [x] Ask the UC4 expert for the scoring rules (answered 2026-09-29 with the v2 files; see [SME answer][sme]).
- [ ] Send the [follow-up questions][sme-followups]: exact thresholds, trial vs line, and which lines make up each trial.
- [ ] Everyone loads the seven v2 UC4 CSVs locally.
- [x] Split roles: data and rules, AI answers, screen and log, docs and demo. See [team roles](../team/ROLES.md); owners still to be named.
- [x] Start the shared prompt log today. See [prompt log](../team/PROMPT_LOG.md).

## Glossary

| Term | Meaning |
| --- | --- |
| LLM | Large language model: the AI that reads and writes text. We reach it through Portkey. |
| RAG | Fetch real records first, then let the AI answer only from them. |
| MCP | A standard way to give an AI access to tools and data. Optional for us. |
| Baseline | The current way of doing the task, used to show we are better. |
| Germplasm / line | The plant breeding material being evaluated. |
| GUID / key | A unique ID that links a row in one file to rows in another. |
| Join | Combining rows from two files that share a key. |
| Human in the loop | A person makes the final decision; the AI only recommends. |

[hb]: ../get_started/2026_Participant_Handbook.pdf
[hb2]: ../get_started/2026_Participant_Handbook.pdf#page=2
[hb3]: ../get_started/2026_Participant_Handbook.pdf#page=3
[hb4]: ../get_started/2026_Participant_Handbook.pdf#page=4
[brief]: ../get_started/2026_Use_Case_Briefs.pdf
[brief5]: ../get_started/2026_Use_Case_Briefs.pdf#page=5
[uc4]: uc4/README.md
[sme]: ../team/SME_ANSWERS.md
[sme-followups]: ../team/SME_ANSWERS.md#follow-up-questions-to-send
