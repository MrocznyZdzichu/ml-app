import json
from collections.abc import Callable
from typing import Any, Protocol
from uuid import uuid4

from redis import Redis

from app.core.config import settings
from app.core.errors import ResourceNotFoundError
from app.ports.task_queue import TaskQueue, require_task_queue


class RedisJobStore(Protocol):
    def setex(self, name: str, time: int, value: str) -> Any: ...
    def get(self, name: str) -> Any: ...
    def delete(self, *names: str) -> Any: ...


class DatasetAnalysisJobs:
    """Submit dataset analysis work and authorize access to its result."""

    key_prefix: str
    task_name: str
    not_found_message: str

    def __init__(
        self,
        redis_client: RedisJobStore | None = None,
        task_queue: TaskQueue | None = None,
    ) -> None:
        self.redis = redis_client or Redis.from_url(settings.redis_url)
        self.task_queue = task_queue
        self.expires_seconds = settings.descriptive_profile_result_expires_seconds

    def start(
        self,
        dataset_id: str,
        owner_id: str,
        options: dict[str, Any],
        asset_owner_id: str | None = None,
        *,
        asset_id: str | None = None,
    ) -> dict[str, Any]:
        job_id = str(uuid4())
        key = f"{self.key_prefix}:{job_id}"
        resolved_id = asset_id or dataset_id
        ownership = {"dataset_id": dataset_id, "owner_id": owner_id}
        if resolved_id != dataset_id:
            ownership["asset_id"] = resolved_id
        self.redis.setex(key, self.expires_seconds, json.dumps(ownership))

        task_args = [resolved_id, asset_owner_id or owner_id, options]
        if asset_owner_id and asset_owner_id != owner_id:
            task_args.append(owner_id)
        try:
            require_task_queue(self.task_queue).enqueue(self.task_name, task_args, task_id=job_id)
        except Exception:
            self.redis.delete(key)
            raise
        return {"job_id": job_id, "status": "queued", "result": None, "error": None}

    def status(
        self,
        dataset_id: str,
        owner_id: str,
        job_id: str,
        *,
        check_dataset_access: Callable[[str], object],
    ) -> dict[str, Any]:
        raw = self.redis.get(f"{self.key_prefix}:{job_id}")
        try:
            ownership = json.loads(raw) if raw else None
        except (TypeError, ValueError):
            ownership = None
        if (
            not isinstance(ownership, dict)
            or ownership.get("dataset_id") != dataset_id
            or ownership.get("owner_id") != owner_id
        ):
            raise ResourceNotFoundError(self.not_found_message)
        # The URL keeps the caller's ID. Authorization follows the version the worker read.
        check_dataset_access(ownership.get("asset_id", dataset_id))

        task = require_task_queue(self.task_queue).result(job_id)
        if task.successful():
            return {"job_id": job_id, "status": "completed", "result": task.result, "error": None}
        if task.failed() or task.state == "REVOKED":
            return {"job_id": job_id, "status": "failed", "result": None, "error": str(task.result)}
        status_name = "running" if task.state in {"STARTED", "RETRY"} else "queued"
        return {"job_id": job_id, "status": status_name, "result": None, "error": None}
