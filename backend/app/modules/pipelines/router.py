from fastapi import APIRouter, Depends, Query

from app.core.security import Principal, require_user
from app.modules.pipelines.schemas import (
    PipelineCreate,
    PipelineRead,
    PipelineRunCreate,
    PipelineRunOutputPreviewRead,
    PipelineRunOutputProfileRead,
    PipelineRunRead,
    PipelineStepTypeRead,
    PipelineVersionRead,
    PipelineVersionUpdate,
)
from app.modules.pipelines.service import PipelineService

router = APIRouter(prefix="/pipelines", tags=["pipelines"])
service = PipelineService()


@router.get("/step-types", response_model=list[PipelineStepTypeRead])
def list_step_types(principal: Principal = Depends(require_user)) -> list[PipelineStepTypeRead]:
    return [PipelineStepTypeRead.model_validate(item) for item in service.list_step_types()]


@router.post("", response_model=PipelineRead, status_code=201)
def create_pipeline(
    payload: PipelineCreate,
    principal: Principal = Depends(require_user),
) -> PipelineRead:
    return PipelineRead.model_validate(service.create_pipeline(payload, principal))


@router.get("", response_model=list[PipelineRead])
def list_pipelines(
    business_case_id: str | None = Query(default=None),
    principal: Principal = Depends(require_user),
) -> list[PipelineRead]:
    return [
        PipelineRead.model_validate(item)
        for item in service.list_pipelines(principal, business_case_id)
    ]


@router.get("/{pipeline_id}", response_model=PipelineRead)
def get_pipeline(
    pipeline_id: str,
    principal: Principal = Depends(require_user),
) -> PipelineRead:
    return PipelineRead.model_validate(service.get_pipeline(pipeline_id, principal))


@router.get("/{pipeline_id}/versions", response_model=list[PipelineVersionRead])
def list_versions(
    pipeline_id: str,
    principal: Principal = Depends(require_user),
) -> list[PipelineVersionRead]:
    return [PipelineVersionRead.model_validate(item) for item in service.list_versions(pipeline_id, principal)]


@router.patch("/{pipeline_id}/versions/draft", response_model=PipelineVersionRead)
def update_draft_version(
    pipeline_id: str,
    payload: PipelineVersionUpdate,
    principal: Principal = Depends(require_user),
) -> PipelineVersionRead:
    return PipelineVersionRead.model_validate(service.update_draft_version(pipeline_id, payload, principal))


@router.post("/{pipeline_id}/versions/draft", response_model=PipelineVersionRead, status_code=201)
def create_next_draft_version(
    pipeline_id: str,
    principal: Principal = Depends(require_user),
) -> PipelineVersionRead:
    return PipelineVersionRead.model_validate(service.create_next_draft_version(pipeline_id, principal))


@router.post("/{pipeline_id}/versions/draft/publish", response_model=PipelineVersionRead)
def publish_draft_version(
    pipeline_id: str,
    principal: Principal = Depends(require_user),
) -> PipelineVersionRead:
    return PipelineVersionRead.model_validate(service.publish_draft_version(pipeline_id, principal))


@router.post("/{pipeline_id}/runs", response_model=PipelineRunRead, status_code=201)
def create_run(
    pipeline_id: str,
    payload: PipelineRunCreate,
    principal: Principal = Depends(require_user),
) -> PipelineRunRead:
    return PipelineRunRead.model_validate(service.create_run(pipeline_id, payload, principal))


@router.get("/{pipeline_id}/runs", response_model=list[PipelineRunRead])
def list_pipeline_runs(
    pipeline_id: str,
    principal: Principal = Depends(require_user),
) -> list[PipelineRunRead]:
    return [PipelineRunRead.model_validate(item) for item in service.list_runs(principal, pipeline_id)]


@router.get("/{pipeline_id}/runs/{run_id}", response_model=PipelineRunRead)
def get_pipeline_run(
    pipeline_id: str,
    run_id: str,
    principal: Principal = Depends(require_user),
) -> PipelineRunRead:
    return PipelineRunRead.model_validate(service.get_run(pipeline_id, run_id, principal))


@router.get("/{pipeline_id}/runs/{run_id}/preview", response_model=PipelineRunOutputPreviewRead)
def preview_pipeline_run_output(
    pipeline_id: str,
    run_id: str,
    output_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(require_user),
) -> PipelineRunOutputPreviewRead:
    return PipelineRunOutputPreviewRead.model_validate(
        service.preview_run_output(
            pipeline_id,
            run_id,
            principal,
            output_id=output_id,
            limit=limit,
            offset=offset,
        )
    )


@router.get("/{pipeline_id}/runs/{run_id}/profile", response_model=PipelineRunOutputProfileRead)
def profile_pipeline_run_output(
    pipeline_id: str,
    run_id: str,
    output_id: str | None = Query(default=None),
    max_columns: int = Query(default=30, ge=1, le=100),
    top_n: int = Query(default=10, ge=1, le=50),
    principal: Principal = Depends(require_user),
) -> PipelineRunOutputProfileRead:
    return PipelineRunOutputProfileRead.model_validate(
        service.profile_run_output(
            pipeline_id,
            run_id,
            principal,
            output_id=output_id,
            max_columns=max_columns,
            top_n=top_n,
        )
    )
