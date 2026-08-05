from dataclasses import replace
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    func,
    or_,
    select,
    text,
)
from sqlalchemy.engine import Engine

from app.core.database import get_engine
from app.modules.business_cases.repository import business_case_data_attachments_table
from app.modules.pipelines.repository import pipelines_table
from app.modules.datasets.domain import DataAsset
from app.modules.datasets.domain import DataAssetStatus, SourceType


DATASET_SCHEMA = "mlapp"
metadata = MetaData(schema=DATASET_SCHEMA)
DATASET_SUMMARY_METADATA_KEYS = (
    "pipeline_output",
    "origin",
    "source_schema",
    "data_roles",
    "data_view",
)

data_assets_table = Table(
    "data_assets",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("owner_id", String(64), nullable=False, index=True),
    Column("name", String(255), nullable=False),
    Column("source_type", String(32), nullable=False),
    Column("format", String(32), nullable=False),
    Column("logical_id", String(64), nullable=False, index=True),
    Column("version_number", Integer, nullable=False, default=1),
    Column("version_stage", String(32), nullable=False, default="source"),
    Column("description", Text, nullable=False, default=""),
    Column("original_filename", String(512), nullable=True),
    Column("location_uri", Text, nullable=True),
    Column("file_size_bytes", Integer, nullable=True),
    Column("row_count", Integer, nullable=True),
    Column("has_header", Boolean, nullable=True),
    Column("uploaded_by", String(64), nullable=True),
    Column("uploaded_at", DateTime(timezone=True), nullable=True),
    Column("deleted_by", String(64), nullable=True),
    Column("deleted_at", DateTime(timezone=True), nullable=True),
    Column("status", String(32), nullable=False),
    Column("tags", JSON, nullable=False, default=list),
    Column("metadata", JSON, nullable=False, default=dict),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
Index(
    "uq_data_assets_logical_version",
    data_assets_table.c.owner_id,
    data_assets_table.c.logical_id,
    data_assets_table.c.version_number,
    unique=True,
)


class DatasetRepository(Protocol):
    def add(self, asset: DataAsset) -> DataAsset:
        ...

    def add_version(self, asset: DataAsset) -> DataAsset:
        ...

    def list_for_owner(self, owner_id: str) -> list[DataAsset]:
        ...

    def list_all(self) -> list[DataAsset]:
        ...

    def list_summaries(self, owner_id: str | None = None) -> list[DataAsset]:
        ...

    def list_by_ids(
        self,
        asset_ids: set[str],
        *,
        summary: bool = False,
    ) -> list[DataAsset]:
        ...

    def get_many(self, asset_ids: set[str]) -> dict[str, DataAsset]:
        ...

    def page_by_ids(
        self,
        asset_ids: set[str] | None,
        *,
        limit: int,
        offset: int,
        summary: bool = False,
        search: str = "",
        status: str = "",
        source_type: str = "",
        asset_kind: str = "",
        include_deleted: bool = True,
        families: bool = False,
        business_case_id: str = "",
        pipeline_id: str = "",
        pipeline_type: str = "",
        uploaded_only: bool = False,
        owner_id: str = "",
    ) -> tuple[list[DataAsset], int]:
        ...

    def get(self, asset_id: str) -> DataAsset | None:
        ...

    def list_versions(self, owner_id: str, logical_id: str) -> list[DataAsset]:
        ...

    def list_by_logical_id(self, logical_id: str) -> list[DataAsset]:
        ...

    def get_latest_version(self, owner_id: str, logical_id: str) -> DataAsset | None:
        ...

    def update(self, asset: DataAsset) -> DataAsset:
        ...


class InMemoryDatasetRepository:
    def __init__(self) -> None:
        self._items: dict[str, DataAsset] = {}

    def add(self, asset: DataAsset) -> DataAsset:
        self._items[asset.id] = asset
        return asset

    def add_version(self, asset: DataAsset) -> DataAsset:
        versions = self.list_versions(asset.owner_id, asset.logical_id)
        asset.version_number = max((item.version_number for item in versions), default=0) + 1
        self._items[asset.id] = asset
        return asset

    def list_for_owner(self, owner_id: str) -> list[DataAsset]:
        return [asset for asset in self._items.values() if asset.owner_id == owner_id]

    def list_all(self) -> list[DataAsset]:
        return list(self._items.values())

    def list_summaries(self, owner_id: str | None = None) -> list[DataAsset]:
        return [
            replace(
                asset,
                metadata={
                    key: asset.metadata[key]
                    for key in DATASET_SUMMARY_METADATA_KEYS
                    if key in asset.metadata
                },
            )
            for asset in self._items.values()
            if owner_id is None or asset.owner_id == owner_id
        ]

    def list_by_ids(
        self,
        asset_ids: set[str],
        *,
        summary: bool = False,
    ) -> list[DataAsset]:
        items = [asset for asset in self._items.values() if asset.id in asset_ids]
        if not summary:
            return items
        return [
            replace(
                asset,
                metadata={
                    key: asset.metadata[key]
                    for key in DATASET_SUMMARY_METADATA_KEYS
                    if key in asset.metadata
                },
            )
            for asset in items
        ]

    def get_many(self, asset_ids: set[str]) -> dict[str, DataAsset]:
        return {
            asset_id: self._items[asset_id]
            for asset_id in asset_ids
            if asset_id in self._items
        }

    def page_by_ids(
        self,
        asset_ids: set[str] | None,
        *,
        limit: int,
        offset: int,
        summary: bool = False,
        search: str = "",
        status: str = "",
        source_type: str = "",
        asset_kind: str = "",
        include_deleted: bool = True,
        families: bool = False,
        business_case_id: str = "",
        pipeline_id: str = "",
        pipeline_type: str = "",
        uploaded_only: bool = False,
        owner_id: str = "",
    ) -> tuple[list[DataAsset], int]:
        needle = search.strip().casefold()
        candidates = [
            asset
            for asset in self._items.values()
            if asset_ids is None or asset.id in asset_ids
            if not owner_id or asset.owner_id == owner_id
        ]
        if families:
            grouped: dict[str, list[DataAsset]] = {}
            for asset in candidates:
                grouped.setdefault(asset.logical_id, []).append(asset)
            candidates = [
                max(
                    versions,
                    key=lambda item: (
                        item.version_number,
                        item.created_at,
                        item.id,
                    ),
                )
                for versions in grouped.values()
            ]
        items = [
            asset
            for asset in candidates
            if (asset_ids is None or asset.id in asset_ids)
            and (not status or asset.status.value == status)
            and (not source_type or asset.source_type.value == source_type)
            and (
                not asset_kind
                or (asset_kind == "view" and asset.source_type.value == "view")
                or (asset_kind == "dataset" and asset.source_type.value != "view")
            )
            and (include_deleted or asset.status.value != "deleted")
            and (
                not pipeline_id
                or str((asset.metadata.get("pipeline_output") or {}).get("pipeline_id") or "")
                == pipeline_id
            )
            and (
                not uploaded_only
                or (
                    asset.source_type.value != "view"
                    and not str((asset.metadata.get("pipeline_output") or {}).get("pipeline_id") or "")
                    and asset.metadata.get("origin") != "platform_generated"
                )
            )
            and (
                not needle
                or any(
                    needle in str(value or "").casefold()
                    for value in (
                        asset.name,
                        asset.description,
                        asset.logical_id,
                        asset.original_filename,
                    )
                )
            )
        ]
        items.sort(key=lambda asset: asset.created_at, reverse=True)
        page = items[offset : offset + limit]
        if summary:
            page = [
                replace(
                    asset,
                    metadata={
                        key: asset.metadata[key]
                        for key in DATASET_SUMMARY_METADATA_KEYS
                        if key in asset.metadata
                    },
                )
                for asset in page
            ]
        return page, len(items)

    def get(self, asset_id: str) -> DataAsset | None:
        return self._items.get(asset_id)

    def list_versions(self, owner_id: str, logical_id: str) -> list[DataAsset]:
        return sorted(
            (
                asset for asset in self._items.values()
                if asset.owner_id == owner_id and asset.logical_id == logical_id
            ),
            key=lambda asset: asset.version_number,
        )

    def list_by_logical_id(self, logical_id: str) -> list[DataAsset]:
        return sorted(
            (
                asset for asset in self._items.values()
                if asset.logical_id == logical_id
            ),
            key=lambda asset: asset.version_number,
        )

    def get_latest_version(self, owner_id: str, logical_id: str) -> DataAsset | None:
        versions = [
            asset for asset in self.list_versions(owner_id, logical_id)
            if asset.status != DataAssetStatus.DELETED
        ]
        return versions[-1] if versions else None

    def update(self, asset: DataAsset) -> DataAsset:
        asset.updated_at = datetime.now(timezone.utc)
        self._items[asset.id] = asset
        return asset


class PostgresDatasetRepository:
    def __init__(self, engine: Engine | None = None) -> None:
        self.engine = engine or get_engine()
        self._initialized = False

    def add(self, asset: DataAsset) -> DataAsset:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            connection.execute(
                data_assets_table.insert().values(**self._to_record(asset)),
            )
        return asset

    def add_version(self, asset: DataAsset) -> DataAsset:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:logical_id))"),
                {"logical_id": f"{asset.owner_id}:{asset.logical_id}"},
            )
            next_version = connection.execute(
                select(func.coalesce(func.max(data_assets_table.c.version_number), 0) + 1)
                .where(data_assets_table.c.owner_id == asset.owner_id)
                .where(data_assets_table.c.logical_id == asset.logical_id)
            ).scalar_one()
            asset.version_number = int(next_version)
            connection.execute(data_assets_table.insert().values(**self._to_record(asset)))
        return asset

    def list_for_owner(self, owner_id: str) -> list[DataAsset]:
        self._ensure_initialized()
        statement = (
            select(data_assets_table)
            .where(data_assets_table.c.owner_id == owner_id)
            .order_by(data_assets_table.c.created_at.desc())
        )
        with self.engine.begin() as connection:
            return [self._from_record(row._mapping) for row in connection.execute(statement)]

    def list_all(self) -> list[DataAsset]:
        self._ensure_initialized()
        statement = select(data_assets_table).order_by(data_assets_table.c.created_at.desc())
        with self.engine.begin() as connection:
            return [self._from_record(row._mapping) for row in connection.execute(statement)]

    def list_summaries(self, owner_id: str | None = None) -> list[DataAsset]:
        """Project catalog fields and the small metadata subset consumed by the UI."""
        return self._list_summaries(owner_id=owner_id)

    def list_by_ids(
        self,
        asset_ids: set[str],
        *,
        summary: bool = False,
    ) -> list[DataAsset]:
        self._ensure_initialized()
        if not asset_ids:
            return []
        if summary:
            return self._list_summaries(asset_ids=asset_ids)
        statement = (
            select(data_assets_table)
            .where(data_assets_table.c.id.in_(asset_ids))
            .order_by(data_assets_table.c.created_at.desc())
        )
        with self.engine.begin() as connection:
            return [
                self._from_record(row._mapping)
                for row in connection.execute(statement)
            ]

    def get_many(self, asset_ids: set[str]) -> dict[str, DataAsset]:
        return {
            asset.id: asset
            for asset in self.list_by_ids(asset_ids)
        }

    def page_by_ids(
        self,
        asset_ids: set[str] | None,
        *,
        limit: int,
        offset: int,
        summary: bool = False,
        search: str = "",
        status: str = "",
        source_type: str = "",
        asset_kind: str = "",
        include_deleted: bool = True,
        families: bool = False,
        business_case_id: str = "",
        pipeline_id: str = "",
        pipeline_type: str = "",
        uploaded_only: bool = False,
        owner_id: str = "",
    ) -> tuple[list[DataAsset], int]:
        self._ensure_initialized()
        if asset_ids is not None and not asset_ids:
            return [], 0
        if families:
            return self._page_family_summaries(
                asset_ids,
                limit=limit,
                offset=offset,
                search=search,
                status=status,
                source_type=source_type,
                asset_kind=asset_kind,
                include_deleted=include_deleted,
                business_case_id=business_case_id,
                pipeline_id=pipeline_id,
                pipeline_type=pipeline_type,
                uploaded_only=uploaded_only,
                owner_id=owner_id,
            )
        filters = []
        if asset_ids is not None:
            filters.append(data_assets_table.c.id.in_(asset_ids))
        if owner_id:
            filters.append(data_assets_table.c.owner_id == owner_id)
        if status:
            filters.append(data_assets_table.c.status == status)
        if source_type:
            filters.append(data_assets_table.c.source_type == source_type)
        if asset_kind == "view":
            filters.append(data_assets_table.c.source_type == "view")
        elif asset_kind == "dataset":
            filters.append(data_assets_table.c.source_type != "view")
        if not include_deleted:
            filters.append(data_assets_table.c.status != "deleted")
        needle = search.strip()
        if needle:
            pattern = f"%{needle}%"
            filters.append(or_(
                data_assets_table.c.name.ilike(pattern),
                data_assets_table.c.description.ilike(pattern),
                data_assets_table.c.logical_id.ilike(pattern),
                data_assets_table.c.original_filename.ilike(pattern),
            ))
        if summary:
            columns = [
                column
                for column in data_assets_table.c
                if column.name != "metadata"
            ]
            page_statement = select(
                *columns,
                *(
                    data_assets_table.c.metadata[key].label(f"metadata_{key}")
                    for key in DATASET_SUMMARY_METADATA_KEYS
                ),
            )
        else:
            page_statement = select(data_assets_table)
        count_statement = select(func.count()).select_from(data_assets_table)
        if filters:
            page_statement = page_statement.where(*filters)
            count_statement = count_statement.where(*filters)
        page_statement = (
            page_statement
            .order_by(data_assets_table.c.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        with self.engine.begin() as connection:
            total = int(connection.execute(count_statement).scalar_one())
            rows = [row._mapping for row in connection.execute(page_statement)]
        if not summary:
            return [self._from_record(row) for row in rows], total
        items: list[DataAsset] = []
        for row in rows:
            values = dict(row)
            values["metadata"] = {
                key: values.get(f"metadata_{key}")
                for key in DATASET_SUMMARY_METADATA_KEYS
                if values.get(f"metadata_{key}") is not None
            }
            items.append(self._from_record(values))
        return items, total

    def _page_family_summaries(
        self,
        asset_ids: set[str] | None,
        *,
        limit: int,
        offset: int,
        search: str,
        status: str,
        source_type: str,
        asset_kind: str,
        include_deleted: bool,
        business_case_id: str,
        pipeline_id: str,
        pipeline_type: str,
        uploaded_only: bool,
        owner_id: str,
    ) -> tuple[list[DataAsset], int]:
        columns = [
            column
            for column in data_assets_table.c
            if column.name != "metadata"
        ]
        ranked = select(
            *columns,
            *(
                (
                    data_assets_table.c.metadata[key].as_string()
                    if key == "origin"
                    else data_assets_table.c.metadata[key]
                ).label(f"metadata_{key}")
                for key in DATASET_SUMMARY_METADATA_KEYS
            ),
            func.row_number().over(
                partition_by=data_assets_table.c.logical_id,
                order_by=(
                    data_assets_table.c.version_number.desc(),
                    data_assets_table.c.created_at.desc(),
                    data_assets_table.c.id.desc(),
                ),
            ).label("family_rank"),
        )
        if asset_ids is not None:
            ranked = ranked.where(data_assets_table.c.id.in_(asset_ids))
        if owner_id:
            ranked = ranked.where(data_assets_table.c.owner_id == owner_id)
        if business_case_id:
            attached_logical_ids = (
                select(data_assets_table.c.logical_id)
                .join(
                    business_case_data_attachments_table,
                    business_case_data_attachments_table.c.data_asset_id
                    == data_assets_table.c.id,
                )
                .where(
                    business_case_data_attachments_table.c.business_case_id
                    == business_case_id
                )
            )
            ranked = ranked.where(
                data_assets_table.c.logical_id.in_(attached_logical_ids)
            )
        ranked_rows = ranked.subquery()
        filters = [ranked_rows.c.family_rank == 1]
        ranked_pipeline_id = (
            ranked_rows.c.metadata_pipeline_output["pipeline_id"].as_string()
        )
        ranked_origin = ranked_rows.c.metadata_origin
        if status:
            filters.append(ranked_rows.c.status == status)
        if source_type:
            filters.append(ranked_rows.c.source_type == source_type)
        if asset_kind == "view":
            filters.append(ranked_rows.c.source_type == "view")
        elif asset_kind == "dataset":
            filters.append(ranked_rows.c.source_type != "view")
        if not include_deleted:
            filters.append(ranked_rows.c.status != "deleted")
        if pipeline_id:
            filters.append(ranked_pipeline_id == pipeline_id)
        if pipeline_type:
            filters.append(
                ranked_pipeline_id.in_(
                    select(pipelines_table.c.id).where(
                        pipelines_table.c.template == pipeline_type
                    )
                )
            )
        if uploaded_only:
            filters.extend([
                ranked_rows.c.source_type != "view",
                or_(ranked_pipeline_id.is_(None), ranked_pipeline_id == ""),
                or_(
                    ranked_origin.is_(None),
                    ranked_origin != "platform_generated",
                ),
            ])
        needle = search.strip()
        if needle:
            pattern = f"%{needle}%"
            filters.append(or_(
                ranked_rows.c.name.ilike(pattern),
                ranked_rows.c.description.ilike(pattern),
                ranked_rows.c.logical_id.ilike(pattern),
                ranked_rows.c.original_filename.ilike(pattern),
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
        items: list[DataAsset] = []
        for row in rows:
            values = dict(row)
            values["metadata"] = {
                key: values.get(f"metadata_{key}")
                for key in DATASET_SUMMARY_METADATA_KEYS
                if values.get(f"metadata_{key}") is not None
            }
            items.append(self._from_record(values))
        return items, total

    def _list_summaries(
        self,
        *,
        owner_id: str | None = None,
        asset_ids: set[str] | None = None,
    ) -> list[DataAsset]:
        """Execute the bounded dataset catalog projection with SQL-side filters."""
        self._ensure_initialized()
        columns = [column for column in data_assets_table.c if column.name != "metadata"]
        statement = select(
            *columns,
            *(
                data_assets_table.c.metadata[key].label(f"metadata_{key}")
                for key in DATASET_SUMMARY_METADATA_KEYS
            ),
        )
        if owner_id is not None:
            statement = statement.where(data_assets_table.c.owner_id == owner_id)
        if asset_ids is not None:
            statement = statement.where(data_assets_table.c.id.in_(asset_ids))
        statement = statement.order_by(data_assets_table.c.created_at.desc())
        with self.engine.begin() as connection:
            rows = [row._mapping for row in connection.execute(statement)]
        summaries: list[DataAsset] = []
        for row in rows:
            values = dict(row)
            values["metadata"] = {
                key: values.get(f"metadata_{key}")
                for key in DATASET_SUMMARY_METADATA_KEYS
                if values.get(f"metadata_{key}") is not None
            }
            summaries.append(self._from_record(values))
        return summaries

    def get(self, asset_id: str) -> DataAsset | None:
        self._ensure_initialized()
        statement = select(data_assets_table).where(data_assets_table.c.id == asset_id)
        with self.engine.begin() as connection:
            row = connection.execute(statement).first()
        if not row:
            return None
        return self._from_record(row._mapping)

    def list_versions(self, owner_id: str, logical_id: str) -> list[DataAsset]:
        self._ensure_initialized()
        statement = (
            select(data_assets_table)
            .where(data_assets_table.c.owner_id == owner_id)
            .where(data_assets_table.c.logical_id == logical_id)
            .order_by(data_assets_table.c.version_number.asc())
        )
        with self.engine.begin() as connection:
            return [self._from_record(row._mapping) for row in connection.execute(statement)]

    def list_by_logical_id(self, logical_id: str) -> list[DataAsset]:
        self._ensure_initialized()
        statement = (
            select(data_assets_table)
            .where(data_assets_table.c.logical_id == logical_id)
            .order_by(data_assets_table.c.version_number.asc())
        )
        with self.engine.begin() as connection:
            return [
                self._from_record(row._mapping)
                for row in connection.execute(statement)
            ]

    def get_latest_version(self, owner_id: str, logical_id: str) -> DataAsset | None:
        self._ensure_initialized()
        statement = (
            select(data_assets_table)
            .where(data_assets_table.c.owner_id == owner_id)
            .where(data_assets_table.c.logical_id == logical_id)
            .where(data_assets_table.c.status != DataAssetStatus.DELETED.value)
            .order_by(data_assets_table.c.version_number.desc())
            .limit(1)
        )
        with self.engine.begin() as connection:
            row = connection.execute(statement).first()
        return self._from_record(row._mapping) if row else None

    def update(self, asset: DataAsset) -> DataAsset:
        self._ensure_initialized()
        asset.updated_at = datetime.now(timezone.utc)
        statement = (
            data_assets_table.update()
            .where(data_assets_table.c.id == asset.id)
            .values(**self._to_record(asset))
        )
        with self.engine.begin() as connection:
            connection.execute(statement)
        return asset

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        with self.engine.begin() as connection:
            connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {DATASET_SCHEMA}"))
            metadata.create_all(connection)
        self._initialized = True

    def _to_record(self, asset: DataAsset) -> dict[str, object]:
        return {
            "id": asset.id,
            "owner_id": asset.owner_id,
            "name": asset.name,
            "source_type": asset.source_type.value,
            "format": asset.format,
            "logical_id": asset.logical_id,
            "version_number": asset.version_number,
            "version_stage": asset.version_stage,
            "description": asset.description,
            "original_filename": asset.original_filename,
            "location_uri": asset.location_uri,
            "file_size_bytes": asset.file_size_bytes,
            "row_count": asset.row_count,
            "has_header": asset.has_header,
            "uploaded_by": asset.uploaded_by,
            "uploaded_at": asset.uploaded_at,
            "deleted_by": asset.deleted_by,
            "deleted_at": asset.deleted_at,
            "status": asset.status.value,
            "tags": asset.tags,
            "metadata": asset.metadata,
            "created_at": asset.created_at,
            "updated_at": asset.updated_at,
        }

    def _from_record(self, record: object) -> DataAsset:
        return DataAsset(
            id=record["id"],
            owner_id=record["owner_id"],
            name=record["name"],
            source_type=SourceType(record["source_type"]),
            format=record["format"],
            logical_id=record["logical_id"],
            version_number=record["version_number"],
            version_stage=record["version_stage"],
            description=record["description"],
            original_filename=record["original_filename"],
            location_uri=record["location_uri"],
            file_size_bytes=record["file_size_bytes"],
            row_count=record["row_count"],
            has_header=record["has_header"],
            uploaded_by=record["uploaded_by"],
            uploaded_at=record["uploaded_at"],
            deleted_by=record["deleted_by"],
            deleted_at=record["deleted_at"],
            status=DataAssetStatus(record["status"]),
            tags=list(record["tags"] or []),
            metadata=dict(record["metadata"] or {}),
            created_at=record["created_at"],
            updated_at=record["updated_at"],
        )
