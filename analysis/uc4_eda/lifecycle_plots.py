"""Calendar and consistency-check figures (figures 8 and 9)."""

from __future__ import annotations

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

from lifecycle import OPERATION_ORDER, operations_with_trial, snapshot_date
from style import BLUE, INK, INK_2, MUTED, NEUTRAL, SERIES, SURFACE, grid, headline, save

OP_STATUS_COLORS = {"COMPLETED": SERIES[0], "PLANNED": SERIES[1]}
OP_MARKERS = {"PLANTING": "o", "IRRIGATION": "s", "HARVEST": "^"}


def fig_operations_calendar(t: dict[str, pd.DataFrame]) -> Path:
    ops = operations_with_trial(t)
    snap = snapshot_date(t)
    rng = np.random.default_rng(7)
    fig, ax = plt.subplots(figsize=(12, 4.8))
    years = sorted(ops["START_YEAR"].unique())
    for op in OPERATION_ORDER:
        for status, c in OP_STATUS_COLORS.items():
            d = ops[(ops["OPERATION_TYPE_LID"] == op) & (ops["OPERATION_STATUS_LID"] == status)]
            y = d["START_YEAR"].map({yr: i for i, yr in enumerate(years)})
            ax.scatter(d["date"], y + rng.uniform(-0.3, 0.3, len(d)), s=22, color=c,
                       marker=OP_MARKERS[op], edgecolor=SURFACE, linewidth=0.8, zorder=3)
    ax.axvline(snap, color=INK, linewidth=1)
    ax.text(snap, len(years) - 0.45, f" extract {snap:%d %b %Y}", fontsize=8, color=INK_2)
    ax.set_yticks(range(len(years)), [f"{y} trials" for y in years])
    ax.set_ylim(-0.6, len(years) - 0.3)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    grid(ax, "x")
    handles = [Line2D([], [], color=c, marker="o", linestyle="none", label=s.title())
               for s, c in OP_STATUS_COLORS.items()]
    handles += [Line2D([], [], color=MUTED, marker=m, linestyle="none", label=o.title())
                for o, m in OP_MARKERS.items()]
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(0, -0.1), ncol=5)
    wrong = int((ops["date"].dt.year != ops["START_YEAR"]).sum())
    past_planned = int(((ops["OPERATION_STATUS_LID"] == "PLANNED") & (ops["date"] < snap)).sum())
    top = headline(fig, "Operations: every date falls in April to September 2026",
                   f"Rows = trial start year. {wrong} of {len(ops)} operations sit outside their "
                   f"trial's year, and all {past_planned} PLANNED operations are already in the past.")
    fig.tight_layout(rect=(0, 0, 1, top))
    return save(fig, "fig08_operations_calendar")


def fig_checks(checks: pd.DataFrame) -> Path:
    rows: list[tuple[str, object]] = []
    for stage, grp in checks.groupby("stage", sort=False):
        rows.append(("stage", stage))
        rows.extend(("rule", r) for r in grp.itertuples())
    fig, ax = plt.subplots(figsize=(11, 0.36 * len(rows) + 1.3))
    ys = np.arange(len(rows))[::-1]
    labels = []
    for y, (kind, item) in zip(ys, rows):
        if kind == "stage":
            ax.text(-0.01, y - 0.15, str(item).upper(), transform=ax.get_yaxis_transform(),
                    ha="right", fontsize=7.5, color=MUTED, fontweight="semibold")
            labels.append("")
            continue
        r = item
        ax.barh(y, max(r.share, 0.004), height=0.62, color=BLUE if r.violations else NEUTRAL)
        ax.text(r.share + 0.012, y, f"{r.violations:,} of {r.checked:,}", va="center", fontsize=8,
                color=INK_2)
        labels.append(r.rule)
    ax.set_yticks(ys, labels)
    ax.set_xlim(0, 1.12)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}" if v <= 1 else "")
    grid(ax, "x")
    ax.tick_params(axis="y", length=0)
    failing = int((checks["violations"] > 0).sum())
    top = headline(fig, "Consistency checks on the v2 record",
                   f"Share of checkable records that break each rule. {failing} of {len(checks)} "
                   "rules fail somewhere; the inferred rule matches every supplied verdict.")
    fig.tight_layout(rect=(0, 0, 1, top))
    return save(fig, "fig09_consistency_checks")
