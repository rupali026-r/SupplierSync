"""Read-only dashboard queries and safe wrappers around the existing CLI."""

from __future__ import annotations

import csv
import io
import json
import os
import sqlite3
import subprocess
import sys
import time
from collections.abc import Iterable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEMO_ROOT = PROJECT_ROOT / ".suppliersync_demo"
DEMO_DB = DEMO_ROOT / "suppliersync_demo.db"
DEMO_REPORT = DEMO_ROOT / "latest.json"
COUNT_FIELDS = (
    "input_count",
    "accepted_count",
    "rejected_count",
    "duplicate_count",
    "unprocessed_count",
    "inserted_count",
    "updated_count",
    "unchanged_count",
    "published_count",
)


@contextmanager
def _readonly(db_path: str | Path):
    path = Path(db_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Database does not exist: {path}")
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=3)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def database_status(db_path: str | Path) -> tuple[bool, str]:
    try:
        with _readonly(db_path) as db:
            tables = {
                row[0]
                for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            required = {
                "products",
                "source_events",
                "quarantine",
                "product_history",
                "pipeline_runs",
            }
            missing = sorted(required - tables)
            if missing:
                return False, "Database schema is incomplete: " + ", ".join(missing)
            db.execute("SELECT 1").fetchone()
        return True, "Connected · schema ready"
    except (OSError, sqlite3.Error) as exc:
        return False, f"Database unavailable: {exc}"


def _rows(
    db_path: str | Path, sql: str, params: Iterable[Any] = ()
) -> list[dict[str, Any]]:
    with _readonly(db_path) as db:
        return [dict(row) for row in db.execute(sql, tuple(params)).fetchall()]


def get_runs(db_path: str | Path, limit: int | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM pipeline_runs ORDER BY started_at DESC, run_id DESC"
    params: tuple[Any, ...] = ()
    if limit is not None:
        sql += " LIMIT ?"
        params = (max(0, int(limit)),)
    return _rows(db_path, sql, params)


def get_products(
    db_path: str | Path,
    search: str = "",
    categories: Iterable[str] = (),
    suppliers: Iterable[str] = (),
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if search.strip():
        clauses.append("(p.name LIKE ? ESCAPE '\\' OR p.product_id LIKE ? ESCAPE '\\')")
        escaped = (
            search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        params.extend((f"%{escaped}%", f"%{escaped}%"))
    for field, selected in (
        ("p.category", categories),
        ("p.winning_source", suppliers),
    ):
        values = tuple(selected)
        if values:
            clauses.append(f"{field} IN ({','.join('?' for _ in values)})")
            params.extend(values)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    sql = f"""SELECT p.product_id, p.name, p.category, p.price, p.currency,
        p.updated_at, p.winning_source, p.winning_record_id,
        (SELECT e.source_file FROM source_events e
         WHERE e.product_id=p.product_id AND e.supplier=p.winning_source
           AND e.source_record_id=p.winning_record_id
         ORDER BY e.source_updated_at DESC, e.event_id DESC LIMIT 1) AS winning_source_file
        FROM products p{where} ORDER BY p.name COLLATE NOCASE, p.product_id"""
    return _rows(db_path, sql, params)


def get_quarantine(
    db_path: str | Path,
    suppliers: Iterable[str] = (),
    reasons: Iterable[str] = (),
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    for field, selected in (("supplier", suppliers), ("reason", reasons)):
        values = tuple(selected)
        if values:
            clauses.append(f"{field} IN ({','.join('?' for _ in values)})")
            params.extend(values)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return _rows(
        db_path,
        "SELECT quarantine_id, fingerprint, run_id, supplier, source_file, source_record_id, reason, raw_json, created_at FROM quarantine"
        + where
        + " ORDER BY created_at DESC, quarantine_id",
        params,
    )


def get_lineage(
    db_path: str | Path, product_id: str
) -> dict[str, list[dict[str, Any]]]:
    events = _rows(
        db_path,
        """SELECT event_id, supplier, source_file, source_record_id, source_updated_at,
           product_id, raw_json, normalized_json, run_id, outcome
           FROM source_events WHERE product_id=?
           ORDER BY source_updated_at DESC, supplier, source_record_id""",
        (product_id,),
    )
    history = _rows(
        db_path,
        "SELECT history_id, product_id, run_id, changed_at, old_json, new_json, source_event_id FROM product_history WHERE product_id=? ORDER BY changed_at DESC, history_id",
        (product_id,),
    )
    current_change = _rows(
        db_path,
        "SELECT source_event_id FROM product_history WHERE product_id=? ORDER BY changed_at DESC, history_id DESC LIMIT 1",
        (product_id,),
    )
    current_winner_event_id = (
        current_change[0]["source_event_id"] if current_change else None
    )
    for event in events:
        event["winner_status"] = (
            "Current winner"
            if event["event_id"] == current_winner_event_id
            else "Other accepted observation"
        )
        event["raw"] = _safe_json(event.pop("raw_json"))
        event["normalized"] = _safe_json(event.pop("normalized_json"))
    for item in history:
        item["old_projection"] = _safe_json(item.pop("old_json"))
        item["new_projection"] = _safe_json(item.pop("new_json"))
    return {"events": events, "history": history}


def _safe_json(value: str) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {"unparsed_value": value}


def product_count(db_path: str | Path) -> int:
    rows = _rows(db_path, "SELECT COUNT(*) AS n FROM products")
    return int(rows[0]["n"])


def reconciliation(run: dict[str, Any]) -> dict[str, int | bool]:
    parts = {name: int(run.get(name) or 0) for name in COUNT_FIELDS}
    return {
        **parts,
        "balanced": parts["input_count"]
        == parts["accepted_count"]
        + parts["rejected_count"]
        + parts["duplicate_count"]
        + parts["unprocessed_count"],
    }


def csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    if not rows:
        return b""
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output, fieldnames=list(rows[0]), extrasaction="ignore", lineterminator="\n"
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                key: json.dumps(value, sort_keys=True)
                if isinstance(value, (dict, list))
                else value
                for key, value in row.items()
            }
        )
    return output.getvalue().encode("utf-8")


def report_for_run(
    db_path: str | Path, run_id: str, report_path: str | Path | None = None
) -> dict[str, Any]:
    if report_path and Path(report_path).is_file():
        try:
            report = json.loads(Path(report_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Run report cannot be read: {exc}") from exc
        if not isinstance(report, dict) or not isinstance(report.get("run_id"), str):
            raise ValueError("Run report must be a JSON object with a run_id")
        if report["run_id"] == run_id:
            report["report_source"] = "original CLI report"
            return report
    runs = get_runs(db_path)
    run = next((item for item in runs if item["run_id"] == run_id), None)
    if run is None:
        raise KeyError(f"Run not found: {run_id}")
    report = dict(run)
    report["reconciliation"] = reconciliation(run)
    report["report_source"] = "reconstructed from persisted pipeline_runs row"
    return report


def generate_demo_inputs(
    parent: str | Path, records: int = 40, seed: int = 1729
) -> tuple[Path, dict[str, int]]:
    """Generate into a new, unique directory; existing files are never replaced."""
    from .generate import generate

    root = Path(parent).resolve()
    root.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    candidate = root / f"sample-{stamp}"
    suffix = 1
    while candidate.exists():
        candidate = root / f"sample-{stamp}-{suffix}"
        suffix += 1
    input_dir = candidate / "input"
    stats = generate(input_dir, records=records, seed=seed)
    return input_dir, stats


def validate_project_directory(path: str | Path, must_exist: bool = True) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_relative_to(PROJECT_ROOT):
        raise ValueError(
            "For this local demo, select a path inside the SupplierSync project directory."
        )
    if must_exist and not resolved.is_dir():
        raise FileNotFoundError(f"Directory does not exist: {resolved}")
    return resolved


def validate_database_path(path: str | Path) -> Path:
    """Validate a configured dashboard database without opening it."""
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_relative_to(PROJECT_ROOT):
        raise ValueError(
            "For this local demo, choose a database path inside the project directory."
        )
    primary = (PROJECT_ROOT / "data" / "suppliersync.db").resolve()
    if resolved == primary:
        raise ValueError(
            "Dashboard runs may not use data/suppliersync.db; choose a separate demo database."
        )
    return resolved


def run_pipeline_cli(
    input_dir: str | Path,
    db_path: str | Path,
    report_path: str | Path,
    timeout: int = 300,
) -> dict[str, Any]:
    input_path = validate_project_directory(input_dir)
    db = validate_database_path(db_path)
    report = Path(report_path).expanduser().resolve()
    if not report.is_relative_to(PROJECT_ROOT):
        raise ValueError(
            "Database and report paths must stay inside the project directory."
        )
    db.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    inputs = [
        p
        for p in input_path.iterdir()
        if p.is_file() and p.name.lower() in {"supplier_a.csv", "supplier_b.json"}
    ]
    if not inputs:
        raise FileNotFoundError(
            f"No supported supplier feeds found in {input_path}; expected supplier_a.csv or supplier_b.json"
        )
    cmd = [
        sys.executable,
        "-m",
        "suppliersync.cli",
        "run",
        "--input",
        str(input_path),
        "--db",
        str(db),
        "--report",
        str(report),
    ]
    env = os.environ.copy()
    # Use the real package source even when tests or a caller override the demo root.
    src = str(Path(__file__).resolve().parents[2] / "src")
    env["PYTHONPATH"] = src + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "status": "failed",
            "exit_status": None,
            "duration_seconds": time.perf_counter() - started,
            "stdout": "",
            "stderr": str(exc),
            "report": None,
            "command": cmd,
        }
    elapsed = time.perf_counter() - started
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise TypeError("report root is not an object")
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        payload = None
        report_error = f"Unable to parse the generated run report: {exc}"
    else:
        report_error = None
    if payload is not None:
        balanced = (
            all(field in payload for field in COUNT_FIELDS)
            and reconciliation(payload)["balanced"]
        )
        if not balanced:
            report_error = (
                "Generated run report is missing required counts or does not reconcile."
            )
    else:
        balanced = False
    succeeded = (
        completed.returncode == 0
        and payload is not None
        and payload.get("status") == "succeeded"
        and balanced
    )
    return {
        "status": "succeeded" if succeeded else "failed",
        "exit_status": completed.returncode,
        "duration_seconds": elapsed,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "report": payload,
        "report_error": report_error,
        "command": cmd,
    }
