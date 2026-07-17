from typing import Protocol

from app.modules.exports.domain import ExportJob


class ExportRepository(Protocol):
    def add(self, job: ExportJob) -> ExportJob:
        ...

    def list_for_owner(self, owner_id: str) -> list[ExportJob]:
        ...

    def list_all(self) -> list[ExportJob]:
        ...


class InMemoryExportRepository:
    def __init__(self) -> None:
        self._items: dict[str, ExportJob] = {}

    def add(self, job: ExportJob) -> ExportJob:
        self._items[job.id] = job
        return job

    def list_for_owner(self, owner_id: str) -> list[ExportJob]:
        return [job for job in self._items.values() if job.owner_id == owner_id]

    def list_all(self) -> list[ExportJob]:
        return list(self._items.values())
