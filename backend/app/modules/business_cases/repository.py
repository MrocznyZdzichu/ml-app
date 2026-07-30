from typing import Protocol

from app.modules.business_cases.domain import Artifact, BusinessCase, BusinessCaseDataAttachment
from app.modules.business_cases.domain import ArtifactType

class BusinessCaseRepository(Protocol):
    def add_business_case(self, business_case: BusinessCase) -> BusinessCase:
        ...

    def list_business_cases(self, owner_id: str) -> list[BusinessCase]:
        ...

    def list_all_business_cases(self) -> list[BusinessCase]:
        ...

    def list_business_cases_by_ids(self, business_case_ids: set[str]) -> list[BusinessCase]:
        ...

    def page_business_cases(
        self,
        business_case_ids: set[str] | None,
        *,
        limit: int,
        offset: int,
        search: str = "",
    ) -> tuple[list[BusinessCase], int]:
        ...

    def page_business_case_catalog(
        self,
        *,
        limit: int,
        offset: int,
        search: str = "",
    ) -> tuple[list[BusinessCase], int]:
        ...

    def business_case_name_exists(self, name: str, *, exclude_id: str = "") -> bool:
        ...

    def get_business_case(self, business_case_id: str) -> BusinessCase | None:
        ...

    def update_business_case(self, business_case: BusinessCase) -> BusinessCase:
        ...

    def add_artifact(self, artifact: Artifact) -> Artifact:
        ...

    def get_artifact(self, artifact_id: str) -> Artifact | None:
        ...

    def get_artifacts(self, artifact_ids: set[str]) -> dict[str, Artifact]:
        ...

    def update_artifact(self, artifact: Artifact) -> Artifact:
        ...

    def list_artifacts(self, owner_id: str, artifact_type: ArtifactType | None = None) -> list[Artifact]:
        ...

    def list_artifacts_for_business_cases(
        self, business_case_ids: set[str] | None, artifact_type: ArtifactType | None = None
    ) -> list[Artifact]:
        ...

    def list_model_version_artifacts(self, logical_model_id: str) -> list[Artifact]:
        ...

    def list_model_summary_artifacts_for_business_cases(
        self, business_case_ids: set[str] | None
    ) -> list[Artifact]:
        ...

    def page_serving_model_summaries(
        self,
        business_case_id: str,
        *,
        limit: int,
        offset: int,
        search: str = "",
        model_ids: set[str] | None = None,
    ) -> tuple[list[tuple[Artifact, int]], int]:
        ...

    def page_model_family_summaries(
        self,
        business_case_ids: set[str] | None,
        *,
        limit: int,
        offset: int,
        search: str = "",
        stage: str = "",
        pipeline_id: str = "",
        pipeline_type: str = "",
    ) -> tuple[list[tuple[Artifact, int]], int]:
        ...

    def list_feature_transform_summary_artifacts_for_business_cases(
        self, business_case_ids: set[str] | None
    ) -> list[Artifact]:
        ...

    def list_feature_transform_summary_artifacts_for_run_ids(
        self, run_ids: set[str]
    ) -> list[Artifact]:
        ...

    def list_scoring_report_summary_artifacts_for_business_cases(
        self, business_case_ids: set[str] | None
    ) -> list[Artifact]:
        ...

    def page_scoring_report_family_summaries(
        self,
        business_case_ids: set[str] | None,
        *,
        limit: int,
        offset: int,
        search: str = "",
        problem_type: str = "",
        pipeline_id: str = "",
        pipeline_type: str = "",
        sort_by: str = "created",
        sort_direction: str = "desc",
    ) -> tuple[list[tuple[Artifact, int]], int]:
        ...

    def list_scoring_report_family_summary_artifacts(
        self,
        business_case_ids: set[str] | None,
        logical_report_id: str,
    ) -> list[Artifact]:
        ...

    def list_scoring_report_family_artifacts(
        self,
        business_case_ids: set[str] | None,
        logical_report_id: str,
    ) -> list[Artifact]:
        ...

    def find_feature_transform_artifact(
        self,
        business_case_id: str,
        pipeline_run_id: str,
        pipeline_step_id: str,
    ) -> Artifact | None:
        ...

    def find_artifact(self, owner_id: str, reference_id: str, business_case_id: str | None) -> Artifact | None:
        ...

    def add_data_attachment(self, attachment: BusinessCaseDataAttachment) -> BusinessCaseDataAttachment:
        ...

    def get_data_attachment(self, attachment_id: str) -> BusinessCaseDataAttachment | None:
        ...

    def update_data_attachment(self, attachment: BusinessCaseDataAttachment) -> BusinessCaseDataAttachment:
        ...

    def delete_data_attachment(self, attachment_id: str) -> None:
        ...

    def list_data_attachments(self, business_case_id: str) -> list[BusinessCaseDataAttachment]:
        ...

    def page_data_attachments(
        self,
        business_case_id: str,
        *,
        limit: int,
        offset: int,
        search: str = "",
        role: str = "",
        pipeline_id: str = "",
        pipeline_type: str = "",
        uploaded_only: bool = False,
        deleted_only: bool = False,
    ) -> tuple[list[BusinessCaseDataAttachment], int]:
        ...

from app.modules.business_cases.repositories import (
    InMemoryBusinessCaseRepository,
    PostgresBusinessCaseRepository,
)
from app.modules.business_cases.tables import (
    BUSINESS_CASE_SCHEMA,
    artifacts_table,
    business_case_data_attachments_table,
    business_cases_table,
    metadata,
)

__all__ = [
    "BUSINESS_CASE_SCHEMA",
    "ArtifactType",
    "BusinessCaseRepository",
    "InMemoryBusinessCaseRepository",
    "PostgresBusinessCaseRepository",
    "artifacts_table",
    "business_case_data_attachments_table",
    "business_cases_table",
    "metadata",
]
