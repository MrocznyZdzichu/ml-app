from fastapi import APIRouter, Depends, Header, Query

from app.core.security import Principal, require_user
from app.modules.serving.schemas import (
    DeploymentCreate,
    ChallengerReplayCreate,
    ChallengerReplayRead,
    DeploymentRead,
    DeploymentModelOptionRead,
    DeploymentRollbackRequest,
    DeploymentRevisionCreate,
    DeploymentRevisionRead,
    DeploymentStatusUpdate,
    InferencePage,
    InferenceSummaryPage,
    InferenceDetail,
    InferenceInputContractRead,
    ModelServingUsageRead,
    OnlineMonitoringArchiveRequest,
    OnlineMonitoringRunCreate,
    OnlineMonitoringRunRead,
    ScoreRequest,
    ScoreResponse,
)
from app.modules.serving.service import ServingService
from app.modules.serving.monitoring import OnlineMonitoringService

router = APIRouter(prefix="/serving", tags=["serving"])
service = ServingService()
monitoring_service = OnlineMonitoringService(repository=service.repository, models=service.models)


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
def list_deployments(
    include_archived: bool = Query(default=False),
    principal: Principal = Depends(require_user),
) -> list[DeploymentRead]:
    return [_deployment_read(item) for item in service.list_deployments(principal, include_archived=include_archived)]


@router.get("/model-families/{logical_id}/usage", response_model=list[ModelServingUsageRead])
def list_model_family_usage(
    logical_id: str,
    principal: Principal = Depends(require_user),
) -> list[ModelServingUsageRead]:
    return [ModelServingUsageRead.model_validate(item) for item in service.list_model_family_usage(logical_id, principal)]


@router.get("/deployments/{deployment_id}", response_model=DeploymentRead)
def get_deployment(deployment_id: str, principal: Principal = Depends(require_user)) -> DeploymentRead:
    return _deployment_read(service.get_deployment(deployment_id, principal))


@router.get(
    "/deployments/{deployment_id}/input-contract",
    response_model=InferenceInputContractRead,
)
def get_input_contract(
    deployment_id: str,
    challenger_model_id: str = Query(default="", max_length=64),
    principal: Principal = Depends(require_user),
) -> InferenceInputContractRead:
    return InferenceInputContractRead.model_validate(
        service.input_contract(deployment_id, principal, challenger_model_id=challenger_model_id)
    )


@router.get(
    "/deployments/{deployment_id}/model-options",
    response_model=list[DeploymentModelOptionRead],
)
def get_deployment_model_options(
    deployment_id: str,
    principal: Principal = Depends(require_user),
) -> list[DeploymentModelOptionRead]:
    return [
        DeploymentModelOptionRead.model_validate(item)
        for item in service.deployment_model_options(deployment_id, principal)
    ]


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


@router.post("/deployments/{deployment_id}/status", response_model=DeploymentRead)
def update_deployment_status(
    deployment_id: str,
    payload: DeploymentStatusUpdate,
    principal: Principal = Depends(require_user),
) -> DeploymentRead:
    return _deployment_read(service.set_deployment_status(
        deployment_id, payload.status, payload.reason, principal
    ))


@router.post(
    "/deployments/{deployment_id}/revisions/{revision_id}/rollback",
    response_model=DeploymentRevisionRead,
    status_code=201,
)
def rollback_deployment(
    deployment_id: str,
    revision_id: str,
    payload: DeploymentRollbackRequest,
    principal: Principal = Depends(require_user),
) -> DeploymentRevisionRead:
    return DeploymentRevisionRead.model_validate(service.rollback_deployment(
        deployment_id, revision_id, payload.reason, principal
    ))


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
    "/deployments/{deployment_id}/inference-log-summary",
    response_model=InferenceSummaryPage,
)
def inference_log_summary(
    deployment_id: str,
    principal: Principal = Depends(require_user),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str = Query(default=""),
    record_id: str = Query(default="", max_length=512),
) -> InferenceSummaryPage:
    return service.inference_history_summary(
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


@router.post(
    "/deployments/{deployment_id}/monitoring-runs",
    response_model=OnlineMonitoringRunRead,
    status_code=202,
)
def create_online_monitoring_run(
    deployment_id: str,
    payload: OnlineMonitoringRunCreate,
    principal: Principal = Depends(require_user),
) -> OnlineMonitoringRunRead:
    return OnlineMonitoringRunRead.model_validate(
        monitoring_service.create_run(deployment_id, payload, principal)
    )


@router.get(
    "/deployments/{deployment_id}/monitoring-runs",
    response_model=list[OnlineMonitoringRunRead],
)
def list_deployment_monitoring_runs(
    deployment_id: str,
    limit: int = Query(default=100, ge=1, le=200),
    include_archived: bool = Query(default=False),
    principal: Principal = Depends(require_user),
) -> list[OnlineMonitoringRunRead]:
    return [
        OnlineMonitoringRunRead.model_validate(item)
        for item in monitoring_service.list_runs(
            principal, deployment_id=deployment_id, limit=limit,
            include_archived=include_archived,
        )
    ]


@router.get("/monitoring-runs", response_model=list[OnlineMonitoringRunRead])
def list_online_monitoring_runs(
    limit: int = Query(default=200, ge=1, le=200),
    include_archived: bool = Query(default=False),
    principal: Principal = Depends(require_user),
) -> list[OnlineMonitoringRunRead]:
    return [
        OnlineMonitoringRunRead.model_validate(item)
        for item in monitoring_service.list_runs(
            principal, limit=limit, include_archived=include_archived
        )
    ]


@router.post(
    "/deployments/{deployment_id}/monitoring-runs/archive",
    response_model=dict[str, int],
)
def archive_deployment_monitoring_history(
    deployment_id: str,
    payload: OnlineMonitoringArchiveRequest,
    principal: Principal = Depends(require_user),
) -> dict[str, int]:
    return {
        "archived_run_count": monitoring_service.archive_history(
            deployment_id, payload.reason, principal
        )
    }


@router.post(
    "/monitoring-runs/{run_id}/archive",
    response_model=OnlineMonitoringRunRead,
)
def archive_online_monitoring_run(
    run_id: str,
    payload: OnlineMonitoringArchiveRequest,
    principal: Principal = Depends(require_user),
) -> OnlineMonitoringRunRead:
    return OnlineMonitoringRunRead.model_validate(
        monitoring_service.archive_run(run_id, payload.reason, principal)
    )


@router.get("/monitoring-runs/{run_id}", response_model=OnlineMonitoringRunRead)
def get_online_monitoring_run(
    run_id: str,
    principal: Principal = Depends(require_user),
) -> OnlineMonitoringRunRead:
    return OnlineMonitoringRunRead.model_validate(
        monitoring_service.get_run(run_id, principal)
    )
