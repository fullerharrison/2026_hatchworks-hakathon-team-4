"""UC4 v3 profile: figures, inferred scoring rule, consistency checks, tables and a report.

Run: uv run --no-project --with pandas --with matplotlib python uc4_eda.py
Reads the supplied v3 zip (and the v2 zip, for the version diff) read-only; writes
figures/, tables/ and report.html here. Earlier outputs are kept in v1/ and v2/.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

import evidence_plots
import lifecycle_plots
import plots
from bin_cases import bins_table, fig_binning, numeric_cases, ordinal_cases
from lifecycle import chronology_checks, header_facts, snapshot_date, stage_counts
from load import (
    FIELD_TRAITS, TRAITS, V2_ZIP_NAME, align, find_zip, link_rates, load_tables, material_table,
)
from plant_lifecycle import phase_map, trial_timeline
from report import write_report
from rules import (
    apply_rule, criteria_flags, decision_by_verdict, field_reconciliation, genomics_reconciliation,
    threshold_intervals,
)
from style import apply_style
from versions import version_diff

HERE = Path(__file__).parent
TABLE_DIR = HERE / "tables"


def numeric_summary(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Summary of every numeric measurement column, one row per trait or lab trait."""
    rec = t["recommendations"]
    gen = t["genomics"]
    lab = t["lab"].assign(group=lambda d: "LAB " + d["TRAIT_GUID"].str[-2:])
    obs = t["observation"]
    series = {f"{c} [{TRAITS[c][1]}]": rec[c] for c in TRAITS}
    series |= {f"PLOT {c} [{TRAITS[c][1]}]":
               obs.loc[obs["TRAIT_CODE"] == c, "OBSERVATION_VALUE"] for c in FIELD_TRAITS}
    series |= {c: gen[c] for c in ["GENOMIC_BREEDING_VALUE", "QC_CALL_RATE_PCT"]}
    series |= {g: d["NUMBER_VALUE"] for g, d in lab.groupby("group")}
    rows = []
    for group, s in series.items():
        if s.count() == 0:
            continue  # e.g. a categorical lab trait: nothing numeric to summarise
        d = s.describe()
        rows.append({"group": group, "count": d["count"], "missing": int(s.isna().sum()),
                     **{k: d[k] for k in ["mean", "std", "min", "25%", "50%", "75%", "max"]}})
    return pd.DataFrame(rows).round(3)


def categorical_summary(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for table, col, _ in plots.CATEGORICALS:
        counts = plots.level_counts(t[table][col])
        for level, n in counts.items():
            rows.append({"table": table, "column": col, "level": level, "count": int(n),
                         "share": round(n / counts.sum(), 3)})
    return pd.DataFrame(rows)


def column_quality(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    frames = [plots.column_classes(df).rename("class").rename_axis("column").reset_index()
              .assign(table=k) for k, df in t.items()]
    return pd.concat(frames)[["table", "column", "class"]]


def trial_level(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Supplied trial verdicts next to the inferred rule's verdict and criterion flags."""
    rec = t["recommendations"]
    cols = ["TRIAL_ID", "START_YEAR", *TRAITS, "TRIAL_RECOMMENDATION", "RECOMMENDATION_RATIONALE"]
    return pd.concat([rec[cols], apply_rule(rec), criteria_flags(rec)], axis=1)


def main() -> None:
    apply_style()
    supplied = load_tables(find_zip())
    links = link_rates(supplied)
    diff = version_diff(load_tables(find_zip(name=V2_ZIP_NAME)), supplied)
    t = align(supplied)
    mat = material_table(t)
    rec = t["recommendations"]
    checks = chronology_checks(t)
    timeline, pm = trial_timeline(t), phase_map(t)
    field = field_reconciliation(t)
    figs = [
        plots.fig_inventory(supplied),
        plots.fig_rule_traits(rec),
        plots.fig_rule_paths(rec),
        plots.fig_categoricals(t),
        plots.fig_lab(t),
        plots.fig_genomics(t),
        plots.fig_reconciliation(t),
        lifecycle_plots.fig_operations_calendar(t),
        lifecycle_plots.fig_checks(checks),
        lifecycle_plots.fig_plant_lifecycle(pm),
        lifecycle_plots.fig_trial_timelines(t, timeline),
        evidence_plots.fig_links(links),
        evidence_plots.fig_field_traits(t["observation"]),
        evidence_plots.fig_field_reconciliation(field),
    ]
    num, cat = numeric_cases(t), ordinal_cases(t)
    figs.append(fig_binning(num, "fig10a_bins_numeric", "Quartile bins: trial-level traits",
                            "One value per trial, cut at 0 / .25 / .5 / .75 / 1. "
                            "Shaded bands alternate between bins.", ncols=4))
    figs.append(fig_binning(cat, "fig10b_bins_categorical",
                            "Quantile bins: ordinal columns after rank encoding",
                            "Three-level markers and verdicts cannot fill four bins. "
                            "Orange line = two or more quantiles on the same value.", ncols=4))
    TABLE_DIR.mkdir(exist_ok=True)
    tables = {
        "version_diff": diff,
        "link_rates": links,
        "field_reconciliation": field,
        "decision_by_verdict": decision_by_verdict(t),
        "chronology_checks": checks,
        "trial_timeline": timeline,
        "lifecycle_phase_map": pm,
        "trial_level": trial_level(t),
        "rule_intervals": threshold_intervals(rec),
        "genomics_reconciliation": genomics_reconciliation(t),
        "source_counts": pd.DataFrame(stage_counts(t)).T.rename_axis("source").reset_index(),
        "numeric_summary": numeric_summary(t),
        "categorical_summary": categorical_summary(t),
        "quantile_bins": bins_table(num + cat),
        "column_quality": column_quality(supplied),
        "material_level": mat,
    }
    for name, df in tables.items():
        df.to_csv(TABLE_DIR / f"{name}.csv", index=False)
    out = write_report(HERE / "report.html", figs, tables, mat, stage_counts(t), snapshot_date(t),
                       header_facts(t))
    print(f"{len(figs)} figures, {len(tables)} tables -> {out}")


if __name__ == "__main__":
    main()
