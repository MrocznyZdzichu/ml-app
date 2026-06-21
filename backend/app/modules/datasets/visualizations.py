from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable

import duckdb
from fastapi import HTTPException, status

from app.modules.datasets.columnar import ColumnarDatasetStore
from app.modules.datasets.domain import DataAsset
from app.modules.datasets.schemas import DataAssetDrillRequest, DataAssetVisualizationRequest


class FullDatasetVisualization:
    """Executes bounded visualization queries while scanning the complete columnar dataset."""

    def __init__(self, store: ColumnarDatasetStore | None = None) -> None:
        self.store = store or ColumnarDatasetStore()

    def render(
        self,
        asset: DataAsset,
        request: DataAssetVisualizationRequest,
        load_asset: Callable[[str], DataAsset] | None = None,
    ) -> dict[str, Any]:
        connection = self.store.connect(asset)
        relation = self.store.relation_sql(asset, load_asset)
        try:
            columns = self._columns(connection, relation)
            self._validate_columns(request, columns)
            row_count = int(connection.execute(f"SELECT count(*) FROM {relation}").fetchone()[0])
            if request.kind == "kpi":
                result = self._kpi(connection, relation, request)
            elif request.kind == "histogram":
                result = self._histogram(connection, relation, request)
            elif request.kind == "scatter":
                result = self._scatter(connection, relation, request)
            else:
                result = self._grouped(connection, relation, request, columns)
            return {
                "dataset_id": asset.id,
                "row_count": row_count,
                "scanned_row_count": row_count,
                "execution_mode": "full_dataset",
                "truncated": False,
                **result,
            }
        except duckdb.Error as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Visualization query failed: {exc}") from exc
        finally:
            connection.close()

    def group_values(
        self,
        asset: DataAsset,
        column: str,
        limit: int,
        load_asset: Callable[[str], DataAsset] | None = None,
    ) -> dict[str, Any]:
        connection = self.store.connect(asset)
        relation = self.store.relation_sql(asset, load_asset)
        try:
            columns = self._columns(connection, relation)
            self._require_column(column, columns)
            quoted = self.store.identifier(column)
            rows = connection.execute(
                f"SELECT CAST({quoted} AS VARCHAR), count(*) AS frequency FROM {relation} "
                f"WHERE {quoted} IS NOT NULL GROUP BY {quoted} ORDER BY frequency DESC, 1 LIMIT ?",
                [limit + 1],
            ).fetchall()
            return {
                "dataset_id": asset.id,
                "values": [str(row[0]) for row in rows[:limit]],
                "truncated": len(rows) > limit,
            }
        finally:
            connection.close()

    def preview(
        self,
        asset: DataAsset,
        limit: int,
        load_asset: Callable[[str], DataAsset] | None = None,
    ) -> dict[str, Any]:
        connection = self.store.connect(asset)
        relation = self.store.relation_sql(asset, load_asset)
        try:
            columns = self._preview_columns(connection, relation)
            row_count = int(connection.execute(f"SELECT count(*) FROM {relation}").fetchone()[0])
            rows = connection.execute(f"SELECT * FROM {relation} LIMIT ?", [limit]).fetchall()
            records = self._serialize_records(columns, rows)
            return {
                "dataset_id": asset.id,
                "columns": columns,
                "records": records,
                "row_count": row_count,
                "returned_count": len(records),
                "limit": limit,
            }
        finally:
            connection.close()

    def drill(
        self,
        asset: DataAsset,
        request: DataAssetDrillRequest,
        load_asset: Callable[[str], DataAsset] | None = None,
    ) -> dict[str, Any]:
        connection = self.store.connect(asset)
        relation = self.store.relation_sql(asset, load_asset)
        try:
            columns = self._preview_columns(connection, relation)
            column_names = [column["name"] for column in columns]
            unknown_filters = sorted(set(request.filters) - set(column_names))
            if unknown_filters:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unknown drill filter column: {unknown_filters[0]}",
                )
            definition = {
                "filters": {
                    column: config.model_dump()
                    for column, config in request.filters.items()
                }
            }
            query, parameters = self.store.compile_browser_query(
                relation,
                column_names,
                definition,
            )
            rows = connection.execute(
                f"WITH drill_source AS ({query}) "
                f"SELECT *, count(*) OVER () AS __mlapp_total_count FROM drill_source LIMIT ?",
                [*parameters, request.limit],
            ).fetchall()
            row_count = int(rows[0][-1]) if rows else 0
            records = self._serialize_records(columns, rows)
            return {
                "dataset_id": asset.id,
                "columns": columns,
                "records": records,
                "row_count": row_count,
                "returned_count": len(records),
                "limit": request.limit,
            }
        except duckdb.Error as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Drill query failed: {exc}") from exc
        finally:
            connection.close()

    def _grouped(
        self,
        connection: duckdb.DuckDBPyConnection,
        relation: str,
        request: DataAssetVisualizationRequest,
        columns: dict[str, str],
    ) -> dict[str, Any]:
        x = self.store.identifier(request.x)
        y = self.store.identifier(request.y)
        group = self.store.identifier(request.group) if request.group else ""
        numeric_x = self._frontend_type(columns[request.x]) == "number"
        if request.x_epsilon > 0 and not numeric_x:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="X epsilon requires a numeric horizontal axis",
            )
        x_expression = x
        if request.x_epsilon > 0:
            bucket_width = request.x_epsilon * 2
            width_sql = format(bucket_width, ".17g")
            x_expression = f"round((floor(CAST({x} AS DOUBLE) / {width_sql} + 1e-12) + 0.5) * {width_sql}, 12)"
        aggregations = list(dict.fromkeys(request.aggregations or ["average"]))
        select_aggregates = ", ".join(
            f"{self._aggregate_sql(aggregation, y)} AS {self.store.identifier('metric_' + aggregation)}"
            for aggregation in aggregations
        )
        group_select = f", CAST({group} AS VARCHAR) AS group_value" if group else ", 'Values' AS group_value"
        where, parameters = self._where(request, x, y, group)
        group_by = f"{x_expression}, {group}" if group else x_expression
        output_limit = max(1, request.max_points // max(1, len(aggregations)))
        rows = self._fetch_dicts(
            connection,
            f"WITH grouped AS ("
            f"SELECT {x_expression} AS x_value{group_select}, {select_aggregates}, count({y}) AS valid_count "
            f"FROM {relation} {where} GROUP BY {group_by}"
            f") SELECT *, sum(valid_count) OVER () AS total_valid_count, count(*) OVER () AS total_group_count "
            f"FROM grouped ORDER BY x_value, group_value LIMIT ?",
            [*parameters, output_limit],
        )
        total_valid_count = int(rows[0]["total_valid_count"]) if rows else 0
        total_group_count = int(rows[0]["total_group_count"]) if rows else 0
        truncated = total_group_count > output_limit
        labels = list(dict.fromkeys(
            self._format(float(row["x_value"])) if numeric_x else self._label(row["x_value"])
            for row in rows
        ))
        label_positions = {label: index for index, label in enumerate(labels)}
        points: list[dict[str, Any]] = []
        for row in rows:
            x_value = row["x_value"]
            label = self._format(float(x_value)) if numeric_x else self._label(x_value)
            group_value = str(row["group_value"])
            for aggregation in aggregations:
                value = self._number(row[f"metric_{aggregation}"])
                if value is None:
                    continue
                series = group_value if len(aggregations) == 1 else f"{group_value} · {self._aggregation_label(aggregation)}"
                point = {
                    "x": self._number(x_value) if numeric_x else label_positions[label],
                    "y": value,
                    "xLabel": label,
                    "series": series,
                    "group": group_value,
                    "aggregation": aggregation,
                    "count": int(row["valid_count"]),
                }
                if request.x_epsilon > 0:
                    center = float(x_value)
                    point["xRange"] = [center - request.x_epsilon, center + request.x_epsilon]
                points.append(point)
        return {
            "points": points,
            "series": list(dict.fromkeys(point["series"] for point in points)),
            "kpi": None,
            "valid_count": total_valid_count,
            "truncated": truncated,
        }

    def _kpi(self, connection: duckdb.DuckDBPyConnection, relation: str, request: DataAssetVisualizationRequest) -> dict[str, Any]:
        y = self.store.identifier(request.y)
        aggregation = (request.aggregations or ["average"])[0]
        row = connection.execute(
            f"SELECT {self._aggregate_sql(aggregation, y)}, count({y}) FROM {relation} WHERE {y} IS NOT NULL"
        ).fetchone()
        return {"points": [], "series": [], "kpi": self._number(row[0]), "valid_count": int(row[1])}

    def _histogram(self, connection: duckdb.DuckDBPyConnection, relation: str, request: DataAssetVisualizationRequest) -> dict[str, Any]:
        x = self.store.identifier(request.x)
        low, high, count = connection.execute(
            f"SELECT min({x}), max({x}), count({x}) FROM {relation} WHERE {x} IS NOT NULL"
        ).fetchone()
        if not count:
            return {"points": [], "series": ["Count"], "kpi": None, "valid_count": 0}
        low_number, high_number = float(low), float(high)
        if low_number == high_number:
            points = [{"x": 0, "y": int(count), "xLabel": self._label(low), "series": "Count", "group": "Count"}]
        else:
            width = (high_number - low_number) / request.bins
            rows = connection.execute(
                f"SELECT least(?, floor(({x} - ?) / ?))::INTEGER AS bin, count(*) FROM {relation} "
                f"WHERE {x} IS NOT NULL GROUP BY bin ORDER BY bin",
                [request.bins - 1, low_number, width],
            ).fetchall()
            counts = {int(row[0]): int(row[1]) for row in rows}
            points = [
                {
                    "x": index,
                    "y": counts.get(index, 0),
                    "xLabel": f"{self._format(low_number + index * width)}–{self._format(high_number if index == request.bins - 1 else low_number + (index + 1) * width)}",
                    "xRange": [
                        low_number + index * width,
                        high_number if index == request.bins - 1 else low_number + (index + 1) * width,
                    ],
                    "xRangeInclusive": index == request.bins - 1,
                    "series": "Count",
                    "group": "Count",
                }
                for index in range(request.bins)
            ]
        return {"points": points, "series": ["Count"], "kpi": None, "valid_count": int(count)}

    def _scatter(self, connection: duckdb.DuckDBPyConnection, relation: str, request: DataAssetVisualizationRequest) -> dict[str, Any]:
        x, y = self.store.identifier(request.x), self.store.identifier(request.y)
        group = self.store.identifier(request.group) if request.group else ""
        where, parameters = self._where(request, x, y, group)
        group_count_sql = f"count(DISTINCT {group})" if group else "1"
        bounds = connection.execute(
            f"SELECT min({x}), max({x}), min({y}), max({y}), {group_count_sql} FROM {relation} {where}",
            parameters,
        ).fetchone()
        if bounds[0] is None:
            return {"points": [], "series": [], "kpi": None, "valid_count": 0}
        x_low, x_high, y_low, y_high = map(float, bounds[:4])
        group_count = max(1, int(bounds[4]))
        grid = max(5, min(50, int((request.max_points / group_count) ** 0.5)))
        x_width = (x_high - x_low) / grid or 1.0
        y_width = (y_high - y_low) / grid or 1.0
        group_select = f", CAST({group} AS VARCHAR) AS group_value" if group else ", 'Values' AS group_value"
        group_by = "x_bin, y_bin, group_value"
        rows = self._fetch_dicts(
            connection,
            f"WITH binned AS ("
            f"SELECT least(?, floor(({x} - ?) / ?))::INTEGER AS x_bin, least(?, floor(({y} - ?) / ?))::INTEGER AS y_bin{group_select}, "
            f"avg({x}) AS x_center, avg({y}) AS y_center, count(*) AS point_count "
            f"FROM {relation} {where} GROUP BY {group_by}"
            f") SELECT *, sum(point_count) OVER () AS total_valid_count, count(*) OVER () AS total_bin_count "
            f"FROM binned ORDER BY x_bin, y_bin LIMIT ?",
            [grid - 1, x_low, x_width, grid - 1, y_low, y_width, *parameters, request.max_points],
        )
        points = [
            {
                "x": float(row["x_center"]),
                "y": float(row["y_center"]),
                "xLabel": f"{request.x}: {self._format(float(row['x_center']))}",
                "series": str(row["group_value"]),
                "group": str(row["group_value"]),
                "count": int(row["point_count"]),
                "xRange": [
                    x_low + int(row["x_bin"]) * x_width,
                    x_high if int(row["x_bin"]) == grid - 1 else x_low + (int(row["x_bin"]) + 1) * x_width,
                ],
                "yRange": [
                    y_low + int(row["y_bin"]) * y_width,
                    y_high if int(row["y_bin"]) == grid - 1 else y_low + (int(row["y_bin"]) + 1) * y_width,
                ],
                "xRangeInclusive": int(row["x_bin"]) == grid - 1,
                "yRangeInclusive": int(row["y_bin"]) == grid - 1,
            }
            for row in rows
        ]
        total_valid_count = int(rows[0]["total_valid_count"]) if rows else 0
        total_bin_count = int(rows[0]["total_bin_count"]) if rows else 0
        return {
            "points": points,
            "series": list(dict.fromkeys(point["series"] for point in points)),
            "kpi": None,
            "valid_count": total_valid_count,
            "truncated": total_bin_count > request.max_points,
        }

    def _where(self, request: DataAssetVisualizationRequest, x: str, y: str, group: str) -> tuple[str, list[Any]]:
        clauses = [f"{x} IS NOT NULL", f"{y} IS NOT NULL"]
        parameters: list[Any] = []
        if group:
            clauses.append(f"{group} IS NOT NULL")
            if request.selected_groups is not None:
                if not request.selected_groups:
                    clauses.append("false")
                else:
                    placeholders = ", ".join("?" for _ in request.selected_groups)
                    clauses.append(f"CAST({group} AS VARCHAR) IN ({placeholders})")
                    parameters.extend(request.selected_groups)
        return "WHERE " + " AND ".join(clauses), parameters

    def _validate_columns(self, request: DataAssetVisualizationRequest, columns: dict[str, str]) -> None:
        required = [name for name in [request.x if request.kind != "kpi" else "", request.y if request.kind != "histogram" else "", request.group] if name]
        for name in required:
            self._require_column(name, columns)
        if request.group and request.group in {request.x, request.y}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Series column must be different from chart axes",
            )
        if request.kind == "histogram" and self._frontend_type(columns[request.x]) != "number":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Histogram measure must be numeric",
            )
        if request.kind == "scatter" and any(self._frontend_type(columns[name]) != "number" for name in [request.x, request.y]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Scatter axes must be numeric",
            )
        if request.kind in {"line", "bar", "kpi"} and self._frontend_type(columns[request.y]) != "number":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Visualization measure must be numeric",
            )

    @staticmethod
    def _require_column(name: str, columns: dict[str, str]) -> None:
        if name not in columns:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown visualization column: {name}")

    @staticmethod
    def _aggregate_sql(aggregation: str, column: str) -> str:
        return {
            "average": f"avg({column})", "median": f"median({column})", "std": f"coalesce(stddev_samp({column}), 0)",
            "sum": f"sum({column})", "count": f"count({column})", "min": f"min({column})", "max": f"max({column})",
        }[aggregation]

    @staticmethod
    def _aggregation_label(value: str) -> str:
        return {"average": "Average", "median": "Median", "std": "Std. dev.", "sum": "Sum", "count": "Count", "min": "Minimum", "max": "Maximum"}[value]

    @staticmethod
    def _columns(connection: duckdb.DuckDBPyConnection, relation: str) -> dict[str, str]:
        return {str(row[0]): str(row[1]) for row in connection.execute(f"DESCRIBE SELECT * FROM {relation}").fetchall()}

    def _preview_columns(self, connection: duckdb.DuckDBPyConnection, relation: str) -> list[dict[str, str]]:
        return [
            {"name": str(row[0]), "type": self._frontend_type(str(row[1]))}
            for row in connection.execute(f"DESCRIBE SELECT * FROM {relation}").fetchall()
        ]

    def _serialize_records(
        self,
        columns: list[dict[str, str]],
        rows: list[tuple[Any, ...]],
    ) -> list[dict[str, Any]]:
        return [
            {column["name"]: self._json_value(row[index]) for index, column in enumerate(columns)}
            for row in rows
        ]

    @staticmethod
    def _fetch_dicts(
        connection: duckdb.DuckDBPyConnection,
        sql: str,
        parameters: list[Any],
    ) -> list[dict[str, Any]]:
        cursor = connection.execute(sql, parameters)
        names = [str(column[0]) for column in cursor.description]
        return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]

    @staticmethod
    def _frontend_type(value: str) -> str:
        upper = value.upper()
        return "number" if any(token in upper for token in ["INT", "DECIMAL", "DOUBLE", "FLOAT", "REAL", "HUGEINT"]) else "date" if any(token in upper for token in ["DATE", "TIME"]) else "text"

    @staticmethod
    def _number(value: Any) -> float | None:
        return None if value is None else float(value)

    @staticmethod
    def _json_value(value: Any) -> Any:
        if isinstance(value, datetime | date):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        return value

    @staticmethod
    def _label(value: Any) -> str:
        if isinstance(value, datetime | date):
            return value.isoformat()
        if isinstance(value, Decimal):
            return format(value, "f")
        return str(value)

    @staticmethod
    def _format(value: float) -> str:
        return f"{value:.6g}"
