from typing import Protocol

from sqlalchemy import JSON, Column, DateTime, MetaData, String, Table, Text, func, or_, select, text
from sqlalchemy.engine import Engine

from app.core.database import get_engine
from app.modules.pipelines.repository import pipelines_table
from app.modules.business_cases.domain import Artifact, BusinessCase, BusinessCaseDataAttachment
from app.modules.business_cases.domain import (
    ArtifactOrigin,
    ArtifactType,
    BusinessCaseStatus,
    DataArtifactKind,
    DataRole,
    ProblemType,
)


BUSINESS_CASE_SCHEMA = "mlapp"
metadata = MetaData(schema=BUSINESS_CASE_SCHEMA)

business_cases_table = Table(
    "business_cases",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("owner_id", String(64), nullable=False, index=True),
    Column("name", String(255), nullable=False),
    Column("description", Text, nullable=False, default=""),
    Column("problem_type", String(64), nullable=False),
    Column("status", String(32), nullable=False),
    Column("business_owner", String(255), nullable=False, default=""),
    Column("primary_metric", String(128), nullable=False, default=""),
    Column("target_column", String(255), nullable=False, default=""),
    Column("business_goal", Text, nullable=False, default=""),
    Column("success_criteria", Text, nullable=False, default=""),
    Column("created_by", String(64), nullable=False),
    Column("updated_by", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

artifacts_table = Table(
    "artifacts",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("owner_id", String(64), nullable=False, index=True),
    Column("type", String(64), nullable=False),
    Column("reference_id", String(128), nullable=False, index=True),
    Column("origin", String(64), nullable=False),
    Column("business_case_id", String(64), nullable=True, index=True),
    Column("external_notes", Text, nullable=False, default=""),
    Column("metadata", JSON, nullable=False, default=dict),
    Column("created_by", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

business_case_data_attachments_table = Table(
    "business_case_data_attachments",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("owner_id", String(64), nullable=False, index=True),
    Column("business_case_id", String(64), nullable=False, index=True),
    Column("artifact_id", String(64), nullable=False, index=True),
    Column("data_asset_id", String(64), nullable=False, index=True),
    Column("data_asset_kind", String(32), nullable=False),
    Column("role", String(64), nullable=False),
    Column("context_note", Text, nullable=False, default=""),
    Column("primary_key_column", String(255), nullable=False, default=""),
    Column("target_column", String(255), nullable=False, default=""),
    Column("created_by", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


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


class InMemoryBusinessCaseRepository:
    def __init__(self) -> None:
        self._business_cases: dict[str, BusinessCase] = {}
        self._artifacts: dict[str, Artifact] = {}
        self._data_attachments: dict[str, BusinessCaseDataAttachment] = {}

    def add_business_case(self, business_case: BusinessCase) -> BusinessCase:
        self._business_cases[business_case.id] = business_case
        return business_case

    def list_business_cases(self, owner_id: str) -> list[BusinessCase]:
        return [item for item in self._business_cases.values() if item.owner_id == owner_id]

    def list_all_business_cases(self) -> list[BusinessCase]:
        return list(self._business_cases.values())

    def list_business_cases_by_ids(self, business_case_ids: set[str]) -> list[BusinessCase]:
        return [
            item for item in self._business_cases.values()
            if item.id in business_case_ids
        ]

    def page_business_cases(
        self,
        business_case_ids: set[str] | None,
        *,
        limit: int,
        offset: int,
        search: str = "",
    ) -> tuple[list[BusinessCase], int]:
        needle = search.strip().casefold()
        items = [
            item
            for item in self._business_cases.values()
            if (business_case_ids is None or item.id in business_case_ids)
            and (
                not needle
                or any(
                    needle in str(value or "").casefold()
                    for value in (
                        item.name,
                        item.description,
                        item.problem_type.value,
                        item.status.value,
                        item.primary_metric,
                        item.target_column,
                    )
                )
            )
        ]
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return items[offset : offset + limit], len(items)

    def business_case_name_exists(self, name: str, *, exclude_id: str = "") -> bool:
        normalized = name.strip().casefold()
        return any(
            item.id != exclude_id and item.name.strip().casefold() == normalized
            for item in self._business_cases.values()
        )

    def get_business_case(self, business_case_id: str) -> BusinessCase | None:
        return self._business_cases.get(business_case_id)

    def update_business_case(self, business_case: BusinessCase) -> BusinessCase:
        self._business_cases[business_case.id] = business_case
        return business_case

    def add_artifact(self, artifact: Artifact) -> Artifact:
        self._artifacts[artifact.id] = artifact
        return artifact

    def get_artifact(self, artifact_id: str) -> Artifact | None:
        return self._artifacts.get(artifact_id)

    def get_artifacts(self, artifact_ids: set[str]) -> dict[str, Artifact]:
        return {
            artifact_id: self._artifacts[artifact_id]
            for artifact_id in artifact_ids
            if artifact_id in self._artifacts
        }

    def update_artifact(self, artifact: Artifact) -> Artifact:
        self._artifacts[artifact.id] = artifact
        return artifact

    def list_artifacts(self, owner_id: str, artifact_type: ArtifactType | None = None) -> list[Artifact]:
        return [
            item for item in self._artifacts.values()
            if item.owner_id == owner_id and (artifact_type is None or item.type == artifact_type)
        ]

    def list_artifacts_for_business_cases(
        self, business_case_ids: set[str] | None, artifact_type: ArtifactType | None = None
    ) -> list[Artifact]:
        return [item for item in self._artifacts.values()
                if (business_case_ids is None or item.business_case_id in business_case_ids)
                and (artifact_type is None or item.type == artifact_type)]

    def list_model_version_artifacts(self, logical_model_id: str) -> list[Artifact]:
        return [
            item for item in self._artifacts.values()
            if item.type == ArtifactType.MODEL_VERSION
            and str(item.metadata.get("logical_model_id") or "") == logical_model_id
        ]

    def list_model_summary_artifacts_for_business_cases(
        self, business_case_ids: set[str] | None
    ) -> list[Artifact]:
        return [
            item for item in self._artifacts.values()
            if item.type == ArtifactType.MODEL_VERSION
            and (business_case_ids is None or item.business_case_id in business_case_ids)
        ]

    def page_serving_model_summaries(
        self,
        business_case_id: str,
        *,
        limit: int,
        offset: int,
        search: str = "",
        model_ids: set[str] | None = None,
    ) -> tuple[list[tuple[Artifact, int]], int]:
        all_models = sorted(
            self.list_model_summary_artifacts_for_business_cases({business_case_id}),
            key=lambda item: (item.created_at, item.id),
        )
        version_by_id: dict[str, int] = {}
        family_counts: dict[str, int] = {}
        for artifact in all_models:
            logical_id = str(
                artifact.metadata.get("logical_model_id") or artifact.id
            )
            family_counts[logical_id] = family_counts.get(logical_id, 0) + 1
            version_by_id[artifact.id] = family_counts[logical_id]
        needle = search.strip().casefold()
        filtered = [
            artifact
            for artifact in all_models
            if str(artifact.metadata.get("stage") or "") in {"staging", "production"}
            and (model_ids is None or artifact.id in model_ids)
            and (
                not needle
                or any(
                    needle in str(value or "").casefold()
                    for value in (
                        artifact.metadata.get("model_name"),
                        artifact.metadata.get("algorithm"),
                        artifact.id,
                    )
                )
            )
        ]
        filtered.sort(key=lambda item: (item.created_at, item.id), reverse=True)
        page = filtered[offset : offset + limit]
        return [(item, version_by_id[item.id]) for item in page], len(filtered)

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
        families: dict[str, list[Artifact]] = {}
        for artifact in self.list_model_summary_artifacts_for_business_cases(
            business_case_ids
        ):
            logical_id = str(
                artifact.metadata.get("logical_model_id") or artifact.id
            )
            families.setdefault(logical_id, []).append(artifact)
        needle = search.strip().casefold()
        items: list[tuple[Artifact, int]] = []
        for versions in families.values():
            versions.sort(
                key=lambda item: (item.created_at, item.id),
                reverse=True,
            )
            latest = versions[0]
            metadata = latest.metadata
            lineage = dict(metadata.get("lineage") or {})
            if stage and str(metadata.get("stage") or "developed") != stage:
                continue
            if pipeline_id and str(lineage.get("pipeline_id") or "") != pipeline_id:
                continue
            if needle and not any(
                needle in str(value or "").casefold()
                for value in (
                    metadata.get("model_name"),
                    metadata.get("algorithm"),
                    metadata.get("problem_type"),
                    metadata.get("logical_model_id"),
                )
            ):
                continue
            items.append((latest, len(versions)))
        items.sort(key=lambda item: (item[0].created_at, item[0].id), reverse=True)
        return items[offset : offset + limit], len(items)

    def list_feature_transform_summary_artifacts_for_business_cases(
        self, business_case_ids: set[str] | None
    ) -> list[Artifact]:
        return [
            item for item in self._artifacts.values()
            if item.type == ArtifactType.FEATURE_TRANSFORM
            and (business_case_ids is None or item.business_case_id in business_case_ids)
        ]

    def list_feature_transform_summary_artifacts_for_run_ids(
        self, run_ids: set[str]
    ) -> list[Artifact]:
        return [
            item for item in self._artifacts.values()
            if item.type == ArtifactType.FEATURE_TRANSFORM
            and str((item.metadata.get("lineage") or {}).get("pipeline_run_id") or "")
            in run_ids
        ]

    def list_scoring_report_summary_artifacts_for_business_cases(
        self, business_case_ids: set[str] | None
    ) -> list[Artifact]:
        return [
            item for item in self._artifacts.values()
            if item.type == ArtifactType.REPORT
            and (business_case_ids is None or item.business_case_id in business_case_ids)
        ]

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
        families: dict[str, list[Artifact]] = {}
        for artifact in self.list_scoring_report_summary_artifacts_for_business_cases(
            business_case_ids
        ):
            logical_id = str(
                artifact.metadata.get("logical_report_id") or artifact.id
            )
            families.setdefault(logical_id, []).append(artifact)
        needle = search.strip().casefold()
        items: list[tuple[Artifact, int]] = []
        for versions in families.values():
            versions.sort(
                key=lambda item: (item.created_at, item.id),
                reverse=True,
            )
            latest = versions[0]
            metadata = latest.metadata
            lineage = dict(metadata.get("lineage") or {})
            evaluation = dict(metadata.get("evaluation") or {})
            if problem_type and str(evaluation.get("problem_type") or "") != problem_type:
                continue
            if pipeline_id and str(lineage.get("pipeline_id") or "") != pipeline_id:
                continue
            if needle and not any(
                needle in str(value or "").casefold()
                for value in (
                    metadata.get("report_name"),
                    metadata.get("logical_report_id"),
                    evaluation.get("problem_type"),
                )
            ):
                continue
            items.append((latest, len(versions)))
        def sort_value(item: tuple[Artifact, int]):
            artifact = item[0]
            metadata = artifact.metadata
            lineage = dict(metadata.get("lineage") or {})
            evaluation = dict(metadata.get("evaluation") or {})
            scope = dict(evaluation.get("data_scope") or {})
            values = {
                "report": str(metadata.get("report_name") or ""),
                "business_case": artifact.business_case_id or "",
                "pipeline": str(lineage.get("pipeline_id") or ""),
                "problem": str(evaluation.get("problem_type") or ""),
                "scope": int(scope.get("evaluated_row_count") or 0),
                "created": artifact.created_at,
            }
            return values.get(sort_by, artifact.created_at)

        items.sort(key=sort_value, reverse=sort_direction != "asc")
        return items[offset : offset + limit], len(items)

    def list_scoring_report_family_summary_artifacts(
        self,
        business_case_ids: set[str] | None,
        logical_report_id: str,
    ) -> list[Artifact]:
        return [
            item for item in self._artifacts.values()
            if item.type == ArtifactType.REPORT
            and (
                business_case_ids is None
                or item.business_case_id in business_case_ids
            )
            and str(item.metadata.get("logical_report_id") or item.id)
            == logical_report_id
        ]

    def list_scoring_report_family_artifacts(
        self,
        business_case_ids: set[str] | None,
        logical_report_id: str,
    ) -> list[Artifact]:
        return self.list_scoring_report_family_summary_artifacts(
            business_case_ids,
            logical_report_id,
        )

    def find_feature_transform_artifact(
        self,
        business_case_id: str,
        pipeline_run_id: str,
        pipeline_step_id: str,
    ) -> Artifact | None:
        return next((
            item for item in self._artifacts.values()
            if item.type == ArtifactType.FEATURE_TRANSFORM
            and item.business_case_id == business_case_id
            and str((item.metadata.get("lineage") or {}).get("pipeline_run_id") or "") == pipeline_run_id
            and str((item.metadata.get("lineage") or {}).get("pipeline_step_id") or "") == pipeline_step_id
        ), None)

    def find_artifact(self, owner_id: str, reference_id: str, business_case_id: str | None) -> Artifact | None:
        for artifact in self._artifacts.values():
            if (
                artifact.owner_id == owner_id
                and artifact.reference_id == reference_id
                and artifact.business_case_id == business_case_id
            ):
                return artifact
        return None

    def add_data_attachment(self, attachment: BusinessCaseDataAttachment) -> BusinessCaseDataAttachment:
        self._data_attachments[attachment.id] = attachment
        return attachment

    def get_data_attachment(self, attachment_id: str) -> BusinessCaseDataAttachment | None:
        return self._data_attachments.get(attachment_id)

    def update_data_attachment(self, attachment: BusinessCaseDataAttachment) -> BusinessCaseDataAttachment:
        self._data_attachments[attachment.id] = attachment
        return attachment

    def delete_data_attachment(self, attachment_id: str) -> None:
        self._data_attachments.pop(attachment_id, None)

    def list_data_attachments(self, business_case_id: str) -> list[BusinessCaseDataAttachment]:
        return [
            item
            for item in self._data_attachments.values()
            if item.business_case_id == business_case_id
        ]

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
        needle = search.strip().casefold()
        items = [
            item
            for item in self.list_data_attachments(business_case_id)
            if (not role or item.role.value == role)
            and (not pipeline_id or item.data_asset_pipeline_id == pipeline_id)
            and (
                not pipeline_type
                or item.data_asset_pipeline_template == pipeline_type
            )
            and (
                not uploaded_only
                or (
                    item.data_asset_source_type != "view"
                    and not item.data_asset_pipeline_id
                )
            )
            and (
                (item.data_asset_status == "deleted")
                if deleted_only
                else item.data_asset_status != "deleted"
            )
            and (
                not needle
                or any(
                    needle in str(value or "").casefold()
                    for value in (
                        item.data_asset_name,
                        item.data_asset_id,
                        item.context_note,
                        item.role.value,
                    )
                )
            )
        ]
        items.sort(key=lambda item: (item.created_at, item.id), reverse=True)
        return items[offset : offset + limit], len(items)


class PostgresBusinessCaseRepository:
    def __init__(self, engine: Engine | None = None) -> None:
        self.engine = engine or get_engine()
        self._initialized = False

    def add_business_case(self, business_case: BusinessCase) -> BusinessCase:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            connection.execute(business_cases_table.insert().values(**self._business_case_to_record(business_case)))
        return business_case

    def list_business_cases(self, owner_id: str) -> list[BusinessCase]:
        self._ensure_initialized()
        statement = (
            select(business_cases_table)
            .where(business_cases_table.c.owner_id == owner_id)
            .order_by(business_cases_table.c.updated_at.desc())
        )
        with self.engine.begin() as connection:
            return [self._business_case_from_record(row._mapping) for row in connection.execute(statement)]

    def list_all_business_cases(self) -> list[BusinessCase]:
        self._ensure_initialized()
        statement = select(business_cases_table).order_by(business_cases_table.c.updated_at.desc())
        with self.engine.begin() as connection:
            return [self._business_case_from_record(row._mapping) for row in connection.execute(statement)]

    def list_business_cases_by_ids(self, business_case_ids: set[str]) -> list[BusinessCase]:
        self._ensure_initialized()
        if not business_case_ids:
            return []
        statement = (
            select(business_cases_table)
            .where(business_cases_table.c.id.in_(business_case_ids))
            .order_by(business_cases_table.c.updated_at.desc())
        )
        with self.engine.begin() as connection:
            return [
                self._business_case_from_record(row._mapping)
                for row in connection.execute(statement)
            ]

    def page_business_cases(
        self,
        business_case_ids: set[str] | None,
        *,
        limit: int,
        offset: int,
        search: str = "",
    ) -> tuple[list[BusinessCase], int]:
        self._ensure_initialized()
        if business_case_ids is not None and not business_case_ids:
            return [], 0
        filters = []
        if business_case_ids is not None:
            filters.append(business_cases_table.c.id.in_(business_case_ids))
        needle = search.strip()
        if needle:
            pattern = f"%{needle}%"
            filters.append(or_(
                business_cases_table.c.name.ilike(pattern),
                business_cases_table.c.description.ilike(pattern),
                business_cases_table.c.problem_type.ilike(pattern),
                business_cases_table.c.status.ilike(pattern),
                business_cases_table.c.primary_metric.ilike(pattern),
                business_cases_table.c.target_column.ilike(pattern),
            ))
        page_statement = select(business_cases_table)
        count_statement = select(func.count()).select_from(business_cases_table)
        if filters:
            page_statement = page_statement.where(*filters)
            count_statement = count_statement.where(*filters)
        page_statement = (
            page_statement
            .order_by(business_cases_table.c.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        with self.engine.begin() as connection:
            total = int(connection.execute(count_statement).scalar_one())
            items = [
                self._business_case_from_record(row._mapping)
                for row in connection.execute(page_statement)
            ]
        return items, total

    def business_case_name_exists(self, name: str, *, exclude_id: str = "") -> bool:
        self._ensure_initialized()
        statement = select(business_cases_table.c.id).where(
            func.lower(business_cases_table.c.name) == name.strip().lower()
        )
        if exclude_id:
            statement = statement.where(business_cases_table.c.id != exclude_id)
        with self.engine.begin() as connection:
            return connection.execute(statement.limit(1)).scalar_one_or_none() is not None

    def get_business_case(self, business_case_id: str) -> BusinessCase | None:
        self._ensure_initialized()
        statement = select(business_cases_table).where(business_cases_table.c.id == business_case_id)
        with self.engine.begin() as connection:
            row = connection.execute(statement).first()
        return self._business_case_from_record(row._mapping) if row else None

    def update_business_case(self, business_case: BusinessCase) -> BusinessCase:
        self._ensure_initialized()
        statement = (
            business_cases_table.update()
            .where(business_cases_table.c.id == business_case.id)
            .values(**self._business_case_to_record(business_case))
        )
        with self.engine.begin() as connection:
            connection.execute(statement)
        return business_case

    def add_artifact(self, artifact: Artifact) -> Artifact:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            connection.execute(artifacts_table.insert().values(**self._artifact_to_record(artifact)))
        return artifact

    def get_artifact(self, artifact_id: str) -> Artifact | None:
        self._ensure_initialized()
        statement = select(artifacts_table).where(artifacts_table.c.id == artifact_id)
        with self.engine.begin() as connection:
            row = connection.execute(statement).first()
        return self._artifact_from_record(row._mapping) if row else None

    def get_artifacts(self, artifact_ids: set[str]) -> dict[str, Artifact]:
        self._ensure_initialized()
        if not artifact_ids:
            return {}
        statement = select(artifacts_table).where(
            artifacts_table.c.id.in_(artifact_ids)
        )
        with self.engine.begin() as connection:
            artifacts = [
                self._artifact_from_record(row._mapping)
                for row in connection.execute(statement)
            ]
        return {artifact.id: artifact for artifact in artifacts}

    def update_artifact(self, artifact: Artifact) -> Artifact:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            connection.execute(
                artifacts_table.update().where(artifacts_table.c.id == artifact.id)
                .values(**self._artifact_to_record(artifact))
            )
        return artifact

    def list_artifacts(self, owner_id: str, artifact_type: ArtifactType | None = None) -> list[Artifact]:
        self._ensure_initialized()
        statement = select(artifacts_table).where(artifacts_table.c.owner_id == owner_id)
        if artifact_type is not None:
            statement = statement.where(artifacts_table.c.type == artifact_type.value)
        statement = statement.order_by(artifacts_table.c.created_at.desc())
        with self.engine.begin() as connection:
            return [self._artifact_from_record(row._mapping) for row in connection.execute(statement)]

    def list_artifacts_for_business_cases(
        self, business_case_ids: set[str] | None, artifact_type: ArtifactType | None = None
    ) -> list[Artifact]:
        self._ensure_initialized()
        if business_case_ids is not None and not business_case_ids:
            return []
        statement = select(artifacts_table)
        if business_case_ids is not None:
            statement = statement.where(
                artifacts_table.c.business_case_id.in_(business_case_ids)
            )
        if artifact_type is not None:
            statement = statement.where(artifacts_table.c.type == artifact_type.value)
        statement = statement.order_by(artifacts_table.c.created_at.desc())
        with self.engine.begin() as connection:
            return [self._artifact_from_record(row._mapping) for row in connection.execute(statement)]

    def list_model_version_artifacts(self, logical_model_id: str) -> list[Artifact]:
        """Read one model family without materializing the full model registry."""
        self._ensure_initialized()
        statement = (
            select(
                artifacts_table.c.id,
                artifacts_table.c.owner_id,
                artifacts_table.c.reference_id,
                artifacts_table.c.business_case_id,
                artifacts_table.c.created_by,
                artifacts_table.c.created_at,
                artifacts_table.c.metadata["model_name"].as_string().label("model_name"),
                artifacts_table.c.metadata["algorithm"].as_string().label("algorithm"),
                artifacts_table.c.metadata["stage"].as_string().label("stage"),
                artifacts_table.c.metadata["problem_type"].as_string().label("problem_type"),
                artifacts_table.c.metadata["model_hash"].as_string().label("model_hash"),
                artifacts_table.c.metadata["logical_model_id"].as_string().label("logical_model_id"),
                artifacts_table.c.metadata["lineage"]["pipeline_id"].as_string().label("pipeline_id"),
                artifacts_table.c.metadata["lineage"]["pipeline_version_id"].as_string().label("pipeline_version_id"),
                artifacts_table.c.metadata["lineage"]["pipeline_run_id"].as_string().label("pipeline_run_id"),
                artifacts_table.c.metadata["lineage"]["pipeline_step_id"].as_string().label("pipeline_step_id"),
            )
            .where(
                artifacts_table.c.type == ArtifactType.MODEL_VERSION.value,
                artifacts_table.c.metadata["logical_model_id"].as_string() == logical_model_id,
            )
            .order_by(artifacts_table.c.created_at.asc(), artifacts_table.c.id.asc())
        )
        with self.engine.begin() as connection:
            rows = [row._mapping for row in connection.execute(statement)]
        return [
            Artifact(
                id=row["id"],
                owner_id=row["owner_id"],
                type=ArtifactType.MODEL_VERSION,
                reference_id=row["reference_id"],
                origin=ArtifactOrigin.PLATFORM_GENERATED,
                business_case_id=row["business_case_id"],
                external_notes="",
                metadata={
                    "model_name": row["model_name"] or "Pipeline model",
                    "algorithm": row["algorithm"] or "unknown",
                    "stage": "developed" if (row["stage"] or "developed") == "candidate" else (row["stage"] or "developed"),
                    "problem_type": row["problem_type"] or "",
                    "model_hash": row["model_hash"] or "",
                    "logical_model_id": row["logical_model_id"] or logical_model_id,
                    "lineage": {
                        "pipeline_id": row["pipeline_id"] or "",
                        "pipeline_version_id": row["pipeline_version_id"] or "",
                        "pipeline_run_id": row["pipeline_run_id"] or "",
                        "pipeline_step_id": row["pipeline_step_id"] or "",
                    },
                },
                created_by=row["created_by"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def list_model_summary_artifacts_for_business_cases(
        self, business_case_ids: set[str] | None
    ) -> list[Artifact]:
        """Project registry fields needed for discovery without large experiment payloads."""
        self._ensure_initialized()
        if business_case_ids is not None and not business_case_ids:
            return []
        statement = (
            select(
                artifacts_table.c.id,
                artifacts_table.c.owner_id,
                artifacts_table.c.reference_id,
                artifacts_table.c.business_case_id,
                artifacts_table.c.created_by,
                artifacts_table.c.created_at,
                artifacts_table.c.metadata["model_name"].as_string().label("model_name"),
                artifacts_table.c.metadata["algorithm"].as_string().label("algorithm"),
                artifacts_table.c.metadata["stage"].as_string().label("stage"),
                artifacts_table.c.metadata["problem_type"].as_string().label("problem_type"),
                artifacts_table.c.metadata["target_column"].as_string().label("target_column"),
                artifacts_table.c.metadata["feature_columns"].label("feature_columns"),
                artifacts_table.c.metadata["training_config"]["auto_feature_engineering"]["resolved_recipe"].label("resolved_recipe"),
                artifacts_table.c.metadata["model_hash"].as_string().label("model_hash"),
                artifacts_table.c.metadata["logical_model_id"].as_string().label("logical_model_id"),
                artifacts_table.c.metadata["lineage"]["pipeline_id"].as_string().label("pipeline_id"),
                artifacts_table.c.metadata["lineage"]["pipeline_version_id"].as_string().label("pipeline_version_id"),
                artifacts_table.c.metadata["lineage"]["pipeline_run_id"].as_string().label("pipeline_run_id"),
                artifacts_table.c.metadata["lineage"]["pipeline_step_id"].as_string().label("pipeline_step_id"),
            )
            .where(artifacts_table.c.type == ArtifactType.MODEL_VERSION.value)
            .order_by(artifacts_table.c.created_at.asc(), artifacts_table.c.id.asc())
        )
        if business_case_ids is not None:
            statement = statement.where(
                artifacts_table.c.business_case_id.in_(business_case_ids)
            )
        with self.engine.begin() as connection:
            rows = [row._mapping for row in connection.execute(statement)]
        return [self._model_summary_artifact(row) for row in rows]

    def page_serving_model_summaries(
        self,
        business_case_id: str,
        *,
        limit: int,
        offset: int,
        search: str = "",
        model_ids: set[str] | None = None,
    ) -> tuple[list[tuple[Artifact, int]], int]:
        """Page deployable immutable versions before loading inference bundles."""
        self._ensure_initialized()
        logical_id = func.coalesce(
            artifacts_table.c.metadata["logical_model_id"].as_string(),
            artifacts_table.c.id,
        )
        ranked = (
            select(
                artifacts_table.c.id,
                artifacts_table.c.owner_id,
                artifacts_table.c.reference_id,
                artifacts_table.c.business_case_id,
                artifacts_table.c.created_by,
                artifacts_table.c.created_at,
                artifacts_table.c.metadata["model_name"].as_string().label("model_name"),
                artifacts_table.c.metadata["algorithm"].as_string().label("algorithm"),
                artifacts_table.c.metadata["stage"].as_string().label("stage"),
                artifacts_table.c.metadata["problem_type"].as_string().label("problem_type"),
                artifacts_table.c.metadata["target_column"].as_string().label("target_column"),
                artifacts_table.c.metadata["feature_columns"].label("feature_columns"),
                artifacts_table.c.metadata["training_config"]["auto_feature_engineering"]["resolved_recipe"].label("resolved_recipe"),
                artifacts_table.c.metadata["model_hash"].as_string().label("model_hash"),
                logical_id.label("logical_model_id"),
                artifacts_table.c.metadata["lineage"]["pipeline_id"].as_string().label("pipeline_id"),
                artifacts_table.c.metadata["lineage"]["pipeline_version_id"].as_string().label("pipeline_version_id"),
                artifacts_table.c.metadata["lineage"]["pipeline_run_id"].as_string().label("pipeline_run_id"),
                artifacts_table.c.metadata["lineage"]["pipeline_step_id"].as_string().label("pipeline_step_id"),
                func.row_number().over(
                    partition_by=logical_id,
                    order_by=(
                        artifacts_table.c.created_at.asc(),
                        artifacts_table.c.id.asc(),
                    ),
                ).label("version_number"),
            )
            .where(
                artifacts_table.c.type == ArtifactType.MODEL_VERSION.value,
                artifacts_table.c.business_case_id == business_case_id,
            )
        )
        ranked_rows = ranked.subquery()
        filters = [ranked_rows.c.stage.in_(("staging", "production"))]
        if model_ids is not None:
            if not model_ids:
                return [], 0
            filters.append(ranked_rows.c.id.in_(model_ids))
        needle = search.strip()
        if needle:
            pattern = f"%{needle}%"
            filters.append(or_(
                ranked_rows.c.model_name.ilike(pattern),
                ranked_rows.c.algorithm.ilike(pattern),
                ranked_rows.c.id.ilike(pattern),
            ))
        filtered = select(ranked_rows).where(*filters).subquery()
        count_statement = select(func.count()).select_from(filtered)
        page_statement = (
            select(filtered)
            .order_by(filtered.c.created_at.desc(), filtered.c.id.desc())
            .limit(limit)
            .offset(offset)
        )
        with self.engine.begin() as connection:
            total = int(connection.execute(count_statement).scalar_one())
            rows = [row._mapping for row in connection.execute(page_statement)]
        return [
            (self._model_summary_artifact(row), int(row["version_number"]))
            for row in rows
        ], total

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
        """Page latest model families before enriching their referenced contracts."""
        self._ensure_initialized()
        if business_case_ids is not None and not business_case_ids:
            return [], 0
        logical_id = func.coalesce(
            artifacts_table.c.metadata["logical_model_id"].as_string(),
            artifacts_table.c.id,
        )
        ranked = (
            select(
                artifacts_table.c.id,
                artifacts_table.c.owner_id,
                artifacts_table.c.reference_id,
                artifacts_table.c.business_case_id,
                artifacts_table.c.created_by,
                artifacts_table.c.created_at,
                artifacts_table.c.metadata["model_name"].as_string().label("model_name"),
                artifacts_table.c.metadata["algorithm"].as_string().label("algorithm"),
                artifacts_table.c.metadata["stage"].as_string().label("stage"),
                artifacts_table.c.metadata["problem_type"].as_string().label("problem_type"),
                artifacts_table.c.metadata["target_column"].as_string().label("target_column"),
                artifacts_table.c.metadata["feature_columns"].label("feature_columns"),
                artifacts_table.c.metadata["training_config"]["auto_feature_engineering"]["resolved_recipe"].label("resolved_recipe"),
                artifacts_table.c.metadata["model_hash"].as_string().label("model_hash"),
                logical_id.label("logical_model_id"),
                artifacts_table.c.metadata["lineage"]["pipeline_id"].as_string().label("pipeline_id"),
                artifacts_table.c.metadata["lineage"]["pipeline_version_id"].as_string().label("pipeline_version_id"),
                artifacts_table.c.metadata["lineage"]["pipeline_run_id"].as_string().label("pipeline_run_id"),
                artifacts_table.c.metadata["lineage"]["pipeline_step_id"].as_string().label("pipeline_step_id"),
                func.row_number().over(
                    partition_by=logical_id,
                    order_by=(
                        artifacts_table.c.created_at.desc(),
                        artifacts_table.c.id.desc(),
                    ),
                ).label("family_rank"),
                func.count().over(partition_by=logical_id).label("version_count"),
            )
            .where(artifacts_table.c.type == ArtifactType.MODEL_VERSION.value)
        )
        if business_case_ids is not None:
            ranked = ranked.where(
                artifacts_table.c.business_case_id.in_(business_case_ids)
            )
        ranked_rows = ranked.subquery()
        filters = [ranked_rows.c.family_rank == 1]
        if stage:
            normalized_stage = "candidate" if stage == "developed" else stage
            if stage == "developed":
                filters.append(or_(
                    ranked_rows.c.stage.in_(("developed", "candidate")),
                    ranked_rows.c.stage.is_(None),
                ))
            else:
                filters.append(ranked_rows.c.stage == normalized_stage)
        if pipeline_id:
            filters.append(ranked_rows.c.pipeline_id == pipeline_id)
        if pipeline_type:
            filters.append(
                ranked_rows.c.pipeline_id.in_(
                    select(pipelines_table.c.id).where(
                        pipelines_table.c.template == pipeline_type
                    )
                )
            )
        needle = search.strip()
        if needle:
            pattern = f"%{needle}%"
            filters.append(or_(
                ranked_rows.c.model_name.ilike(pattern),
                ranked_rows.c.algorithm.ilike(pattern),
                ranked_rows.c.problem_type.ilike(pattern),
                ranked_rows.c.logical_model_id.ilike(pattern),
            ))
        filtered = select(ranked_rows).where(*filters).subquery()
        count_statement = select(func.count()).select_from(filtered)
        page_statement = (
            select(filtered)
            .order_by(filtered.c.created_at.desc(), filtered.c.id.desc())
            .limit(limit)
            .offset(offset)
        )
        with self.engine.begin() as connection:
            total = int(connection.execute(count_statement).scalar_one())
            rows = [row._mapping for row in connection.execute(page_statement)]
        return [
            (self._model_summary_artifact(row), int(row["version_count"]))
            for row in rows
        ], total

    @staticmethod
    def _model_summary_artifact(row: object) -> Artifact:
        stage = row["stage"] or "developed"
        return Artifact(
            id=row["id"],
            owner_id=row["owner_id"],
            type=ArtifactType.MODEL_VERSION,
            reference_id=row["reference_id"],
            origin=ArtifactOrigin.PLATFORM_GENERATED,
            business_case_id=row["business_case_id"],
            external_notes="",
            metadata={
                "model_name": row["model_name"] or "Pipeline model",
                "algorithm": row["algorithm"] or "unknown",
                "stage": "developed" if stage == "candidate" else stage,
                "problem_type": row["problem_type"] or "",
                "target_column": row["target_column"] or "",
                "feature_columns": list(row["feature_columns"] or []),
                "training_config": {
                    "auto_feature_engineering": {
                        "resolved_recipe": dict(row["resolved_recipe"] or {})
                    }
                } if row["resolved_recipe"] else {},
                "model_hash": row["model_hash"] or "",
                "logical_model_id": row["logical_model_id"] or row["id"],
                "lineage": {
                    "pipeline_id": row["pipeline_id"] or "",
                    "pipeline_version_id": row["pipeline_version_id"] or "",
                    "pipeline_run_id": row["pipeline_run_id"] or "",
                    "pipeline_step_id": row["pipeline_step_id"] or "",
                },
            },
            created_by=row["created_by"],
            created_at=row["created_at"],
        )

    def list_feature_transform_summary_artifacts_for_business_cases(
        self, business_case_ids: set[str] | None
    ) -> list[Artifact]:
        """Project only lineage used to bind models to fitted transforms."""
        self._ensure_initialized()
        if business_case_ids is not None and not business_case_ids:
            return []
        statement = (
            select(
                artifacts_table.c.id,
                artifacts_table.c.owner_id,
                artifacts_table.c.reference_id,
                artifacts_table.c.business_case_id,
                artifacts_table.c.created_by,
                artifacts_table.c.created_at,
                artifacts_table.c.metadata["lineage"]["pipeline_run_id"].as_string().label("pipeline_run_id"),
                artifacts_table.c.metadata["lineage"]["pipeline_step_id"].as_string().label("pipeline_step_id"),
            )
            .where(artifacts_table.c.type == ArtifactType.FEATURE_TRANSFORM.value)
        )
        if business_case_ids is not None:
            statement = statement.where(
                artifacts_table.c.business_case_id.in_(business_case_ids)
            )
        with self.engine.begin() as connection:
            rows = [row._mapping for row in connection.execute(statement)]
        return [
            Artifact(
                id=row["id"],
                owner_id=row["owner_id"],
                type=ArtifactType.FEATURE_TRANSFORM,
                reference_id=row["reference_id"],
                origin=ArtifactOrigin.PLATFORM_GENERATED,
                business_case_id=row["business_case_id"],
                external_notes="",
                metadata={
                    "lineage": {
                        "pipeline_run_id": row["pipeline_run_id"] or "",
                        "pipeline_step_id": row["pipeline_step_id"] or "",
                    }
                },
                created_by=row["created_by"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def list_feature_transform_summary_artifacts_for_run_ids(
        self, run_ids: set[str]
    ) -> list[Artifact]:
        """Project fitted-transform lineage only for runs referenced by models."""
        self._ensure_initialized()
        if not run_ids:
            return []
        statement = (
            select(
                artifacts_table.c.id,
                artifacts_table.c.owner_id,
                artifacts_table.c.reference_id,
                artifacts_table.c.business_case_id,
                artifacts_table.c.created_by,
                artifacts_table.c.created_at,
                artifacts_table.c.metadata["lineage"]["pipeline_run_id"].as_string().label("pipeline_run_id"),
                artifacts_table.c.metadata["lineage"]["pipeline_step_id"].as_string().label("pipeline_step_id"),
            )
            .where(
                artifacts_table.c.type == ArtifactType.FEATURE_TRANSFORM.value,
                artifacts_table.c.metadata["lineage"]["pipeline_run_id"]
                .as_string()
                .in_(run_ids),
            )
        )
        with self.engine.begin() as connection:
            rows = [row._mapping for row in connection.execute(statement)]
        return [
            Artifact(
                id=row["id"],
                owner_id=row["owner_id"],
                type=ArtifactType.FEATURE_TRANSFORM,
                reference_id=row["reference_id"],
                origin=ArtifactOrigin.PLATFORM_GENERATED,
                business_case_id=row["business_case_id"],
                external_notes="",
                metadata={
                    "lineage": {
                        "pipeline_run_id": row["pipeline_run_id"] or "",
                        "pipeline_step_id": row["pipeline_step_id"] or "",
                    }
                },
                created_by=row["created_by"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def list_scoring_report_summary_artifacts_for_business_cases(
        self, business_case_ids: set[str] | None
    ) -> list[Artifact]:
        """Project report catalog fields without the potentially large evaluation payload."""
        self._ensure_initialized()
        if business_case_ids is not None and not business_case_ids:
            return []
        statement = (
            select(
                artifacts_table.c.id,
                artifacts_table.c.owner_id,
                artifacts_table.c.reference_id,
                artifacts_table.c.business_case_id,
                artifacts_table.c.created_by,
                artifacts_table.c.created_at,
                artifacts_table.c.metadata["report_name"].as_string().label("report_name"),
                artifacts_table.c.metadata["logical_report_id"].as_string().label("logical_report_id"),
                artifacts_table.c.metadata["prediction_dataset_id"].as_string().label("prediction_dataset_id"),
                artifacts_table.c.metadata["prediction_artifact_id"].as_string().label("prediction_artifact_id"),
                artifacts_table.c.metadata["model_artifact_id"].as_string().label("model_artifact_id"),
                artifacts_table.c.metadata["lineage"]["pipeline_id"].as_string().label("pipeline_id"),
                artifacts_table.c.metadata["lineage"]["pipeline_version_id"].as_string().label("pipeline_version_id"),
                artifacts_table.c.metadata["lineage"]["pipeline_run_id"].as_string().label("pipeline_run_id"),
                artifacts_table.c.metadata["lineage"]["pipeline_step_id"].as_string().label("pipeline_step_id"),
                artifacts_table.c.metadata["evaluation"]["problem_type"].as_string().label("problem_type"),
                artifacts_table.c.metadata["evaluation"]["data_scope"]["evaluated_row_count"].as_integer().label("evaluated_row_count"),
            )
            .where(artifacts_table.c.type == ArtifactType.REPORT.value)
            .order_by(artifacts_table.c.created_at.desc())
        )
        if business_case_ids is not None:
            statement = statement.where(
                artifacts_table.c.business_case_id.in_(business_case_ids)
            )
        with self.engine.begin() as connection:
            rows = [row._mapping for row in connection.execute(statement)]
        return [self._scoring_report_summary_artifact(row) for row in rows]

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
        """Page latest report families without loading full evaluation payloads."""
        self._ensure_initialized()
        if business_case_ids is not None and not business_case_ids:
            return [], 0
        logical_id = func.coalesce(
            func.nullif(
                artifacts_table.c.metadata["logical_report_id"].as_string(),
                "",
            ),
            artifacts_table.c.id,
        )
        ranked = (
            select(
                artifacts_table.c.id,
                artifacts_table.c.owner_id,
                artifacts_table.c.reference_id,
                artifacts_table.c.business_case_id,
                artifacts_table.c.created_by,
                artifacts_table.c.created_at,
                artifacts_table.c.metadata["report_name"].as_string().label("report_name"),
                logical_id.label("logical_report_id"),
                artifacts_table.c.metadata["prediction_dataset_id"].as_string().label("prediction_dataset_id"),
                artifacts_table.c.metadata["prediction_artifact_id"].as_string().label("prediction_artifact_id"),
                artifacts_table.c.metadata["model_artifact_id"].as_string().label("model_artifact_id"),
                artifacts_table.c.metadata["lineage"]["pipeline_id"].as_string().label("pipeline_id"),
                artifacts_table.c.metadata["lineage"]["pipeline_version_id"].as_string().label("pipeline_version_id"),
                artifacts_table.c.metadata["lineage"]["pipeline_run_id"].as_string().label("pipeline_run_id"),
                artifacts_table.c.metadata["lineage"]["pipeline_step_id"].as_string().label("pipeline_step_id"),
                artifacts_table.c.metadata["evaluation"]["problem_type"].as_string().label("problem_type"),
                artifacts_table.c.metadata["evaluation"]["data_scope"]["evaluated_row_count"].as_integer().label("evaluated_row_count"),
                func.row_number().over(
                    partition_by=logical_id,
                    order_by=(
                        artifacts_table.c.created_at.desc(),
                        artifacts_table.c.id.desc(),
                    ),
                ).label("family_rank"),
                func.count().over(partition_by=logical_id).label("version_count"),
            )
            .where(artifacts_table.c.type == ArtifactType.REPORT.value)
        )
        if business_case_ids is not None:
            ranked = ranked.where(
                artifacts_table.c.business_case_id.in_(business_case_ids)
            )
        ranked_rows = ranked.subquery()
        filters = [ranked_rows.c.family_rank == 1]
        if problem_type:
            filters.append(ranked_rows.c.problem_type == problem_type)
        if pipeline_id:
            filters.append(ranked_rows.c.pipeline_id == pipeline_id)
        if pipeline_type:
            filters.append(
                ranked_rows.c.pipeline_id.in_(
                    select(pipelines_table.c.id).where(
                        pipelines_table.c.template == pipeline_type
                    )
                )
            )
        needle = search.strip()
        if needle:
            pattern = f"%{needle}%"
            filters.append(or_(
                ranked_rows.c.report_name.ilike(pattern),
                ranked_rows.c.logical_report_id.ilike(pattern),
                ranked_rows.c.problem_type.ilike(pattern),
            ))
        filtered = select(ranked_rows).where(*filters).subquery()
        count_statement = select(func.count()).select_from(filtered)
        sort_columns = {
            "report": filtered.c.report_name,
            "business_case": filtered.c.business_case_id,
            "pipeline": filtered.c.pipeline_id,
            "problem": filtered.c.problem_type,
            "scope": filtered.c.evaluated_row_count,
            "created": filtered.c.created_at,
        }
        sort_column = sort_columns.get(sort_by, filtered.c.created_at)
        ordering = sort_column.asc() if sort_direction == "asc" else sort_column.desc()
        page_statement = (
            select(filtered)
            .order_by(ordering, filtered.c.id.desc())
            .limit(limit)
            .offset(offset)
        )
        with self.engine.begin() as connection:
            total = int(connection.execute(count_statement).scalar_one())
            rows = [row._mapping for row in connection.execute(page_statement)]
        return [
            (self._scoring_report_summary_artifact(row), int(row["version_count"]))
            for row in rows
        ], total

    @staticmethod
    def _scoring_report_summary_artifact(row: object) -> Artifact:
        return Artifact(
            id=row["id"],
            owner_id=row["owner_id"],
            type=ArtifactType.REPORT,
            reference_id=row["reference_id"],
            origin=ArtifactOrigin.PLATFORM_GENERATED,
            business_case_id=row["business_case_id"],
            external_notes="",
            metadata={
                "report_name": row["report_name"] or "Scoring report",
                "logical_report_id": row["logical_report_id"] or row["id"],
                "prediction_dataset_id": row["prediction_dataset_id"] or "",
                "prediction_artifact_id": row["prediction_artifact_id"] or "",
                "model_artifact_id": row["model_artifact_id"] or "",
                "lineage": {
                    "pipeline_id": row["pipeline_id"] or "",
                    "pipeline_version_id": row["pipeline_version_id"] or "",
                    "pipeline_run_id": row["pipeline_run_id"] or "",
                    "pipeline_step_id": row["pipeline_step_id"] or "",
                },
                "evaluation": {
                    "problem_type": row["problem_type"] or "",
                    "data_scope": {
                        "evaluated_row_count": int(row["evaluated_row_count"] or 0)
                    },
                },
            },
            created_by=row["created_by"],
            created_at=row["created_at"],
        )

    def list_scoring_report_family_summary_artifacts(
        self,
        business_case_ids: set[str] | None,
        logical_report_id: str,
    ) -> list[Artifact]:
        """Read one report family without scanning every report in the BC."""
        self._ensure_initialized()
        logical_id = func.coalesce(
            func.nullif(
                artifacts_table.c.metadata["logical_report_id"].as_string(),
                "",
            ),
            artifacts_table.c.id,
        )
        statement = (
            select(
                artifacts_table.c.id,
                artifacts_table.c.owner_id,
                artifacts_table.c.reference_id,
                artifacts_table.c.business_case_id,
                artifacts_table.c.created_by,
                artifacts_table.c.created_at,
                artifacts_table.c.metadata["report_name"].as_string().label("report_name"),
                artifacts_table.c.metadata["logical_report_id"].as_string().label("logical_report_id"),
                artifacts_table.c.metadata["prediction_dataset_id"].as_string().label("prediction_dataset_id"),
                artifacts_table.c.metadata["prediction_artifact_id"].as_string().label("prediction_artifact_id"),
                artifacts_table.c.metadata["model_artifact_id"].as_string().label("model_artifact_id"),
                artifacts_table.c.metadata["lineage"]["pipeline_id"].as_string().label("pipeline_id"),
                artifacts_table.c.metadata["lineage"]["pipeline_version_id"].as_string().label("pipeline_version_id"),
                artifacts_table.c.metadata["lineage"]["pipeline_run_id"].as_string().label("pipeline_run_id"),
                artifacts_table.c.metadata["lineage"]["pipeline_step_id"].as_string().label("pipeline_step_id"),
                artifacts_table.c.metadata["evaluation"]["problem_type"].as_string().label("problem_type"),
                artifacts_table.c.metadata["evaluation"]["data_scope"]["evaluated_row_count"].as_integer().label("evaluated_row_count"),
            )
            .where(
                artifacts_table.c.type == ArtifactType.REPORT.value,
                logical_id == logical_report_id,
            )
            .order_by(artifacts_table.c.created_at.asc(), artifacts_table.c.id.asc())
        )
        if business_case_ids is not None:
            if not business_case_ids:
                return []
            statement = statement.where(
                artifacts_table.c.business_case_id.in_(business_case_ids)
            )
        with self.engine.begin() as connection:
            rows = [row._mapping for row in connection.execute(statement)]
        return [
            Artifact(
                id=row["id"],
                owner_id=row["owner_id"],
                type=ArtifactType.REPORT,
                reference_id=row["reference_id"],
                origin=ArtifactOrigin.PLATFORM_GENERATED,
                business_case_id=row["business_case_id"],
                external_notes="",
                metadata={
                    "report_name": row["report_name"] or "Scoring report",
                    "logical_report_id": row["logical_report_id"] or row["id"],
                    "prediction_dataset_id": row["prediction_dataset_id"] or "",
                    "prediction_artifact_id": row["prediction_artifact_id"] or "",
                    "model_artifact_id": row["model_artifact_id"] or "",
                    "lineage": {
                        "pipeline_id": row["pipeline_id"] or "",
                        "pipeline_version_id": row["pipeline_version_id"] or "",
                        "pipeline_run_id": row["pipeline_run_id"] or "",
                        "pipeline_step_id": row["pipeline_step_id"] or "",
                    },
                    "evaluation": {
                        "problem_type": row["problem_type"] or "",
                        "data_scope": {
                            "evaluated_row_count": int(row["evaluated_row_count"] or 0)
                        },
                    },
                },
                created_by=row["created_by"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def list_scoring_report_family_artifacts(
        self,
        business_case_ids: set[str] | None,
        logical_report_id: str,
    ) -> list[Artifact]:
        self._ensure_initialized()
        if business_case_ids is not None and not business_case_ids:
            return []
        logical_id = func.coalesce(
            func.nullif(
                artifacts_table.c.metadata["logical_report_id"].as_string(),
                "",
            ),
            artifacts_table.c.id,
        )
        statement = (
            select(artifacts_table)
            .where(
                artifacts_table.c.type == ArtifactType.REPORT.value,
                logical_id == logical_report_id,
            )
            .order_by(artifacts_table.c.created_at.asc(), artifacts_table.c.id.asc())
        )
        if business_case_ids is not None:
            statement = statement.where(
                artifacts_table.c.business_case_id.in_(business_case_ids)
            )
        with self.engine.begin() as connection:
            return [
                self._artifact_from_record(row._mapping)
                for row in connection.execute(statement)
            ]

    def find_feature_transform_artifact(
        self,
        business_case_id: str,
        pipeline_run_id: str,
        pipeline_step_id: str,
    ) -> Artifact | None:
        """Resolve one immutable fitted transform without scanning the registry."""
        self._ensure_initialized()
        statement = (
            select(artifacts_table)
            .where(
                artifacts_table.c.type == ArtifactType.FEATURE_TRANSFORM.value,
                artifacts_table.c.business_case_id == business_case_id,
                artifacts_table.c.metadata["lineage"]["pipeline_run_id"].as_string() == pipeline_run_id,
                artifacts_table.c.metadata["lineage"]["pipeline_step_id"].as_string() == pipeline_step_id,
            )
            .order_by(artifacts_table.c.created_at.desc())
            .limit(1)
        )
        with self.engine.begin() as connection:
            row = connection.execute(statement).first()
        return self._artifact_from_record(row._mapping) if row else None

    def find_artifact(self, owner_id: str, reference_id: str, business_case_id: str | None) -> Artifact | None:
        self._ensure_initialized()
        statement = select(artifacts_table).where(
            artifacts_table.c.owner_id == owner_id,
            artifacts_table.c.reference_id == reference_id,
            artifacts_table.c.business_case_id == business_case_id,
        )
        with self.engine.begin() as connection:
            row = connection.execute(statement).first()
        return self._artifact_from_record(row._mapping) if row else None

    def add_data_attachment(self, attachment: BusinessCaseDataAttachment) -> BusinessCaseDataAttachment:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            connection.execute(
                business_case_data_attachments_table.insert().values(**self._attachment_to_record(attachment))
            )
        return attachment

    def get_data_attachment(self, attachment_id: str) -> BusinessCaseDataAttachment | None:
        self._ensure_initialized()
        statement = select(business_case_data_attachments_table).where(
            business_case_data_attachments_table.c.id == attachment_id
        )
        with self.engine.begin() as connection:
            row = connection.execute(statement).first()
        return self._attachment_from_record(row._mapping) if row else None

    def update_data_attachment(self, attachment: BusinessCaseDataAttachment) -> BusinessCaseDataAttachment:
        self._ensure_initialized()
        statement = (
            business_case_data_attachments_table.update()
            .where(business_case_data_attachments_table.c.id == attachment.id)
            .values(**self._attachment_to_record(attachment))
        )
        with self.engine.begin() as connection:
            connection.execute(statement)
        return attachment

    def delete_data_attachment(self, attachment_id: str) -> None:
        self._ensure_initialized()
        statement = business_case_data_attachments_table.delete().where(
            business_case_data_attachments_table.c.id == attachment_id
        )
        with self.engine.begin() as connection:
            connection.execute(statement)

    def list_data_attachments(self, business_case_id: str) -> list[BusinessCaseDataAttachment]:
        self._ensure_initialized()
        statement = (
            select(business_case_data_attachments_table)
            .where(business_case_data_attachments_table.c.business_case_id == business_case_id)
            .order_by(business_case_data_attachments_table.c.created_at.desc())
        )
        with self.engine.begin() as connection:
            return [self._attachment_from_record(row._mapping) for row in connection.execute(statement)]

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
        """Page BC mappings and resolve only the latest lightweight dataset version."""
        self._ensure_initialized()
        filters = ["business_case_id = :business_case_id"]
        parameters: dict[str, object] = {
            "business_case_id": business_case_id,
            "limit": limit,
            "offset": offset,
        }
        if role:
            filters.append("role = :role")
            parameters["role"] = role
        if pipeline_id:
            filters.append("data_asset_pipeline_id = :pipeline_id")
            parameters["pipeline_id"] = pipeline_id
        if pipeline_type:
            filters.append("data_asset_pipeline_template = :pipeline_type")
            parameters["pipeline_type"] = pipeline_type
        if uploaded_only:
            filters.extend([
                "data_asset_source_type <> 'view'",
                "data_asset_pipeline_id = ''",
            ])
        filters.append(
            "data_asset_status = 'deleted'"
            if deleted_only
            else "data_asset_status <> 'deleted'"
        )
        needle = search.strip()
        if needle:
            filters.append(
                "(data_asset_name ILIKE :search OR data_asset_id ILIKE :search "
                "OR context_note ILIKE :search OR role ILIKE :search)"
            )
            parameters["search"] = f"%{needle}%"
        where_clause = " AND ".join(filters)
        mapped_cte = """
            WITH mapped AS (
                SELECT
                    attachment.*,
                    latest.name AS data_asset_name,
                    latest.status AS data_asset_status,
                    latest.source_type AS data_asset_source_type,
                    latest.logical_id AS data_asset_logical_id,
                    latest.version_number AS data_asset_version_number,
                    COALESCE(latest.metadata #>> '{pipeline_output,pipeline_id}', '') AS data_asset_pipeline_id,
                    COALESCE(pipeline.template, '') AS data_asset_pipeline_template
                FROM mlapp.business_case_data_attachments AS attachment
                JOIN mlapp.data_assets AS attached
                  ON attached.id = attachment.data_asset_id
                JOIN LATERAL (
                    SELECT candidate.*
                    FROM mlapp.data_assets AS candidate
                    WHERE candidate.logical_id = attached.logical_id
                    ORDER BY candidate.version_number DESC, candidate.created_at DESC, candidate.id DESC
                    LIMIT 1
                ) AS latest ON TRUE
                LEFT JOIN mlapp.pipelines AS pipeline
                  ON pipeline.id = COALESCE(latest.metadata #>> '{pipeline_output,pipeline_id}', '')
            )
        """
        count_statement = text(
            f"{mapped_cte} SELECT COUNT(*) FROM mapped WHERE {where_clause}"
        )
        page_statement = text(
            f"{mapped_cte} SELECT * FROM mapped WHERE {where_clause} "
            "ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset"
        )
        with self.engine.begin() as connection:
            total = int(connection.execute(count_statement, parameters).scalar_one())
            rows = [row._mapping for row in connection.execute(page_statement, parameters)]
        items: list[BusinessCaseDataAttachment] = []
        for row in rows:
            attachment = self._attachment_from_record(row)
            attachment.data_asset_name = str(row["data_asset_name"] or "")
            attachment.data_asset_status = str(row["data_asset_status"] or "")
            attachment.data_asset_source_type = str(row["data_asset_source_type"] or "")
            attachment.data_asset_logical_id = str(row["data_asset_logical_id"] or "")
            attachment.data_asset_version_number = int(row["data_asset_version_number"] or 0)
            attachment.data_asset_pipeline_id = str(row["data_asset_pipeline_id"] or "")
            attachment.data_asset_pipeline_template = str(
                row["data_asset_pipeline_template"] or ""
            )
            items.append(attachment)
        return items, total

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        with self.engine.begin() as connection:
            connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {BUSINESS_CASE_SCHEMA}"))
            metadata.create_all(connection)
        self._initialized = True

    def _business_case_to_record(self, business_case: BusinessCase) -> dict[str, object]:
        return {
            "id": business_case.id,
            "owner_id": business_case.owner_id,
            "name": business_case.name,
            "description": business_case.description,
            "problem_type": business_case.problem_type.value,
            "status": business_case.status.value,
            "business_owner": business_case.business_owner,
            "primary_metric": business_case.primary_metric,
            "target_column": business_case.target_column,
            "business_goal": business_case.business_goal,
            "success_criteria": business_case.success_criteria,
            "created_by": business_case.created_by,
            "updated_by": business_case.updated_by,
            "created_at": business_case.created_at,
            "updated_at": business_case.updated_at,
        }

    def _business_case_from_record(self, record: object) -> BusinessCase:
        return BusinessCase(
            id=record["id"],
            owner_id=record["owner_id"],
            name=record["name"],
            description=record["description"],
            problem_type=ProblemType(record["problem_type"]),
            status=BusinessCaseStatus(record["status"]),
            business_owner=record["business_owner"],
            primary_metric=record["primary_metric"],
            target_column=record["target_column"],
            business_goal=record["business_goal"],
            success_criteria=record["success_criteria"],
            created_by=record["created_by"],
            updated_by=record["updated_by"],
            created_at=record["created_at"],
            updated_at=record["updated_at"],
        )

    def _artifact_to_record(self, artifact: Artifact) -> dict[str, object]:
        return {
            "id": artifact.id,
            "owner_id": artifact.owner_id,
            "type": artifact.type.value,
            "reference_id": artifact.reference_id,
            "origin": artifact.origin.value,
            "business_case_id": artifact.business_case_id,
            "external_notes": artifact.external_notes,
            "metadata": artifact.metadata,
            "created_by": artifact.created_by,
            "created_at": artifact.created_at,
        }

    def _artifact_from_record(self, record: object) -> Artifact:
        return Artifact(
            id=record["id"],
            owner_id=record["owner_id"],
            type=ArtifactType(record["type"]),
            reference_id=record["reference_id"],
            origin=ArtifactOrigin(record["origin"]),
            business_case_id=record["business_case_id"],
            external_notes=record["external_notes"],
            metadata=dict(record["metadata"] or {}),
            created_by=record["created_by"],
            created_at=record["created_at"],
        )

    def _attachment_to_record(self, attachment: BusinessCaseDataAttachment) -> dict[str, object]:
        return {
            "id": attachment.id,
            "owner_id": attachment.owner_id,
            "business_case_id": attachment.business_case_id,
            "artifact_id": attachment.artifact_id,
            "data_asset_id": attachment.data_asset_id,
            "data_asset_kind": attachment.data_asset_kind.value,
            "role": attachment.role.value,
            "context_note": attachment.context_note,
            "primary_key_column": attachment.primary_key_column,
            "target_column": attachment.target_column,
            "created_by": attachment.created_by,
            "created_at": attachment.created_at,
        }

    def _attachment_from_record(self, record: object) -> BusinessCaseDataAttachment:
        return BusinessCaseDataAttachment(
            id=record["id"],
            owner_id=record["owner_id"],
            business_case_id=record["business_case_id"],
            artifact_id=record["artifact_id"],
            data_asset_id=record["data_asset_id"],
            data_asset_kind=DataArtifactKind(record["data_asset_kind"]),
            role=DataRole(record["role"]),
            context_note=record["context_note"],
            primary_key_column=record["primary_key_column"],
            target_column=record["target_column"],
            created_by=record["created_by"],
            created_at=record["created_at"],
        )
