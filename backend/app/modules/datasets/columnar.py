import os
import hashlib
import json
import threading
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import duckdb
from fastapi import HTTPException, status

from app.core.config import settings
from app.modules.datasets.domain import DataAsset, SourceType


AssetLoader = Callable[[str], DataAsset]


class ColumnarDatasetStore:
    """Provides a reusable Parquet representation for full-dataset analytics."""

    _locks_guard = threading.Lock()
    _conversion_locks: dict[str, threading.Lock] = {}

    def __init__(self, repository_root: Path | None = None) -> None:
        self.repository_root = (repository_root or Path("data/repository")).resolve()

    def relation_sql(self, asset: DataAsset, load_asset: AssetLoader | None = None) -> str:
        parquet_path = self.ensure_parquet(asset, load_asset)
        return f"read_parquet({self.literal(str(parquet_path))})"

    def lightweight_csv_relation_sql(self, asset: DataAsset) -> str:
        source_path = self.source_path(asset)
        return self._csv_relation_sql(asset, source_path, sample_size=20_480)

    def connect(self, asset: DataAsset) -> duckdb.DuckDBPyConnection:
        dataset_dir = self.analytics_directory(asset)
        temporary_dir = dataset_dir / ".duckdb-tmp"
        temporary_dir.mkdir(parents=True, exist_ok=True)
        connection = duckdb.connect(database=":memory:")
        connection.execute(f"SET temp_directory = {self.literal(str(temporary_dir))}")
        connection.execute(f"SET threads = {settings.descriptive_profile_duckdb_threads}")
        connection.execute("SET preserve_insertion_order = false")
        return connection

    def ensure_parquet(self, asset: DataAsset, load_asset: AssetLoader | None = None, depth: int = 0) -> Path:
        if asset.source_type == SourceType.VIEW:
            if load_asset is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Data View source resolver is not available")
            return self._ensure_view_parquet(asset, load_asset, depth)
        source_path = self.source_path(asset)
        parquet_path = source_path.with_name("dataset.mlapp.parquet")
        if parquet_path.exists() and parquet_path.stat().st_mtime_ns >= source_path.stat().st_mtime_ns:
            return parquet_path

        lock_key = str(parquet_path.resolve())
        with self._locks_guard:
            conversion_lock = self._conversion_locks.setdefault(lock_key, threading.Lock())
        with conversion_lock:
            if parquet_path.exists() and parquet_path.stat().st_mtime_ns >= source_path.stat().st_mtime_ns:
                return parquet_path
            return self._build_parquet(asset, source_path, parquet_path)

    def _ensure_view_parquet(self, asset: DataAsset, load_asset: AssetLoader, depth: int) -> Path:
        if depth > 5:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Data View nesting is too deep")
        metadata = self._record(asset.metadata.get("data_view"))
        source_id = str(metadata.get("source_dataset_id") or "")
        definition = self._record(metadata.get("definition"))
        if not source_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Data View source is missing")
        source = load_asset(source_id)
        source_parquet = self.ensure_parquet(source, load_asset, depth + 1)
        definition_hash = hashlib.sha256(json.dumps(definition, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:16]
        view_directory = self.analytics_directory(asset)
        parquet_path = view_directory / f"dataset.mlapp.view.{definition_hash}.parquet"
        if parquet_path.exists() and parquet_path.stat().st_mtime_ns >= source_parquet.stat().st_mtime_ns:
            return parquet_path

        lock_key = str(parquet_path.resolve())
        with self._locks_guard:
            conversion_lock = self._conversion_locks.setdefault(lock_key, threading.Lock())
        with conversion_lock:
            if parquet_path.exists() and parquet_path.stat().st_mtime_ns >= source_parquet.stat().st_mtime_ns:
                return parquet_path
            temporary_path = parquet_path.with_name(f".{parquet_path.name}.{uuid4().hex}.tmp")
            connection = self.connect(asset)
            try:
                source_relation = f"read_parquet({self.literal(str(source_parquet))})"
                source_name = source.name.strip() or "dataset"
                connection.execute(f"CREATE TEMP VIEW {self.identifier(source_name)} AS SELECT * FROM {source_relation}")
                query, parameters = self._view_query(connection, source_relation, source_name, definition)
                connection.execute(
                    f"COPY ({query}) TO {self.literal(str(temporary_path))} "
                    "(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 122880)",
                    parameters,
                )
                os.replace(temporary_path, parquet_path)
                for old_path in view_directory.glob("dataset.mlapp.view.*.parquet"):
                    if old_path != parquet_path:
                        old_path.unlink(missing_ok=True)
            except duckdb.Error as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Data View query failed: {exc}") from exc
            finally:
                connection.close()
                temporary_path.unlink(missing_ok=True)
            return parquet_path

    def _view_query(
        self,
        connection: duckdb.DuckDBPyConnection,
        source_relation: str,
        source_name: str,
        definition: dict[str, Any],
    ) -> tuple[str, list[Any]]:
        kind = str(definition.get("kind") or "browser")
        if kind == "sql":
            sql = str(definition.get("sql") or "").strip().removesuffix(";").strip()
            if not sql.lower().startswith(("select", "with")) or ";" in sql:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Data View SQL must be one read-only SELECT query")
            return sql, []
        columns = [str(row[0]) for row in connection.execute(f"DESCRIBE SELECT * FROM {source_relation}").fetchall()]
        return self.compile_browser_query(source_relation, columns, definition)

    def compile_browser_query(self, relation: str, columns: list[str], definition: dict[str, Any]) -> tuple[str, list[Any]]:
        filters = self._record(definition.get("filters"))
        aggregation_filters = self._record(definition.get("aggregation_filters"))
        grouping = self._record(definition.get("grouping"))
        sort_rules = self._list(definition.get("sort_rules"))
        visible_columns = [str(value) for value in self._list(definition.get("visible_columns")) if str(value) in columns]
        clauses: list[str] = []
        parameters: list[Any] = []
        search = str(definition.get("search") or "").strip()
        if search:
            clauses.append("(" + " OR ".join(f"lower(CAST({self.identifier(column)} AS VARCHAR)) LIKE '%' || lower(?) || '%'" for column in columns) + ")")
            parameters.extend([search] * len(columns))
        for column, raw_config in filters.items():
            if column not in columns:
                continue
            clause, values = self._filter_sql(self.identifier(column), self._record(raw_config))
            if clause:
                clauses.append(clause)
                parameters.extend(values)
        where_sql = " WHERE " + " AND ".join(clauses) if clauses else ""
        group_columns = [column for column in columns if self._record(grouping.get(column)).get("role") == "group"]
        aggregate_columns = [column for column in columns if self._record(grouping.get(column)).get("role") == "aggregate"]

        if group_columns or aggregate_columns:
            selections = [self.identifier(column) for column in group_columns]
            selections.append('count(*) AS "records"')
            output_columns = [*group_columns, "records"]
            for column in aggregate_columns:
                aggregate = str(self._record(grouping.get(column)).get("aggregate") or "count_non_empty")
                label = f"{self._aggregation_label(aggregate)} {column}"
                selections.append(f"{self._browser_aggregate_sql(aggregate, self.identifier(column))} AS {self.identifier(label)}")
                output_columns.append(label)
            query = f"SELECT {', '.join(selections)} FROM {relation}{where_sql}"
            if group_columns:
                query += " GROUP BY " + ", ".join(self.identifier(column) for column in group_columns)
            having: list[str] = []
            for column, raw_config in aggregation_filters.items():
                if column not in output_columns:
                    continue
                clause, values = self._filter_sql(self.identifier(column), self._record(raw_config))
                if clause:
                    having.append(clause)
                    parameters.extend(values)
            if having:
                query += " HAVING " + " AND ".join(having)
        else:
            output_columns = visible_columns or columns
            query = f"SELECT {', '.join(self.identifier(column) for column in output_columns)} FROM {relation}{where_sql}"

        order_parts = []
        for raw_rule in sort_rules:
            rule = self._record(raw_rule)
            column = str(rule.get("column") or "")
            if column in output_columns:
                direction = "DESC" if str(rule.get("direction") or "asc").lower() == "desc" else "ASC"
                order_parts.append(f"{self.identifier(column)} {direction}")
        if order_parts:
            query += " ORDER BY " + ", ".join(order_parts)
        return query, parameters

    def _filter_sql(self, column: str, config: dict[str, Any]) -> tuple[str, list[Any]]:
        operator = str(config.get("operator") or "contains")
        value = str(config.get("value") or "")
        values = [str(item) for item in self._list(config.get("values"))]
        text = f"CAST({column} AS VARCHAR)"
        if operator == "empty":
            return f"({column} IS NULL OR {text} = '')", []
        if operator == "not_empty":
            return f"({column} IS NOT NULL AND {text} <> '')", []
        if operator == "in":
            return (f"{text} IN ({', '.join('?' for _ in values)})", values) if values else ("", [])
        if operator == "between" and len(values) >= 2:
            upper_symbol = "<=" if bool(config.get("upper_inclusive")) else "<"
            return (
                f"try_cast({column} AS DOUBLE) >= try_cast(? AS DOUBLE) "
                f"AND try_cast({column} AS DOUBLE) {upper_symbol} try_cast(? AS DOUBLE)",
                values[:2],
            )
        if operator in {"gt", "gte", "lt", "lte"}:
            symbol = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[operator]
            return f"try_cast({column} AS DOUBLE) {symbol} try_cast(? AS DOUBLE)", [value]
        if operator == "regex":
            return f"regexp_matches({text}, ?)", [value]
        if operator == "equals":
            return f"lower({text}) = lower(?)", [value]
        if operator == "not_equals":
            return f"lower({text}) <> lower(?)", [value]
        if operator == "starts_with":
            return f"lower({text}) LIKE lower(?) || '%'", [value]
        if operator == "ends_with":
            return f"lower({text}) LIKE '%' || lower(?)", [value]
        return f"lower({text}) LIKE '%' || lower(?) || '%'", [value]

    @staticmethod
    def _browser_aggregate_sql(aggregate: str, column: str) -> str:
        return {
            "count": "count(*)", "count_non_empty": f"count({column})", "unique_count": f"count(DISTINCT {column})",
            "sum": f"sum({column})", "average": f"avg({column})", "min": f"min({column})", "max": f"max({column})",
            "median": f"median({column})", "mode": f"mode({column})", "first": f"first({column})", "last": f"last({column})",
        }.get(aggregate, f"count({column})")

    @staticmethod
    def _aggregation_label(aggregate: str) -> str:
        return {
            "count": "Count rows", "count_non_empty": "Count values", "unique_count": "Unique count", "sum": "Sum",
            "average": "Average", "min": "Minimum", "max": "Maximum", "median": "Median", "mode": "Most frequent",
            "first": "First value", "last": "Last value",
        }.get(aggregate, "Count values")

    @staticmethod
    def _record(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _list(value: Any) -> list[Any]:
        return value if isinstance(value, list) else []

    def _build_parquet(self, asset: DataAsset, source_path: Path, parquet_path: Path) -> Path:

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

    def analytics_directory(self, asset: DataAsset) -> Path:
        if asset.source_type == SourceType.FILE:
            return self.dataset_directory(asset)
        if asset.source_type == SourceType.VIEW:
            directory = (self.repository_root / "users" / asset.owner_id / asset.id).resolve()
            self._assert_in_repository(directory)
            directory.mkdir(parents=True, exist_ok=True)
            return directory
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Columnar analytics requires an uploaded dataset or Data View")

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
