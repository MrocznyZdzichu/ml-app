from pathlib import Path

import duckdb
import pytest

from app.shared.duckdb_runtime import (
    configured_duckdb_connection,
    write_parquet_atomic,
)
from app.modules.datasets.columnar import ColumnarDatasetStore


def test_atomic_parquet_write_returns_copy_metadata_without_output_rescan(
    tmp_path: Path,
) -> None:
    connection = configured_duckdb_connection(tmp_path / "duckdb-tmp")
    destination = tmp_path / "result.parquet"
    try:
        stats = write_parquet_atomic(
            connection,
            "SELECT range AS row_id, range * 2 AS value FROM range(1000)",
            destination,
        )

        assert stats.row_count == 1000
        assert [(str(row[0]), str(row[1])) for row in stats.schema_rows] == [
            ("row_id", "BIGINT"),
            ("value", "BIGINT"),
        ]
        assert connection.execute(
            "SELECT count(*), max(value) FROM read_parquet(?)",
            [str(destination)],
        ).fetchone() == (1000, 1998)
    finally:
        connection.close()


def test_failed_atomic_parquet_write_preserves_previous_output(tmp_path: Path) -> None:
    connection = configured_duckdb_connection(tmp_path / "duckdb-tmp")
    destination = tmp_path / "result.parquet"
    try:
        write_parquet_atomic(connection, "SELECT 7 AS value", destination)

        with pytest.raises(duckdb.Error):
            write_parquet_atomic(
                connection,
                "SELECT missing_column FROM range(5)",
                destination,
            )

        assert connection.execute(
            "SELECT value FROM read_parquet(?)",
            [str(destination)],
        ).fetchone() == (7,)
        assert not list(tmp_path.glob(".result.parquet.*.tmp"))
    finally:
        connection.close()


def test_columnar_conversion_lock_is_released_after_last_user() -> None:
    lock_key = "test-lock-key"

    with ColumnarDatasetStore._conversion_lock(lock_key):
        assert ColumnarDatasetStore._conversion_locks[lock_key].users == 1

    assert lock_key not in ColumnarDatasetStore._conversion_locks
