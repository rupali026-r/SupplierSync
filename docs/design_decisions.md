# Design decisions

## Identity and conflicts

Product identity is a curated reference mapping, never fuzzy name similarity. The generator creates two distinct supplier code spaces and maps them to shared product IDs. Conflict selection is deterministic: latest source `updated_at` wins; equal timestamps rank Supplier A above Supplier B, then lexicographically ascending source record ID wins. Every accepted source value remains in `source_events`, even when it loses. Canonical change history stores the selected old/new projections.

## Validation and idempotency

Required fields must be present and nonblank. Price must parse as a finite, strictly positive number. `updated_at` must be a timezone-aware ISO-8601 timestamp. Currency is uppercased; names are whitespace-normalized; unknown categories become `unknown`. Duplicate `(supplier, source_record_id)` keys within a batch keep the first discovered row and quarantine later rows. The fingerprint includes the raw row, so the same payload/key/file repeated is skipped; modified values become a new auditable event.

Input filenames are fixed to the two documented suppliers. A malformed JSON file is represented as one file-level quarantine item. CSV parsing handles ordinary CSV quoting and encoding; it does not attempt recovery of arbitrary broken CSV dialects. CSV headers are not strictly rejected for added columns; missing fields reject records. Unknown supplier files are ignored.

## Recovery, performance, limitations

One SQLite transaction covers a run's accepted source events, rejected rows, canonical writes and history. Failure rolls back those writes, then stores a failed operational run row. Failed-run metrics count only committed accepted/rejected rows and explicitly classify rolled-back inputs as unprocessed; previously seen duplicates remain counted. Retrying the same input is safe after success because of unique fingerprints. A failure after rollback will retry all input. Changing a product mapping does not change the source payload fingerprint, so an already-seen source event is skipped and is not automatically reassigned; mapping changes need a deliberate database backfill/rebuild procedure. There is no concurrent writer coordination beyond SQLite's `BEGIN IMMEDIATE`, no schema evolution framework beyond the additive run-metric column migration, and no durable external object store for raw files; source payloads are embedded in SQLite.

Input files and valid candidates are materialized in memory to allow deterministic conflict selection across supplier feeds. This is simple and reproducible, but memory grows with batch size. A reasonable next optimization is bounded-memory staging to a temporary SQLite table plus indexed winner selection; it trades implementation complexity and extra disk I/O for lower RAM use.

Synthetic data includes reproducible supplier rows and code mappings plus deterministic edge cases: duplicate source keys, missing/null fields, non-finite and nonnumeric prices, a malformed JSON row, an unmapped product code, an unknown category, an unexpected column, and older/changed observations. The benchmark includes those edge rows. No production data is used.

## Interview discussion

Explain the distinction between source-event deduplication (same supplier observation) and entity resolution (explicit mapping to the same product). Discuss the deterministic tie-break rule, why losing source values are still retained, and how the transaction and unique fingerprint constraints make retries safe. The winner policy is intentionally simple and would typically become configurable by attribute, supplier quality, effective date, and business ownership in production.
