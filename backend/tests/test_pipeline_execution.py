from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest
from pydantic import ValidationError

from app.modules.datasets.domain import DataAsset, DataAssetStatus, SourceType
from app.modules.datasets.repository import InMemoryDatasetRepository
from app.modules.pipelines.dag import PipelineDefinition
from app.modules.pipelines.domain import PipelineRun, PipelineRunStatus, PipelineRunTrigger
from app.modules.pipelines.execution import (
    CsvDatasetInputAdapter,
    DuckDbPipelineExecutionEngine,
    compile_condition,
)
from app.modules.pipelines.run_preview import PipelineRunOutputReader
from app.shared.sql_security import (
    bind_user_sql_to_inputs,
    validate_filter_sql,
    validate_user_sql,
)
from app.modules.pipelines.workflow import (
    normalize_workflow_definition,
    validate_workflow_definition,
)
from app.worker import tasks as worker_tasks


def _asset(asset_id: str, owner_id: str, path: Path, row_count: int) -> DataAsset:
    return DataAsset(
        id=asset_id,
        owner_id=owner_id,
        name=asset_id,
        source_type=SourceType.FILE,
        format="csv",
        location_uri=f"file://{path.as_posix()}",
        row_count=row_count,
        has_header=True,
        status=DataAssetStatus.READY,
    )


def test_dry_run_output_reader_paginates_and_profiles_full_parquet(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    output_path = repository_root / "users" / "owner-1" / "pipeline-runs" / "run-1" / "result.parquet"
    output_path.parent.mkdir(parents=True)
    connection = duckdb.connect()
    connection.execute(
        "COPY (SELECT row_number() OVER () AS id, CASE WHEN range < 60 THEN 0 ELSE 1 END AS species "
        "FROM range(120)) TO ? (FORMAT PARQUET)",
        [str(output_path)],
    )
    connection.close()
    run = PipelineRun(
        id="run-1",
        owner_id="owner-1",
        pipeline_id="pipeline-1",
        pipeline_version_id="version-1",
        business_case_id="bc-1",
        status=PipelineRunStatus.SUCCEEDED,
        trigger_type=PipelineRunTrigger.MANUAL,
        is_dry_run=True,
        output_row_count=120,
        output_manifest=[{
            "output_id": "result",
            "location_uri": f"file://{output_path.as_posix()}",
            "row_count": 120,
            "schema": [{"name": "id", "type": "BIGINT"}, {"name": "species", "type": "INTEGER"}],
        }],
    )
    reader = PipelineRunOutputReader(repository_root)

    page = reader.preview(run, output_id="result", limit=25, offset=50)
    assert page["returned_count"] == 25
    assert page["has_previous"] is True
    assert page["has_next"] is True
    assert [row["species"] for row in page["records"]].count(0) == 10
    assert [row["species"] for row in page["records"]].count(1) == 15

    profile = reader.profile(run, output_id="result", max_columns=10, top_n=10)
    species = next(item for item in profile["columns"] if item["name"] == "species")
    assert species["null_count"] == 0
    assert species["approx_distinct_count"] == 2
    assert species["top_values"] == [
        {"value": 0, "count": 60, "share": 0.5},
        {"value": 1, "count": 60, "share": 0.5},
    ]


def test_dag_rejects_cycles_and_unknown_ports() -> None:
    definition = {
        "contract_version": "1.0",
        "inputs": [{"input_id": "source", "dataset_id": "dataset", "output_port_id": "out"}],
        "steps": [
            {
                "step_id": "a",
                "type": "select_columns",
                "inputs": [{"port_id": "input", "source": {"node_id": "b", "port_id": "out"}}],
                "output_port_id": "out",
                "config": {"columns": ["id"]},
            },
            {
                "step_id": "b",
                "type": "select_columns",
                "inputs": [{"port_id": "input", "source": {"node_id": "a", "port_id": "out"}}],
                "output_port_id": "out",
                "config": {"columns": ["id"]},
            },
        ],
        "outputs": [
            {
                "output_id": "result",
                "input": {"node_id": "a", "port_id": "missing"},
                "materialization": "temporary",
            }
        ],
        "parameters": {},
    }

    with pytest.raises(ValidationError) as error:
        PipelineDefinition.model_validate(definition)

    assert "unknown port" in str(error.value)


def test_duckdb_engine_executes_multiple_csv_inputs_join_and_full_output(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    owner_id = "owner-1"
    source_directory = repository_root / "users" / owner_id / "datasets"
    source_directory.mkdir(parents=True)
    customers_path = source_directory / "customers.csv"
    orders_path = source_directory / "orders.csv"
    customers_path.write_text("customer_id,segment\n1,enterprise\n2,smb\n3,smb\n", encoding="utf-8")
    orders_path.write_text(
        "order_id,customer_id,amount\n10,1,100\n11,1,40\n12,2,20\n13,3,60\n",
        encoding="utf-8",
    )
    repository = InMemoryDatasetRepository()
    repository.add(_asset("customers", owner_id, customers_path, 3))
    repository.add(_asset("orders", owner_id, orders_path, 4))
    definition = PipelineDefinition.model_validate(
        {
            "contract_version": "1.0",
            "inputs": [
                {"input_id": "customers", "dataset_id": "customers", "output_port_id": "out"},
                {"input_id": "orders", "dataset_id": "orders", "output_port_id": "out"},
            ],
            "steps": [
                {
                    "step_id": "joined",
                    "type": "join",
                    "inputs": [
                        {"port_id": "left", "source": {"node_id": "orders", "port_id": "out"}},
                        {"port_id": "right", "source": {"node_id": "customers", "port_id": "out"}},
                    ],
                    "output_port_id": "out",
                    "config": {
                        "join_type": "inner",
                        "keys": [{"left": "customer_id", "right": "customer_id"}],
                    },
                },
                {
                    "step_id": "large_orders",
                    "type": "filter_rows",
                    "inputs": [{"port_id": "input", "source": {"node_id": "joined", "port_id": "out"}}],
                    "output_port_id": "out",
                    "config": {
                        "conditions": [{"column": "amount", "operator": "gte", "value": 50}],
                        "combine": "and",
                    },
                },
                {
                    "step_id": "gross_amount",
                    "type": "derive_column",
                    "inputs": [
                        {"port_id": "input", "source": {"node_id": "large_orders", "port_id": "out"}}
                    ],
                    "output_port_id": "out",
                    "config": {
                        "name": "gross_amount",
                        "expression": {
                            "operator": "multiply",
                            "left": {"column": "amount"},
                            "right": {"literal": 1.23},
                        },
                    },
                },
            ],
            "outputs": [
                {
                    "output_id": "result",
                    "input": {"node_id": "gross_amount", "port_id": "out"},
                    "materialization": "temporary",
                    "write_mode": "replace",
                }
            ],
            "parameters": {},
        }
    )
    adapter = CsvDatasetInputAdapter(repository=repository, repository_root=repository_root)
    engine = DuckDbPipelineExecutionEngine(input_adapter=adapter, repository_root=repository_root)

    result = engine.execute(definition, "run-1", owner_id, is_dry_run=True)

    assert result.input_row_count == 7
    assert result.processed_row_count == 7
    assert result.output_row_count == 2
    assert result.output_manifest[0]["data_scope"] == "full"
    assert result.output_manifest[0]["materialization"] == "temporary"
    output_path = Path(result.output_manifest[0]["location_uri"].removeprefix("file://"))
    rows = duckdb.connect().execute(
        "SELECT order_id, segment, gross_amount FROM read_parquet(?) ORDER BY order_id",
        [str(output_path)],
    ).fetchall()
    assert [(row[0], row[1], float(row[2])) for row in rows] == [
        (10, "enterprise", 123.0),
        (13, "smb", 73.8),
    ]


def test_csv_adapter_rejects_another_owners_dataset(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    path = repository_root / "users" / "owner-a" / "dataset.csv"
    path.parent.mkdir(parents=True)
    path.write_text("id\n1\n", encoding="utf-8")
    repository = InMemoryDatasetRepository()
    repository.add(_asset("private", "owner-a", path, 1))

    adapter = CsvDatasetInputAdapter(repository=repository, repository_root=repository_root)

    with pytest.raises(ValueError, match="not found"):
        adapter.relation("private", "owner-b")


@pytest.mark.parametrize(
    ("sql", "message"),
    [
        ("COPY input TO 'output.csv'", "read-only SELECT"),
        ("SELECT * FROM read_csv_auto('/tmp/secret.csv')", "forbidden external function"),
        ("SELECT * FROM information_schema.tables", "system catalog"),
        ("SELECT * FROM 'private.parquet'", "file or URI"),
        ("SELECT 1; SELECT 2", "exactly one"),
    ],
)
def test_user_written_sql_rejects_unsafe_queries(sql: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_user_sql(sql)


def test_failed_pipeline_run_is_persisted_and_fails_the_celery_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = SimpleNamespace(
        id="run-1",
        pipeline_version_id="version-1",
        status=PipelineRunStatus.QUEUED,
        started_at=None,
        finished_at=None,
        error_message="",
    )
    version = SimpleNamespace(definition={})

    class Repository:
        def get_run(self, run_id: str):
            return run if run_id == run.id else None

        def get_version(self, version_id: str):
            return version if version_id == run.pipeline_version_id else None

        @staticmethod
        def update_run(updated):
            return updated

    monkeypatch.setattr(worker_tasks, "PostgresPipelineRepository", Repository)

    with pytest.raises(Exception, match="validation error"):
        worker_tasks.execute_pipeline_run.run(run.id)

    assert run.status == PipelineRunStatus.FAILED
    assert run.error_message
    assert run.finished_at is not None


def test_user_written_sql_binds_only_declared_input_relations() -> None:
    connection = duckdb.connect()
    try:
        connection.execute('CREATE VIEW "__source" AS SELECT 1 AS value')
        query = bind_user_sql_to_inputs(
            connection,
            "WITH prepared AS (SELECT value * 2 AS value FROM input) SELECT * FROM prepared",
            {"input": "__source"},
        )
        assert connection.execute(query).fetchall() == [(2,)]

        with pytest.raises(ValueError, match="outside its declared inputs"):
            bind_user_sql_to_inputs(connection, "SELECT * FROM secret_table", {"input": "__source"})
    finally:
        connection.close()


def test_sql_where_filter_accepts_predicate_and_rejects_extra_clauses() -> None:
    assert validate_filter_sql("amount >= 100 AND status IN ('paid', 'sent')") == (
        "amount >= 100 AND status IN ('paid', 'sent')"
    )
    with pytest.raises(ValueError, match="forbidden clause"):
        validate_filter_sql("amount >= 100 UNION SELECT * FROM secret")


def test_duckdb_engine_executes_sql_where_filter(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    owner_id = "owner-1"
    path = repository_root / "users" / owner_id / "dataset.csv"
    path.parent.mkdir(parents=True)
    path.write_text("id,amount,status\n1,20,new\n2,100,paid\n3,150,sent\n", encoding="utf-8")
    repository = InMemoryDatasetRepository()
    repository.add(_asset("orders", owner_id, path, 3))
    definition = PipelineDefinition.model_validate(
        {
            "contract_version": "1.0",
            "inputs": [{"input_id": "orders", "dataset_id": "orders", "output_port_id": "out"}],
            "steps": [{
                "step_id": "filter",
                "type": "filter_rows",
                "inputs": [{"port_id": "input", "source": {"node_id": "orders", "port_id": "out"}}],
                "output_port_id": "out",
                "config": {"mode": "sql", "sql": "amount >= 100 AND status IN ('paid', 'sent')"},
            }],
            "outputs": [{
                "output_id": "result",
                "input": {"node_id": "filter", "port_id": "out"},
                "materialization": "temporary",
            }],
            "parameters": {},
        }
    )
    engine = DuckDbPipelineExecutionEngine(
        input_adapter=CsvDatasetInputAdapter(repository=repository, repository_root=repository_root),
        repository_root=repository_root,
    )

    result = engine.execute(definition, "where-run", owner_id, is_dry_run=True)

    assert result.output_row_count == 2


def test_duckdb_engine_executes_rich_imputation_rules(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    owner_id = "owner-1"
    path = repository_root / "users" / owner_id / "dataset.csv"
    path.parent.mkdir(parents=True)
    path.write_text(
        "id,petal_len,species,required\n"
        "1,1.0,setosa,yes\n"
        "2,,setosa,yes\n"
        "3,3.0,,yes\n"
        "4,100.0,virginica,\n",
        encoding="utf-8",
    )
    repository = InMemoryDatasetRepository()
    repository.add(_asset("iris", owner_id, path, 4))
    definition = PipelineDefinition.model_validate(
        {
            "contract_version": "1.0",
            "inputs": [{"input_id": "iris", "dataset_id": "iris", "output_port_id": "out"}],
            "steps": [{
                "step_id": "impute",
                "type": "impute_missing",
                "inputs": [{"port_id": "input", "source": {"node_id": "iris", "port_id": "out"}}],
                "output_port_id": "out",
                "config": {
                    "rules": [
                        {"column": "petal_len", "method": "median", "add_indicator": True},
                        {"column": "species", "method": "mode", "add_indicator": True},
                        {"column": "required", "method": "drop_rows"},
                    ]
                },
            }],
            "outputs": [{
                "output_id": "result",
                "input": {"node_id": "impute", "port_id": "out"},
                "materialization": "temporary",
            }],
            "parameters": {},
        }
    )
    engine = DuckDbPipelineExecutionEngine(
        input_adapter=CsvDatasetInputAdapter(repository=repository, repository_root=repository_root),
        repository_root=repository_root,
    )

    result = engine.execute(definition, "impute-run", owner_id, is_dry_run=True)

    assert result.output_row_count == 3
    output_path = Path(result.output_manifest[0]["location_uri"].removeprefix("file://"))
    rows = duckdb.connect().execute(
        "SELECT id, petal_len, petal_len__was_missing, species, species__was_missing "
        "FROM read_parquet(?) ORDER BY id",
        [str(output_path)],
    ).fetchall()
    assert rows == [
        (1, 1.0, False, "setosa", False),
        (2, 2.0, True, "setosa", False),
        (3, 3.0, False, "setosa", True),
    ]


def test_map_categories_can_feed_integer_cast(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    owner_id = "owner-1"
    path = repository_root / "users" / owner_id / "iris.csv"
    path.parent.mkdir(parents=True)
    path.write_text(
        "petal_length,petal_width,species\n"
        "1.4,0.2,setosa\n"
        "4.7,1.4,versicolor\n"
        "5.1,1.8,virginica\n",
        encoding="utf-8",
    )
    repository = InMemoryDatasetRepository()
    repository.add(_asset("iris", owner_id, path, 3))
    definition = PipelineDefinition.model_validate(
        {
            "contract_version": "1.0",
            "inputs": [{"input_id": "source_1", "dataset_id": "iris", "output_port_id": "out"}],
            "steps": [
                {
                    "step_id": "filter",
                    "type": "filter_rows",
                    "inputs": [{"port_id": "input", "source": {"node_id": "source_1", "port_id": "out"}}],
                    "output_port_id": "out",
                    "config": {
                        "mode": "visual",
                        "combine": "and",
                        "conditions": [{"column": "species", "operator": "in", "values": ["versicolor", "virginica"]}],
                    },
                },
                {
                    "step_id": "map",
                    "type": "map_categories",
                    "inputs": [{"port_id": "input", "source": {"node_id": "filter", "port_id": "out"}}],
                    "output_port_id": "out",
                    "config": {"column": "species", "mapping": {"virginica": 1, "versicolor": 0}},
                },
                {
                    "step_id": "cast",
                    "type": "cast_columns",
                    "inputs": [{"port_id": "input", "source": {"node_id": "map", "port_id": "out"}}],
                    "output_port_id": "out",
                    "config": {"casts": {"species": "INTEGER"}},
                },
            ],
            "outputs": [{
                "output_id": "result",
                "input": {"node_id": "cast", "port_id": "out"},
                "materialization": "temporary",
            }],
            "parameters": {},
        }
    )
    engine = DuckDbPipelineExecutionEngine(
        input_adapter=CsvDatasetInputAdapter(repository=repository, repository_root=repository_root),
        repository_root=repository_root,
    )

    result = engine.execute(definition, "map-cast-run", owner_id, is_dry_run=True)

    output_path = Path(result.output_manifest[0]["location_uri"].removeprefix("file://"))
    rows = duckdb.connect().execute(
        "SELECT species FROM read_parquet(?) ORDER BY species",
        [str(output_path)],
    ).fetchall()
    assert rows == [(0,), (1,)]


def test_duckdb_engine_executes_user_written_sql_on_full_input(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    owner_id = "owner-1"
    path = repository_root / "users" / owner_id / "dataset.csv"
    path.parent.mkdir(parents=True)
    path.write_text("id,amount\n1,20\n2,100\n3,150\n", encoding="utf-8")
    repository = InMemoryDatasetRepository()
    repository.add(_asset("orders", owner_id, path, 3))
    definition = PipelineDefinition.model_validate(
        {
            "contract_version": "1.0",
            "inputs": [{"input_id": "orders", "dataset_id": "orders", "output_port_id": "out"}],
            "steps": [
                {
                    "step_id": "written-sql",
                    "type": "custom_sql",
                    "inputs": [{"port_id": "input", "source": {"node_id": "orders", "port_id": "out"}}],
                    "output_port_id": "out",
                    "config": {
                        "sql": (
                            "SELECT id, amount, amount * 1.23 AS gross_amount "
                            "FROM input WHERE amount >= 100"
                        )
                    },
                }
            ],
            "outputs": [
                {
                    "output_id": "result",
                    "input": {"node_id": "written-sql", "port_id": "out"},
                    "materialization": "temporary",
                    "write_mode": "replace",
                }
            ],
            "parameters": {},
        }
    )
    engine = DuckDbPipelineExecutionEngine(
        input_adapter=CsvDatasetInputAdapter(repository=repository, repository_root=repository_root),
        repository_root=repository_root,
    )

    result = engine.execute(definition, "custom-sql-run", owner_id, is_dry_run=True)

    assert result.input_row_count == 3
    assert result.output_row_count == 2
    assert result.output_manifest[0]["data_scope"] == "full"


def test_legacy_de_definition_is_migrated_to_one_high_level_workflow_step() -> None:
    legacy = {
        "contract_version": "1.0",
        "inputs": [{"input_id": "source", "dataset_id": "dataset", "output_port_id": "out"}],
        "steps": [],
        "outputs": [
            {
                "output_id": "result",
                "input": {"node_id": "source", "port_id": "out"},
                "materialization": "dataset",
                "dataset_name": "Prepared data",
            }
        ],
        "parameters": {},
    }

    workflow = validate_workflow_definition(legacy, executable=True)

    assert workflow["contract_version"] == "2.0"
    assert workflow["steps"][0]["type"] == "data_engineering"
    assert workflow["steps"][0]["config"]["definition"]["contract_version"] == "1.0"
    assert workflow["outputs"][0]["source"]["step_id"] == "de_1"


def test_empty_workflow_is_valid_as_draft_but_not_executable() -> None:
    empty = normalize_workflow_definition({})

    assert validate_workflow_definition(empty, executable=False)["steps"] == []
    with pytest.raises(ValueError, match="at least one workflow step"):
        validate_workflow_definition(empty, executable=True)


def test_metadata_aware_filter_operators_compile_to_safe_predicates() -> None:
    assert compile_condition(
        {"column": "species", "operator": "not_in", "values": ["setosa", "versicolor"]}
    ) == '"species" NOT IN (\'setosa\', \'versicolor\')'
    assert compile_condition(
        {"column": "description", "operator": "contains", "value": "priority"}
    ) == 'CAST("description" AS VARCHAR) ILIKE \'%priority%\''


def test_metadata_aware_filter_operator_requires_non_empty_list() -> None:
    with pytest.raises(ValueError, match="non-empty values list"):
        compile_condition({"column": "species", "operator": "not_in", "values": []})
