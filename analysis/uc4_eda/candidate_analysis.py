"""Current UC4 candidate analysis. Reads only the replacement ZIP, without repairs.

Legacy v3 helpers remain in load.py/rules.py for historical regression tests.
Run: python analysis/uc4_eda/uc4_eda.py
"""
from __future__ import annotations

import base64
import hashlib
import html
import re
import zipfile
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt

from style import apply_style

HERE = Path(__file__).resolve().parent
ZIP_PATH = HERE.parents[1] / "get_started" / "candidate_recommendations_synthetic.zip"
# The report and running app use the same reconstruction and policy implementation.
import sys
sys.path.insert(0, str(HERE.parents[1] / "app" / "src"))
from uc4_mcp.candidate_core import (FILES, KEYS, REQUIRED, load_current, audit_links,
    consistency, reconstruct, candidate_rule, thresholds, reason_precision_audit)


def distribution_tables(t: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Numeric and categorical profiles, retaining the different measurement grains."""
    numeric, categorical = [], []
    def describe(source, metric, unit, s):
        summary = s.describe()
        numeric.append(dict(source=source, metric=metric, unit=unit,
                            missing=int(s.isna().sum()), **summary.to_dict()))
    rec = t["recommendations"]
    units = {"N_TRIALS": "trials", "N_TRIALS_USED": "trials", "YIELD_VS_CHECK_PCT": "% of checks",
             "DISEASE_SCORE_MEAN": "score", "MOISTURE_PCT_MEAN": "%", "GERMINATION_PCT": "%",
             "FUMONISIN_PPM": "ppm", "GENOMIC_BREEDING_VALUE": "index"}
    for col, unit in units.items():
        describe("candidate summary", col, unit, rec[col])
    dictionary = t["dictionary"].set_index("TRAIT_GUID")
    for source in ["observation", "lab"]:
        for guid, df in t[source].groupby("TRAIT_GUID"):
            if guid in dictionary.index:
                describe(source, dictionary.loc[guid, "TRAIT_CODE"], dictionary.loc[guid, "UNIT"], df.NUMBER_VALUE)
    for col in ["GENOMIC_BREEDING_VALUE", "QC_CALL_RATE_PCT"]:
        describe("genomics", col, "%" if col == "QC_CALL_RATE_PCT" else "index", t["genomics"][col])
    describe("operation updates", "DELAY_DAYS", "days", t["operations"].DELAY_DAYS)
    for source, cols in {"recommendations": ["SYSTEM_RAG", "MARKER_DISEASE_RESISTANCE"],
                         "genomics": ["QC_STATUS_LID", "MARKER_DISEASE_RESISTANCE", "MARKER_DROUGHT_TOLERANCE", "MARKER_YIELD_POTENTIAL"],
                         "operations": ["OPERATION_TYPE_LID", "STATUS_LID", "RECORDED_VIA"],
                         "bridge": ["ENTRY_ROLE_LID"]}.items():
        for col in cols:
            for value, count in t[source][col].fillna("(missing)").value_counts().items():
                categorical.append(dict(source=source, column=col, level=value, count=int(count), share=count/len(t[source])))
    return pd.DataFrame(numeric), pd.DataFrame(categorical)


def create_figures(rec, means, ops, reconciliation, out: Path) -> list[Path]:
    apply_style()
    out.mkdir(exist_ok=True)
    paths = []
    colors = {"GREEN": "#1baf7a", "AMBER": "#eda100", "RED": "#eb6834"}
    def save(fig, name):
        p = out / f"{name}.png"
        fig.savefig(p, dpi=160, bbox_inches="tight")
        plt.close(fig)
        paths.append(p)
    fig, ax = plt.subplots(figsize=(8, 3))
    counts = rec.SYSTEM_RAG.value_counts().reindex(colors, fill_value=0)
    ax.barh(counts.index, counts.values, color=list(colors.values()))
    for i, n in enumerate(counts): ax.text(n + .7, i, str(n), va="center")
    ax.set(title="150 candidate recommendations", xlabel="Candidates", xlim=(0, 75))
    save(fig, "candidate_verdicts")
    fig, axes = plt.subplots(2, 3, figsize=(12, 6))
    for ax, col, boundary in zip(axes.flat, ["YIELD_VS_CHECK_PCT", "DISEASE_SCORE_MEAN", "MOISTURE_PCT_MEAN", "GERMINATION_PCT", "FUMONISIN_PPM", "N_TRIALS_USED"], [95, 6, 23, 90, 4, 2]):
        for label, color in colors.items():
            ax.hist(rec.loc[rec.SYSTEM_RAG == label, col].dropna(), bins=12, alpha=.5, label=label, color=color)
        ax.axvline(boundary, color="#52514e", linestyle="--")
        ax.set_title(col.replace("_", " "))
    axes.flat[0].legend()
    fig.suptitle("Candidate metrics; dashed lines show selected compatible cut-points")
    fig.tight_layout()
    save(fig, "candidate_metrics")
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.5))
    rec.N_TRIALS_USED.value_counts().sort_index().plot.bar(ax=axes[0], color="#2a78d6", rot=0)
    axes[0].set(title="Usable trials per candidate", xlabel="Usable trials", ylabel="Candidates")
    ops.groupby(["OPERATION_TYPE_LID", "STATUS_LID"]).size().unstack(fill_value=0).plot.barh(stacked=True, ax=axes[1])
    axes[1].set(title="Recorded operation status", ylabel="", xlabel="Operation updates")
    fig.tight_layout()
    save(fig, "candidate_coverage_operations")
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.5))
    for ax, col, rebuilt in [(axes[0], "YIELD_VS_CHECK_PCT", "REBUILT_YIELD_VS_CHECK_PCT"), (axes[1], "YIELD_VS_CHECK_PCT", "MEAN_TRIAL_RATIOS")]:
        x = rec[[col, rebuilt]].dropna()
        ax.scatter(x[col], x[rebuilt] - x[col], s=14, color="#2a78d6")
        ax.axhline(.05, ls="--", color="#eda100"); ax.axhline(-.05, ls="--", color="#eda100")
        ax.set(xlabel="Supplied yield vs checks (%)", ylabel="Rebuilt minus supplied (percentage points)")
    axes[0].set_title("Ratio of mean yields: source-compatible")
    axes[1].set_title("Mean trial ratios: different calculation")
    fig.tight_layout()
    save(fig, "candidate_yield_reconciliation")
    return paths


def report_text(t, rec, means, tables, figures, digest) -> str:
    def table(df): return df.to_html(index=False, escape=True, border=0)
    def figure(p):
        data = base64.b64encode(p.read_bytes()).decode()
        return f'<img alt="{html.escape(p.stem.replace("_", " "))}" src="data:image/png;base64,{data}">'
    samples = pd.concat([rec[rec.SYSTEM_RAG == c].head(1) for c in ["GREEN", "AMBER", "RED"]]
                        + [rec[rec.N_TRIALS_USED == 0].head(1)])
    samples = samples[["MATERIAL_ID", "SYSTEM_RAG", "SYSTEM_REASON", "CAVEATS", "_source_file", "_line_no"]]
    ops = t["operations"]
    rounded_disagree = rec[rec.SOURCE_RAG != rec.SYSTEM_RAG]
    mismatches = rec[rec.INFERRED_RAG != rec.SYSTEM_RAG]
    warnings = tables["reason_precision_audit"]
    precision_cases = warnings[~warnings.printed_warning_agrees | ~warnings.supplied_warning_agrees | ~warnings.rebuilt_warning_agrees]
    excluded = means.loc[means.EXCLUDED_IRRIGATION_MISSED, "TRIAL_GUID"].nunique()
    linked = int((tables["link_rates"].resolved == tables["link_rates"].distinct).sum())
    violations = int(tables["consistency_checks"].violations.sum())
    links = ''.join(f'<li><a href="tables/{name}.csv">{name.replace("_", " ")}</a></li>' for name in tables)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>UC4 replacement candidate analysis</title><style>
body{{font:16px/1.55 system-ui,sans-serif;color:#202820;background:#fcfcfb;max-width:1200px;margin:auto;padding:28px}}
h1,h2{{line-height:1.2}}a{{color:#175a97}}table{{border-collapse:collapse;font-size:13px;display:block;overflow:auto;margin:20px 0;max-height:650px}}
th,td{{padding:8px;border-bottom:1px solid #deded7;text-align:left}}th{{background:#eef1e9;position:sticky;top:0}}img{{max-width:100%;height:auto}}
.brief{{background:#edf4eb;border-left:5px solid #1baf7a;padding:18px}}code{{overflow-wrap:anywhere}}section{{margin:35px 0}}
</style></head><body><h1>UC4: evidence behind candidate recommendations</h1>
<p>Replacement delivery received 1 October 2026; fourth local delivery (source remarks say “integrated V2 (fixed)”). All data are synthetic.</p>
<nav><a href="#overview">Overview</a> · <a href="#sources">Sources and joins</a> · <a href="#reconcile">Reconstruction</a> · <a href="#rules">Scoring audit</a> · <a href="#operations">Operations</a> · <a href="#limits">Limits and questions</a> · <a href="#downloads">Audit tables</a></nav>
<section id="overview"><h2>What changed for the breeder</h2><div class="brief">
<p>The recommendation now belongs to a <strong>candidate line</strong>, rather than a trial. There are 150 recommendations: <strong>32 GREEN, 53 AMBER and 65 RED</strong>. GREEN indicates a candidate meeting the compatible field/lab criteria; AMBER needs review; RED fails a must-pass criterion. These remain system recommendations; all breeder decision/comment fields are blank.</p>
<p>The replacement supplies check varieties, a recorded trial-to-line bridge, named lab traits with units, and field measurements. Yield is compared with checks, replacing the old fixed absolute-yield rule. Two candidates have no field data and remain AMBER. The previous SYNTH_V1 rule and trial examples are historical.</p></div>
{figure(figures[0])}<h3>Examples with source citations</h3>{table(samples)}</section>
<section id="sources"><h2>Eight files, explicit recorded joins</h2>{table(tables['source_manifest'])}
<p>The 152 germplasm/genomics records cover 150 candidates plus two check varieties. The bridge has 1,296 TRIAL_ENTRY rows and 432 CHECK rows across 72 trials: three replicates, with six candidate entries and two checks per trial. Only 148 candidates appear in field trials. Each bridge entry has three trait measurements.</p>
<p>All {linked}/{len(tables['link_rates'])} audited key relationships resolve; {violations} violations across the identity and chronology checks. Membership resolution alone does not prove biological correctness. No positional GUID repairs or old-source metadata are used.</p>
{table(tables['link_rates'])}{table(tables['consistency_checks'])}
<p><strong>No trial master file is supplied.</strong> Trial IDs and GUIDs come from the bridge; field entity IDs are a separate key namespace. Location, trial year/status and exclusion policy are not supplied as trial attributes. Operation dates do not establish a trial's official status.</p></section>
<section id="reconcile"><h2>Do recommendations reproduce from the measurements?</h2>
<p>For each trial/material, average the three replicate observations. For checks, average the two check-variety yields within each trial. Exclude a trial if its recorded irrigation operation is MISSED. Average each candidate's remaining trial means with equal trial weight. Yield vs checks = 100 × mean candidate yield / mean corresponding check yield. Averaging the per-trial ratios gives a different answer.</p>
<p>This ratio-of-means calculation reproduces all 148 available yield comparisons within ±0.05 percentage points. Disease uses ±0.005 score units and moisture ±0.05 percentage points, reflecting the precision of the supplied candidate file. Lab germination and fumonisin join through the trait dictionary; genomic values and markers join directly by material GUID. Missing field values for the two untested lines are retained.</p>
{table(tables['metric_reconciliation'])}{figure(figures[3])}
<p>These methods are <strong>inferred from reproducibility</strong>, not a confirmed analysis protocol. Full unrounded reconstructed values, alternative mean-ratio results, original values and provenance are downloadable below.</p></section>
<section id="distributions"><h2>Trait distributions and completeness</h2>
<p>Summaries retain the source grain: candidate summaries, individual field measurements, material-level lab tests and genomic samples. They include cold-test vigour and genomic QC even though neither needs a gate to reproduce this snapshot's RAG.</p>
{table(tables['numeric_summary'])}{table(tables['categorical_summary'])}</section>
<section id="rules"><h2>Candidate scoring replaces SYNTH_V1</h2>
<p>A compatible rule reproduces {len(rec)-len(mismatches)}/150 supplied RAG values using the rounded candidate summary: RED for yield below 95%, disease above 6, or fumonisin above 4 ppm. Otherwise GREEN requires yield ≥103%, disease ≤4, moisture ≤23%, germination ≥90%, a non-susceptible disease marker and at least two usable trials; otherwise AMBER. No field data yields AMBER.</p>
<p>Supplied reasons state numeric targets/limits. The complete GREEN conjunction, precedence, equality behavior and no-data priority remain inferred. Moisture above 25% and germination below 85% are warnings rather than RED knockouts in the observed outcomes. Genomic breeding value and cold-test vigour require no gate to reproduce this snapshot; this does not establish their intended role.</p>
{table(tables['threshold_evidence'])}{figure(figures[1])}
<h3>Rounding audit</h3><p>Applying the same rule to reconstructed source precision differs from the supplied RAG for {len(rounded_disagree)} candidates. This is audited separately from matching the supplied rounded summary; equality at a displayed threshold can hide an underlying value on the other side.</p>
{table(rounded_disagree[['MATERIAL_ID','SYSTEM_RAG','INFERRED_RAG','SOURCE_RAG','DISEASE_SCORE_MEAN','REBUILT_DISEASE_SCORE_MEAN','MOISTURE_PCT_MEAN','REBUILT_MOISTURE_PCT_MEAN']])}
<p>Warning-level precision is audited separately: {len(precision_cases)} warnings have a printed, summary or reconstructed value that does not satisfy the stated comparison. Reasons can print a disease value of 6.0 as “above 6.0” because the reason uses one decimal while the candidate summary retains two. Such formatting is not a RAG mismatch; use the cited numeric record.</p>
{table(precision_cases)}
<h3>Supplied-summary rule mismatches</h3>{table(mismatches[['MATERIAL_ID','SYSTEM_RAG','INFERRED_RAG','SYSTEM_REASON']])}</section>
<section id="operations"><h2>Operational evidence changes usable coverage</h2>
<p>{excluded} trials have missed irrigation, accounting for the exclusion caveats on 30 candidates. There are 344 COMPLETED, 11 DELAYED and five MISSED operation updates. Delays affect fungicide spray and harvest; excluding these as well is not needed to reconstruct the supplied candidate summary. Record updates are evidence of what was reported, not independent proof that work occurred.</p>
{figure(figures[2])}{table(tables['excluded_trials'])}
<p>Lab dates and operational planned/actual/update dates are available. Plot observation dates, trial start/status/location metadata, pedigree and breeding stage are absent or unfilled; no breeding-cycle improvement can be measured.</p></section>
<section id="limits"><h2>Open questions and app migration impacts</h2><ol>
<li>Confirm the ratio-of-means calculation, equal trial weighting and exclusion of all candidates/check comparisons from a trial with missed irrigation.</li>
<li>Confirm the complete RAG rule, threshold equality and rounding policy, including moisture >25%, germination <85%, and no-field-data precedence.</li>
<li>Confirm whether genomic breeding value or cold-test vigour should affect RAG and whether the missing pedigree/stage/trial metadata is intentional.</li>
<li>Confirm use of the maize-like synthetic data for the vegetable-seed challenge.</li></ol>
<p>The running app now uses <strong>candidate-level recommendations</strong>, the shared reconstruction code and provisional RAG policy. Breeders can view and filter the full list, record ADVANCE/HOLD/DISCARD choices, and review enrichment before activating a new evidence revision. SQLite history preserves copied recommendations and source snapshots. Historical v2 decisions retain their original payload and trial scope; unrecorded snapshot identity remains unknown. The v2 demo is available only through its explicit historical launch option. Dataset reproduction does not replace SME confirmation of biological policy.</p>
<p>Earlier analyses are superseded: <a href="v1/report_v1.html">v1</a>, <a href="v2/report_v2.html">v2</a>, <a href="v3/report_v3.html">v3</a>. Previous ZIPs are retained as historical evidence and for the app dependency; none supplies evidence to this report.</p></section>
<section id="downloads"><h2>Reproducibility and downloadable evidence</h2>
<p>Source: <code>{ZIP_PATH.name}</code><br>SHA-256: <code>{digest}</code><br>Regenerate: <code>python analysis/uc4_eda/uc4_eda.py</code> (pandas and matplotlib required). Audit CSVs include source member names and CSV row numbers (header is line 1).</p><ul>{links}</ul>
</section></body></html>'''


def main() -> None:
    t = load_current()
    links, checks = audit_links(t), consistency(t)
    rec, means, reconciliation = reconstruct(t)
    numeric, categorical = distribution_tables(t)
    rec["INFERRED_RAG"] = candidate_rule(rec)
    source = rec.copy()
    for col in ["YIELD_VS_CHECK_PCT", "DISEASE_SCORE_MEAN", "MOISTURE_PCT_MEAN", "GERMINATION_PCT", "FUMONISIN_PPM", "GENOMIC_BREEDING_VALUE", "MARKER_DISEASE_RESISTANCE", "N_TRIALS_USED"]:
        source[col] = rec[f"REBUILT_{col}"]
    rec["SOURCE_RAG"] = candidate_rule(source)
    digest = hashlib.sha256(ZIP_PATH.read_bytes()).hexdigest()
    manifest = pd.DataFrame([dict(table=k, member=v._source_file.iloc[0], rows=len(v),
                                   columns=len(v.columns)-2, primary_key=KEYS[k], archive=ZIP_PATH.name,
                                   archive_sha256=digest) for k, v in t.items()])
    excluded = means.loc[means.EXCLUDED_IRRIGATION_MISSED, ["TRIAL_GUID", "TRIAL_ID"]].drop_duplicates()
    op_sources = t["operations"].loc[(t["operations"].OPERATION_TYPE_LID == "IRRIGATION") & (t["operations"].STATUS_LID == "MISSED")]
    trial_map = t["bridge"][["TRIAL_GUID", "FIELD_ENTITY_ID"]].drop_duplicates()
    excluded = excluded.merge(trial_map, on="TRIAL_GUID", validate="one_to_one").merge(
        op_sources, left_on="FIELD_ENTITY_ID", right_on="ATTACHED_TO_FIELD_ENTITY_ID", validate="one_to_one")
    provenance = []
    for k, df in t.items():
        refs = df[[KEYS[k], "_source_file", "_line_no"]].rename(columns={KEYS[k]: "source_key"}).assign(table=k)
        provenance.append(refs)
    tables = {"source_manifest": manifest, "link_rates": links, "consistency_checks": checks,
              "candidate_level": rec, "trial_material_means": means, "metric_reconciliation": reconciliation,
              "threshold_evidence": thresholds(), "excluded_trials": excluded,
              "reason_precision_audit": reason_precision_audit(rec),
              "source_provenance": pd.concat(provenance, ignore_index=True),
              "operation_updates": t["operations"], "trait_dictionary": t["dictionary"],
              "numeric_summary": numeric, "categorical_summary": categorical,
              "column_quality": pd.DataFrame([dict(table=k, column=c, missing=int(df[c].isna().sum()), distinct=int(df[c].nunique()))
                                               for k, df in t.items() for c in df.columns if not c.startswith("_")])}
    # v3 was archived before this generator was activated. Remove stale generated
    # files only in these two resolved output directories; never touch source ZIPs.
    for directory in [HERE / "tables", HERE / "figures"]:
        directory.mkdir(exist_ok=True)
        assert directory.resolve().parent == HERE
        for p in directory.iterdir():
            if p.is_file() and p.suffix in {".csv", ".png"}:
                p.unlink()
    for name, df in tables.items():
        df.to_csv(HERE / "tables" / f"{name}.csv", index=False)
    figures = create_figures(rec, means, t["operations"], reconciliation, HERE / "figures")
    out = HERE / "report.html"
    out.write_text(report_text(t, rec, means, tables, figures, digest), encoding="utf-8")
    print(f"{len(figures)} figures, {len(tables)} tables -> {out}")
    print(f"RAG summary rule matches: {(rec.INFERRED_RAG == rec.SYSTEM_RAG).sum()}/150; source-precision matches: {(rec.SOURCE_RAG == rec.SYSTEM_RAG).sum()}/150")


if __name__ == "__main__":
    main()
