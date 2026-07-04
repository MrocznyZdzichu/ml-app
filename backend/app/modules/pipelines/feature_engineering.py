from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import duckdb
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.business_cases.domain import ArtifactType
from app.modules.business_cases.repository import (
    BusinessCaseRepository,
    PostgresBusinessCaseRepository,
)
from app.modules.pipelines.execution import (
    CsvDatasetInputAdapter,
    PipelineInputAdapter,
)
from app.modules.pipelines.runtime import (
    SourceRelation,
    json_safe,
    relation_columns,
    safe_filename,
    sql_literal,
)
from app.shared.sql_security import identifier, validate_scalar_sql_expression
from app.shared.duckdb_runtime import (
    ParquetWriteStats,
    configured_duckdb_connection,
    write_parquet_atomic,
)


class FeatureInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_id: str = Field(min_length=1, max_length=128)
    role: Literal["training", "validation", "test", "scoring_input"]
    dataset_id: str = Field(default="", max_length=128)
    version_policy: Literal["latest", "select_at_run", "select_at_run_any"] = "latest"


class FeatureTransformation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transform_id: str = Field(min_length=1, max_length=128)
    type: Literal[
        "impute",
        "scale_numeric",
        "encode_categorical",
        "datetime_features",
        "numeric_interaction",
        "math_transform",
        "sql_expression",
        "pca",
    ]
    columns: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_config(self) -> FeatureTransformation:
        if not self.columns and self.type not in {"numeric_interaction", "sql_expression"}:
            raise ValueError(f"Feature transform '{self.transform_id}' requires columns")
        allowed: dict[str, set[str]] = {
            "impute": {"method", "value", "add_indicator"},
            "scale_numeric": {"method", "output_suffix"},
            "encode_categorical": {
                "method", "min_frequency", "max_categories", "handle_unknown",
                "drop_original", "output_suffix",
            },
            "datetime_features": {"features", "cyclical", "drop_original"},
            "numeric_interaction": {"left", "right", "operator", "output_column", "zero_division"},
            "math_transform": {"operation", "output_suffix"},
            "sql_expression": {"expression", "output_column", "output_type"},
            "pca": {"n_components", "output_prefix", "whiten", "drop_original"},
        }
        unexpected = sorted(set(self.config) - allowed[self.type])
        if unexpected:
            raise ValueError(
                f"Feature transform '{self.transform_id}' has unsupported config fields: "
                f"{', '.join(unexpected)}"
            )
        if self.type == "impute":
            method = self.config.get("method", "median")
            if method not in {"constant", "mean", "median", "mode"}:
                raise ValueError("FE imputation method must be constant, mean, median or mode")
            if method == "constant" and "value" not in self.config:
                raise ValueError("Constant FE imputation requires a value")
        if self.type == "scale_numeric" and self.config.get("method", "standard") not in {
            "standard", "minmax", "robust",
        }:
            raise ValueError("Numeric scaling method must be standard, minmax or robust")
        if self.type == "encode_categorical":
            if self.config.get("method", "ordinal") not in {"ordinal", "one_hot", "frequency"}:
                raise ValueError("Categorical encoding method must be ordinal, one_hot or frequency")
            if self.config.get("handle_unknown", "other") not in {"other", "error"}:
                raise ValueError("Unknown category policy must be other or error")
            maximum = int(self.config.get("max_categories", 50))
            if maximum < 2 or maximum > 500:
                raise ValueError("max_categories must be between 2 and 500")
            if int(self.config.get("min_frequency", 1)) < 1:
                raise ValueError("min_frequency must be positive")
        if self.type == "datetime_features":
            features = self.config.get("features", ["year", "month", "day_of_week"])
            allowed_parts = {"year", "quarter", "month", "day", "day_of_week", "hour", "is_weekend"}
            if not isinstance(features, list) or not features or set(features) - allowed_parts:
                raise ValueError("datetime_features contains unsupported date parts")
        if self.type == "numeric_interaction":
            required = {"left", "right", "operator", "output_column"}
            if not required.issubset(self.config):
                raise ValueError("numeric_interaction requires left, right, operator and output_column")
            if self.config["operator"] not in {"add", "subtract", "multiply", "divide"}:
                raise ValueError("Unsupported numeric interaction operator")
        if self.type == "math_transform":
            if self.config.get("operation", "square") not in {
                "square", "sqrt", "exp", "log", "log1p", "abs",
            }:
                raise ValueError("Unsupported mathematical feature transformation")
            suffix = self.config.get("output_suffix")
            if not isinstance(suffix, str) or not suffix:
                raise ValueError("math_transform requires a non-empty output_suffix")
        if self.type == "sql_expression":
            output = self.config.get("output_column")
            if not isinstance(output, str) or not output:
                raise ValueError("sql_expression requires output_column")
            try:
                validate_scalar_sql_expression(str(self.config.get("expression", "")))
            except ValueError as exc:
                raise ValueError(f"Invalid FE SQL expression: {exc}") from exc
            if self.config.get("output_type", "number") not in {
                "number", "text", "boolean", "date",
            }:
                raise ValueError("sql_expression output_type is unsupported")
        if self.type == "pca":
            if len(self.columns) > 200:
                raise ValueError("PCA supports at most 200 input columns per block")
            components = self.config.get("n_components", 2)
            if isinstance(components, bool) or not isinstance(components, int):
                raise ValueError("PCA n_components must be an integer")
            if components < 1 or components > min(len(self.columns), 50):
                raise ValueError("PCA n_components must be between 1 and the selected column count")
            prefix = self.config.get("output_prefix", "pca_")
            if not isinstance(prefix, str) or not prefix:
                raise ValueError("PCA output_prefix cannot be empty")
        return self


class FeatureOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_id: str = Field(min_length=1, max_length=128)
    input_id: str = Field(min_length=1, max_length=128)
    dataset_name: str = Field(min_length=1, max_length=255)
    business_case_role: Literal["training", "validation", "test", "scoring_input"] = "training"


class CrossValidationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    strategy: Literal["kfold", "stratified", "group", "time"] = "kfold"
    folds: int = Field(default=5, ge=2, le=20)
    shuffle: bool = True
    seed: int = 42


class EvaluationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    split_strategy: Literal["predefined", "random", "stratified", "group", "time"] = "predefined"
    validation_size: float = Field(default=0.1, ge=0, lt=1)
    test_size: float = Field(default=0.2, gt=0, lt=1)
    seed: int = 42
    stratify_column: str = ""
    group_column: str = ""
    time_column: str = ""
    cross_validation: CrossValidationConfig = Field(default_factory=CrossValidationConfig)

    @model_validator(mode="after")
    def validate_evaluation(self) -> EvaluationConfig:
        if self.split_strategy != "predefined" and self.validation_size + self.test_size >= 1:
            raise ValueError("Validation and test shares must leave a non-empty training share")
        if self.split_strategy == "stratified" and not self.stratify_column:
            raise ValueError("Stratified split requires stratify_column")
        if self.split_strategy == "group" and not self.group_column:
            raise ValueError("Group split requires group_column")
        if self.split_strategy == "time" and not self.time_column:
            raise ValueError("Time split requires time_column")
        cv = self.cross_validation
        if cv.enabled and cv.strategy == "stratified" and not self.stratify_column:
            raise ValueError("Stratified cross-validation requires stratify_column")
        if cv.enabled and cv.strategy == "group" and not self.group_column:
            raise ValueError("Group cross-validation requires group_column")
        if cv.enabled and cv.strategy == "time" and not self.time_column:
            raise ValueError("Time cross-validation requires time_column")
        return self


class FeatureEngineeringDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["1.0"] = "1.0"
    mode: Literal["fit_transform", "transform"] = "fit_transform"
    inputs: list[FeatureInput] = Field(default_factory=list)
    feature_columns: list[str] = Field(default_factory=list)
    target_column: str = ""
    row_id_column: str = ""
    group_column: str = ""
    event_time_column: str = ""
    transformations: list[FeatureTransformation] = Field(default_factory=list)
    outputs: list[FeatureOutput] = Field(default_factory=list)
    fitted_state_artifact_id: str = ""
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)

    @model_validator(mode="after")
    def validate_definition(self) -> FeatureEngineeringDefinition:
        input_ids = [item.input_id for item in self.inputs]
        if len(input_ids) != len(set(input_ids)):
            raise ValueError("FE input_id values must be unique")
        roles = [item.role for item in self.inputs]
        if len(roles) != len(set(roles)):
            raise ValueError("FE input roles must be unique")
        transform_ids = [item.transform_id for item in self.transformations]
        if len(transform_ids) != len(set(transform_ids)):
            raise ValueError("FE transform_id values must be unique")
        output_ids = [item.output_id for item in self.outputs]
        if len(output_ids) != len(set(output_ids)):
            raise ValueError("FE output_id values must be unique")
        output_roles = [item.business_case_role for item in self.outputs]
        if len(output_roles) != len(set(output_roles)):
            raise ValueError("FE output Business Case roles must be unique")
        virtual_split_inputs = (
            {"training", "validation", "test"}
            if self.evaluation.split_strategy != "predefined"
            else set()
        )
        unknown_inputs = sorted(
            {item.input_id for item in self.outputs} - set(input_ids) - virtual_split_inputs
        )
        if unknown_inputs:
            raise ValueError(f"FE outputs reference unknown inputs: {', '.join(unknown_inputs)}")
        protected = [value for value in (
            self.target_column,
            self.row_id_column,
            self.group_column,
            self.event_time_column,
        ) if value]
        if set(protected) & set(self.feature_columns):
            raise ValueError("Target, row ID, group and event time columns cannot be selected as features")
        if self.mode == "transform" and not self.fitted_state_artifact_id:
            raise ValueError("Transform mode requires fitted_state_artifact_id")
        if self.evaluation.split_strategy in {"random", "stratified"} and not self.row_id_column:
            raise ValueError("Random and stratified splits require row_id_column for reproducibility")
        if (
            self.evaluation.cross_validation.enabled
            and self.evaluation.cross_validation.strategy in {"kfold", "stratified"}
            and not self.row_id_column
        ):
            raise ValueError("K-fold and stratified cross-validation require row_id_column")
        return self

    def validate_executable(self) -> None:
        if not self.inputs:
            raise ValueError("Executable Feature Engineering requires at least one input")
        if not self.outputs:
            raise ValueError("Executable Feature Engineering requires at least one output")
        if self.mode == "fit_transform" and "training" not in {item.role for item in self.inputs}:
            raise ValueError("fit_transform requires exactly one training input")
        if self.evaluation.split_strategy != "predefined":
            if len(self.inputs) != 1 or self.inputs[0].role != "training":
                raise ValueError("Generated splits require one source input with the training role")
            output_inputs = {item.input_id for item in self.outputs}
            required = {"training", "test"}
            if self.evaluation.validation_size > 0:
                required.add("validation")
            if not required.issubset(output_inputs):
                raise ValueError("Generated split outputs must include training, test and optional validation")


@dataclass(frozen=True)
class FeatureEngineeringExecutionResult:
    input_row_count: int
    processed_row_count: int
    output_row_count: int
    output_manifest: list[dict[str, Any]]
    warnings: list[str]
    input_dataset_ids: list[str]


class DuckDbFeatureEngineeringEngine:
    def __init__(
        self,
        input_adapter: PipelineInputAdapter | None = None,
        business_cases: BusinessCaseRepository | None = None,
        repository_root: Path | None = None,
    ) -> None:
        self.repository_root = (repository_root or Path("data/repository")).resolve()
        self.input_adapter = input_adapter or CsvDatasetInputAdapter(repository_root=self.repository_root)
        self.business_cases = business_cases or PostgresBusinessCaseRepository()

    def execute(
        self,
        *,
        definition: FeatureEngineeringDefinition,
        run_id: str,
        owner_id: str,
        is_dry_run: bool,
        upstream_relations: dict[str, SourceRelation] | None = None,
    ) -> FeatureEngineeringExecutionResult:
        definition.validate_executable()
        run_directory = self._run_directory(owner_id, run_id)
        temp_directory = run_directory / ".duckdb-fe-tmp"
        connection = configured_duckdb_connection(temp_directory)
        relations: dict[str, str] = {}
        input_counts: dict[str, int] = {}
        input_dataset_ids: list[str] = []
        manifests: list[dict[str, Any]] = []
        warnings: list[str] = []
        evaluation_manifest: dict[str, Any] = {}
        try:
            upstream_relations = upstream_relations or {}
            for item in definition.inputs:
                source = upstream_relations.get(item.input_id)
                if source is None:
                    if not item.dataset_id:
                        raise ValueError(f"FE input '{item.input_id}' has no upstream binding or dataset_id")
                    source = self.input_adapter.relation(item.dataset_id, owner_id)
                    input_dataset_ids.append(item.dataset_id)
                view = f"__mlapp_fe_input_{safe_filename(item.input_id)}"
                connection.execute(f"CREATE TEMP VIEW {identifier(view)} AS SELECT * FROM {source.sql}")
                relations[item.input_id] = view
                count = source.row_count
                if count < 0:
                    count = int(connection.execute(f"SELECT count(*) FROM {identifier(view)}").fetchone()[0])
                input_counts[item.input_id] = count

            relations, evaluation_manifest = self._prepare_evaluation(
                connection,
                definition,
                relations,
            )

            if definition.mode == "fit_transform":
                state = self._fit(connection, definition, relations)
                state["definition_hash"] = _definition_hash(definition)
                state["recipe_hash"] = _recipe_hash(definition)
                state["feature_roles"] = _feature_roles(definition)
            else:
                state = self._load_state(definition.fitted_state_artifact_id, owner_id)
                if state.get("recipe_hash") != _recipe_hash(definition):
                    raise ValueError(
                        "Feature Engineering recipe does not match the pinned fitted transform"
                    )

            transformed: dict[str, str] = {}
            for input_id, input_relation in relations.items():
                current = input_relation
                for transform in definition.transformations:
                    current = self._apply_transform(
                        connection,
                        current,
                        transform,
                        state["transforms"][transform.transform_id],
                        input_id,
                    )
                transformed[input_id] = current

            for output in definition.outputs:
                source_view = transformed[output.input_id]
                destination = run_directory / f"fe-{safe_filename(output.output_id)}.parquet"
                write_stats = self._write_parquet(connection, source_view, destination)
                manifest = self._dataset_manifest(
                    connection,
                    destination,
                    write_stats,
                    output,
                    is_dry_run,
                    definition,
                    state,
                    evaluation_manifest,
                )
                manifests.append(manifest)

            if definition.mode == "fit_transform":
                state_path = run_directory / "fitted-feature-transform.json"
                temporary = state_path.with_name(f".{state_path.name}.{uuid4().hex}.tmp")
                temporary.write_text(
                    json.dumps(state, sort_keys=True, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8",
                )
                os.replace(temporary, state_path)
                manifests.append({
                    "output_id": "fitted_transform",
                    "artifact_type": ArtifactType.FEATURE_TRANSFORM.value,
                    "materialization": "temporary" if is_dry_run else "artifact",
                    "location_uri": f"file://{state_path.as_posix()}",
                    "state_hash": _state_hash(state),
                    "definition_hash": state["definition_hash"],
                    "data_scope": "full",
                    "is_dry_run": is_dry_run,
                    "feature_manifest": state.get("feature_manifest", []),
                    "split_evaluation": evaluation_manifest,
                })
        finally:
            connection.close()

        dataset_manifests = [item for item in manifests if item.get("artifact_type", "dataset") == "dataset"]
        return FeatureEngineeringExecutionResult(
            input_row_count=sum(input_counts.values()),
            processed_row_count=sum(input_counts.values()),
            output_row_count=sum(int(item["row_count"]) for item in dataset_manifests),
            output_manifest=manifests,
            warnings=warnings,
            input_dataset_ids=input_dataset_ids,
        )

    def _prepare_evaluation(
        self,
        connection: duckdb.DuckDBPyConnection,
        definition: FeatureEngineeringDefinition,
        relations: dict[str, str],
    ) -> tuple[dict[str, str], dict[str, Any]]:
        evaluation = definition.evaluation
        prepared = dict(relations)
        if evaluation.split_strategy != "predefined":
            source_id = definition.inputs[0].input_id
            source = relations[source_id]
            self._validate_evaluation_columns(connection, source, evaluation)
            score_expression = self._split_score_expression(evaluation, definition.row_id_column)
            scored = f"__mlapp_fe_split_scored_{uuid4().hex[:8]}"
            connection.execute(
                f"CREATE TEMP VIEW {identifier(scored)} AS "
                f"SELECT *, {score_expression} AS __mlapp_split_score FROM {identifier(source)}"
            )
            test_end = evaluation.test_size
            validation_end = round(test_end + evaluation.validation_size, 12)
            predicates = {
                "test": f"__mlapp_split_score < {sql_literal(test_end)}",
                "validation": (
                    f"__mlapp_split_score >= {sql_literal(test_end)} "
                    f"AND __mlapp_split_score < {sql_literal(validation_end)}"
                ),
                "training": f"__mlapp_split_score >= {sql_literal(validation_end)}",
            }
            prepared = {}
            for role, predicate in predicates.items():
                if role == "validation" and evaluation.validation_size == 0:
                    continue
                view = f"__mlapp_fe_split_{role}_{uuid4().hex[:8]}"
                connection.execute(
                    f"CREATE TEMP VIEW {identifier(view)} AS "
                    f"SELECT * EXCLUDE (__mlapp_split_score) FROM {identifier(scored)} "
                    f"WHERE {predicate}"
                )
                prepared[role] = view

        if evaluation.cross_validation.enabled:
            training = prepared["training"]
            self._validate_evaluation_columns(connection, training, evaluation, for_cv=True)
            expression = self._cv_fold_expression(
                evaluation,
                definition.row_id_column,
            )
            folded = f"__mlapp_fe_cv_training_{uuid4().hex[:8]}"
            connection.execute(
                f"CREATE TEMP VIEW {identifier(folded)} AS "
                f"SELECT *, CAST({expression} AS INTEGER) AS __mlapp_cv_fold "
                f"FROM {identifier(training)}"
            )
            prepared["training"] = folded

        split_counts = {
            role: int(connection.execute(
                f"SELECT count(*) FROM {identifier(view)}"
            ).fetchone()[0])
            for role, view in prepared.items()
        }
        if evaluation.split_strategy != "predefined" and (
            split_counts.get("training", 0) == 0 or split_counts.get("test", 0) == 0
        ):
            raise ValueError("Generated split produced an empty training or test partition")
        fold_counts: list[dict[str, int]] = []
        if evaluation.cross_validation.enabled:
            fold_counts = [
                {"fold": int(row[0]), "row_count": int(row[1])}
                for row in connection.execute(
                    f"SELECT __mlapp_cv_fold, count(*) FROM {identifier(prepared['training'])} "
                    "GROUP BY __mlapp_cv_fold ORDER BY __mlapp_cv_fold"
                ).fetchall()
            ]
            if len(fold_counts) < 2:
                raise ValueError("Cross-validation produced fewer than two non-empty folds")
        return prepared, {
            "split_strategy": evaluation.split_strategy,
            "validation_size": evaluation.validation_size,
            "test_size": evaluation.test_size,
            "seed": evaluation.seed,
            "split_row_counts": split_counts,
            "cross_validation": {
                **evaluation.cross_validation.model_dump(mode="json"),
                "fold_column": "__mlapp_cv_fold" if evaluation.cross_validation.enabled else "",
                "fold_row_counts": fold_counts,
                "time_semantics": (
                    "For fold i, train on earlier folds and validate on fold i."
                    if evaluation.cross_validation.enabled
                    and evaluation.cross_validation.strategy == "time"
                    else ""
                ),
            },
        }

    @staticmethod
    def _validate_evaluation_columns(
        connection: duckdb.DuckDBPyConnection,
        source: str,
        evaluation: EvaluationConfig,
        *,
        for_cv: bool = False,
    ) -> None:
        available = set(relation_columns(connection, source))
        strategy = evaluation.cross_validation.strategy if for_cv else evaluation.split_strategy
        required = {
            "stratified": evaluation.stratify_column,
            "group": evaluation.group_column,
            "time": evaluation.time_column,
        }.get(strategy, "")
        if required and required not in available:
            raise ValueError(f"Evaluation strategy references unknown column '{required}'")
        if required:
            null_count = int(connection.execute(
                f"SELECT count(*) FROM {identifier(source)} "
                f"WHERE {identifier(required)} IS NULL"
            ).fetchone()[0])
            if null_count:
                raise ValueError(
                    f"Evaluation column '{required}' contains {null_count} null values"
                )

    @staticmethod
    def _row_key_expression(row_id_column: str, seed: int) -> str:
        base = (
            f"CAST({identifier(row_id_column)} AS VARCHAR)"
            if row_id_column
            else "CAST(row_number() OVER () AS VARCHAR)"
        )
        return f"concat({base}, '|', {sql_literal(seed)})"

    def _split_score_expression(
        self,
        evaluation: EvaluationConfig,
        row_id_column: str,
    ) -> str:
        strategy = evaluation.split_strategy
        if strategy == "group":
            return (
                f"(hash(concat(CAST({identifier(evaluation.group_column)} AS VARCHAR), "
                f"'|', {sql_literal(evaluation.seed)})) % 1000000) / 1000000.0"
            )
        key = self._row_key_expression(
            row_id_column or evaluation.time_column,
            evaluation.seed,
        )
        if strategy == "stratified":
            target = identifier(evaluation.stratify_column)
            return (
                f"(row_number() OVER (PARTITION BY {target} ORDER BY hash({key})) - 1) "
                f"/ greatest(count(*) OVER (PARTITION BY {target}), 1)::DOUBLE"
            )
        if strategy == "time":
            return (
                f"1.0 - ((row_number() OVER (ORDER BY {identifier(evaluation.time_column)}, "
                f"hash({key})) - 1) / greatest(count(*) OVER (), 1)::DOUBLE)"
            )
        return f"(hash({key}) % 1000000) / 1000000.0"

    def _cv_fold_expression(
        self,
        evaluation: EvaluationConfig,
        row_id_column: str,
    ) -> str:
        cv = evaluation.cross_validation
        if cv.strategy == "group":
            return (
                f"hash(concat(CAST({identifier(evaluation.group_column)} AS VARCHAR), "
                f"'|', {sql_literal(cv.seed)})) % {cv.folds}"
            )
        key = self._row_key_expression(
            row_id_column or evaluation.time_column,
            cv.seed,
        )
        if cv.strategy == "stratified":
            target = identifier(evaluation.stratify_column)
            ordering = f"hash({key})" if cv.shuffle else key
            return (
                f"(row_number() OVER (PARTITION BY {target} ORDER BY {ordering}) - 1) "
                f"% {cv.folds}"
            )
        if cv.strategy == "time":
            return (
                f"ntile({cv.folds}) OVER (ORDER BY {identifier(evaluation.time_column)}, hash({key})) - 1"
            )
        if not cv.shuffle:
            return f"(row_number() OVER (ORDER BY {key}) - 1) % {cv.folds}"
        return f"hash({key}) % {cv.folds}"

    def _fit(
        self,
        connection: duckdb.DuckDBPyConnection,
        definition: FeatureEngineeringDefinition,
        relations: dict[str, str],
    ) -> dict[str, Any]:
        training_id = next(item.input_id for item in definition.inputs if item.role == "training")
        current = relations[training_id]
        transform_states: dict[str, Any] = {}
        for transform in definition.transformations:
            self._validate_columns(connection, current, transform)
            fitted = self._fit_transform(connection, current, transform)
            transform_states[transform.transform_id] = fitted
            current = self._apply_transform(
                connection, current, transform, fitted, f"fit_{training_id}",
            )
        schema_rows = connection.execute(f"DESCRIBE SELECT * FROM {identifier(current)}").fetchall()
        final_names = {str(row[0]) for row in schema_rows}
        missing_features = sorted(
            feature for feature in definition.feature_columns
            if feature not in final_names
            and not any(name.startswith(f"{feature}__") for name in final_names)
        )
        if missing_features:
            raise ValueError(
                "Selected model features are not present after the FE recipe: "
                + ", ".join(missing_features)
            )
        protected = {
            value for value in (
                definition.target_column,
                definition.row_id_column,
                definition.group_column,
                definition.event_time_column,
            ) if value
        }
        selected_features = set(definition.feature_columns)
        feature_manifest = [
            {
                "feature_id": hashlib.sha256(str(row[0]).encode("utf-8")).hexdigest()[:16],
                "name": str(row[0]),
                "type": str(row[1]),
                "role": (
                    "target" if str(row[0]) == definition.target_column
                    else "row_id" if str(row[0]) == definition.row_id_column
                    else "group" if str(row[0]) == definition.group_column
                    else "event_time" if str(row[0]) == definition.event_time_column
                    else "cv_fold" if str(row[0]) == "__mlapp_cv_fold"
                    else "feature" if not selected_features or str(row[0]) in selected_features
                    or any(str(row[0]).startswith(f"{column}__") for column in selected_features)
                    else "passthrough"
                ),
            }
            for row in schema_rows
            if str(row[0]) not in protected or str(row[0]) in protected
        ]
        return {
            "contract_version": "1.0",
            "engine": "duckdb",
            "transforms": transform_states,
            "feature_manifest": feature_manifest,
        }

    def _fit_transform(
        self,
        connection: duckdb.DuckDBPyConnection,
        source: str,
        transform: FeatureTransformation,
    ) -> dict[str, Any]:
        if transform.type == "impute":
            method = str(transform.config.get("method", "median"))
            values: dict[str, Any] = {}
            if method == "constant":
                for column in transform.columns:
                    values[column] = transform.config.get("value")
            elif method in {"mean", "median"}:
                function = "avg" if method == "mean" else "median"
                row = connection.execute(
                    "SELECT "
                    + ", ".join(
                        f"{function}({identifier(column)})"
                        for column in transform.columns
                    )
                    + f" FROM {identifier(source)}"
                ).fetchone()
                values.update(zip(transform.columns, row, strict=True))
            else:
                for column in transform.columns:
                    values[column] = connection.execute(
                        f"SELECT {identifier(column)} FROM {identifier(source)} "
                        f"WHERE {identifier(column)} IS NOT NULL GROUP BY {identifier(column)} "
                        f"ORDER BY count(*) DESC, {identifier(column)} LIMIT 1"
                    ).fetchone()
                    values[column] = values[column][0] if values[column] else None
            return {"type": transform.type, "method": method, "values": _json_values(values)}
        if transform.type == "scale_numeric":
            method = str(transform.config.get("method", "standard"))
            columns: dict[str, Any] = {}
            functions = {
                "standard": ("avg", "stddev_pop"),
                "minmax": ("min", "max"),
                "robust": ("median", "quantile_cont_25", "quantile_cont_75"),
            }[method]
            expressions: list[str] = []
            for column in transform.columns:
                name = identifier(column)
                for function in functions:
                    if function == "quantile_cont_25":
                        expressions.append(f"quantile_cont({name}, 0.25)")
                    elif function == "quantile_cont_75":
                        expressions.append(f"quantile_cont({name}, 0.75)")
                    else:
                        expressions.append(f"{function}({name})")
            aggregate_row = connection.execute(
                f"SELECT {', '.join(expressions)} FROM {identifier(source)}"
            ).fetchone()
            width = len(functions)
            for index, column in enumerate(transform.columns):
                values = aggregate_row[index * width:(index + 1) * width]
                if method == "standard":
                    center, scale = values
                elif method == "minmax":
                    minimum, maximum = values
                    center = minimum or 0
                    scale = (
                        maximum - minimum
                        if minimum is not None and maximum is not None
                        else 1
                    )
                else:
                    center, lower, upper = values
                    center = center or 0
                    scale = upper - lower if lower is not None and upper is not None else 1
                columns[column] = {
                    "center": json_safe(center),
                    "scale": json_safe(scale or 1),
                }
            return {"type": transform.type, "method": method, "columns": columns}
        if transform.type == "encode_categorical":
            method = str(transform.config.get("method", "ordinal"))
            minimum = int(transform.config.get("min_frequency", 1))
            maximum = int(transform.config.get("max_categories", 50))
            training_row_count = int(
                connection.execute(f"SELECT count(*) FROM {identifier(source)}").fetchone()[0]
            )
            columns: dict[str, Any] = {}
            for column in transform.columns:
                rows = connection.execute(
                    f"SELECT {identifier(column)}, count(*) AS frequency FROM {identifier(source)} "
                    f"WHERE {identifier(column)} IS NOT NULL GROUP BY {identifier(column)} "
                    f"HAVING count(*) >= ? ORDER BY frequency DESC, CAST({identifier(column)} AS VARCHAR) "
                    f"LIMIT ?",
                    [minimum, maximum],
                ).fetchall()
                columns[column] = {
                    "categories": [json_safe(row[0]) for row in rows],
                    "frequencies": {str(row[0]): int(row[1]) for row in rows},
                    "training_row_count": training_row_count,
                }
            return {
                "type": transform.type,
                "method": method,
                "handle_unknown": transform.config.get("handle_unknown", "other"),
                "columns": columns,
            }
        if transform.type == "pca":
            selected = list(transform.columns)
            null_predicate = " OR ".join(
                f"{identifier(column)} IS NULL" for column in selected
            )
            covariance_expressions = [
                f"covar_pop(CAST({identifier(left)} AS DOUBLE), "
                f"CAST({identifier(right)} AS DOUBLE))"
                for left in selected
                for right in selected
            ]
            aggregate_row = connection.execute(
                "SELECT "
                f"count(*), count(*) FILTER (WHERE {null_predicate}), "
                + ", ".join(
                    f"avg(CAST({identifier(column)} AS DOUBLE))"
                    for column in selected
                )
                + ", "
                + ", ".join(covariance_expressions)
                + f" FROM {identifier(source)}"
            ).fetchone()
            row_count = int(aggregate_row[0])
            null_count = int(aggregate_row[1])
            if null_count:
                raise ValueError(
                    f"PCA transform '{transform.transform_id}' found {null_count} rows with "
                    "missing selected values; add imputation before PCA"
                )
            if row_count < 2:
                raise ValueError("PCA requires at least two training rows")
            width = len(selected)
            means_row = aggregate_row[2:2 + width]
            covariance_row = aggregate_row[2 + width:]
            covariance = np.asarray(covariance_row, dtype=float).reshape((width, width))
            eigenvalues, eigenvectors = np.linalg.eigh(covariance)
            order = np.argsort(eigenvalues)[::-1]
            eigenvalues = np.maximum(eigenvalues[order], 0.0)
            eigenvectors = eigenvectors[:, order]
            component_count = int(transform.config.get("n_components", 2))
            components = eigenvectors[:, :component_count].T
            for index in range(component_count):
                pivot = int(np.argmax(np.abs(components[index])))
                if components[index, pivot] < 0:
                    components[index] *= -1
            total_variance = float(np.sum(eigenvalues))
            explained = eigenvalues[:component_count]
            return {
                "type": transform.type,
                "columns": selected,
                "means": [float(value) for value in means_row],
                "components": components.tolist(),
                "explained_variance": explained.tolist(),
                "explained_variance_ratio": (
                    (explained / total_variance).tolist()
                    if total_variance > 0
                    else [0.0] * component_count
                ),
            }
        return {"type": transform.type}

    def _apply_transform(
        self,
        connection: duckdb.DuckDBPyConnection,
        source: str,
        transform: FeatureTransformation,
        fitted: dict[str, Any],
        scope_id: str,
    ) -> str:
        columns = relation_columns(connection, source)
        selection = [identifier(column) for column in columns]
        if transform.type == "impute":
            selection = []
            for column in columns:
                if column not in transform.columns:
                    selection.append(identifier(column))
                    continue
                replacement = sql_literal(fitted["values"].get(column))
                selection.append(
                    f"coalesce({identifier(column)}, {replacement}) AS {identifier(column)}"
                )
                if bool(transform.config.get("add_indicator", False)):
                    selection.append(
                        f"{identifier(column)} IS NULL AS {identifier(f'{column}__was_missing')}"
                    )
        elif transform.type == "scale_numeric":
            suffix = str(transform.config.get("output_suffix", "__scaled"))
            for column in transform.columns:
                params = fitted["columns"][column]
                selection.append(
                    f"(CAST({identifier(column)} AS DOUBLE) - {sql_literal(params['center'])}) "
                    f"/ {sql_literal(params['scale'])} AS {identifier(column + suffix)}"
                )
        elif transform.type == "encode_categorical":
            method = fitted["method"]
            suffix = str(transform.config.get("output_suffix", ""))
            drop_original = bool(transform.config.get("drop_original", True))
            if drop_original:
                selection = [identifier(column) for column in columns if column not in transform.columns]
            for column in transform.columns:
                info = fitted["columns"][column]
                categories = info["categories"]
                known = ", ".join(sql_literal(value) for value in categories) or "NULL"
                if fitted["handle_unknown"] == "error":
                    count = int(connection.execute(
                        f"SELECT count(*) FROM {identifier(source)} WHERE {identifier(column)} IS NOT NULL "
                        f"AND {identifier(column)} NOT IN ({known})"
                    ).fetchone()[0])
                    if count:
                        raise ValueError(
                            f"FE input '{scope_id}' contains {count} unknown values in '{column}'"
                        )
                if method == "one_hot":
                    for index, category in enumerate(categories):
                        selection.append(
                            f"CAST({identifier(column)} = {sql_literal(category)} AS TINYINT) "
                            f"AS {identifier(f'{column}__{index}')}"
                        )
                    if fitted["handle_unknown"] == "other":
                        selection.append(
                            f"CAST({identifier(column)} IS NULL OR {identifier(column)} NOT IN ({known}) "
                            f"AS TINYINT) AS {identifier(f'{column}__other')}"
                        )
                elif method == "ordinal":
                    cases = " ".join(
                        f"WHEN {identifier(column)} = {sql_literal(category)} THEN {index}"
                        for index, category in enumerate(categories)
                    )
                    selection.append(
                        f"CASE {cases} ELSE -1 END AS {identifier(column + suffix + '__ordinal')}"
                    )
                else:
                    total = max(int(info["training_row_count"]), 1)
                    cases = " ".join(
                        f"WHEN {identifier(column)} = {sql_literal(category)} "
                        f"THEN {sql_literal(info['frequencies'][str(category)] / total)}"
                        for category in categories
                    )
                    selection.append(
                        f"CASE {cases} ELSE 0.0 END AS {identifier(column + suffix + '__frequency')}"
                    )
        elif transform.type == "datetime_features":
            parts = transform.config.get("features", ["year", "month", "day_of_week"])
            drop_original = bool(transform.config.get("drop_original", False))
            if drop_original:
                selection = [identifier(column) for column in columns if column not in transform.columns]
            expressions = {
                "year": "year",
                "quarter": "quarter",
                "month": "month",
                "day": "day",
                "day_of_week": "dayofweek",
                "hour": "hour",
            }
            for column in transform.columns:
                for part in parts:
                    if part == "is_weekend":
                        selection.append(
                            f"CAST(dayofweek(CAST({identifier(column)} AS TIMESTAMP)) IN (0, 6) AS TINYINT) "
                            f"AS {identifier(f'{column}__is_weekend')}"
                        )
                    else:
                        selection.append(
                            f"{expressions[part]}(CAST({identifier(column)} AS TIMESTAMP)) "
                            f"AS {identifier(f'{column}__{part}')}"
                        )
                if bool(transform.config.get("cyclical", False)):
                    for part, period in (("month", 12), ("day_of_week", 7), ("hour", 24)):
                        if part not in parts:
                            continue
                        function = expressions[part]
                        base = f"{function}(CAST({identifier(column)} AS TIMESTAMP))"
                        selection.append(
                            f"sin(2 * pi() * {base} / {period}) AS {identifier(f'{column}__{part}_sin')}"
                        )
                        selection.append(
                            f"cos(2 * pi() * {base} / {period}) AS {identifier(f'{column}__{part}_cos')}"
                        )
        elif transform.type == "math_transform":
            operation = str(transform.config.get("operation", "square"))
            suffix = str(transform.config["output_suffix"])
            for column in transform.columns:
                value = f"CAST({identifier(column)} AS DOUBLE)"
                expression = {
                    "square": f"power({value}, 2)",
                    "sqrt": f"CASE WHEN {value} >= 0 THEN sqrt({value}) ELSE NULL END",
                    "exp": f"exp({value})",
                    "log": f"CASE WHEN {value} > 0 THEN ln({value}) ELSE NULL END",
                    "log1p": f"CASE WHEN {value} > -1 THEN ln(1 + {value}) ELSE NULL END",
                    "abs": f"abs({value})",
                }[operation]
                selection.append(
                    f"{expression} AS {identifier(column + suffix)}"
                )
        elif transform.type == "sql_expression":
            expression = validate_scalar_sql_expression(str(transform.config["expression"]))
            output = str(transform.config["output_column"])
            selection.append(f"({expression}) AS {identifier(output)}")
        elif transform.type == "pca":
            if bool(transform.config.get("drop_original", False)):
                selected = set(transform.columns)
                selection = [identifier(column) for column in columns if column not in selected]
            prefix = str(transform.config.get("output_prefix", "pca_"))
            whiten = bool(transform.config.get("whiten", False))
            for index, weights in enumerate(fitted["components"]):
                terms = [
                    f"((CAST({identifier(column)} AS DOUBLE) - {sql_literal(mean)}) "
                    f"* {sql_literal(weight)})"
                    for column, mean, weight in zip(
                        fitted["columns"], fitted["means"], weights, strict=True
                    )
                ]
                expression = f"({' + '.join(terms)})"
                if whiten:
                    scale = max(float(fitted["explained_variance"][index]) ** 0.5, 1e-12)
                    expression = f"{expression} / {sql_literal(scale)}"
                selection.append(
                    f"{expression} AS {identifier(f'{prefix}{index + 1}')}"
                )
        elif transform.type == "numeric_interaction":
            left = identifier(str(transform.config["left"]))
            right = identifier(str(transform.config["right"]))
            operator = transform.config["operator"]
            symbol = {"add": "+", "subtract": "-", "multiply": "*", "divide": "/"}[operator]
            if operator == "divide":
                zero_policy = transform.config.get("zero_division", "null")
                right = f"nullif({right}, 0)" if zero_policy == "null" else right
            selection.append(
                f"({left} {symbol} {right}) AS {identifier(str(transform.config['output_column']))}"
            )
        else:
            raise ValueError(f"Unsupported Feature Engineering transform '{transform.type}'")
        view = f"__mlapp_fe_{safe_filename(transform.transform_id)}_{uuid4().hex[:8]}"
        connection.execute(
            f"CREATE TEMP VIEW {identifier(view)} AS SELECT {', '.join(selection)} "
            f"FROM {identifier(source)}"
        )
        return view

    def _load_state(self, artifact_id: str, owner_id: str) -> dict[str, Any]:
        artifact = self.business_cases.get_artifact(artifact_id)
        if (
            artifact is None
            or artifact.owner_id != owner_id
            or artifact.type != ArtifactType.FEATURE_TRANSFORM
        ):
            raise ValueError("Fitted feature transform artifact was not found")
        uri = str(artifact.metadata.get("location_uri") or "")
        path = self._path_from_uri(uri)
        return json.loads(path.read_text(encoding="utf-8"))

    def _dataset_manifest(
        self,
        connection: duckdb.DuckDBPyConnection,
        path: Path,
        write_stats: ParquetWriteStats,
        output: FeatureOutput,
        is_dry_run: bool,
        definition: FeatureEngineeringDefinition,
        state: dict[str, Any],
        evaluation_manifest: dict[str, Any],
    ) -> dict[str, Any]:
        relation = f"read_parquet({sql_literal(str(path))})"
        row_count = write_stats.row_count
        schema_rows = write_stats.schema_rows
        preview_cursor = connection.execute(f"SELECT * FROM {relation} LIMIT 50")
        names = [str(item[0]) for item in preview_cursor.description or []]
        records = [
            {name: json_safe(value) for name, value in zip(names, row, strict=True)}
            for row in preview_cursor.fetchall()
        ]
        return {
            "output_id": output.output_id,
            "artifact_type": "dataset",
            "materialization": "temporary" if is_dry_run else "dataset",
            "write_mode": "replace",
            "location_uri": f"file://{path.as_posix()}",
            "row_count": row_count,
            "schema": [{"name": str(row[0]), "type": str(row[1])} for row in schema_rows],
            "schema_hash": hashlib.sha256(
                json.dumps([(str(row[0]), str(row[1])) for row in schema_rows]).encode("utf-8")
            ).hexdigest(),
            "feature_manifest": state.get("feature_manifest", []),
            "split_evaluation": evaluation_manifest,
            "data_scope": "full",
            "is_dry_run": is_dry_run,
            "dataset_name": output.dataset_name,
            "business_case_role": output.business_case_role,
            "input_id": output.input_id,
            "preview": {
                "records": records,
                "returned_count": len(records),
                "limit": 50,
                "sampled": row_count > len(records),
            },
        }

    @staticmethod
    def _write_parquet(
        connection: duckdb.DuckDBPyConnection,
        source: str,
        destination: Path,
    ) -> ParquetWriteStats:
        return write_parquet_atomic(
            connection,
            f"SELECT * FROM {identifier(source)}",
            destination,
        )

    @staticmethod
    def _validate_columns(
        connection: duckdb.DuckDBPyConnection,
        source: str,
        transform: FeatureTransformation,
    ) -> None:
        available = set(relation_columns(connection, source))
        referenced = set(transform.columns)
        if transform.type == "numeric_interaction":
            referenced.update({str(transform.config["left"]), str(transform.config["right"])})
        missing = sorted(referenced - available)
        if missing:
            raise ValueError(
                f"Feature transform '{transform.transform_id}' references unknown columns: "
                f"{', '.join(missing)}"
            )
        output_names: list[str] = []
        if transform.type == "numeric_interaction":
            output_names = [str(transform.config["output_column"])]
        elif transform.type == "sql_expression":
            output_names = [str(transform.config["output_column"])]
        elif transform.type == "math_transform":
            suffix = str(transform.config["output_suffix"])
            output_names = [f"{column}{suffix}" for column in transform.columns]
        elif transform.type == "pca":
            prefix = str(transform.config.get("output_prefix", "pca_"))
            output_names = [
                f"{prefix}{index + 1}"
                for index in range(int(transform.config.get("n_components", 2)))
            ]
        collisions = sorted(set(output_names) & available)
        if collisions:
            raise ValueError(
                f"Feature transform '{transform.transform_id}' would overwrite columns: "
                + ", ".join(collisions)
            )
        numeric_transforms = {"scale_numeric", "numeric_interaction", "math_transform", "pca"}
        if transform.type in numeric_transforms:
            described = connection.execute(
                f"DESCRIBE SELECT * FROM {identifier(source)}"
            ).fetchall()
            types = {str(row[0]): str(row[1]).upper() for row in described}
            non_numeric = sorted(
                column for column in referenced
                if not any(token in types.get(column, "") for token in (
                    "INT", "DECIMAL", "DOUBLE", "FLOAT", "REAL", "HUGEINT",
                ))
            )
            if non_numeric:
                raise ValueError(
                    f"Feature transform '{transform.transform_id}' requires numeric columns: "
                    + ", ".join(non_numeric)
                )

    def _run_directory(self, owner_id: str, run_id: str) -> Path:
        root = (self.repository_root / "users").resolve()
        directory = (root / owner_id / "pipeline-runs" / run_id).resolve()
        try:
            directory.relative_to(root)
        except ValueError as exc:
            raise ValueError("Feature Engineering run path is outside the repository root") from exc
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _path_from_uri(self, uri: str) -> Path:
        if not uri.startswith("file://"):
            raise ValueError("Feature transform artifact has no local location")
        path = Path(uri.removeprefix("file://")).resolve()
        try:
            path.relative_to(self.repository_root)
        except ValueError as exc:
            raise ValueError("Feature transform artifact is outside the repository root") from exc
        if not path.is_file():
            raise ValueError("Feature transform state file was not found")
        return path


def empty_feature_engineering_definition() -> dict[str, Any]:
    return {
        "contract_version": "1.0",
        "mode": "fit_transform",
        "inputs": [{"input_id": "training", "role": "training", "dataset_id": ""}],
        "feature_columns": [],
        "target_column": "",
        "row_id_column": "",
        "group_column": "",
        "event_time_column": "",
        "transformations": [],
        "outputs": [{
            "output_id": "training_features",
            "input_id": "training",
            "dataset_name": "Training features",
            "business_case_role": "training",
        }],
        "fitted_state_artifact_id": "",
        "evaluation": {
            "split_strategy": "predefined",
            "validation_size": 0.1,
            "test_size": 0.2,
            "seed": 42,
            "stratify_column": "",
            "group_column": "",
            "time_column": "",
            "cross_validation": {
                "enabled": False,
                "strategy": "kfold",
                "folds": 5,
                "shuffle": True,
                "seed": 42,
            },
        },
    }


def _scalar(connection: duckdb.DuckDBPyConnection, source: str, expression: str) -> Any:
    value = connection.execute(
        f"SELECT {expression} FROM {identifier(source)}"
    ).fetchone()[0]
    return json_safe(value)


def _json_values(values: dict[str, Any]) -> dict[str, Any]:
    return {key: json_safe(value) for key, value in values.items()}


def _definition_hash(definition: FeatureEngineeringDefinition) -> str:
    payload = json.dumps(
        definition.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _state_hash(state: dict[str, Any]) -> str:
    payload = json.dumps(state, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _recipe_hash(definition: FeatureEngineeringDefinition) -> str:
    feature_roles = _feature_roles(definition)
    feature_roles.pop("cv_fold_column", None)
    payload = json.dumps(
        {
            "transformations": [
                item.model_dump(mode="json") for item in definition.transformations
            ],
            "feature_roles": feature_roles,
        },
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _feature_roles(definition: FeatureEngineeringDefinition) -> dict[str, Any]:
    return {
        "feature_columns": definition.feature_columns,
        "target_column": definition.target_column,
        "row_id_column": definition.row_id_column,
        "group_column": definition.group_column,
        "event_time_column": definition.event_time_column,
        "cv_fold_column": (
            "__mlapp_cv_fold"
            if definition.evaluation.cross_validation.enabled
            else ""
        ),
    }
