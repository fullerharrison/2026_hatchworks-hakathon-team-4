"""The v3 record placed on a crop season: which growth phase each value describes, and when.

The files never name the crop (``CROP_GUID`` is one unnamed GUID). Yield in t/ha, plant
height of 1.5 to 3 m, 45 to 95 days to flowering and grain moisture at harvest fit maize,
so the phases use maize growth-stage codes (VE, V, VT/R1, R2-R6). Treat that as an
assumption.

Each trial's season is anchored on its first PLANTING operation and expressed in days
after planting (DAP), as in v2, so the two versions stay comparable. Flowering is then
placed at planting + ``FLOWERING_DAYS``. A trial with no planting record cannot be
placed, and nothing is guessed for it. v3 plot observations and ``BEGIN_DATE`` are
dated too; ``lifecycle.chronology_checks`` tests them against the trial year.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import numpy as np
import pandas as pd

from lifecycle import operations_with_trial
from rules import criteria_flags

# Days either side of flowering treated as the flowering window (tassel to early silk).
FLOWERING_HALF_WINDOW = 14
IN_SEASON = ["vegetative", "flowering", "grain_fill"]


@dataclass(frozen=True)
class Evidence:
    """One column that describes a phase.

    ``op_type`` restricts operations to one type; ``trait`` restricts observations to
    one TRAIT_CODE. Both count trials with at least one such record.
    """

    table: str
    column: str
    op_type: str | None = None
    trait: str | None = None


@dataclass(frozen=True)
class Phase:
    """One step of the crop season, with the data that describes it and what is missing."""

    key: str
    name: str
    code: str
    window: str
    what_happens: str
    evidence: tuple[Evidence, ...]
    gap: str


MARKER_COLS = ["MARKER_DISEASE_RESISTANCE", "MARKER_YIELD_POTENTIAL",
               "MARKER_DROUGHT_TOLERANCE", "MARKER_MATURITY"]

PHASES: list[Phase] = [
    Phase("pre_season", "Line and genotype", "before sowing", "before planting",
          "The line exists, is genotyped, and has lab tests on its seed or tissue.",
          (Evidence("germplasm", "MATERIAL_ID"), Evidence("germplasm", "PEDIGREE"),
           Evidence("germplasm", "STAGE_CODE_LID"), Evidence("genomics", "GENOTYPING_DATE"),
           Evidence("genomics", "GENOMIC_BREEDING_VALUE"), Evidence("lab", "NUMBER_VALUE"),
           Evidence("lab", "OBSERVATION_DATE")),
          "Pedigree and lab dates are new in v3, but lab traits are still unnamed and "
          "genomics joins lines only by GUID position."),
    Phase("planting", "Planting and emergence", "VE", "day 0",
          "Seed goes in; seedlings emerge within about a week.",
          (Evidence("operations", "OPERATION_DATE", "PLANTING"), Evidence("trial", "START_YEAR"),
           Evidence("trial", "BEGIN_DATE")),
          "BEGIN_DATE is new in v3 and matches the start year; most operations do not."),
    Phase("vegetative", "Vegetative growth", "V1 to Vn", "day 0 to flowering - 14",
          "Leaves and stalk build up; the plant reaches its final height before tasselling.",
          (Evidence("recommendations", "PLANT_HEIGHT_CM"),
           Evidence("observation", "OBSERVATION_VALUE", trait="PLANT_HEIGHT_CM"),
           Evidence("operations", "OPERATION_DATE", "IRRIGATION"),
           Evidence("genomics", "MARKER_DROUGHT_TOLERANCE")),
          "Plot heights are dated but few per trial, and do not average to the trial value."),
    Phase("flowering", "Flowering", "VT / R1", "flowering ± 14 days",
          "Tassel and silks emerge and pollination sets kernel number. Water stress here "
          "costs the most yield.",
          (Evidence("recommendations", "FLOWERING_DAYS"),
           Evidence("observation", "OBSERVATION_VALUE", trait="FLOWERING_DAYS"),
           Evidence("genomics", "MARKER_MATURITY"),
           Evidence("operations", "OPERATION_DATE", "IRRIGATION")),
          "Flowering is a day count, not a date: it can only be placed where planting is recorded."),
    Phase("grain_fill", "Grain fill to maturity", "R2 to R6", "flowering + 14 to harvest",
          "Kernels fill and dry down to physiological maturity; disease now cuts grain fill.",
          (Evidence("recommendations", "DISEASE_SCORE"),
           Evidence("observation", "OBSERVATION_VALUE", trait="DISEASE_SCORE"),
           Evidence("genomics", "MARKER_DISEASE_RESISTANCE"),
           Evidence("operations", "OPERATION_DATE", "IRRIGATION")),
          "Plot disease scores do not average to the trial's score."),
    Phase("harvest", "Harvest", "harvest", "harvest operation",
          "Grain is harvested and weighed; moisture is measured at harvest.",
          (Evidence("operations", "OPERATION_DATE", "HARVEST"),
           Evidence("recommendations", "YIELD_T_HA"), Evidence("recommendations", "MOISTURE_PCT"),
           Evidence("observation", "OBSERVATION_VALUE", trait="YIELD_T_HA"),
           Evidence("observation", "OBSERVATION_VALUE", trait="MOISTURE_PCT"),
           Evidence("genomics", "MARKER_YIELD_POTENTIAL")),
          "Some harvests are dated before the trial's planting or expected flowering."),
    Phase("decision", "Recommendation", "decision", "after harvest",
          "Trial values run through the SYNTH_V1 rule to a PASS, HOLD or FAIL; each line "
          "carries its own advancement decision.",
          (Evidence("recommendations", "TRIAL_RECOMMENDATION"),
           Evidence("recommendations", "RECOMMENDATION_RATIONALE"),
           Evidence("recommendations", "RULE_VERSION"),
           Evidence("germplasm", "ADVANCEMENT_DECISION")),
          "No decision date; the rationale omits the resistant-material criterion, and no "
          "rule links a line's decision to its trials' verdicts."),
]
PHASE_NAMES = {p.key: p.name for p in PHASES}


def _coverage(t: dict[str, pd.DataFrame], e: Evidence) -> tuple[int, int, str]:
    """(present, total, unit) for one evidence column; op types count trials with that op."""
    df = t[e.table]
    if e.op_type or e.trait:
        key, val = ("OPERATION_TYPE_LID", e.op_type) if e.op_type else ("TRAIT_CODE", e.trait)
        rows = df[(df[key] == val) & df[e.column].notna()]
        return cast(pd.Series, rows["TRIAL_GUID"]).nunique(), len(t["trial"]), "trials"
    return int(cast(pd.Series, df[e.column]).notna().sum()), len(df), "rows"


def phase_map(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One row per phase and evidence column, with how much of that column is filled."""
    rows = []
    for i, p in enumerate(PHASES):
        for e in p.evidence:
            present, total, unit = _coverage(t, e)
            tag = e.op_type or e.trait
            label = f"{e.column} ({tag.lower()})" if tag else e.column
            rows.append({"order": i, "phase": p.name, "stage_code": p.code, "when": p.window,
                         "source": e.table, "column": label, "present": present,
                         "total": total, "unit": unit, "gap": p.gap})
    return pd.DataFrame(rows)


def classify_operation(dap: float, flowering_days: float,
                       harvest_dap: float = np.nan) -> str:
    """Growth phase for an event ``dap`` days after planting.

    Args:
        dap: Days after the trial's first planting; NaN if the trial has no planting.
        flowering_days: The trial's days to flowering.
        harvest_dap: Days after planting of the trial's first harvest, if any.

    Returns:
        A phase key from ``IN_SEASON``, or ``before_planting``, ``after_harvest`` or
        ``unplaced`` (no planting to anchor on).
    """
    if np.isnan(dap):
        return "unplaced"
    if dap < 0:
        return "before_planting"
    if not np.isnan(harvest_dap) and 0 <= harvest_dap < dap:
        return "after_harvest"
    if dap < flowering_days - FLOWERING_HALF_WINDOW:
        return "vegetative"
    if dap <= flowering_days + FLOWERING_HALF_WINDOW:
        return "flowering"
    return "grain_fill"


def _anchors(ops: pd.DataFrame) -> pd.DataFrame:
    """Per TRIAL_GUID: first planting and first harvest date."""
    first = ops.pivot_table(index="TRIAL_GUID", columns="OPERATION_TYPE_LID", values="date",
                            aggfunc="min")
    return first.reindex(columns=["PLANTING", "HARVEST"]).rename(
        columns={"PLANTING": "planting_date", "HARVEST": "harvest_date"})


def operation_phases(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Every operation with its days after planting and the growth phase it falls in."""
    ops = operations_with_trial(t)
    flower = t["recommendations"].set_index("TRIAL_GUID")["FLOWERING_DAYS"]
    ops = ops.join(_anchors(ops), on="TRIAL_GUID").assign(
        FLOWERING_DAYS=lambda d: d["TRIAL_GUID"].map(flower))
    ops["dap"] = (ops["date"] - ops["planting_date"]).dt.days
    ops["harvest_dap"] = (ops["harvest_date"] - ops["planting_date"]).dt.days
    ops["phase"] = [
        "planting" if op == "PLANTING" and dap == 0 else
        "harvest" if op == "HARVEST" and dap == hdap else
        classify_operation(float(dap), float(f), float(hdap))
        for op, dap, hdap, f in zip(ops["OPERATION_TYPE_LID"], ops["dap"], ops["harvest_dap"],
                                    ops["FLOWERING_DAYS"])
    ]
    return ops


def verdict_reason(flags: dict[str, bool], verdict: str) -> str:
    """Plain-English reason for a verdict from one row of ``criteria_flags``."""
    if verdict == "FAIL":
        kos = [txt for col, txt in [("ko_yield", "yield below 7 t/ha"),
                                    ("ko_disease", "disease score above 7")] if flags[col]]
        return " and ".join(kos) or "no knockout reproduces it"
    missed = [txt for col, txt in [("yield_ok", "yield target"), ("moisture_ok", "moisture limit"),
                                   ("disease_ok", "disease limit"), ("gbv_ok", "GBV target"),
                                   ("resistant_ok", "resistant-material share")]
              if not flags[col]]
    return "misses the " + ", ".join(missed) if missed else "meets all five criteria"


def _flags(tl: pd.DataFrame, ops: pd.DataFrame) -> pd.DataFrame:
    off_year = (ops["date"].dt.year != ops["START_YEAR"]).groupby(ops["TRIAL_GUID"]).any()
    return tl.assign(
        no_planting=tl["planting_date"].isna(),
        no_harvest=tl["harvest_date"].isna(),
        harvest_before_planting=tl["season_days"] < 0,
        harvest_before_flowering=tl["season_days"].between(0, tl["FLOWERING_DAYS"],
                                                           inclusive="left"),
        date_outside_start_year=tl["TRIAL_GUID"].map(off_year).fillna(False).astype(bool),
    )


def trial_timeline(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One row per trial: season anchors, irrigation per phase, anomaly flags and a narrative."""
    rec = t["recommendations"]
    ops = operation_phases(t)
    cols = ["TRIAL_GUID", "TRIAL_ID", "START_YEAR", "FLOWERING_DAYS", "TRIAL_RECOMMENDATION"]
    tl = rec[cols].join(_anchors(ops), on="TRIAL_GUID")
    days = cast(pd.Series, tl["FLOWERING_DAYS"]).to_numpy(dtype=float)
    tl["flowering_date"] = tl["planting_date"] + pd.to_timedelta(days, unit="D")
    tl["season_days"] = (tl["harvest_date"] - tl["planting_date"]).dt.days
    irr = ops[ops["OPERATION_TYPE_LID"] == "IRRIGATION"]
    counts = pd.crosstab(irr["TRIAL_GUID"], irr["phase"]).add_prefix("irrigation_")
    tl = tl.join(counts, on="TRIAL_GUID")
    irr_cols = [c for c in tl if c.startswith("irrigation_")]
    tl[irr_cols] = tl[irr_cols].fillna(0).astype(int)
    tl["reason"] = [verdict_reason(f, v) for f, v in
                    zip(criteria_flags(rec).to_dict("records"), rec["TRIAL_RECOMMENDATION"])]
    tl = _flags(tl, ops)
    tl["narrative"] = [describe_trial(r) for r in tl.to_dict("records")]
    return cast(pd.DataFrame, tl)


def _day(d: object) -> str:
    return f"{pd.Timestamp(cast(str, d)):%d %b %Y}"


def _missing(v: object) -> bool:
    return bool(pd.isna(cast(float, v)))


def _irrigation_text(r: dict[str, object]) -> str:
    parts = [f"{r[f'irrigation_{k}']}× {PHASE_NAMES.get(k, k.replace('_', ' ')).lower()}"
             for k in [*IN_SEASON, "before_planting", "after_harvest"]
             if int(cast(int, r.get(f"irrigation_{k}", 0))) > 0]
    return "irrigated " + ", ".join(parts) if parts else "no irrigation recorded"


def describe_trial(r: dict[str, object]) -> str:
    """One sentence saying what happened to a trial's crop, and when.

    Args:
        r: A ``trial_timeline`` row as a dict (anchors, irrigation counts, reason).

    Returns:
        The narrative. Missing anchors read "not recorded"; nothing is inferred for them.
    """
    head = f"{r['TRIAL_ID']} ({r['START_YEAR']} trial"
    head += ", operations dated in another year ⚠)" if r["date_outside_start_year"] else ")"
    verdict = f"Verdict {r['TRIAL_RECOMMENDATION']}: {r['reason']}."
    if _missing(r["planting_date"]):
        harvest = ("no harvest recorded" if _missing(r["harvest_date"])
                   else "harvest " + _day(r["harvest_date"]))
        return (f"{head}: planting not recorded, so the season cannot be placed "
                f"({harvest}; flowering at day {r['FLOWERING_DAYS']:.0f} has no anchor). {verdict}")
    steps = [f"planted {_day(r['planting_date'])}", _irrigation_text(r),
             f"flowering expected ~day {r['FLOWERING_DAYS']:.0f} ({_day(r['flowering_date'])})"]
    if _missing(r["harvest_date"]):
        steps.append("harvest not recorded")
    else:
        warn = (" – before planting ⚠" if r["harvest_before_planting"] else
                " – before expected flowering ⚠" if r["harvest_before_flowering"] else "")
        steps.append(f"harvested {_day(r['harvest_date'])} (day {r['season_days']:.0f}){warn}")
    return f"{head}: " + "; ".join(steps) + f". {verdict}"


def lifecycle_coverage(tl: pd.DataFrame) -> dict[str, int]:
    """How many trials can be placed on a season, and how many read in a plausible order."""
    f = {c: cast(pd.Series, tl[c]).astype(bool) for c in
         ["no_planting", "no_harvest", "harvest_before_planting", "harvest_before_flowering"]}
    placed = ~f["no_planting"]
    both = placed & ~f["no_harvest"]
    in_order = both & ~f["harvest_before_planting"] & ~f["harvest_before_flowering"]
    return {"trials": len(tl), "placed": int(placed.sum()), "planting_and_harvest": int(both.sum()),
            "in_order": int(in_order.sum())}
