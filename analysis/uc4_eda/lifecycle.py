"""Consistency checks on the UC4 v2 tables, plus headline counts per source.

Each check tests something a breeding record implies: operations fall in their
trial's season, a completed trial has no work still planned, and trial aggregates
agree with the materials the files link to the trial. Records where either side is
missing are "not checkable" and excluded from the denominator rather than passing.
"""

from __future__ import annotations

from typing import cast

import pandas as pd

from rules import apply_rule, genomics_reconciliation, rationale_flags

OPERATION_ORDER = ["PLANTING", "IRRIGATION", "HARVEST"]


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


def operations_with_trial(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Operations with their trial's ID, start year and status attached."""
    trial = t["trial"][["TRIAL_GUID", "TRIAL_ID", "START_YEAR", "STATUS_LID"]].rename(
        columns={"STATUS_LID": "TRIAL_STATUS"})
    ops = t["operations"].merge(trial, on="TRIAL_GUID", how="left")
    return ops.assign(date=_dt(ops["OPERATION_DATE"]))


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
    obs_pairs = set(zip(t["observation"]["ATTACHED_TO_FIELD_ENTITY_ID"], t["observation"]["GID"]))
    unlinked = pd.Series([float((a, b) not in obs_pairs)
                          for a, b in zip(ops["TRIAL_GUID"], ops["MATERIAL_GUID"])], index=ops.index)
    return [
        _row("Operation dated outside its trial's start year", "Operations",
             wrong_year.where(ops["date"].notna()), ops["TRIAL_ID"]),
        _row("Completed trial still has planned operations", "Operations",
             complete.apply(lambda s: float((s == "PLANNED").any())),
             complete.size().index.to_series()),
        _row("Planned operation dated before the extract", "Operations",
             before(ops.loc[planned, "OPERATION_DATE"], snap[planned]), ops.loc[planned, "OPERATION_GUID"]),
        _row("Completed operation dated after the extract", "Operations",
             before(snap[done], ops.loc[done, "OPERATION_DATE"]), ops.loc[done, "OPERATION_GUID"]),
        _row("Trial's first harvest dated before its first planting", "Operations",
             hbp, hbp.index.to_series()),
        _row("Operation's trial + material not linked in observations", "Links",
             unlinked, ops["OPERATION_GUID"]),
    ]


def _recommendation_rows(t: dict[str, pd.DataFrame]) -> list[dict[str, object]]:
    rec = t["recommendations"]
    recon = genomics_reconciliation(t)
    all_four = rationale_flags(rec).all(axis=1)
    return [
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
    return pd.DataFrame(_operation_rows(t) + _recommendation_rows(t) + _record_rows(t))


def stage_counts(t: dict[str, pd.DataFrame]) -> dict[str, dict[str, object]]:
    """Headline numbers and key fields for each source card."""
    g, trial, obs, ops, lab, gen, rec = (
        t[k] for k in ["germplasm", "trial", "observation", "operations", "lab", "genomics",
                       "recommendations"])
    years = trial["START_YEAR"]
    per_trial = obs.groupby("ATTACHED_TO_FIELD_ENTITY_ID")["GID"].nunique()
    per_mat = obs.groupby("GID")["ATTACHED_TO_FIELD_ENTITY_ID"].nunique()
    return {
        "germplasm": {"n": len(g), "unit": "lines",
                      "detail": "IDs only: no pedigree, stage or decision"},
        "genomics": {"n": len(gen), "unit": "genotyped lines",
                     "detail": f"{len([c for c in gen if c.startswith('MARKER_')])} markers + GBV, "
                               f"QC {'/'.join(gen['QC_STATUS_LID'].unique())}"},
        "lab": {"n": len(lab), "unit": "lab results",
                "detail": f"{lab['TRAIT_GUID'].nunique()} unnamed traits, "
                          f"{lab['MATERIAL_GUID'].nunique()} lines"},
        "trials": {"n": len(trial), "unit": "trials",
                   "detail": f"{trial['LOCATION_GUID'].nunique()} locations, {years.min()} to "
                             f"{years.max()}, all {'/'.join(trial['STATUS_LID'].unique())}"},
        "observations": {"n": len(obs), "unit": "trial-line links",
                         "detail": f"{per_trial.median():.0f} lines per trial, "
                                   f"{per_mat.min()} to {per_mat.max()} trials per line, no values"},
        "operations": {"n": len(ops), "unit": "operations",
                       "detail": ", ".join(o.title() for o in OPERATION_ORDER)},
        "recommendations": {"n": len(rec), "unit": "trial verdicts",
                            "detail": " / ".join(f"{k.title()} {v}" for k, v in
                                                 rec["TRIAL_RECOMMENDATION"].value_counts().items())},
    }
