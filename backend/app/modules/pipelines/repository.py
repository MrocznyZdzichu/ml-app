from typing import Protocol

from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, MetaData, String, Table, Text, select, text
from sqlalchemy.engine import Engine

from app.core.database import get_engine
from app.modules.pipelines.domain import (
    Pipeline,
    PipelineRun,
    PipelineStepRun,
    PipelineVersion,
    PipelineVersionStatus,
)
from app.modules.pipelines.domain import (
    PipelineRunStatus,
    PipelineRunTrigger,
    PipelineStatus,
    PipelineType,
)


PIPELINE_SCHEMA = "mlapp"
metadata = MetaData(schema=PIPELINE_SCHEMA)

pipelines_table = Table(
    "pipelines",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("owner_id", String(64), nullable=False, index=True),
    Column("business_case_id", String(64), nullable=False, index=True),
    Column("name", String(255), nullable=False),
    Column("description", Text, nullable=False, default=""),
    Column("type", String(64), nullable=False),
    Column("status", String(32), nullable=False),
    Column("created_by", String(64), nullable=False),
    Column("updated_by", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

pipeline_versions_table = Table(
    "pipeline_versions",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("owner_id", String(64), nullable=False, index=True),
    Column("pipeline_id", String(64), nullable=False, index=True),
    Column("business_case_id", String(64), nullable=False, index=True),
    Column("version_number", Integer, nullable=False),
    Column("status", String(32), nullable=False),
    Column("definition", JSON, nullable=False, default=dict),
    Column("definition_hash", String(64), nullable=False),
    Column("created_by", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("published_by", String(64), nullable=False, default=""),
    Column("published_at", DateTime(timezone=True), nullable=True),
)

pipeline_runs_table = Table(
    "pipeline_runs",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("owner_id", String(64), nullable=False, index=True),
    Column("pipeline_id", String(64), nullable=False, index=True),
    Column("pipeline_version_id", String(64), nullable=False, index=True),
    Column("business_case_id", String(64), nullable=False, index=True),
    Column("status", String(32), nullable=False),
    Column("trigger_type", String(32), nullable=False),
    Column("runtime_parameters", JSON, nullable=False, default=dict),
    Column("is_dry_run", Boolean, nullable=False, default=False),
    Column("requested_step_id", String(128), nullable=False, default=""),
    Column("input_row_count", Integer, nullable=True),
    Column("processed_row_count", Integer, nullable=True),
    Column("output_row_count", Integer, nullable=True),
    Column("rejected_row_count", Integer, nullable=True),
    Column("warnings", JSON, nullable=False, default=list),
    Column("output_artifact_ids", JSON, nullable=False, default=list),
    Column("output_manifest", JSON, nullable=False, default=list),
    Column("error_message", Text, nullable=False, default=""),
    Column("created_by", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("finished_at", DateTime(timezone=True), nullable=True),
)

pipeline_step_runs_table = Table(
    "pipeline_step_runs",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("owner_id", String(64), nullable=False, index=True),
    Column("pipeline_run_id", String(64), nullable=False, index=True),
    Column("pipeline_step_id", String(128), nullable=False),
    Column("step_type", String(64), nullable=False),
    Column("status", String(32), nullable=False),
    Column("input_row_count", Integer, nullable=True),
    Column("processed_row_count", Integer, nullable=True),
    Column("output_row_count", Integer, nullable=True),
    Column("warnings", JSON, nullable=False, default=list),
    Column("output_manifest", JSON, nullable=False, default=list),
    Column("error_message", Text, nullable=False, default=""),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("finished_at", DateTime(timezone=True), nullable=True),
)


class PipelineRepository(Protocol):
    def add_pipeline(self, pipeline: Pipeline) -> Pipeline:
        ...

    def list_pipelines(self, owner_id: str, business_case_id: str | None = None) -> list[Pipeline]:
        ...

    def get_pipeline(self, pipeline_id: str) -> Pipeline | None:
        ...

    def update_pipeline(self, pipeline: Pipeline) -> Pipeline:
        ...

    def add_version(self, version: PipelineVersion) -> PipelineVersion:
        ...

    def list_versions(self, pipeline_id: str) -> list[PipelineVersion]:
        ...

    def get_version(self, version_id: str) -> PipelineVersion | None:
        ...

    def get_draft_version(self, pipeline_id: str) -> PipelineVersion | None:
        ...

    def update_version(self, version: PipelineVersion) -> PipelineVersion:
        ...

    def add_run(self, run: PipelineRun) -> PipelineRun:
        ...

    def get_run(self, run_id: str) -> PipelineRun | None:
        ...

    def update_run(self, run: PipelineRun) -> PipelineRun:
        ...

    def list_runs(self, pipeline_id: str | None, owner_id: str) -> list[PipelineRun]:
        ...

    def add_step_run(self, step_run: PipelineStepRun) -> PipelineStepRun:
        ...

    def update_step_run(self, step_run: PipelineStepRun) -> PipelineStepRun:
        ...

    def list_step_runs(self, pipeline_run_id: str, owner_id: str) -> list[PipelineStepRun]:
        ...


class InMemoryPipelineRepository:
    def __init__(self) -> None:
        self._pipelines: dict[str, Pipeline] = {}
        self._versions: dict[str, PipelineVersion] = {}
        self._runs: dict[str, PipelineRun] = {}
        self._step_runs: dict[str, PipelineStepRun] = {}

    def add_pipeline(self, pipeline: Pipeline) -> Pipeline:
        self._pipelines[pipeline.id] = pipeline
        return pipeline

    def list_pipelines(self, owner_id: str, business_case_id: str | None = None) -> list[Pipeline]:
        return [
            item
            for item in self._pipelines.values()
            if item.owner_id == owner_id and (business_case_id is None or item.business_case_id == business_case_id)
        ]

    def get_pipeline(self, pipeline_id: str) -> Pipeline | None:
        return self._pipelines.get(pipeline_id)

    def update_pipeline(self, pipeline: Pipeline) -> Pipeline:
        self._pipelines[pipeline.id] = pipeline
        return pipeline

    def add_version(self, version: PipelineVersion) -> PipelineVersion:
        self._versions[version.id] = version
        return version

    def list_versions(self, pipeline_id: str) -> list[PipelineVersion]:
        return sorted(
            [item for item in self._versions.values() if item.pipeline_id == pipeline_id],
            key=lambda item: item.version_number,
        )

    def get_version(self, version_id: str) -> PipelineVersion | None:
        return self._versions.get(version_id)

    def get_draft_version(self, pipeline_id: str) -> PipelineVersion | None:
        for version in self._versions.values():
            if version.pipeline_id == pipeline_id and version.status == PipelineVersionStatus.DRAFT:
                return version
        return None

    def update_version(self, version: PipelineVersion) -> PipelineVersion:
        self._versions[version.id] = version
        return version

    def add_run(self, run: PipelineRun) -> PipelineRun:
        self._runs[run.id] = run
        return run

    def get_run(self, run_id: str) -> PipelineRun | None:
        return self._runs.get(run_id)

    def update_run(self, run: PipelineRun) -> PipelineRun:
        self._runs[run.id] = run
        return run

    def list_runs(self, pipeline_id: str | None, owner_id: str) -> list[PipelineRun]:
        return [
            item
            for item in self._runs.values()
            if item.owner_id == owner_id and (pipeline_id is None or item.pipeline_id == pipeline_id)
        ]

    def add_step_run(self, step_run: PipelineStepRun) -> PipelineStepRun:
        self._step_runs[step_run.id] = step_run
        return step_run

    def update_step_run(self, step_run: PipelineStepRun) -> PipelineStepRun:
        self._step_runs[step_run.id] = step_run
        return step_run

    def list_step_runs(self, pipeline_run_id: str, owner_id: str) -> list[PipelineStepRun]:
        return [
            item for item in self._step_runs.values()
            if item.pipeline_run_id == pipeline_run_id and item.owner_id == owner_id
        ]


class PostgresPipelineRepository:
    def __init__(self, engine: Engine | None = None) -> None:
        self.engine = engine or get_engine()
        self._initialized = False

    def add_pipeline(self, pipeline: Pipeline) -> Pipeline:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            connection.execute(pipelines_table.insert().values(**self._pipeline_to_record(pipeline)))
        return pipeline

    def list_pipelines(self, owner_id: str, business_case_id: str | None = None) -> list[Pipeline]:
        self._ensure_initialized()
        statement = select(pipelines_table).where(pipelines_table.c.owner_id == owner_id)
        if business_case_id is not None:
            statement = statement.where(pipelines_table.c.business_case_id == business_case_id)
        statement = statement.order_by(pipelines_table.c.updated_at.desc())
        with self.engine.begin() as connection:
            return [self._pipeline_from_record(row._mapping) for row in connection.execute(statement)]

    def get_pipeline(self, pipeline_id: str) -> Pipeline | None:
        self._ensure_initialized()
        statement = select(pipelines_table).where(pipelines_table.c.id == pipeline_id)
        with self.engine.begin() as connection:
            row = connection.execute(statement).first()
        return self._pipeline_from_record(row._mapping) if row else None

    def update_pipeline(self, pipeline: Pipeline) -> Pipeline:
        self._ensure_initialized()
        statement = (
            pipelines_table.update()
            .where(pipelines_table.c.id == pipeline.id)
            .values(**self._pipeline_to_record(pipeline))
        )
        with self.engine.begin() as connection:
            connection.execute(statement)
        return pipeline

    def add_version(self, version: PipelineVersion) -> PipelineVersion:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            connection.execute(pipeline_versions_table.insert().values(**self._version_to_record(version)))
        return version

    def list_versions(self, pipeline_id: str) -> list[PipelineVersion]:
        self._ensure_initialized()
        statement = (
            select(pipeline_versions_table)
            .where(pipeline_versions_table.c.pipeline_id == pipeline_id)
            .order_by(pipeline_versions_table.c.version_number.asc())
        )
        with self.engine.begin() as connection:
            return [self._version_from_record(row._mapping) for row in connection.execute(statement)]

    def get_version(self, version_id: str) -> PipelineVersion | None:
        self._ensure_initialized()
        statement = select(pipeline_versions_table).where(pipeline_versions_table.c.id == version_id)
        with self.engine.begin() as connection:
            row = connection.execute(statement).first()
        return self._version_from_record(row._mapping) if row else None

    def get_draft_version(self, pipeline_id: str) -> PipelineVersion | None:
        self._ensure_initialized()
        statement = select(pipeline_versions_table).where(
            pipeline_versions_table.c.pipeline_id == pipeline_id,
            pipeline_versions_table.c.status == PipelineVersionStatus.DRAFT.value,
        )
        with self.engine.begin() as connection:
            row = connection.execute(statement).first()
        return self._version_from_record(row._mapping) if row else None

    def update_version(self, version: PipelineVersion) -> PipelineVersion:
        self._ensure_initialized()
        statement = (
            pipeline_versions_table.update()
            .where(pipeline_versions_table.c.id == version.id)
            .values(**self._version_to_record(version))
        )
        with self.engine.begin() as connection:
            connection.execute(statement)
        return version

    def add_run(self, run: PipelineRun) -> PipelineRun:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            connection.execute(pipeline_runs_table.insert().values(**self._run_to_record(run)))
        return run

    def get_run(self, run_id: str) -> PipelineRun | None:
        self._ensure_initialized()
        statement = select(pipeline_runs_table).where(pipeline_runs_table.c.id == run_id)
        with self.engine.begin() as connection:
            row = connection.execute(statement).first()
        return self._run_from_record(row._mapping) if row else None

    def update_run(self, run: PipelineRun) -> PipelineRun:
        self._ensure_initialized()
        statement = (
            pipeline_runs_table.update()
            .where(pipeline_runs_table.c.id == run.id)
            .values(**self._run_to_record(run))
        )
        with self.engine.begin() as connection:
            connection.execute(statement)
        return run

    def list_runs(self, pipeline_id: str | None, owner_id: str) -> list[PipelineRun]:
        self._ensure_initialized()
        statement = select(pipeline_runs_table).where(pipeline_runs_table.c.owner_id == owner_id)
        if pipeline_id is not None:
            statement = statement.where(pipeline_runs_table.c.pipeline_id == pipeline_id)
        statement = statement.order_by(pipeline_runs_table.c.created_at.desc())
        with self.engine.begin() as connection:
            return [self._run_from_record(row._mapping) for row in connection.execute(statement)]

    def add_step_run(self, step_run: PipelineStepRun) -> PipelineStepRun:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            connection.execute(
                pipeline_step_runs_table.insert().values(**self._step_run_to_record(step_run))
            )
        return step_run

    def update_step_run(self, step_run: PipelineStepRun) -> PipelineStepRun:
        self._ensure_initialized()
        statement = (
            pipeline_step_runs_table.update()
            .where(pipeline_step_runs_table.c.id == step_run.id)
            .values(**self._step_run_to_record(step_run))
        )
        with self.engine.begin() as connection:
            connection.execute(statement)
        return step_run

    def list_step_runs(self, pipeline_run_id: str, owner_id: str) -> list[PipelineStepRun]:
        self._ensure_initialized()
        statement = (
            select(pipeline_step_runs_table)
            .where(
                pipeline_step_runs_table.c.pipeline_run_id == pipeline_run_id,
                pipeline_step_runs_table.c.owner_id == owner_id,
            )
            .order_by(pipeline_step_runs_table.c.started_at.asc())
        )
        with self.engine.begin() as connection:
            return [
                self._step_run_from_record(row._mapping)
                for row in connection.execute(statement)
            ]

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        with self.engine.begin() as connection:
            connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {PIPELINE_SCHEMA}"))
            metadata.create_all(connection)
            connection.execute(text(
                "ALTER TABLE mlapp.pipeline_runs "
                "ADD COLUMN IF NOT EXISTS output_manifest JSONB NOT NULL DEFAULT '[]'::jsonb"
            ))
            connection.execute(text(
                "ALTER TABLE mlapp.pipeline_runs "
                "ADD COLUMN IF NOT EXISTS error_message TEXT NOT NULL DEFAULT ''"
            ))
            connection.execute(text(
                "ALTER TABLE mlapp.pipeline_runs "
                "ADD COLUMN IF NOT EXISTS requested_step_id VARCHAR(128) NOT NULL DEFAULT ''"
            ))
        self._initialized = True

    def _pipeline_to_record(self, pipeline: Pipeline) -> dict[str, object]:
        return {
            "id": pipeline.id,
            "owner_id": pipeline.owner_id,
            "business_case_id": pipeline.business_case_id,
            "name": pipeline.name,
            "description": pipeline.description,
            "type": pipeline.type.value,
            "status": pipeline.status.value,
            "created_by": pipeline.created_by,
            "updated_by": pipeline.updated_by,
            "created_at": pipeline.created_at,
            "updated_at": pipeline.updated_at,
        }

    def _pipeline_from_record(self, record: object) -> Pipeline:
        return Pipeline(
            id=record["id"],
            owner_id=record["owner_id"],
            business_case_id=record["business_case_id"],
            name=record["name"],
            description=record["description"],
            type=PipelineType(record["type"]),
            status=PipelineStatus(record["status"]),
            created_by=record["created_by"],
            updated_by=record["updated_by"],
            created_at=record["created_at"],
            updated_at=record["updated_at"],
        )

    def _version_to_record(self, version: PipelineVersion) -> dict[str, object]:
        return {
            "id": version.id,
            "owner_id": version.owner_id,
            "pipeline_id": version.pipeline_id,
            "business_case_id": version.business_case_id,
            "version_number": version.version_number,
            "status": version.status.value,
            "definition": version.definition,
            "definition_hash": version.definition_hash,
            "created_by": version.created_by,
            "created_at": version.created_at,
            "published_by": version.published_by,
            "published_at": version.published_at,
        }

    def _version_from_record(self, record: object) -> PipelineVersion:
        return PipelineVersion(
            id=record["id"],
            owner_id=record["owner_id"],
            pipeline_id=record["pipeline_id"],
            business_case_id=record["business_case_id"],
            version_number=record["version_number"],
            status=PipelineVersionStatus(record["status"]),
            definition=dict(record["definition"] or {}),
            definition_hash=record["definition_hash"],
            created_by=record["created_by"],
            created_at=record["created_at"],
            published_by=record["published_by"],
            published_at=record["published_at"],
        )

    def _run_to_record(self, run: PipelineRun) -> dict[str, object]:
        return {
            "id": run.id,
            "owner_id": run.owner_id,
            "pipeline_id": run.pipeline_id,
            "pipeline_version_id": run.pipeline_version_id,
            "business_case_id": run.business_case_id,
            "status": run.status.value,
            "trigger_type": run.trigger_type.value,
            "runtime_parameters": run.runtime_parameters,
            "is_dry_run": run.is_dry_run,
            "requested_step_id": run.requested_step_id,
            "input_row_count": run.input_row_count,
            "processed_row_count": run.processed_row_count,
            "output_row_count": run.output_row_count,
            "rejected_row_count": run.rejected_row_count,
            "warnings": run.warnings,
            "output_artifact_ids": run.output_artifact_ids,
            "output_manifest": run.output_manifest,
            "error_message": run.error_message,
            "created_by": run.created_by,
            "created_at": run.created_at,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
        }

    def _run_from_record(self, record: object) -> PipelineRun:
        return PipelineRun(
            id=record["id"],
            owner_id=record["owner_id"],
            pipeline_id=record["pipeline_id"],
            pipeline_version_id=record["pipeline_version_id"],
            business_case_id=record["business_case_id"],
            status=PipelineRunStatus(record["status"]),
            trigger_type=PipelineRunTrigger(record["trigger_type"]),
            runtime_parameters=dict(record["runtime_parameters"] or {}),
            is_dry_run=record["is_dry_run"],
            requested_step_id=record["requested_step_id"] or "",
            input_row_count=record["input_row_count"],
            processed_row_count=record["processed_row_count"],
            output_row_count=record["output_row_count"],
            rejected_row_count=record["rejected_row_count"],
            warnings=list(record["warnings"] or []),
            output_artifact_ids=list(record["output_artifact_ids"] or []),
            output_manifest=list(record["output_manifest"] or []),
            error_message=record["error_message"] or "",
            created_by=record["created_by"],
            created_at=record["created_at"],
            started_at=record["started_at"],
            finished_at=record["finished_at"],
        )

    @staticmethod
    def _step_run_to_record(step_run: PipelineStepRun) -> dict[str, object]:
        return {
            "id": step_run.id,
            "owner_id": step_run.owner_id,
            "pipeline_run_id": step_run.pipeline_run_id,
            "pipeline_step_id": step_run.pipeline_step_id,
            "step_type": step_run.step_type,
            "status": step_run.status.value,
            "input_row_count": step_run.input_row_count,
            "processed_row_count": step_run.processed_row_count,
            "output_row_count": step_run.output_row_count,
            "warnings": step_run.warnings,
            "output_manifest": step_run.output_manifest,
            "error_message": step_run.error_message,
            "started_at": step_run.started_at,
            "finished_at": step_run.finished_at,
        }

    @staticmethod
    def _step_run_from_record(record: object) -> PipelineStepRun:
        return PipelineStepRun(
            id=record["id"],
            owner_id=record["owner_id"],
            pipeline_run_id=record["pipeline_run_id"],
            pipeline_step_id=record["pipeline_step_id"],
            step_type=record["step_type"],
            status=PipelineRunStatus(record["status"]),
            input_row_count=record["input_row_count"],
            processed_row_count=record["processed_row_count"],
            output_row_count=record["output_row_count"],
            warnings=list(record["warnings"] or []),
            output_manifest=list(record["output_manifest"] or []),
            error_message=record["error_message"] or "",
            started_at=record["started_at"],
            finished_at=record["finished_at"],
        )
