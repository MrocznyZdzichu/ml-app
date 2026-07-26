from typing import Any, Protocol

from sqlalchemy import JSON, Boolean, Column, DateTime, Index, Integer, MetaData, String, Table, Text, case, func, or_, select, text
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
    Column("events", JSON, nullable=False, default=list),
    Column("output_artifact_ids", JSON, nullable=False, default=list),
    Column("output_manifest", JSON, nullable=False, default=list),
    Column("error_message", Text, nullable=False, default=""),
    Column("created_by", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("finished_at", DateTime(timezone=True), nullable=True),
)
Index(
    "ix_pipeline_runs_owner_created_at",
    pipeline_runs_table.c.owner_id,
    pipeline_runs_table.c.created_at.desc(),
)
Index(
    "ix_pipeline_runs_owner_pipeline_created_at",
    pipeline_runs_table.c.owner_id,
    pipeline_runs_table.c.pipeline_id,
    pipeline_runs_table.c.created_at.desc(),
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
    Column("events", JSON, nullable=False, default=list),
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

    def list_pipelines_for_business_cases(
        self,
        business_case_ids: set[str] | None,
    ) -> list[Pipeline]:
        ...

    def page_pipelines_for_business_cases(
        self,
        business_case_ids: set[str] | None,
        *,
        limit: int,
        offset: int,
        search: str = "",
        pipeline_type: str = "",
        pipeline_template: str = "",
        pipeline_status: str = "",
        include_deprecated: bool = True,
    ) -> tuple[list[Pipeline], int]:
        ...

    def list_pipeline_ids_for_business_cases(
        self,
        business_case_ids: set[str] | None,
    ) -> set[str]:
        ...

    def get_pipeline(self, pipeline_id: str) -> Pipeline | None:
        ...

    def update_pipeline(self, pipeline: Pipeline) -> Pipeline:
        ...

    def delete_pipeline_without_runs(self, pipeline_id: str) -> bool:
        ...

    def add_version(self, version: PipelineVersion) -> PipelineVersion:
        ...

    def list_versions(self, pipeline_id: str) -> list[PipelineVersion]:
        ...

    def page_versions(
        self,
        pipeline_id: str,
        *,
        limit: int,
        offset: int,
        status: str = "",
    ) -> tuple[list[PipelineVersion], int]:
        ...

    def list_versions_for_pipelines(
        self,
        owner_id: str,
        pipeline_ids: list[str],
    ) -> list[PipelineVersion]:
        ...

    def list_versions_for_pipeline_ids(
        self,
        pipeline_ids: set[str],
    ) -> list[PipelineVersion]:
        ...

    def list_versions_by_ids(
        self,
        version_ids: set[str],
    ) -> list[PipelineVersion]:
        ...

    def version_catalog_summaries(
        self,
        pipeline_ids: set[str],
    ) -> dict[str, dict[str, Any]]:
        ...

    def get_version(self, version_id: str) -> PipelineVersion | None:
        ...

    def get_draft_version(self, pipeline_id: str) -> PipelineVersion | None:
        ...

    def get_latest_version(self, pipeline_id: str) -> PipelineVersion | None:
        ...

    def get_latest_published_version(self, pipeline_id: str) -> PipelineVersion | None:
        ...

    def update_version(self, version: PipelineVersion) -> PipelineVersion:
        ...

    def add_run(self, run: PipelineRun) -> PipelineRun:
        ...

    def get_run(self, run_id: str) -> PipelineRun | None:
        ...

    def get_run_summary(self, run_id: str) -> PipelineRun | None:
        """Load run progress without events, parameters, or output manifests."""
        ...

    def list_run_references(self, run_ids: set[str]) -> dict[str, tuple[str, str]]:
        """Map run ID to (owner ID, pipeline ID) without loading run payloads."""
        ...

    def update_run(self, run: PipelineRun) -> PipelineRun:
        ...

    def list_runs(
        self,
        pipeline_id: str | None,
        owner_id: str,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[PipelineRun]:
        ...

    def list_run_summaries(
        self,
        owner_id: str,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[PipelineRun]:
        ...

    def list_run_summaries_for_pipelines(
        self,
        pipeline_ids: set[str],
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[PipelineRun]:
        ...

    def page_run_summaries_for_pipelines(
        self,
        pipeline_ids: set[str],
        *,
        limit: int,
        offset: int,
        search: str = "",
        run_status: str = "",
        pipeline_id: str = "",
        pipeline_version_id: str = "",
        business_case_id: str = "",
        trigger_type: str = "",
        dry_run: bool | None = None,
    ) -> tuple[list[PipelineRun], int]:
        ...

    def list_runs_for_pipelines(
        self,
        pipeline_ids: set[str],
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[PipelineRun]:
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

    def list_pipelines_for_business_cases(
        self,
        business_case_ids: set[str] | None,
    ) -> list[Pipeline]:
        return [
            item for item in self._pipelines.values()
            if business_case_ids is None or item.business_case_id in business_case_ids
        ]

    def page_pipelines_for_business_cases(
        self,
        business_case_ids: set[str] | None,
        *,
        limit: int,
        offset: int,
        search: str = "",
        pipeline_type: str = "",
        pipeline_template: str = "",
        pipeline_status: str = "",
        include_deprecated: bool = True,
    ) -> tuple[list[Pipeline], int]:
        needle = search.strip().casefold()
        items = [
            item
            for item in self._pipelines.values()
            if (business_case_ids is None or item.business_case_id in business_case_ids)
            and (not pipeline_type or item.type.value == pipeline_type)
            and (not pipeline_template or item.template == pipeline_template)
            and (not pipeline_status or item.status.value == pipeline_status)
            and (include_deprecated or item.status.value != "deprecated")
            and (
                not needle
                or needle in item.name.casefold()
                or needle in item.description.casefold()
            )
        ]
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return items[offset : offset + limit], len(items)

    def list_pipeline_ids_for_business_cases(
        self,
        business_case_ids: set[str] | None,
    ) -> set[str]:
        return {
            item.id for item in self._pipelines.values()
            if business_case_ids is None or item.business_case_id in business_case_ids
        }

    def get_pipeline(self, pipeline_id: str) -> Pipeline | None:
        return self._pipelines.get(pipeline_id)

    def update_pipeline(self, pipeline: Pipeline) -> Pipeline:
        self._pipelines[pipeline.id] = pipeline
        return pipeline

    def delete_pipeline_without_runs(self, pipeline_id: str) -> bool:
        if any(item.pipeline_id == pipeline_id for item in self._runs.values()):
            return False
        self._versions = {
            key: item for key, item in self._versions.items()
            if item.pipeline_id != pipeline_id
        }
        return self._pipelines.pop(pipeline_id, None) is not None

    def add_version(self, version: PipelineVersion) -> PipelineVersion:
        self._versions[version.id] = version
        return version

    def list_versions(self, pipeline_id: str) -> list[PipelineVersion]:
        return sorted(
            [item for item in self._versions.values() if item.pipeline_id == pipeline_id],
            key=lambda item: item.version_number,
        )

    def page_versions(
        self,
        pipeline_id: str,
        *,
        limit: int,
        offset: int,
        status: str = "",
    ) -> tuple[list[PipelineVersion], int]:
        items = [
            item
            for item in self._versions.values()
            if item.pipeline_id == pipeline_id
            and (not status or item.status.value == status)
        ]
        items.sort(key=lambda item: item.version_number, reverse=True)
        return items[offset : offset + limit], len(items)

    def list_versions_for_pipelines(
        self,
        owner_id: str,
        pipeline_ids: list[str],
    ) -> list[PipelineVersion]:
        return sorted(
            [
                item for item in self._versions.values()
                if item.owner_id == owner_id and item.pipeline_id in pipeline_ids
            ],
            key=lambda item: (item.pipeline_id, item.version_number),
        )

    def list_versions_for_pipeline_ids(
        self,
        pipeline_ids: set[str],
    ) -> list[PipelineVersion]:
        return sorted(
            [
                item for item in self._versions.values()
                if item.pipeline_id in pipeline_ids
            ],
            key=lambda item: (item.pipeline_id, item.version_number),
        )

    def list_versions_by_ids(
        self,
        version_ids: set[str],
    ) -> list[PipelineVersion]:
        return [
            item for item in self._versions.values()
            if item.id in version_ids
        ]

    def version_catalog_summaries(
        self,
        pipeline_ids: set[str],
    ) -> dict[str, dict[str, Any]]:
        summaries: dict[str, dict[str, Any]] = {}
        for pipeline_id in pipeline_ids:
            versions = self.list_versions(pipeline_id)
            published = [
                item for item in versions
                if item.status == PipelineVersionStatus.PUBLISHED
            ]
            drafts = [
                item for item in versions
                if item.status == PipelineVersionStatus.DRAFT
            ]
            selected = (
                max(published, key=lambda item: item.version_number)
                if published
                else max(drafts, key=lambda item: item.version_number, default=None)
            )
            summaries[pipeline_id] = {
                "latest_published_version_number": (
                    max(item.version_number for item in published)
                    if published else None
                ),
                "published_version_count": len(published),
                "draft_version_number": (
                    max(item.version_number for item in drafts)
                    if drafts else None
                ),
                "definition": selected.definition if selected else {},
            }
        return summaries

    def get_version(self, version_id: str) -> PipelineVersion | None:
        return self._versions.get(version_id)

    def get_draft_version(self, pipeline_id: str) -> PipelineVersion | None:
        for version in self._versions.values():
            if version.pipeline_id == pipeline_id and version.status == PipelineVersionStatus.DRAFT:
                return version
        return None

    def get_latest_version(self, pipeline_id: str) -> PipelineVersion | None:
        versions = self.list_versions(pipeline_id)
        return versions[-1] if versions else None

    def get_latest_published_version(self, pipeline_id: str) -> PipelineVersion | None:
        published = [
            version
            for version in self.list_versions(pipeline_id)
            if version.status == PipelineVersionStatus.PUBLISHED
        ]
        return published[-1] if published else None

    def update_version(self, version: PipelineVersion) -> PipelineVersion:
        self._versions[version.id] = version
        return version

    def add_run(self, run: PipelineRun) -> PipelineRun:
        self._runs[run.id] = run
        return run

    def get_run(self, run_id: str) -> PipelineRun | None:
        return self._runs.get(run_id)

    def get_run_summary(self, run_id: str) -> PipelineRun | None:
        return self._runs.get(run_id)

    def list_run_references(self, run_ids: set[str]) -> dict[str, tuple[str, str]]:
        return {
            run.id: (run.owner_id, run.pipeline_id)
            for run in self._runs.values()
            if run.id in run_ids
        }

    def update_run(self, run: PipelineRun) -> PipelineRun:
        self._runs[run.id] = run
        return run

    def list_runs(
        self,
        pipeline_id: str | None,
        owner_id: str,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[PipelineRun]:
        matching = [
            item
            for item in self._runs.values()
            if item.owner_id == owner_id and (pipeline_id is None or item.pipeline_id == pipeline_id)
        ]
        matching.sort(key=lambda item: item.created_at, reverse=True)
        return matching[offset:offset + limit]

    def list_run_summaries(
        self,
        owner_id: str,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[PipelineRun]:
        return self.list_runs(None, owner_id, limit=limit, offset=offset)

    def list_run_summaries_for_pipelines(
        self,
        pipeline_ids: set[str],
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[PipelineRun]:
        matching = [
            item for item in self._runs.values()
            if item.pipeline_id in pipeline_ids
        ]
        matching.sort(key=lambda item: item.created_at, reverse=True)
        return matching[offset:offset + limit]

    def page_run_summaries_for_pipelines(
        self,
        pipeline_ids: set[str],
        *,
        limit: int,
        offset: int,
        search: str = "",
        run_status: str = "",
        pipeline_id: str = "",
        pipeline_version_id: str = "",
        business_case_id: str = "",
        trigger_type: str = "",
        dry_run: bool | None = None,
    ) -> tuple[list[PipelineRun], int]:
        needle = search.strip().casefold()
        matching = [
            item
            for item in self._runs.values()
            if item.pipeline_id in pipeline_ids
            and (
                not run_status
                or item.status.value == run_status
                or (
                    run_status == "active"
                    and item.status.value in {"queued", "running"}
                )
            )
            and (not pipeline_id or item.pipeline_id == pipeline_id)
            and (
                not pipeline_version_id
                or item.pipeline_version_id == pipeline_version_id
            )
            and (not business_case_id or item.business_case_id == business_case_id)
            and (not trigger_type or item.trigger_type == trigger_type)
            and (dry_run is None or item.is_dry_run == dry_run)
            and (
                not needle
                or needle in item.id.casefold()
                or needle in item.pipeline_id.casefold()
                or needle in item.error_message.casefold()
            )
        ]
        matching.sort(
            key=lambda item: (item.created_at, item.id),
            reverse=True,
        )
        return matching[offset : offset + limit], len(matching)

    def list_runs_for_pipelines(
        self,
        pipeline_ids: set[str],
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[PipelineRun]:
        matching = [
            item for item in self._runs.values()
            if item.pipeline_id in pipeline_ids
        ]
        matching.sort(key=lambda item: item.created_at, reverse=True)
        return matching[offset:offset + limit]

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

    def list_pipelines_for_business_cases(
        self,
        business_case_ids: set[str] | None,
    ) -> list[Pipeline]:
        self._ensure_initialized()
        if business_case_ids is not None and not business_case_ids:
            return []
        statement = select(pipelines_table)
        if business_case_ids is not None:
            statement = statement.where(
                pipelines_table.c.business_case_id.in_(business_case_ids)
            )
        statement = statement.order_by(pipelines_table.c.updated_at.desc())
        with self.engine.begin() as connection:
            return [self._pipeline_from_record(row._mapping) for row in connection.execute(statement)]

    def page_pipelines_for_business_cases(
        self,
        business_case_ids: set[str] | None,
        *,
        limit: int,
        offset: int,
        search: str = "",
        pipeline_type: str = "",
        pipeline_template: str = "",
        pipeline_status: str = "",
        include_deprecated: bool = True,
    ) -> tuple[list[Pipeline], int]:
        self._ensure_initialized()
        if business_case_ids is not None and not business_case_ids:
            return [], 0
        filters = []
        if business_case_ids is not None:
            filters.append(pipelines_table.c.business_case_id.in_(business_case_ids))
        if pipeline_type:
            filters.append(pipelines_table.c.type == pipeline_type)
        if pipeline_template:
            filters.append(pipelines_table.c.template == pipeline_template)
        if pipeline_status:
            filters.append(pipelines_table.c.status == pipeline_status)
        if not include_deprecated:
            filters.append(pipelines_table.c.status != PipelineStatus.DEPRECATED.value)
        needle = search.strip()
        if needle:
            pattern = f"%{needle}%"
            filters.append(or_(
                pipelines_table.c.name.ilike(pattern),
                pipelines_table.c.description.ilike(pattern),
            ))
        page_statement = select(pipelines_table)
        count_statement = select(func.count()).select_from(pipelines_table)
        if filters:
            page_statement = page_statement.where(*filters)
            count_statement = count_statement.where(*filters)
        page_statement = (
            page_statement
            .order_by(pipelines_table.c.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        with self.engine.begin() as connection:
            total = int(connection.execute(count_statement).scalar_one())
            items = [
                self._pipeline_from_record(row._mapping)
                for row in connection.execute(page_statement)
            ]
        return items, total

    def list_pipeline_ids_for_business_cases(
        self,
        business_case_ids: set[str] | None,
    ) -> set[str]:
        self._ensure_initialized()
        if business_case_ids is not None and not business_case_ids:
            return set()
        statement = select(pipelines_table.c.id)
        if business_case_ids is not None:
            statement = statement.where(
                pipelines_table.c.business_case_id.in_(business_case_ids)
            )
        with self.engine.begin() as connection:
            return {str(row[0]) for row in connection.execute(statement)}

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

    def delete_pipeline_without_runs(self, pipeline_id: str) -> bool:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            existing_run = connection.execute(
                select(pipeline_runs_table.c.id)
                .where(pipeline_runs_table.c.pipeline_id == pipeline_id)
                .limit(1)
            ).first()
            if existing_run:
                return False
            connection.execute(
                pipeline_versions_table.delete().where(
                    pipeline_versions_table.c.pipeline_id == pipeline_id
                )
            )
            result = connection.execute(
                pipelines_table.delete().where(pipelines_table.c.id == pipeline_id)
            )
        return bool(result.rowcount)

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

    def page_versions(
        self,
        pipeline_id: str,
        *,
        limit: int,
        offset: int,
        status: str = "",
    ) -> tuple[list[PipelineVersion], int]:
        self._ensure_initialized()
        filters = [pipeline_versions_table.c.pipeline_id == pipeline_id]
        if status:
            filters.append(pipeline_versions_table.c.status == status)
        with self.engine.begin() as connection:
            total = int(connection.execute(
                select(func.count()).select_from(pipeline_versions_table).where(*filters)
            ).scalar_one())
            rows = connection.execute(
                select(pipeline_versions_table)
                .where(*filters)
                .order_by(pipeline_versions_table.c.version_number.desc())
                .limit(limit)
                .offset(offset)
            )
            return [self._version_from_record(row._mapping) for row in rows], total

    def list_versions_for_pipelines(
        self,
        owner_id: str,
        pipeline_ids: list[str],
    ) -> list[PipelineVersion]:
        if not pipeline_ids:
            return []
        self._ensure_initialized()
        statement = (
            select(pipeline_versions_table)
            .where(
                pipeline_versions_table.c.owner_id == owner_id,
                pipeline_versions_table.c.pipeline_id.in_(pipeline_ids),
            )
            .order_by(
                pipeline_versions_table.c.pipeline_id.asc(),
                pipeline_versions_table.c.version_number.asc(),
            )
        )
        with self.engine.begin() as connection:
            return [
                self._version_from_record(row._mapping)
                for row in connection.execute(statement)
            ]

    def list_versions_for_pipeline_ids(
        self,
        pipeline_ids: set[str],
    ) -> list[PipelineVersion]:
        if not pipeline_ids:
            return []
        self._ensure_initialized()
        statement = (
            select(pipeline_versions_table)
            .where(pipeline_versions_table.c.pipeline_id.in_(pipeline_ids))
            .order_by(
                pipeline_versions_table.c.pipeline_id.asc(),
                pipeline_versions_table.c.version_number.asc(),
            )
        )
        with self.engine.begin() as connection:
            return [
                self._version_from_record(row._mapping)
                for row in connection.execute(statement)
            ]

    def list_versions_by_ids(
        self,
        version_ids: set[str],
    ) -> list[PipelineVersion]:
        if not version_ids:
            return []
        self._ensure_initialized()
        statement = select(pipeline_versions_table).where(
            pipeline_versions_table.c.id.in_(version_ids)
        )
        with self.engine.begin() as connection:
            return [
                self._version_from_record(row._mapping)
                for row in connection.execute(statement)
            ]

    def version_catalog_summaries(
        self,
        pipeline_ids: set[str],
    ) -> dict[str, dict[str, Any]]:
        """Return counts and one representative definition per pipeline."""
        if not pipeline_ids:
            return {}
        self._ensure_initialized()
        published = PipelineVersionStatus.PUBLISHED.value
        draft = PipelineVersionStatus.DRAFT.value
        stats = (
            select(
                pipeline_versions_table.c.pipeline_id.label("pipeline_id"),
                func.max(pipeline_versions_table.c.version_number)
                .filter(pipeline_versions_table.c.status == published)
                .label("latest_published_version_number"),
                func.count()
                .filter(pipeline_versions_table.c.status == published)
                .label("published_version_count"),
                func.max(pipeline_versions_table.c.version_number)
                .filter(pipeline_versions_table.c.status == draft)
                .label("draft_version_number"),
            )
            .where(pipeline_versions_table.c.pipeline_id.in_(pipeline_ids))
            .group_by(pipeline_versions_table.c.pipeline_id)
            .subquery("pipeline_version_catalog_stats")
        )
        selected = pipeline_versions_table.alias("selected_pipeline_version")
        selected_definition = (
            select(selected.c.definition)
            .where(selected.c.pipeline_id == stats.c.pipeline_id)
            .order_by(
                case((selected.c.status == published, 0), else_=1),
                selected.c.version_number.desc(),
            )
            .limit(1)
            .scalar_subquery()
        )
        statement = select(
            stats.c.pipeline_id,
            stats.c.latest_published_version_number,
            stats.c.published_version_count,
            stats.c.draft_version_number,
            selected_definition.label("definition"),
        )
        with self.engine.begin() as connection:
            return {
                str(row.pipeline_id): {
                    "latest_published_version_number": (
                        int(row.latest_published_version_number)
                        if row.latest_published_version_number is not None
                        else None
                    ),
                    "published_version_count": int(row.published_version_count or 0),
                    "draft_version_number": (
                        int(row.draft_version_number)
                        if row.draft_version_number is not None
                        else None
                    ),
                    "definition": dict(row.definition or {}),
                }
                for row in connection.execute(statement)
            }

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

    def get_latest_version(self, pipeline_id: str) -> PipelineVersion | None:
        self._ensure_initialized()
        statement = (
            select(pipeline_versions_table)
            .where(pipeline_versions_table.c.pipeline_id == pipeline_id)
            .order_by(pipeline_versions_table.c.version_number.desc())
            .limit(1)
        )
        with self.engine.begin() as connection:
            row = connection.execute(statement).first()
        return self._version_from_record(row._mapping) if row else None

    def get_latest_published_version(self, pipeline_id: str) -> PipelineVersion | None:
        self._ensure_initialized()
        statement = (
            select(pipeline_versions_table)
            .where(
                pipeline_versions_table.c.pipeline_id == pipeline_id,
                pipeline_versions_table.c.status
                == PipelineVersionStatus.PUBLISHED.value,
            )
            .order_by(pipeline_versions_table.c.version_number.desc())
            .limit(1)
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

    def get_run_summary(self, run_id: str) -> PipelineRun | None:
        self._ensure_initialized()
        statement = select(*self._run_summary_columns()).where(
            pipeline_runs_table.c.id == run_id
        )
        with self.engine.begin() as connection:
            row = connection.execute(statement).first()
        return self._run_from_record(row._mapping) if row else None

    def list_run_references(self, run_ids: set[str]) -> dict[str, tuple[str, str]]:
        if not run_ids:
            return {}
        self._ensure_initialized()
        statement = select(
            pipeline_runs_table.c.id,
            pipeline_runs_table.c.owner_id,
            pipeline_runs_table.c.pipeline_id,
        ).where(pipeline_runs_table.c.id.in_(run_ids))
        with self.engine.begin() as connection:
            return {
                row.id: (row.owner_id, row.pipeline_id)
                for row in connection.execute(statement)
            }

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

    def list_runs(
        self,
        pipeline_id: str | None,
        owner_id: str,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[PipelineRun]:
        self._ensure_initialized()
        statement = select(pipeline_runs_table).where(pipeline_runs_table.c.owner_id == owner_id)
        if pipeline_id is not None:
            statement = statement.where(pipeline_runs_table.c.pipeline_id == pipeline_id)
        statement = (
            statement
            .order_by(pipeline_runs_table.c.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        with self.engine.begin() as connection:
            return [self._run_from_record(row._mapping) for row in connection.execute(statement)]

    def list_run_summaries(
        self,
        owner_id: str,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[PipelineRun]:
        self._ensure_initialized()
        statement = (
            select(*self._run_summary_columns())
            .where(pipeline_runs_table.c.owner_id == owner_id)
            .order_by(pipeline_runs_table.c.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        with self.engine.begin() as connection:
            return [
                self._run_from_record(row._mapping)
                for row in connection.execute(statement)
            ]

    def list_run_summaries_for_pipelines(
        self,
        pipeline_ids: set[str],
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[PipelineRun]:
        if not pipeline_ids:
            return []
        self._ensure_initialized()
        statement = (
            select(*self._run_summary_columns())
            .where(pipeline_runs_table.c.pipeline_id.in_(pipeline_ids))
            .order_by(pipeline_runs_table.c.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        with self.engine.begin() as connection:
            return [
                self._run_from_record(row._mapping)
                for row in connection.execute(statement)
            ]

    def page_run_summaries_for_pipelines(
        self,
        pipeline_ids: set[str],
        *,
        limit: int,
        offset: int,
        search: str = "",
        run_status: str = "",
        pipeline_id: str = "",
        pipeline_version_id: str = "",
        business_case_id: str = "",
        trigger_type: str = "",
        dry_run: bool | None = None,
    ) -> tuple[list[PipelineRun], int]:
        if not pipeline_ids:
            return [], 0
        self._ensure_initialized()
        filters = [pipeline_runs_table.c.pipeline_id.in_(pipeline_ids)]
        if run_status == "active":
            filters.append(
                pipeline_runs_table.c.status.in_(("queued", "running"))
            )
        elif run_status:
            filters.append(pipeline_runs_table.c.status == run_status)
        if pipeline_id:
            filters.append(pipeline_runs_table.c.pipeline_id == pipeline_id)
        if pipeline_version_id:
            filters.append(
                pipeline_runs_table.c.pipeline_version_id == pipeline_version_id
            )
        if business_case_id:
            filters.append(
                pipeline_runs_table.c.business_case_id == business_case_id
            )
        if trigger_type:
            filters.append(pipeline_runs_table.c.trigger_type == trigger_type)
        if dry_run is not None:
            filters.append(pipeline_runs_table.c.is_dry_run == dry_run)
        needle = search.strip()
        if needle:
            pattern = f"%{needle}%"
            filters.append(or_(
                pipeline_runs_table.c.id.ilike(pattern),
                pipeline_runs_table.c.pipeline_id.ilike(pattern),
                pipeline_runs_table.c.error_message.ilike(pattern),
            ))
        count_statement = (
            select(func.count())
            .select_from(pipeline_runs_table)
            .where(*filters)
        )
        page_statement = (
            select(*self._run_summary_columns())
            .where(*filters)
            .order_by(
                pipeline_runs_table.c.created_at.desc(),
                pipeline_runs_table.c.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        with self.engine.begin() as connection:
            total = int(connection.execute(count_statement).scalar_one())
            runs = [
                self._run_from_record(row._mapping)
                for row in connection.execute(page_statement)
            ]
        return runs, total

    @staticmethod
    def _run_summary_columns() -> list[Any]:
        return [
            pipeline_runs_table.c.id,
            pipeline_runs_table.c.owner_id,
            pipeline_runs_table.c.pipeline_id,
            pipeline_runs_table.c.pipeline_version_id,
            pipeline_runs_table.c.business_case_id,
            pipeline_runs_table.c.status,
            pipeline_runs_table.c.trigger_type,
            pipeline_runs_table.c.is_dry_run,
            pipeline_runs_table.c.requested_step_id,
            pipeline_runs_table.c.input_row_count,
            pipeline_runs_table.c.processed_row_count,
            pipeline_runs_table.c.output_row_count,
            pipeline_runs_table.c.rejected_row_count,
            pipeline_runs_table.c.error_message,
            pipeline_runs_table.c.created_by,
            pipeline_runs_table.c.created_at,
            pipeline_runs_table.c.started_at,
            pipeline_runs_table.c.finished_at,
        ]

    def list_runs_for_pipelines(
        self,
        pipeline_ids: set[str],
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[PipelineRun]:
        if not pipeline_ids:
            return []
        self._ensure_initialized()
        statement = (
            select(pipeline_runs_table)
            .where(pipeline_runs_table.c.pipeline_id.in_(pipeline_ids))
            .order_by(pipeline_runs_table.c.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        with self.engine.begin() as connection:
            return [
                self._run_from_record(row._mapping)
                for row in connection.execute(statement)
            ]

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
                f"ALTER TABLE {PIPELINE_SCHEMA}.pipeline_runs "
                "ADD COLUMN IF NOT EXISTS events JSON NOT NULL DEFAULT '[]'"
            ))
            connection.execute(text(
                f"ALTER TABLE {PIPELINE_SCHEMA}.pipeline_step_runs "
                "ADD COLUMN IF NOT EXISTS events JSON NOT NULL DEFAULT '[]'"
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
            "events": run.events,
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
            runtime_parameters=dict(record.get("runtime_parameters") or {}),
            is_dry_run=record["is_dry_run"],
            requested_step_id=record["requested_step_id"] or "",
            input_row_count=record["input_row_count"],
            processed_row_count=record["processed_row_count"],
            output_row_count=record["output_row_count"],
            rejected_row_count=record["rejected_row_count"],
            warnings=list(record.get("warnings") or []),
            events=list(record.get("events") or []),
            output_artifact_ids=list(record.get("output_artifact_ids") or []),
            output_manifest=list(record.get("output_manifest") or []),
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
            "events": step_run.events,
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
            events=list(record.get("events") or []),
            output_manifest=list(record["output_manifest"] or []),
            error_message=record["error_message"] or "",
            started_at=record["started_at"],
            finished_at=record["finished_at"],
        )
