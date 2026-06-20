from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable

import duckdb
from fastapi import HTTPException, status

from app.modules.datasets.columnar import ColumnarDatasetStore
from app.modules.datasets.domain import DataAsset
from app.modules.datasets.schemas import DataAssetVisualizationRequest


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
            described = connection.execute(f"DESCRIBE SELECT * FROM {relation}").fetchall()
            columns = [{"name": str(row[0]), "type": self._frontend_type(str(row[1]))} for row in described]
            row_count = int(connection.execute(f"SELECT count(*) FROM {relation}").fetchone()[0])
            rows = connection.execute(f"SELECT * FROM {relation} LIMIT ?", [limit]).fetchall()
            records = [
                {columns[index]["name"]: self._json_value(value) for index, value in enumerate(row)}
                for row in rows
            ]
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
        aggregations = list(dict.fromkeys(request.aggregations or ["average"]))
        select_aggregates = ", ".join(
            f"{self._aggregate_sql(aggregation, y)} AS {self.store.identifier('metric_' + aggregation)}"
            for aggregation in aggregations
        )
        group_select = f", CAST({group} AS VARCHAR) AS group_value" if group else ", 'Values' AS group_value"
        where, parameters = self._where(request, x, y, group)
        group_by = f"{x}, {group}" if group else x
        output_limit = max(1, request.max_points // max(1, len(aggregations)))
        rows = connection.execute(
            f"SELECT {x} AS x_value{group_select}, {select_aggregates}, count({y}) AS valid_count "
            f"FROM {relation} {where} GROUP BY {group_by} ORDER BY {x}, group_value LIMIT ?",
            [*parameters, output_limit + 1],
        ).fetchall()
        truncated = len(rows) > output_limit
        rows = rows[:output_limit]
        numeric_x = self._frontend_type(columns[request.x]) == "number"
        labels = list(dict.fromkeys(self._label(row[0]) for row in rows))
        label_positions = {label: index for index, label in enumerate(labels)}
        points: list[dict[str, Any]] = []
        for row in rows:
            label = self._label(row[0])
            group_value = str(row[1])
            for index, aggregation in enumerate(aggregations):
                value = self._number(row[2 + index])
                if value is None:
                    continue
                series = group_value if len(aggregations) == 1 else f"{group_value} · {self._aggregation_label(aggregation)}"
                points.append({
                    "x": self._number(row[0]) if numeric_x else label_positions[label],
                    "y": value,
                    "xLabel": label,
                    "series": series,
                    "group": group_value,
                    "aggregation": aggregation,
                    "count": int(row[-1]),
                })
        return {
            "points": points,
            "series": list(dict.fromkeys(point["series"] for point in points)),
            "kpi": None,
            "valid_count": sum(int(row[-1]) for row in rows),
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
        bounds = connection.execute(f"SELECT min({x}), max({x}), min({y}), max({y}) FROM {relation} {where}", parameters).fetchone()
        if bounds[0] is None:
            return {"points": [], "series": [], "kpi": None, "valid_count": 0}
        x_low, x_high, y_low, y_high = map(float, bounds)
        group_count = 1
        if group:
            group_count = max(1, int(connection.execute(
                f"SELECT count(DISTINCT {group}) FROM {relation} {where}", parameters
            ).fetchone()[0]))
        grid = max(5, min(50, int((request.max_points / group_count) ** 0.5)))
        x_width = (x_high - x_low) / grid or 1.0
        y_width = (y_high - y_low) / grid or 1.0
        group_select = f", CAST({group} AS VARCHAR) AS group_value" if group else ", 'Values' AS group_value"
        group_by = "x_bin, y_bin, group_value"
        rows = connection.execute(
            f"SELECT least(?, floor(({x} - ?) / ?))::INTEGER AS x_bin, least(?, floor(({y} - ?) / ?))::INTEGER AS y_bin{group_select}, "
            f"avg({x}), avg({y}), count(*) FROM {relation} {where} GROUP BY {group_by} ORDER BY x_bin, y_bin",
            [grid - 1, x_low, x_width, grid - 1, y_low, y_width, *parameters],
        ).fetchall()
        points = [
            {"x": float(row[3]), "y": float(row[4]), "xLabel": f"{request.x}: {self._format(float(row[3]))}", "series": str(row[2]), "group": str(row[2]), "count": int(row[5])}
            for row in rows[: request.max_points]
        ]
        return {"points": points, "series": list(dict.fromkeys(point["series"] for point in points)), "kpi": None, "valid_count": sum(int(row[5]) for row in rows)}

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
