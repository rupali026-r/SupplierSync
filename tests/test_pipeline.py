import csv
import json
import sqlite3

import pytest

from suppliersync.generate import generate
from suppliersync.pipeline import connect, normalize, run_pipeline


def setup_feed(tmp_path, rows_a=None, rows_b=None, mappings=None):
    inp = tmp_path / "input"
    inp.mkdir(exist_ok=True)
    rows_a = rows_a or []
    with (inp / "supplier_a.csv").open("w", newline="") as f:
        fields = (
            list(rows_a[0])
            if rows_a
            else [
                "source_record_id",
                "sku",
                "name",
                "category",
                "price",
                "currency",
                "updated_at",
            ]
        )
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows_a)
    (inp / "supplier_b.json").write_text(json.dumps(rows_b or []))
    ref = tmp_path / "reference"
    ref.mkdir(exist_ok=True)
    if mappings is not None:
        (ref / "product_mappings.json").write_text(json.dumps(mappings))
    return inp


def row(
    code="A1", price="10", timestamp="2025-01-01T00:00:00Z", source_id="1", **extra
):
    return {
        "source_record_id": source_id,
        "sku": code,
        "name": " Gadget ",
        "category": "Electronics",
        "price": price,
        "currency": "usd",
        "updated_at": timestamp,
        **extra,
    }


def test_happy_path_and_conflict_resolution(tmp_path):
    inp = setup_feed(
        tmp_path,
        [row()],
        [
            {
                "source_record_id": "b1",
                "item_code": "B1",
                "title": "Gadget",
                "department": "home",
                "amount": 12,
                "currency": "USD",
                "updated_at": "2025-01-02T00:00:00Z",
            }
        ],
        {"supplier_a:A1": "prod-1", "supplier_b:B1": "prod-1"},
    )
    report = run_pipeline(inp, tmp_path / "db.sqlite")
    assert report["status"] == "succeeded" and report["published_count"] == 1
    with connect(tmp_path / "db.sqlite") as db:
        p = db.execute("select * from products").fetchone()
        assert p["price"] == 12 and p["winning_source"] == "supplier_b"
        assert db.execute("select count(*) from source_events").fetchone()[0] == 2
        assert db.execute("select count(*) from product_history").fetchone()[0] == 1


def test_supplier_a_wins_exact_timestamp_tie(tmp_path):
    timestamp = "2025-01-02T00:00:00Z"
    inp = setup_feed(
        tmp_path,
        [row(timestamp=timestamp, source_id="A-2", price="10")],
        [
            {
                "source_record_id": "B-1",
                "item_code": "B1",
                "title": "Gadget",
                "department": "home",
                "amount": 12,
                "currency": "USD",
                "updated_at": timestamp,
            }
        ],
        {"supplier_a:A1": "prod-tie", "supplier_b:B1": "prod-tie"},
    )
    report = run_pipeline(inp, tmp_path / "db.sqlite")
    assert report["inserted_count"] == 1
    with connect(tmp_path / "db.sqlite") as db:
        p = db.execute(
            "select price, winning_source, winning_record_id from products"
        ).fetchone()
        assert tuple(p) == (10.0, "supplier_a", "A-2")


def test_idempotent_repeated_input(tmp_path):
    inp = setup_feed(tmp_path, [row()])
    dbpath = tmp_path / "db.sqlite"
    first = run_pipeline(inp, dbpath)
    second = run_pipeline(inp, dbpath)
    assert first["inserted_count"] == 1 and second["duplicate_count"] == 1
    assert first["run_id"] != second["run_id"]
    assert first["started_at"].endswith("Z") and first["finished_at"].endswith("Z")
    with connect(dbpath) as db:
        assert db.execute("select count(*) from products").fetchone()[0] == 1
        assert db.execute("select count(*) from product_history").fetchone()[0] == 1


@pytest.mark.parametrize("price", ["0", "-1", "NaN", "inf", "abc", None])
def test_reject_invalid_price(tmp_path, price):
    r = row(price=price)
    inp = setup_feed(tmp_path, [r])
    result = run_pipeline(inp, tmp_path / "db.sqlite")
    assert result["rejected_count"] == 1 and result["published_count"] == 0


def test_missing_null_unknown_category_and_extra_columns(tmp_path):
    r = row(category="not a category", unused="surprise")
    r["name"] = None
    inp = setup_feed(tmp_path, [r])
    result = run_pipeline(inp, tmp_path / "db.sqlite")
    assert result["rejected_count"] == 1
    with connect(tmp_path / "db.sqlite") as db:
        assert (
            db.execute("select reason from quarantine").fetchone()[0]
            == "missing_required_fields: name"
        )
    assert (
        normalize("supplier_a", {**row(), "category": "bogus"})[0]["category"]
        == "unknown"
    )


def test_unknown_mapping_is_quarantined(tmp_path):
    inp = setup_feed(tmp_path, [row()], mappings={})
    result = run_pipeline(inp, tmp_path / "db.sqlite")
    assert result["rejected_count"] == 1
    with connect(tmp_path / "db.sqlite") as db:
        assert (
            "invalid_reference_mapping"
            in db.execute("select reason from quarantine").fetchone()[0]
        )


def test_duplicate_source_key_and_reproducibility(tmp_path):
    inp = setup_feed(
        tmp_path, [row(source_id="same"), row(source_id="same", price="11")]
    )
    result = run_pipeline(inp, tmp_path / "db.sqlite")
    assert result["accepted_count"] == 1 and result["rejected_count"] == 1
    a, b = tmp_path / "a", tmp_path / "b"
    stats_a = generate(a, 40, 99)
    stats_b = generate(b, 40, 99)
    assert stats_a == stats_b and stats_a["rejected_edge_records"] == 6
    assert (a / "supplier_a.csv").read_bytes() == (b / "supplier_a.csv").read_bytes()
    assert (a / "supplier_b.json").read_bytes() == (b / "supplier_b.json").read_bytes()


def test_empty_batch_and_transaction_rollback(tmp_path):
    inp = setup_feed(tmp_path)
    empty = run_pipeline(inp, tmp_path / "empty.sqlite")
    assert empty["status"] == "succeeded" and empty["published_count"] == 0
    setup_feed(tmp_path, [row()])
    result = run_pipeline(inp, tmp_path / "rollback.sqlite", fail_after=1)
    assert result["status"] == "failed" and result["unprocessed_count"] == 1
    assert result["accepted_count"] == 0
    assert result["reconciliation"][
        "input_equals_accepted_plus_rejected_plus_duplicates_plus_unprocessed"
    ]
    with connect(tmp_path / "rollback.sqlite") as db:
        assert db.execute("select count(*) from products").fetchone()[0] == 0
        assert db.execute("select status from pipeline_runs").fetchone()[0] == "failed"


def test_malformed_json_quarantined(tmp_path):
    inp = setup_feed(tmp_path)
    (inp / "supplier_b.json").write_text("{")
    result = run_pipeline(inp, tmp_path / "db.sqlite")
    assert result["rejected_count"] == 1


def test_late_arriving_older_update_does_not_revert_product(tmp_path):
    inp = setup_feed(
        tmp_path,
        [row(price="22", timestamp="2025-02-01T00:00:00Z")],
        mappings={"supplier_a:A1": "prod-1"},
    )
    dbpath = tmp_path / "db.sqlite"
    assert run_pipeline(inp, dbpath)["inserted_count"] == 1
    setup_feed(
        tmp_path,
        [row(price="10", timestamp="2025-01-01T00:00:00Z", source_id="older")],
        mappings={"supplier_a:A1": "prod-1"},
    )
    second = run_pipeline(inp, dbpath)
    assert second["unchanged_count"] == 1
    with connect(dbpath) as db:
        assert db.execute("select price from products").fetchone()[0] == 22
        assert db.execute("select count(*) from source_events").fetchone()[0] == 2


def test_extra_columns_are_preserved_and_missing_schema_is_rejected(tmp_path):
    inp = setup_feed(tmp_path, [row(unexpected="extra")])
    first = run_pipeline(inp, tmp_path / "db.sqlite")
    assert first["accepted_count"] == 1
    with connect(tmp_path / "db.sqlite") as db:
        raw = json.loads(db.execute("select raw_json from source_events").fetchone()[0])
        assert raw["unexpected"] == "extra"
    setup_feed(tmp_path, [{"source_record_id": "2", "sku": "A2"}])
    second = run_pipeline(inp, tmp_path / "other.sqlite")
    assert second["rejected_count"] == 1


def test_malformed_csv_file_is_quarantined(tmp_path):
    inp = setup_feed(tmp_path)
    (inp / "supplier_a.csv").write_text(
        'source_record_id,sku,name,category,price,currency,updated_at\n1,A,"broken,Electronics,10,USD,2025-01-01T00:00:00Z\n'
    )
    result = run_pipeline(inp, tmp_path / "db.sqlite")
    assert result["rejected_count"] == 1
    with connect(tmp_path / "db.sqlite") as db:
        assert (
            "malformed_record"
            in db.execute("select reason from quarantine").fetchone()[0]
        )


def test_unheaded_extra_csv_values_remain_in_lineage(tmp_path):
    inp = setup_feed(tmp_path)
    (inp / "supplier_a.csv").write_text(
        "source_record_id,sku,name,category,price,currency,updated_at\n1,A1,Gadget,electronics,10,USD,2025-01-01T00:00:00Z,extra\n"
    )
    result = run_pipeline(inp, tmp_path / "db.sqlite")
    assert result["accepted_count"] == 1
    with connect(tmp_path / "db.sqlite") as db:
        raw = json.loads(db.execute("select raw_json from source_events").fetchone()[0])
        assert raw["_extra_fields"] == ["extra"]


def test_malformed_mapping_fails_run_and_reconciles_unprocessed(tmp_path):
    inp = setup_feed(tmp_path, [row()])
    (tmp_path / "reference" / "product_mappings.json").write_text("[]")
    result = run_pipeline(inp, tmp_path / "db.sqlite")
    assert result["status"] == "failed"
    assert "must be an object" in result["error"]
    assert result["unprocessed_count"] == 1
    with connect(tmp_path / "db.sqlite") as db:
        run = db.execute(
            "select status, accepted_count, unprocessed_count, error from pipeline_runs"
        ).fetchone()
        assert run[0] == "failed" and run[1] == 0 and run[2] == 1


def test_generated_edge_dataset_reconciles_actual_rejections(tmp_path):
    inputs = tmp_path / "data" / "input"
    stats = generate(inputs, 40, 1729)
    result = run_pipeline(inputs, tmp_path / "fresh.sqlite")
    assert result["input_count"] == stats["input_records"] == 48
    assert result["accepted_count"] == 42 and result["rejected_count"] == 6
    assert (
        result["published_count"] == 10
        and result["reconciliation"][
            "input_equals_accepted_plus_rejected_plus_duplicates_plus_unprocessed"
        ]
    )
    with connect(tmp_path / "fresh.sqlite") as db:
        assert db.execute("select count(*) from quarantine").fetchone()[0] == 6
        assert db.execute("select count(*) from products").fetchone()[0] == 10
        assert db.execute("select count(*) from source_events").fetchone()[0] == 42


def test_existing_run_table_gets_additive_unprocessed_migration(tmp_path):
    dbpath = tmp_path / "legacy.sqlite"
    with sqlite3.connect(dbpath) as db:
        db.execute(
            "CREATE TABLE pipeline_runs (run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL, input_count INTEGER NOT NULL DEFAULT 0, accepted_count INTEGER NOT NULL DEFAULT 0, rejected_count INTEGER NOT NULL DEFAULT 0, duplicate_count INTEGER NOT NULL DEFAULT 0, inserted_count INTEGER NOT NULL DEFAULT 0, updated_count INTEGER NOT NULL DEFAULT 0, unchanged_count INTEGER NOT NULL DEFAULT 0, published_count INTEGER NOT NULL DEFAULT 0, duration_seconds REAL, error TEXT)"
        )
    with connect(dbpath) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(pipeline_runs)")}
        assert "unprocessed_count" in columns
