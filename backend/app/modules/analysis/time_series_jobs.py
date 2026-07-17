import json
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status
from redis import Redis

from app.core.config import settings
from app.worker.celery_app import celery_app
from app.worker.tasks import time_series_analysis_dataset


class TimeSeriesAnalysisJobs:
    """Queues full-dataset temporal diagnostics and authorizes result polling."""

    key_prefix = "time-series-analysis-owner"

    def __init__(self, redis_client: Any | None = None) -> None:
        self.redis = redis_client or Redis.from_url(settings.redis_url)
        self.expires_seconds = settings.descriptive_profile_result_expires_seconds

    def start(self, dataset_id: str, owner_id: str, options: dict[str, Any], asset_owner_id: str | None = None) -> dict[str, Any]:
        job_id = str(uuid4())
        key = self._key(job_id)
        self.redis.setex(key, self.expires_seconds, json.dumps({"dataset_id": dataset_id, "owner_id": owner_id}))
        try:
            task_args = [dataset_id, owner_id, options]
            if asset_owner_id and asset_owner_id != owner_id:
                task_args = [dataset_id, asset_owner_id, options, owner_id]
            time_series_analysis_dataset.apply_async(args=task_args, task_id=job_id)
        except Exception:
            self.redis.delete(key)
            raise
        return {"job_id": job_id, "status": "queued", "result": None, "error": None}

    def status(self, dataset_id: str, owner_id: str, job_id: str) -> dict[str, Any]:
        raw = self.redis.get(self._key(job_id))
        try:
            ownership = json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            ownership = {}
        if ownership.get("dataset_id") != dataset_id or ownership.get("owner_id") != owner_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Time-series analysis job not found")
        task = celery_app.AsyncResult(job_id)
        if task.successful():
            return {"job_id": job_id, "status": "completed", "result": task.result, "error": None}
        if task.failed() or task.state == "REVOKED":
            return {"job_id": job_id, "status": "failed", "result": None, "error": str(task.result)}
        return {"job_id": job_id, "status": "running" if task.state in {"STARTED", "RETRY"} else "queued", "result": None, "error": None}

    def _key(self, job_id: str) -> str:
        return f"{self.key_prefix}:{job_id}"
