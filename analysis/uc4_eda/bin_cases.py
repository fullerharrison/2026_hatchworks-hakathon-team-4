"""Quantile-binning cases for UC4: trial-level numeric traits and ordinal columns.

v3 germplasm has nominal attributes again (generation, stage...), but the v1
target-encoded nominal cases are not restored: the trial verdict they were encoded
against does not follow the line (see ``rules.decision_by_verdict``).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.axes import Axes

from binning import QUANTILES, BinResult, ordinal_encode, quantile_bin
from load import MARKERS, TRAITS
from style import BLUE, INK, INK_2, SERIES, SURFACE, grid, headline, save, subtitle

BAND = "#e8f0fa"

# (table, column, explicit order). Marker orders are assumptions to confirm.
ORDINALS: list[tuple[str, str, list[object]]] = [
    *[("genomics", col, list(order)) for col, order in MARKERS.items()],
    ("recommendations", "TRIAL_RECOMMENDATION", ["FAIL", "HOLD", "PASS"]),
    ("trial", "START_YEAR", [2024, 2025, 2026]),
    ("operations", "OPERATION_STATUS_LID", ["PLANNED", "COMPLETED"]),
]


@dataclass
class BinCase:
    """One column prepared for quantile binning.

    ``levels`` maps each category to its encoded value (empty for numeric traits).
    """

    table: str
    column: str
    method: str
    values: pd.Series
    levels: dict[str, float]
    result: BinResult


def numeric_cases(t: dict[str, pd.DataFrame]) -> list[BinCase]:
    rec = t["recommendations"]
    cases = []
    for code in TRAITS:
        v = rec[code].reset_index(drop=True)
        cases.append(BinCase("recommendations", code, "numeric (per trial)", v, {},
                             quantile_bin(v)))
    return cases


def ordinal_cases(t: dict[str, pd.DataFrame]) -> list[BinCase]:
    cases = []
    for table, col, order in ORDINALS:
        v = ordinal_encode(t[table][col], order)
        levels = {str(level): float(rank) for rank, level in enumerate(order, start=1)}
        cases.append(BinCase(table, col, "ordinal rank", v, levels, quantile_bin(v)))
    return cases


def level_bins(case: BinCase) -> dict[str, str]:
    """Which quantile bin each category falls into (Q1 = lowest)."""
    edges = case.result.edges
    out = {}
    for level, x in case.levels.items():
        idx = int(np.searchsorted(edges[1:-1], x, side="left")) + 1 if len(edges) > 2 else 1
        out[level] = f"Q{idx}"
    return out


def bins_table(cases: list[BinCase]) -> pd.DataFrame:
    rows = []
    for c in cases:
        r = c.result
        rows.append({
            "table": c.table, "column": c.column, "method": c.method,
            "n": int(c.values.notna().sum()), "n_missing": r.n_missing,
            **{f"q{q:g}": round(e, 4) for q, e in zip(QUANTILES, r.raw_edges)},
            "n_bins": r.n_bins, "collapsed": r.collapsed,
            "bin_counts": "/".join(map(str, r.counts)),
            "level_to_bin": "; ".join(f"{k}->{b}" for k, b in level_bins(c).items()),
        })
    return pd.DataFrame(rows)


def edge_lines(ax: Axes, r: BinResult) -> None:
    """Draw each distinct edge once; tied quantiles share one labelled line."""
    tally: dict[float, int] = {}
    for e in r.raw_edges:
        tally[round(e, 9)] = tally.get(round(e, 9), 0) + 1
    for e, k in tally.items():
        ax.axvline(e, color=SERIES[1] if k > 1 else INK, linewidth=1.6 if k > 1 else 0.8,
                   zorder=2)


def bin_bands(ax: Axes, r: BinResult) -> None:
    """Shade alternate bins and name them Q1..Qk along the top of the panel."""
    for i, (lo, hi) in enumerate(zip(r.edges[:-1], r.edges[1:])):
        if i % 2 == 0:
            ax.axvspan(lo, hi, color=BAND, zorder=0, linewidth=0)
        ax.text((lo + hi) / 2, 0.97, f"Q{i + 1}", transform=ax.get_xaxis_transform(),
                ha="center", va="top", fontsize=7.5, color=INK_2, fontweight="semibold")


def draw_levels(ax: Axes, c: BinCase) -> None:
    """One row per category: dot at its encoded value, with size and assigned bin."""
    counts = c.values.value_counts()
    bins = level_bins(c)
    names = list(c.levels)
    xs = np.array([c.levels[n] for n in names])
    ys = np.arange(len(names))
    ax.scatter(xs, ys, s=70, color=BLUE, edgecolor=SURFACE, linewidth=2, zorder=3)
    for n, x, y in zip(names, xs, ys):
        ax.annotate(f"n={counts.get(c.levels[n], 0)} → {bins[n]}", (x, y), xytext=(8, 0),
                    textcoords="offset points", va="center", fontsize=7.5, color=INK_2,
                    zorder=4, bbox={"boxstyle": "square,pad=0.15", "fc": SURFACE, "ec": "none"})
    ax.set_yticks(ys, names)
    ax.set_ylim(-0.7, len(names) - 0.1)
    span = max(xs.max() - xs.min(), 1e-9)
    ax.set_xlim(xs.min() - span * 0.12, xs.max() + span * 0.45)
    ax.spines["left"].set_visible(False)


def draw_case(ax: Axes, c: BinCase) -> None:
    r = c.result
    if c.levels:
        draw_levels(ax, c)
    else:
        ax.hist(c.values.dropna(), bins=16, color=BLUE, edgecolor=SURFACE, linewidth=1, zorder=1)
        ax.set_ylim(0, ax.get_ylim()[1] * 1.2)
        ax.set_xlabel(TRAITS[c.column][1])
        grid(ax)
    bin_bands(ax, r)
    edge_lines(ax, r)
    status = f"tied edges, {r.n_bins} of 4 bins" if r.collapsed else "4 bins"
    ax.set_title(TRAITS[c.column][0] if c.column in TRAITS else c.column, fontsize=9)
    subtitle(ax, f"{c.method} · {status} · per bin {'/'.join(map(str, r.counts))}")


def fig_binning(cases: list[BinCase], name: str, title: str, sub: str, ncols: int = 3) -> Path:
    nrows = int(np.ceil(len(cases) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.6 * ncols, 3.0 * nrows + 0.9),
                             squeeze=False)
    for ax, c in zip(axes.flat, cases):
        draw_case(ax, c)
    for ax in list(axes.flat)[len(cases):]:
        ax.axis("off")
    top = headline(fig, title, sub)
    fig.tight_layout(rect=(0, 0, 1, top), h_pad=2.4, w_pad=2.4)
    return save(fig, name)
