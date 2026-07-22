"""Stable scenario contract used by the numbered Example 01 notebooks.

The module contains fixed pipeline-definition builders. User-facing resource
names stay explicit in the notebooks and platform operations go through
``MLAppClient``.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from examples.estates_bootstrap_manifest import build_automl_definition
from ml_app_client import PipelineRun


SCENARIO_VERSION = "1.0"
SCENARIO_TAGS = ["example01", "estates", "deterministic"]


def data_file(filename: str) -> Path:
    path = Path(__file__).resolve().parent / "data" / filename
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def build_training_definition(
    training_logical_id: str,
    *,
    model_name: str,
    output_name_prefix: str,
) -> dict[str, Any]:
    """Return the fixed, tutorial-sized full-scope AutoML workflow."""
    definition = build_automl_definition(
        training_logical_id,
        asset_name_prefix=output_name_prefix,
        model_name=model_name,
        cv_folds=3,
        max_trials=6,
        timeout_seconds=600,
        definition_parameters={
            "example_id": "Example01",
            "example_contract_version": SCENARIO_VERSION,
        },
    )
    automl = next(step for step in definition["steps"] if step["type"] == "automl")
    auto_fe = automl["config"]["definition"]["auto_feature_engineering"]
    auto_fe["max_recipe_candidates"] = 3
    auto_fe["exploration_trials_per_recipe"] = 1
    return definition


def build_batch_scoring_definition(
    model: Mapping[str, Any],
    scoring_logical_id: str,
    *,
    output_name_prefix: str,
) -> dict[str, Any]:
    """Build a strict batch workflow from one immutable training bundle."""
    source_de = deepcopy(dict(model.get("data_engineering_definition") or {}))
    source_fe = deepcopy(dict(model.get("feature_engineering_definition") or {}))
    target_column = str(model.get("target_column") or "sale_price_pln")
    if not source_de.get("inputs") or not source_de.get("outputs"):
        raise ValueError("The selected model has no reusable Data Engineering definition")
    unsupported = [
        str(step.get("type"))
        for step in source_de.get("steps") or []
        if step.get("type") not in {"select_columns", "cast_columns"}
    ]
    if unsupported:
        raise ValueError(
            "Example01 only reuses select/cast Data Engineering operations for scoring; "
            f"unsupported operations: {', '.join(unsupported)}"
        )

    old_input_id = str(source_de["inputs"][0]["input_id"])
    source_de["inputs"] = [{
        **source_de["inputs"][0],
        "input_id": "scoring_input",
        "dataset_id": scoring_logical_id,
        "version_policy": "latest",
    }]
    for step in source_de.get("steps") or []:
        for input_port in step.get("inputs") or []:
            source = input_port.get("source") or {}
            if source.get("node_id") == old_input_id:
                source["node_id"] = "scoring_input"
        config = step.get("config") or {}
        if step.get("type") == "select_columns":
            config["columns"] = [
                column for column in config.get("columns") or []
                if column != target_column
            ]
        elif step.get("type") == "cast_columns":
            config["casts"] = {
                column: value for column, value in (config.get("casts") or {}).items()
                if column != target_column
            }
    output = source_de["outputs"][0]
    contract = output.get("data_contract") or {}
    if contract:
        contract["columns"] = [
            column for column in contract.get("columns") or []
            if column.get("name") != target_column
        ]
    output.update({
        "output_id": "scoring_prepared",
        "materialization": "temporary",
        "dataset_name": f"{output_name_prefix} - Scoring Ready",
        "business_case_role": "scoring_input",
    })

    source_fe.update({
        "mode": "transform",
        "inputs": [{
            "input_id": "scoring_input",
            "role": "scoring_input",
            "dataset_id": "",
            "version_policy": "latest",
        }],
        "outputs": [{
            "output_id": "scoring_features",
            "input_id": "scoring_input",
            "dataset_name": f"{output_name_prefix} - Scoring Features",
            "business_case_role": "scoring_input",
        }],
        "fitted_state_artifact_id": str(model.get("fitted_transform_artifact_id") or ""),
    })
    evaluation = source_fe.setdefault("evaluation", {})
    evaluation["split_strategy"] = "predefined"
    evaluation.setdefault("cross_validation", {})["enabled"] = False
    if not source_fe["fitted_state_artifact_id"]:
        raise ValueError("The selected model has no fitted Feature Engineering state")

    return {
        "contract_version": "2.0",
        "steps": [
            {
                "step_id": "de_1",
                "name": "Scoring Data Engineering",
                "type": "data_engineering",
                "inputs": [],
                "output_port_id": "dataset",
                "additional_output_port_ids": [],
                "config": {"definition": source_de},
            },
            {
                "step_id": "fe_1",
                "name": "Feature Engineering Transform",
                "type": "feature_engineering",
                "inputs": [{
                    "port_id": "scoring_input",
                    "source": {"step_id": "de_1", "port_id": "dataset"},
                }],
                "output_port_id": "scoring_input",
                "additional_output_port_ids": [],
                "config": {"definition": source_fe},
            },
            {
                "step_id": "scoring_1",
                "name": "Batch Scoring",
                "type": "scoring",
                "inputs": [{
                    "port_id": "data",
                    "source": {"step_id": "fe_1", "port_id": "scoring_input"},
                }],
                "output_port_id": "predictions",
                "additional_output_port_ids": [],
                "config": {"definition": {
                    "contract_version": "1.0",
                    "purpose": "batch",
                    "model_artifact_id": str(model["id"]),
                    "row_id_column": "property_id",
                    "target_column": "",
                    "prediction_column": "prediction",
                    "dataset_name": f"{output_name_prefix} - Batch Predictions",
                    "report_name": "Batch scoring",
                    "batch_size": 10_000,
                }},
            },
        ],
        "outputs": [{
            "output_id": "result",
            "source": {"step_id": "scoring_1", "port_id": "predictions"},
        }],
        "parameters": {
            "template": "batch_scoring",
            "example_id": "Example01",
            "example_contract_version": SCENARIO_VERSION,
            "inferred_from": {
                "pipeline_id": str(model.get("pipeline_id") or ""),
                "pipeline_version_id": str(model.get("pipeline_version_id") or ""),
                "pipeline_run_id": str(model.get("pipeline_run_id") or ""),
                "model_artifact_id": str(model["id"]),
                "fitted_transform_artifact_id": source_fe["fitted_state_artifact_id"],
            },
        },
    }


def prediction_output(run: PipelineRun) -> Mapping[str, Any]:
    matches = [
        item for item in run.raw.get("output_manifest") or []
        if item.get("artifact_type") == "prediction_dataset" and item.get("dataset_id")
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Batch run {run.id} has {len(matches)} prediction outputs; expected one"
        )
    return matches[0]


def build_monitoring_definition(
    batch_run: PipelineRun,
    actuals_logical_id: str,
    *,
    output_name_prefix: str,
) -> dict[str, Any]:
    """Build monitoring pinned to one prediction dataset and latest actuals family."""
    prediction = prediction_output(batch_run)
    prediction_dataset_id = str(prediction["dataset_id"])
    return {
        "contract_version": "2.0",
        "steps": [
            {
                "step_id": "process_join_1",
                "name": "Process & Join",
                "type": "data_engineering",
                "inputs": [],
                "output_port_id": "dataset",
                "additional_output_port_ids": [],
                "config": {"definition": {
                    "contract_version": "1.0",
                    "inputs": [
                        {
                            "input_id": "predictions",
                            "dataset_id": prediction_dataset_id,
                            "output_port_id": "out",
                            "version_policy": "pinned",
                        },
                        {
                            "input_id": "actuals",
                            "dataset_id": actuals_logical_id,
                            "output_port_id": "out",
                            "version_policy": "latest",
                        },
                    ],
                    "steps": [{
                        "step_id": "join_predictions_actuals",
                        "type": "join",
                        "inputs": [
                            {"port_id": "left", "source": {"node_id": "predictions", "port_id": "out"}},
                            {"port_id": "right", "source": {"node_id": "actuals", "port_id": "out"}},
                        ],
                        "output_port_id": "out",
                        "config": {
                            "join_type": "left",
                            "keys": [{"left": "property_id", "right": "property_id"}],
                            "right_suffix": "_actuals",
                        },
                    }],
                    "outputs": [{
                        "output_id": "joined_monitoring_data",
                        "input": {"node_id": "join_predictions_actuals", "port_id": "out"},
                        "materialization": "dataset",
                        "write_mode": "replace",
                        "dataset_name": f"{output_name_prefix} - Predictions with Actuals",
                        "business_case_role": "monitoring_input",
                    }],
                    "parameters": {"purpose": "monitoring_process_join"},
                }},
            },
            {
                "step_id": "monitoring_1",
                "name": "Performance Report",
                "type": "monitoring",
                "inputs": [{
                    "port_id": "data",
                    "source": {"step_id": "process_join_1", "port_id": "dataset"},
                }],
                "output_port_id": "performance_report",
                "additional_output_port_ids": [],
                "config": {"definition": {
                    "contract_version": "2.0",
                    "row_id_column": "property_id",
                    "target_column": "sale_price_pln",
                    "prediction_column": "prediction",
                    "problem_type": "regression",
                    "report_name": f"{output_name_prefix} - Monitoring Report",
                }},
            },
        ],
        "outputs": [{
            "output_id": "result",
            "source": {"step_id": "monitoring_1", "port_id": "performance_report"},
        }],
        "parameters": {
            "template": "monitoring",
            "example_id": "Example01",
            "example_contract_version": SCENARIO_VERSION,
            "inferred_from": {
                "pipeline_id": batch_run.pipeline_id,
                "pipeline_version_id": batch_run.pipeline_version_id,
                "pipeline_run_id": batch_run.id,
                "prediction_dataset_id": prediction_dataset_id,
                "prediction_artifact_id": str(prediction.get("artifact_id") or ""),
            },
        },
    }
