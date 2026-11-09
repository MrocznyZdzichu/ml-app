from app.core.errors import ResourceNotFoundError
from app.core.security import Principal
from app.modules.exports.domain import ExportJob
from app.modules.exports.repository import ExportRepository, InMemoryExportRepository
from fastapi import HTTPException
from app.modules.datasets.repository import DatasetRepository, PostgresDatasetRepository
from app.modules.models.service import ModelService
from app.modules.sharing.domain import ResourceAccessRole, ResourceKind
from app.modules.sharing.postgres_access import access_policy


class ExportService:
    def __init__(
        self,
        repository: ExportRepository | None = None,
        datasets: DatasetRepository | None = None,
        models: ModelService | None = None,
    ) -> None:
        self.repository = repository or InMemoryExportRepository()
        self.datasets = datasets or PostgresDatasetRepository()
        self.models = models or ModelService()

    def list_exports(self, principal: Principal) -> list[ExportJob]:
        visible: list[ExportJob] = []
        for job in self.repository.list_all():
            try:
                if job.resource_kind in {"dataset", "data_view"}:
                    asset = self.datasets.get(job.resource_id)
                    if asset is None:
                        continue
                    access_policy.require_resource(principal, ResourceKind.DATA_VIEW if asset.source_type.value == "view" else ResourceKind.DATASET,
                                                   asset.id, asset.owner_id, ResourceAccessRole.READER)
                elif job.resource_kind == "model":
                    self.models.get_model(job.resource_id, principal)
                else:
                    continue
                visible.append(job)
            except (HTTPException, ResourceNotFoundError):
                continue
        return visible
