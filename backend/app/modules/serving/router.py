from fastapi import APIRouter, Depends

from app.core.security import Principal, require_user
from app.modules.serving.schemas import (
    BatchScoreJobRead,
    BatchScoreRequest,
    DeploymentCreate,
    DeploymentRead,
    ScoreRequest,
    ScoreResponse,
)
from app.modules.serving.service import ServingService

router = APIRouter(prefix="/serving", tags=["serving"])
service = ServingService()


@router.post("/deployments", response_model=DeploymentRead, status_code=201)
def create_deployment(
    payload: DeploymentCreate,
    principal: Principal = Depends(require_user),
) -> DeploymentRead:
    return DeploymentRead.model_validate(service.create_deployment(payload, principal))


@router.get("/deployments", response_model=list[DeploymentRead])
def list_deployments(principal: Principal = Depends(require_user)) -> list[DeploymentRead]:
    return [DeploymentRead.model_validate(item) for item in service.list_deployments(principal)]


@router.get("/deployments/{deployment_id}", response_model=DeploymentRead)
def get_deployment(deployment_id: str, principal: Principal = Depends(require_user)) -> DeploymentRead:
    return DeploymentRead.model_validate(service.get_deployment(deployment_id, principal))


@router.post("/deployments/{deployment_id}/score", response_model=ScoreResponse)
def score_online(
    deployment_id: str,
    payload: ScoreRequest,
    principal: Principal = Depends(require_user),
) -> ScoreResponse:
    return service.score(deployment_id, payload.records, principal)


@router.post("/deployments/{deployment_id}/batch-score", response_model=BatchScoreJobRead)
def score_batch(
    deployment_id: str,
    payload: BatchScoreRequest,
    principal: Principal = Depends(require_user),
) -> BatchScoreJobRead:
    return BatchScoreJobRead.model_validate(
        service.enqueue_batch_score(deployment_id, payload, principal)
    )


@router.get("/batch-jobs", response_model=list[BatchScoreJobRead])
def list_batch_jobs(principal: Principal = Depends(require_user)) -> list[BatchScoreJobRead]:
    return [BatchScoreJobRead.model_validate(job) for job in service.list_batch_jobs(principal)]
