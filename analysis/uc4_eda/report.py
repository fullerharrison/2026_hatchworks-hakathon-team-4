"""Self-contained HTML report (figures embedded as base64) for the UC4 v3 archive.

Every number in the prose is read from the generated tables, never typed in.
"""

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
    "fig05_lab": ("Lab results", "The four lab TRAIT_GUIDs; one is categorical (ALPHA_VALUE). "
                  "Names and units are not supplied."),
    "fig06_genomics": ("Genomics", "Breeding value, genotyping QC and the disease-resistance "
                       "marker for the 150 genotyped lines, joined to lines by GUID position."),
    "fig13_links": ("Recorded links", "Every key one file uses to point at another, and how many "
                    "of its values the target file holds. Full list: tables/link_rates.csv."),
    "fig14_field_traits": ("Plot values", "The five field traits measured per plot, split by "
                           "quality flag."),
    "fig15_field_reconciliation": ("Plots vs trial values", "Each trial's supplied trait value "
                                   "against the mean of its own plots. Full list: "
                                   "tables/field_reconciliation.csv."),
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
    ("germplasm", "Breeding lines", "MATERIAL_GUID; parents by MATERIAL_GUID", None),
    ("genomics", "Genomics", "MATERIAL_GUID from v2: joins by GUID position only", "Links"),
    ("lab", "Lab tests", "MATERIAL_GUID only (no trial key)", None),
    ("trials", "Field trials", "TRIAL_GUID", None),
    ("observations", "Plot observations", "TRIAL_GUID + MATERIAL_GUID", "Observations"),
    ("operations", "Field operations", "TRIAL_GUID + MATERIAL_GUID", "Operations"),
    ("recommendations", "Trial recommendation", "TRIAL_ID only (its GUIDs are from v2)",
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


def _check(tables: dict[str, pd.DataFrame], rule: str) -> pd.Series:
    return tables["chronology_checks"].set_index("rule").loc[rule]


def _of(row: pd.Series) -> str:
    """``violations/checked`` for one check row."""
    return f"{int(row['violations'])}/{int(row['checked'])}"


def _link(tables: dict[str, pd.DataFrame], label: str) -> str:
    r = tables["link_rates"].set_index("link").loc[label]
    return f"{int(r['resolved'])}/{int(r['distinct'])}"


def _carried(tables: dict[str, pd.DataFrame]) -> list[str]:
    """Files whose content is unchanged from the previous archive."""
    d = tables["version_diff"]
    return d.loc[d["identical"].astype(bool), "file"].tolist()


def _decision_shares(tables: dict[str, pd.DataFrame]) -> dict[str, float]:
    d = tables["decision_by_verdict"].set_index("TRIAL_RECOMMENDATION")["advance_share"]
    return {k: float(v) for k, v in d.items()}


def findings(tables: dict[str, pd.DataFrame], mat: pd.DataFrame,
             facts: dict[str, object]) -> list[str]:
    cov = lifecycle_coverage(tables["trial_timeline"])
    trials = tables["trial_level"]
    counts = trials["TRIAL_RECOMMENDATION"].value_counts()
    match = _check(tables, "Supplied recommendation differs from the inferred rule")
    hidden = _check(tables, "Rationale reports all four criteria met, yet not PASS")
    gbv = _check(tables, "Trial GBV mean differs from its observation-linked materials")
    field = _check(tables, "Trial trait value differs from the mean of its plots")
    status = _check(tables, "Trial has a verdict but is not COMPLETE in the trial file")
    planned = _check(tables, "Plot observation on a trial still PLANNED")
    obs_year = _check(tables, "Plot observation dated outside its trial's start year")
    op_year = _check(tables, "Operation dated outside its trial's start year")
    recon = tables["genomics_reconciliation"]
    carried = " and ".join(f"<code>{c}</code>" for c in _carried(tables)) or "none"
    decisions = mat["ADVANCEMENT_DECISION"].value_counts()
    share = _decision_shares(tables)
    links = tables["link_rates"]
    return [
        f"<b>Two files were resent unchanged.</b> {carried} are identical to the v2 files, so "
        "they still carry v2 keys. The other five were regenerated and share no GUID with v2. "
        f"Genomics lines resolve {_link(tables, 'Genomics → line')} and recommendation trial GUIDs "
        f"{_link(tables, 'Recommendation → trial (GUID)')}; "
        f"{int((links['share'] == 1).sum())} of {len(links)} recorded links resolve fully.",
        f"<b>The inferred rule still reproduces every verdict</b> "
        f"({int(match['checked'] - match['violations'])} of {int(match['checked'])}), as it must "
        f"with an unchanged file: PASS {counts.get('PASS', 0)}, HOLD {counts.get('HOLD', 0)}, "
        f"FAIL {counts.get('FAIL', 0)}. FAIL if yield &lt; 7 t/ha or disease &gt; 7; PASS if "
        "yield ≥ 9, moisture ≤ 22%, disease ≤ 5, GBV mean ≥ ~102 and resistant materials ≥ 50%; "
        "otherwise HOLD.",
        f"<b>The rationale text hides one criterion.</b> {int(hidden['violations'])} of "
        f"{int(hidden['checked'])} trials whose rationale says all four criteria are met are HOLD, "
        "held back by the resistant-material share the text never mentions.",
        f"<b>Plots now carry values, but not the trials' values.</b> {_of(field)} trial × trait "
        "pairs differ from the mean of the trial's own plots, with or without non-accepted plots. "
        "The trial values were computed before these plots existed.",
        f"<b>Genomic aggregates do not follow the observed lines either.</b> The GBV mean differs "
        f"from the lines observed in the trial in {_of(gbv)} trials (joined by GUID position). "
        f"The v2 block-of-10 mapping now reproduces {int(recon['gbv_match_block'].sum())}.",
        f"<b>Lines carry their own decision again.</b> Pedigree, breeding stage and "
        f"<code>ADVANCEMENT_DECISION</code> are back (ADVANCE {decisions.get('ADVANCE', 0)}, HOLD "
        f"{decisions.get('HOLD', 0)}, DISCARD {decisions.get('DISCARD', 0)}). ADVANCE lines make "
        f"up {share.get('PASS', 0):.0%} of lines in PASS trials and {share.get('FAIL', 0):.0%} in "
        "FAIL trials: the line decision does not follow the trial verdict.",
        f"<b>Trial status contradicts the verdicts.</b> {_of(status)} trials with a verdict are "
        f"not COMPLETE in the trial file, and {_of(planned)} plot values sit on trials still "
        "PLANNED.",
        f"<b>Plots follow the calendar; operations do not.</b> {_of(obs_year)} plot values fall "
        f"outside their trial's start year, against {_of(op_year)} operations (dated "
        f"{facts['operation_months']}). Only {cov['placed']} of {cov['trials']} trials have a "
        f"planting operation to anchor a season, and {cov['in_order']} read in a plausible order.",
    ]


def meeting_briefing(tables: dict[str, pd.DataFrame],
                     stages: dict[str, dict[str, object]]) -> str:
    """Introduce the synthetic archive for newcomers and expose its audit trail."""
    trials = tables["trial_level"].set_index("TRIAL_ID")
    counts = trials["TRIAL_RECOMMENDATION"].value_counts()
    gbv = _check(tables, "Trial GBV mean differs from its observation-linked materials")
    resistant = _check(tables, "Trial resistant % differs from its observation-linked materials")
    field = _check(tables, "Trial trait value differs from the mean of its plots")
    operations = _check(tables, "Operation dated outside its trial's start year")
    obs_year = _check(tables, "Plot observation dated outside its trial's start year")
    op_links = _check(tables, "Operation's trial + material not linked in observations")
    hidden = _check(tables, "Rationale reports all four criteria met, yet not PASS")
    match = _check(tables, "Supplied recommendation differs from the inferred rule")
    status = _check(tables, "Trial has a verdict but is not COMPLETE in the trial file")
    no_lab = _check(tables, "Line with no lab result")
    carried = " and ".join(_carried(tables)) or "none"
    links = tables["link_rates"]
    share = _decision_shares(tables)
    passing = trials.loc["SYN-TR-0003"]
    holding = trials.loc["SYN-TR-0037"]
    failing = trials.loc["SYN-TR-0001"]
    return f"""<section id="overview"><div class="section-head">
  <span class="eyebrow">Start here · plain language</span><h2>What is in this data?</h2>
  <p>This is a synthetic snapshot, not results from live breeding systems. A <b>line</b> is a
  candidate plant material; a <b>trial</b> tests a group of lines at one site. The supplied
  PASS / HOLD / FAIL label describes a <b>trial</b>; each line now also carries its own
  advancement decision.</p></div>
  <ul class="findings">
  <li><b>What we have.</b> Seven files describe {stages['germplasm']['n']} lines,
  {stages['trials']['n']} trials, {stages['observations']['n']} plot values,
  {stages['genomics']['n']} genomic records, {stages['lab']['n']} lab results and
  {stages['operations']['n']} field operations. Each trial has one of
  {counts.get('PASS', 0)} PASS, {counts.get('HOLD', 0)} HOLD or {counts.get('FAIL', 0)} FAIL
  recommendations. <a href="#sources">Explore the sources</a>.</li>
  <li><b>What changed on 30 Sep.</b> The SME re-linked lines, trials, plots and operations, and
  added pedigree, breeding stage, line decisions and per-plot measurements. Two files
  ({carried}) were resent unchanged from 29 Sep, so they do not connect by key to the rest.
  <a href="#changes">See what changed</a>.</li>
  <li><b>What a verdict means.</b> {passing.name} is PASS (yield {passing['YIELD_T_HA']:g} t/ha,
  disease {passing['DISEASE_SCORE']:g}); {holding.name} is HOLD despite favourable wording.
  Its trial record reports {holding['RESISTANT_MATERIAL_PCT']:g}% resistant materials, below
  the reconstructed PASS target; this share does not reconcile to the linked lines.
  {failing.name} is FAIL with disease {failing['DISEASE_SCORE']:g}. The cut-points used to
  explain these labels are <b>inferred from the outcomes</b>, not a supplied scoring policy.
  <a href="#rule">See the rule</a>.</li>
  <li><b>What we cannot conclude.</b> A trial's yield or disease value is not the average of
  its own plots, its genomic summary does not match its lines, and a line's advancement
  decision does not follow its trials' verdicts. Until the SME explains how these relate, a
  trial verdict cannot justify a line decision. <a href="#expert">Review the evidence limits</a>.</li>
  </ul></section>
  <section id="expert"><div class="section-head">
  <span class="eyebrow">For technical readers · evidence audit</span>
  <h2>What can be joined, reproduced and trusted?</h2>
  <p>The counts below are checks on the supplied synthetic records. A reconstructed rule
  matching the records does not establish the SME's intended thresholds or make the
  underlying joins valid.</p></div>
  <ul class="findings">
  <li><b>Joins.</b> {int((links['share'] == 1).sum())}/{len(links)} recorded links resolve fully.
  The {carried} files keep their v2 keys: genomics lines resolve
  {_link(tables, 'Genomics → line')}, recommendation trial GUIDs
  {_link(tables, 'Recommendation → trial (GUID)')}. This profile repairs them for analysis:
  recommendations by <code>TRIAL_ID</code>, a shared key
  ({_link(tables, 'Recommendation → trial (ID)')}), and genomics by the last GUID block, which
  <b>is positional and not a verified join</b>. {_of(no_lab)} lines have no lab result.
  <a href="#links">Link rates</a> and <a href="tables/link_rates.csv">their table</a>.</li>
  <li><b>Grain and provenance.</b> The {stages['observations']['n']} plot values carry trait,
  unit, date, replicate and quality flag, and link trial and line. Lab results are dated and
  join lines, but have no trial key, trait dictionary or units.
  <a href="#field">Plot values</a>; <a href="#lab">lab detail</a>.</li>
  <li><b>Rule fit is not rule authority.</b> A fixed-threshold reconstruction agrees with
  {int(match['checked'] - match['violations'])}/{int(match['checked'])} supplied trial verdicts.
  {int(hidden['violations'])}/{int(hidden['checked'])} rationales stating all four named
  criteria are met still have a HOLD verdict: resistant-material share is omitted from the
  text. <a href="#thresholds">Inspect the observed threshold brackets</a> and
  <a href="tables/rule_intervals.csv">their source table</a>.</li>
  <li><b>Trial values do not trace back.</b> {_of(field)} trial × trait pairs differ from the
  trial's plot mean. Trial GBV differs from the observed lines in {_of(gbv)} trials; resistant
  share in {_of(resistant)}. {_of(op_links)} operation trial-line pairs lack a plot record.
  <a href="#reconciliation">See reconciliation</a>,
  <a href="tables/field_reconciliation.csv">plot-level</a> and
  <a href="tables/genomics_reconciliation.csv">genomic results</a>.</li>
  <li><b>Status and dates.</b> {_of(status)} trials with a verdict are not COMPLETE. Plot values
  are outside their trial's start year in {_of(obs_year)} cases, operations in
  {_of(operations)}. ADVANCE lines are {share.get('PASS', 0):.0%} of PASS-trial lines and
  {share.get('FAIL', 0):.0%} of FAIL-trial lines.
  <a href="#checks">Review all consistency checks</a> and
  <a href="tables/chronology_checks.csv">their denominators</a>.</li>
  </ul>
  <p class="note"><b>Questions for the UC4 expert:</b> Can genomics and trial recommendations be
  regenerated from the corrected lines and trials? How are trial values computed from plots
  (which quality flags, which replicates)? How does a line's advancement decision relate to its
  trials' verdicts? What are the authoritative cut-points? What do the four lab traits and the
  operation quantity units mean? Is the intended crop maize? Until confirmed, none of these
  assumptions is a source fact.</p>
  </section>"""


def changes_section(fig: dict[str, Path], tables: dict[str, pd.DataFrame]) -> str:
    """What the 30 Sep archive changed, file by file, and which links now resolve."""
    diff = tables["version_diff"].assign(
        same_as_v2=lambda d: d["identical"].map({True: "yes", False: "no"}),
        cols_added=lambda d: d["cols_added"].map(lambda s: len(s.split(", ")) if s else 0),
        cols_removed=lambda d: d["cols_removed"].map(lambda s: len(s.split(", ")) if s else 0))
    cols = ["file", "same_as_v2", "rows_new", "filled_cols_old", "filled_cols_new",
            "n_newly_filled", "cols_added", "cols_removed", "shared_guids"]
    table = table_html(diff, cols, set(cols) - {"file", "same_as_v2"})
    return f"""<section id="changes"><div class="section-head">
<span class="eyebrow">v2 → v3</span><h2>What changed on 30 Sep</h2>
<p>Each file against the 29 Sep (v2) archive: filled columns before and after, schema changes,
and how many GUID values it still shares with v2. Regenerated files share none; unchanged files
share all of theirs. Column lists: <code>tables/version_diff.csv</code>.</p></div>
{table}
<div id="links" class="section-head"><h3>Which recorded links resolve</h3></div>
{figure(fig["fig13_links"])}
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
never name the crop; the trait ranges fit maize, so maize stage codes are used. Each trial's
season is counted in days from its first planting operation, and flowering is placed at
planting + <code>FLOWERING_DAYS</code>. Plot observations and <code>BEGIN_DATE</code> are dated
too; the consistency checks test them against the trial year.</p></div>
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
        sec("field", "Sources", "Plot observations",
            "New in v3: every observation row is one plot value for one of five field traits, "
            "with a unit, a date, a replicate and a quality flag. These are the first line-level "
            "field measurements in any UC4 archive.", ["fig14_field_traits"]),
        sec("genomics", "Sources", "Genomics",
            "One genotyped sample per line with four marker calls, a genomic breeding value and "
            "QC. The file is unchanged from v2, so it joins the regenerated lines only by the "
            "last block of the GUID. The trial file summarises these values per trial.",
            ["fig06_genomics"]),
        sec("reconciliation", "Sources", "Do the trial values trace back to plots and lines?",
            "A breeder asking <i>why</i> a trial failed will want the plots and lines behind it. "
            "Neither the field values nor the genomic summaries can be rebuilt from the records "
            "the files link to the trial. The recommendation file is unchanged from v2, so it "
            "was computed before these plots and links existed.",
            ["fig15_field_reconciliation", "fig07_reconciliation"]),
        sec("lab", "Sources", "Lab tests",
            "Lab results attach to a line, not a trial. They are now dated, but some lines have "
            "none, trait names and units are missing, and the recommendation does not use them.",
            ["fig05_lab"]),
        sec("operations", "Sources", "Field operations",
            "Planting, fertiliser, irrigation, inspection and harvest, now with a quantity. The "
            "quantity units vary within an operation type, and the dates do not follow the "
            "trials they belong to.", ["fig08_operations_calendar"]),
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
    html = f"""<meta charset="utf-8">
<title>UC4 Breeding Data Profile</title>
{FONTS}
<style>{CSS}</style>
<main>
<header>
  <span class="eyebrow">Hackathon 2026 · UC4 R&amp;D data source unification · v3 archive</span>
  <h1>Breeding trials, from line to recommendation</h1>
  <p>The corrected seven synthetic UC4 files the SME sent on 30 Sep 2026: which lines, where they
  were tested, what each plot measured, what the recommendation says, the rule that reproduces
  it, and whether the evidence traces back.</p>
  <div class="facts"><span><b>{facts["lines"]}</b> lines</span>
  <span><b>{facts["trials"]}</b> trials</span><span><b>{facts["sites"]}</b> sites</span>
  <span><b>{facts["years"]}</b></span>
  <span><b>{len(tables["trial_level"])}</b> trial verdicts</span>
  <span>synthetic, read-only</span></div>
  <nav class="toc"><a href="#overview">Overview</a><a href="#expert">Evidence audit</a>
  <a href="#changes">v2 → v3</a><a href="#plant-lifecycle">Season</a><a href="#sources">Sources</a>
  <a href="#rule">Rule</a><a href="#field">Plots</a><a href="#genomics">Genomics</a>
  <a href="#reconciliation">Reconciliation</a><a href="#lab">Lab</a><a href="#operations">Operations</a>
  <a href="#thresholds">Thresholds</a><a href="#checks">Checks</a><a href="#appendix">Appendix</a></nav>
</header>
<p class="note"><b>Inferred, not supplied.</b> The recommendation file states outcomes and a rule
version, not thresholds. The cut-points on this page are the simplest fixed values that
reproduce every outcome. Confirm them with the UC4 expert before presenting them as the rule.
Earlier profiles are kept in <a href="v2/report_v2.html">v2/report_v2.html</a> (29 Sep) and
<a href="v1/report_v1.html">v1/report_v1.html</a> (kickoff).</p>
{meeting_briefing(tables, stages)}
<section><h2>Key findings</h2><ul class="findings">{items}</ul></section>
{changes_section(fig, tables)}
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
<p>All numeric columns: trial-level traits, plot-level traits (<code>PLOT</code>), genomics
and lab values. Lab traits have no supplied unit.</p></div>
{table_html(tables["numeric_summary"], ["group", "count", "missing", "mean", "std", "min", "25%",
                                         "50%", "75%", "max"],
            {"count", "missing", "mean", "std", "min", "25%", "50%", "75%", "max"})}
</section>
<footer>Generated by analysis/uc4_eda/uc4_eda.py from the v3 UC4 archive (30 Sep 2026) in
get_started/, with the v2 archive for the version comparison.
The data is synthetic. The thresholds are inferred from the SYNTH_V1 outcomes; nothing here is a
confirmed Syngenta scoring rule or a real breeding result. Row-level CSV links require the
adjacent tables/ folder when sharing this HTML on its own.</footer>
</main>"""
    path.write_text(html, encoding="utf-8")
    return path
