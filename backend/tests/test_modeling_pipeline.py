from pathlib import Path

import duckdb
import joblib
import numpy as np
import pytest

from app.modules.pipelines.modeling import (
    ScoringDefinition,
    SklearnScoringEngine,
    SklearnTrainingEngine,
    TrainingDefinition,
)
from app.modules.pipelines.runtime import SourceRelation
from app.modules.pipelines.workflow import validate_workflow_definition
from app.worker.tasks import _definition_with_resolved_inputs


def _relation(path: Path, rows: int) -> SourceRelation:
    escaped = str(path).replace("'", "''")
    return SourceRelation(sql=f"read_parquet('{escaped}')", row_count=rows)


def test_training_and_scoring_process_full_declared_inputs(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    source = repository / "users" / "owner-1" / "source"
    source.mkdir(parents=True)
    train_path = source / "train.parquet"
    test_path = source / "test.parquet"
    connection = duckdb.connect()
    connection.execute(
        "COPY (SELECT range AS row_id, range::DOUBLE AS x, "
        "CASE WHEN range >= 50 THEN 1 ELSE 0 END AS target FROM range(100)) "
        f"TO '{str(train_path).replace(chr(39), chr(39) * 2)}' (FORMAT PARQUET)"
    )
    connection.execute(
        "COPY (SELECT range + 100 AS row_id, (range + 40)::DOUBLE AS x, "
        "CASE WHEN range + 40 >= 50 THEN 1 ELSE 0 END AS target FROM range(20)) "
        f"TO '{str(test_path).replace(chr(39), chr(39) * 2)}' (FORMAT PARQUET)"
    )
    connection.close()
    training = SklearnTrainingEngine(repository)
    trained = training.execute(
        TrainingDefinition(
            problem_type="binary_classification",
            algorithm="sgd_classifier",
            target_column="target",
            feature_columns=["x"],
            model_name="Threshold classifier",
            epochs=10,
            batch_size=100,
        ),
        _relation(train_path, 100),
        _relation(test_path, 20),
        run_id="run-1",
        owner_id="owner-1",
        is_dry_run=True,
    )

    assert trained.input_row_count == 100
    assert trained.processed_row_count == 1000
    model = next(item for item in trained.output_manifest if item["output_id"] == "model")
    assert model["data_scope"] == "full"
    assert model["metrics"]["evaluated_row_count"] == 20
    assert model["model_hash"]

    scored = SklearnScoringEngine(repository).execute(
        ScoringDefinition(
            row_id_column="row_id",
            target_column="target",
            dataset_name="Test predictions",
            batch_size=100,
        ),
        _relation(test_path, 20),
        model,
        run_id="run-1",
        owner_id="owner-1",
        is_dry_run=True,
    )

    output = scored.output_manifest[0]
    assert scored.input_row_count == scored.output_row_count == 20
    assert output["artifact_type"] == "prediction_dataset"
    assert output["metrics"]["scored_row_count"] == 20
    assert output["score_contract"]["positive_class"] == 1
    assert output["score_contract"]["prediction_score_kind"] == "positive_class_probability"
    scored_rows = duckdb.connect().execute(
        "SELECT row_id, prediction_score, positive_class_probability "
        "FROM read_parquet(?) ORDER BY row_id",
        [output["location_uri"].removeprefix("file://")],
    ).fetchall()
    assert len(scored_rows) == 20
    assert len({row[0] for row in scored_rows}) == 20
    assert all(row[1] == pytest.approx(row[2]) for row in scored_rows)
    bundle = joblib.load(model["location_uri"].removeprefix("file://"))
    expected = bundle["estimator"].predict_proba(
        np.arange(40, 60, dtype=float).reshape(-1, 1)
    )[:, 1]
    assert np.asarray([row[2] for row in scored_rows]) == pytest.approx(expected)
    assert any(
        abs(probability - max(probability, 1 - probability)) > 1e-9
        for probability in expected
    )


def test_training_early_stopping_uses_explicit_validation_and_best_epoch(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    source = repository / "users" / "owner-1" / "source"
    source.mkdir(parents=True)
    train_path = source / "train.parquet"
    validation_path = source / "validation.parquet"
    connection = duckdb.connect()
    for path, offset in ((train_path, 0), (validation_path, 100)):
        escaped_path = str(path).replace("'", "''")
        connection.execute(
            "COPY (SELECT range + ? AS row_id, range::DOUBLE AS x, "
            "CASE WHEN range >= 25 THEN 1 ELSE 0 END AS target FROM range(50)) "
            f"TO '{escaped_path}' (FORMAT PARQUET)",
            [offset],
        )
    connection.close()

    result = SklearnTrainingEngine(repository).execute(
        TrainingDefinition(
            problem_type="binary_classification",
            algorithm="sgd_classifier",
            target_column="target",
            feature_columns=["x"],
            epochs=20,
            early_stopping=True,
            early_stopping_patience=2,
            early_stopping_min_delta=1.0,
            batch_size=100,
        ),
        _relation(train_path, 50),
        _relation(validation_path, 50),
        run_id="early-stop-run",
        owner_id="owner-1",
        is_dry_run=True,
    )

    model = next(item for item in result.output_manifest if item["output_id"] == "model")
    assert model["metrics"]["early_stopping_enabled"] is True
    assert model["metrics"]["stopped_early"] is True
    assert model["metrics"]["executed_epochs"] == 3
    assert model["metrics"]["best_epoch"] == 1
    assert len(model["metrics"]["validation_history"]) == 3
    assert result.processed_row_count == 150
    assert result.warnings


@pytest.mark.parametrize(
    ("problem_type", "algorithm"),
    [
        ("binary_classification", "passive_aggressive_classifier"),
        ("binary_classification", "perceptron_classifier"),
        ("regression", "sgd_regressor"),
        ("regression", "passive_aggressive_regressor"),
    ],
)
def test_supported_incremental_estimators_fit_full_input(
    tmp_path: Path,
    problem_type: str,
    algorithm: str,
) -> None:
    repository = tmp_path / "repository"
    source = repository / "users" / "owner-1" / "source"
    source.mkdir(parents=True)
    path = source / f"{algorithm}.parquet"
    target = "range::DOUBLE * 2.5 + 1" if problem_type == "regression" else "CASE WHEN range >= 20 THEN 1 ELSE 0 END"
    escaped_path = str(path).replace("'", "''")
    duckdb.connect().execute(
        f"COPY (SELECT range AS row_id, range::DOUBLE AS x, {target} AS target FROM range(40)) "
        f"TO '{escaped_path}' (FORMAT PARQUET)"
    ).close()

    result = SklearnTrainingEngine(repository).execute(
        TrainingDefinition(
            problem_type=problem_type,
            algorithm=algorithm,
            target_column="target",
            feature_columns=["x"],
            epochs=2,
            batch_size=100,
        ),
        _relation(path, 40),
        None,
        run_id=f"run-{algorithm}",
        owner_id="owner-1",
        is_dry_run=True,
    )

    model = next(item for item in result.output_manifest if item["output_id"] == "model")
    assert model["algorithm"] == algorithm
    assert model["data_scope"] == "full"
    assert result.processed_row_count == 80
    if problem_type != "regression":
        scored = SklearnScoringEngine(repository).execute(
            ScoringDefinition(
                row_id_column="row_id",
                target_column="target",
                dataset_name=f"{algorithm} predictions",
                batch_size=100,
            ),
            _relation(path, 40),
            model,
            run_id=f"run-{algorithm}",
            owner_id="owner-1",
            is_dry_run=True,
        )
        scoring_output = scored.output_manifest[0]
        schema_names = {item["name"] for item in scoring_output["schema"]}
        assert "prediction_score" in schema_names
        assert "positive_class_probability" not in schema_names
        assert scoring_output["score_contract"]["positive_class"] == 1
        assert scoring_output["score_contract"]["prediction_score_kind"] == "decision_function"
    else:
        scored = SklearnScoringEngine(repository).execute(
            ScoringDefinition(
                row_id_column="row_id",
                target_column="target",
                dataset_name=f"{algorithm} predictions",
                batch_size=100,
            ),
            _relation(path, 40),
            model,
            run_id=f"run-{algorithm}",
            owner_id="owner-1",
            is_dry_run=True,
        )
        schema_names = {item["name"] for item in scored.output_manifest[0]["schema"]}
        assert "prediction_score" not in schema_names
        assert "positive_class_probability" not in schema_names
        assert scored.output_manifest[0]["score_contract"]["problem_type"] == "regression"


def test_multiclass_scoring_persists_per_class_probabilities(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    source = repository / "users" / "owner-1" / "source"
    source.mkdir(parents=True)
    path = source / "multiclass.parquet"
    escaped_path = str(path).replace("'", "''")
    duckdb.connect().execute(
        "COPY (SELECT range AS row_id, range::DOUBLE AS x, "
        "CASE WHEN range < 20 THEN 0 WHEN range < 40 THEN 1 ELSE 2 END AS target "
        f"FROM range(60)) TO '{escaped_path}' (FORMAT PARQUET)"
    ).close()
    trained = SklearnTrainingEngine(repository).execute(
        TrainingDefinition(
            problem_type="multiclass_classification",
            algorithm="sgd_classifier",
            target_column="target",
            feature_columns=["x"],
            epochs=5,
            batch_size=100,
        ),
        _relation(path, 60),
        None,
        run_id="multiclass-run",
        owner_id="owner-1",
        is_dry_run=True,
    )
    model = next(item for item in trained.output_manifest if item["output_id"] == "model")
    scored = SklearnScoringEngine(repository).execute(
        ScoringDefinition(
            row_id_column="row_id",
            target_column="target",
            dataset_name="Multiclass predictions",
            batch_size=100,
        ),
        _relation(path, 60),
        model,
        run_id="multiclass-run",
        owner_id="owner-1",
        is_dry_run=True,
    )

    output = scored.output_manifest[0]
    schema_names = {item["name"] for item in output["schema"]}
    assert {"prediction_score", "class_probability_0", "class_probability_1", "class_probability_2"} <= schema_names
    assert output["score_contract"]["positive_class"] is None
    assert [item["label"] for item in output["score_contract"]["classes"]] == [0, 1, 2]


def test_training_parameters_are_scoped_to_selected_algorithm() -> None:
    with pytest.raises(ValueError, match="Unsupported training parameters"):
        TrainingDefinition(
            problem_type="binary_classification",
            algorithm="sgd_classifier",
            target_column="target",
            feature_columns=["x"],
            parameters={"C": 2},
        )


def test_runtime_input_resolution_does_not_inject_inputs_into_training_definition() -> None:
    definition = {
        "steps": [
            {
                "step_id": "de_1",
                "type": "data_engineering",
                "config": {
                    "definition": {
                        "inputs": [{"input_id": "source", "dataset_id": "logical-dataset"}]
                    }
                },
            },
            {
                "step_id": "training_1",
                "type": "training",
                "config": {
                    "definition": {
                        "problem_type": "binary_classification",
                        "algorithm": "perceptron_classifier",
                        "target_column": "target",
                        "feature_columns": ["x"],
                    }
                },
            },
        ]
    }
    resolved = _definition_with_resolved_inputs(
        definition,
        {
            "resolved_input_versions": {
                "de_1:source": {"dataset_id": "physical-version"}
            }
        },
    )

    assert resolved["steps"][0]["config"]["definition"]["inputs"][0]["dataset_id"] == "physical-version"
    assert "inputs" not in resolved["steps"][1]["config"]["definition"]


def test_training_and_scoring_workflow_requires_typed_ports() -> None:
    definition = {
        "contract_version": "2.0",
        "steps": [
            {
                "step_id": "fe",
                "name": "Feature Engineering",
                "type": "feature_engineering",
                "inputs": [],
                "output_port_id": "training",
                "additional_output_port_ids": ["test", "fitted_transform"],
                "config": {
                    "definition": {
                        "contract_version": "1.0",
                        "mode": "fit_transform",
                        "inputs": [
                            {"input_id": "training", "role": "training", "dataset_id": "train"},
                            {"input_id": "test", "role": "test", "dataset_id": "test"},
                        ],
                        "feature_columns": ["x"],
                        "target_column": "target",
                        "row_id_column": "row_id",
                        "transformations": [],
                        "outputs": [
                            {
                                "output_id": "training_features",
                                "input_id": "training",
                                "dataset_name": "Training features",
                                "business_case_role": "training",
                            },
                            {
                                "output_id": "test_features",
                                "input_id": "test",
                                "dataset_name": "Test features",
                                "business_case_role": "test",
                            },
                        ],
                    }
                },
            },
            {
                "step_id": "train",
                "name": "Training",
                "type": "training",
                "inputs": [
                    {"port_id": "training", "source": {"step_id": "fe", "port_id": "training"}}
                ],
                "output_port_id": "model",
                "additional_output_port_ids": ["metrics"],
                "config": {
                    "definition": {
                        "problem_type": "binary_classification",
                        "algorithm": "sgd_classifier",
                        "target_column": "target",
                        "feature_columns": ["x"],
                    }
                },
            },
            {
                "step_id": "score",
                "name": "Test scoring",
                "type": "scoring",
                "inputs": [
                    {"port_id": "data", "source": {"step_id": "fe", "port_id": "test"}},
                    {"port_id": "model", "source": {"step_id": "train", "port_id": "model"}},
                ],
                "output_port_id": "predictions",
                "additional_output_port_ids": [],
                "config": {
                    "definition": {
                        "row_id_column": "row_id",
                        "target_column": "target",
                    }
                },
            },
        ],
        "outputs": [
            {"output_id": "predictions", "source": {"step_id": "score", "port_id": "predictions"}}
        ],
    }

    validated = validate_workflow_definition(definition, executable=True)
    assert [step["type"] for step in validated["steps"]] == [
        "feature_engineering",
        "training",
        "scoring",
    ]

    invalid = {
        **definition,
        "steps": [
            *definition["steps"][:2],
            {**definition["steps"][2], "inputs": definition["steps"][2]["inputs"][:1]},
        ],
    }
    with pytest.raises(ValueError, match="data.*model"):
        validate_workflow_definition(invalid, executable=True)

    early_stopping_without_validation = {
        **definition,
        "steps": [
            definition["steps"][0],
            {
                **definition["steps"][1],
                "config": {
                    "definition": {
                        **definition["steps"][1]["config"]["definition"],
                        "early_stopping": True,
                    }
                },
            },
        ],
        "outputs": [
            {"output_id": "model", "source": {"step_id": "train", "port_id": "model"}}
        ],
    }
    with pytest.raises(ValueError, match="early stopping.*validation"):
        validate_workflow_definition(early_stopping_without_validation, executable=True)
