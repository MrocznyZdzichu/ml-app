import math
from typing import Any, Callable, Literal, TypedDict

import duckdb

from app.modules.datasets.schemas import (
    DataAssetVisualizationRequest,
    VisualizationFittedTrend,
)


TREND_POINT_COUNT = 80
SPLINE_SOURCE_BIN_COUNT = 24
MAX_TREND_GROUP_COUNT = 100
FetchRows = Callable[
    [duckdb.DuckDBPyConnection, str, list[Any]],
    list[dict[str, Any]],
]

class TrendPoint(TypedDict):
    x: float
    y: float


class TrendCurve(TypedDict, total=False):
    series: str
    kind: VisualizationFittedTrend
    valid_count: int
    points: list[TrendPoint]
    parameters: dict[str, Any]
    r_squared: float | None
    fit_space: Literal["y", "log_y", "binned_y"]
    approximate: bool


class ScatterTrendFitter:
    """Fits bounded scatter trend curves from full-relation DuckDB aggregates."""

    def __init__(self, fetch_rows: FetchRows) -> None:
        self._fetch_rows = fetch_rows

    def fit(
        self,
        connection: duckdb.DuckDBPyConnection,
        relation: str,
        request: DataAssetVisualizationRequest,
        x: str,
        y: str,
        group: str,
        where: str,
        parameters: list[Any],
    ) -> list[TrendCurve]:
        if request.trend == "none":
            return []
        group_expression = f"CAST({group} AS VARCHAR)" if group else "'Values'"
        if request.trend == "spline":
            return self._fit_splines(connection, relation, x, y, group_expression, where, parameters)
        if request.trend in {"linear", "exponential"}:
            return self._fit_regressions(
                connection, relation, request.trend, x, y, group_expression, where, parameters,
            )
        return self._fit_polynomials(
            connection, relation, request.polynomial_degree, x, y, group_expression, where, parameters,
        )

    def _fit_regressions(
        self,
        connection: duckdb.DuckDBPyConnection,
        relation: str,
        trend: Literal["linear", "exponential"],
        x: str,
        y: str,
        group_expression: str,
        where: str,
        parameters: list[Any],
    ) -> list[TrendCurve]:
        positive_y = f" AND {y} > 0" if trend == "exponential" else ""
        target = f"ln(CAST({y} AS DOUBLE))" if trend == "exponential" else f"CAST({y} AS DOUBLE)"
        rows = self._fetch_rows(
            connection,
            f"WITH source AS NOT MATERIALIZED ("
            f"SELECT CAST({x} AS DOUBLE) AS x_value, {target} AS target, {group_expression} AS group_value "
            f"FROM {relation} {where}{positive_y}"
            f") SELECT group_value, min(x_value) AS x_min, max(x_value) AS x_max, count(*) AS valid_count, "
            f"regr_slope(target, x_value) AS slope, regr_intercept(target, x_value) AS intercept, "
            f"regr_r2(target, x_value) AS r_squared FROM source GROUP BY group_value ORDER BY group_value",
            parameters,
        )
        curves: list[TrendCurve] = []
        for row in rows:
            slope = finite_number(row["slope"])
            intercept = finite_number(row["intercept"])
            if slope is None or intercept is None:
                continue
            x_min, x_max = float(row["x_min"]), float(row["x_max"])
            points = self._regression_points(x_min, x_max, slope, intercept, trend)
            fit_parameters = (
                {"amplitude": math.exp(min(709.0, intercept)), "rate": slope}
                if trend == "exponential"
                else {"slope": slope, "intercept": intercept}
            )
            curves.append({
                "series": str(row["group_value"]),
                "kind": trend,
                "valid_count": int(row["valid_count"]),
                "points": points,
                "parameters": fit_parameters,
                "r_squared": finite_number(row["r_squared"]),
                "fit_space": "log_y" if trend == "exponential" else "y",
            })
        return curves

    def _fit_polynomials(
        self,
        connection: duckdb.DuckDBPyConnection,
        relation: str,
        degree: int,
        x: str,
        y: str,
        group_expression: str,
        where: str,
        parameters: list[Any],
    ) -> list[TrendCurve]:
        moments = ", ".join(
            [f"sum(pow(z, {power})) AS s{power}" for power in range(2 * degree + 1)]
            + [f"sum(target * pow(z, {power})) AS t{power}" for power in range(degree + 1)]
            + ["sum(target * target) AS target_square_sum"]
        )
        rows = self._fetch_rows(
            connection,
            f"WITH source AS NOT MATERIALIZED ("
            f"SELECT CAST({x} AS DOUBLE) AS x_value, CAST({y} AS DOUBLE) AS target, "
            f"{group_expression} AS group_value FROM {relation} {where}"
            f"), stats AS ("
            f"SELECT group_value, min(x_value) AS x_min, max(x_value) AS x_max, count(*) AS valid_count "
            f"FROM source GROUP BY group_value"
            f"), normalized AS ("
            f"SELECT source.*, stats.x_min, stats.x_max, stats.valid_count, "
            f"2 * (source.x_value - stats.x_min) / nullif(stats.x_max - stats.x_min, 0) - 1 AS z "
            f"FROM source JOIN stats USING (group_value)"
            f") SELECT group_value, min(x_min) AS x_min, max(x_max) AS x_max, "
            f"max(valid_count) AS valid_count, {moments} FROM normalized WHERE z IS NOT NULL "
            f"GROUP BY group_value ORDER BY group_value",
            parameters,
        )
        curves: list[TrendCurve] = []
        for row in rows:
            matrix = [[float(row[f"s{i + j}"]) for j in range(degree + 1)] for i in range(degree + 1)]
            target_vector = [float(row[f"t{i}"]) for i in range(degree + 1)]
            coefficients = self._solve_linear_system(matrix, target_vector)
            if coefficients is None:
                continue
            x_min, x_max = float(row["x_min"]), float(row["x_max"])
            original_coefficients = self._original_axis_coefficients(coefficients, x_min, x_max)
            if any(not math.isfinite(coefficient) for coefficient in original_coefficients):
                continue
            curves.append({
                "series": str(row["group_value"]),
                "kind": "polynomial",
                "valid_count": int(row["valid_count"]),
                "points": self._polynomial_points(x_min, x_max, coefficients),
                "parameters": {"coefficients": original_coefficients, "degree": degree},
                "r_squared": self._polynomial_r_squared(row, coefficients, target_vector),
                "fit_space": "y",
            })
        return curves

    def _fit_splines(
        self,
        connection: duckdb.DuckDBPyConnection,
        relation: str,
        x: str,
        y: str,
        group_expression: str,
        where: str,
        parameters: list[Any],
    ) -> list[TrendCurve]:
        last_bin = SPLINE_SOURCE_BIN_COUNT - 1
        rows = self._fetch_rows(
            connection,
            f"WITH source AS NOT MATERIALIZED ("
            f"SELECT CAST({x} AS DOUBLE) AS x_value, CAST({y} AS DOUBLE) AS y_value, "
            f"{group_expression} AS group_value FROM {relation} {where}"
            f"), stats AS ("
            f"SELECT group_value, min(x_value) AS x_min, max(x_value) AS x_max, count(*) AS valid_count "
            f"FROM source GROUP BY group_value"
            f"), bounded AS ("
            f"SELECT source.*, stats.x_min, stats.x_max, stats.valid_count "
            f"FROM source JOIN stats USING (group_value)"
            f"), binned AS ("
            f"SELECT group_value, least({last_bin}, floor({SPLINE_SOURCE_BIN_COUNT} * "
            f"(x_value - x_min) / nullif(x_max - x_min, 0)))::INTEGER AS bin, "
            f"avg(x_value) AS x_value, avg(y_value) AS y_value, count(*) AS bin_count, "
            f"max(valid_count) AS valid_count FROM bounded WHERE x_min < x_max GROUP BY group_value, bin"
            f") SELECT * FROM binned ORDER BY group_value, x_value",
            parameters,
        )
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(str(row["group_value"]), []).append(row)
        return [
            {
                "series": series,
                "kind": "spline",
                "valid_count": int(nodes[0]["valid_count"]),
                "points": self._natural_spline(
                    [(float(node["x_value"]), float(node["y_value"])) for node in nodes],
                ),
                "approximate": True,
                "parameters": {"nodes": len(nodes), "source_bins": SPLINE_SOURCE_BIN_COUNT},
                "fit_space": "binned_y",
            }
            for series, nodes in grouped.items()
            if len(nodes) >= 2
        ]

    @staticmethod
    def _regression_points(
        x_min: float,
        x_max: float,
        slope: float,
        intercept: float,
        trend: Literal["linear", "exponential"],
    ) -> list[TrendPoint]:
        points: list[TrendPoint] = []
        for index in range(TREND_POINT_COUNT):
            x_value = interpolate(x_min, x_max, index, TREND_POINT_COUNT)
            fitted = intercept + slope * x_value
            y_value = math.exp(min(709.0, fitted)) if trend == "exponential" else fitted
            if finite_number(y_value) is not None:
                points.append({"x": x_value, "y": y_value})
        return points

    @staticmethod
    def _polynomial_points(
        x_min: float,
        x_max: float,
        coefficients: list[float],
    ) -> list[TrendPoint]:
        points: list[TrendPoint] = []
        for index in range(TREND_POINT_COUNT):
            x_value = interpolate(x_min, x_max, index, TREND_POINT_COUNT)
            normalized_x = 2 * (x_value - x_min) / (x_max - x_min) - 1
            y_value = sum(
                coefficient * normalized_x ** power
                for power, coefficient in enumerate(coefficients)
            )
            if finite_number(y_value) is not None:
                points.append({"x": x_value, "y": y_value})
        return points

    @staticmethod
    def _polynomial_r_squared(
        row: dict[str, Any],
        coefficients: list[float],
        target_vector: list[float],
    ) -> float | None:
        target_square_sum = finite_number(row["target_square_sum"])
        if target_square_sum is None:
            return None
        residual_sum = target_square_sum - sum(
            coefficient * target_vector[index]
            for index, coefficient in enumerate(coefficients)
        )
        total_sum = target_square_sum - target_vector[0] ** 2 / int(row["valid_count"])
        return min(1.0, 1.0 - residual_sum / total_sum) if total_sum > 1e-15 else None

    @staticmethod
    def _solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float] | None:
        if any(not math.isfinite(value) for row in matrix for value in row):
            return None
        if any(not math.isfinite(value) for value in vector):
            return None
        size = len(vector)
        augmented = [row[:] + [vector[index]] for index, row in enumerate(matrix)]
        for column in range(size):
            pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
            if abs(augmented[pivot][column]) < 1e-12:
                return None
            augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
            divisor = augmented[column][column]
            augmented[column] = [value / divisor for value in augmented[column]]
            for row in range(size):
                if row == column:
                    continue
                factor = augmented[row][column]
                augmented[row] = [
                    value - factor * pivot_value
                    for value, pivot_value in zip(augmented[row], augmented[column])
                ]
        return [augmented[index][-1] for index in range(size)]

    @staticmethod
    def _original_axis_coefficients(
        coefficients: list[float], x_min: float, x_max: float,
    ) -> list[float]:
        scale = 2.0 / (x_max - x_min)
        shift = -1.0 - scale * x_min
        original = [0.0] * len(coefficients)
        for power, coefficient in enumerate(coefficients):
            for x_power in range(power + 1):
                original[x_power] += (
                    coefficient
                    * math.comb(power, x_power)
                    * scale ** x_power
                    * shift ** (power - x_power)
                )
        return original

    @staticmethod
    def _natural_spline(nodes: list[tuple[float, float]]) -> list[TrendPoint]:
        unique_nodes: list[tuple[float, float]] = []
        for node in sorted(nodes):
            if not unique_nodes or node[0] != unique_nodes[-1][0]:
                unique_nodes.append(node)
        if len(unique_nodes) < 2:
            return []
        xs = [node[0] for node in unique_nodes]
        ys = [node[1] for node in unique_nodes]
        second = [0.0] * len(xs)
        upper = [0.0] * len(xs)
        for index in range(1, len(xs) - 1):
            ratio = (xs[index] - xs[index - 1]) / (xs[index + 1] - xs[index - 1])
            pivot = ratio * second[index - 1] + 2.0
            second[index] = (ratio - 1.0) / pivot
            slope_delta = (
                (ys[index + 1] - ys[index]) / (xs[index + 1] - xs[index])
                - (ys[index] - ys[index - 1]) / (xs[index] - xs[index - 1])
            )
            upper[index] = (
                6.0 * slope_delta / (xs[index + 1] - xs[index - 1])
                - ratio * upper[index - 1]
            ) / pivot
        for index in range(len(xs) - 2, -1, -1):
            second[index] = second[index] * second[index + 1] + upper[index]
        return ScatterTrendFitter._evaluate_spline(xs, ys, second)

    @staticmethod
    def _evaluate_spline(xs: list[float], ys: list[float], second: list[float]) -> list[TrendPoint]:
        points: list[TrendPoint] = []
        interval = 0
        for sample in range(TREND_POINT_COUNT):
            x_value = interpolate(xs[0], xs[-1], sample, TREND_POINT_COUNT)
            while interval < len(xs) - 2 and x_value > xs[interval + 1]:
                interval += 1
            width = xs[interval + 1] - xs[interval]
            left = (xs[interval + 1] - x_value) / width
            right = (x_value - xs[interval]) / width
            y_value = (
                left * ys[interval]
                + right * ys[interval + 1]
                + (
                    (left ** 3 - left) * second[interval]
                    + (right ** 3 - right) * second[interval + 1]
                )
                * width ** 2
                / 6.0
            )
            if finite_number(y_value) is not None:
                points.append({"x": x_value, "y": y_value})
        return points

def finite_number(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def interpolate(low: float, high: float, index: int, count: int) -> float:
    ratio = index / (count - 1)
    return low * (1.0 - ratio) + high * ratio
