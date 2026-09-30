"""The SYNTH_V1 trial recommendation rule, inferred from the SME's scoring file.

The v2 and v3 archives ship ``trial_recommendations_synthetic.csv``: one PASS / HOLD / FAIL
per trial with a text rationale and ``RULE_VERSION = SYNTH_V1``. The file gives
outcomes, not cut-points. The thresholds below are the simplest fixed values that
reproduce every supplied outcome; the data only brackets each one (see
``threshold_intervals``). They are an inference to confirm with the SME, not a
supplied Syngenta rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import numpy as np
import pandas as pd

# Rationale phrase that marks each criterion as met, keyed by trait column.
RATIONALE_OK: dict[str, str] = {
    "YIELD_T_HA": "yield meets threshold",
    "MOISTURE_PCT": "moisture meets threshold",
    "DISEASE_SCORE": "disease score acceptable",
    "GENOMIC_BREEDING_VALUE_MEAN": "genomic value favourable",
}


@dataclass(frozen=True)
class Rule:
    """Fixed per-trial thresholds; FAIL knockouts win over PASS criteria.

    Attributes:
        yield_min: PASS needs ``YIELD_T_HA >= yield_min``.
        moisture_max: PASS needs ``MOISTURE_PCT <= moisture_max``.
        disease_max: PASS needs ``DISEASE_SCORE <= disease_max``.
        gbv_min: PASS needs ``GENOMIC_BREEDING_VALUE_MEAN >= gbv_min``.
        resistant_min: PASS needs ``RESISTANT_MATERIAL_PCT >= resistant_min``.
        yield_knockout: FAIL if ``YIELD_T_HA < yield_knockout``.
        disease_knockout: FAIL if ``DISEASE_SCORE > disease_knockout``.
    """

    version: str = "SYNTH_V1 (inferred)"
    yield_min: float = 9.0
    moisture_max: float = 22.0
    disease_max: float = 5.0
    gbv_min: float = 102.0
    resistant_min: float = 50.0
    yield_knockout: float = 7.0
    disease_knockout: float = 7.0


SYNTH_V1 = Rule()


def criteria_flags(df: pd.DataFrame, rule: Rule = SYNTH_V1) -> pd.DataFrame:
    """One boolean column per PASS criterion and per FAIL knockout.

    A missing value never meets a PASS criterion and never triggers a knockout, so a
    trial with a gap lands on HOLD, not PASS.
    """
    y, m, d = df["YIELD_T_HA"], df["MOISTURE_PCT"], df["DISEASE_SCORE"]
    return pd.DataFrame(
        {
            "yield_ok": y >= rule.yield_min,
            "moisture_ok": m <= rule.moisture_max,
            "disease_ok": d <= rule.disease_max,
            "gbv_ok": df["GENOMIC_BREEDING_VALUE_MEAN"] >= rule.gbv_min,
            "resistant_ok": df["RESISTANT_MATERIAL_PCT"] >= rule.resistant_min,
            "ko_yield": y < rule.yield_knockout,
            "ko_disease": d > rule.disease_knockout,
        },
        index=df.index,
    )


def apply_rule(df: pd.DataFrame, rule: Rule = SYNTH_V1) -> pd.Series:
    """PASS / HOLD / FAIL per trial row."""
    f = criteria_flags(df, rule)
    fail = f["ko_yield"] | f["ko_disease"]
    passed = f[["yield_ok", "moisture_ok", "disease_ok", "gbv_ok", "resistant_ok"]].all(axis=1)
    out = np.where(fail, "FAIL", np.where(passed, "PASS", "HOLD"))
    return pd.Series(out, index=df.index, name="RULE_RECOMMENDATION")


def rationale_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Which of the four criteria the supplied rationale text reports as met."""
    text = df["RECOMMENDATION_RATIONALE"].str.lower()
    return pd.DataFrame({c: text.str.contains(p, regex=False) for c, p in RATIONALE_OK.items()})


def _interval(criterion: str, column: str, test: str, lo: object, hi: object,
              used: float) -> dict[str, object]:
    return {"criterion": criterion, "column": column, "test": test,
            "bracket_low": float(cast(float, lo)), "bracket_high": float(cast(float, hi)),
            "used": used}


def threshold_intervals(df: pd.DataFrame, rule: Rule = SYNTH_V1) -> pd.DataFrame:
    """Tightest bracket the supplied outcomes allow for each cut-point.

    The four rationale criteria are bracketed by the values the rationale calls met
    vs not met. Resistant % is bracketed within trials that meet the other four and
    trip no knockout. Each knockout is bracketed within trials the other knockout
    does not already explain.
    """
    ok = rationale_flags(df)
    rec = df["TRIAL_RECOMMENDATION"]
    fail = rec == "FAIL"
    rows = []
    for col, low_is_good in [("YIELD_T_HA", False), ("MOISTURE_PCT", True),
                             ("DISEASE_SCORE", True), ("GENOMIC_BREEDING_VALUE_MEAN", False)]:
        good, bad = df.loc[ok[col], col], df.loc[~ok[col], col]
        if low_is_good:
            rows.append(_interval(f"{col} acceptable", col, "<= t", good.max(), bad.min(),
                                  rule.moisture_max if col == "MOISTURE_PCT" else rule.disease_max))
        else:
            rows.append(_interval(f"{col} meets target", col, ">= t", bad.max(), good.min(),
                                  rule.yield_min if col == "YIELD_T_HA" else rule.gbv_min))
    four = ok.all(axis=1) & ~fail
    res = df["RESISTANT_MATERIAL_PCT"]
    rows.append(_interval("RESISTANT_MATERIAL_PCT for PASS", "RESISTANT_MATERIAL_PCT", ">= t",
                          res[four & (rec == "HOLD")].max(), res[four & (rec == "PASS")].min(),
                          rule.resistant_min))
    y, d = df["YIELD_T_HA"], df["DISEASE_SCORE"]
    rows.append(_interval("Yield knockout (FAIL below)", "YIELD_T_HA", "< t",
                          y[fail & (d <= rule.disease_knockout)].max(), y[~fail].min(),
                          rule.yield_knockout))
    rows.append(_interval("Disease knockout (FAIL above)", "DISEASE_SCORE", "> t",
                          d[~fail].max(), d[fail & (y >= rule.yield_knockout)].min(),
                          rule.disease_knockout))
    return pd.DataFrame(rows)


def trial_number(trial_id: pd.Series) -> pd.Series:
    """``SYN-TR-0007`` -> 7."""
    return trial_id.str.extract(r"(\d+)$")[0].astype(int)


def trial_material_links(t: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Three candidate trial -> material mappings, each as (TRIAL_GUID, MATERIAL_GUID).

    ``observation`` and ``operations`` are the links the files record. ``block`` is
    the mapping that reproduced every v2 genomics aggregate: trial k takes the 10
    consecutive materials of block (k - 1) mod 15 in MATERIAL_ID order. It is kept
    to show whether a later archive still follows it.
    """
    obs = t["observation"]
    mats = t["germplasm"].sort_values("MATERIAL_ID")["MATERIAL_GUID"].reset_index(drop=True)
    blocks = pd.DataFrame({"MATERIAL_GUID": mats, "block": mats.index // 10})
    trials = t["trial"][["TRIAL_GUID", "TRIAL_ID"]].assign(
        block=lambda d: (trial_number(d["TRIAL_ID"]) - 1) % blocks["block"].nunique())
    cols = ["TRIAL_GUID", "MATERIAL_GUID"]
    return {
        "observation": cast(pd.DataFrame, obs[cols].drop_duplicates()),
        "operations": cast(pd.DataFrame, t["operations"][cols].drop_duplicates()),
        "block": cast(pd.DataFrame, trials.merge(blocks, on="block")[cols]),
    }


def genomics_reconciliation(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Per trial: supplied genomics aggregates vs those recomputed from each mapping.

    ``gbv_match_*`` allows for the supplied one-decimal rounding. Expects ``align``-ed
    tables: in v3 neither recommendations nor genomics share GUIDs with the other files.
    """
    gen = t["genomics"][["MATERIAL_GUID", "GENOMIC_BREEDING_VALUE", "MARKER_DISEASE_RESISTANCE"]]
    rec = t["recommendations"][["TRIAL_GUID", "TRIAL_ID", "GENOMIC_BREEDING_VALUE_MEAN",
                                "RESISTANT_MATERIAL_PCT"]].set_index("TRIAL_GUID")
    out = rec.copy()
    for name, links in trial_material_links(t).items():
        agg = links.merge(gen, on="MATERIAL_GUID").groupby("TRIAL_GUID").agg(
            gbv=("GENOMIC_BREEDING_VALUE", "mean"),
            res=("MARKER_DISEASE_RESISTANCE", lambda s: (s == "RESISTANT").mean() * 100),
            n=("MATERIAL_GUID", "nunique"))
        out[f"gbv_{name}"] = agg["gbv"].round(2)
        out[f"resistant_{name}"] = agg["res"].round(1)
        out[f"n_{name}"] = agg["n"]
        gbv_gap = np.abs(agg["gbv"] - rec["GENOMIC_BREEDING_VALUE_MEAN"])
        res_gap = np.abs(agg["res"] - rec["RESISTANT_MATERIAL_PCT"])
        out[f"gbv_match_{name}"] = gbv_gap <= 0.051
        out[f"resistant_match_{name}"] = res_gap < 0.01
    return out.reset_index()


def decision_by_verdict(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Line-in-trial pairs by the line's ADVANCEMENT_DECISION and the trial's verdict.

    Expects ``align``-ed tables. Returns counts plus ``advance_share``: the share of
    pairs in each verdict whose line is ADVANCE.
    """
    pairs = t["observation"][["TRIAL_GUID", "MATERIAL_GUID"]].drop_duplicates()
    pairs = pairs.merge(t["germplasm"][["MATERIAL_GUID", "ADVANCEMENT_DECISION"]],
                        on="MATERIAL_GUID").merge(
        t["recommendations"][["TRIAL_GUID", "TRIAL_RECOMMENDATION"]], on="TRIAL_GUID")
    ct = pd.crosstab(pairs["TRIAL_RECOMMENDATION"], pairs["ADVANCEMENT_DECISION"])
    ct["advance_share"] = (ct.get("ADVANCE", 0) / ct.sum(axis=1)).round(3)
    return ct.rename_axis(columns=None).reset_index()


# Largest gap still read as a rounding difference: one decimal, flowering in whole days.
FIELD_TOLERANCE: dict[str, float] = {"FLOWERING_DAYS": 0.51}


def field_reconciliation(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Per trial and field trait: the supplied trial value vs the mean of its plot values.

    Expects ``align``-ed tables. ``plot_mean`` uses every plot; ``accepted_mean`` only
    ACCEPTED ones. ``match`` holds if either mean agrees within rounding.
    """
    obs = t["observation"]
    rec = t["recommendations"].set_index("TRIAL_GUID")
    traits = sorted(obs["TRAIT_CODE"].unique())
    means = {"plot_mean": obs, "accepted_mean": obs[obs["QUALITY_FLAG_LID"] == "ACCEPTED"]}
    frames = []
    for trait in traits:
        out = pd.DataFrame({"TRIAL_ID": rec["TRIAL_ID"], "trait": trait, "supplied": rec[trait]})
        for name, d in means.items():
            d = d[d["TRAIT_CODE"] == trait].groupby("TRIAL_GUID")["OBSERVATION_VALUE"]
            out[name] = d.mean().round(2)
            if name == "plot_mean":
                out["n_plots"] = d.size()
        tol = FIELD_TOLERANCE.get(trait, 0.051)
        gaps = [np.abs(out[c] - out["supplied"]) <= tol for c in means]
        out["match"] = gaps[0] | gaps[1]
        out["n_plots"] = out["n_plots"].fillna(0).astype(int)
        frames.append(out)
    return pd.concat(frames).reset_index()
