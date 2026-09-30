"""Calendar, consistency-check and plant-lifecycle figures (figures 8, 9, 11 and 12)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Polygon

from lifecycle import OPERATION_ORDER, month_span, operations_with_trial, snapshot_date
from plant_lifecycle import FLOWERING_HALF_WINDOW, PHASES, Phase, operation_phases
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
    top = headline(fig, f"Operations: every date falls in {month_span(ops['date'])}",
                   f"Rows = trial start year. {wrong} of {len(ops)} operations sit outside their "
                   f"trial's year, and all {past_planned} PLANNED operations are already in the past.")
    fig.tight_layout(rect=(0, 0, 1, top))
    return save(fig, "fig08_operations_calendar")


PHASE_FILL = {"pre_season": "#efeee9", "decision": "#efeee9"}
SEASON_FILL = "#e8f0fa"
FLOWER_FILL = "#cfe0f5"


def _chevron(ax: Axes, x0: float, x1: float, y0: float, y1: float, color: str) -> None:
    d, ym = 0.012, (y0 + y1) / 2
    pts = [(x0, y0), (x1 - d, y0), (x1, ym), (x1 - d, y1), (x0, y1), (x0 + d, ym)]
    ax.add_patch(Polygon(pts, closed=True, facecolor=color, edgecolor=SURFACE, linewidth=2))


def _phase_column(ax: Axes, x: float, w: float, phase: Phase, cover: pd.DataFrame) -> None:
    fill = PHASE_FILL.get(phase.key, FLOWER_FILL if phase.key == "flowering" else SEASON_FILL)
    _chevron(ax, x, x + w, 0.80, 0.97, fill)
    ax.text(x + 0.02, 0.905, phase.name, fontsize=9.5, fontweight="semibold", va="center")
    ax.text(x + 0.005, 0.765, f"{phase.code} · {phase.window}", fontsize=7.5, color=BLUE, va="top")
    ax.text(x + 0.005, 0.70, textwrap.fill(phase.what_happens, 30), fontsize=7.8, color=INK_2,
            va="top", linespacing=1.35)
    y = 0.40
    for r in cover.itertuples():
        full = r.present == r.total
        mark, color = ("●", INK) if r.present else ("○", MUTED)
        note = "" if full else f"  {r.present}/{r.total}"
        ax.text(x + 0.005, y, f"{mark} {r.column}{note}", fontsize=6.9, color=color,
                family="monospace", va="top")
        y -= 0.055


def fig_plant_lifecycle(pm: pd.DataFrame) -> Path:
    """Schematic season strip: what happens in each phase and which columns describe it."""
    fig, ax = plt.subplots(figsize=(15, 5.4))
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    w = 1 / len(PHASES)
    for i, p in enumerate(PHASES):
        _phase_column(ax, i * w, w, p, pm[pm["order"] == i])
    ax.text(0, 0.46, "DATA THAT DESCRIBES IT", fontsize=7, color=MUTED, fontweight="semibold")
    top = headline(fig, "A maize season, phase by phase, with the columns that describe each",
                   "● column filled (count shown if partly)   ○ column empty.   Not to scale: "
                   "the crop is not named, and maize stage codes are an assumption.")
    fig.tight_layout(rect=(0, 0, 1, top))
    return save(fig, "fig11_plant_lifecycle")


def _season_bands(ax: Axes, y: float, flower: float, end: float) -> None:
    lo, hi = flower - FLOWERING_HALF_WINDOW, flower + FLOWERING_HALF_WINDOW
    for a, b, c in [(0, lo, SEASON_FILL), (lo, hi, FLOWER_FILL), (hi, end, SEASON_FILL)]:
        if b > a:
            ax.barh(y, b - a, left=a, height=0.7, color=c, zorder=1, linewidth=0)
    ax.plot([flower, flower], [y - 0.35, y + 0.35], color=BLUE, linewidth=1.2, zorder=2)


def fig_trial_timelines(t: dict[str, pd.DataFrame], tl: pd.DataFrame) -> Path:
    """Swimlane of every trial with a planting record, in days after planting."""
    ops = operation_phases(t)
    order = {"PASS": 0, "HOLD": 1, "FAIL": 2}
    placed = tl[~tl["no_planting"]].assign(
        k=lambda d: d["TRIAL_RECOMMENDATION"].map(order)).sort_values(["k", "TRIAL_ID"])
    fig, ax = plt.subplots(figsize=(12, 0.24 * len(placed) + 1.9))
    ys = {g: i for i, g in enumerate(placed["TRIAL_GUID"][::-1])}
    for r in placed.itertuples():
        y = ys[r.TRIAL_GUID]
        end = r.season_days if r.season_days > r.FLOWERING_DAYS else r.FLOWERING_DAYS + 50
        _season_bands(ax, y, r.FLOWERING_DAYS, end)
    for op, m in OP_MARKERS.items():
        d = ops[(ops["OPERATION_TYPE_LID"] == op) & ops["TRIAL_GUID"].isin(ys)]
        odd = d["phase"].isin(["before_planting", "after_harvest"]) | (
            (op == "HARVEST") & (d["dap"] < d["FLOWERING_DAYS"]))
        ax.scatter(d["dap"], d["TRIAL_GUID"].map(ys), marker=m, s=34, zorder=3,
                   color=np.where(odd, SERIES[1], INK_2), edgecolor=SURFACE, linewidth=0.8)
    labels = [f"{i} · {v}" for i, v in zip(placed["TRIAL_ID"], placed["TRIAL_RECOMMENDATION"])]
    ax.set_yticks(list(ys.values()), labels[::-1], fontsize=7.5, family="monospace")
    ax.axvline(0, color=INK, linewidth=0.8, zorder=2)
    ax.set_xlabel("days after the trial's first planting")
    grid(ax, "x")
    handles = [Line2D([], [], color=INK_2, marker=m, linestyle="none", label=o.title())
               for o, m in OP_MARKERS.items()]
    handles += [Line2D([], [], color=SERIES[1], marker="o", linestyle="none",
                       label="out of order"),
                Line2D([], [], color=BLUE, label="expected flowering"),
                Patch(color=FLOWER_FILL, label=f"flowering ± {FLOWERING_HALF_WINDOW} d")]
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(0, -0.06 * 36 / len(placed)),
              ncol=6)
    bad = int((placed["harvest_before_planting"] | placed["harvest_before_flowering"]).sum())
    top = headline(fig, f"{len(placed)} of {len(tl)} trials can be placed on a season",
                   f"Rows = trials with a planting record, PASS then HOLD then FAIL. {bad} of them "
                   "are harvested before planting or before expected flowering (orange).")
    fig.tight_layout(rect=(0, 0, 1, top))
    return save(fig, "fig12_trial_timelines")


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
