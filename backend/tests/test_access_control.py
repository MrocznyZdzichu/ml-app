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
    new_version = client.post(
        "/api/v1/datasets/upload", headers=bob_headers,
        data={"logical_id": dataset["logical_id"]},
        files={"file": ("customers-v2.csv", b"id,churn\n1,0\n2,1\n3,0\n", "text/csv")},
    )
    assert new_version.status_code == 201, new_version.text
    assert new_version.json()["owner_id"] == alice["user_id"]
    assert new_version.json()["uploaded_by"] == bob["user_id"]
    assert new_version.json()["version_number"] == 2
    visible_versions = client.get(
        f"/api/v1/datasets/{dataset['logical_id']}/versions", headers=bob_headers
    )
    assert visible_versions.status_code == 200, visible_versions.text
    assert [item["version_number"] for item in visible_versions.json()] == [1, 2]
    assert new_version.json()["id"] in {
        item["id"] for item in client.get("/api/v1/datasets", headers=bob_headers).json()
    }
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


def test_global_business_case_directory_and_permission_request_workflow() -> None:
    client = TestClient(create_app())
    alice, alice_headers = register(client, "alice")
    bob, bob_headers = register(client, "bob")
    manager, manager_headers = register(client, "dupe")
    rejected_user, rejected_headers = register(client, "roles-owner")
    business_case = create_case(client, alice_headers)

    directory = client.get(
        "/api/v1/business-cases/catalog/page",
        headers=bob_headers,
        params={"search": "Shared churn"},
    )
    assert directory.status_code == 200, directory.text
    catalog_entry = next(
        item
        for item in directory.json()["items"]
        if item["id"] == business_case["id"]
    )
    assert catalog_entry == {
        "id": business_case["id"],
        "name": "Shared churn",
        "status": "draft",
        "access_role": "",
        "request_status": "",
    }
    assert "description" not in catalog_entry

    group = client.post(
        "/api/v1/sharing/groups",
        headers=alice_headers,
        json={"name": f"BC managers {uuid4()}", "description": ""},
    ).json()
    assert client.put(
        f"/api/v1/sharing/groups/{group['id']}/members",
        headers=alice_headers,
        json={"user_id": manager["user_id"], "membership_role": "member"},
    ).status_code == 200
    assert client.put(
        f"/api/v1/sharing/business-cases/{business_case['id']}/grants",
        headers=alice_headers,
        json={
            "subject_type": "group",
            "subject_id": group["id"],
            "access_role": "manager",
        },
    ).status_code == 200

    first_request = client.post(
        f"/api/v1/sharing/business-cases/{business_case['id']}/access-requests",
        headers=bob_headers,
        json={"requested_role": "reader", "justification": "I maintain the churn report"},
    )
    assert first_request.status_code == 201, first_request.text
    assert first_request.json()["status"] == "pending"
    duplicate = client.post(
        f"/api/v1/sharing/business-cases/{business_case['id']}/access-requests",
        headers=bob_headers,
        json={"requested_role": "contributor", "justification": "Duplicate"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "business_case_access_request_pending"

    second_request = client.post(
        f"/api/v1/sharing/business-cases/{business_case['id']}/access-requests",
        headers=rejected_headers,
        json={"requested_role": "report_viewer", "justification": "I need the published report"},
    )
    assert second_request.status_code == 201, second_request.text

    bob_catalog = client.get(
        "/api/v1/business-cases/catalog/page",
        headers=bob_headers,
        params={"search": "Shared churn"},
    ).json()["items"]
    assert next(item for item in bob_catalog if item["id"] == business_case["id"])[
        "request_status"
    ] == "pending"

    incoming = client.get(
        "/api/v1/sharing/access-requests/page",
        headers=manager_headers,
        params={"box": "incoming", "status": "pending"},
    )
    assert incoming.status_code == 200, incoming.text
    incoming_ids = {item["id"] for item in incoming.json()["items"]}
    assert first_request.json()["id"] in incoming_ids
    assert second_request.json()["id"] in incoming_ids

    mine = client.get(
        "/api/v1/sharing/access-requests/page",
        headers=bob_headers,
        params={"box": "mine"},
    )
    assert mine.status_code == 200
    assert [item["id"] for item in mine.json()["items"]] == [first_request.json()["id"]]

    approved = client.post(
        f"/api/v1/sharing/access-requests/{first_request.json()['id']}/approve",
        headers=manager_headers,
        json={"access_role": "contributor", "decision_note": "Approved for delivery work"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["granted_role"] == "contributor"
    visible = client.get("/api/v1/business-cases", headers=bob_headers).json()
    assert next(item for item in visible if item["id"] == business_case["id"])[
        "access_role"
    ] == "contributor"
    grant_page = client.get(
        f"/api/v1/sharing/business-cases/{business_case['id']}/grants/page",
        headers=manager_headers,
    )
    assert grant_page.status_code == 200, grant_page.text
    grants_by_subject = {
        item["subject_id"]: item for item in grant_page.json()["items"]
    }
    assert grants_by_subject[bob["user_id"]]["subject_name"] == "Bob"
    assert grants_by_subject[bob["user_id"]]["subject_email"] == bob["email"]
    assert (
        grants_by_subject[bob["user_id"]]["business_case_name"]
        == business_case["name"]
    )
    assert grants_by_subject[group["id"]]["subject_name"] == group["name"]
    assert grants_by_subject[group["id"]]["subject_email"] == ""

    rejected = client.post(
        f"/api/v1/sharing/access-requests/{second_request.json()['id']}/reject",
        headers=manager_headers,
        json={"decision_note": "Use the shared aggregate instead"},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"
    assert client.get("/api/v1/business-cases", headers=rejected_headers).json() == []

    submitted_history = client.get(
        "/api/v1/sharing/access-requests/page",
        headers=bob_headers,
        params={"box": "submitted_history"},
    )
    assert submitted_history.status_code == 200, submitted_history.text
    assert [item["id"] for item in submitted_history.json()["items"]] == [
        first_request.json()["id"]
    ]

    handled_history = client.get(
        "/api/v1/sharing/access-requests/page",
        headers=manager_headers,
        params={"box": "handled"},
    )
    assert handled_history.status_code == 200, handled_history.text
    assert {item["id"] for item in handled_history.json()["items"]} == {
        first_request.json()["id"], second_request.json()["id"]
    }
    assert client.get(
        "/api/v1/sharing/access-requests/page",
        headers=bob_headers,
        params={"box": "handled"},
    ).json()["items"] == []
    rejected_history = client.get(
        "/api/v1/sharing/access-requests/page",
        headers=manager_headers,
        params={"box": "handled", "status": "rejected"},
    )
    assert [item["id"] for item in rejected_history.json()["items"]] == [
        second_request.json()["id"]
    ]

    repeated_decision = client.post(
        f"/api/v1/sharing/access-requests/{first_request.json()['id']}/approve",
        headers=alice_headers,
        json={"access_role": "reader"},
    )
    assert repeated_decision.status_code == 409
    assert repeated_decision.json()["code"] == "access_request_already_decided"
