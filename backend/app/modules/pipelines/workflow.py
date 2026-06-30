from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.modules.pipelines.dag import PipelineDefinition


class WorkflowPortReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(min_length=1, max_length=128)
    port_id: str = Field(min_length=1, max_length=128)


class WorkflowStepInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    port_id: str = Field(min_length=1, max_length=128)
    source: WorkflowPortReference


class WorkflowStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=200)
    type: Literal["data_engineering"]
    inputs: list[WorkflowStepInput] = Field(default_factory=list)
    output_port_id: str = Field(default="dataset", min_length=1, max_length=128)
    config: dict[str, Any] = Field(default_factory=dict)


class WorkflowOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_id: str = Field(min_length=1, max_length=128)
    source: WorkflowPortReference


class WorkflowDefinition(BaseModel):
    """High-level lifecycle DAG. Domain operations live inside step config."""

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["2.0"] = "2.0"
    steps: list[WorkflowStep]
    outputs: list[WorkflowOutput]
    parameters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_graph(self) -> WorkflowDefinition:
        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("Workflow step_id values must be unique")
        output_ids = [output.output_id for output in self.outputs]
        if len(output_ids) != len(set(output_ids)):
            raise ValueError("Workflow output_id values must be unique")

        ports = {step.step_id: {step.output_port_id} for step in self.steps}
        dependencies: dict[str, set[str]] = defaultdict(set)
        for step in self.steps:
            input_ids = [item.port_id for item in step.inputs]
            if len(input_ids) != len(set(input_ids)):
                raise ValueError(f"Workflow step '{step.step_id}' has duplicate input port IDs")
            for item in step.inputs:
                _validate_reference(step.step_id, item.source, ports)
                dependencies[step.step_id].add(item.source.step_id)
            if set(step.config) - {"definition"}:
                raise ValueError(f"Workflow step '{step.step_id}' contains unsupported config fields")
            if not isinstance(step.config.get("definition"), dict):
                raise ValueError(f"Workflow step '{step.step_id}' requires a DE definition")

        for output in self.outputs:
            _validate_reference(output.output_id, output.source, ports)
        _assert_acyclic(step_ids, dependencies)
        return self


def empty_workflow_definition() -> dict[str, Any]:
    return {
        "contract_version": "2.0",
        "steps": [],
        "outputs": [],
        "parameters": {},
    }


def normalize_workflow_definition(definition: dict[str, Any]) -> dict[str, Any]:
    if str(definition.get("contract_version") or "1.0") == "2.0":
        normalized = dict(definition)
        normalized.setdefault("steps", [])
        normalized.setdefault("outputs", [])
        normalized.setdefault("parameters", {})
        return normalized

    legacy = dict(definition)
    legacy.setdefault("contract_version", "1.0")
    legacy.setdefault("inputs", [])
    legacy.setdefault("steps", [])
    legacy.setdefault("outputs", [])
    legacy.setdefault("parameters", {})
    if not legacy["inputs"] and not legacy["steps"] and not legacy["outputs"]:
        return empty_workflow_definition()
    return {
        "contract_version": "2.0",
        "steps": [
            {
                "step_id": "de_1",
                "name": "Data Engineering",
                "type": "data_engineering",
                "inputs": [],
                "output_port_id": "dataset",
                "config": {"definition": legacy},
            }
        ],
        "outputs": [
            {
                "output_id": "result",
                "source": {"step_id": "de_1", "port_id": "dataset"},
            }
        ],
        "parameters": {},
    }


def validate_workflow_definition(definition: dict[str, Any], executable: bool) -> dict[str, Any]:
    normalized = normalize_workflow_definition(definition)
    workflow = WorkflowDefinition.model_validate(normalized)
    if executable and not workflow.steps:
        raise ValueError("An executable pipeline requires at least one workflow step")
    if len(workflow.steps) > 1:
        raise ValueError("The current functional prototype supports one Data Engineering step")
    for step in workflow.steps:
        de_definition = dict(step.config["definition"])
        de_is_empty = (
            not de_definition.get("inputs")
            and not de_definition.get("steps")
            and not de_definition.get("outputs")
        )
        if executable or not de_is_empty:
            validated = PipelineDefinition.model_validate(de_definition)
            step.config["definition"] = validated.model_dump(mode="json")
    if executable and not workflow.outputs:
        raise ValueError("An executable pipeline requires a workflow output")
    return workflow.model_dump(mode="json")


def workflow_validation_errors(exc: ValidationError) -> list[dict[str, str]]:
    return [
        {
            "path": ".".join(str(part) for part in error["loc"]),
            "message": error["msg"],
        }
        for error in exc.errors(include_url=False)
    ]


def data_engineering_step(workflow: WorkflowDefinition) -> WorkflowStep:
    if len(workflow.steps) != 1 or workflow.steps[0].type != "data_engineering":
        raise ValueError("The current functional prototype requires exactly one Data Engineering step")
    return workflow.steps[0]


def _validate_reference(
    target_id: str,
    reference: WorkflowPortReference,
    ports: dict[str, set[str]],
) -> None:
    if reference.step_id == target_id:
        raise ValueError(f"Workflow node '{target_id}' cannot reference itself")
    if reference.step_id not in ports:
        raise ValueError(f"Workflow node '{target_id}' references unknown step '{reference.step_id}'")
    if reference.port_id not in ports[reference.step_id]:
        raise ValueError(
            f"Workflow node '{target_id}' references unknown port '{reference.port_id}' "
            f"on step '{reference.step_id}'"
        )


def _assert_acyclic(step_ids: list[str], dependencies: dict[str, set[str]]) -> None:
    remaining = {step_id: set(dependencies.get(step_id, ())) for step_id in step_ids}
    children: dict[str, set[str]] = defaultdict(set)
    for step_id, parents in remaining.items():
        for parent in parents:
            children[parent].add(step_id)
    ready = deque(step_id for step_id, parents in remaining.items() if not parents)
    visited = 0
    while ready:
        resolved = ready.popleft()
        visited += 1
        for child in children.get(resolved, ()):
            remaining[child].remove(resolved)
            if not remaining[child]:
                ready.append(child)
    if visited != len(step_ids):
        raise ValueError("Workflow definition contains a cycle")
