import math
import threading
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable

import duckdb
from fastapi import HTTPException, status

from app.core.config import settings
from app.modules.datasets.columnar import ColumnarDatasetStore
from app.modules.datasets.domain import DataAsset
from app.modules.datasets.schemas import DataAssetDrillRequest, DataAssetVisualizationRequest
from app.modules.datasets.visualization_trends import (
    MAX_TREND_GROUP_COUNT,
    ScatterTrendFitter,
    finite_number,
)
from app.modules.datasets.dimensionality import FullDatasetPcaProjection
from app.modules.datasets.time_series import FullDatasetTimeSeriesAnalyzer


SCATTER_MIN_GRID_SIZE = 5
SCATTER_MAX_GRID_SIZE = 50
MAX_SAFE_SCATTER_BIN_INDEX = 9e18
MAX_COMPARISON_GROUP_COUNT = 20
MIN_DENSITY_SOURCE_BINS = 128
MAX_DENSITY_SOURCE_BINS = 512


class FullDatasetVisualization:
    """Executes bounded visualization queries while scanning the complete columnar dataset."""

    def __init__(self, store: ColumnarDatasetStore | None = None) -> None:
        self.store = store or ColumnarDatasetStore()
        self.trend_fitter = ScatterTrendFitter(self._fetch_dicts)
        self.pca_projection = FullDatasetPcaProjection(self.store)
        self.time_series = FullDatasetTimeSeriesAnalyzer(self.store)
        self._execution_slots = threading.BoundedSemaphore(settings.visualization_max_concurrency)

    def render(
        self,
        asset: DataAsset,
        request: DataAssetVisualizationRequest,
        load_asset: Callable[[str], DataAsset] | None = None,
    ) -> dict[str, Any]:
        with self._execution_slots:
            return self._render_in_execution_slot(asset, request, load_asset)

    def _render_in_execution_slot(
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
            row_count = (
                int(asset.row_count)
                if asset.row_count is not None
                else int(connection.execute(f"SELECT count(*) FROM {relation}").fetchone()[0])
            )
            if request.kind in {"time_series", "autocorrelation", "lag_relationship"}:
                result = self.time_series.visualization(connection, relation, request, columns)
            elif request.kind == "projection":
                result = self.pca_projection.render(connection, relation, request, columns)
            elif request.kind == "kpi":
                result = self._render_kpi(connection, relation, request)
            elif request.kind == "histogram":
                result = self._render_distribution(connection, relation, request)
            elif request.kind == "boxplot":
                result = self._render_boxplot(connection, relation, request)
            elif request.kind == "scatter":
                result = self._render_scatter(connection, relation, request)
            else:
                result = self._render_grouped_aggregate(connection, relation, request, columns)
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

    def _render_grouped_aggregate(
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
        finite_columns = [y, x] if numeric_x else [y]
        where, parameters = self._filtered_where(request, [x, y], group, finite_columns)
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

    def _render_kpi(self, connection: duckdb.DuckDBPyConnection, relation: str, request: DataAssetVisualizationRequest) -> dict[str, Any]:
        y = self.store.identifier(request.y)
        group = self.store.identifier(request.group) if request.group else ""
        aggregation = (request.aggregations or ["average"])[0]
        where, parameters = self._filtered_where(request, [y], group, [y])
        row = connection.execute(
            f"SELECT {self._aggregate_sql(aggregation, y)}, count({y}) FROM {relation} "
            f"{where}",
            parameters,
        ).fetchone()
        return {"points": [], "series": [], "kpi": self._number(row[0]), "valid_count": int(row[1])}

    def _render_boxplot(self, connection: duckdb.DuckDBPyConnection, relation: str, request: DataAssetVisualizationRequest) -> dict[str, Any]:
        x = self.store.identifier(request.x)
        group = self.store.identifier(request.group) if request.group else ""
        group_expression = f"CAST({group} AS VARCHAR)" if group else "'All rows'"
        where, parameters = self._filtered_where(request, [x], group, [x])
        self._enforce_group_limit(
            connection, relation, request, group, where, parameters,
            MAX_COMPARISON_GROUP_COUNT, "Box plots",
        )
        rows = self._fetch_dicts(
            connection,
            "WITH base AS ("
            f"SELECT CAST({x} AS DOUBLE) AS value, {group_expression} AS group_value FROM {relation} {where}"
            "), quartiles AS ("
            "SELECT group_value, count(*) AS valid_count, min(value) AS minimum, max(value) AS maximum, "
            "quantile_cont(value, 0.25) AS q1, quantile_cont(value, 0.5) AS median, quantile_cont(value, 0.75) AS q3 "
            "FROM base GROUP BY group_value"
            ") SELECT q.group_value, q.valid_count, q.minimum, q.maximum, q.q1, q.median, q.q3, "
            "min(b.value) FILTER (WHERE b.value >= q.q1 - 1.5 * (q.q3 - q.q1)) AS lower_whisker, "
            "max(b.value) FILTER (WHERE b.value <= q.q3 + 1.5 * (q.q3 - q.q1)) AS upper_whisker, "
            "sum(CASE WHEN b.value < q.q1 - 1.5 * (q.q3 - q.q1) OR b.value > q.q3 + 1.5 * (q.q3 - q.q1) THEN 1 ELSE 0 END) AS outlier_count "
            "FROM quartiles q JOIN base b ON b.group_value = q.group_value "
            "GROUP BY q.group_value, q.valid_count, q.minimum, q.maximum, q.q1, q.median, q.q3 "
            "ORDER BY q.group_value LIMIT ?",
            [*parameters, MAX_COMPARISON_GROUP_COUNT + 1],
        )
        if len(rows) > MAX_COMPARISON_GROUP_COUNT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Box plots support at most {MAX_COMPARISON_GROUP_COUNT} selected groups; narrow the group selection",
            )
        points = [
            {
                "x": index,
                "y": float(row["median"]),
                "xLabel": str(row["group_value"]),
                "xRange": [float(row["lower_whisker"]), float(row["upper_whisker"])],
                "xRangeInclusive": True,
                "series": str(row["group_value"]),
                "group": str(row["group_value"]),
                "count": int(row["valid_count"]),
                "minimum": float(row["minimum"]),
                "q1": float(row["q1"]),
                "median": float(row["median"]),
                "q3": float(row["q3"]),
                "maximum": float(row["maximum"]),
                "lowerWhisker": float(row["lower_whisker"]),
                "upperWhisker": float(row["upper_whisker"]),
                "outlierCount": int(row["outlier_count"]),
            }
            for index, row in enumerate(rows)
        ]
        return {
            "points": points,
            "series": [point["series"] for point in points],
            "kpi": None,
            "valid_count": sum(point["count"] for point in points),
        }

    def _render_distribution(self, connection: duckdb.DuckDBPyConnection, relation: str, request: DataAssetVisualizationRequest) -> dict[str, Any]:
        x = self.store.identifier(request.x)
        group = self.store.identifier(request.group) if request.group else ""
        group_expression = f"CAST({group} AS VARCHAR)" if group else "'Values'"
        where, parameters = self._filtered_where(request, [x], group, [x])
        self._enforce_group_limit(
            connection, relation, request, group, where, parameters,
            MAX_COMPARISON_GROUP_COUNT, "Distribution comparison",
        )
        stats = self._fetch_dicts(
            connection,
            f"SELECT {group_expression} AS group_value, min(CAST({x} AS DOUBLE)) AS minimum, "
            f"max(CAST({x} AS DOUBLE)) AS maximum, avg(CAST({x} AS DOUBLE)) AS mean, "
            f"coalesce(stddev_samp(CAST({x} AS DOUBLE)), 0) AS deviation, count(*) AS valid_count "
            f"FROM {relation} {where} GROUP BY group_value ORDER BY group_value LIMIT ?",
            [*parameters, MAX_COMPARISON_GROUP_COUNT + 1],
        )
        if not stats:
            return {"points": [], "series": [], "kpi": None, "valid_count": 0, "approximate": True, "approximation_method": "binned_gaussian_kde"}
        if len(stats) > MAX_COMPARISON_GROUP_COUNT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Distribution comparison supports at most {MAX_COMPARISON_GROUP_COUNT} selected groups; narrow the group selection",
            )

        source_low = min(float(row["minimum"]) for row in stats)
        source_high = max(float(row["maximum"]) for row in stats)
        source_span = source_high - source_low
        source_bins = max(MIN_DENSITY_SOURCE_BINS, min(MAX_DENSITY_SOURCE_BINS, request.bins * 4))
        source_width = source_span / source_bins if source_span > 0 else 1.0
        binned = self._fetch_dicts(
            connection,
            f"SELECT {group_expression} AS group_value, "
            f"least(?, floor((CAST({x} AS DOUBLE) - ?) / ?))::INTEGER AS bin_index, count(*) AS bin_count "
            f"FROM {relation} {where} GROUP BY group_value, bin_index ORDER BY group_value, bin_index",
            [source_bins - 1, source_low, source_width, *parameters],
        )
        counts_by_group: dict[str, list[tuple[float, int]]] = {}
        for row in binned:
            center = source_low if source_span == 0 else source_low + (int(row["bin_index"]) + 0.5) * source_width
            counts_by_group.setdefault(str(row["group_value"]), []).append((center, int(row["bin_count"])))

        bandwidths: dict[str, float] = {}
        for row in stats:
            name = str(row["group_value"])
            count = int(row["valid_count"])
            deviation = float(row["deviation"])
            fallback_scale = source_span / 20 if source_span > 0 else max(abs(float(row["mean"])) * 0.01, 1.0)
            bandwidths[name] = max(1e-12, (1.06 * deviation if deviation > 0 else fallback_scale) * count ** -0.2)
        tail = 3 * max(bandwidths.values())
        evaluation_low = source_low - tail
        evaluation_high = source_high + tail
        if source_low >= 0 and evaluation_low < 0:
            evaluation_low = 0.0
        if source_high <= 0 and evaluation_high > 0:
            evaluation_high = 0.0
        if evaluation_low == evaluation_high:
            evaluation_high = evaluation_low + tail
        evaluation_width = (evaluation_high - evaluation_low) / max(1, request.bins - 1)
        normalizer = math.sqrt(2 * math.pi)
        points: list[dict[str, Any]] = []
        for row in stats:
            name = str(row["group_value"])
            count = int(row["valid_count"])
            bandwidth = bandwidths[name]
            weighted_bins = counts_by_group.get(name, [])
            for index in range(request.bins):
                value = evaluation_low + index * evaluation_width
                density = sum(
                    bin_count * math.exp(-0.5 * ((value - center) / bandwidth) ** 2)
                    for center, bin_count in weighted_bins
                ) / (count * bandwidth * normalizer)
                lower = max(evaluation_low, value - evaluation_width / 2)
                upper = min(evaluation_high, value + evaluation_width / 2)
                points.append({
                    "x": value,
                    "y": density,
                    "xLabel": self._format(value),
                    "xRange": [lower, upper],
                    "xRangeInclusive": index == request.bins - 1,
                    "series": name,
                    "group": name,
                    "count": count,
                })
        return {
            "points": points,
            "series": [str(row["group_value"]) for row in stats],
            "kpi": None,
            "valid_count": sum(int(row["valid_count"]) for row in stats),
            "approximate": True,
            "approximation_method": "binned_gaussian_kde",
        }

    def _render_scatter(self, connection: duckdb.DuckDBPyConnection, relation: str, request: DataAssetVisualizationRequest) -> dict[str, Any]:
        x, y = self.store.identifier(request.x), self.store.identifier(request.y)
        group = self.store.identifier(request.group) if request.group else ""
        where, parameters = self._filtered_where(request, [x, y], group, [x, y])
        group_count_sql = f"count(DISTINCT {group})" if group else "1"
        bounds = connection.execute(
            f"SELECT min({x}), max({x}), min({y}), max({y}), {group_count_sql} FROM {relation} {where}",
            parameters,
        ).fetchone()
        if bounds[0] is None:
            return {"points": [], "series": [], "kpi": None, "valid_count": 0}
        x_low, x_high, y_low, y_high = map(float, bounds[:4])
        group_count = max(1, int(bounds[4]))
        if request.trend != "none" and group_count > MAX_TREND_GROUP_COUNT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Scatter trends support at most {MAX_TREND_GROUP_COUNT} selected groups; narrow the group selection",
            )
        grid = max(
            SCATTER_MIN_GRID_SIZE,
            min(SCATTER_MAX_GRID_SIZE, int((request.max_points / group_count) ** 0.5)),
        )
        x_width = request.x_epsilon * 2 if request.x_epsilon > 0 else self._scatter_auto_width(x_low, x_high, grid)
        y_width = request.y_epsilon * 2 if request.y_epsilon > 0 else self._scatter_auto_width(y_low, y_high, grid)
        self._validate_scatter_bucket_width("X", x_low, x_high, x_width, request.x_epsilon > 0)
        self._validate_scatter_bucket_width("Y", y_low, y_high, y_width, request.y_epsilon > 0)
        x_origin = 0.0 if request.x_epsilon > 0 else x_low
        y_origin = 0.0 if request.y_epsilon > 0 else y_low
        x_bin_expression = f"floor(({x} - ?) / ? + 1e-12)::BIGINT" if request.x_epsilon > 0 else f"least({grid - 1}, floor(({x} - ?) / ?))::BIGINT"
        y_bin_expression = f"floor(({y} - ?) / ? + 1e-12)::BIGINT" if request.y_epsilon > 0 else f"least({grid - 1}, floor(({y} - ?) / ?))::BIGINT"
        group_select = f", CAST({group} AS VARCHAR) AS group_value" if group else ", 'Values' AS group_value"
        group_by = "x_bin, y_bin, group_value"
        rows = self._fetch_dicts(
            connection,
            f"WITH binned AS ("
            f"SELECT {x_bin_expression} AS x_bin, {y_bin_expression} AS y_bin{group_select}, "
            f"avg({x}) AS x_center, avg({y}) AS y_center, count(*) AS point_count "
            f"FROM {relation} {where} GROUP BY {group_by}"
            f"), ranked AS ("
            f"SELECT *, sum(point_count) OVER () AS total_valid_count, count(*) OVER () AS total_bin_count, "
            f"row_number() OVER (PARTITION BY group_value ORDER BY point_count DESC, x_bin, y_bin) AS group_rank "
            f"FROM binned"
            f") SELECT * FROM ranked ORDER BY group_rank, point_count DESC, group_value LIMIT ?",
            [x_origin, x_width, y_origin, y_width, *parameters, request.max_points],
        )
        rows.sort(key=lambda row: (int(row["x_bin"]), int(row["y_bin"]), str(row["group_value"])))
        points = [
            {
                "x": x_origin + (int(row["x_bin"]) + 0.5) * x_width if request.x_epsilon > 0 else float(row["x_center"]),
                "y": y_origin + (int(row["y_bin"]) + 0.5) * y_width if request.y_epsilon > 0 else float(row["y_center"]),
                "xLabel": f"{request.x}: {self._format(x_origin + (int(row['x_bin']) + 0.5) * x_width if request.x_epsilon > 0 else float(row['x_center']))}",
                "series": str(row["group_value"]),
                "group": str(row["group_value"]),
                "count": int(row["point_count"]),
                "xRange": [
                    x_origin + int(row["x_bin"]) * x_width,
                    x_origin + (int(row["x_bin"]) + 1) * x_width,
                ],
                "yRange": [
                    y_origin + int(row["y_bin"]) * y_width,
                    y_origin + (int(row["y_bin"]) + 1) * y_width,
                ],
                "xRangeInclusive": request.x_epsilon <= 0 and int(row["x_bin"]) == grid - 1,
                "yRangeInclusive": request.y_epsilon <= 0 and int(row["y_bin"]) == grid - 1,
            }
            for row in rows
        ]
        total_valid_count = int(rows[0]["total_valid_count"]) if rows else 0
        total_bin_count = int(rows[0]["total_bin_count"]) if rows else 0
        return {
            "points": points,
            "trends": self.trend_fitter.fit(connection, relation, request, x, y, group, where, parameters),
            "series": list(dict.fromkeys(point["series"] for point in points)),
            "kpi": None,
            "valid_count": total_valid_count,
            "truncated": total_bin_count > request.max_points,
        }

    @staticmethod
    def _scatter_auto_width(low: float, high: float, grid: int) -> float:
        span = high - low
        if math.isfinite(span):
            return span / grid or 1.0
        return high / grid - low / grid

    @staticmethod
    def _validate_scatter_bucket_width(axis: str, low: float, high: float, width: float, explicit: bool) -> None:
        if not math.isfinite(width) or width <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{axis} epsilon produces a non-finite scatter bucket width",
            )
        if explicit and max(abs(low / width), abs(high / width)) > MAX_SAFE_SCATTER_BIN_INDEX:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{axis} epsilon is too small for this data range; increase epsilon",
            )

    def _filtered_where(
        self,
        request: DataAssetVisualizationRequest,
        required_columns: list[str],
        group: str,
        finite_columns: list[str] | None = None,
    ) -> tuple[str, list[Any]]:
        clauses = [f"{column} IS NOT NULL" for column in dict.fromkeys(required_columns)]
        clauses.extend(
            f"isfinite(CAST({column} AS DOUBLE))"
            for column in dict.fromkeys(finite_columns or [])
        )
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

    def _enforce_group_limit(
        self,
        connection: duckdb.DuckDBPyConnection,
        relation: str,
        request: DataAssetVisualizationRequest,
        group: str,
        where: str,
        parameters: list[Any],
        limit: int,
        label: str,
    ) -> None:
        if not group:
            return
        if request.selected_groups is not None:
            selected_count = len(set(request.selected_groups))
            if selected_count <= limit:
                return
        else:
            rows = connection.execute(
                f"SELECT DISTINCT CAST({group} AS VARCHAR) FROM {relation} {where} LIMIT ?",
                [*parameters, limit + 1],
            ).fetchall()
            if len(rows) <= limit:
                return
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label} supports at most {limit} selected groups; narrow the group selection",
        )

    def _validate_columns(self, request: DataAssetVisualizationRequest, columns: dict[str, str]) -> None:
        required = request.feature_columns + ([request.target_column] if request.target_column else []) if request.kind == "projection" else [name for name in [request.x if request.kind != "kpi" else "", request.y if request.kind not in {"histogram", "boxplot"} else "", request.group] if name]
        for name in required:
            self._require_column(name, columns)
        if request.kind == "projection":
            if any(self._frontend_type(columns[name]) != "number" for name in request.feature_columns):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PCA feature columns must be numeric")
            return
        if request.kind in {"time_series", "autocorrelation", "lag_relationship"}:
            if self._frontend_type(columns[request.y]) != "number":
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Time-series value column must be numeric")
            if request.group:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Time-series charts do not support series grouping yet")
            if request.kind == "lag_relationship":
                self._require_column(request.driver_column, columns)
            return
        if request.group and request.group in {request.x, request.y}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Series column must be different from chart axes",
            )
        if request.kind in {"histogram", "boxplot"} and self._frontend_type(columns[request.x]) != "number":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Distribution measure must be numeric",
            )
        if request.kind == "scatter" and any(self._frontend_type(columns[name]) != "number" for name in [request.x, request.y]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Scatter axes must be numeric",
            )
        if request.kind != "scatter" and (request.y_epsilon > 0 or request.trend != "none"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Y epsilon and trend fitting are available only for scatter charts",
            )
        if request.kind not in {"line", "bar", "scatter"} and request.x_epsilon > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="X epsilon is available only for line, bar, and scatter charts",
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
        return finite_number(value)

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
