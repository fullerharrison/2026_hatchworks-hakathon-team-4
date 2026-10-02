"""Candidate evidence views and deterministic recommendations over one immutable revision."""
from __future__ import annotations

import math
import datetime as dt
import time
from types import MappingProxyType
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
GATES = [("YIELD_VS_CHECK_PCT", ">=", 103), ("DISEASE_SCORE_MEAN", "<=", 4),
         ("MOISTURE_PCT_MEAN", "<=", 23), ("GERMINATION_PCT", ">=", 90),
         ("FUMONISIN_PPM", "<=", 4), ("N_TRIALS_USED", ">=", 2)]
KNOCKOUTS = [("YIELD_VS_CHECK_PCT", "<", 95), ("DISEASE_SCORE_MEAN", ">", 6), ("FUMONISIN_PPM", ">", 4)]
WARNINGS = [("MOISTURE_PCT_MEAN", ">", 25), ("GERMINATION_PCT", "<", 85)]
UNITS = {"YIELD_VS_CHECK_PCT": "%", "DISEASE_SCORE_MEAN": "score", "MOISTURE_PCT_MEAN": "%",
         "GERMINATION_PCT": "%", "FUMONISIN_PPM": "ppm", "N_TRIALS_USED": "trials"}


def policy_tests(specs):
    return [dict(field=f, test=op, threshold=v, unit=UNITS[f]) for f, op, v in specs]


def validate_boundary(boundary):
    if boundary is None:
        return None
    if not isinstance(boundary, dict) or set(boundary) != {"field", "kind", "tolerance", "side"}:
        raise ValueError("Boundary requires field, kind, tolerance and side only")
    specs = {"green_gate": GATES, "red_knockout": KNOCKOUTS}
    if not all(isinstance(boundary[k], str) for k in ("field", "kind", "side")) or boundary["kind"] not in specs or boundary["side"] not in {"both", "meets", "fails"}:
        raise ValueError("Unsupported boundary kind or side")
    selected = next((x for x in specs[boundary["kind"]] if x[0] == boundary["field"]), None)
    if selected is None:
        raise ValueError("Unsupported numeric policy boundary")
    tolerance = boundary["tolerance"]
    if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("Boundary tolerance must be a finite nonnegative number")
    if selected[0] == "N_TRIALS_USED" and not float(tolerance).is_integer():
        raise ValueError("Usable trial tolerance must be an integer")
    return dict(boundary, test=selected[1], threshold=selected[2], unit=UNITS[selected[0]])


def assessment(field, value, op, threshold):
    known = value is not None
    passed = known and {">=": lambda: value >= threshold, "<=": lambda: value <= threshold,
                       ">": lambda: value > threshold, "<": lambda: value < threshold,
                       "in": lambda: value in threshold}[op]()
    return dict(field=field, value=value, test=op, threshold=threshold, unit=UNITS.get(field, "category"),
                margin=value - threshold if known and op != "in" else None,
                status="unknown" if not known else "meets" if passed else "fails", passed=bool(passed))


def review_data(rec, boundary=None):
    gates = [assessment(c["field"], c["value"], c["test"], c["threshold"]) for c in rec["criteria"]]
    knockouts = [assessment(f, rec["metrics"][f], op, limit) for f, op, limit in KNOCKOUTS]
    triggers = [c for c in knockouts if c["passed"]]
    no_data = rec["metrics"]["N_TRIALS_USED"] == 0
    decisive = [c for c in gates if c["field"] == "N_TRIALS_USED"] if no_data else triggers or [c for c in gates if not c["passed"]] or gates
    result = dict(green_counts={s: sum(c["status"] == s for c in gates) for s in ("meets", "fails", "unknown")},
                  gates=gates, triggered_knockout_fields=[c["field"] for c in triggers],
                  knockout_precedence_applies=bool(triggers) and not no_data, no_usable_field_data=no_data,
                  decisive_assessments=decisive)
    if boundary:
        c = assessment(boundary["field"], rec["metrics"][boundary["field"]], boundary["test"], boundary["threshold"])
        result["boundary"] = dict(boundary, observed=c["value"], signed_margin=c["margin"],
                                  distance=abs(c["margin"]) if c["margin"] is not None else None,
                                  test_outcome=c["status"])
    return result
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
        started = time.perf_counter()
        self.rec, self.means, self.reconciliation = reconstruct(self.tables)
        effective = self.rec.copy()
        for col in SCORING_FIELDS:
            if f"REBUILT_{col}" in effective:
                effective[col] = effective[f"REBUILT_{col}"]
        effective["rag"] = candidate_rule(effective)
        self.effective = effective
        self.by_guid = {r["MATERIAL_GUID"]: self._recommendation(r) for r in effective.to_dict("records")}
        elapsed = time.perf_counter() - started
        self.build_diagnostics = MappingProxyType(dict(
            elapsed_seconds=elapsed if math.isfinite(elapsed) and elapsed >= 0 else None,
            measured_at=dt.datetime.now(dt.UTC).isoformat(),
            scope="reconstruction_scoring_recommendation_creation", runtime="local_revision_build",
            snapshot_id=snapshot_id, revision_id=revision_id))

    def processing(self):
        """Runtime disclosure only; never part of a recommendation or its identity."""
        families = [
            ("Field observations and trial membership", ("observation", "bridge")),
            ("Operations", ("operations",)), ("Lab", ("lab",)),
            ("Genomics", ("genomics",)), ("Material metadata", ("germplasm",)),
            ("Trait definitions", ("dictionary",)), ("Supplied recommendations", ("recommendations",))]
        sources = []
        for family, keys in families:
            tables = []
            for key in keys:
                frame = self.base_tables[key]
                filename = frame.attrs.get("source_file")
                if filename is None and len(frame):
                    filename = str(frame.iloc[0]["_source_file"])
                tables.append(dict(table=key, source_file=filename, supplied_rows=len(frame)))
            sources.append(dict(family=family, tables=tables))
        diagnostics = getattr(self, "build_diagnostics", None)
        measurement = dict(diagnostics) if diagnostics else None
        if measurement:
            elapsed = measurement.get("elapsed_seconds")
            if (isinstance(elapsed, bool) or not isinstance(elapsed, (int, float)) or
                    not math.isfinite(elapsed) or elapsed < 0 or
                    (measurement.get("snapshot_id"), measurement.get("revision_id")) !=
                    (self.snapshot_id, self.revision_id)):
                measurement = None
        # Superseding an overlay changes a field; it does not add another source row.
        corrections = {(x["table"], x["row_id"], x["field"]) for x in self.overlays if x["kind"] == "correction"}
        additions = {(x["table"], x["row_id"], x["field"], x["id"] if x["field"] == "NOTE" else None)
                     for x in self.overlays if x["kind"] == "metadata"}
        bridge = self.base_tables["bridge"]
        return dict(snapshot_id=self.snapshot_id, revision_id=self.revision_id, measurement=measurement,
                    sources=sources, candidate_count=len(self.by_guid),
                    check_variety_count=int(bridge.loc[bridge.ENTRY_ROLE_LID == "CHECK", "MATERIAL_GUID"].nunique()),
                    active_corrections=len(corrections), contextual_additions=len(additions))

    def _recommendation(self, row):
        metrics = {k: row.get(k) for k in SCORING_FIELDS}
        specs = GATES
        criteria = []
        for field, op, threshold in specs:
            value = metrics[field]
            passed = pd.notna(value) and (value >= threshold if op == ">=" else value <= threshold)
            criteria.append(dict(field=field, value=value, test=op, threshold=threshold, passed=bool(passed)))
        marker = metrics["MARKER_DISEASE_RESISTANCE"]
        criteria.append(dict(field="MARKER_DISEASE_RESISTANCE", value=marker,
                             test="in", threshold=["RESISTANT", "INTERMEDIATE"],
                             passed=bool(pd.notna(marker) and marker in ("RESISTANT", "INTERMEDIATE"))))
        knockouts = [field for field, op, limit in KNOCKOUTS
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
        rec["assessments"] = [dict(c, unit=UNITS.get(c["field"], "category"),
            margin=(c["value"] - c["threshold"] if c["value"] is not None and c["test"] != "in" else None),
            status="Unknown" if c["value"] is None else "Meets gate" if c["passed"] else "Outside GREEN target")
            for c in rec["criteria"]]
        rec["policy"] = self.rule()
        rec["review"] = review_data(rec)
        rec["criterion_evidence"] = self.criterion_evidence(rec, entries, comparison_entries, fields)
        return {"status": "ok", "result": rec}

    def criterion_evidence(self, rec, entries, comparison_entries, fields):
        """Capture effective and original sources from this immutable revision."""
        result = {}
        trait_map = {"YIELD_VS_CHECK_PCT": "YIELD_T_HA", "DISEASE_SCORE_MEAN": "DISEASE_SCORE",
                     "MOISTURE_PCT_MEAN": "MOISTURE_PCT"}
        for metric in SCORING_FIELDS:
            trait = trait_map.get(metric, metric)
            dictionary = self.tables["dictionary"]
            definitions = dictionary[dictionary.TRAIT_CODE == trait]
            if metric.startswith("N_TRIALS"):
                masks = {"bridge": self.tables["bridge"].TRIAL_ENTRY_GUID.isin(entries.TRIAL_ENTRY_GUID)}
                explanation = "Count distinct observed candidate trials in reconstructed trial means; usable trials exclude missed irrigation. Membership alone does not add an observed trial."
            elif metric in trait_map:
                members = comparison_entries if metric == "YIELD_VS_CHECK_PCT" else entries
                masks = {"bridge": self.tables["bridge"].TRIAL_ENTRY_GUID.isin(members.TRIAL_ENTRY_GUID),
                         "observation": self.tables["observation"].TRIAL_ENTRY_RELATIONSHIP_GUID.isin(members.TRIAL_ENTRY_GUID) & (self.tables["observation"].TRAIT_CODE == trait)}
                explanation = ("Mean replications within each trial; equally weight usable trial means. Yield versus checks is 100 times the ratio of overall candidate mean yield to overall CHECK-role mean yield, not the mean of trial ratios."
                               if metric == "YIELD_VS_CHECK_PCT" else "Mean replications within each trial, then equally weight usable trial means. Excluded trials remain visible but do not contribute.")
            elif metric in {"GERMINATION_PCT", "FUMONISIN_PPM", "COLD_TEST_PCT"}:
                masks = {"lab": (self.tables["lab"].MATERIAL_GUID == rec["material_guid"]) & self.tables["lab"].TRAIT_GUID.isin(definitions.TRAIT_GUID)}
                explanation = "Selected material's laboratory value linked through the trait dictionary. No trial relationship is supplied."
            else:
                masks = {"genomics": self.tables["genomics"].MATERIAL_GUID == rec["material_guid"]}
                explanation = f"Selected material's genomic record, field {metric}." + (" Context only under this policy." if metric == "GENOMIC_BREEDING_VALUE" else " Category participates in the GREEN gate.")
            field_metric = metric in trait_map or metric.startswith("N_TRIALS")
            if field_metric:
                masks["operations"] = self.tables["operations"].ATTACHED_TO_FIELD_ENTITY_ID.isin(fields) & (self.tables["operations"].OPERATION_TYPE_LID == "IRRIGATION")
            sources, corrections = {}, []
            for table, mask in masks.items():
                originals = {str(x[KEYS[table]]): x for x in self.base_tables[table].to_dict("records")}
                rows = source_records(self.tables[table][mask], table)
                for row in rows:
                    trial = row.get("FIELD_ID") or row.get("TRIAL_GUID")
                    if table == "operations":
                        memberships = entries[entries.FIELD_ENTITY_ID == row["ATTACHED_TO_FIELD_ENTITY_ID"]]
                        trial = memberships.TRIAL_GUID.iloc[0] if len(memberships) else None
                    if trial is not None:
                        trial_means = self.means[self.means.TRIAL_GUID == trial]
                        row["EXCLUDED_IRRIGATION_MISSED"] = bool(trial_means.EXCLUDED_IRRIGATION_MISSED.any())
                    changes = [x for x in self.overlays if x["kind"] == "correction" and x["table"] == table and x["row_id"] == row["row_id"]
                               and (table != "genomics" or x["field"] == metric)]
                    row["original_values"] = {x["field"]: to_json_safe(originals[row["row_id"]][x["field"]]) for x in changes}
                    row["latest_corrections"] = {x["field"]: x for x in changes}
                    row["revision_id"] = self.revision_id
                    corrections.extend(changes)
                sources[table] = rows
            comparisons = self.means[self.means.TRIAL_GUID.isin(entries.TRIAL_GUID) &
                                     ((self.means.MATERIAL_GUID == rec["material_guid"]) |
                                      ((self.means.ENTRY_ROLE_LID == "CHECK") & (metric == "YIELD_VS_CHECK_PCT")))] if field_metric else pd.DataFrame()
            result[metric] = to_json_safe(dict(material_guid=rec["material_guid"], material_id=rec["material_id"],
                snapshot_id=self.snapshot_id, revision_id=self.revision_id, field=metric, calculation=explanation,
                source_rows=sources, dictionary=source_records(definitions, "dictionary"),
                trial_comparisons=comparisons.to_dict("records"), active_corrections=corrections))
        return result

    def query(self, filters: dict | None = None, latest: dict | None = None):
        filters, latest = filters or {}, latest or {}
        if not isinstance(filters, dict):
            raise ValueError("Filters must be an object")
        allowed = {"search", "rag", "decision", "review_state", "marker", "excluded", "ranges", "include_missing", "sort", "descending", "boundary"}
        if set(filters) - allowed:
            raise ValueError("Unknown filters: " + ", ".join(set(filters) - allowed))
        ranges = filters.get("ranges") or {}
        boundary = validate_boundary(filters.get("boundary"))
        if filters.get("sort") == "boundary_distance" and boundary is None:
            raise ValueError("Distance sorting requires an active boundary")
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
        review = filters.get("review_state", "all")
        if review not in {"all", "reviewed", "undecided", "latest_override"}:
            raise ValueError("Unknown review state")
        if filters.get("marker") and filters["marker"] not in {"RESISTANT", "INTERMEDIATE", "SUSCEPTIBLE"}:
            raise ValueError("Unknown disease marker")
        rows = []
        for original in self.by_guid.values():
            r = dict(original, latest_decision=latest.get(original["material_guid"]))
            r["review"] = review_data(r, boundary)
            if boundary:
                context = r["review"]["boundary"]
                if context["distance"] is None or context["distance"] > boundary["tolerance"]:
                    continue
                if boundary["side"] != "both" and boundary["side"] != context["test_outcome"]:
                    continue
            saved = r["latest_decision"]
            if (review == "reviewed" and saved is None or
                review == "undecided" and saved is not None or
                review == "latest_override" and not (saved and saved["overrides"])):
                continue
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
        if sort not in ["material_id", "rag", "boundary_distance", *METRICS]:
            raise ValueError("Unsupported sort column")
        def key(r):
            v = r.get(sort) if sort in r else r["metrics"].get(sort)
            return (v is None, v if v is not None else 0, r["material_id"])
        if sort == "boundary_distance":
            rows.sort(key=lambda r: ((-1 if filters.get("descending") else 1) * r["review"]["boundary"]["distance"], r["material_id"]))
        else:
            rows.sort(key=key, reverse=bool(filters.get("descending")))
        return rows

    def rule(self):
        return dict(rule_version=RULE_VERSION, provisional=True, precision="Unrounded calculations; presentation only is rounded",
                    outcomes=[{"rag": rag} for rag in ACTIONS],
                    criteria=thresholds().to_dict("records"), no_field_data_precedence="AMBER",
                    gates=policy_tests(GATES) + [dict(field="MARKER_DISEASE_RESISTANCE", test="in",
                        threshold=["RESISTANT", "INTERMEDIATE"], unit="category")],
                    knockouts=policy_tests(KNOCKOUTS), warnings=policy_tests(WARNINGS),
                    context_only=["COLD_TEST_PCT", "GENOMIC_BREEDING_VALUE"],
                    missing_data="Missing required values do not pass GREEN gates; zero usable trials takes AMBER precedence.")
