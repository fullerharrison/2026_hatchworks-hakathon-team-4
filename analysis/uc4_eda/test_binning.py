import math

import numpy as np
import pandas as pd
import pytest

from binning import ordinal_encode, quantile_bin, target_encode


def test_continuous_values_give_four_equal_bins() -> None:
    result = quantile_bin(pd.Series(np.arange(1, 101, dtype=float)))
    assert result.n_bins == 4
    assert not result.collapsed
    assert result.counts == [25, 25, 25, 25]
    assert result.raw_edges[0] == 1 and result.raw_edges[-1] == 100


def test_three_level_ordinal_is_flagged_collapsed() -> None:
    stages = pd.Series(["S1"] * 10 + ["S2"] * 10 + ["S3"] * 80)
    result = quantile_bin(ordinal_encode(stages, ["S1", "S2", "S3"]))
    assert result.collapsed
    assert result.n_bins < 4
    assert sum(result.counts) == 100


def test_target_encoding_matches_hand_calculation() -> None:
    df = pd.DataFrame({"region": ["EU", "EU", "NAM", "NAM", None], "yield": [8.0, 10.0, 6.0, np.nan, 5.0]})
    encoded = target_encode(df, "region", "yield")
    assert encoded.tolist()[:4] == [9.0, 9.0, 6.0, 6.0]
    assert math.isnan(encoded.iloc[4])


def test_missing_values_stay_missing_not_zero() -> None:
    values = pd.Series([1.0, 2.0, np.nan, 3.0, 4.0, 5.0])
    result = quantile_bin(values)
    assert result.n_missing == 1
    assert pd.isna(result.bins.iloc[2])
    assert sum(result.counts) == 5


def test_unknown_ordinal_level_becomes_nan() -> None:
    encoded = ordinal_encode(pd.Series(["S1", "S9"]), ["S1", "S2"])
    assert encoded.iloc[0] == 1.0 and math.isnan(encoded.iloc[1])


def test_too_few_values_raise() -> None:
    with pytest.raises(ValueError):
        quantile_bin(pd.Series([1.0, np.nan]))
