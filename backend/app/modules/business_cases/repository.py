from typing import Protocol

from sqlalchemy import JSON, Column, DateTime, MetaData, String, Table, Text, select, text
from sqlalchemy.engine import Engine

from app.core.database import get_engine
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

    def get_business_case(self, business_case_id: str) -> BusinessCase | None:
        ...

    def update_business_case(self, business_case: BusinessCase) -> BusinessCase:
        ...

    def add_artifact(self, artifact: Artifact) -> Artifact:
        ...

    def get_artifact(self, artifact_id: str) -> Artifact | None:
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
