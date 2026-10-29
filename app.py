"""Local Streamlit interface for inspecting and running SupplierSync."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

from suppliersync.dashboard_data import (
    DEMO_DB,
    DEMO_REPORT,
    DEMO_ROOT,
    PROJECT_ROOT,
    csv_bytes,
    database_status,
    generate_demo_inputs,
    get_lineage,
    get_products,
    get_quarantine,
    get_runs,
    product_count,
    reconciliation,
    report_for_run,
    run_pipeline_cli,
    validate_database_path,
    validate_project_directory,
)

st.set_page_config(
    page_title="SupplierSync — Supplier Data Intelligence", layout="wide"
)
RUN_LOCK = threading.Lock()
NAVIGATION = ("Overview", "Products", "Data quality", "Source lineage", "Run history")


def _default_state() -> None:
    st.session_state.setdefault("db_path", str(DEMO_DB))
    st.session_state.setdefault("input_dir", str(PROJECT_ROOT / "data" / "input"))
    st.session_state.setdefault("db_path_widget", str(DEMO_DB))
    st.session_state.setdefault(
        "input_dir_widget", str(PROJECT_ROOT / "data" / "input")
    )
    st.session_state.setdefault("pipeline_result", None)


def _pretty_frame(rows: list[dict[str, Any]]) -> None:
    if rows:
        st.dataframe(rows, width="stretch", hide_index=True)
    else:
        st.info("No records match this view yet.")


def _database_status(db_path: str) -> tuple[bool, str]:
    try:
        safe_path = validate_database_path(db_path)
    except ValueError as exc:
        return False, str(exc)
    return database_status(safe_path)


def _show_metrics(run: dict[str, Any], products: int) -> None:
    values = reconciliation(run)
    st.caption(
        "Run counts reconcile input rows to accepted, rejected, duplicate, or unprocessed outcomes."
    )
    columns = st.columns(5)
    metrics = (
        ("Input records", "input_count"),
        ("Accepted", "accepted_count"),
        ("Rejected", "rejected_count"),
        ("Duplicates", "duplicate_count"),
        ("Unprocessed", "unprocessed_count"),
    )
    for col, (label, key) in zip(columns, metrics):
        col.metric(label, values[key])
    columns = st.columns(5)
    for col, (label, key) in zip(
        columns,
        (
            ("Inserted", "inserted_count"),
            ("Updated", "updated_count"),
            ("Unchanged", "unchanged_count"),
            ("Published products", "published_count"),
            ("Current products", None),
        ),
    ):
        col.metric(label, products if key is None else values[key])
    if values["balanced"]:
        st.success(
            "Reconciliation balanced: input = accepted + rejected + duplicates + unprocessed."
        )
    else:
        st.error(
            "Reconciliation does not balance: "
            f"{values['input_count']} input vs "
            f"{values['accepted_count']} accepted + {values['rejected_count']} rejected + "
            f"{values['duplicate_count']} duplicates + {values['unprocessed_count']} unprocessed."
        )


def _run_sidebar() -> None:
    st.sidebar.header("Workspace")
    st.sidebar.caption("Dashboard writes use a separate demo database by default.")
    if st.sidebar.button(
        "Generate fresh deterministic sample",
        help="Creates a new timestamped folder and leaves existing files untouched.",
    ):
        try:
            input_dir, stats = generate_demo_inputs(DEMO_ROOT / "samples")
            st.session_state.input_dir = str(input_dir)
            st.session_state.input_dir_widget = str(input_dir)
            st.session_state.generated_sample = stats
        except (OSError, ValueError) as exc:
            st.sidebar.error(f"Sample generation failed: {exc}")
    if st.session_state.get("generated_sample"):
        stats = st.session_state.generated_sample
        st.sidebar.caption(
            f"Latest generated sample: {stats['input_records']} rows · seed 1729"
        )

    st.session_state.db_path = st.sidebar.text_input(
        "Demo database path", st.session_state.db_path, key="db_path_widget"
    )
    st.session_state.input_dir = st.sidebar.text_input(
        "Input directory", st.session_state.input_dir, key="input_dir_widget"
    )
    ok, message = _database_status(st.session_state.db_path)
    if ok:
        st.sidebar.success(message)
    else:
        st.sidebar.caption(message)
    st.sidebar.caption(f"Demo report: `{DEMO_REPORT.relative_to(PROJECT_ROOT)}`")

    st.sidebar.divider()
    if st.sidebar.button("Run Pipeline", type="primary", use_container_width=True):
        if RUN_LOCK.locked():
            st.sidebar.warning(
                "A pipeline run is already in progress in this app process."
            )
        else:
            try:
                input_path = validate_project_directory(st.session_state.input_dir)
                database_path = validate_database_path(st.session_state.db_path)
                with (
                    RUN_LOCK,
                    st.status(
                        "Running the existing SupplierSync CLI…", expanded=True
                    ) as status,
                ):
                    result = run_pipeline_cli(input_path, database_path, DEMO_REPORT)
                    st.session_state.pipeline_result = result
                    if result["status"] == "succeeded":
                        status.update(
                            label="Pipeline completed successfully", state="complete"
                        )
                    else:
                        status.update(label="Pipeline failed", state="error")
            except (OSError, ValueError) as exc:
                st.sidebar.error(f"Run was not started: {exc}")
    st.sidebar.caption(
        "Runs happen only when you press the button. Existing `data/suppliersync.db` is never selected by default."
    )


def _overview(db_path: str) -> None:
    st.subheader("Pipeline overview")
    if not Path(db_path).expanduser().exists():
        st.info(
            "No pipeline run is recorded in this demo database. Generate sample inputs, choose the input folder, then select **Run Pipeline**."
        )
        st.metric("Current canonical products", 0)
        return
    try:
        runs = get_runs(db_path, limit=1)
        current_products = product_count(db_path)
    except (OSError, ValueError) as exc:
        st.error(f"Could not read the dashboard database: {exc}")
        return
    except sqlite3.Error as exc:  # sqlite can report corrupt or locked files here.
        st.error(f"Could not read the dashboard database: {exc}")
        return
    if not runs:
        st.info(
            "No pipeline run is recorded in this demo database. Generate sample inputs, choose the input folder, then select **Run Pipeline**."
        )
        st.metric("Current canonical products", current_products)
        return
    run = runs[0]
    if run["status"] == "succeeded":
        st.success("Most recent run succeeded")
    else:
        st.error(
            f"Most recent run {run['status']}: {run.get('error') or 'No error detail was recorded.'}"
        )
    st.caption(
        f"Run `{run['run_id']}` · started {run['started_at']} · "
        f"finished {run.get('finished_at') or 'in progress'} · "
        f"duration {run.get('duration_seconds') or 0:.3f}s"
    )
    _show_metrics(run, current_products)
    st.caption(
        "Published product count is the distinct current canonical product total, not the number of accepted source records."
    )
    st.subheader("Recent run history")
    recent_runs = get_runs(db_path, limit=10)
    _pretty_frame(
        [
            {**item, "reconciliation_balanced": reconciliation(item)["balanced"]}
            for item in recent_runs
        ]
    )
    result = st.session_state.get("pipeline_result")
    if result:
        with st.expander("Most recent dashboard execution details"):
            st.write(
                f"Exit status: `{result.get('exit_status')}` · elapsed {result.get('duration_seconds', 0):.3f}s"
            )
            if result.get("report"):
                st.json(result["report"])
            if result.get("stdout"):
                st.text_area("CLI stdout", result["stdout"], height=120)
            if result.get("stderr"):
                st.text_area("CLI stderr", result["stderr"], height=100)
            if result.get("report_error"):
                st.error(result["report_error"])


def _products(db_path: str) -> None:
    st.subheader("Canonical product explorer")
    try:
        all_products = get_products(db_path)
    except (OSError, ValueError, sqlite3.Error) as exc:
        st.error(f"Products are unavailable: {exc}")
        return
    if not all_products:
        st.info(
            "No canonical products have been published yet. Run the pipeline to populate this view."
        )
        return
    left, categories_col, suppliers_col = st.columns([2, 1, 1])
    search = left.text_input("Search product name or ID", key="product_search")
    categories = categories_col.multiselect(
        "Category", sorted({row["category"] for row in all_products})
    )
    suppliers = suppliers_col.multiselect(
        "Winning supplier", sorted({row["winning_source"] for row in all_products})
    )
    rows = get_products(db_path, search, categories, suppliers)
    display = [
        {
            **row,
            "price": f"{row['price']:.2f} {row['currency']}",
            "updated_at": datetime.fromisoformat(row["updated_at"]).strftime(
                "%Y-%m-%d %H:%M UTC"
            ),
        }
        for row in rows
    ]
    _pretty_frame(display)
    st.download_button(
        "Download selected products CSV",
        csv_bytes(rows),
        "suppliersync_products.csv",
        "text/csv",
        disabled=not rows,
    )
    st.caption(
        f"Showing {len(rows)} of {len(all_products)} distinct canonical products."
    )


def _data_quality(db_path: str) -> None:
    st.subheader("Quarantine and data quality")
    st.caption(
        "These source rows were rejected and were not published as canonical products. Their stored raw payload is retained for investigation."
    )
    try:
        all_rows = get_quarantine(db_path)
    except (OSError, ValueError, sqlite3.Error) as exc:
        st.error(f"Quarantine records are unavailable: {exc}")
        return
    if not all_rows:
        st.info("No quarantined records are present in this database.")
        return
    col1, col2 = st.columns(2)
    suppliers = col1.multiselect("Supplier", sorted({r["supplier"] for r in all_rows}))
    reasons = col2.multiselect(
        "Rejection reason", sorted({r["reason"] for r in all_rows})
    )
    rows = get_quarantine(db_path, suppliers, reasons)
    if not rows:
        st.info("No quarantined records match the selected filters.")
        return
    visible = [{**row, "raw_json": row["raw_json"]} for row in rows]
    _pretty_frame(visible)
    st.download_button(
        "Download selected quarantine CSV",
        csv_bytes(rows),
        "suppliersync_quarantine.csv",
        "text/csv",
        disabled=not rows,
    )
    selected = st.selectbox(
        "Inspect raw source evidence",
        range(len(rows)),
        format_func=lambda i: (
            f"{rows[i]['supplier']} · {rows[i]['source_file']} · {rows[i]['source_record_id']} · {rows[i]['reason']}"
        ),
    )
    try:
        st.json(json.loads(rows[selected]["raw_json"]))
    except json.JSONDecodeError:
        st.text(rows[selected]["raw_json"])


def _lineage(db_path: str) -> None:
    st.subheader("Source lineage")
    try:
        products = get_products(db_path)
    except (OSError, ValueError, sqlite3.Error) as exc:
        st.error(f"Lineage is unavailable: {exc}")
        return
    if not products:
        st.info("Publish products first to inspect their source lineage.")
        return
    selected_id = st.selectbox(
        "Canonical product",
        [p["product_id"] for p in products],
        format_func=lambda value: next(
            f"{p['name']} · {value}" for p in products if p["product_id"] == value
        ),
    )
    try:
        lineage = get_lineage(db_path, selected_id)
    except (OSError, ValueError, sqlite3.Error) as exc:
        st.error(f"Could not load lineage: {exc}")
        return
    st.caption(
        "Winner status is derived from the current canonical winning supplier and source record. Earlier winning states are not stored on events."
    )
    st.markdown("**Accepted source events**")
    _pretty_frame(lineage["events"])
    for event in lineage["events"]:
        with st.expander(
            f"{event['supplier']} · {event['source_file']} · {event['source_record_id']} · {event['winner_status']}"
        ):
            st.write(
                f"Source timestamp: {event['source_updated_at']} · Run: `{event['run_id']}`"
            )
            st.json({"original": event["raw"], "normalized": event["normalized"]})
    st.markdown("**Canonical product history**")
    _pretty_frame(lineage["history"])


def _run_history(db_path: str) -> None:
    st.subheader("Persisted run history")
    try:
        runs = get_runs(db_path)
    except (OSError, ValueError, sqlite3.Error) as exc:
        st.error(f"Run history is unavailable: {exc}")
        return
    if not runs:
        st.info("No run history is available yet.")
        return
    _pretty_frame(
        [
            {**item, "reconciliation_balanced": reconciliation(item)["balanced"]}
            for item in runs
        ]
    )
    ids = [run["run_id"] for run in runs]
    run_status = {run["run_id"]: run["status"] for run in runs}
    selected = st.selectbox(
        "Run details",
        ids,
        format_func=lambda run_id: f"{run_id} · {run_status[run_id]}",
    )
    run = next(row for row in runs if row["run_id"] == selected)
    values = reconciliation(run)
    with st.expander("Selected run reconciliation", expanded=True):
        st.json(values)
        st.code(
            "input_count = accepted_count + rejected_count + duplicate_count + unprocessed_count"
        )
    try:
        report = report_for_run(db_path, selected, DEMO_REPORT)
        st.caption(f"JSON source: {report['report_source']}")
        st.download_button(
            "Download selected run JSON",
            json.dumps(report, indent=2, sort_keys=True),
            f"suppliersync_run_{selected}.json",
            "application/json",
        )
        with st.expander("Run report contents"):
            st.json(report)
    except (OSError, ValueError, KeyError) as exc:
        st.error(f"The selected run report could not be prepared: {exc}")
    st.caption(
        "When the original CLI JSON is not for this run, the download is reconstructed from the persisted pipeline_runs row and labelled accordingly."
    )


def main() -> None:
    _default_state()
    st.title("SupplierSync — Supplier Data Intelligence")
    st.write("Normalize, validate, reconcile, and publish multi-supplier product data.")
    _run_sidebar()
    page = st.sidebar.radio("Dashboard", NAVIGATION, label_visibility="visible")
    db_path = st.session_state.db_path
    ok, message = _database_status(db_path)
    if not ok and Path(db_path).exists():
        st.error(message)
        return
    if page == "Overview":
        _overview(db_path)
    elif page == "Products":
        _products(db_path)
    elif page == "Data quality":
        _data_quality(db_path)
    elif page == "Source lineage":
        _lineage(db_path)
    else:
        _run_history(db_path)
    st.divider()
    st.caption(
        "Local assessment demo · not authenticated or hardened for untrusted public access."
    )


if __name__ == "__main__":
    main()
