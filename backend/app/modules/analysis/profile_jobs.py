import json
from typing import Any, Protocol
from uuid import uuid4

from fastapi import HTTPException, status
from redis import Redis

from app.core.config import settings
from app.worker.celery_app import celery_app
from app.worker.tasks import descriptive_profile_dataset


class RedisJobStore(Protocol):
    def setex(self, name: str, time: int, value: str) -> Any:
        ...

    def get(self, name: str) -> Any:
        ...

    def delete(self, *names: str) -> Any:
        ...


class DescriptiveProfileJobs:
    """Owns queue submission, result polling, and job-level authorization metadata."""

    key_prefix = "descriptive-profile-owner"

    def __init__(self, redis_client: RedisJobStore | None = None) -> None:
        self.redis = redis_client or Redis.from_url(settings.redis_url)
        self.expires_seconds = settings.descriptive_profile_result_expires_seconds

    def start(self, dataset_id: str, owner_id: str, options: dict[str, Any], asset_owner_id: str | None = None) -> dict[str, Any]:
        job_id = str(uuid4())
        ownership_key = self._key(job_id)
        self.redis.setex(
            ownership_key,
            self.expires_seconds,
            json.dumps({"dataset_id": dataset_id, "owner_id": owner_id}),
        )
        try:
            task_args = [dataset_id, owner_id, options]
            if asset_owner_id and asset_owner_id != owner_id:
                task_args = [dataset_id, asset_owner_id, options, owner_id]
            descriptive_profile_dataset.apply_async(
                args=task_args,
                task_id=job_id,
            )
        except Exception:
            self.redis.delete(ownership_key)
            raise
        return {"job_id": job_id, "status": "queued", "result": None, "error": None}

    def status(self, dataset_id: str, owner_id: str, job_id: str) -> dict[str, Any]:
        self._authorize(dataset_id, owner_id, job_id)
        task = celery_app.AsyncResult(job_id)
        if task.successful():
            return {"job_id": job_id, "status": "completed", "result": task.result, "error": None}
        if task.failed() or task.state == "REVOKED":
            return {"job_id": job_id, "status": "failed", "result": None, "error": str(task.result)}
        status_name = "running" if task.state in {"STARTED", "RETRY"} else "queued"
        return {"job_id": job_id, "status": status_name, "result": None, "error": None}

    def _authorize(self, dataset_id: str, owner_id: str, job_id: str) -> None:
        raw_ownership = self.redis.get(self._key(job_id))
        try:
            ownership = json.loads(raw_ownership) if raw_ownership else {}
        except (TypeError, ValueError):
            ownership = {}
        if ownership.get("dataset_id") != dataset_id or ownership.get("owner_id") != owner_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile job not found")

    def _key(self, job_id: str) -> str:
        return f"{self.key_prefix}:{job_id}"
