from collections import defaultdict
from dataclasses import replace

from fastapi import HTTPException, status

from app.core.security import Principal
from app.modules.business_cases.domain import Artifact, ArtifactType
from app.modules.business_cases.repository import (
    BusinessCaseRepository,
    PostgresBusinessCaseRepository,
)
from app.modules.scoring_reports.domain import ScoringReport
from app.modules.sharing.domain import BusinessCaseAccessRole
from app.modules.sharing.policy import access_policy


class ScoringReportService:
    def __init__(self, artifacts: BusinessCaseRepository | None = None) -> None:
        self.artifacts = artifacts or PostgresBusinessCaseRepository()

    def list_reports(
        self,
        principal: Principal,
        business_case_id: str | None = None,
        *,
        summary: bool = False,
    ) -> list[ScoringReport]:
        if isinstance(self.artifacts, PostgresBusinessCaseRepository):
            if business_case_id is not None:
                access_policy.require_business_case(
                    principal,
                    business_case_id,
                    BusinessCaseAccessRole.REPORT_VIEWER,
                )
                case_ids: set[str] | None = {business_case_id}
            else:
                case_ids = access_policy.accessible_business_case_ids(
                    principal,
                    BusinessCaseAccessRole.REPORT_VIEWER,
                )
            owners: set[str] = set()
        else:
            case_ids = None
            owners = {principal.user_id}
        artifacts = (
            (
                self.artifacts.list_scoring_report_summary_artifacts_for_business_cases(case_ids)
                if summary
                else self.artifacts.list_artifacts_for_business_cases(case_ids, ArtifactType.REPORT)
            )
            if isinstance(self.artifacts, PostgresBusinessCaseRepository)
            else [item for owner_id in owners for item in self.artifacts.list_artifacts(owner_id, ArtifactType.REPORT)]
        )
        reports = [self._from_artifact(artifact) for artifact in artifacts]
        if summary and case_ids is None:
            reports = [
                replace(
                    report,
                    evaluation={
                        "problem_type": report.problem_type,
                        "data_scope": {"evaluated_row_count": report.evaluated_row_count},
                    },
                )
                for report in reports
            ]
        self._assign_version_numbers(reports)
        return sorted(reports, key=lambda item: (item.created_at, item.id), reverse=True)

    def page_report_families(
        self,
        principal: Principal,
        business_case_id: str | None = None,
        *,
        limit: int,
        offset: int,
        search: str = "",
        problem_type: str = "",
        pipeline_id: str = "",
        pipeline_type: str = "",
        sort_by: str = "created",
        sort_direction: str = "desc",
    ) -> tuple[list[tuple[ScoringReport, int]], int]:
        if isinstance(self.artifacts, PostgresBusinessCaseRepository):
            if business_case_id is not None:
                access_policy.require_business_case(
                    principal,
                    business_case_id,
                    BusinessCaseAccessRole.REPORT_VIEWER,
                )
                case_ids: set[str] | None = {business_case_id}
            else:
                case_ids = access_policy.accessible_business_case_ids(
                    principal,
                    BusinessCaseAccessRole.REPORT_VIEWER,
                )
            page, total = self.artifacts.page_scoring_report_family_summaries(
                case_ids,
                limit=limit,
                offset=offset,
                search=search,
                problem_type=problem_type,
                pipeline_id=pipeline_id,
                pipeline_type=pipeline_type,
                sort_by=sort_by,
                sort_direction=sort_direction,
            )
            reports = [
                (self._from_artifact(artifact), version_count)
                for artifact, version_count in page
            ]
            for report, version_count in reports:
                report.version_number = version_count
            return reports, total

        reports = self.list_reports(
            principal,
            business_case_id,
            summary=True,
        )
        families: dict[str, list[ScoringReport]] = defaultdict(list)
        for report in reports:
            families[report.logical_id].append(report)
        needle = search.strip().casefold()
        page_items: list[tuple[ScoringReport, int]] = []
        for versions in families.values():
            versions.sort(
                key=lambda item: (item.created_at, item.id),
                reverse=True,
            )
            latest = versions[0]
            if problem_type and latest.problem_type != problem_type:
                continue
            if pipeline_id and latest.pipeline_id != pipeline_id:
                continue
            if needle and not any(
                needle in str(value or "").casefold()
                for value in (latest.name, latest.logical_id, latest.problem_type)
            ):
                continue
            latest.version_number = len(versions)
            page_items.append((latest, len(versions)))
        page_items.sort(
            key=lambda item: (item[0].created_at, item[0].id),
            reverse=True,
        )
        total = len(page_items)
        return page_items[offset : offset + limit], total

    def get_report(self, report_id: str, principal: Principal) -> ScoringReport:
        if isinstance(self.artifacts, PostgresBusinessCaseRepository):
            artifact = self.artifacts.get_artifact(report_id)
            if artifact is None or artifact.type != ArtifactType.REPORT or not artifact.business_case_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Scoring report not found",
                )
            access_policy.require_business_case(
                principal,
                artifact.business_case_id,
                BusinessCaseAccessRole.REPORT_VIEWER,
            )
            report = self._from_artifact(artifact)
            family = [
                self._from_artifact(item)
                for item in self.artifacts.list_scoring_report_family_summary_artifacts(
                    {artifact.business_case_id},
                    report.logical_id,
                )
            ]
            self._assign_version_numbers(family)
            version = next((item for item in family if item.id == report_id), None)
            if version is not None:
                report.version_number = version.version_number
            return report
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

    def list_versions(
        self,
        logical_id: str,
        principal: Principal,
        *,
        summary: bool = False,
    ) -> list[ScoringReport]:
        if isinstance(self.artifacts, PostgresBusinessCaseRepository):
            case_ids = access_policy.accessible_business_case_ids(
                principal,
                BusinessCaseAccessRole.REPORT_VIEWER,
            )
            artifacts = (
                self.artifacts.list_scoring_report_family_summary_artifacts(
                    case_ids,
                    logical_id,
                )
                if summary
                else self.artifacts.list_scoring_report_family_artifacts(
                    case_ids,
                    logical_id,
                )
            )
            versions = [
                self._from_artifact(item)
                for item in artifacts
            ]
            self._assign_version_numbers(versions)
        else:
            versions = [
                item
                for item in self.list_reports(principal, summary=summary)
                if item.logical_id == logical_id
            ]
        if not versions:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Scoring report family not found",
            )
        return sorted(versions, key=lambda item: item.version_number)

    def page_versions(
        self,
        logical_id: str,
        principal: Principal,
        *,
        limit: int,
        offset: int,
        summary: bool = True,
    ) -> tuple[list[ScoringReport], int]:
        versions = list(reversed(
            self.list_versions(logical_id, principal, summary=summary)
        ))
        return versions[offset : offset + limit], len(versions)

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
