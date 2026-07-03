from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
import duckdb

from app.modules.datasets.columnar import ColumnarDatasetStore
from app.modules.datasets.domain import DataAsset, DataAssetStatus, SourceType
from app.modules.datasets.repository import DatasetRepository, PostgresDatasetRepository
from app.modules.pipelines.dag import PipelineDefinition, PipelineStep, topological_order
from app.modules.pipelines.data_quality import evaluate_data_contract
from app.modules.pipelines.runtime import (
    SourceRelation,
    json_safe,
    relation_columns,
    safe_filename,
    sql_literal,
)
from app.shared.sql_security import (
    bind_user_sql_to_inputs,
    identifier,
    validate_filter_sql,
)
from app.shared.duckdb_runtime import configured_duckdb_connection, write_parquet_atomic


class PipelineInputAdapter(Protocol):
    def relation(self, dataset_id: str, owner_id: str) -> SourceRelation:
        ...


class CsvDatasetInputAdapter:
    """Resolves an owned CSV or platform-generated Parquet into a lazy relation."""

    def __init__(
        self,
        repository: DatasetRepository | None = None,
        repository_root: Path | None = None,
    ) -> None:
        self.repository = repository or PostgresDatasetRepository()
        self.repository_root = (repository_root or Path("data/repository")).resolve()
        self.store = ColumnarDatasetStore(self.repository_root)

    def relation(self, dataset_id: str, owner_id: str) -> SourceRelation:
        asset = self.repository.get(dataset_id)
        if not asset or asset.owner_id != owner_id or asset.status == DataAssetStatus.DELETED:
            raise ValueError(f"Input dataset '{dataset_id}' was not found")
        self._validate_asset(asset)
        path = self.store.source_path(asset)
        if not path.is_file():
            raise ValueError(f"Input dataset file for '{dataset_id}' was not found")
        if asset.format.lower() == "parquet":
            return SourceRelation(
                sql=f"read_parquet({sql_literal(str(path))})",
                row_count=int(asset.row_count or -1),
            )
        header = "true" if asset.has_header is not False else "false"
        relation = (
            "read_csv_auto("
            f"{sql_literal(str(path))}, header={header}, sample_size=-1, "
            "null_padding=true, ignore_errors=false)"
        )
        return SourceRelation(sql=relation, row_count=int(asset.row_count or -1))

    @staticmethod
    def _validate_asset(asset: DataAsset) -> None:
        if asset.source_type != SourceType.FILE or asset.format.lower() not in {"csv", "parquet"}:
            raise ValueError(f"Input dataset '{asset.id}' is not a supported CSV/Parquet dataset")
        if not asset.location_uri or not asset.location_uri.startswith("file://"):
            raise ValueError(f"Input dataset '{asset.id}' has no local file location")


@dataclass(frozen=True)
class PipelineExecutionResult:
    input_row_count: int
    processed_row_count: int
    output_row_count: int
    output_manifest: list[dict[str, Any]]
    warnings: list[str]
    rejected_row_count: int = 0


class PipelineExecutionEngine(Protocol):
    def execute(
        self,
        definition: PipelineDefinition,
        run_id: str,
        owner_id: str,
        is_dry_run: bool,
    ) -> PipelineExecutionResult:
        ...


class DuckDbPipelineExecutionEngine:
    def __init__(
        self,
        input_adapter: PipelineInputAdapter | None = None,
        repository_root: Path | None = None,
    ) -> None:
        self.repository_root = (repository_root or Path("data/repository")).resolve()
        self.input_adapter = input_adapter or CsvDatasetInputAdapter(repository_root=self.repository_root)

    def execute(
        self,
        definition: PipelineDefinition,
        run_id: str,
        owner_id: str,
        is_dry_run: bool,
    ) -> PipelineExecutionResult:
        run_directory = self._run_directory(owner_id, run_id)
        temp_directory = run_directory / ".duckdb-tmp"
        connection = configured_duckdb_connection(temp_directory)
        relations: dict[tuple[str, str], str] = {}
        input_counts: list[int] = []
        manifests: list[dict[str, Any]] = []
        warnings: list[str] = []
        rejected_row_count = 0
        try:
            for pipeline_input in definition.inputs:
                source = self.input_adapter.relation(pipeline_input.dataset_id, owner_id)
                view = internal_name("input", pipeline_input.input_id)
                connection.execute(f"CREATE TEMP VIEW {identifier(view)} AS SELECT * FROM {source.sql}")
                relations[(pipeline_input.input_id, pipeline_input.output_port_id)] = view
                count = source.row_count
                if count < 0:
                    count = int(connection.execute(f"SELECT count(*) FROM {identifier(view)}").fetchone()[0])
                input_counts.append(count)

            steps = {step.step_id: step for step in definition.steps}
            outputs = {output.output_id: output for output in definition.outputs}
            for node_id in topological_order(definition):
                if node_id in steps:
                    step = steps[node_id]
                    query = compile_step(connection, step, relations)
                    view = internal_name("step", step.step_id)
                    connection.execute(f"CREATE TEMP VIEW {identifier(view)} AS {query}")
                    relations[(step.step_id, step.output_port_id)] = view
                elif node_id in outputs:
                    output = outputs[node_id]
                    upstream = relations[(output.input.node_id, output.input.port_id)]
                    quality = evaluate_data_contract(connection, upstream, output.data_contract)
                    warnings.extend(quality.warnings)
                    rejected_row_count += quality.rejected_row_count
                    destination = run_directory / f"{safe_filename(output.output_id)}.parquet"
                    write_stats = write_parquet_atomic(
                        connection,
                        (
                            f"SELECT * FROM {identifier(upstream)} "
                            f"WHERE NOT ({quality.reject_predicate})"
                        ),
                        destination,
                    )
                    row_count = write_stats.row_count
                    schema_rows = write_stats.schema_rows
                    effective_materialization = "temporary" if is_dry_run else output.materialization
                    preview_cursor = connection.execute(
                        f"SELECT * FROM read_parquet({sql_literal(str(destination))}) LIMIT 50"
                    )
                    preview_names = [str(item[0]) for item in preview_cursor.description or []]
                    preview_records = [
                        {
                            name: json_safe(value)
                            for name, value in zip(preview_names, row, strict=True)
                        }
                        for row in preview_cursor.fetchall()
                    ]
                    manifests.append(
                        {
                            "output_id": output.output_id,
                            "materialization": effective_materialization,
                            "write_mode": "replace",
                            "location_uri": f"file://{destination.as_posix()}",
                            "row_count": row_count,
                            "schema": [{"name": str(row[0]), "type": str(row[1])} for row in schema_rows],
                            "data_scope": "full",
                            "is_dry_run": is_dry_run,
                            "dataset_name": output.dataset_name or output.output_id,
                            "business_case_role": output.business_case_role,
                            "quality": quality.report,
                            "preview": {
                                "records": preview_records,
                                "returned_count": len(preview_records),
                                "limit": 50,
                                "sampled": row_count > len(preview_records),
                            },
                        }
                    )
                    if quality.rejected_row_count:
                        rejected_output_id = f"{output.output_id}__rejected"
                        rejected_destination = run_directory / f"{safe_filename(rejected_output_id)}.parquet"
                        rejected_stats = write_parquet_atomic(
                            connection,
                            (
                                "SELECT row_number() OVER () AS _quality_source_row_number, *, "
                                f"{quality.reject_reason_expression} AS _quality_rejection_reason "
                                f"FROM {identifier(upstream)} WHERE {quality.reject_predicate}"
                            ),
                            rejected_destination,
                        )
                        manifests.append(
                            {
                                "output_id": rejected_output_id,
                                "materialization": "temporary" if is_dry_run else "dataset",
                                "write_mode": "replace",
                                "location_uri": f"file://{rejected_destination.as_posix()}",
                                "row_count": rejected_stats.row_count,
                                "schema": [
                                    {"name": str(row[0]), "type": str(row[1])}
                                    for row in rejected_stats.schema_rows
                                ],
                                "data_scope": "full",
                                "is_dry_run": is_dry_run,
                                "dataset_name": f"{output.dataset_name or output.output_id} rejected records",
                                "business_case_role": "reference",
                                "quality_output_kind": "rejected_records",
                                "source_output_id": output.output_id,
                                "preview": {
                                    "records": [],
                                    "returned_count": 0,
                                    "limit": 0,
                                    "sampled": True,
                                },
                            }
                        )
        finally:
            connection.close()

        return PipelineExecutionResult(
            input_row_count=sum(input_counts),
            processed_row_count=sum(input_counts),
            output_row_count=sum(
                int(item["row_count"])
                for item in manifests
                if item.get("quality_output_kind") != "rejected_records"
            ),
            output_manifest=manifests,
            warnings=warnings,
            rejected_row_count=rejected_row_count,
        )

    def _run_directory(self, owner_id: str, run_id: str) -> Path:
        root = self.repository_root / "users"
        directory = (root / owner_id / "pipeline-runs" / run_id).resolve()
        try:
            directory.relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError("Pipeline run output path is outside the repository root") from exc
        directory.mkdir(parents=True, exist_ok=True)
        return directory


def compile_step(
    connection: duckdb.DuckDBPyConnection,
    step: PipelineStep,
    relations: dict[tuple[str, str], str],
) -> str:
    sources = {
        port.port_id: relations[(port.source.node_id, port.source.port_id)]
        for port in step.inputs
    }
    source_names = list(sources.values())
    source = identifier(source_names[0])
    config = step.config

    if step.type == "select_columns":
        columns = require_string_list(config["columns"], "columns")
        return f"SELECT {', '.join(identifier(column) for column in columns)} FROM {source}"
    if step.type == "add_identifier":
        return compile_add_identifier(connection, source_names[0], config)
    if step.type == "rename_columns":
        renames = require_mapping(config["renames"], "renames")
        columns = relation_columns(connection, source_names[0])
        selection = [
            f"{identifier(column)} AS {identifier(str(renames[column]))}" if column in renames else identifier(column)
            for column in columns
        ]
        return f"SELECT {', '.join(selection)} FROM {source}"
    if step.type == "cast_columns":
        casts = require_mapping(config["casts"], "casts")
        columns = relation_columns(connection, source_names[0])
        selection = []
        for column in columns:
            if column in casts:
                target = validated_type(str(casts[column]))
                selection.append(f"CAST({identifier(column)} AS {target}) AS {identifier(column)}")
            else:
                selection.append(identifier(column))
        return f"SELECT {', '.join(selection)} FROM {source}"
    if step.type == "filter_rows":
        if config.get("mode", "visual") == "sql":
            predicate = validate_filter_sql(str(config["sql"]))
            return bind_user_sql_to_inputs(
                connection,
                f"SELECT * FROM input WHERE {predicate}",
                {"input": source_names[0]},
            )
        combine = str(config.get("combine", "and")).upper()
        if combine not in {"AND", "OR"}:
            raise ValueError("filter_rows combine must be 'and' or 'or'")
        clauses = [compile_condition(item) for item in require_record_list(config["conditions"], "conditions")]
        return f"SELECT * FROM {source} WHERE {f' {combine} '.join(clauses)}"
    if step.type == "sort_rows":
        rules = require_record_list(config["columns"], "columns")
        order = []
        for rule in rules:
            direction = str(rule.get("direction", "asc")).upper()
            if direction not in {"ASC", "DESC"}:
                raise ValueError("sort direction must be asc or desc")
            order.append(f"{identifier(str(rule['column']))} {direction}")
        return f"SELECT * FROM {source} ORDER BY {', '.join(order)}"
    if step.type == "deduplicate":
        columns = require_string_list(config["columns"], "columns", allow_empty=True)
        if not columns:
            return f"SELECT DISTINCT * FROM {source}"
        partition = ", ".join(identifier(column) for column in columns)
        return f"SELECT * FROM {source} QUALIFY row_number() OVER (PARTITION BY {partition}) = 1"
    if step.type == "impute_missing":
        return compile_impute_missing(connection, source_names[0], config)
    if step.type == "derive_column":
        name = str(config["name"])
        expression = compile_expression(config["expression"])
        return f"SELECT *, {expression} AS {identifier(name)} FROM {source}"
    if step.type == "aggregate":
        groups = require_string_list(config.get("group_by", []), "group_by", allow_empty=True)
        selections = [identifier(column) for column in groups]
        allowed = {"count", "count_distinct", "sum", "avg", "min", "max"}
        for aggregation in require_record_list(config["aggregations"], "aggregations"):
            function = str(aggregation.get("function", "")).lower()
            if function not in allowed:
                raise ValueError(f"Unsupported aggregate function '{function}'")
            column = str(aggregation.get("column", "*"))
            argument = "*" if column == "*" else identifier(column)
            if function == "count_distinct":
                expression = f"count(DISTINCT {argument})"
            else:
                expression = f"{function}({argument})"
            selections.append(f"{expression} AS {identifier(str(aggregation['alias']))}")
        group_sql = f" GROUP BY {', '.join(identifier(column) for column in groups)}" if groups else ""
        return f"SELECT {', '.join(selections)} FROM {source}{group_sql}"
    if step.type == "join":
        return compile_join(connection, sources, config)
    if step.type == "union":
        by_name = bool(config.get("by_name", True))
        operator = "UNION ALL BY NAME" if by_name else "UNION ALL"
        return f" {operator} ".join(f"SELECT * FROM {identifier(name)}" for name in source_names)
    if step.type == "map_categories":
        column = str(config["column"])
        output = str(config.get("output_column") or column)
        mapping = require_mapping(config["mapping"], "mapping")
        cases = " ".join(
            f"WHEN {identifier(column)} = {sql_literal(key)} THEN {sql_literal(str(value))}"
            for key, value in mapping.items()
        )
        expression = f"CASE {cases} ELSE CAST({identifier(column)} AS VARCHAR) END"
        if output == column:
            columns = relation_columns(connection, source_names[0])
            selection = [
                f"{expression} AS {identifier(item)}" if item == column else identifier(item)
                for item in columns
            ]
            return f"SELECT {', '.join(selection)} FROM {source}"
        return f"SELECT *, {expression} AS {identifier(output)} FROM {source}"
    if step.type == "custom_sql":
        return bind_user_sql_to_inputs(connection, str(config["sql"]), sources)
    raise ValueError(f"Unsupported pipeline step type '{step.type}'")


def compile_add_identifier(
    connection: duckdb.DuckDBPyConnection,
    source_name: str,
    config: dict[str, Any],
) -> str:
    available = relation_columns(connection, source_name)
    output_column = str(config["output_column"])
    if output_column in available:
        raise ValueError(f"Identifier output column '{output_column}' already exists")

    mode = str(config["mode"])
    source = identifier(source_name)
    if mode in {"record_hash", "columns_hash"}:
        columns = (
            available
            if mode == "record_hash"
            else require_string_list(config.get("columns"), "columns")
        )
        missing = sorted(set(columns) - set(available))
        if missing:
            raise ValueError(f"Identifier references unknown columns: {', '.join(missing)}")
        encoded = [
            (
                f"CASE WHEN {identifier(column)} IS NULL THEN 'N;' "
                f"ELSE 'V' || length(CAST({identifier(column)} AS VARCHAR))::VARCHAR "
                f"|| ':' || CAST({identifier(column)} AS VARCHAR) || ';' END"
            )
            for column in columns
        ]
        digest = f"sha256(concat({', '.join(encoded)}))"
        return f"SELECT *, {digest} AS {identifier(output_column)} FROM {source}"

    if mode == "sequence":
        order_by = require_record_list(config.get("order_by"), "order_by")
        order_columns = [str(rule["column"]) for rule in order_by]
        missing = sorted(set(order_columns) - set(available))
        if missing:
            raise ValueError(f"Identifier ordering references unknown columns: {', '.join(missing)}")
        order_sql = ", ".join(
            f"{identifier(str(rule['column']))} {str(rule.get('direction', 'asc')).upper()}"
            for rule in order_by
        )
        start = int(config.get("start", 1))
        sequence = f"row_number() OVER (ORDER BY {order_sql}) + {start - 1}"
        return f"SELECT *, {sequence} AS {identifier(output_column)} FROM {source}"

    raise ValueError(f"Unsupported identifier mode '{mode}'")


def compile_join(
    connection: duckdb.DuckDBPyConnection,
    sources: dict[str, str],
    config: dict[str, Any],
) -> str:
    left_name, right_name = sources["left"], sources["right"]
    join_type = str(config.get("join_type", "inner")).upper()
    if join_type not in {"INNER", "LEFT", "RIGHT", "FULL"}:
        raise ValueError("join_type must be inner, left, right or full")
    keys = require_record_list(config["keys"], "keys")
    if not keys:
        raise ValueError("join requires at least one key pair")
    conditions = [
        f"l.{identifier(str(key['left']))} = r.{identifier(str(key['right']))}"
        for key in keys
    ]
    left_columns = relation_columns(connection, left_name)
    right_columns = relation_columns(connection, right_name)
    right_key_columns = {str(key["right"]) for key in keys}
    suffix = str(config.get("right_suffix", "_right"))
    selections = [f"l.{identifier(column)}" for column in left_columns]
    for column in right_columns:
        if column in right_key_columns:
            continue
        output = f"{column}{suffix}" if column in left_columns else column
        selections.append(f"r.{identifier(column)} AS {identifier(output)}")
    return (
        f"SELECT {', '.join(selections)} FROM {identifier(left_name)} l "
        f"{join_type} JOIN {identifier(right_name)} r ON {' AND '.join(conditions)}"
    )


def compile_impute_missing(
    connection: duckdb.DuckDBPyConnection,
    source_name: str,
    config: dict[str, Any],
) -> str:
    columns = relation_columns(connection, source_name)
    rules = imputation_rules(config)
    rules_by_column = {str(rule["column"]): rule for rule in rules}
    missing = sorted(set(rules_by_column) - set(columns))
    if missing:
        raise ValueError(f"Imputation references unknown columns: {', '.join(missing)}")

    where_clauses = [
        f"{identifier(column)} IS NOT NULL"
        for column, rule in rules_by_column.items()
        if str(rule.get("method")) == "drop_rows"
    ]
    selection: list[str] = []
    for column in columns:
        column_sql = identifier(column)
        rule = rules_by_column.get(column)
        if not rule or str(rule.get("method")) == "drop_rows":
            selection.append(column_sql)
        else:
            selection.append(f"{imputation_expression(source_name, column, rule)} AS {column_sql}")
        if rule and bool(rule.get("add_indicator")):
            selection.append(f"{column_sql} IS NULL AS {identifier(f'{column}__was_missing')}")
    where_sql = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    return f"SELECT {', '.join(selection)} FROM {identifier(source_name)}{where_sql}"


def imputation_rules(config: dict[str, Any]) -> list[dict[str, Any]]:
    if "rules" in config:
        return require_record_list(config["rules"], "rules")
    values = require_mapping(config.get("values"), "values")
    return [{"column": column, "method": "fixed", "value": value} for column, value in values.items()]


def imputation_expression(source_name: str, column: str, rule: dict[str, Any]) -> str:
    column_sql = identifier(column)
    method = str(rule.get("method", "fixed"))
    if method in {"fixed", "constant"}:
        replacement = sql_literal(rule.get("value"))
    elif method == "unknown":
        replacement = sql_literal("Unknown")
    elif method == "mean":
        replacement = f"avg({column_sql}) OVER ()"
    elif method == "median":
        replacement = f"median({column_sql}) OVER ()"
    elif method == "mode":
        replacement = (
            f"(SELECT {column_sql} FROM {identifier(source_name)} "
            f"WHERE {column_sql} IS NOT NULL GROUP BY {column_sql} "
            f"ORDER BY count(*) DESC, {column_sql} LIMIT 1)"
        )
    else:
        raise ValueError(f"Unsupported imputation method '{method}'")
    return f"coalesce({column_sql}, {replacement})"


def compile_condition(condition: dict[str, Any]) -> str:
    column = identifier(str(condition["column"]))
    operator = str(condition["operator"])
    if operator == "is_null":
        return f"{column} IS NULL"
    if operator == "not_null":
        return f"{column} IS NOT NULL"
    if operator in {"in", "not_in"}:
        values = condition.get("values")
        if not isinstance(values, list) or not values:
            raise ValueError("A list filter requires a non-empty values list")
        keyword = "NOT IN" if operator == "not_in" else "IN"
        return f"{column} {keyword} ({', '.join(sql_literal(value) for value in values)})"
    if operator in {"contains", "starts_with", "ends_with"}:
        value = str(condition.get("value") or "")
        pattern = f"%{value}%" if operator == "contains" else f"{value}%" if operator == "starts_with" else f"%{value}"
        return f"CAST({column} AS VARCHAR) ILIKE {sql_literal(pattern)}"
    symbols = {"eq": "=", "ne": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
    return f"{column} {symbols[operator]} {sql_literal(condition.get('value'))}"


def compile_expression(expression: dict[str, Any]) -> str:
    if "column" in expression:
        return identifier(str(expression["column"]))
    if "literal" in expression:
        return sql_literal(expression["literal"])
    symbols = {"add": "+", "subtract": "-", "multiply": "*", "divide": "/", "concat": "||"}
    return (
        f"({compile_expression(expression['left'])} {symbols[str(expression['operator'])]} "
        f"{compile_expression(expression['right'])})"
    )


def validated_type(value: str) -> str:
    normalized = value.strip().upper()
    allowed = {
        "BOOLEAN", "TINYINT", "SMALLINT", "INTEGER", "BIGINT", "FLOAT", "DOUBLE",
        "DECIMAL", "VARCHAR", "DATE", "TIMESTAMP", "TIMESTAMPTZ",
    }
    if normalized not in allowed:
        raise ValueError(f"Unsupported cast target type '{value}'")
    return normalized


def require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not value:
        raise ValueError(f"'{name}' must be a non-empty object")
    return {str(key): item for key, item in value.items()}


def require_record_list(value: Any, name: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"'{name}' must be a non-empty list of objects")
    return value


def require_string_list(value: Any, name: str, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"'{name}' must be a list of non-empty strings")
    if not value and not allow_empty:
        raise ValueError(f"'{name}' cannot be empty")
    return value


def internal_name(kind: str, stable_id: str) -> str:
    return f"__mlapp_{kind}_{stable_id}"
