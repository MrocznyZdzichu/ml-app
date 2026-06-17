from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    select,
    text,
)
from sqlalchemy.engine import Engine

from app.core.database import get_engine
from app.modules.datasets.domain import DataAsset
from app.modules.datasets.domain import DataAssetStatus, SourceType


DATASET_SCHEMA = "mlapp"
metadata = MetaData(schema=DATASET_SCHEMA)

data_assets_table = Table(
    "data_assets",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("owner_id", String(64), nullable=False, index=True),
    Column("name", String(255), nullable=False),
    Column("source_type", String(32), nullable=False),
    Column("format", String(32), nullable=False),
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


class DatasetRepository(Protocol):
    def add(self, asset: DataAsset) -> DataAsset:
        ...

    def list_for_owner(self, owner_id: str) -> list[DataAsset]:
        ...

    def get(self, asset_id: str) -> DataAsset | None:
        ...

    def update(self, asset: DataAsset) -> DataAsset:
        ...


class InMemoryDatasetRepository:
    def __init__(self) -> None:
        self._items: dict[str, DataAsset] = {}

    def add(self, asset: DataAsset) -> DataAsset:
        self._items[asset.id] = asset
        return asset

    def list_for_owner(self, owner_id: str) -> list[DataAsset]:
        return [asset for asset in self._items.values() if asset.owner_id == owner_id]

    def get(self, asset_id: str) -> DataAsset | None:
        return self._items.get(asset_id)

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

    def list_for_owner(self, owner_id: str) -> list[DataAsset]:
        self._ensure_initialized()
        statement = (
            select(data_assets_table)
            .where(data_assets_table.c.owner_id == owner_id)
            .order_by(data_assets_table.c.created_at.desc())
        )
        with self.engine.begin() as connection:
            return [self._from_record(row._mapping) for row in connection.execute(statement)]

    def get(self, asset_id: str) -> DataAsset | None:
        self._ensure_initialized()
        statement = select(data_assets_table).where(data_assets_table.c.id == asset_id)
        with self.engine.begin() as connection:
            row = connection.execute(statement).first()
        if not row:
            return None
        return self._from_record(row._mapping)

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
            connection.execute(text("ALTER TABLE mlapp.data_assets ADD COLUMN IF NOT EXISTS deleted_by VARCHAR(64)"))
            connection.execute(text("ALTER TABLE mlapp.data_assets ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ"))
            connection.execute(text("ALTER TABLE mlapp.data_assets ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb"))
        self._initialized = True

    def _to_record(self, asset: DataAsset) -> dict[str, object]:
        return {
            "id": asset.id,
            "owner_id": asset.owner_id,
            "name": asset.name,
            "source_type": asset.source_type.value,
            "format": asset.format,
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
