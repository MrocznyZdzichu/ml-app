from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from app.modules.pipelines.dag import PipelineDefinition
from app.modules.pipelines.autofe import (
    AutoFEPlan,
    DuckDbAutoFEPlanner,
    model_aware_autofe_plans,
)
from app.modules.pipelines.execution import DuckDbPipelineExecutionEngine
from app.modules.pipelines.feature_engineering import (
    DuckDbFeatureEngineeringEngine,
    FeatureEngineeringDefinition,
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
        candidate_algorithms = (
            list(definition.optimization.candidate_algorithms)
            or automl_algorithms(definition.problem_type)
        )
        plans = (
            model_aware_autofe_plans(
                plan,
                candidate_algorithms,
                max_candidates=min(
                    definition.auto_feature_engineering.max_recipe_candidates,
                    definition.optimization.max_trials,
                    max(1, definition.optimization.timeout_seconds // 10),
                ),
            )
            if definition.auto_feature_engineering.joint_search_enabled
            else [plan]
        )
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
        if context.emit_event:
            context.emit_event("autofe.plan_created", {
                "message": "AutoFE created model-aware tabular recipe candidates",
                "profiled_row_count": plan.provenance["profiled_row_count"],
                "recipe_candidate_count": len(plans),
                "validation_source": plan.provenance["validation_source"],
                "evaluated_algorithms": evaluated_algorithms,
                "skipped_algorithms": skipped_algorithms,
            })

        recipe_weights = [
            max(1, len(recipe.provenance.get("compatible_algorithms") or []))
            for recipe in plans
        ]
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
        study_candidates: list[dict[str, Any]] = []
        processed_row_count = 0
        for index, recipe in enumerate(plans):
            recipe_id = str(recipe.provenance.get("recipe_id") or f"recipe_{index + 1}")
            if context.is_cancel_requested and context.is_cancel_requested():
                raise PipelineExecutionCancelled("Pipeline run was cancelled")
            if context.emit_event:
                context.emit_event("autofe.recipe_trial_started", {
                    "message": f"Evaluating AutoFE recipe '{recipe_id}'",
                    "recipe_id": recipe_id,
                    "candidate_algorithms": recipe.provenance.get("compatible_algorithms", []),
                    "trial_budget": trial_allocations[index],
                })
            candidate_run_id = f"{context.run_id}/autofe-candidates/{recipe_id}"
            try:
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
                processed_row_count += feature_result.processed_row_count
                candidate_optimization = definition.optimization.model_copy(update={
                    "candidate_algorithms": list(
                        recipe.provenance.get("compatible_algorithms") or candidate_algorithms
                    ),
                    "max_trials": trial_allocations[index],
                    "timeout_seconds": max(10, timeout_allocations[index]),
                })
                candidate_definition = definition.model_copy(update={
                    "feature_columns": resolved_features,
                    "feature_selection": "explicit",
                    "model_name": f"{definition.model_name} candidate {recipe_id}",
                    "optimization": candidate_optimization,
                })
                candidate_result = self.engine.execute(
                    candidate_definition,
                    prepared_training,
                    prepared_validation,
                    run_id=candidate_run_id,
                    owner_id=context.owner_id,
                    is_dry_run=True,
                    emit_event=context.emit_event,
                    is_cancel_requested=context.is_cancel_requested,
                )
                processed_row_count += candidate_result.processed_row_count
                candidate_warnings.extend(feature_result.warnings)
                candidate_warnings.extend(candidate_result.warnings)
                model_manifest = next(
                    item for item in candidate_result.output_manifest
                    if item.get("artifact_type") == "model_version"
                )
                optimization = dict(model_manifest.get("metrics", {}).get("optimization") or {})
                score = optimization.get("best_score")
                if score is None:
                    raise ValueError(
                        f"AutoFE recipe '{recipe_id}' did not produce a comparable holdout score"
                    )
                study_candidates.append({
                    "recipe": recipe,
                    "recipe_id": recipe_id,
                    "status": "succeeded",
                    "score": float(score),
                    "best_algorithm": str(optimization.get("best_algorithm") or model_manifest["algorithm"]),
                    "best_parameters": dict(optimization.get("best_parameters") or {}),
                    "trial_count": int(optimization.get("trial_count") or 0),
                    "processed_row_count": candidate_result.processed_row_count,
                    "resolved_feature_count": len(resolved_features),
                    "resolved_features": resolved_features,
                    "optimization": optimization,
                })
                if context.emit_event:
                    context.emit_event("autofe.recipe_trial_completed", {
                        "message": f"AutoFE recipe '{recipe_id}' evaluation completed",
                        "recipe_id": recipe_id,
                        "best_score": float(score),
                        "best_algorithm": optimization.get("best_algorithm"),
                        "resolved_feature_count": len(resolved_features),
                    })
            except PipelineExecutionCancelled:
                raise
            except Exception as exc:
                study_candidates.append({
                    "recipe": recipe,
                    "recipe_id": recipe_id,
                    "status": "failed",
                    "error": str(exc),
                    "score": None,
                    "trial_count": 0,
                    "resolved_feature_count": 0,
                    "resolved_features": [],
                })
                if context.emit_event:
                    context.emit_event("autofe.recipe_trial_failed", {
                        "message": f"AutoFE recipe '{recipe_id}' failed: {exc}",
                        "recipe_id": recipe_id,
                    })
            finally:
                self._cleanup_candidate_run(context.owner_id, candidate_run_id)

        successful = [item for item in study_candidates if item["status"] == "succeeded"]
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
                "joint_model_aware_holdout"
                if definition.auto_feature_engineering.joint_search_enabled
                else "fixed_recipe_model_search"
            ),
            "primary_metric": definition.optimization.primary_metric,
            "trial_budget": definition.optimization.max_trials,
            "recipe_candidate_count": len(plans),
            "successful_recipe_count": len(successful),
            "failed_recipe_count": len(study_candidates) - len(successful),
            "requested_algorithms": candidate_algorithms,
            "evaluated_algorithms": evaluated_algorithms,
            "skipped_algorithms": skipped_algorithms,
            "selected_recipe_id": winner["recipe_id"],
            "selected_algorithm": winner["best_algorithm"],
            "selected_parameters": winner["best_parameters"],
            "best_score": winner["score"],
            "candidates": [
                {
                    key: value
                    for key, value in item.items()
                    if key != "recipe"
                }
                for item in study_candidates
            ],
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
