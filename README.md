# SupplierSync

An auditable, local Python pipeline for validating CSV and JSON supplier feeds, preserving source events and rejected rows, and publishing deterministic canonical products to SQLite.

## Requirements and setup

Python 3.11+ (developed and verified with Python 3.14) and pytest for tests. Runtime uses only the standard library.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
```

## Run from the repository root

```sh
suppliersync generate --output data/input --records 40 --seed 1729
suppliersync run --input data/input --db data/suppliersync.db --report reports/latest.json
suppliersync export --db data/suppliersync.db --output outputs/products.csv
suppliersync report --db data/suppliersync.db
pytest -q
python scripts/benchmark.py --records 100000
```

Without installing the package, use `.venv/bin/python -m suppliersync.cli ...` (with `PYTHONPATH=src`) or `PYTHONPATH=src .venv/bin/python -m suppliersync.cli ...`.

Generated files are reproducible for a fixed record count and seed. `data/expected/sample_generation.json` records generator expectations, distinct from feed inputs; runtime reconciliation is emitted to `reports/latest.json`. Product IDs in the reference mapping intentionally join equivalent supplier codes. The pipeline does not infer identity from names.

## What gets stored

`products` is the current canonical projection. `source_events` retains normalized and raw values for accepted feed events. `quarantine` retains every rejected payload and reason. `product_history` records changes to the canonical projection. `pipeline_runs` reports counts, duration and failure details. Schema and keys are described in [docs/data_dictionary.md](docs/data_dictionary.md); operational behavior and policy are described in [docs/design_decisions.md](docs/design_decisions.md).

Each run has a UUID; event fingerprints are deterministic over supplier, source record key and raw payload. Replaying an event is counted as a duplicate. A changed payload under an existing record key is a new event. Publication occurs in one SQLite transaction; if publishing fails, the transaction rolls back and a failed run row is committed afterward. File-level parse errors become quarantined records where practical. A backfill can be run by supplying the desired files; existing event fingerprints will be skipped.

The report reconciles each input as accepted, rejected, or previously seen duplicate. Accepted events may represent the same product; published count is the number of distinct current products in the database, not the number of accepted records.

## Example database inspection

```sql
SELECT status, input_count, accepted_count, rejected_count, duplicate_count,
       inserted_count, updated_count, unchanged_count, published_count
FROM pipeline_runs ORDER BY started_at;
SELECT reason, COUNT(*) FROM quarantine GROUP BY reason;
SELECT product_id, COUNT(*) AS supplier_events FROM source_events GROUP BY product_id;
```

See [docs/architecture.md](docs/architecture.md) for the flow and [docs/design_decisions.md](docs/design_decisions.md) for limitations and trade-offs.
