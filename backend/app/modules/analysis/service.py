from uuid import uuid4

from fastapi import HTTPException, status

from app.core.security import Principal
from app.modules.analysis.domain import AnalysisJob
from app.modules.analysis.repository import AnalysisRepository, InMemoryAnalysisRepository
from app.modules.analysis.schemas import AnalysisCreate, DescriptiveStatsResponse
from app.modules.analysis.statistics import describe_records
from app.modules.datasets.repository import PostgresDatasetRepository
from app.modules.sharing.domain import ResourceAccessRole, ResourceKind
from app.modules.sharing.policy import access_policy


class AnalysisService:
    def __init__(self, repository: AnalysisRepository | None = None) -> None:
        self.repository = repository or InMemoryAnalysisRepository()
        self.datasets = PostgresDatasetRepository()

    def create(self, payload: AnalysisCreate, principal: Principal) -> AnalysisJob:
        asset = self.datasets.get(payload.dataset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="Dataset not found")
        access_policy.require_resource(principal, ResourceKind.DATA_VIEW if asset.source_type.value == "view" else ResourceKind.DATASET,
                                       asset.id, asset.owner_id, ResourceAccessRole.EDITOR)
        job = AnalysisJob(
            id=str(uuid4()),
            owner_id=asset.owner_id,
            dataset_id=payload.dataset_id,
            kind=payload.kind,
            title=payload.title,
            parameters=dict(payload.parameters),
        )
        return self.repository.add(job)

    def list_jobs(self, principal: Principal) -> list[AnalysisJob]:
        return [job for job in self.repository.list_all() if self._can_read(job, principal)]

    def get_job(self, job_id: str, principal: Principal) -> AnalysisJob:
        job = self.repository.get(job_id)
        if not job or not self._can_read(job, principal):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis job not found")
        return job

    def _can_read(self, job: AnalysisJob, principal: Principal) -> bool:
        asset = self.datasets.get(job.dataset_id)
        if asset is None:
            return job.owner_id == principal.user_id or principal.is_administrator
        return access_policy.resource_role(
            principal,
            ResourceKind.DATA_VIEW if asset.source_type.value == "view" else ResourceKind.DATASET,
            asset.id,
            asset.owner_id,
        ) is not None

    def describe_inline_records(self, records: list[dict]) -> DescriptiveStatsResponse:
        return describe_records(records)
