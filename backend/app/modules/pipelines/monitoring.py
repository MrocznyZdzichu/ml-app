from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.pipelines.model_evaluation import ModelEvaluationSnapshotBuilder
from app.modules.pipelines.runtime import SourceRelation
from app.shared.duckdb_runtime import configured_duckdb_connection
from app.shared.sql_security import identifier


class MonitoringDefinition(BaseModel):
    """Configuration of the report-only monitoring workflow step."""

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["2.0"] = "2.0"
    row_id_column: str = Field(default="row_id", min_length=1, max_length=255)
    target_column: str = Field(default="target", min_length=1, max_length=255)
    prediction_column: str = Field(default="prediction", min_length=1, max_length=255)
    problem_type: Literal[
        "binary_classification",
        "multiclass_classification",
        "regression",
    ] = "binary_classification"
    report_name: str = Field(
        default="Model performance monitoring",
        min_length=1,
        max_length=200,
    )

    def validate_executable(self) -> None:
        return None


class DuckDbMonitoringEngine:
    """Calculates a bounded report from a prepared, full-scope joined relation."""

    def execute(
        self,
        definition: MonitoringDefinition,
        source: SourceRelation,
        *,
        run_id: str,
        owner_id: str,
        is_dry_run: bool,
    ):
        from app.modules.pipelines.execution import PipelineExecutionResult

        location_uri = str(source.metadata.get("location_uri") or "")
        if not location_uri.startswith("file://"):
            raise ValueError(
                "Performance Report requires a materialized upstream Process & Join output"
            )
        temp_directory = (
            Path(location_uri.removeprefix("file://")).resolve().parent
            / ".monitoring-duckdb"
        )
        connection = configured_duckdb_connection(temp_directory)
        try:
            available = {
                str(row[0])
                for row in connection.execute(
                    f"DESCRIBE SELECT * FROM {source.sql}"
                ).fetchall()
            }
            required = {
                definition.row_id_column,
                definition.target_column,
                definition.prediction_column,
            }
            missing = sorted(required - available)
            if missing:
                raise ValueError(
                    "Performance Report input is missing columns: "
                    + ", ".join(missing)
                )
            row_id = identifier(definition.row_id_column)
            total, null_ids, distinct_ids = connection.execute(
                f"SELECT count(*), count(*) FILTER (WHERE {row_id} IS NULL), "
                f"count(DISTINCT {row_id}) FROM {source.sql}"
            ).fetchone()
            if int(null_ids):
                raise ValueError(
                    f"Monitoring row ID column '{definition.row_id_column}' "
                    f"contains {int(null_ids)} null values"
                )
            if int(distinct_ids) != int(total):
                raise ValueError(
                    f"Monitoring row ID column '{definition.row_id_column}' must be unique; "
                    f"found {int(distinct_ids)} distinct IDs in {int(total)} rows. "
                    "Review Process & Join keys to avoid a many-to-many join."
                )

            score_contract = dict(source.metadata.get("score_contract") or {})
            evaluation = ModelEvaluationSnapshotBuilder().build(
                connection,
                f"SELECT * FROM {source.sql}",
                problem_type=(
                    "regression"
                    if definition.problem_type == "regression"
                    else "classification"
                ),
                target_column=definition.target_column,
                prediction_column=definition.prediction_column,
                score_contract=score_contract,
            )
            evaluated = int(
                evaluation.get("data_scope", {}).get("evaluated_row_count") or 0
            )
            evaluation["join_diagnostics"] = {
                "joined_row_count": int(total),
                "matched_target_row_count": evaluated,
                "missing_target_row_count": int(total) - evaluated,
                "row_id_column": definition.row_id_column,
                "scope": "full",
            }
            warnings = list(evaluation.get("warnings") or [])
            missing_targets = int(total) - evaluated
            if missing_targets:
                warnings.append(
                    f"{missing_targets} joined rows have no usable target and were excluded from metrics"
                )
            return PipelineExecutionResult(
                input_row_count=int(total),
                processed_row_count=int(total),
                output_row_count=evaluated,
                warnings=list(dict.fromkeys(warnings)),
                output_manifest=[{
                    "output_id": "performance_report_source",
                    "artifact_type": "report_source",
                    "materialization": "evaluation",
                    "location_uri": location_uri,
                    "row_count": int(total),
                    "evaluation": evaluation,
                    "prediction_dataset_id": str(
                        source.metadata.get("dataset_id") or ""
                    ),
                    "prediction_artifact_id": str(
                        source.metadata.get("artifact_id") or ""
                    ),
                    "model_artifact_id": str(
                        source.metadata.get("model_artifact_id") or ""
                    ),
                    "data_scope": "full",
                    "is_dry_run": is_dry_run,
                }],
            )
        finally:
            connection.close()
