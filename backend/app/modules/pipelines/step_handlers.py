from __future__ import annotations

import math
import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from sklearn.base import clone
from sklearn.metrics import get_scorer

from app.modules.pipelines.dag import PipelineDefinition
from app.modules.pipelines.autofe import (
    AutoFEPlan,
    AutoFECrossValidationPlan,
    DuckDbAutoFEPlanner,
    model_aware_autofe_plans,
)
from app.modules.pipelines.execution import DuckDbPipelineExecutionEngine
from app.modules.pipelines.feature_engineering import (
    DuckDbFeatureEngineeringEngine,
    EvaluationConfig,
    FeatureEngineeringDefinition,
    FeatureInput,
    FeatureOutput,
)
from app.modules.pipelines.modeling import (
    ScoringDefinition,
    SklearnScoringEngine,
    SklearnTrainingEngine,
    TrainingDefinition,
)
from app.modules.pipelines.modeling_catalog import automl_algorithms
from app.modules.pipelines.domain import PipelineExecutionCancelled
from app.modules.pipelines.monitoring import DuckDbMonitoringEngine, MonitoringDefinition
from app.modules.pipelines.runtime import SourceRelation, sql_literal
from app.modules.pipelines.workflow import WorkflowStep
from app.modules.business_cases.domain import ArtifactType
from app.modules.business_cases.repository import (
    BusinessCaseRepository,
    PostgresBusinessCaseRepository,
)
from app.shared.duckdb_runtime import configured_duckdb_connection


@dataclass(frozen=True)
class StepExecutionContext:
    run_id: str
    owner_id: str
    is_dry_run: bool
    upstream_relations: dict[tuple[str, str], SourceRelation]
    upstream_artifacts: dict[tuple[str, str], dict] = field(default_factory=dict)
    emit_event: Callable[[str, dict[str, Any]], None] | None = None
    is_cancel_requested: Callable[[], bool] | None = None


@dataclass(frozen=True)
class HandledStepResult:
    input_row_count: int
    processed_row_count: int
    output_row_count: int
    warnings: list[str]
    output_manifest: list[dict]
    input_dataset_ids: list[str]
    relation_output_ids: dict[str, str]
    artifact_output_ids: dict[str, str] = field(default_factory=dict)
    relation_passthroughs: dict[str, tuple[str, str]] = field(default_factory=dict)
    external_input_artifact_ids: list[str] = field(default_factory=list)
    external_input_lineage: list[dict] = field(default_factory=list)


class PipelineStepHandler(Protocol):
    step_type: str

    def execute(
        self,
        step: WorkflowStep,
        context: StepExecutionContext,
    ) -> HandledStepResult:
        ...


class DataEngineeringStepHandler:
    step_type = "data_engineering"

    def __init__(self, engine: DuckDbPipelineExecutionEngine | None = None) -> None:
        self.engine = engine or DuckDbPipelineExecutionEngine()

    def execute(
        self,
        step: WorkflowStep,
        context: StepExecutionContext,
    ) -> HandledStepResult:
        definition = PipelineDefinition.model_validate(step.config["definition"])
        result = self.engine.execute(
            definition=definition,
            run_id=context.run_id,
            owner_id=context.owner_id,
            is_dry_run=context.is_dry_run,
        )
        dataset_outputs = [
            item
            for item in result.output_manifest
            if item.get("quality_output_kind") != "rejected_records"
        ]
        if not dataset_outputs:
            raise ValueError("Data Engineering produced no workflow output")
        return HandledStepResult(
            input_row_count=result.input_row_count,
            processed_row_count=result.processed_row_count,
            output_row_count=result.output_row_count,
            warnings=list(result.warnings),
            output_manifest=list(result.output_manifest),
            input_dataset_ids=_input_dataset_ids(definition.inputs),
            relation_output_ids={
                step.output_port_id: str(dataset_outputs[0]["output_id"]),
            },
            artifact_output_ids={},
        )


class FeatureEngineeringStepHandler:
    step_type = "feature_engineering"

    def __init__(self, engine: DuckDbFeatureEngineeringEngine | None = None) -> None:
        self.engine = engine or DuckDbFeatureEngineeringEngine()

    def execute(
        self,
        step: WorkflowStep,
        context: StepExecutionContext,
    ) -> HandledStepResult:
        definition = FeatureEngineeringDefinition.model_validate(step.config["definition"])
        bindings: dict[str, SourceRelation] = {}
        for port in step.inputs:
            source = context.upstream_relations.get(
                (port.source.step_id, port.source.port_id)
            )
            if source is None:
                raise ValueError(
                    f"Feature Engineering input '{port.port_id}' "
                    "has no executable upstream output"
                )
            bindings[port.port_id] = source
        result = self.engine.execute(
            definition=definition,
            run_id=context.run_id,
            owner_id=context.owner_id,
            is_dry_run=context.is_dry_run,
            upstream_relations=bindings,
        )
        relation_output_ids: dict[str, str] = {}
        declared_ports = {
            step.output_port_id,
            *step.additional_output_port_ids,
        }
        for item in result.output_manifest:
            if item.get("artifact_type", "dataset") != "dataset":
                continue
            role = str(item.get("business_case_role") or "training")
            if role not in declared_ports:
                raise ValueError(
                    f"Feature Engineering produced undeclared output role '{role}'"
                )
            relation_output_ids[role] = str(item["output_id"])
        return HandledStepResult(
            input_row_count=result.input_row_count,
            processed_row_count=result.processed_row_count,
            output_row_count=result.output_row_count,
            warnings=list(result.warnings),
            output_manifest=list(result.output_manifest),
            input_dataset_ids=_input_dataset_ids(definition.inputs),
            relation_output_ids=relation_output_ids,
            artifact_output_ids={
                "fitted_transform": "fitted_transform"
            } if definition.mode == "fit_transform" else {},
            external_input_artifact_ids=(
                [definition.fitted_state_artifact_id]
                if definition.mode == "transform" else []
            ),
            external_input_lineage=(
                [{
                    "input_port_id": "fitted_transform",
                    "artifact_ids": [definition.fitted_state_artifact_id],
                }]
                if definition.mode == "transform" else []
            ),
        )


class TrainingStepHandler:
    step_type = "training"

    def __init__(self, engine: SklearnTrainingEngine | None = None) -> None:
        self.engine = engine or SklearnTrainingEngine()

    def execute(self, step: WorkflowStep, context: StepExecutionContext) -> HandledStepResult:
        definition = TrainingDefinition.model_validate(step.config["definition"])
        sources = {
            port.port_id: context.upstream_relations.get(
                (port.source.step_id, port.source.port_id)
            )
            for port in step.inputs
        }
        training = sources.get("training")
        if training is None:
            raise ValueError("Training step requires a bound 'training' dataset input")
        if definition.feature_selection == "upstream_contract":
            resolved_features = [
                str(item.get("name"))
                for item in training.metadata.get("feature_manifest", [])
                if item.get("role") == "feature" and item.get("name")
            ]
            if resolved_features:
                definition = definition.model_copy(
                    update={"feature_columns": resolved_features}
                )
        result = self.engine.execute(
            definition,
            training,
            sources.get("validation"),
            run_id=context.run_id,
            owner_id=context.owner_id,
            is_dry_run=context.is_dry_run,
            emit_event=context.emit_event,
            is_cancel_requested=context.is_cancel_requested,
        )
        test_port = next((port for port in step.inputs if port.port_id == "test"), None)
        return HandledStepResult(
            input_row_count=result.input_row_count,
            processed_row_count=result.processed_row_count,
            output_row_count=result.output_row_count,
            warnings=result.warnings,
            output_manifest=result.output_manifest,
            input_dataset_ids=[],
            relation_output_ids={},
            artifact_output_ids={"model": "model", "metrics": "training_metrics"},
            relation_passthroughs=(
                {"test": (test_port.source.step_id, test_port.source.port_id)}
                if test_port is not None and "test" in step.additional_output_port_ids
                else {}
            ),
        )


class AutoMLStepHandler(TrainingStepHandler):
    """Governed AutoML entry point with optional leakage-safe tabular AutoFE."""

    step_type = "automl"

    def __init__(
        self,
        engine: SklearnTrainingEngine | None = None,
        feature_engine: DuckDbFeatureEngineeringEngine | None = None,
        planner: DuckDbAutoFEPlanner | None = None,
    ) -> None:
        super().__init__(engine)
        self.feature_engine = feature_engine or DuckDbFeatureEngineeringEngine()
        self.planner = planner or DuckDbAutoFEPlanner(
            repository_root=self.feature_engine.repository_root
        )

    def execute(self, step: WorkflowStep, context: StepExecutionContext) -> HandledStepResult:
        definition = TrainingDefinition.model_validate(step.config["definition"])
        if definition.optimization.mode != "automl":
            raise ValueError("AutoML step requires optimization mode 'automl'")
        if not definition.auto_feature_engineering.enabled:
            return super().execute(step, context)

        sources = {
            port.port_id: context.upstream_relations.get(
                (port.source.step_id, port.source.port_id)
            )
            for port in step.inputs
        }
        raw_training = sources.get("training")
        if raw_training is None:
            raise ValueError("AutoML AutoFE requires a bound 'training' dataset input")
        raw_validation = sources.get("validation")
        raw_test = sources.get("test")
        if context.emit_event:
            context.emit_event("autofe.planning_started", {
                "message": "Profiling the full training scope for AutoFE",
                "row_count": raw_training.row_count,
            })
        plan = self.planner.plan(
            training=raw_training,
            validation=raw_validation,
            test=raw_test,
            training_definition=definition,
            run_id=context.run_id,
            owner_id=context.owner_id,
        )
        uses_fold_local_cv = (
            definition.optimization.validation_strategy == "cross_validation"
        )
        if uses_fold_local_cv and int(raw_training.metadata.get("fitted_transform_count") or 0):
            raise ValueError(
                "Fold-local AutoFE requires pre-FE training data. The connected input "
                "already contains state fitted on the complete training partition; connect "
                "the Data Engineering output directly or use holdout validation for the "
                "human-made FE pipeline."
            )
        cv_plan = (
            self.planner.cross_validation_plan(
                training=raw_training,
                training_definition=definition,
                run_id=context.run_id,
                owner_id=context.owner_id,
            )
            if uses_fold_local_cv else None
        )
        candidate_algorithms = (
            list(definition.optimization.candidate_algorithms)
            or automl_algorithms(definition.problem_type)
        )
        recipe_configuration = definition.auto_feature_engineering
        generated_plans = (
            model_aware_autofe_plans(
                plan,
                candidate_algorithms,
                max_candidates=(
                    24
                    if recipe_configuration.numeric_recipe_search_v2
                    else recipe_configuration.max_recipe_candidates
                ),
                numeric_feature_search=(
                    definition.auto_feature_engineering.numeric_feature_search
                ),
                numeric_recipe_search_v2=(
                    definition.auto_feature_engineering.numeric_recipe_search_v2
                ),
                numeric_scaling_search=(
                    definition.auto_feature_engineering.numeric_scaling_search
                ),
                numeric_scaling_candidates=list(
                    definition.auto_feature_engineering.numeric_scaling_candidates
                ),
                winsorization_lower_quantile=(
                    definition.auto_feature_engineering.winsorization_lower_quantile
                ),
                winsorization_upper_quantile=(
                    definition.auto_feature_engineering.winsorization_upper_quantile
                ),
                signed_log_features=(
                    definition.auto_feature_engineering.signed_log_features
                ),
                low_variance_selection=(
                    definition.auto_feature_engineering.low_variance_selection
                ),
                variance_threshold=(
                    definition.auto_feature_engineering.variance_threshold
                ),
                profile_aware_generation=recipe_configuration.profile_aware_generation,
                distribution_transformations=(
                    recipe_configuration.distribution_transformations
                ),
                numeric_interactions=recipe_configuration.numeric_interactions,
                interaction_operators=list(recipe_configuration.interaction_operators),
                max_generated_features=recipe_configuration.max_generated_features,
                max_interaction_features=recipe_configuration.max_interaction_features,
                skewness_threshold=recipe_configuration.skewness_threshold,
            )
            if definition.auto_feature_engineering.joint_search_enabled
            else [plan]
        )
        configured_plans = generated_plans[:recipe_configuration.max_recipe_candidates]
        cap_skipped_recipe_candidates = [
            {
                "recipe_id": str(item.provenance.get("recipe_id") or "recipe"),
                "recipe_hash": str(item.provenance.get("recipe_hash") or ""),
                "recipe_contract": dict(item.provenance.get("recipe_contract") or {}),
                "status": "skipped",
                "reason": "explicit max_recipe_candidates cap",
            }
            for item in generated_plans[recipe_configuration.max_recipe_candidates:]
        ]
        uses_two_phase_scheduler = (
            recipe_configuration.two_phase_search_enabled
            and recipe_configuration.joint_search_enabled
            and len(configured_plans) > 1
        )
        exploration_trials_per_recipe = (
            recipe_configuration.exploration_trials_per_recipe
            if uses_two_phase_scheduler else 1
        )
        executable_recipe_limit = min(
            len(configured_plans),
            definition.optimization.max_trials // exploration_trials_per_recipe,
            max(1, definition.optimization.timeout_seconds // 10),
        )
        plans = configured_plans[:executable_recipe_limit]
        budget_skipped_recipe_candidates = [
            {
                "recipe_id": str(item.provenance.get("recipe_id") or "recipe"),
                "recipe_hash": str(item.provenance.get("recipe_hash") or ""),
                "recipe_contract": dict(item.provenance.get("recipe_contract") or {}),
                "status": "skipped",
                "reason": "global trial or wall-clock budget cannot allocate a minimum evaluation",
            }
            for item in configured_plans[executable_recipe_limit:]
        ]
        skipped_recipe_candidates = [
            *cap_skipped_recipe_candidates,
            *budget_skipped_recipe_candidates,
        ]
        if not plans:
            raise ValueError("AutoFE found no model-aware recipe candidates")
        evaluated_algorithms = list(dict.fromkeys(
            algorithm
            for recipe in plans
            for algorithm in (
                recipe.provenance.get("compatible_algorithms") or candidate_algorithms
            )
        ))
        skipped_algorithms = [
            algorithm for algorithm in candidate_algorithms
            if algorithm not in evaluated_algorithms
        ]
        if skipped_algorithms:
            candidate_warnings = [
                "AutoFE recipe limit excluded these configured algorithms from the joint "
                f"study: {', '.join(skipped_algorithms)}"
            ]
        else:
            candidate_warnings = []
        if cap_skipped_recipe_candidates:
            candidate_warnings.append(
                f"AutoFE skipped {len(cap_skipped_recipe_candidates)} recipe candidate(s) "
                "because of the explicit max_recipe_candidates cap"
            )
        if budget_skipped_recipe_candidates:
            candidate_warnings.append(
                f"AutoFE skipped {len(budget_skipped_recipe_candidates)} recipe candidate(s) because "
                "the global trial/time budget could not allocate a minimum evaluation"
            )
        if cv_plan is not None and definition.resource_limits.max_parallel_jobs > 1:
            candidate_warnings.append(
                "Fold-local AutoFE currently evaluates trials serially so run-scoped fitted "
                "state and memory accounting remain isolated and deterministic"
            )
        if context.emit_event:
            context.emit_event("autofe.plan_created", {
                "message": "AutoFE created model-aware tabular recipe candidates",
                "profiled_row_count": plan.provenance["profiled_row_count"],
                "recipe_candidate_count": len(plans),
                "configured_recipe_candidate_count": len(configured_plans),
                "generated_recipe_candidate_count": len(generated_plans),
                "skipped_recipe_candidates": skipped_recipe_candidates,
                "validation_source": plan.provenance["validation_source"],
                "evaluated_algorithms": evaluated_algorithms,
                "skipped_algorithms": skipped_algorithms,
                **({"cross_validation": cv_plan.provenance} if cv_plan else {}),
            })

        recipe_weights = [
            max(1, len(recipe.provenance.get("compatible_algorithms") or []))
            for recipe in plans
        ]
        if uses_two_phase_scheduler:
            trial_allocations = [exploration_trials_per_recipe] * len(plans)
            exploration_timeout_total = min(
                definition.optimization.timeout_seconds,
                max(
                    len(plans) * 10,
                    int(
                        definition.optimization.timeout_seconds
                        * recipe_configuration.exploration_time_fraction
                    ),
                ),
            )
            timeout_allocations = self._allocate_weighted_budget(
                exploration_timeout_total,
                recipe_weights,
                minimum=10,
            )
        else:
            trial_allocations = self._allocate_weighted_budget(
                definition.optimization.max_trials,
                recipe_weights,
                minimum=1,
            )
            timeout_allocations = self._allocate_weighted_budget(
                definition.optimization.timeout_seconds,
                recipe_weights,
                minimum=10,
            )

        processed_row_count = 0
        def evaluate_phase(
            recipe: AutoFEPlan,
            index: int,
            *,
            phase: str,
            trial_budget: int,
            timeout_budget: int,
            seed_offset: int,
        ) -> dict[str, Any]:
            nonlocal processed_row_count
            recipe_id = str(recipe.provenance.get("recipe_id") or f"recipe_{index + 1}")
            if context.is_cancel_requested and context.is_cancel_requested():
                raise PipelineExecutionCancelled("Pipeline run was cancelled")
            if context.emit_event:
                context.emit_event("autofe.recipe_trial_started", {
                    "message": f"Evaluating AutoFE recipe '{recipe_id}' in {phase}",
                    "recipe_id": recipe_id,
                    "phase": phase,
                    "candidate_algorithms": recipe.provenance.get("compatible_algorithms", []),
                    "trial_budget": trial_budget,
                    "timeout_budget_seconds": timeout_budget,
                })
            candidate_run_id = f"{context.run_id}/autofe-candidates/{recipe_id}/{phase}"
            try:
                candidate, warnings, phase_processed = self._evaluate_autofe_recipe_candidate(
                    recipe=recipe,
                    definition=definition,
                    raw_training=raw_training,
                    raw_validation=raw_validation,
                    cv_plan=cv_plan,
                    candidate_algorithms=candidate_algorithms,
                    context=context,
                    candidate_run_id=candidate_run_id,
                    phase=phase,
                    trial_budget=trial_budget,
                    timeout_budget=timeout_budget,
                    seed_offset=seed_offset,
                )
                processed_row_count += phase_processed
                candidate_warnings.extend(warnings)
                if context.emit_event:
                    context.emit_event("autofe.recipe_trial_completed", {
                        "message": f"AutoFE recipe '{recipe_id}' {phase} completed",
                        "recipe_id": recipe_id,
                        "phase": phase,
                        "best_score": candidate["score"],
                        "best_algorithm": candidate["best_algorithm"],
                        "resolved_feature_count": candidate["resolved_feature_count"],
                    })
                return candidate
            except PipelineExecutionCancelled:
                raise
            except Exception as exc:
                failed = {
                    "recipe": recipe,
                    "recipe_id": recipe_id,
                    "recipe_hash": recipe.provenance.get("recipe_hash"),
                    "recipe_contract": recipe.provenance.get("recipe_contract"),
                    "status": "failed",
                    "phase": phase,
                    "error": str(exc),
                    "score": None,
                    "trial_count": 0,
                    "allocated_trial_budget": trial_budget,
                    "allocated_timeout_seconds": timeout_budget,
                    "resolved_feature_count": 0,
                    "resolved_features": [],
                }
                if context.emit_event:
                    context.emit_event("autofe.recipe_trial_failed", {
                        "message": f"AutoFE recipe '{recipe_id}' failed in {phase}: {exc}",
                        "recipe_id": recipe_id,
                        "phase": phase,
                    })
                return failed
            finally:
                self._cleanup_candidate_run(context.owner_id, candidate_run_id)

        exploration_results = [
            evaluate_phase(
                recipe,
                index,
                phase="exploration" if uses_two_phase_scheduler else "flat_search",
                trial_budget=trial_allocations[index],
                timeout_budget=timeout_allocations[index],
                seed_offset=0,
            )
            for index, recipe in enumerate(plans)
        ]

        deepening_results: dict[str, dict[str, Any]] = {}
        promoted_recipe_ids: list[str] = []
        if uses_two_phase_scheduler:
            remaining_trials = definition.optimization.max_trials - sum(trial_allocations)
            remaining_timeout = definition.optimization.timeout_seconds - sum(timeout_allocations)
            ranked_exploration = sorted(
                (
                    item for item in exploration_results
                    if item["status"] == "succeeded"
                    and isinstance(item.get("score"), (int, float))
                ),
                key=lambda item: (-float(item["score"]), str(item["recipe_id"])),
            )
            promotion_count = min(
                recipe_configuration.promotion_top_k,
                len(ranked_exploration),
                remaining_trials,
                remaining_timeout // 10,
            )
            promoted = ranked_exploration[:promotion_count]
            promoted_recipe_ids = [str(item["recipe_id"]) for item in promoted]
            if promoted:
                plan_indexes = {
                    str(recipe.provenance.get("recipe_id") or f"recipe_{index + 1}"): index
                    for index, recipe in enumerate(plans)
                }
                promoted_weights = [recipe_weights[plan_indexes[item["recipe_id"]]] for item in promoted]
                deep_trial_allocations = self._allocate_weighted_budget(
                    remaining_trials,
                    promoted_weights,
                    minimum=1,
                )
                deep_timeout_allocations = self._allocate_weighted_budget(
                    remaining_timeout,
                    promoted_weights,
                    minimum=10,
                )
                if context.emit_event:
                    context.emit_event("autofe.deepening_started", {
                        "message": "AutoFE promoted the strongest exploration recipes",
                        "promoted_recipe_ids": promoted_recipe_ids,
                        "remaining_trial_budget": remaining_trials,
                        "remaining_timeout_seconds": remaining_timeout,
                    })
                for rank, explored in enumerate(promoted):
                    recipe_index = plan_indexes[str(explored["recipe_id"])]
                    deepening_results[str(explored["recipe_id"])] = evaluate_phase(
                        plans[recipe_index],
                        recipe_index,
                        phase="deepening",
                        trial_budget=deep_trial_allocations[rank],
                        timeout_budget=deep_timeout_allocations[rank],
                        seed_offset=10_000 + rank,
                    )
            elif remaining_trials or remaining_timeout >= 10:
                candidate_warnings.append(
                    "AutoFE two-phase scheduler could not deepen a recipe because no successful "
                    "exploration candidate or complete minimum budget remained"
                )

        study_candidates: list[dict[str, Any]] = []
        if not uses_two_phase_scheduler:
            study_candidates = exploration_results
        else:
            for explored in exploration_results:
                recipe_id = str(explored["recipe_id"])
                phase_snapshots = [{
                    key: value for key, value in explored.items() if key != "recipe"
                }]
                if explored["status"] != "succeeded":
                    explored["phases"] = phase_snapshots
                    study_candidates.append(explored)
                    continue
                deepened = deepening_results.get(recipe_id)
                if deepened is None:
                    candidate = dict(explored)
                    candidate["status"] = "pruned" if promoted_recipe_ids else "explored"
                    candidate["reason"] = (
                        "not promoted after exploration"
                        if promoted_recipe_ids else "no complete deepening budget remained"
                    )
                    candidate["phases"] = phase_snapshots
                    study_candidates.append(candidate)
                    continue
                phase_snapshots.append({
                    key: value for key, value in deepened.items() if key != "recipe"
                })
                best = (
                    max([explored, deepened], key=lambda item: float(item["score"]))
                    if deepened["status"] == "succeeded" else explored
                )
                candidate = dict(best)
                candidate["recipe"] = explored["recipe"]
                candidate["status"] = "promoted"
                candidate["trial_count"] = int(explored["trial_count"]) + int(deepened["trial_count"])
                candidate["processed_row_count"] = (
                    int(explored.get("processed_row_count") or 0)
                    + int(deepened.get("processed_row_count") or 0)
                )
                candidate["allocated_trial_budget"] = (
                    int(explored.get("allocated_trial_budget") or 0)
                    + int(deepened.get("allocated_trial_budget") or 0)
                )
                candidate["allocated_timeout_seconds"] = (
                    int(explored.get("allocated_timeout_seconds") or 0)
                    + int(deepened.get("allocated_timeout_seconds") or 0)
                )
                candidate["exploration_score"] = explored["score"]
                candidate["deepening_score"] = deepened.get("score")
                candidate["promotion_reason"] = "ranked within configured exploration top-k"
                candidate["phases"] = phase_snapshots
                if deepened["status"] != "succeeded":
                    candidate["deepening_error"] = deepened.get("error")
                study_candidates.append(candidate)

        successful = [
            item for item in study_candidates
            if item["status"] != "failed" and isinstance(item.get("score"), (int, float))
        ]
        if not successful:
            failures = "; ".join(
                f"{item['recipe_id']}: {item.get('error', 'unknown failure')}"
                for item in study_candidates
            )
            raise ValueError(f"Every model-aware AutoFE recipe failed: {failures}")
        winner = max(successful, key=lambda item: float(item["score"]))
        selected_plan = winner["recipe"]
        feature_result, prepared_training, prepared_validation, prepared_test, resolved_features = (
            self._prepare_features(
                selected_plan,
                raw_training,
                raw_validation,
                raw_test,
                run_id=context.run_id,
                owner_id=context.owner_id,
                is_dry_run=context.is_dry_run,
            )
        )
        processed_row_count += feature_result.processed_row_count
        final_optimization = definition.optimization.model_copy(update={
            "mode": "single",
            "candidate_algorithms": [],
            "search_space": {},
            "max_trials": 1,
        })
        executable_definition = definition.model_copy(update={
            "algorithm": winner["best_algorithm"],
            "parameters": winner["best_parameters"],
            "feature_columns": resolved_features,
            "feature_selection": "explicit",
            "early_stopping": False,
            "optimization": final_optimization,
            "auto_feature_engineering": definition.auto_feature_engineering.model_copy(
                update={"enabled": False}
            ),
        })
        training_result = self.engine.execute(
            executable_definition,
            prepared_training,
            prepared_validation,
            run_id=context.run_id,
            owner_id=context.owner_id,
            is_dry_run=context.is_dry_run,
            emit_event=context.emit_event,
            is_cancel_requested=context.is_cancel_requested,
        )
        processed_row_count += training_result.processed_row_count

        joint_study = {
            "mode": (
                "joint_model_aware_fold_local_cv"
                if cv_plan is not None and definition.auto_feature_engineering.joint_search_enabled
                else "fixed_recipe_fold_local_cv"
                if cv_plan is not None
                else "joint_model_aware_holdout"
                if definition.auto_feature_engineering.joint_search_enabled
                else "fixed_recipe_model_search"
            ),
            "primary_metric": definition.optimization.primary_metric,
            "trial_budget": definition.optimization.max_trials,
            "recipe_candidate_count": len(plans),
            "configured_recipe_candidate_count": len(configured_plans),
            "generated_recipe_candidate_count": len(generated_plans),
            "successful_recipe_count": len(successful),
            "failed_recipe_count": sum(
                1 for item in study_candidates if item["status"] == "failed"
            ),
            "promoted_recipe_count": sum(
                1 for item in study_candidates if item["status"] == "promoted"
            ),
            "pruned_recipe_count": sum(
                1 for item in study_candidates if item["status"] == "pruned"
            ),
            "skipped_recipe_count": len(skipped_recipe_candidates),
            "requested_algorithms": candidate_algorithms,
            "evaluated_algorithms": evaluated_algorithms,
            "skipped_algorithms": skipped_algorithms,
            **({"cross_validation": cv_plan.provenance} if cv_plan else {}),
            "selected_recipe_id": winner["recipe_id"],
            "selected_algorithm": winner["best_algorithm"],
            "selected_parameters": winner["best_parameters"],
            "best_score": winner["score"],
            "scheduler": {
                "mode": "two_phase" if uses_two_phase_scheduler else "flat",
                "exploration_trials_per_recipe": (
                    exploration_trials_per_recipe if uses_two_phase_scheduler else None
                ),
                "exploration_time_fraction": (
                    recipe_configuration.exploration_time_fraction
                    if uses_two_phase_scheduler else None
                ),
                "promotion_top_k": (
                    recipe_configuration.promotion_top_k
                    if uses_two_phase_scheduler else None
                ),
                "promoted_recipe_ids": promoted_recipe_ids,
                "allocated_exploration_trials": sum(trial_allocations),
                "allocated_exploration_timeout_seconds": sum(timeout_allocations),
                "allocated_deepening_trials": sum(
                    int(item.get("allocated_trial_budget") or 0)
                    for item in deepening_results.values()
                ),
                "allocated_deepening_timeout_seconds": sum(
                    int(item.get("allocated_timeout_seconds") or 0)
                    for item in deepening_results.values()
                ),
                "completed_trials": sum(
                    int(item.get("trial_count") or 0) for item in study_candidates
                ),
            },
            "candidates": [
                {
                    key: value
                    for key, value in item.items()
                    if key != "recipe"
                }
                for item in study_candidates
            ] + skipped_recipe_candidates,
        }
        auto_fe_payload = {
            **selected_plan.provenance,
            "resolved_feature_count": len(resolved_features),
            "resolved_features": resolved_features,
            "joint_study": joint_study,
        }
        for item in training_result.output_manifest:
            item["auto_feature_engineering"] = auto_fe_payload
            item["internal_input_outputs"] = [{
                "output_id": "fitted_transform",
                "input_port_id": "fitted_transform",
            }]
            if item.get("artifact_type") == "model_version":
                item["training_config"]["auto_feature_engineering"] = auto_fe_payload
            if item.get("artifact_type") == "metrics":
                item["metrics"]["auto_feature_engineering"] = auto_fe_payload

        # Feature matrices are run-scoped intermediates. The fitted transform is
        # persisted so the selected model can later be reproduced for scoring.
        feature_manifests = list(feature_result.output_manifest)
        if not context.is_dry_run:
            for item in feature_manifests:
                if item.get("artifact_type") == "dataset":
                    item["materialization"] = "temporary"
                    item["auto_generated_intermediate"] = True
        return HandledStepResult(
            input_row_count=feature_result.input_row_count,
            processed_row_count=(
                processed_row_count
            ),
            output_row_count=training_result.output_row_count,
            warnings=list(dict.fromkeys([
                *selected_plan.warnings,
                *candidate_warnings,
                *feature_result.warnings,
                *training_result.warnings,
            ])),
            output_manifest=[*feature_manifests, *training_result.output_manifest],
            input_dataset_ids=feature_result.input_dataset_ids,
            relation_output_ids=(
                {"test": "autofe_test"} if prepared_test is not None else {}
            ),
            artifact_output_ids={
                "model": "model",
                "metrics": "training_metrics",
                "fitted_transform": "fitted_transform",
            },
        )

    def _evaluate_autofe_recipe_candidate(
        self,
        *,
        recipe: AutoFEPlan,
        definition: TrainingDefinition,
        raw_training: SourceRelation,
        raw_validation: SourceRelation | None,
        cv_plan: AutoFECrossValidationPlan | None,
        candidate_algorithms: list[str],
        context: StepExecutionContext,
        candidate_run_id: str,
        phase: str,
        trial_budget: int,
        timeout_budget: int,
        seed_offset: int,
    ) -> tuple[dict[str, Any], list[str], int]:
        recipe_id = str(recipe.provenance.get("recipe_id") or "recipe")
        feature_result, prepared_training, prepared_validation, _, resolved_features = (
            self._prepare_features(
                recipe,
                raw_training,
                raw_validation,
                None,
                run_id=candidate_run_id,
                owner_id=context.owner_id,
                is_dry_run=True,
            )
        )
        candidate_optimization = definition.optimization.model_copy(update={
            "candidate_algorithms": list(
                recipe.provenance.get("compatible_algorithms") or candidate_algorithms
            ),
            "max_trials": trial_budget,
            "timeout_seconds": max(10, timeout_budget),
        })
        candidate_definition = definition.model_copy(update={
            "feature_columns": resolved_features,
            "feature_selection": "explicit",
            "model_name": f"{definition.model_name} candidate {recipe_id} {phase}",
            "random_seed": definition.random_seed + seed_offset,
            "optimization": candidate_optimization,
            "resource_limits": (
                definition.resource_limits.model_copy(update={"max_parallel_jobs": 1})
                if cv_plan is not None else definition.resource_limits
            ),
        })
        fold_local_stats = {"processed_row_count": 0, "feature_counts": []}
        candidate_result = self.engine.execute(
            candidate_definition,
            prepared_training,
            prepared_validation,
            run_id=candidate_run_id,
            owner_id=context.owner_id,
            is_dry_run=True,
            emit_event=context.emit_event,
            is_cancel_requested=context.is_cancel_requested,
            optimization_score_callback=(
                self._fold_local_score_callback(
                    recipe=recipe,
                    cv_plan=cv_plan,
                    definition=candidate_definition,
                    run_id=candidate_run_id,
                    owner_id=context.owner_id,
                    emit_event=context.emit_event,
                    is_cancel_requested=context.is_cancel_requested,
                    stats=fold_local_stats,
                )
                if cv_plan is not None else None
            ),
        )
        model_manifest = next(
            item for item in candidate_result.output_manifest
            if item.get("artifact_type") == "model_version"
        )
        optimization = dict(model_manifest.get("metrics", {}).get("optimization") or {})
        trial_oof_summaries = dict(fold_local_stats.get("trial_oof_summaries", {}))
        for trial in optimization.get("trials") or []:
            number = int(trial.get("number", -1))
            if number in trial_oof_summaries:
                trial["oof_summary"] = trial_oof_summaries[number]
        scored_trials = [
            trial for trial in optimization.get("trials") or []
            if trial.get("status") == "succeeded"
            and isinstance(trial.get("score"), (int, float))
        ]
        selected_oof_summary = (
            dict(max(scored_trials, key=lambda trial: float(trial["score"])).get("oof_summary") or {})
            if scored_trials else {}
        )
        score = optimization.get("best_score")
        if score is None:
            raise ValueError(
                f"AutoFE recipe '{recipe_id}' did not produce a comparable holdout score"
            )
        processed_row_count = (
            feature_result.processed_row_count
            + candidate_result.processed_row_count
            + int(fold_local_stats["processed_row_count"])
        )
        candidate = {
            "recipe": recipe,
            "recipe_id": recipe_id,
            "recipe_hash": recipe.provenance.get("recipe_hash"),
            "recipe_contract": recipe.provenance.get("recipe_contract"),
            "status": "succeeded",
            "phase": phase,
            "score": float(score),
            "best_algorithm": str(
                optimization.get("best_algorithm") or model_manifest["algorithm"]
            ),
            "best_parameters": dict(optimization.get("best_parameters") or {}),
            "trial_count": int(optimization.get("trial_count") or 0),
            "allocated_trial_budget": trial_budget,
            "allocated_timeout_seconds": timeout_budget,
            "processed_row_count": processed_row_count,
            "resolved_feature_count": len(resolved_features),
            "resolved_features": resolved_features,
            "optimization": optimization,
            **({
                "fold_local_feature_counts": list(fold_local_stats["feature_counts"]),
                "fold_cache": {
                    "scope": (
                        "run_recipe" if phase == "flat_search" else "run_recipe_phase"
                    ),
                    "recipe_hash": recipe.provenance.get("recipe_hash"),
                    "fold_count": len(cv_plan.folds),
                    "miss_count": int(fold_local_stats.get("cache_misses", 0)),
                    "hit_count": int(fold_local_stats.get("cache_hits", 0)),
                    **({"phase": phase} if phase != "flat_search" else {}),
                },
                "oof_summaries": [
                    {"trial_number": number, **summary}
                    for number, summary in sorted(trial_oof_summaries.items())
                ],
                "selected_oof_summary": selected_oof_summary,
            } if cv_plan else {}),
        }
        return candidate, [*feature_result.warnings, *candidate_result.warnings], processed_row_count

    def _fold_local_score_callback(
        self,
        *,
        recipe: AutoFEPlan,
        cv_plan: AutoFECrossValidationPlan,
        definition: TrainingDefinition,
        run_id: str,
        owner_id: str,
        emit_event: Callable[[str, dict[str, Any]], None] | None,
        is_cancel_requested: Callable[[], bool] | None,
        stats: dict[str, Any],
    ) -> Callable[[Any, str], tuple[float, list[float]]]:
        """Evaluate one estimator with FE fitted independently inside every fold."""

        fold_cache: dict[int, dict[str, Any]] = {}

        def score(estimator: Any, metric: str) -> tuple[float, list[float]]:
            scorer = get_scorer(metric)
            fold_scores: list[float] = []
            trial_number = int(stats.get("trial_count", 0))
            stats["trial_count"] = trial_number + 1
            trial_feature_counts: list[dict[str, int]] = []
            for fold in cv_plan.folds:
                if is_cancel_requested and is_cancel_requested():
                    raise PipelineExecutionCancelled("Pipeline run was cancelled")
                fold_run_id = f"{run_id}/fold-local/cache/fold-{fold.fold}"
                fold_definition = recipe.definition.model_copy(update={
                    "inputs": [
                        FeatureInput(input_id="training", role="training"),
                        FeatureInput(input_id="validation", role="validation"),
                    ],
                    "outputs": [
                        FeatureOutput(
                            output_id="autofe_training",
                            input_id="training",
                            dataset_name=f"{definition.model_name} fold {fold.fold} training",
                            business_case_role="training",
                        ),
                        FeatureOutput(
                            output_id="autofe_validation",
                            input_id="validation",
                            dataset_name=f"{definition.model_name} fold {fold.fold} validation",
                            business_case_role="validation",
                        ),
                    ],
                    "evaluation": EvaluationConfig(split_strategy="predefined"),
                })
                fold_recipe = AutoFEPlan(
                    definition=fold_definition,
                    provenance=recipe.provenance,
                    warnings=recipe.warnings,
                )
                cached = fold_cache.get(fold.fold)
                cache_hit = cached is not None
                if cached is None:
                    if emit_event:
                        emit_event("autofe.fold_cache_miss", {
                            "message": f"Preparing fold-local FE cache for fold {fold.fold + 1}",
                            "fold": fold.fold,
                            "fold_count": len(cv_plan.folds),
                            "recipe_hash": recipe.provenance.get("recipe_hash"),
                            "training_row_count": fold.training.row_count,
                            "validation_row_count": fold.validation.row_count,
                        })
                    feature_result, prepared_training, prepared_validation, _, features = (
                        self._prepare_features(
                            fold_recipe,
                            fold.training,
                            fold.validation,
                            None,
                            run_id=fold_run_id,
                            owner_id=owner_id,
                            is_dry_run=True,
                        )
                    )
                    if prepared_validation is None:
                        raise ValueError("Fold-local AutoFE produced no validation matrix")
                    fitted_state = next(
                        (
                            item for item in feature_result.output_manifest
                            if item.get("artifact_type") == "feature_transform"
                        ),
                        {},
                    )
                    cached = {
                        "training": prepared_training,
                        "validation": prepared_validation,
                        "features": features,
                        "fitted_state_hash": str(fitted_state.get("state_hash") or ""),
                        "fitted_state_signature": self._stable_state_signature(
                            str(fitted_state.get("location_uri") or "")
                        ),
                        "cache_key": hashlib.sha256(
                            (
                                f"{recipe.provenance.get('recipe_hash', '')}|"
                                f"{fold.fold}|{cv_plan.provenance.get('seed')}|"
                                f"{fold.training.sql}|{fold.validation.sql}"
                            ).encode("utf-8")
                        ).hexdigest(),
                    }
                    fold_cache[fold.fold] = cached
                    stats["cache_misses"] = int(stats.get("cache_misses", 0)) + 1
                    stats["processed_row_count"] = (
                        int(stats.get("processed_row_count", 0))
                        + int(feature_result.processed_row_count)
                    )
                else:
                    stats["cache_hits"] = int(stats.get("cache_hits", 0)) + 1
                    if emit_event:
                        emit_event("autofe.fold_cache_hit", {
                            "message": f"Reusing fold-local FE cache for fold {fold.fold + 1}",
                            "fold": fold.fold,
                            "recipe_hash": recipe.provenance.get("recipe_hash"),
                            "cache_key": cached["cache_key"],
                        })
                prepared_training = cached["training"]
                prepared_validation = cached["validation"]
                features = list(cached["features"])
                try:
                    fold_training_definition = definition.model_copy(update={
                        "feature_columns": features,
                        "feature_selection": "explicit",
                    })
                    connection = configured_duckdb_connection(
                        self.feature_engine.repository_root
                        / "users" / owner_id / "pipeline-runs" / fold_run_id / ".matrix"
                    )
                    try:
                        x_train, y_train, train_bytes = self.engine._load_matrix(
                            connection,
                            prepared_training,
                            fold_training_definition,
                            row_count=prepared_training.row_count,
                        )
                        x_validation, y_validation, validation_bytes = self.engine._load_matrix(
                            connection,
                            prepared_validation,
                            fold_training_definition,
                            row_count=prepared_validation.row_count,
                        )
                        self.engine._enforce_memory_budget(
                            train_bytes + validation_bytes,
                            definition.resource_limits.max_memory_mb,
                            prepared_training.row_count + prepared_validation.row_count,
                            len(features),
                        )
                    finally:
                        connection.close()
                    fitted = clone(estimator).fit(x_train, y_train)
                    fold_score = float(scorer(fitted, x_validation, y_validation))
                    fold_scores.append(fold_score)
                    processed = int(prepared_training.row_count + prepared_validation.row_count)
                    stats["processed_row_count"] = int(stats.get("processed_row_count", 0)) + processed
                    trial_feature_counts.append({
                        "fold": fold.fold,
                        "feature_count": len(features),
                        "fitted_state_hash": cached["fitted_state_hash"],
                        "fitted_state_signature": cached["fitted_state_signature"],
                        "cache_key": cached["cache_key"],
                        "cache_hit": cache_hit,
                    })
                    if emit_event:
                        emit_event("autofe.fold_completed", {
                            "message": f"Fold-local FE completed for fold {fold.fold + 1}",
                            "fold": fold.fold,
                            "score": fold_score,
                            "metric": metric,
                            "resolved_feature_count": len(features),
                        })
                finally:
                    # Fold Parquet/state stays run-scoped until the recipe study ends.
                    # The outer candidate cleanup removes the entire cache directory.
                    pass
            stats.setdefault("trial_feature_counts", []).append(trial_feature_counts)
            stats["feature_counts"] = trial_feature_counts
            if not fold_scores:
                raise ValueError("Fold-local AutoFE produced no fold scores")
            weights = [fold.validation.row_count for fold in cv_plan.folds]
            prediction_count = sum(weights)
            weighted_score = sum(
                fold_score * weight
                for fold_score, weight in zip(fold_scores, weights, strict=True)
            ) / prediction_count
            mean_score = sum(fold_scores) / len(fold_scores)
            variance = sum(
                (value - mean_score) ** 2 for value in fold_scores
            ) / len(fold_scores)
            stats.setdefault("trial_oof_summaries", {})[trial_number] = {
                "data_scope": "full_training_scope",
                "prediction_count": prediction_count,
                "expected_row_count": int(cv_plan.provenance["planned_row_count"]),
                "coverage": prediction_count / int(cv_plan.provenance["planned_row_count"]),
                "fold_count": len(fold_scores),
                "primary_metric": metric,
                "fold_score_mean": mean_score,
                "fold_score_weighted_mean": weighted_score,
                "fold_score_std": math.sqrt(variance),
                "fold_score_min": min(fold_scores),
                "fold_score_max": max(fold_scores),
                "predictions_persisted": False,
                "aggregation": "fold_score_summary",
            }
            return sum(fold_scores) / len(fold_scores), fold_scores

        return score

    @staticmethod
    def _stable_state_signature(location_uri: str) -> str:
        """Hash fitted state with normalized floats for stable leakage assertions/audit."""

        if not location_uri.startswith("file://"):
            return ""
        payload = json.loads(
            Path(location_uri.removeprefix("file://")).read_text(encoding="utf-8")
        )

        def normalize(value: Any) -> Any:
            if isinstance(value, float):
                return float(format(value, ".12g"))
            if isinstance(value, dict):
                return {key: normalize(item) for key, item in value.items()}
            if isinstance(value, list):
                return [normalize(item) for item in value]
            return value

        canonical = json.dumps(
            normalize(payload),
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _prepare_features(
        self,
        plan: AutoFEPlan,
        raw_training: SourceRelation,
        raw_validation: SourceRelation | None,
        raw_test: SourceRelation | None,
        *,
        run_id: str,
        owner_id: str,
        is_dry_run: bool,
    ) -> tuple[Any, SourceRelation, SourceRelation | None, SourceRelation | None, list[str]]:
        feature_definition = plan.definition
        # Candidate studies need only train/validation. Holdout test is transformed
        # once with the selected winner, never while comparing candidate recipes.
        if raw_test is None and any(item.input_id == "test" for item in feature_definition.inputs):
            feature_definition = feature_definition.model_copy(update={
                "inputs": [item for item in feature_definition.inputs if item.input_id != "test"],
                "outputs": [item for item in feature_definition.outputs if item.input_id != "test"],
            })
        result = self.feature_engine.execute(
            definition=feature_definition,
            run_id=run_id,
            owner_id=owner_id,
            is_dry_run=is_dry_run,
            upstream_relations={
                "training": raw_training,
                **({"validation": raw_validation} if raw_validation is not None else {}),
                **({"test": raw_test} if raw_test is not None else {}),
            },
        )
        feature_outputs = {
            str(item.get("business_case_role")): item
            for item in result.output_manifest
            if item.get("artifact_type") == "dataset"
        }
        prepared_training = self._relation_from_feature_manifest(
            feature_outputs.get("training"), "training"
        )
        if prepared_training is None:
            raise ValueError("AutoFE did not produce a training feature dataset")
        prepared_validation = self._relation_from_feature_manifest(
            feature_outputs.get("validation"), "validation"
        )
        prepared_test = self._relation_from_feature_manifest(feature_outputs.get("test"), "test")
        resolved_features = [
            str(item.get("name"))
            for item in prepared_training.metadata.get("feature_manifest", [])
            if item.get("role") == "feature" and item.get("name")
        ]
        if not resolved_features:
            raise ValueError("AutoFE produced no resolved model features")
        return result, prepared_training, prepared_validation, prepared_test, resolved_features

    @staticmethod
    def _allocate_weighted_budget(
        total: int,
        weights: list[int],
        *,
        minimum: int,
    ) -> list[int]:
        count = len(weights)
        if count < 1 or total < count * minimum:
            raise ValueError("AutoML budget cannot cover every model-aware recipe candidate")
        allocation = [minimum] * count
        remaining = total - count * minimum
        if not remaining:
            return allocation
        weight_sum = sum(max(1, weight) for weight in weights)
        exact = [remaining * max(1, weight) / weight_sum for weight in weights]
        floors = [int(value) for value in exact]
        allocation = [value + floors[index] for index, value in enumerate(allocation)]
        leftover = total - sum(allocation)
        order = sorted(
            range(count),
            key=lambda index: (exact[index] - floors[index], -index),
            reverse=True,
        )
        for index in order[:leftover]:
            allocation[index] += 1
        return allocation

    def _cleanup_candidate_run(self, owner_id: str, run_id: str) -> None:
        root = (self.feature_engine.repository_root / "users" / owner_id / "pipeline-runs").resolve()
        directory = (root / run_id).resolve()
        try:
            directory.relative_to(root)
        except ValueError as exc:
            raise ValueError("AutoFE candidate path is outside the pipeline-run root") from exc
        if directory != root:
            shutil.rmtree(directory, ignore_errors=True)

    @staticmethod
    def _relation_from_feature_manifest(
        manifest: dict | None,
        role: str,
    ) -> SourceRelation | None:
        if manifest is None:
            if role == "training":
                raise ValueError("AutoFE did not produce a training feature dataset")
            return None
        location = str(manifest.get("location_uri") or "")
        if not location.startswith("file://"):
            raise ValueError(f"AutoFE {role} output has no local Parquet location")
        return SourceRelation(
            sql=f"read_parquet({sql_literal(location.removeprefix('file://'))})",
            row_count=int(manifest.get("row_count") or -1),
            metadata={
                "feature_manifest": list(manifest.get("feature_manifest") or []),
                "split_evaluation": dict(manifest.get("split_evaluation") or {}),
                "fitted_transform_count": int(manifest.get("fitted_transform_count") or 0),
                "feature_recipe_hash": str(manifest.get("feature_recipe_hash") or ""),
                "auto_feature_engineering": True,
            },
        )


class ScoringStepHandler:
    step_type = "scoring"

    def __init__(
        self,
        engine: SklearnScoringEngine | None = None,
        artifacts: BusinessCaseRepository | None = None,
    ) -> None:
        self.engine = engine or SklearnScoringEngine()
        self.artifacts = artifacts or PostgresBusinessCaseRepository()

    def execute(self, step: WorkflowStep, context: StepExecutionContext) -> HandledStepResult:
        definition = ScoringDefinition.model_validate(step.config["definition"])
        inputs = {port.port_id: port for port in step.inputs}
        data_port = inputs.get("data")
        model_port = inputs.get("model")
        if data_port is None:
            raise ValueError("Scoring step requires an explicit 'data' input")
        data = context.upstream_relations.get(
            (data_port.source.step_id, data_port.source.port_id)
        )
        model: dict | None = None
        external_model_artifact_id = ""
        if definition.purpose == "batch":
            artifact = self.artifacts.get_artifact(definition.model_artifact_id)
            if (
                artifact is None
                or artifact.owner_id != context.owner_id
                or artifact.type != ArtifactType.MODEL_VERSION
            ):
                raise ValueError("Pinned batch-scoring model artifact was not found")
            external_model_artifact_id = artifact.id
            model = {
                "artifact_id": artifact.id,
                "artifact_type": artifact.type.value,
                **dict(artifact.metadata),
            }
        elif model_port is not None:
            model = context.upstream_artifacts.get(
                (model_port.source.step_id, model_port.source.port_id)
            )
        if data is None:
            raise ValueError("Scoring data input is not a dataset output")
        if model is None or model.get("artifact_type") != "model_version":
            raise ValueError("Scoring model input is not a model-version artifact")
        result = self.engine.execute(
            definition,
            data,
            model,
            run_id=context.run_id,
            owner_id=context.owner_id,
            is_dry_run=context.is_dry_run,
        )
        for manifest in result.output_manifest:
            if external_model_artifact_id:
                manifest["model_artifact_id"] = external_model_artifact_id
        return HandledStepResult(
            input_row_count=result.input_row_count,
            processed_row_count=result.processed_row_count,
            output_row_count=result.output_row_count,
            warnings=result.warnings,
            output_manifest=result.output_manifest,
            input_dataset_ids=[],
            relation_output_ids={"predictions": "predictions"},
            artifact_output_ids={},
            external_input_artifact_ids=(
                [external_model_artifact_id] if external_model_artifact_id else []
            ),
            external_input_lineage=(
                [{
                    "input_port_id": "model",
                    "artifact_ids": [external_model_artifact_id],
                }]
                if external_model_artifact_id else []
            ),
        )


class MonitoringStepHandler:
    step_type = "monitoring"

    def __init__(self, engine: DuckDbMonitoringEngine | None = None) -> None:
        self.engine = engine or DuckDbMonitoringEngine()

    def execute(self, step: WorkflowStep, context: StepExecutionContext) -> HandledStepResult:
        definition = MonitoringDefinition.model_validate(step.config["definition"])
        inputs = {item.port_id: item for item in step.inputs}
        data_port = inputs.get("data")
        if data_port is None:
            raise ValueError("Performance Report requires an explicit 'data' input")
        source = context.upstream_relations.get(
            (data_port.source.step_id, data_port.source.port_id)
        )
        if source is None:
            raise ValueError("Performance Report input is not a dataset output")
        result = self.engine.execute(
            definition,
            source,
            run_id=context.run_id,
            owner_id=context.owner_id,
            is_dry_run=context.is_dry_run,
        )
        return HandledStepResult(
            input_row_count=result.input_row_count,
            processed_row_count=result.processed_row_count,
            output_row_count=result.output_row_count,
            warnings=result.warnings,
            output_manifest=result.output_manifest,
            input_dataset_ids=[],
            relation_output_ids={
                "performance_report": "performance_report_source"
            },
        )


class PipelineStepHandlerRegistry:
    def __init__(self, handlers: list[PipelineStepHandler] | None = None) -> None:
        configured = handlers or [
            DataEngineeringStepHandler(),
            FeatureEngineeringStepHandler(),
            TrainingStepHandler(),
            AutoMLStepHandler(),
            ScoringStepHandler(),
            MonitoringStepHandler(),
        ]
        self._handlers = {handler.step_type: handler for handler in configured}
        if len(self._handlers) != len(configured):
            raise ValueError("Pipeline step handler types must be unique")

    def execute(
        self,
        step: WorkflowStep,
        context: StepExecutionContext,
    ) -> HandledStepResult:
        handler = self._handlers.get(step.type)
        if handler is None:
            raise ValueError(f"No execution handler is registered for step type '{step.type}'")
        return handler.execute(step, context)


def _input_dataset_ids(inputs: list) -> list[str]:
    return list(dict.fromkeys(
        item.dataset_id
        for item in inputs
        if item.dataset_id
    ))
