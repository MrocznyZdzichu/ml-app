from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest
from pydantic import ValidationError

from app.modules.datasets.domain import DataAsset, DataAssetStatus, SourceType
from app.modules.datasets.repository import InMemoryDatasetRepository
from app.modules.business_cases.repository import InMemoryBusinessCaseRepository
from app.modules.pipelines.dag import PipelineDefinition
from app.modules.pipelines.domain import (
    PipelineRun,
    PipelineRunStatus,
    PipelineRunTrigger,
    PipelineVersion,
    PipelineVersionStatus,
)
from app.modules.pipelines.execution import (
    CsvDatasetInputAdapter,
    DuckDbPipelineExecutionEngine,
    compile_condition,
)
from app.modules.pipelines.run_preview import PipelineRunOutputReader
from app.modules.pipelines.step_handlers import (
    HandledStepResult,
    PipelineStepHandlerRegistry,
    StepExecutionContext,
)
from app.modules.pipelines.materialization import PipelineOutputMaterializer
from app.shared.sql_security import (
    bind_user_sql_to_inputs,
    validate_filter_sql,
    validate_user_sql,
)
from app.modules.pipelines.workflow import (
    WorkflowDefinition,
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


def test_dry_run_output_reader_disambiguates_same_output_id_by_pipeline_step(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    output_dir = repository_root / "users" / "owner-1" / "pipeline-runs" / "run-1"
    output_dir.mkdir(parents=True)
    de_path = output_dir / "de-result.parquet"
    fe_path = output_dir / "fe-result.parquet"
    connection = duckdb.connect()
    connection.execute("COPY (SELECT 1 AS marker) TO ? (FORMAT PARQUET)", [str(de_path)])
    connection.execute("COPY (SELECT 2 AS marker) TO ? (FORMAT PARQUET)", [str(fe_path)])
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
        output_manifest=[
            {
                "pipeline_step_id": "de_1",
                "output_id": "result",
                "location_uri": f"file://{de_path.as_posix()}",
                "row_count": 1,
                "schema": [{"name": "marker", "type": "INTEGER"}],
            },
            {
                "pipeline_step_id": "fe_1",
                "output_id": "result",
                "location_uri": f"file://{fe_path.as_posix()}",
                "row_count": 1,
                "schema": [{"name": "marker", "type": "INTEGER"}],
            },
        ],
    )

    page = PipelineRunOutputReader(repository_root).preview(
        run,
        output_id="result",
        pipeline_step_id="fe_1",
        limit=10,
        offset=0,
    )

    assert page["pipeline_step_id"] == "fe_1"
    assert page["records"] == [{"marker": 2}]


def test_materialized_pipeline_outputs_are_versions_of_one_logical_dataset(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    datasets = InMemoryDatasetRepository()
    business_cases = InMemoryBusinessCaseRepository()
    materializer = PipelineOutputMaterializer(
        datasets=datasets,
        business_cases=business_cases,
        repository_root=repository_root,
    )
    workflow = WorkflowDefinition.model_validate({
        "contract_version": "2.0",
        "steps": [{
            "step_id": "de_1",
            "name": "Data Engineering",
            "type": "data_engineering",
            "output_port_id": "dataset",
            "config": {"definition": {}},
        }],
        "outputs": [{
            "output_id": "result",
            "source": {"step_id": "de_1", "port_id": "dataset"},
        }],
    })
    version = PipelineVersion(
        id="pipeline-version-1",
        owner_id="owner-1",
        pipeline_id="pipeline-1",
        business_case_id="bc-1",
        version_number=1,
        status=PipelineVersionStatus.PUBLISHED,
        definition=workflow.model_dump(mode="json"),
        definition_hash="definition-hash",
        created_by="owner-1",
    )

    outputs = []
    for run_number in (1, 2):
        source = (
            repository_root
            / "users"
            / "owner-1"
            / "pipeline-runs"
            / f"run-{run_number}"
            / "result.parquet"
        )
        source.parent.mkdir(parents=True)
        source.write_bytes(f"version-{run_number}".encode())
        run = PipelineRun(
            id=f"run-{run_number}",
            owner_id="owner-1",
            pipeline_id="pipeline-1",
            pipeline_version_id=version.id,
            business_case_id="bc-1",
            status=PipelineRunStatus.RUNNING,
            trigger_type=PipelineRunTrigger.MANUAL,
            created_by="owner-1",
        )
        manifest, artifact_ids = materializer.materialize(
            run=run,
            version=version,
            workflow=workflow,
            output_manifest=[{
                "output_id": "result",
                "materialization": "dataset",
                "dataset_name": "Prepared Iris",
                "business_case_role": "training",
                "location_uri": f"file://{source.as_posix()}",
                "row_count": run_number,
                "schema": [{"name": "id", "type": "BIGINT"}],
            }],
            step_id="de_1",
            input_dataset_ids=[],
            output_stage="final",
        )
        outputs.append(datasets.get(manifest[0]["dataset_id"]))
        assert artifact_ids == [manifest[0]["artifact_id"]]
        assert manifest[0]["logical_id"] == outputs[-1].logical_id
        assert manifest[0]["version_number"] == run_number

    assert outputs[0] is not None and outputs[1] is not None
    assert outputs[0].logical_id == outputs[1].logical_id
    assert [outputs[0].version_number, outputs[1].version_number] == [1, 2]
    assert len(business_cases.list_data_attachments("bc-1")) == 1
    assert business_cases.list_data_attachments("bc-1")[0].data_asset_id == outputs[1].id


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


def test_data_contract_rejects_invalid_rows_and_reports_full_scope_quality(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    owner_id = "owner-1"
    path = repository_root / "users" / owner_id / "quality.csv"
    path.parent.mkdir(parents=True)
    path.write_text(
        "id,amount,segment\n"
        "1,10,retail\n"
        "2,-5,retail\n"
        "2,20,unknown\n"
        "4,,business\n",
        encoding="utf-8",
    )
    repository = InMemoryDatasetRepository()
    repository.add(_asset("quality", owner_id, path, 4))
    definition = PipelineDefinition.model_validate(
        {
            "contract_version": "1.0",
            "inputs": [{"input_id": "source", "dataset_id": "quality", "output_port_id": "out"}],
            "steps": [],
            "outputs": [{
                "output_id": "result",
                "input": {"node_id": "source", "port_id": "out"},
                "materialization": "temporary",
                "data_contract": {
                    "schema_drift_policy": "fail",
                    "allow_unexpected_columns": True,
                    "columns": [
                        {"name": "id", "type": "BIGINT", "unique": True, "policy": "warn"},
                        {
                            "name": "amount",
                            "type": "BIGINT",
                            "nullable": False,
                            "minimum": 0,
                            "policy": "reject",
                        },
                        {
                            "name": "segment",
                            "type": "VARCHAR",
                            "allowed_values": ["retail", "business"],
                            "policy": "reject",
                        },
                    ],
                },
            }],
            "parameters": {},
        }
    )
    engine = DuckDbPipelineExecutionEngine(
        input_adapter=CsvDatasetInputAdapter(repository=repository, repository_root=repository_root),
        repository_root=repository_root,
    )

    result = engine.execute(definition, "quality-run", owner_id, is_dry_run=True)

    assert result.output_row_count == 1
    assert result.rejected_row_count == 3
    assert len(result.output_manifest) == 2
    assert result.output_manifest[0]["quality"]["checked_row_count"] == 4
    assert result.output_manifest[0]["quality"]["status"] == "issues_detected"
    assert result.output_manifest[1]["quality_output_kind"] == "rejected_records"
    rejected_path = Path(result.output_manifest[1]["location_uri"].removeprefix("file://"))
    rejected = duckdb.connect().execute(
        "SELECT id, _quality_rejection_reason FROM read_parquet(?) ORDER BY id",
        [str(rejected_path)],
    ).fetchall()
    assert rejected == [
        (2, "amount.minimum"),
        (2, "segment.allowed_values"),
        (4, "amount.nullable"),
    ]


def test_pipeline_step_handler_registry_dispatches_by_step_type() -> None:
    expected = HandledStepResult(
        input_row_count=3,
        processed_row_count=3,
        output_row_count=2,
        warnings=[],
        output_manifest=[],
        input_dataset_ids=["dataset-1"],
        relation_output_ids={},
    )

    class TrainingHandler:
        step_type = "training"

        def execute(self, step, context):
            assert step.type == "training"
            assert context.run_id == "run-1"
            return expected

    registry = PipelineStepHandlerRegistry([TrainingHandler()])
    step = SimpleNamespace(type="training")
    context = StepExecutionContext(
        run_id="run-1",
        owner_id="owner-1",
        is_dry_run=False,
        upstream_relations={},
    )

    assert registry.execute(step, context) is expected


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


@pytest.mark.parametrize(
    ("mode_config", "expected_type"),
    [
        ({"mode": "record_hash", "output_column": "row_id"}, "VARCHAR"),
        (
            {
                "mode": "columns_hash",
                "output_column": "row_id",
                "columns": ["customer", "event_time"],
            },
            "VARCHAR",
        ),
        (
            {
                "mode": "sequence",
                "output_column": "row_id",
                "order_by": [
                    {"column": "event_time", "direction": "asc"},
                    {"column": "customer", "direction": "asc"},
                ],
                "start": 100,
            },
            "BIGINT",
        ),
    ],
)
def test_add_identifier_supports_all_modes_deterministically(
    tmp_path: Path,
    mode_config: dict,
    expected_type: str,
) -> None:
    repository_root = tmp_path / "repository"
    owner_id = "owner-1"
    path = repository_root / "users" / owner_id / "events.csv"
    path.parent.mkdir(parents=True)
    path.write_text(
        "customer,event_time,value\n"
        "b,2025-01-02,10\n"
        "a,2025-01-01,20\n"
        "a,2025-01-03,\n",
        encoding="utf-8",
    )
    repository = InMemoryDatasetRepository()
    repository.add(_asset("events", owner_id, path, 3))
    definition = PipelineDefinition.model_validate({
        "contract_version": "1.0",
        "inputs": [{"input_id": "events", "dataset_id": "events", "output_port_id": "out"}],
        "steps": [{
            "step_id": "identifier",
            "type": "add_identifier",
            "inputs": [{"port_id": "input", "source": {"node_id": "events", "port_id": "out"}}],
            "output_port_id": "out",
            "config": mode_config,
        }],
        "outputs": [{
            "output_id": "result",
            "input": {"node_id": "identifier", "port_id": "out"},
            "materialization": "temporary",
        }],
        "parameters": {},
    })
    engine = DuckDbPipelineExecutionEngine(
        input_adapter=CsvDatasetInputAdapter(
            repository=repository,
            repository_root=repository_root,
        ),
        repository_root=repository_root,
    )

    first = engine.execute(definition, f"{mode_config['mode']}-1", owner_id, is_dry_run=True)
    second = engine.execute(definition, f"{mode_config['mode']}-2", owner_id, is_dry_run=True)
    first_path = Path(first.output_manifest[0]["location_uri"].removeprefix("file://"))
    second_path = Path(second.output_manifest[0]["location_uri"].removeprefix("file://"))
    connection = duckdb.connect()
    first_rows = connection.execute(
        "SELECT customer, event_time, row_id FROM read_parquet(?) ORDER BY event_time, customer",
        [str(first_path)],
    ).fetchall()
    second_rows = connection.execute(
        "SELECT customer, event_time, row_id FROM read_parquet(?) ORDER BY event_time, customer",
        [str(second_path)],
    ).fetchall()
    row_id_type = connection.execute(
        "DESCRIBE SELECT row_id FROM read_parquet(?)",
        [str(first_path)],
    ).fetchone()[1]
    connection.close()

    assert first_rows == second_rows
    assert row_id_type == expected_type
    assert len({row[2] for row in first_rows}) == 3
    if mode_config["mode"] == "sequence":
        assert [row[2] for row in first_rows] == [100, 101, 102]
    else:
        assert all(len(row[2]) == 64 for row in first_rows)


def test_add_identifier_validates_mode_specific_configuration() -> None:
    base = {
        "contract_version": "1.0",
        "inputs": [{"input_id": "source", "dataset_id": "dataset", "output_port_id": "out"}],
        "outputs": [{
            "output_id": "result",
            "input": {"node_id": "identifier", "port_id": "out"},
            "materialization": "temporary",
        }],
        "parameters": {},
    }

    for config, message in [
        ({"mode": "columns_hash", "output_column": "row_id", "columns": []}, "cannot be empty"),
        ({"mode": "sequence", "output_column": "row_id", "order_by": []}, "list of objects"),
        (
            {
                "mode": "sequence",
                "output_column": "row_id",
                "order_by": [{"column": "event_time", "direction": "sideways"}],
            },
            "direction",
        ),
    ]:
        definition = {
            **base,
            "steps": [{
                "step_id": "identifier",
                "type": "add_identifier",
                "inputs": [{"port_id": "input", "source": {"node_id": "source", "port_id": "out"}}],
                "output_port_id": "out",
                "config": config,
            }],
        }
        with pytest.raises(ValidationError, match=message):
            PipelineDefinition.model_validate(definition)


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
