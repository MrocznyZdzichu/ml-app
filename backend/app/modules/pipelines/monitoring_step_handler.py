"""Batch performance-monitoring pipeline step handler."""

from __future__ import annotations

from app.modules.pipelines.monitoring import DuckDbMonitoringEngine, MonitoringDefinition
from app.modules.pipelines.step_contracts import HandledStepResult, StepExecutionContext
from app.modules.pipelines.workflow import WorkflowStep


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
