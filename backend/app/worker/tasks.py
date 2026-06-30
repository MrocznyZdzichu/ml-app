from datetime import datetime, timezone

from app.worker.celery_app import celery_app
from app.modules.analysis.full_profile import FullDatasetProfiler
from app.modules.datasets.repository import PostgresDatasetRepository
from app.modules.datasets.columnar import ColumnarDatasetStore
from app.modules.datasets.schemas import TimeSeriesAnalysisRequest
from app.modules.datasets.time_series import FullDatasetTimeSeriesAnalyzer
from app.modules.pipelines.dag import PipelineDefinition
from app.modules.pipelines.domain import PipelineRunStatus
from app.modules.pipelines.execution import DuckDbPipelineExecutionEngine
from app.modules.pipelines.materialization import PipelineOutputMaterializer
from app.modules.pipelines.repository import PostgresPipelineRepository
from app.modules.pipelines.workflow import WorkflowDefinition, data_engineering_step


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
    try:
        workflow = WorkflowDefinition.model_validate(version.definition)
        step = data_engineering_step(workflow)
        if run.requested_step_id and run.requested_step_id != step.step_id:
            raise ValueError("Requested workflow step does not match the executable DE step")
        definition = PipelineDefinition.model_validate(step.config["definition"])
        result = DuckDbPipelineExecutionEngine().execute(
            definition=definition,
            run_id=run.id,
            owner_id=run.owner_id,
            is_dry_run=run.is_dry_run,
        )
        run.input_row_count = result.input_row_count
        run.processed_row_count = result.processed_row_count
        run.output_row_count = result.output_row_count
        run.rejected_row_count = 0
        run.output_manifest = result.output_manifest
        if not run.is_dry_run:
            run.output_manifest, run.output_artifact_ids = PipelineOutputMaterializer().materialize(
                run=run,
                version=version,
                workflow=workflow,
                output_manifest=result.output_manifest,
            )
        run.warnings = result.warnings
        run.status = PipelineRunStatus.SUCCEEDED
    except Exception as exc:
        run.status = PipelineRunStatus.FAILED
        run.error_message = str(exc)[:4000]
    finally:
        run.finished_at = datetime.now(timezone.utc)
        repository.update_run(run)
    return {
        "run_id": run.id,
        "status": run.status.value,
        "input_row_count": run.input_row_count,
        "output_row_count": run.output_row_count,
    }


@celery_app.task(name="app.worker.tasks.descriptive_profile_dataset", track_started=True)
def descriptive_profile_dataset(dataset_id: str, owner_id: str, settings: dict) -> dict:
    repository = PostgresDatasetRepository()
    asset = repository.get(dataset_id)
    if asset is None or asset.owner_id != owner_id:
        raise ValueError("Dataset not found")

    def load_asset(asset_id: str):
        loaded = repository.get(asset_id)
        if loaded is None or loaded.owner_id != owner_id:
            raise ValueError("Data View source not found")
        return loaded

    return FullDatasetProfiler().profile(asset, settings, load_asset)


@celery_app.task(name="app.worker.tasks.time_series_analysis_dataset", track_started=True)
def time_series_analysis_dataset(dataset_id: str, owner_id: str, options: dict) -> dict:
    repository = PostgresDatasetRepository()
    asset = repository.get(dataset_id)
    if asset is None or asset.owner_id != owner_id:
        raise ValueError("Dataset not found")

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


@celery_app.task(name="app.worker.tasks.train_model")
def train_model(training_job_id: str) -> dict[str, str]:
    return {"training_job_id": training_job_id, "status": "queued"}


@celery_app.task(name="app.worker.tasks.batch_score")
def batch_score(batch_job_id: str) -> dict[str, str]:
    return {"batch_job_id": batch_job_id, "status": "queued"}


@celery_app.task(name="app.worker.tasks.export_resource")
def export_resource(export_job_id: str) -> dict[str, str]:
    return {"export_job_id": export_job_id, "status": "queued"}
