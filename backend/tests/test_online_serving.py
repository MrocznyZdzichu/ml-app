from datetime import datetime

import pytest

from app.core.security import Principal
from app.modules.models.domain import ModelArtifact, ModelStage
from app.modules.models.schemas import PromoteModelRequest
from app.modules.pipelines.feature_engineering import DuckDbFeatureEngineeringEngine
from app.modules.serving.domain import DeploymentRole, DeploymentStatus, InferenceStatus
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

    def list_inference_summaries(self, deployment_id, limit, cursor, record_id=None):
        rows = self.list_inference(deployment_id, limit, cursor, record_id)
        return [
            {
                key: value for key, value in item.__dict__.items()
                if key not in {"request_payload", "response_payload", "request_hash", "idempotency_key"}
            }
            for item in rows
        ]

    def inference_items(self, request_id):
        return [item for item in self.items if item["request_id"] == request_id]

    def prune_expired(self, deployment_id, cutoff):
        return 0

    def active_assignments_for_model(self, model_id):
        result = []
        for deployment in self.deployments.values():
            if deployment.status in {DeploymentStatus.STOPPED, DeploymentStatus.ARCHIVED}:
                continue
            revision = self.revisions.get(deployment.active_revision_id)
            for assignment in revision.assignments if revision else []:
                if assignment.model_id == model_id:
                    result.append({
                        "deployment_id": deployment.id,
                        "deployment_name": deployment.name,
                        "deployment_slug": deployment.slug,
                        "deployment_status": deployment.status,
                        "endpoint_url": deployment.endpoint_url,
                        "revision_id": revision.id,
                        "revision_version": revision.version_number,
                        "role": assignment.role,
                    })
        return result

    def clear_active_assignments(self, deployment_id):
        return None

    def restore_active_assignments(self, deployment, revision):
        return None

    def set_deployment_status(self, deployment, revision):
        self.deployments[deployment.id] = deployment
        return deployment


class Models:
    def __init__(self, models):
        self.models = {item.id: item for item in models}

    def get_model(self, model_id, principal):
        return self.models[model_id]

    def list_versions(self, logical_id, principal):
        return [item for item in self.models.values() if item.logical_id == logical_id]

    def list_models(self, principal):
        return list(self.models.values())


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


def test_candidate_input_is_canonicalized_to_developed() -> None:
    assert PromoteModelRequest(stage="candidate").stage == ModelStage.DEVELOPED


def test_categorical_suggestions_are_ranked_from_persisted_training_frequencies(monkeypatch) -> None:
    engine = DuckDbFeatureEngineeringEngine()
    monkeypatch.setattr(engine, "_load_state", lambda *args: {
        "transforms": {
            "encode": {
                "columns": {
                    "region": {
                        "frequencies": {
                            "south": 12, "north": 30, "west": 40,
                            "east": 25, "central": 18, "other": 1,
                        }
                    }
                }
            }
        }
    })

    suggestions = engine.categorical_suggestions(
        fitted_state_artifact_id="state-1", owner_id="owner", limit=5
    )

    assert suggestions == {
        "region": ["west", "north", "east", "central", "south"]
    }


def test_model_family_usage_exposes_active_service_role(principal) -> None:
    repository = MemoryServingRepository()
    champion = model("model-v11")
    champion.logical_id = "model-family"
    service = ServingService(repository=repository, runtime=Runtime(), models=Models([champion]))
    deployment = service.create_deployment(
        DeploymentCreate(name="Estates Service", model_id=champion.id), principal
    )

    usage = service.list_model_family_usage("model-family", principal)

    assert usage == [{
        "model_id": champion.id,
        "deployment_id": deployment.id,
        "deployment_name": deployment.name,
        "deployment_slug": deployment.slug,
        "deployment_status": DeploymentStatus.RUNNING,
        "endpoint_url": deployment.endpoint_url,
        "revision_id": deployment.active_revision_id,
        "revision_version": 1,
        "role": DeploymentRole.CHAMPION,
    }]


def test_input_contract_uses_raw_features_types_and_profile_defaults(principal) -> None:
    repository = MemoryServingRepository()
    champion = model("model-v11")
    champion.feature_engineering_definition = {
        "feature_columns": ["age", "region", "is_active"]
    }
    champion.training_config = {
        "auto_feature_engineering": {
            "column_decisions": [
                {
                    "column": "age", "type": "BIGINT", "role": "numeric",
                    "numeric_profile": {"min": 18, "max": 82, "mean": 41.4},
                },
                {"column": "region", "type": "VARCHAR", "role": "categorical"},
                {"column": "is_active", "type": "BOOLEAN", "role": "categorical"},
            ]
        }
    }
    service = ServingService(repository=repository, runtime=Runtime(), models=Models([champion]))
    deployment = service.create_deployment(
        DeploymentCreate(name="Contract service", model_id=champion.id), principal
    )

    contract = service.input_contract(deployment.id, principal)

    assert contract["model_id"] == champion.id
    assert contract["role"] == DeploymentRole.CHAMPION
    assert contract["example_features"] == {
        "age": 41, "region": "example", "is_active": False,
    }
    assert contract["fields"][0]["minimum"] == 18
    assert contract["fields"][0]["maximum"] == 82


def test_deployment_model_options_expose_opaque_contract_compatibility(principal) -> None:
    repository = MemoryServingRepository()
    champion = model("champion")
    compatible = model("compatible", ModelStage.STAGING)
    incompatible = model("incompatible", ModelStage.STAGING)
    incompatible.feature_columns = ["other_value"]
    developed = model("developed", ModelStage.DEVELOPED)
    service = ServingService(
        repository=repository,
        runtime=Runtime(),
        models=Models([champion, compatible, incompatible, developed]),
    )
    deployment = service.create_deployment(
        DeploymentCreate(name="Options service", model_id=champion.id), principal
    )

    options = service.deployment_model_options(deployment.id, principal)
    by_id = {item["model_id"]: item for item in options}

    assert set(by_id) == {"champion", "compatible", "incompatible"}
    assert by_id["compatible"]["compatible_with_active_champion"] is True
    assert by_id["incompatible"]["compatible_with_active_champion"] is False
    assert by_id["compatible"]["allowed_roles"] == [
        DeploymentRole.CHALLENGER, DeploymentRole.SHADOW,
    ]


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
    assert repository.deployments[deployment.id].status == DeploymentStatus.DEGRADED
    assert result.predictions[0].prediction == 42.0
    assert result.predictions[0].prediction_id == f"{result.request_id}:{fallback.id}:0"
    assert "no stable record_id" in result.warnings[0]
    assert repository.inferences[result.request_id].status == InferenceStatus.SUCCEEDED
    assert repository.inferences[result.request_id].requested_model_id == champion.id
    assert repository.inferences[result.request_id].requested_role == DeploymentRole.CHAMPION
    assert {item["role"] for item in repository.items} == {"champion", "fallback", "shadow"}
    assert next(item for item in repository.items if item["role"] == "champion")["status"] == "failed"
    assert service.score(deployment.id, [ScoreRecord(features={"value": 42})], principal, idempotency_key="one").request_id == result.request_id
    with pytest.raises(Exception) as idempotency_error:
        service.score(deployment.id, [ScoreRecord(features={"value": 999})], principal, idempotency_key="one")
    assert getattr(idempotency_error.value, "status_code", None) == 409
    runtime.failures.clear()
    service.score(
        deployment.id,
        [ScoreRecord(record_id="recovered", features={"value": 7})],
        principal,
        idempotency_key="two",
    )
    assert repository.deployments[deployment.id].status == DeploymentStatus.RUNNING
    summary = service.inference_history_summary(deployment.id, principal, limit=1)
    assert len(summary.items) == 1
    assert summary.next_cursor is not None
    assert "request_payload" not in summary.items[0].model_dump()
    assert "response_payload" not in summary.items[0].model_dump()


def test_developed_model_cannot_become_champion(principal) -> None:
    developed = model("developed", ModelStage.DEVELOPED)
    service = ServingService(repository=MemoryServingRepository(), runtime=Runtime(), models=Models([developed]))
    with pytest.raises(Exception) as error:
        service.create_deployment(DeploymentCreate(name="Unsafe", model_id=developed.id), principal)
    assert getattr(error.value, "status_code", None) == 409


def test_invalid_active_model_stage_degrades_and_blocks_scoring(principal) -> None:
    champion = model("champion")
    repository = MemoryServingRepository()
    service = ServingService(repository=repository, runtime=Runtime(), models=Models([champion]))
    deployment = service.create_deployment(
        DeploymentCreate(name="Lifecycle guarded", model_id=champion.id), principal
    )
    champion.stage = ModelStage.DEVELOPED

    with pytest.raises(Exception) as error:
        service.score(deployment.id, [ScoreRecord(features={"value": 1})], principal)

    assert getattr(error.value, "status_code", None) == 503
    assert repository.deployments[deployment.id].status.value == "degraded"


def test_service_stop_start_and_rollback_create_a_new_revision(principal) -> None:
    first, second = model("first"), model("second")
    repository = MemoryServingRepository()
    service = ServingService(
        repository=repository, runtime=Runtime(), models=Models([first, second])
    )
    deployment = service.create_deployment(
        DeploymentCreate(name="Operable service", model_id=first.id), principal
    )
    original_revision_id = deployment.active_revision_id
    service.create_revision(deployment.id, DeploymentRevisionCreate(
        assignments=[{"model_id": second.id, "role": "champion"}],
        reason="Move to second",
    ), principal)

    rollback = service.rollback_deployment(
        deployment.id, original_revision_id, "Second model regressed", principal
    )
    assert rollback.version_number == 3
    assert rollback.assignments[0].model_id == first.id
    assert repository.deployments[deployment.id].active_revision_id == rollback.id

    stopped = service.set_deployment_status(
        deployment.id, DeploymentStatus.STOPPED, "Maintenance", principal
    )
    assert stopped.status == DeploymentStatus.STOPPED
    with pytest.raises(Exception) as stopped_error:
        service.score(deployment.id, [ScoreRecord(features={"value": 1})], principal)
    assert getattr(stopped_error.value, "status_code", None) == 503

    started = service.set_deployment_status(
        deployment.id, DeploymentStatus.RUNNING, "Maintenance complete", principal
    )
    assert started.status == DeploymentStatus.RUNNING

    archived = service.set_deployment_status(
        deployment.id, DeploymentStatus.ARCHIVED, "Trial service is no longer needed", principal
    )
    assert archived.status == DeploymentStatus.ARCHIVED
    assert service.list_deployments(principal) == []
    assert service.list_deployments(principal, include_archived=True) == [archived]
    with pytest.raises(Exception) as archived_error:
        service.set_deployment_status(
            deployment.id, DeploymentStatus.RUNNING, "Attempt to restore", principal
        )
    assert getattr(archived_error.value, "status_code", None) == 409


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
