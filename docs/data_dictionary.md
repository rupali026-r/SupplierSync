# Data dictionary

Tables are created by `suppliersync.pipeline.SCHEMA`. SQLite uses its normal dynamic typing; the declared affinities below are `TEXT`, `INTEGER`, and `REAL`. Times are UTC ISO-8601 text ending in `Z`. SQL `NOT NULL` fields are required. JSON payloads are serialized as text. Tables have no cascade deletes.

## Tables

| Table | Column | SQLite type | Null? | Key or rule |
|---|---|---|---|---|
| `products` | `product_id` | TEXT | No | Primary key; explicit canonical ID |
| | `name`, `category`, `currency`, `updated_at`, `winning_source`, `winning_record_id` | TEXT | No | Current canonical values and selected source |
| | `price` | REAL | No | `CHECK(price > 0)` |
| `source_events` | `event_id` | TEXT | No | Primary key; stable event digest |
| | `fingerprint` | TEXT | No | Unique; digest of supplier, source record ID, and raw row |
| | `supplier`, `source_file`, `source_record_id`, `source_updated_at`, `product_id`, `raw_json`, `normalized_json`, `run_id`, `outcome` | TEXT | No | Source lineage; raw and normalized values |
| `quarantine` | `quarantine_id` | TEXT | No | Primary key |
| | `fingerprint` | TEXT | No | Unique rejected-observation digest |
| | `run_id`, `supplier`, `source_file`, `source_record_id`, `reason`, `raw_json`, `created_at` | TEXT | No | Rejection context and preserved payload |
| `product_history` | `history_id` | TEXT | No | Primary key |
| | `product_id`, `run_id`, `changed_at`, `old_json`, `new_json`, `source_event_id` | TEXT | No | Before/after snapshots and cause |
| | `(product_id, source_event_id)` | — | — | Unique; prevents duplicate history per event |
| `pipeline_runs` | `run_id` | TEXT | No | Primary key; UUID |
| | `started_at`, `finished_at`, `status`, `error` | TEXT | `finished_at`, `error` can be NULL | UTC lifecycle and failure details |
| | `input_count`, `accepted_count`, `rejected_count`, `duplicate_count`, `unprocessed_count`, `inserted_count`, `updated_count`, `unchanged_count`, `published_count` | INTEGER | No | Counters default to zero |
| | `duration_seconds` | REAL | Yes | Elapsed wall time |

`idx_events_product` indexes `source_events(product_id)`. Unique indexes are created for source event fingerprints and `(product_id, source_event_id)` history pairs. `pipeline_runs` has an additive migration for `unprocessed_count` when opening a database created by the earlier schema version.

## Feed schemas and relationships

Supplier A is `supplier_a.csv` with required `sku,name,category,price,currency,updated_at`. Supplier B is `supplier_b.json`, a JSON array with `item_code,title,department,amount,currency,updated_at`. `source_record_id` is optional; fallback IDs are the CSV data row number (header is line 1) and the one-based JSON array index. Source IDs are converted to text.

Extra named columns and extra unheaded CSV values are accepted and preserved in `raw_json`; missing required fields reject each affected row. Unknown categories normalize to `unknown`. Invalid/non-finite/zero/negative prices and timezone-naive/invalid timestamps are rejected. The optional `data/reference/product_mappings.json` maps `supplier_name:source_code` to a non-empty canonical product ID. When present, a missing code mapping is rejected. When absent, supplier-scoped hashes prevent cross-supplier merges. Product IDs and run IDs in other tables reference these IDs logically; the schema does not currently declare SQL foreign-key constraints. History `source_event_id` identifies the event causing a canonical change. All rejected rows retain supplier, filename, source identifier, raw payload, and reason.
