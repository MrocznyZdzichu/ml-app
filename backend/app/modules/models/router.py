from fastapi import APIRouter, Depends, Query

from app.core.security import Principal, require_user
from app.modules.models.schemas import (
    ModelArtifactRead,
    ModelFamilyRead,
    DatasetLineageRead,
    PromoteModelRequest,
    TrainingJobRead,
    TrainingRequest,
)
from app.modules.models.service import ModelService
from app.modules.business_cases.lineage import DatasetLineageResolver
from app.modules.models.domain import ModelStage
from app.shared.pagination import OffsetPage

router = APIRouter(prefix="/models", tags=["models"])
service = ModelService()
lineage_resolver = DatasetLineageResolver()


@router.post("/training-jobs", response_model=TrainingJobRead, status_code=201)
def train_model(
    payload: TrainingRequest,
    principal: Principal = Depends(require_user),
) -> TrainingJobRead:
    return TrainingJobRead.model_validate(service.start_training(payload, principal))


@router.get("/training-jobs", response_model=list[TrainingJobRead])
def list_training_jobs(principal: Principal = Depends(require_user)) -> list[TrainingJobRead]:
    return [TrainingJobRead.model_validate(job) for job in service.list_training_jobs(principal)]


@router.get("", response_model=list[ModelArtifactRead])
def list_models(
    summary: bool = Query(default=False),
    principal: Principal = Depends(require_user),
) -> list[ModelArtifactRead]:
    models = service.list_model_summaries(principal) if summary else service.list_models(principal)
    return [ModelArtifactRead.model_validate(model) for model in models]


@router.get("/page", response_model=OffsetPage[ModelFamilyRead])
def page_model_families(
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str = Query(default="", max_length=200),
    business_case_id: str = Query(default="", max_length=64),
    stage: ModelStage | None = Query(default=None),
    pipeline_id: str = Query(default="", max_length=64),
    pipeline_type: str = Query(default="", max_length=64),
    principal: Principal = Depends(require_user),
) -> OffsetPage[ModelFamilyRead]:
    items, total = service.page_model_families(
        principal,
        limit=limit,
        offset=offset,
        search=search,
        business_case_id=business_case_id,
        stage=stage.value if stage else "",
        pipeline_id=pipeline_id,
        pipeline_type=pipeline_type,
    )
    return OffsetPage[ModelFamilyRead].build(
        [
            ModelFamilyRead(
                latest=ModelArtifactRead.model_validate(model),
                version_count=version_count,
            )
            for model, version_count in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{logical_id}/versions", response_model=list[ModelArtifactRead])
def list_model_versions(
    logical_id: str,
    principal: Principal = Depends(require_user),
) -> list[ModelArtifactRead]:
    return [
        ModelArtifactRead.model_validate(model)
        for model in service.list_versions(logical_id, principal)
    ]


@router.get(
    "/{logical_id}/versions/page",
    response_model=OffsetPage[ModelArtifactRead],
)
def page_model_versions(
    logical_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(require_user),
) -> OffsetPage[ModelArtifactRead]:
    items, total = service.page_versions(
        logical_id,
        principal,
        limit=limit,
        offset=offset,
    )
    return OffsetPage[ModelArtifactRead].build(
        [ModelArtifactRead.model_validate(model) for model in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{model_id}", response_model=ModelArtifactRead)
def get_model(model_id: str, principal: Principal = Depends(require_user)) -> ModelArtifactRead:
    return ModelArtifactRead.model_validate(service.get_model(model_id, principal))


@router.get("/{model_id}/data-lineage", response_model=list[DatasetLineageRead])
def get_model_data_lineage(
    model_id: str,
    principal: Principal = Depends(require_user),
) -> list[DatasetLineageRead]:
    model = service.get_model(model_id, principal)
    artifact = service.artifacts.get_artifact(model.id)
    if artifact is None:
        return []
    return [
        DatasetLineageRead.model_validate(item)
        for item in lineage_resolver.resolve(artifact)
    ]


@router.patch("/{model_id}/stage", response_model=ModelArtifactRead)
def update_model_stage(
    model_id: str,
    payload: PromoteModelRequest,
    principal: Principal = Depends(require_user),
) -> ModelArtifactRead:
    return ModelArtifactRead.model_validate(service.promote_model(model_id, payload, principal))


@router.post("/{model_id}/promote", response_model=ModelArtifactRead, deprecated=True)
def promote_model(
    model_id: str,
    payload: PromoteModelRequest,
    principal: Principal = Depends(require_user),
) -> ModelArtifactRead:
    return ModelArtifactRead.model_validate(service.promote_model(model_id, payload, principal))
