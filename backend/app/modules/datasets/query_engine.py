import re
import sqlite3
from datetime import datetime
from typing import Any, Callable

from fastapi import HTTPException, status

from app.modules.datasets.domain import DataAsset, SourceType
from app.modules.datasets.schemas import DataAssetPreviewRead
from app.modules.datasets.sources import DatasetSourceRegistry


AssetLoader = Callable[[str], DataAsset]


class DatasetQueryEngine:
    """Executes tabular previews, SQL queries, and saved Data View definitions."""

    def __init__(self, sources: DatasetSourceRegistry) -> None:
        self.sources = sources

    def preview(
        self,
        asset: DataAsset,
        load_asset: AssetLoader,
        limit: int,
        dataset_id: str | None = None,
    ) -> DataAssetPreviewRead:
        if asset.source_type == SourceType.VIEW:
            view_metadata = self._data_view_metadata(asset)
            return self.preview_definition(
                load_asset(str(view_metadata["source_dataset_id"])),
                self._as_record(view_metadata.get("definition")),
                load_asset,
                limit,
                dataset_id=dataset_id or asset.id,
            )

        columns, records = self.records_for_asset(asset, load_asset)
        return self._preview_from_records(dataset_id or asset.id, columns, records, limit)

    def query(
        self,
        asset: DataAsset,
        load_asset: AssetLoader,
        sql: str,
        limit: int,
        dataset_id: str | None = None,
    ) -> DataAssetPreviewRead:
        columns, records = self.records_for_asset(asset, load_asset)
        result_columns, result_rows = self._execute_sql(asset.name.strip() or "dataset", columns, records, sql)
        return self._preview_from_records(dataset_id or asset.id, result_columns, result_rows, limit)

    def preview_definition(
        self,
        source: DataAsset,
        definition: dict[str, Any],
        load_asset: AssetLoader,
        limit: int,
        dataset_id: str | None = None,
    ) -> DataAssetPreviewRead:
        columns, records = self.records_for_asset(source, load_asset)
        kind = str(definition.get("kind") or "browser")
        if kind == "sql":
            sql = str(definition.get("sql") or "").strip()
            if not sql:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Data View SQL is empty")
            columns, records = self._execute_sql(source.name.strip() or "dataset", columns, records, sql)
        else:
            columns, records = self._apply_browser_view_definition(columns, records, definition)
        return self._preview_from_records(dataset_id or source.id, columns, records, limit)

    def records_for_asset(
        self,
        asset: DataAsset,
        load_asset: AssetLoader,
        depth: int = 0,
    ) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
        if depth > 5:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Data View nesting is too deep")
        if asset.source_type == SourceType.VIEW:
            view_metadata = self._data_view_metadata(asset)
            source = load_asset(str(view_metadata["source_dataset_id"]))
            columns, records = self.records_for_asset(source, load_asset, depth + 1)
            definition = self._as_record(view_metadata.get("definition"))
            if str(definition.get("kind") or "browser") == "sql":
                return self._execute_sql(source.name.strip() or "dataset", columns, records, str(definition.get("sql") or ""))
            return self._apply_browser_view_definition(columns, records, definition)

        tabular = self.sources.read(asset, action="browsed")
        columns = [{"name": column, "type": "empty"} for column in tabular.columns]
        records: list[dict[str, Any]] = []
        column_types: dict[str, set[str]] = {column["name"]: set() for column in columns}
        for row in tabular.rows:
            record: dict[str, Any] = {}
            for index, column in enumerate(tabular.columns):
                raw_value = row[index] if index < len(row) else ""
                parsed, value_type = self._parse_cell(raw_value)
                record[column] = parsed
                column_types[column].add(value_type)
            records.append(record)

        return [
            {"name": column["name"], "type": self._resolve_column_type(column_types[column["name"]])}
            for column in columns
        ], records

    def _preview_from_records(
        self,
        dataset_id: str,
        columns: list[dict[str, str]],
        records: list[dict[str, Any]],
        limit: int,
    ) -> DataAssetPreviewRead:
        normalized_columns = self._columns_with_inferred_types(columns, records)
        limited_rows = records[:limit]
        return DataAssetPreviewRead(
            dataset_id=dataset_id,
            columns=normalized_columns,
            records=limited_rows,
            row_count=len(records),
            returned_count=len(limited_rows),
            limit=limit,
        )

    def _columns_with_inferred_types(
        self,
        columns: list[dict[str, str]],
        records: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        names = [column["name"] for column in columns]
        column_types: dict[str, set[str]] = {name: set() for name in names}
        for record in records:
            for name in names:
                column_types[name].add(self._value_type(record.get(name)))
        return [{"name": name, "type": self._resolve_column_type(column_types[name])} for name in names]

    def _execute_sql(
        self,
        table_name: str,
        columns: list[dict[str, str]],
        records: list[dict[str, Any]],
        sql: str,
    ) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
        sql = sql.strip()
        if not sql.lower().startswith(("select", "with")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only read-only SELECT queries are supported",
            )

        column_names = [column["name"] for column in columns]
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        try:
            quoted_columns = ", ".join(f"{self._quote_identifier(column)}" for column in column_names)
            connection.execute(f"CREATE TABLE {self._quote_identifier(table_name)} ({quoted_columns})")
            placeholders = ", ".join("?" for _ in column_names)
            insert_sql = f"INSERT INTO {self._quote_identifier(table_name)} ({quoted_columns}) VALUES ({placeholders})"
            for record in records:
                connection.execute(insert_sql, [record.get(column) for column in column_names])
            connection.commit()
            connection.set_authorizer(self._sqlite_readonly_authorizer)
            cursor = connection.execute(sql)
            result_names = [description[0] for description in cursor.description or []]
            result_rows = [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"SQL query failed: {exc}",
            ) from exc
        finally:
            connection.close()
        return [{"name": name, "type": "empty"} for name in result_names], result_rows

    def _apply_browser_view_definition(
        self,
        columns: list[dict[str, str]],
        records: list[dict[str, Any]],
        definition: dict[str, Any],
    ) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
        search = str(definition.get("search") or "").strip().lower()
        filters = self._as_record(definition.get("filters"))
        sort_rules = self._as_list(definition.get("sort_rules"))
        grouping = self._as_record(definition.get("grouping"))
        aggregation_filters = self._as_record(definition.get("aggregation_filters"))
        visible_columns = [str(item) for item in self._as_list(definition.get("visible_columns")) if isinstance(item, str)]

        filtered_records = [
            record for record in records
            if self._matches_search(record, search) and self._matches_filters(record, filters)
        ]

        group_columns = [
            column for column in columns
            if self._as_record(grouping.get(column["name"])).get("role") == "group"
        ]
        aggregate_columns = [
            column for column in columns
            if self._as_record(grouping.get(column["name"])).get("role") == "aggregate"
        ]

        if group_columns or aggregate_columns:
            columns, filtered_records = self._aggregate_records(filtered_records, group_columns, aggregate_columns, grouping)
            filtered_records = [
                record for record in filtered_records
                if self._matches_filters(record, aggregation_filters)
            ]
        elif visible_columns:
            visible_set = set(visible_columns)
            columns = [column for column in columns if column["name"] in visible_set]
            filtered_records = [
                {column["name"]: record.get(column["name"]) for column in columns}
                for record in filtered_records
            ]

        sorted_records = self._sort_records(filtered_records, sort_rules)
        return self._columns_with_inferred_types(columns, sorted_records), sorted_records

    def _matches_search(self, record: dict[str, Any], search: str) -> bool:
        if not search:
            return True
        return any(search in self._display_value(value).lower() for value in record.values())

    def _matches_filters(self, record: dict[str, Any], filters: dict[str, Any]) -> bool:
        for column, config_value in filters.items():
            config = self._as_record(config_value)
            if not self._matches_filter(record.get(column), config):
                return False
        return True

    def _matches_filter(self, value: Any, config: dict[str, Any]) -> bool:
        operator = str(config.get("operator") or "contains")
        filter_value = str(config.get("value") or "")
        values = [str(item) for item in self._as_list(config.get("values"))]
        display = self._display_value(value)
        lowered = display.lower()
        expected = filter_value.lower()

        if operator == "empty":
            return display == ""
        if operator == "not_empty":
            return display != ""
        if operator == "equals":
            return lowered == expected
        if operator == "not_equals":
            return lowered != expected
        if operator == "in":
            return display in values
        if operator == "starts_with":
            return lowered.startswith(expected)
        if operator == "ends_with":
            return lowered.endswith(expected)
        if operator == "regex":
            try:
                return re.search(filter_value, display) is not None
            except re.error:
                return True
        if operator in {"gt", "gte", "lt", "lte"}:
            left = self._comparable_number(value)
            right = self._comparable_number(filter_value)
            if left is None or right is None:
                return True
            if operator == "gt":
                return left > right
            if operator == "gte":
                return left >= right
            if operator == "lt":
                return left < right
            return left <= right
        return expected in lowered

    def _aggregate_records(
        self,
        records: list[dict[str, Any]],
        group_columns: list[dict[str, str]],
        aggregate_columns: list[dict[str, str]],
        grouping: dict[str, Any],
    ) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
        result_columns = [
            *group_columns,
            {"name": "records", "type": "number"},
            *[
                {
                    "name": f"{self._aggregation_label(str(self._as_record(grouping.get(column['name'])).get('aggregate') or 'count_non_empty'))} {column['name']}",
                    "type": "empty",
                }
                for column in aggregate_columns
            ],
        ]
        groups: dict[str, list[dict[str, Any]]] = {}
        for record in records:
            key = "\u001f".join(self._display_value(record.get(column["name"])) for column in group_columns) or "__all__"
            groups.setdefault(key, []).append(record)

        result_records: list[dict[str, Any]] = []
        for group_rows in groups.values():
            output: dict[str, Any] = {}
            for column in group_columns:
                output[column["name"]] = group_rows[0].get(column["name"])
            output["records"] = len(group_rows)
            for column in aggregate_columns:
                aggregate = str(self._as_record(grouping.get(column["name"])).get("aggregate") or "count_non_empty")
                output[f"{self._aggregation_label(aggregate)} {column['name']}"] = self._aggregate_values(
                    [row.get(column["name"]) for row in group_rows],
                    aggregate,
                )
            result_records.append(output)
        return result_columns, result_records

    def _aggregate_values(self, values: list[Any], aggregate: str) -> Any:
        concrete = [value for value in values if value not in (None, "")]
        numeric = sorted(value for value in concrete if isinstance(value, int | float))
        if aggregate == "count":
            return len(values)
        if aggregate == "count_non_empty":
            return len(concrete)
        if aggregate == "unique_count":
            return len({self._display_value(value) for value in concrete})
        if aggregate == "sum":
            return sum(numeric)
        if aggregate == "average":
            return None if not numeric else round(sum(numeric) / len(numeric), 6)
        if aggregate == "min":
            return min(concrete, key=self._sort_key, default=None)
        if aggregate == "max":
            return max(concrete, key=self._sort_key, default=None)
        if aggregate == "median":
            if not numeric:
                return None
            middle = len(numeric) // 2
            return round((numeric[middle - 1] + numeric[middle]) / 2, 6) if len(numeric) % 2 == 0 else numeric[middle]
        if aggregate == "mode":
            counts: dict[str, tuple[Any, int]] = {}
            for value in concrete:
                key = self._display_value(value)
                counts[key] = (value, counts.get(key, (value, 0))[1] + 1)
            return max(counts.values(), key=lambda item: item[1])[0] if counts else None
        if aggregate == "first":
            return concrete[0] if concrete else None
        return concrete[-1] if concrete else None

    def _sort_records(self, records: list[dict[str, Any]], sort_rules: list[Any]) -> list[dict[str, Any]]:
        normalized_rules = [self._as_record(rule) for rule in sort_rules]
        for rule in reversed(normalized_rules):
            column = str(rule.get("column") or "")
            direction = str(rule.get("direction") or "asc")
            if column:
                records = sorted(records, key=lambda record: self._sort_key(record.get(column)), reverse=direction == "desc")
        return records

    def _sort_key(self, value: Any) -> tuple[int, Any]:
        if value is None or value == "":
            return (1, "")
        comparable = self._comparable_number(value)
        if comparable is not None:
            return (0, comparable)
        return (0, self._display_value(value).lower())

    def _parse_cell(self, value: str) -> tuple[Any, str]:
        stripped = value.strip()
        if stripped == "":
            return None, "empty"
        lowered = stripped.lower()
        if lowered in {"true", "false"}:
            return lowered == "true", "boolean"
        try:
            number = float(stripped)
        except ValueError:
            pass
        else:
            if number.is_integer() and "." not in stripped and "e" not in lowered:
                return int(number), "number"
            return number, "number"
        try:
            datetime.fromisoformat(stripped.replace("Z", "+00:00"))
        except ValueError:
            return stripped, "text"
        return stripped, "date"

    def _value_type(self, value: Any) -> str:
        if value is None or value == "":
            return "empty"
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int | float):
            return "number"
        if isinstance(value, str):
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return "text"
            return "date"
        return "unsupported"

    def _resolve_column_type(self, value_types: set[str]) -> str:
        concrete_types = value_types - {"empty"}
        if not concrete_types:
            return "empty"
        if len(concrete_types) == 1:
            return next(iter(concrete_types))
        return "mixed"

    def _comparable_number(self, value: Any) -> float | None:
        if isinstance(value, int | float):
            return float(value)
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
            except ValueError:
                pass
            try:
                return float(value)
            except ValueError:
                return None
        return None

    def _display_value(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    def _aggregation_label(self, aggregate: str) -> str:
        return {
            "count": "Count rows",
            "count_non_empty": "Count values",
            "unique_count": "Unique count",
            "sum": "Sum",
            "average": "Average",
            "min": "Minimum",
            "max": "Maximum",
            "median": "Median",
            "mode": "Most frequent",
            "first": "First value",
            "last": "Last value",
        }.get(aggregate, aggregate)

    def _data_view_metadata(self, asset: DataAsset) -> dict[str, Any]:
        metadata = self._as_record(asset.metadata.get("data_view"))
        if not metadata.get("source_dataset_id"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Data View definition is missing source dataset")
        return metadata

    def _quote_identifier(self, identifier: str) -> str:
        return f'"{identifier.replace("\"", "\"\"")}"'

    def _sqlite_readonly_authorizer(
        self,
        action_code: int,
        _arg1: str | None,
        _arg2: str | None,
        _database_name: str | None,
        _trigger_or_view: str | None,
    ) -> int:
        allowed_actions = {
            sqlite3.SQLITE_SELECT,
            sqlite3.SQLITE_READ,
            sqlite3.SQLITE_FUNCTION,
        }
        return sqlite3.SQLITE_OK if action_code in allowed_actions else sqlite3.SQLITE_DENY

    def _as_record(self, value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _as_list(self, value: Any) -> list[Any]:
        return value if isinstance(value, list) else []
