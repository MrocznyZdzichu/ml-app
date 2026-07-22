from __future__ import annotations

import unittest

from examples.example01_lifecycle import (
    build_batch_scoring_definition,
    build_monitoring_definition,
    build_training_definition,
)
from ml_app_client import PipelineRun


class Example01LifecycleTests(unittest.TestCase):
    def test_training_definition_uses_tutorial_budget_and_marker(self) -> None:
        definition = build_training_definition(
            "training-family",
            model_name="Tutorial price model",
            output_name_prefix="Tutorial outputs",
        )
        automl = next(step for step in definition["steps"] if step["type"] == "automl")
        training = automl["config"]["definition"]

        self.assertEqual(training["optimization"]["max_trials"], 6)
        self.assertEqual(training["optimization"]["cv_folds"], 3)
        self.assertEqual(training["auto_feature_engineering"]["max_recipe_candidates"], 3)
        self.assertEqual(training["model_name"], "Tutorial price model")
        self.assertEqual(definition["parameters"]["example_id"], "Example01")

    def test_batch_definition_removes_target_and_pins_training_bundle(self) -> None:
        model = {
            "id": "model-1",
            "target_column": "sale_price_pln",
            "pipeline_id": "training-pipeline",
            "pipeline_version_id": "training-version",
            "pipeline_run_id": "training-run",
            "fitted_transform_artifact_id": "fitted-1",
            "data_engineering_definition": {
                "contract_version": "1.0",
                "inputs": [{
                    "input_id": "source_1", "dataset_id": "training-family",
                    "output_port_id": "out", "version_policy": "latest",
                }],
                "steps": [
                    {
                        "step_id": "select", "type": "select_columns",
                        "inputs": [{"port_id": "input", "source": {"node_id": "source_1", "port_id": "out"}}],
                        "output_port_id": "out",
                        "config": {"columns": ["property_id", "feature", "sale_price_pln"]},
                    },
                    {
                        "step_id": "cast", "type": "cast_columns",
                        "inputs": [{"port_id": "input", "source": {"node_id": "select", "port_id": "out"}}],
                        "output_port_id": "out",
                        "config": {"casts": {
                            "property_id": "VARCHAR", "feature": "DOUBLE", "sale_price_pln": "DOUBLE",
                        }},
                    },
                ],
                "outputs": [{
                    "output_id": "result",
                    "input": {"node_id": "cast", "port_id": "out"},
                    "materialization": "dataset", "write_mode": "replace",
                    "dataset_name": "training", "business_case_role": "training",
                    "data_contract": {"columns": [
                        {"name": "property_id"}, {"name": "feature"}, {"name": "sale_price_pln"},
                    ]},
                }],
                "parameters": {},
            },
            "feature_engineering_definition": {
                "contract_version": "1.0", "mode": "fit_transform",
                "inputs": [], "outputs": [], "evaluation": {"cross_validation": {"enabled": True}},
            },
        }

        definition = build_batch_scoring_definition(
            model,
            "scoring-family",
            output_name_prefix="Tutorial model",
        )
        de = definition["steps"][0]["config"]["definition"]
        fe = definition["steps"][1]["config"]["definition"]

        self.assertEqual(de["inputs"][0]["dataset_id"], "scoring-family")
        self.assertNotIn("sale_price_pln", de["steps"][0]["config"]["columns"])
        self.assertNotIn("sale_price_pln", de["steps"][1]["config"]["casts"])
        self.assertEqual(fe["fitted_state_artifact_id"], "fitted-1")
        self.assertEqual(fe["mode"], "transform")

    def test_monitoring_definition_pins_prediction_and_resolves_actuals_family(self) -> None:
        run = PipelineRun.from_api({
            "id": "batch-run", "pipeline_id": "batch-pipeline",
            "pipeline_version_id": "batch-version", "status": "succeeded",
            "processed_row_count": 100, "error_message": "",
            "output_manifest": [{
                "artifact_type": "prediction_dataset", "dataset_id": "predictions-v1",
                "artifact_id": "prediction-artifact",
            }],
        })

        definition = build_monitoring_definition(
            run,
            "actuals-family",
            output_name_prefix="Tutorial model",
        )
        inputs = definition["steps"][0]["config"]["definition"]["inputs"]

        self.assertEqual(inputs[0]["dataset_id"], "predictions-v1")
        self.assertEqual(inputs[0]["version_policy"], "pinned")
        self.assertEqual(inputs[1]["dataset_id"], "actuals-family")
        self.assertEqual(inputs[1]["version_policy"], "latest")


if __name__ == "__main__":
    unittest.main()
