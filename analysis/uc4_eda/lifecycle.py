"""Consistency checks on the UC4 v3 tables, plus headline counts per source.

Each check tests something a breeding record implies: operations and plot
observations fall in their trial's season, a completed trial has no work still
planned, recorded keys resolve, and trial aggregates agree with the plots and lines
the files link to the trial. Records where either side is missing are "not
checkable" and excluded from the denominator rather than passing.

Expects ``load.align``-ed tables; link checks read the supplied keys from the
``SOURCE_*`` columns ``align`` keeps.
"""

from __future__ import annotations

from typing import cast

import pandas as pd

from rules import apply_rule, field_reconciliation, genomics_reconciliation, rationale_flags

OPERATION_ORDER = ["PLANTING", "FERTILISER_APPLICATION", "IRRIGATION", "PLOT_INSPECTION",
                   "HARVEST"]


def _dt(s: pd.Series) -> pd.Series:
    return cast(pd.Series, pd.to_datetime(s, errors="coerce"))


def before(a: pd.Series, b: pd.Series) -> pd.Series:
    """1.0 where date ``a`` precedes date ``b``, 0.0 where it does not, NaN if either is missing."""
    a, b = _dt(a), _dt(b)
    out = (a < b).astype(float)
    return out.where(a.notna() & b.notna())


def _row(rule: str, stage: str, flags: pd.Series, ids: pd.Series) -> dict[str, object]:
    checkable = flags.notna()
    violated = flags[checkable] == 1
    example = ids[checkable][violated]
    n, v = int(checkable.sum()), int(violated.sum())
    return {
        "stage": stage,
        "rule": rule,
        "checked": n,
        "violations": v,
        "share": round(v / n, 3) if n else float("nan"),
        "not_checkable": int((~checkable).sum()),
        "example": str(example.iloc[0]) if len(example) else "",
    }


def snapshot_date(t: dict[str, pd.DataFrame]) -> pd.Timestamp:
    """When the extract was taken: the latest LAST_CHG_DATE stamp in any table."""
    stamps = [_dt(df["LAST_CHG_DATE"]) for df in t.values() if "LAST_CHG_DATE" in df]
    return cast(pd.Timestamp, pd.concat(stamps).max())


def month_span(dates: pd.Series) -> str:
    """``April to September 2026``, or ``April 2025 to September 2026`` across years."""
    d = _dt(dates).dropna()
    lo, hi = d.min(), d.max()
    return f"{lo:%B} to {hi:%B %Y}" if lo.year == hi.year else f"{lo:%B %Y} to {hi:%B %Y}"


def header_facts(t: dict[str, pd.DataFrame]) -> dict[str, object]:
    """Counts shown in the report header, derived rather than typed in."""
    years = t["trial"]["START_YEAR"]
    return {"lines": len(t["germplasm"]), "trials": len(t["trial"]),
            "sites": t["trial"]["LOCATION_GUID"].nunique(),
            "years": f"{years.min()} to {years.max()}",
            "operation_months": month_span(t["operations"]["OPERATION_DATE"])}


def _with_trial(df: pd.DataFrame, t: dict[str, pd.DataFrame], date_col: str) -> pd.DataFrame:
    """``df`` with its trial's ID, start year, begin date and status, and a parsed ``date``."""
    cols = [c for c in ["TRIAL_GUID", "TRIAL_ID", "START_YEAR", "BEGIN_DATE", "STATUS_LID"]
            if c in t["trial"]]
    trial = t["trial"][cols].rename(columns={"STATUS_LID": "TRIAL_STATUS"})
    out = df.merge(trial, on="TRIAL_GUID", how="left")
    return out.assign(date=_dt(out[date_col]))


def operations_with_trial(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Operations with their trial's ID, start year, begin date and status attached."""
    return _with_trial(t["operations"], t, "OPERATION_DATE")


def observations_with_trial(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Plot observations with their trial's ID, start year, begin date and status attached."""
    return _with_trial(t["observation"], t, "OBSERVATION_DATE")


def _before_begin(df: pd.DataFrame) -> pd.Series:
    if "BEGIN_DATE" not in df:
        return pd.Series(float("nan"), index=df.index)
    return before(df["date"], df["BEGIN_DATE"])


def _off_modal_unit(ops: pd.DataFrame) -> pd.Series:
    """1.0 where an operation's quantity unit is not the most common unit for its type."""
    if "QUANTITY_UOM" not in ops:
        return pd.Series(float("nan"), index=ops.index)
    modal = ops.groupby("OPERATION_TYPE_LID")["QUANTITY_UOM"].agg(lambda s: s.mode().iloc[0])
    off = (ops["QUANTITY_UOM"] != ops["OPERATION_TYPE_LID"].map(modal)).astype(float)
    return off.where(ops["QUANTITY_UOM"].notna())


def _harvest_before_planting(ops: pd.DataFrame) -> pd.Series:
    """Per trial: 1.0 if the first harvest precedes the first planting."""
    first = ops.pivot_table(index="TRIAL_ID", columns="OPERATION_TYPE_LID", values="date",
                            aggfunc="min")
    if not {"HARVEST", "PLANTING"} <= set(first.columns):
        return pd.Series(dtype=float)
    return before(first["HARVEST"], first["PLANTING"])


def _operation_rows(t: dict[str, pd.DataFrame]) -> list[dict[str, object]]:
    ops = operations_with_trial(t)
    snap = pd.Series(snapshot_date(t), index=ops.index)
    planned = ops["OPERATION_STATUS_LID"] == "PLANNED"
    done = ~planned
    wrong_year = (ops["date"].dt.year != ops["START_YEAR"]).astype(float)
    complete = ops[ops["TRIAL_STATUS"] == "COMPLETE"].groupby("TRIAL_ID")["OPERATION_STATUS_LID"]
    hbp = _harvest_before_planting(ops)
    return [
        _row("Operation dated outside its trial's start year", "Operations",
             wrong_year.where(ops["date"].notna()), ops["TRIAL_ID"]),
        _row("Operation dated before its trial's BEGIN_DATE", "Operations",
             _before_begin(ops), ops["OPERATION_GUID"]),
        _row("Operation quantity unit differs from its type's usual unit", "Operations",
             _off_modal_unit(ops), ops["OPERATION_GUID"]),
        _row("Completed trial still has planned operations", "Operations",
             complete.apply(lambda s: float((s == "PLANNED").any())),
             complete.size().index.to_series()),
        _row("Planned operation dated before the extract", "Operations",
             before(ops.loc[planned, "OPERATION_DATE"], snap[planned]), ops.loc[planned, "OPERATION_GUID"]),
        _row("Completed operation dated after the extract", "Operations",
             before(snap[done], ops.loc[done, "OPERATION_DATE"]), ops.loc[done, "OPERATION_GUID"]),
        _row("Trial's first harvest dated before its first planting", "Operations",
             hbp, hbp.index.to_series()),
    ]


def _observation_rows(t: dict[str, pd.DataFrame]) -> list[dict[str, object]]:
    obs = observations_with_trial(t)
    snap = pd.Series(snapshot_date(t), index=obs.index)
    wrong_year = (obs["date"].dt.year != obs["START_YEAR"]).astype(float)
    not_done = obs["TRIAL_STATUS"].isin(["PLANNED"]).astype(float)
    return [
        _row("Plot observation dated outside its trial's start year", "Observations",
             wrong_year.where(obs["date"].notna()), obs["OBSERVATION_GUID"]),
        _row("Plot observation dated before its trial's BEGIN_DATE", "Observations",
             _before_begin(obs), obs["OBSERVATION_GUID"]),
        _row("Plot observation dated after the extract", "Observations",
             before(snap, obs["OBSERVATION_DATE"]), obs["OBSERVATION_GUID"]),
        _row("Plot observation on a trial still PLANNED", "Observations",
             not_done.where(obs["TRIAL_STATUS"].notna()), obs["OBSERVATION_GUID"]),
        _row("Plot observation flagged REJECTED", "Observations",
             (obs["QUALITY_FLAG_LID"] == "REJECTED").astype(float), obs["OBSERVATION_GUID"]),
    ]


def _source(df: pd.DataFrame, col: str) -> pd.Series:
    """The supplied key: ``SOURCE_<col>`` after ``align``, else ``col`` itself."""
    return cast(pd.Series, df.get(f"SOURCE_{col}", df[col]))


def _link_rows(t: dict[str, pd.DataFrame]) -> list[dict[str, object]]:
    germ, trial, gen, rec, ops = (t[k] for k in ["germplasm", "trial", "genomics",
                                                 "recommendations", "operations"])
    obs_pairs = set(zip(t["observation"]["TRIAL_GUID"], t["observation"]["MATERIAL_GUID"]))
    unlinked = pd.Series([float((a, b) not in obs_pairs)
                          for a, b in zip(ops["TRIAL_GUID"], ops["MATERIAL_GUID"])], index=ops.index)
    lines = set(germ["MATERIAL_GUID"])
    no_lab = (~germ["MATERIAL_GUID"].isin(set(t["lab"]["MATERIAL_GUID"]))).astype(float)
    return [
        _row("Operation's trial + material not linked in observations", "Links",
             unlinked, ops["OPERATION_GUID"]),
        _row("Genomics MATERIAL_GUID not found in germplasm", "Links",
             (~_source(gen, "MATERIAL_GUID").isin(lines)).astype(float), gen["SAMPLE_ID"]),
        _row("Recommendation TRIAL_GUID not found in the trial file", "Links",
             (~_source(rec, "TRIAL_GUID").isin(set(trial["TRIAL_GUID"]))).astype(float),
             rec["TRIAL_ID"]),
        _row("Line with no lab result", "Links", no_lab, germ["MATERIAL_ID"]),
    ]


def _field_rows(t: dict[str, pd.DataFrame]) -> list[dict[str, object]]:
    if "TRAIT_CODE" not in t["observation"]:
        return []
    fr = field_reconciliation(t)
    return [_row("Trial trait value differs from the mean of its plots", "Recommendation",
                 (~fr["match"]).astype(float).where(fr["n_plots"] > 0),
                 fr["TRIAL_ID"] + " " + fr["trait"])]


def _recommendation_rows(t: dict[str, pd.DataFrame]) -> list[dict[str, object]]:
    rec = t["recommendations"]
    recon = genomics_reconciliation(t)
    all_four = rationale_flags(rec).all(axis=1)
    status = rec["TRIAL_GUID"].map(t["trial"].set_index("TRIAL_GUID")["STATUS_LID"])
    return [
        *_field_rows(t),
        _row("Trial has a verdict but is not COMPLETE in the trial file", "Recommendation",
             (status != "COMPLETE").astype(float).where(status.notna()), rec["TRIAL_ID"]),
        _row("Trial GBV mean differs from its observation-linked materials", "Recommendation",
             (~recon["gbv_match_observation"]).astype(float), recon["TRIAL_ID"]),
        _row("Trial resistant % differs from its observation-linked materials", "Recommendation",
             (~recon["resistant_match_observation"]).astype(float), recon["TRIAL_ID"]),
        _row("Rationale reports all four criteria met, yet not PASS", "Recommendation",
             (rec["TRIAL_RECOMMENDATION"] != "PASS").astype(float).where(all_four), rec["TRIAL_ID"]),
        _row("Supplied recommendation differs from the inferred rule", "Recommendation",
             (apply_rule(rec) != rec["TRIAL_RECOMMENDATION"]).astype(float), rec["TRIAL_ID"]),
    ]


def _record_rows(t: dict[str, pd.DataFrame]) -> list[dict[str, object]]:
    gen = t["genomics"]
    snap = pd.Series(snapshot_date(t), index=gen.index)
    return [
        _row("Genotyping dated after the extract", "Record keeping",
             before(snap, gen["GENOTYPING_DATE"]), gen["SAMPLE_ID"]),
        _row("Genomics record last changed before it was created", "Record keeping",
             before(gen["LAST_CHG_DATE"], gen["CREATE_DATE"]), gen["SAMPLE_ID"]),
    ]


def chronology_checks(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Evaluate every consistency rule; one row per rule."""
    return pd.DataFrame(_operation_rows(t) + _observation_rows(t) + _link_rows(t)
                        + _recommendation_rows(t) + _record_rows(t))


def stage_counts(t: dict[str, pd.DataFrame]) -> dict[str, dict[str, object]]:
    """Headline numbers and key fields for each source card."""
    g, trial, obs, ops, lab, gen, rec = (
        t[k] for k in ["germplasm", "trial", "observation", "operations", "lab", "genomics",
                       "recommendations"])
    years = trial["START_YEAR"]
    per_trial = obs.groupby("TRIAL_GUID")["MATERIAL_GUID"].nunique()
    decisions = g["ADVANCEMENT_DECISION"].value_counts()
    status = trial["STATUS_LID"].value_counts()
    rejected = int((obs["QUALITY_FLAG_LID"] == "REJECTED").sum())
    return {
        "germplasm": {"n": len(g), "unit": "lines",
                      "detail": "pedigree, stage and decision: " + " / ".join(
                          f"{k.title()} {v}" for k, v in decisions.items())},
        "genomics": {"n": len(gen), "unit": "genotyped lines",
                     "detail": f"{len([c for c in gen if c.startswith('MARKER_')])} markers + GBV, "
                               f"QC {'/'.join(gen['QC_STATUS_LID'].unique())}"},
        "lab": {"n": len(lab), "unit": "lab results",
                "detail": f"{lab['TRAIT_GUID'].nunique()} unnamed traits, "
                          f"{lab['MATERIAL_GUID'].nunique()} of {len(g)} lines"},
        "trials": {"n": len(trial), "unit": "trials",
                   "detail": f"{trial['LOCATION_GUID'].nunique()} locations, {years.min()} to "
                             f"{years.max()}; " + " / ".join(
                                 f"{k.title()} {v}" for k, v in status.items())},
        "observations": {"n": len(obs), "unit": "plot values",
                         "detail": f"{obs['TRAIT_CODE'].nunique()} field traits, "
                                   f"{per_trial.median():.0f} lines per trial, "
                                   f"{rejected} rejected"},
        "operations": {"n": len(ops), "unit": "operations",
                       "detail": ", ".join(o.replace("_", " ").title() for o in OPERATION_ORDER
                                           if o in set(ops["OPERATION_TYPE_LID"]))},
        "recommendations": {"n": len(rec), "unit": "trial verdicts",
                            "detail": " / ".join(f"{k.title()} {v}" for k, v in
                                                 rec["TRIAL_RECOMMENDATION"].value_counts().items())},
    }
