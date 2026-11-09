from app.core.container import get_container
from app.modules.pipelines.run_executor import PipelineRunExecutor
from app.worker.celery_app import celery_app


@celery_app.task(name="app.worker.tasks.profile_dataset")
def profile_dataset(dataset_id: str) -> dict[str, str]:
    return {"dataset_id": dataset_id, "status": "queued"}


_pipeline_run_executor = PipelineRunExecutor(repository_factory=lambda: get_container().pipeline_repository)


@celery_app.task(name="app.worker.tasks.execute_pipeline_run", track_started=True, reject_on_worker_lost=True)
def execute_pipeline_run(run_id: str) -> dict:
    return _pipeline_run_executor.execute(run_id)


@celery_app.task(name="app.worker.tasks.reconcile_interrupted_pipeline_runs", expires=60)
def reconcile_interrupted_pipeline_runs() -> dict[str, int]:
    return _pipeline_run_executor.reconcile_interrupted_runs()


@celery_app.task(name="app.worker.tasks.descriptive_profile_dataset", track_started=True)
def descriptive_profile_dataset(dataset_id: str, owner_id: str, settings: dict, actor_id: str | None = None) -> dict:
    return get_container().dataset_analysis_executor.profile(dataset_id, owner_id, settings, actor_id)


@celery_app.task(name="app.worker.tasks.time_series_analysis_dataset", track_started=True)
def time_series_analysis_dataset(dataset_id: str, owner_id: str, options: dict, actor_id: str | None = None) -> dict:
    return get_container().dataset_analysis_executor.analyze_time_series(dataset_id, owner_id, options, actor_id)


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
