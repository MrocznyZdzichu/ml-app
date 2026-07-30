"""Compatibility facade and registry for focused pipeline step handlers."""

from __future__ import annotations

from app.modules.pipelines.automl_step_handler import AutoMLStepHandler
from app.modules.pipelines.data_step_handlers import (
    DataEngineeringStepHandler,
    FeatureEngineeringStepHandler,
)
from app.modules.pipelines.monitoring_step_handler import MonitoringStepHandler
from app.modules.pipelines.scoring_step_handler import ScoringStepHandler
from app.modules.pipelines.step_contracts import (
    HandledStepResult,
    PipelineStepHandler,
    StepExecutionContext,
)
from app.modules.pipelines.training_step_handler import TrainingStepHandler
from app.modules.pipelines.workflow import WorkflowStep


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


__all__ = [
    "AutoMLStepHandler",
    "DataEngineeringStepHandler",
    "FeatureEngineeringStepHandler",
    "HandledStepResult",
    "MonitoringStepHandler",
    "PipelineStepHandler",
    "PipelineStepHandlerRegistry",
    "ScoringStepHandler",
    "StepExecutionContext",
    "TrainingStepHandler",
]
