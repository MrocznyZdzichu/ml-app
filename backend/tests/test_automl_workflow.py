from types import SimpleNamespace

import pytest

from app.modules.pipelines.runtime import SourceRelation
from app.modules.pipelines.step_handlers import AutoMLStepHandler, StepExecutionContext
from app.modules.pipelines.workflow import WorkflowStep, validate_workflow_definition


def automl_definition(*, mode: str = "automl") -> dict:
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
