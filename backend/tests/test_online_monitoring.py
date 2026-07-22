from datetime import datetime, timezone
from types import SimpleNamespace

import duckdb
import pytest

from app.modules.serving.domain import MonitoringRunStatus, OnlineMonitoringRun
from app.modules.serving.monitoring import OnlineMonitoringService
from app.modules.serving.schemas import OnlineMonitoringRunCreate


def monitoring_run(**overrides) -> OnlineMonitoringRun:
    values = {
        "id": "monitoring-1",
        "deployment_id": "deployment-1",
        "business_case_id": "bc-1",
        "owner_id": "owner-1",
        "requested_by": "user-1",
        "status": MonitoringRunStatus.RUNNING,
        "since": datetime(2026, 7, 1, tzinfo=timezone.utc),
        "until": datetime(2026, 7, 2, tzinfo=timezone.utc),
        "source_before": datetime(2026, 7, 3, tzinfo=timezone.utc),
        "actuals_dataset_id": "actuals-1",
        "actuals_artifact_id": "artifact-1",
        "actuals_target_column": "outcome",
        "actuals_record_id_column": "record_id",
    }
    values.update(overrides)
    return OnlineMonitoringRun(**values)


def service_without_external_repositories() -> OnlineMonitoringService:
    return object.__new__(OnlineMonitoringService)


def test_monitoring_request_allows_an_operational_run_without_actuals() -> None:
    payload = OnlineMonitoringRunCreate(
        since=datetime(2026, 7, 1, tzinfo=timezone.utc),
        until=datetime(2026, 7, 2, tzinfo=timezone.utc),
    )

    assert payload.actuals_dataset_id == ""


def test_hourly_aggregation_returns_one_row_per_calendar_hour_including_empty_hours() -> None:
    connection = duckdb.connect(":memory:")
    connection.execute(
        "CREATE TABLE snapshot(request_id VARCHAR, scored_at TIMESTAMPTZ, "
        "request_status VARCHAR, fallback_used BOOLEAN, request_latency_ms INTEGER, "
        "served BOOLEAN)"
    )
    connection.execute(
        "INSERT INTO snapshot VALUES "
        "('request-1', '2026-07-01T00:30:00Z', 'succeeded', false, 100, true), "
        "('request-1', '2026-07-01T00:30:00Z', 'succeeded', false, 100, false), "
        "('request-2', '2026-07-01T02:15:00Z', 'failed', true, 300, false)"
    )
    run = monitoring_run(
        since=datetime(2026, 7, 1, 0, 15, tzinfo=timezone.utc),
        until=datetime(2026, 7, 1, 3, 0, tzinfo=timezone.utc),
        aggregation_granularity="hour",
    )

    result = service_without_external_repositories()._time_aggregation(
        connection, "snapshot", run
    )

    assert result["bucket_count"] == 3
    assert result["buckets"][0]["label"] == "2026-07-01 00:00–00:59"
    assert result["buckets"][0]["request_count"] == 1
    assert result["buckets"][0]["execution_count"] == 2
    assert result["buckets"][1]["request_count"] == 0
    assert result["buckets"][2]["failed_request_count"] == 1


def test_auto_join_prefers_prediction_id_and_returns_actual_for_served_record() -> None:
    connection = duckdb.connect(":memory:")
    connection.execute(
        "CREATE TABLE snapshot(prediction_id VARCHAR, request_id VARCHAR, "
        "record_id VARCHAR, served BOOLEAN)"
    )
    connection.execute(
        "INSERT INTO snapshot VALUES ('request-1:model-1:0', 'request-1', 'row-1', true)"
    )
    connection.execute("CREATE TABLE actuals(prediction_id VARCHAR, outcome DOUBLE)")
    connection.execute("INSERT INTO actuals VALUES ('request-1:model-1:0', 42.5)")
    service = service_without_external_repositories()
    run = monitoring_run()

    strategy = service._resolve_join_strategy(run, {"prediction_id", "outcome"})
    labels_sql, unmatched = service._labels_sql(
        connection, run, strategy, "snapshot", "actuals"
    )

    assert strategy == "prediction_id"
    assert connection.execute(labels_sql).fetchall() == [("request-1", "row-1", 42.5)]
    assert unmatched == 0


def test_record_id_join_rejects_repeated_predictions_in_selected_window() -> None:
    connection = duckdb.connect(":memory:")
    connection.execute(
        "CREATE TABLE snapshot(prediction_id VARCHAR, request_id VARCHAR, "
        "record_id VARCHAR, served BOOLEAN)"
    )
    connection.execute(
        "INSERT INTO snapshot VALUES "
        "('prediction-1', 'request-1', 'row-1', true), "
        "('prediction-2', 'request-2', 'row-1', true)"
    )
    connection.execute("CREATE TABLE actuals(record_id VARCHAR, outcome DOUBLE)")
    connection.execute("INSERT INTO actuals VALUES ('row-1', 42.5)")
    service = service_without_external_repositories()
    run = monitoring_run(join_strategy="record_id")

    with pytest.raises(ValueError, match="record_id is not unique"):
        service._labels_sql(connection, run, "record_id", "snapshot", "actuals")


def test_snapshot_csv_contract_is_valid_for_an_empty_full_scope(tmp_path) -> None:
    path = tmp_path / "empty-snapshot.csv"
    path.write_text(",".join(OnlineMonitoringService.snapshot_columns) + "\n", encoding="utf-8")
    service = service_without_external_repositories()
    connection = duckdb.connect(":memory:")

    assert connection.execute(
        f"SELECT count(*) FROM ({service._csv_relation(path)})"
    ).fetchone()[0] == 0


def test_per_model_effectiveness_keeps_revision_role_and_bundle_dimensions() -> None:
    connection = duckdb.connect(":memory:")
    connection.execute(
        "CREATE TABLE joined(deployment_revision_id VARCHAR, model_id VARCHAR, role VARCHAR, "
        "served BOOLEAN, execution_status VARCHAR, monitoring_actual DOUBLE, "
        "prediction_value VARCHAR, prediction_score DOUBLE)"
    )
    connection.execute(
        "INSERT INTO joined VALUES ('revision-2', 'model-1', 'fallback', true, "
        "'succeeded', 42.0, '40.0', NULL)"
    )
    model = SimpleNamespace(
        id="model-1", pipeline_run_id="training-run-7", problem_type="regression",
        model_parameters={}, training_config={},
    )

    report = service_without_external_repositories()._performance_report(
        connection, "joined", monitoring_run(problem_type="regression"),
        model, {model.id: model},
    )

    assert report["service"]["data_scope"]["evaluated_row_count"] == 1
    assert report["models"][0]["deployment_revision_id"] == "revision-2"
    assert report["models"][0]["role"] == "fallback"
    assert report["models"][0]["bundle_id"] == "training-run-7"
    assert "selective technical-failure cohort" in report["models"][0]["evaluation"]["warnings"][-1]
