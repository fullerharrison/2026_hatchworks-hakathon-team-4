"""The SYNTH_V1 trial recommendation rule, inferred from the SME's scoring file.

The v2 archive ships ``trial_recommendations_synthetic.csv``: one PASS / HOLD / FAIL
per trial with a text rationale and ``RULE_VERSION = SYNTH_V1``. The file gives
outcomes, not cut-points. The thresholds below are the simplest fixed values that
reproduce every supplied outcome; the data only brackets each one (see
``threshold_intervals``). They are an inference to confirm with the SME, not a
supplied Syngenta rule.

Ported from ``analysis/uc4_eda/rules.py`` (the evidence record, left unchanged);
``explain()`` and its criterion table are new here.
"""

from __future__ import annotations

import math
import operator
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

import numpy as np
import pandas as pd

from uc4_mcp.models import Criterion, Recommendation, evidence_ref

# Rationale phrase that marks each criterion as met, keyed by trait column.
RATIONALE_OK: dict[str, str] = {
    "YIELD_T_HA": "yield meets threshold",
    "MOISTURE_PCT": "moisture meets threshold",
    "DISEASE_SCORE": "disease score acceptable",
    "GENOMIC_BREEDING_VALUE_MEAN": "genomic value favourable",
}
# Rationale phrase that marks each criterion as not met. With RATIONALE_OK these are
# the only eight phrases in the file; resistant % is never mentioned.
RATIONALE_UNMET: dict[str, str] = {
    "YIELD_T_HA": "yield below target",
    "MOISTURE_PCT": "moisture above target",
    "DISEASE_SCORE": "disease risk elevated",
    "GENOMIC_BREEDING_VALUE_MEAN": "genomic value below target",
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
    the mapping that reproduces the supplied genomics aggregates: trial k takes the
    10 consecutive materials of block (k - 1) mod 15 in MATERIAL_ID order.
    """
    obs = t["observation"].rename(columns={"ATTACHED_TO_FIELD_ENTITY_ID": "TRIAL_GUID",
                                           "GID": "MATERIAL_GUID"})
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

    ``gbv_match_*`` allows for the supplied one-decimal rounding.
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


# --- explain(): one trial's verdict, criterion by criterion ------------------


@dataclass(frozen=True)
class CriterionSpec:
    """One SYNTH_V1 test. ``interval`` is its ``criterion`` name in
    ``threshold_intervals()``; brackets map by it because ``field`` repeats."""

    interval: str
    field: str
    label: str
    short: str  # used in Recommendation.reason
    unit: str
    test: str
    rule_attr: str
    kind: str  # "pass" | "knockout"


# Fixed order: the five PASS criteria, then the two FAIL knockouts.
CRITERIA: tuple[CriterionSpec, ...] = (
    CriterionSpec("YIELD_T_HA meets target", "YIELD_T_HA", "Yield meets target",
                  "yield", " t/ha", ">=", "yield_min", "pass"),
    CriterionSpec("MOISTURE_PCT acceptable", "MOISTURE_PCT", "Moisture acceptable",
                  "moisture", "%", "<=", "moisture_max", "pass"),
    CriterionSpec("DISEASE_SCORE acceptable", "DISEASE_SCORE", "Disease score acceptable",
                  "disease score", "", "<=", "disease_max", "pass"),
    CriterionSpec("GENOMIC_BREEDING_VALUE_MEAN meets target", "GENOMIC_BREEDING_VALUE_MEAN",
                  "Genomic breeding value meets target", "GBV mean", "", ">=", "gbv_min", "pass"),
    CriterionSpec("RESISTANT_MATERIAL_PCT for PASS", "RESISTANT_MATERIAL_PCT",
                  "Resistant lines for PASS", "resistant lines", "%", ">=", "resistant_min",
                  "pass"),
    CriterionSpec("Yield knockout (FAIL below)", "YIELD_T_HA", "Yield knockout (FAIL below)",
                  "yield", " t/ha", "<", "yield_knockout", "knockout"),
    CriterionSpec("Disease knockout (FAIL above)", "DISEASE_SCORE",
                  "Disease knockout (FAIL above)", "disease score", "", ">", "disease_knockout",
                  "knockout"),
)
_OPS: dict[str, Callable[[float, float], bool]] = {
    ">=": operator.ge, "<=": operator.le, "<": operator.lt, ">": operator.gt}
_NEGATION = {">=": "<", "<=": ">"}
COLOURS = {"PASS": "green", "HOLD": "amber", "FAIL": "red"}


def _value(raw: Any) -> float | None:
    return None if raw is None or pd.isna(raw) else float(raw)


def _criterion(spec: CriterionSpec, row: pd.Series, brackets: dict[str, tuple[float, float]],
               rule: Rule) -> Criterion:
    value = _value(row[spec.field])
    threshold = float(getattr(rule, spec.rule_attr))
    holds = value is not None and _OPS[spec.test](value, threshold)
    knockout = spec.kind == "knockout"
    return Criterion(field=spec.field, label=spec.label, value=value, test=spec.test,
                     threshold=threshold, bracket=brackets[spec.interval], kind=spec.kind,
                     passed=value is not None and (not holds if knockout else holds),
                     triggered=knockout and holds)


def _num(x: float) -> str:
    return f"{x:g}"


def _reason(verdict: str, pairs: list[tuple[CriterionSpec, Criterion]]) -> str:
    if verdict == "PASS":
        return "PASS: all five criteria met (inferred thresholds)"
    parts = []
    for spec, c in pairs:
        if verdict == "FAIL" and c.triggered:
            parts.append(f"{spec.short} {_num(cast(float, c.value))}{spec.unit} {c.test} "
                         f"{_num(c.threshold)}{spec.unit}")
        elif verdict == "HOLD" and c.kind == "pass" and not c.passed:
            parts.append(f"{spec.short} missing" if c.value is None else
                         f"{spec.short} {_num(c.value)}{spec.unit} {_NEGATION[c.test]} "
                         f"{_num(c.threshold)}{spec.unit}")
    plural = len(parts) > 1
    note = "inferred thresholds" if plural else "inferred threshold"
    if verdict == "FAIL":
        note = f"{'knockouts' if plural else 'knockout'}, {note}"
    return f"{verdict}: {'; '.join(parts)} ({note})"


def _rationale_omits(text: str, criteria: tuple[Criterion, ...]) -> tuple[str, ...]:
    """Fields the rule finds unmet that the rationale reports neither as met nor unmet."""
    unmet = [c.field for c in criteria if (c.kind == "pass" and not c.passed) or c.triggered]
    mentioned = {f for f in RATIONALE_OK
                 if RATIONALE_OK[f] in text or RATIONALE_UNMET[f] in text}
    return tuple(f for f in dict.fromkeys(unmet) if f not in mentioned)


def explain(row: pd.Series, intervals: pd.DataFrame, rule: Rule = SYNTH_V1) -> Recommendation:
    """Score one recommendations row, criterion by criterion, without flags.

    Args:
        row: One row of the ``recommendations`` table (with provenance columns).
        intervals: ``threshold_intervals()`` over all 72 trials, computed once.
        rule: The thresholds to apply.

    Returns:
        The verdict, the 7 criteria in ``CRITERIA`` order, a one-line reason and the
        comparison with the supplied verdict and rationale. ``flags`` is empty; the
        store fills it with ``dataclasses.replace``.
    """
    brackets = {str(name): (float(lo), float(hi)) for name, lo, hi in
                zip(intervals["criterion"], intervals["bracket_low"], intervals["bracket_high"])}
    pairs = [(s, _criterion(s, row, brackets, rule)) for s in CRITERIA]
    criteria = tuple(c for _, c in pairs)
    knockout = tuple(c.field for c in criteria if c.triggered)
    if knockout:
        verdict = "FAIL"
    elif all(c.passed for c in criteria if c.kind == "pass"):
        verdict = "PASS"
    else:
        verdict = "HOLD"
    rationale = row.get("RECOMMENDATION_RATIONALE")
    rationale = rationale if isinstance(rationale, str) else ""
    supplied = str(row["TRIAL_RECOMMENDATION"])
    return Recommendation(
        trial_guid=str(row["TRIAL_GUID"]), trial_id=str(row["TRIAL_ID"]), verdict=verdict,
        colour=COLOURS[verdict], criteria=criteria, knockout=knockout,
        reason=_reason(verdict, pairs), rule_version=rule.version, supplied_verdict=supplied,
        matches_supplied=verdict == supplied, supplied_rationale=rationale,
        rationale_omits=_rationale_omits(rationale.lower(), criteria),
        evidence_row_ids=(evidence_ref(row),), flags=())
