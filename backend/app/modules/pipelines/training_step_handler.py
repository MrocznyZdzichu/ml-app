"""Explicit training pipeline step handler."""

from __future__ import annotations

from app.modules.pipelines.modeling import SklearnTrainingEngine, TrainingDefinition
from app.modules.pipelines.step_contracts import HandledStepResult, StepExecutionContext
from app.modules.pipelines.workflow import WorkflowStep


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
            artifact_output_ids={
                "model": "model",
                "metrics": "training_metrics",
                **({"training_report": "training_report"} if any(
                    item.get("output_id") == "training_report" for item in result.output_manifest
                ) else {}),
            },
            relation_passthroughs=(
                {"test": (test_port.source.step_id, test_port.source.port_id)}
                if test_port is not None and "test" in step.additional_output_port_ids
                else {}
            ),
        )
