from datetime import datetime, timezone

from app.worker.celery_app import celery_app
from app.modules.analysis.full_profile import FullDatasetProfiler
from app.modules.datasets.repository import PostgresDatasetRepository
from app.modules.datasets.columnar import ColumnarDatasetStore
from app.modules.datasets.schemas import TimeSeriesAnalysisRequest
from app.modules.datasets.time_series import FullDatasetTimeSeriesAnalyzer
from app.modules.datasets.temporary import TemporaryPipelineOutputResolver
from app.modules.pipelines.dag import PipelineDefinition
from app.modules.pipelines.domain import PipelineRunStatus, PipelineStepRun
from app.modules.pipelines.execution import DuckDbPipelineExecutionEngine
from app.modules.pipelines.runtime import SourceRelation, sql_literal
from app.modules.pipelines.feature_engineering import (
    DuckDbFeatureEngineeringEngine,
    FeatureEngineeringDefinition,
)
from app.modules.pipelines.materialization import PipelineOutputMaterializer
from app.modules.pipelines.repository import PostgresPipelineRepository
from app.modules.pipelines.workflow import WorkflowDefinition, normalize_workflow_definition
from uuid import uuid4


class PipelineRunCancelled(Exception):
    pass


@celery_app.task(name="app.worker.tasks.profile_dataset")
def profile_dataset(dataset_id: str) -> dict[str, str]:
    return {"dataset_id": dataset_id, "status": "queued"}


@celery_app.task(name="app.worker.tasks.execute_pipeline_run", track_started=True)
def execute_pipeline_run(run_id: str) -> dict:
    repository = PostgresPipelineRepository()
    run = repository.get_run(run_id)
    if run is None:
        raise ValueError("Pipeline run not found")
    version = repository.get_version(run.pipeline_version_id)
    if version is None:
        raise ValueError("Pipeline version not found")
    if run.status in {PipelineRunStatus.CANCELLED, PipelineRunStatus.SUCCEEDED}:
        return {"run_id": run.id, "status": run.status.value}

    run.status = PipelineRunStatus.RUNNING
    run.started_at = datetime.now(timezone.utc)
    repository.update_run(run)
    failure: Exception | None = None
    active_step_run: PipelineStepRun | None = None
    try:
        workflow = WorkflowDefinition.model_validate(
            _definition_with_resolved_inputs(
                normalize_workflow_definition(version.definition),
                getattr(run, "runtime_parameters", {}),
            )
        )
        if not workflow.steps:
            raise ValueError(
                "Pipeline workflow validation error: no executable steps were declared"
            )
        requested_index = (
            next(
                index for index, step in enumerate(workflow.steps)
                if step.step_id == run.requested_step_id
            )
            if run.requested_step_id
            else len(workflow.steps) - 1
        )
        relations: dict[tuple[str, str], SourceRelation] = {}
        all_output_manifests: list[dict] = []
        all_artifact_ids: list[str] = []
        all_warnings: list[str] = []
        upstream_artifact_ids: dict[str, list[str]] = {}
        result = None
        executed_step = None
        for index, step in enumerate(workflow.steps):
            if index > requested_index:
                break
            current = repository.get_run(run.id)
            if current is not None and current.status == PipelineRunStatus.CANCELLED:
                raise PipelineRunCancelled("Pipeline run was cancelled")
            executed_step = step
            active_step_run = PipelineStepRun(
                id=str(uuid4()),
                owner_id=run.owner_id,
                pipeline_run_id=run.id,
                pipeline_step_id=step.step_id,
                step_type=step.type,
                status=PipelineRunStatus.RUNNING,
                started_at=datetime.now(timezone.utc),
            )
            repository.add_step_run(active_step_run)
            if step.type == "data_engineering":
                definition = PipelineDefinition.model_validate(step.config["definition"])
                de_result = DuckDbPipelineExecutionEngine().execute(
                    definition=definition,
                    run_id=run.id,
                    owner_id=run.owner_id,
                    is_dry_run=run.is_dry_run,
                )
                if not de_result.output_manifest:
                    raise ValueError("Data Engineering produced no workflow output")
                result = de_result
            else:
                definition = FeatureEngineeringDefinition.model_validate(step.config["definition"])
                bindings: dict[str, SourceRelation] = {}
                for port in step.inputs:
                    source = relations.get((port.source.step_id, port.source.port_id))
                    if source is None:
                        raise ValueError(
                            f"Feature Engineering input '{port.port_id}' has no executable upstream output"
                        )
                    bindings[port.port_id] = source
                fe_result = DuckDbFeatureEngineeringEngine().execute(
                    definition=definition,
                    run_id=run.id,
                    owner_id=run.owner_id,
                    is_dry_run=run.is_dry_run,
                    upstream_relations=bindings,
                )
                result = fe_result
                declared_ports = {
                    step.output_port_id,
                    *step.additional_output_port_ids,
                }
                for dataset_manifest in (
                    item for item in fe_result.output_manifest
                    if item.get("artifact_type", "dataset") == "dataset"
                ):
                    role = str(dataset_manifest.get("business_case_role") or "training")
                    if role not in declared_ports:
                        raise ValueError(
                            f"Feature Engineering produced undeclared output role '{role}'"
                        )
                    relations[(step.step_id, role)] = SourceRelation(
                        sql=(
                            "read_parquet("
                            f"{sql_literal(dataset_manifest['location_uri'].removeprefix('file://'))}"
                            ")"
                        ),
                        row_count=int(dataset_manifest["row_count"]),
                    )
            current = repository.get_run(run.id)
            if current is not None and current.status == PipelineRunStatus.CANCELLED:
                active_step_run.status = PipelineRunStatus.CANCELLED
                active_step_run.finished_at = datetime.now(timezone.utc)
                repository.update_step_run(active_step_run)
                active_step_run = None
                raise PipelineRunCancelled("Pipeline run was cancelled")
            step_output_manifest = list(result.output_manifest)
            step_input_artifact_ids = list(dict.fromkeys(
                artifact_id
                for port in step.inputs
                for artifact_id in upstream_artifact_ids.get(port.source.step_id, [])
            ))
            if not run.is_dry_run:
                materialized_manifest, materialized_artifact_ids = PipelineOutputMaterializer().materialize(
                    run=run,
                    version=version,
                    workflow=workflow,
                    output_manifest=step_output_manifest,
                    step_id=step.step_id,
                    input_dataset_ids=list(dict.fromkeys(
                        item.dataset_id for item in (
                            PipelineDefinition.model_validate(step.config["definition"]).inputs
                            if step.type == "data_engineering"
                            else FeatureEngineeringDefinition.model_validate(step.config["definition"]).inputs
                        )
                        if item.dataset_id
                    )),
                    input_artifact_ids=step_input_artifact_ids or None,
                    step_type=step.type,
                    output_stage=(
                        "final"
                        if any(output.source.step_id == step.step_id for output in workflow.outputs)
                        else "intermediate"
                    ),
                )
                step_output_manifest = materialized_manifest
                upstream_artifact_ids[step.step_id] = materialized_artifact_ids
                all_artifact_ids.extend(materialized_artifact_ids)
            for manifest in step_output_manifest:
                manifest["pipeline_step_id"] = step.step_id
                manifest["output_stage"] = (
                    "intermediate"
                    if manifest.get("artifact_type") == "feature_transform"
                    else (
                        "final"
                        if any(output.source.step_id == step.step_id for output in workflow.outputs)
                        else "intermediate"
                    )
                )
            all_output_manifests.extend(step_output_manifest)

            if step.type == "data_engineering":
                primary = step_output_manifest[0]
                relations[(step.step_id, step.output_port_id)] = SourceRelation(
                    sql=f"read_parquet({sql_literal(primary['location_uri'].removeprefix('file://'))})",
                    row_count=int(primary["row_count"]),
                )

            active_step_run.input_row_count = result.input_row_count
            active_step_run.processed_row_count = result.processed_row_count
            active_step_run.output_row_count = result.output_row_count
            active_step_run.warnings = result.warnings
            all_warnings.extend(result.warnings)
            active_step_run.output_manifest = step_output_manifest
            active_step_run.status = PipelineRunStatus.SUCCEEDED
            active_step_run.finished_at = datetime.now(timezone.utc)
            repository.update_step_run(active_step_run)
            active_step_run = None
        if result is None or executed_step is None:
            raise ValueError("Pipeline workflow has no executable steps")
        run.input_row_count = result.input_row_count
        run.processed_row_count = result.processed_row_count
        run.output_row_count = result.output_row_count
        run.rejected_row_count = sum(
            int(item.get("row_count") or 0)
            for item in all_output_manifests
            if item.get("quality_output_kind") == "rejected_records"
        )
        run.output_manifest = all_output_manifests
        run.output_artifact_ids = list(dict.fromkeys(all_artifact_ids))
        run.warnings = list(dict.fromkeys(all_warnings))
        run.status = PipelineRunStatus.SUCCEEDED
    except PipelineRunCancelled:
        if active_step_run is not None:
            active_step_run.status = PipelineRunStatus.CANCELLED
            active_step_run.finished_at = datetime.now(timezone.utc)
            repository.update_step_run(active_step_run)
        run.status = PipelineRunStatus.CANCELLED
        run.error_message = ""
        run.warnings = list(dict.fromkeys([
            *run.warnings,
            "Pipeline run cancelled at a workflow step boundary",
        ]))
    except Exception as exc:
        if active_step_run is not None:
            active_step_run.status = PipelineRunStatus.FAILED
            active_step_run.error_message = str(exc)[:4000]
            active_step_run.finished_at = datetime.now(timezone.utc)
            repository.update_step_run(active_step_run)
        run.status = PipelineRunStatus.FAILED
        run.error_message = str(exc)[:4000]
        failure = exc
    finally:
        run.finished_at = datetime.now(timezone.utc)
        repository.update_run(run)
    if failure is not None:
        raise failure
    return {
        "run_id": run.id,
        "status": run.status.value,
        "input_row_count": run.input_row_count,
        "output_row_count": run.output_row_count,
    }


@celery_app.task(name="app.worker.tasks.descriptive_profile_dataset", track_started=True)
def descriptive_profile_dataset(dataset_id: str, owner_id: str, settings: dict) -> dict:
    repository = PostgresDatasetRepository()
    asset = _load_analysis_asset(dataset_id, owner_id, repository)

    def load_asset(asset_id: str):
        loaded = repository.get(asset_id)
        if loaded is None or loaded.owner_id != owner_id:
            raise ValueError("Data View source not found")
        return loaded

    return FullDatasetProfiler().profile(asset, settings, load_asset)


@celery_app.task(name="app.worker.tasks.time_series_analysis_dataset", track_started=True)
def time_series_analysis_dataset(dataset_id: str, owner_id: str, options: dict) -> dict:
    repository = PostgresDatasetRepository()
    asset = _load_analysis_asset(dataset_id, owner_id, repository)

    def load_asset(asset_id: str):
        loaded = repository.get(asset_id)
        if loaded is None or loaded.owner_id != owner_id:
            raise ValueError("Data View source not found")
        return loaded

    store = ColumnarDatasetStore()
    connection = store.connect(asset)
    relation = store.relation_sql(asset, load_asset)
    try:
        columns = {str(row[0]): str(row[1]) for row in connection.execute(f"DESCRIBE SELECT * FROM {relation}").fetchall()}
        request = TimeSeriesAnalysisRequest.model_validate(options)
        result = FullDatasetTimeSeriesAnalyzer(store).analyze(connection, relation, request, columns)
        return {"dataset_id": asset.id, "time_column": request.time_column, "value_column": request.value_column, **result}
    finally:
        connection.close()


def _load_analysis_asset(dataset_id: str, owner_id: str, repository: PostgresDatasetRepository):
    temporary_outputs = TemporaryPipelineOutputResolver()
    if temporary_outputs.recognizes(dataset_id):
        return temporary_outputs.resolve(dataset_id, owner_id)
    asset = repository.get(dataset_id)
    if asset is None or asset.owner_id != owner_id:
        raise ValueError("Dataset not found")
    return asset


def _definition_with_resolved_inputs(
    definition: dict,
    runtime_parameters: dict,
) -> dict:
    resolved = runtime_parameters.get("resolved_input_versions", {})
    if not isinstance(resolved, dict):
        return definition
    copied = {
        **definition,
        "steps": [
            {
                **step,
                "config": {
                    **dict(step.get("config") or {}),
                    "definition": {
                        **dict(dict(step.get("config") or {}).get("definition") or {}),
                        "inputs": [
                            {
                                **item,
                                "dataset_id": str(
                                    dict(resolved.get(
                                        f"{step.get('step_id')}:{item.get('input_id')}",
                                        {},
                                    )).get("dataset_id") or item.get("dataset_id") or ""
                                ),
                            }
                            for item in dict(
                                dict(step.get("config") or {}).get("definition") or {}
                            ).get("inputs", [])
                        ],
                    },
                },
            }
            for step in definition.get("steps", [])
        ],
    }
    return copied


@celery_app.task(name="app.worker.tasks.train_model")
def train_model(training_job_id: str) -> dict[str, str]:
    return {"training_job_id": training_job_id, "status": "queued"}


@celery_app.task(name="app.worker.tasks.batch_score")
def batch_score(batch_job_id: str) -> dict[str, str]:
    return {"batch_job_id": batch_job_id, "status": "queued"}


@celery_app.task(name="app.worker.tasks.export_resource")
def export_resource(export_job_id: str) -> dict[str, str]:
    return {"export_job_id": export_job_id, "status": "queued"}
