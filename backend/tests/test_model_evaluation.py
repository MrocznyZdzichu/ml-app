import duckdb
import pytest

from app.modules.pipelines.model_evaluation import ModelEvaluationSnapshotBuilder


def test_binary_evaluation_snapshot_uses_full_data_and_bounded_curves() -> None:
    connection = duckdb.connect()
    connection.execute(
        """
        CREATE TABLE predictions AS
        SELECT * FROM (VALUES
            (0, 0, 0.05), (0, 0, 0.20), (0, 1, 0.60),
            (1, 0, 0.40), (1, 1, 0.80), (1, 1, 0.95)
        ) AS values(actual, prediction, probability)
        """
    )

    report = ModelEvaluationSnapshotBuilder().build(
        connection,
        "SELECT * FROM predictions",
        problem_type="binary_classification",
        target_column="actual",
        prediction_column="prediction",
        score_contract={
            "prediction_score_column": "probability",
            "positive_class": 1,
            "probability_available": True,
        },
    )
    connection.close()

    metrics = {item["id"]: item["value"] for item in report["metrics"]}
    assert report["contract_version"] == "1.0"
    assert report["data_scope"]["mode"] == "full"
    assert report["data_scope"]["evaluated_row_count"] == 6
    assert metrics["accuracy"] == pytest.approx(4 / 6)
    assert metrics["roc_auc"] == pytest.approx(8 / 9)
    assert metrics["average_precision"] == pytest.approx(0.9166666667)
    assert metrics["brier_score"] > 0
    assert len(report["curves"]["roc"]["points"]) <= 101
    assert report["curves"]["calibration"]["points"]
    assert report["confusion_matrix"]["values"] == [[2, 1], [1, 2]]
    assert report["monitoring"]["baseline_eligible"] is True


def test_binary_evaluation_infers_positive_class_when_contract_value_is_null() -> None:
    connection = duckdb.connect()
    connection.execute(
        "CREATE TABLE predictions AS SELECT * FROM (VALUES "
        "(0, 0, 0.05), (0, 0, 0.20), (0, 1, 0.60), "
        "(1, 0, 0.40), (1, 1, 0.80), (1, 1, 0.95)) "
        "AS values(actual, prediction, probability)"
    )

    report = ModelEvaluationSnapshotBuilder().build(
        connection,
        "SELECT * FROM predictions",
        problem_type="binary_classification",
        target_column="actual",
        prediction_column="prediction",
        score_contract={
            "prediction_score_column": "probability",
            "positive_class": None,
            "probability_available": True,
        },
    )
    connection.close()

    metrics = {item["id"]: item["value"] for item in report["metrics"]}
    assert report["positive_class"] == 1
    assert metrics["roc_auc"] == pytest.approx(8 / 9)
    assert metrics["average_precision"] == pytest.approx(0.9166666667)


def test_regression_evaluation_snapshot_reports_residual_diagnostics() -> None:
    connection = duckdb.connect()
    connection.execute(
        """
        CREATE TABLE predictions AS
        SELECT range::DOUBLE AS actual,
               range::DOUBLE + CASE WHEN range % 2 = 0 THEN 1 ELSE -1 END AS prediction
        FROM range(1000)
        """
    )

    report = ModelEvaluationSnapshotBuilder().build(
        connection,
        "SELECT * FROM predictions",
        problem_type="regression",
        target_column="actual",
        prediction_column="prediction",
        score_contract={},
    )
    connection.close()

    metrics = {item["id"]: item["value"] for item in report["metrics"]}
    assert report["data_scope"]["evaluated_row_count"] == 1000
    assert metrics["mae"] == pytest.approx(1)
    assert metrics["rmse"] == pytest.approx(1)
    assert metrics["r2"] > 0.99
    assert len(report["residuals"]["histogram"]) == 20
    assert len(report["residuals"]["qq_plot"]["points"]) == 99
    assert report["residuals"]["qq_plot"]["points"][49] == pytest.approx({
        "theoretical": 0,
        "observed": 0,
    })
    assert "full-data" in report["residuals"]["qq_plot"]["rendering"]
    assert len(report["residuals"]["actual_vs_predicted"]["points"]) == 500
    assert report["monitoring"]["comparison_dimensions"] == [
        "metrics",
        "prediction_distribution",
        "residual_distribution",
    ]


def test_evaluation_snapshot_explains_missing_actuals() -> None:
    connection = duckdb.connect()
    report = ModelEvaluationSnapshotBuilder().build(
        connection,
        "SELECT 1 AS prediction",
        problem_type="binary_classification",
        target_column="",
        prediction_column="prediction",
        score_contract={},
    )
    connection.close()

    assert report["status"] == "target_unavailable"
    assert report["monitoring"]["requires_actuals"] is True
    assert report["metrics"] == []


def test_constant_scores_produce_monotonic_collapsed_curves() -> None:
    connection = duckdb.connect()
    connection.execute(
        "CREATE TABLE predictions AS "
        "SELECT range % 2 AS actual, 0 AS prediction, 0.0::DOUBLE AS score "
        "FROM range(200)"
    )

    report = ModelEvaluationSnapshotBuilder().build(
        connection,
        "SELECT * FROM predictions",
        problem_type="binary_classification",
        target_column="actual",
        prediction_column="prediction",
        score_contract={
            "prediction_score_column": "score",
            "positive_class": 1,
            "probability_available": True,
        },
    )
    connection.close()

    assert report["curves"]["roc"]["points"] == [
        {"x": 0.0, "y": 0.0, "threshold": None},
        {"x": 1.0, "y": 1.0, "threshold": 0.0},
    ]
    assert report["curves"]["precision_recall"]["points"] == [
        {"x": 0.0, "y": 1.0, "threshold": None},
        {"x": 1.0, "y": 0.5, "threshold": 0.0},
    ]
    assert any("same score" in warning for warning in report["warnings"])
