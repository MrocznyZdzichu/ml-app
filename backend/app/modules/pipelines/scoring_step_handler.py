"""Batch and test-scoring pipeline step handler."""

from __future__ import annotations

from app.modules.business_cases.domain import ArtifactType
from app.modules.business_cases.repository import (
    BusinessCaseRepository,
    PostgresBusinessCaseRepository,
)
from app.modules.pipelines.modeling import ScoringDefinition, SklearnScoringEngine
from app.modules.pipelines.step_contracts import HandledStepResult, StepExecutionContext
from app.modules.pipelines.workflow import WorkflowStep


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
