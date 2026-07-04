from __future__ import annotations

from datetime import datetime, timezone
from math import sqrt
from typing import Any

import duckdb

from app.modules.pipelines.runtime import identifier, json_safe, sql_literal


class ModelEvaluationSnapshotBuilder:
    """Build a bounded report contract from full-scope prediction relations."""

    contract_version = "1.0"
    max_reported_classes = 100
    max_confusion_classes = 30
    curve_bins = 100
    histogram_bins = 20
    scatter_limit = 500

    def build(
        self,
        connection: duckdb.DuckDBPyConnection,
        relation_sql: str,
        *,
        problem_type: str,
        target_column: str,
        prediction_column: str,
        score_contract: dict[str, Any],
    ) -> dict[str, Any]:
        if not target_column:
            return {
                "contract_version": self.contract_version,
                "kind": "model_performance",
                "status": "target_unavailable",
                "problem_type": problem_type,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "data_scope": {
                    "mode": "full",
                    "evaluated_row_count": 0,
                    "excluded_row_count": 0,
                },
                "metrics": [],
                "warnings": ["Assign a target column in Scoring to calculate test performance."],
                "monitoring": {
                    "baseline_eligible": False,
                    "requires_actuals": True,
                },
            }

        target = identifier(target_column)
        prediction = identifier(prediction_column)
        relation = f"({relation_sql}) AS evaluation_source"
        total, evaluated = connection.execute(
            f"SELECT count(*), count(*) FILTER (WHERE {target} IS NOT NULL AND {prediction} IS NOT NULL) "
            f"FROM {relation}"
        ).fetchone()
        base = {
            "contract_version": self.contract_version,
            "kind": "model_performance",
            "status": "available",
            "problem_type": problem_type,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_scope": {
                "mode": "full",
                "scanned_row_count": int(total),
                "evaluated_row_count": int(evaluated),
                "excluded_row_count": int(total - evaluated),
            },
            "columns": {
                "target": target_column,
                "prediction": prediction_column,
                "score": score_contract.get("prediction_score_column"),
            },
            "warnings": [],
            "monitoring": {
                "baseline_eligible": True,
                "requires_actuals": True,
                "comparison_dimensions": ["metrics", "prediction_distribution"],
            },
        }
        if evaluated == 0:
            return {
                **base,
                "status": "target_unavailable",
                "metrics": [],
                "warnings": ["No rows contain both target and prediction values."],
                "monitoring": {**base["monitoring"], "baseline_eligible": False},
            }
        if problem_type == "regression":
            return {**base, **self._regression(connection, relation, target, prediction)}
        return {
            **base,
            **self._classification(
                connection,
                relation,
                target,
                prediction,
                score_contract,
            ),
        }

    def _classification(
        self,
        connection: duckdb.DuckDBPyConnection,
        relation_sql: str,
        target: str,
        prediction: str,
        score_contract: dict[str, Any],
    ) -> dict[str, Any]:
        rows = connection.execute(
            f"""
            WITH base AS (
                SELECT {target} AS actual, {prediction} AS predicted
                FROM {relation_sql}
                WHERE {target} IS NOT NULL AND {prediction} IS NOT NULL
            ),
            labels AS (
                SELECT actual AS label FROM base
                UNION
                SELECT predicted AS label FROM base
            ),
            actuals AS (
                SELECT actual AS label, count(*) AS actual_count
                FROM base GROUP BY actual
            ),
            predictions AS (
                SELECT predicted AS label, count(*) AS predicted_count
                FROM base GROUP BY predicted
            ),
            correct AS (
                SELECT actual AS label, count(*) AS true_positive
                FROM base WHERE actual = predicted GROUP BY actual
            )
            SELECT labels.label,
                   coalesce(actual_count, 0),
                   coalesce(predicted_count, 0),
                   coalesce(true_positive, 0)
            FROM labels
            LEFT JOIN actuals USING (label)
            LEFT JOIN predictions USING (label)
            LEFT JOIN correct USING (label)
            ORDER BY coalesce(actual_count, 0) DESC, cast(labels.label AS VARCHAR)
            """
        ).fetchall()
        total = sum(int(row[1]) for row in rows)
        correct = sum(int(row[3]) for row in rows)
        class_metrics = []
        for label, support, predicted_count, true_positive in rows:
            precision = self._safe_div(true_positive, predicted_count)
            recall = self._safe_div(true_positive, support)
            class_metrics.append({
                "label": json_safe(label),
                "support": int(support),
                "predicted_count": int(predicted_count),
                "precision": precision,
                "recall": recall,
                "f1": self._safe_div(2 * precision * recall, precision + recall),
            })
        accuracy = self._safe_div(correct, total)
        macro_precision = self._mean([item["precision"] for item in class_metrics])
        macro_recall = self._mean([item["recall"] for item in class_metrics])
        macro_f1 = self._mean([item["f1"] for item in class_metrics])
        weighted_f1 = self._safe_div(
            sum(item["f1"] * item["support"] for item in class_metrics),
            total,
        )
        metrics = [
            self._metric("accuracy", "Accuracy", accuracy, "higher"),
            self._metric("balanced_accuracy", "Balanced accuracy", macro_recall, "higher"),
            self._metric("precision_macro", "Macro precision", macro_precision, "higher"),
            self._metric("recall_macro", "Macro recall", macro_recall, "higher"),
            self._metric("f1_macro", "Macro F1", macro_f1, "higher"),
            self._metric("f1_weighted", "Weighted F1", weighted_f1, "higher"),
        ]
        labels = [item["label"] for item in class_metrics]
        confusion = self._confusion_matrix(
            connection,
            relation_sql,
            target,
            prediction,
            labels,
        )
        warnings: list[str] = []
        if len(class_metrics) > self.max_reported_classes:
            warnings.append(
                f"Per-class table is limited to {self.max_reported_classes} of {len(class_metrics)} classes."
            )
        result: dict[str, Any] = {
            "metrics": metrics,
            "class_metrics": class_metrics[: self.max_reported_classes],
            "class_count": len(class_metrics),
            "confusion_matrix": confusion,
            "curves": {},
            "distributions": {},
            "warnings": warnings,
            "monitoring": {
                "baseline_eligible": True,
                "requires_actuals": True,
                "comparison_dimensions": [
                    "metrics",
                    "class_support",
                    "prediction_distribution",
                    "confusion_matrix",
                ],
            },
        }
        if len(labels) == 2 and score_contract.get("prediction_score_column"):
            positive = score_contract.get("positive_class", labels[-1])
            score = identifier(str(score_contract["prediction_score_column"]))
            binary = self._binary_score_report(
                connection,
                relation_sql,
                target,
                score,
                positive,
                probability=bool(score_contract.get("probability_available")),
            )
            result["metrics"].extend(binary["metrics"])
            result["curves"] = binary["curves"]
            result["distributions"] = binary["distributions"]
            result["warnings"].extend(binary["warnings"])
            result["positive_class"] = json_safe(positive)
            result["monitoring"]["comparison_dimensions"].extend([
                "score_distribution",
                "calibration",
            ])
        return result

    def _binary_score_report(
        self,
        connection: duckdb.DuckDBPyConnection,
        relation_sql: str,
        target: str,
        score: str,
        positive: Any,
        *,
        probability: bool,
    ) -> dict[str, Any]:
        positive_sql = sql_literal(positive)
        base = (
            f"SELECT cast({score} AS DOUBLE) AS score, "
            f"CASE WHEN {target} = {positive_sql} THEN 1 ELSE 0 END AS positive "
            f"FROM {relation_sql} WHERE {target} IS NOT NULL AND {score} IS NOT NULL"
        )
        auc, average_precision, positives, negatives = connection.execute(
            f"""
            WITH score_groups AS (
                SELECT score,
                       sum(positive)::DOUBLE AS positives,
                       sum(1 - positive)::DOUBLE AS negatives
                FROM ({base}) GROUP BY score
            ),
            ascending AS (
                SELECT *,
                       coalesce(sum(negatives) OVER (
                           ORDER BY score ASC ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                       ), 0) AS negatives_before
                FROM score_groups
            ),
            descending AS (
                SELECT *,
                       sum(positives) OVER (ORDER BY score DESC) AS cumulative_positives,
                       sum(negatives) OVER (ORDER BY score DESC) AS cumulative_negatives
                FROM score_groups
            ),
            totals AS (
                SELECT sum(positives) AS positive_total, sum(negatives) AS negative_total
                FROM score_groups
            )
            SELECT
                sum(a.positives * (a.negatives_before + 0.5 * a.negatives))
                    / nullif(t.positive_total * t.negative_total, 0) AS roc_auc,
                sum(d.positives / nullif(t.positive_total, 0)
                    * d.cumulative_positives
                    / nullif(d.cumulative_positives + d.cumulative_negatives, 0)) AS average_precision,
                t.positive_total,
                t.negative_total
            FROM ascending a
            JOIN descending d USING (score, positives, negatives)
            CROSS JOIN totals t
            GROUP BY t.positive_total, t.negative_total
            """
        ).fetchone()
        curve_rows = connection.execute(
            f"""
            WITH score_groups AS (
                SELECT score,
                       sum(positive)::DOUBLE AS positives,
                       sum(1 - positive)::DOUBLE AS negatives
                FROM ({base})
                GROUP BY score
            ),
            ranked AS (
                SELECT *,
                       sum(positives + negatives) OVER (
                           ORDER BY score DESC ROWS UNBOUNDED PRECEDING
                       ) AS cumulative_rows,
                       sum(positives + negatives) OVER () AS total_rows
                FROM score_groups
            ),
            bucketed AS (
                SELECT *,
                       greatest(1, ceil(cumulative_rows * {self.curve_bins}
                           / nullif(total_rows, 0)))::INTEGER AS bucket
                FROM ranked
            ),
            grouped AS (
                SELECT bucket, min(score) AS threshold,
                       sum(positives)::DOUBLE AS positives,
                       sum(negatives)::DOUBLE AS negatives
                FROM bucketed GROUP BY bucket
            ),
            cumulative AS (
                SELECT bucket, threshold,
                       sum(positives) OVER (ORDER BY bucket) AS true_positives,
                       sum(negatives) OVER (ORDER BY bucket) AS false_positives,
                       sum(positives) OVER () AS positive_total,
                       sum(negatives) OVER () AS negative_total
                FROM grouped
            )
            SELECT threshold,
                   false_positives / nullif(negative_total, 0) AS fpr,
                   true_positives / nullif(positive_total, 0) AS tpr,
                   true_positives / nullif(true_positives + false_positives, 0) AS precision,
                   true_positives / nullif(positive_total, 0) AS recall
            FROM cumulative ORDER BY bucket
            """
        ).fetchall()
        roc_points = [{"x": 0.0, "y": 0.0, "threshold": None}]
        pr_points = [{"x": 0.0, "y": 1.0, "threshold": None}]
        for threshold, fpr, tpr, precision, recall in curve_rows:
            roc_points.append({
                "x": float(fpr or 0),
                "y": float(tpr or 0),
                "threshold": float(threshold),
            })
            pr_points.append({
                "x": float(recall or 0),
                "y": float(precision or 0),
                "threshold": float(threshold),
            })
        score_distribution = self._score_distribution(
            connection,
            base,
            probability=probability,
        )
        metrics = [
            self._metric("roc_auc", "ROC AUC", float(auc or 0), "higher"),
            self._metric(
                "average_precision",
                "Average precision",
                float(average_precision or 0),
                "higher",
            ),
        ]
        curves: dict[str, Any] = {
            "roc": {
                "x_label": "False positive rate",
                "y_label": "True positive rate",
                "points": roc_points,
                "rendering": "full-data quantile-binned curve",
            },
            "precision_recall": {
                "x_label": "Recall",
                "y_label": "Precision",
                "points": pr_points,
                "rendering": "full-data quantile-binned curve",
            },
        }
        warnings = [
            f"ROC and precision-recall charts are rendered with at most {self.curve_bins} score bins; "
            "their headline metrics use the full score distribution."
        ]
        if len(curve_rows) == 1:
            warnings.append(
                "All evaluated rows have the same score; ranking curves collapse to "
                "a single threshold and ROC AUC is 0.5."
            )
        if probability:
            brier, log_loss = connection.execute(
                f"""
                SELECT avg(power(greatest(0.0, least(1.0, score)) - positive, 2)),
                       avg(-(positive * ln(greatest(1e-15, least(1 - 1e-15, score)))
                           + (1 - positive) * ln(greatest(1e-15, least(1 - 1e-15, 1 - score)))))
                FROM ({base})
                """
            ).fetchone()
            metrics.extend([
                self._metric("brier_score", "Brier score", float(brier), "lower", unit="number"),
                self._metric("log_loss", "Log loss", float(log_loss), "lower", unit="number"),
            ])
            calibration = connection.execute(
                f"""
                WITH binned AS (
                    SELECT least(9, greatest(0, floor(score * 10)::INTEGER)) AS bin,
                           score, positive
                    FROM ({base})
                    WHERE score BETWEEN 0 AND 1
                )
                SELECT bin, avg(score), avg(positive), count(*)
                FROM binned GROUP BY bin ORDER BY bin
                """
            ).fetchall()
            curves["calibration"] = {
                "x_label": "Mean predicted probability",
                "y_label": "Observed positive rate",
                "points": [
                    {"x": float(mean_score), "y": float(observed), "count": int(count)}
                    for _, mean_score, observed, count in calibration
                ],
                "rendering": "10 equal-width probability bins over full data",
            }
        return {
            "metrics": metrics,
            "curves": curves,
            "distributions": {"score_by_actual": score_distribution},
            "warnings": warnings,
            "positive_count": int(positives or 0),
            "negative_count": int(negatives or 0),
        }

    def _regression(
        self,
        connection: duckdb.DuckDBPyConnection,
        relation_sql: str,
        target: str,
        prediction: str,
    ) -> dict[str, Any]:
        row = connection.execute(
            f"""
            WITH base AS (
                SELECT cast({target} AS DOUBLE) AS actual,
                       cast({prediction} AS DOUBLE) AS predicted,
                       cast({prediction} AS DOUBLE) - cast({target} AS DOUBLE) AS residual
                FROM {relation_sql}
                WHERE {target} IS NOT NULL AND {prediction} IS NOT NULL
            )
            SELECT count(*), avg(abs(residual)), avg(residual * residual),
                   1 - sum(residual * residual)
                       / nullif(sum(power(actual - (SELECT avg(actual) FROM base), 2)), 0),
                   avg(residual), stddev_pop(residual),
                   quantile_cont(residual, 0.05), quantile_cont(residual, 0.5),
                   quantile_cont(residual, 0.95),
                   avg(abs(residual / nullif(actual, 0))) FILTER (WHERE actual != 0),
                   count(*) FILTER (WHERE actual != 0)
            FROM base
            """
        ).fetchone()
        count, mae, mse, r2, mean_residual, residual_std, p05, median, p95, mape, mape_count = row
        metrics = [
            self._metric("mae", "MAE", float(mae), "lower", unit="number"),
            self._metric("rmse", "RMSE", sqrt(float(mse)), "lower", unit="number"),
            self._metric("r2", "R²", float(r2 or 0), "higher", unit="number"),
            self._metric(
                "mean_residual",
                "Mean residual",
                float(mean_residual),
                "target_zero",
                unit="number",
            ),
        ]
        warnings = [
            f"Actual-vs-predicted chart contains a deterministic rendering sample of at most {self.scatter_limit} rows; "
            "metrics and residual histogram use the full evaluated data."
        ]
        if mape is not None:
            metrics.append(self._metric("mape", "MAPE", float(mape), "lower", unit="ratio"))
            if int(mape_count) < int(count):
                warnings.append(
                    f"MAPE excludes {int(count) - int(mape_count)} rows with zero actual value."
                )
        histogram = self._residual_histogram(connection, relation_sql, target, prediction)
        scatter = connection.execute(
            f"""
            SELECT cast({target} AS DOUBLE), cast({prediction} AS DOUBLE)
            FROM {relation_sql}
            WHERE {target} IS NOT NULL AND {prediction} IS NOT NULL
            USING SAMPLE reservoir({self.scatter_limit} ROWS) REPEATABLE (42)
            """
        ).fetchall()
        return {
            "metrics": metrics,
            "residuals": {
                "summary": {
                    "mean": float(mean_residual),
                    "standard_deviation": float(residual_std or 0),
                    "p05": float(p05),
                    "median": float(median),
                    "p95": float(p95),
                },
                "histogram": histogram,
                "actual_vs_predicted": {
                    "points": [{"actual": float(a), "predicted": float(p)} for a, p in scatter],
                    "rendering": f"reservoir sample, maximum {self.scatter_limit} rows",
                },
            },
            "warnings": warnings,
            "monitoring": {
                "baseline_eligible": True,
                "requires_actuals": True,
                "comparison_dimensions": [
                    "metrics",
                    "prediction_distribution",
                    "residual_distribution",
                ],
            },
        }

    def _confusion_matrix(
        self,
        connection: duckdb.DuckDBPyConnection,
        relation_sql: str,
        target: str,
        prediction: str,
        labels: list[Any],
    ) -> dict[str, Any]:
        shown = labels[: self.max_confusion_classes]
        if not shown:
            return {"labels": [], "values": [], "truncated": False}
        clauses = ", ".join(sql_literal(label) for label in shown)
        rows = connection.execute(
            f"""
            SELECT {target}, {prediction}, count(*)
            FROM {relation_sql}
            WHERE {target} IN ({clauses}) AND {prediction} IN ({clauses})
            GROUP BY {target}, {prediction}
            """
        ).fetchall()
        index = {str(label): idx for idx, label in enumerate(shown)}
        values = [[0 for _ in shown] for _ in shown]
        for actual, predicted, count in rows:
            values[index[str(json_safe(actual))]][index[str(json_safe(predicted))]] = int(count)
        return {
            "labels": shown,
            "values": values,
            "truncated": len(labels) > len(shown),
            "total_class_count": len(labels),
        }

    def _score_distribution(
        self,
        connection: duckdb.DuckDBPyConnection,
        base_sql: str,
        *,
        probability: bool,
    ) -> list[dict[str, Any]]:
        minimum, maximum = connection.execute(
            f"SELECT min(score), max(score) FROM ({base_sql})"
        ).fetchone()
        if minimum is None or maximum is None:
            return []
        minimum = 0.0 if probability else float(minimum)
        maximum = 1.0 if probability else float(maximum)
        width = (maximum - minimum) / self.histogram_bins if maximum > minimum else 1.0
        rows = connection.execute(
            f"""
            SELECT least({self.histogram_bins - 1}, greatest(0,
                       floor((score - {minimum}) / {width})::INTEGER)) AS bin,
                   positive,
                   count(*)
            FROM ({base_sql})
            GROUP BY bin, positive ORDER BY bin, positive
            """
        ).fetchall()
        counts = {(int(bin_index), int(positive)): int(count) for bin_index, positive, count in rows}
        return [
            {
                "lower": minimum + index * width,
                "upper": minimum + (index + 1) * width,
                "negative_count": counts.get((index, 0), 0),
                "positive_count": counts.get((index, 1), 0),
            }
            for index in range(self.histogram_bins)
        ]

    def _residual_histogram(
        self,
        connection: duckdb.DuckDBPyConnection,
        relation_sql: str,
        target: str,
        prediction: str,
    ) -> list[dict[str, Any]]:
        residual = f"cast({prediction} AS DOUBLE) - cast({target} AS DOUBLE)"
        minimum, maximum = connection.execute(
            f"SELECT min({residual}), max({residual}) FROM {relation_sql} "
            f"WHERE {target} IS NOT NULL AND {prediction} IS NOT NULL"
        ).fetchone()
        minimum, maximum = float(minimum), float(maximum)
        width = (maximum - minimum) / self.histogram_bins if maximum > minimum else 1.0
        rows = connection.execute(
            f"""
            SELECT least({self.histogram_bins - 1}, greatest(0,
                       floor(({residual} - {minimum}) / {width})::INTEGER)) AS bin,
                   count(*)
            FROM {relation_sql}
            WHERE {target} IS NOT NULL AND {prediction} IS NOT NULL
            GROUP BY bin ORDER BY bin
            """
        ).fetchall()
        counts = {int(index): int(count) for index, count in rows}
        return [
            {
                "lower": minimum + index * width,
                "upper": minimum + (index + 1) * width,
                "count": counts.get(index, 0),
            }
            for index in range(self.histogram_bins)
        ]

    @staticmethod
    def _metric(
        metric_id: str,
        label: str,
        value: float,
        direction: str,
        *,
        unit: str = "ratio",
    ) -> dict[str, Any]:
        return {
            "id": metric_id,
            "label": label,
            "value": value,
            "direction": direction,
            "unit": unit,
        }

    @staticmethod
    def _safe_div(numerator: float, denominator: float) -> float:
        return float(numerator / denominator) if denominator else 0.0

    @staticmethod
    def _mean(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0
