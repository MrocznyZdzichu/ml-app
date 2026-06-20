import os
from pathlib import Path
from uuid import uuid4

import duckdb
from fastapi import HTTPException, status

from app.core.config import settings
from app.modules.datasets.domain import DataAsset, SourceType


class ColumnarDatasetStore:
    """Provides a reusable Parquet representation for full-dataset analytics."""

    def __init__(self, repository_root: Path | None = None) -> None:
        self.repository_root = (repository_root or Path("data/repository")).resolve()

    def relation_sql(self, asset: DataAsset) -> str:
        parquet_path = self.ensure_parquet(asset)
        return f"read_parquet({self.literal(str(parquet_path))})"

    def lightweight_csv_relation_sql(self, asset: DataAsset) -> str:
        source_path = self.source_path(asset)
        return self._csv_relation_sql(asset, source_path, sample_size=20_480)

    def connect(self, asset: DataAsset) -> duckdb.DuckDBPyConnection:
        dataset_dir = self.dataset_directory(asset)
        temporary_dir = dataset_dir / ".duckdb-tmp"
        temporary_dir.mkdir(parents=True, exist_ok=True)
        connection = duckdb.connect(database=":memory:")
        connection.execute(f"SET temp_directory = {self.literal(str(temporary_dir))}")
        connection.execute(f"SET threads = {settings.descriptive_profile_duckdb_threads}")
        connection.execute("SET preserve_insertion_order = false")
        return connection

    def ensure_parquet(self, asset: DataAsset) -> Path:
        source_path = self.source_path(asset)
        parquet_path = source_path.with_name("dataset.mlapp.parquet")
        if parquet_path.exists() and parquet_path.stat().st_mtime_ns >= source_path.stat().st_mtime_ns:
            return parquet_path

        temporary_path = parquet_path.with_name(f".{parquet_path.name}.{uuid4().hex}.tmp")
        connection = self.connect(asset)
        try:
            source = self._csv_relation_sql(asset, source_path, sample_size=-1)
            connection.execute(
                f"COPY (SELECT * FROM {source}) TO {self.literal(str(temporary_path))} "
                "(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 122880)"
            )
            os.replace(temporary_path, parquet_path)
        except duckdb.Error as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Dataset could not be prepared for analytics: {exc}",
            ) from exc
        finally:
            connection.close()
            temporary_path.unlink(missing_ok=True)
        return parquet_path

    def _csv_relation_sql(self, asset: DataAsset, source_path: Path, sample_size: int) -> str:
        header = "true" if asset.has_header is not False else "false"
        names = self._stored_column_names(asset)
        names_option = ""
        if names:
            names_option = ", names=[" + ", ".join(self.literal(name) for name in names) + "]"
        skip_rows = self._leading_blank_lines(source_path)
        skip_option = f", skip={skip_rows}" if skip_rows else ""
        return (
            "read_csv_auto("
            f"{self.literal(str(source_path))}, header={header}, sample_size={sample_size}, "
            f"null_padding=true, ignore_errors=false{skip_option}{names_option})"
        )

    def _leading_blank_lines(self, source_path: Path) -> int:
        count = 0
        with source_path.open("r", encoding="utf-8-sig", newline="") as source:
            for line in source:
                if line.strip():
                    break
                count += 1
        return count

    def _stored_column_names(self, asset: DataAsset) -> list[str]:
        schema = asset.metadata.get("source_schema") if isinstance(asset.metadata, dict) else None
        if not isinstance(schema, list):
            return []
        return [
            str(column["name"])
            for column in schema
            if isinstance(column, dict) and isinstance(column.get("name"), str)
        ]

    def source_path(self, asset: DataAsset) -> Path:
        if asset.source_type != SourceType.FILE or asset.format.lower() != "csv":
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Full-dataset profiling currently requires an uploaded CSV dataset",
            )
        if not asset.location_uri or not asset.location_uri.startswith("file://"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Dataset file location is not available",
            )
        path = Path(asset.location_uri.removeprefix("file://")).resolve()
        self._assert_in_repository(path)
        if not path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset file not found")
        return path

    def dataset_directory(self, asset: DataAsset) -> Path:
        directory = self.source_path(asset).parent.resolve()
        self._assert_in_repository(directory)
        return directory

    def _assert_in_repository(self, path: Path) -> None:
        try:
            path.relative_to(self.repository_root)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Dataset file location is outside the repository root",
            ) from exc

    @staticmethod
    def identifier(value: str) -> str:
        return f'"{value.replace(chr(34), chr(34) * 2)}"'

    @staticmethod
    def literal(value: str) -> str:
        return f"'{value.replace(chr(39), chr(39) * 2)}'"
