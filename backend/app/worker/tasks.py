from app.worker.celery_app import celery_app
from app.modules.analysis.full_profile import FullDatasetProfiler
from app.modules.datasets.repository import PostgresDatasetRepository
from app.modules.datasets.columnar import ColumnarDatasetStore
from app.modules.datasets.schemas import TimeSeriesAnalysisRequest
from app.modules.datasets.time_series import FullDatasetTimeSeriesAnalyzer


@celery_app.task(name="app.worker.tasks.profile_dataset")
def profile_dataset(dataset_id: str) -> dict[str, str]:
    return {"dataset_id": dataset_id, "status": "queued"}


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
