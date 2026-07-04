from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import duckdb
from fastapi import HTTPException, status

from app.core.config import settings
from app.modules.pipelines.domain import PipelineRun, PipelineRunStatus
from app.modules.pipelines.runtime import json_safe, sql_literal


class PipelineRunOutputReader:
    def __init__(self, repository_root: Path | None = None) -> None:
        self.repository_root = (repository_root or Path("data/repository")).resolve()

    def preview(
        self,
        run: PipelineRun,
        *,
        output_id: str | None,
        pipeline_step_id: str | None = None,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        output = self._resolve_output(run, output_id, pipeline_step_id)
        path = self._resolve_output_path(output)
        row_count = int(output.get("row_count") or 0)
        connection = self._connect(path)
        try:
            cursor = connection.execute(
                "SELECT * FROM read_parquet(?) LIMIT ? OFFSET ?",
                [str(path), limit, offset],
            )
            names = [str(item[0]) for item in cursor.description or []]
            records = [
                {name: json_safe(value) for name, value in zip(names, row, strict=True)}
                for row in cursor.fetchall()
            ]
        finally:
            connection.close()
        return {
            "output_id": str(output.get("output_id") or ""),
            "pipeline_step_id": str(output.get("pipeline_step_id") or ""),
            "row_count": row_count,
            "limit": limit,
            "offset": offset,
            "returned_count": len(records),
            "records": records,
            "has_next": offset + len(records) < row_count,
            "has_previous": offset > 0,
            "columns": output.get("schema") or [],
        }

    def profile(
        self,
        run: PipelineRun,
        *,
        output_id: str | None,
        pipeline_step_id: str | None = None,
        max_columns: int,
        top_n: int,
    ) -> dict[str, Any]:
        output = self._resolve_output(run, output_id, pipeline_step_id)
        path = self._resolve_output_path(output)
        schema = output.get("schema") or []
        columns = [str(item["name"]) for item in schema if isinstance(item, dict) and item.get("name")]
        row_count = int(output.get("row_count") or 0)
        profiled_columns = columns[:max_columns]
        connection = self._connect(path)
        try:
            summaries = [
                self._column_summary(connection, path, column, row_count, top_n)
                for column in profiled_columns
            ]
        finally:
            connection.close()
        return {
            "output_id": str(output.get("output_id") or ""),
            "pipeline_step_id": str(output.get("pipeline_step_id") or ""),
            "row_count": row_count,
            "profiled_column_count": len(summaries),
            "total_column_count": len(columns),
            "columns": summaries,
        }

    def resolve_output(
        self,
        run: PipelineRun,
        output_id: str | None = None,
        pipeline_step_id: str | None = None,
    ) -> tuple[dict[str, Any], Path]:
        """Resolve an authorized run's temporary output without exposing its filesystem path."""
        output = self._resolve_output(run, output_id, pipeline_step_id)
        return output, self._resolve_output_path(output)

    def _column_summary(
        self,
        connection: duckdb.DuckDBPyConnection,
        path: Path,
        column: str,
        row_count: int,
        top_n: int,
    ) -> dict[str, Any]:
        quoted = '"' + column.replace('"', '""') + '"'
        null_count, approx_distinct = connection.execute(
            f"SELECT count(*) - count({quoted}), approx_count_distinct({quoted}) "
            "FROM read_parquet(?)",
            [str(path)],
        ).fetchone()
        top_rows = connection.execute(
            f"SELECT {quoted}, count(*) AS records "
            "FROM read_parquet(?) "
            f"GROUP BY {quoted} "
            "ORDER BY records DESC, "
            f"CAST({quoted} AS VARCHAR) ASC NULLS LAST "
            f"LIMIT {int(top_n)}",
            [str(path)],
        ).fetchall()
        return {
            "name": column,
            "null_count": int(null_count or 0),
            "non_null_count": max(row_count - int(null_count or 0), 0),
            "approx_distinct_count": int(approx_distinct or 0),
            "top_values": [
                {
                    "value": json_safe(value),
                    "count": int(count),
                    "share": (int(count) / row_count) if row_count else 0,
                }
                for value, count in top_rows
            ],
        }

    def _resolve_output(
        self,
        run: PipelineRun,
        output_id: str | None,
        pipeline_step_id: str | None = None,
    ) -> dict[str, Any]:
        if not run.is_dry_run:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only dry-run outputs can be previewed here")
        if run.status != PipelineRunStatus.SUCCEEDED:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Dry-run output is not available yet")
        outputs = [item for item in run.output_manifest if isinstance(item, dict)]
        if not outputs:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dry-run output not found")
        if output_id:
            for output in outputs:
                if (
                    output.get("output_id") == output_id
                    and (
                        not pipeline_step_id
                        or output.get("pipeline_step_id") == pipeline_step_id
                    )
                ):
                    return output
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dry-run output not found")
        return outputs[0]

    def _resolve_output_path(self, output: dict[str, Any]) -> Path:
        location_uri = str(output.get("location_uri") or "")
        parsed = urlparse(location_uri)
        if parsed.scheme != "file":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Dry-run output location is not a local file")
        path = Path(unquote(parsed.path)).resolve()
        if path.suffix.lower() != ".parquet" or not path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dry-run output file not found")
        try:
            path.relative_to(self.repository_root)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Dry-run output path is not allowed") from exc
        return path

    def _connect(self, path: Path) -> duckdb.DuckDBPyConnection:
        (path.parent / ".duckdb-tmp").mkdir(parents=True, exist_ok=True)
        connection = duckdb.connect(database=":memory:")
        connection.execute(f"SET threads = {int(settings.duckdb_threads)}")
        connection.execute(f"SET memory_limit = {sql_literal(settings.duckdb_memory_limit)}")
        connection.execute(f"SET temp_directory = {sql_literal(str(path.parent / '.duckdb-tmp'))}")
        return connection
