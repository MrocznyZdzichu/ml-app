from types import SimpleNamespace

import duckdb
import pytest

from app.modules.pipelines.runtime import SourceRelation, sql_literal
from app.modules.pipelines.autofe import DuckDbAutoFEPlanner, model_aware_autofe_plans
from app.modules.pipelines.feature_engineering import DuckDbFeatureEngineeringEngine
from app.modules.pipelines.feature_engineering import empty_feature_engineering_definition
from app.modules.pipelines.modeling import SklearnTrainingEngine, TrainingDefinition
from app.modules.pipelines.step_handlers import AutoMLStepHandler, StepExecutionContext
from app.modules.pipelines.workflow import WorkflowStep, validate_workflow_definition


def automl_definition(*, mode: str = "automl", autofe: bool = False) -> dict:
    return {
        "contract_version": "1.0",
        "problem_type": "binary_classification",
        "algorithm": "sgd_classifier",
        "target_column": "target",
        "feature_columns": ["x"],
        "feature_selection": "explicit",
        "model_name": "AutoML champion",
        "epochs": 5,
        "early_stopping": False,
        "early_stopping_patience": 5,
        "early_stopping_min_delta": 0.0001,
        "batch_size": 1000,
        "random_seed": 42,
        "parameters": {},
        "optimization": {
            "mode": mode,
            "validation_strategy": "holdout",
            "primary_metric": "auto",
            "cv_folds": 5,
            "max_trials": 10,
            "timeout_seconds": 60,
            "candidate_algorithms": ["sgd_classifier"],
            "search_space": {},
        },
        "resource_limits": {"max_memory_mb": 512, "max_parallel_jobs": 1},
        "auto_feature_engineering": {
            "enabled": autofe,
            "strategy": "balanced",
            "row_id_column": "row_id" if autofe else "",
            "excluded_columns": [],
            "validation_size": 0.2,
            "numeric_scaling": "standard",
            "add_missing_indicators": True,
            "include_datetime_features": True,
            "detect_identifier_columns": True,
            "min_category_frequency": 2,
            "max_one_hot_categories": 32,
            "max_frequency_categories": 500,
        },
    }


def automl_workflow(*, mode: str = "automl") -> dict:
    return {
        "contract_version": "2.0",
        "steps": [
            {
                "step_id": "de_1",
                "name": "Data Engineering",
                "type": "data_engineering",
                "inputs": [],
                "output_port_id": "dataset",
                "additional_output_port_ids": [],
                "config": {"definition": {
                    "contract_version": "1.0", "inputs": [], "steps": [],
                    "outputs": [], "parameters": {},
                }},
            },
            {
                "step_id": "automl_1",
                "name": "AutoML",
                "type": "automl",
                "inputs": [{
                    "port_id": "training",
                    "source": {"step_id": "de_1", "port_id": "dataset"},
                }],
                "output_port_id": "model",
                "additional_output_port_ids": ["metrics"],
                "config": {"definition": automl_definition(mode=mode)},
            },
        ],
        "outputs": [{
            "output_id": "result",
            "source": {"step_id": "automl_1", "port_id": "model"},
        }],
        "parameters": {"template": "automl"},
    }


def test_automl_workflow_contract_accepts_de_to_automl() -> None:
    validated = validate_workflow_definition(automl_workflow(), executable=False)
    assert [step["type"] for step in validated["steps"]] == ["data_engineering", "automl"]
    assert validated["steps"][1]["config"]["definition"]["optimization"]["mode"] == "automl"


def test_automl_workflow_preserves_inferred_data_engineering_provenance() -> None:
    workflow = automl_workflow()
    workflow["steps"][0]["config"]["definition"] = {
        "contract_version": "1.0",
        "inputs": [{
            "input_id": "source",
            "dataset_id": "",
            "output_port_id": "out",
            "version_policy": "select_at_run_any",
        }],
        "steps": [],
        "outputs": [{
            "output_id": "prepared",
            "input": {"node_id": "source", "port_id": "out"},
            "materialization": "temporary",
            "write_mode": "replace",
            "dataset_name": "",
            "business_case_role": "training",
        }],
        "parameters": {},
    }
    workflow["parameters"]["data_engineering_inferred_from"] = {
        "pipeline_id": "training-pipeline",
        "pipeline_version_id": "training-v3",
        "pipeline_version_number": 3,
        "pipeline_version_status": "published",
        "definition_hash": "abc123",
        "source_step_id": "source_de",
    }

    validated = validate_workflow_definition(workflow, executable=False)

    assert validated["steps"][0]["config"]["definition"]["outputs"][0]["output_id"] == "prepared"
    assert validated["parameters"]["data_engineering_inferred_from"] == {
        "pipeline_id": "training-pipeline",
        "pipeline_version_id": "training-v3",
        "pipeline_version_number": 3,
        "pipeline_version_status": "published",
        "definition_hash": "abc123",
        "source_step_id": "source_de",
    }


def test_custom_lifecycle_accepts_de_fe_automl_scoring_and_monitoring() -> None:
    workflow = automl_workflow()
    feature_definition = empty_feature_engineering_definition()
    feature_step = {
        "step_id": "fe_1",
        "name": "Feature Engineering",
        "type": "feature_engineering",
        "inputs": [{
            "port_id": "training",
            "source": {"step_id": "de_1", "port_id": "dataset"},
        }],
        "output_port_id": "training",
        "additional_output_port_ids": ["fitted_transform"],
        "config": {"definition": feature_definition},
    }
    workflow["steps"].insert(1, feature_step)
    workflow["steps"][2]["inputs"] = [
        {"port_id": "training", "source": {"step_id": "fe_1", "port_id": "training"}},
        {"port_id": "fitted_transform", "source": {"step_id": "fe_1", "port_id": "fitted_transform"}},
    ]
    workflow["steps"].extend([
        {
            "step_id": "scoring_1",
            "name": "Test Scoring",
            "type": "scoring",
            "inputs": [
                {"port_id": "data", "source": {"step_id": "fe_1", "port_id": "training"}},
                {"port_id": "model", "source": {"step_id": "automl_1", "port_id": "model"}},
            ],
            "output_port_id": "predictions",
            "additional_output_port_ids": [],
            "config": {"definition": {
                "contract_version": "1.0",
                "purpose": "test",
                "model_artifact_id": "",
                "row_id_column": "row_id",
                "target_column": "target",
                "prediction_column": "prediction",
                "dataset_name": "Predictions",
                "report_name": "Test report",
                "batch_size": 1000,
            }},
        },
        {
            "step_id": "monitoring_1",
            "name": "Monitoring",
            "type": "monitoring",
            "inputs": [{
                "port_id": "data",
                "source": {"step_id": "scoring_1", "port_id": "predictions"},
            }],
            "output_port_id": "performance_report",
            "additional_output_port_ids": [],
            "config": {"definition": {
                "contract_version": "2.0",
                "row_id_column": "row_id",
                "target_column": "target",
                "prediction_column": "prediction",
                "problem_type": "binary_classification",
                "report_name": "Model monitoring",
            }},
        },
    ])
    workflow["outputs"] = [{
        "output_id": "performance_report",
        "source": {"step_id": "monitoring_1", "port_id": "performance_report"},
    }]

    validated = validate_workflow_definition(workflow, executable=False)

    assert [step["type"] for step in validated["steps"]] == [
        "data_engineering", "feature_engineering", "automl", "scoring", "monitoring"
    ]


def test_automl_workflow_recovers_a_legacy_early_stopping_value() -> None:
    workflow = automl_workflow()
    workflow["steps"][1]["config"]["definition"]["early_stopping"] = True

    validated = validate_workflow_definition(workflow, executable=False)

    assert validated["steps"][1]["config"]["definition"]["early_stopping"] is False


def test_automl_workflow_rejects_non_automl_optimization_mode() -> None:
    with pytest.raises(ValueError, match="requires optimization mode 'automl'"):
        validate_workflow_definition(automl_workflow(mode="optuna"), executable=False)


def test_automl_handler_executes_through_native_training_engine() -> None:
    class Engine:
        def execute(self, definition, training, validation, **kwargs):
            assert definition.optimization.mode == "automl"
            assert training.metadata["scope"] == "full"
            assert validation is None
            return SimpleNamespace(
                input_row_count=100,
                processed_row_count=100,
                output_row_count=1,
                warnings=[],
                output_manifest=[{"output_id": "model", "artifact_type": "model_version"}],
            )

    step = WorkflowStep.model_validate(automl_workflow()["steps"][1])
    source = SourceRelation(
        sql="SELECT * FROM training",
        row_count=100,
        metadata={"scope": "full"},
    )
    result = AutoMLStepHandler(Engine()).execute(
        step,
        StepExecutionContext(
            run_id="run-1",
            owner_id="owner-1",
            is_dry_run=False,
            upstream_relations={("de_1", "dataset"): source},
        ),
    )
    assert result.processed_row_count == 100
    assert result.artifact_output_ids == {"model": "model", "metrics": "training_metrics"}


def test_autofe_planner_profiles_full_scope_and_builds_bounded_recipe(tmp_path) -> None:
    definition = TrainingDefinition.model_validate({
        **automl_definition(autofe=True),
        "feature_columns": [],
        "feature_selection": "upstream_contract",
    })
    source = SourceRelation(
        sql=(
            "(SELECT i AS row_id, CAST(i % 2 AS INTEGER) AS target, "
            "CASE WHEN i = 3 THEN NULL ELSE CAST(i AS DOUBLE) END AS amount, "
            "CASE WHEN i % 3 = 0 THEN 'a' ELSE 'b' END AS segment, "
            "'customer_' || CAST(i AS VARCHAR) AS customer_id, "
            "CAST(i % 5 AS INTEGER) AS __mlapp_cv_fold FROM range(100) t(i))"
        ),
        row_count=100,
    )

    plan = DuckDbAutoFEPlanner(tmp_path).plan(
        training=source,
        validation=None,
        test=None,
        training_definition=definition,
        run_id="run-plan",
        owner_id="owner",
    )

    assert plan.provenance["profiled_row_count"] == 100
    assert plan.provenance["data_scope"] == "full"
    assert plan.provenance["cardinality_is_approximate"] is True
    assert plan.provenance["validation_source"] == "generated_stratified_holdout"
    decisions = {item["column"]: item for item in plan.provenance["column_decisions"]}
    assert "__mlapp_cv_fold" not in decisions
    assert "__mlapp_cv_fold" not in plan.definition.feature_columns
    assert decisions["customer_id"]["action"] == "exclude"
    assert decisions["segment"]["action"] == "one_hot"
    assert [item.type for item in plan.definition.transformations] == [
        "impute", "scale_numeric", "encode_categorical"
    ]
    assert {item.business_case_role for item in plan.definition.outputs} == {
        "training", "validation"
    }

    model_aware = model_aware_autofe_plans(
        plan,
        ["logistic_regression", "random_forest_classifier", "complement_nb"],
    )
    assert [item.provenance["recipe_id"] for item in model_aware] == [
        "scaled_dense", "tree_unscaled", "non_negative"
    ]
    assert len({item.provenance["recipe_hash"] for item in model_aware}) == 3
    repeated = model_aware_autofe_plans(
        plan,
        ["logistic_regression", "random_forest_classifier", "complement_nb"],
    )
    assert [item.provenance["recipe_hash"] for item in repeated] == [
        item.provenance["recipe_hash"] for item in model_aware
    ]
    scaling = {
        item.provenance["recipe_id"]: [
            transform.config.get("method")
            for transform in item.definition.transformations
            if transform.type == "scale_numeric"
        ]
        for item in model_aware
    }
    assert scaling == {
        "scaled_dense": ["standard"],
        "tree_unscaled": [],
        "non_negative": ["minmax"],
    }
    expanded = model_aware_autofe_plans(
        plan,
        ["logistic_regression", "random_forest_classifier", "complement_nb"],
        max_candidates=6,
        numeric_feature_search=True,
    )
    assert [item.provenance["recipe_id"] for item in expanded] == [
        "scaled_dense",
        "tree_unscaled",
        "non_negative",
        "scaled_dense__robust_generated",
        "tree_unscaled__robust_generated",
        "non_negative__robust_generated",
    ]
    enhanced = expanded[3]
    assert enhanced.provenance["recipe_contract"] == {
        "contract_version": "2.0",
        "capability_profile": "scaled_dense",
        "numeric_variant": "robust_generated",
        "numeric_scaling": "standard",
        "winsorization": {"lower_quantile": 0.01, "upper_quantile": 0.99},
        "signed_log_features": True,
        "feature_selector": {"type": "variance_filter", "threshold": 0.0},
    }
    assert [item.type for item in enhanced.definition.transformations] == [
        "impute",
        "winsorize_numeric",
        "math_transform",
        "scale_numeric",
        "encode_categorical",
        "variance_filter",
    ]
    assert expanded[5].provenance["recipe_contract"]["signed_log_features"] is False
    v2 = model_aware_autofe_plans(
        plan,
        ["logistic_regression", "random_forest_classifier", "complement_nb"],
        max_candidates=24,
        numeric_feature_search=True,
        numeric_recipe_search_v2=True,
        numeric_scaling_search=True,
        numeric_scaling_candidates=["standard", "robust", "minmax", "none"],
    )
    v2_ids = [item.provenance["recipe_id"] for item in v2]
    assert v2_ids[:10] == [
        "scaled_dense",
        "tree_unscaled",
        "non_negative",
        "scaled_dense__winsorized",
        "tree_unscaled__winsorized",
        "non_negative__winsorized",
        "scaled_dense__signed_log",
        "tree_unscaled__signed_log",
        "scaled_dense__winsorized_signed_log",
        "tree_unscaled__winsorized_signed_log",
    ]
    assert "scaled_dense__robust" in v2_ids
    assert "scaled_dense__winsorized__minmax" in v2_ids
    assert "scaled_dense__signed_log__none" in v2_ids
    assert len(v2_ids) == len(set(v2_ids)) == 22
    robust = next(item for item in v2 if item.provenance["recipe_id"] == "scaled_dense__robust")
    assert robust.provenance["recipe_contract"]["numeric_scaling"] == "robust"
    assert [
        transform.config.get("method")
        for transform in robust.definition.transformations
        if transform.type == "scale_numeric"
    ] == ["robust"]
    winsor_only = next(
        item for item in v2 if item.provenance["recipe_id"] == "scaled_dense__winsorized"
    )
    assert winsor_only.provenance["recipe_contract"]["signed_log_features"] is False
    assert winsor_only.provenance["recipe_contract"]["winsorization"] is not None


def test_autofe_planner_accepts_parquet_table_function_relation(tmp_path) -> None:
    """Feature Engineering publishes its outputs as a raw read_parquet relation."""
    parquet_path = tmp_path / "fe-training_features.parquet"
    connection = duckdb.connect()
    try:
        connection.execute(
            "COPY (SELECT i AS row_id, CAST(i % 2 AS INTEGER) AS target, "
            "CAST(i AS DOUBLE) AS amount FROM range(100) t(i)) TO ? (FORMAT PARQUET)",
            [str(parquet_path)],
        )
    finally:
        connection.close()

    definition = TrainingDefinition.model_validate({
        **automl_definition(autofe=True),
        "feature_columns": [],
        "feature_selection": "upstream_contract",
    })
    source = SourceRelation(
        sql=f"read_parquet({sql_literal(str(parquet_path))})",
        row_count=100,
    )

    plan = DuckDbAutoFEPlanner(tmp_path).plan(
        training=source,
        validation=None,
        test=None,
        training_definition=definition,
        run_id="run-parquet-relation",
        owner_id="owner",
    )

    assert plan.provenance["profiled_row_count"] == 100
    assert {item["column"] for item in plan.provenance["column_decisions"]} == {"amount"}


def test_autofe_planner_inherits_upstream_row_id_contract(tmp_path) -> None:
    definition = TrainingDefinition.model_validate({
        **automl_definition(autofe=True),
        "feature_columns": [],
        "feature_selection": "upstream_contract",
        "auto_feature_engineering": {
            **automl_definition(autofe=True)["auto_feature_engineering"],
            "row_id_column": "",
        },
    })
    source = SourceRelation(
        sql=(
            "(SELECT 'customer_' || CAST(i AS VARCHAR) AS customer_id, "
            "CAST(i % 2 AS INTEGER) AS target, CAST(i AS DOUBLE) AS amount "
            "FROM range(100) t(i))"
        ),
        row_count=100,
        metadata={"feature_manifest": [{"name": "customer_id", "role": "row_id"}]},
    )

    plan = DuckDbAutoFEPlanner(tmp_path).plan(
        training=source,
        validation=source,
        test=None,
        training_definition=definition,
        run_id="run-inherited-row-id",
        owner_id="owner",
    )

    assert plan.definition.row_id_column == "customer_id"
    assert plan.provenance["inherited_row_id_column"] == "customer_id"
    assert "customer_id" not in plan.definition.feature_columns


def test_automl_handler_applies_autofe_before_model_search(tmp_path) -> None:
    calls = []

    class Engine:
        def execute(self, definition, training, validation, **kwargs):
            assert validation is not None
            assert definition.feature_selection == "explicit"
            assert "row_id" not in definition.feature_columns
            assert "target" not in definition.feature_columns
            assert "amount__scaled" in definition.feature_columns
            assert any(name.startswith("segment__") for name in definition.feature_columns)
            calls.append(definition)
            is_candidate = definition.optimization.mode == "automl"
            optimization = {
                "mode": definition.optimization.mode,
                "primary_metric": "roc_auc",
                "validation_strategy": "holdout",
                "trial_count": definition.optimization.max_trials if is_candidate else 1,
                "best_score": 0.91 if is_candidate else None,
                "best_algorithm": "sgd_classifier",
                "best_parameters": {},
                "trials": [],
            }
            return SimpleNamespace(
                input_row_count=training.row_count,
                processed_row_count=training.row_count,
                output_row_count=1,
                warnings=[],
                output_manifest=[
                    {
                        "output_id": "model",
                        "artifact_type": "model_version",
                        "materialization": "temporary",
                        "algorithm": "sgd_classifier",
                        "metrics": {"optimization": optimization},
                        "training_config": {},
                    },
                    {
                        "output_id": "training_metrics",
                        "artifact_type": "metrics",
                        "materialization": "temporary",
                        "metrics": {"optimization": optimization},
                    },
                ],
            )

    step_payload = automl_workflow()
    handler_definition = {
        **automl_definition(autofe=True),
        "feature_columns": [],
        "feature_selection": "upstream_contract",
    }
    handler_definition["optimization"] = {
        **handler_definition["optimization"],
        "candidate_algorithms": ["sgd_classifier", "random_forest_classifier"],
    }
    handler_definition["auto_feature_engineering"] = {
        **handler_definition["auto_feature_engineering"],
        "max_recipe_candidates": 1,
    }
    step_payload["steps"][1]["config"]["definition"] = handler_definition
    step_payload["steps"][1]["inputs"].append({
        "port_id": "validation",
        "source": {"step_id": "fe_1", "port_id": "validation"},
    })
    step_payload["steps"][1]["inputs"].append({
        "port_id": "test",
        "source": {"step_id": "fe_1", "port_id": "test"},
    })
    step = WorkflowStep.model_validate(step_payload["steps"][1])
    source = SourceRelation(
        sql=(
            "(SELECT i AS row_id, CAST(i % 2 AS INTEGER) AS target, "
            "CAST(i AS DOUBLE) AS amount, "
            "CASE WHEN i % 3 = 0 THEN 'a' ELSE 'b' END AS segment "
            "FROM range(100) t(i))"
        ),
        row_count=100,
        metadata={"scope": "full"},
    )
    feature_engine = DuckDbFeatureEngineeringEngine(repository_root=tmp_path)
    validation_source = SourceRelation(
        sql=(
            "(SELECT i + 500 AS row_id, CAST(i % 2 AS INTEGER) AS target, "
            "CAST(i AS DOUBLE) AS amount, "
            "CASE WHEN i % 3 = 0 THEN 'a' ELSE 'b' END AS segment "
            "FROM range(20) t(i))"
        ),
        row_count=20,
        metadata={"scope": "full"},
    )
    test_source = SourceRelation(
        sql=(
            "(SELECT i + 1000 AS row_id, CAST(i % 2 AS INTEGER) AS target, "
            "CAST(i AS DOUBLE) AS amount, "
            "CASE WHEN i % 3 = 0 THEN 'new_segment' ELSE 'b' END AS segment "
            "FROM range(20) t(i))"
        ),
        row_count=20,
        metadata={"scope": "full"},
    )
    result = AutoMLStepHandler(
        Engine(),
        feature_engine=feature_engine,
        planner=DuckDbAutoFEPlanner(tmp_path),
    ).execute(
        step,
        StepExecutionContext(
            run_id="run-autofe",
            owner_id="owner",
            is_dry_run=True,
            upstream_relations={
                ("de_1", "dataset"): source,
                ("fe_1", "validation"): validation_source,
                ("fe_1", "test"): test_source,
            },
        ),
    )

    assert result.output_row_count == 1
    assert result.artifact_output_ids["fitted_transform"] == "fitted_transform"
    assert result.relation_output_ids == {"test": "autofe_test"}
    transformed_test = next(item for item in result.output_manifest if item["output_id"] == "autofe_test")
    assert transformed_test["row_count"] == 20
    assert any(item["name"] == "amount__scaled" for item in transformed_test["feature_manifest"])
    model = next(item for item in result.output_manifest if item["output_id"] == "model")
    assert len(calls) == 2
    assert calls[0].auto_feature_engineering.enabled is True
    assert calls[0].optimization.mode == "automl"
    assert calls[1].auto_feature_engineering.enabled is False
    assert calls[1].optimization.mode == "single"
    assert model["auto_feature_engineering"]["recipe_search_mode"] == "joint_model_aware_holdout"
    assert model["auto_feature_engineering"]["joint_study"]["selected_recipe_id"] == "scaled_dense"
    assert model["auto_feature_engineering"]["joint_study"]["skipped_algorithms"] == [
        "random_forest_classifier"
    ]
    assert any("random_forest_classifier" in warning for warning in result.warnings)


def test_integrated_autofe_and_automl_train_a_real_classification_model(tmp_path) -> None:
    step_payload = automl_workflow()
    definition = {
        **automl_definition(autofe=True),
        "feature_columns": [],
        "feature_selection": "upstream_contract",
    }
    definition["optimization"] = {
        **definition["optimization"],
        "validation_strategy": "auto",
        "max_trials": 5,
    }
    definition["auto_feature_engineering"] = {
        **definition["auto_feature_engineering"],
        "numeric_feature_search": True,
        "numeric_recipe_search_v2": True,
        "numeric_scaling_search": True,
        "numeric_scaling_candidates": ["standard", "robust", "minmax", "none"],
        "max_recipe_candidates": 3,
        "two_phase_search_enabled": True,
        "exploration_trials_per_recipe": 1,
        "exploration_time_fraction": 0.35,
        "promotion_top_k": 1,
    }
    step_payload["steps"][1]["config"]["definition"] = definition
    step = WorkflowStep.model_validate(step_payload["steps"][1])
    source = SourceRelation(
        sql=(
            "(SELECT i AS row_id, CAST(i % 2 AS INTEGER) AS target, "
            "CAST(i AS DOUBLE) AS amount, "
            "CASE WHEN i % 4 < 2 THEN 'retail' ELSE 'business' END AS segment "
            "FROM range(120) t(i))"
        ),
        row_count=120,
        metadata={"scope": "full"},
    )
    feature_engine = DuckDbFeatureEngineeringEngine(repository_root=tmp_path)

    result = AutoMLStepHandler(
        SklearnTrainingEngine(repository_root=tmp_path),
        feature_engine=feature_engine,
        planner=DuckDbAutoFEPlanner(tmp_path),
    ).execute(
        step,
        StepExecutionContext(
            run_id="run-real-autofe",
            owner_id="owner",
            is_dry_run=True,
            upstream_relations={("de_1", "dataset"): source},
        ),
    )

    model = next(item for item in result.output_manifest if item["output_id"] == "model")
    assert model["algorithm"] == "sgd_classifier"
    assert model["metrics"]["optimization"]["trial_count"] == 1
    assert model["auto_feature_engineering"]["profiled_row_count"] == 120
    assert model["auto_feature_engineering"]["resolved_feature_count"] >= 3
    study = model["auto_feature_engineering"]["joint_study"]
    assert study["recipe_candidate_count"] == 3
    assert study["configured_recipe_candidate_count"] == 3
    assert study["generated_recipe_candidate_count"] == 16
    assert study["skipped_recipe_count"] == 13
    executed = [item for item in study["candidates"] if item["status"] != "skipped"]
    skipped = [item for item in study["candidates"] if item["status"] == "skipped"]
    assert sum(item["trial_count"] for item in executed) == 5
    assert study["scheduler"] == {
        "mode": "two_phase",
        "exploration_trials_per_recipe": 1,
        "exploration_time_fraction": 0.35,
        "promotion_top_k": 1,
        "promoted_recipe_ids": [
            next(item["recipe_id"] for item in executed if item["status"] == "promoted")
        ],
        "allocated_exploration_trials": 3,
        "allocated_exploration_timeout_seconds": 30,
        "allocated_deepening_trials": 2,
        "allocated_deepening_timeout_seconds": 30,
        "completed_trials": 5,
    }
    assert [item["status"] for item in executed].count("promoted") == 1
    assert [item["status"] for item in executed].count("pruned") == 2
    promoted = next(item for item in executed if item["status"] == "promoted")
    assert [phase["phase"] for phase in promoted["phases"]] == ["exploration", "deepening"]
    assert [phase["allocated_trial_budget"] for phase in promoted["phases"]] == [1, 2]
    assert [item["recipe_contract"]["numeric_variant"] for item in executed] == [
        "baseline", "winsorized", "signed_log",
    ]
    assert all(item["reason"] == "explicit max_recipe_candidates cap" for item in skipped)
    assert all(item["recipe_contract"] for item in skipped)
    assert executed[2]["resolved_feature_count"] > executed[0]["resolved_feature_count"]


def test_automl_incremental_winner_refits_balanced_class_weight(tmp_path) -> None:
    step_payload = automl_workflow()
    definition = {
        **automl_definition(autofe=True),
        "feature_columns": [],
        "feature_selection": "upstream_contract",
        "epochs": 2,
    }
    definition["optimization"] = {
        **definition["optimization"],
        "validation_strategy": "auto",
        "max_trials": 1,
        "candidate_algorithms": ["sgd_classifier"],
        "search_space": {
            "sgd_classifier__class_weight": {
                "kind": "categorical",
                "values": ["balanced"],
            },
        },
    }
    definition["auto_feature_engineering"] = {
        **definition["auto_feature_engineering"],
        "max_recipe_candidates": 1,
        "numeric_feature_search": False,
    }
    step_payload["steps"][1]["config"]["definition"] = definition
    source = SourceRelation(
        sql=(
            "(SELECT i AS row_id, CAST(i < 90 AS INTEGER) AS target, "
            "CAST(i AS DOUBLE) AS amount FROM range(120) t(i))"
        ),
        row_count=120,
        metadata={"scope": "full"},
    )

    result = AutoMLStepHandler(
        SklearnTrainingEngine(repository_root=tmp_path),
        feature_engine=DuckDbFeatureEngineeringEngine(repository_root=tmp_path),
        planner=DuckDbAutoFEPlanner(tmp_path),
    ).execute(
        WorkflowStep.model_validate(step_payload["steps"][1]),
        StepExecutionContext(
            run_id="run-balanced-incremental-winner",
            owner_id="owner",
            is_dry_run=True,
            upstream_relations={("de_1", "dataset"): source},
        ),
    )

    model = next(item for item in result.output_manifest if item["output_id"] == "model")
    resolution = model["metrics"]["optimization"]["parameter_resolution"]
    assert model["algorithm"] == "sgd_classifier"
    assert resolution["kind"] == "balanced_class_weight"
    assert resolution["data_scope"] == "full_training"
    assert sum(resolution["class_counts"].values()) == resolution["row_count"]
    assert model["training_config"]["resolved_parameters"]["class_weight"] != "balanced"


def test_joint_autofe_compares_model_specific_recipes_on_one_holdout(tmp_path) -> None:
    step_payload = automl_workflow()
    definition = {
        **automl_definition(autofe=True),
        "problem_type": "regression",
        "algorithm": "ridge_regression",
        "parameters": {},
        "feature_columns": [],
        "feature_selection": "upstream_contract",
    }
    definition["optimization"] = {
        **definition["optimization"],
        "validation_strategy": "auto",
        "primary_metric": "neg_root_mean_squared_error",
        "max_trials": 4,
        "candidate_algorithms": ["ridge_regression", "decision_tree_regressor"],
    }
    step_payload["steps"][1]["config"]["definition"] = definition
    step = WorkflowStep.model_validate(step_payload["steps"][1])
    source = SourceRelation(
        sql=(
            "(SELECT i AS row_id, CAST(i AS DOUBLE) AS amount, "
            "CASE WHEN i % 3 = 0 THEN 'a' ELSE 'b' END AS segment, "
            "power(CAST(i AS DOUBLE), 2) + sin(CAST(i AS DOUBLE)) AS target "
            "FROM range(160) t(i))"
        ),
        row_count=160,
        metadata={"scope": "full"},
    )
    feature_engine = DuckDbFeatureEngineeringEngine(repository_root=tmp_path)

    result = AutoMLStepHandler(
        SklearnTrainingEngine(repository_root=tmp_path),
        feature_engine=feature_engine,
        planner=DuckDbAutoFEPlanner(tmp_path),
    ).execute(
        step,
        StepExecutionContext(
            run_id="run-joint-autofe",
            owner_id="owner",
            is_dry_run=True,
            upstream_relations={("de_1", "dataset"): source},
        ),
    )

    model = next(item for item in result.output_manifest if item["output_id"] == "model")
    study = model["auto_feature_engineering"]["joint_study"]
    assert study["recipe_candidate_count"] == 2
    assert study["successful_recipe_count"] == 2
    assert {item["recipe_id"] for item in study["candidates"]} == {
        "scaled_dense", "tree_unscaled"
    }
    assert sum(item["trial_count"] for item in study["candidates"]) == 4
    assert study["selected_recipe_id"] in {"scaled_dense", "tree_unscaled"}
    assert study["selected_algorithm"] in {
        "ridge_regression", "decision_tree_regressor"
    }


def test_autofe_cross_validation_plan_is_deterministic_disjoint_and_full_scope(tmp_path) -> None:
    payload = {
        **automl_definition(autofe=True),
        "feature_columns": [],
        "feature_selection": "upstream_contract",
    }
    payload["optimization"] = {
        **payload["optimization"],
        "validation_strategy": "cross_validation",
        "cv_folds": 4,
    }
    definition = TrainingDefinition.model_validate(payload)
    source = SourceRelation(
        sql=(
            "(SELECT i AS row_id, CAST(i % 2 AS INTEGER) AS target, "
            "CAST(i AS DOUBLE) AS amount FROM range(120) t(i))"
        ),
        row_count=120,
        metadata={"scope": "full"},
    )
    planner = DuckDbAutoFEPlanner(tmp_path)

    first = planner.cross_validation_plan(
        training=source,
        training_definition=definition,
        run_id="cv-plan-first",
        owner_id="owner",
    )
    second = planner.cross_validation_plan(
        training=source,
        training_definition=definition,
        run_id="cv-plan-second",
        owner_id="owner",
    )

    assert first.provenance == second.provenance
    assert first.provenance["data_scope"] == "full"
    assert first.provenance["fold_assignment_stage"] == "raw_before_feature_engineering"
    assert sum(item.validation.row_count for item in first.folds) == 120
    connection = duckdb.connect()
    try:
        for left, right in zip(first.folds, second.folds, strict=True):
            first_ids = {
                row[0] for row in connection.execute(
                    f"SELECT row_id FROM {left.validation.sql}"
                ).fetchall()
            }
            second_ids = {
                row[0] for row in connection.execute(
                    f"SELECT row_id FROM {right.validation.sql}"
                ).fetchall()
            }
            training_ids = {
                row[0] for row in connection.execute(
                    f"SELECT row_id FROM {left.training.sql}"
                ).fetchall()
            }
            assert first_ids == second_ids
            assert first_ids.isdisjoint(training_ids)
            assert len(first_ids | training_ids) == 120
    finally:
        connection.close()


def test_integrated_autofe_runs_fold_local_cross_validation_and_refits_winner(tmp_path) -> None:
    step_payload = automl_workflow()
    definition = {
        **automl_definition(autofe=True),
        "feature_columns": [],
        "feature_selection": "upstream_contract",
    }
    definition["optimization"] = {
        **definition["optimization"],
        "validation_strategy": "cross_validation",
        "cv_folds": 3,
        "max_trials": 2,
        "candidate_algorithms": ["logistic_regression"],
    }
    definition["auto_feature_engineering"] = {
        **definition["auto_feature_engineering"],
        "max_recipe_candidates": 1,
    }
    step_payload["steps"][1]["config"]["definition"] = definition
    step = WorkflowStep.model_validate(step_payload["steps"][1])
    source = SourceRelation(
        sql=(
            "(SELECT i AS row_id, CAST(i % 2 AS INTEGER) AS target, "
            "CAST(i AS DOUBLE) + CASE WHEN i % 2 = 0 THEN 25 ELSE 0 END AS amount, "
            "CASE WHEN i % 4 < 2 THEN 'retail' ELSE 'business' END AS segment "
            "FROM range(150) t(i))"
        ),
        row_count=150,
        metadata={"scope": "full"},
    )
    feature_engine = DuckDbFeatureEngineeringEngine(repository_root=tmp_path)

    result = AutoMLStepHandler(
        SklearnTrainingEngine(repository_root=tmp_path),
        feature_engine=feature_engine,
        planner=DuckDbAutoFEPlanner(tmp_path),
    ).execute(
        step,
        StepExecutionContext(
            run_id="run-fold-local-autofe",
            owner_id="owner",
            is_dry_run=True,
            upstream_relations={("de_1", "dataset"): source},
        ),
    )

    model = next(item for item in result.output_manifest if item["output_id"] == "model")
    study = model["auto_feature_engineering"]["joint_study"]
    assert study["mode"] == "joint_model_aware_fold_local_cv"
    assert study["cross_validation"]["fold_count"] == 3
    assert study["cross_validation"]["planned_row_count"] == 150
    assert study["candidates"][0]["optimization"]["validation_strategy"] == "cross_validation"
    assert len(study["candidates"][0]["optimization"]["trials"][0]["fold_scores"]) == 3
    assert len(study["candidates"][0]["fold_local_feature_counts"]) == 3
    assert study["candidates"][0]["fold_cache"] == {
        "scope": "run_recipe",
        "recipe_hash": study["candidates"][0]["fold_cache"]["recipe_hash"],
        "fold_count": 3,
        "miss_count": 3,
        "hit_count": 3,
    }
    assert len(study["candidates"][0]["oof_summaries"]) == 2
    for trial in study["candidates"][0]["optimization"]["trials"]:
        assert trial["oof_summary"]["prediction_count"] == 150
        assert trial["oof_summary"]["coverage"] == 1.0
        assert trial["oof_summary"]["predictions_persisted"] is False
    assert study["candidates"][0]["selected_oof_summary"]["coverage"] == 1.0
    assert model["training_config"]["auto_feature_engineering"]["joint_study"]["best_score"] is not None


def test_fold_local_autofe_rejects_globally_fitted_human_fe_input(tmp_path) -> None:
    step_payload = automl_workflow()
    definition = {
        **automl_definition(autofe=True),
        "feature_columns": [],
        "feature_selection": "upstream_contract",
    }
    definition["optimization"] = {
        **definition["optimization"],
        "validation_strategy": "cross_validation",
    }
    step_payload["steps"][1]["config"]["definition"] = definition
    step = WorkflowStep.model_validate(step_payload["steps"][1])
    source = SourceRelation(
        sql="(SELECT i AS row_id, i % 2 AS target, i::DOUBLE AS amount FROM range(20) t(i))",
        row_count=20,
        metadata={"fitted_transform_count": 1},
    )

    with pytest.raises(ValueError, match="requires pre-FE training data"):
        AutoMLStepHandler(
            SklearnTrainingEngine(repository_root=tmp_path),
            feature_engine=DuckDbFeatureEngineeringEngine(repository_root=tmp_path),
            planner=DuckDbAutoFEPlanner(tmp_path),
        ).execute(
            step,
            StepExecutionContext(
                run_id="run-reject-global-fe",
                owner_id="owner",
                is_dry_run=True,
                upstream_relations={("de_1", "dataset"): source},
            ),
        )


def test_integrated_autofe_fold_local_cv_supports_regression(tmp_path) -> None:
    step_payload = automl_workflow()
    definition = {
        **automl_definition(autofe=True),
        "problem_type": "regression",
        "algorithm": "ridge_regression",
        "parameters": {},
        "feature_columns": [],
        "feature_selection": "upstream_contract",
    }
    definition["optimization"] = {
        **definition["optimization"],
        "validation_strategy": "cross_validation",
        "primary_metric": "neg_root_mean_squared_error",
        "cv_folds": 3,
        "max_trials": 2,
        "candidate_algorithms": ["ridge_regression"],
    }
    definition["auto_feature_engineering"] = {
        **definition["auto_feature_engineering"],
        "max_recipe_candidates": 2,
        "numeric_feature_search": True,
        "numeric_recipe_search_v2": True,
    }
    step_payload["steps"][1]["config"]["definition"] = definition
    source = SourceRelation(
        sql=(
            "(SELECT i AS row_id, CAST(i AS DOUBLE) AS amount, "
            "CASE WHEN i % 3 = 0 THEN 'north' ELSE 'south' END AS region, "
            "2.5 * CAST(i AS DOUBLE) + 10 AS target FROM range(120) t(i))"
        ),
        row_count=120,
        metadata={"scope": "full"},
    )

    result = AutoMLStepHandler(
        SklearnTrainingEngine(repository_root=tmp_path),
        feature_engine=DuckDbFeatureEngineeringEngine(repository_root=tmp_path),
        planner=DuckDbAutoFEPlanner(tmp_path),
    ).execute(
        WorkflowStep.model_validate(step_payload["steps"][1]),
        StepExecutionContext(
            run_id="run-fold-local-regression",
            owner_id="owner",
            is_dry_run=True,
            upstream_relations={("de_1", "dataset"): source},
        ),
    )

    model = next(item for item in result.output_manifest if item["output_id"] == "model")
    study = model["auto_feature_engineering"]["joint_study"]
    assert model["problem_type"] == "regression"
    assert study["cross_validation"]["strategy"] == "kfold"
    assert len(study["candidates"][0]["optimization"]["trials"][0]["fold_scores"]) == 3
    assert study["candidates"][1]["recipe_contract"]["numeric_variant"] == "winsorized"
    assert len(study["candidates"][1]["fold_local_feature_counts"]) == 3


def test_fold_local_fitted_state_does_not_see_validation_only_changes(tmp_path) -> None:
    step_payload = automl_workflow()
    definition_payload = {
        **automl_definition(autofe=True),
        "feature_columns": [],
        "feature_selection": "upstream_contract",
    }
    definition_payload["optimization"] = {
        **definition_payload["optimization"],
        "validation_strategy": "cross_validation",
        "cv_folds": 3,
        "max_trials": 1,
        "candidate_algorithms": ["logistic_regression"],
    }
    definition_payload["auto_feature_engineering"] = {
        **definition_payload["auto_feature_engineering"],
        "max_recipe_candidates": 1,
    }
    step_payload["steps"][1]["config"]["definition"] = definition_payload
    definition = TrainingDefinition.model_validate(definition_payload)
    base = SourceRelation(
        sql=(
            "(SELECT i AS row_id, CAST(i % 2 AS INTEGER) AS target, "
            "CAST(i AS DOUBLE) AS amount FROM range(90) t(i))"
        ),
        row_count=90,
        metadata={"scope": "full"},
    )
    planner = DuckDbAutoFEPlanner(tmp_path)
    cv_plan = planner.cross_validation_plan(
        training=base,
        training_definition=definition,
        run_id="leakage-plan",
        owner_id="owner",
    )
    connection = duckdb.connect()
    try:
        validation_ids = [
            int(row[0]) for row in connection.execute(
                f"SELECT row_id FROM {cv_plan.folds[0].validation.sql}"
            ).fetchall()
        ]
    finally:
        connection.close()
    changed = SourceRelation(
        sql=(
            "(SELECT i AS row_id, CAST(i % 2 AS INTEGER) AS target, "
            f"CASE WHEN i IN ({', '.join(map(str, validation_ids))}) "
            "THEN CAST(i AS DOUBLE) + 100000 ELSE CAST(i AS DOUBLE) END AS amount "
            "FROM range(90) t(i))"
        ),
        row_count=90,
        metadata={"scope": "full"},
    )

    def run(source: SourceRelation, run_id: str) -> dict:
        result = AutoMLStepHandler(
            SklearnTrainingEngine(repository_root=tmp_path),
            feature_engine=DuckDbFeatureEngineeringEngine(repository_root=tmp_path),
            planner=DuckDbAutoFEPlanner(tmp_path),
        ).execute(
            WorkflowStep.model_validate(step_payload["steps"][1]),
            StepExecutionContext(
                run_id=run_id,
                owner_id="owner",
                is_dry_run=True,
                upstream_relations={("de_1", "dataset"): source},
            ),
        )
        model = next(item for item in result.output_manifest if item["output_id"] == "model")
        return model["auto_feature_engineering"]["joint_study"]["candidates"][0]

    original_candidate = run(base, "leakage-original")
    changed_candidate = run(changed, "leakage-changed")
    original_states = {
        item["fold"]: item["fitted_state_signature"]
        for item in original_candidate["fold_local_feature_counts"]
    }
    changed_states = {
        item["fold"]: item["fitted_state_signature"]
        for item in changed_candidate["fold_local_feature_counts"]
    }

    assert original_states[0] == changed_states[0]
    assert any(original_states[fold] != changed_states[fold] for fold in (1, 2))
