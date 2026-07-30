from app.worker.celery_app import celery_app
from app.modules.analysis.full_profile import FullDatasetProfiler
from app.modules.datasets.repository import PostgresDatasetRepository
from app.modules.datasets.columnar import ColumnarDatasetStore
from app.modules.datasets.schemas import TimeSeriesAnalysisRequest
from app.modules.datasets.time_series import FullDatasetTimeSeriesAnalyzer
from app.modules.datasets.temporary import TemporaryPipelineOutputResolver
from app.modules.pipelines.run_executor import PipelineRunExecutor
from app.core.security import Principal
from app.modules.auth.repository import PostgresUserRepository
from app.modules.sharing.domain import ResourceAccessRole, ResourceKind
from app.modules.sharing.policy import access_policy


@celery_app.task(name="app.worker.tasks.profile_dataset")
def profile_dataset(dataset_id: str) -> dict[str, str]:
    return {"dataset_id": dataset_id, "status": "queued"}


_pipeline_run_executor = PipelineRunExecutor()


@celery_app.task(name="app.worker.tasks.execute_pipeline_run", track_started=True)
def execute_pipeline_run(run_id: str) -> dict:
    return _pipeline_run_executor.execute(run_id)


@celery_app.task(name="app.worker.tasks.descriptive_profile_dataset", track_started=True)
def descriptive_profile_dataset(dataset_id: str, owner_id: str, settings: dict, actor_id: str | None = None) -> dict:
    repository = PostgresDatasetRepository()
    asset = _load_analysis_asset(dataset_id, owner_id, repository)
    _require_worker_dataset_access(asset, actor_id or owner_id, ResourceAccessRole.EDITOR)

    def load_asset(asset_id: str):
        loaded = repository.get(asset_id)
        if loaded is None or loaded.owner_id != owner_id:
            raise ValueError("Data View source not found")
        return loaded

    return FullDatasetProfiler().profile(asset, settings, load_asset)


@celery_app.task(name="app.worker.tasks.time_series_analysis_dataset", track_started=True)
def time_series_analysis_dataset(dataset_id: str, owner_id: str, options: dict, actor_id: str | None = None) -> dict:
    repository = PostgresDatasetRepository()
    asset = _load_analysis_asset(dataset_id, owner_id, repository)
    _require_worker_dataset_access(asset, actor_id or owner_id, ResourceAccessRole.EDITOR)

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


def _require_worker_dataset_access(asset, actor_id: str, minimum: ResourceAccessRole) -> None:
    actor = PostgresUserRepository().get(actor_id)
    if actor is None or not actor.is_active:
        raise ValueError("Dataset analysis actor is no longer active")
    principal = Principal(
        user_id=actor.id, email=actor.email, display_name=actor.display_name,
        login_name=actor.login_name, roles=actor.roles, session_version=actor.session_version,
    )
    access_policy.require_resource(
        principal,
        ResourceKind.DATA_VIEW if asset.source_type.value == "view" else ResourceKind.DATASET,
        asset.id,
        asset.owner_id,
        minimum,
    )


@celery_app.task(name="app.worker.tasks.train_model")
def train_model(training_job_id: str) -> dict[str, str]:
    return {"training_job_id": training_job_id, "status": "queued"}


@celery_app.task(name="app.worker.tasks.batch_score")
def batch_score(batch_job_id: str) -> dict[str, str]:
    return {"batch_job_id": batch_job_id, "status": "queued"}


@celery_app.task(name="app.worker.tasks.replay_challenger", track_started=True)
def replay_challenger(replay_job_id: str) -> dict[str, str | int]:
    from app.modules.serving.service import ServingService

    job = ServingService().run_replay(replay_job_id)
    return {
        "replay_job_id": job.id,
        "status": job.status.value,
        "processed_requests": job.processed_requests,
        "processed_records": job.processed_records,
        "failed_requests": job.failed_requests,
    }


@celery_app.task(name="app.worker.tasks.run_online_monitoring", track_started=True)
def run_online_monitoring(run_id: str) -> dict[str, str | int]:
    from app.modules.serving.monitoring import OnlineMonitoringService

    run = OnlineMonitoringService().execute_run(run_id)
    return {
        "monitoring_run_id": run.id,
        "status": run.status.value,
        "processed_requests": run.processed_request_count,
        "processed_rows": run.processed_row_count,
        "matched_actuals": run.matched_row_count,
    }


@celery_app.task(name="app.worker.tasks.prune_serving_inference_history")
def prune_serving_inference_history() -> dict[str, int]:
    from datetime import datetime, timedelta, timezone

    from app.modules.serving.repository import PostgresServingRepository

    repository = PostgresServingRepository()
    now = datetime.now(timezone.utc)
    deleted = 0
    deployments = repository.list_all_deployments()
    for deployment in deployments:
        deleted += repository.prune_expired(
            deployment.id,
            now - timedelta(days=deployment.retention_days),
        )
    return {"deployments_checked": len(deployments), "requests_deleted": deleted}


@celery_app.task(name="app.worker.tasks.export_resource")
def export_resource(export_job_id: str) -> dict[str, str]:
    return {"export_job_id": export_job_id, "status": "queued"}
