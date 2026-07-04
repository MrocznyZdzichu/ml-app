from fastapi import APIRouter, Depends

from app.core.security import Principal, require_user
from app.modules.models.schemas import (
    ModelArtifactRead,
    DatasetLineageRead,
    PromoteModelRequest,
    TrainingJobRead,
    TrainingRequest,
)
from app.modules.models.service import ModelService
from app.modules.business_cases.lineage import DatasetLineageResolver

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
def list_models(principal: Principal = Depends(require_user)) -> list[ModelArtifactRead]:
    return [ModelArtifactRead.model_validate(model) for model in service.list_models(principal)]


@router.get("/{logical_id}/versions", response_model=list[ModelArtifactRead])
def list_model_versions(
    logical_id: str,
    principal: Principal = Depends(require_user),
) -> list[ModelArtifactRead]:
    return [
        ModelArtifactRead.model_validate(model)
        for model in service.list_versions(logical_id, principal)
    ]


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


@router.post("/{model_id}/promote", response_model=ModelArtifactRead)
def promote_model(
    model_id: str,
    payload: PromoteModelRequest,
    principal: Principal = Depends(require_user),
) -> ModelArtifactRead:
    return ModelArtifactRead.model_validate(service.promote_model(model_id, payload, principal))
