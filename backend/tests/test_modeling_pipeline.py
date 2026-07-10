from pathlib import Path

import duckdb
import joblib
import numpy as np
import pytest

from app.modules.pipelines.modeling import (
    ModelingResult,
    ScoringDefinition,
    SklearnScoringEngine,
    SklearnTrainingEngine,
    TrainingDefinition,
)
from app.modules.pipelines.modeling_catalog import (
    ALGORITHM_SPECS,
    build_estimator,
    training_catalog,
)
from app.modules.pipelines.runtime import SourceRelation
from app.modules.pipelines.step_handlers import StepExecutionContext, TrainingStepHandler
from app.modules.pipelines.workflow import WorkflowStep, validate_workflow_definition
from app.worker.tasks import _definition_with_resolved_inputs


def _relation(path: Path, rows: int) -> SourceRelation:
    escaped = str(path).replace("'", "''")
    return SourceRelation(sql=f"read_parquet('{escaped}')", row_count=rows)


def test_training_resolves_dynamic_one_hot_features_from_upstream_contract() -> None:
    captured: dict[str, TrainingDefinition] = {}

    class Engine:
        def execute(self, definition, training, validation, **kwargs):
            captured["definition"] = definition
            return ModelingResult(10, 10, 1, [], [])

    step = WorkflowStep.model_validate({
        "step_id": "training_1",
        "name": "Training",
        "type": "training",
        "inputs": [{
            "port_id": "training",
            "source": {"step_id": "fe_1", "port_id": "training"},
        }],
        "output_port_id": "model",
        "config": {"definition": {
            "problem_type": "binary_classification",
            "algorithm": "sgd_classifier",
            "target_column": "churned",
            "feature_columns": ["age", "segment"],
            "feature_selection": "upstream_contract",
        }},
    })
    relation = SourceRelation(
        sql="input",
        row_count=10,
        metadata={"feature_manifest": [
            {"name": "age", "role": "feature"},
            {"name": "segment_0", "role": "feature"},
            {"name": "segment_1", "role": "feature"},
            {"name": "churned", "role": "target"},
        ]},
    )

    TrainingStepHandler(Engine()).execute(
        step,
        StepExecutionContext(
            run_id="run-1",
            owner_id="owner-1",
            is_dry_run=True,
            upstream_relations={("fe_1", "training"): relation},
        ),
    )

    assert captured["definition"].feature_columns == ["age", "segment_0", "segment_1"]


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
    assert model["training_config"]["feature_columns"] == ["x"]
    assert model["training_config"]["target_column"] == "target"
    assert model["model_parameters"]["total_weight_count"] == 1
    assert model["model_parameters"]["weights"][0]["feature"] == "x"
    assert model["model_parameters"]["returned_weight_count"] == 1
    assert model["model_parameters"]["truncated"] is False

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
    assert output["evaluation"]["contract_version"] == "1.0"
    assert output["evaluation"]["status"] == "available"
    assert output["evaluation"]["data_scope"]["evaluated_row_count"] == 20
    assert {
        metric["id"] for metric in output["evaluation"]["metrics"]
    } >= {"accuracy", "f1_macro", "roc_auc", "average_precision"}
    assert output["evaluation"]["confusion_matrix"]["values"]
    assert output["evaluation"]["monitoring"]["baseline_eligible"] is True
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


def test_batch_scoring_creates_predictions_without_performance_report(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    source = repository / "users" / "owner-1" / "source"
    source.mkdir(parents=True)
    train_path = source / "train.parquet"
    scoring_path = source / "scoring.parquet"
    connection = duckdb.connect()
    connection.execute(
        "COPY (SELECT range AS row_id, range::DOUBLE AS x, "
        "CASE WHEN range >= 20 THEN 1 ELSE 0 END AS target FROM range(40)) "
        f"TO '{str(train_path).replace(chr(39), chr(39) * 2)}' (FORMAT PARQUET)"
    )
    connection.execute(
        "COPY (SELECT range + 100 AS row_id, range::DOUBLE AS x FROM range(15)) "
        f"TO '{str(scoring_path).replace(chr(39), chr(39) * 2)}' (FORMAT PARQUET)"
    )
    connection.close()
    trained = SklearnTrainingEngine(repository).execute(
        TrainingDefinition(
            problem_type="binary_classification",
            algorithm="sgd_classifier",
            target_column="target",
            feature_columns=["x"],
            epochs=2,
            batch_size=100,
        ),
        _relation(train_path, 40),
        None,
        run_id="batch-run",
        owner_id="owner-1",
        is_dry_run=True,
    )
    model = next(item for item in trained.output_manifest if item["output_id"] == "model")

    scored = SklearnScoringEngine(repository).execute(
        ScoringDefinition(
            purpose="batch",
            model_artifact_id="model-artifact-1",
            row_id_column="row_id",
            dataset_name="Batch predictions",
            batch_size=100,
        ),
        _relation(scoring_path, 15),
        model,
        run_id="batch-run",
        owner_id="owner-1",
        is_dry_run=True,
    )

    output = scored.output_manifest[0]
    assert output["row_count"] == 15
    assert output["metrics"] == {"scored_row_count": 15}
    assert "evaluation" not in output


def test_batch_scoring_rejects_non_unique_record_ids(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    source = repository / "users" / "owner-1" / "source"
    source.mkdir(parents=True)
    path = source / "duplicates.parquet"
    escaped_path = str(path).replace("'", "''")
    duckdb.connect().execute(
        "COPY (SELECT range % 2 AS row_id, range::DOUBLE AS x, "
        "CASE WHEN range >= 2 THEN 1 ELSE 0 END AS target FROM range(4)) "
        f"TO '{escaped_path}' (FORMAT PARQUET)"
    ).close()
    trained = SklearnTrainingEngine(repository).execute(
        TrainingDefinition(
            problem_type="binary_classification",
            algorithm="sgd_classifier",
            target_column="target",
            feature_columns=["x"],
            epochs=1,
            batch_size=100,
        ),
        _relation(path, 4),
        None,
        run_id="duplicate-run",
        owner_id="owner-1",
        is_dry_run=True,
    )
    model = next(item for item in trained.output_manifest if item["output_id"] == "model")

    with pytest.raises(ValueError, match="must be unique"):
        SklearnScoringEngine(repository).execute(
            ScoringDefinition(
                purpose="batch",
                model_artifact_id="model-artifact-1",
                row_id_column="row_id",
            ),
            _relation(path, 4),
            model,
            run_id="duplicate-run",
            owner_id="owner-1",
            is_dry_run=True,
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


def test_training_catalog_exposes_a_broad_executable_algorithm_registry() -> None:
    catalog = training_catalog()
    classification = [
        item for item in catalog["algorithms"]
        if "binary_classification" in item["problem_types"]
    ]
    regression = [
        item for item in catalog["algorithms"]
        if "regression" in item["problem_types"]
    ]

    assert catalog["algorithm_count"] >= 50
    assert len(classification) >= 25
    assert len(regression) >= 20
    assert {
        "Linear models",
        "Support vector machines",
        "Tree ensembles",
        "Modern boosting",
        "Neural networks",
    } <= {item["family"] for item in catalog["algorithms"]}
    assert {
        "single", "grid_search", "random_search", "optuna", "automl"
    } == {item["id"] for item in catalog["optimization_modes"]}
    assert all(item["parameters"] is not None for item in catalog["algorithms"])


def test_every_available_catalog_entry_has_an_estimator_factory() -> None:
    built = [
        build_estimator(
            spec.id,
            spec.problem_types[0],
            {},
            random_seed=42,
            n_jobs=1,
        )
        for spec in ALGORITHM_SPECS
        if spec.available
    ]

    assert len(built) >= 40


@pytest.mark.parametrize(
    ("problem_type", "algorithm", "parameters"),
    [
        ("binary_classification", "logistic_regression", {}),
        ("binary_classification", "linear_svc", {}),
        (
            "binary_classification",
            "random_forest_classifier",
            {"n_estimators": 20, "max_depth": 4},
        ),
        (
            "binary_classification",
            "hist_gradient_boosting_classifier",
            {"max_iter": 20, "max_depth": 4},
        ),
        (
            "binary_classification",
            "mlp_classifier",
            {"hidden_layer_sizes": [8], "max_iter": 40, "early_stopping": False},
        ),
        ("regression", "ridge_regression", {}),
        ("regression", "linear_svr", {}),
        (
            "regression",
            "random_forest_regressor",
            {"n_estimators": 20, "max_depth": 4},
        ),
        (
            "regression",
            "hist_gradient_boosting_regressor",
            {"max_iter": 20, "max_depth": 4},
        ),
        (
            "regression",
            "mlp_regressor",
            {"hidden_layer_sizes": [8], "max_iter": 40, "early_stopping": False},
        ),
    ],
)
def test_representative_advanced_estimators_train_on_the_complete_scope(
    tmp_path: Path,
    problem_type: str,
    algorithm: str,
    parameters: dict,
) -> None:
    repository = tmp_path / "repository"
    source = repository / "users" / "owner-1" / "source"
    source.mkdir(parents=True)
    path = source / f"{algorithm}.parquet"
    target = (
        "range::DOUBLE * 2.5 + sin(range::DOUBLE / 3)"
        if problem_type == "regression"
        else "CASE WHEN range % 17 < 8 THEN 1 ELSE 0 END"
    )
    escaped_path = str(path).replace("'", "''")
    duckdb.connect().execute(
        f"COPY (SELECT range AS row_id, range::DOUBLE AS x, "
        f"sin(range::DOUBLE / 5) AS wave, {target} AS target FROM range(80)) "
        f"TO '{escaped_path}' (FORMAT PARQUET)"
    ).close()

    result = SklearnTrainingEngine(repository).execute(
        TrainingDefinition(
            problem_type=problem_type,
            algorithm=algorithm,
            target_column="target",
            feature_columns=["x", "wave"],
            parameters=parameters,
            resource_limits={"max_memory_mb": 128, "max_parallel_jobs": 1},
        ),
        _relation(path, 80),
        None,
        run_id=f"run-{algorithm}",
        owner_id="owner-1",
        is_dry_run=True,
    )

    model = next(item for item in result.output_manifest if item["output_id"] == "model")
    assert model["algorithm"] == algorithm
    assert model["data_scope"] == "full"
    assert model["metrics"]["evaluated_row_count"] == 80
    assert result.input_row_count == 80
    assert result.processed_row_count == 80
    assert "materialized in worker memory" in result.warnings[0]


def test_grid_search_records_trials_and_refits_the_best_full_data_model(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    source = repository / "users" / "owner-1" / "source"
    source.mkdir(parents=True)
    path = source / "grid.parquet"
    escaped_path = str(path).replace("'", "''")
    duckdb.connect().execute(
        "COPY (SELECT range AS row_id, range::DOUBLE AS x, "
        "CASE WHEN range >= 30 THEN 1 ELSE 0 END AS target FROM range(60)) "
        f"TO '{escaped_path}' (FORMAT PARQUET)"
    ).close()

    result = SklearnTrainingEngine(repository).execute(
        TrainingDefinition(
            problem_type="binary_classification",
            algorithm="logistic_regression",
            target_column="target",
            feature_columns=["x"],
            optimization={
                "mode": "grid_search",
                "validation_strategy": "cross_validation",
                "primary_metric": "accuracy",
                "cv_folds": 3,
                "max_trials": 4,
                "timeout_seconds": 60,
            },
            resource_limits={"max_memory_mb": 128, "max_parallel_jobs": 1},
        ),
        _relation(path, 60),
        None,
        run_id="grid-run",
        owner_id="owner-1",
        is_dry_run=True,
    )

    model = next(item for item in result.output_manifest if item["output_id"] == "model")
    optimization = model["metrics"]["optimization"]
    assert optimization["mode"] == "grid_search"
    assert optimization["trial_count"] == 4
    assert optimization["planned_trial_count"] == 4
    assert optimization["total_candidate_count"] >= 4
    assert optimization["max_trials"] == 4
    assert optimization["successful_trial_count"] == 4
    assert optimization["best_score"] is not None
    assert optimization["best_algorithm"] == "logistic_regression"
    assert len(optimization["trials"]) == 4
    assert result.processed_row_count == 60 + 60 * 2 * 4


def test_grid_search_uses_user_configured_search_space(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    source = repository / "users" / "owner-1" / "source"
    source.mkdir(parents=True)
    path = source / "custom-grid.parquet"
    escaped_path = str(path).replace("'", "''")
    duckdb.connect().execute(
        "COPY (SELECT range AS row_id, range::DOUBLE AS x, "
        "CASE WHEN range >= 20 THEN 1 ELSE 0 END AS target FROM range(40)) "
        f"TO '{escaped_path}' (FORMAT PARQUET)"
    ).close()

    result = SklearnTrainingEngine(repository).execute(
        TrainingDefinition(
            problem_type="binary_classification",
            algorithm="logistic_regression",
            target_column="target",
            feature_columns=["x"],
            optimization={
                "mode": "grid_search",
                "validation_strategy": "cross_validation",
                "primary_metric": "accuracy",
                "cv_folds": 2,
                "max_trials": 2,
                "timeout_seconds": 60,
                "search_space": {
                    "C": {"kind": "float", "low": 0.25, "high": 0.5, "points": 2},
                    "penalty": {"kind": "categorical", "values": ["l2"]},
                },
            },
            resource_limits={"max_memory_mb": 128, "max_parallel_jobs": 1},
        ),
        _relation(path, 40),
        None,
        run_id="custom-grid-run",
        owner_id="owner-1",
        is_dry_run=True,
    )

    model = next(item for item in result.output_manifest if item["output_id"] == "model")
    optimization = model["metrics"]["optimization"]
    assert optimization["search_space"]["C"] == [0.25, 0.5]
    assert optimization["search_space"]["penalty"] == ["l2"]
    assert {
        trial["parameters"]["C"]
        for trial in optimization["trials"]
        if trial["status"] == "succeeded"
    }.issubset({0.25, 0.5})


def test_grid_search_allows_large_deterministic_combination_cap() -> None:
    definition = TrainingDefinition(
        problem_type="binary_classification",
        algorithm="random_forest_classifier",
        target_column="target",
        feature_columns=["x"],
        optimization={"mode": "grid_search", "max_trials": 100000},
    )

    assert definition.optimization.max_trials == 100000


def test_non_grid_optimization_rejects_excessive_trial_cap() -> None:
    with pytest.raises(ValueError, match="limited to 1000 trials"):
        TrainingDefinition(
            problem_type="binary_classification",
            algorithm="random_forest_classifier",
            target_column="target",
            feature_columns=["x"],
            optimization={"mode": "optuna", "max_trials": 100000},
        )


def test_in_memory_training_rejects_scope_above_explicit_budget_without_sampling(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    source = repository / "users" / "owner-1" / "source"
    source.mkdir(parents=True)
    path = source / "too-large.parquet"
    escaped_path = str(path).replace("'", "''")
    duckdb.connect().execute(
        "COPY (SELECT range::DOUBLE AS x, range % 2 AS target FROM range(10)) "
        f"TO '{escaped_path}' (FORMAT PARQUET)"
    ).close()

    with pytest.raises(ValueError, match="data was not sampled"):
        SklearnTrainingEngine(repository).execute(
            TrainingDefinition(
                problem_type="binary_classification",
                algorithm="random_forest_classifier",
                target_column="target",
                feature_columns=["x"],
                resource_limits={"max_memory_mb": 128, "max_parallel_jobs": 1},
            ),
            _relation(path, 100_000_000),
            None,
            run_id="memory-run",
            owner_id="owner-1",
            is_dry_run=True,
        )


@pytest.mark.parametrize(
    ("problem_type", "algorithm", "parameters"),
    [
        (
            "binary_classification",
            "xgboost_classifier",
            {"n_estimators": 20, "max_depth": 3},
        ),
        (
            "binary_classification",
            "lightgbm_classifier",
            {"n_estimators": 20, "max_depth": 3},
        ),
        (
            "binary_classification",
            "catboost_classifier",
            {"iterations": 20, "depth": 3},
        ),
        (
            "regression",
            "xgboost_regressor",
            {"n_estimators": 20, "max_depth": 3},
        ),
        (
            "regression",
            "lightgbm_regressor",
            {"n_estimators": 20, "max_depth": 3},
        ),
        (
            "regression",
            "catboost_regressor",
            {"iterations": 20, "depth": 3},
        ),
    ],
)
def test_external_boosters_train_and_persist_full_scope_models(
    tmp_path: Path,
    problem_type: str,
    algorithm: str,
    parameters: dict,
) -> None:
    repository = tmp_path / "repository"
    source = repository / "users" / "owner-1" / "source"
    source.mkdir(parents=True)
    path = source / f"{algorithm}.parquet"
    target = (
        "range::DOUBLE * 1.7 + cos(range::DOUBLE / 5)"
        if problem_type == "regression"
        else "CASE WHEN range % 11 < 5 THEN 'yes' ELSE 'no' END"
    )
    escaped_path = str(path).replace("'", "''")
    duckdb.connect().execute(
        f"COPY (SELECT range AS row_id, range::DOUBLE AS x, "
        f"cos(range::DOUBLE / 4) AS wave, {target} AS target FROM range(70)) "
        f"TO '{escaped_path}' (FORMAT PARQUET)"
    ).close()

    result = SklearnTrainingEngine(repository).execute(
        TrainingDefinition(
            problem_type=problem_type,
            algorithm=algorithm,
            target_column="target",
            feature_columns=["x", "wave"],
            parameters=parameters,
            resource_limits={"max_memory_mb": 128, "max_parallel_jobs": 1},
        ),
        _relation(path, 70),
        None,
        run_id=f"run-{algorithm}",
        owner_id="owner-1",
        is_dry_run=True,
    )

    model = next(item for item in result.output_manifest if item["output_id"] == "model")
    assert model["algorithm"] == algorithm
    assert model["metrics"]["evaluated_row_count"] == 70
    assert model["model_hash"]
    assert result.processed_row_count == 70
    scored = SklearnScoringEngine(repository).execute(
        ScoringDefinition(
            row_id_column="row_id",
            target_column="target",
            dataset_name=f"{algorithm} predictions",
            batch_size=100,
        ),
        _relation(path, 70),
        model,
        run_id=f"score-{algorithm}",
        owner_id="owner-1",
        is_dry_run=True,
    )
    output = scored.output_manifest[0]
    assert output["row_count"] == 70
    assert output["score_contract"]["problem_type"] == problem_type
    if problem_type != "regression":
        assert output["score_contract"]["positive_class"] == "yes"


def test_optuna_search_is_reproducible_and_persists_trial_history(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    source = repository / "users" / "owner-1" / "source"
    source.mkdir(parents=True)
    path = source / "optuna.parquet"
    escaped_path = str(path).replace("'", "''")
    duckdb.connect().execute(
        "COPY (SELECT range AS row_id, range::DOUBLE AS x, "
        "CASE WHEN range % 13 < 6 THEN 1 ELSE 0 END AS target FROM range(78)) "
        f"TO '{escaped_path}' (FORMAT PARQUET)"
    ).close()

    result = SklearnTrainingEngine(repository).execute(
        TrainingDefinition(
            problem_type="binary_classification",
            algorithm="hist_gradient_boosting_classifier",
            target_column="target",
            feature_columns=["x"],
            optimization={
                "mode": "optuna",
                "validation_strategy": "cross_validation",
                "primary_metric": "balanced_accuracy",
                "cv_folds": 3,
                "max_trials": 3,
                "timeout_seconds": 60,
            },
            resource_limits={"max_memory_mb": 128, "max_parallel_jobs": 1},
        ),
        _relation(path, 78),
        None,
        run_id="optuna-run",
        owner_id="owner-1",
        is_dry_run=True,
    )

    model = next(item for item in result.output_manifest if item["output_id"] == "model")
    optimization = model["metrics"]["optimization"]
    assert optimization["mode"] == "optuna"
    assert optimization["trial_count"] == 3
    assert optimization["successful_trial_count"] == 3
    assert optimization["best_algorithm"] == "hist_gradient_boosting_classifier"
    assert all(item["fold_scores"] for item in optimization["trials"])


def test_automl_selects_and_refits_one_of_the_explicit_candidates(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    source = repository / "users" / "owner-1" / "source"
    source.mkdir(parents=True)
    path = source / "automl.parquet"
    escaped_path = str(path).replace("'", "''")
    duckdb.connect().execute(
        "COPY (SELECT range AS row_id, range::DOUBLE AS x, "
        "sin(range::DOUBLE / 4) AS wave, "
        "range::DOUBLE * 2 + sin(range::DOUBLE / 3) AS target FROM range(75)) "
        f"TO '{escaped_path}' (FORMAT PARQUET)"
    ).close()

    result = SklearnTrainingEngine(repository).execute(
        TrainingDefinition(
            problem_type="regression",
            algorithm="ridge_regression",
            target_column="target",
            feature_columns=["x", "wave"],
            optimization={
                "mode": "automl",
                "validation_strategy": "cross_validation",
                "primary_metric": "neg_root_mean_squared_error",
                "cv_folds": 3,
                "max_trials": 4,
                "timeout_seconds": 60,
                "candidate_algorithms": [
                    "ridge_regression",
                    "decision_tree_regressor",
                ],
            },
            resource_limits={"max_memory_mb": 128, "max_parallel_jobs": 1},
        ),
        _relation(path, 75),
        None,
        run_id="automl-run",
        owner_id="owner-1",
        is_dry_run=True,
    )

    model = next(item for item in result.output_manifest if item["output_id"] == "model")
    optimization = model["metrics"]["optimization"]
    assert optimization["mode"] == "automl"
    assert optimization["trial_count"] == 4
    assert optimization["best_algorithm"] in {
        "ridge_regression", "decision_tree_regressor"
    }
    assert model["algorithm"] == optimization["best_algorithm"]
    assert model["training_config"]["resolved_algorithm"] == model["algorithm"]


def test_optimization_uses_auditable_upstream_cv_fold_assignments(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    source = repository / "users" / "owner-1" / "source"
    source.mkdir(parents=True)
    path = source / "planned-folds.parquet"
    escaped_path = str(path).replace("'", "''")
    duckdb.connect().execute(
        "COPY (SELECT range AS row_id, range::DOUBLE AS x, "
        "range % 3 AS __mlapp_cv_fold, "
        "CASE WHEN range % 7 < 3 THEN 1 ELSE 0 END AS target FROM range(60)) "
        f"TO '{escaped_path}' (FORMAT PARQUET)"
    ).close()
    relation = _relation(path, 60)
    relation = SourceRelation(
        sql=relation.sql,
        row_count=relation.row_count,
        metadata={
            "feature_manifest": [
                {"name": "x", "role": "feature"},
                {"name": "target", "role": "target"},
                {"name": "__mlapp_cv_fold", "role": "cv_fold"},
            ],
            "split_evaluation": {
                "cross_validation": {
                    "enabled": True,
                    "strategy": "stratified",
                    "folds": 3,
                }
            },
            "fitted_transform_count": 0,
        },
    )

    result = SklearnTrainingEngine(repository).execute(
        TrainingDefinition(
            problem_type="binary_classification",
            algorithm="logistic_regression",
            target_column="target",
            feature_columns=["x"],
            optimization={
                "mode": "grid_search",
                "validation_strategy": "cross_validation",
                "primary_metric": "accuracy",
                "cv_folds": 5,
                "max_trials": 2,
                "timeout_seconds": 60,
            },
            resource_limits={"max_memory_mb": 128, "max_parallel_jobs": 1},
        ),
        relation,
        None,
        run_id="planned-fold-run",
        owner_id="owner-1",
        is_dry_run=True,
    )

    model = next(item for item in result.output_manifest if item["output_id"] == "model")
    assert model["metrics"]["optimization"]["cv_fold_source"] == "upstream_plan"
    assert any("upstream CV fold plan with 3 folds" in warning for warning in result.warnings)
    assert result.processed_row_count == 60 + 60 * 2 * 2


def test_cross_validation_rejects_reused_full_training_fe_state(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    source = repository / "users" / "owner-1" / "source"
    source.mkdir(parents=True)
    path = source / "leaky-fe.parquet"
    escaped_path = str(path).replace("'", "''")
    duckdb.connect().execute(
        "COPY (SELECT range::DOUBLE AS x, range % 2 AS target FROM range(20)) "
        f"TO '{escaped_path}' (FORMAT PARQUET)"
    ).close()
    relation = _relation(path, 20)
    relation = SourceRelation(
        sql=relation.sql,
        row_count=relation.row_count,
        metadata={"fitted_transform_count": 2},
    )

    with pytest.raises(ValueError, match="no potentially leaked CV score"):
        SklearnTrainingEngine(repository).execute(
            TrainingDefinition(
                problem_type="binary_classification",
                algorithm="logistic_regression",
                target_column="target",
                feature_columns=["x"],
                optimization={
                    "mode": "optuna",
                    "validation_strategy": "cross_validation",
                    "max_trials": 2,
                    "timeout_seconds": 60,
                },
                resource_limits={"max_memory_mb": 128, "max_parallel_jobs": 1},
            ),
            relation,
            None,
            run_id="leakage-guard-run",
            owner_id="owner-1",
            is_dry_run=True,
        )


def test_incomplete_modeling_steps_are_valid_drafts_but_not_executable() -> None:
    training = TrainingDefinition(
        problem_type="binary_classification",
        algorithm="sgd_classifier",
    )
    with pytest.raises(ValueError, match="target column"):
        training.validate_executable()

    scoring = ScoringDefinition(purpose="batch")
    with pytest.raises(ValueError, match="row ID"):
        scoring.validate_executable()


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


def test_batch_scoring_workflow_pins_model_and_has_no_target_or_model_port() -> None:
    definition = {
        "contract_version": "2.0",
        "steps": [
            {
                "step_id": "de",
                "name": "Scoring preparation",
                "type": "data_engineering",
                "inputs": [],
                "output_port_id": "dataset",
                "additional_output_port_ids": [],
                "config": {
                    "definition": {
                        "contract_version": "1.0",
                        "inputs": [{
                            "input_id": "scoring_input",
                            "dataset_id": "",
                            "version_policy": "select_at_run_any",
                        }],
                        "steps": [],
                        "outputs": [{
                            "output_id": "prepared",
                            "input": {"node_id": "scoring_input", "port_id": "out"},
                            "materialization": "temporary",
                            "dataset_name": "Prepared scoring input",
                            "business_case_role": "scoring_input",
                        }],
                    }
                },
            },
            {
                "step_id": "fe",
                "name": "Feature transform",
                "type": "feature_engineering",
                "inputs": [{
                    "port_id": "scoring_input",
                    "source": {"step_id": "de", "port_id": "dataset"},
                }],
                "output_port_id": "scoring_input",
                "additional_output_port_ids": [],
                "config": {
                    "definition": {
                        "contract_version": "1.0",
                        "mode": "transform",
                        "inputs": [{
                            "input_id": "scoring_input",
                            "role": "scoring_input",
                        }],
                        "feature_columns": ["x"],
                        "row_id_column": "row_id",
                        "transformations": [],
                        "outputs": [{
                            "output_id": "scoring_features",
                            "input_id": "scoring_input",
                            "dataset_name": "Scoring features",
                            "business_case_role": "scoring_input",
                        }],
                        "fitted_state_artifact_id": "fitted-1",
                    }
                },
            },
            {
                "step_id": "score",
                "name": "Batch scoring",
                "type": "scoring",
                "inputs": [{
                    "port_id": "data",
                    "source": {"step_id": "fe", "port_id": "scoring_input"},
                }],
                "output_port_id": "predictions",
                "additional_output_port_ids": [],
                "config": {
                    "definition": {
                        "purpose": "batch",
                        "model_artifact_id": "model-1",
                        "row_id_column": "row_id",
                        "target_column": "",
                    }
                },
            },
        ],
        "outputs": [{
            "output_id": "predictions",
            "source": {"step_id": "score", "port_id": "predictions"},
        }],
    }

    validated = validate_workflow_definition(definition, executable=True)
    assert validated["steps"][2]["config"]["definition"]["purpose"] == "batch"

    invalid = {
        **definition,
        "steps": [
            definition["steps"][0],
            definition["steps"][1],
            {
                **definition["steps"][2],
                "config": {
                    "definition": {
                        **definition["steps"][2]["config"]["definition"],
                        "target_column": "target",
                    }
                },
            },
        ],
    }
    with pytest.raises(ValueError, match="cannot consume a target"):
        validate_workflow_definition(invalid, executable=True)
