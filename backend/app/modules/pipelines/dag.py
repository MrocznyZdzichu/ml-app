from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PortReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(min_length=1, max_length=128)
    port_id: str = Field(min_length=1, max_length=128)


class PipelineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_id: str = Field(min_length=1, max_length=128)
    dataset_id: str = Field(min_length=1, max_length=128)
    output_port_id: str = Field(default="out", min_length=1, max_length=128)
    version_policy: Literal["latest", "select_at_run"] = "latest"


class StepInputPort(BaseModel):
    model_config = ConfigDict(extra="forbid")

    port_id: str = Field(min_length=1, max_length=128)
    source: PortReference


class PipelineStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(min_length=1, max_length=128)
    type: Literal[
        "select_columns",
        "add_identifier",
        "rename_columns",
        "cast_columns",
        "filter_rows",
        "sort_rows",
        "deduplicate",
        "impute_missing",
        "derive_column",
        "aggregate",
        "join",
        "union",
        "map_categories",
        "custom_sql",
    ]
    inputs: list[StepInputPort] = Field(min_length=1)
    output_port_id: str = Field(default="out", min_length=1, max_length=128)
    config: dict[str, Any] = Field(default_factory=dict)


class PipelineOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_id: str = Field(min_length=1, max_length=128)
    input: PortReference
    materialization: Literal["temporary", "dataset"] = "temporary"
    write_mode: Literal["replace"] = "replace"
    dataset_name: str = Field(default="", max_length=255)
    business_case_role: Literal[
        "source",
        "training",
        "validation",
        "test",
        "scoring_input",
        "scoring_output",
        "monitoring_actuals",
        "reference",
    ] = "source"
    data_contract: "DataContract | None" = None


class DataContractColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    type: str = Field(min_length=1, max_length=128)
    nullable: bool = True
    unique: bool = False
    minimum: int | float | None = None
    maximum: int | float | None = None
    allowed_values: list[Any] | None = None
    policy: Literal["fail", "warn", "reject"] = "fail"

    @model_validator(mode="after")
    def validate_range(self) -> "DataContractColumn":
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError(f"Data contract column '{self.name}' has minimum greater than maximum")
        if self.allowed_values is not None and not self.allowed_values:
            raise ValueError(f"Data contract column '{self.name}' allowed_values cannot be empty")
        return self


class DataContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    columns: list[DataContractColumn] = Field(min_length=1)
    schema_drift_policy: Literal["fail", "warn"] = "fail"
    allow_unexpected_columns: bool = True

    @model_validator(mode="after")
    def validate_columns(self) -> "DataContract":
        names = [column.name for column in self.columns]
        if len(names) != len(set(names)):
            raise ValueError("Data contract column names must be unique")
        return self


class PipelineDefinition(BaseModel):
    """Stage 1 executable DAG contract.

    Inputs and outputs are graph nodes. Every edge targets a stable input port and
    references one stable upstream output port; array order has no execution meaning.
    """

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["1.0"] = "1.0"
    inputs: list[PipelineInput]
    steps: list[PipelineStep]
    outputs: list[PipelineOutput]
    parameters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_graph(self) -> PipelineDefinition:
        node_ids = [item.input_id for item in self.inputs]
        node_ids.extend(step.step_id for step in self.steps)
        node_ids.extend(output.output_id for output in self.outputs)
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("input_id, step_id and output_id values must be unique across the DAG")
        if not self.inputs:
            raise ValueError("An executable pipeline requires at least one input")
        if not self.outputs:
            raise ValueError("An executable pipeline requires at least one output")

        ports = {item.input_id: {item.output_port_id} for item in self.inputs}
        ports.update({step.step_id: {step.output_port_id} for step in self.steps})
        dependencies: dict[str, set[str]] = defaultdict(set)

        for step in self.steps:
            input_port_ids = [port.port_id for port in step.inputs]
            if len(input_port_ids) != len(set(input_port_ids)):
                raise ValueError(f"Step '{step.step_id}' has duplicate input port IDs")
            self._validate_arity(step)
            for port in step.inputs:
                self._validate_reference(step.step_id, port.source, ports)
                dependencies[step.step_id].add(port.source.node_id)
            validate_step_config(step)

        for output in self.outputs:
            self._validate_reference(output.output_id, output.input, ports)
            dependencies[output.output_id].add(output.input.node_id)

        self._assert_acyclic(node_ids, dependencies)
        reachable = set(item.input_id for item in self.inputs)
        for node_id in topological_order(self):
            if node_id in reachable:
                continue
            if any(parent in reachable for parent in dependencies.get(node_id, ())):
                reachable.add(node_id)
        disconnected = [output.output_id for output in self.outputs if output.output_id not in reachable]
        if disconnected:
            raise ValueError(f"Outputs are not reachable from a dataset input: {', '.join(disconnected)}")
        return self

    @staticmethod
    def _validate_reference(target_id: str, reference: PortReference, ports: dict[str, set[str]]) -> None:
        if reference.node_id == target_id:
            raise ValueError(f"Node '{target_id}' cannot reference itself")
        if reference.node_id not in ports:
            raise ValueError(f"Node '{target_id}' references unknown upstream node '{reference.node_id}'")
        if reference.port_id not in ports[reference.node_id]:
            raise ValueError(
                f"Node '{target_id}' references unknown port '{reference.port_id}' "
                f"on node '{reference.node_id}'"
            )

    @staticmethod
    def _validate_arity(step: PipelineStep) -> None:
        count = len(step.inputs)
        if step.type == "join" and count != 2:
            raise ValueError(f"Join step '{step.step_id}' requires exactly two inputs")
        if step.type == "union" and count < 2:
            raise ValueError(f"Union step '{step.step_id}' requires at least two inputs")
        if step.type not in {"join", "union"} and count != 1:
            raise ValueError(f"Step '{step.step_id}' requires exactly one input")

    @staticmethod
    def _assert_acyclic(node_ids: list[str], dependencies: dict[str, set[str]]) -> None:
        remaining = {node_id: set(dependencies.get(node_id, ())) for node_id in node_ids}
        children: dict[str, set[str]] = defaultdict(set)
        for node_id, parents in remaining.items():
            for parent in parents:
                children[parent].add(node_id)
        ready = deque(node_id for node_id, parents in remaining.items() if not parents)
        visited = 0
        while ready:
            resolved = ready.popleft()
            visited += 1
            for child in children.get(resolved, ()):
                remaining[child].remove(resolved)
                if not remaining[child]:
                    ready.append(child)
        if visited != len(node_ids):
            raise ValueError("Pipeline definition contains a cycle")


def topological_order(definition: PipelineDefinition) -> list[str]:
    nodes = [item.input_id for item in definition.inputs]
    nodes.extend(step.step_id for step in definition.steps)
    nodes.extend(output.output_id for output in definition.outputs)
    dependencies: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    for step in definition.steps:
        dependencies[step.step_id] = {port.source.node_id for port in step.inputs}
    for output in definition.outputs:
        dependencies[output.output_id] = {output.input.node_id}
    order: list[str] = []
    while dependencies:
        ready = sorted(node_id for node_id, parents in dependencies.items() if not parents)
        if not ready:
            raise ValueError("Pipeline definition contains a cycle")
        order.extend(ready)
        for node_id in ready:
            dependencies.pop(node_id)
        for parents in dependencies.values():
            parents.difference_update(ready)
    return order


def validate_step_config(step: PipelineStep) -> None:
    config = step.config
    required: dict[str, tuple[str, ...]] = {
        "select_columns": ("columns",),
        "add_identifier": ("mode", "output_column"),
        "rename_columns": ("renames",),
        "cast_columns": ("casts",),
        "filter_rows": (),
        "sort_rows": ("columns",),
        "deduplicate": ("columns",),
        "impute_missing": (),
        "derive_column": ("name", "expression"),
        "aggregate": ("aggregations",),
        "join": ("keys",),
        "map_categories": ("column", "mapping"),
        "custom_sql": ("sql",),
    }
    missing = [key for key in required.get(step.type, ()) if key not in config]
    if missing:
        raise ValueError(f"Step '{step.step_id}' is missing config fields: {', '.join(missing)}")
    allowed_fields: dict[str, set[str]] = {
        "select_columns": {"columns"},
        "add_identifier": {"mode", "output_column", "columns", "order_by", "start"},
        "rename_columns": {"renames"},
        "cast_columns": {"casts"},
        "filter_rows": {"mode", "conditions", "combine", "sql"},
        "sort_rows": {"columns"},
        "deduplicate": {"columns"},
        "impute_missing": {"values", "rules"},
        "derive_column": {"name", "expression"},
        "aggregate": {"group_by", "aggregations"},
        "join": {"join_type", "keys", "right_suffix"},
        "union": {"by_name"},
        "map_categories": {"column", "mapping", "output_column"},
        "custom_sql": {"sql"},
    }
    unexpected = sorted(set(config) - allowed_fields[step.type])
    if unexpected:
        raise ValueError(f"Step '{step.step_id}' has unsupported config fields: {', '.join(unexpected)}")
    if step.type == "join":
        port_ids = {port.port_id for port in step.inputs}
        if port_ids != {"left", "right"}:
            raise ValueError(f"Join step '{step.step_id}' must use input ports 'left' and 'right'")
    if step.type == "union" and len({port.port_id for port in step.inputs}) != len(step.inputs):
        raise ValueError(f"Union step '{step.step_id}' input ports must be unique")
    if step.type == "filter_rows":
        mode = config.get("mode", "visual")
        if mode not in {"visual", "sql"}:
            raise ValueError(f"Step '{step.step_id}' filter mode must be visual or sql")
        if mode == "sql":
            from app.shared.sql_security import validate_filter_sql

            _non_empty_string(config.get("sql"), step.step_id, "sql")
            validate_filter_sql(config["sql"])
        else:
            allowed = {
                "eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in",
                "contains", "starts_with", "ends_with", "is_null", "not_null",
            }
            for condition in _list_of_records(config.get("conditions"), step.step_id):
                if not isinstance(condition.get("column"), str) or not condition["column"]:
                    raise ValueError(f"Step '{step.step_id}' filter condition requires a column")
                if condition.get("operator") not in allowed:
                    raise ValueError(f"Step '{step.step_id}' contains an unsupported filter operator")
                if condition["operator"] in {"in", "not_in"} and (
                    not isinstance(condition.get("values"), list) or not condition["values"]
                ):
                    raise ValueError(f"Step '{step.step_id}' list filter requires non-empty values")
                if condition["operator"] not in {"in", "not_in", "is_null", "not_null"} and "value" not in condition:
                    raise ValueError(f"Step '{step.step_id}' filter condition requires a value")
    if step.type == "derive_column":
        _non_empty_string(config.get("name"), step.step_id, "name")
        validate_expression(config.get("expression"), step.step_id)
    if step.type == "add_identifier":
        mode = config.get("mode")
        if mode not in {"record_hash", "columns_hash", "sequence"}:
            raise ValueError(
                f"Step '{step.step_id}' identifier mode must be record_hash, columns_hash or sequence"
            )
        _non_empty_string(config.get("output_column"), step.step_id, "output_column")
        if mode == "columns_hash":
            _string_list(config.get("columns"), step.step_id, "columns", allow_empty=False)
        if mode == "sequence":
            order_by = _list_of_records(config.get("order_by"), step.step_id)
            order_columns: list[str] = []
            for rule in order_by:
                _non_empty_string(rule.get("column"), step.step_id, "column")
                order_columns.append(rule["column"])
                if rule.get("direction", "asc") not in {"asc", "desc"}:
                    raise ValueError(
                        f"Step '{step.step_id}' identifier sequence direction must be asc or desc"
                    )
            if len(order_columns) != len(set(order_columns)):
                raise ValueError(
                    f"Step '{step.step_id}' identifier sequence order columns must be unique"
                )
            start = config.get("start", 1)
            if isinstance(start, bool) or not isinstance(start, int) or start < 0:
                raise ValueError(
                    f"Step '{step.step_id}' identifier sequence start must be a non-negative integer"
                )
    if step.type in {"select_columns", "deduplicate"}:
        _string_list(config.get("columns"), step.step_id, "columns", allow_empty=step.type == "deduplicate")
    if step.type in {"rename_columns", "cast_columns"}:
        field = {"rename_columns": "renames", "cast_columns": "casts"}[step.type]
        _non_empty_mapping(config.get(field), step.step_id, field)
    if step.type == "impute_missing":
        if "rules" in config:
            allowed_methods = {"fixed", "constant", "mean", "median", "mode", "unknown", "drop_rows"}
            for rule in _list_of_records(config.get("rules"), step.step_id):
                _non_empty_string(rule.get("column"), step.step_id, "column")
                if rule.get("method") not in allowed_methods:
                    raise ValueError(f"Step '{step.step_id}' contains an unsupported imputation method")
                if rule.get("method") in {"fixed", "constant"} and "value" not in rule:
                    raise ValueError(f"Step '{step.step_id}' fixed imputation requires a value")
                if "add_indicator" in rule and not isinstance(rule.get("add_indicator"), bool):
                    raise ValueError(f"Step '{step.step_id}' add_indicator must be boolean")
        elif "values" in config:
            _non_empty_mapping(config.get("values"), step.step_id, "values")
        else:
            raise ValueError(f"Step '{step.step_id}' is missing config fields: rules")
    if step.type == "sort_rows":
        for rule in _list_of_records(config.get("columns"), step.step_id):
            _non_empty_string(rule.get("column"), step.step_id, "column")
            if rule.get("direction", "asc") not in {"asc", "desc"}:
                raise ValueError(f"Step '{step.step_id}' sort direction must be asc or desc")
    if step.type == "aggregate":
        _string_list(config.get("group_by", []), step.step_id, "group_by", allow_empty=True)
        for aggregation in _list_of_records(config.get("aggregations"), step.step_id):
            if aggregation.get("function") not in {"count", "count_distinct", "sum", "avg", "min", "max"}:
                raise ValueError(f"Step '{step.step_id}' contains an unsupported aggregate function")
            _non_empty_string(aggregation.get("column"), step.step_id, "column")
            _non_empty_string(aggregation.get("alias"), step.step_id, "alias")
    if step.type == "join":
        if config.get("join_type", "inner") not in {"inner", "left", "right", "full"}:
            raise ValueError(f"Step '{step.step_id}' contains an unsupported join type")
        for key in _list_of_records(config.get("keys"), step.step_id):
            _non_empty_string(key.get("left"), step.step_id, "left")
            _non_empty_string(key.get("right"), step.step_id, "right")
    if step.type == "union" and "by_name" in config and not isinstance(config["by_name"], bool):
        raise ValueError(f"Step '{step.step_id}' union by_name must be boolean")
    if step.type == "map_categories":
        _non_empty_string(config.get("column"), step.step_id, "column")
        if not isinstance(config.get("mapping"), dict):
            raise ValueError(f"Step '{step.step_id}' mapping must be an object")
        if "output_column" in config:
            _non_empty_string(config["output_column"], step.step_id, "output_column")
    if step.type == "custom_sql":
        from app.shared.sql_security import validate_user_sql

        _non_empty_string(config.get("sql"), step.step_id, "sql")
        validate_user_sql(config["sql"])


def validate_expression(value: Any, step_id: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"Step '{step_id}' expression must be an object")
    variants = [key for key in ("column", "literal", "operator") if key in value]
    if len(variants) != 1:
        raise ValueError(f"Step '{step_id}' expression must define exactly one of column, literal or operator")
    if "operator" in value:
        if value["operator"] not in {"add", "subtract", "multiply", "divide", "concat"}:
            raise ValueError(f"Step '{step_id}' contains an unsupported expression operator")
        validate_expression(value.get("left"), step_id)
        validate_expression(value.get("right"), step_id)


def _list_of_records(value: Any, step_id: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"Step '{step_id}' config field must be a list of objects")
    return value


def _string_list(value: Any, step_id: str, field: str, allow_empty: bool) -> None:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"Step '{step_id}' config '{field}' must be a list of non-empty strings")
    if not value and not allow_empty:
        raise ValueError(f"Step '{step_id}' config '{field}' cannot be empty")


def _non_empty_mapping(value: Any, step_id: str, field: str) -> None:
    if not isinstance(value, dict) or not value:
        raise ValueError(f"Step '{step_id}' config '{field}' must be a non-empty object")


def _non_empty_string(value: Any, step_id: str, field: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"Step '{step_id}' config '{field}' must be a non-empty string")
