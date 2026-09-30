"""v3 evidence figures: recorded cross-file links and the new plot-level field traits
(figures 13 to 15)."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from load import FIELD_TRAITS, QUALITY_FLAGS, TRAITS
from style import BLUE, INK, INK_2, MUTED, NEUTRAL, SERIES, SURFACE, grid, headline, save, subtitle

RNG = np.random.default_rng(13)
# Reused categorical slots in fixed order: accepted = blue, review = amber, rejected = orange.
FLAG_COLORS = {"ACCEPTED": SERIES[0], "REVIEW": SERIES[3], "REJECTED": SERIES[1]}


def fig_links(links: pd.DataFrame) -> Path:
    """One bar per recorded link: share of distinct key values that resolve in the target."""
    d = links.iloc[::-1].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(11, 0.34 * len(d) + 1.6))
    colors = [BLUE if s == 1 else SERIES[1] if s > 0 else NEUTRAL for s in d["share"]]
    ax.barh(d.index, np.maximum(d["share"], 0.004), height=0.62, color=colors)
    for y, r in d.iterrows():
        ax.text(r["share"] + 0.012, y, f"{r['resolved']:,} of {r['distinct']:,}", va="center",
                fontsize=8, color=INK_2)
    ax.set_yticks(d.index, [f"{r['link']}  ·  {r['from']}" for _, r in d.iterrows()])
    ax.set_xlim(0, 1.15)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}" if v <= 1 else "")
    grid(ax, "x")
    broken = links.loc[links["share"] < 1, "link"].tolist()
    top = headline(fig, f"{int((links['share'] == 1).sum())} of {len(links)} recorded links "
                        "resolve fully",
                   "Share of distinct key values found in the target file. Broken: "
                   + ("; ".join(broken) if broken else "none") + ".")
    fig.tight_layout(rect=(0, 0, 1, top))
    return save(fig, "fig13_links")


def fig_field_traits(obs: pd.DataFrame) -> Path:
    """Plot-level values per field trait, split by quality flag."""
    fig, axes = plt.subplots(1, len(FIELD_TRAITS), figsize=(15, 4.2))
    for ax, code in zip(axes, FIELD_TRAITS):
        d = obs[obs["TRAIT_CODE"] == code]
        for i, flag in enumerate(QUALITY_FLAGS):
            v = d.loc[d["QUALITY_FLAG_LID"] == flag, "OBSERVATION_VALUE"]
            ax.scatter(i + RNG.uniform(-0.2, 0.2, len(v)), v, s=12, color=FLAG_COLORS[flag],
                       edgecolor=SURFACE, linewidth=0.6, zorder=3)
            if len(v):
                ax.plot([i - 0.28, i + 0.28], [v.median()] * 2, color=INK, linewidth=1.6, zorder=4)
        counts = d["QUALITY_FLAG_LID"].value_counts()
        ax.set_xticks(range(len(QUALITY_FLAGS)),
                      [f"{f.title()}\nn={counts.get(f, 0)}" for f in QUALITY_FLAGS])
        label, unit = TRAITS[code]
        ax.set_title(f"{label} ({unit})")
        subtitle(ax, f"{len(d)} plots · {d['TRIAL_GUID'].nunique()} trials")
        grid(ax)
    flags = obs["QUALITY_FLAG_LID"].value_counts()
    top = headline(fig, "Field traits now arrive per plot, with a quality flag",
                   f"{len(obs)} plot values: " + ", ".join(
                       f"{flags.get(f, 0)} {f.lower()}" for f in QUALITY_FLAGS)
                   + ". One dot per plot, bar = median.")
    fig.tight_layout(rect=(0, 0, 1, top), w_pad=2)
    return save(fig, "fig14_field_traits")


def fig_field_reconciliation(fr: pd.DataFrame) -> Path:
    """Supplied trial value vs the mean of its plots, one panel per field trait."""
    fig, axes = plt.subplots(1, len(FIELD_TRAITS), figsize=(15, 4.2))
    for ax, code in zip(axes, FIELD_TRAITS):
        d = fr[(fr["trait"] == code) & (fr["n_plots"] > 0)]
        ax.scatter(d["supplied"], d["plot_mean"], s=16, color=BLUE, edgecolor=SURFACE,
                   linewidth=0.6, zorder=3)
        lo = float(min(d["supplied"].min(), d["plot_mean"].min()))
        hi = float(max(d["supplied"].max(), d["plot_mean"].max()))
        ax.plot([lo, hi], [lo, hi], color=MUTED, linewidth=1, zorder=2)
        label, unit = TRAITS[code]
        ax.set_title(f"{label} ({unit})")
        subtitle(ax, f"{int(d['match'].sum())} of {len(d)} trials agree")
        ax.set_xlabel("supplied trial value")
        if code == FIELD_TRAITS[0]:
            ax.set_ylabel("mean of the trial's plots")
        grid(ax)
    checked = fr[fr["n_plots"] > 0]
    top = headline(fig, "Trial values do not come from the trial's own plots",
                   f"Grey line = perfect agreement. {int(checked['match'].sum())} of {len(checked)} "
                   "trial × trait pairs agree within rounding, with or without non-accepted plots.")
    fig.tight_layout(rect=(0, 0, 1, top), w_pad=2)
    return save(fig, "fig15_field_reconciliation")
