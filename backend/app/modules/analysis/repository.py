from typing import Protocol

from app.modules.analysis.domain import AnalysisJob


class AnalysisRepository(Protocol):
    def add(self, job: AnalysisJob) -> AnalysisJob:
        ...

    def list_for_owner(self, owner_id: str) -> list[AnalysisJob]:
        ...

    def get(self, job_id: str) -> AnalysisJob | None:
        ...


class InMemoryAnalysisRepository:
    def __init__(self) -> None:
        self._items: dict[str, AnalysisJob] = {}

    def add(self, job: AnalysisJob) -> AnalysisJob:
        self._items[job.id] = job
        return job

    def list_for_owner(self, owner_id: str) -> list[AnalysisJob]:
        return [job for job in self._items.values() if job.owner_id == owner_id]

    def get(self, job_id: str) -> AnalysisJob | None:
        return self._items.get(job_id)
