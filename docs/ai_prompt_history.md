# AI prompt history

This file records the user-provided prompts that directed the implementation and this audit. AI assistance was used to inspect, implement, test, document, and prepare the repository. The measured results are from commands executed against the local project, not supplied by the prompt. No secrets or credentials are included.

## Prompt 1 — Build SupplierSync (provided as a pasted text attachment)

Purpose: implement the assessment project end to end. The following is the actual prompt text supplied for that work.

```text
# Build SupplierSync: Complete Data Engineering Assessment

Act as a senior data engineer and Python developer. Build a complete, tested, maintainable data engineering project in the current workspace named SupplierSync.

## Context

This project is for a 72-hour data engineering coding assessment. The requirement is to combine product feeds from multiple suppliers with different schemas and product codes, standardize attributes, resolve conflicts deterministically, maintain source-level traceability, quarantine invalid records, and publish reliable outputs.

This must be a real, executable data engineering pipeline, not a mockup, a website-only solution, or a collection of pseudocode files.

## 1. Inspect the workspace first

Inspect the existing files before making changes. Preserve useful work. Do not overwrite files blindly.

Create a concise implementation plan, then execute it. Do not stop after generating a plan or skeleton.

## 2. Technology

Use:
- Python 3.14-compatible code where practical.
- SQLite for persistent local storage.
- Python standard library for CSV, JSON, hashing, timestamps, and SQLite.
- pytest for automated tests.
- A minimal dependency set.
- A CLI for running the pipeline.
- SQL queries and CSV/JSON reports for demonstrating results.

Avoid Docker, paid cloud services, unnecessary frameworks, and complex infrastructure.

## 3. Supplier feeds

Generate reproducible synthetic supplier data in different schemas and formats:
- Supplier A: CSV.
- Supplier B: JSON.
- At least two different supplier product-code systems.
- Matching products with conflicting prices and categories.
- Missing required fields, nulls, invalid prices, duplicate source keys, malformed records, unknown categories, and unexpected columns.
- Late-arriving records and changed product attributes.
- Invalid reference keys where applicable.

Use a fixed random seed. Provide a configurable generator capable of producing at least 100,000 records. Keep expected results separate from input data.

## 4. Canonical data model

Define and document:
- Canonical products.
- Supplier product-code mappings.
- Source record lineage.
- Quarantined records.
- Pipeline run history.
- Relevant product change history.

Use snake_case, deterministic IDs, explicit data types, UTC ISO-8601 timestamps, run_id, source_file, and source record identifiers.

Do not merge products based solely on fuzzy name matching. Use explicit supplier mappings or a documented deterministic matching strategy. Do not silently merge uncertain matches.

## 5. Pipeline

Implement modular, readable functions for:
- Input discovery and ingestion.
- File and schema validation.
- Required-field and business-rule validation.
- Canonical attribute normalization.
- Supplier code mapping.
- Duplicate detection.
- Deterministic conflict resolution.
- Quarantine and rejection reasons.
- Transactional SQLite publishing.
- Source lineage and change history.
- Operational metrics and reconciliation.

Every rejected record must retain enough source information to investigate it.

Document the conflict-resolution policy. Include deterministic tie-breakers and tests. Preserve conflicting source values rather than losing auditability.

## 6. Idempotency and recovery

Running the same input twice must not create duplicate products, duplicate source events, or duplicate history entries.

Use stable source-record fingerprints or explicit event identifiers. Distinguish source-record deduplication from matching products across suppliers.

Use database transactions and appropriate uniqueness constraints. Ensure failures roll back incomplete publishing. Record failed runs where possible. Document retry, restart, and backfill behavior.

Do not claim full recovery guarantees unless implemented and tested.

## 7. Observability

Every run should record:
- run_id
- start and finish timestamps
- status
- input record count
- accepted record count
- rejected record count
- duplicate count
- inserted, updated, and unchanged counts
- published product count
- duration
- error details, if any

Provide structured JSON logs and a machine-readable run report.

Reconciliation must explain the relationship between input, accepted, rejected, deduplicated, and published records.

## 8. Tests

Write automated pytest tests for:
- Happy path.
- Empty batch.
- Malformed CSV and JSON.
- Missing required fields and nulls.
- Duplicate source keys and repeated inputs.
- Unexpected schema changes.
- Invalid prices, including zero, negative, nonnumeric, and non-finite values.
- Invalid reference mappings.
- Conflicting supplier prices.
- Late-arriving updates.
- Partial publishing failure and transaction rollback.
- Re-running the same input.
- Reproducible synthetic data generation.

Use temporary directories and temporary databases for tests. Never rely on the developer's existing production data.

## 9. Performance

Provide a benchmark script that generates and processes 100,000 or more records. Measure actual elapsed time and report actual counts and throughput.

Do not invent benchmark numbers. Identify one reasonable optimization and explain its trade-offs.

## 10. Documentation

Create:
- README.md with clean installation and execution instructions.
- docs/architecture.md with an architecture diagram in Mermaid.
- docs/data_dictionary.md with schemas, keys, constraints, and relationships.
- docs/design_decisions.md with assumptions, trade-offs, limitations, and next steps.
- docs/ai_prompt_history.md to record prompts used and their purpose. Do not fabricate historical prompts or claim unperformed actions.
- A reproducible sample dataset and clearly labelled expected results.
- A .gitignore that excludes .venv, local databases, caches, and secrets.

Document all assumptions explicitly.

## 11. Commands and execution

Provide a clear CLI, for example:
- Generate sample data.
- Run the pipeline.
- Run tests.
- Run the benchmark.
- Inspect or export the reconciliation report.

Prefer commands that work from the project root.

## 12. Quality requirements

- Follow PEP 8.
- Use type hints where helpful.
- Keep functions focused and readable.
- Handle errors explicitly.
- Avoid unnecessary abstractions.
- Do not leave placeholder implementations, fake tests, TODO-only modules, or hardcoded successful results.
- Do not claim tests pass without executing them.
- Run the complete test suite and fix failures.
- Run the pipeline from a clean sample workspace.
- Verify the database contents and reconciliation outputs.
- Run the benchmark if the environment allows it.
- Report any unverified requirements or environment limitations honestly.

## 13. GitHub preparation

Inspect the Git status first. Never delete existing work.

Prepare the project for a dedicated public GitHub repository. If GitHub authentication and repository-creation permissions are available, ask for confirmation before creating a public repository or publishing anything. Never publish credentials, tokens, private information, or local databases containing unintended data.

Use meaningful commits. Do not fabricate commit history or claim a push succeeded without verifying it.

## Final response

When implementation is complete, summarize:
1. Files created.
2. Exact setup and execution commands.
3. Tests actually executed and their results.
4. Actual sample reconciliation results.
5. Actual benchmark results, if executed.
6. Known limitations.
7. GitHub publication steps or verified repository URL.
8. The important design choices I must understand for an interview.

Start by inspecting the workspace, then implement the project end to end.
```

## Prompt 2 — Final audit, verification, and publication (user message on 2026-10-28)

Purpose: audit the already implemented project, correct defects, clean publication scope, verify in a fresh environment, update assessment evidence, and publish the verified project publicly. The user's message specified these requirements: inspect the existing project and Git status/history/remotes; preserve code and history; audit data correctness, mappings, validation, traceability, SQLite transactions, rollback, idempotency, late records, metrics, reports, and reconciliation; safely ignore generated files and secrets; create a temporary environment and install declared dependencies; run the full tests, clean sample, repeat-input idempotency check, rollback check, documented CLI, and 100,000-record benchmark; update the README, architecture, data dictionary, design decisions, sample expectations, actual test and benchmark evidence, and prompt history; inspect the connected GitHub account and repository name without overwriting unrelated repositories; create or use the public `SupplierSync` repository only where authenticated permissions allow; review staged content, preserve history, push `main`, and verify visibility, URL, branch, commit, and files; report only evidence-backed results and any genuine authentication or permission blocker. The task explicitly said to perform the work directly, not stop at instructions or a checklist, and not claim publication or verification without evidence.

## Verbatim prompt 2 — Final audit, completion, verification, and public release

```text
# FINAL TASK: Audit, Complete, Verify, and Publish SupplierSync

You are my autonomous senior data engineering engineer and release manager. An existing SupplierSync project has already been implemented in this workspace. Your job is to finish the project properly and publish the verified result to a public GitHub repository.

I do NOT want instructions for me to execute manually. Perform the work directly in the workspace wherever your tools and permissions allow. Run commands, inspect files, modify code, execute tests, fix failures, and verify results.

Do not recreate the project from scratch. Preserve existing working code and Git history.

## PHASE 1: Inspect the current project

1. Confirm the workspace is the existing SupplierSync project.
2. Inspect README.md, pyproject.toml, .gitignore, source files, tests, sample data, expected results, documentation, benchmark script, reports, and Git history.
3. Run `git status --short --branch` and inspect `git ls-files`.
4. Inspect the existing commits and remote configuration.
5. Identify missing requirements, implementation defects, misleading documentation, unverified claims, and generated files that should not be published.
6. Create a private working checklist and execute it. Do not stop after producing a checklist.

## PHASE 2: Audit the implementation against the assessment

Check the actual implementation, not merely the README.

### Data correctness
- Multiple supplier schemas and file formats.
- Explicit, deterministic supplier-to-canonical product mappings.
- Correct normalization and data types.
- Deterministic conflict resolution and tie-breaking.
- Preservation of original source values.
- Stable canonical product IDs.
- Duplicate source record and cross-supplier product matching handled separately.
- Required fields, null values, malformed records, invalid prices, and invalid reference mappings.
- Unexpected schema changes handled according to a documented policy.
- Source-level traceability for accepted and rejected records.

### Persistence and recovery
- SQLite schema, keys, constraints, and indexes.
- Transactional publishing and rollback on partial failures.
- Idempotent reruns of the same inputs.
- Changed records and late-arriving records.
- Correct insert, update, unchanged, and rejection metrics.
- Run status and failure details recorded honestly.
- Retry, restart, and backfill behavior documented and tested.
- No duplicate history entries on repeated processing of unchanged inputs.

### Observability and reconciliation
- Unique run IDs.
- UTC ISO-8601 timestamps.
- Input, accepted, rejected, duplicate, inserted, updated, unchanged, and published counts.
- Machine-readable reports.
- Reconciliation assertions and useful error messages.
- Source filenames and record identifiers preserved.

Fix real defects where practical. If a requirement is unsupported, either implement it or explicitly document the limitation. Do not hide defects by weakening tests.

## PHASE 3: Clean the repository safely

The project archive may contain `.venv`, `__pycache__`, `.pytest_cache`, `__MACOSX`, local SQLite databases, and generated reports.

1. Inspect which files are tracked and which are untracked before removing anything.
2. Preserve source code, tests, documentation, reproducible synthetic input data, useful expected outputs, and the actual AI prompt history.
3. Ensure `.gitignore` excludes:
   - `.venv/`
   - `__pycache__/`
   - `.pytest_cache/`
   - `.DS_Store`
   - `__MACOSX/`
   - `*.py[cod]`
   - temporary files and logs
   - local working databases and SQLite sidecar files
   - generated benchmark artifacts
   - credentials, `.env` files, and secrets
4. Keep a small sample database or output file only if it is intentionally required as a documented assessment artifact. Do not publish accidental local working databases.
5. Remove generated artifacts from Git tracking where necessary without destroying the user's local work.
6. Do not delete or rewrite existing commits unnecessarily. Never use a destructive reset or force-push simply to make the repository look clean.
7. Review the complete list of files intended for publication before pushing.

## PHASE 4: Run verification from a clean environment

Use the project's declared dependencies and documented setup.

1. Create a fresh virtual environment in a temporary location if feasible.
2. Install the project and development dependencies from pyproject.toml.
3. Run the complete test suite.
4. Fix actual failures and rerun the complete suite.
5. Generate a fresh deterministic sample dataset using the documented seed.
6. Run the pipeline against a fresh temporary SQLite database.
7. Verify the actual database rows, keys, lineage, rejected records, run metrics, and reconciliation.
8. Run the identical input a second time and prove there are no unintended duplicate products, source events, or history entries.
9. Exercise transaction rollback and failure reporting where implemented.
10. Run the documented CLI commands from the README.
11. Run the 100,000-record benchmark if the environment allows it.
12. Record actual elapsed time, accepted records, rejected records, product count, and throughput.

Do not fabricate successful test results or benchmark measurements. Distinguish tests actually run from scenarios only inspected manually. Do not modify expected results just to make a broken implementation pass.

## PHASE 5: Improve documentation and assessment evidence

Ensure the repository includes:

- A clear README with project purpose, architecture, prerequisites, setup, sample execution, CLI usage, test commands, benchmark commands, and limitations.
- An architecture diagram.
- A complete data dictionary with keys, types, nullability, and relationships.
- A design and trade-off document.
- Synthetic sample inputs and separate expected results.
- Example output and reconciliation evidence.
- Actual test results.
- Actual benchmark results, if measured.
- A useful .gitignore.
- `docs/ai_prompt_history.md`.

The AI prompt history must contain the actual prompts used, including the project implementation prompt and this final audit/publishing prompt. Preserve any earlier prompts already recorded. Never invent historical prompts, claim to have used tools that were not used, or claim human work that did not happen.

Do not expose secrets or private personal information in the prompt history. Explain honestly where AI was used and which results were independently verified.

Update documentation to match the real implementation and measured results.

## PHASE 6: Prepare a professional public repository

Use the repository name `SupplierSync`.

The repository must be public because the assessment requires a public GitHub repository.

Before publishing:
1. Inspect the GitHub account and existing repository if a remote is already configured.
2. Never overwrite an unrelated repository.
3. If no suitable repository exists, create a dedicated public repository named SupplierSync using available authenticated GitHub tools or the GitHub CLI.
4. If repository creation or authentication requires interactive user action, stop only at that blocker and explain exactly what is required. Do not pretend to have published the project.
5. Do not create a README or initial commit remotely if it would cause an avoidable conflict with the existing local history.
6. Preserve existing commits and add meaningful commits for genuine fixes and cleanup.
7. Review staged files before committing. Never stage secrets, virtual environments, caches, or accidental local databases.
8. Push the intended branch, normally `main`.
9. If a push fails, diagnose the actual cause and retry safely without force-pushing.
10. Verify the remote URL, branch, latest commit, repository visibility, and availability of key files through authenticated GitHub tools or a public browser request if available.

The goal is to complete publication, not merely provide commands for me to copy.

## PHASE 7: Final release checklist

Before declaring completion, confirm:

- [ ] Clean setup works.
- [ ] All executed tests pass.
- [ ] Sample outputs are reproducible.
- [ ] Reconciliation is verified.
- [ ] Idempotency is tested.
- [ ] Failure handling and limitations are documented.
- [ ] Benchmark claims are backed by actual measurements.
- [ ] AI prompt history is accurate and complete for the prompts available.
- [ ] No secrets or unintended generated artifacts are tracked.
- [ ] Git history is preserved.
- [ ] The public GitHub repository exists and contains the latest verified code.
- [ ] The repository link is verified.

## FINAL RESPONSE

Report:
1. The actual public GitHub URL, if successfully published.
2. The exact test command and observed result.
3. Sample input, acceptance, rejection, product, and reconciliation counts.
4. Actual benchmark results, if executed.
5. Important code changes and files cleaned up.
6. Any unresolved limitations.
7. Any action genuinely blocked by authentication or permissions.

Do not claim success without evidence. Do not stop after writing a plan. Start by inspecting the existing workspace and carry the task through to verified publication wherever possible.
```

## Prompt 3 — Streamlit dashboard, documentation, verification, and publication (provided as a pasted text attachment on 2026-10-29)

Purpose: extend the existing repository with an optional Streamlit dashboard, rewrite the README for first-time setup and evaluation, add dashboard data/query tests, verify the app and CLI sample workflow, accurately update prompt history, and publish a reviewed commit to the existing public Rupali repository. The actual request required preserving the pipeline, schema, CLI, tests, Git history, and user data; inspecting files and Git state before edits; using a dedicated ignored dashboard database and safe non-overwriting sample generation; invoking the existing CLI rather than duplicating business logic; using read-only, parameterized dashboard queries; providing overview/reconciliation, product search/filter/export, quarantine, lineage, run history, and JSON/CSV downloads; documenting installation, Windows/macOS/Linux commands, limitations, local-only security posture, and troubleshooting; testing empty/missing/malformed/valid data and run success/failure without weakening coverage; staging only reviewed files; never force-pushing or publishing secrets; and verifying the GitHub result if authentication permitted. The prompt also prohibited fabricated tests, benchmark results, screenshots, and deployment URLs. This is an accurate summary of the attached prompt, not a claim that unexecuted actions have been performed.

## Prompt 4 — Browser-based supplier file uploads (provided as a pasted text attachment on 2026-10-29)

Purpose: modify the existing SupplierSync Streamlit dashboard to accept the real `supplier_a.csv`, `supplier_b.json`, and `product_mappings.json` files, validate their exact supported formats before the user can run, preview file sizes and records, and stage each batch in a unique ignored project-local directory matching the existing CLI's input/reference layout. The attached prompt required preserving the existing pipeline and functionality, keeping uploads local, enforcing size/path safety, retaining the separately labelled sample generator, exercising invalid and successful upload behavior with temporary paths and AppTest, running pytest and Ruff, updating README and verification evidence honestly, reviewing Git changes without disturbing the pre-existing `reports/latest.json` modification, and committing/pushing normally to Rupali's public `main` branch without force-pushing. The actual prompt also asked for final user steps to launch the dashboard and upload/process supplier files. This summary records the content of the attachment; it does not imply any action not yet verified.
