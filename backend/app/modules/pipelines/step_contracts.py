"""Stable contracts shared by pipeline step handlers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from app.modules.pipelines.runtime import SourceRelation
from app.modules.pipelines.workflow import WorkflowStep


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
