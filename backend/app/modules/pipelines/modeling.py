from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

import duckdb
import joblib
import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.pipelines.model_evaluation import ModelEvaluationSnapshotBuilder
from app.modules.pipelines.model_training import (
    ModelOptimizationEngine,
    OptimizationScoreCallback,
    OptimizationMode,
    ValidationStrategy,
)
from app.modules.pipelines.modeling_catalog import (
    ProblemType,
    algorithm_spec,
    build_estimator,
    validate_algorithm_parameters,
)
from app.modules.pipelines.runtime import SourceRelation, json_safe, safe_filename, sql_literal
from app.shared.duckdb_runtime import configured_duckdb_connection, write_parquet_atomic
from app.shared.sql_security import identifier


class OptimizationDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: OptimizationMode = "single"
    validation_strategy: ValidationStrategy = "auto"
    primary_metric: str = Field(default="auto", min_length=1, max_length=100)
    cv_folds: int = Field(default=5, ge=2, le=20)
    max_trials: int = Field(default=30, ge=1, le=100_000)
    timeout_seconds: int = Field(default=3600, ge=10, le=604_800)
    candidate_algorithms: list[str] = Field(default_factory=list, max_length=100)
    search_space: dict[str, dict[str, Any]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_candidates(self) -> "OptimizationDefinition":
        if len(self.candidate_algorithms) != len(set(self.candidate_algorithms)):
            raise ValueError("AutoML candidate algorithms must be unique")
        if self.mode != "grid_search" and self.max_trials > 1000:
            raise ValueError(
                "Random search, Optuna and AutoML are limited to 1000 trials; "
                "only grid search can evaluate up to 100000 deterministic combinations"
            )
        return self


class TrainingResourceLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_memory_mb: int = Field(default=2048, ge=128, le=262_144)
    max_parallel_jobs: int = Field(default=1, ge=1, le=64)


class AutoFeatureEngineeringDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    strategy: Literal["balanced"] = "balanced"
    joint_search_enabled: bool = True
    max_recipe_candidates: int = Field(default=3, ge=1, le=3)
    row_id_column: str = Field(default="", max_length=255)
    excluded_columns: list[str] = Field(default_factory=list, max_length=500)
    validation_size: float = Field(default=0.2, gt=0, lt=0.5)
    numeric_scaling: Literal["none", "standard", "minmax", "robust"] = "standard"
    add_missing_indicators: bool = True
    include_datetime_features: bool = True
    detect_identifier_columns: bool = True
    min_category_frequency: int = Field(default=2, ge=1, le=1_000_000)
    max_one_hot_categories: int = Field(default=32, ge=2, le=500)
    max_frequency_categories: int = Field(default=500, ge=2, le=500)

    @model_validator(mode="after")
    def validate_columns_and_bounds(self) -> "AutoFeatureEngineeringDefinition":
        if len(self.excluded_columns) != len(set(self.excluded_columns)):
            raise ValueError("AutoFE excluded columns must be unique")
        if self.max_frequency_categories < self.max_one_hot_categories:
            raise ValueError(
                "AutoFE max_frequency_categories cannot be lower than max_one_hot_categories"
            )
        return self


class TrainingDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["1.0"] = "1.0"
    problem_type: ProblemType
    algorithm: str = Field(min_length=1, max_length=100)
    target_column: str = Field(default="", max_length=255)
    feature_columns: list[str] = Field(default_factory=list, max_length=500)
    feature_selection: Literal["upstream_contract", "explicit"] = "upstream_contract"
    model_name: str = Field(default="Trained model", min_length=1, max_length=200)
    epochs: int = Field(default=5, ge=1, le=100)
    early_stopping: bool = False
    early_stopping_patience: int = Field(default=5, ge=1, le=50)
    early_stopping_min_delta: float = Field(default=0.0001, ge=0, le=1)
    batch_size: int = Field(default=10_000, ge=100, le=100_000)
    random_seed: int = 42
    parameters: dict[str, Any] = Field(default_factory=dict)
    optimization: OptimizationDefinition = Field(default_factory=OptimizationDefinition)
    resource_limits: TrainingResourceLimits = Field(default_factory=TrainingResourceLimits)
    auto_feature_engineering: AutoFeatureEngineeringDefinition = Field(
        default_factory=AutoFeatureEngineeringDefinition
    )

    @model_validator(mode="after")
    def validate_algorithm(self) -> TrainingDefinition:
        spec = algorithm_spec(self.algorithm)
        validate_algorithm_parameters(
            self.algorithm,
            self.problem_type,
            self.parameters,
        )
        if len(self.feature_columns) != len(set(self.feature_columns)):
            raise ValueError("Training feature columns must be unique")
        if self.target_column in self.feature_columns:
            raise ValueError("The target column cannot also be a feature")
        if self.early_stopping and spec.execution_mode != "incremental":
            raise ValueError(
                "Step-level early stopping is available for incremental estimators; "
                "use the selected estimator's own early-stopping parameter otherwise"
            )
        if self.early_stopping and self.optimization.mode != "single":
            raise ValueError(
                "Step-level early stopping cannot be combined with hyperparameter optimization"
            )
        if self.optimization.mode == "automl":
            for candidate in self.optimization.candidate_algorithms:
                candidate_spec = algorithm_spec(candidate)
                if self.problem_type not in candidate_spec.problem_types:
                    raise ValueError(
                        f"AutoML candidate '{candidate}' does not support "
                        f"{self.problem_type}"
                    )
        if self.auto_feature_engineering.enabled and self.optimization.mode != "automl":
            raise ValueError("AutoFE can currently be enabled only for AutoML optimization")
        if (
            self.auto_feature_engineering.row_id_column
            and self.auto_feature_engineering.row_id_column == self.target_column
        ):
            raise ValueError("AutoFE row ID column cannot be the target column")
        return self

    def validate_executable(self) -> None:
        if not self.target_column:
            raise ValueError("Training requires a target column")
        if not self.feature_columns and not self.auto_feature_engineering.enabled:
            raise ValueError("Training requires at least one model feature")


class ScoringDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["1.0"] = "1.0"
    purpose: Literal["test", "batch"] = "test"
    model_artifact_id: str = Field(default="", max_length=128)
    row_id_column: str = Field(default="", max_length=255)
    target_column: str = Field(default="", max_length=255)
    prediction_column: str = Field(default="prediction", min_length=1, max_length=255)
    dataset_name: str = Field(default="Model predictions", min_length=1, max_length=200)
    report_name: str = Field(default="Test scoring report", min_length=1, max_length=200)
    batch_size: int = Field(default=10_000, ge=100, le=100_000)

    @model_validator(mode="after")
    def validate_purpose(self) -> "ScoringDefinition":
        if self.purpose == "batch":
            if self.target_column:
                raise ValueError(
                    "Batch scoring cannot consume a target column; "
                    "actuals belong to a monitoring pipeline"
                )
        return self

    def validate_executable(self) -> None:
        if not self.row_id_column:
            raise ValueError("Scoring requires a row ID column")
        if self.purpose == "batch" and not self.model_artifact_id:
            raise ValueError("Batch scoring requires a pinned model_artifact_id")


@dataclass(frozen=True)
class ModelingResult:
    input_row_count: int
    processed_row_count: int
    output_row_count: int
    output_manifest: list[dict[str, Any]]
    warnings: list[str]


class SklearnTrainingEngine:
    """Memory-bounded, deterministic first training adapter over full DuckDB relations."""

    def __init__(self, repository_root: Path | None = None) -> None:
        self.repository_root = (repository_root or Path("data/repository")).resolve()

    def execute(
        self,
        definition: TrainingDefinition,
        training: SourceRelation,
        validation: SourceRelation | None,
        *,
        run_id: str,
        owner_id: str,
        is_dry_run: bool,
        emit_event: Callable[[str, dict[str, Any]], None] | None = None,
        is_cancel_requested: Callable[[], bool] | None = None,
        optimization_score_callback: OptimizationScoreCallback | None = None,
    ) -> ModelingResult:
        directory = self._run_directory(owner_id, run_id)
        connection = configured_duckdb_connection(directory / ".training-duckdb")
        try:
            self._validate_columns(connection, training, definition)
            row_count = self._count(connection, training)
            if emit_event:
                emit_event(
                    "training.matrix_preflight",
                    {
                        "message": "Training data preflight completed",
                        "row_count": row_count,
                        "feature_count": len(definition.feature_columns),
                        "algorithm": definition.algorithm,
                        "optimization_mode": definition.optimization.mode,
                    },
                )
            if row_count < 2:
                raise ValueError("Training requires at least two rows")
            classes: np.ndarray | None = None
            if definition.problem_type != "regression":
                class_rows = connection.execute(
                    f"SELECT DISTINCT {identifier(definition.target_column)} "
                    f"FROM {training.sql} "
                    f"WHERE {identifier(definition.target_column)} IS NOT NULL ORDER BY 1"
                ).fetchall()
                if len(class_rows) < 2:
                    raise ValueError("Classification training requires at least two target classes")
                if len(class_rows) > 1000:
                    raise ValueError("Classification target has more than 1000 classes")
                classes = np.asarray([row[0] for row in class_rows])

            spec = algorithm_spec(definition.algorithm)
            optimization_summary: dict[str, Any]
            actual_epochs = 1
            stopped_early = False
            best_epoch: int | None = None
            validation_history: list[dict[str, Any]] = []
            warnings: list[str] = []
            if (
                spec.execution_mode == "incremental"
                and definition.optimization.mode == "single"
            ):
                (
                    estimator,
                    actual_epochs,
                    stopped_early,
                    best_epoch,
                    validation_history,
                ) = self._fit_incremental(
                    connection,
                    definition,
                    training,
                    validation,
                    classes,
                )
                processed_row_count = row_count * actual_epochs
                resolved_algorithm = definition.algorithm
                resolved_parameters = validate_algorithm_parameters(
                    definition.algorithm,
                    definition.problem_type,
                    definition.parameters,
                )
                optimization_summary = {
                    "mode": "single",
                    "primary_metric": (
                        "rmse"
                        if definition.problem_type == "regression"
                        else "accuracy"
                    ),
                    "validation_strategy": (
                        "holdout" if validation is not None else "training"
                    ),
                    "trial_count": 1,
                    "successful_trial_count": 1,
                    "failed_trial_count": 0,
                    "best_score": None,
                    "best_algorithm": resolved_algorithm,
                    "best_parameters": resolved_parameters,
                    "trials": [],
                }
            else:
                uses_cross_validation = (
                    definition.optimization.mode != "single"
                    and (
                        definition.optimization.validation_strategy
                        == "cross_validation"
                        or (
                            definition.optimization.validation_strategy == "auto"
                            and validation is None
                        )
                    )
                )
                fitted_transform_count = int(
                    training.metadata.get("fitted_transform_count") or 0
                )
                if (
                    uses_cross_validation
                    and fitted_transform_count
                    and optimization_score_callback is None
                ):
                    raise ValueError(
                        "Leakage-safe cross-validation cannot reuse Feature Engineering "
                        f"state fitted on the complete training partition "
                        f"({fitted_transform_count} fitted transformation(s) detected). "
                        "Provide an explicit validation output for holdout optimization "
                        "or remove fitted FE transformations. Data was not sampled and "
                        "no potentially leaked CV score was produced."
                    )
                cv_fold_column = next(
                    (
                        str(item.get("name"))
                        for item in training.metadata.get("feature_manifest", [])
                        if item.get("role") == "cv_fold" and item.get("name")
                    ),
                    "",
                )
                cv_fold_assignments = (
                    self._load_cv_fold_assignments(
                        connection,
                        training,
                        cv_fold_column,
                        row_count,
                    )
                    if uses_cross_validation and cv_fold_column
                    else None
                )
                split_evaluation = (
                    training.metadata.get("split_evaluation")
                    if isinstance(training.metadata.get("split_evaluation"), dict)
                    else {}
                )
                cross_validation_metadata = (
                    split_evaluation.get("cross_validation")
                    if isinstance(split_evaluation.get("cross_validation"), dict)
                    else {}
                )
                cv_strategy = str(
                    cross_validation_metadata.get("strategy") or ""
                )
                validation_rows = (
                    self._count(connection, validation)
                    if validation is not None
                    else 0
                )
                needs_validation_matrix = (
                    definition.optimization.mode != "single"
                    and validation is not None
                    and definition.optimization.validation_strategy
                    in {"auto", "holdout"}
                )
                preflight_rows = (
                    row_count + validation_rows
                    if needs_validation_matrix
                    else row_count
                )
                self._enforce_memory_budget(
                    self._preflight_memory_bytes(
                        preflight_rows,
                        len(definition.feature_columns),
                    ),
                    definition.resource_limits.max_memory_mb,
                    preflight_rows,
                    len(definition.feature_columns),
                )
                x_train, y_train, estimated_bytes = self._load_matrix(
                    connection,
                    training,
                    definition,
                    row_count=row_count,
                )
                if emit_event:
                    emit_event(
                        "training.matrix_loaded",
                        {
                            "message": "Training matrix loaded into worker memory",
                            "row_count": row_count,
                            "feature_count": len(definition.feature_columns),
                            "estimated_bytes": estimated_bytes,
                            "memory_budget_mb": definition.resource_limits.max_memory_mb,
                        },
                    )
                x_validation: np.ndarray | None = None
                y_validation: np.ndarray | None = None
                if needs_validation_matrix and validation is not None:
                    (
                        x_validation,
                        y_validation,
                        validation_estimated_bytes,
                    ) = self._load_matrix(
                        connection,
                        validation,
                        definition,
                        row_count=validation_rows,
                    )
                    estimated_bytes += validation_estimated_bytes
                self._enforce_memory_budget(
                    estimated_bytes,
                    definition.resource_limits.max_memory_mb,
                    (
                        row_count + validation_rows
                        if needs_validation_matrix
                        else row_count
                    ),
                    len(definition.feature_columns),
                )
                fit_result = ModelOptimizationEngine().fit(
                    algorithm=definition.algorithm,
                    problem_type=definition.problem_type,
                    parameters=definition.parameters,
                    random_seed=definition.random_seed,
                    epochs=definition.epochs,
                    x_train=x_train,
                    y_train=y_train,
                    x_validation=x_validation,
                    y_validation=y_validation,
                    mode=definition.optimization.mode,
                    validation_strategy=definition.optimization.validation_strategy,
                    primary_metric=definition.optimization.primary_metric,
                    cv_folds=definition.optimization.cv_folds,
                    max_trials=definition.optimization.max_trials,
                    timeout_seconds=definition.optimization.timeout_seconds,
                    max_parallel_jobs=definition.resource_limits.max_parallel_jobs,
                    candidate_algorithms=(
                        definition.optimization.candidate_algorithms
                    ),
                    search_space=definition.optimization.search_space,
                    cv_fold_assignments=cv_fold_assignments,
                    cv_strategy=cv_strategy,
                    emit_event=emit_event,
                    is_cancel_requested=is_cancel_requested,
                    score_callback=optimization_score_callback,
                )
                estimator = fit_result.estimator
                processed_row_count = fit_result.processed_row_count
                resolved_algorithm = fit_result.algorithm
                resolved_parameters = fit_result.parameters
                optimization_summary = fit_result.optimization_summary
                warnings.append(
                    "Full training matrix was materialized in worker memory "
                    f"within the configured "
                    f"{definition.resource_limits.max_memory_mb} MiB budget"
                )
                if resolved_algorithm != definition.algorithm:
                    warnings.append(
                        f"AutoML selected '{resolved_algorithm}' instead of the "
                        f"initial '{definition.algorithm}' candidate"
                    )
                if cv_fold_assignments is not None:
                    resolved_fold_count = len(np.unique(cv_fold_assignments))
                    warnings.append(
                        "Hyperparameter optimization used the auditable upstream "
                        f"CV fold plan with {resolved_fold_count} folds"
                    )
            metrics = self._evaluate(connection, estimator, validation or training, definition)
            if emit_event:
                emit_event(
                    "training.evaluation_completed",
                    {
                        "message": "Model evaluation completed",
                        "algorithm": resolved_algorithm,
                        "processed_row_count": processed_row_count,
                        "evaluated_row_count": metrics.get("evaluated_row_count"),
                        "optimization_mode": optimization_summary.get("mode"),
                        "best_score": optimization_summary.get("best_score"),
                    },
                )
            metrics.update({
                "configured_max_epochs": definition.epochs,
                "executed_epochs": actual_epochs,
                "early_stopping_enabled": definition.early_stopping,
                "stopped_early": stopped_early,
                "best_epoch": best_epoch,
                "early_stopping_patience": definition.early_stopping_patience,
                "early_stopping_min_delta": definition.early_stopping_min_delta,
                "validation_history": validation_history,
                "optimization": optimization_summary,
            })
            model_path = directory / f"{safe_filename(definition.model_name)}.joblib"
            bundle = {
                "contract_version": "1.0",
                "estimator": estimator,
                "problem_type": definition.problem_type,
                "algorithm": resolved_algorithm,
                "feature_columns": definition.feature_columns,
                "target_column": definition.target_column,
                "classes": classes.tolist() if classes is not None else [],
                "definition": definition.model_dump(mode="json"),
                "resolved_parameters": resolved_parameters,
            }
            joblib.dump(bundle, model_path, compress=3)
            model_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
            metrics_path = directory / "training_metrics.json"
            metrics_path.write_text(
                json.dumps(metrics, sort_keys=True, ensure_ascii=True),
                encoding="utf-8",
            )
            training_config = {
                **definition.model_dump(mode="json"),
                "resolved_algorithm": resolved_algorithm,
                "resolved_parameters": json_safe(resolved_parameters),
            }
            model_parameters = self._model_parameter_summary(
                estimator,
                definition.feature_columns,
                classes.tolist() if classes is not None else [],
            )
            return ModelingResult(
                input_row_count=row_count,
                processed_row_count=processed_row_count,
                output_row_count=1,
                warnings=[
                    *warnings,
                    *(
                        [
                        f"Early stopping ended after {actual_epochs} epochs "
                        f"and restored validation-best epoch {best_epoch}"
                        ]
                        if stopped_early
                        else []
                    ),
                ],
                output_manifest=[
                    {
                        "output_id": "model",
                        "artifact_type": "model_version",
                        "materialization": "temporary" if is_dry_run else "artifact",
                        "location_uri": f"file://{model_path.as_posix()}",
                        "model_name": definition.model_name,
                        "algorithm": resolved_algorithm,
                        "problem_type": definition.problem_type,
                        "feature_columns": definition.feature_columns,
                        "target_column": definition.target_column,
                        "model_hash": model_hash,
                        "metrics": metrics,
                        "training_config": training_config,
                        "model_parameters": model_parameters,
                        "row_count": 1,
                        "data_scope": "full",
                        "is_dry_run": is_dry_run,
                    },
                    {
                        "output_id": "training_metrics",
                        "artifact_type": "metrics",
                        "materialization": "temporary" if is_dry_run else "artifact",
                        "location_uri": f"file://{metrics_path.as_posix()}",
                        "metrics": metrics,
                        "row_count": row_count,
                        "data_scope": "full",
                        "is_dry_run": is_dry_run,
                    },
                ],
            )
        finally:
            connection.close()

    @staticmethod
    def _model_parameter_summary(
        estimator: Any,
        feature_columns: list[str],
        classes: list[Any],
        limit: int = 2_000,
    ) -> dict[str, Any]:
        """Return a bounded, JSON-safe view of fitted model parameters."""
        fitted = getattr(estimator, "estimator", estimator)
        coefficients = np.asarray(getattr(fitted, "coef_", np.empty((0, 0))))
        if coefficients.ndim == 1:
            coefficients = coefficients.reshape(1, -1)
        weights: list[dict[str, Any]] = []
        total_weight_count = int(coefficients.size)
        for class_index, row in enumerate(coefficients):
            class_label = classes[class_index] if class_index < len(classes) else None
            for feature_index, value in enumerate(row):
                if len(weights) >= limit:
                    break
                weights.append({
                    "class": json_safe(class_label),
                    "feature": (
                        feature_columns[feature_index]
                        if feature_index < len(feature_columns)
                        else f"feature_{feature_index}"
                    ),
                    "weight": float(value),
                })
            if len(weights) >= limit:
                break
        intercept = np.asarray(getattr(fitted, "intercept_", np.empty(0))).reshape(-1)
        raw_importance = np.asarray(
            getattr(fitted, "feature_importances_", np.empty(0))
        ).reshape(-1)
        feature_importance = [
            {
                "feature": (
                    feature_columns[index]
                    if index < len(feature_columns)
                    else f"feature_{index}"
                ),
                "importance": float(value),
            }
            for index, value in enumerate(raw_importance[:limit])
        ]
        return {
            "weights": weights,
            "intercepts": [float(value) for value in intercept[:100]],
            "total_weight_count": total_weight_count,
            "returned_weight_count": len(weights),
            "truncated": total_weight_count > len(weights),
            "feature_importance": feature_importance,
            "total_feature_importance_count": int(raw_importance.size),
            "fitted_iterations": json_safe(
                getattr(
                    fitted,
                    "n_iter_",
                    getattr(fitted, "tree_count_", None),
                )
            ),
        }

    def _fit_incremental(
        self,
        connection: Any,
        definition: TrainingDefinition,
        training: SourceRelation,
        validation: SourceRelation | None,
        classes: np.ndarray | None,
    ) -> tuple[Any, int, bool, int | None, list[dict[str, Any]]]:
        estimator = build_estimator(
            definition.algorithm,
            definition.problem_type,
            definition.parameters,
            random_seed=definition.random_seed,
            n_jobs=definition.resource_limits.max_parallel_jobs,
        )
        selection = [*definition.feature_columns, definition.target_column]
        query = (
            f"SELECT {', '.join(identifier(item) for item in selection)} "
            f"FROM {training.sql}"
            f"{self._stable_order_clause(training, selection)}"
        )
        best_estimator = None
        best_score: float | None = None
        best_epoch: int | None = None
        epochs_without_improvement = 0
        validation_history: list[dict[str, Any]] = []
        actual_epochs = 0
        stopped_early = False
        for epoch in range(definition.epochs):
            cursor = connection.execute(query)
            first_batch = True
            while frame := cursor.fetchmany(definition.batch_size):
                values = np.asarray(frame, dtype=object)
                x = values[:, :-1].astype(np.float64)
                y = values[:, -1]
                self._validate_matrix(x, y, definition.problem_type)
                if definition.problem_type == "regression":
                    estimator.partial_fit(x, y.astype(np.float64))
                else:
                    estimator.partial_fit(
                        x,
                        y,
                        classes=classes if first_batch else None,
                    )
                first_batch = False
            actual_epochs = epoch + 1
            if definition.early_stopping:
                if validation is None:
                    raise ValueError(
                        "Early stopping requires an explicit validation input"
                    )
                epoch_metrics = self._evaluate(
                    connection, estimator, validation, definition
                )
                validation_history.append({"epoch": actual_epochs, **epoch_metrics})
                score = float(
                    epoch_metrics["rmse"]
                    if definition.problem_type == "regression"
                    else epoch_metrics["accuracy"]
                )
                improved = (
                    best_score is None
                    or (
                        score < best_score - definition.early_stopping_min_delta
                        if definition.problem_type == "regression"
                        else score > best_score + definition.early_stopping_min_delta
                    )
                )
                if improved:
                    best_score = score
                    best_epoch = actual_epochs
                    best_estimator = deepcopy(estimator)
                    epochs_without_improvement = 0
                else:
                    epochs_without_improvement += 1
                    if (
                        epochs_without_improvement
                        >= definition.early_stopping_patience
                    ):
                        stopped_early = True
                        break
        return (
            best_estimator if best_estimator is not None else estimator,
            actual_epochs,
            stopped_early,
            best_epoch,
            validation_history,
        )

    def _load_matrix(
        self,
        connection: Any,
        relation: SourceRelation,
        definition: TrainingDefinition,
        *,
        row_count: int,
    ) -> tuple[np.ndarray, np.ndarray, int]:
        self._validate_columns(connection, relation, definition)
        columns = [*definition.feature_columns, definition.target_column]
        frame = connection.execute(
            f"SELECT {', '.join(identifier(item) for item in columns)} "
            f"FROM {relation.sql}"
            f"{self._stable_order_clause(relation, columns)}"
        ).fetch_df()
        if len(frame) != row_count:
            raise ValueError(
                f"Training relation changed while being read: expected "
                f"{row_count} rows, received {len(frame)}"
            )
        x = frame[definition.feature_columns].to_numpy(dtype=np.float64)
        y = frame[definition.target_column].to_numpy()
        self._validate_matrix(x, y, definition.problem_type)
        if definition.problem_type == "regression":
            y = y.astype(np.float64)
        estimated_bytes = int(
            x.nbytes
            + y.nbytes
            + frame.memory_usage(index=True, deep=True).sum()
            + (x.nbytes + y.nbytes) * 2
        )
        return x, y, estimated_bytes

    @staticmethod
    def _validate_matrix(
        x: np.ndarray,
        y: np.ndarray,
        problem_type: ProblemType,
    ) -> None:
        if not np.isfinite(x).all():
            raise ValueError(
                "Training features contain null, NaN or infinite values"
            )
        if any(value is None or bool(pd.isna(value)) for value in y):
            raise ValueError("Training target contains null values")
        if problem_type == "regression":
            numeric = y.astype(np.float64)
            if not np.isfinite(numeric).all():
                raise ValueError(
                    "Regression target contains NaN or infinite values"
                )

    @staticmethod
    def _preflight_memory_bytes(row_count: int, feature_count: int) -> int:
        # Numeric matrix, target, dataframe buffers and estimator/search working copies.
        return int(row_count * max(1, feature_count + 1) * 8 * 6)

    @staticmethod
    def _load_cv_fold_assignments(
        connection: Any,
        relation: SourceRelation,
        fold_column: str,
        row_count: int,
    ) -> np.ndarray:
        rows = connection.execute(
            f"SELECT {identifier(fold_column)} FROM {relation.sql}"
            f"{SklearnTrainingEngine._stable_order_clause(relation, [fold_column])}"
        ).fetchnumpy()
        assignments = np.asarray(rows[fold_column])
        if len(assignments) != row_count:
            raise ValueError(
                "Upstream CV fold plan row count does not match the training input"
            )
        if assignments.dtype.kind not in {"i", "u"}:
            try:
                assignments = assignments.astype(np.int64)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "Upstream CV fold assignments must be integer-valued"
                ) from exc
        if len(np.unique(assignments)) < 2:
            raise ValueError(
                "Upstream CV fold plan must contain at least two non-empty folds"
            )
        return assignments.astype(np.int64, copy=False)

    @staticmethod
    def _enforce_memory_budget(
        estimated_bytes: int,
        max_memory_mb: int,
        row_count: int,
        feature_count: int,
    ) -> None:
        limit = max_memory_mb * 1024 * 1024
        if estimated_bytes > limit:
            estimated_mb = estimated_bytes / (1024 * 1024)
            raise ValueError(
                "The selected estimator requires a full in-memory training matrix. "
                f"The complete {row_count}-row, {feature_count}-feature scope is "
                f"estimated at {estimated_mb:.1f} MiB, above the configured "
                f"{max_memory_mb} MiB limit. Increase the explicit resource budget "
                "or choose a streaming/large-scale estimator; data was not sampled."
            )

    def _evaluate(self, connection, estimator, relation, definition) -> dict[str, Any]:
        self._validate_columns(connection, relation, definition)
        columns = [*definition.feature_columns, definition.target_column]
        cursor = connection.execute(
            f"SELECT {', '.join(identifier(item) for item in columns)} FROM {relation.sql}"
            f"{self._stable_order_clause(relation, columns)}"
        )
        count = 0
        absolute_error = squared_error = target_sum = target_square_sum = 0.0
        correct = 0
        while rows := cursor.fetchmany(definition.batch_size):
            values = np.asarray(rows, dtype=object)
            x = values[:, :-1].astype(np.float64)
            y = values[:, -1]
            predictions = estimator.predict(x)
            count += len(rows)
            if definition.problem_type == "regression":
                actual = y.astype(np.float64)
                residual = predictions.astype(np.float64) - actual
                absolute_error += float(np.abs(residual).sum())
                squared_error += float(np.square(residual).sum())
                target_sum += float(actual.sum())
                target_square_sum += float(np.square(actual).sum())
            else:
                correct += int(np.sum(predictions == y))
        if not count:
            raise ValueError("Evaluation input is empty")
        if definition.problem_type != "regression":
            return {"accuracy": correct / count, "evaluated_row_count": count}
        denominator = target_square_sum - (target_sum * target_sum / count)
        return {
            "mae": absolute_error / count,
            "rmse": (squared_error / count) ** 0.5,
            "r2": 1.0 - squared_error / denominator if denominator > 0 else 0.0,
            "evaluated_row_count": count,
        }

    @staticmethod
    def _validate_columns(connection, relation, definition) -> None:
        available = {
            str(row[0])
            for row in connection.execute(f"DESCRIBE SELECT * FROM {relation.sql}").fetchall()
        }
        required = {*definition.feature_columns, definition.target_column}
        missing = sorted(required - available)
        if missing:
            raise ValueError(f"Training input is missing columns: {', '.join(missing)}")

    @staticmethod
    def _count(connection, relation: SourceRelation) -> int:
        return relation.row_count if relation.row_count >= 0 else int(
            connection.execute(f"SELECT count(*) FROM {relation.sql}").fetchone()[0]
        )

    @staticmethod
    def _stable_order_clause(
        relation: SourceRelation,
        fallback_columns: list[str],
    ) -> str:
        manifest = relation.metadata.get("feature_manifest")
        if isinstance(manifest, list):
            for item in manifest:
                if (
                    isinstance(item, dict)
                    and item.get("role") == "row_id"
                    and item.get("name")
                ):
                    return f" ORDER BY {identifier(str(item['name']))}"
        columns = list(dict.fromkeys(column for column in fallback_columns if column))
        if not columns:
            return ""
        return " ORDER BY " + ", ".join(identifier(column) for column in columns)

    def _run_directory(self, owner_id: str, run_id: str) -> Path:
        directory = (self.repository_root / "users" / owner_id / "pipeline-runs" / run_id).resolve()
        directory.relative_to(self.repository_root)
        directory.mkdir(parents=True, exist_ok=True)
        return directory


class SklearnScoringEngine:
    def __init__(self, repository_root: Path | None = None) -> None:
        self.repository_root = (repository_root or Path("data/repository")).resolve()

    def execute(
        self,
        definition: ScoringDefinition,
        data: SourceRelation,
        model_manifest: dict[str, Any],
        *,
        run_id: str,
        owner_id: str,
        is_dry_run: bool,
    ) -> ModelingResult:
        model_path = Path(str(model_manifest["location_uri"]).removeprefix("file://")).resolve()
        model_path.relative_to(self.repository_root)
        expected_model_hash = str(model_manifest.get("model_hash") or "")
        if expected_model_hash:
            actual_model_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
            if actual_model_hash != expected_model_hash:
                raise ValueError("Pinned model artifact hash does not match its registry metadata")
        bundle = joblib.load(model_path)
        features = [str(item) for item in bundle["feature_columns"]]
        estimator = bundle["estimator"]
        problem_type = str(bundle["problem_type"])
        is_classification = problem_type != "regression"
        class_labels = (
            list(np.asarray(getattr(estimator, "classes_", bundle.get("classes", []))).tolist())
            if is_classification else []
        )
        positive_class_index = len(class_labels) - 1 if len(class_labels) == 2 else None
        positive_class = (
            class_labels[positive_class_index]
            if positive_class_index is not None else None
        )
        probability_available = is_classification and hasattr(estimator, "predict_proba")
        decision_score_available = is_classification and hasattr(estimator, "decision_function")
        if is_classification and not probability_available and not decision_score_available:
            raise ValueError("Classifier exposes neither predict_proba nor decision_function")
        score_kind = (
            "positive_class_probability"
            if positive_class_index is not None and probability_available
            else "decision_function"
            if decision_score_available
            else "class_probability"
        )
        class_score_columns = (
            [f"class_score_{index}" for index in range(len(class_labels))]
            if len(class_labels) > 2 and decision_score_available else []
        )
        class_probability_columns = (
            [f"class_probability_{index}" for index in range(len(class_labels))]
            if len(class_labels) > 2 and probability_available else []
        )
        score_contract = {
            "problem_type": problem_type,
            "classes": [
                {
                    "index": index,
                    "label": label,
                    "score_column": (
                        class_score_columns[index]
                        if index < len(class_score_columns) else None
                    ),
                    "probability_column": (
                        class_probability_columns[index]
                        if index < len(class_probability_columns) else None
                    ),
                }
                for index, label in enumerate(class_labels)
            ],
            "positive_class": positive_class,
            "positive_class_index": positive_class_index,
            "prediction_score_column": "prediction_score" if is_classification else None,
            "prediction_score_kind": score_kind if is_classification else None,
            "positive_class_probability_column": (
                "positive_class_probability"
                if positive_class_index is not None and probability_available else None
            ),
            "probability_available": probability_available,
        }
        directory = (self.repository_root / "users" / owner_id / "pipeline-runs" / run_id).resolve()
        directory.relative_to(self.repository_root)
        directory.mkdir(parents=True, exist_ok=True)
        connection = configured_duckdb_connection(directory / ".scoring-duckdb")
        reader = configured_duckdb_connection(directory / ".scoring-reader-duckdb")
        output_path = directory / f"{safe_filename(definition.dataset_name)}.parquet"
        table_name = "__mlapp_predictions"
        try:
            available = {
                str(row[0])
                for row in reader.execute(f"DESCRIBE SELECT * FROM {data.sql}").fetchall()
            }
            required = {definition.row_id_column, *features}
            if definition.target_column:
                required.add(definition.target_column)
            missing = sorted(required - available)
            if missing:
                raise ValueError(f"Scoring input is missing columns: {', '.join(missing)}")
            total_rows, null_row_ids, distinct_row_ids = reader.execute(
                f"SELECT count(*), "
                f"count(*) FILTER (WHERE {identifier(definition.row_id_column)} IS NULL), "
                f"count(DISTINCT {identifier(definition.row_id_column)}) "
                f"FROM {data.sql}"
            ).fetchone()
            if int(null_row_ids):
                raise ValueError(
                    f"Scoring row ID column '{definition.row_id_column}' "
                    f"contains {int(null_row_ids)} null values"
                )
            if int(distinct_row_ids) != int(total_rows):
                raise ValueError(
                    f"Scoring row ID column '{definition.row_id_column}' must be unique; "
                    f"found {int(distinct_row_ids)} distinct IDs in {int(total_rows)} rows"
                )
            selected = [definition.row_id_column, *features]
            if definition.target_column:
                selected.append(definition.target_column)
            cursor = reader.execute(
                f"SELECT {', '.join(identifier(item) for item in selected)} FROM {data.sql}"
                f" ORDER BY {identifier(definition.row_id_column)}"
            )
            total = correct = 0
            absolute_error = squared_error = 0.0
            created = False
            while rows := cursor.fetchmany(definition.batch_size):
                frame = pd.DataFrame.from_records(rows, columns=selected)
                x = frame[features].to_numpy(dtype=np.float64)
                if not np.isfinite(x).all():
                    raise ValueError("Scoring features contain null, NaN or infinite values")
                predictions = self._prediction_vector(
                    estimator.predict(x),
                    problem_type=problem_type,
                    class_labels=class_labels,
                )
                output = pd.DataFrame({
                    definition.row_id_column: frame[definition.row_id_column],
                    definition.prediction_column: predictions,
                })
                if probability_available:
                    probabilities = estimator.predict_proba(x)
                    if positive_class_index is not None:
                        positive_probabilities = probabilities[:, positive_class_index]
                        output["prediction_score"] = positive_probabilities
                        output["positive_class_probability"] = positive_probabilities
                    else:
                        predicted_indices = np.asarray([
                            class_labels.index(prediction)
                            for prediction in predictions.tolist()
                        ])
                        output["prediction_score"] = probabilities[
                            np.arange(len(predictions)), predicted_indices
                        ]
                        for index, column in enumerate(class_probability_columns):
                            output[column] = probabilities[:, index]
                elif decision_score_available:
                    decision_scores = np.asarray(estimator.decision_function(x))
                    if positive_class_index is not None:
                        output["prediction_score"] = (
                            decision_scores
                            if decision_scores.ndim == 1
                            else decision_scores[:, positive_class_index]
                        )
                    else:
                        predicted_indices = np.asarray([
                            class_labels.index(prediction)
                            for prediction in predictions.tolist()
                        ])
                        output["prediction_score"] = decision_scores[
                            np.arange(len(predictions)), predicted_indices
                        ]
                        for index, column in enumerate(class_score_columns):
                            output[column] = decision_scores[:, index]
                if definition.target_column:
                    actual = frame[definition.target_column].to_numpy()
                    output[definition.target_column] = actual
                    if problem_type == "regression":
                        residual = predictions.astype(float) - actual.astype(float)
                        absolute_error += float(np.abs(residual).sum())
                        squared_error += float(np.square(residual).sum())
                    else:
                        correct += int(np.sum(predictions == actual))
                total += len(output)
                connection.register("__mlapp_prediction_batch", output)
                if not created:
                    connection.execute(
                        f"CREATE TABLE {identifier(table_name)} AS SELECT * FROM __mlapp_prediction_batch"
                    )
                    created = True
                else:
                    connection.execute(
                        f"INSERT INTO {identifier(table_name)} SELECT * FROM __mlapp_prediction_batch"
                    )
                connection.unregister("__mlapp_prediction_batch")
            if not created:
                raise ValueError("Scoring input is empty")
            stats = write_parquet_atomic(
                connection,
                f"SELECT * FROM {identifier(table_name)}",
                output_path,
            )
            evaluation = (
                ModelEvaluationSnapshotBuilder().build(
                    connection,
                    f"SELECT * FROM {identifier(table_name)}",
                    problem_type=problem_type,
                    target_column=definition.target_column,
                    prediction_column=definition.prediction_column,
                    score_contract=score_contract,
                )
                if definition.target_column
                else None
            )
            metrics: dict[str, Any] = {"scored_row_count": total}
            if definition.target_column:
                if problem_type == "regression":
                    metrics.update({
                        "mae": absolute_error / total,
                        "rmse": (squared_error / total) ** 0.5,
                    })
                else:
                    metrics["accuracy"] = correct / total
            if evaluation is not None:
                metrics.update({
                    str(item["id"]): item["value"]
                    for item in evaluation.get("metrics", [])
                    if isinstance(item, dict) and item.get("id") and item.get("value") is not None
                })
            preview_cursor = connection.execute(
                f"SELECT * FROM read_parquet({sql_literal(str(output_path))}) LIMIT 50"
            )
            names = [str(item[0]) for item in preview_cursor.description or []]
            preview = [
                {name: json_safe(value) for name, value in zip(names, row, strict=True)}
                for row in preview_cursor.fetchall()
            ]
            return ModelingResult(
                input_row_count=total,
                processed_row_count=total,
                output_row_count=total,
                warnings=[],
                output_manifest=[{
                    "output_id": "predictions",
                    "artifact_type": "prediction_dataset",
                    "materialization": "temporary" if is_dry_run else "dataset",
                    "location_uri": f"file://{output_path.as_posix()}",
                    "row_count": total,
                    "schema": [{"name": str(row[0]), "type": str(row[1])} for row in stats.schema_rows],
                    "dataset_name": definition.dataset_name,
                    "business_case_role": "scoring_output",
                    "metrics": metrics,
                    **({"evaluation": evaluation} if evaluation is not None else {}),
                    "score_contract": score_contract,
                    "row_id_column": definition.row_id_column,
                    "prediction_column": definition.prediction_column,
                    "data_scope": "full",
                    "is_dry_run": is_dry_run,
                    "preview": {
                        "records": preview,
                        "returned_count": len(preview),
                        "limit": 50,
                        "sampled": total > len(preview),
                    },
                }],
            )
        finally:
            reader.close()
            connection.close()

    @staticmethod
    def _prediction_vector(
        values: Any,
        *,
        problem_type: str,
        class_labels: list[Any],
    ) -> np.ndarray:
        """Normalize estimator output to the one prediction column contract.

        A few third-party multiclass estimators return a score/probability
        matrix from ``predict``. The scoring artifact stores those values in
        explicit per-class columns, while its prediction column must contain
        exactly one chosen class per input row.
        """
        predictions = np.asarray(values)
        if predictions.ndim == 1:
            return predictions
        if predictions.ndim == 2 and predictions.shape[1] == 1:
            return predictions[:, 0]
        if (
            problem_type != "regression"
            and predictions.ndim == 2
            and class_labels
            and predictions.shape[1] == len(class_labels)
        ):
            labels = np.asarray(class_labels, dtype=object)
            return labels[np.argmax(predictions, axis=1)]
        raise ValueError(
            "Model predict() returned a matrix that cannot be represented as "
            "one prediction per row"
        )
