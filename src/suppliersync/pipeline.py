"""Supplier feed ingestion, validation, audit and deterministic publishing."""
from __future__ import annotations

import csv
import hashlib
import json
import logging
import math
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOG = logging.getLogger("suppliersync")
SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS products (
 product_id TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
 price REAL NOT NULL CHECK(price > 0), currency TEXT NOT NULL,
 updated_at TEXT NOT NULL, winning_source TEXT NOT NULL, winning_record_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS source_events (
 event_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL UNIQUE, supplier TEXT NOT NULL,
 source_file TEXT NOT NULL, source_record_id TEXT NOT NULL, source_updated_at TEXT NOT NULL,
 product_id TEXT NOT NULL, raw_json TEXT NOT NULL, normalized_json TEXT NOT NULL,
 run_id TEXT NOT NULL, outcome TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS quarantine (
 quarantine_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL UNIQUE, run_id TEXT NOT NULL,
 supplier TEXT NOT NULL, source_file TEXT NOT NULL, source_record_id TEXT NOT NULL,
 reason TEXT NOT NULL, raw_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS product_history (
 history_id TEXT PRIMARY KEY, product_id TEXT NOT NULL, run_id TEXT NOT NULL,
 changed_at TEXT NOT NULL, old_json TEXT NOT NULL, new_json TEXT NOT NULL,
 source_event_id TEXT NOT NULL, UNIQUE(product_id, source_event_id)
);
CREATE TABLE IF NOT EXISTS pipeline_runs (
 run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
 input_count INTEGER NOT NULL DEFAULT 0, accepted_count INTEGER NOT NULL DEFAULT 0,
 rejected_count INTEGER NOT NULL DEFAULT 0, duplicate_count INTEGER NOT NULL DEFAULT 0,
 unprocessed_count INTEGER NOT NULL DEFAULT 0,
 inserted_count INTEGER NOT NULL DEFAULT 0, updated_count INTEGER NOT NULL DEFAULT 0,
 unchanged_count INTEGER NOT NULL DEFAULT 0, published_count INTEGER NOT NULL DEFAULT 0,
 duration_seconds REAL, error TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_product ON source_events(product_id);
"""

EXPECTED = {
 "supplier_a": {"sku", "name", "category", "price", "currency", "updated_at"},
 "supplier_b": {"item_code", "title", "department", "amount", "currency", "updated_at"},
}
CATEGORY = {"electronics": "electronics", "home": "home", "apparel": "apparel", "books": "books", "unknown": "unknown"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def connect(path: str | Path) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    columns = {row[1] for row in db.execute("PRAGMA table_info(pipeline_runs)")}
    if "unprocessed_count" not in columns:
        db.execute("ALTER TABLE pipeline_runs ADD COLUMN unprocessed_count INTEGER NOT NULL DEFAULT 0")
        db.commit()
    return db


def fingerprint(supplier: str, record_id: str, raw: Any) -> str:
    payload = json.dumps([supplier, str(record_id), raw], sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def stable_product_id(supplier: str, code: str) -> str:
    # Product identity requires a curated explicit cross-supplier mapping.
    return hashlib.sha256(f"{supplier}:{code}".encode()).hexdigest()[:24]


def read_inputs(directory: str | Path) -> list[tuple[str, str, dict[str, Any], str]]:
    records = []
    for path in sorted(Path(directory).glob("*")):
        if not path.is_file() or path.suffix.lower() not in {".csv", ".json"}:
            continue
        supplier = path.stem.lower()
        if supplier not in EXPECTED:
            continue
        if path.suffix.lower() == ".csv":
            try:
                with path.open(newline="", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f, strict=True, restkey="_extra_fields")
                    for i, row in enumerate(reader, 2):
                        records.append((supplier, path.name, dict(row), str(row.get("source_record_id") or i)))
            except (OSError, csv.Error, UnicodeError) as exc:
                records.append((supplier, path.name, {"_malformed": str(exc)}, "file"))
        else:
            try:
                with path.open(encoding="utf-8") as f:
                    value = json.load(f)
                if not isinstance(value, list):
                    raise ValueError("JSON root must be an array")
                for i, row in enumerate(value, 1):
                    if isinstance(row, dict):
                        records.append((supplier, path.name, row, str(row.get("source_record_id") or row.get("record_id") or i)))
                    else:
                        records.append((supplier, path.name, {"_malformed": row}, str(i)))
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                records.append((supplier, path.name, {"_malformed": str(exc)}, "file"))
    return records


def normalize(supplier: str, raw: dict[str, Any], mappings: dict[str, str] | None = None) -> tuple[dict[str, Any] | None, str | None]:
    if "_malformed" in raw:
        return None, f"malformed_record: {raw['_malformed']}"
    fields = ("sku", "name", "category", "price", "currency", "updated_at") if supplier == "supplier_a" else ("item_code", "title", "department", "amount", "currency", "updated_at")
    missing = [f for f in fields if raw.get(f) is None or str(raw.get(f)).strip() == ""]
    if missing:
        return None, "missing_required_fields: " + ",".join(missing)
    code, name, category, price = (raw[fields[0]], raw[fields[1]], raw[fields[2]], raw[fields[3]])
    try:
        price = float(price)
        if not math.isfinite(price) or price <= 0:
            raise ValueError
    except (ValueError, TypeError, OverflowError):
        return None, "invalid_price"
    cat = str(category).strip().lower()
    cat = CATEGORY.get(cat, "unknown")
    try:
        updated = datetime.fromisoformat(str(raw["updated_at"]).replace("Z", "+00:00"))
        if updated.tzinfo is None:
            return None, "updated_at_requires_timezone"
        updated = updated.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except (ValueError, TypeError):
        return None, "invalid_updated_at"
    mapping_key = f"{supplier}:{str(code).strip()}"
    product_id = (mappings or {}).get(mapping_key)
    if mappings is not None and product_id is None:
        return None, "invalid_reference_mapping"
    product_id = product_id or stable_product_id(supplier, str(code).strip())
    return {"product_id": product_id, "name": " ".join(str(name).strip().split()), "category": cat, "price": price, "currency": str(raw["currency"]).upper().strip(), "updated_at": updated}, None


def run_pipeline(input_dir: str | Path, db_path: str | Path, report_path: str | Path | None = None, fail_after: int | None = None) -> dict[str, Any]:
    started = time.perf_counter(); started_at = utc_now(); run_id = str(uuid.uuid4())
    records = read_inputs(input_dir)
    db = connect(db_path)
    counts = dict(input_count=len(records), accepted_count=0, rejected_count=0, duplicate_count=0, unprocessed_count=0, inserted_count=0, updated_count=0, unchanged_count=0, published_count=0)
    db.execute("INSERT INTO pipeline_runs(run_id,started_at,status,input_count) VALUES(?,?,?,?)", (run_id, started_at, "running", len(records)))
    db.commit()
    try:
        db.execute("BEGIN IMMEDIATE")
        mapping_path = Path(input_dir).parent / "reference" / "product_mappings.json"
        mappings = json.loads(mapping_path.read_text(encoding="utf-8")) if mapping_path.exists() else None
        if mappings is not None and (not isinstance(mappings, dict) or any(not isinstance(k, str) or not isinstance(v, str) or not v.strip() for k, v in mappings.items())):
            raise ValueError("product_mappings.json must be an object of non-empty string IDs")
        candidates: dict[str, list[tuple[dict[str, Any], str, str, str, str, str]]] = {}
        seen_source_keys: set[tuple[str, str]] = set()
        for supplier, source_file, raw, source_id in records:
            raw_json = json.dumps(raw, sort_keys=True, default=str)
            fp = fingerprint(supplier, source_id, raw)
            if db.execute("SELECT 1 FROM source_events WHERE fingerprint=?", (fp,)).fetchone() or db.execute("SELECT 1 FROM quarantine WHERE fingerprint=?", (fp,)).fetchone():
                counts["duplicate_count"] += 1; continue
            # Duplicate source keys in one feed: keep first deterministically, quarantine later rows.
            key = (supplier, source_id)
            if key in seen_source_keys:
                reason = "duplicate_source_key"
                db.execute("INSERT OR IGNORE INTO quarantine VALUES(?,?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), fp, run_id, supplier, source_file, source_id, reason, raw_json, utc_now()))
                counts["rejected_count"] += 1; continue
            seen_source_keys.add(key)
            norm, reason = normalize(supplier, raw, mappings)
            if norm is None:
                db.execute("INSERT OR IGNORE INTO quarantine VALUES(?,?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), fp, run_id, supplier, source_file, source_id, reason, raw_json, utc_now()))
                counts["rejected_count"] += 1; continue
            event_id = hashlib.sha256(f"{supplier}:{source_file}:{source_id}:{fp}".encode()).hexdigest()
            candidates.setdefault(norm["product_id"], []).append((norm, supplier, source_file, source_id, raw_json, event_id))
            db.execute("INSERT INTO source_events VALUES(?,?,?,?,?,?,?,?,?,?,?)", (event_id, fp, supplier, source_file, source_id, norm["updated_at"], norm["product_id"], raw_json, json.dumps(norm, sort_keys=True), run_id, "accepted"))
            counts["accepted_count"] += 1
        for product_id, vals in sorted(candidates.items()):
            # Newest update wins; Supplier A, then ascending source ID break ties.
            latest = max(item[0]["updated_at"] for item in vals)
            chosen, supplier, _, _, _, event_id = min(
                (item for item in vals if item[0]["updated_at"] == latest),
                key=lambda x: (0 if x[1] == "supplier_a" else 1, x[3]),
            )
            oldrow = db.execute("SELECT * FROM products WHERE product_id=?", (product_id,)).fetchone()
            old = dict(oldrow) if oldrow else None
            incoming_rank = (0 if supplier == "supplier_a" else 1, next(x[3] for x in vals if x[5] == event_id))
            existing_rank = (0 if old and old["winning_source"] == "supplier_a" else 1, old["winning_record_id"] if old else "")
            if old is not None and (old["updated_at"] > chosen["updated_at"] or (old["updated_at"] == chosen["updated_at"] and existing_rank <= incoming_rank)):
                counts["unchanged_count"] += 1
                continue
            winning_record_id = incoming_rank[1]
            new = {**chosen, "winning_source": supplier, "winning_record_id": winning_record_id}
            if old is None:
                counts["inserted_count"] += 1
            elif any(old[k] != new[k] for k in new):
                counts["updated_count"] += 1
            else:
                counts["unchanged_count"] += 1
            if old != new:
                db.execute("INSERT INTO product_history VALUES(?,?,?,?,?,?,?)", (str(uuid.uuid4()), product_id, run_id, utc_now(), json.dumps(old, sort_keys=True) if old else "{}", json.dumps(new, sort_keys=True), event_id))
                db.execute("""INSERT INTO products VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(product_id) DO UPDATE SET name=excluded.name,category=excluded.category,price=excluded.price,currency=excluded.currency,updated_at=excluded.updated_at,winning_source=excluded.winning_source,winning_record_id=excluded.winning_record_id""", (product_id, new["name"], new["category"], new["price"], new["currency"], new["updated_at"], supplier, winning_record_id))
            if fail_after is not None and counts["inserted_count"] + counts["updated_count"] >= fail_after:
                raise RuntimeError("injected publishing failure")
        counts["published_count"] = db.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        db.commit()
        status, error = "succeeded", None
    except Exception as exc:
        db.rollback(); status, error = "failed", f"{type(exc).__name__}: {exc}"
        # Counts in a failed publication describe committed facts; the rest are explicitly unprocessed.
        counts["unprocessed_count"] = max(0, counts["input_count"] - counts["duplicate_count"])
        counts["accepted_count"] = counts["rejected_count"] = 0
        counts["inserted_count"] = counts["updated_count"] = counts["unchanged_count"] = 0
        counts["published_count"] = db.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    finished = utc_now(); duration = time.perf_counter() - started
    db.execute("UPDATE pipeline_runs SET finished_at=?,status=?,input_count=?,accepted_count=?,rejected_count=?,duplicate_count=?,unprocessed_count=?,inserted_count=?,updated_count=?,unchanged_count=?,published_count=?,duration_seconds=?,error=? WHERE run_id=?", (finished, status, *(counts[k] for k in ("input_count", "accepted_count", "rejected_count", "duplicate_count", "unprocessed_count", "inserted_count", "updated_count", "unchanged_count", "published_count")), duration, error, run_id)); db.commit(); db.close()
    report = {"run_id": run_id, "started_at": started_at, "finished_at": finished, "status": status, "duration_seconds": round(duration, 6), **counts, "error": error, "reconciliation": {"input_equals_accepted_plus_rejected_plus_duplicates_plus_unprocessed": counts["input_count"] == counts["accepted_count"] + counts["rejected_count"] + counts["duplicate_count"] + counts["unprocessed_count"], "accepted_are_source_events": counts["accepted_count"], "published_is_current_unique_products": counts["published_count"]}}
    LOG.info(json.dumps(report, sort_keys=True))
    if report_path:
        Path(report_path).parent.mkdir(parents=True, exist_ok=True); Path(report_path).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def export_products(db_path: str | Path, output: str | Path) -> None:
    with connect(db_path) as db:
        rows = db.execute("SELECT * FROM products ORDER BY product_id").fetchall()
    output = Path(output); output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["product_id", "name", "category", "price", "currency", "updated_at", "winning_source", "winning_record_id"], lineterminator="\n")
        writer.writeheader(); writer.writerows([dict(r) for r in rows])
