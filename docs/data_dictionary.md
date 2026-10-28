# Data dictionary

All tables are created by `suppliersync.pipeline.SCHEMA`. Timestamps are UTC ISO-8601 strings ending in `Z`. Identifiers are text. JSON columns hold serialized objects.

| Table | Purpose and important fields | Keys/constraints |
|---|---|---|
| `products` | Current canonical `product_id`, `name`, normalized `category`, positive `price`, `currency`, `updated_at`, `winning_source`, `winning_record_id` | `product_id` primary key; price check > 0 |
| `source_events` | Immutable accepted source observation including supplier, source file/key, source timestamp, product, raw and normalized JSON, run ID, outcome | `event_id` primary key; `fingerprint` unique |
| `quarantine` | Rejected payload with supplier, file, source key, reason and creation time | `quarantine_id` primary key; fingerprint unique |
| `product_history` | Old/new canonical projection and event causing the change | history ID primary key; `(product_id, source_event_id)` unique |
| `pipeline_runs` | Start/end/status, reconciliation counts, duration and error | run ID primary key |

Supplier A requires `sku,name,category,price,currency,updated_at`; Supplier B requires `item_code,title,department,amount,currency,updated_at`. `source_record_id` is optional and falls back to the one-based CSV data row number (header is row 1) or JSON array index. Extra fields remain in raw JSON. Unknown categories are normalized to `unknown`, not rejected. `data/reference/product_mappings.json` maps `supplier_name:source_code` to a shared canonical product ID; a present mapping file makes unmapped codes invalid. Without it, supplier-scoped deterministic IDs prevent accidental cross-supplier joins.

Foreign key relationships are represented by IDs in event/history records; the SQLite schema enables foreign keys but does not currently declare all these relationships as SQL foreign keys. This makes ingestion resilient to source history retention and avoids cascade deletion.
