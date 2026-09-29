"""Quantile binning helpers for UC4 descriptive statistics.

Categorical columns have no quantiles of their own, so they are first mapped to
numbers: ordinals by their rank, nominals by a target mean per category. The
encoded values are then cut at the requested quantiles. Categoricals have few
levels, so edges often tie; ``BinResult.collapsed`` makes that explicit instead
of silently returning fewer bins.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence, cast

import pandas as pd

QUANTILES: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 1.0)


@dataclass
class BinResult:
    """Outcome of cutting one column at quantile edges.

    Attributes:
        raw_edges: Value at each requested quantile, ties included.
        edges: Distinct edges actually used for the cut.
        counts: Number of non-missing values per resulting bin, in bin order.
        bins: Bin label per input row (NaN where the input was missing).
        collapsed: True when tied edges produced fewer bins than requested.
        n_missing: Inputs left unbinned because they were missing.
    """

    raw_edges: list[float]
    edges: list[float]
    counts: list[int]
    bins: pd.Series = field(repr=False)
    collapsed: bool
    n_missing: int

    @property
    def n_bins(self) -> int:
        return len(self.counts)


def quantile_bin(values: pd.Series, q: Sequence[float] = QUANTILES) -> BinResult:
    """Cut numeric values at quantile edges, dropping tied edges.

    Args:
        values: Numeric series; NaN stays NaN and is never imputed.
        q: Increasing quantile probabilities, including 0 and 1.

    Returns:
        BinResult describing the edges, bin counts and whether bins collapsed.

    Raises:
        ValueError: If ``values`` holds fewer than two non-missing values.
    """
    s = pd.Series(pd.to_numeric(values, errors="coerce"), index=values.index, dtype=float)
    present = s.dropna()
    if present.size < 2:
        raise ValueError("quantile_bin needs at least two non-missing values")
    raw_edges = [float(v) for v in present.quantile(list(q))]
    bins = cast(pd.Series, pd.qcut(s, q=list(q), duplicates="drop"))
    edges = [float(e) for e in pd.unique(pd.Series(raw_edges))]
    counts = [int(c) for c in bins.value_counts(sort=False)]
    return BinResult(
        raw_edges=raw_edges,
        edges=edges,
        counts=counts,
        bins=bins,
        collapsed=len(counts) < len(q) - 1,
        n_missing=int(s.isna().sum()),
    )


def ordinal_encode(series: pd.Series, order: Sequence[object]) -> pd.Series:
    """Map ordered categories to ranks 1..k; unknown or missing values become NaN."""
    ranks = {level: rank for rank, level in enumerate(order, start=1)}
    return series.map(ranks).astype(float)


def target_encode(df: pd.DataFrame, col: str, target: str) -> pd.Series:
    """Replace each category in ``col`` by the mean of ``target`` within that category.

    Rows with a missing category, or a category with no observed target, get NaN.
    """
    means = cast(pd.Series, df.groupby(col, dropna=True)[target].mean())
    return cast(pd.Series, df[col]).map(means.to_dict()).astype(float)
