from fastapi import APIRouter, Depends, Query

from app.core.security import Principal, require_user
from app.modules.pipelines.schemas import (
    PipelineCopy,
    PipelineCreate,
    PipelineRead,
    PipelineRunCreate,
    PipelineRunOutputPreviewRead,
    PipelineRunOutputProfileRead,
    PipelineRunRead,
    PipelineRunSummaryRead,
    PipelineRunDetailsRead,
    PipelineStepTypeRead,
    PipelineStepRunRead,
    PipelineUpdate,
    PipelineVersionRead,
    PipelineVersionUpdate,
)
from app.modules.pipelines.service import PipelineService
from app.modules.pipelines.modeling_catalog import training_catalog
from app.modules.pipelines.domain import PipelineStatus
from app.shared.pagination import OffsetPage

router = APIRouter(prefix="/pipelines", tags=["pipelines"])
service = PipelineService()


@router.get("/step-types", response_model=list[PipelineStepTypeRead])
def list_step_types(principal: Principal = Depends(require_user)) -> list[PipelineStepTypeRead]:
    return [PipelineStepTypeRead.model_validate(item) for item in service.list_step_types()]


@router.get("/model-training/catalog")
def get_model_training_catalog(
    principal: Principal = Depends(require_user),
) -> dict:
    return training_catalog()


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


@router.get("/page", response_model=OffsetPage[PipelineRead])
def page_pipelines(
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str = Query(default="", max_length=200),
    business_case_id: str | None = Query(default=None),
    pipeline_type: str = Query(default="", max_length=64),
    pipeline_template: str = Query(default="", max_length=64),
    pipeline_status: PipelineStatus | None = Query(default=None, alias="status"),
    include_deprecated: bool = Query(default=True),
    principal: Principal = Depends(require_user),
) -> OffsetPage[PipelineRead]:
    items, total = service.page_pipelines(
        principal,
        limit=limit,
        offset=offset,
        search=search,
        business_case_id=business_case_id,
        pipeline_type=pipeline_type,
        pipeline_template=pipeline_template,
        pipeline_status=pipeline_status.value if pipeline_status else "",
        include_deprecated=include_deprecated,
    )
    return OffsetPage[PipelineRead].build(
        [PipelineRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{pipeline_id}", response_model=PipelineRead)
def get_pipeline(
    pipeline_id: str,
    principal: Principal = Depends(require_user),
) -> PipelineRead:
    return PipelineRead.model_validate(service.get_pipeline(pipeline_id, principal))


@router.patch("/{pipeline_id}", response_model=PipelineRead)
def update_pipeline(
    pipeline_id: str,
    payload: PipelineUpdate,
    principal: Principal = Depends(require_user),
) -> PipelineRead:
    return PipelineRead.model_validate(service.update_pipeline(pipeline_id, payload, principal))


@router.post("/{pipeline_id}/copy", response_model=PipelineRead, status_code=201)
def copy_pipeline(
    pipeline_id: str,
    payload: PipelineCopy,
    principal: Principal = Depends(require_user),
) -> PipelineRead:
    return PipelineRead.model_validate(service.copy_pipeline(pipeline_id, payload, principal))


@router.delete("/{pipeline_id}")
def delete_pipeline(
    pipeline_id: str,
    principal: Principal = Depends(require_user),
) -> dict[str, str]:
    return {"action": service.delete_pipeline(pipeline_id, principal)}


@router.get("/{pipeline_id}/versions", response_model=list[PipelineVersionRead])
def list_versions(
    pipeline_id: str,
    principal: Principal = Depends(require_user),
) -> list[PipelineVersionRead]:
    return [PipelineVersionRead.model_validate(item) for item in service.list_versions(pipeline_id, principal)]


@router.get(
    "/{pipeline_id}/versions/page",
    response_model=OffsetPage[PipelineVersionRead],
)
def page_versions(
    pipeline_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: str = Query(default="", pattern="^(|draft|published)$"),
    principal: Principal = Depends(require_user),
) -> OffsetPage[PipelineVersionRead]:
    items, total = service.page_versions(
        pipeline_id,
        principal,
        limit=limit,
        offset=offset,
        version_status=status,
    )
    return OffsetPage[PipelineVersionRead].build(
        [PipelineVersionRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


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
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(require_user),
) -> list[PipelineRunRead]:
    return [
        PipelineRunRead.model_validate(item)
        for item in service.list_runs(principal, pipeline_id, limit=limit, offset=offset)
    ]


@router.get("/runs/history", response_model=list[PipelineRunSummaryRead])
def list_run_history(
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(require_user),
) -> list[PipelineRunSummaryRead]:
    return [
        PipelineRunSummaryRead.model_validate(item)
        for item in service.list_run_summaries(principal, limit=limit, offset=offset)
    ]


@router.get("/runs/history/page", response_model=OffsetPage[PipelineRunSummaryRead])
def page_run_history(
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str = Query(default="", max_length=200),
    status: str = Query(default="", max_length=30),
    pipeline_id: str = Query(default="", max_length=64),
    pipeline_version_id: str = Query(default="", max_length=64),
    business_case_id: str = Query(default="", max_length=64),
    trigger_type: str = Query(default="", max_length=50),
    dry_run: bool | None = Query(default=None),
    principal: Principal = Depends(require_user),
) -> OffsetPage[PipelineRunSummaryRead]:
    runs, total = service.page_run_summaries(
        principal,
        limit=limit,
        offset=offset,
        search=search,
        run_status=status,
        pipeline_id=pipeline_id,
        pipeline_version_id=pipeline_version_id,
        business_case_id=business_case_id,
        trigger_type=trigger_type,
        dry_run=dry_run,
    )
    return OffsetPage[PipelineRunSummaryRead].build(
        items=[PipelineRunSummaryRead.model_validate(item) for item in runs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{pipeline_id}/runs/{run_id}", response_model=PipelineRunRead)
def get_pipeline_run(
    pipeline_id: str,
    run_id: str,
    principal: Principal = Depends(require_user),
) -> PipelineRunRead:
    return PipelineRunRead.model_validate(service.get_run(pipeline_id, run_id, principal))


@router.get("/{pipeline_id}/runs/{run_id}/status", response_model=PipelineRunSummaryRead)
def get_pipeline_run_status(
    pipeline_id: str,
    run_id: str,
    principal: Principal = Depends(require_user),
) -> PipelineRunSummaryRead:
    return PipelineRunSummaryRead.model_validate(
        service.get_run_status(pipeline_id, run_id, principal)
    )


@router.get("/{pipeline_id}/runs/{run_id}/details", response_model=PipelineRunDetailsRead)
def get_pipeline_run_details(
    pipeline_id: str,
    run_id: str,
    principal: Principal = Depends(require_user),
) -> PipelineRunDetailsRead:
    return PipelineRunDetailsRead.model_validate(
        service.get_run_details(pipeline_id, run_id, principal)
    )


@router.post("/{pipeline_id}/runs/{run_id}/cancel", response_model=PipelineRunRead)
def cancel_pipeline_run(
    pipeline_id: str,
    run_id: str,
    principal: Principal = Depends(require_user),
) -> PipelineRunRead:
    return PipelineRunRead.model_validate(service.cancel_run(pipeline_id, run_id, principal))


@router.post("/{pipeline_id}/runs/{run_id}/retry", response_model=PipelineRunRead, status_code=201)
def retry_pipeline_run(
    pipeline_id: str,
    run_id: str,
    principal: Principal = Depends(require_user),
) -> PipelineRunRead:
    return PipelineRunRead.model_validate(service.retry_run(pipeline_id, run_id, principal))


@router.get("/{pipeline_id}/runs/{run_id}/steps", response_model=list[PipelineStepRunRead])
def list_pipeline_step_runs(
    pipeline_id: str,
    run_id: str,
    principal: Principal = Depends(require_user),
) -> list[PipelineStepRunRead]:
    return [
        PipelineStepRunRead.model_validate(item)
        for item in service.list_step_runs(pipeline_id, run_id, principal)
    ]


@router.get("/{pipeline_id}/runs/{run_id}/preview", response_model=PipelineRunOutputPreviewRead)
def preview_pipeline_run_output(
    pipeline_id: str,
    run_id: str,
    output_id: str | None = Query(default=None),
    pipeline_step_id: str | None = Query(default=None),
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
            pipeline_step_id=pipeline_step_id,
            limit=limit,
            offset=offset,
        )
    )


@router.get("/{pipeline_id}/runs/{run_id}/profile", response_model=PipelineRunOutputProfileRead)
def profile_pipeline_run_output(
    pipeline_id: str,
    run_id: str,
    output_id: str | None = Query(default=None),
    pipeline_step_id: str | None = Query(default=None),
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
            pipeline_step_id=pipeline_step_id,
            max_columns=max_columns,
            top_n=top_n,
        )
    )
