from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from app.modules.pipelines.dag import PipelineDefinition
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
from app.modules.pipelines.monitoring import DuckDbMonitoringEngine, MonitoringDefinition
from app.modules.pipelines.runtime import SourceRelation
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
        return HandledStepResult(
            input_row_count=result.input_row_count,
            processed_row_count=result.processed_row_count,
            output_row_count=result.output_row_count,
            warnings=result.warnings,
            output_manifest=result.output_manifest,
            input_dataset_ids=[],
            relation_output_ids={},
            artifact_output_ids={"model": "model", "metrics": "training_metrics"},
        )


class AutoMLStepHandler(TrainingStepHandler):
    """Governed AutoML entry point backed by the current native optimization engine."""

    step_type = "automl"

    def execute(self, step: WorkflowStep, context: StepExecutionContext) -> HandledStepResult:
        definition = TrainingDefinition.model_validate(step.config["definition"])
        if definition.optimization.mode != "automl":
            raise ValueError("AutoML step requires optimization mode 'automl'")
        return super().execute(step, context)


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
