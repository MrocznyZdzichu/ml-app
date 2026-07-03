from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import duckdb
import joblib
import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sklearn.linear_model import (
    Perceptron,
    SGDClassifier,
    SGDRegressor,
)

from app.modules.pipelines.runtime import SourceRelation, json_safe, safe_filename, sql_literal
from app.shared.duckdb_runtime import configured_duckdb_connection, write_parquet_atomic
from app.shared.sql_security import identifier


class TrainingDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["1.0"] = "1.0"
    problem_type: Literal["binary_classification", "multiclass_classification", "regression"]
    algorithm: Literal[
        "sgd_classifier",
        "passive_aggressive_classifier",
        "perceptron_classifier",
        "sgd_regressor",
        "passive_aggressive_regressor",
    ]
    target_column: str = Field(min_length=1, max_length=255)
    feature_columns: list[str] = Field(min_length=1, max_length=500)
    model_name: str = Field(default="Trained model", min_length=1, max_length=200)
    epochs: int = Field(default=5, ge=1, le=100)
    early_stopping: bool = False
    early_stopping_patience: int = Field(default=5, ge=1, le=50)
    early_stopping_min_delta: float = Field(default=0.0001, ge=0, le=1)
    batch_size: int = Field(default=10_000, ge=100, le=100_000)
    random_seed: int = 42
    parameters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_algorithm(self) -> TrainingDefinition:
        regression_algorithms = {"sgd_regressor", "passive_aggressive_regressor"}
        classification_algorithms = {
            "sgd_classifier",
            "passive_aggressive_classifier",
            "perceptron_classifier",
        }
        if self.problem_type == "regression" and self.algorithm not in regression_algorithms:
            raise ValueError("Regression requires a regression algorithm")
        if self.problem_type != "regression" and self.algorithm not in classification_algorithms:
            raise ValueError("Classification requires a classification algorithm")
        if len(self.feature_columns) != len(set(self.feature_columns)):
            raise ValueError("Training feature columns must be unique")
        if self.target_column in self.feature_columns:
            raise ValueError("The target column cannot also be a feature")
        allowed_by_algorithm = {
            "sgd_classifier": {"alpha", "penalty", "l1_ratio", "learning_rate", "eta0", "fit_intercept"},
            "sgd_regressor": {"alpha", "penalty", "l1_ratio", "learning_rate", "eta0", "fit_intercept"},
            "passive_aggressive_classifier": {"C", "loss", "average", "fit_intercept"},
            "passive_aggressive_regressor": {"C", "epsilon", "loss", "average", "fit_intercept"},
            "perceptron_classifier": {"alpha", "penalty", "eta0", "fit_intercept"},
        }
        allowed = allowed_by_algorithm[self.algorithm]
        unsupported = set(self.parameters) - allowed
        if unsupported:
            raise ValueError(f"Unsupported training parameters: {', '.join(sorted(unsupported))}")
        if self.parameters.get("penalty") not in {None, "l1", "l2", "elasticnet"}:
            raise ValueError("Penalty must be none, l1, l2 or elasticnet")
        if self.algorithm == "passive_aggressive_classifier" and self.parameters.get("loss", "hinge") not in {
            "hinge", "squared_hinge"
        }:
            raise ValueError("Passive-Aggressive classifier loss must be hinge or squared_hinge")
        if self.algorithm == "passive_aggressive_regressor" and self.parameters.get(
            "loss", "epsilon_insensitive"
        ) not in {"epsilon_insensitive", "squared_epsilon_insensitive"}:
            raise ValueError("Passive-Aggressive regressor loss is invalid")
        if self.algorithm in {"sgd_classifier", "sgd_regressor"} and self.parameters.get(
            "learning_rate", "optimal"
        ) not in {"optimal", "constant", "invscaling", "adaptive"}:
            raise ValueError("SGD learning_rate is invalid")
        for positive_key in {"C", "eta0"} & set(self.parameters):
            if float(self.parameters[positive_key]) <= 0:
                raise ValueError(f"{positive_key} must be greater than zero")
        for non_negative_key in {"alpha", "epsilon", "l1_ratio"} & set(self.parameters):
            if float(self.parameters[non_negative_key]) < 0:
                raise ValueError(f"{non_negative_key} cannot be negative")
        return self


class ScoringDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["1.0"] = "1.0"
    row_id_column: str = Field(min_length=1, max_length=255)
    target_column: str = Field(default="", max_length=255)
    prediction_column: str = Field(default="prediction", min_length=1, max_length=255)
    dataset_name: str = Field(default="Model predictions", min_length=1, max_length=200)
    batch_size: int = Field(default=10_000, ge=100, le=100_000)


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
    ) -> ModelingResult:
        directory = self._run_directory(owner_id, run_id)
        connection = configured_duckdb_connection(directory / ".training-duckdb")
        try:
            self._validate_columns(connection, training, definition)
            row_count = self._count(connection, training)
            if row_count < 2:
                raise ValueError("Training requires at least two rows")
            estimator = self._estimator(definition)
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

            selection = [*definition.feature_columns, definition.target_column]
            query = f"SELECT {', '.join(identifier(item) for item in selection)} FROM {training.sql}"
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
                    if not np.isfinite(x).all():
                        raise ValueError("Training features contain null, NaN or infinite values")
                    if any(value is None for value in y):
                        raise ValueError("Training target contains null values")
                    if definition.problem_type == "regression":
                        estimator.partial_fit(x, y.astype(np.float64))
                    else:
                        estimator.partial_fit(x, y, classes=classes if first_batch else None)
                    first_batch = False
                actual_epochs = epoch + 1
                if definition.early_stopping:
                    if validation is None:
                        raise ValueError("Early stopping requires an explicit validation input")
                    epoch_metrics = self._evaluate(connection, estimator, validation, definition)
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
                        if epochs_without_improvement >= definition.early_stopping_patience:
                            stopped_early = True
                            break

            if best_estimator is not None:
                estimator = best_estimator
            metrics = self._evaluate(connection, estimator, validation or training, definition)
            metrics.update({
                "configured_max_epochs": definition.epochs,
                "executed_epochs": actual_epochs,
                "early_stopping_enabled": definition.early_stopping,
                "stopped_early": stopped_early,
                "best_epoch": best_epoch,
                "early_stopping_patience": definition.early_stopping_patience,
                "early_stopping_min_delta": definition.early_stopping_min_delta,
                "validation_history": validation_history,
            })
            model_path = directory / f"{safe_filename(definition.model_name)}.joblib"
            bundle = {
                "contract_version": "1.0",
                "estimator": estimator,
                "problem_type": definition.problem_type,
                "algorithm": definition.algorithm,
                "feature_columns": definition.feature_columns,
                "target_column": definition.target_column,
                "classes": classes.tolist() if classes is not None else [],
                "definition": definition.model_dump(mode="json"),
            }
            joblib.dump(bundle, model_path, compress=3)
            model_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
            metrics_path = directory / "training_metrics.json"
            metrics_path.write_text(
                json.dumps(metrics, sort_keys=True, ensure_ascii=True),
                encoding="utf-8",
            )
            training_config = definition.model_dump(mode="json")
            model_parameters = self._model_parameter_summary(
                estimator,
                definition.feature_columns,
                classes.tolist() if classes is not None else [],
            )
            return ModelingResult(
                input_row_count=row_count,
                processed_row_count=row_count * actual_epochs,
                output_row_count=1,
                warnings=(
                    [
                        f"Early stopping ended after {actual_epochs} epochs "
                        f"and restored validation-best epoch {best_epoch}"
                    ]
                    if stopped_early else []
                ),
                output_manifest=[
                    {
                        "output_id": "model",
                        "artifact_type": "model_version",
                        "materialization": "temporary" if is_dry_run else "artifact",
                        "location_uri": f"file://{model_path.as_posix()}",
                        "model_name": definition.model_name,
                        "algorithm": definition.algorithm,
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
        """Return a bounded, JSON-safe view of fitted linear-model parameters."""
        coefficients = np.asarray(getattr(estimator, "coef_", np.empty((0, 0))))
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
        intercept = np.asarray(getattr(estimator, "intercept_", np.empty(0))).reshape(-1)
        return {
            "weights": weights,
            "intercepts": [float(value) for value in intercept[:100]],
            "total_weight_count": total_weight_count,
            "returned_weight_count": len(weights),
            "truncated": total_weight_count > len(weights),
        }

    @staticmethod
    def _estimator(definition: TrainingDefinition):
        sgd_common = {
            "random_state": definition.random_seed,
            "alpha": float(definition.parameters.get("alpha", 0.0001)),
            "penalty": str(definition.parameters.get("penalty", "l2")),
            "learning_rate": str(definition.parameters.get("learning_rate", "optimal")),
            "fit_intercept": bool(definition.parameters.get("fit_intercept", True)),
        }
        if "l1_ratio" in definition.parameters:
            sgd_common["l1_ratio"] = float(definition.parameters["l1_ratio"])
        if "eta0" in definition.parameters:
            sgd_common["eta0"] = float(definition.parameters["eta0"])
        if definition.algorithm == "sgd_regressor":
            return SGDRegressor(**sgd_common)
        if definition.algorithm == "sgd_classifier":
            return SGDClassifier(loss="log_loss", **sgd_common)
        if definition.algorithm == "perceptron_classifier":
            return Perceptron(
                random_state=definition.random_seed,
                alpha=float(definition.parameters.get("alpha", 0.0001)),
                penalty=definition.parameters.get("penalty"),
                eta0=float(definition.parameters.get("eta0", 1.0)),
                fit_intercept=bool(definition.parameters.get("fit_intercept", True)),
            )
        if definition.algorithm == "passive_aggressive_classifier":
            return SGDClassifier(
                random_state=definition.random_seed,
                loss=str(definition.parameters.get("loss", "hinge")),
                penalty=None,
                learning_rate="pa1",
                eta0=float(definition.parameters.get("C", 1.0)),
                average=bool(definition.parameters.get("average", False)),
                fit_intercept=bool(definition.parameters.get("fit_intercept", True)),
            )
        return SGDRegressor(
            random_state=definition.random_seed,
            penalty=None,
            learning_rate="pa1",
            eta0=float(definition.parameters.get("C", 1.0)),
            epsilon=float(definition.parameters.get("epsilon", 0.1)),
            loss=str(definition.parameters.get("loss", "epsilon_insensitive")),
            average=bool(definition.parameters.get("average", False)),
            fit_intercept=bool(definition.parameters.get("fit_intercept", True)),
        )

    def _evaluate(self, connection, estimator, relation, definition) -> dict[str, Any]:
        self._validate_columns(connection, relation, definition)
        columns = [*definition.feature_columns, definition.target_column]
        cursor = connection.execute(
            f"SELECT {', '.join(identifier(item) for item in columns)} FROM {relation.sql}"
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
            selected = [definition.row_id_column, *features]
            if definition.target_column:
                selected.append(definition.target_column)
            cursor = reader.execute(
                f"SELECT {', '.join(identifier(item) for item in selected)} FROM {data.sql}"
            )
            total = correct = 0
            absolute_error = squared_error = 0.0
            created = False
            while rows := cursor.fetchmany(definition.batch_size):
                frame = pd.DataFrame.from_records(rows, columns=selected)
                x = frame[features].to_numpy(dtype=np.float64)
                if not np.isfinite(x).all():
                    raise ValueError("Scoring features contain null, NaN or infinite values")
                predictions = estimator.predict(x)
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
            metrics: dict[str, Any] = {"scored_row_count": total}
            if definition.target_column:
                if problem_type == "regression":
                    metrics.update({
                        "mae": absolute_error / total,
                        "rmse": (squared_error / total) ** 0.5,
                    })
                else:
                    metrics["accuracy"] = correct / total
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
                    "score_contract": score_contract,
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
