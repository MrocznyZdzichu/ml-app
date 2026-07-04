from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from app.core.security import Principal
from app.modules.business_cases.domain import Artifact, ArtifactOrigin, ArtifactType
from app.modules.models.repository import InMemoryModelRepository
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
            "metrics": {"f1": 0.82, "note": "not numeric"},
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
    assert response.metrics == {"f1": 0.82}
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
