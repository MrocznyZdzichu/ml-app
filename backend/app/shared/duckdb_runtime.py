from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import duckdb

from app.core.config import settings


@dataclass(frozen=True)
class ParquetWriteStats:
    row_count: int
    schema_rows: list[tuple]


def configured_duckdb_connection(temp_directory: Path) -> duckdb.DuckDBPyConnection:
    temp_directory.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(database=":memory:")
    connection.execute(f"SET temp_directory = {_literal(str(temp_directory))}")
    connection.execute(f"SET threads = {settings.duckdb_threads}")
    connection.execute(f"SET memory_limit = {_literal(settings.duckdb_memory_limit)}")
    connection.execute("SET preserve_insertion_order = false")
    return connection


def write_parquet_atomic(
    connection: duckdb.DuckDBPyConnection,
    select_sql: str,
    destination: Path,
) -> ParquetWriteStats:
    """Write a full relation atomically without rescanning Parquet for metadata."""
    schema_rows = connection.execute(f"DESCRIBE {select_sql}").fetchall()
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    try:
        copied = connection.execute(
            f"COPY ({select_sql}) TO {_literal(str(temporary))} "
            "(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 122880)"
        ).fetchone()
        if copied is None:
            raise RuntimeError("DuckDB COPY did not return a row count")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return ParquetWriteStats(
        row_count=int(copied[0]),
        schema_rows=list(schema_rows),
    )


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
