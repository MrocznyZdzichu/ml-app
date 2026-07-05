from pathlib import Path

import duckdb
import pytest

from app.modules.pipelines.dag import PipelineDefinition
from app.modules.pipelines.execution import DuckDbPipelineExecutionEngine
from app.modules.pipelines.monitoring import DuckDbMonitoringEngine, MonitoringDefinition
from app.modules.pipelines.runtime import SourceRelation, sql_literal
from app.modules.pipelines.workflow import validate_workflow_definition


class StaticInputAdapter:
    def __init__(self, paths: dict[str, Path]) -> None:
        self.paths = paths

    def relation(self, dataset_id: str, owner_id: str) -> SourceRelation:
        path = self.paths[dataset_id]
        return SourceRelation(
            sql=f"read_parquet({sql_literal(str(path))})",
            row_count=-1,
            metadata={
                "dataset_id": dataset_id,
                "score_contract": {
                    "prediction_score_column": "prediction_score",
                    "prediction_score_kind": "positive_class_probability",
                    "positive_class": 1,
                    "positive_class_index": 1,
                } if dataset_id == "predictions" else {},
                "model_artifact_id": "model-1" if dataset_id == "predictions" else "",
            },
        )


def _write_parquet(path: Path, query: str) -> None:
    connection = duckdb.connect()
    try:
        connection.execute(f"COPY ({query}) TO ? (FORMAT PARQUET)", [str(path)])
    finally:
        connection.close()


def _process_join_definition() -> PipelineDefinition:
    return PipelineDefinition.model_validate({
        "inputs": [
            {"input_id": "predictions", "dataset_id": "predictions"},
            {"input_id": "actuals", "dataset_id": "actuals"},
        ],
        "steps": [
            {
                "step_id": "cast_predictions",
                "type": "cast_columns",
                "inputs": [{
                    "port_id": "input",
                    "source": {"node_id": "predictions", "port_id": "out"},
                }],
                "config": {"casts": {"prediction": "BIGINT"}},
            },
            {
                "step_id": "map_actual_labels",
                "type": "map_categories",
                "inputs": [{
                    "port_id": "input",
                    "source": {"node_id": "actuals", "port_id": "out"},
                }],
                "config": {
                    "column": "species",
                    "output_column": "actual",
                    "mapping": {"setosa": "0", "versicolor": "1"},
                },
            },
            {
                "step_id": "cast_actuals",
                "type": "cast_columns",
                "inputs": [{
                    "port_id": "input",
                    "source": {"node_id": "map_actual_labels", "port_id": "out"},
                }],
                "config": {"casts": {"actual": "BIGINT"}},
            },
            {
                "step_id": "join_predictions_actuals",
                "type": "join",
                "inputs": [
                    {
                        "port_id": "left",
                        "source": {"node_id": "cast_predictions", "port_id": "out"},
                    },
                    {
                        "port_id": "right",
                        "source": {"node_id": "cast_actuals", "port_id": "out"},
                    },
                ],
                "config": {
                    "join_type": "left",
                    "keys": [{"left": "row_id", "right": "entity_id"}],
                    "right_suffix": "_actuals",
                },
            },
        ],
        "outputs": [{
            "output_id": "joined_monitoring_data",
            "input": {"node_id": "join_predictions_actuals", "port_id": "out"},
            "materialization": "dataset",
            "dataset_name": "Predictions with actuals",
            "business_case_role": "reference",
        }],
    })


def _report_definition() -> MonitoringDefinition:
    return MonitoringDefinition(
        row_id_column="row_id",
        target_column="actual",
        prediction_column="prediction",
        problem_type="binary_classification",
    )


def test_process_join_maps_labels_casts_and_builds_full_report(tmp_path: Path) -> None:
    predictions_path = tmp_path / "predictions.parquet"
    actuals_path = tmp_path / "actuals.parquet"
    _write_parquet(
        predictions_path,
        "SELECT * FROM (VALUES (1, '0', 0.1), (2, '1', 0.9), (3, '1', 0.8)) "
        "t(row_id, prediction, prediction_score)",
    )
    _write_parquet(
        actuals_path,
        "SELECT * FROM (VALUES (1, 'setosa'), (2, 'versicolor'), "
        "(3, 'setosa')) t(entity_id, species)",
    )
    repository_root = tmp_path / "repository"
    process = DuckDbPipelineExecutionEngine(
        input_adapter=StaticInputAdapter({
            "predictions": predictions_path,
            "actuals": actuals_path,
        }),
        repository_root=repository_root,
    ).execute(
        _process_join_definition(),
        run_id="run-1",
        owner_id="owner",
        is_dry_run=False,
    )
    joined = process.output_manifest[0]

    report = DuckDbMonitoringEngine().execute(
        _report_definition(),
        SourceRelation(
            sql=(
                "read_parquet("
                f"{sql_literal(joined['location_uri'].removeprefix('file://'))}"
                ")"
            ),
            row_count=joined["row_count"],
            metadata={
                "location_uri": joined["location_uri"],
                "dataset_id": "joined-dataset",
                "artifact_id": "joined-artifact",
                "score_contract": joined["score_contract"],
                "model_artifact_id": joined["model_artifact_id"],
            },
        ),
        run_id="run-1",
        owner_id="owner",
        is_dry_run=False,
    )

    assert process.output_row_count == 3
    output = report.output_manifest[0]
    assert output["artifact_type"] == "report_source"
    assert output["prediction_artifact_id"] == "joined-artifact"
    assert output["model_artifact_id"] == "model-1"
    assert output["evaluation"]["data_scope"]["evaluated_row_count"] == 3
    accuracy = next(
        metric["value"]
        for metric in output["evaluation"]["metrics"]
        if metric["id"] == "accuracy"
    )
    assert accuracy == pytest.approx(2 / 3)
    assert output["evaluation"]["join_diagnostics"]["missing_target_row_count"] == 0


def test_performance_report_rejects_many_to_many_join_result(tmp_path: Path) -> None:
    joined_path = tmp_path / "joined.parquet"
    _write_parquet(
        joined_path,
        "SELECT * FROM (VALUES (1, 1, 1), (1, 1, 0)) "
        "t(row_id, prediction, actual)",
    )
    with pytest.raises(ValueError, match="must be unique"):
        DuckDbMonitoringEngine().execute(
            _report_definition(),
            SourceRelation(
                sql=f"read_parquet({sql_literal(str(joined_path))})",
                row_count=2,
                metadata={"location_uri": f"file://{joined_path.as_posix()}"},
            ),
            run_id="run-duplicate",
            owner_id="owner",
            is_dry_run=True,
        )


def test_monitoring_workflow_requires_process_join_then_report() -> None:
    process_definition = _process_join_definition().model_dump(mode="json")
    validated = validate_workflow_definition({
        "contract_version": "2.0",
        "steps": [
            {
                "step_id": "process_join_1",
                "name": "Process & Join",
                "type": "data_engineering",
                "inputs": [],
                "output_port_id": "dataset",
                "additional_output_port_ids": [],
                "config": {"definition": process_definition},
            },
            {
                "step_id": "monitoring_1",
                "name": "Performance Report",
                "type": "monitoring",
                "inputs": [{
                    "port_id": "data",
                    "source": {"step_id": "process_join_1", "port_id": "dataset"},
                }],
                "output_port_id": "performance_report",
                "additional_output_port_ids": [],
                "config": {"definition": _report_definition().model_dump(mode="json")},
            },
        ],
        "outputs": [{
            "output_id": "result",
            "source": {"step_id": "monitoring_1", "port_id": "performance_report"},
        }],
        "parameters": {"template": "monitoring"},
    }, executable=True)

    assert [step["type"] for step in validated["steps"]] == [
        "data_engineering",
        "monitoring",
    ]
