# Architecture

```mermaid
flowchart LR
  A[Supplier A CSV] --> I[Input discovery and parsing]
  B[Supplier B JSON] --> I
  M[Explicit product mappings] --> N[Normalize and validate]
  I --> N
  N -->|Invalid| Q[Quarantine with raw payload and reason]
  N -->|Valid| D[Fingerprint and deduplicate]
  D -->|New source event| L[Source event lineage]
  L --> C[Deterministic conflict resolution]
  C --> P[SQLite canonical products]
  P --> H[Product change history]
  D --> R[Run metrics and reconciliation]
  Q --> R
  P --> R
  R --> J[JSON run report]
  P --> E[CSV export]
  CLI[CLI] --> I
  UI[Optional Streamlit dashboard] -->|explicit button invokes CLI| CLI
  DB[(SQLite)] -->|read-only queries| UI
```

The CLI discovers known supplier filenames (`supplier_a.csv` and `supplier_b.json`), parses rows, validates the supplier-specific schema, standardizes values, resolves explicit product mappings, and stages accepted events and quarantine records in SQLite. The current canonical row is selected among newly observed records per product by latest `updated_at`; timestamp ties use supplier A before supplier B, then ascending source record ID. Previously published newer values cannot be replaced by late older observations. Only a changed canonical projection creates a history row. The transaction protects the publish of event, quarantine, history, and product state. A failed transaction leaves a run row and counts rolled-back records as unprocessed.

For a compact single-process assessment workload, the implementation reads parsed records into memory before publishing. The benchmark measures this real path. A future streaming/batched staging design would reduce peak memory at the cost of more complex cross-file deterministic selection and transaction management.

The optional dashboard is a presentation and inspection layer. Its query helpers use SQLite URI `mode=ro` connections and parameterized filters. A dashboard run invokes the existing CLI in a subprocess only after the user presses **Run Pipeline**. The default database, report, and generated sample area are under the ignored `.suppliersync_demo/` directory; the tracked working database path is blocked. Sample generation chooses a new timestamped folder so it does not replace existing inputs.
