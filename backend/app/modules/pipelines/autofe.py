from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.modules.pipelines.feature_engineering import (
    EvaluationConfig,
    FeatureEngineeringDefinition,
    FeatureInput,
    FeatureOutput,
    FeatureTransformation,
)
from app.modules.pipelines.modeling_catalog import algorithm_spec
from app.modules.pipelines.runtime import SourceRelation
from app.shared.duckdb_runtime import configured_duckdb_connection
from app.shared.sql_security import identifier


_NUMERIC_TYPE_TOKENS = (
    "INT", "DECIMAL", "NUMERIC", "DOUBLE", "FLOAT", "REAL", "HUGEINT",
)
_TEMPORAL_TYPE_TOKENS = ("DATE", "TIME", "TIMESTAMP")
_CATEGORICAL_TYPE_TOKENS = ("CHAR", "VARCHAR", "TEXT", "STRING", "ENUM", "BOOLEAN")
_IDENTIFIER_NAME_TOKENS = ("id", "uuid", "guid", "key", "identifier")


@dataclass(frozen=True)
class AutoFEPlan:
    definition: FeatureEngineeringDefinition
    provenance: dict[str, Any]
    warnings: list[str]


@dataclass(frozen=True)
class AutoFERecipeSpec:
    """Versioned, engine-neutral identity of one complete AutoFE candidate."""

    contract_version: str
    capability_profile: str
    numeric_variant: str
    numeric_scaling: str
    winsorization: dict[str, float] | None
    signed_log_features: bool
    feature_selector: dict[str, Any] | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "capability_profile": self.capability_profile,
            "numeric_variant": self.numeric_variant,
            "numeric_scaling": self.numeric_scaling,
            "winsorization": self.winsorization,
            "signed_log_features": self.signed_log_features,
            "feature_selector": self.feature_selector,
        }


@dataclass(frozen=True)
class AutoFECrossValidationFold:
    fold: int
    training: SourceRelation
    validation: SourceRelation


@dataclass(frozen=True)
class AutoFECrossValidationPlan:
    strategy: str
    folds: list[AutoFECrossValidationFold]
    provenance: dict[str, Any]


def model_aware_autofe_plans(
    base_plan: AutoFEPlan,
    candidate_algorithms: list[str],
    *,
    max_candidates: int = 3,
    numeric_feature_search: bool = False,
    winsorization_lower_quantile: float = 0.01,
    winsorization_upper_quantile: float = 0.99,
    signed_log_features: bool = True,
    low_variance_selection: bool = True,
    variance_threshold: float = 0.0,
) -> list[AutoFEPlan]:
    """Derive model-compatible recipes from one full-scope profiling pass."""

    grouped: dict[str, list[str]] = {}
    for algorithm in candidate_algorithms:
        profile = algorithm_spec(algorithm).feature_engineering_profile
        grouped.setdefault(profile, []).append(algorithm)
    preferred_order = ["scaled_dense", "tree_unscaled", "non_negative"]
    ordered_profiles = [profile for profile in preferred_order if profile in grouped]
    ordered_profiles.extend(sorted(set(grouped) - set(ordered_profiles)))
    plans: list[AutoFEPlan] = []
    variants = ["baseline"]
    if numeric_feature_search:
        variants.append("robust_generated")
    candidate_pairs = [
        (profile, variant)
        for variant in variants
        for profile in ordered_profiles
    ]
    for profile, variant in candidate_pairs[:max_candidates]:
        definition = base_plan.definition.model_copy(deep=True)
        transformations = [
            transform
            for transform in definition.transformations
            if transform.transform_id not in {
                "autofe_numeric_scaling",
                "autofe_numeric_winsorization",
                "autofe_numeric_signed_log",
                "autofe_low_variance_selection",
            }
        ]
        numeric_columns = [
            str(item["column"])
            for item in base_plan.provenance.get("column_decisions", [])
            if item.get("role") == "numeric" and item.get("column")
        ]
        scaling = {
            "scaled_dense": "standard",
            "tree_unscaled": "none",
            "non_negative": "minmax",
        }.get(profile, "standard")
        enhanced = variant == "robust_generated" and bool(numeric_columns)
        generated_columns = []
        if enhanced:
            numeric_insert_at = next(
                (
                    index for index, item in enumerate(transformations)
                    if item.type not in {"impute"}
                ),
                len(transformations),
            )
            transformations.insert(numeric_insert_at, FeatureTransformation(
                transform_id="autofe_numeric_winsorization",
                type="winsorize_numeric",
                columns=numeric_columns,
                config={
                    "lower_quantile": winsorization_lower_quantile,
                    "upper_quantile": winsorization_upper_quantile,
                },
            ))
            if signed_log_features and profile != "non_negative":
                generated_columns = [f"{column}__signed_log1p" for column in numeric_columns]
                transformations.insert(numeric_insert_at + 1, FeatureTransformation(
                    transform_id="autofe_numeric_signed_log",
                    type="math_transform",
                    columns=numeric_columns,
                    config={
                        "operation": "signed_log1p",
                        "output_suffix": "__signed_log1p",
                        "drop_original": False,
                    },
                ))
        scale_columns = numeric_columns + generated_columns
        if scale_columns and scaling != "none":
            scaling_transform = FeatureTransformation(
                transform_id="autofe_numeric_scaling",
                type="scale_numeric",
                columns=scale_columns,
                config={
                    "method": scaling,
                    "output_suffix": "__scaled",
                    "drop_original": True,
                },
            )
            insert_at = next(
                (
                    index
                    for index, item in enumerate(transformations)
                    if item.type in {"encode_categorical", "datetime_features"}
                ),
                len(transformations),
            )
            transformations.insert(insert_at, scaling_transform)
        selector_columns = (
            [f"{column}__scaled" for column in scale_columns]
            if scaling != "none" else scale_columns
        )
        if enhanced and low_variance_selection and selector_columns:
            transformations.append(FeatureTransformation(
                transform_id="autofe_low_variance_selection",
                type="variance_filter",
                columns=selector_columns,
                config={"threshold": variance_threshold},
            ))
        definition = definition.model_copy(update={"transformations": transformations})
        decisions = []
        for raw_decision in base_plan.provenance.get("column_decisions", []):
            decision = dict(raw_decision)
            if decision.get("role") == "numeric":
                decision["action"] = {
                    "scaled_dense": "impute_and_standard_scale",
                    "tree_unscaled": "impute_without_scaling",
                    "non_negative": "impute_and_minmax_scale",
                }.get(profile, decision.get("action"))
            decisions.append(decision)
        recipe_id = profile if variant == "baseline" else f"{profile}__{variant}"
        recipe_contract = AutoFERecipeSpec(
            contract_version="2.0",
            capability_profile=profile,
            numeric_variant=variant,
            numeric_scaling=scaling,
            winsorization=(
                {
                    "lower_quantile": winsorization_lower_quantile,
                    "upper_quantile": winsorization_upper_quantile,
                }
                if enhanced else None
            ),
            signed_log_features=bool(generated_columns),
            feature_selector=(
                {"type": "variance_filter", "threshold": variance_threshold}
                if enhanced and low_variance_selection else None
            ),
        ).as_dict()
        provenance = {
            **base_plan.provenance,
            "planner": "duckdb_model_aware_tabular_v3",
            "recipe_search_mode": "joint_model_aware_holdout",
            "recipe_id": recipe_id,
            "feature_capability_profile": profile,
            "compatible_algorithms": list(grouped[profile]),
            "numeric_scaling": scaling,
            "recipe_contract": recipe_contract,
            "column_decisions": decisions,
            "resolved_recipe": definition.model_dump(mode="json"),
            "recipe_hash": _autofe_recipe_hash(definition, recipe_contract),
        }
        plans.append(AutoFEPlan(
            definition=definition,
            provenance=provenance,
            warnings=list(base_plan.warnings),
        ))
    return plans


class DuckDbAutoFEPlanner:
    """Build a bounded, auditable tabular FE recipe from full-scope aggregates."""

    def __init__(self, repository_root: Path | None = None) -> None:
        self.repository_root = (repository_root or Path("data/repository")).resolve()

    def plan(
        self,
        *,
        training: SourceRelation,
        validation: SourceRelation | None,
        test: SourceRelation | None,
        training_definition: Any,
        run_id: str,
        owner_id: str,
    ) -> AutoFEPlan:
        config = training_definition.auto_feature_engineering
        temp = self.repository_root / "users" / owner_id / "pipeline-runs" / run_id / ".autofe-plan"
        connection = configured_duckdb_connection(temp)
        try:
            schema_rows = connection.execute(
                f"DESCRIBE SELECT * FROM {training.sql} AS autofe_training"
            ).fetchall()
            schema = {str(row[0]): str(row[1]).upper() for row in schema_rows}
            if training_definition.target_column not in schema:
                raise ValueError(
                    f"AutoFE target column '{training_definition.target_column}' was not found"
                )
            inherited_row_id_column = self._upstream_row_id_column(training, schema)
            row_id_column = config.row_id_column or inherited_row_id_column
            row_count = int(connection.execute(
                f"SELECT count(*) FROM {training.sql} AS autofe_training"
            ).fetchone()[0])
            if row_count < 2:
                raise ValueError("AutoFE requires at least two training rows")

            excluded = {
                training_definition.target_column,
                row_id_column,
                *config.excluded_columns,
                *(name for name in schema if self._is_internal_column(name)),
            }
            requested = (
                list(training_definition.feature_columns)
                if training_definition.feature_selection == "explicit"
                else []
            )
            candidates = requested or [name for name in schema if name not in excluded]
            unknown = sorted(set(candidates) - set(schema))
            if unknown:
                raise ValueError("AutoFE feature columns were not found: " + ", ".join(unknown))
            candidates = [name for name in candidates if name not in excluded]
            if not candidates:
                raise ValueError("AutoFE found no candidate feature columns after exclusions")

            profile = self._profile_columns(connection, training, candidates, row_count)
            decisions: list[dict[str, Any]] = []
            numeric: list[str] = []
            categorical_one_hot: list[str] = []
            categorical_frequency: list[str] = []
            temporal: list[str] = []
            warnings = [
                "AutoFE cardinality decisions use full-scope approximate distinct counts; "
                "the processed row count and approximation are recorded in provenance"
            ]

            for column in candidates:
                column_type = schema[column]
                stats = profile[column]
                decision = {
                    "column": column,
                    "type": column_type,
                    "null_count": stats["null_count"],
                    "approx_distinct_count": stats["approx_distinct_count"],
                }
                if self._is_numeric(column_type):
                    numeric.append(column)
                    decision.update({"role": "numeric", "action": "impute_and_scale"})
                elif self._is_temporal(column_type) and config.include_datetime_features:
                    temporal.append(column)
                    decision.update({"role": "datetime", "action": "calendar_components"})
                elif self._is_categorical(column_type):
                    distinct = stats["approx_distinct_count"]
                    if (
                        config.detect_identifier_columns
                        and self._looks_like_identifier(column)
                        and distinct >= max(2, int(row_count * 0.98))
                    ):
                        decision.update({
                            "role": "identifier",
                            "action": "exclude",
                            "reason": "identifier-like name and near-unique values",
                        })
                        warnings.append(
                            f"AutoFE excluded likely identifier column '{column}' from model features"
                        )
                    elif distinct <= config.max_one_hot_categories:
                        categorical_one_hot.append(column)
                        decision.update({"role": "categorical", "action": "one_hot"})
                    else:
                        categorical_frequency.append(column)
                        decision.update({
                            "role": "categorical",
                            "action": "frequency_encode",
                            "bounded_categories": config.max_frequency_categories,
                        })
                else:
                    decision.update({
                        "role": "unsupported",
                        "action": "exclude",
                        "reason": "unsupported physical type for tabular AutoFE v1",
                    })
                    warnings.append(
                        f"AutoFE excluded unsupported column '{column}' ({column_type})"
                    )
                decisions.append(decision)

            selected = numeric + categorical_one_hot + categorical_frequency + temporal
            if not selected:
                raise ValueError("AutoFE found no executable numeric, categorical or datetime features")
            transformations = self._transformations(
                numeric=numeric,
                one_hot=categorical_one_hot,
                frequency=categorical_frequency,
                temporal=temporal,
                profile=profile,
                config=config,
            )
            inputs = [FeatureInput(input_id="training", role="training")]
            uses_fold_local_cv = (
                training_definition.optimization.validation_strategy == "cross_validation"
            )
            if validation is not None:
                inputs.append(FeatureInput(input_id="validation", role="validation"))
                output_input_ids = {"training": "training", "validation": "validation"}
                evaluation = EvaluationConfig(split_strategy="predefined")
                validation_source = (
                    "explicit_post_cv_evaluation" if uses_fold_local_cv else "explicit"
                )
            elif uses_fold_local_cv:
                if not row_id_column:
                    raise ValueError(
                        "Fold-local AutoFE requires a stable row_id_column"
                    )
                if row_id_column not in schema:
                    raise ValueError(
                        f"AutoFE row ID column '{row_id_column}' was not found"
                    )
                output_input_ids = {"training": "training"}
                evaluation = EvaluationConfig(split_strategy="predefined")
                validation_source = "fold_local_cross_validation"
            else:
                if not row_id_column:
                    raise ValueError(
                        "AutoFE v1 requires an explicit validation input or row_id_column "
                        "for a deterministic holdout"
                    )
                if row_id_column not in schema:
                    raise ValueError(
                        f"AutoFE row ID column '{row_id_column}' was not found"
                    )
                split_strategy = (
                    "stratified"
                    if training_definition.problem_type in {
                        "binary_classification", "multiclass_classification",
                    }
                    else "random"
                )
                evaluation = EvaluationConfig(
                    split_strategy=split_strategy,
                    validation_size=config.validation_size,
                    test_size=0,
                    seed=training_definition.random_seed,
                    stratify_column=(
                        training_definition.target_column if split_strategy == "stratified" else ""
                    ),
                )
                output_input_ids = {"training": "training", "validation": "validation"}
                validation_source = f"generated_{split_strategy}_holdout"
            if test is not None:
                inputs.append(FeatureInput(input_id="test", role="test"))
                output_input_ids["test"] = "test"

            outputs = [
                FeatureOutput(
                    output_id=f"autofe_{role}",
                    input_id=input_id,
                    dataset_name=f"{training_definition.model_name} AutoFE {role} features",
                    business_case_role=role,
                )
                for role, input_id in output_input_ids.items()
            ]

            definition = FeatureEngineeringDefinition(
                mode="fit_transform",
                inputs=inputs,
                feature_columns=selected,
                target_column=training_definition.target_column,
                row_id_column=row_id_column,
                transformations=transformations,
                outputs=outputs,
                evaluation=evaluation,
            )
            recipe_contract = AutoFERecipeSpec(
                contract_version="2.0",
                capability_profile="balanced",
                numeric_variant="baseline",
                numeric_scaling=config.numeric_scaling,
                winsorization=None,
                signed_log_features=False,
                feature_selector=None,
            ).as_dict()
            provenance = {
                "contract_version": "2.0",
                "planner": "duckdb_rule_based_tabular_v1",
                "strategy": config.strategy,
                "supported_problem_scope": "classification_and_regression",
                "recipe_search_mode": "fixed_planned_recipe",
                "data_scope": "full",
                "profiled_row_count": row_count,
                "cardinality_estimator": "approx_count_distinct",
                "cardinality_is_approximate": True,
                "validation_source": validation_source,
                "inherited_row_id_column": inherited_row_id_column,
                "column_decisions": decisions,
                "resolved_recipe": definition.model_dump(mode="json"),
                "recipe_contract": recipe_contract,
                "recipe_hash": _autofe_recipe_hash(definition, recipe_contract),
            }
            return AutoFEPlan(definition=definition, provenance=provenance, warnings=warnings)
        finally:
            connection.close()

    def cross_validation_plan(
        self,
        *,
        training: SourceRelation,
        training_definition: Any,
        run_id: str,
        owner_id: str,
    ) -> AutoFECrossValidationPlan:
        """Build deterministic raw-data folds before any learned FE is fitted."""

        config = training_definition.auto_feature_engineering
        row_id_column = config.row_id_column or self._upstream_row_id_column_from_relation(
            training
        )
        if not row_id_column:
            raise ValueError(
                "Fold-local AutoFE requires a stable row_id_column so every recipe "
                "uses the same reproducible folds"
            )
        fold_count = int(training_definition.optimization.cv_folds)
        seed = int(training_definition.random_seed)
        temp = (
            self.repository_root / "users" / owner_id / "pipeline-runs" / run_id
            / ".autofe-cv-plan"
        )
        connection = configured_duckdb_connection(temp)
        try:
            schema_rows = connection.execute(
                f"DESCRIBE SELECT * FROM {training.sql} AS autofe_cv_schema"
            ).fetchall()
            schema = {str(row[0]) for row in schema_rows}
            if row_id_column not in schema:
                raise ValueError(
                    f"AutoFE row ID column '{row_id_column}' was not found"
                )
            target_column = str(training_definition.target_column)
            if target_column not in schema:
                raise ValueError(
                    f"AutoFE target column '{target_column}' was not found"
                )
            key = (
                f"hash(concat(CAST({identifier(row_id_column)} AS VARCHAR), "
                f"'|', CAST({seed} AS VARCHAR)))"
            )
            if training_definition.problem_type in {
                "binary_classification", "multiclass_classification",
            }:
                fold_expression = (
                    f"(row_number() OVER (PARTITION BY {identifier(target_column)} "
                    f"ORDER BY {key}) - 1) % {fold_count}"
                )
                strategy = "stratified_kfold"
            else:
                fold_expression = f"{key} % {fold_count}"
                strategy = "kfold"
            folded_sql = (
                "(SELECT *, CAST("
                + fold_expression
                + " AS INTEGER) AS __mlapp_autofe_fold "
                + f"FROM {training.sql} AS autofe_cv_source)"
            )
            count_rows = connection.execute(
                "SELECT __mlapp_autofe_fold, count(*) "
                f"FROM {folded_sql} AS autofe_cv_counts "
                "GROUP BY __mlapp_autofe_fold ORDER BY __mlapp_autofe_fold"
            ).fetchall()
            counts = {int(row[0]): int(row[1]) for row in count_rows}
            missing = [fold for fold in range(fold_count) if not counts.get(fold)]
            if missing:
                raise ValueError(
                    "Fold-local AutoFE produced empty validation folds: "
                    + ", ".join(str(item) for item in missing)
                )
            total = sum(counts.values())
            folds = [
                AutoFECrossValidationFold(
                    fold=fold,
                    training=SourceRelation(
                        sql=(
                            "(SELECT * EXCLUDE (__mlapp_autofe_fold) "
                            f"FROM {folded_sql} AS autofe_cv_train "
                            f"WHERE __mlapp_autofe_fold <> {fold})"
                        ),
                        row_count=total - counts[fold],
                        metadata={**training.metadata, "autofe_cv_fold": fold, "role": "training"},
                    ),
                    validation=SourceRelation(
                        sql=(
                            "(SELECT * EXCLUDE (__mlapp_autofe_fold) "
                            f"FROM {folded_sql} AS autofe_cv_validation "
                            f"WHERE __mlapp_autofe_fold = {fold})"
                        ),
                        row_count=counts[fold],
                        metadata={**training.metadata, "autofe_cv_fold": fold, "role": "validation"},
                    ),
                )
                for fold in range(fold_count)
            ]
            return AutoFECrossValidationPlan(
                strategy=strategy,
                folds=folds,
                provenance={
                    "strategy": strategy,
                    "fold_count": fold_count,
                    "seed": seed,
                    "row_id_column": row_id_column,
                    "data_scope": "full",
                    "planned_row_count": total,
                    "fold_row_counts": [
                        {"fold": fold, "validation_row_count": counts[fold]}
                        for fold in range(fold_count)
                    ],
                    "fold_assignment_stage": "raw_before_feature_engineering",
                },
            )
        finally:
            connection.close()

    @staticmethod
    def _upstream_row_id_column_from_relation(training: SourceRelation) -> str:
        for item in training.metadata.get("feature_manifest") or []:
            if isinstance(item, dict) and item.get("role") == "row_id" and item.get("name"):
                return str(item["name"])
        return ""

    @staticmethod
    def _upstream_row_id_column(training: SourceRelation, schema: dict[str, str]) -> str:
        """Read the row-ID contract carried by an upstream FE output, if present."""
        for item in training.metadata.get("feature_manifest") or []:
            if not isinstance(item, dict) or item.get("role") != "row_id":
                continue
            column = str(item.get("name") or "")
            if column in schema:
                return column
        return ""

    @staticmethod
    def _profile_columns(connection, source: SourceRelation, columns: list[str], row_count: int) -> dict[str, dict[str, int]]:
        result: dict[str, dict[str, int]] = {}
        for start in range(0, len(columns), 64):
            chunk = columns[start:start + 64]
            expressions: list[str] = []
            for column in chunk:
                expressions.extend([
                    f"count(*) FILTER (WHERE {identifier(column)} IS NULL)",
                    f"approx_count_distinct({identifier(column)})",
                ])
            row = connection.execute(
                "SELECT " + ", ".join(expressions)
                + f" FROM {source.sql} AS autofe_profile"
            ).fetchone()
            for index, column in enumerate(chunk):
                result[column] = {
                    "null_count": int(row[index * 2] or 0),
                    "approx_distinct_count": min(row_count, int(row[index * 2 + 1] or 0)),
                }
        return result

    @staticmethod
    def _transformations(*, numeric, one_hot, frequency, temporal, profile, config) -> list[FeatureTransformation]:
        transforms: list[FeatureTransformation] = []
        numeric_missing = [column for column in numeric if profile[column]["null_count"]]
        temporal_missing = [column for column in temporal if profile[column]["null_count"]]
        if numeric_missing:
            transforms.append(FeatureTransformation(
                transform_id="autofe_numeric_imputation",
                type="impute",
                columns=numeric_missing,
                config={"method": "median", "add_indicator": config.add_missing_indicators},
            ))
        if temporal_missing:
            transforms.append(FeatureTransformation(
                transform_id="autofe_datetime_imputation",
                type="impute",
                columns=temporal_missing,
                config={"method": "mode", "add_indicator": config.add_missing_indicators},
            ))
        if numeric and config.numeric_scaling != "none":
            transforms.append(FeatureTransformation(
                transform_id="autofe_numeric_scaling",
                type="scale_numeric",
                columns=numeric,
                config={
                    "method": config.numeric_scaling,
                    "output_suffix": "__scaled",
                    "drop_original": True,
                },
            ))
        if one_hot:
            transforms.append(FeatureTransformation(
                transform_id="autofe_one_hot",
                type="encode_categorical",
                columns=one_hot,
                config={
                    "method": "one_hot",
                    "min_frequency": config.min_category_frequency,
                    "max_categories": config.max_one_hot_categories,
                    "handle_unknown": "other",
                    "drop_original": True,
                },
            ))
        if frequency:
            transforms.append(FeatureTransformation(
                transform_id="autofe_frequency",
                type="encode_categorical",
                columns=frequency,
                config={
                    "method": "frequency",
                    "min_frequency": config.min_category_frequency,
                    "max_categories": config.max_frequency_categories,
                    "handle_unknown": "other",
                    "drop_original": True,
                },
            ))
        if temporal:
            transforms.append(FeatureTransformation(
                transform_id="autofe_datetime",
                type="datetime_features",
                columns=temporal,
                config={
                    "features": ["year", "quarter", "month", "day_of_week", "is_weekend"],
                    "cyclical": True,
                    "drop_original": True,
                },
            ))
        return transforms

    @staticmethod
    def _is_numeric(column_type: str) -> bool:
        return any(token in column_type for token in _NUMERIC_TYPE_TOKENS)

    @staticmethod
    def _is_temporal(column_type: str) -> bool:
        return any(token in column_type for token in _TEMPORAL_TYPE_TOKENS)

    @staticmethod
    def _is_categorical(column_type: str) -> bool:
        return any(token in column_type for token in _CATEGORICAL_TYPE_TOKENS)

    @staticmethod
    def _looks_like_identifier(column: str) -> bool:
        normalized = column.lower().replace("-", "_")
        parts = {part for part in normalized.split("_") if part}
        return bool(parts & set(_IDENTIFIER_NAME_TOKENS)) or normalized.endswith("id")

    @staticmethod
    def _is_internal_column(column: str) -> bool:
        return column.lower().startswith("__mlapp_")


def _autofe_recipe_hash(
    definition: FeatureEngineeringDefinition,
    recipe_contract: dict[str, Any] | None = None,
) -> str:
    payload = {
        "contract_version": definition.contract_version,
        "feature_columns": definition.feature_columns,
        "target_column": definition.target_column,
        "row_id_column": definition.row_id_column,
        "group_column": definition.group_column,
        "event_time_column": definition.event_time_column,
        "transformations": [
            item.model_dump(mode="json") for item in definition.transformations
        ],
        "recipe_contract": recipe_contract or {},
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
