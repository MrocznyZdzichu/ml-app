from pathlib import Path
import subprocess
import sys
from time import monotonic, sleep

import duckdb
import pytest

from app.shared.duckdb_runtime import (
    configured_duckdb_connection,
    write_parquet_atomic,
)
from app.shared.file_lock import exclusive_file_lock


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


def test_conversion_lock_serializes_processes_and_releases_after_error(tmp_path: Path) -> None:
    lock_path = tmp_path / "dataset.mlapp.lock"
    ready = tmp_path / "ready"
    acquired = tmp_path / "acquired"
    child_code = """
from pathlib import Path
import sys
from app.shared.file_lock import exclusive_file_lock

lock, ready, acquired = map(Path, sys.argv[1:])
ready.touch()
with exclusive_file_lock(lock):
    acquired.touch()
"""
    child = None
    try:
        with pytest.raises(ValueError, match="conversion failed"):
            with exclusive_file_lock(lock_path):
                child = subprocess.Popen(
                    [sys.executable, "-c", child_code, str(lock_path), str(ready), str(acquired)],
                )
                deadline = monotonic() + 5
                while not ready.exists() and monotonic() < deadline:
                    sleep(0.01)
                assert ready.exists()
                sleep(0.15)
                assert not acquired.exists()
                raise ValueError("conversion failed")
        assert child.wait(timeout=5) == 0
        assert acquired.exists()
    finally:
        if child is not None and child.poll() is None:
            child.kill()
            child.wait()
