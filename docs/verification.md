# Verification evidence

Executed on 2026-10-28 with a fresh temporary virtual environment using Python 3.14.3. `pip install -e '.[dev]'` completed successfully with the declared `pytest>=8` development extra.

## Tests and sample

Command: `pytest -q` from the fresh environment. Result: **21 passed**. `ruff check src tests scripts` and `ruff format --check src tests scripts` also passed; Ruff was installed into the temporary audit environment only and is not a project runtime dependency.

The documented generator command `suppliersync generate --output data/input --records 40 --seed 1729` generated 24 CSV records and 24 JSON records (48 total, including eight edge-case rows), with 10 mapped canonical product IDs. The fresh-database `run` command reported 48 input, 42 accepted, 6 rejected, 0 duplicate, 0 unprocessed, 10 inserted and 10 published. Reconciliation balanced. The CSV export and database report CLI were also run.

The database contained 10 products, 42 source events, 6 quarantine rows, 10 history rows, and 2 run rows after repeating the same inputs. The repeat reported 48 duplicates and zero new accepted, rejected, inserted, updated, or unchanged rows. Product, event, quarantine, and history counts remained unchanged. The database returned `ok` for `PRAGMA integrity_check`; `PRAGMA foreign_key_check` returned no rows. Every event and history product/event reference checked by left join resolved.

The six rejection reasons in the sample were one each: duplicate source key, invalid price, invalid reference mapping, malformed JSON record, missing `name`, and missing `title`. Other invalid-price forms and malformed CSV are covered separately by tests.

Transaction failure and recovery were executed through pytest with the injected partial-publish failure. The products table remained empty after rollback; a failed run row was retained with zero committed accepted rows and one unprocessed input. Reconciliation included unprocessed rows and balanced.

## Benchmark

Command: `python scripts/benchmark.py --records 100000` in the fresh installed environment. This generated 100,008 total records (100,000 requested plus eight deterministic edge rows). The run accepted **100,002**, rejected **6**, had **0** duplicates, and published **25,000** products. Measured wall time including generation was **3.787 seconds**, for **26,411.1 records/second**. Pipeline-only duration reported by the run was **3.746116 seconds**. These measurements describe this environment and are not a performance guarantee.

## Known scope limits

The process reads the batch and candidates into memory; see the design decisions document for a SQLite staging optimization. Discovery is limited to the two documented supplier filenames; unrelated files are ignored. Extra named fields are preserved, while absent required fields reject individual records. Malformed whole JSON files are represented as one file-level rejected record. The schema uses logical IDs for lineage instead of declared foreign-key constraints. SQLite transactions and unique indexes protect local single-database processing; this is not a distributed or multi-writer pipeline.

## Dashboard and documentation verification (2026-10-29)

Installed the dashboard and development extras in the project virtual environment with `python -m pip install -e '.[dev,dashboard]'`. The resolved dashboard dependency was Streamlit **1.66.1** on Python **3.14.3**. The command `.venv/bin/python -m pytest -q` completed with **33 passed**. This suite includes read-only/incomplete/missing database behavior, product and quarantine filters, parameterized search values, lineage and winner labels, reconciliation, CSV and JSON report outputs, malformed report handling, successful and failed CLI subprocesses, a duplicate replay, safe unique sample generation, Streamlit AppTest empty-state and plain-rerun checks, and a full AppTest button-triggered run against a separate temporary demo database.

The app was started bound to localhost with `.venv/bin/streamlit run app.py --server.headless true --server.port 8503 --server.address 127.0.0.1 --server.fileWatcherType none`; `curl http://localhost:8503/` returned **HTTP 200**. Streamlit AppTest loaded the overview with no app exceptions and confirmed the empty state. The ordinary AppTest rerun left the pipeline result unset. No manual browser click-through was performed. Ruff check and format checks passed for `app.py`, `src`, `tests`, and `scripts`; Ruff was installed only into the local ignored virtual environment and is not declared as a project dependency.

A fresh temporary CLI run generated inputs with seed 1729 in a temporary directory and used a temporary database and report. It generated **48** input records, accepted **42**, rejected **6**, and published **10** products; the reconciliation assertion was true. A replay reported **48 duplicates**, with accepted/rejected/inserted/updated/unchanged all zero. Product/event/quarantine/history table counts stayed at **10/42/6/10** before and after replay. SQLite `integrity_check` returned `ok`; CLI CSV export and run-report commands completed.

A new benchmark run used `.venv/bin/python scripts/benchmark.py --records 100000`. It generated **100,008** rows, accepted **100,002**, rejected **6**, published **25,000** products, and reconciled. Measured elapsed time was **3.926 seconds** including generation, or **25,473.6 records/second**. Pipeline-only duration was **3.888060 seconds**. This is a single local measurement, not a performance guarantee.

The user's pre-existing local modification to the tracked `reports/latest.json` was inspected and preserved; it was not used as a run target, staged, or reverted. Dashboard generated files use the ignored `.suppliersync_demo/` path.
