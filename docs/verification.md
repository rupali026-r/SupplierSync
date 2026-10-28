# Verification evidence

Executed on 2026-10-28 with a fresh temporary virtual environment using Python 3.14.3. `pip install -e '.[dev]'` completed successfully with the declared `pytest>=8` development extra.

## Tests and sample

Command: `pytest -q` from the fresh environment. Result: **20 passed**.

The documented generator command `suppliersync generate --output data/input --records 40 --seed 1729` generated 24 CSV records and 24 JSON records (48 total, including eight edge-case rows), with 10 mapped canonical product IDs. The fresh-database `run` command reported 48 input, 42 accepted, 6 rejected, 0 duplicate, 0 unprocessed, 10 inserted and 10 published. Reconciliation balanced. The CSV export and database report CLI were also run.

The database contained 10 products, 42 source events, 6 quarantine rows, 10 history rows, and 2 run rows after repeating the same inputs. The repeat reported 48 duplicates and zero new accepted, rejected, inserted, updated, or unchanged rows. Product, event, quarantine, and history counts remained unchanged. The database returned `ok` for `PRAGMA integrity_check`; `PRAGMA foreign_key_check` returned no rows. Every event and history product/event reference checked by left join resolved.

The six rejection reasons in the sample were one each: duplicate source key, invalid price, invalid reference mapping, malformed JSON record, missing `name`, and missing `title`. Other invalid-price forms and malformed CSV are covered separately by tests.

Transaction failure and recovery were executed through pytest with the injected partial-publish failure. The products table remained empty after rollback; a failed run row was retained with zero committed accepted rows and one unprocessed input. Reconciliation included unprocessed rows and balanced.

## Benchmark

Command: `python scripts/benchmark.py --records 100000` in the fresh installed environment. This generated 100,008 total records (100,000 requested plus eight deterministic edge rows). The run accepted **100,002**, rejected **6**, had **0** duplicates, and published **25,000** products. Measured wall time including generation was **4.110 seconds**, for **24,333.9 records/second**. Pipeline-only duration reported by the run was **4.069416 seconds**. These measurements describe this environment and are not a performance guarantee.

## Known scope limits

The process reads the batch and candidates into memory; see the design decisions document for a SQLite staging optimization. Discovery is limited to the two documented supplier filenames; unrelated files are ignored. Extra named fields are preserved, while absent required fields reject individual records. Malformed whole JSON files are represented as one file-level rejected record. The schema uses logical IDs for lineage instead of declared foreign-key constraints. SQLite transactions and unique indexes protect local single-database processing; this is not a distributed or multi-writer pipeline.
