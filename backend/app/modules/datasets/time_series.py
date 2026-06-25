from __future__ import annotations

import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import duckdb
from fastapi import HTTPException, status

from app.modules.datasets.columnar import ColumnarDatasetStore
from app.modules.datasets.schemas import DataAssetVisualizationRequest, TimeSeriesAnalysisRequest


type DisplayBins = tuple[float, float, int, int, float]


class FullDatasetTimeSeriesAnalyzer:
    """Full-scope time-axis diagnostics with bounded aggregate outputs."""

    def __init__(self, store: ColumnarDatasetStore) -> None:
        self.store = store

    def analyze(
        self,
        connection: duckdb.DuckDBPyConnection,
        relation: str,
        request: TimeSeriesAnalysisRequest,
        columns: dict[str, str],
    ) -> dict[str, Any]:
        self._validate(request.time_column, request.value_column, columns)
        time = self.store.identifier(request.time_column)
        value = self.store.identifier(request.value_column)
        base = (
            f"SELECT try_cast({time} AS TIMESTAMP) AS ts, try_cast({value} AS DOUBLE) AS value "
            f"FROM {relation}"
        )
        counts = connection.execute(
            f"WITH source AS ({base}) SELECT count(*), count(ts), count(value) FILTER (WHERE isfinite(value)), "
            "count(*) FILTER (WHERE ts IS NOT NULL AND value IS NOT NULL AND isfinite(value)), "
            "count(DISTINCT ts) FILTER (WHERE ts IS NOT NULL), min(ts), max(ts) FROM source"
        ).fetchone()
        row_count = int(counts[0])
        valid_count = int(counts[3])
        if valid_count < 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Time-series analysis requires at least two valid time/value rows")
        valid = f"SELECT ts, value FROM ({base}) source WHERE ts IS NOT NULL AND value IS NOT NULL AND isfinite(value)"
        interval = connection.execute(
            f"WITH ordered AS (SELECT ts, epoch(ts) - epoch(lag(ts) OVER (ORDER BY ts)) AS delta FROM ({valid}) valid), "
            "deltas AS (SELECT delta FROM ordered WHERE delta > 0) "
            "SELECT count(*), median(delta), avg(delta), stddev_pop(delta), min(delta), max(delta) FROM deltas"
        ).fetchone()
        interval_count = int(interval[0])
        median_interval = float(interval[1]) if interval[1] is not None else None
        interval_mean = float(interval[2]) if interval[2] is not None else None
        interval_std = float(interval[3]) if interval[3] is not None else None
        gap_count = 0
        regular_ratio = None
        if median_interval and median_interval > 0:
            tolerance = max(1e-6, median_interval * 0.05)
            timing = connection.execute(
                f"WITH ordered AS (SELECT epoch(ts) - epoch(lag(ts) OVER (ORDER BY ts)) AS delta FROM ({valid}) valid) "
                "SELECT count(*) FILTER (WHERE delta > ?), "
                "avg(CASE WHEN delta > 0 AND abs(delta - ?) <= ? THEN 1.0 WHEN delta > 0 THEN 0.0 END) FROM ordered",
                [median_interval * 1.5, median_interval, tolerance],
            ).fetchone()
            gap_count = int(timing[0])
            regular_ratio = self._number(timing[1])
        value_stats = connection.execute(
            f"WITH valid AS ({valid}), numbered AS (SELECT ts, value, row_number() OVER (ORDER BY ts) AS position, "
            "lag(value) OVER (ORDER BY ts) AS previous FROM valid) "
            "SELECT avg(value), stddev_pop(value), min(value), max(value), "
            "regr_slope(value, epoch(ts) / 86400.0), regr_r2(value, epoch(ts) / 86400.0), "
            "avg(value - previous), stddev_pop(value - previous), corr(value, previous) FROM numbered"
        ).fetchone()
        autocorrelation = self._autocorrelation(connection, valid, request.max_lag)
        driver_columns = self._driver_columns(request.driver_column, request.driver_columns, request.value_column)
        driver_relationships = [
            self._driver_relationship(
                connection, relation, request.time_column, request.value_column, driver_column, request.max_lag, columns
            )
            for driver_column in driver_columns
        ]
        driver_relationships.sort(
            key=lambda item: abs(float(item["strongest_correlation"] or 0.0)),
            reverse=True,
        )
        cross_correlation = driver_relationships[0]["correlations"] if driver_relationships else []
        suggested_period = self._suggest_period(autocorrelation)
        seasonal_period = request.seasonal_period or suggested_period or 0
        series = self._series(connection, valid, request.max_points, request.rolling_window)
        seasonal_profile = self._seasonal_profile(connection, valid, seasonal_period) if seasonal_period >= 2 else []
        decomposition = self._decomposition(connection, valid, request.max_points, seasonal_period)
        difference_series = self._difference_series(connection, valid, request.max_points, request.rolling_window)
        feature_preview = self._feature_preview(connection, valid, seasonal_period, request.rolling_window)
        duplicate_timestamps = max(0, int(counts[1]) - int(counts[4]))
        missing_time = row_count - int(counts[1])
        invalid_value = row_count - int(counts[2])
        span_seconds = (counts[6] - counts[5]).total_seconds() if counts[5] is not None and counts[6] is not None else 0.0
        summary = {
            "start": self._json(counts[5]),
            "end": self._json(counts[6]),
            "span_seconds": span_seconds,
            "missing_time_count": missing_time,
            "invalid_value_count": invalid_value,
            "duplicate_timestamp_count": duplicate_timestamps,
            "median_interval_seconds": median_interval,
            "mean_interval_seconds": interval_mean,
            "interval_std_seconds": interval_std,
            "minimum_interval_seconds": self._number(interval[4]),
            "maximum_interval_seconds": self._number(interval[5]),
            "regular_interval_ratio": regular_ratio,
            "gap_count": gap_count,
            "mean": self._number(value_stats[0]),
            "std_dev": self._number(value_stats[1]),
            "minimum": self._number(value_stats[2]),
            "maximum": self._number(value_stats[3]),
            "trend_per_day": self._number(value_stats[4]),
            "trend_r_squared": self._number(value_stats[5]),
            "difference_mean": self._number(value_stats[6]),
            "difference_std_dev": self._number(value_stats[7]),
            "lag1_autocorrelation": self._number(value_stats[8]),
            "suggested_seasonal_period": suggested_period,
            "seasonal_period": seasonal_period or None,
            "interval_count": interval_count,
            "driver_column": driver_columns[0] if driver_columns else None,
        }
        strongest_driver = driver_relationships[0] if driver_relationships else None
        if strongest_driver:
            summary["strongest_driver_lag"] = strongest_driver["strongest_lag"]
            summary["strongest_driver_correlation"] = strongest_driver["strongest_correlation"]
            summary["strongest_driver_column"] = strongest_driver["driver_column"]
        return {
            "row_count": row_count,
            "scanned_row_count": row_count,
            "valid_count": valid_count,
            "execution_mode": "full_dataset",
            "summary": summary,
            "series": series,
            "autocorrelation": autocorrelation,
            "cross_correlation": cross_correlation,
            "driver_relationships": driver_relationships,
            "seasonal_profile": seasonal_profile,
            "decomposition": decomposition,
            "difference_series": difference_series,
            "feature_preview": feature_preview,
            "quality_notes": self._quality_notes(summary, valid_count),
        }

    def visualization(
        self,
        connection: duckdb.DuckDBPyConnection,
        relation: str,
        request: DataAssetVisualizationRequest,
        columns: dict[str, str],
    ) -> dict[str, Any]:
        self._validate(request.x, request.y, columns)
        time = self.store.identifier(request.x)
        value = self.store.identifier(request.y)
        valid = (
            f"SELECT try_cast({time} AS TIMESTAMP) AS ts, try_cast({value} AS DOUBLE) AS value FROM {relation} "
            f"WHERE try_cast({time} AS TIMESTAMP) IS NOT NULL AND isfinite(try_cast({value} AS DOUBLE))"
        )
        valid_count = int(connection.execute(f"SELECT count(*) FROM ({valid}) valid").fetchone()[0])
        if request.kind in {"autocorrelation", "lag_relationship"}:
            source = self._cross_correlation(
                connection, relation, request.x, request.y, request.driver_column, request.max_lag, columns
            ) if request.kind == "lag_relationship" else self._autocorrelation(connection, valid, request.max_lag)
            label = "Cross-correlation" if request.kind == "lag_relationship" else "ACF"
            points = [{
                "x": item["lag"], "y": item["correlation"], "xLabel": f"Lag {item['lag']}",
                "series": label, "count": item["pair_count"],
            } for item in source if item["correlation"] is not None]
            return {"points": points, "series": [label], "kpi": None, "valid_count": valid_count}
        series = self._series(connection, valid, request.max_points, request.rolling_window)
        points: list[dict[str, Any]] = []
        for item in series:
            epoch_value = datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00")).timestamp()
            points.append({
                "x": epoch_value, "y": item["value"], "xLabel": item["timestamp"], "series": "Observed",
                "count": item["count"], "yRange": [item["minimum"], item["maximum"]],
            })
            if item["rolling_mean"] is not None:
                points.append({
                    "x": epoch_value, "y": item["rolling_mean"], "xLabel": item["timestamp"],
                    "series": f"Rolling mean ({request.rolling_window} bins)", "count": item["count"],
                })
        return {
            "points": points,
            "series": list(dict.fromkeys(point["series"] for point in points)),
            "kpi": None,
            "valid_count": valid_count,
            "truncated": len(series) * 2 >= request.max_points,
        }

    def _autocorrelation(self, connection: duckdb.DuckDBPyConnection, valid: str, max_lag: int) -> list[dict[str, Any]]:
        lag_columns = ", ".join(f"lag(value, {lag}) OVER (ORDER BY ts) AS lag_{lag}" for lag in range(1, max_lag + 1))
        aggregates = ", ".join(
            f"corr(value, lag_{lag}) AS corr_{lag}, count(lag_{lag}) AS count_{lag}" for lag in range(1, max_lag + 1)
        )
        row = connection.execute(f"WITH lagged AS (SELECT value, {lag_columns} FROM ({valid}) valid) SELECT {aggregates} FROM lagged").fetchone()
        return [
            {"lag": lag, "correlation": self._number(row[(lag - 1) * 2]), "pair_count": int(row[(lag - 1) * 2 + 1])}
            for lag in range(1, max_lag + 1)
        ]

    def _cross_correlation(
        self,
        connection: duckdb.DuckDBPyConnection,
        relation: str,
        time_column: str,
        value_column: str,
        driver_column: str,
        max_lag: int,
        columns: dict[str, str],
    ) -> list[dict[str, Any]]:
        if driver_column not in columns:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown time-series column: {driver_column}")
        if self._frontend_type(columns[driver_column]) != "number":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Lag driver column must be numeric")
        if driver_column == value_column:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Lag driver must be different from the analyzed signal")
        time = self.store.identifier(time_column)
        value = self.store.identifier(value_column)
        driver = self.store.identifier(driver_column)
        valid = (
            f"SELECT try_cast({time} AS TIMESTAMP) AS ts, try_cast({value} AS DOUBLE) AS value, "
            f"try_cast({driver} AS DOUBLE) AS driver FROM {relation} WHERE try_cast({time} AS TIMESTAMP) IS NOT NULL "
            f"AND isfinite(try_cast({value} AS DOUBLE)) AND isfinite(try_cast({driver} AS DOUBLE))"
        )
        lag_columns = ", ".join(
            ["driver AS driver_lag_0"] + [f"lag(driver, {lag}) OVER (ORDER BY ts) AS driver_lag_{lag}" for lag in range(1, max_lag + 1)]
        )
        aggregates = ", ".join(
            f"corr(value, driver_lag_{lag}) AS corr_{lag}, count(driver_lag_{lag}) AS count_{lag}" for lag in range(max_lag + 1)
        )
        row = connection.execute(f"WITH lagged AS (SELECT value, {lag_columns} FROM ({valid}) valid) SELECT {aggregates} FROM lagged").fetchone()
        return [
            {"lag": lag, "correlation": self._number(row[lag * 2]), "pair_count": int(row[lag * 2 + 1])}
            for lag in range(max_lag + 1)
        ]

    def _driver_relationship(
        self,
        connection: duckdb.DuckDBPyConnection,
        relation: str,
        time_column: str,
        value_column: str,
        driver_column: str,
        max_lag: int,
        columns: dict[str, str],
    ) -> dict[str, Any]:
        correlations = self._cross_correlation(
            connection, relation, time_column, value_column, driver_column, max_lag, columns
        )
        strongest = max(
            (item for item in correlations if item["correlation"] is not None),
            key=lambda item: abs(float(item["correlation"])),
            default=None,
        )
        lag = int(strongest["lag"]) if strongest else None
        correlation = self._number(strongest["correlation"]) if strongest else None
        pair_count = int(strongest["pair_count"]) if strongest else 0
        return {
            "driver_column": driver_column,
            "strongest_lag": lag,
            "strongest_correlation": correlation,
            "pair_count": pair_count,
            "direction": self._relationship_direction(correlation),
            "strength": self._relationship_strength(correlation),
            "correlations": correlations,
        }

    def _series(self, connection: duckdb.DuckDBPyConnection, valid: str, max_points: int, rolling_window: int) -> list[dict[str, Any]]:
        low, _, _, bins, width = self._display_bins(connection, valid, max_points)
        cursor = connection.execute(
            f"WITH binned AS (SELECT least(?, floor((epoch(ts) - ?) / ?))::BIGINT AS bin, "
            f"min(ts) AS timestamp, avg(value) AS value, min(value) AS minimum, max(value) AS maximum, count(*) AS point_count "
            f"FROM ({valid}) valid GROUP BY bin), rolled AS (SELECT *, "
            f"avg(value) OVER (ORDER BY bin ROWS BETWEEN {rolling_window - 1} PRECEDING AND CURRENT ROW) AS rolling_mean, "
            f"stddev_pop(value) OVER (ORDER BY bin ROWS BETWEEN {rolling_window - 1} PRECEDING AND CURRENT ROW) AS rolling_std "
            "FROM binned) SELECT * FROM rolled ORDER BY bin",
            [bins - 1, low, width],
        )
        names = [str(column[0]) for column in cursor.description]
        return [{
            "timestamp": self._json(row["timestamp"]),
            "value": self._number(row["value"]),
            "minimum": self._number(row["minimum"]),
            "maximum": self._number(row["maximum"]),
            "count": int(row["point_count"]),
            "rolling_mean": self._number(row["rolling_mean"]),
            "rolling_std_dev": self._number(row["rolling_std"]),
        } for row in (dict(zip(names, values, strict=True)) for values in cursor.fetchall())]

    def _seasonal_profile(self, connection: duckdb.DuckDBPyConnection, valid: str, period: int) -> list[dict[str, Any]]:
        if period > 10_000:
            return []
        rows = connection.execute(
            f"WITH numbered AS (SELECT value, (row_number() OVER (ORDER BY ts) - 1) % ? AS phase FROM ({valid}) valid) "
            "SELECT phase, avg(value), stddev_pop(value), count(*) FROM numbered GROUP BY phase ORDER BY phase",
            [period],
        ).fetchall()
        return [{"phase": int(row[0]), "mean": self._number(row[1]), "std_dev": self._number(row[2]), "count": int(row[3])} for row in rows]

    def _decomposition(
        self,
        connection: duckdb.DuckDBPyConnection,
        valid: str,
        max_points: int,
        seasonal_period: int,
    ) -> list[dict[str, Any]]:
        low, _, _, bins, width = self._display_bins(connection, valid, max_points)
        period = seasonal_period if 2 <= seasonal_period <= 10_000 else 0
        rows = connection.execute(
            f"WITH numbered AS (SELECT ts, value, row_number() OVER (ORDER BY ts) - 1 AS position FROM ({valid}) valid), "
            "trend_stats AS (SELECT regr_slope(value, epoch(ts) / 86400.0) AS slope, "
            "regr_intercept(value, epoch(ts) / 86400.0) AS intercept, avg(value) AS fallback FROM numbered), "
            "trended AS (SELECT ts, value, position, "
            "coalesce(intercept + slope * epoch(ts) / 86400.0, fallback) AS trend, "
            "value - coalesce(intercept + slope * epoch(ts) / 86400.0, fallback) AS detrended "
            "FROM numbered CROSS JOIN trend_stats), "
            "phased AS (SELECT ts, value, trend, detrended, CASE WHEN ? >= 2 THEN position % ? ELSE 0 END AS phase FROM trended), "
            "seasonal AS (SELECT phase, CASE WHEN ? >= 2 THEN avg(detrended) ELSE 0 END AS seasonal FROM phased GROUP BY phase), "
            "binned AS (SELECT least(?, floor((epoch(ts) - ?) / ?))::BIGINT AS bin, min(ts) AS timestamp, "
            "avg(value) AS observed, avg(trend) AS trend, avg(seasonal.seasonal) AS seasonal, "
            "avg(value - trend - seasonal.seasonal) AS residual, count(*) AS point_count "
            "FROM phased JOIN seasonal USING (phase) GROUP BY bin) "
            "SELECT timestamp, observed, trend, seasonal, residual, point_count FROM binned ORDER BY bin",
            [period, period, period, bins - 1, low, width],
        ).fetchall()
        return [{
            "timestamp": self._json(row[0]),
            "observed": self._number(row[1]),
            "trend": self._number(row[2]),
            "seasonal": self._number(row[3]),
            "residual": self._number(row[4]),
            "count": int(row[5]),
        } for row in rows]

    def _difference_series(
        self,
        connection: duckdb.DuckDBPyConnection,
        valid: str,
        max_points: int,
        rolling_window: int,
    ) -> list[dict[str, Any]]:
        low, _, _, bins, width = self._display_bins(connection, valid, max_points)
        rows = connection.execute(
            f"WITH differenced AS (SELECT ts, value - lag(value) OVER (ORDER BY ts) AS difference FROM ({valid}) valid), "
            "binned AS (SELECT least(?, floor((epoch(ts) - ?) / ?))::BIGINT AS bin, min(ts) AS timestamp, "
            "avg(difference) AS difference, stddev_pop(difference) AS std_dev, count(difference) AS point_count "
            "FROM differenced WHERE difference IS NOT NULL GROUP BY bin), "
            f"rolled AS (SELECT *, avg(abs(difference)) OVER (ORDER BY bin ROWS BETWEEN {rolling_window - 1} PRECEDING AND CURRENT ROW) AS rolling_abs_difference "
            "FROM binned) SELECT timestamp, difference, std_dev, rolling_abs_difference, point_count FROM rolled ORDER BY bin",
            [bins - 1, low, width],
        ).fetchall()
        return [{
            "timestamp": self._json(row[0]),
            "difference": self._number(row[1]),
            "std_dev": self._number(row[2]),
            "rolling_abs_difference": self._number(row[3]),
            "count": int(row[4]),
        } for row in rows]

    def _display_bins(self, connection: duckdb.DuckDBPyConnection, valid: str, max_points: int) -> DisplayBins:
        bounds = connection.execute(f"SELECT min(epoch(ts)), max(epoch(ts)), count(*) FROM ({valid}) valid").fetchone()
        low, high, count = float(bounds[0]), float(bounds[1]), int(bounds[2])
        bins = max(1, min(max_points // 2, count))
        width = (high - low) / bins or 1.0
        return low, high, count, bins, width

    def _feature_preview(
        self,
        connection: duckdb.DuckDBPyConnection,
        valid: str,
        seasonal_period: int,
        rolling_window: int,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        seasonal_lag = max(1, seasonal_period)
        rows = connection.execute(
            f"WITH featured AS (SELECT ts, value, lag(value) OVER (ORDER BY ts) AS lag_1, "
            f"lag(value, {seasonal_lag}) OVER (ORDER BY ts) AS seasonal_lag, "
            f"value - lag(value) OVER (ORDER BY ts) AS difference, "
            f"avg(value) OVER (ORDER BY ts ROWS BETWEEN {rolling_window - 1} PRECEDING AND CURRENT ROW) AS rolling_mean, "
            f"stddev_pop(value) OVER (ORDER BY ts ROWS BETWEEN {rolling_window - 1} PRECEDING AND CURRENT ROW) AS rolling_std, "
            f"row_number() OVER (ORDER BY ts) AS position, count(*) OVER () AS total_count FROM ({valid}) valid) "
            "SELECT ts, value, lag_1, seasonal_lag, difference, rolling_mean, rolling_std, position "
            "FROM featured WHERE position <= ? OR position > total_count - ? ORDER BY position",
            [limit // 2, limit // 2],
        ).fetchall()
        return [{
            "timestamp": self._json(row[0]), "value": self._number(row[1]), "lag_1": self._number(row[2]),
            "seasonal_lag": self._number(row[3]), "difference": self._number(row[4]),
            "rolling_mean": self._number(row[5]), "rolling_std_dev": self._number(row[6]), "position": int(row[7]),
        } for row in rows]

    @staticmethod
    def _suggest_period(autocorrelation: list[dict[str, Any]]) -> int | None:
        candidates = []
        for index in range(1, len(autocorrelation) - 1):
            item = autocorrelation[index]
            previous = autocorrelation[index - 1]["correlation"]
            following = autocorrelation[index + 1]["correlation"]
            correlation = item["correlation"]
            if item["lag"] >= 3 and correlation is not None and previous is not None and following is not None:
                if float(correlation) > float(previous) and float(correlation) >= float(following):
                    candidates.append(item)
        if not candidates:
            return None
        best = max(candidates, key=lambda item: float(item["correlation"]))
        return int(best["lag"]) if float(best["correlation"]) >= 0.3 else None

    @staticmethod
    def _quality_notes(summary: dict[str, Any], valid_count: int) -> list[str]:
        notes: list[str] = []
        if summary["missing_time_count"]:
            notes.append(f"{summary['missing_time_count']} rows have an invalid or missing timestamp.")
        if summary["invalid_value_count"]:
            notes.append(f"{summary['invalid_value_count']} rows have an invalid or missing value.")
        if summary["duplicate_timestamp_count"]:
            notes.append(f"{summary['duplicate_timestamp_count']} observations share a timestamp; define an aggregation or entity key.")
        if summary["gap_count"]:
            notes.append(f"Detected {summary['gap_count']} intervals larger than 1.5× the median cadence.")
        if summary["regular_interval_ratio"] is not None and summary["regular_interval_ratio"] < 0.95:
            notes.append("Sampling is irregular; resample explicitly before algorithms that assume fixed cadence.")
        if summary["lag1_autocorrelation"] is not None and abs(summary["lag1_autocorrelation"]) >= 0.7:
            notes.append("Strong lag-1 autocorrelation: random train/test splitting would leak temporal structure.")
        if summary["suggested_seasonal_period"]:
            notes.append(f"ACF suggests a candidate seasonal period near lag {summary['suggested_seasonal_period']}; validate it with domain knowledge.")
        if summary.get("strongest_driver_lag") is not None:
            notes.append(
                f"Strongest tested driver relationship is {summary.get('strongest_driver_column') or 'the selected driver'} "
                f"at lag {summary['strongest_driver_lag']} "
                f"(correlation {summary['strongest_driver_correlation']:.3f}); correlation alone does not establish causality."
            )
        if not notes:
            notes.append(f"No major time-axis quality issue detected across {valid_count} valid observations.")
        return notes

    def _validate(self, time_column: str, value_column: str, columns: dict[str, str]) -> None:
        for name in (time_column, value_column):
            if name not in columns:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown time-series column: {name}")
        if self._frontend_type(columns[value_column]) != "number":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Time-series value column must be numeric")
        if time_column == value_column:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Time and value columns must be different")

    def _driver_columns(self, driver_column: str, driver_columns: list[str], value_column: str) -> list[str]:
        selected = [name for name in [driver_column, *driver_columns] if name]
        output: list[str] = []
        for name in selected:
            if name != value_column and name not in output:
                output.append(name)
        return output

    @staticmethod
    def _relationship_direction(correlation: float | None) -> str:
        if correlation is None:
            return "none"
        if correlation > 0:
            return "positive"
        if correlation < 0:
            return "negative"
        return "flat"

    @staticmethod
    def _relationship_strength(correlation: float | None) -> str:
        if correlation is None:
            return "not enough data"
        absolute = abs(correlation)
        if absolute >= 0.7:
            return "strong"
        if absolute >= 0.4:
            return "moderate"
        if absolute >= 0.2:
            return "weak"
        return "very weak"

    @staticmethod
    def _frontend_type(value: str) -> str:
        upper = value.upper()
        return "number" if any(token in upper for token in ["INT", "DECIMAL", "DOUBLE", "FLOAT", "REAL", "HUGEINT"]) else "date" if any(token in upper for token in ["DATE", "TIME"]) else "text"

    @staticmethod
    def _number(value: Any) -> float | None:
        if value is None:
            return None
        number = float(value)
        return number if math.isfinite(number) else None

    @staticmethod
    def _json(value: Any) -> Any:
        if isinstance(value, datetime | date):
            return value.isoformat().replace("+00:00", "Z")
        if isinstance(value, Decimal):
            return float(value)
        return value
