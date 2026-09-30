"""Self-contained HTML report (figures embedded as base64) for the UC4 v2 archive."""

from __future__ import annotations

import base64
from collections.abc import Set as AbstractSet
from html import escape
from pathlib import Path

import pandas as pd

from plant_lifecycle import lifecycle_coverage

CAPTIONS: dict[str, tuple[str, str]] = {
    "fig01_inventory": ("Inventory", "Rows per file, and whether each column is complete, "
                        "partly missing, constant or entirely null. Full list: tables/column_quality.csv."),
    "fig02_rule_traits": ("Rule inputs", "Every trial-level value in the SME's recommendation "
                          "file, split by the supplied PASS / HOLD / FAIL, with the inferred "
                          "cut-points. Full list: tables/trial_level.csv."),
    "fig03_rule_paths": ("Decision paths", "Which PASS criteria each HOLD trial misses, and which "
                         "knockout sent each FAIL trial there."),
    "fig04_categoricals": ("Categoricals", "Level counts for every categorical column the breeder "
                           "assistant might filter or group on."),
    "fig05_lab": ("Lab results", "The four lab TRAIT_GUIDs. Names, units and dates are not supplied."),
    "fig06_genomics": ("Genomics", "Breeding value, genotyping QC and the disease-resistance "
                       "marker for the 150 lines."),
    "fig07_reconciliation": ("Reconciliation", "Trial genomics aggregates as supplied vs recomputed "
                             "from the lines each mapping assigns to the trial. Full list: "
                             "tables/genomics_reconciliation.csv."),
    "fig08_operations_calendar": ("Operations calendar", "Each operation's date against its "
                                  "trial's start year, with the extract date."),
    "fig09_consistency_checks": ("Consistency checks", "Share of checkable records that break "
                                 "each rule. Full list: tables/chronology_checks.csv."),
    "fig11_plant_lifecycle": ("Season phases", "Each growth phase, what the plant does in it, and "
                              "the supplied columns that describe it. Full list: "
                              "tables/lifecycle_phase_map.csv."),
    "fig12_trial_timelines": ("Trial seasons", "Operations for each trial with a planting record, "
                              "in days after that planting, against its expected flowering. Full "
                              "list with a sentence per trial: tables/trial_timeline.csv."),
    "fig10a_bins_numeric": ("Numeric bins", "Quartile edges for each trial-level trait."),
    "fig10b_bins_categorical": ("Ordinal bins", "Quantile edges after rank encoding. Where edges "
                                "tie, fewer than four bins exist."),
}

# Source map: (key in stage_counts, card title, join key, consistency-check stage).
STAGES: list[tuple[str, str, str, str | None]] = [
    ("germplasm", "Breeding lines", "MATERIAL_GUID", None),
    ("genomics", "Genomics", "MATERIAL_GUID (one sample per line)", "Record keeping"),
    ("lab", "Lab tests", "MATERIAL_GUID only (no trial key)", None),
    ("trials", "Field trials", "TRIAL_GUID", None),
    ("observations", "Trial-line links", "ATTACHED_TO_FIELD_ENTITY_ID + GID", "Links"),
    ("operations", "Field operations", "TRIAL_GUID + MATERIAL_GUID", "Operations"),
    ("recommendations", "Trial recommendation", "TRIAL_GUID (one verdict per trial)",
     "Recommendation"),
]

CSS = """
/* Layout: one reading column; the lifecycle map is a wrapping grid of numbered cards,
   figures sit on light plates that span the column. */
:root {
  --page: #f6f7f4; --paper: #fdfdfb; --ink: #15171a; --ink-2: #4d524f; --muted: #7b807b;
  --rule: #dfe2dc; --accent: #2a78d6; --flag: #c4521f; --flag-wash: #fbeee7; --plate: #fcfcfb;
  --f-display: "IBM Plex Sans Condensed", "Arial Narrow", system-ui, sans-serif;
  --f-body: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
  --f-mono: "IBM Plex Mono", ui-monospace, Consolas, monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { color-scheme: dark; --page: #121413; --paper: #1a1c1b;
    --ink: #eef0ec; --ink-2: #bfc4be; --muted: #8b918a; --rule: #2e322f; --accent: #6da7ec;
    --flag: #ec835a; --flag-wash: #2d201a; }
}
:root[data-theme="dark"] { color-scheme: dark; --page: #121413; --paper: #1a1c1b;
  --ink: #eef0ec; --ink-2: #bfc4be; --muted: #8b918a; --rule: #2e322f; --accent: #6da7ec;
  --flag: #ec835a; --flag-wash: #2d201a; }
body { background: var(--page); color: var(--ink); font: 15px/1.6 var(--f-body);
  padding-inline: 20px; padding-block: 40px 80px; }
main { max-width: 1080px; margin: 0 auto; display: grid; gap: 56px; }
h1, h2, h3 { font-family: var(--f-display); text-wrap: balance; margin: 0; }
h1 { font-size: clamp(30px, 5vw, 46px); font-weight: 600; line-height: 1.08; }
h2 { font-size: 24px; font-weight: 600; }
h3 { font-size: 16px; font-weight: 600; }
p { margin: 0; max-width: 70ch; color: var(--ink-2); }
code { font: 0.88em var(--f-mono); color: var(--ink); }
.eyebrow { font: 500 12px/1 var(--f-mono); letter-spacing: .08em; text-transform: uppercase;
  color: var(--accent); }
header { display: grid; gap: 14px; border-bottom: 1px solid var(--rule); padding-bottom: 28px; }
.facts { display: flex; flex-wrap: wrap; gap: 8px 28px; font: 13px var(--f-mono); color: var(--muted); }
.facts b { color: var(--ink); font-weight: 600; }
nav.toc { display: flex; flex-wrap: wrap; gap: 6px 18px; font: 13px var(--f-mono); }
nav.toc a { color: var(--accent); text-decoration: none; }
nav.toc a:hover, nav.toc a:focus-visible { text-decoration: underline; }
section { display: grid; gap: 18px; scroll-margin-top: 16px; }
.section-head { display: grid; gap: 8px; }
.note { border-left: 3px solid var(--flag); background: var(--flag-wash); padding: 10px 14px;
  border-radius: 0 4px 4px 0; max-width: 78ch; color: var(--ink-2); }
.note b { color: var(--ink); }
ul.findings { margin: 0; padding-left: 20px; display: grid; gap: 8px; max-width: 78ch; }
ul.findings li { color: var(--ink-2); }
ul.findings b { color: var(--ink); }
ol.map { list-style: none; margin: 0; padding: 0; display: grid; gap: 12px;
  grid-template-columns: repeat(auto-fill, minmax(196px, 1fr)); counter-reset: step; }
ol.map li { counter-increment: step; background: var(--paper); border: 1px solid var(--rule);
  border-radius: 6px; padding: 14px; display: grid; gap: 6px; align-content: start; }
ol.map li::before { content: counter(step, decimal-leading-zero); font: 500 11px var(--f-mono);
  color: var(--muted); letter-spacing: .06em; }
.card-n { font: 600 28px/1 var(--f-display); font-variant-numeric: tabular-nums; }
.card-unit { font-size: 12.5px; color: var(--muted); }
.card-detail { font-size: 13px; color: var(--ink-2); }
.card-join { font: 11.5px/1.4 var(--f-mono); color: var(--muted); border-top: 1px dashed var(--rule);
  padding-top: 6px; overflow-wrap: anywhere; }
.card-join::before { content: "links by "; font-family: var(--f-body); }
.badge { justify-self: start; font: 500 11px var(--f-mono); padding: 2px 8px; border-radius: 99px;
  border: 1px solid currentColor; }
.badge.fail { color: var(--flag); }
.badge.none { color: var(--muted); }
figure { margin: 0; display: grid; gap: 10px; }
figure img { display: block; width: 100%; height: auto; background: var(--plate);
  border: 1px solid var(--rule); border-radius: 4px; }
figcaption { font-size: 13px; color: var(--muted); max-width: 80ch; }
figcaption b { color: var(--ink); font-family: var(--f-display); font-size: 14px; }
.table-wrap { overflow-x: auto; border: 1px solid var(--rule); border-radius: 4px; background: var(--paper); }
table { border-collapse: collapse; width: 100%; font: 12.5px/1.4 var(--f-mono);
  font-variant-numeric: tabular-nums; }
th, td { padding: 7px 10px; text-align: left; border-bottom: 1px solid var(--rule); white-space: nowrap; }
th { color: var(--muted); font-weight: 500; font-size: 11.5px; letter-spacing: .04em; }
td.num { text-align: right; }
td.wrap { white-space: normal; min-width: 220px; }
.pill { display: inline-block; padding: 1px 8px; border-radius: 99px; font-size: 11px;
  border: 1px solid currentColor; }
.pill.ok { color: var(--accent); }
.pill.tie { color: var(--flag); }
.appendix { border-top: 1px solid var(--rule); padding-top: 40px; }
footer { font-size: 12.5px; color: var(--muted); border-top: 1px solid var(--rule); padding-top: 16px; }
"""

FONTS = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500'
         '&family=IBM+Plex+Sans+Condensed:wght@500;600&family=IBM+Plex+Sans:wght@400;600&display=swap">')


def img_tag(path: Path) -> str:
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    title = CAPTIONS.get(path.stem, (path.stem, ""))[0]
    return f'<img src="data:image/png;base64,{data}" alt="{escape(title)}" loading="lazy">'


def figure(path: Path) -> str:
    title, text = CAPTIONS.get(path.stem, (path.stem, ""))
    return (f"<figure>{img_tag(path)}<figcaption><b>{escape(title)}.</b> "
            f"{escape(text)}</figcaption></figure>")


def table_html(df: pd.DataFrame, cols: list[str], num: AbstractSet[str],
               wrap: AbstractSet[str] = frozenset()) -> str:
    head = "".join(f"<th>{escape(c)}</th>" for c in cols)
    body = "".join(
        "<tr>" + "".join(
            f'<td class="{"num" if c in num else "wrap" if c in wrap else ""}">{escape(str(r[c]))}</td>'
            for c in cols) + "</tr>"
        for r in df.to_dict("records")
    )
    return f'<div class="table-wrap"><table><tr>{head}</tr>{body}</table></div>'


def bins_html(bins: pd.DataFrame) -> str:
    head = ("<tr><th>column</th><th>encoding</th><th>n</th><th>q0</th><th>q.25</th><th>q.5</th>"
            "<th>q.75</th><th>q1</th><th>bins</th><th>counts</th><th>category → bin</th></tr>")
    rows = []
    for d in bins.to_dict("records"):
        pill = ('<span class="pill tie">tied: {} bins</span>' if d["collapsed"]
                else '<span class="pill ok">{} bins</span>').format(d["n_bins"])
        qs = "".join(f'<td class="num">{d[k]:g}</td>' for k in ["q0", "q0.25", "q0.5", "q0.75", "q1"])
        rows.append(f"<tr><td>{escape(d['column'])}</td><td>{escape(d['method'])}</td>"
                    f'<td class="num">{d["n"]}</td>{qs}<td>{pill}</td><td>{d["bin_counts"]}</td>'
                    f'<td class="wrap">{escape(str(d["level_to_bin"] or "–"))}</td></tr>')
    return f'<div class="table-wrap"><table>{head}{"".join(rows)}</table></div>'


def lifecycle_map(stages: dict[str, dict[str, object]], checks: pd.DataFrame) -> str:
    cards = []
    for key, title, join, check_stage in STAGES:
        s = stages[key]
        if check_stage:
            c = checks[checks["stage"] == check_stage]
            failing = int((c["violations"] > 0).sum())
            badge = (f'<span class="badge {"fail" if failing else "none"}">'
                     f"{failing} of {len(c)} checks fail</span>")
        else:
            badge = '<span class="badge none">no date checks</span>'
        cards.append(
            f"<li><h3>{escape(title)}</h3><span class=\"card-n\">{s['n']:,}</span>"
            f"<span class=\"card-unit\">{escape(str(s['unit']))}</span>"
            f"<span class=\"card-detail\">{escape(str(s['detail']))}</span>{badge}"
            f"<span class=\"card-join\">{escape(join)}</span></li>"
        )
    return f'<ol class="map">{"".join(cards)}</ol>'


def findings(tables: dict[str, pd.DataFrame], mat: pd.DataFrame,
             facts: dict[str, object]) -> list[str]:
    checks = tables["chronology_checks"].set_index("rule")
    cov = lifecycle_coverage(tables["trial_timeline"])
    trials = tables["trial_level"]
    counts = trials["TRIAL_RECOMMENDATION"].value_counts()
    mismatch = int(checks.loc["Supplied recommendation differs from the inferred rule", "violations"])
    hidden = checks.loc["Rationale reports all four criteria met, yet not PASS"]
    gbv = checks.loc["Trial GBV mean differs from its observation-linked materials"]
    year = checks.loc["Operation dated outside its trial's start year"]
    return [
        f"<b>The scoring logic now ships as outcomes, not thresholds.</b> "
        f"<code>trial_recommendations_synthetic.csv</code> gives one verdict per trial (PASS "
        f"{counts.get('PASS', 0)}, HOLD {counts.get('HOLD', 0)}, FAIL {counts.get('FAIL', 0)}) "
        "with a text rationale and <code>RULE_VERSION = SYNTH_V1</code>, but no cut-points.",
        f"<b>Fixed thresholds reproduce every verdict</b> ({len(trials) - mismatch} of "
        f"{len(trials)}): FAIL if yield &lt; 7 t/ha or disease &gt; 7; PASS if yield ≥ 9, "
        "moisture ≤ 22%, disease ≤ 5, GBV mean ≥ ~102 and resistant materials ≥ 50%; otherwise "
        "HOLD. The comparison basis is a fixed target, not a check variety or trial mean.",
        f"<b>The rationale text hides one criterion.</b> {int(hidden['violations'])} of "
        f"{int(hidden['checked'])} trials whose rationale says all four criteria are met are HOLD, "
        "held back by the resistant-material share the text never mentions.",
        f"<b>The grain changed from line to trial.</b> Observations now carry no values: they only "
        f"link {mat['n_trials'].min()} to {mat['n_trials'].max()} trials to each line. The "
        "pedigree, breeding stage and <code>ADVANCEMENT_DECISION</code> of v1 are gone.",
        f"<b>Trial aggregates do not follow the recorded links.</b> The GBV mean differs from the "
        f"observation-linked lines in {int(gbv['violations'])} of {int(gbv['checked'])} trials; "
        "a block-of-10 mapping by line ID reproduces all of them.",
        f"<b>Operations ignore the trial calendar.</b> {int(year['violations'])} of "
        f"{int(year['checked'])} operations fall outside their trial's start year; all are dated "
        f"{facts['operation_months']}. Lab results (all {facts['lines']} lines) have no dates or "
        "trait names.",
        f"<b>Most trials cannot be told as a season.</b> Only {cov['placed']} of {cov['trials']} "
        f"trials have a planting record to anchor on, {cov['planting_and_harvest']} have both "
        f"planting and harvest, and {cov['in_order']} read in a plausible order (harvest after "
        "expected flowering). Every other trial-level value has no date at all.",
    ]


def meeting_briefing(tables: dict[str, pd.DataFrame],
                     stages: dict[str, dict[str, object]]) -> str:
    """Introduce the synthetic archive for newcomers and expose its audit trail."""
    trials = tables["trial_level"].set_index("TRIAL_ID")
    counts = trials["TRIAL_RECOMMENDATION"].value_counts()
    checks = tables["chronology_checks"].set_index("rule")
    gbv = checks.loc["Trial GBV mean differs from its observation-linked materials"]
    resistant = checks.loc["Trial resistant % differs from its observation-linked materials"]
    operations = checks.loc["Operation dated outside its trial's start year"]
    links = checks.loc["Operation's trial + material not linked in observations"]
    hidden = checks.loc["Rationale reports all four criteria met, yet not PASS"]
    match = checks.loc["Supplied recommendation differs from the inferred rule"]
    passing = trials.loc["SYN-TR-0003"]
    holding = trials.loc["SYN-TR-0037"]
    failing = trials.loc["SYN-TR-0001"]
    return f"""<section id="overview"><div class="section-head">
  <span class="eyebrow">Start here · plain language</span><h2>What is in this data?</h2>
  <p>This is a synthetic snapshot, not results from live breeding systems. A <b>line</b> is a
  candidate plant material; a <b>trial</b> tests a group of lines at one site. The supplied
  PASS / HOLD / FAIL label describes a <b>trial</b>, not a final decision about any line.</p></div>
  <ul class="findings">
  <li><b>What we have.</b> Seven files describe {stages['germplasm']['n']} lines,
  {stages['trials']['n']} trials, {stages['observations']['n']} trial-line links,
  {stages['genomics']['n']} genomic records, {stages['lab']['n']} lab results and
  {stages['operations']['n']} field operations. Each trial has one of
  {counts.get('PASS', 0)} PASS, {counts.get('HOLD', 0)} HOLD or {counts.get('FAIL', 0)} FAIL
  recommendations. <a href="#sources">Explore the sources</a>.</li>
  <li><b>What a verdict means.</b> {passing.name} is PASS (yield {passing['YIELD_T_HA']:g} t/ha,
  disease {passing['DISEASE_SCORE']:g}); {holding.name} is HOLD despite favourable wording.
  Its trial record reports {holding['RESISTANT_MATERIAL_PCT']:g}% resistant materials, below
  the reconstructed PASS target; this share does not reconcile to the linked lines.
  {failing.name} is FAIL with disease {failing['DISEASE_SCORE']:g}. The cut-points used to
  explain these labels are <b>inferred from the outcomes</b>, not a supplied scoring policy.
  <a href="#rule">See the rule</a>.</li>
  <li><b>What we cannot conclude.</b> The files give no yield or disease measurement for an
  individual line, no names or units for the lab traits, and no reliable trial chronology.
  The trial's genomic summary also does not match the lines linked to it. We cannot use a
  trial verdict as a line advancement decision. <a href="#expert">Review the evidence limits</a>.</li>
  </ul></section>
  <section id="expert"><div class="section-head">
  <span class="eyebrow">For technical readers · evidence audit</span>
  <h2>What can be joined, reproduced and trusted?</h2>
  <p>The counts below are checks on the supplied synthetic records. A reconstructed rule
  matching the records does not establish the SME's intended thresholds or make the
  underlying joins valid.</p></div>
  <ul class="findings">
  <li><b>Grain and provenance.</b> The {stages['observations']['n']} observation rows link
  trial and material IDs but contain no field-trait values. Yield, moisture, disease, height
  and flowering occur once per trial in the recommendation file; lab results join to material
  IDs but have no trial key, trait dictionary, units or dates.
  <a href="#sources">Source keys and counts</a>; <a href="#lab">lab detail</a>.</li>
  <li><b>Rule fit is not rule authority.</b> A fixed-threshold reconstruction agrees with
  {int(match['checked'] - match['violations'])}/{int(match['checked'])} supplied trial verdicts.
  {int(hidden['violations'])}/{int(hidden['checked'])} rationales stating all four named
  criteria are met still have a HOLD verdict: resistant-material share is omitted from the
  text. <a href="#thresholds">Inspect the observed threshold brackets</a> and
  <a href="tables/rule_intervals.csv">their source table</a>.</li>
  <li><b>Recorded links do not reproduce genomic summaries.</b> Trial GBV differs from the
  observation-linked lines in {int(gbv['violations'])}/{int(gbv['checked'])} trials; resistant
  share differs in {int(resistant['violations'])}/{int(resistant['checked'])}. An ID-ordered
  block of ten lines reproduces the supplied aggregates, but no file records that mapping;
  it is not a verified join. {int(links['violations'])}/{int(links['checked'])} operation
  trial-material pairs also lack an observation link.
  <a href="#reconciliation">See reconciliation</a> and
  <a href="tables/genomics_reconciliation.csv">trial-by-trial results</a>.</li>
  <li><b>Dates are not a season record.</b>
{int(operations['violations'])}/{int(operations['checked'])} operations are outside the
linked trial's start year. The
  operation dates and undated measurements cannot establish a reliable sequence or duration.
  <a href="#checks">Review all consistency checks</a> and
  <a href="tables/chronology_checks.csv">their denominators</a>.</li>
  </ul>
  <p class="note"><b>Questions for the UC4 expert:</b> What are the authoritative cut-points
  and bounds? Which lines produced the trial aggregates? What do the four lab traits mean?
  Is the intended crop maize? Until confirmed, none of these assumptions is a source fact.</p>
  </section>"""


def phase_table(pm: pd.DataFrame) -> pd.DataFrame:
    """One row per phase: the evidence columns with their fill, and the gap."""
    def evidence(g: pd.DataFrame) -> str:
        return "; ".join(f"{r.column} {r.present}/{r.total}" for r in g.itertuples())

    rows = [{"phase": g["phase"].iloc[0], "stage": g["stage_code"].iloc[0],
             "when": g["when"].iloc[0], "data (filled / total)": evidence(g),
             "gap": g["gap"].iloc[0]} for _, g in pm.groupby("order")]
    return pd.DataFrame(rows)


def example_narratives(tl: pd.DataFrame) -> str:
    """One narrative per verdict, preferring trials whose season can be placed."""
    items = []
    for verdict in ["PASS", "HOLD", "FAIL"]:
        pool = tl[tl["TRIAL_RECOMMENDATION"] == verdict].sort_values(
            ["no_planting", "no_harvest", "harvest_before_planting", "harvest_before_flowering",
             "TRIAL_ID"])
        if len(pool):
            items.append(f"<li>{escape(str(pool['narrative'].iloc[0]))}</li>")
    return f'<ul class="findings">{"".join(items)}</ul>'


def plant_lifecycle_section(fig: dict[str, Path], tables: dict[str, pd.DataFrame]) -> str:
    """The season view: phases, what describes them, and each trial placed on a season."""
    tl, pm = tables["trial_timeline"], tables["lifecycle_phase_map"]
    cov = lifecycle_coverage(tl)
    table = table_html(phase_table(pm), ["phase", "stage", "when", "data (filled / total)", "gap"],
                       set(), wrap={"data (filled / total)", "gap"})
    return f"""<section id="plant-lifecycle"><div class="section-head">
<span class="eyebrow">Plant lifecycle</span><h2>A season, phase by phase</h2>
<p>To say <i>what happened and when</i>, every value is placed on the crop's season: before
sowing, planting, vegetative growth, flowering, grain fill, harvest and the decision. The files
never name the crop; the trait ranges fit maize, so maize stage codes are used. Only operations
carry in-season dates, so each trial's season is counted in days from its first planting, and
flowering is placed at planting + <code>FLOWERING_DAYS</code>.</p></div>
{figure(fig["fig11_plant_lifecycle"])}
{table}
<p class="note"><b>{cov['placed']} of {cov['trials']} trials can be placed on a season.</b>
{cov['planting_and_harvest']} have both a planting and a harvest, and {cov['in_order']} of those
are harvested after expected flowering. The rest are described without dates, and the
assistant should say so rather than infer them.</p>
{figure(fig["fig12_trial_timelines"])}
<div class="section-head"><h3>What the assistant can say, one trial per verdict</h3>
<p>Generated from the timeline table; every trial has one in
<code>tables/trial_timeline.csv</code>.</p></div>
{example_narratives(tl)}
</section>"""


def stage_sections(fig: dict[str, Path]) -> str:
    """Prose and figures for each lifecycle stage, in pipeline order."""
    def sec(anchor: str, eyebrow: str, title: str, text: str, stems: list[str]) -> str:
        figs = "".join(figure(fig[s]) for s in stems)
        return (f'<section id="{anchor}"><div class="section-head"><span class="eyebrow">{eyebrow}'
                f"</span><h2>{title}</h2><p>{text}</p></div>{figs}</section>")

    return "".join([
        sec("rule", "Scoring", "The trial recommendation and its rule",
            "Each of the 72 trials carries a PASS, HOLD or FAIL, the trial-level values behind it "
            "and a rationale naming four criteria. Two knockouts (low yield, high disease) decide "
            "FAIL; five criteria together decide PASS. The cut-points are inferred: the file "
            "brackets them but does not state them.", ["fig02_rule_traits", "fig03_rule_paths"]),
        sec("genomics", "Sources", "Genomics",
            "New in v2: one genotyped sample per line with four marker calls, a genomic breeding "
            "value and QC. The trial file summarises these per trial.", ["fig06_genomics"]),
        sec("reconciliation", "Sources", "Do the trial aggregates trace back to lines?",
            "A breeder asking <i>why</i> a trial failed will want the lines behind it. The genomics "
            "aggregates can be rebuilt, but only from a mapping the files never record. The field "
            "aggregates (yield, moisture, disease, height, flowering) have no line-level source at "
            "all, because v2 observations carry no values.", ["fig07_reconciliation"]),
        sec("lab", "Sources", "Lab tests",
            "Lab results attach to a line, not a trial. Every line now has two or three, but "
            "names, units and dates are missing and the recommendation does not use them.",
            ["fig05_lab"]),
        sec("operations", "Sources", "Field operations",
            "Planting, irrigation and harvest only, with no quantities. The dates do not follow "
            "the trials they belong to.", ["fig08_operations_calendar"]),
    ])


def write_report(path: Path, figs: list[Path], tables: dict[str, pd.DataFrame],
                 mat: pd.DataFrame, stages: dict[str, dict[str, object]],
                 snapshot: pd.Timestamp, facts: dict[str, object]) -> Path:
    """Render the lifecycle report and return its path."""
    fig = {p.stem: p for p in figs}
    snap_text = f"{snapshot:%d %b %Y %H:%M}"
    checks = tables["chronology_checks"]
    items = "".join(f"<li>{f}</li>" for f in findings(tables, mat, facts))
    check_table = table_html(checks.assign(share=lambda d: d["share"].map("{:.0%}".format)),
                             ["stage", "rule", "checked", "violations", "share", "example"],
                             {"checked", "violations", "share"})
    intervals = tables["rule_intervals"]
    interval_table = table_html(intervals, ["criterion", "column", "test", "used", "bracket_low",
                                            "bracket_high"],
                                {"used", "bracket_low", "bracket_high"})
    html = f"""<title>UC4 Breeding Data Profile</title>
{FONTS}
<style>{CSS}</style>
<main>
<header>
  <span class="eyebrow">Hackathon 2026 · UC4 R&amp;D data source unification · v2 archive</span>
  <h1>Breeding trials, from line to recommendation</h1>
  <p>The seven synthetic UC4 files the SME sent on 29 Sep 2026, including the pre-configured
  trial recommendations: which lines, where they were tested, what the recommendation says, the
  rule that reproduces it, and whether the evidence traces back.</p>
  <div class="facts"><span><b>{facts["lines"]}</b> lines</span>
  <span><b>{facts["trials"]}</b> trials</span><span><b>{facts["sites"]}</b> sites</span>
  <span><b>{facts["years"]}</b></span>
  <span><b>{len(tables["trial_level"])}</b> trial verdicts</span>
  <span>synthetic, read-only</span></div>
  <nav class="toc"><a href="#overview">Overview</a><a href="#expert">Evidence audit</a>
  <a href="#plant-lifecycle">Season</a><a href="#sources">Sources</a>
  <a href="#rule">Rule</a><a href="#genomics">Genomics</a>
  <a href="#reconciliation">Reconciliation</a><a href="#lab">Lab</a><a href="#operations">Operations</a>
  <a href="#thresholds">Thresholds</a><a href="#checks">Checks</a><a href="#appendix">Appendix</a></nav>
</header>
<p class="note"><b>Inferred, not supplied.</b> The recommendation file states outcomes and a rule
version, not thresholds. The cut-points on this page are the simplest fixed values that
reproduce every outcome. Confirm them with the UC4 expert before presenting them as the rule.
The v1 (kickoff) profile is kept in <code>v1/report_v1.html</code>.</p>
{meeting_briefing(tables, stages)}
<section><h2>Key findings</h2><ul class="findings">{items}</ul></section>
{plant_lifecycle_section(fig, tables)}
<section id="sources"><div class="section-head"><h2>The sources in this data</h2>
<p>Seven files, with the record count in each and the key that links it. The badge counts
consistency rules that fail for that source.</p></div>
{lifecycle_map(stages, checks)}
</section>
{stage_sections(fig)}
<section id="thresholds"><div class="section-head"><span class="eyebrow">Scoring</span>
<h2>How tightly the data pins each cut-point</h2>
<p>Each threshold lies somewhere in its bracket: the lower bound is the value closest to the line
on one side, the upper bound on the other. <code>used</code> is the value this profile applies.
Plant height, days to flowering and genomics QC never change an outcome.</p></div>
{interval_table}
</section>
<section id="checks"><div class="section-head"><span class="eyebrow">Validation</span>
<h2>Consistency checks</h2>
<p>Operation rules test the record against the trial calendar and the extract
({snap_text}). Link and recommendation rules test whether trial-level values trace back to the
lines the files connect to the trial. For the demo, the assistant should surface these as
reasons for amber, not hide them.</p></div>
{figure(fig["fig09_consistency_checks"])}
{check_table}
</section>
<section id="appendix" class="appendix"><div class="section-head"><span class="eyebrow">Appendix</span>
<h2>File inventory and categorical detail</h2></div>
{figure(fig["fig01_inventory"])}
{figure(fig["fig04_categoricals"])}
</section>
<section><div class="section-head"><span class="eyebrow">Appendix</span>
<h2>Quantile bins</h2>
<p>Trial-level traits cut at their quartiles, and ordinal columns (genomic markers, verdict,
year, operation status) cut after rank encoding. With three levels, quantile edges tie and the
four bins collapse (<span class="pill tie">tied</span>). Use these bins descriptively only.</p></div>
{bins_html(tables["quantile_bins"])}
{figure(fig["fig10a_bins_numeric"])}
{figure(fig["fig10b_bins_categorical"])}
</section>
<section><div class="section-head"><span class="eyebrow">Appendix</span><h2>Numeric summary</h2>
<p>All numeric columns: trial-level traits, genomics and lab values. Lab traits have no
supplied unit.</p></div>
{table_html(tables["numeric_summary"], ["group", "count", "missing", "mean", "std", "min", "25%",
                                         "50%", "75%", "max"],
            {"count", "missing", "mean", "std", "min", "25%", "50%", "75%", "max"})}
</section>
<footer>Generated by analysis/uc4_eda/uc4_eda.py from the v2 UC4 archive in get_started/.
The data is synthetic. The thresholds are inferred from the SYNTH_V1 outcomes; nothing here is a
confirmed Syngenta scoring rule or a real breeding result. Row-level CSV links require the
adjacent tables/ folder when sharing this HTML on its own.</footer>
</main>"""
    path.write_text(html, encoding="utf-8")
    return path
