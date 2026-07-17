from uuid import uuid4

from app.core.security import Principal
from app.modules.exports.domain import ExportJob
from app.modules.exports.repository import ExportRepository, InMemoryExportRepository
from app.modules.exports.schemas import ExportRequest
from fastapi import HTTPException
from app.modules.datasets.repository import PostgresDatasetRepository
from app.modules.models.service import ModelService
from app.modules.sharing.domain import BusinessCaseAccessRole, ResourceAccessRole, ResourceKind
from app.modules.sharing.policy import access_policy


class ExportService:
    def __init__(self, repository: ExportRepository | None = None) -> None:
        self.repository = repository or InMemoryExportRepository()
        self.datasets = PostgresDatasetRepository()
        self.models = ModelService()

    def create_export(self, payload: ExportRequest, principal: Principal) -> ExportJob:
        owner_id = principal.user_id
        if payload.resource_kind in {"dataset", "data_view"}:
            asset = self.datasets.get(payload.resource_id)
            if asset is None:
                raise HTTPException(status_code=404, detail="Resource not found")
            access_policy.require_resource(principal, ResourceKind.DATA_VIEW if asset.source_type.value == "view" else ResourceKind.DATASET,
                                           asset.id, asset.owner_id, ResourceAccessRole.READER)
            owner_id = asset.owner_id
        elif payload.resource_kind == "model":
            model = self.models.get_model(payload.resource_id, principal)
            access_policy.require_business_case(principal, model.business_case_id, BusinessCaseAccessRole.READER)
            owner_id = model.owner_id
        else:
            raise HTTPException(status_code=422, detail="Unsupported export resource kind")
        job = ExportJob(
            id=str(uuid4()),
            owner_id=owner_id,
            resource_kind=payload.resource_kind,
            resource_id=payload.resource_id,
            format=payload.format,
            options=dict(payload.options),
            output_uri=f"s3://exports/{owner_id}/{payload.resource_kind}/{payload.resource_id}",
        )
        return self.repository.add(job)

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
            except HTTPException:
                continue
        return visible
