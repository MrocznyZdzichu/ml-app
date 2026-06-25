from __future__ import annotations

import math
from typing import Any

import duckdb
import numpy as np
from fastapi import HTTPException, status

from app.modules.datasets.columnar import ColumnarDatasetStore
from app.modules.datasets.schemas import DataAssetVisualizationRequest


MAX_PROJECTION_CLASSES = 40


class FullDatasetPcaProjection:
    """Fits PCA from full-dataset sufficient statistics and returns bounded 2-D bins."""

    def __init__(self, store: ColumnarDatasetStore) -> None:
        self.store = store

    def render(
        self,
        connection: duckdb.DuckDBPyConnection,
        relation: str,
        request: DataAssetVisualizationRequest,
        columns: dict[str, str],
    ) -> dict[str, Any]:
        feature_names = request.feature_columns
        quoted = [self.store.identifier(name) for name in feature_names]
        target = self.store.identifier(request.target_column) if request.target_column else ""
        target_is_numeric = bool(target and self._frontend_type(columns[request.target_column]) == "number")
        required = [*quoted, *([target] if target else [])]
        where = "WHERE " + " AND ".join(
            [f"{column} IS NOT NULL" for column in required]
            + [f"isfinite(CAST({column} AS DOUBLE))" for column in quoted]
            + ([f"isfinite(CAST({target} AS DOUBLE))"] if target_is_numeric else [])
        )

        means_sql = ", ".join(f"avg(CAST({column} AS DOUBLE))" for column in quoted)
        stds_sql = ", ".join(f"stddev_pop(CAST({column} AS DOUBLE))" for column in quoted)
        stats = connection.execute(
            f"SELECT count(*), {means_sql}, {stds_sql} FROM {relation} {where}"
        ).fetchone()
        valid_count = int(stats[0])
        if valid_count < 2:
            return self._empty(valid_count, feature_names, target_is_numeric)

        feature_count = len(quoted)
        means = np.asarray(stats[1 : 1 + feature_count], dtype=float)
        stds = np.asarray(stats[1 + feature_count :], dtype=float)
        safe_stds = np.where(np.isfinite(stds) & (stds > 0), stds, 1.0)
        standardized = [f"((CAST({column} AS DOUBLE) - {self._literal(means[index])}) / {self._literal(safe_stds[index])})" for index, column in enumerate(quoted)]
        covariance_sql = ", ".join(
            f"covar_pop({standardized[left]}, {standardized[right]})"
            for left in range(feature_count)
            for right in range(left, feature_count)
        )
        covariance_values = connection.execute(f"SELECT {covariance_sql} FROM {relation} {where}").fetchone()
        covariance = np.zeros((feature_count, feature_count), dtype=float)
        value_index = 0
        for left in range(feature_count):
            for right in range(left, feature_count):
                value = float(covariance_values[value_index] or 0.0)
                covariance[left, right] = covariance[right, left] = value
                value_index += 1

        eigenvalues, eigenvectors = np.linalg.eigh(covariance)
        order = np.argsort(eigenvalues)[::-1]
        eigenvalues = np.maximum(eigenvalues[order], 0.0)
        components = eigenvectors[:, order[:2]]
        for component_index in range(components.shape[1]):
            pivot = int(np.argmax(np.abs(components[:, component_index])))
            if components[pivot, component_index] < 0:
                components[:, component_index] *= -1
        pc1 = self._component_sql(standardized, components[:, 0])
        pc2 = self._component_sql(standardized, components[:, 1])
        projected = f"SELECT {pc1} AS pc1, {pc2} AS pc2{f', {target} AS target_value' if target else ''} FROM {relation} {where}"
        bounds = connection.execute(f"SELECT min(pc1), max(pc1), min(pc2), max(pc2) FROM ({projected}) projected").fetchone()
        if bounds[0] is None:
            return self._empty(valid_count, feature_names, target_is_numeric)
        x_low, x_high, y_low, y_high = map(float, bounds)
        class_count = 1
        if target and not target_is_numeric:
            class_count = int(connection.execute(f"SELECT count(DISTINCT target_value) FROM ({projected}) projected").fetchone()[0])
            if class_count > MAX_PROJECTION_CLASSES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"PCA classification coloring supports at most {MAX_PROJECTION_CLASSES} target classes",
                )
        grid = max(8, min(50, int(math.sqrt(request.max_points / max(1, class_count)))))
        x_width = (x_high - x_low) / grid or 1.0
        y_width = (y_high - y_low) / grid or 1.0
        x_bin = f"least({grid - 1}, floor((pc1 - {self._literal(x_low)}) / {self._literal(x_width)}))::BIGINT"
        y_bin = f"least({grid - 1}, floor((pc2 - {self._literal(y_low)}) / {self._literal(y_width)}))::BIGINT"
        if target and not target_is_numeric:
            group_select = ", CAST(target_value AS VARCHAR) AS group_value"
            group_by = "x_bin, y_bin, group_value"
            target_select = ", NULL::DOUBLE AS target_mean"
        else:
            group_select = ", 'Target gradient' AS group_value"
            group_by = "x_bin, y_bin, group_value"
            target_select = ", avg(CAST(target_value AS DOUBLE)) AS target_mean" if target else ", NULL::DOUBLE AS target_mean"
        rows = self._fetch_dicts(
            connection,
            f"WITH projected AS ({projected}), binned AS ("
            f"SELECT {x_bin} AS x_bin, {y_bin} AS y_bin{group_select}, avg(pc1) AS pc1, avg(pc2) AS pc2, "
            f"count(*) AS point_count{target_select} FROM projected GROUP BY {group_by}"
            f"), ranked AS (SELECT *, count(*) OVER () AS total_bin_count FROM binned) "
            f"SELECT * FROM ranked ORDER BY point_count DESC, x_bin, y_bin LIMIT ?",
            [request.max_points],
        )
        rows.sort(key=lambda row: (int(row["x_bin"]), int(row["y_bin"]), str(row["group_value"])))
        points = [
            {
                "x": float(row["pc1"]),
                "y": float(row["pc2"]),
                "xLabel": f"PC1: {float(row['pc1']):.4g}",
                "series": str(row["group_value"]),
                "group": str(row["group_value"]),
                "count": int(row["point_count"]),
                "targetValue": float(row["target_mean"]) if row["target_mean"] is not None else None,
                "xRange": [x_low + int(row["x_bin"]) * x_width, x_low + (int(row["x_bin"]) + 1) * x_width],
                "yRange": [y_low + int(row["y_bin"]) * y_width, y_low + (int(row["y_bin"]) + 1) * y_width],
            }
            for row in rows
        ]
        total_variance = float(eigenvalues.sum())
        explained = [float(value / total_variance) if total_variance > 0 else 0.0 for value in eigenvalues[:2]]
        return {
            "points": points,
            "series": list(dict.fromkeys(point["series"] for point in points)),
            "kpi": None,
            "valid_count": valid_count,
            "truncated": bool(rows and int(rows[0]["total_bin_count"]) > request.max_points),
            "reduction_metadata": {
                "method": "pca",
                "feature_columns": feature_names,
                "feature_count": feature_count,
                "target_column": request.target_column or None,
                "target_type": "continuous" if target_is_numeric else "categorical" if target else "none",
                "explained_variance_ratio": explained,
                "complete_case_rows": valid_count,
                "fit_scope": "full_dataset_complete_cases",
            },
        }

    @staticmethod
    def _component_sql(standardized: list[str], weights: np.ndarray) -> str:
        return " + ".join(f"({FullDatasetPcaProjection._literal(float(weight))} * {column})" for column, weight in zip(standardized, weights, strict=True))

    @staticmethod
    def _literal(value: float) -> str:
        if not math.isfinite(value):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PCA statistics contain non-finite values")
        return format(value, ".17g")

    @staticmethod
    def _fetch_dicts(connection: duckdb.DuckDBPyConnection, sql: str, parameters: list[Any]) -> list[dict[str, Any]]:
        cursor = connection.execute(sql, parameters)
        names = [str(column[0]) for column in cursor.description]
        return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]

    @staticmethod
    def _frontend_type(value: str) -> str:
        upper = value.upper()
        return "number" if any(token in upper for token in ["INT", "DECIMAL", "DOUBLE", "FLOAT", "REAL", "HUGEINT"]) else "text"

    @staticmethod
    def _empty(valid_count: int, features: list[str], target_is_numeric: bool) -> dict[str, Any]:
        return {
            "points": [], "series": [], "kpi": None, "valid_count": valid_count,
            "reduction_metadata": {
                "method": "pca", "feature_columns": features,
                "target_type": "continuous" if target_is_numeric else "categorical",
                "complete_case_rows": valid_count, "fit_scope": "full_dataset_complete_cases",
            },
        }
