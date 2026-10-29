import json
from pathlib import Path

import pytest

from suppliersync import dashboard_data as dashboard
from suppliersync.generate import generate
from suppliersync.pipeline import connect, run_pipeline


def _sample(tmp_path):
    inputs = tmp_path / "data" / "input"
    stats = generate(inputs, records=8, seed=1729)
    db_path = tmp_path / "demo.sqlite"
    report = run_pipeline(inputs, db_path)
    return inputs, db_path, report, stats


def test_missing_and_incomplete_databases_are_reported_without_mutation(tmp_path):
    missing = tmp_path / "missing.sqlite"
    assert dashboard.database_status(missing)[0] is False
    assert not missing.exists()
    incomplete = tmp_path / "incomplete.sqlite"
    import sqlite3

    with sqlite3.connect(incomplete) as db:
        db.execute("CREATE TABLE unrelated(value TEXT)")
    assert dashboard.database_status(incomplete)[0] is False
    with sqlite3.connect(incomplete) as db:
        assert db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall() == [("unrelated",)]


def test_configured_dashboard_database_must_stay_in_project_and_be_separate(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(dashboard, "PROJECT_ROOT", tmp_path.resolve())
    assert (
        dashboard.validate_database_path(tmp_path / ".demo" / "db.sqlite")
        == (tmp_path / ".demo" / "db.sqlite").resolve()
    )
    with pytest.raises(ValueError, match="inside the project"):
        dashboard.validate_database_path(tmp_path.parent / "unrelated.sqlite")
    with pytest.raises(ValueError, match="may not use"):
        dashboard.validate_database_path(tmp_path / "data" / "suppliersync.db")


def test_products_are_filtered_and_user_values_are_parameterized(tmp_path):
    _, db_path, _, _ = _sample(tmp_path)
    products = dashboard.get_products(db_path)
    assert len(products) == 2
    assert dashboard.get_products(db_path, search=products[0]["product_id"])
    assert dashboard.get_products(db_path, categories=[products[0]["category"]])
    assert dashboard.get_products(db_path, suppliers=[products[0]["winning_source"]])
    assert dashboard.get_products(db_path, search="%' OR 1=1 --") == []


def test_quarantine_filtering_lineage_and_reconciliation(tmp_path):
    _, db_path, report, _ = _sample(tmp_path)
    assert dashboard.reconciliation(report)["balanced"] is True
    quarantine = dashboard.get_quarantine(db_path)
    assert len(quarantine) == report["rejected_count"]
    assert dashboard.get_quarantine(db_path, suppliers=[quarantine[0]["supplier"]])
    assert dashboard.get_quarantine(db_path, reasons=[quarantine[0]["reason"]])
    product = dashboard.get_products(db_path)[0]
    lineage = dashboard.get_lineage(db_path, product["product_id"])
    assert lineage["events"]
    assert (
        sum(row["winner_status"] == "Current winner" for row in lineage["events"]) == 1
    )


def test_csv_and_json_report_helpers(tmp_path):
    _, db_path, report, _ = _sample(tmp_path)
    rows = dashboard.get_products(db_path)
    assert dashboard.csv_bytes(rows).startswith(b"product_id,name,")
    assert dashboard.csv_bytes([]) == b""
    generated_report = tmp_path / "report.json"
    generated_report.write_text(json.dumps(report), encoding="utf-8")
    assert (
        dashboard.report_for_run(db_path, report["run_id"], generated_report)[
            "report_source"
        ]
        == "original CLI report"
    )
    reconstructed = dashboard.report_for_run(db_path, report["run_id"])
    assert reconstructed["report_source"].startswith("reconstructed")


def test_malformed_report_is_an_explicit_error(tmp_path):
    _, db_path, report, _ = _sample(tmp_path)
    broken = tmp_path / "broken.json"
    broken.write_text("{bad json", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot be read"):
        dashboard.report_for_run(db_path, report["run_id"], broken)


def test_pipeline_wrapper_uses_separate_database_and_captures_failure(
    tmp_path, monkeypatch
):
    inputs, _, _, _ = _sample(tmp_path)
    monkeypatch.setattr(dashboard, "PROJECT_ROOT", tmp_path.resolve())
    result = dashboard.run_pipeline_cli(
        inputs, tmp_path / ".demo" / "dashboard.sqlite", tmp_path / ".demo" / "run.json"
    )
    assert result["status"] == "succeeded"
    assert result["exit_status"] == 0
    assert result["report"]["input_count"] == 16
    assert result["report"]["duplicate_count"] == 0
    replay = dashboard.run_pipeline_cli(
        inputs,
        tmp_path / ".demo" / "dashboard.sqlite",
        tmp_path / ".demo" / "replay.json",
    )
    assert replay["report"]["duplicate_count"] == 16
    assert (tmp_path / ".demo" / "dashboard.sqlite").is_file()
    with pytest.raises(ValueError, match="may not use"):
        dashboard.run_pipeline_cli(
            inputs,
            tmp_path / "data" / "suppliersync.db",
            tmp_path / ".demo" / "other.json",
        )


def test_pipeline_wrapper_reports_failed_cli_run(tmp_path, monkeypatch):
    inputs, _, _, _ = _sample(tmp_path)
    (tmp_path / "data" / "reference" / "product_mappings.json").write_text(
        "[]", encoding="utf-8"
    )
    monkeypatch.setattr(dashboard, "PROJECT_ROOT", tmp_path.resolve())
    result = dashboard.run_pipeline_cli(
        inputs, tmp_path / ".demo" / "failed.sqlite", tmp_path / ".demo" / "failed.json"
    )
    assert result["status"] == "failed"
    assert result["exit_status"] == 1
    assert result["report"]["status"] == "failed"
    assert "must be an object" in result["report"]["error"]


def test_empty_database_is_a_valid_read_state(tmp_path):
    db_path = tmp_path / "empty.sqlite"
    with connect(db_path):
        pass
    assert dashboard.database_status(db_path)[0] is True
    assert dashboard.get_runs(db_path) == []
    assert dashboard.get_products(db_path) == []


def test_safe_sample_generation_uses_new_directory_each_time(tmp_path):
    first, _ = dashboard.generate_demo_inputs(tmp_path / "samples", records=4)
    first_content = (first / "supplier_a.csv").read_bytes()
    second, _ = dashboard.generate_demo_inputs(tmp_path / "samples", records=4)
    assert first != second
    assert (first / "supplier_a.csv").read_bytes() == first_content
    assert (second / "supplier_a.csv").is_file()


def _valid_uploads():
    return {
        "supplier_a": (
            "supplier_a.csv",
            b"sku,name,category,price,currency,updated_at\nA-1,Widget,electronics,12.50,USD,2026-01-01T00:00:00Z\n",
        ),
        "supplier_b": (
            "supplier_b.json",
            b'[{"item_code":"B-1","title":"Widget","department":"electronics","amount":12.5,"currency":"USD","updated_at":"2026-01-01T00:00:00Z"}]',
        ),
        "mappings": (
            "product_mappings.json",
            b'{"supplier_a:A-1":"widget-1","supplier_b:B-1":"widget-1"}',
        ),
    }


def test_upload_validation_and_safe_staging_feed_existing_pipeline(
    tmp_path, monkeypatch
):
    uploads = _valid_uploads()
    result = dashboard.validate_upload_batch(uploads)
    assert result["valid"] is True
    assert result["row_counts"] == {"supplier_a": 1, "supplier_b": 1}

    project_root = tmp_path.resolve()
    monkeypatch.setattr(dashboard, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(dashboard, "DEMO_ROOT", project_root / ".demo")
    batch_id, inputs = dashboard.stage_upload_batch(uploads)
    batch_root = inputs.parent
    assert len(batch_id) == 32
    assert (inputs / "supplier_a.csv").read_bytes() == uploads["supplier_a"][1]
    assert (inputs / "supplier_b.json").read_bytes() == uploads["supplier_b"][1]
    assert (batch_root / "reference" / "product_mappings.json").read_bytes() == uploads[
        "mappings"
    ][1]

    output = tmp_path / ".demo" / "run.json"
    run = dashboard.run_pipeline_cli(inputs, tmp_path / ".demo" / "run.sqlite", output)
    assert run["status"] == "succeeded"
    assert run["report"]["input_count"] == 2
    assert run["report"]["accepted_count"] == 2
    assert run["report"]["rejected_count"] == 0
    assert run["report"]["published_count"] == 1
    assert dashboard.reconciliation(run["report"])["balanced"] is True
    assert (
        len(
            dashboard.get_lineage(tmp_path / ".demo" / "run.sqlite", "widget-1")[
                "events"
            ]
        )
        == 2
    )


@pytest.mark.parametrize(
    ("role", "filename", "content", "message"),
    [
        ("supplier_a", "../supplier_a.csv", b"x", "unsafe filename"),
        ("supplier_a", "supplier_a.csv", b"\xff", "valid UTF-8"),
        (
            "supplier_a",
            "supplier_a.csv",
            b"sku,name\nA-1,Widget\n",
            "missing required columns",
        ),
        (
            "supplier_a",
            "supplier_a.csv",
            b'sku,name,category,price,currency,updated_at\nA-1,"broken,electronics,1,USD,2026-01-01\n',
            "malformed CSV",
        ),
        ("supplier_a", "supplier_a.csv", b"", "is empty"),
        ("supplier_b", "supplier_b.json", b"{bad", "invalid JSON"),
        ("mappings", "product_mappings.json", b"[]", "must contain a JSON object"),
    ],
)
def test_upload_validation_rejects_malformed_or_unsafe_files(
    role, filename, content, message
):
    uploads = _valid_uploads()
    uploads[role] = (filename, content)
    assert dashboard.validate_upload_batch(uploads)["valid"] is False
    assert any(
        message in error for error in dashboard.validate_upload_batch(uploads)["errors"]
    )


def test_upload_validation_requires_all_files_and_enforces_size():
    assert not dashboard.validate_upload_batch({})["valid"]
    uploads = _valid_uploads()
    uploads["supplier_a"] = ("supplier_a.csv", b"x" * 11)
    result = dashboard.validate_upload_batch(uploads, max_upload_bytes=10)
    assert not result["valid"]
    assert any("larger than" in message for message in result["errors"])


def test_upload_staging_rejects_path_outside_project(tmp_path):
    with pytest.raises(ValueError, match="inside the SupplierSync project"):
        dashboard.stage_upload_batch(
            _valid_uploads(),
            demo_root=tmp_path / "outside",
            project_root=tmp_path / "project",
        )


def test_streamlit_upload_page_stages_and_runs_selected_batch(tmp_path, monkeypatch):
    streamlit = pytest.importorskip("streamlit.testing.v1")
    source_root = dashboard.PROJECT_ROOT
    demo_root = tmp_path.resolve() / ".demo"
    monkeypatch.setattr(dashboard, "PROJECT_ROOT", tmp_path.resolve())
    monkeypatch.setattr(dashboard, "DEMO_ROOT", demo_root)
    monkeypatch.setattr(dashboard, "DEMO_DB", demo_root / "dashboard.sqlite")
    monkeypatch.setattr(dashboard, "DEMO_REPORT", demo_root / "report.json")

    app = streamlit.AppTest.from_file(str(source_root / "app.py"))
    app.session_state["db_path_widget"] = str(dashboard.DEMO_DB)
    app.run()
    app.radio[0].set_value("Upload supplier data").run()
    assert next(
        button for button in app.button if button.label == "Run Pipeline"
    ).disabled

    mime_types = ("text/csv", "application/json", "application/json")
    for index, (filename, content) in enumerate(_valid_uploads().values()):
        app.file_uploader[index].set_value((filename, content, mime_types[index])).run()

    assert not app.exception
    assert not app.error
    next(
        button
        for button in app.button
        if button.label == "Stage and select this upload batch"
    ).click().run()
    assert not app.exception
    assert app.session_state["selected_batch_id"]
    assert Path(app.session_state["input_dir_widget"]).is_dir()
    next(
        button for button in app.button if button.label == "Run Pipeline"
    ).click().run()
    assert not app.exception
    assert app.session_state["pipeline_result"]["status"] == "succeeded"
    assert dashboard.get_runs(dashboard.DEMO_DB)[0]["input_count"] == 2


def test_streamlit_page_starts_and_plain_rerun_does_not_run_pipeline():
    streamlit = pytest.importorskip("streamlit.testing.v1")
    app = streamlit.AppTest.from_file(str(dashboard.PROJECT_ROOT / "app.py"))
    app.session_state["db_path_widget"] = str(
        dashboard.PROJECT_ROOT / ".suppliersync_test_empty" / "empty.sqlite"
    )
    app.run()
    assert not app.exception
    assert any(
        item.value == "SupplierSync — Supplier Data Intelligence" for item in app.title
    )
    assert any("No pipeline run is recorded" in item.value for item in app.info)
    assert app.session_state["pipeline_result"] is None
    app.run()
    assert app.session_state["pipeline_result"] is None


def test_streamlit_run_button_executes_once_against_configured_demo_database(
    tmp_path, monkeypatch
):
    streamlit = pytest.importorskip("streamlit.testing.v1")
    source_root = dashboard.PROJECT_ROOT
    demo_root = tmp_path.resolve()
    monkeypatch.setattr(dashboard, "PROJECT_ROOT", demo_root)
    monkeypatch.setattr(dashboard, "DEMO_ROOT", demo_root / ".demo")
    monkeypatch.setattr(dashboard, "DEMO_DB", demo_root / ".demo" / "dashboard.sqlite")
    monkeypatch.setattr(dashboard, "DEMO_REPORT", demo_root / ".demo" / "report.json")
    app = streamlit.AppTest.from_file(str(source_root / "app.py"))
    app.session_state["db_path_widget"] = str(dashboard.DEMO_DB)
    app.run()
    next(
        button
        for button in app.button
        if button.label == "Generate fresh deterministic sample"
    ).click().run()
    assert ".demo/samples/sample-" in app.session_state["input_dir_widget"]
    next(
        button for button in app.button if button.label == "Run Pipeline"
    ).click().run()
    assert not app.exception
    assert app.session_state["pipeline_result"]["status"] == "succeeded"
    assert dashboard.get_runs(dashboard.DEMO_DB)[0]["input_count"] == 48
    app.run()
    assert len(dashboard.get_runs(dashboard.DEMO_DB)) == 1
