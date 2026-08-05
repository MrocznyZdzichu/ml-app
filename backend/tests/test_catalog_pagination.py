from secrets import token_hex
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app


def _register(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"catalog-{uuid4()}@example.com",
            "password": "password123",
            "display_name": "Catalog tester",
        },
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def test_business_case_page_is_bounded_searchable_and_exact() -> None:
    client = TestClient(create_app())
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    marker = token_hex(16)
    for index in range(4):
        response = client.post(
            "/api/v1/business-cases",
            headers=headers,
            json={
                "name": f"Pagination {marker} {index}",
                "problem_type": "custom",
            },
        )
        assert response.status_code == 201

    first = client.get(
        "/api/v1/business-cases/page",
        headers=headers,
        params={"limit": 2, "offset": 0, "search": marker},
    )
    second = client.get(
        "/api/v1/business-cases/page",
        headers=headers,
        params={
            "limit": 2,
            "offset": 2,
            "search": marker,
            "manageable_only": True,
        },
    )

    assert first.status_code == 200
    assert first.json()["total"] == 4
    assert len(first.json()["items"]) == 2
    assert first.json()["has_next"] is True
    assert second.status_code == 200
    assert second.json()["total"] == 4
    assert len(second.json()["items"]) == 2
    assert second.json()["has_next"] is False
    assert {
        item["id"] for item in first.json()["items"]
    }.isdisjoint(item["id"] for item in second.json()["items"])


def test_uploaded_only_dataset_family_page_uses_text_json_metadata_filter() -> None:
    client = TestClient(create_app())
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    marker = token_hex(16)

    uploaded = client.post(
        "/api/v1/datasets/upload",
        headers=headers,
        data={"name": f"Uploaded {marker}", "tags": "catalog-test"},
        files={"file": (f"{marker}.csv", b"id,value\n1,10\n", "text/csv")},
    )
    assert uploaded.status_code == 201

    page = client.get(
        "/api/v1/datasets/page",
        headers=headers,
        params={
            "limit": 20,
            "offset": 0,
            "search": marker,
            "asset_kind": "dataset",
            "families": True,
            "include_deleted": False,
            "uploaded_only": True,
        },
    )

    assert page.status_code == 200
    assert page.json()["total"] == 1
    assert page.json()["items"][0]["id"] == uploaded.json()["id"]
