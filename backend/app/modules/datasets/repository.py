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
    select,
    text,
)
from sqlalchemy.engine import Engine

from app.core.database import get_engine
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

    def get(self, asset_id: str) -> DataAsset | None:
        ...

    def list_versions(self, owner_id: str, logical_id: str) -> list[DataAsset]:
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
