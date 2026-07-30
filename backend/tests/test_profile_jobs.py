import json

import pytest
from fastapi import HTTPException

from app.modules.analysis import profile_jobs
from app.modules.analysis.profile_jobs import DescriptiveProfileJobs


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}

    def setex(self, key: str, _seconds: int, value: str) -> None:
        self.values[key] = value.encode()

    def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    def delete(self, *keys: str) -> None:
        for key in keys:
            self.values.pop(key, None)


class FakeTaskQueue:
    def __init__(self) -> None:
        self.submitted: dict[str, object] = {}

    def enqueue(
        self,
        task_name: str,
        args: list[object],
        *,
        task_id: str | None = None,
    ) -> None:
        self.submitted = {
            "task_name": task_name,
            "args": args,
            "task_id": task_id,
        }

    def result(self, task_id: str):
        raise AssertionError(f"Unexpected result lookup for {task_id}")


def test_profile_job_start_records_dataset_ownership(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = FakeRedis()
    task_queue = FakeTaskQueue()
    monkeypatch.setattr(profile_jobs, "uuid4", lambda: "job-1")
    jobs = DescriptiveProfileJobs(fake_redis, task_queue)

    response = jobs.start("dataset-1", "owner-1", {"include_summary": True})

    assert response["job_id"] == "job-1"
    assert task_queue.submitted == {
        "task_name": "app.worker.tasks.descriptive_profile_dataset",
        "args": ["dataset-1", "owner-1", {"include_summary": True}],
        "task_id": "job-1",
    }
    ownership = json.loads(fake_redis.values["descriptive-profile-owner:job-1"])
    assert ownership == {"dataset_id": "dataset-1", "owner_id": "owner-1"}


def test_profile_job_status_rejects_wrong_owner_before_reading_result() -> None:
    fake_redis = FakeRedis()
    fake_redis.setex(
        "descriptive-profile-owner:job-1",
        3600,
        json.dumps({"dataset_id": "dataset-1", "owner_id": "owner-1"}),
    )
    jobs = DescriptiveProfileJobs(fake_redis)

    with pytest.raises(HTTPException) as error:
        jobs.status("dataset-1", "owner-2", "job-1")

    assert error.value.status_code == 404
