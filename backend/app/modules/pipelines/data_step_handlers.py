"""Data and feature-engineering pipeline step handlers."""

from __future__ import annotations

from app.modules.pipelines.dag import PipelineDefinition
from app.modules.pipelines.execution import DuckDbPipelineExecutionEngine
from app.modules.pipelines.feature_engineering import (
    DuckDbFeatureEngineeringEngine,
    FeatureEngineeringDefinition,
)
from app.modules.pipelines.runtime import SourceRelation
from app.modules.pipelines.step_contracts import HandledStepResult, StepExecutionContext
from app.modules.pipelines.workflow import WorkflowStep


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


def _input_dataset_ids(inputs: list) -> list[str]:
    return list(dict.fromkeys(
        item.dataset_id
        for item in inputs
        if item.dataset_id
    ))
