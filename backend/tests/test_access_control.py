from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app


def register(client: TestClient, prefix: str):
    email = f"{prefix}-{uuid4()}@example.com"
    response = client.post("/api/v1/auth/register", json={
        "email": email, "password": "password123", "display_name": prefix.title(),
    })
    assert response.status_code == 201, response.text
    return response.json(), {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_case(client: TestClient, headers: dict[str, str]):
    response = client.post("/api/v1/business-cases", headers=headers, json={
        "name": "Shared churn", "description": "Access matrix test", "problem_type": "binary_classification",
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_root_bootstrap_open_registration_and_administration() -> None:
    client = TestClient(create_app())
    root_login = client.post("/api/v1/auth/login", json={"login": "root", "password": "toor"})
    assert root_login.status_code == 200, root_login.text
    root_headers = {"Authorization": f"Bearer {root_login.json()['access_token']}"}
    root_profile = client.get("/api/v1/auth/me", headers=root_headers).json()
    assert root_profile["login_name"] == "root"
    assert "administrator" in root_profile["roles"]

    account, account_headers = register(client, "alice")
    profile = client.get("/api/v1/auth/me", headers=account_headers).json()
    assert profile["roles"] == ["user"]

    users = client.get("/api/v1/users", headers=root_headers)
    assert users.status_code == 200
    assert account["user_id"] in {item["user_id"] for item in users.json()}

    promoted = client.patch(f"/api/v1/users/{account['user_id']}", headers=root_headers, json={
        "roles": ["user", "governance_steward"], "is_active": True,
    })
    assert promoted.status_code == 200
    assert "governance_steward" in promoted.json()["roles"]
    assert client.get("/api/v1/auth/me", headers=account_headers).status_code == 401

    root_demote = client.patch("/api/v1/users/root", headers=root_headers, json={
        "roles": ["user"], "is_active": True,
    })
    assert root_demote.status_code == 409


def test_business_case_access_levels_and_shared_execution() -> None:
    client = TestClient(create_app())
    alice, alice_headers = register(client, "alice")
    bob, bob_headers = register(client, "bob")
    business_case = create_case(client, alice_headers)

    upload = client.post(
        "/api/v1/datasets/upload", headers=alice_headers,
        data={"name": "Customers"},
        files={"file": ("customers.csv", b"id,churn\n1,0\n2,1\n", "text/csv")},
    )
    assert upload.status_code == 201
    dataset = upload.json()
    attachment = client.post(
        f"/api/v1/business-cases/{business_case['id']}/data-attachments",
        headers=alice_headers,
        json={"data_asset_id": dataset["id"], "data_asset_kind": "dataset", "role": "training"},
    )
    assert attachment.status_code == 201, attachment.text

    assert client.get("/api/v1/business-cases", headers=bob_headers).json() == []
    report_grant = client.put(
        f"/api/v1/sharing/business-cases/{business_case['id']}/grants",
        headers=alice_headers,
        json={"subject_type": "user", "subject_id": bob["user_id"], "access_role": "report_viewer"},
    )
    assert report_grant.status_code == 200, report_grant.text
    assert client.get("/api/v1/business-cases", headers=bob_headers).json()[0]["access_role"] == "report_viewer"
    assert client.get("/api/v1/datasets", headers=bob_headers).json() == []
    assert client.get(
        f"/api/v1/business-cases/{business_case['id']}/data-attachments", headers=bob_headers
    ).status_code == 404
    assert client.get("/api/v1/pipelines", headers=bob_headers).json() == []

    reader_grant = client.put(
        f"/api/v1/sharing/business-cases/{business_case['id']}/grants",
        headers=alice_headers,
        json={"subject_type": "user", "subject_id": bob["user_id"], "access_role": "reader"},
    )
    assert reader_grant.status_code == 200
    assert dataset["id"] in {item["id"] for item in client.get("/api/v1/datasets", headers=bob_headers).json()}
    forbidden_create = client.post("/api/v1/pipelines", headers=bob_headers, json={
        "business_case_id": business_case["id"], "name": "Reader pipeline", "type": "custom",
    })
    assert forbidden_create.status_code == 404

    contributor_grant = client.put(
        f"/api/v1/sharing/business-cases/{business_case['id']}/grants",
        headers=alice_headers,
        json={"subject_type": "user", "subject_id": bob["user_id"], "access_role": "contributor"},
    )
    assert contributor_grant.status_code == 200
    created = client.post("/api/v1/pipelines", headers=bob_headers, json={
        "business_case_id": business_case["id"], "name": "Shared pipeline", "type": "custom",
    })
    assert created.status_code == 201, created.text
    assert created.json()["owner_id"] == alice["user_id"]
    assert created.json()["created_by"] == bob["user_id"]

    transferred = client.post(
        f"/api/v1/business-cases/{business_case['id']}/transfer-ownership",
        headers=alice_headers,
        json={"new_owner_id": bob["user_id"], "reason": "Operational handover"},
    )
    assert transferred.status_code == 200, transferred.text
    assert transferred.json()["owner_id"] == bob["user_id"]
    assert created.json()["id"] in {item["id"] for item in client.get("/api/v1/pipelines", headers=bob_headers).json()}
    assert client.get("/api/v1/business-cases", headers=alice_headers).json() == []


def test_group_grant_and_direct_loose_dataset_exception() -> None:
    client = TestClient(create_app())
    alice, alice_headers = register(client, "alice")
    bob, bob_headers = register(client, "bob")
    business_case = create_case(client, alice_headers)

    group = client.post("/api/v1/sharing/groups", headers=alice_headers, json={
        "name": f"Analysts {uuid4()}", "description": "Shared analyst team",
    })
    assert group.status_code == 201
    group_id = group.json()["id"]
    memberships = client.get(f"/api/v1/sharing/groups/{group_id}/members", headers=alice_headers)
    assert memberships.status_code == 200
    assert any(
        item["user_id"] == alice["user_id"] and item["membership_role"] == "owner"
        for item in memberships.json()
    )
    assert client.delete(
        f"/api/v1/sharing/groups/{group_id}/members/{alice['user_id']}", headers=alice_headers
    ).status_code == 409
    directory = client.get("/api/v1/sharing/directory/users", headers=alice_headers)
    assert directory.status_code == 200
    assert all(item["id"] != "root" for item in directory.json())
    member = client.put(f"/api/v1/sharing/groups/{group_id}/members", headers=alice_headers, json={
        "user_id": bob["user_id"], "membership_role": "member",
    })
    assert member.status_code == 200
    grant = client.put(f"/api/v1/sharing/business-cases/{business_case['id']}/grants", headers=alice_headers, json={
        "subject_type": "group", "subject_id": group_id, "access_role": "reader",
    })
    assert grant.status_code == 200
    assert business_case["id"] in {item["id"] for item in client.get("/api/v1/business-cases", headers=bob_headers).json()}

    upload = client.post(
        "/api/v1/datasets/upload", headers=alice_headers,
        data={"name": "Loose lookup"},
        files={"file": ("lookup.csv", b"id,label\n1,A\n", "text/csv")},
    )
    assert upload.status_code == 201
    dataset = upload.json()
    direct = client.put("/api/v1/sharing/resources/grants", headers=alice_headers, json={
        "resource_kind": "dataset", "resource_id": dataset["id"],
        "subject_type": "user", "subject_id": bob["user_id"], "access_role": "reader",
    })
    assert direct.status_code == 200, direct.text
    assert dataset["id"] in {item["id"] for item in client.get("/api/v1/datasets", headers=bob_headers).json()}
    assert client.patch(
        f"/api/v1/datasets/{dataset['id']}/metadata", headers=bob_headers, json={"metadata": {"x": 1}}
    ).status_code == 404

    direct_editor = client.put("/api/v1/sharing/resources/grants", headers=alice_headers, json={
        "resource_kind": "dataset", "resource_id": dataset["id"],
        "subject_type": "user", "subject_id": bob["user_id"], "access_role": "editor",
    })
    assert direct_editor.status_code == 200
    assert client.patch(
        f"/api/v1/datasets/{dataset['id']}/metadata", headers=bob_headers, json={"metadata": {"shared": True}}
    ).status_code == 200
