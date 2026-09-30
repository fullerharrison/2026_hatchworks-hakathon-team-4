"""EvidenceStore: every question the tools answer, over the seven v2 tables, with sources.

Built once from the loaded tables: SYNTH_V1 recommendations (``explain()`` plus the
trial-scope flags), the consistency flags, and row indexes. Views cite each value as an
``EvidenceRow`` (file, row key, line number). The store is read-only and knows nothing
about MCP; ``server.py`` wraps it.
"""

from __future__ import annotations

import dataclasses
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd

from uc4_mcp.checks import FLAG_CODES, all_flags
from uc4_mcp.models import (Candidate, EvidenceRow, Flag, LineTrial, LineView, OperationView,
                            Recommendation, Resolution, TrialLine, TrialView, none, ok,
                            to_json_safe)
from uc4_mcp.rules import CRITERIA, explain, genomics_reconciliation, threshold_intervals
from uc4_mcp.sources import find_zip, lab_trait_label, load_tables

Tables = dict[str, pd.DataFrame]
Record = dict[str, Any]

MAX_CANDIDATES = 20
# Table key -> the (field, unit) pairs cited as EvidenceRows. Lab rows cite NUMBER_VALUE
# under the trait's label (the file names no traits).
VALUE_FIELDS: dict[str, tuple[tuple[str, str | None], ...]] = {
    "germplasm": (("MATERIAL_ID", None),),
    "trial": (("START_YEAR", None), ("STATUS_LID", None), ("LOCATION_GUID", None)),
    "observation": (("REPLICATION_NO", None),),
    "operations": (("OPERATION_TYPE_LID", None), ("OPERATION_STATUS_LID", None)),
    "lab": (("NUMBER_VALUE", None),),
    "genomics": (("GENOMIC_BREEDING_VALUE", None), ("MARKER_DISEASE_RESISTANCE", None),
                 ("MARKER_YIELD_POTENTIAL", None), ("MARKER_DROUGHT_TOLERANCE", None),
                 ("MARKER_MATURITY", None), ("QC_STATUS_LID", None), ("QC_CALL_RATE_PCT", "%")),
    "recommendations": (("YIELD_T_HA", "t/ha"), ("MOISTURE_PCT", "%"), ("DISEASE_SCORE", "score"),
                        ("PLANT_HEIGHT_CM", "cm"), ("FLOWERING_DAYS", "days"),
                        ("GENOMIC_BREEDING_VALUE_MEAN", None), ("RESISTANT_MATERIAL_PCT", "%"),
                        ("GENOMICS_QC_PASS_PCT", "%")),
}
DATE_FIELDS: dict[str, str] = {"operations": "OPERATION_DATE", "genomics": "GENOTYPING_DATE"}
# Which column holds the trial / material key; lab and genomics rows have no trial key.
TRIAL_KEY: dict[str, str] = {"trial": "TRIAL_GUID", "recommendations": "TRIAL_GUID",
                             "operations": "TRIAL_GUID",
                             "observation": "ATTACHED_TO_FIELD_ENTITY_ID"}
MATERIAL_KEY: dict[str, str] = {"germplasm": "MATERIAL_GUID", "observation": "GID",
                                "operations": "MATERIAL_GUID", "lab": "MATERIAL_GUID",
                                "genomics": "MATERIAL_GUID"}
TRIAL_LINE_GENOMICS = ("GENOMIC_BREEDING_VALUE", "MARKER_DISEASE_RESISTANCE")
LINE_NOTE = ("Verdicts are per trial: each is the SYNTH_V1 (inferred) verdict of a trial this "
             "line appears in, not a verdict on the line.")

VERDICTS = ("PASS", "HOLD", "FAIL")
KNOCKOUTS: dict[str, frozenset[str]] = {
    "yield": frozenset({"YIELD_T_HA"}), "disease": frozenset({"DISEASE_SCORE"}),
    "both": frozenset({"YIELD_T_HA", "DISEASE_SCORE"})}
MISSED_FIELDS = tuple(s.field for s in CRITERIA if s.kind == "pass")
QUERY_FLAGS = tuple(c for c, s in FLAG_CODES.items() if s.scope in ("trial", "operation"))


def _text(value: Any) -> str | None:
    return None if value is None or pd.isna(value) else str(value)


def _plural(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def resolve(query: str, keys: pd.DataFrame, kind: str) -> Resolution:
    """Resolve a query against ``keys`` (columns ``id``, ``guid``, ``label``).

    Order: exact GUID, then exact ID, then ID fragment, all case-insensitive. GUIDs never
    match as fragments: their hex sequence suffixes would add false hits.
    """
    shown = query.strip()
    q = shown.upper()
    if not q:
        return Resolution("none", None, (), f"Empty query; give a {kind} ID, ID fragment or GUID")
    ids = keys["id"].str.upper()
    for mask in (keys["guid"].str.upper() == q, ids == q):
        if mask.any():
            hit = keys[mask].iloc[0]
            return Resolution("ok", str(hit["guid"]), (), str(hit["id"]))
    hits = keys[ids.str.contains(q, regex=False)].sort_values("id")
    if hits.empty:
        return Resolution("none", None, (), f"No {kind} matches '{shown}'")
    if len(hits) == 1:
        return Resolution("ok", str(hits["guid"].iloc[0]), (), str(hits["id"].iloc[0]))
    candidates = tuple(Candidate(id=str(r["id"]), guid=str(r["guid"]), label=str(r["label"]))
                       for r in hits.head(MAX_CANDIDATES).to_dict("records"))
    message = f"{len(hits)} {kind}s match '{shown}'; which one?"
    if len(hits) > MAX_CANDIDATES:
        message = (f"{len(hits)} {kind}s match '{shown}'; showing the first {MAX_CANDIDATES}; "
                   "refine the query")
    return Resolution("many", None, candidates, message)


def _group(records: Iterable[Record], column: str) -> dict[str, list[Record]]:
    out: dict[str, list[Record]] = defaultdict(list)
    for r in records:
        if pd.notna(r[column]):
            out[str(r[column])].append(r)
    return out


class EvidenceStore:
    """Read-only answers over the seven tables; build once with ``from_tables``/``from_zip``.

    Attributes:
        tables: The loaded tables, with provenance columns.
        flags: Every consistency flag (``checks.all_flags``).
        trial_guids: Trial GUIDs in ``TRIAL_ID`` order.
        line_guids: Line (material) GUIDs in ``MATERIAL_ID`` order.
        operation_trial: Operation GUID -> its trial GUID.
    """

    def __init__(self, tables: Tables) -> None:
        self.tables = tables
        self.flags = all_flags(tables)
        records = {k: df.to_dict("records") for k, df in tables.items()}
        self._rows = {k: {str(r["_row_id"]): r for r in rs} for k, rs in records.items()}
        self._obs_by_trial = _group(records["observation"], "ATTACHED_TO_FIELD_ENTITY_ID")
        self._obs_by_line = _group(records["observation"], "GID")
        self._ops_by_trial = _group(records["operations"], "TRIAL_GUID")
        self._ops_by_line = _group(records["operations"], "MATERIAL_GUID")
        self._lab_by_line = _group(records["lab"], "MATERIAL_GUID")
        self._gen_by_line = _group(records["genomics"], "MATERIAL_GUID")
        trial, germplasm = tables["trial"], tables["germplasm"]
        self.trial_guids = tuple(trial.sort_values("TRIAL_ID")["TRIAL_GUID"])
        self.line_guids = tuple(germplasm.sort_values("MATERIAL_ID")["MATERIAL_GUID"])
        self._trial_id = dict(zip(trial["TRIAL_GUID"], trial["TRIAL_ID"]))
        self._material_id = dict(zip(germplasm["MATERIAL_GUID"], germplasm["MATERIAL_ID"]))
        self.operation_trial = dict(zip(tables["operations"]["OPERATION_GUID"],
                                        tables["operations"]["TRIAL_GUID"]))
        self._recs = self._recommendations(tables["recommendations"])
        self._linked = genomics_reconciliation(tables).set_index("TRIAL_GUID")[
            ["gbv_observation", "resistant_observation"]].to_dict("index")
        self._flag_trials = self._trials_by_flag()
        self._trial_keys = pd.DataFrame(
            [{"id": self._trial_id[g], "guid": g,
              "label": f"{self._trial_id[g]} ({self._rows['trial'][g]['START_YEAR']}, "
                       f"{self._recs[g].verdict})"} for g in self.trial_guids])
        self._line_keys = pd.DataFrame(
            [{"id": self._material_id[g], "guid": g,
              "label": f"{self._material_id[g]} ({_plural(len(self._obs_by_line[g]), 'trial')})"}
             for g in self.line_guids])

    @classmethod
    def from_tables(cls, tables: Tables) -> EvidenceStore:
        """Build from tables loaded by ``sources.load_tables``."""
        return cls(tables)

    @classmethod
    def from_zip(cls, zip_path: Path | None = None) -> EvidenceStore:
        """Load the v2 archive (``sources.find_zip`` when no path is given) and build."""
        return cls(load_tables(zip_path or find_zip()))

    def _recommendations(self, rec: pd.DataFrame) -> dict[str, Recommendation]:
        intervals = threshold_intervals(rec)
        return {str(row["TRIAL_GUID"]): dataclasses.replace(
                    explain(row, intervals),
                    flags=self.flags.by_trial.get(str(row["TRIAL_GUID"]), ()))
                for _, row in rec.iterrows()}

    def _trials_by_flag(self) -> dict[str, set[str]]:
        out: dict[str, set[str]] = defaultdict(set)
        for guid, flags in self.flags.by_trial.items():
            for f in flags:
                out[f.code].add(guid)
        for op, flags in self.flags.by_operation.items():
            for f in flags:
                out[f.code].add(self.operation_trial[op])
        return out

    # --- resolution ---------------------------------------------------------

    def resolve_trial(self, query: str) -> Resolution:
        """Trial by ID, GUID or ID fragment (e.g. ``"0037"``)."""
        return resolve(query, self._trial_keys, "trial")

    def resolve_line(self, query: str) -> Resolution:
        """Line by ID, GUID or ID fragment (e.g. ``"SYN-MZ-00001"``)."""
        return resolve(query, self._line_keys, "line")

    # --- evidence -----------------------------------------------------------

    def _evidence(self, key: str, r: Record, fields: Iterable[str] | None = None,
                  flags: tuple[str, ...] = ()) -> tuple[EvidenceRow, ...]:
        units = dict(VALUE_FIELDS[key])
        date_col = DATE_FIELDS.get(key)
        date = _text(r[date_col]) if date_col else None
        return tuple(EvidenceRow(
            source_file=str(r["_source_file"]), row_id=str(r["_row_id"]),
            line_no=int(r["_line_no"]),
            trial_guid=_text(r[TRIAL_KEY[key]]) if key in TRIAL_KEY else None,
            material_guid=_text(r[MATERIAL_KEY[key]]) if key in MATERIAL_KEY else None,
            field=lab_trait_label(str(r["TRAIT_GUID"])) if key == "lab" else field,
            value=to_json_safe(r[field]), uom=units[field],
            date=date[:10] if date else None, flags=flags)
            for field in (fields if fields is not None else units))

    def _operations(self, records: Iterable[Record]) -> tuple[OperationView, ...]:
        views = []
        for r in records:
            guid = str(r["OPERATION_GUID"])
            codes = tuple(f.code for f in self.flags.by_operation.get(guid, ()))
            evidence = self._evidence("operations", r, flags=codes)
            views.append(OperationView(
                operation_guid=guid, operation_type=str(r["OPERATION_TYPE_LID"]),
                status=str(r["OPERATION_STATUS_LID"]), date=evidence[0].date,
                evidence=evidence))
        return tuple(sorted(views, key=lambda o: (o.date or "", o.operation_guid)))

    def _operation_flags(self, ops: Iterable[OperationView]) -> tuple[Flag, ...]:
        return tuple(f for o in ops for f in self.flags.by_operation.get(o.operation_guid, ()))

    # --- views --------------------------------------------------------------

    def recommendation(self, trial_guid: str) -> Recommendation:
        """The SYNTH_V1 recommendation for a trial GUID, with its trial-scope flags.

        Raises:
            KeyError: If the GUID is not a trial.
        """
        return self._recs[trial_guid]

    def trial_view(self, trial_guid: str) -> TrialView:
        """Meta, trial values, verdict, the 10 observation-linked lines, operations, flags.

        Raises:
            KeyError: If the GUID is not a trial.
        """
        trial = self._rows["trial"][trial_guid]
        rec_row = self._rows["recommendations"][trial_guid]
        links = sorted(self._obs_by_trial.get(trial_guid, []),
                       key=lambda o: self._material_id.get(o["GID"], o["GID"]))
        lines = tuple(TrialLine(
            material_guid=str(o["GID"]), material_id=str(self._material_id.get(o["GID"], o["GID"])),
            link=self._evidence("observation", o)[0],
            genomics=tuple(e for g in self._gen_by_line.get(o["GID"], [])
                           for e in self._evidence("genomics", g, TRIAL_LINE_GENOMICS)))
            for o in links)
        ops = self._operations(self._ops_by_trial.get(trial_guid, []))
        linked = self._linked.get(trial_guid, {})
        return TrialView(
            trial_guid=trial_guid, trial_id=str(trial["TRIAL_ID"]),
            meta=self._evidence("trial", trial), values=self._evidence("recommendations", rec_row),
            recommendation=self._recs[trial_guid],
            supplied_gbv_mean=to_json_safe(rec_row["GENOMIC_BREEDING_VALUE_MEAN"]),
            linked_gbv_mean=to_json_safe(linked.get("gbv_observation")),
            supplied_resistant_pct=to_json_safe(rec_row["RESISTANT_MATERIAL_PCT"]),
            linked_resistant_pct=to_json_safe(linked.get("resistant_observation")),
            lines=lines, operations=ops,
            flags=self.flags.by_trial.get(trial_guid, ()) + self._operation_flags(ops))

    def line_view(self, material_guid: str) -> LineView:
        """Identity, genomics, lab rows, the trials the line is in (with each trial's
        verdict), its operations and flags.

        Raises:
            KeyError: If the GUID is not a line.
        """
        line = self._rows["germplasm"][material_guid]
        lab_codes = tuple(f.code for f in self.flags.by_line.get(material_guid, ()))
        trials = tuple(sorted((LineTrial(
            trial_guid=str(o["ATTACHED_TO_FIELD_ENTITY_ID"]),
            trial_id=str(self._trial_id[o["ATTACHED_TO_FIELD_ENTITY_ID"]]),
            verdict=(rec := self._recs[o["ATTACHED_TO_FIELD_ENTITY_ID"]]).verdict,
            colour=rec.colour, reason=rec.reason, link=self._evidence("observation", o)[0])
            for o in self._obs_by_line.get(material_guid, [])), key=lambda t: t.trial_id))
        ops = self._operations(self._ops_by_line.get(material_guid, []))
        return LineView(
            material_guid=material_guid, material_id=str(line["MATERIAL_ID"]),
            identity=self._evidence("germplasm", line),
            genomics=tuple(e for g in self._gen_by_line.get(material_guid, [])
                           for e in self._evidence("genomics", g)),
            lab=tuple(e for r in self._lab_by_line.get(material_guid, [])
                      for e in self._evidence("lab", r, flags=lab_codes)),
            trials=trials, operations=ops,
            flags=self.flags.by_line.get(material_guid, ()) + self._operation_flags(ops),
            note=LINE_NOTE)

    # --- queries ------------------------------------------------------------

    def _invalid(self, verdict: str | None, knockout: str | None, missed: str | None,
                 only: bool, flag: str | None) -> str | None:
        if verdict is not None and verdict.upper() not in VERDICTS:
            return f"Unknown verdict '{verdict}'; valid: {', '.join(VERDICTS)}"
        if knockout is not None and knockout.lower() not in KNOCKOUTS:
            return f"Unknown knockout '{knockout}'; valid: {', '.join(KNOCKOUTS)}"
        if missed is not None and missed.upper() not in MISSED_FIELDS:
            return f"Unknown criterion '{missed}'; valid: {', '.join(MISSED_FIELDS)}"
        if flag is not None and flag.upper() not in QUERY_FLAGS:
            return (f"'{flag}' is not a trial or operation flag; valid: "
                    f"{', '.join(QUERY_FLAGS)}")
        if only and missed is None and knockout is None:
            return "only=true needs missed or knockout"
        return None

    def _matches(self, rec: Recommendation, verdict: str | None, knockout: str | None,
                 missed: str | None, only: bool, flag: str | None) -> bool:
        unmet = [c.field for c in rec.criteria if c.kind == "pass" and not c.passed]
        fired = {c.field for c in rec.criteria if c.triggered}
        if verdict is not None and rec.verdict != verdict.upper():
            return False
        if missed is not None and (missed.upper() not in unmet
                                   or (only and unmet != [missed.upper()])):
            return False
        want = KNOCKOUTS[knockout.lower()] if knockout is not None else frozenset()
        if knockout is not None and (not want <= fired or (only and fired != want)):
            return False
        return flag is None or rec.trial_guid in self._flag_trials[flag.upper()]

    def query_trials(self, verdict: str | None = None, knockout: str | None = None,
                     missed: str | None = None, only: bool = False,
                     flag: str | None = None) -> dict[str, Any]:
        """Trials matching every given filter (AND), as an envelope sorted by ``TRIAL_ID``.

        Args:
            verdict: PASS, HOLD or FAIL (the SYNTH_V1 verdict, which equals the supplied one).
            knockout: ``yield``, ``disease`` or ``both``: those FAIL knockouts triggered.
            missed: A PASS criterion field (e.g. ``MOISTURE_PCT``) the trial does not meet.
            only: With ``missed``, it is the sole unmet PASS criterion; with ``knockout``,
                no other knockout triggered.
            flag: A trial- or operation-scope code from ``FLAG_CODES``; an operation flag
                counts its trial once.

        Returns:
            ``ok`` with ``[{trial_id, verdict, reason}]`` (possibly empty), or ``none``
            naming the valid values when a filter is not recognised.
        """
        error = self._invalid(verdict, knockout, missed, only, flag)
        if error:
            return none(error)
        rows = [{"trial_id": rec.trial_id, "verdict": rec.verdict, "reason": rec.reason}
                for rec in (self._recs[g] for g in self.trial_guids)
                if self._matches(rec, verdict, knockout, missed, only, flag)]
        return ok(rows, _plural(len(rows), "trial"))

    def baseline(self) -> dict[str, Any]:
        """SYNTH_V1 verdicts against the supplied ones: expect 72 checked, 72 matched."""
        recs = [self._recs[g] for g in self.trial_guids]
        mismatches = [{"trial_id": r.trial_id, "verdict": r.verdict,
                       "supplied": r.supplied_verdict} for r in recs if not r.matches_supplied]
        return {"checked": len(recs), "matched": len(recs) - len(mismatches),
                "mismatches": mismatches}
