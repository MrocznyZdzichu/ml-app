from fastapi import APIRouter, Depends

from app.core.security import Principal, require_user
from app.modules.analysis.schemas import (
    AnalysisCreate,
    AnalysisRead,
    DescriptiveStatsResponse,
    InlineRecordsRequest,
)
from app.modules.analysis.service import AnalysisService

router = APIRouter(prefix="/analysis", tags=["analysis"])
service = AnalysisService()


@router.post("", response_model=AnalysisRead, status_code=201)
def create_analysis(
    payload: AnalysisCreate,
    principal: Principal = Depends(require_user),
) -> AnalysisRead:
    return AnalysisRead.model_validate(service.create(payload, principal))


@router.get("", response_model=list[AnalysisRead])
def list_analysis(principal: Principal = Depends(require_user)) -> list[AnalysisRead]:
    return [AnalysisRead.model_validate(job) for job in service.list_jobs(principal)]


@router.get("/{analysis_id}", response_model=AnalysisRead)
def get_analysis(analysis_id: str, principal: Principal = Depends(require_user)) -> AnalysisRead:
    return AnalysisRead.model_validate(service.get_job(analysis_id, principal))


@router.post("/descriptive-stats", response_model=DescriptiveStatsResponse)
def descriptive_stats(
    payload: InlineRecordsRequest,
    _principal: Principal = Depends(require_user),
) -> DescriptiveStatsResponse:
    return service.describe_inline_records(payload.records)
