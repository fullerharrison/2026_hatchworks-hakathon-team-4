"""Descriptive and rule figures for the seven UC4 v2 tables (figures 1 to 7)."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.patches import Patch

from load import MARKERS, RECOMMENDATIONS, TRAITS, lab_trait_label
from rules import SYNTH_V1, criteria_flags, genomics_reconciliation
from style import (
    BLUE, INK, INK_2, MUTED, NEUTRAL, REC_COLORS, SERIES, SURFACE, grid, headline, save,
    subtitle,
)

BAR_H = 0.62
RNG = np.random.default_rng(4)

# Trait -> [(threshold, label)] drawn on the rule figure.
CUTS: dict[str, list[tuple[float, str]]] = {
    "YIELD_T_HA": [(SYNTH_V1.yield_knockout, "FAIL below"), (SYNTH_V1.yield_min, "PASS needs")],
    "MOISTURE_PCT": [(SYNTH_V1.moisture_max, "PASS needs ≤")],
    "DISEASE_SCORE": [(SYNTH_V1.disease_max, "PASS needs ≤"),
                      (SYNTH_V1.disease_knockout, "FAIL above")],
    "GENOMIC_BREEDING_VALUE_MEAN": [(SYNTH_V1.gbv_min, "PASS needs ≈")],
    "RESISTANT_MATERIAL_PCT": [(SYNTH_V1.resistant_min, "PASS needs")],
}


def column_classes(df: pd.DataFrame) -> pd.Series:
    """Classify each column: complete and varying, partly missing, constant or all null."""

    def classify(s: pd.Series) -> str:
        if s.isna().all():
            return "All null"
        if s.nunique(dropna=True) == 1:
            return "Constant"
        return "Partly missing" if s.isna().any() else "Complete, varying"

    return pd.Series({c: classify(df[c]) for c in df.columns})


def hbar(ax: Axes, counts: pd.Series, title: str, color: str = BLUE) -> None:
    """Horizontal count bars, largest first, value at the tip."""
    counts = counts.iloc[::-1]
    y = np.arange(len(counts))
    colors = [NEUTRAL if str(k) == "(missing)" else color for k in counts.index]
    ax.barh(y, counts.to_numpy(), height=BAR_H, color=colors)
    ax.set_yticks(y, [str(k) for k in counts.index])
    top = counts.max()
    for yi, v in zip(y, counts.to_numpy()):
        ax.text(v + top * 0.02, yi, f"{v:,}", va="center", fontsize=8, color=INK_2)
    ax.set_xlim(0, top * 1.18)
    ax.set_title(title)
    grid(ax, "x")


def vbar_labels(ax: Axes, xs: list, vals: list) -> None:
    """Value on each column cap, with headroom so labels clear the title."""
    top = max(vals)
    for x, v in zip(xs, vals):
        ax.text(x, v + top * 0.02, f"{v}", ha="center", va="bottom", fontsize=8, color=INK_2)
    ax.set_ylim(0, top * 1.15)


def fig_inventory(t: dict[str, pd.DataFrame]) -> Path:
    classes = ["Complete, varying", "Partly missing", "Constant", "All null"]
    tab = pd.DataFrame({k: column_classes(df).value_counts() for k, df in t.items()}).T
    tab = tab.reindex(columns=classes).fillna(0).astype(int)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.2), width_ratios=[1, 2.2])
    rows = pd.Series({k: len(df) for k, df in t.items()})
    hbar(a1, rows.sort_values(ascending=False), "Rows per file")
    order = rows.sort_values(ascending=False).index[::-1]
    left = np.zeros(len(order))
    for cls, color in zip(classes, SERIES):
        vals = tab.loc[order, cls].to_numpy()
        a2.barh(order, vals, left=left, height=BAR_H, color=color, label=cls,
                edgecolor=SURFACE, linewidth=1.5)
        left += vals
    for yi, total in enumerate(left):
        a2.text(total + 0.8, yi, f"{int(total)} cols", va="center", fontsize=8, color=INK_2)
    a2.set_title("What each column holds")
    a2.legend(ncol=4, loc="upper left", bbox_to_anchor=(0, -0.1))
    grid(a2, "x")
    wide = tab.loc[["germplasm", "trial"]]
    dead = int(wide[["Constant", "All null"]].to_numpy().sum())
    top = headline(fig, f"Seven synthetic CSVs, {rows.sum():,} rows",
                   f"Germplasm and trial keep their wide v1 headers, but {dead} of their "
                   f"{int(wide.to_numpy().sum())} columns are now empty or constant.")
    fig.tight_layout(rect=(0, 0, 1, top))
    return save(fig, "fig01_inventory")


def rule_strip(ax: Axes, rec: pd.DataFrame, code: str) -> None:
    """One dot per trial, by supplied recommendation, with the inferred cut-points."""
    label, unit = TRAITS[code]
    for i, r in enumerate(RECOMMENDATIONS):
        v = rec.loc[rec["TRIAL_RECOMMENDATION"] == r, code]
        ax.scatter(i + RNG.uniform(-0.18, 0.18, len(v)), v, s=22, color=REC_COLORS[r],
                   edgecolor=SURFACE, linewidth=1, zorder=3)
    for cut, text in CUTS.get(code, []):
        ax.axhline(cut, color=INK, linewidth=0.9, linestyle="--", zorder=2)
        ax.text(2.45, cut, f" {text} {cut:g}", va="center", fontsize=7, color=INK_2)
    counts = rec["TRIAL_RECOMMENDATION"].value_counts()
    ax.set_xticks(range(3), [f"{r.title()}\nn={counts.get(r, 0)}" for r in RECOMMENDATIONS])
    ax.set_xlim(-0.5, 3.4)
    ax.set_title(f"{label} ({unit})")
    subtitle(ax, "used by the rule" if code in CUTS else "not used by the rule")
    grid(ax)


def fig_rule_traits(rec: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(2, 4, figsize=(15, 7.6))
    for ax, code in zip(axes.flat, TRAITS):
        rule_strip(ax, rec, code)
    last = axes.flat[-1]
    counts = rec["TRIAL_RECOMMENDATION"].value_counts().reindex(RECOMMENDATIONS)
    last.bar(range(3), counts.to_numpy(), width=0.55, color=[REC_COLORS[r] for r in RECOMMENDATIONS])
    vbar_labels(last, list(range(3)), counts.tolist())
    last.set_xticks(range(3), [r.title() for r in RECOMMENDATIONS])
    last.set_title("Trials per supplied recommendation")
    subtitle(last, f"RULE_VERSION {rec['RULE_VERSION'].iloc[0]}")
    grid(last)
    fig.legend(handles=[Patch(color=REC_COLORS[r], label=r.title()) for r in RECOMMENDATIONS],
               loc="upper right", ncol=3, bbox_to_anchor=(0.99, 0.99))
    top = headline(fig, "The SME's trial recommendations and the thresholds that reproduce them",
                   "One dot per trial. Dashed lines are the inferred fixed cut-points; together "
                   "they reproduce all 72 supplied PASS / HOLD / FAIL outcomes.")
    fig.tight_layout(rect=(0, 0, 1, top), h_pad=2.5)
    return save(fig, "fig02_rule_traits")


def fig_rule_paths(rec: pd.DataFrame) -> Path:
    f = criteria_flags(rec)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.2), width_ratios=[1.4, 1])
    hold = f[rec["TRIAL_RECOMMENDATION"] == "HOLD"]
    names = {"yield_ok": "Yield ≥ 9", "moisture_ok": "Moisture ≤ 22", "disease_ok": "Disease ≤ 5",
             "gbv_ok": "GBV mean ≥ ~102", "resistant_ok": "Resistant ≥ 50% (not in rationale)"}
    missed = pd.Series({v: int((~hold[k]).sum()) for k, v in names.items()}).sort_values(
        ascending=False)
    hbar(a1, missed, "Why HOLD: PASS criteria each HOLD trial misses", REC_COLORS["HOLD"])
    subtitle(a1, f"{len(hold)} HOLD trials; one trial can miss several")
    fail = f[rec["TRIAL_RECOMMENDATION"] == "FAIL"]
    trig = pd.Series({
        "Yield < 7 only": int((fail["ko_yield"] & ~fail["ko_disease"]).sum()),
        "Disease > 7 only": int((fail["ko_disease"] & ~fail["ko_yield"]).sum()),
        "Both": int((fail["ko_yield"] & fail["ko_disease"]).sum()),
    })
    hbar(a2, trig, "Why FAIL: which knockout fired", REC_COLORS["FAIL"])
    subtitle(a2, f"{len(fail)} FAIL trials")
    only_res = int((~hold["resistant_ok"] & hold[["yield_ok", "moisture_ok", "disease_ok",
                                                   "gbv_ok"]].all(axis=1)).sum())
    top = headline(fig, "Decision paths: knockouts decide FAIL, five criteria decide PASS",
                   f"{only_res} HOLD trials meet every criterion the rationale text names and "
                   "are held only by the resistant-material share.")
    fig.tight_layout(rect=(0, 0, 1, top), w_pad=3)
    return save(fig, "fig03_rule_paths")


CATEGORICALS: list[tuple[str, str, str]] = [
    *[("genomics", c, c.removeprefix("MARKER_").replace("_", " ").title() + " marker")
      for c in MARKERS],
    ("genomics", "QC_STATUS_LID", "Genomics QC status"),
    ("trial", "START_YEAR", "Trial start year"),
    ("trial", "STATUS_LID", "Trial status"),
    ("recommendations", "TRIAL_RECOMMENDATION", "Supplied recommendation"),
    ("observation", "REPLICATION_NO", "Replication label"),
    ("operations", "OPERATION_STATUS_LID", "Operation status"),
    ("germplasm", "STATUS_LID", "Material status"),
]


def level_counts(s: pd.Series) -> pd.Series:
    return s.astype("string").fillna("(missing)").value_counts()


def ops_panel(ax: Axes, ops: pd.DataFrame) -> None:
    ct = pd.crosstab(ops["OPERATION_TYPE_LID"], ops["OPERATION_STATUS_LID"])
    ct = ct.loc[ct.sum(axis=1).sort_values().index, ["COMPLETED", "PLANNED"]]
    left = np.zeros(len(ct))
    for status, color in zip(ct.columns, SERIES):
        ax.barh(range(len(ct)), ct[status], left=left, height=BAR_H, color=color,
                label=status.title(), edgecolor=SURFACE, linewidth=1.5)
        left += ct[status].to_numpy()
    ax.set_yticks(range(len(ct)), [s.replace("_", " ").title() for s in ct.index])
    ax.set_xlim(0, left.max() * 1.1)
    ax.set_title("Operations by type and status")
    subtitle(ax, "operations · OPERATION_TYPE_LID × STATUS")
    ax.legend(loc="upper left", bbox_to_anchor=(0, -0.12), ncol=2)
    grid(ax, "x")


def fig_categoricals(t: dict[str, pd.DataFrame]) -> Path:
    fig, axes = plt.subplots(3, 4, figsize=(13, 8.8))
    for ax, (table, col, title) in zip(axes.flat, CATEGORICALS):
        hbar(ax, level_counts(t[table][col]), title)
        subtitle(ax, f"{table} · {col}")
    ops_panel(axes.flat[-1], t["operations"])
    top = headline(fig, "Categorical make-up",
                   "Genomic markers have three levels each; QC, trial status and material "
                   "status hold a single value. Grey = missing.")
    fig.tight_layout(rect=(0, 0, 1, top), h_pad=2.2, w_pad=2)
    return save(fig, "fig04_categoricals")


def fig_lab(t: dict[str, pd.DataFrame]) -> Path:
    lab = t["lab"].assign(TRAIT=lambda d: d["TRAIT_GUID"].map(lab_trait_label))
    traits = sorted(lab["TRAIT"].unique())
    fig, axes = plt.subplots(1, len(traits), figsize=(13, 4))
    for ax, trait in zip(axes, traits):
        d = lab[lab["TRAIT"] == trait]
        nums = d["NUMBER_VALUE"].dropna()
        ax.hist(nums, bins=np.arange(0, 21, 1.5), color=BLUE, edgecolor=SURFACE, linewidth=1.2)
        ax.axvline(nums.median(), color=INK, linewidth=0.9)
        ax.set_xlabel("NUMBER_VALUE (unit not supplied)")
        ax.set_title(trait)
        subtitle(ax, f"{len(d)} rows, {d['MATERIAL_GUID'].nunique()} materials · "
                     f"median {nums.median():.3g}")
        grid(ax)
    top = headline(fig, "Lab results by TRAIT_GUID",
                   f"Four unnamed numeric traits, each spread evenly over {lab['NUMBER_VALUE'].min():.0f}"
                   f" to {lab['NUMBER_VALUE'].max():.0f}. No trait dictionary, units or dates ship "
                   "with the data, and the rule does not use them.")
    fig.tight_layout(rect=(0, 0, 1, top))
    return save(fig, "fig05_lab")


def fig_genomics(t: dict[str, pd.DataFrame]) -> Path:
    gen = t["genomics"]
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), width_ratios=[1, 1, 1.2])
    for ax, col, title in [(axes[0], "GENOMIC_BREEDING_VALUE", "Genomic breeding value"),
                           (axes[1], "QC_CALL_RATE_PCT", "QC call rate (%)")]:
        v = gen[col]
        ax.hist(v, bins=16, color=BLUE, edgecolor=SURFACE, linewidth=1.2)
        ax.axvline(v.median(), color=INK, linewidth=0.9)
        ax.set_title(title)
        subtitle(ax, f"{len(v)} lines · {v.min():g} to {v.max():g}, median {v.median():.4g}")
        grid(ax)
    ax = axes[2]
    order = MARKERS["MARKER_DISEASE_RESISTANCE"]
    for i, lvl in enumerate(order):
        v = gen.loc[gen["MARKER_DISEASE_RESISTANCE"] == lvl, "GENOMIC_BREEDING_VALUE"]
        ax.scatter(i + RNG.uniform(-0.18, 0.18, len(v)), v, s=18, color=SERIES[i],
                   edgecolor=SURFACE, linewidth=0.8, zorder=3)
        ax.plot([i - 0.25, i + 0.25], [v.median()] * 2, color=INK, linewidth=2, zorder=4)
    ax.set_xticks(range(3), [f"{o.title()}\nn={(gen['MARKER_DISEASE_RESISTANCE'] == o).sum()}"
                             for o in order])
    ax.set_title("GBV by disease-resistance marker")
    subtitle(ax, "one dot per line, bar = median")
    grid(ax)
    top = headline(fig, "Genomics: one sample per line, all QC PASS",
                   "New in v2. The trial file's GBV mean and resistant share are built from these "
                   "values, but not from the lines the observations link to (figure 7).")
    fig.tight_layout(rect=(0, 0, 1, top), w_pad=2.5)
    return save(fig, "fig06_genomics")


def recon_panel(ax: Axes, recon: pd.DataFrame, supplied: str, prefix: str, title: str) -> None:
    lo, hi = recon[supplied].min(), recon[supplied].max()
    for name, color, marker in [("observation", SERIES[1], "o"), ("block", SERIES[2], "s")]:
        match = int(recon[f"{prefix.split('_')[0]}_match_{name}"].sum())
        ax.scatter(recon[supplied], recon[f"{prefix}_{name}"], s=20, color=color, marker=marker,
                   edgecolor=SURFACE, linewidth=0.8, zorder=3,
                   label=f"{name} links: {match}/{len(recon)} match")
    pad = (hi - lo) * 0.1
    ax.plot([lo - pad, hi + pad], [lo - pad, hi + pad], color=MUTED, linewidth=1, zorder=2)
    ax.set_xlabel(f"supplied {supplied}")
    ax.set_ylabel("recomputed from genomics")
    ax.set_title(title)
    ax.legend(loc="upper left", bbox_to_anchor=(0, -0.16), ncol=1)
    grid(ax)


def fig_reconciliation(t: dict[str, pd.DataFrame]) -> Path:
    recon = genomics_reconciliation(t)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 5.2))
    recon_panel(a1, recon, "GENOMIC_BREEDING_VALUE_MEAN", "gbv", "GBV mean per trial")
    recon_panel(a2, recon, "RESISTANT_MATERIAL_PCT", "resistant", "Resistant materials per trial (%)")
    top = headline(fig, "Trial aggregates do not come from the materials linked to the trial",
                   "Grey line = perfect agreement. Observation links reproduce no GBV mean; the "
                   "'block' mapping (trial k ↔ lines of block (k−1) mod 15) reproduces all 72.")
    fig.tight_layout(rect=(0, 0, 1, top), w_pad=3)
    return save(fig, "fig07_reconciliation")
