from fastapi import APIRouter, Depends, Header, Query

from app.core.security import Principal, require_user
from app.modules.serving.schemas import (
    DeploymentCreate,
    ChallengerReplayCreate,
    ChallengerReplayRead,
    DeploymentRead,
    DeploymentRevisionCreate,
    DeploymentRevisionRead,
    InferencePage,
    InferenceDetail,
    ScoreRequest,
    ScoreResponse,
)
from app.modules.serving.service import ServingService

router = APIRouter(prefix="/serving", tags=["serving"])
service = ServingService()


def _deployment_read(deployment) -> DeploymentRead:
    active = service.repository.get_revision(deployment.active_revision_id)
    return DeploymentRead(
        **DeploymentRead.model_validate(deployment).model_dump(exclude={"active_revision"}),
        active_revision=(DeploymentRevisionRead.model_validate(active) if active else None),
    )


@router.post("/deployments", response_model=DeploymentRead, status_code=201)
def create_deployment(
    payload: DeploymentCreate,
    principal: Principal = Depends(require_user),
) -> DeploymentRead:
    return _deployment_read(service.create_deployment(payload, principal))


@router.get("/deployments", response_model=list[DeploymentRead])
def list_deployments(principal: Principal = Depends(require_user)) -> list[DeploymentRead]:
    return [_deployment_read(item) for item in service.list_deployments(principal)]


@router.get("/deployments/{deployment_id}", response_model=DeploymentRead)
def get_deployment(deployment_id: str, principal: Principal = Depends(require_user)) -> DeploymentRead:
    return _deployment_read(service.get_deployment(deployment_id, principal))


@router.get("/deployments/{deployment_id}/revisions", response_model=list[DeploymentRevisionRead])
def list_revisions(
    deployment_id: str,
    principal: Principal = Depends(require_user),
) -> list[DeploymentRevisionRead]:
    return [DeploymentRevisionRead.model_validate(item) for item in service.list_revisions(deployment_id, principal)]


@router.post("/deployments/{deployment_id}/revisions", response_model=DeploymentRevisionRead, status_code=201)
def create_revision(
    deployment_id: str,
    payload: DeploymentRevisionCreate,
    principal: Principal = Depends(require_user),
) -> DeploymentRevisionRead:
    return DeploymentRevisionRead.model_validate(service.create_revision(deployment_id, payload, principal))


@router.post("/deployments/{deployment_id}/predictions", response_model=ScoreResponse)
def score_online(
    deployment_id: str,
    payload: ScoreRequest,
    principal: Principal = Depends(require_user),
    correlation_id: str = Header(default="", alias="X-Correlation-ID"),
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
) -> ScoreResponse:
    return service.score(
        deployment_id,
        payload.instances,
        principal,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
    )


# Compatibility alias for the original prototype. New clients use /predictions.
@router.post("/deployments/{deployment_id}/score", response_model=ScoreResponse, deprecated=True)
def score_online_legacy(
    deployment_id: str,
    payload: ScoreRequest,
    principal: Principal = Depends(require_user),
    correlation_id: str = Header(default="", alias="X-Correlation-ID"),
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
) -> ScoreResponse:
    return service.score(deployment_id, payload.instances, principal, correlation_id=correlation_id, idempotency_key=idempotency_key)


@router.post(
    "/deployments/{deployment_id}/challengers/{model_id}/predictions",
    response_model=ScoreResponse,
)
def score_challenger(
    deployment_id: str,
    model_id: str,
    payload: ScoreRequest,
    principal: Principal = Depends(require_user),
    correlation_id: str = Header(default="", alias="X-Correlation-ID"),
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
) -> ScoreResponse:
    return service.score(
        deployment_id,
        payload.instances,
        principal,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        challenger_model_id=model_id,
    )


@router.get("/deployments/{deployment_id}/inference-log", response_model=InferencePage)
def inference_log(
    deployment_id: str,
    principal: Principal = Depends(require_user),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str = Query(default=""),
    record_id: str = Query(default="", max_length=512),
) -> InferencePage:
    return service.inference_history(
        deployment_id,
        principal,
        limit=limit,
        cursor=cursor,
        record_id=record_id,
    )


@router.get(
    "/deployments/{deployment_id}/inference-log/{request_id}",
    response_model=InferenceDetail,
)
def inference_log_detail(
    deployment_id: str,
    request_id: str,
    principal: Principal = Depends(require_user),
) -> InferenceDetail:
    return service.inference_detail(deployment_id, request_id, principal)


@router.post(
    "/deployments/{deployment_id}/challenger-replays",
    response_model=ChallengerReplayRead,
    status_code=202,
)
def create_challenger_replay(
    deployment_id: str,
    payload: ChallengerReplayCreate,
    principal: Principal = Depends(require_user),
) -> ChallengerReplayRead:
    return ChallengerReplayRead.model_validate(service.create_replay(deployment_id, payload, principal))


@router.get(
    "/deployments/{deployment_id}/challenger-replays",
    response_model=list[ChallengerReplayRead],
)
def list_challenger_replays(
    deployment_id: str,
    principal: Principal = Depends(require_user),
) -> list[ChallengerReplayRead]:
    return [ChallengerReplayRead.model_validate(item) for item in service.list_replays(deployment_id, principal)]
