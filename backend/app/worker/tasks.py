from datetime import datetime, timezone

from app.worker.celery_app import celery_app
from app.modules.analysis.full_profile import FullDatasetProfiler
from app.modules.datasets.repository import PostgresDatasetRepository
from app.modules.datasets.columnar import ColumnarDatasetStore
from app.modules.datasets.schemas import TimeSeriesAnalysisRequest
from app.modules.datasets.time_series import FullDatasetTimeSeriesAnalyzer
from app.modules.datasets.temporary import TemporaryPipelineOutputResolver
from app.modules.pipelines.domain import (
    PipelineExecutionCancelled,
    PipelineRunStatus,
    PipelineStepRun,
)
from app.modules.pipelines.runtime import SourceRelation, json_safe, sql_literal
from app.modules.pipelines.materialization import (
    PipelineOutputMaterializer,
    ScoringReportMaterializer,
)
from app.modules.pipelines.repository import PostgresPipelineRepository
from app.modules.pipelines.step_handlers import (
    PipelineStepHandlerRegistry,
    StepExecutionContext,
)
from app.modules.pipelines.workflow import WorkflowDefinition, normalize_workflow_definition
from uuid import uuid4


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
    _append_run_event(
        run,
        "run.started",
        {"message": "Pipeline run started in worker", "status": run.status.value},
    )
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
        artifacts: dict[tuple[str, str], dict] = {}
        all_output_manifests: list[dict] = []
        all_artifact_ids: list[str] = []
        all_warnings: list[str] = []
        upstream_artifact_ids: dict[tuple[str, str], list[str]] = {}
        handler_registry = PipelineStepHandlerRegistry()
        result = None
        executed_step = None

        def emit_event(event_type: str, details: dict) -> None:
            nonlocal active_step_run
            event = _build_run_event(
                event_type,
                details,
                step_id=active_step_run.pipeline_step_id if active_step_run else "",
            )
            latest = repository.get_run(run.id)
            if latest is not None:
                run.status = latest.status
                run.finished_at = latest.finished_at
                run.warnings = list(latest.warnings)
                run.events = list(getattr(latest, "events", []) or [])
            run.events = [*list(getattr(run, "events", []) or []), event][-1000:]
            repository.update_run(run)
            if active_step_run is not None:
                active_step_run.events = [
                    *list(getattr(active_step_run, "events", []) or []),
                    event,
                ][-1000:]
                repository.update_step_run(active_step_run)

        def cancellation_requested() -> bool:
            current_run = repository.get_run(run.id)
            return current_run is not None and current_run.status == PipelineRunStatus.CANCELLED

        for index, step in enumerate(workflow.steps):
            if index > requested_index:
                break
            current = repository.get_run(run.id)
            if current is not None and current.status == PipelineRunStatus.CANCELLED:
                raise PipelineExecutionCancelled("Pipeline run was cancelled")
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
            emit_event(
                "step.started",
                {
                    "message": "Pipeline step started",
                    "step_id": step.step_id,
                    "step_type": step.type,
                    "position": index + 1,
                    "total_steps": min(len(workflow.steps), requested_index + 1),
                },
            )
            result = handler_registry.execute(
                step,
                StepExecutionContext(
                    run_id=run.id,
                    owner_id=run.owner_id,
                    is_dry_run=run.is_dry_run,
                    upstream_relations=relations,
                    upstream_artifacts=artifacts,
                    emit_event=emit_event,
                    is_cancel_requested=cancellation_requested,
                ),
            )
            current = repository.get_run(run.id)
            if current is not None and current.status == PipelineRunStatus.CANCELLED:
                active_step_run.status = PipelineRunStatus.CANCELLED
                active_step_run.finished_at = datetime.now(timezone.utc)
                active_step_run.events = [
                    *active_step_run.events,
                    _build_run_event(
                        "step.cancelled",
                        {"message": "Pipeline step cancelled", "step_id": step.step_id},
                        step_id=step.step_id,
                    ),
                ][-1000:]
                repository.update_step_run(active_step_run)
                active_step_run = None
                raise PipelineExecutionCancelled("Pipeline run was cancelled")
            step_output_manifest = json_safe(list(result.output_manifest))
            step_input_artifact_ids = list(dict.fromkeys(
                [
                    artifact_id
                    for port in step.inputs
                    for artifact_id in upstream_artifact_ids.get(
                        (port.source.step_id, port.source.port_id),
                        [],
                    )
                ]
                + list(result.external_input_artifact_ids)
            ))
            step_input_lineage = [
                {
                    "input_port_id": port.port_id,
                    "source_step_id": port.source.step_id,
                    "source_port_id": port.source.port_id,
                    "artifact_ids": upstream_artifact_ids.get(
                        (port.source.step_id, port.source.port_id),
                        [],
                    ),
                }
                for port in step.inputs
            ] + list(result.external_input_lineage)
            if not run.is_dry_run:
                materialized_manifest, materialized_artifact_ids = PipelineOutputMaterializer().materialize(
                    run=run,
                    version=version,
                    workflow=workflow,
                    output_manifest=step_output_manifest,
                    step_id=step.step_id,
                    input_dataset_ids=result.input_dataset_ids,
                    input_artifact_ids=step_input_artifact_ids or None,
                    input_lineage=step_input_lineage,
                    step_type=step.type,
                    output_stage=(
                        "final"
                        if any(output.source.step_id == step.step_id for output in workflow.outputs)
                        else "intermediate"
                    ),
                )
                step_output_manifest = materialized_manifest
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

            manifests_by_output_id = {
                str(item.get("output_id")): item
                for item in step_output_manifest
            }
            for port_id, output_id in {
                **result.relation_output_ids,
                **result.artifact_output_ids,
            }.items():
                bound_output = manifests_by_output_id.get(output_id)
                artifact_id = str((bound_output or {}).get("artifact_id") or "")
                upstream_artifact_ids[(step.step_id, port_id)] = (
                    [artifact_id] if artifact_id else []
                )
            for port_id, output_id in result.relation_output_ids.items():
                output = manifests_by_output_id.get(output_id)
                if output is None:
                    raise ValueError(
                        f"Step '{step.step_id}' did not produce bound output '{output_id}'"
                    )
                relations[(step.step_id, port_id)] = SourceRelation(
                    sql=(
                        "read_parquet("
                        f"{sql_literal(output['location_uri'].removeprefix('file://'))}"
                        ")"
                    ),
                    row_count=int(output["row_count"]),
                    metadata={
                        "feature_manifest": list(output.get("feature_manifest") or []),
                        "split_evaluation": dict(output.get("split_evaluation") or {}),
                        "fitted_transform_count": int(output.get("fitted_transform_count") or 0),
                        "feature_recipe_hash": str(output.get("feature_recipe_hash") or ""),
                        "dataset_id": str(output.get("dataset_id") or ""),
                        "artifact_id": str(output.get("artifact_id") or ""),
                        "business_case_role": str(output.get("business_case_role") or ""),
                        "dataset_name": str(output.get("dataset_name") or ""),
                        "location_uri": str(output.get("location_uri") or ""),
                        "score_contract": dict(output.get("score_contract") or {}),
                        "model_artifact_id": str(output.get("model_artifact_id") or ""),
                    },
                )
            for port_id, output_id in result.artifact_output_ids.items():
                output = manifests_by_output_id.get(output_id)
                if output is None:
                    raise ValueError(
                        f"Step '{step.step_id}' did not produce bound artifact '{output_id}'"
                    )
                artifacts[(step.step_id, port_id)] = output
            for port_id, source_key in result.relation_passthroughs.items():
                source = relations.get(source_key)
                if source is None:
                    raise ValueError(
                        f"Step '{step.step_id}' cannot pass through missing relation "
                        f"'{source_key[0]}:{source_key[1]}'"
                    )
                relations[(step.step_id, port_id)] = source
                upstream_artifact_ids[(step.step_id, port_id)] = list(
                    upstream_artifact_ids.get(source_key, [])
                )

            active_step_run.input_row_count = result.input_row_count
            active_step_run.processed_row_count = result.processed_row_count
            active_step_run.output_row_count = result.output_row_count
            active_step_run.warnings = json_safe(list(result.warnings))
            all_warnings.extend(active_step_run.warnings)
            active_step_run.output_manifest = json_safe(step_output_manifest)
            active_step_run.status = PipelineRunStatus.SUCCEEDED
            active_step_run.finished_at = datetime.now(timezone.utc)
            emit_event(
                "step.succeeded",
                {
                    "message": "Pipeline step completed",
                    "step_id": step.step_id,
                    "step_type": step.type,
                    "input_row_count": result.input_row_count,
                    "processed_row_count": result.processed_row_count,
                    "output_row_count": result.output_row_count,
                    "warning_count": len(result.warnings),
                },
            )
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
        if not run.is_dry_run:
            report_manifests, report_artifact_ids = ScoringReportMaterializer().materialize(
                run=run,
                version=version,
                workflow=workflow,
                output_manifest=all_output_manifests,
            )
            all_output_manifests.extend(report_manifests)
            all_artifact_ids.extend(report_artifact_ids)
        run.output_manifest = json_safe(all_output_manifests)
        run.output_artifact_ids = list(dict.fromkeys(all_artifact_ids))
        run.warnings = json_safe(list(dict.fromkeys(all_warnings)))
        run.status = PipelineRunStatus.SUCCEEDED
        _append_run_event(
            run,
            "run.succeeded",
            {
                "message": "Pipeline run completed",
                "processed_row_count": run.processed_row_count,
                "output_row_count": run.output_row_count,
                "rejected_row_count": run.rejected_row_count,
            },
        )
    except PipelineExecutionCancelled:
        if active_step_run is not None:
            active_step_run.status = PipelineRunStatus.CANCELLED
            active_step_run.finished_at = datetime.now(timezone.utc)
            active_step_run.events = [
                *active_step_run.events,
                _build_run_event(
                    "step.cancelled",
                    {
                        "message": "Pipeline step cancelled",
                        "step_id": active_step_run.pipeline_step_id,
                    },
                    step_id=active_step_run.pipeline_step_id,
                ),
            ][-1000:]
            repository.update_step_run(active_step_run)
        run.status = PipelineRunStatus.CANCELLED
        run.error_message = ""
        run.warnings = list(dict.fromkeys([
            *run.warnings,
            "Pipeline run cancelled at a workflow step boundary",
        ]))
        _append_run_event(
            run,
            "run.cancelled",
            {"message": "Pipeline run cancelled by user request"},
            level="warning",
        )
    except Exception as exc:
        if active_step_run is not None:
            active_step_run.status = PipelineRunStatus.FAILED
            active_step_run.error_message = str(exc)[:4000]
            active_step_run.finished_at = datetime.now(timezone.utc)
            active_step_run.events = [
                *active_step_run.events,
                _build_run_event(
                    "step.failed",
                    {
                        "message": "Pipeline step failed",
                        "step_id": active_step_run.pipeline_step_id,
                        "error": str(exc)[:1000],
                    },
                    step_id=active_step_run.pipeline_step_id,
                    level="error",
                ),
            ][-1000:]
            repository.update_step_run(active_step_run)
        run.status = PipelineRunStatus.FAILED
        run.error_message = str(exc)[:4000]
        _append_run_event(
            run,
            "run.failed",
            {"message": "Pipeline run failed", "error": str(exc)[:1000]},
            level="error",
        )
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
        resolved = {}
    resolved_models = runtime_parameters.get("resolved_model_versions", {})
    if not isinstance(resolved_models, dict):
        resolved_models = {}
    steps: list[dict] = []
    for raw_step in definition.get("steps", []):
        step = dict(raw_step)
        config = dict(step.get("config") or {})
        nested = dict(config.get("definition") or {})
        if "inputs" in nested:
            nested["inputs"] = [
                {
                    **item,
                    "dataset_id": str(
                        dict(resolved.get(
                            f"{step.get('step_id')}:{item.get('input_id')}",
                            {},
                        )).get("dataset_id") or item.get("dataset_id") or ""
                    ),
                }
                for item in nested.get("inputs", [])
            ]
        selected_model = resolved_models.get(str(step.get("step_id")), {})
        if isinstance(selected_model, dict) and selected_model.get("model_artifact_id"):
            nested["model_artifact_id"] = str(selected_model["model_artifact_id"])
        config["definition"] = nested
        step["config"] = config
        steps.append(step)
    return {**definition, "steps": steps}


def _append_run_event(
    run,
    event_type: str,
    details: dict,
    *,
    level: str = "info",
    step_id: str = "",
) -> None:
    run.events = [
        *list(getattr(run, "events", []) or []),
        _build_run_event(event_type, details, level=level, step_id=step_id),
    ][-1000:]


def _build_run_event(
    event_type: str,
    details: dict,
    *,
    level: str = "info",
    step_id: str = "",
) -> dict:
    timestamp = datetime.now(timezone.utc).isoformat()
    return {
        "timestamp": timestamp,
        "level": level,
        "type": event_type,
        "step_id": step_id,
        "message": str(details.get("message") or event_type),
        "details": json_safe({
            key: value
            for key, value in details.items()
            if key != "message"
        }),
    }


@celery_app.task(name="app.worker.tasks.train_model")
def train_model(training_job_id: str) -> dict[str, str]:
    return {"training_job_id": training_job_id, "status": "queued"}


@celery_app.task(name="app.worker.tasks.batch_score")
def batch_score(batch_job_id: str) -> dict[str, str]:
    return {"batch_job_id": batch_job_id, "status": "queued"}


@celery_app.task(name="app.worker.tasks.export_resource")
def export_resource(export_job_id: str) -> dict[str, str]:
    return {"export_job_id": export_job_id, "status": "queued"}
