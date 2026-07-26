from fastapi import APIRouter, Depends, Query

from app.core.security import Principal, require_user
from app.modules.scoring_reports.schemas import (
    DatasetLineageRead,
    ScoringReportFamilyRead,
    ScoringReportRead,
)
from app.modules.scoring_reports.service import ScoringReportService
from app.modules.business_cases.lineage import DatasetLineageResolver
from app.modules.sharing.domain import BusinessCaseAccessRole
from app.modules.sharing.policy import access_policy
from app.shared.pagination import OffsetPage
from app.core.container import get_container


router = APIRouter(prefix="/scoring-reports", tags=["scoring-reports"])
service: ScoringReportService = get_container().scoring_reports
lineage_resolver = DatasetLineageResolver()


@router.get("", response_model=list[ScoringReportRead])
def list_scoring_reports(
    business_case_id: str | None = Query(default=None),
    summary: bool = Query(default=False),
    principal: Principal = Depends(require_user),
) -> list[ScoringReportRead]:
    return [
        ScoringReportRead.model_validate(report)
        for report in service.list_reports(principal, business_case_id, summary=summary)
    ]


@router.get("/page", response_model=OffsetPage[ScoringReportFamilyRead])
def page_scoring_reports(
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str = Query(default="", max_length=200),
    business_case_id: str | None = Query(default=None),
    problem_type: str = Query(default="", max_length=50),
    pipeline_id: str = Query(default="", max_length=64),
    pipeline_type: str = Query(default="", max_length=64),
    sort_by: str = Query(
        default="created",
        pattern="^(report|business_case|pipeline|problem|created|scope)$",
    ),
    sort_direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    principal: Principal = Depends(require_user),
) -> OffsetPage[ScoringReportFamilyRead]:
    page, total = service.page_report_families(
        principal,
        business_case_id,
        limit=limit,
        offset=offset,
        search=search,
        problem_type=problem_type,
        pipeline_id=pipeline_id,
        pipeline_type=pipeline_type,
        sort_by=sort_by,
        sort_direction=sort_direction,
    )
    return OffsetPage[ScoringReportFamilyRead].build(
        items=[
            ScoringReportFamilyRead(
                latest=ScoringReportRead.model_validate(report),
                version_count=version_count,
            )
            for report, version_count in page
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{logical_id}/versions", response_model=list[ScoringReportRead])
def list_scoring_report_versions(
    logical_id: str,
    summary: bool = Query(default=False),
    principal: Principal = Depends(require_user),
) -> list[ScoringReportRead]:
    return [
        ScoringReportRead.model_validate(report)
        for report in service.list_versions(logical_id, principal, summary=summary)
    ]


@router.get(
    "/{logical_id}/versions/page",
    response_model=OffsetPage[ScoringReportRead],
)
def page_scoring_report_versions(
    logical_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    summary: bool = Query(default=True),
    principal: Principal = Depends(require_user),
) -> OffsetPage[ScoringReportRead]:
    items, total = service.page_versions(
        logical_id,
        principal,
        limit=limit,
        offset=offset,
        summary=summary,
    )
    return OffsetPage[ScoringReportRead].build(
        [ScoringReportRead.model_validate(report) for report in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{report_id}", response_model=ScoringReportRead)
def get_scoring_report(
    report_id: str,
    principal: Principal = Depends(require_user),
) -> ScoringReportRead:
    return ScoringReportRead.model_validate(service.get_report(report_id, principal))


@router.get("/{report_id}/data-lineage", response_model=list[DatasetLineageRead])
def get_scoring_report_data_lineage(
    report_id: str,
    principal: Principal = Depends(require_user),
) -> list[DatasetLineageRead]:
    report = service.get_report(report_id, principal)
    access_policy.require_business_case(principal, report.business_case_id, BusinessCaseAccessRole.READER)
    artifact = service.artifacts.get_artifact(report.id)
    if artifact is None:
        return []
    return [
        DatasetLineageRead.model_validate(item)
        for item in lineage_resolver.resolve(artifact)
    ]
