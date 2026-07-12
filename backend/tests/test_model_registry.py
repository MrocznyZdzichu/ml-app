from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from app.core.security import Principal
from app.modules.business_cases.domain import Artifact, ArtifactOrigin, ArtifactType
from app.modules.models.repository import InMemoryModelRepository
from app.modules.models.domain import ModelArtifact
from app.modules.models.schemas import ModelArtifactRead
from app.modules.models.service import ModelService


def test_pipeline_model_registry_exposes_governance_metadata_and_bounded_parameters() -> None:
    created_at = datetime.now(timezone.utc)
    artifact = Artifact(
        id="artifact-model-1",
        owner_id="owner-1",
        type=ArtifactType.MODEL_VERSION,
        reference_id="model-reference-1",
        origin=ArtifactOrigin.PLATFORM_GENERATED,
        business_case_id="bc-1",
        metadata={
            "location_uri": "file:///repository/model.joblib",
            "model_name": "Churn classifier",
            "algorithm": "sgd_classifier",
            "problem_type": "binary_classification",
            "target_column": "churn",
            "feature_columns": ["tenure", "balance"],
            "model_hash": "sha256-value",
            "metrics": {
                "f1": 0.82,
                "note": "registry-safe metadata",
                "optimization": {
                    "mode": "automl",
                    "best_algorithm": "ridge_classifier",
                    "trials": [{"number": 0, "score": 0.81}],
                },
            },
            "training_config": {
                "epochs": 10,
                "batch_size": 10_000,
                "parameters": {"alpha": 0.0001},
            },
            "model_parameters": {
                "weights": [
                    {"class": 1, "feature": "tenure", "weight": 0.25},
                    {"class": 1, "feature": "balance", "weight": -0.1},
                ],
                "total_weight_count": 2,
                "returned_weight_count": 2,
                "truncated": False,
            },
            "lineage": {
                "pipeline_id": "pipeline-1",
                "pipeline_version_id": "version-1",
                "pipeline_run_id": "run-1",
                "pipeline_step_id": "training-1",
                "input_artifact_ids": ["training-data-1"],
            },
        },
        created_by="owner-1",
        created_at=created_at,
    )

    model = ModelService._artifact_model(artifact)
    response = ModelArtifactRead.model_validate(model)

    assert response.business_case_id == "bc-1"
    assert response.pipeline_id == "pipeline-1"
    assert response.pipeline_run_id == "run-1"
    assert response.feature_columns == ["tenure", "balance"]
    assert response.metrics["f1"] == 0.82
    assert response.metrics["optimization"]["mode"] == "automl"
    assert response.metrics["optimization"]["trials"][0]["score"] == 0.81
    assert response.training_config["parameters"] == {"alpha": 0.0001}
    assert response.model_parameters["weights"][0]["feature"] == "tenure"
    assert response.lineage["input_artifact_ids"] == ["training-data-1"]
    assert response.created_at == created_at


def test_pipeline_runs_are_presented_as_versions_of_one_logical_model() -> None:
    created_at = datetime.now(timezone.utc)

    def artifact(artifact_id: str, run_id: str, timestamp: datetime) -> Artifact:
        return Artifact(
            id=artifact_id,
            owner_id="owner-1",
            type=ArtifactType.MODEL_VERSION,
            reference_id=f"reference-{artifact_id}",
            origin=ArtifactOrigin.PLATFORM_GENERATED,
            business_case_id="bc-1",
            metadata={
                "model_name": "Churn classifier",
                "algorithm": "sgd_classifier",
                "lineage": {
                    "pipeline_run_id": run_id,
                    "pipeline_step_id": "training-1",
                },
            },
            created_by="owner-1",
            created_at=timestamp,
        )

    artifacts = Mock()
    pipeline_models = [
        artifact("model-2", "run-2", created_at + timedelta(minutes=5)),
        artifact("model-1", "run-1", created_at),
    ]
    artifacts.list_artifacts.side_effect = lambda owner_id, artifact_type: (
        pipeline_models if artifact_type == ArtifactType.MODEL_VERSION else []
    )
    pipelines = Mock()
    pipelines.get_run.side_effect = lambda run_id: SimpleNamespace(
        owner_id="owner-1",
        pipeline_id="pipeline-1",
        id=run_id,
    )
    pipelines.list_versions_for_pipelines.return_value = []
    service = ModelService(
        repository=InMemoryModelRepository(),
        artifacts=artifacts,
        pipelines=pipelines,
    )
    principal = Principal("owner-1", "owner@example.com", "Owner")

    models = service.list_models(principal)

    assert len({model.logical_id for model in models}) == 1
    assert [(model.id, model.version, model.version_number) for model in models] == [
        ("model-2", "v2", 2),
        ("model-1", "v1", 1),
    ]
    assert pipelines.list_versions_for_pipelines.call_count == 1
    assert artifacts.list_artifacts.call_count == 2
    assert [model.id for model in service.list_versions(models[0].logical_id, principal)] == [
        "model-1",
        "model-2",
    ]


def test_batch_scoring_contract_prefers_autofe_recipe_and_matching_step_state() -> None:
    automl_recipe = {
        "contract_version": "1.0",
        "feature_columns": ["amount", "segment"],
        "target_column": "churned",
        "row_id_column": "customer_id",
        "transformations": [{"transform_id": "one_hot", "type": "encode_categorical"}],
    }
    source_feature_definition = {
        "contract_version": "1.0",
        "feature_columns": [],
        "target_column": "churned",
        "row_id_column": "customer_id",
        "transformations": [],
    }
    version = SimpleNamespace(
        id="version-1",
        owner_id="owner-1",
        definition={
            "steps": [
                {"type": "data_engineering", "config": {"definition": {"steps": ["safe"]}}},
                {"type": "feature_engineering", "config": {"definition": source_feature_definition}},
            ]
        },
    )
    model = ModelArtifact(
        id="automl-model",
        owner_id="owner-1",
        training_job_id="",
        name="AutoML churn",
        version="v1",
        algorithm="sgd_classifier",
        artifact_uri="file:///model.joblib",
        pipeline_version_id="version-1",
        pipeline_run_id="run-1",
        pipeline_step_id="automl_1",
        training_config={"auto_feature_engineering": {"resolved_recipe": automl_recipe}},
    )
    split_state = Artifact(
        id="split-state",
        owner_id="owner-1",
        type=ArtifactType.FEATURE_TRANSFORM,
        reference_id="split-ref",
        origin=ArtifactOrigin.PLATFORM_GENERATED,
        metadata={"lineage": {"pipeline_run_id": "run-1", "pipeline_step_id": "fe_1"}},
    )
    automl_state = Artifact(
        id="automl-state",
        owner_id="owner-1",
        type=ArtifactType.FEATURE_TRANSFORM,
        reference_id="automl-ref",
        origin=ArtifactOrigin.PLATFORM_GENERATED,
        metadata={"lineage": {"pipeline_run_id": "run-1", "pipeline_step_id": "automl_1"}},
    )

    ModelService._enrich_batch_scoring_contract(
        model,
        {("run-1", "fe_1"): split_state, ("run-1", "automl_1"): automl_state},
        {"version-1": version},
    )

    assert model.fitted_transform_artifact_id == "automl-state"
    assert model.feature_engineering_definition == automl_recipe
    assert model.data_engineering_definition == {"steps": ["safe"]}


def test_batch_scoring_contract_keeps_pipeline_fe_for_traditional_model() -> None:
    feature_definition = {
        "contract_version": "1.0",
        "feature_columns": ["amount"],
        "target_column": "churned",
        "row_id_column": "customer_id",
        "transformations": [{"transform_id": "scale", "type": "scale_numeric"}],
    }
    version = SimpleNamespace(
        id="version-1",
        owner_id="owner-1",
        definition={"steps": [
            {"step_id": "fe_1", "type": "feature_engineering", "config": {"definition": feature_definition}},
            {"step_id": "training_1", "type": "training", "inputs": [
                {"port_id": "training", "source": {"step_id": "fe_1", "port_id": "training"}},
            ]},
        ]},
    )
    model = ModelArtifact(
        id="training-model",
        owner_id="owner-1",
        training_job_id="",
        name="Traditional churn",
        version="v1",
        algorithm="sgd_classifier",
        artifact_uri="file:///model.joblib",
        pipeline_version_id="version-1",
        pipeline_run_id="run-1",
        pipeline_step_id="training_1",
    )
    state = Artifact(
        id="training-state",
        owner_id="owner-1",
        type=ArtifactType.FEATURE_TRANSFORM,
        reference_id="training-ref",
        origin=ArtifactOrigin.PLATFORM_GENERATED,
        metadata={"lineage": {"pipeline_run_id": "run-1", "pipeline_step_id": "training_1"}},
    )

    ModelService._enrich_batch_scoring_contract(
        model,
        {("run-1", "fe_1"): state},
        {"version-1": version},
    )

    assert model.fitted_transform_artifact_id == "training-state"
    assert model.feature_engineering_definition == feature_definition
