import json

import pytest
from fastapi import HTTPException

from app.core.errors import ResourceNotFoundError
from app.core.identity import Principal
from app.modules.analysis import dataset_jobs
from app.modules.analysis.profile_jobs import DescriptiveProfileJobs
from app.modules.analysis.time_series_jobs import TimeSeriesAnalysisJobs
from app.modules.datasets.domain import DataAsset, SourceType
from app.modules.datasets.repository import InMemoryDatasetRepository
from app.modules.datasets.schemas import FullDescriptiveProfileRequest, TimeSeriesAnalysisRequest
from app.modules.datasets.service import DatasetService


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
    monkeypatch.setattr(dataset_jobs, "uuid4", lambda: "job-1")
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

    with pytest.raises(ResourceNotFoundError, match="Profile job not found"):
        jobs.status("dataset-1", "owner-2", "job-1", check_dataset_access=pytest.fail)


@pytest.mark.parametrize("job_kind", ["descriptive_profile", "time_series_analysis"])
def test_analysis_jobs_pin_logical_dataset_at_submission(job_kind: str) -> None:
    repository = InMemoryDatasetRepository()
    repository.add_version(DataAsset(
        id="version-1", logical_id="family", owner_id="owner-1",
        name="First version", source_type=SourceType.FILE, format="csv",
    ))
    service = DatasetService(repository)
    redis = FakeRedis()
    queue = FakeTaskQueue()
    service.profile_jobs = DescriptiveProfileJobs(redis, queue)
    service.time_series_jobs = TimeSeriesAnalysisJobs(redis, queue)
    principal = Principal(user_id="owner-1", email="owner@example.com", display_name="Owner")
    if job_kind == "descriptive_profile":
        job = service.start_descriptive_profile("family", FullDescriptiveProfileRequest(), principal)
        read_status = service.descriptive_profile_status
    else:
        job = service.start_time_series_analysis(
            "family", TimeSeriesAnalysisRequest(time_column="timestamp", value_column="value"), principal
        )
        read_status = service.time_series_analysis_status
    assert queue.submitted["args"][0] == "version-1"

    repository.add_version(DataAsset(
        id="version-2", logical_id="family", owner_id="owner-1",
        name="Second version", source_type=SourceType.FILE, format="csv",
    ))
    repository.get("version-1").owner_id = "another-owner"

    with pytest.raises(HTTPException) as error:
        read_status("family", job["job_id"], principal)
    assert error.value.status_code == 404
    assert service.get_asset("family", principal).id == "version-2"
