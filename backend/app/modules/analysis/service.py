from uuid import uuid4

from fastapi import HTTPException, status

from app.core.security import Principal
from app.modules.analysis.domain import AnalysisJob
from app.modules.analysis.repository import AnalysisRepository, InMemoryAnalysisRepository
from app.modules.analysis.schemas import AnalysisCreate, DescriptiveStatsResponse
from app.modules.analysis.statistics import describe_records


class AnalysisService:
    def __init__(self, repository: AnalysisRepository | None = None) -> None:
        self.repository = repository or InMemoryAnalysisRepository()

    def create(self, payload: AnalysisCreate, principal: Principal) -> AnalysisJob:
        job = AnalysisJob(
            id=str(uuid4()),
            owner_id=principal.user_id,
            dataset_id=payload.dataset_id,
            kind=payload.kind,
            title=payload.title,
            parameters=dict(payload.parameters),
        )
        return self.repository.add(job)

    def list_jobs(self, principal: Principal) -> list[AnalysisJob]:
        return self.repository.list_for_owner(principal.user_id)

    def get_job(self, job_id: str, principal: Principal) -> AnalysisJob:
        job = self.repository.get(job_id)
        if not job or job.owner_id != principal.user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis job not found")
        return job

    def describe_inline_records(self, records: list[dict]) -> DescriptiveStatsResponse:
        return describe_records(records)
