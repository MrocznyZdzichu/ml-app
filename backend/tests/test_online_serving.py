from datetime import datetime

import pytest

from app.core.security import Principal
from app.modules.models.domain import ModelArtifact, ModelStage
from app.modules.serving.domain import DeploymentRole, InferenceStatus
from app.modules.serving.runtime import RuntimeUnavailableError
from app.modules.serving.schemas import DeploymentCreate, DeploymentRevisionCreate, ScoreRecord
from app.modules.serving.service import ServingService
from app.modules.sharing.domain import BusinessCaseAccessRole
from app.modules.sharing.policy import access_policy


class MemoryServingRepository:
    def __init__(self) -> None:
        self.deployments = {}
        self.revisions = {}
        self.inferences = {}
        self.items = []

    def add_deployment(self, deployment, revision):
        self.deployments[deployment.id] = deployment
        self.revisions[revision.id] = revision
        return deployment

    def update_deployment(self, deployment):
        self.deployments[deployment.id] = deployment
        return deployment

    def list_all_deployments(self):
        return list(self.deployments.values())

    def get_deployment(self, value):
        return next((item for item in self.deployments.values() if value in {item.id, item.slug}), None)

    def add_revision(self, revision, deployment):
        self.revisions[revision.id] = revision
        self.deployments[deployment.id] = deployment
        return revision

    def get_revision(self, revision_id):
        return self.revisions.get(revision_id)

    def list_revisions(self, deployment_id):
        return [item for item in self.revisions.values() if item.deployment_id == deployment_id]

    def add_inference(self, inference):
        self.inferences[inference.id] = inference
        return inference

    def get_inference(self, request_id):
        return self.inferences.get(request_id)

    def find_idempotent(self, deployment_id, requested_by, key):
        return next((item for item in self.inferences.values() if key and item.deployment_id == deployment_id and item.requested_by == requested_by and item.idempotency_key == key), None)

    def complete_inference(self, inference, items):
        self.inferences[inference.id] = inference
        self.items.extend(items)
        return inference

    def list_inference(self, deployment_id, limit, cursor, record_id=None):
        rows = [item for item in self.inferences.values() if item.deployment_id == deployment_id]
        return sorted(rows, key=lambda item: (item.created_at, item.id), reverse=True)[:limit]

    def inference_items(self, request_id):
        return [item for item in self.items if item["request_id"] == request_id]

    def prune_expired(self, deployment_id, cutoff):
        return 0


class Models:
    def __init__(self, models):
        self.models = {item.id: item for item in models}

    def get_model(self, model_id, principal):
        return self.models[model_id]


class Runtime:
    def __init__(self, failures=()):
        self.failures = set(failures)
        self.calls = []

    def score(self, *, model_artifact_uri, model_hash, records, request_id):
        self.calls.append(model_artifact_uri)
        if model_artifact_uri in self.failures:
            raise RuntimeUnavailableError("runtime unavailable")
        return [{"prediction": float(record["value"]), "prediction_score": 0.9} for record in records]


def model(model_id: str, stage: ModelStage = ModelStage.PRODUCTION) -> ModelArtifact:
    return ModelArtifact(
        id=model_id, owner_id="owner", training_job_id="run", name=model_id,
        version="v1", algorithm="ridge", artifact_uri=f"file:///{model_id}.joblib",
        stage=stage, business_case_id="bc-1", problem_type="regression",
        feature_columns=["value"], model_hash=f"hash-{model_id}",
    )


@pytest.fixture
def principal(monkeypatch):
    value = Principal(
        user_id="admin", email="admin@example.com", display_name="Admin",
        roles=("user", "administrator"),
    )
    monkeypatch.setattr(access_policy, "require_business_case", lambda *args, **kwargs: BusinessCaseAccessRole.OWNER)
    monkeypatch.setattr(access_policy, "business_case_role", lambda *args, **kwargs: BusinessCaseAccessRole.OWNER)
    monkeypatch.setattr(ServingService, "_audit", staticmethod(lambda *args, **kwargs: None))
    return value


def test_versioned_roles_fallback_and_inference_history(principal) -> None:
    repository = MemoryServingRepository()
    champion, fallback = model("champion"), model("fallback")
    challenger, shadow = model("challenger", ModelStage.STAGING), model("shadow", ModelStage.STAGING)
    runtime = Runtime(failures={champion.artifact_uri})
    service = ServingService(repository=repository, runtime=runtime, models=Models([champion, fallback, challenger, shadow]))
    deployment = service.create_deployment(
        DeploymentCreate(name="Estates Sell Prices Service", model_id=champion.id), principal
    )
    revision = service.create_revision(deployment.id, DeploymentRevisionCreate(
        assignments=[
            {"model_id": champion.id, "role": "champion"},
            {"model_id": fallback.id, "role": "fallback"},
            {"model_id": challenger.id, "role": "challenger"},
            {"model_id": shadow.id, "role": "shadow"},
        ],
        reason="Add fallback and challenger",
    ), principal)

    result = service.score(
        deployment.id,
        [ScoreRecord(record_id=None, features={"value": 42})],
        principal,
        idempotency_key="one",
    )

    assert revision.version_number == 2
    assert result.model_id == fallback.id
    assert result.served_role == DeploymentRole.FALLBACK
    assert result.fallback_used is True
    assert result.predictions[0].prediction == 42.0
    assert "no stable record_id" in result.warnings[0]
    assert repository.inferences[result.request_id].status == InferenceStatus.SUCCEEDED
    assert {item["role"] for item in repository.items} == {"fallback", "shadow"}
    assert service.score(deployment.id, [ScoreRecord(features={"value": 999})], principal, idempotency_key="one").request_id == result.request_id


def test_candidate_cannot_become_champion(principal) -> None:
    candidate = model("candidate", ModelStage.CANDIDATE)
    service = ServingService(repository=MemoryServingRepository(), runtime=Runtime(), models=Models([candidate]))
    with pytest.raises(Exception) as error:
        service.create_deployment(DeploymentCreate(name="Unsafe", model_id=candidate.id), principal)
    assert getattr(error.value, "status_code", None) == 409


def test_success_is_not_returned_when_audit_completion_fails(principal) -> None:
    class FailingAuditRepository(MemoryServingRepository):
        def complete_inference(self, inference, items):
            raise OSError("database unavailable")

    champion = model("champion")
    service = ServingService(
        repository=FailingAuditRepository(), runtime=Runtime(), models=Models([champion])
    )
    deployment = service.create_deployment(
        DeploymentCreate(name="Governed service", model_id=champion.id), principal
    )
    with pytest.raises(Exception) as error:
        service.score(
            deployment.id,
            [ScoreRecord(record_id="row-1", features={"value": 1})],
            principal,
        )
    assert getattr(error.value, "status_code", None) == 503
