"""Portable Estates Sell Prices demo manifest.

The manifest intentionally contains no installation-specific UUIDs. Runtime
artifacts such as fitted transforms, models, predictions, and reports must be
created by executing the lifecycle pipelines in the target installation.
"""

from __future__ import annotations

from typing import Any


BUSINESS_CASE = {
    "name": "Estates Sell Prices",
    "description": "Estimate residential property sale prices and demonstrate the full ML lifecycle.",
    "problem_type": "regression",
    "status": "draft",
    "primary_metric": "MAPE",
    "target_column": "sale_price_pln",
    "business_goal": "Build a reproducible property valuation workflow from training through monitoring.",
    "success_criteria": "Evaluate full-scope holdout and monitoring metrics with traceable lineage.",
}

DATASETS = (
    {
        "key": "training",
        "name": "sale-prices",
        "filename": "regression-example.csv",
        "role": "source",
        "description": "Deterministic 10k-row estates training dataset.",
        "primary_key_column": "property_id",
        "target_column": "sale_price_pln",
    },
    {
        "key": "scoring",
        "name": "Estates Sell Prices - Scoring Data",
        "filename": "estates-sale-prices-batch-scoring-100k.parquet",
        "role": "scoring_input",
        "description": "Deterministic 100k-row estates batch-scoring cohort without target values.",
        "primary_key_column": "property_id",
        "target_column": "",
    },
    {
        "key": "actuals",
        "name": "Estates Sell Prices - Scoring Actuals",
        "filename": "estates-sale-prices-batch-scoring-100k-actuals.parquet",
        "role": "monitoring_actuals",
        "description": "Delayed sale-price outcomes for the deterministic scoring cohort.",
        "primary_key_column": "property_id",
        "target_column": "sale_price_pln",
    },
)


FEATURE_COLUMNS = [
    "region", "district_score", "property_type", "floor_area_sqm", "rooms",
    "building_age_years", "floor_number", "has_elevator",
    "distance_to_center_km", "distance_to_transit_m", "school_rating",
    "energy_class", "condition_level", "heating_type", "parking_type",
    "listing_channel", "days_on_market",
]


def build_automl_definition(training_logical_id: str) -> dict[str, Any]:
    """Build the executable AutoFEML draft using the target installation's dataset ID."""
    selected_columns = [*FEATURE_COLUMNS, "sale_price_pln", "property_id"]
    casts = {
        "property_id": "VARCHAR",
        "region": "VARCHAR",
        "district_score": "INTEGER",
        "property_type": "VARCHAR",
        "floor_area_sqm": "DOUBLE",
        "rooms": "INTEGER",
        "building_age_years": "INTEGER",
        "floor_number": "INTEGER",
        "has_elevator": "BOOLEAN",
        "distance_to_center_km": "DOUBLE",
        "distance_to_transit_m": "DOUBLE",
        "school_rating": "INTEGER",
        "energy_class": "VARCHAR",
        "condition_level": "VARCHAR",
        "heating_type": "VARCHAR",
        "parking_type": "VARCHAR",
        "listing_channel": "VARCHAR",
        "days_on_market": "INTEGER",
        "sale_price_pln": "DOUBLE",
    }
    data_contract = [
        {
            "name": name,
            "type": casts[name],
            "nullable": name != "property_id",
            "unique": name == "property_id",
            "policy": "fail",
        }
        for name in selected_columns
    ]
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
                    "contract_version": "1.0",
                    "inputs": [{
                        "input_id": "source_1",
                        "dataset_id": training_logical_id,
                        "output_port_id": "out",
                        "version_policy": "latest",
                    }],
                    "steps": [
                        {
                            "step_id": "select_training_columns",
                            "type": "select_columns",
                            "inputs": [{
                                "port_id": "input",
                                "source": {"node_id": "source_1", "port_id": "out"},
                            }],
                            "output_port_id": "out",
                            "config": {"columns": selected_columns},
                        },
                        {
                            "step_id": "cast_training_columns",
                            "type": "cast_columns",
                            "inputs": [{
                                "port_id": "input",
                                "source": {"node_id": "select_training_columns", "port_id": "out"},
                            }],
                            "output_port_id": "out",
                            "config": {"casts": casts},
                        },
                    ],
                    "outputs": [{
                        "output_id": "result",
                        "input": {"node_id": "cast_training_columns", "port_id": "out"},
                        "materialization": "dataset",
                        "write_mode": "replace",
                        "dataset_name": "Estates Sell Prices - AutoFEML - Input",
                        "business_case_role": "source",
                        "data_contract": {
                            "columns": data_contract,
                            "schema_drift_policy": "fail",
                            "allow_unexpected_columns": False,
                        },
                    }],
                    "parameters": {},
                }},
            },
            {
                "step_id": "fe_1",
                "name": "Evaluation Split",
                "type": "feature_engineering",
                "inputs": [{
                    "port_id": "training",
                    "source": {"step_id": "de_1", "port_id": "dataset"},
                }],
                "output_port_id": "training",
                "additional_output_port_ids": ["validation", "test", "fitted_transform"],
                "config": {"definition": {
                    "contract_version": "1.0",
                    "mode": "fit_transform",
                    "inputs": [{
                        "input_id": "training",
                        "role": "training",
                        "dataset_id": "",
                        "version_policy": "latest",
                    }],
                    "feature_columns": FEATURE_COLUMNS,
                    "target_column": "sale_price_pln",
                    "row_id_column": "property_id",
                    "group_column": "",
                    "event_time_column": "",
                    "transformations": [],
                    "outputs": [
                        {
                            "output_id": "training_features",
                            "input_id": "training",
                            "dataset_name": "Estates Sell Prices - AutoFEML - Train",
                            "business_case_role": "training",
                        },
                        {
                            "output_id": "validation_features",
                            "input_id": "validation",
                            "dataset_name": "Estates Sell Prices - AutoFEML - Validate",
                            "business_case_role": "validation",
                        },
                        {
                            "output_id": "test_features",
                            "input_id": "test",
                            "dataset_name": "Estates Sell Prices - AutoFEML - Test",
                            "business_case_role": "test",
                        },
                    ],
                    "evaluation": {
                        "split_strategy": "random",
                        "validation_size": 0.1,
                        "test_size": 0.2,
                        "seed": 42,
                        "stratify_column": "",
                        "group_column": "",
                        "time_column": "",
                        "cross_validation": {
                            "enabled": True,
                            "strategy": "kfold",
                            "folds": 5,
                            "shuffle": True,
                            "seed": 42,
                        },
                    },
                }},
            },
            {
                "step_id": "automl_1",
                "name": "AutoML and AutoFE",
                "type": "automl",
                "inputs": [
                    {"port_id": "training", "source": {"step_id": "fe_1", "port_id": "training"}},
                    {"port_id": "validation", "source": {"step_id": "fe_1", "port_id": "validation"}},
                    {"port_id": "test", "source": {"step_id": "fe_1", "port_id": "test"}},
                    {"port_id": "fitted_transform", "source": {"step_id": "fe_1", "port_id": "fitted_transform"}},
                ],
                "output_port_id": "model",
                "additional_output_port_ids": ["metrics", "test"],
                "config": {"definition": {
                    "contract_version": "1.0",
                    "model_name": "Estates Sell Prices - AutoFEML - Model",
                    "problem_type": "regression",
                    "target_column": "sale_price_pln",
                    "feature_columns": FEATURE_COLUMNS,
                    "feature_selection": "upstream_contract",
                    "algorithm": "ridge_regression",
                    "parameters": {"alpha": 1.0, "fit_intercept": True, "positive": False},
                    "random_seed": 42,
                    "batch_size": 10_000,
                    "epochs": 50,
                    "early_stopping": False,
                    "early_stopping_patience": 5,
                    "early_stopping_min_delta": 0.0001,
                    "resource_limits": {"max_memory_mb": 4096, "max_parallel_jobs": 1},
                    "optimization": {
                        "mode": "automl",
                        "primary_metric": "neg_mean_absolute_error",
                        "validation_strategy": "cross_validation",
                        "cv_folds": 5,
                        "max_trials": 24,
                        "timeout_seconds": 900,
                        "candidate_algorithms": [
                            "ridge_regression", "elastic_net_regression",
                            "random_forest_regressor", "extra_trees_regressor",
                            "hist_gradient_boosting_regressor",
                        ],
                        "search_space": {},
                    },
                    "auto_feature_engineering": {
                        "enabled": True,
                        "strategy": "balanced",
                        "joint_search_enabled": True,
                        "max_generated_features": 64,
                        "max_interaction_features": 12,
                        "max_recipe_candidates": 8,
                        "exploration_trials_per_recipe": 2,
                        "numeric_scaling": "standard",
                        "numeric_interactions": True,
                        "add_missing_indicators": True,
                        "detect_identifier_columns": True,
                        "max_one_hot_categories": 32,
                        "min_category_frequency": 2,
                    },
                }},
            },
            {
                "step_id": "scoring_1",
                "name": "Holdout Test Scoring",
                "type": "scoring",
                "inputs": [
                    {"port_id": "data", "source": {"step_id": "automl_1", "port_id": "test"}},
                    {"port_id": "model", "source": {"step_id": "automl_1", "port_id": "model"}},
                ],
                "output_port_id": "predictions",
                "additional_output_port_ids": [],
                "config": {"definition": {
                    "contract_version": "1.0",
                    "purpose": "test",
                    "model_artifact_id": "",
                    "row_id_column": "property_id",
                    "target_column": "sale_price_pln",
                    "prediction_column": "prediction",
                    "dataset_name": "Estates Sell Prices - AutoFEML - Test Scoring Results",
                    "report_name": "Estates Sell Prices - AutoFEML - Test Scoring Report",
                    "batch_size": 10_000,
                }},
            },
        ],
        "outputs": [{
            "output_id": "result",
            "source": {"step_id": "scoring_1", "port_id": "predictions"},
        }],
        "parameters": {"template": "automl", "bootstrap_manifest_version": "1.0"},
    }


PIPELINE = {
    "name": "Estates Sell Prices - AutoFEML",
    "description": "Portable AutoML and AutoFE training workflow for the Estates demo.",
    "pipeline_type": "automl",
}
