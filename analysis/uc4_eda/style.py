"""One visual system for every UC4 figure (dataviz reference palette, light surface)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.axes import Axes  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
NEUTRAL = "#d4d3cd"

# Categorical slots in fixed order; the first three validate all-pairs.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
BLUE = SERIES[0]
# PASS / HOLD / FAIL read as green / amber / red-orange, matching the proposed RAG mapping.
REC_COLORS = {"PASS": SERIES[2], "HOLD": SERIES[3], "FAIL": SERIES[1]}

DIVERGING = LinearSegmentedColormap.from_list(
    "blue_gray_red", ["#104281", "#5598e7", "#f0efec", "#ec7b7a", "#a82a2a"]
)

DPI = 200
FIG_DIR = Path(__file__).parent / "figures"


def apply_style() -> None:
    plt.rcParams.update(
        {
            "font.family": ["Segoe UI", "DejaVu Sans"],
            "font.size": 9,
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "axes.edgecolor": AXIS,
            "axes.linewidth": 0.8,
            "axes.labelcolor": INK_2,
            "axes.titlecolor": INK,
            "axes.titlesize": 10,
            "axes.titleweight": "semibold",
            "axes.titlelocation": "left",
            "axes.titlepad": 19,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": False,
            "grid.color": GRID,
            "grid.linewidth": 0.8,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "xtick.labelcolor": INK_2,
            "ytick.labelcolor": INK_2,
            "xtick.major.size": 0,
            "ytick.major.size": 0,
            "legend.frameon": False,
            "legend.fontsize": 8.5,
            "text.color": INK,
        }
    )


def grid(ax: Axes, axis: Literal["x", "y"] = "y") -> None:
    """Recessive hairline grid on the value axis; the value-axis spine is dropped."""
    ax.grid(True, axis=axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines["bottom" if axis == "x" else "left"].set_visible(False)


def subtitle(ax: Axes, text: str) -> None:
    """Secondary line in the gap between a panel title and its plot area."""
    ax.annotate(text, (0, 1), xycoords="axes fraction", xytext=(0, 5),
                textcoords="offset points", fontsize=8, color=MUTED, va="bottom")


def headline(fig: Figure, title: str, sub: str) -> float:
    """Figure title and one-line takeaway; returns the top fraction left for panels."""
    h = fig.get_figheight()
    fig.text(0.01, 1 - 0.18 / h, title, ha="left", va="top", fontsize=13, fontweight="semibold")
    fig.text(0.01, 1 - 0.48 / h, sub, ha="left", va="top", fontsize=9, color=INK_2)
    return 1 - 0.8 / h


def save(fig: Figure, name: str) -> Path:
    FIG_DIR.mkdir(exist_ok=True)
    path = FIG_DIR / f"{name}.png"
    fig.savefig(path, dpi=DPI, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    return path
