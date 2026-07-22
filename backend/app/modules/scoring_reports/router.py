from fastapi import APIRouter, Depends, Query

from app.core.security import Principal, require_user
from app.modules.scoring_reports.schemas import DatasetLineageRead, ScoringReportRead
from app.modules.scoring_reports.service import ScoringReportService
from app.modules.business_cases.lineage import DatasetLineageResolver
from app.modules.sharing.domain import BusinessCaseAccessRole
from app.modules.sharing.policy import access_policy


router = APIRouter(prefix="/scoring-reports", tags=["scoring-reports"])
service = ScoringReportService()
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
