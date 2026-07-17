from collections import defaultdict

from fastapi import HTTPException, status

from app.core.security import Principal
from app.modules.business_cases.domain import Artifact, ArtifactType
from app.modules.business_cases.repository import (
    BusinessCaseRepository,
    PostgresBusinessCaseRepository,
)
from app.modules.scoring_reports.domain import ScoringReport
from app.modules.business_cases.service import BusinessCaseService


class ScoringReportService:
    def __init__(self, artifacts: BusinessCaseRepository | None = None) -> None:
        self.artifacts = artifacts or PostgresBusinessCaseRepository()
        self.business_cases = BusinessCaseService()

    def list_reports(
        self,
        principal: Principal,
        business_case_id: str | None = None,
    ) -> list[ScoringReport]:
        if isinstance(self.artifacts, PostgresBusinessCaseRepository):
            cases = self.business_cases.list_business_cases(principal)
            if business_case_id is not None:
                cases = [case for case in cases if case.id == business_case_id]
            case_ids = {case.id for case in cases}
            owners = {case.owner_id for case in cases}
        else:
            case_ids = None
            owners = {principal.user_id}
        artifacts = (
            self.artifacts.list_artifacts_for_business_cases(case_ids, ArtifactType.REPORT)
            if case_ids is not None
            else [item for owner_id in owners for item in self.artifacts.list_artifacts(owner_id, ArtifactType.REPORT)]
        )
        reports = [self._from_artifact(artifact) for artifact in artifacts]
        self._assign_version_numbers(reports)
        return sorted(reports, key=lambda item: (item.created_at, item.id), reverse=True)

    def get_report(self, report_id: str, principal: Principal) -> ScoringReport:
        report = next(
            (item for item in self.list_reports(principal) if item.id == report_id),
            None,
        )
        if report is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Scoring report not found",
            )
        return report

    def list_versions(self, logical_id: str, principal: Principal) -> list[ScoringReport]:
        versions = [
            item
            for item in self.list_reports(principal)
            if item.logical_id == logical_id
        ]
        if not versions:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Scoring report family not found",
            )
        return sorted(versions, key=lambda item: item.version_number)

    @staticmethod
    def _assign_version_numbers(reports: list[ScoringReport]) -> None:
        families: dict[str, list[ScoringReport]] = defaultdict(list)
        for report in reports:
            families[report.logical_id].append(report)
        for versions in families.values():
            versions.sort(key=lambda item: (item.created_at, item.id))
            for number, report in enumerate(versions, start=1):
                report.version_number = number

    @staticmethod
    def _from_artifact(artifact: Artifact) -> ScoringReport:
        metadata = artifact.metadata
        lineage = dict(metadata.get("lineage") or {})
        evaluation = dict(metadata.get("evaluation") or {})
        data_scope = dict(evaluation.get("data_scope") or {})
        return ScoringReport(
            id=artifact.id,
            owner_id=artifact.owner_id,
            name=str(metadata.get("report_name") or "Scoring report"),
            logical_id=str(metadata.get("logical_report_id") or artifact.id),
            version_number=1,
            business_case_id=artifact.business_case_id or "",
            pipeline_id=str(lineage.get("pipeline_id") or ""),
            pipeline_version_id=str(lineage.get("pipeline_version_id") or ""),
            pipeline_run_id=str(lineage.get("pipeline_run_id") or ""),
            pipeline_step_id=str(lineage.get("pipeline_step_id") or ""),
            problem_type=str(evaluation.get("problem_type") or ""),
            prediction_dataset_id=str(metadata.get("prediction_dataset_id") or ""),
            prediction_artifact_id=str(metadata.get("prediction_artifact_id") or ""),
            model_artifact_id=str(metadata.get("model_artifact_id") or ""),
            evaluated_row_count=int(data_scope.get("evaluated_row_count") or 0),
            evaluation=evaluation,
            lineage=lineage,
            created_at=artifact.created_at,
        )
