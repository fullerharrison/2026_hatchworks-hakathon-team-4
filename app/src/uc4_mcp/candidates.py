"""Candidate evidence views and deterministic recommendations over one immutable revision."""
from __future__ import annotations

import math
from typing import Any

import pandas as pd

from uc4_mcp.candidate_core import KEYS, audit_links, consistency, reconstruct, candidate_rule, thresholds
from uc4_mcp.models import to_json_safe

RULE_VERSION = "CANDIDATE_PROVISIONAL_V1"
METRICS = ["YIELD_VS_CHECK_PCT", "DISEASE_SCORE_MEAN", "MOISTURE_PCT_MEAN",
           "GERMINATION_PCT", "FUMONISIN_PPM", "GENOMIC_BREEDING_VALUE",
           "COLD_TEST_PCT", "N_TRIALS", "N_TRIALS_USED"]
SCORING_FIELDS = METRICS + ["MARKER_DISEASE_RESISTANCE"]
ACTIONS = {"GREEN": "ADVANCE", "AMBER": "HOLD", "RED": "DISCARD"}
LABELS = {"YIELD_VS_CHECK_PCT": "Yield versus checks", "DISEASE_SCORE_MEAN": "Disease score",
          "MOISTURE_PCT_MEAN": "Moisture", "GERMINATION_PCT": "Germination", "FUMONISIN_PPM": "Fumonisin",
          "N_TRIALS_USED": "Usable trials", "MARKER_DISEASE_RESISTANCE": "Disease resistance marker"}


def validate_tables(tables):
    links = audit_links(tables)
    if links.missing_rows.sum() or links.unresolved.astype(bool).any():
        raise ValueError("Unresolved source relationships; archive cannot be activated")
    checks = consistency(tables)
    if checks.violations.sum():
        raise ValueError("Source consistency violations: " + "; ".join(checks.loc[checks.violations > 0, "check"]))
    for key in ("observation", "lab"):
        values = pd.to_numeric(tables[key].NUMBER_VALUE, errors="coerce")
        if any(not math.isfinite(v) for v in values):
            raise ValueError(f"{key}: measurements must be finite numbers")
    dictionary = tables["dictionary"].set_index("TRAIT_CODE")
    for trait, unit in {"YIELD_T_HA": "t/ha", "MOISTURE_PCT": "%", "GERMINATION_PCT": "%", "FUMONISIN_PPM": "ppm"}.items():
        if trait not in dictionary.index or dictionary.loc[trait, "UNIT"] != unit:
            raise ValueError(f"Missing or incompatible unit for {trait}")


def source_records(frame: pd.DataFrame, key: str) -> list[dict]:
    records = []
    for row in frame.to_dict("records"):
        row.update(source_file=row["_source_file"], row_id=str(row[KEYS[key]]), line_no=row["_line_no"])
        records.append(row)
    return to_json_safe(records)


class CandidateStore:
    def __init__(self, tables, snapshot_id: str, revision_id: str, overlays=()):
        self.base_tables = tables
        self.tables = {k: v.copy(deep=True) for k, v in tables.items()}
        self.snapshot_id, self.revision_id = snapshot_id, revision_id
        self.overlays = list(overlays)
        for item in overlays:
            if item["kind"] == "correction":
                frame = self.tables[item["table"]]
                frame.loc[frame[KEYS[item["table"]]].astype(str) == item["row_id"], item["field"]] = item["value"]
        checks = consistency(self.tables)
        self.source_warnings = to_json_safe(checks[checks.violations > 0].to_dict("records"))
        self.rec, self.means, self.reconciliation = reconstruct(self.tables)
        effective = self.rec.copy()
        for col in SCORING_FIELDS:
            if f"REBUILT_{col}" in effective:
                effective[col] = effective[f"REBUILT_{col}"]
        effective["rag"] = candidate_rule(effective)
        self.effective = effective
        self.by_guid = {r["MATERIAL_GUID"]: self._recommendation(r) for r in effective.to_dict("records")}

    def _recommendation(self, row):
        metrics = {k: row.get(k) for k in SCORING_FIELDS}
        specs = [("YIELD_VS_CHECK_PCT", ">=", 103), ("DISEASE_SCORE_MEAN", "<=", 4),
                 ("MOISTURE_PCT_MEAN", "<=", 23), ("GERMINATION_PCT", ">=", 90),
                 ("FUMONISIN_PPM", "<=", 4), ("N_TRIALS_USED", ">=", 2)]
        criteria = []
        for field, op, threshold in specs:
            value = metrics[field]
            passed = pd.notna(value) and (value >= threshold if op == ">=" else value <= threshold)
            criteria.append(dict(field=field, value=value, test=op, threshold=threshold, passed=bool(passed)))
        marker = metrics["MARKER_DISEASE_RESISTANCE"]
        criteria.append(dict(field="MARKER_DISEASE_RESISTANCE", value=marker,
                             test="in", threshold=["RESISTANT", "INTERMEDIATE"],
                             passed=bool(pd.notna(marker) and marker in ("RESISTANT", "INTERMEDIATE"))))
        knockouts = [field for field, op, limit in [("YIELD_VS_CHECK_PCT", "<", 95),
                     ("DISEASE_SCORE_MEAN", ">", 6), ("FUMONISIN_PPM", ">", 4)]
                     if pd.notna(metrics[field]) and (metrics[field] < limit if op == "<" else metrics[field] > limit)]
        warnings = []
        if metrics["N_TRIALS_USED"] == 0:
            reason = "No usable field data; AMBER takes precedence."
        elif row["rag"] == "RED":
            reason = "Provisional knockout: " + ", ".join(LABELS[k] for k in knockouts)
        elif row["rag"] == "GREEN":
            reason = "All provisional GREEN criteria met."
        else:
            reason = "GREEN criteria not met: " + ", ".join(LABELS[c["field"]] for c in criteria if not c["passed"])
        for field, limit, above in [("MOISTURE_PCT_MEAN", 25, True), ("GERMINATION_PCT", 85, False)]:
            value = metrics[field]
            if pd.notna(value) and (value > limit if above else value < limit):
                warnings.append(f"{LABELS[field]} {value} {'>' if above else '<'} {limit}; warning only")
        if any(pd.isna(metrics[k]) for k in SCORING_FIELDS if k != "COLD_TEST_PCT"):
            warnings.append("Missing evidence: inspect criteria and trial comparisons")
        return to_json_safe(dict(material_guid=row["MATERIAL_GUID"], material_id=row["MATERIAL_ID"],
            snapshot_id=self.snapshot_id, revision_id=self.revision_id, rule_version=RULE_VERSION,
            recommendation_id=f"{self.revision_id}:{row['MATERIAL_GUID']}", rag=row["rag"],
            verdict=row["rag"], colour=row["rag"].lower(), metrics=metrics, criteria=criteria,
            knockouts=knockouts, reason=reason, warnings=warnings, provisional=True,
            source_warnings=self.source_warnings,
            supplied_rag=row["SYSTEM_RAG"], supplied_reason=row["SYSTEM_REASON"],
            matches_supplied=row["rag"] == row["SYSTEM_RAG"],
            excluded_trials=int(row["REBUILT_EXCLUDED_TRIALS"]),
            evidence_row_ids=[f"{row['_source_file']}#{row['MATERIAL_GUID']}"]))

    def resolve(self, query):
        query = query.strip().lower()
        records = list(self.by_guid.values())
        exact = [r for r in records if query in (r["material_guid"].lower(), r["material_id"].lower())]
        found = exact or [r for r in records if query and (query in r["material_id"].lower() or query in r["material_guid"].lower())]
        if not found:
            return {"status": "none", "message": f"No candidate matches {query}"}
        if len(found) != 1:
            return {"status": "many", "message": "Choose a candidate", "candidates": [dict(id=r["material_id"], guid=r["material_guid"], label=r["material_id"]) for r in found]}
        return {"status": "ok", "result": found[0]}

    def detail(self, query):
        result = self.resolve(query)
        if result["status"] != "ok":
            return result
        rec = result["result"].copy()
        guid = rec["material_guid"]
        b = self.tables["bridge"]
        entries = b[b.MATERIAL_GUID == guid]
        trials = entries.TRIAL_GUID.unique()
        fields = b[b.TRIAL_GUID.isin(trials)].FIELD_ENTITY_ID.unique()
        # Include checks and their observations: every comparison is inspectable.
        comparison_entries = b[b.TRIAL_GUID.isin(trials) & ((b.MATERIAL_GUID == guid) | (b.ENTRY_ROLE_LID == "CHECK"))]
        masks = {
            "germplasm": self.tables["germplasm"].MATERIAL_GUID == guid,
            "genomics": self.tables["genomics"].MATERIAL_GUID == guid,
            "lab": self.tables["lab"].MATERIAL_GUID == guid,
            "bridge": b.TRIAL_ENTRY_GUID.isin(comparison_entries.TRIAL_ENTRY_GUID),
            "observation": self.tables["observation"].TRIAL_ENTRY_RELATIONSHIP_GUID.isin(comparison_entries.TRIAL_ENTRY_GUID),
            "operations": self.tables["operations"].ATTACHED_TO_FIELD_ENTITY_ID.isin(fields),
        }
        rec["evidence"] = {k: source_records(self.base_tables[k][mask], k) for k, mask in masks.items()}
        rec["trial_comparisons"] = to_json_safe(self.means[self.means.MATERIAL_GUID == guid].to_dict("records"))
        rec["dictionary"] = source_records(self.tables["dictionary"], "dictionary")
        rec["active_corrections"] = self.overlays
        rec["source_warnings"] = self.source_warnings
        rec["reviewed_metadata"] = {item["field"]: item for item in self.overlays
                                    if item["kind"] == "metadata" and item["material_guid"] == guid and item["field"] != "NOTE"}
        rec["metadata_note"] = "Synthetic maize-like demo. Absent pedigree, stage and trial location are unknown. Lab values have no trial key."
        return {"status": "ok", "result": rec}

    def query(self, filters: dict | None = None, latest: dict | None = None):
        filters, latest = filters or {}, latest or {}
        if not isinstance(filters, dict):
            raise ValueError("Filters must be an object")
        allowed = {"search", "rag", "decision", "marker", "excluded", "ranges", "include_missing", "sort", "descending"}
        if set(filters) - allowed:
            raise ValueError("Unknown filters: " + ", ".join(set(filters) - allowed))
        ranges = filters.get("ranges") or {}
        if not isinstance(ranges, dict):
            raise ValueError("Ranges must be an object keyed by metric")
        if set(ranges) - set(METRICS):
            raise ValueError("Unknown metric")
        for bounds in ranges.values():
            if not isinstance(bounds, dict) or set(bounds) - {"min", "max"}:
                raise ValueError("Ranges accept min and max")
            if any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in bounds.values()):
                raise ValueError("Range limits must be finite numbers")
            if "min" in bounds and "max" in bounds and bounds["min"] > bounds["max"]:
                raise ValueError("Minimum cannot exceed maximum")
        if filters.get("rag") and filters["rag"] not in ACTIONS:
            raise ValueError("Unknown RAG")
        if filters.get("decision") and filters["decision"] not in [*ACTIONS.values(), "UNDECIDED"]:
            raise ValueError("Unknown decision")
        if filters.get("marker") and filters["marker"] not in {"RESISTANT", "INTERMEDIATE", "SUSCEPTIBLE"}:
            raise ValueError("Unknown disease marker")
        rows = []
        for original in self.by_guid.values():
            r = dict(original, latest_decision=latest.get(original["material_guid"]))
            if filters.get("search") and filters["search"].lower() not in (r["material_id"] + r["material_guid"]).lower():
                continue
            if filters.get("rag") and r["rag"] != filters["rag"]:
                continue
            decision = r["latest_decision"]["action"] if r["latest_decision"] else "UNDECIDED"
            if filters.get("decision") and decision != filters["decision"]:
                continue
            if filters.get("marker") and r["metrics"]["MARKER_DISEASE_RESISTANCE"] != filters["marker"]:
                continue
            if filters.get("excluded") is not None and bool(r["excluded_trials"]) != filters["excluded"]:
                continue
            keep = True
            for metric, bounds in ranges.items():
                v = r["metrics"].get(metric)
                if v is None:
                    keep &= bool(filters.get("include_missing"))
                else:
                    keep &= ("min" not in bounds or v >= bounds["min"]) and ("max" not in bounds or v <= bounds["max"])
            if keep:
                rows.append(r)
        sort = filters.get("sort", "material_id")
        if sort not in ["material_id", "rag", *METRICS]:
            raise ValueError("Unsupported sort column")
        def key(r):
            v = r.get(sort) if sort in r else r["metrics"].get(sort)
            return (v is None, v if v is not None else 0, r["material_id"])
        rows.sort(key=key, reverse=bool(filters.get("descending")))
        return rows

    def rule(self):
        return dict(rule_version=RULE_VERSION, provisional=True, precision="Unrounded calculations; presentation only is rounded",
                    outcomes=[{"rag": rag} for rag in ACTIONS],
                    criteria=thresholds().to_dict("records"), no_field_data_precedence="AMBER")
