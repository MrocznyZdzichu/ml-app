import time
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app


def _register(client: TestClient, name: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"{name}-{uuid4()}@example.com",
            "password": "password123",
            "display_name": name.title(),
        },
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def _create_business_case(client: TestClient, token: str) -> dict:
    response = client.post(
        "/api/v1/business-cases",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Iris classification",
            "description": "Recognize Iris species",
            "problem_type": "multiclass_classification",
            "target_column": "species",
            "primary_metric": "f1_macro",
            "business_goal": "Standardize a reusable ML workflow",
            "success_criteria": "F1 macro >= 0.95",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_model_training_catalog_is_available_to_authenticated_pipeline_editors() -> None:
    client = TestClient(create_app())
    token = _register(client, "alice")

    response = client.get(
        "/api/v1/pipelines/model-training/catalog",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["algorithm_count"] >= 50
    assert len(body["algorithms"]) == body["algorithm_count"]
    assert all(item["parameters"] is not None for item in body["algorithms"])


def test_automl_pipeline_purpose_is_accepted_by_create_api() -> None:
    client = TestClient(create_app())
    token = _register(client, "automl-create")
    business_case = _create_business_case(client, token)

    response = client.post(
        "/api/v1/pipelines",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "business_case_id": business_case["id"],
            "name": "Iris AutoML",
            "type": "automl",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["type"] == "automl"


def test_business_case_can_exist_without_data_and_owns_data_mappings() -> None:
    client = TestClient(create_app())
    token = _register(client, "alice")
    business_case = _create_business_case(client, token)
    listed = client.get("/api/v1/business-cases", headers={"Authorization": f"Bearer {token}"})
    assert listed.status_code == 200
    assert business_case["id"] in {item["id"] for item in listed.json()}

    attachment = client.post(
        f"/api/v1/business-cases/{business_case['id']}/data-attachments",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "data_asset_id": "dataset-iris",
            "data_asset_kind": "dataset",
            "role": "training",
            "context_note": "Original training dataset",
            "primary_key_column": "sample_id",
            "target_column": "species",
            "origin": "uploaded",
        },
    )
    assert attachment.status_code == 201
    body = attachment.json()
    assert body["business_case_id"] == business_case["id"]
    assert body["role"] == "training"
    assert body["primary_key_column"] == "sample_id"

    attachments = client.get(
        f"/api/v1/business-cases/{business_case['id']}/data-attachments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert attachments.status_code == 200
    assert attachments.json()[0]["data_asset_id"] == "dataset-iris"


def test_external_registered_data_mapping_requires_notes() -> None:
    client = TestClient(create_app())
    token = _register(client, "alice")
    business_case = _create_business_case(client, token)

    response = client.post(
        f"/api/v1/business-cases/{business_case['id']}/data-attachments",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "data_asset_id": "external-blackbox",
            "data_asset_kind": "dataset",
            "role": "reference",
            "origin": "external_registered",
        },
    )

    assert response.status_code == 422


def test_business_case_can_be_updated_after_initial_discovery() -> None:
    client = TestClient(create_app())
    token = _register(client, "alice")
    headers = {"Authorization": f"Bearer {token}"}
    business_case = _create_business_case(client, token)

    updated = client.patch(
        f"/api/v1/business-cases/{business_case['id']}",
        headers=headers,
        json={
            "name": "Iris binary classifier",
            "description": "Detect whether Iris sample is Virginica",
            "problem_type": "binary_classification",
            "status": "active",
            "business_owner": "Botany Ops",
            "primary_metric": "roc_auc",
            "target_column": "is_virginica",
            "business_goal": "Prioritize likely Virginica samples",
            "success_criteria": "ROC AUC >= 0.97",
        },
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["id"] == business_case["id"]
    assert body["problem_type"] == "binary_classification"
    assert body["status"] == "active"
    assert body["primary_metric"] == "roc_auc"
    assert body["target_column"] == "is_virginica"
    assert body["updated_at"] != business_case["updated_at"]

    fetched = client.get(f"/api/v1/business-cases/{business_case['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Iris binary classifier"
    assert fetched.json()["business_owner"] == "Botany Ops"


def test_business_case_data_mapping_can_be_updated_and_deleted() -> None:
    client = TestClient(create_app())
    token = _register(client, "alice")
    headers = {"Authorization": f"Bearer {token}"}
    business_case = _create_business_case(client, token)

    first = client.post(
        f"/api/v1/business-cases/{business_case['id']}/data-attachments",
        headers=headers,
        json={
            "data_asset_id": "dataset-iris",
            "data_asset_kind": "dataset",
            "role": "training",
            "context_note": "Initial training mapping",
            "primary_key_column": "",
            "target_column": "species",
            "origin": "uploaded",
        },
    )
    assert first.status_code == 201
    second = client.post(
        f"/api/v1/business-cases/{business_case['id']}/data-attachments",
        headers=headers,
        json={
            "data_asset_id": "dataset-iris",
            "data_asset_kind": "dataset",
            "role": "source",
            "origin": "uploaded",
        },
    )
    assert second.status_code == 201

    updated = client.patch(
        f"/api/v1/business-cases/{business_case['id']}/data-attachments/{first.json()['id']}",
        headers=headers,
        json={
            "role": "source",
            "context_note": "Canonical source mapping",
            "primary_key_column": "sample_id",
            "target_column": "species",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["role"] == "source"
    assert updated.json()["context_note"] == "Canonical source mapping"
    assert updated.json()["primary_key_column"] == "sample_id"

    deleted = client.delete(
        f"/api/v1/business-cases/{business_case['id']}/data-attachments/{second.json()['id']}",
        headers=headers,
    )
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True

    attachments = client.get(
        f"/api/v1/business-cases/{business_case['id']}/data-attachments",
        headers=headers,
    )
    assert attachments.status_code == 200
    assert [item["id"] for item in attachments.json()] == [first.json()["id"]]
    assert attachments.json()[0]["role"] == "source"


def test_pipeline_version_and_run_contracts_are_auditable(monkeypatch) -> None:
    from app.worker.tasks import execute_pipeline_run

    dispatched: list[str] = []
    monkeypatch.setattr(execute_pipeline_run, "delay", lambda run_id: dispatched.append(run_id))
    client = TestClient(create_app())
    token = _register(client, "alice")
    business_case = _create_business_case(client, token)
    uploaded = client.post(
        "/api/v1/datasets/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={"name": "Contract input"},
        files={"file": ("contract.csv", b"sepal_length,sepal_width,species\n5.1,3.5,setosa\n", "text/csv")},
    )
    assert uploaded.status_code == 201
    dataset_id = uploaded.json()["logical_id"]

    created = client.post(
        "/api/v1/pipelines",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "business_case_id": business_case["id"],
            "name": "Iris feature engineering",
            "description": "Reusable FE placeholder",
            "type": "feature_engineering",
            "definition": {
                "contract_version": "1.0",
                    "inputs": [{"input_id": "training", "dataset_id": dataset_id, "output_port_id": "out"}],
                "steps": [
                    {
                        "step_id": "select-iris-columns",
                        "type": "select_columns",
                        "inputs": [
                            {
                                "port_id": "input",
                                "source": {"node_id": "training", "port_id": "out"},
                            }
                        ],
                        "output_port_id": "out",
                        "config": {"columns": ["sepal_length", "sepal_width", "species"]},
                    }
                ],
                "outputs": [
                    {
                        "output_id": "prepared",
                        "input": {"node_id": "select-iris-columns", "port_id": "out"},
                        "materialization": "temporary",
                        "write_mode": "replace",
                    }
                ],
                "parameters": {"template": "training"},
            },
        },
    )
    assert created.status_code == 201
    pipeline = created.json()
    assert pipeline["business_case_id"] == business_case["id"]
    assert pipeline["status"] == "draft"
    assert pipeline["template"] == "training"
    assert pipeline["draft_version_number"] == 1
    assert pipeline["latest_published_version_number"] is None

    versions = client.get(
        f"/api/v1/pipelines/{pipeline['id']}/versions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert versions.status_code == 200
    draft = versions.json()[0]
    assert draft["version_number"] == 1
    assert draft["status"] == "draft"
    assert len(draft["definition_hash"]) == 64
    assert draft["definition"]["contract_version"] == "2.0"
    assert draft["definition"]["steps"][0]["type"] == "data_engineering"
    assert draft["definition"]["steps"][0]["config"]["definition"]["contract_version"] == "1.0"

    blocked_run = client.post(
        f"/api/v1/pipelines/{pipeline['id']}/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={"trigger_type": "manual", "is_dry_run": False},
    )
    assert blocked_run.status_code == 409

    dry_run = client.post(
        f"/api/v1/pipelines/{pipeline['id']}/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={"trigger_type": "manual", "is_dry_run": True},
    )
    assert dry_run.status_code == 201
    assert dry_run.json()["is_dry_run"] is True
    assert dry_run.json()["status"] == "queued"
    assert dispatched == [dry_run.json()["id"]]

    published = client.post(
        f"/api/v1/pipelines/{pipeline['id']}/versions/draft/publish",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    catalog = client.get(
        "/api/v1/pipelines",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert catalog.status_code == 200
    catalog_pipeline = next(item for item in catalog.json() if item["id"] == pipeline["id"])
    assert catalog_pipeline["latest_published_version_number"] == 1
    assert catalog_pipeline["published_version_count"] == 1
    assert catalog_pipeline["draft_version_number"] is None
    assert catalog_pipeline["template"] == "training"
    details_response = client.get(
        f"/api/v1/pipelines/{pipeline['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert details_response.status_code == 200
    assert details_response.json()["latest_published_version_number"] == 1
    assert details_response.json()["published_version_count"] == 1

    no_draft_update = client.patch(
        f"/api/v1/pipelines/{pipeline['id']}/versions/draft",
        headers={"Authorization": f"Bearer {token}"},
        json={"definition": {"inputs": [], "steps": [], "outputs": [], "parameters": {}}},
    )
    assert no_draft_update.status_code == 409

    official_run = client.post(
        f"/api/v1/pipelines/{pipeline['id']}/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={"trigger_type": "manual", "is_dry_run": False},
    )
    assert official_run.status_code == 201
    assert official_run.json()["pipeline_version_id"] == published.json()["id"]
    assert official_run.json()["status"] == "queued"
    run_status = client.get(
        f"/api/v1/pipelines/{pipeline['id']}/runs/{official_run.json()['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert run_status.status_code == 200
    assert run_status.json()["status"] == "queued"
    details = client.get(
        f"/api/v1/pipelines/{pipeline['id']}/runs/{official_run.json()['id']}/details",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert details.status_code == 200
    assert details.json()["pipeline_version"]["definition_hash"] == published.json()["definition_hash"]
    assert details.json()["resolved_inputs"][0]["dataset_id"] == uploaded.json()["id"]
    assert details.json()["steps"] == []

    cancelled = client.post(
        f"/api/v1/pipelines/{pipeline['id']}/runs/{official_run.json()['id']}/cancel",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    retried = client.post(
        f"/api/v1/pipelines/{pipeline['id']}/runs/{official_run.json()['id']}/retry",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert retried.status_code == 201
    assert retried.json()["id"] != official_run.json()["id"]
    assert retried.json()["pipeline_version_id"] == official_run.json()["pipeline_version_id"]
    assert retried.json()["runtime_parameters"]["retry_of_run_id"] == official_run.json()["id"]
    history = client.get(
        "/api/v1/pipelines/runs/history?limit=1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert history.status_code == 200
    assert [item["id"] for item in history.json()] == [retried.json()["id"]]
    assert "events" not in history.json()[0]
    assert "output_manifest" not in history.json()[0]
    assert "runtime_parameters" not in history.json()[0]


def test_select_at_run_requires_and_audits_a_concrete_dataset_version(monkeypatch) -> None:
    from app.worker.tasks import execute_pipeline_run

    monkeypatch.setattr(execute_pipeline_run, "delay", lambda run_id: None)
    client = TestClient(create_app())
    token = _register(client, "versioned-input")
    headers = {"Authorization": f"Bearer {token}"}
    business_case = _create_business_case(client, token)
    first_response = client.post(
        "/api/v1/datasets/upload",
        headers=headers,
        data={"name": "Iris"},
        files={"file": ("iris-v1.csv", b"id,species\n1,setosa\n", "text/csv")},
    )
    assert first_response.status_code == 201
    first = first_response.json()
    second_response = client.post(
        "/api/v1/datasets/upload",
        headers=headers,
        data={"logical_id": first["logical_id"]},
        files={"file": ("iris-v2.csv", b"id,species\n1,setosa\n2,versicolor\n", "text/csv")},
    )
    assert second_response.status_code == 201
    second = second_response.json()
    definition = {
        "contract_version": "1.0",
        "inputs": [{
            "input_id": "source",
            "dataset_id": first["logical_id"],
            "output_port_id": "out",
            "version_policy": "select_at_run",
        }],
        "steps": [],
        "outputs": [{
            "output_id": "result",
            "input": {"node_id": "source", "port_id": "out"},
            "materialization": "dataset",
            "write_mode": "replace",
            "dataset_name": "Iris output",
            "business_case_role": "source",
        }],
        "parameters": {},
    }
    pipeline_response = client.post(
        "/api/v1/pipelines",
        headers=headers,
        json={
            "business_case_id": business_case["id"],
            "name": "Version-aware Iris",
            "type": "data_preparation",
            "definition": definition,
        },
    )
    assert pipeline_response.status_code == 201
    pipeline = pipeline_response.json()
    published = client.post(
        f"/api/v1/pipelines/{pipeline['id']}/versions/draft/publish",
        headers=headers,
    )
    assert published.status_code == 200

    missing = client.post(
        f"/api/v1/pipelines/{pipeline['id']}/runs",
        headers=headers,
        json={"trigger_type": "manual", "is_dry_run": False},
    )
    assert missing.status_code == 422

    selected = client.post(
        f"/api/v1/pipelines/{pipeline['id']}/runs",
        headers=headers,
        json={
            "trigger_type": "manual",
            "is_dry_run": False,
            "input_versions": {"de_1:source": first["id"]},
        },
    )
    assert selected.status_code == 201
    resolved = selected.json()["runtime_parameters"]["resolved_input_versions"]["de_1:source"]
    assert resolved["logical_id"] == first["logical_id"]
    assert resolved["dataset_id"] == first["id"]
    assert resolved["version_number"] == 1
    assert resolved["dataset_id"] != second["id"]


def test_business_case_and_pipeline_are_owner_scoped() -> None:
    client = TestClient(create_app())
    token_a = _register(client, "alice")
    token_b = _register(client, "bob")
    business_case = _create_business_case(client, token_a)

    other_user_get = client.get(
        f"/api/v1/business-cases/{business_case['id']}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert other_user_get.status_code == 404

    other_user_pipeline = client.post(
        "/api/v1/pipelines",
        headers={"Authorization": f"Bearer {token_b}"},
        json={
            "business_case_id": business_case["id"],
            "name": "Unauthorized pipeline",
            "type": "custom",
        },
    )
    assert other_user_pipeline.status_code == 404


def test_pipeline_name_can_be_changed_without_creating_a_new_version() -> None:
    client = TestClient(create_app())
    token = _register(client, "alice")
    headers = {"Authorization": f"Bearer {token}"}
    business_case = _create_business_case(client, token)
    created = client.post(
        "/api/v1/pipelines",
        headers=headers,
        json={
            "business_case_id": business_case["id"],
            "name": "Iris-DE",
            "type": "custom",
        },
    )
    assert created.status_code == 201
    pipeline_id = created.json()["id"]
    versions_before = client.get(
        f"/api/v1/pipelines/{pipeline_id}/versions",
        headers=headers,
    ).json()

    renamed = client.patch(
        f"/api/v1/pipelines/{pipeline_id}",
        headers=headers,
        json={
            "name": "  Iris training and operations  ",
            "description": "End-to-end governed workflow",
            "type": "training",
        },
    )

    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Iris training and operations"
    assert renamed.json()["description"] == "End-to-end governed workflow"
    assert renamed.json()["type"] == "training"
    assert renamed.json()["updated_by"] == created.json()["owner_id"]
    versions_after = client.get(
        f"/api/v1/pipelines/{pipeline_id}/versions",
        headers=headers,
    ).json()
    assert [(item["id"], item["definition_hash"]) for item in versions_after] == [
        (item["id"], item["definition_hash"]) for item in versions_before
    ]

    blank = client.patch(
        f"/api/v1/pipelines/{pipeline_id}",
        headers=headers,
        json={"name": "   "},
    )
    assert blank.status_code == 422


def test_pipeline_can_be_copied_as_editable_draft_and_only_deleted_without_runs(
    monkeypatch,
) -> None:
    from app.worker.tasks import execute_pipeline_run

    monkeypatch.setattr(execute_pipeline_run, "delay", lambda run_id: None)
    client = TestClient(create_app())
    token = _register(client, "pipeline-copy")
    other_token = _register(client, "pipeline-copy-other")
    headers = {"Authorization": f"Bearer {token}"}
    other_headers = {"Authorization": f"Bearer {other_token}"}
    business_case = _create_business_case(client, token)
    uploaded = client.post(
        "/api/v1/datasets/upload",
        headers=headers,
        data={"name": "Reusable pipeline input"},
        files={"file": ("copy-source.csv", b"id,value\n1,10\n", "text/csv")},
    )
    assert uploaded.status_code == 201
    definition = {
        "contract_version": "1.0",
        "inputs": [{
            "input_id": "source",
            "dataset_id": uploaded.json()["logical_id"],
            "output_port_id": "out",
        }],
        "steps": [],
        "outputs": [{
            "output_id": "result",
            "input": {"node_id": "source", "port_id": "out"},
            "materialization": "temporary",
            "write_mode": "replace",
        }],
        "parameters": {"variant": "challenger"},
    }
    created = client.post(
        "/api/v1/pipelines",
        headers=headers,
        json={
            "business_case_id": business_case["id"],
            "name": "Reusable DE and FE",
            "description": "Shared preparation workflow",
            "type": "training",
            "definition": definition,
        },
    )
    assert created.status_code == 201
    source = created.json()

    copied = client.post(
        f"/api/v1/pipelines/{source['id']}/copy",
        headers=headers,
        json={"name": "  Challenger model pipeline  "},
    )
    assert copied.status_code == 201
    copy = copied.json()
    assert copy["id"] != source["id"]
    assert copy["name"] == "Challenger model pipeline"
    assert copy["business_case_id"] == source["business_case_id"]
    assert copy["description"] == source["description"]
    assert copy["type"] == source["type"]
    assert copy["status"] == "draft"

    copied_versions = client.get(
        f"/api/v1/pipelines/{copy['id']}/versions",
        headers=headers,
    )
    assert copied_versions.status_code == 200
    assert len(copied_versions.json()) == 1
    copied_draft = copied_versions.json()[0]
    assert copied_draft["version_number"] == 1
    assert copied_draft["status"] == "draft"
    nested_definition = copied_draft["definition"]["steps"][0]["config"]["definition"]
    assert nested_definition["parameters"]["variant"] == "challenger"

    forbidden_copy = client.post(
        f"/api/v1/pipelines/{source['id']}/copy",
        headers=other_headers,
        json={"name": "Stolen pipeline"},
    )
    assert forbidden_copy.status_code == 404

    deleted = client.delete(f"/api/v1/pipelines/{copy['id']}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json() == {"action": "deleted"}
    assert client.get(f"/api/v1/pipelines/{copy['id']}", headers=headers).status_code == 404
    assert client.get(
        f"/api/v1/pipelines/{copy['id']}/versions",
        headers=headers,
    ).status_code == 404

    run = client.post(
        f"/api/v1/pipelines/{source['id']}/runs",
        headers=headers,
        json={"trigger_type": "manual", "is_dry_run": True},
    )
    assert run.status_code == 201
    deprecated = client.delete(f"/api/v1/pipelines/{source['id']}", headers=headers)
    assert deprecated.status_code == 200
    assert deprecated.json() == {"action": "deprecated"}
    preserved = client.get(f"/api/v1/pipelines/{source['id']}", headers=headers)
    assert preserved.status_code == 200
    assert preserved.json()["status"] == "deprecated"
    assert client.get(
        f"/api/v1/pipelines/{source['id']}/runs/{run.json()['id']}",
        headers=headers,
    ).status_code == 200
    assert client.patch(
        f"/api/v1/pipelines/{source['id']}",
        headers=headers,
        json={"name": "Should not change"},
    ).status_code == 409
    assert client.post(
        f"/api/v1/pipelines/{source['id']}/runs",
        headers=headers,
        json={"trigger_type": "manual", "is_dry_run": True},
    ).status_code == 409

    forbidden_delete = client.delete(
        f"/api/v1/pipelines/{source['id']}",
        headers=other_headers,
    )
    assert forbidden_delete.status_code == 404


def test_business_case_and_pipeline_survive_app_restart_and_relogin() -> None:
    client = TestClient(create_app())
    email = f"alice-{uuid4()}@example.com"
    password = "password123"
    register = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "display_name": "Alice"},
    )
    assert register.status_code == 201
    token = register.json()["access_token"]
    business_case = _create_business_case(client, token)
    pipeline = client.post(
        "/api/v1/pipelines",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "business_case_id": business_case["id"],
            "name": "Persistent FE",
            "type": "feature_engineering",
            "definition": {"inputs": [], "steps": [], "outputs": [], "parameters": {}},
        },
    )
    assert pipeline.status_code == 201
    pipeline_id = pipeline.json()["id"]

    restarted_client = TestClient(create_app())
    login = restarted_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200
    restarted_token = login.json()["access_token"]

    business_cases = restarted_client.get(
        "/api/v1/business-cases",
        headers={"Authorization": f"Bearer {restarted_token}"},
    )
    assert business_cases.status_code == 200
    assert business_case["id"] in {item["id"] for item in business_cases.json()}

    pipelines = restarted_client.get(
        "/api/v1/pipelines",
        headers={"Authorization": f"Bearer {restarted_token}"},
    )
    assert pipelines.status_code == 200
    assert pipeline_id in {item["id"] for item in pipelines.json()}

    versions = restarted_client.get(
        f"/api/v1/pipelines/{pipeline_id}/versions",
        headers={"Authorization": f"Bearer {restarted_token}"},
    )
    assert versions.status_code == 200
    assert versions.json()[0]["version_number"] == 1
    assert versions.json()[0]["definition_hash"]


def test_pipeline_dry_run_executes_through_worker_on_full_uploaded_csv(
    monkeypatch,
) -> None:
    from app.worker.tasks import execute_pipeline_run

    monkeypatch.setattr(
        execute_pipeline_run,
        "delay",
        lambda run_id: None,
    )
    client = TestClient(create_app())
    token = _register(client, "alice")
    headers = {"Authorization": f"Bearer {token}"}
    business_case = _create_business_case(client, token)
    upload = client.post(
        "/api/v1/datasets/upload",
        headers=headers,
        data={"name": "Stage 1 execution input"},
        files={
            "file": (
                "orders.csv",
                b"order_id,amount\n1,25\n2,100\n3,175\n",
                "text/csv",
            )
        },
    )
    assert upload.status_code == 201
    dataset_id = upload.json()["id"]
    definition = {
        "contract_version": "1.0",
        "inputs": [{"input_id": "orders", "dataset_id": dataset_id, "output_port_id": "out"}],
        "steps": [
            {
                "step_id": "user-written-sql",
                "type": "custom_sql",
                "inputs": [{"port_id": "input", "source": {"node_id": "orders", "port_id": "out"}}],
                "output_port_id": "out",
                "config": {
                    "sql": "SELECT order_id, amount * 1.23 AS gross_amount FROM input WHERE amount >= 100",
                },
            }
        ],
        "outputs": [
            {
                "output_id": "result",
                "input": {"node_id": "user-written-sql", "port_id": "out"},
                "materialization": "dataset",
                "write_mode": "replace",
                "dataset_name": "Prepared orders",
                "business_case_role": "training",
            }
        ],
        "parameters": {},
    }
    created = client.post(
        "/api/v1/pipelines",
        headers=headers,
        json={
            "business_case_id": business_case["id"],
            "name": "Executable DE pipeline",
            "type": "data_preparation",
            "definition": definition,
        },
    )
    assert created.status_code == 201
    pipeline_id = created.json()["id"]

    queued = client.post(
        f"/api/v1/pipelines/{pipeline_id}/runs",
        headers=headers,
        json={"trigger_type": "manual", "is_dry_run": True, "step_id": "de_1"},
    )
    assert queued.status_code == 201
    assert queued.json()["status"] == "queued"
    run_id = queued.json()["id"]
    execute_pipeline_run.run(run_id)

    deadline = time.monotonic() + 20
    run = queued.json()
    while run["status"] in {"queued", "running"} and time.monotonic() < deadline:
        time.sleep(0.1)
        response = client.get(f"/api/v1/pipelines/{pipeline_id}/runs/{run_id}", headers=headers)
        assert response.status_code == 200
        run = response.json()

    assert run["status"] == "succeeded", run["error_message"]
    assert run["input_row_count"] == 3
    assert run["processed_row_count"] == 3
    assert run["output_row_count"] == 2
    assert run["is_dry_run"] is True
    assert run["requested_step_id"] == "de_1"
    assert run["output_artifact_ids"] == []
    assert run["output_manifest"][0]["materialization"] == "temporary"
    assert run["output_manifest"][0]["data_scope"] == "full"
    assert run["output_manifest"][0]["row_count"] == 2
    assert run["output_manifest"][0]["preview"]["returned_count"] == 2
    output_id = run["output_manifest"][0]["output_id"]
    paged_preview = client.get(
        f"/api/v1/pipelines/{pipeline_id}/runs/{run_id}/preview",
        headers=headers,
        params={"output_id": output_id, "limit": 1, "offset": 1},
    )
    assert paged_preview.status_code == 200
    assert paged_preview.json()["returned_count"] == 1
    assert paged_preview.json()["has_previous"] is True
    assert paged_preview.json()["has_next"] is False
    output_profile = client.get(
        f"/api/v1/pipelines/{pipeline_id}/runs/{run_id}/profile",
        headers=headers,
        params={"output_id": output_id, "top_n": 5},
    )
    assert output_profile.status_code == 200
    assert output_profile.json()["row_count"] == 2
    assert {item["name"] for item in output_profile.json()["columns"]} == {"order_id", "gross_amount"}
    temporary_asset_id = f"dry-run-output:{run_id}:{output_id}"
    analysis_preview = client.get(
        f"/api/v1/datasets/{temporary_asset_id}/preview",
        headers=headers,
        params={"limit": 10},
    )
    assert analysis_preview.status_code == 200
    assert analysis_preview.json()["row_count"] == 2
    assert analysis_preview.json()["returned_count"] == 2
    analysis_visualization = client.post(
        f"/api/v1/datasets/{temporary_asset_id}/visualization",
        headers=headers,
        json={"kind": "histogram", "x": "gross_amount", "bins": 20},
    )
    assert analysis_visualization.status_code == 200
    assert analysis_visualization.json()["scanned_row_count"] == 2
    assert analysis_visualization.json()["execution_mode"] == "full_dataset"
    profile_job = client.post(
        f"/api/v1/datasets/{temporary_asset_id}/descriptive-profile",
        headers=headers,
        json={"include_target_relations": False, "include_segments": False},
    )
    assert profile_job.status_code == 202
    profile_status = profile_job.json()
    profile_deadline = time.monotonic() + 20
    while profile_status["status"] in {"queued", "running"} and time.monotonic() < profile_deadline:
        time.sleep(0.1)
        profile_status = client.get(
            f"/api/v1/datasets/{temporary_asset_id}/descriptive-profile/{profile_status['job_id']}",
            headers=headers,
        ).json()
    assert profile_status["status"] == "completed", profile_status["error"]
    assert profile_status["result"]["row_count"] == 2
    assert all(item["id"] != temporary_asset_id for item in client.get("/api/v1/datasets", headers=headers).json())

    published = client.post(
        f"/api/v1/pipelines/{pipeline_id}/versions/draft/publish",
        headers=headers,
    )
    assert published.status_code == 200
    official = client.post(
        f"/api/v1/pipelines/{pipeline_id}/runs",
        headers=headers,
        json={"trigger_type": "manual", "is_dry_run": False},
    )
    assert official.status_code == 201, official.text
    official_run = official.json()
    execute_pipeline_run.run(official_run["id"])
    deadline = time.monotonic() + 20
    while official_run["status"] in {"queued", "running"} and time.monotonic() < deadline:
        time.sleep(0.1)
        official_run = client.get(
            f"/api/v1/pipelines/{pipeline_id}/runs/{official_run['id']}",
            headers=headers,
        ).json()

    assert official_run["status"] == "succeeded", official_run["error_message"]
    assert official_run["output_artifact_ids"]
    official_output = official_run["output_manifest"][0]
    assert official_output["materialization"] == "dataset"
    assert official_output["dataset_id"]
    assert official_output["artifact_id"] in official_run["output_artifact_ids"]
    datasets = client.get("/api/v1/datasets", headers=headers)
    persisted = next(item for item in datasets.json() if item["id"] == official_output["dataset_id"])
    assert persisted["name"] == "Prepared orders"
    assert persisted["format"] == "parquet"
    assert persisted["row_count"] == 2
    lineage = persisted["metadata"]["lineage"]
    assert lineage["pipeline_run_id"] == official_run["id"]
    assert lineage["pipeline_version_id"] == published.json()["id"]
    assert lineage["pipeline_step_id"] == "de_1"
    assert lineage["input_artifact_ids"]
    assert lineage["row_count"] == 2
    attachments = client.get(
        f"/api/v1/business-cases/{business_case['id']}/data-attachments",
        headers=headers,
    )
    output_attachment = next(
        item for item in attachments.json() if item["data_asset_id"] == official_output["dataset_id"]
    )
    assert output_attachment["role"] == "training"
    preview = client.get(
        f"/api/v1/datasets/{official_output['dataset_id']}/preview?limit=10",
        headers=headers,
    )
    assert preview.status_code == 200
    assert preview.json()["row_count"] == 2
