"""Consistency flags: what the data profile found, attached to trials, operations and lines.

Each flag cites the rows it rests on (``"<source_file>#<row_id>"``) and never changes a
SYNTH_V1 verdict. The conditions reuse ``lifecycle.operation_checks`` and
``rules.genomics_reconciliation`` / ``rules.rationale_flags``, so the counts are those of
the EDA's ``chronology_checks.csv``. A check with a missing side raises no flag.

One function per code (named as the code, lower-case) returns
``{key GUID: (Flag,)}``; ``all_flags`` combines them into a ``FlagIndex``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

import pandas as pd

from uc4_mcp.lifecycle import operation_checks, snapshot_date
from uc4_mcp.models import Flag, evidence_ref
from uc4_mcp.rules import _num, genomics_reconciliation, rationale_flags

Tables = dict[str, pd.DataFrame]
FlagMap = dict[str, tuple[Flag, ...]]


@dataclass(frozen=True)
class FlagSpec:
    """Catalogue entry: what a flag is keyed on, how serious it is, what it means."""

    scope: str  # "trial" | "operation" | "line"
    severity: str  # one of models.SEVERITIES
    meaning: str


# Catalogue order is the order flags are listed in, per key.
FLAG_CODES: Mapping[str, FlagSpec] = MappingProxyType({
    "THRESHOLDS_INFERRED": FlagSpec(
        "trial", "info", "SYNTH_V1 thresholds are inferred from the supplied verdicts, "
                         "not a supplied rule"),
    "AGGREGATE_LINKS_UNVERIFIED": FlagSpec(
        "trial", "info", "Supplied GBV mean or resistant % does not match the lines the "
                         "observation file links to the trial"),
    "RATIONALE_READS_AS_PASS": FlagSpec(
        "trial", "warning", "Rationale reports all four criteria met, but the verdict is "
                            "not PASS"),
    "OPS_OUTSIDE_TRIAL_YEAR": FlagSpec(
        "operation", "warning", "Operation dated outside its trial's start year"),
    "PLANNED_OPS_PAST_EXTRACT": FlagSpec(
        "operation", "warning", "Operation still PLANNED but dated before the extract"),
    "COMPLETE_TRIAL_HAS_PLANNED_OPS": FlagSpec(
        "trial", "warning", "Trial is COMPLETE but has operations still PLANNED"),
    "OP_LINE_NOT_IN_TRIAL": FlagSpec(
        "operation", "warning", "Operation's line is not linked to its trial in the "
                                "observation file"),
    "LAB_NOT_TRIAL_LINKED": FlagSpec(
        "line", "info", "Lab results carry no trial key, so they cannot be tied to a trial"),
})


@dataclass(frozen=True)
class FlagIndex:
    """All flags by key GUID; keys sorted, flags in catalogue order. Read-only."""

    by_trial: Mapping[str, tuple[Flag, ...]]
    by_operation: Mapping[str, tuple[Flag, ...]]
    by_line: Mapping[str, tuple[Flag, ...]]


def _refs(df: pd.DataFrame) -> list[str]:
    return [evidence_ref(r) for r in df[["_source_file", "_row_id"]].to_dict("records")]


def _flag(code: str, message: str, refs: Iterable[str]) -> Flag:
    return Flag(code=code, severity=FLAG_CODES[code].severity, message=message,
                evidence_row_ids=tuple(refs))


def _one(code: str, items: Iterable[tuple[Any, str, Iterable[str]]]) -> FlagMap:
    return {str(key): (_flag(code, message, refs),) for key, message, refs in items}


def _day(value: Any) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")


# --- trial scope ------------------------------------------------------------


def thresholds_inferred(t: Tables) -> FlagMap:
    """Every recommendation: the SYNTH_V1 cut-points are inferred, not supplied."""
    rec = t["recommendations"]
    return _one("THRESHOLDS_INFERRED", (
        (guid, "SYNTH_V1 thresholds are inferred from the supplied verdicts; confirm with "
               "the SME", [ref])
        for guid, ref in zip(rec["TRIAL_GUID"], _refs(rec))))


def _compare(label: str, supplied: Any, recomputed: Any, checkable: bool, match: bool) -> str:
    if not checkable:
        return f"{label} not checkable"
    return f"{label} {_num(supplied)} {'=' if match else '≠'} {_num(recomputed)}"


def aggregate_links_unverified(t: Tables) -> FlagMap:
    """Supplied GBV mean or resistant % differs from the observation-linked lines.

    Each side is compared only when both the supplied value and the recomputed one
    exist; a trial with neither comparison possible gets no flag.
    """
    recon = genomics_reconciliation(t).set_index("TRIAL_GUID")
    rec = t["recommendations"].set_index("TRIAL_GUID")
    obs = t["observation"]
    gen = t["genomics"]
    out: FlagMap = {}
    for guid, r in recon.iterrows():
        gbv_ok = pd.notna(r["GENOMIC_BREEDING_VALUE_MEAN"]) and pd.notna(r["gbv_observation"])
        res_ok = pd.notna(r["RESISTANT_MATERIAL_PCT"]) and pd.notna(r["resistant_observation"])
        gbv_bad = gbv_ok and not r["gbv_match_observation"]
        res_bad = res_ok and not r["resistant_match_observation"]
        if not (gbv_bad or res_bad):
            continue
        links = obs[obs["ATTACHED_TO_FIELD_ENTITY_ID"] == guid]
        lines = gen[gen["MATERIAL_GUID"].isin(links["GID"])]
        gbv = _compare("GBV mean", r["GENOMIC_BREEDING_VALUE_MEAN"], r["gbv_observation"],
                       gbv_ok, not gbv_bad)
        res = _compare("resistant %", r["RESISTANT_MATERIAL_PCT"], r["resistant_observation"],
                       res_ok, not res_bad)
        message = (f"Supplied {gbv} over the {_num(r['n_observation'])} observation-linked "
                   f"lines; {res}")
        refs = _refs(rec.loc[[guid]]) + _refs(links) + _refs(lines)
        out[str(guid)] = (_flag("AGGREGATE_LINKS_UNVERIFIED", message, refs),)
    return out


def rationale_reads_as_pass(t: Tables) -> FlagMap:
    """Rationale text reports all four criteria met, yet the supplied verdict is not PASS."""
    rec = t["recommendations"]
    has_text = rec["RECOMMENDATION_RATIONALE"].map(lambda v: isinstance(v, str))
    all_four = rationale_flags(rec).fillna(False).astype(bool).all(axis=1)
    hit = rec[has_text & all_four & (rec["TRIAL_RECOMMENDATION"] != "PASS")]
    return _one("RATIONALE_READS_AS_PASS", (
        (guid, f"Rationale reports all four criteria met, but the verdict is {verdict}", [ref])
        for guid, verdict, ref in zip(hit["TRIAL_GUID"], hit["TRIAL_RECOMMENDATION"],
                                      _refs(hit))))


def complete_trial_has_planned_ops(t: Tables) -> FlagMap:
    """A COMPLETE trial with at least one operation still PLANNED."""
    trial = t["trial"]
    ops = t["operations"]
    planned = ops[ops["OPERATION_STATUS_LID"] == "PLANNED"]
    out: FlagMap = {}
    for guid, status, ref in zip(trial["TRIAL_GUID"], trial["STATUS_LID"], _refs(trial)):
        rows = planned[planned["TRIAL_GUID"] == guid]
        if status != "COMPLETE" or rows.empty:
            continue
        n = len(rows)
        noun = "operation is" if n == 1 else "operations are"
        out[str(guid)] = (_flag("COMPLETE_TRIAL_HAS_PLANNED_OPS",
                                f"Trial is COMPLETE but {n} {noun} still PLANNED",
                                [ref, *_refs(rows)]),)
    return out


# --- operation scope --------------------------------------------------------


def _flagged_ops(t: Tables, column: str) -> pd.DataFrame:
    """Operation rows (with provenance) whose ``operation_checks`` column is 1.0."""
    oc = operation_checks(t)
    hit = oc.loc[oc[column] == 1.0, "OPERATION_GUID"]
    ops = t["operations"]
    return ops[ops["OPERATION_GUID"].isin(hit) & ops["OPERATION_GUID"].notna()]


def ops_outside_trial_year(t: Tables) -> FlagMap:
    """Operation dated in a year other than its trial's ``START_YEAR``."""
    ops = _flagged_ops(t, "wrong_year")
    trial = t["trial"].set_index("TRIAL_GUID")
    trial_ref = dict(zip(trial.index, _refs(trial)))
    return _one("OPS_OUTSIDE_TRIAL_YEAR", (
        (r["OPERATION_GUID"],
         f"{r['OPERATION_TYPE_LID']} on {_day(r['OPERATION_DATE'])} is outside trial start "
         f"year {_num(trial.loc[r['TRIAL_GUID'], 'START_YEAR'])}",
         [ref, trial_ref[r["TRIAL_GUID"]]])
        for r, ref in zip(ops.to_dict("records"), _refs(ops))))


def planned_ops_past_extract(t: Tables) -> FlagMap:
    """PLANNED operation dated before the extract (``lifecycle.snapshot_date``)."""
    ops = _flagged_ops(t, "planned_past_extract")
    snap = snapshot_date(t).strftime("%Y-%m-%d %H:%M")
    return _one("PLANNED_OPS_PAST_EXTRACT", (
        (r["OPERATION_GUID"],
         f"{r['OPERATION_TYPE_LID']} dated {_day(r['OPERATION_DATE'])} is still PLANNED at "
         f"the extract ({snap})", [ref])
        for r, ref in zip(ops.to_dict("records"), _refs(ops))))


def op_line_not_in_trial(t: Tables) -> FlagMap:
    """Operation's (trial, line) pair has no observation row; the absent link can't be cited."""
    ops = _flagged_ops(t, "unlinked")
    ids = dict(zip(t["germplasm"]["MATERIAL_GUID"], t["germplasm"]["MATERIAL_ID"]))
    ids.update(zip(t["trial"]["TRIAL_GUID"], t["trial"]["TRIAL_ID"]))
    return _one("OP_LINE_NOT_IN_TRIAL", (
        (r["OPERATION_GUID"],
         f"{r['OPERATION_TYPE_LID']} is for line {ids.get(r['MATERIAL_GUID'], r['MATERIAL_GUID'])}, "
         f"which has no observation row in trial {ids.get(r['TRIAL_GUID'], r['TRIAL_GUID'])}",
         [ref])
        for r, ref in zip(ops.to_dict("records"), _refs(ops))))


# --- line scope -------------------------------------------------------------


def lab_not_trial_linked(t: Tables) -> FlagMap:
    """Every line with lab rows: the lab file has no trial key."""
    lab = t["lab"][t["lab"]["MATERIAL_GUID"].notna()]
    out: FlagMap = {}
    for guid, rows in lab.groupby("MATERIAL_GUID", sort=True):
        n = len(rows)
        noun = "lab result has" if n == 1 else "lab results have"
        out[str(guid)] = (_flag("LAB_NOT_TRIAL_LINKED",
                                f"{n} {noun} no trial key, so cannot be tied to a trial",
                                _refs(rows)),)
    return out


# --- index ------------------------------------------------------------------


_FUNCTIONS: dict[str, Callable[[Tables], FlagMap]] = {
    code: globals()[code.lower()] for code in FLAG_CODES}


def _frozen(flags: dict[str, list[Flag]]) -> Mapping[str, tuple[Flag, ...]]:
    rank = {c: i for i, c in enumerate(FLAG_CODES)}
    return MappingProxyType({
        k: tuple(sorted(flags[k], key=lambda f: (rank[f.code], f.evidence_row_ids)))
        for k in sorted(flags)})


def all_flags(t: Tables) -> FlagIndex:
    """Run every check once; flags grouped by the key their scope names."""
    scopes: dict[str, dict[str, list[Flag]]] = {"trial": {}, "operation": {}, "line": {}}
    for code, spec in FLAG_CODES.items():
        for key, flags in _FUNCTIONS[code](t).items():
            scopes[spec.scope].setdefault(key, []).extend(flags)
    return FlagIndex(by_trial=_frozen(scopes["trial"]),
                     by_operation=_frozen(scopes["operation"]),
                     by_line=_frozen(scopes["line"]))
