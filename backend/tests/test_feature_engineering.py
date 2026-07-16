import json
import time
from pathlib import Path
from uuid import uuid4

import duckdb
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.modules.datasets.domain import DataAsset, DataAssetStatus, SourceType
from app.modules.datasets.repository import InMemoryDatasetRepository
from app.modules.business_cases.domain import Artifact, ArtifactOrigin, ArtifactType
from app.modules.business_cases.repository import InMemoryBusinessCaseRepository
from app.modules.pipelines.execution import CsvDatasetInputAdapter
from app.modules.pipelines.feature_engineering import (
    DuckDbFeatureEngineeringEngine,
    FeatureEngineeringDefinition,
)
from app.modules.pipelines.workflow import validate_workflow_definition
from app.main import create_app


def _asset(asset_id: str, owner_id: str, path: Path, rows: int) -> DataAsset:
    return DataAsset(
        id=asset_id,
        owner_id=owner_id,
        name=asset_id,
        source_type=SourceType.FILE,
        format="csv",
        location_uri=f"file://{path.as_posix()}",
        row_count=rows,
        has_header=True,
        status=DataAssetStatus.READY,
    )


def test_stratified_draft_can_be_saved_before_a_stable_row_id_is_configured() -> None:
    definition = FeatureEngineeringDefinition.model_validate({
        "inputs": [{"input_id": "training", "role": "training"}],
        "target_column": "species",
        "evaluation": {"split_strategy": "stratified", "stratify_column": "species"},
        "outputs": [
            {"output_id": "train", "input_id": "training", "dataset_name": "Train", "business_case_role": "training"},
            {"output_id": "validation", "input_id": "validation", "dataset_name": "Validation", "business_case_role": "validation"},
            {"output_id": "test", "input_id": "test", "dataset_name": "Test", "business_case_role": "test"},
        ],
    })

    with pytest.raises(ValueError, match="row_id_column"):
        definition.validate_executable()


def _definition(handle_unknown: str = "other") -> FeatureEngineeringDefinition:
    return FeatureEngineeringDefinition.model_validate({
        "contract_version": "1.0",
        "mode": "fit_transform",
        "inputs": [
            {"input_id": "training", "role": "training", "dataset_id": "train"},
            {"input_id": "validation", "role": "validation", "dataset_id": "validation"},
        ],
        "feature_columns": ["age", "city"],
        "target_column": "target",
        "row_id_column": "id",
        "transformations": [
            {
                "transform_id": "impute_age",
                "type": "impute",
                "columns": ["age"],
                "config": {"method": "mean", "add_indicator": True},
            },
            {
                "transform_id": "scale_age",
                "type": "scale_numeric",
                "columns": ["age"],
                "config": {"method": "standard", "output_suffix": "__scaled"},
            },
            {
                "transform_id": "encode_city",
                "type": "encode_categorical",
                "columns": ["city"],
                "config": {
                    "method": "one_hot",
                    "min_frequency": 1,
                    "max_categories": 10,
                    "handle_unknown": handle_unknown,
                    "drop_original": True,
                },
            },
        ],
        "outputs": [
            {
                "output_id": "training_features",
                "input_id": "training",
                "dataset_name": "Training features",
                "business_case_role": "training",
            },
            {
                "output_id": "validation_features",
                "input_id": "validation",
                "dataset_name": "Validation features",
                "business_case_role": "validation",
            },
        ],
    })


def test_feature_engineering_fits_only_training_and_handles_unseen_categories(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    source = repository_root / "users" / "owner-1" / "source"
    source.mkdir(parents=True)
    train_path = source / "train.csv"
    validation_path = source / "validation.csv"
    train_path.write_text(
        "id,age,city,target\n1,10,A,0\n2,20,B,1\n3,,A,0\n",
        encoding="utf-8",
    )
    validation_path.write_text(
        "id,age,city,target\n4,100,C,1\n5,,A,0\n",
        encoding="utf-8",
    )
    repository = InMemoryDatasetRepository()
    repository.add(_asset("train", "owner-1", train_path, 3))
    repository.add(_asset("validation", "owner-1", validation_path, 2))
    engine = DuckDbFeatureEngineeringEngine(
        input_adapter=CsvDatasetInputAdapter(repository, repository_root),
        repository_root=repository_root,
    )

    result = engine.execute(
        definition=_definition(),
        run_id="run-1",
        owner_id="owner-1",
        is_dry_run=True,
    )

    assert result.input_row_count == 5
    assert result.processed_row_count == 5
    assert result.output_row_count == 5
    assert all(item["data_scope"] == "full" for item in result.output_manifest)
    state_item = next(item for item in result.output_manifest if item["output_id"] == "fitted_transform")
    state = json.loads(
        Path(state_item["location_uri"].removeprefix("file://")).read_text(encoding="utf-8")
    )
    assert state["transforms"]["impute_age"]["values"]["age"] == 15
    assert state["transforms"]["scale_age"]["columns"]["age"] == {
        "center": 15.0,
        "scale": pytest.approx(4.08248290463863),
    }
    validation_item = next(
        item for item in result.output_manifest if item["output_id"] == "validation_features"
    )
    validation_rows = duckdb.connect().execute(
        "SELECT id, age, age__was_missing, age__scaled, city__0, city__1, city__other "
        "FROM read_parquet(?) ORDER BY id",
        [validation_item["location_uri"].removeprefix("file://")],
    ).fetchall()
    assert validation_rows == [
        (4, 100.0, False, pytest.approx(20.820662813657012), 0, 0, 1),
        (5, 15.0, True, 0.0, 1, 0, 0),
    ]
    assert validation_item["schema_hash"]
    assert any(item["role"] == "target" for item in validation_item["feature_manifest"])
    assert any(item["role"] == "row_id" for item in validation_item["feature_manifest"])


def test_feature_engineering_unknown_error_reports_input_and_count(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    source = repository_root / "users" / "owner-1" / "source"
    source.mkdir(parents=True)
    train_path = source / "train.csv"
    validation_path = source / "validation.csv"
    train_path.write_text("id,age,city,target\n1,10,A,0\n2,20,B,1\n", encoding="utf-8")
    validation_path.write_text("id,age,city,target\n3,30,C,1\n", encoding="utf-8")
    repository = InMemoryDatasetRepository()
    repository.add(_asset("train", "owner-1", train_path, 2))
    repository.add(_asset("validation", "owner-1", validation_path, 1))
    engine = DuckDbFeatureEngineeringEngine(
        input_adapter=CsvDatasetInputAdapter(repository, repository_root),
        repository_root=repository_root,
    )

    with pytest.raises(ValueError, match="validation.*1 unknown values.*city"):
        engine.execute(
            definition=_definition(handle_unknown="error"),
            run_id="run-2",
            owner_id="owner-1",
            is_dry_run=True,
        )


def test_frequency_encoding_with_no_retained_categories_outputs_zero(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    source = repository_root / "users" / "owner-1" / "source"
    source.mkdir(parents=True)
    train_path = source / "train.csv"
    validation_path = source / "validation.csv"
    train_path.write_text(
        "id,age,city,target\n1,10,A,0\n2,20,B,1\n3,30,C,0\n",
        encoding="utf-8",
    )
    validation_path.write_text("id,age,city,target\n4,40,D,1\n", encoding="utf-8")
    repository = InMemoryDatasetRepository()
    repository.add(_asset("train", "owner-1", train_path, 3))
    repository.add(_asset("validation", "owner-1", validation_path, 1))
    payload = _definition().model_dump(mode="json")
    payload["transformations"] = [{
        "transform_id": "encode_city_frequency",
        "type": "encode_categorical",
        "columns": ["city"],
        "config": {
            "method": "frequency",
            "min_frequency": 2,
            "max_categories": 10,
            "handle_unknown": "other",
            "drop_original": True,
        },
    }]
    definition = FeatureEngineeringDefinition.model_validate(payload)
    engine = DuckDbFeatureEngineeringEngine(
        input_adapter=CsvDatasetInputAdapter(repository, repository_root),
        repository_root=repository_root,
    )

    result = engine.execute(
        definition=definition,
        run_id="run-frequency-without-categories",
        owner_id="owner-1",
        is_dry_run=True,
    )

    validation = next(item for item in result.output_manifest if item["output_id"] == "validation_features")
    values = duckdb.connect().execute(
        "SELECT city__frequency FROM read_parquet(?)",
        [validation["location_uri"].removeprefix("file://")],
    ).fetchall()
    assert values == [(0.0,)]


def test_transform_mode_reuses_pinned_state_without_refitting(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    source = repository_root / "users" / "owner-1" / "source"
    source.mkdir(parents=True)
    train_path = source / "train.csv"
    validation_path = source / "validation.csv"
    scoring_path = source / "scoring.csv"
    train_path.write_text("id,age,city,target\n1,10,A,0\n2,20,B,1\n", encoding="utf-8")
    validation_path.write_text("id,age,city,target\n3,30,A,1\n", encoding="utf-8")
    scoring_path.write_text("id,age,city\n4,100,C\n", encoding="utf-8")
    datasets = InMemoryDatasetRepository()
    datasets.add(_asset("train", "owner-1", train_path, 2))
    datasets.add(_asset("validation", "owner-1", validation_path, 1))
    datasets.add(_asset("scoring", "owner-1", scoring_path, 1))
    business_cases = InMemoryBusinessCaseRepository()
    engine = DuckDbFeatureEngineeringEngine(
        input_adapter=CsvDatasetInputAdapter(datasets, repository_root),
        business_cases=business_cases,
        repository_root=repository_root,
    )
    fitted_definition_payload = _definition().model_dump(mode="json")
    fitted_definition_payload["transformations"].append({
        "transform_id": "drop_constant_scaled_age",
        "type": "variance_filter",
        "columns": ["age__scaled"],
        "config": {"threshold": 0.0},
    })
    fitted_definition = FeatureEngineeringDefinition.model_validate(fitted_definition_payload)
    fitted = engine.execute(
        definition=fitted_definition,
        run_id="fit-run",
        owner_id="owner-1",
        is_dry_run=True,
    )
    state_item = next(item for item in fitted.output_manifest if item["output_id"] == "fitted_transform")
    business_cases.add_artifact(Artifact(
        id="state-1",
        owner_id="owner-1",
        type=ArtifactType.FEATURE_TRANSFORM,
        reference_id="state-ref",
        origin=ArtifactOrigin.PLATFORM_GENERATED,
        metadata={"location_uri": state_item["location_uri"]},
    ))
    payload = fitted_definition.model_dump(mode="json")
    # JSON.stringify in the browser serializes the fitted recipe's 0.0 as 0.
    # Both representations must pin the same semantic FE recipe.
    payload["transformations"][-1]["config"]["threshold"] = 0
    payload.update({
        "mode": "transform",
        "inputs": [{"input_id": "scoring", "role": "scoring_input", "dataset_id": "scoring"}],
        "outputs": [{
            "output_id": "scoring_features",
            "input_id": "scoring",
            "dataset_name": "Scoring features",
            "business_case_role": "scoring_input",
        }],
        "fitted_state_artifact_id": "state-1",
    })

    result = engine.execute(
        definition=FeatureEngineeringDefinition.model_validate(payload),
        run_id="score-run",
        owner_id="owner-1",
        is_dry_run=True,
    )

    output = result.output_manifest[0]
    row = duckdb.connect().execute(
        "SELECT age__scaled, city__other FROM read_parquet(?)",
        [output["location_uri"].removeprefix("file://")],
    ).fetchone()
    assert row == (17.0, 1)
    assert all(item["output_id"] != "fitted_transform" for item in result.output_manifest)


def test_feature_recipe_supports_derived_columns_math_sql_and_full_data_pca(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    source = repository_root / "users" / "owner-1" / "source"
    source.mkdir(parents=True)
    train_path = source / "train.csv"
    validation_path = source / "validation.csv"
    train_path.write_text(
        "id,x,y,target\n1,1,2,0\n2,2,4,1\n3,4,5,1\n4,8,9,0\n",
        encoding="utf-8",
    )
    validation_path.write_text(
        "id,x,y,target\n5,100,200,1\n",
        encoding="utf-8",
    )
    datasets = InMemoryDatasetRepository()
    datasets.add(_asset("train", "owner-1", train_path, 4))
    datasets.add(_asset("validation", "owner-1", validation_path, 1))
    engine = DuckDbFeatureEngineeringEngine(
        input_adapter=CsvDatasetInputAdapter(datasets, repository_root),
        repository_root=repository_root,
    )
    definition = FeatureEngineeringDefinition.model_validate({
        "contract_version": "1.0",
        "mode": "fit_transform",
        "inputs": [
            {"input_id": "training", "role": "training", "dataset_id": "train"},
            {"input_id": "validation", "role": "validation", "dataset_id": "validation"},
        ],
        "feature_columns": ["x__square__scaled", "custom_score", "pc_1", "pc_2"],
        "target_column": "target",
        "row_id_column": "id",
        "transformations": [
            {
                "transform_id": "square_x",
                "type": "math_transform",
                "columns": ["x"],
                "config": {"operation": "square", "output_suffix": "__square"},
            },
            {
                "transform_id": "scale_square",
                "type": "scale_numeric",
                "columns": ["x__square"],
                "config": {"method": "standard", "output_suffix": "__scaled"},
            },
            {
                "transform_id": "custom_score",
                "type": "sql_expression",
                "columns": [],
                "config": {
                    "expression": '"x__square__scaled" + CAST("y" AS DOUBLE)',
                    "output_column": "custom_score",
                },
            },
            {
                "transform_id": "pca_projection",
                "type": "pca",
                "columns": ["x__square__scaled", "y"],
                "config": {
                    "n_components": 2,
                    "output_prefix": "pc_",
                    "whiten": False,
                    "drop_original": False,
                },
            },
        ],
        "outputs": [
            {
                "output_id": "training_features",
                "input_id": "training",
                "dataset_name": "Training features",
                "business_case_role": "training",
            },
            {
                "output_id": "validation_features",
                "input_id": "validation",
                "dataset_name": "Validation features",
                "business_case_role": "validation",
            },
        ],
    })

    result = engine.execute(
        definition=definition,
        run_id="advanced-fe",
        owner_id="owner-1",
        is_dry_run=True,
    )

    state_item = next(item for item in result.output_manifest if item["output_id"] == "fitted_transform")
    state = json.loads(
        Path(state_item["location_uri"].removeprefix("file://")).read_text(encoding="utf-8")
    )
    assert state["transforms"]["scale_square"]["columns"]["x__square"]["center"] == 21.25
    assert state["transforms"]["pca_projection"]["means"][0] == pytest.approx(0.0)
    assert state["transforms"]["pca_projection"]["means"][1] == pytest.approx(5.0)
    assert len(state["transforms"]["pca_projection"]["components"]) == 2
    validation = next(
        item for item in result.output_manifest if item["output_id"] == "validation_features"
    )
    row = duckdb.connect().execute(
        'SELECT "x__square", "x__square__scaled", custom_score, pc_1, pc_2 '
        "FROM read_parquet(?)",
        [validation["location_uri"].removeprefix("file://")],
    ).fetchone()
    assert row[0] == 10_000
    assert row[2] == pytest.approx(row[1] + 200)
    assert all(value is not None for value in row[3:])
    roles = {item["name"]: item["role"] for item in validation["feature_manifest"]}
    assert all(roles[name] == "feature" for name in definition.feature_columns)


def test_feature_sql_expression_rejects_queries_and_external_reads() -> None:
    for expression in [
        "(SELECT max(x) FROM input)",
        "read_csv_auto('/tmp/private.csv')",
    ]:
        with pytest.raises(ValidationError, match="Invalid FE SQL expression"):
            FeatureEngineeringDefinition.model_validate({
                "contract_version": "1.0",
                "mode": "fit_transform",
                "inputs": [{"input_id": "training", "role": "training", "dataset_id": "train"}],
                "feature_columns": ["result"],
                "transformations": [{
                    "transform_id": "unsafe",
                    "type": "sql_expression",
                    "columns": [],
                    "config": {"expression": expression, "output_column": "result"},
                }],
                "outputs": [{
                    "output_id": "training_features",
                    "input_id": "training",
                    "dataset_name": "Training features",
                    "business_case_role": "training",
                }],
            })


def test_numeric_generation_and_variance_selection_fit_only_training_scope(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    source = repository_root / "users" / "owner-1" / "source"
    source.mkdir(parents=True)
    train_path = source / "numeric-train.csv"
    validation_path = source / "numeric-validation.csv"
    train_path.write_text(
        "id,signal,constant,target\n1,0,5,0\n2,1,5,0\n3,2,5,1\n4,100,5,1\n",
        encoding="utf-8",
    )
    validation_path.write_text(
        "id,signal,constant,target\n5,1000,5,1\n",
        encoding="utf-8",
    )
    repository = InMemoryDatasetRepository()
    repository.add(_asset("numeric-train", "owner-1", train_path, 4))
    repository.add(_asset("numeric-validation", "owner-1", validation_path, 1))
    engine = DuckDbFeatureEngineeringEngine(
        input_adapter=CsvDatasetInputAdapter(repository, repository_root),
        repository_root=repository_root,
    )
    definition = FeatureEngineeringDefinition.model_validate({
        "contract_version": "1.0",
        "mode": "fit_transform",
        "inputs": [
            {"input_id": "training", "role": "training", "dataset_id": "numeric-train"},
            {"input_id": "validation", "role": "validation", "dataset_id": "numeric-validation"},
        ],
        "feature_columns": ["signal", "constant"],
        "target_column": "target",
        "row_id_column": "id",
        "transformations": [
            {
                "transform_id": "winsor",
                "type": "winsorize_numeric",
                "columns": ["signal", "constant"],
                "config": {"lower_quantile": 0.25, "upper_quantile": 0.75},
            },
            {
                "transform_id": "signed_log",
                "type": "math_transform",
                "columns": ["signal"],
                "config": {"operation": "signed_log1p", "output_suffix": "__signed_log1p"},
            },
            {
                "transform_id": "selector",
                "type": "variance_filter",
                "columns": ["signal", "constant", "signal__signed_log1p"],
                "config": {"threshold": 0.0},
            },
        ],
        "outputs": [
            {"output_id": "training_features", "input_id": "training", "dataset_name": "Train", "business_case_role": "training"},
            {"output_id": "validation_features", "input_id": "validation", "dataset_name": "Validation", "business_case_role": "validation"},
        ],
    })

    result = engine.execute(
        definition=definition,
        run_id="numeric-generation",
        owner_id="owner-1",
        is_dry_run=True,
    )
    state_item = next(item for item in result.output_manifest if item["output_id"] == "fitted_transform")
    state = json.loads(Path(state_item["location_uri"].removeprefix("file://")).read_text(encoding="utf-8"))
    assert state["transforms"]["winsor"]["columns"]["signal"] == {
        "lower": 0.75,
        "upper": 26.5,
    }
    assert state["transforms"]["selector"]["dropped_columns"] == ["constant"]
    validation = next(item for item in result.output_manifest if item["output_id"] == "validation_features")
    row = duckdb.connect().execute(
        'SELECT signal, "signal__signed_log1p" FROM read_parquet(?)',
        [validation["location_uri"].removeprefix("file://")],
    ).fetchone()
    assert row == (26.5, pytest.approx(3.3141860046725258))
    assert "constant" not in {item["name"] for item in validation["schema"]}


def test_numeric_interaction_zero_policy_produces_finite_features(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    source = repository_root / "users" / "owner-1" / "source"
    source.mkdir(parents=True)
    train_path = source / "interaction-train.csv"
    validation_path = source / "interaction-validation.csv"
    train_path.write_text(
        "id,left_value,right_value,target\n1,10,2,0\n2,5,0,1\n3,9,3,0\n",
        encoding="utf-8",
    )
    validation_path.write_text(
        "id,left_value,right_value,target\n4,7,0,1\n",
        encoding="utf-8",
    )
    datasets = InMemoryDatasetRepository()
    datasets.add(_asset("interaction-train", "owner-1", train_path, 3))
    datasets.add(_asset("interaction-validation", "owner-1", validation_path, 1))
    definition = FeatureEngineeringDefinition.model_validate({
        "contract_version": "1.0",
        "mode": "fit_transform",
        "inputs": [
            {"input_id": "training", "role": "training", "dataset_id": "interaction-train"},
            {"input_id": "validation", "role": "validation", "dataset_id": "interaction-validation"},
        ],
        "feature_columns": ["safe_ratio"],
        "target_column": "target",
        "row_id_column": "id",
        "transformations": [{
            "transform_id": "safe_ratio",
            "type": "numeric_interaction",
            "config": {
                "left": "left_value",
                "right": "right_value",
                "operator": "divide",
                "output_column": "safe_ratio",
                "zero_division": "zero",
            },
        }],
        "outputs": [
            {"output_id": "training_features", "input_id": "training", "dataset_name": "Train"},
            {"output_id": "validation_features", "input_id": "validation", "dataset_name": "Validation", "business_case_role": "validation"},
        ],
    })
    result = DuckDbFeatureEngineeringEngine(
        input_adapter=CsvDatasetInputAdapter(datasets, repository_root),
        repository_root=repository_root,
    ).execute(
        definition=definition,
        run_id="safe-interaction",
        owner_id="owner-1",
        is_dry_run=True,
    )
    training = next(item for item in result.output_manifest if item["output_id"] == "training_features")
    validation = next(item for item in result.output_manifest if item["output_id"] == "validation_features")
    assert duckdb.connect().execute(
        "SELECT safe_ratio FROM read_parquet(?) ORDER BY id",
        [training["location_uri"].removeprefix("file://")],
    ).fetchall() == [(5.0,), (0.0,), (3.0,)]
    assert duckdb.connect().execute(
        "SELECT safe_ratio FROM read_parquet(?)",
        [validation["location_uri"].removeprefix("file://")],
    ).fetchone() == (0.0,)


def test_workflow_accepts_de_followed_by_feature_engineering() -> None:
    workflow = {
        "contract_version": "2.0",
        "steps": [
            {
                "step_id": "de_1",
                "name": "Data Engineering",
                "type": "data_engineering",
                "inputs": [],
                "output_port_id": "dataset",
                "config": {
                    "definition": {
                        "contract_version": "1.0",
                        "inputs": [{"input_id": "source", "dataset_id": "dataset-1"}],
                        "steps": [],
                        "outputs": [{
                            "output_id": "prepared",
                            "input": {"node_id": "source", "port_id": "out"},
                            "materialization": "dataset",
                            "dataset_name": "Prepared",
                        }],
                    }
                },
            },
            {
                "step_id": "fe_1",
                "name": "Feature Engineering",
                "type": "feature_engineering",
                "inputs": [{
                    "port_id": "training",
                    "source": {"step_id": "de_1", "port_id": "dataset"},
                }],
                "output_port_id": "dataset",
                "additional_output_port_ids": ["fitted_transform"],
                "config": {
                    "definition": {
                        "contract_version": "1.0",
                        "mode": "fit_transform",
                        "inputs": [{"input_id": "training", "role": "training"}],
                        "row_id_column": "id",
                        "transformations": [],
                        "outputs": [
                            {
                                "output_id": "training_features",
                                "input_id": "training",
                                "dataset_name": "Training features",
                                "business_case_role": "training",
                            },
                            {
                                "output_id": "validation_features",
                                "input_id": "validation",
                                "dataset_name": "Validation features",
                                "business_case_role": "validation",
                            },
                            {
                                "output_id": "test_features",
                                "input_id": "test",
                                "dataset_name": "Test features",
                                "business_case_role": "test",
                            },
                        ],
                        "evaluation": {
                            "split_strategy": "random",
                            "validation_size": 0.15,
                            "test_size": 0.15,
                            "seed": 42,
                        },
                    }
                },
            },
        ],
        "outputs": [{"output_id": "result", "source": {"step_id": "fe_1", "port_id": "dataset"}}],
    }

    validated = validate_workflow_definition(workflow, executable=True)

    assert [item["type"] for item in validated["steps"]] == [
        "data_engineering",
        "feature_engineering",
    ]
    feature_step = validated["steps"][1]
    assert feature_step["output_port_id"] == "training"
    assert feature_step["additional_output_port_ids"] == [
        "validation",
        "test",
        "fitted_transform",
    ]
    assert {
        (output["output_id"], output["source"]["port_id"])
        for output in validated["outputs"]
    } == {
        ("training_features", "training"),
        ("validation_features", "validation"),
        ("test_features", "test"),
    }


def test_feature_contract_rejects_target_as_feature() -> None:
    payload = _definition().model_dump(mode="json")
    payload["feature_columns"].append("target")

    with pytest.raises(ValidationError, match="cannot be selected as features"):
        FeatureEngineeringDefinition.model_validate(payload)


def test_stratified_holdout_and_cv_are_deterministic_and_disjoint(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    source = repository_root / "users" / "owner-1" / "source"
    source.mkdir(parents=True)
    path = source / "all.csv"
    path.write_text(
        "id,value,target\n"
        + "\n".join(f"{index},{index * 2},{index % 2}" for index in range(100))
        + "\n",
        encoding="utf-8",
    )
    datasets = InMemoryDatasetRepository()
    datasets.add(_asset("all", "owner-1", path, 100))
    definition = FeatureEngineeringDefinition.model_validate({
        "mode": "fit_transform",
        "inputs": [{"input_id": "training", "role": "training", "dataset_id": "all"}],
        "feature_columns": ["value"],
        "target_column": "target",
        "row_id_column": "id",
        "transformations": [],
        "outputs": [
            {"output_id": "training_features", "input_id": "training", "dataset_name": "Train", "business_case_role": "training"},
            {"output_id": "validation_features", "input_id": "validation", "dataset_name": "Validation", "business_case_role": "validation"},
            {"output_id": "test_features", "input_id": "test", "dataset_name": "Test", "business_case_role": "test"},
        ],
        "evaluation": {
            "split_strategy": "stratified",
            "validation_size": 0.1,
            "test_size": 0.2,
            "seed": 17,
            "stratify_column": "target",
            "cross_validation": {
                "enabled": True,
                "strategy": "stratified",
                "folds": 5,
                "seed": 23,
            },
        },
    })
    engine = DuckDbFeatureEngineeringEngine(
        input_adapter=CsvDatasetInputAdapter(datasets, repository_root),
        repository_root=repository_root,
    )

    first = engine.execute(
        definition=definition, run_id="split-1", owner_id="owner-1", is_dry_run=True,
    )
    second = engine.execute(
        definition=definition, run_id="split-2", owner_id="owner-1", is_dry_run=True,
    )

    def rows(result, output_id: str):
        item = next(entry for entry in result.output_manifest if entry["output_id"] == output_id)
        return duckdb.connect().execute(
            "SELECT id, target, __mlapp_cv_fold FROM read_parquet(?) ORDER BY id"
            if output_id == "training_features"
            else "SELECT id, target, NULL FROM read_parquet(?) ORDER BY id",
            [item["location_uri"].removeprefix("file://")],
        ).fetchall()

    train = rows(first, "training_features")
    validation = rows(first, "validation_features")
    test = rows(first, "test_features")
    assert (len(train), len(validation), len(test)) == (70, 10, 20)
    assert {row[0] for row in train}.isdisjoint({row[0] for row in validation})
    assert {row[0] for row in train}.isdisjoint({row[0] for row in test})
    assert {row[0] for row in validation}.isdisjoint({row[0] for row in test})
    assert sum(row[1] for row in train) == 35
    assert sum(row[1] for row in validation) == 5
    assert sum(row[1] for row in test) == 10
    assert {row[2] for row in train} == {0, 1, 2, 3, 4}
    assert train == rows(second, "training_features")
    manifest_output = next(
        item for item in first.output_manifest if item["output_id"] == "training_features"
    )
    assert "evaluation" not in manifest_output
    manifest = manifest_output["split_evaluation"]
    assert manifest["split_row_counts"] == {"training": 70, "validation": 10, "test": 20}
    assert sum(item["row_count"] for item in manifest["cross_validation"]["fold_row_counts"]) == 70


@pytest.mark.parametrize(("strategy", "column"), [("group", "group_id"), ("time", "event_time")])
def test_group_and_time_splits_respect_boundaries(
    tmp_path: Path,
    strategy: str,
    column: str,
) -> None:
    repository_root = tmp_path / strategy
    source = repository_root / "users" / "owner-1" / "source"
    source.mkdir(parents=True)
    path = source / "all.csv"
    path.write_text(
        "id,value,target,group_id,event_time\n"
        + "\n".join(
            f"{index},{index},0,g{index // 2},2026-01-01T00:{index:02d}:00"
            for index in range(50)
        )
        + "\n",
        encoding="utf-8",
    )
    datasets = InMemoryDatasetRepository()
    datasets.add(_asset("all", "owner-1", path, 50))
    evaluation = {
        "split_strategy": strategy,
        "validation_size": 0.2,
        "test_size": 0.2,
        "seed": 11,
        "group_column": "group_id",
        "time_column": "event_time",
        "cross_validation": {
            "enabled": True,
            "strategy": strategy,
            "folds": 3,
            "seed": 12,
        },
    }
    definition = FeatureEngineeringDefinition.model_validate({
        "inputs": [{"input_id": "training", "role": "training", "dataset_id": "all"}],
        "feature_columns": ["value"],
        "target_column": "target",
        "row_id_column": "id",
        "group_column": "group_id",
        "event_time_column": "event_time",
        "outputs": [
            {"output_id": "training_features", "input_id": "training", "dataset_name": "Train"},
            {"output_id": "validation_features", "input_id": "validation", "dataset_name": "Validation", "business_case_role": "validation"},
            {"output_id": "test_features", "input_id": "test", "dataset_name": "Test", "business_case_role": "test"},
        ],
        "evaluation": evaluation,
    })
    result = DuckDbFeatureEngineeringEngine(
        input_adapter=CsvDatasetInputAdapter(datasets, repository_root),
        repository_root=repository_root,
    ).execute(
        definition=definition, run_id=f"{strategy}-run", owner_id="owner-1", is_dry_run=True,
    )

    partitions = {}
    for output_id in ("training_features", "validation_features", "test_features"):
        item = next(entry for entry in result.output_manifest if entry["output_id"] == output_id)
        partitions[output_id] = duckdb.connect().execute(
            f"SELECT id, group_id, event_time FROM read_parquet(?) ORDER BY id",
            [item["location_uri"].removeprefix("file://")],
        ).fetchall()
    if strategy == "group":
        group_sets = [{row[1] for row in rows} for rows in partitions.values()]
        assert group_sets[0].isdisjoint(group_sets[1])
        assert group_sets[0].isdisjoint(group_sets[2])
        assert group_sets[1].isdisjoint(group_sets[2])
    else:
        train_max = max(row[2] for row in partitions["training_features"])
        validation_min = min(row[2] for row in partitions["validation_features"])
        validation_max = max(row[2] for row in partitions["validation_features"])
        test_min = min(row[2] for row in partitions["test_features"])
        assert train_max < validation_min <= validation_max < test_min


def test_de_to_fe_pipeline_run_creates_step_runs_dataset_and_fitted_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.worker.tasks import execute_pipeline_run

    monkeypatch.setattr(
        execute_pipeline_run,
        "delay",
        lambda run_id: None,
    )
    client = TestClient(create_app())
    email = f"alice-{uuid4()}@example.com"
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "display_name": "Alice"},
    )
    assert registered.status_code == 201
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    business_case = client.post(
        "/api/v1/business-cases",
        headers=headers,
        json={
            "name": "Churn features",
            "problem_type": "binary_classification",
            "target_column": "target",
        },
    ).json()
    source_rows = [
        f"{index},{18 + index % 50},{'A' if index % 2 == 0 else 'B'},{index % 2}"
        for index in range(1, 101)
    ]
    upload = client.post(
        "/api/v1/datasets/upload",
        headers=headers,
        data={"name": "Churn training"},
        files={"file": (
            "training.csv",
            ("id,age,city,target\n" + "\n".join(source_rows) + "\n").encode(),
            "text/csv",
        )},
    )
    assert upload.status_code == 201
    dataset_id = upload.json()["id"]
    workflow = {
        "contract_version": "2.0",
        "steps": [
            {
                "step_id": "de_1",
                "name": "Data Engineering",
                "type": "data_engineering",
                "inputs": [],
                "output_port_id": "dataset",
                "config": {
                    "definition": {
                        "contract_version": "1.0",
                        "inputs": [{"input_id": "source", "dataset_id": dataset_id}],
                        "steps": [],
                        "outputs": [{
                            "output_id": "prepared",
                            "input": {"node_id": "source", "port_id": "out"},
                            "materialization": "dataset",
                            "dataset_name": "Prepared churn",
                            "business_case_role": "training",
                        }],
                    }
                },
            },
            {
                "step_id": "fe_1",
                "name": "Feature Engineering",
                "type": "feature_engineering",
                "inputs": [{
                    "port_id": "training",
                    "source": {"step_id": "de_1", "port_id": "dataset"},
                }],
                "output_port_id": "dataset",
                "additional_output_port_ids": ["fitted_transform"],
                "config": {
                    "definition": {
                        "contract_version": "1.0",
                        "mode": "fit_transform",
                        "inputs": [{"input_id": "training", "role": "training"}],
                        "feature_columns": ["age", "city"],
                        "target_column": "target",
                        "row_id_column": "id",
                        "evaluation": {
                            "split_strategy": "stratified",
                            "validation_size": 0.15,
                            "test_size": 0.15,
                            "seed": 42,
                            "stratify_column": "target",
                        },
                        "transformations": [
                            {
                                "transform_id": "impute_age",
                                "type": "impute",
                                "columns": ["age"],
                                "config": {"method": "mean", "add_indicator": True},
                            },
                            {
                                "transform_id": "encode_city",
                                "type": "encode_categorical",
                                "columns": ["city"],
                                "config": {
                                    "method": "one_hot",
                                    "max_categories": 10,
                                    "handle_unknown": "other",
                                    "drop_original": True,
                                },
                            },
                        ],
                        "outputs": [
                            {
                                "output_id": "training_features",
                                "input_id": "training",
                                "dataset_name": "Churn training features",
                                "business_case_role": "training",
                            },
                            {
                                "output_id": "validation_features",
                                "input_id": "validation",
                                "dataset_name": "Churn validation features",
                                "business_case_role": "validation",
                            },
                            {
                                "output_id": "test_features",
                                "input_id": "test",
                                "dataset_name": "Churn test features",
                                "business_case_role": "test",
                            },
                        ],
                    }
                },
            },
        ],
        "outputs": [{
            "output_id": "result",
            "source": {"step_id": "fe_1", "port_id": "dataset"},
        }],
    }
    created = client.post(
        "/api/v1/pipelines",
        headers=headers,
        json={
            "business_case_id": business_case["id"],
            "name": "Prepare churn features",
            "type": "feature_engineering",
            "definition": workflow,
        },
    )
    assert created.status_code == 201, created.text
    pipeline_id = created.json()["id"]
    published = client.post(
        f"/api/v1/pipelines/{pipeline_id}/versions/draft/publish",
        headers=headers,
    )
    assert published.status_code == 200, published.text
    queued = client.post(
        f"/api/v1/pipelines/{pipeline_id}/runs",
        headers=headers,
        json={"trigger_type": "manual", "is_dry_run": False},
    )
    assert queued.status_code == 201, queued.text
    run = queued.json()
    execute_pipeline_run.run(run["id"])
    deadline = time.monotonic() + 20
    while run["status"] in {"queued", "running"} and time.monotonic() < deadline:
        time.sleep(0.1)
        run = client.get(
            f"/api/v1/pipelines/{pipeline_id}/runs/{run['id']}",
            headers=headers,
        ).json()

    assert run["status"] == "succeeded", run["error_message"]
    assert run["input_row_count"] == 100
    assert run["output_row_count"] == 100
    dataset_items = [
        item for item in run["output_manifest"] if item.get("artifact_type") == "dataset"
    ]
    final_dataset_items = [
        item for item in dataset_items if item["output_stage"] == "final"
    ]
    intermediate_dataset_items = [
        item for item in dataset_items if item["output_stage"] == "intermediate"
    ]
    assert len(intermediate_dataset_items) == 1
    assert intermediate_dataset_items[0]["pipeline_step_id"] == "de_1"
    assert intermediate_dataset_items[0]["dataset_name"] == "Prepared churn"
    assert intermediate_dataset_items[0]["row_count"] == 100
    assert {item["business_case_role"] for item in final_dataset_items} == {
        "training",
        "validation",
        "test",
    }
    assert sum(item["row_count"] for item in final_dataset_items) == 100
    dataset_item = next(
        item for item in final_dataset_items if item["business_case_role"] == "training"
    )
    state_item = next(
        item for item in run["output_manifest"] if item.get("artifact_type") == "feature_transform"
    )
    assert dataset_item["materialization"] == "dataset"
    assert dataset_item["dataset_id"]
    assert dataset_item["schema_hash"]
    assert state_item["materialization"] == "artifact"
    assert state_item["artifact_id"] in run["output_artifact_ids"]
    step_runs = client.get(
        f"/api/v1/pipelines/{pipeline_id}/runs/{run['id']}/steps",
        headers=headers,
    )
    assert step_runs.status_code == 200
    assert [(item["pipeline_step_id"], item["status"]) for item in step_runs.json()] == [
        ("de_1", "succeeded"),
        ("fe_1", "succeeded"),
    ]
    persisted = client.get(
        f"/api/v1/datasets/{dataset_item['dataset_id']}/preview?limit=10",
        headers=headers,
    )
    assert persisted.status_code == 200
    assert persisted.json()["row_count"] == dataset_item["row_count"]
    assert {"city__0", "city__1", "city__other"}.issubset(
        {item["name"] for item in persisted.json()["columns"]}
    )
    attachments = client.get(
        f"/api/v1/business-cases/{business_case['id']}/data-attachments",
        headers=headers,
    )
    assert attachments.status_code == 200
    generated_dataset_ids = {item["dataset_id"] for item in final_dataset_items}
    assert {
        item["role"] for item in attachments.json()
        if item["data_asset_id"] in generated_dataset_ids
    } == {"training", "validation", "test"}


def test_supervised_selector_is_full_scope_redundancy_aware_and_persisted(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    source = repository_root / "users" / "owner-1" / "source"
    source.mkdir(parents=True)
    train_path = source / "selector.csv"
    train_path.write_text(
        "id,signal,signal_copy,noise,target\n"
        + "\n".join(
            f"{index},{index},{index},{(index * 7) % 5},{int(index >= 10)}"
            for index in range(20)
        )
        + "\n",
        encoding="utf-8",
    )
    repository = InMemoryDatasetRepository()
    repository.add(_asset("selector", "owner-1", train_path, 20))
    engine = DuckDbFeatureEngineeringEngine(
        input_adapter=CsvDatasetInputAdapter(repository, repository_root),
        repository_root=repository_root,
    )
    definition = FeatureEngineeringDefinition.model_validate({
        "mode": "fit_transform",
        "inputs": [{"input_id": "training", "role": "training", "dataset_id": "selector"}],
        "feature_columns": ["signal", "signal_copy", "noise"],
        "target_column": "target",
        "row_id_column": "id",
        "transformations": [{
            "transform_id": "supervised",
            "type": "supervised_feature_selector",
            "columns": [],
            "config": {
                "method": "mutual_information",
                "target_column": "target",
                "problem_type": "binary_classification",
                "max_features": 2,
                "correlation_threshold": 0.95,
                "random_seed": 42,
                "max_memory_mb": 128,
                "profile": "compact",
            },
        }],
        "outputs": [{
            "output_id": "training_features", "input_id": "training",
            "dataset_name": "Selected", "business_case_role": "training",
        }],
    })

    result = engine.execute(
        definition=definition, run_id="selector", owner_id="owner-1", is_dry_run=True,
    )
    state_item = next(item for item in result.output_manifest if item["output_id"] == "fitted_transform")
    state = json.loads(Path(state_item["location_uri"].removeprefix("file://")).read_text())
    selector = state["transforms"]["supervised"]
    assert selector["data_scope"] == "full"
    assert selector["fitted_row_count"] == 20
    assert len(selector["selected_columns"]) == 2
    assert {"signal", "signal_copy"} & set(selector["selected_columns"])
    assert selector["correlation_dropped"]


def test_target_encoding_is_cross_fitted_and_reuses_global_state_for_validation(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    source = repository_root / "users" / "owner-1" / "source"
    source.mkdir(parents=True)
    train_path = source / "target-train.csv"
    validation_path = source / "target-validation.csv"
    train_path.write_text(
        "id,city,target\n1,A,0\n2,A,1\n3,B,0\n4,B,1\n5,A,1\n6,B,0\n",
        encoding="utf-8",
    )
    validation_path.write_text("id,city,target\n7,A,1\n8,C,0\n", encoding="utf-8")
    repository = InMemoryDatasetRepository()
    repository.add(_asset("target-train", "owner-1", train_path, 6))
    repository.add(_asset("target-validation", "owner-1", validation_path, 2))
    engine = DuckDbFeatureEngineeringEngine(
        input_adapter=CsvDatasetInputAdapter(repository, repository_root),
        repository_root=repository_root,
    )
    definition = FeatureEngineeringDefinition.model_validate({
        "mode": "fit_transform",
        "inputs": [
            {"input_id": "training", "role": "training", "dataset_id": "target-train"},
            {"input_id": "validation", "role": "validation", "dataset_id": "target-validation"},
        ],
        "feature_columns": ["city"],
        "target_column": "target",
        "row_id_column": "id",
        "transformations": [{
            "transform_id": "target_encoding",
            "type": "encode_categorical",
            "columns": ["city"],
            "config": {
                "method": "target_mean", "min_frequency": 1, "max_categories": 10,
                "handle_unknown": "other", "drop_original": True,
                "target_column": "target", "row_id_column": "id",
                "problem_type": "binary_classification", "cross_fit_folds": 3,
                "smoothing": 2,
            },
        }],
        "outputs": [
            {"output_id": "training_features", "input_id": "training", "dataset_name": "Train", "business_case_role": "training"},
            {"output_id": "validation_features", "input_id": "validation", "dataset_name": "Validation", "business_case_role": "validation"},
        ],
    })

    result = engine.execute(
        definition=definition, run_id="target-encoding", owner_id="owner-1", is_dry_run=True,
    )
    training = next(item for item in result.output_manifest if item["output_id"] == "training_features")
    validation = next(item for item in result.output_manifest if item["output_id"] == "validation_features")
    training_values = duckdb.connect().execute(
        'SELECT "city__target_mean" FROM read_parquet(?) ORDER BY id',
        [training["location_uri"].removeprefix("file://")],
    ).fetchall()
    validation_values = duckdb.connect().execute(
        'SELECT "city__target_mean" FROM read_parquet(?) ORDER BY id',
        [validation["location_uri"].removeprefix("file://")],
    ).fetchall()
    assert len({round(float(row[0]), 6) for row in training_values}) > 1
    assert float(validation_values[0][0]) == pytest.approx(0.6)
    assert float(validation_values[1][0]) == pytest.approx(0.5)
