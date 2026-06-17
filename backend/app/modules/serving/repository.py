from typing import Protocol

from app.modules.serving.domain import BatchScoreJob, Deployment


class ServingRepository(Protocol):
    def add_deployment(self, deployment: Deployment) -> Deployment:
        ...

    def list_deployments(self, owner_id: str) -> list[Deployment]:
        ...

    def get_deployment(self, deployment_id: str) -> Deployment | None:
        ...

    def add_batch_job(self, job: BatchScoreJob) -> BatchScoreJob:
        ...

    def list_batch_jobs(self, owner_id: str) -> list[BatchScoreJob]:
        ...


class InMemoryServingRepository:
    def __init__(self) -> None:
        self._deployments: dict[str, Deployment] = {}
        self._batch_jobs: dict[str, BatchScoreJob] = {}

    def add_deployment(self, deployment: Deployment) -> Deployment:
        self._deployments[deployment.id] = deployment
        return deployment

    def list_deployments(self, owner_id: str) -> list[Deployment]:
        return [deployment for deployment in self._deployments.values() if deployment.owner_id == owner_id]

    def get_deployment(self, deployment_id: str) -> Deployment | None:
        return self._deployments.get(deployment_id)

    def add_batch_job(self, job: BatchScoreJob) -> BatchScoreJob:
        self._batch_jobs[job.id] = job
        return job

    def list_batch_jobs(self, owner_id: str) -> list[BatchScoreJob]:
        return [job for job in self._batch_jobs.values() if job.owner_id == owner_id]
