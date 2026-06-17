from uuid import uuid4

from app.core.security import Principal
from app.modules.exports.domain import ExportJob
from app.modules.exports.repository import ExportRepository, InMemoryExportRepository
from app.modules.exports.schemas import ExportRequest


class ExportService:
    def __init__(self, repository: ExportRepository | None = None) -> None:
        self.repository = repository or InMemoryExportRepository()

    def create_export(self, payload: ExportRequest, principal: Principal) -> ExportJob:
        job = ExportJob(
            id=str(uuid4()),
            owner_id=principal.user_id,
            resource_kind=payload.resource_kind,
            resource_id=payload.resource_id,
            format=payload.format,
            options=dict(payload.options),
            output_uri=f"s3://exports/{principal.user_id}/{payload.resource_kind}/{payload.resource_id}",
        )
        return self.repository.add(job)

    def list_exports(self, principal: Principal) -> list[ExportJob]:
        return self.repository.list_for_owner(principal.user_id)
