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
    type: Literal["data_engineering", "feature_engineering", "training", "scoring"]
    inputs: list[WorkflowStepInput] = Field(default_factory=list)
    output_port_id: str = Field(default="dataset", min_length=1, max_length=128)
    additional_output_port_ids: list[str] = Field(default_factory=list)
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

        ports = {
            step.step_id: {step.output_port_id, *step.additional_output_port_ids}
            for step in self.steps
        }
        dependencies: dict[str, set[str]] = defaultdict(set)
        for step in self.steps:
            input_ids = [item.port_id for item in step.inputs]
            if len(input_ids) != len(set(input_ids)):
                raise ValueError(f"Workflow step '{step.step_id}' has duplicate input port IDs")
            for item in step.inputs:
                _validate_reference(step.step_id, item.source, ports)
                dependencies[step.step_id].add(item.source.step_id)
            if len(step.additional_output_port_ids) != len(set(step.additional_output_port_ids)):
                raise ValueError(f"Workflow step '{step.step_id}' has duplicate output port IDs")
            if step.output_port_id in step.additional_output_port_ids:
                raise ValueError(f"Workflow step '{step.step_id}' has duplicate output port IDs")
            if set(step.config) - {"definition"}:
                raise ValueError(f"Workflow step '{step.step_id}' contains unsupported config fields")
            if not isinstance(step.config.get("definition"), dict):
                raise ValueError(f"Workflow step '{step.step_id}' requires a nested definition")

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
        steps = [dict(step) for step in normalized["steps"]]
        legacy_primary_ports: dict[str, str] = {}
        for step in steps:
            if step.get("type") != "feature_engineering":
                continue
            previous_primary = str(step.get("output_port_id") or "dataset")
            primary, additional = feature_engineering_output_ports(step)
            step["output_port_id"] = primary
            step["additional_output_port_ids"] = additional
            legacy_primary_ports[str(step.get("step_id") or "")] = previous_primary
        normalized["steps"] = steps

        outputs = [dict(output) for output in normalized["outputs"]]
        for output in outputs:
            source = dict(output.get("source") or {})
            step_id = str(source.get("step_id") or "")
            if (
                step_id in legacy_primary_ports
                and source.get("port_id") == legacy_primary_ports[step_id]
            ):
                step = next(item for item in steps if str(item.get("step_id")) == step_id)
                source["port_id"] = step["output_port_id"]
                output["source"] = source
        if steps and steps[-1].get("type") == "feature_engineering":
            outputs = feature_engineering_workflow_outputs(steps[-1])
        normalized["outputs"] = outputs
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
    if len(workflow.steps) > 4:
        raise ValueError("The current workflow supports at most four lifecycle steps")
    if workflow.steps:
        actual_sequence = [step.type for step in workflow.steps]
        order = {"data_engineering": 0, "feature_engineering": 1, "training": 2, "scoring": 3}
        if actual_sequence != sorted(actual_sequence, key=order.__getitem__):
            raise ValueError("Workflow steps must follow DE, FE, Training, Scoring lifecycle order")
        if len(actual_sequence) != len(set(actual_sequence)):
            raise ValueError("The current workflow supports one step of each lifecycle type")
    for index, step in enumerate(workflow.steps):
        nested_definition = dict(step.config["definition"])
        if step.type == "data_engineering":
            nested_is_empty = (
                not nested_definition.get("inputs")
                and not nested_definition.get("steps")
                and not nested_definition.get("outputs")
            )
            if executable or not nested_is_empty:
                validated = PipelineDefinition.model_validate(nested_definition)
                step.config["definition"] = validated.model_dump(mode="json")
        elif step.type == "feature_engineering":
            from app.modules.pipelines.feature_engineering import FeatureEngineeringDefinition

            validated = FeatureEngineeringDefinition.model_validate(nested_definition)
            if executable:
                validated.validate_executable()
            step.config["definition"] = validated.model_dump(mode="json")
            expected_primary, expected_additional = feature_engineering_output_ports(
                step.model_dump(mode="json")
            )
            if (
                step.output_port_id != expected_primary
                or step.additional_output_port_ids != expected_additional
            ):
                raise ValueError(
                    "Feature Engineering workflow ports must match its declared dataset outputs"
                )
            if index > 0 and not step.inputs:
                raise ValueError("Feature Engineering after Data Engineering requires an upstream input")
        elif step.type == "training":
            from app.modules.pipelines.modeling import TrainingDefinition

            validated = TrainingDefinition.model_validate(nested_definition)
            if executable:
                validated.validate_executable()
            step.config["definition"] = validated.model_dump(mode="json")
            ports = {item.port_id for item in step.inputs}
            if "training" not in ports:
                raise ValueError("Training requires an explicit 'training' input port")
            if ports - {"training", "validation", "fitted_transform"}:
                raise ValueError(
                    "Training accepts 'training' and optional 'validation' "
                    "and 'fitted_transform' input ports"
                )
            if validated.early_stopping and "validation" not in ports:
                raise ValueError("Training early stopping requires an explicit 'validation' input port")
            if step.output_port_id != "model":
                raise ValueError("Training primary output port must be 'model'")
        else:
            from app.modules.pipelines.modeling import ScoringDefinition

            validated = ScoringDefinition.model_validate(nested_definition)
            if executable:
                validated.validate_executable()
            step.config["definition"] = validated.model_dump(mode="json")
            ports = {item.port_id for item in step.inputs}
            if validated.purpose == "batch":
                if ports != {"data"}:
                    raise ValueError(
                        "Batch scoring requires exactly one 'data' input port; "
                        "the immutable model is pinned in its definition"
                    )
            elif ports != {"data", "model"}:
                raise ValueError("Test scoring requires exactly 'data' and 'model' input ports")
            if step.output_port_id != "predictions":
                raise ValueError("Scoring primary output port must be 'predictions'")
    _validate_batch_scoring_preparation(workflow)
    if executable and not workflow.outputs:
        raise ValueError("An executable pipeline requires a workflow output")
    return workflow.model_dump(mode="json")


def _validate_batch_scoring_preparation(workflow: WorkflowDefinition) -> None:
    batch_steps = [
        step
        for step in workflow.steps
        if step.type == "scoring"
        and step.config["definition"].get("purpose") == "batch"
    ]
    if not batch_steps:
        return
    if any(step.type == "training" for step in workflow.steps):
        raise ValueError("A batch-scoring workflow cannot contain a Training step")
    feature = next(
        (step for step in workflow.steps if step.type == "feature_engineering"),
        None,
    )
    if feature is None or feature.config["definition"].get("mode") != "transform":
        raise ValueError(
            "Batch scoring requires Feature Engineering in transform mode "
            "with a pinned fitted state"
        )
    target_column = str(feature.config["definition"].get("target_column") or "")
    safe_types = {
        "select_columns",
        "add_identifier",
        "rename_columns",
        "cast_columns",
        "derive_column",
        "map_categories",
    }
    for step in workflow.steps:
        if step.type != "data_engineering":
            continue
        for operation in step.config["definition"].get("steps", []):
            operation_type = str(operation.get("type") or "")
            if operation_type not in safe_types:
                raise ValueError(
                    f"Batch-scoring DE operation '{operation_type}' is not inference-safe; "
                    "keep only deterministic schema and feature preparation"
                )
            config = operation.get("config") or {}
            if operation_type == "add_identifier" and config.get("mode") == "sequence":
                raise ValueError(
                    "Batch-scoring record IDs must be stable; sequence identifiers are not allowed"
                )
            if target_column and _contains_contract_value(config, target_column):
                raise ValueError(
                    f"Batch-scoring DE operation '{operation.get('step_id')}' "
                    "depends on the target column"
                )


def _contains_contract_value(value: Any, expected: str) -> bool:
    if isinstance(value, dict):
        return any(
            _contains_contract_value(key, expected)
            or _contains_contract_value(item, expected)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_contract_value(item, expected) for item in value)
    return str(value) == expected


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


def feature_engineering_step(workflow: WorkflowDefinition) -> WorkflowStep:
    matches = [step for step in workflow.steps if step.type == "feature_engineering"]
    if len(matches) != 1:
        raise ValueError("Workflow requires exactly one Feature Engineering step")
    return matches[0]


def feature_engineering_output_ports(step: dict[str, Any]) -> tuple[str, list[str]]:
    config = step.get("config") if isinstance(step.get("config"), dict) else {}
    definition = config.get("definition") if isinstance(config.get("definition"), dict) else {}
    outputs = definition.get("outputs") if isinstance(definition.get("outputs"), list) else []
    roles = list(dict.fromkeys(
        str(output.get("business_case_role") or "training")
        for output in outputs
        if isinstance(output, dict)
    ))
    primary = "training" if "training" in roles else (roles[0] if roles else "training")
    additional = [role for role in roles if role != primary]
    if str(definition.get("mode") or "fit_transform") == "fit_transform":
        additional.append("fitted_transform")
    return primary, additional


def feature_engineering_workflow_outputs(step: dict[str, Any]) -> list[dict[str, Any]]:
    config = step.get("config") if isinstance(step.get("config"), dict) else {}
    definition = config.get("definition") if isinstance(config.get("definition"), dict) else {}
    outputs = definition.get("outputs") if isinstance(definition.get("outputs"), list) else []
    step_id = str(step.get("step_id") or "fe_1")
    return [
        {
            "output_id": str(output.get("output_id") or f"{role}_features"),
            "source": {"step_id": step_id, "port_id": role},
        }
        for output in outputs
        if isinstance(output, dict)
        for role in [str(output.get("business_case_role") or "training")]
    ]


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
