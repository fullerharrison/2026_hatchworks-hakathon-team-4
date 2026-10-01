"""UC4 current candidate profile; old v3 helpers retained for regression tests.

Run: python analysis/uc4_eda/uc4_eda.py
Reads only candidate_recommendations_synthetic.zip; writes figures/, tables/ and
report.html here. Only the current generated report and assets are retained.
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
    """Generate the replacement candidate analysis; legacy helpers remain importable."""
    from candidate_analysis import main as candidate_main
    candidate_main()


if __name__ == "__main__":
    main()
