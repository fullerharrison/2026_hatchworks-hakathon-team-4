"""Transactional candidate decisions and reviewed evidence revisions."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path

from uc4_mcp.candidate_core import KEYS, ZIP_PATH, load_current
from uc4_mcp.candidates import ACTIONS, CandidateStore, validate_tables
from uc4_mcp.decisions import log_path
from uc4_mcp.models import to_json_safe

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "candidate_history.sqlite3"
ALLOWED_CORRECTIONS = {
    "observation": {"NUMBER_VALUE"}, "lab": {"NUMBER_VALUE"},
    "genomics": {"GENOMIC_BREEDING_VALUE", "MARKER_DISEASE_RESISTANCE"},
    "operations": {"STATUS_LID", "ACTUAL_DATE", "DELAY_DAYS"},
}
ALLOWED_METADATA = {"PEDIGREE", "STAGE_CODE_LID", "RESEARCH_STATION_GUID", "SITE", "NOTE"}
CHOICES = {"ADVANCE", "HOLD", "DISCARD"}


def now():
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def dump(obj):
    return json.dumps(obj, ensure_ascii=False, allow_nan=False, sort_keys=True)


class Conflict(ValueError):
    pass


class CandidateHistory:
    def __init__(self, path: Path | None = None, archive: Path | None = None,
                 legacy_log: Path | None = None):
        self.path = Path(path or os.environ.get("UC4_CANDIDATE_DB", DEFAULT_DB))
        self.archive = Path(archive or os.environ.get("UC4_ZIP", ZIP_PATH))
        self.legacy_log = Path(legacy_log or log_path())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        source = self.archive.read_bytes()
        self.snapshot_id = hashlib.sha256(source).hexdigest()
        self.snapshot_path = self.path.parent / "snapshots" / f"{self.snapshot_id}.zip"
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.snapshot_path.exists():
            temporary = self.snapshot_path.with_suffix(f".{uuid.uuid4().hex}.tmp")
            temporary.write_bytes(source)
            temporary.replace(self.snapshot_path)
        elif hashlib.sha256(self.snapshot_path.read_bytes()).hexdigest() != self.snapshot_id:
            raise ValueError("Stored source snapshot hash differs from its name")
        self.tables = load_current(self.snapshot_path, strict_counts=False)
        validate_tables(self.tables)
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS revisions (
                    id TEXT PRIMARY KEY, parent TEXT, snapshot_id TEXT NOT NULL,
                    overlays TEXT NOT NULL, created_at TEXT NOT NULL,
                    actor TEXT NOT NULL, reason TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS decisions (
                    id TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE,
                    material_guid TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS decisions_material ON decisions(material_guid);
                CREATE TABLE IF NOT EXISTS enrichment (
                    id TEXT PRIMARY KEY, material_guid TEXT NOT NULL, status TEXT NOT NULL,
                    payload TEXT NOT NULL, review TEXT, activated_revision TEXT);
                CREATE TABLE IF NOT EXISTS legacy (
                    id TEXT PRIMARY KEY, source_line INTEGER NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS enrichment_events (
                    id TEXT PRIMARY KEY, enrichment_id TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS recommendations (
                    revision_id TEXT NOT NULL, material_guid TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY (revision_id, material_guid));
            """)
            base = "baseline:" + self.snapshot_id[:16]
            db.execute("INSERT OR IGNORE INTO revisions VALUES (?,?,?,?,?,?,?)",
                       (base, None, self.snapshot_id, "[]", now(), "system", "Original source archive"))
            db.execute("INSERT OR IGNORE INTO state VALUES ('active_revision', ?)", (base,))
            active_snapshot = db.execute("SELECT snapshot_id FROM revisions WHERE id=?", (self._active(db),)).fetchone()[0]
            if active_snapshot != self.snapshot_id:
                db.execute("UPDATE state SET value=? WHERE key='active_revision'", (base,))
        self._stores = {}
        self._cache_lock = threading.Lock()
        self.import_legacy()
        self.store()

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=30000")
        try:
            with db:
                yield db
        finally:
            db.close()

    def _active(self, db):
        return db.execute("SELECT value FROM state WHERE key='active_revision'").fetchone()[0]

    def active_revision(self):
        with self._db() as db:
            return self._active(db)

    def store(self, revision: str | None = None):
        with self._db() as db:
            revision = revision or self._active(db)
            row = db.execute("SELECT * FROM revisions WHERE id=?", (revision,)).fetchone()
        if row is None:
            raise ValueError("Unknown evidence revision")
        with self._cache_lock:
            if revision in self._stores:
                return self._stores[revision]
        tables = self.tables
        if row["snapshot_id"] != self.snapshot_id:
            archive = self.snapshot_path.parent / f"{row['snapshot_id']}.zip"
            if hashlib.sha256(archive.read_bytes()).hexdigest() != row["snapshot_id"]:
                raise ValueError("Historical snapshot integrity check failed")
            tables = load_current(archive, strict_counts=False)
        result = CandidateStore(tables, row["snapshot_id"], revision, json.loads(row["overlays"]))
        with self._db() as db:
            saved = db.execute("SELECT material_guid,payload FROM recommendations WHERE revision_id=?", (revision,)).fetchall()
            if saved:
                result.by_guid = {r["material_guid"]: json.loads(r["payload"]) for r in saved}
            else:
                self._save_recommendations(db, result)
        with self._cache_lock:
            self._stores[revision] = result
            while len(self._stores) > 8:
                self._stores.pop(next(iter(self._stores)), None)
        return result

    def _save_recommendations(self, db, store):
        db.executemany("INSERT OR IGNORE INTO recommendations VALUES (?,?,?)",
                       [(store.revision_id, guid, dump(rec)) for guid, rec in store.by_guid.items()])

    def _enrichment_event(self, db, item_id, action, actor, reason):
        event = dict(id=uuid.uuid4().hex, action=action, actor=actor.strip(),
                     reason=reason.strip(), timestamp=now())
        db.execute("INSERT INTO enrichment_events VALUES (?,?,?)", (event["id"], item_id, dump(event)))
        return event

    def import_legacy(self):
        if not self.legacy_log.exists():
            return 0
        count = 0
        with self._db() as db:
            for number, raw in enumerate(self.legacy_log.read_text(encoding="utf-8").split("\n"), 1):
                if not raw:
                    continue
                payload = json.loads(raw)
                key = hashlib.sha256((str(self.legacy_log.resolve()) + "\n" + str(number) + "\n" + raw).encode()).hexdigest()
                count += db.execute("INSERT OR IGNORE INTO legacy VALUES (?,?,?)", (key, number, dump(payload))).rowcount
        return count

    def legacy(self):
        with self._db() as db:
            rows = db.execute("SELECT payload FROM legacy ORDER BY source_line").fetchall()
        return [json.loads(r[0]) for r in rows]

    def decisions(self, guid: str | None = None):
        with self._db() as db:
            rows = db.execute("SELECT payload FROM decisions WHERE (? IS NULL OR material_guid=?) ORDER BY rowid",
                              (guid, guid)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def latest(self):
        return {r["material_guid"]: r for r in self.decisions()}

    def decide(self, *, query, action, actor, reason, context, recommendation_id,
               previous_decision_id, request_id):
        if action not in CHOICES or not 1 <= len(actor.strip()) <= 80 or not 5 <= len(reason.strip()) <= 1000:
            raise ValueError("A valid action, actor and reason (5-1000 characters) are required")
        if not isinstance(context, dict) or any(not isinstance(context.get(k), str) or not context[k].strip()
                                                for k in ("location", "source_channel")):
            raise ValueError("Context needs a location (or 'unknown') and source channel")
        if not request_id or len(request_id) > 120:
            raise ValueError("A request id is required")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT payload FROM decisions WHERE request_id=?", (request_id,)).fetchone()
            if existing:
                event = json.loads(existing[0])
                if query.strip().lower() not in {event.get("request_query", "").lower(), event["material_id"].lower(), event["material_guid"].lower()}:
                    raise Conflict("Request id was already used for a different candidate")
                if (event["action"], event["actor"], event["reason"], event["context"],
                    event["recommendation"]["recommendation_id"], event["previous_decision_id"]) != (
                    action, actor.strip(), reason.strip(), context, recommendation_id, previous_decision_id):
                    raise Conflict("Request id was already used for a different decision")
                return event
            rec_result = self.store(self._active(db)).resolve(query)
            if rec_result["status"] != "ok":
                raise ValueError(rec_result["message"])
            rec = rec_result["result"]
            latest = db.execute("SELECT id FROM decisions WHERE material_guid=? ORDER BY rowid DESC LIMIT 1",
                                (rec["material_guid"],)).fetchone()
            prior = latest[0] if latest else None
            if rec["recommendation_id"] != recommendation_id or prior != previous_decision_id:
                raise Conflict("The recommendation or latest decision changed; refresh before recording")
            event = dict(id=uuid.uuid4().hex, request_id=request_id, request_query=query.strip(), material_guid=rec["material_guid"],
                         material_id=rec["material_id"], action=action, previous_action=None,
                         previous_decision_id=prior, actor=actor.strip(), reason=reason.strip(),
                         context=context, timestamp=now(), overrides=action != ACTIONS[rec["rag"]],
                         recommendation=rec)
            if prior:
                old = db.execute("SELECT payload FROM decisions WHERE id=?", (prior,)).fetchone()
                event["previous_action"] = json.loads(old[0])["action"]
            db.execute("INSERT INTO decisions VALUES (?,?,?,?)",
                       (event["id"], request_id, rec["material_guid"], dump(event)))
            return event

    def draft(self, *, query, kind, table=None, row_id=None, field=None, value=None,
              actor, reason, observed_at=None, source=None, unit=None, supersedes=None):
        result = self.store().resolve(query)
        if result["status"] != "ok":
            raise ValueError(result["message"])
        guid = result["result"]["material_guid"]
        for label, text in (("Author", actor), ("Evidence source", source), ("When observed", observed_at)):
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"{label} is required")
        if len(reason.strip()) < 5:
            raise ValueError("Why change it: enter at least 5 characters")
        try:
            dt.datetime.fromisoformat(observed_at)
        except (ValueError, TypeError) as exc:
            raise ValueError("Observation time must be an ISO date or date/time") from exc
        if kind == "correction":
            if field not in ALLOWED_CORRECTIONS.get(table, ()):
                raise ValueError("Unsupported source correction")
            frame = self.tables[table]
            match = frame[frame[KEYS[table]].astype(str) == str(row_id)]
            if len(match) != 1:
                raise ValueError("Source row not found")
            if table == "observation":
                bridge = self.tables["bridge"].set_index("TRIAL_ENTRY_GUID")
                entry = match.iloc[0]["TRIAL_ENTRY_RELATIONSHIP_GUID"]
                linked = bridge.loc[entry]
                candidate_trials = set(self.tables["bridge"].loc[
                    self.tables["bridge"].MATERIAL_GUID == guid, "TRIAL_GUID"])
                if linked["MATERIAL_GUID"] != guid and not (
                    linked["ENTRY_ROLE_LID"] == "CHECK" and linked["TRIAL_GUID"] in candidate_trials
                ):
                    raise ValueError("Observation belongs to another candidate or check")
            elif table != "operations" and match.iloc[0]["MATERIAL_GUID"] != guid:
                raise ValueError("Source row belongs to another candidate")
            if table == "operations":
                bridge = self.tables["bridge"]
                trials = set(bridge.loc[bridge.MATERIAL_GUID == guid, "FIELD_ENTITY_ID"])
                if match.iloc[0]["ATTACHED_TO_FIELD_ENTITY_ID"] not in trials:
                    raise ValueError("Operation is outside candidate trials")
            if field == "NUMBER_VALUE" or field in {"GENOMIC_BREEDING_VALUE", "DELAY_DAYS"}:
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError("Measurement must be a finite number")
                if table in ("lab", "observation"):
                    trait = self.tables["dictionary"].set_index("TRAIT_GUID").loc[match.iloc[0]["TRAIT_GUID"]]
                    if unit != trait.UNIT:
                        raise ValueError(f"Expected unit {trait.UNIT}")
                elif unit not in (None, "", "index" if field == "GENOMIC_BREEDING_VALUE" else "days"):
                    raise ValueError("Expected unit " + ("index" if field == "GENOMIC_BREEDING_VALUE" else "days"))
            elif not (field == "ACTUAL_DATE" and value is None) and (not isinstance(value, str) or not value.strip()):
                raise ValueError("Correction requires a value")
            if field == "MARKER_DISEASE_RESISTANCE" and value not in {"RESISTANT", "INTERMEDIATE", "SUSCEPTIBLE"}:
                raise ValueError("Unknown disease marker")
            if field == "STATUS_LID" and value not in {"COMPLETED", "DELAYED", "MISSED"}:
                raise ValueError("Unknown operation status")
            if field == "ACTUAL_DATE" and value is not None:
                try:
                    dt.datetime.fromisoformat(value)
                except ValueError as exc:
                    raise ValueError("Actual date must be an ISO date/time") from exc
        elif kind == "metadata":
            if field not in ALLOWED_METADATA or not isinstance(value, str) or not value.strip():
                raise ValueError("Unsupported metadata field or value")
            table, row_id = "germplasm", guid
        else:
            raise ValueError("Choose correction or metadata")
        current = [x for x in self.store().overlays
                   if (x["table"], x["row_id"], x["field"]) == (table, str(row_id), field)]
        if supersedes and (not current or supersedes != current[-1]["id"] or field == "NOTE"):
            raise ValueError("Replace an earlier addition: choose the current addition for this field and source row")
        if current and field != "NOTE" and supersedes != current[-1]["id"]:
            raise ValueError("Replace an earlier addition: explicitly select the current addition")
        event = dict(id=uuid.uuid4().hex, material_guid=guid, kind=kind, table=table,
                     row_id=str(row_id), field=field, value=value, unit=unit, actor=actor.strip(),
                     reason=reason.strip(), observed_at=observed_at, source=source,
                     supersedes=supersedes, created_at=now())
        with self._db() as db:
            db.execute("INSERT INTO enrichment VALUES (?,?,?,?,?,NULL)",
                       (event["id"], guid, "draft", dump(event), None))
            self._enrichment_event(db, event["id"], "draft", actor, reason)
        return dict(**event, status="draft")

    def enrichment(self, guid: str | None = None):
        with self._db() as db:
            rows = db.execute("SELECT * FROM enrichment WHERE (? IS NULL OR material_guid=?) ORDER BY rowid",
                              (guid, guid)).fetchall()
            events = db.execute("SELECT enrichment_id,payload FROM enrichment_events ORDER BY rowid").fetchall()
        return [dict(**json.loads(r["payload"]), status=r["status"],
                     review=json.loads(r["review"]) if r["review"] else None,
                     events=[json.loads(e["payload"]) for e in events if e["enrichment_id"] == r["id"]],
                     activated_revision=r["activated_revision"]) for r in rows]

    def review(self, item_id: str, action: str, actor: str, reason: str):
        if action not in {"submit", "approve", "reject"} or not actor.strip() or len(reason.strip()) < 5:
            raise ValueError("Review action, actor and reason are required")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM enrichment WHERE id=?", (item_id,)).fetchone()
            if row is None:
                raise ValueError("Enrichment not found")
            new = {"draft": {"submit": "submitted"}, "submitted": {"approve": "approved", "reject": "rejected"}}.get(row["status"], {}).get(action)
            if not new:
                raise Conflict("Enrichment is no longer in the expected review state")
            review = self._enrichment_event(db, item_id, action, actor, reason)
            db.execute("UPDATE enrichment SET status=?,review=? WHERE id=?", (new, dump(review), item_id))
        return next(x for x in self.enrichment(row["material_guid"]) if x["id"] == item_id)

    def preview(self, item_id: str):
        with self._db() as db:
            row = db.execute("SELECT * FROM enrichment WHERE id=?", (item_id,)).fetchone()
            active = self._active(db)
            revision = db.execute("SELECT overlays FROM revisions WHERE id=?", (active,)).fetchone()
        if row is None or row["status"] != "approved":
            raise ValueError("An approved enrichment is required")
        item = json.loads(row["payload"])
        overlays = json.loads(revision[0])
        target = (item["table"], item["row_id"], item["field"])
        conflict = [x for x in overlays if (x["table"], x["row_id"], x["field"]) == target]
        if conflict and item["field"] != "NOTE" and item["supersedes"] != conflict[-1]["id"]:
            raise Conflict("Existing correction must be explicitly superseded")
        after = CandidateStore(self.tables, self.snapshot_id, "preview", [*overlays, item])
        before = self.store(active)
        changed = [dict(material_id=rec["material_id"], before=rec["rag"],
                        after=after.by_guid[guid]["rag"],
                        before_metrics=rec["metrics"], after_metrics=after.by_guid[guid]["metrics"],
                        before_reason=rec["reason"], after_reason=after.by_guid[guid]["reason"],
                        before_warnings=rec["warnings"], after_warnings=after.by_guid[guid]["warnings"])
                   for guid, rec in before.by_guid.items()
                   if rec["metrics"] != after.by_guid[guid]["metrics"] or rec["rag"] != after.by_guid[guid]["rag"]]
        return dict(base_revision=active, item_id=item_id, affected=changed,
                    candidate_count=len(changed), overlay_count=len(overlays) + 1,
                    source_warnings=after.source_warnings, snapshot_id=self.snapshot_id,
                    source_change=self._source_change(item, before, overlays))

    def _source_change(self, item, before, overlays):
        prior = [x for x in overlays if (x["table"], x["row_id"], x["field"]) ==
                 (item["table"], item["row_id"], item["field"])]
        original = None
        trait_code = None
        unit = item["unit"]
        if item["kind"] == "correction":
            frame = self.tables[item["table"]]
            row = frame[frame[KEYS[item["table"]]].astype(str) == item["row_id"]].iloc[0]
            trait_code = row.get("TRAIT_CODE")
            original = to_json_safe(row[item["field"]])
            if isinstance(original, float) and not math.isfinite(original):
                original = None
            if item["field"] == "NUMBER_VALUE":
                trait = self.tables["dictionary"].set_index("TRAIT_GUID").loc[row["TRAIT_GUID"]]
                unit, trait_code = trait.UNIT, trait.TRAIT_CODE
            elif item["field"] in {"GENOMIC_BREEDING_VALUE", "DELAY_DAYS"}:
                unit = "index" if item["field"] == "GENOMIC_BREEDING_VALUE" else "days"
        return dict(kind=item["kind"], material_id=before.by_guid[item["material_guid"]]["material_id"],
                    table=item["table"], row_id=item["row_id"], field=item["field"], trait_code=trait_code,
                    original=original, current=prior[-1]["value"] if prior and item["field"] != "NOTE" else original,
                    proposed=item["value"], unit=unit, source=item["source"], observed_at=item["observed_at"],
                    reason=item["reason"], supersedes=item["supersedes"])

    def activate(self, item_id: str, base_revision: str, actor: str, reason: str):
        if not actor.strip() or len(reason.strip()) < 5:
            raise ValueError("Actor and activation reason are required")
        preview = self.preview(item_id)
        if preview["base_revision"] != base_revision:
            raise Conflict("Evidence revision changed; review the new preview")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            if self._active(db) != base_revision:
                raise Conflict("Evidence revision changed; review the new preview")
            row = db.execute("SELECT * FROM enrichment WHERE id=?", (item_id,)).fetchone()
            if row is None or row["status"] != "approved":
                raise Conflict("Enrichment was already activated or changed")
            old = db.execute("SELECT overlays FROM revisions WHERE id=?", (base_revision,)).fetchone()
            overlays = [*json.loads(old[0]), json.loads(row["payload"])]
            revision = uuid.uuid4().hex
            db.execute("INSERT INTO revisions VALUES (?,?,?,?,?,?,?)",
                       (revision, base_revision, self.snapshot_id, dump(overlays), now(), actor.strip(), reason.strip()))
            candidate_store = CandidateStore(self.tables, self.snapshot_id, revision, overlays)
            self._save_recommendations(db, candidate_store)
            self._enrichment_event(db, item_id, "activate", actor, reason)
            db.execute("UPDATE enrichment SET status='activated',activated_revision=? WHERE id=?", (revision, item_id))
            db.execute("UPDATE state SET value=? WHERE key='active_revision'", (revision,))
        return dict(revision_id=revision, preview=preview)

    def rollback(self, target_revision: str, actor: str, reason: str):
        if not actor.strip() or len(reason.strip()) < 5:
            raise ValueError("Actor and reason are required")
        target = self.store(target_revision)
        if target.snapshot_id != self.snapshot_id:
            raise ValueError("To use another archive, configure UC4_ZIP and restart; its history is retained")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self._active(db)
            overlays = db.execute("SELECT overlays FROM revisions WHERE id=?", (target_revision,)).fetchone()[0]
            new = uuid.uuid4().hex
            db.execute("INSERT INTO revisions VALUES (?,?,?,?,?,?,?)",
                       (new, current, self.snapshot_id, overlays, now(), actor.strip(), f"Rollback to {target_revision}: {reason.strip()}"))
            candidate_store = CandidateStore(self.tables, self.snapshot_id, new, json.loads(overlays))
            candidate_store.by_guid = {guid: dict(rec, revision_id=new, recommendation_id=f"{new}:{guid}")
                                       for guid, rec in target.by_guid.items()}
            self._save_recommendations(db, candidate_store)
            db.execute("UPDATE state SET value=? WHERE key='active_revision'", (new,))
        return dict(revision_id=new, copied_from=target_revision)

    def revisions(self):
        with self._db() as db:
            rows = db.execute("SELECT id,parent,snapshot_id,created_at,actor,reason FROM revisions ORDER BY rowid").fetchall()
        return [dict(r) for r in rows]
