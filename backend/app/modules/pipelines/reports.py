from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field
from sklearn.inspection import permutation_importance

from app.modules.pipelines.runtime import SourceRelation, json_safe
from app.shared.sql_security import identifier


class ReportScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["full", "sample"]
    row_count: int = Field(ge=0)
    sampled: bool = False
    sample_size: int = Field(default=0, ge=0)
    sampling_method: str = ""
    seed: int | None = None


class ReportContract(BaseModel):
    """Shared immutable envelope for lifecycle reports.

    Monitoring keeps its current implementation for now, but future monitoring
    reports can use the same envelope without pretending to be training reports.
    """

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["1.0"] = "1.0"
    report_type: Literal[
        "training_evaluation_report",
        "monitoring_performance_report",
    ]
    name: str
    created_at: str
    data_scope: ReportScope
    sections: dict[str, Any] = Field(default_factory=dict)
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TrainingReportBuilder:
    """Build a bounded, auditable report for a selected fitted estimator."""

    explanation_rows = 256
    explanation_background_rows = 64
    max_explanation_features = 200
    returned_importances = 100

    def build(
        self,
        connection: Any,
        estimator: Any,
        evaluation: SourceRelation,
        *,
        feature_columns: list[str],
        target_column: str,
        problem_type: str,
        model_name: str,
        algorithm: str,
        metrics: dict[str, Any],
        model_parameters: dict[str, Any],
        random_seed: int,
        auto_feature_engineering: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        row_count = self._row_count(connection, evaluation)
        diagnostics: list[dict[str, Any]] = []
        warnings: list[str] = []
        explainability = self._explain(
            connection,
            estimator,
            evaluation,
            feature_columns=feature_columns,
            target_column=target_column,
            problem_type=problem_type,
            random_seed=random_seed,
        )
        if explainability.get("status") != "completed":
            warnings.append(str(explainability.get("reason") or "Explainability was unavailable"))
        optimization = dict(metrics.get("optimization") or {})
        if optimization.get("failed_trial_count"):
            diagnostics.append({
                "severity": "warning",
                "code": "failed_trials",
                "message": (
                    f"{optimization['failed_trial_count']} model-search trial(s) failed; "
                    "successful candidates remain comparable."
                ),
            })
        report = ReportContract(
            report_type="training_evaluation_report",
            name=f"{model_name} training report",
            created_at=datetime.now(timezone.utc).isoformat(),
            data_scope=ReportScope(mode="full", row_count=row_count),
            sections={
                "summary": {
                    "model_name": model_name,
                    "algorithm": algorithm,
                    "problem_type": problem_type,
                    "target_column": target_column,
                    "feature_count": len(feature_columns),
                    "evaluated_row_count": int(metrics.get("evaluated_row_count") or row_count),
                },
                "metrics": metrics,
                "validation": {
                    "strategy": optimization.get("validation_strategy", "training"),
                    "primary_metric": optimization.get("primary_metric", ""),
                    "best_score": optimization.get("best_score"),
                    "fold_count": optimization.get("cv_folds", optimization.get("fold_count")),
                },
                "search": optimization,
                "feature_engineering": dict(auto_feature_engineering or {}),
                "model_parameters": model_parameters,
                "explainability": explainability,
            },
            diagnostics=diagnostics,
            warnings=warnings,
        )
        return report.model_dump(mode="json")

    def _explain(
        self,
        connection: Any,
        estimator: Any,
        relation: SourceRelation,
        *,
        feature_columns: list[str],
        target_column: str,
        problem_type: str,
        random_seed: int,
    ) -> dict[str, Any]:
        scope = {
            "mode": "sample",
            "sampled": True,
            "sample_size": 0,
            "sampling_method": "deterministic_hash_or_stable_prefix",
            "seed": random_seed,
        }
        if len(feature_columns) > self.max_explanation_features:
            return {
                "status": "skipped",
                "reason": (
                    f"Explainability is bounded to {self.max_explanation_features} features; "
                    f"the winner resolved {len(feature_columns)}."
                ),
                "scope": scope,
            }
        try:
            x, y = self._sample(
                connection,
                relation,
                feature_columns,
                target_column,
                random_seed,
            )
            fitted = getattr(estimator, "estimator", estimator)
            classes = np.asarray(getattr(fitted, "classes_", np.empty(0)))
            if len(classes):
                y = y.astype(classes.dtype, copy=False)
            elif problem_type == "regression":
                y = y.astype(np.float64, copy=False)
            scope["sample_size"] = int(len(x))
            if not len(x):
                return {"status": "skipped", "reason": "Evaluation relation is empty", "scope": scope}
            permutation = permutation_importance(
                estimator,
                x,
                y,
                n_repeats=3,
                random_state=random_seed,
                n_jobs=1,
            )
            permutation_rows = self._ranked(
                feature_columns,
                permutation.importances_mean,
                "mean_importance",
                secondary=permutation.importances_std,
            )
            shap_payload = self._shap(estimator, x, feature_columns)
            return {
                "status": "completed",
                "scope": scope,
                "permutation_importance": permutation_rows,
                "shap": shap_payload,
                "notes": [
                    "Model metrics use the full declared evaluation scope.",
                    "Explainability uses a bounded deterministic sample and is not a full-scope metric.",
                ],
            }
        except Exception as exc:  # Explainability must not invalidate a fitted model.
            return {
                "status": "partial",
                "reason": f"Explainability failed safely: {type(exc).__name__}: {exc}",
                "scope": scope,
                "permutation_importance": [],
                "shap": {"status": "unavailable", "values": []},
            }

    def _sample(
        self,
        connection: Any,
        relation: SourceRelation,
        features: list[str],
        target: str,
        seed: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        selected = [*features, target]
        manifest = relation.metadata.get("feature_manifest")
        row_id = next((
            str(item.get("name"))
            for item in manifest or []
            if item.get("role") == "row_id" and item.get("name")
        ), "")
        order = (
            f"ORDER BY hash(CAST({identifier(row_id)} AS VARCHAR) || '|{seed}')"
            if row_id else "ORDER BY " + ", ".join(identifier(item) for item in selected)
        )
        rows = connection.execute(
            f"SELECT {', '.join(identifier(item) for item in selected)} "
            f"FROM {relation.sql} WHERE {identifier(target)} IS NOT NULL "
            f"{order} LIMIT {self.explanation_rows}"
        ).fetchall()
        values = np.asarray(rows, dtype=object)
        if not len(values):
            return np.empty((0, len(features))), np.empty(0)
        return values[:, :-1].astype(np.float64), values[:, -1]

    def _shap(
        self,
        estimator: Any,
        x: np.ndarray,
        features: list[str],
    ) -> dict[str, Any]:
        try:
            import shap
        except ImportError:
            return {
                "status": "unavailable",
                "reason": "The optional SHAP runtime is not installed",
                "values": [],
            }
        fitted = getattr(estimator, "estimator", estimator)
        background = x[: min(len(x), self.explanation_background_rows)]
        if hasattr(fitted, "feature_importances_"):
            explainer = shap.TreeExplainer(fitted)
            values = explainer.shap_values(x)
            explainer_name = "TreeExplainer"
        elif hasattr(fitted, "coef_"):
            explainer = shap.LinearExplainer(fitted, background)
            values = explainer.shap_values(x)
            explainer_name = "LinearExplainer"
        else:
            return {
                "status": "unsupported",
                "reason": "Winner has no bounded native SHAP explainer; permutation importance is available",
                "values": [],
            }
        array = np.asarray(values, dtype=float)
        if array.ndim == 3:
            importance = np.mean(np.abs(array), axis=(0, 2))
        elif array.ndim == 2:
            importance = np.mean(np.abs(array), axis=0)
        elif array.ndim == 1:
            importance = np.abs(array)
        else:
            importance = np.mean(np.abs(array), axis=tuple(range(array.ndim - 1)))
        return {
            "status": "completed",
            "explainer": explainer_name,
            "values": self._ranked(features, importance, "mean_absolute_shap"),
        }

    def _ranked(
        self,
        features: list[str],
        values: Any,
        value_key: str,
        *,
        secondary: Any | None = None,
    ) -> list[dict[str, Any]]:
        main = np.asarray(values, dtype=float).reshape(-1)
        extra = np.asarray(secondary, dtype=float).reshape(-1) if secondary is not None else None
        rows = [
            {
                "feature": feature,
                value_key: float(main[index]),
                **({"std": float(extra[index])} if extra is not None else {}),
            }
            for index, feature in enumerate(features[: len(main)])
        ]
        return sorted(rows, key=lambda item: (-abs(float(item[value_key])), item["feature"]))[
            : self.returned_importances
        ]

    @staticmethod
    def _row_count(connection: Any, relation: SourceRelation) -> int:
        return relation.row_count if relation.row_count >= 0 else int(
            connection.execute(f"SELECT count(*) FROM {relation.sql}").fetchone()[0]
        )
