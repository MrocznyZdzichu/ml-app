import math
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from itertools import combinations
from typing import Any, Callable

import duckdb

from app.modules.datasets.columnar import ColumnarDatasetStore
from app.modules.datasets.domain import DataAsset


COLORS = ["#3f7fc4", "#2ea39a", "#d08b2d", "#c45f74", "#7b6fc2", "#5d8f63", "#b56f3f", "#607d9b"]


@dataclass(frozen=True)
class ProfileOptions:
    target_column: str
    target_type: str
    comparison_column: str
    comparison_type: str
    include_summary: bool
    include_univariate: bool
    include_target_relations: bool
    include_segments: bool
    include_graphic_summaries: bool
    graphic_source_limit: int
    max_target_features: int
    max_segment_features: int

    @classmethod
    def from_mapping(cls, settings: dict[str, Any]) -> "ProfileOptions":
        target_column = str(settings.get("target_column") or "")
        return cls(
            target_column=target_column,
            target_type=str(settings.get("target_type") or "categorical"),
            comparison_column=str(settings.get("comparison_column") or target_column),
            comparison_type=str(settings.get("comparison_type") or settings.get("target_type") or "categorical"),
            include_summary=bool(settings.get("include_summary", True)),
            include_univariate=bool(settings.get("include_univariate", True)),
            include_target_relations=bool(settings.get("include_target_relations", True)),
            include_segments=bool(settings.get("include_segments", True)),
            include_graphic_summaries=bool(settings.get("include_graphic_summaries", True)),
            graphic_source_limit=max(100, int(settings.get("row_limit") or 50_000)),
            max_target_features=max(1, int(settings.get("max_target_features") or 30)),
            max_segment_features=max(2, int(settings.get("max_segment_features") or 4)),
        )


class FullDatasetProfiler:
    """Builds the UI profile contract with SQL aggregates over every dataset row."""

    def __init__(self, store: ColumnarDatasetStore | None = None) -> None:
        self.store = store or ColumnarDatasetStore()

    def profile(
        self,
        asset: DataAsset,
        settings: dict[str, Any],
        load_asset: Callable[[str], DataAsset] | None = None,
    ) -> dict[str, Any]:
        options = ProfileOptions.from_mapping(settings)
        connection = self.store.connect(asset)
        relation = self.store.relation_sql(asset, load_asset)
        try:
            columns = self._asset_columns(connection, relation, asset)
            row_count = int(connection.execute(f"SELECT count(*) FROM {relation}").fetchone()[0])
            roles = self._roles(asset)
            profiles = [
                self._column_profile(
                    connection,
                    relation,
                    column,
                    row_count,
                    roles,
                    detailed=options.include_univariate or (
                        options.include_target_relations and column["name"] == options.comparison_column
                    ),
                    include_graphics=options.include_graphic_summaries,
                )
                for column in columns
            ]
            relations = []
            if options.include_target_relations and options.comparison_column:
                relations = self._relations(
                    connection,
                    relation,
                    columns,
                    profiles,
                    roles,
                    options.comparison_column,
                    options.comparison_type,
                    options.include_graphic_summaries,
                    options.graphic_source_limit,
                    options.max_target_features,
                )
            segment_profile = None
            if options.include_segments and options.target_column:
                segment_profile = self._segments(
                    connection,
                    relation,
                    columns,
                    profiles,
                    roles,
                    options.target_column,
                    options.target_type,
                    options.max_segment_features,
                    options.include_graphic_summaries,
                )
            notes = self._quality_notes(profiles, row_count, roles, options.target_column) if options.include_summary else []
            return {
                "dataset_id": asset.id,
                "columns": columns,
                "row_count": row_count,
                "profile": {
                    "columnProfiles": profiles,
                    "targetRelations": relations,
                    "segmentProfile": segment_profile,
                    "dataQualityNotes": notes,
                },
            }
        finally:
            connection.close()

    def schema(self, asset: DataAsset, limit: int = 1000) -> dict[str, Any]:
        connection = self.store.connect(asset)
        relation = self.store.lightweight_csv_relation_sql(asset)
        try:
            columns = self._asset_columns(connection, relation, asset)
            row_count = int(asset.row_count or 0)
            names = ", ".join(self.store.identifier(column["name"]) for column in columns)
            records = self._fetch_dicts(connection, f"SELECT {names} FROM {relation} LIMIT ?", [limit])
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

    def _columns(self, connection: duckdb.DuckDBPyConnection, relation: str) -> list[dict[str, str]]:
        rows = connection.execute(f"DESCRIBE SELECT * FROM {relation}").fetchall()
        return [{"name": str(row[0]), "type": self._frontend_type(str(row[1]))} for row in rows]

    def _asset_columns(
        self,
        connection: duckdb.DuckDBPyConnection,
        relation: str,
        asset: DataAsset,
    ) -> list[dict[str, str]]:
        stored = asset.metadata.get("source_schema") if isinstance(asset.metadata, dict) else None
        return stored if isinstance(stored, list) and stored else self._columns(connection, relation)

    def _column_profile(
        self,
        connection: duckdb.DuckDBPyConnection,
        relation: str,
        column: dict[str, str],
        row_count: int,
        roles: dict[str, Any],
        detailed: bool,
        include_graphics: bool,
    ) -> dict[str, Any]:
        name = column["name"]
        quoted = self.store.identifier(name)
        numeric = column["type"] == "number"
        aggregates = [
            f"count({quoted})",
            f"count(DISTINCT {quoted})",
            f"min({quoted})",
            f"max({quoted})",
        ]
        if numeric:
            aggregates.append(f"avg({quoted})")
            if detailed:
                aggregates.extend([f"median({quoted})", f"stddev_samp({quoted})"])
        values = connection.execute(f"SELECT {', '.join(aggregates)} FROM {relation}").fetchone()
        count = int(values[0])
        unique = int(values[1])
        minimum = self._json_value(values[2])
        maximum = self._json_value(values[3])
        mean = self._number(values[4]) if numeric else None
        median = self._number(values[5]) if numeric and detailed else None
        std_dev = self._number(values[6]) if numeric and detailed else None
        top_rows = connection.execute(
            f"SELECT {quoted}, count(*) AS frequency FROM {relation} "
            f"WHERE {quoted} IS NOT NULL GROUP BY {quoted} "
            "ORDER BY frequency DESC, CAST(" + quoted + " AS VARCHAR) LIMIT 10"
        ).fetchall() if detailed else []
        top_values = [
            {"value": self._json_value(row[0]), "count": int(row[1]), "share": self._ratio(row[1], row_count)}
            for row in top_rows
        ]
        example_rows = connection.execute(
            f"SELECT {quoted} FROM {relation} WHERE {quoted} IS NOT NULL LIMIT 3"
        ).fetchall() if detailed else []
        role = self._column_role(name, column["type"], roles)
        missing = row_count - count
        missing_rate = self._ratio(missing, row_count)
        unique_rate = self._ratio(unique, count)
        notes: list[str] = []
        if missing_rate >= 0.3:
            notes.append("High missingness")
        if unique_rate >= 0.95 and role not in {"identifier", "timestamp", "period_id"}:
            notes.append("Near-unique values")
        if unique <= 1 and count > 0:
            notes.append("Constant column")
        if role == "ignored":
            notes.append("Excluded by role")
        if role in {"feature_categorical", "text"} and unique > 50:
            notes.append("High-cardinality category")
        histogram = []
        if numeric and detailed and include_graphics and count:
            histogram = self._histogram(connection, relation, quoted, count, minimum, maximum)
        return {
            "name": name,
            "type": column["type"],
            "role": role,
            "count": count,
            "missing": missing,
            "missingRate": missing_rate,
            "unique": unique,
            "uniqueRate": unique_rate,
            "mean": mean,
            "median": median,
            "minimum": minimum,
            "maximum": maximum,
            "stdDev": std_dev,
            "mode": top_values[0]["value"] if top_values else None,
            "topValues": top_values,
            "histogram": histogram,
            "examples": [self._json_value(row[0]) for row in example_rows],
            "notes": notes,
        }

    def _histogram(
        self,
        connection: duckdb.DuckDBPyConnection,
        relation: str,
        quoted: str,
        count: int,
        minimum: Any,
        maximum: Any,
        bins: int = 12,
    ) -> list[dict[str, Any]]:
        low = float(minimum)
        high = float(maximum)
        if low == high:
            return [{"label": self._format(low), "count": count, "share": 1.0}]
        width = (high - low) / bins
        rows = connection.execute(
            f"SELECT least(?, floor(({quoted} - ?) / ?))::INTEGER AS bin, count(*) "
            f"FROM {relation} WHERE {quoted} IS NOT NULL GROUP BY bin ORDER BY bin",
            [bins - 1, low, width],
        ).fetchall()
        counts = {int(row[0]): int(row[1]) for row in rows}
        return [
            {
                "label": f"{self._format(low + index * width)} - {self._format(high if index == bins - 1 else low + (index + 1) * width)}",
                "count": counts.get(index, 0),
                "share": self._ratio(counts.get(index, 0), count),
            }
            for index in range(bins)
        ]

    def _relations(
        self,
        connection: duckdb.DuckDBPyConnection,
        relation: str,
        columns: list[dict[str, str]],
        profiles: list[dict[str, Any]],
        roles: dict[str, Any],
        comparison_column: str,
        comparison_type: str,
        include_graphics: bool,
        graphic_limit: int,
        max_features: int,
    ) -> list[dict[str, Any]]:
        profile_by_name = {profile["name"]: profile for profile in profiles}
        comparison = next((column for column in columns if column["name"] == comparison_column), None)
        if not comparison:
            return []
        output = []
        for feature in columns:
            if feature["name"] == comparison_column:
                continue
            role = self._column_role(feature["name"], feature["type"], roles)
            if role in {"ignored", "identifier"}:
                continue
            feature_numeric = self._is_numeric_measure(feature, role, profile_by_name[feature["name"]])
            if comparison_type == "continuous" and feature_numeric:
                result = self._numeric_relation(
                    connection, relation, feature, role, comparison_column, include_graphics, graphic_limit
                )
            elif comparison_type == "continuous":
                result = self._grouped_relation(
                    connection, relation, feature, role, feature["name"], comparison_column,
                    "comparison mean by feature", comparison_column, include_graphics,
                )
            elif feature_numeric:
                result = self._grouped_relation(
                    connection, relation, feature, role, comparison_column, feature["name"],
                    "feature stats by comparison", comparison_column, include_graphics,
                )
            else:
                result = self._categorical_relation(
                    connection, relation, feature, role, comparison_column, include_graphics
                )
            if result:
                output.append(result)
                if len(output) >= max_features:
                    break
        return output

    def _numeric_relation(
        self,
        connection: duckdb.DuckDBPyConnection,
        relation: str,
        feature: dict[str, str],
        role: str,
        comparison: str,
        include_graphics: bool,
        graphic_limit: int,
    ) -> dict[str, Any] | None:
        x = self.store.identifier(feature["name"])
        y = self.store.identifier(comparison)
        row = connection.execute(
            f"SELECT count(*), corr({x}, {y}), covar_samp({x}, {y}), regr_slope({y}, {x}), "
            f"regr_intercept({y}, {x}), regr_r2({y}, {x}), min({x}), max({x}), min({y}), max({y}) "
            f"FROM {relation} WHERE {x} IS NOT NULL AND {y} IS NOT NULL"
        ).fetchone()
        if not row or int(row[0]) < 3 or row[1] is None:
            return None
        spearman = connection.execute(
            "WITH ranked AS (SELECT "
            f"rank() OVER (ORDER BY {x}) + (count(*) OVER (PARTITION BY {x}) - 1) / 2.0 AS rx, "
            f"rank() OVER (ORDER BY {y}) + (count(*) OVER (PARTITION BY {y}) - 1) / 2.0 AS ry "
            f"FROM {relation} WHERE {x} IS NOT NULL AND {y} IS NOT NULL) SELECT corr(rx, ry) FROM ranked"
        ).fetchone()[0]
        numeric_stats = {
            "pearson": self._number(row[1]),
            "spearman": self._number(spearman),
            "rSquared": self._number(row[5]),
            "covariance": self._number(row[2]),
            "slope": self._number(row[3]),
            "intercept": self._number(row[4]),
        }
        scatter = None
        if include_graphics:
            sample_size = max(100, min(800, graphic_limit))
            points = self._fetch_dicts(
                connection,
                f"SELECT {x} AS x, {y} AS y FROM (SELECT {x}, {y} FROM {relation} "
                f"WHERE {x} IS NOT NULL AND {y} IS NOT NULL USING SAMPLE reservoir({sample_size} ROWS))",
            )
            scatter = {
                "xColumn": feature["name"],
                "yColumn": comparison,
                "xMin": self._number(row[6]),
                "xMax": self._number(row[7]),
                "yMin": self._number(row[8]),
                "yMax": self._number(row[9]),
                "points": [{"x": self._number(point["x"]), "y": self._number(point["y"])} for point in points],
                "trendLine": {
                    "x1": self._number(row[6]),
                    "y1": self._number(row[4]) + self._number(row[3]) * self._number(row[6]),
                    "x2": self._number(row[7]),
                    "y2": self._number(row[4]) + self._number(row[3]) * self._number(row[7]),
                },
            }
        correlation = self._number(row[1])
        return {
            "feature": feature["name"], "role": role, "type": feature["type"],
            "kind": "numeric correlation", "score": min(1.0, abs(correlation)),
            "signal": f"r {self._signed(correlation)}",
            "detail": f"{feature['name']} moves {'with' if correlation >= 0 else 'against'} {comparison} across the full dataset.",
            "comparisonColumn": comparison, "groupStats": [], "densityPlot": None,
            "numericStats": numeric_stats, "scatterPlot": scatter, "categoricalStats": None,
        }

    def _grouped_relation(
        self,
        connection: duckdb.DuckDBPyConnection,
        relation: str,
        feature: dict[str, str],
        role: str,
        group_column: str,
        numeric_column: str,
        kind: str,
        comparison_column: str,
        include_graphics: bool,
    ) -> dict[str, Any] | None:
        group = self.store.identifier(group_column)
        numeric = self.store.identifier(numeric_column)
        total = int(connection.execute(
            f"SELECT count(*) FROM {relation} WHERE {group} IS NOT NULL AND {numeric} IS NOT NULL"
        ).fetchone()[0])
        minimum = max(3, math.floor(total * 0.03))
        rows = connection.execute(
            f"SELECT CAST({group} AS VARCHAR), count(*), min({numeric}), max({numeric}), median({numeric}), "
            f"avg({numeric}), coalesce(stddev_samp({numeric}), 0) FROM {relation} "
            f"WHERE {group} IS NOT NULL AND {numeric} IS NOT NULL GROUP BY 1 HAVING count(*) >= ? ORDER BY avg({numeric}) DESC",
            [minimum],
        ).fetchall()
        if len(rows) < 2 or len(rows) > 50:
            return None
        group_stats = [
            {
                "group": str(row[0]), "count": int(row[1]), "minimum": self._number(row[2]),
                "maximum": self._number(row[3]), "median": self._number(row[4]),
                "mean": self._number(row[5]), "stdDev": self._number(row[6]), "color": COLORS[index % len(COLORS)],
            }
            for index, row in enumerate(rows)
        ]
        spread = self._number(connection.execute(
            f"SELECT stddev_samp({numeric}) FROM {relation} WHERE {group} IS NOT NULL AND {numeric} IS NOT NULL"
        ).fetchone()[0])
        mean_range = group_stats[0]["mean"] - group_stats[-1]["mean"]
        score = 0.0 if spread == 0 else min(1.0, abs(mean_range) / (spread * 4))
        density = self._density_plot(connection, relation, group_column, numeric_column, group_stats) if include_graphics else None
        return {
            "feature": feature["name"], "role": role, "type": feature["type"], "kind": kind,
            "score": score, "signal": f"effect {self._format(score)}",
            "detail": f"{group_stats[0]['group']} has the highest mean ({self._format(group_stats[0]['mean'])}), "
                      f"{group_stats[-1]['group']} the lowest ({self._format(group_stats[-1]['mean'])}).",
            "comparisonColumn": comparison_column, "groupStats": group_stats, "densityPlot": density,
            "numericStats": None, "scatterPlot": None, "categoricalStats": None,
        }

    def _density_plot(
        self,
        connection: duckdb.DuckDBPyConnection,
        relation: str,
        group_column: str,
        numeric_column: str,
        group_stats: list[dict[str, Any]],
        bins: int = 80,
    ) -> dict[str, Any] | None:
        low = min(item["minimum"] for item in group_stats)
        high = max(item["maximum"] for item in group_stats)
        if low == high:
            return None
        raw_range = high - low
        width = raw_range / bins
        group = self.store.identifier(group_column)
        numeric = self.store.identifier(numeric_column)
        allowed = {item["group"]: item for item in group_stats}
        rows = connection.execute(
            f"SELECT CAST({group} AS VARCHAR), least(?, floor(({numeric} - ?) / ?))::INTEGER, count(*) "
            f"FROM {relation} WHERE {group} IS NOT NULL AND {numeric} IS NOT NULL GROUP BY 1, 2",
            [bins - 1, low, width],
        ).fetchall()
        counts = {name: [0] * bins for name in allowed}
        for name, bin_index, count in rows:
            if str(name) in counts:
                counts[str(name)][int(bin_index)] = int(count)
        plot_low = low - raw_range * 0.08
        plot_high = high + raw_range * 0.08
        point_count = 80
        x_values = [
            plot_low + index * (plot_high - plot_low) / (point_count - 1)
            for index in range(point_count)
        ]
        series = []
        y_max = 0.0
        for name, values in counts.items():
            count = max(1, allowed[name]["count"])
            deviation = allowed[name]["stdDev"]
            fallback_bandwidth = max(raw_range / 18, 0.001)
            silverman_bandwidth = 1.06 * (deviation or fallback_bandwidth) * count ** -0.2
            bandwidth = max(silverman_bandwidth, fallback_bandwidth)
            coefficient = 1 / (count * bandwidth * math.sqrt(2 * math.pi))
            centers = [low + (index + 0.5) * width for index in range(bins)]
            points = []
            for x_value in x_values:
                kernel_sum = sum(
                    frequency * math.exp(-0.5 * ((x_value - centers[index]) / bandwidth) ** 2)
                    for index, frequency in enumerate(values)
                )
                points.append({"x": x_value, "y": coefficient * kernel_sum})
            y_max = max(y_max, *(point["y"] for point in points))
            series.append({"group": name, "color": allowed[name]["color"], "points": points})
        return {"xMin": plot_low, "xMax": plot_high, "yMax": y_max, "series": series}

    def _categorical_relation(
        self,
        connection: duckdb.DuckDBPyConnection,
        relation: str,
        feature: dict[str, str],
        role: str,
        comparison: str,
        include_graphics: bool,
    ) -> dict[str, Any] | None:
        feature_column = self.store.identifier(feature["name"])
        target_column = self.store.identifier(comparison)
        rows = connection.execute(
            f"SELECT CAST({feature_column} AS VARCHAR), CAST({target_column} AS VARCHAR), count(*) "
            f"FROM {relation} WHERE {feature_column} IS NOT NULL AND {target_column} IS NOT NULL GROUP BY 1, 2"
        ).fetchall()
        feature_values = self._ordered_values({str(row[0]) for row in rows}, role == "feature_ordinal")
        target_values = self._ordered_values({str(row[1]) for row in rows}, True)
        if len(feature_values) < 2 or len(target_values) < 2 or len(feature_values) > 50:
            return None
        cells = {(str(row[0]), str(row[1])): int(row[2]) for row in rows}
        feature_totals = {value: sum(cells.get((value, target), 0) for target in target_values) for value in feature_values}
        target_totals = {value: sum(cells.get((feature_value, value), 0) for feature_value in feature_values) for value in target_values}
        total = sum(feature_totals.values())
        chi_square = 0.0
        sparse = 0
        strongest = ("", "", 0.0, 0.0)
        table_rows = []
        for feature_value in feature_values:
            table_cells = []
            for target_value in target_values:
                observed = cells.get((feature_value, target_value), 0)
                expected = self._ratio(feature_totals[feature_value] * target_totals[target_value], total)
                if expected < 5:
                    sparse += 1
                residual = 0.0 if expected == 0 else (observed - expected) / math.sqrt(expected)
                lift = 0.0 if expected == 0 else observed / expected
                if abs(residual) > abs(strongest[3]):
                    strongest = (feature_value, target_value, lift, residual)
                if expected:
                    chi_square += (observed - expected) ** 2 / expected
                table_cells.append({
                    "comparisonValue": target_value, "count": observed,
                    "rowShare": self._ratio(observed, feature_totals[feature_value]),
                    "lift": lift, "residual": residual,
                })
            table_rows.append({"featureValue": feature_value, "count": feature_totals[feature_value], "cells": table_cells})
        degrees = (len(feature_values) - 1) * (len(target_values) - 1)
        denominator = total * max(1, min(len(feature_values) - 1, len(target_values) - 1))
        cramers_v = 0.0 if denominator == 0 else math.sqrt(chi_square / denominator)
        ordinal_trend = None
        if role == "feature_ordinal" and len(target_values) == 2:
            ordinal_trend = self._ordinal_trend(feature_values, target_values[-1], target_values, cells)
        return {
            "feature": feature["name"], "role": role, "type": feature["type"],
            "kind": "categorical association", "score": min(1.0, cramers_v),
            "signal": f"V {self._format(cramers_v)}",
            "detail": f"{feature['name']}={strongest[0]} has the strongest cell deviation for {comparison}={strongest[1]} "
                      f"(lift {self._format(strongest[2])}, residual {self._signed(strongest[3])}).",
            "comparisonColumn": comparison, "groupStats": [], "densityPlot": None,
            "numericStats": None, "scatterPlot": None,
            "categoricalStats": {
                "comparisonValues": target_values, "rows": table_rows, "chiSquare": chi_square,
                "degreesFreedom": degrees, "cramersV": cramers_v,
                "sparseCellShare": self._ratio(sparse, len(feature_values) * len(target_values)),
                "ordinalTrend": ordinal_trend, "graphicSummaries": include_graphics,
            },
        }

    def _segments(
        self,
        connection: duckdb.DuckDBPyConnection,
        relation: str,
        columns: list[dict[str, str]],
        profiles: list[dict[str, Any]],
        roles: dict[str, Any],
        target: str,
        target_type: str,
        max_features: int,
        include_graphics: bool,
    ) -> dict[str, Any] | None:
        profile_by_name = {profile["name"]: profile for profile in profiles}
        candidates = [
            column for column in columns
            if column["name"] != target
            and self._column_role(column["name"], column["type"], roles) not in {"ignored", "identifier"}
            and 2 <= profile_by_name[column["name"]]["unique"] <= 12
        ][:max_features]
        if len(candidates) < 2:
            return None
        target_column = self.store.identifier(target)
        valid_count = int(connection.execute(
            f"SELECT count(*) FROM {relation} WHERE {target_column} IS NOT NULL"
        ).fetchone()[0])
        minimum = max(5, math.floor(valid_count * 0.03))
        results: list[dict[str, Any]] = []
        evaluated = 0
        baseline_row = connection.execute(
            f"SELECT avg({target_column}), sum({target_column}), sum({target_column} * {target_column}) "
            f"FROM {relation} WHERE {target_column} IS NOT NULL"
        ).fetchone() if target_type == "continuous" else None
        target_counts = connection.execute(
            f"SELECT CAST({target_column} AS VARCHAR), count(*) FROM {relation} "
            f"WHERE {target_column} IS NOT NULL GROUP BY 1 ORDER BY 2"
        ).fetchall() if target_type != "continuous" else []
        focus_values = [str(row[0]) for row in (target_counts[:1] if len(target_counts) == 2 else target_counts)]
        target_count_map = {str(row[0]): int(row[1]) for row in target_counts}
        for left, right in combinations(candidates, 2):
            left_column = self.store.identifier(left["name"])
            right_column = self.store.identifier(right["name"])
            if target_type == "continuous":
                rows = connection.execute(
                    f"SELECT CAST({left_column} AS VARCHAR), CAST({right_column} AS VARCHAR), count(*), "
                    f"avg({target_column}), stddev_samp({target_column}), sum({target_column}), "
                    f"sum({target_column} * {target_column}) FROM {relation} "
                    f"WHERE {target_column} IS NOT NULL AND {left_column} IS NOT NULL AND {right_column} IS NOT NULL "
                    "GROUP BY 1, 2 HAVING count(*) >= ? AND count(*) < ?",
                    [minimum, valid_count],
                ).fetchall()
                evaluated += len(rows)
                for row in rows:
                    count = int(row[2])
                    rest_count = valid_count - count
                    if rest_count < 2:
                        continue
                    segment_sum = float(row[5])
                    segment_squares = float(row[6])
                    rest_sum = float(baseline_row[1]) - segment_sum
                    rest_squares = float(baseline_row[2]) - segment_squares
                    segment_deviation = self._deviation(count, segment_sum, segment_squares)
                    rest_deviation = self._deviation(rest_count, rest_sum, rest_squares)
                    pooled = math.sqrt(max(0.0, (((count - 1) * segment_deviation ** 2) + ((rest_count - 1) * rest_deviation ** 2)) / (valid_count - 2)))
                    segment_mean = float(row[3])
                    rest_mean = rest_sum / rest_count
                    effect = 0.0 if pooled == 0 else (segment_mean - rest_mean) / pooled
                    error = segment_deviation / math.sqrt(count)
                    support = self._ratio(count, valid_count)
                    results.append({
                        "columns": [left["name"], right["name"]],
                        "segment": f"{left['name']}={row[0]} / {right['name']}={row[1]}",
                        "count": count, "support": support, "targetValue": f"mean {target}",
                        "baseline": self._number(baseline_row[0]), "segmentValue": segment_mean,
                        "difference": segment_mean - float(baseline_row[0]), "relativeLift": None,
                        "confidenceInterval": [segment_mean - 1.96 * error, segment_mean + 1.96 * error],
                        "effectSize": effect, "score": support * effect, "format": "number",
                    })
                continue
            rows = connection.execute(
                f"SELECT CAST({left_column} AS VARCHAR), CAST({right_column} AS VARCHAR), "
                f"CAST({target_column} AS VARCHAR), count(*) FROM {relation} "
                f"WHERE {target_column} IS NOT NULL AND {left_column} IS NOT NULL AND {right_column} IS NOT NULL "
                "GROUP BY 1, 2, 3"
            ).fetchall()
            grouped: dict[tuple[str, str], dict[str, int]] = {}
            for left_value, right_value, target_value, count in rows:
                grouped.setdefault((str(left_value), str(right_value)), {})[str(target_value)] = int(count)
            for (left_value, right_value), counts in grouped.items():
                count = sum(counts.values())
                if count < minimum or count >= valid_count:
                    continue
                evaluated += 1
                for focus in focus_values:
                    successes = counts.get(focus, 0)
                    segment_rate = self._ratio(successes, count)
                    baseline = self._ratio(target_count_map.get(focus, 0), valid_count)
                    difference = segment_rate - baseline
                    support = self._ratio(count, valid_count)
                    results.append({
                        "columns": [left["name"], right["name"]],
                        "segment": f"{left['name']}={left_value} / {right['name']}={right_value}",
                        "count": count, "support": support, "targetValue": f"{target}={focus}",
                        "baseline": baseline, "segmentValue": segment_rate, "difference": difference,
                        "relativeLift": None if baseline == 0 else segment_rate / baseline,
                        "confidenceInterval": self._wilson(successes, count), "effectSize": None,
                        "score": support * difference, "format": "percent",
                    })
        results.sort(key=lambda item: abs(item["score"]), reverse=True)
        return {
            "targetColumn": target, "targetType": target_type,
            "candidateFeatures": [column["name"] for column in candidates],
            "pairsScanned": len(list(combinations(candidates, 2))), "segmentsEvaluated": evaluated,
            "minimumSegmentSize": minimum, "graphicSummaries": include_graphics, "results": results[:12],
        }

    def _quality_notes(
        self,
        profiles: list[dict[str, Any]],
        row_count: int,
        roles: dict[str, Any],
        target: str,
    ) -> list[str]:
        notes = []
        if not target:
            notes.append("No target role is set; target-feature profiling is waiting for metadata.")
        if not roles.get("dataset_roles"):
            notes.append("Dataset role is not set; mark training, validation, scoring, or monitoring intent in Data Roles.")
        high_missing = [profile for profile in profiles if profile["missingRate"] >= 0.3 and profile["role"] != "ignored"]
        if high_missing:
            notes.append(f"{len(high_missing)} columns have at least 30% missing values.")
        near_unique = [
            profile for profile in profiles
            if profile["uniqueRate"] >= 0.95 and profile["role"] not in {"identifier", "timestamp", "period_id", "ignored"}
        ]
        if near_unique:
            notes.append(f"{len(near_unique)} non-ID columns look near-unique; review roles before modeling.")
        constants = [profile for profile in profiles if profile["unique"] <= 1 and profile["count"] > 0]
        if constants:
            notes.append(f"{len(constants)} columns are constant in {row_count:,} profiled rows.")
        return notes

    def _roles(self, asset: DataAsset) -> dict[str, Any]:
        value = asset.metadata.get("data_roles") if isinstance(asset.metadata, dict) else None
        return value if isinstance(value, dict) else {}

    def _column_role(self, name: str, column_type: str, roles: dict[str, Any]) -> str:
        mapped = roles.get("column_roles") if isinstance(roles.get("column_roles"), dict) else {}
        if isinstance(mapped.get(name), str):
            return str(mapped[name])
        if roles.get("target_column") == name:
            return "target"
        if roles.get("entity_id_column") == name:
            return "identifier"
        if roles.get("timestamp_column") == name:
            return "timestamp"
        if roles.get("period_column") == name:
            return "period_id"
        return {"number": "feature_continuous", "boolean": "feature_categorical", "date": "timestamp"}.get(column_type, "feature_categorical")

    def _is_numeric_measure(self, column: dict[str, str], role: str, profile: dict[str, Any]) -> bool:
        if column["type"] != "number":
            return False
        if role in {"feature_categorical", "feature_ordinal", "boolean"}:
            return False
        return profile["unique"] > 12

    def _ordinal_trend(
        self,
        feature_values: list[str],
        focus: str,
        target_values: list[str],
        cells: dict[tuple[str, str], int],
    ) -> dict[str, Any] | None:
        observations = []
        for rank, feature in enumerate(feature_values, start=1):
            for target in target_values:
                observations.append((float(rank), 1.0 if target == focus else 0.0, cells.get((feature, target), 0)))
        total = sum(weight for _, _, weight in observations)
        if total < 3:
            return None
        mean_x = sum(x * weight for x, _, weight in observations) / total
        mean_y = sum(y * weight for _, y, weight in observations) / total
        covariance = sum((x - mean_x) * (y - mean_y) * weight for x, y, weight in observations)
        variance_x = sum((x - mean_x) ** 2 * weight for x, _, weight in observations)
        variance_y = sum((y - mean_y) ** 2 * weight for _, y, weight in observations)
        correlation = 0.0 if variance_x == 0 or variance_y == 0 else covariance / math.sqrt(variance_x * variance_y)
        numeric_order = all(self._is_float(value) for value in feature_values)
        return {
            "focusValue": focus, "spearman": correlation,
            "orderBasis": "numeric ascending" if numeric_order else "lexicographic category order",
        }

    def _ordered_values(self, values: set[str], numeric_when_possible: bool) -> list[str]:
        if numeric_when_possible and values and all(self._is_float(value) for value in values):
            return sorted(values, key=float)
        return sorted(values)

    def _fetch_dicts(
        self,
        connection: duckdb.DuckDBPyConnection,
        sql: str,
        parameters: list[Any] | None = None,
    ) -> list[dict[str, Any]]:
        cursor = connection.execute(sql, parameters or [])
        names = [str(item[0]) for item in cursor.description or []]
        return [
            {name: self._json_value(value) for name, value in zip(names, row, strict=False)}
            for row in cursor.fetchall()
        ]

    def _frontend_type(self, value: str) -> str:
        normalized = value.upper()
        if any(token in normalized for token in ("INT", "DECIMAL", "DOUBLE", "FLOAT", "REAL", "HUGEINT")):
            return "number"
        if "BOOL" in normalized:
            return "boolean"
        if any(token in normalized for token in ("DATE", "TIME")):
            return "date"
        return "text"

    def _json_value(self, value: Any) -> Any:
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, datetime | date):
            return value.isoformat()
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value

    def _number(self, value: Any) -> float:
        if value is None:
            return 0.0
        number = float(value)
        return round(number, 6) if math.isfinite(number) else 0.0

    def _ratio(self, numerator: Any, denominator: Any) -> float:
        return 0.0 if not denominator else float(numerator) / float(denominator)

    def _format(self, value: float) -> str:
        return f"{value:.3f}".rstrip("0").rstrip(".")

    def _signed(self, value: float) -> str:
        return f"{'+' if value >= 0 else ''}{self._format(value)}"

    def _is_float(self, value: str) -> bool:
        try:
            float(value)
        except ValueError:
            return False
        return True

    def _deviation(self, count: int, total: float, squares: float) -> float:
        if count < 2:
            return 0.0
        return math.sqrt(max(0.0, (squares - total ** 2 / count) / (count - 1)))

    def _wilson(self, successes: int, trials: int) -> list[float]:
        if trials == 0:
            return [0.0, 0.0]
        z = 1.96
        proportion = successes / trials
        denominator = 1 + z ** 2 / trials
        center = (proportion + z ** 2 / (2 * trials)) / denominator
        margin = z / denominator * math.sqrt(proportion * (1 - proportion) / trials + z ** 2 / (4 * trials ** 2))
        return [max(0.0, center - margin), min(1.0, center + margin)]
