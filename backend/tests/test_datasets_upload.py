from pathlib import Path
from uuid import uuid4

import duckdb
from fastapi.testclient import TestClient

from app.main import create_app
from app.modules.datasets.repository import PostgresDatasetRepository


def _register(client: TestClient, name: str) -> str:
    response = _register_response(client, name)
    return response.json()["access_token"]


def _register_response(client: TestClient, name: str):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"{name}-{uuid4()}@example.com",
            "password": "password123",
            "display_name": name.title(),
        },
    )
    assert response.status_code == 201
    return response


def test_csv_upload_stores_metadata_and_is_private_by_default() -> None:
    client = TestClient(create_app())
    token_a = _register(client, "alice")
    token_b = _register(client, "bob")
    csv_body = b"sepal_length,sepal_width,species\n5.1,3.5,setosa\n4.9,3.0,setosa\n"

    upload = client.post(
        "/api/v1/datasets/upload",
        headers={"Authorization": f"Bearer {token_a}"},
        data={"name": "iris-sample", "description": "Small Iris sample", "tags": "iris,test"},
        files={"file": ("iris.csv", csv_body, "text/csv")},
    )

    assert upload.status_code == 201
    dataset = upload.json()
    assert dataset["name"] == "iris-sample"
    assert dataset["owner_id"] != ""
    assert dataset["source_type"] == "file"
    assert dataset["format"] == "csv"
    assert dataset["original_filename"] == "iris.csv"
    assert dataset["file_size_bytes"] == len(csv_body)
    assert dataset["row_count"] == 2
    assert dataset["has_header"] is True
    assert dataset["uploaded_by"] == dataset["owner_id"]
    assert dataset["uploaded_at"] is not None
    assert dataset["status"] == "ready"
    assert dataset["tags"] == ["iris", "test"]
    assert dataset["location_uri"].endswith("/iris.csv")

    owned = client.get("/api/v1/datasets", headers={"Authorization": f"Bearer {token_a}"})
    assert dataset["id"] in {item["id"] for item in owned.json()}

    other_user_list = client.get("/api/v1/datasets", headers={"Authorization": f"Bearer {token_b}"})
    assert dataset["id"] not in {item["id"] for item in other_user_list.json()}

    other_user_get = client.get(
        f"/api/v1/datasets/{dataset['id']}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert other_user_get.status_code == 404

    persisted = PostgresDatasetRepository().get(dataset["id"])
    assert persisted is not None
    assert persisted.name == "iris-sample"
    assert persisted.row_count == 2
    assert persisted.has_header is True


def test_upload_can_create_an_immutable_version_of_a_logical_dataset() -> None:
    client = TestClient(create_app())
    token = _register(client, "version-owner")
    headers = {"Authorization": f"Bearer {token}"}

    first = client.post(
        "/api/v1/datasets/upload",
        headers=headers,
        data={"name": "Iris"},
        files={"file": ("iris-v1.csv", b"id,species\n1,setosa\n", "text/csv")},
    )
    assert first.status_code == 201
    first_dataset = first.json()
    assert first_dataset["logical_id"] != first_dataset["id"]
    assert first_dataset["version_number"] == 1

    second = client.post(
        "/api/v1/datasets/upload",
        headers=headers,
        data={"name": "Ignored rename", "logical_id": first_dataset["logical_id"]},
        files={"file": ("iris-v2.csv", b"id,species\n1,setosa\n2,versicolor\n", "text/csv")},
    )
    assert second.status_code == 201
    second_dataset = second.json()
    assert second_dataset["id"] != first_dataset["id"]
    assert second_dataset["logical_id"] == first_dataset["logical_id"]
    assert second_dataset["version_number"] == 2
    assert second_dataset["name"] == "Iris"
    assert second_dataset["row_count"] == 2

    versions = client.get(
        f"/api/v1/datasets/{first_dataset['logical_id']}/versions",
        headers=headers,
    )
    assert versions.status_code == 200
    assert [item["version_number"] for item in versions.json()] == [1, 2]

    latest = client.get(
        f"/api/v1/datasets/{first_dataset['logical_id']}",
        headers=headers,
    )
    assert latest.status_code == 200
    assert latest.json()["id"] == second_dataset["id"]


def test_parquet_upload_is_native_and_available_to_dataset_tools(tmp_path: Path) -> None:
    parquet_path = tmp_path / "customers.parquet"
    connection = duckdb.connect()
    connection.execute(
        "COPY ("
        "SELECT 1::BIGINT AS customer_id, 'north'::VARCHAR AS region, "
        "10.5::DOUBLE AS amount, true::BOOLEAN AS active, DATE '2026-01-02' AS joined "
        "UNION ALL "
        "SELECT 2, 'south', NULL, false, DATE '2026-02-03'"
        ") TO ? (FORMAT PARQUET)",
        [str(parquet_path)],
    )
    connection.close()
    parquet_body = parquet_path.read_bytes()
    client = TestClient(create_app())
    token = _register(client, "alice")
    headers = {"Authorization": f"Bearer {token}"}

    upload = client.post(
        "/api/v1/datasets/upload",
        headers=headers,
        data={"name": "customers-native", "description": "Native Parquet"},
        files={"file": ("customers.parquet", parquet_body, "application/vnd.apache.parquet")},
    )

    assert upload.status_code == 201, upload.text
    dataset = upload.json()
    assert dataset["format"] == "parquet"
    assert dataset["row_count"] == 2
    assert dataset["has_header"] is None
    assert dataset["file_size_bytes"] == len(parquet_body)
    assert dataset["location_uri"].endswith("/customers.parquet")
    assert dataset["metadata"]["source_schema"] == [
        {"name": "customer_id", "type": "number"},
        {"name": "region", "type": "text"},
        {"name": "amount", "type": "number"},
        {"name": "active", "type": "boolean"},
        {"name": "joined", "type": "date"},
    ]

    preview = client.get(
        f"/api/v1/datasets/{dataset['id']}/preview",
        headers=headers,
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["row_count"] == 2
    assert preview.json()["records"][0] == {
        "customer_id": 1,
        "region": "north",
        "amount": 10.5,
        "active": True,
        "joined": "2026-01-02",
    }

    query = client.post(
        f"/api/v1/datasets/{dataset['id']}/query",
        headers=headers,
        json={"sql": 'SELECT region, amount FROM "customers-native" WHERE active = true', "limit": 50},
    )
    assert query.status_code == 200, query.text
    assert query.json()["records"] == [{"region": "north", "amount": 10.5}]


def test_dataset_upload_rejects_unsupported_and_invalid_files() -> None:
    client = TestClient(create_app())
    token = _register(client, "alice")
    headers = {"Authorization": f"Bearer {token}"}

    unsupported = client.post(
        "/api/v1/datasets/upload",
        headers=headers,
        data={"name": "spreadsheet"},
        files={"file": ("dataset.xlsx", b"not-a-dataset", "application/octet-stream")},
    )
    assert unsupported.status_code == 400
    assert "Only .csv and .parquet" in unsupported.json()["detail"]

    invalid_parquet = client.post(
        "/api/v1/datasets/upload",
        headers=headers,
        data={"name": "broken"},
        files={"file": ("broken.parquet", b"not-parquet", "application/vnd.apache.parquet")},
    )
    assert invalid_parquet.status_code == 400
    assert "invalid or unreadable" in invalid_parquet.json()["detail"]


def test_dataset_delete_removes_file_and_keeps_deleted_metadata() -> None:
    client = TestClient(create_app())
    token = _register(client, "delete-owner")
    csv_body = b"feature,target\n1,A\n2,B\n"

    upload = client.post(
        "/api/v1/datasets/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={"name": "delete-me"},
        files={"file": ("delete-me.csv", csv_body, "text/csv")},
    )
    assert upload.status_code == 201
    dataset = upload.json()
    data_path = Path(dataset["location_uri"].removeprefix("file://"))
    assert data_path.exists()

    deleted = client.delete(
        f"/api/v1/datasets/{dataset['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert deleted.status_code == 200
    deleted_dataset = deleted.json()
    assert deleted_dataset["id"] == dataset["id"]
    assert deleted_dataset["status"] == "deleted"
    assert deleted_dataset["deleted_by"] == dataset["owner_id"]
    assert deleted_dataset["deleted_at"] is not None
    assert not data_path.exists()

    persisted = PostgresDatasetRepository().get(dataset["id"])
    assert persisted is not None
    assert persisted.status == "deleted"
    assert persisted.deleted_by == dataset["owner_id"]
    assert persisted.deleted_at is not None

    listed = client.get("/api/v1/datasets", headers={"Authorization": f"Bearer {token}"})
    listed_dataset = next(item for item in listed.json() if item["id"] == dataset["id"])
    assert listed_dataset["status"] == "deleted"
    assert listed_dataset["deleted_at"] is not None

    profile = client.post(
        f"/api/v1/datasets/{dataset['id']}/profile",
        headers={"Authorization": f"Bearer {token}"},
        json={"sample_size": 100},
    )
    assert profile.status_code == 409


def test_dataset_metadata_can_store_data_roles() -> None:
    client = TestClient(create_app())
    token = _register(client, "roles-owner")

    upload = client.post(
        "/api/v1/datasets/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={"name": "roles"},
        files={"file": ("roles.csv", b"customer_id,date,amount,target\n1,2026-01-01,10,yes\n", "text/csv")},
    )
    assert upload.status_code == 201
    dataset_id = upload.json()["id"]

    update = client.patch(
        f"/api/v1/datasets/{dataset_id}/metadata",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "metadata": {
                "data_roles": {
                    "dataset_roles": ["training", "targeted"],
                    "entity_id_column": "customer_id",
                    "timestamp_column": "date",
                    "period_column": "",
                    "target_column": "target",
                    "column_roles": {
                        "customer_id": "identifier",
                        "date": "timestamp",
                        "amount": "feature_continuous",
                        "target": "target",
                    },
                    "notes": "Initial analyst mapping",
                }
            }
        },
    )

    assert update.status_code == 200
    body = update.json()
    assert body["metadata"]["data_roles"]["dataset_roles"] == ["training", "targeted"]
    assert body["metadata"]["data_roles"]["column_roles"]["amount"] == "feature_continuous"

    persisted = PostgresDatasetRepository().get(dataset_id)
    assert persisted is not None
    assert persisted.metadata["data_roles"]["target_column"] == "target"


def test_dataset_metadata_patch_merges_existing_metadata() -> None:
    client = TestClient(create_app())
    token = _register(client, "metadata-merge-owner")

    upload = client.post(
        "/api/v1/datasets/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={"name": "metadata-merge"},
        files={"file": ("metadata-merge.csv", b"id,amount,target\n1,10,yes\n", "text/csv")},
    )
    assert upload.status_code == 201
    dataset_id = upload.json()["id"]

    first_update = client.patch(
        f"/api/v1/datasets/{dataset_id}/metadata",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "metadata": {
                "owner_notes": {"quality": "checked"},
                "data_roles": {
                    "dataset_roles": ["training"],
                    "target_column": "target",
                },
            }
        },
    )
    assert first_update.status_code == 200

    second_update = client.patch(
        f"/api/v1/datasets/{dataset_id}/metadata",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "metadata": {
                "data_roles": {
                    "column_roles": {
                        "id": "identifier",
                        "amount": "feature_continuous",
                    }
                }
            }
        },
    )

    assert second_update.status_code == 200
    metadata = second_update.json()["metadata"]
    assert metadata["owner_notes"] == {"quality": "checked"}
    assert metadata["data_roles"]["dataset_roles"] == ["training"]
    assert metadata["data_roles"]["target_column"] == "target"
    assert metadata["data_roles"]["column_roles"]["amount"] == "feature_continuous"


def test_dataset_sql_query_supports_quoted_dataset_name() -> None:
    client = TestClient(create_app())
    token = _register(client, "sql-owner")

    upload = client.post(
        "/api/v1/datasets/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={"name": "Customer Churn"},
        files={
            "file": (
                "customer-churn.csv",
                b"region,churned,monthly_fee\nnorth,1,80\nnorth,0,40\nsouth,0,20\n",
                "text/csv",
            )
        },
    )
    assert upload.status_code == 201
    dataset_id = upload.json()["id"]

    query = client.post(
        f"/api/v1/datasets/{dataset_id}/query",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "sql": 'SELECT region, COUNT(*) AS records, AVG(churned) AS avg_churn '
            'FROM "Customer Churn" GROUP BY region ORDER BY region',
            "limit": 50,
        },
    )

    assert query.status_code == 200
    body = query.json()
    assert body["row_count"] == 2
    assert [column["name"] for column in body["columns"]] == ["region", "records", "avg_churn"]
    assert body["records"][0] == {"region": "north", "records": 2, "avg_churn": 0.5}

    rejected = client.post(
        f"/api/v1/datasets/{dataset_id}/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"sql": 'DROP TABLE "Customer Churn"', "limit": 50},
    )
    assert rejected.status_code == 400

    unsafe = client.post(
        f"/api/v1/datasets/{dataset_id}/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"sql": "SELECT * FROM read_csv_auto('/etc/passwd')", "limit": 50},
    )
    assert unsafe.status_code == 400
    assert "forbidden external function" in unsafe.json()["detail"]


def test_dataset_sql_query_counts_full_result_while_returning_bounded_rows() -> None:
    client = TestClient(create_app())
    token = _register(client, "sql-owner")
    rows = "\n".join(f"{index},{index * 10}" for index in range(1, 101))
    upload = client.post(
        "/api/v1/datasets/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={"name": "bounded-query"},
        files={
            "file": (
                "bounded-query.csv",
                f"id,amount\n{rows}\n".encode(),
                "text/csv",
            )
        },
    )
    assert upload.status_code == 201

    response = client.post(
        f"/api/v1/datasets/{upload.json()['id']}/query",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "sql": 'SELECT * FROM "bounded-query" ORDER BY id',
            "limit": 7,
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["row_count"] == 100
    assert result["returned_count"] == 7
    assert result["limit"] == 7


def test_deleted_dataset_metadata_survives_app_restart_and_relogin() -> None:
    client = TestClient(create_app())
    email = f"restart-owner-{uuid4()}@example.com"
    password = "password123"
    register = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "display_name": "Restart Owner"},
    )
    assert register.status_code == 201
    token = register.json()["access_token"]

    upload = client.post(
        "/api/v1/datasets/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={"name": "restart-delete"},
        files={"file": ("restart-delete.csv", b"x,y\n1,2\n", "text/csv")},
    )
    assert upload.status_code == 201
    dataset_id = upload.json()["id"]

    delete = client.delete(
        f"/api/v1/datasets/{dataset_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delete.status_code == 200
    assert delete.json()["status"] == "deleted"

    restarted_client = TestClient(create_app())
    login = restarted_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200
    restarted_token = login.json()["access_token"]

    datasets = restarted_client.get(
        "/api/v1/datasets",
        headers={"Authorization": f"Bearer {restarted_token}"},
    )
    assert datasets.status_code == 200
    deleted_dataset = next(item for item in datasets.json() if item["id"] == dataset_id)
    assert deleted_dataset["status"] == "deleted"
    assert deleted_dataset["deleted_at"] is not None


def test_dataset_preview_reads_csv_rows_and_types() -> None:
    client = TestClient(create_app())
    token = _register(client, "preview-owner")

    upload = client.post(
        "/api/v1/datasets/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={"name": "typed-preview"},
        files={
            "file": (
                "typed-preview.csv",
                b"name,score,active,joined,empty\nAlice,42,true,2026-01-02,\nBob,9.5,false,2026-02-03,\n",
                "text/csv",
            )
        },
    )
    assert upload.status_code == 201
    dataset_id = upload.json()["id"]

    preview = client.get(
        f"/api/v1/datasets/{dataset_id}/preview",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert preview.status_code == 200
    body = preview.json()
    assert body["row_count"] == 2
    assert body["returned_count"] == 2
    assert [column["name"] for column in body["columns"]] == ["name", "score", "active", "joined", "empty"]
    assert {column["name"]: column["type"] for column in body["columns"]} == {
        "name": "text",
        "score": "number",
        "active": "boolean",
        "joined": "date",
        "empty": "empty",
    }
    assert body["records"][0]["score"] == 42
    assert body["records"][0]["active"] is True
    assert body["records"][0]["empty"] is None


def test_dataset_preview_infers_column_types_beyond_returned_limit() -> None:
    client = TestClient(create_app())
    token = _register(client, "preview-limit-owner")

    upload = client.post(
        "/api/v1/datasets/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={"name": "limited-preview"},
        files={
            "file": (
                "limited-preview.csv",
                b"score,label\n1,ok\nnot-a-number,check\n",
                "text/csv",
            )
        },
    )
    assert upload.status_code == 201
    dataset_id = upload.json()["id"]

    preview = client.get(
        f"/api/v1/datasets/{dataset_id}/preview?limit=1",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert preview.status_code == 200
    body = preview.json()
    assert body["row_count"] == 2
    assert body["returned_count"] == 1
    assert {column["name"]: column["type"] for column in body["columns"]}["score"] == "mixed"


def test_data_view_can_be_created_and_previewed_from_browser_definition() -> None:
    client = TestClient(create_app())
    token = _register(client, "view-owner")

    upload = client.post(
        "/api/v1/datasets/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={"name": "view-source"},
        files={
            "file": (
                "view-source.csv",
                b"region,plan_type,amount,churned\nnorth,basic,10,0\nnorth,basic,20,1\nsouth,premium,30,0\n",
                "text/csv",
            )
        },
    )
    assert upload.status_code == 201
    dataset_id = upload.json()["id"]

    roles_update = client.patch(
        f"/api/v1/datasets/{dataset_id}/metadata",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "metadata": {
                "data_roles": {
                    "dataset_roles": ["training", "targeted"],
                    "target_column": "churned",
                    "column_roles": {
                        "region": "feature_categorical",
                        "plan_type": "feature_ordinal",
                        "amount": "feature_continuous",
                        "churned": "target",
                    },
                }
            }
        },
    )
    assert roles_update.status_code == 200

    created = client.post(
        "/api/v1/datasets/views",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "north-summary",
            "source_dataset_id": dataset_id,
            "definition": {
                "kind": "browser",
                "filters": {"region": {"operator": "equals", "value": "north"}},
                "grouping": {
                    "region": {"role": "group", "aggregate": "count_non_empty"},
                    "plan_type": {"role": "group", "aggregate": "count_non_empty"},
                    "amount": {"role": "aggregate", "aggregate": "sum"},
                },
                "sort_rules": [{"column": "region", "direction": "asc"}, {"column": "plan_type", "direction": "asc"}],
            },
        },
    )

    assert created.status_code == 201
    view = created.json()
    assert view["source_type"] == "view"
    assert view["format"] == "view"
    assert view["row_count"] == 1
    assert view["metadata"]["data_view"]["source_dataset_id"] == dataset_id
    assert view["metadata"]["data_view"]["column_count"] == 4
    assert view["metadata"]["data_roles"]["column_roles"]["plan_type"] == "feature_ordinal"
    assert view["metadata"]["data_roles"]["column_roles"]["region"] == "feature_categorical"
    assert "target_column" not in view["metadata"]["data_roles"]

    preview = client.get(
        f"/api/v1/datasets/{view['id']}/preview",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert preview.status_code == 200
    body = preview.json()
    assert [column["name"] for column in body["columns"]] == ["region", "plan_type", "records", "Sum amount"]
    assert body["records"] == [{"region": "north", "plan_type": "basic", "records": 2, "Sum amount": 30}]


def test_sql_data_view_can_only_read_its_declared_source() -> None:
    client = TestClient(create_app())
    token = _register(client, "sql-view-owner")
    headers = {"Authorization": f"Bearer {token}"}
    upload = client.post(
        "/api/v1/datasets/upload",
        headers=headers,
        data={"name": "orders"},
        files={
            "file": (
                "orders.csv",
                b"region,amount\nnorth,10\nsouth,20\n",
                "text/csv",
            )
        },
    )
    assert upload.status_code == 201
    dataset_id = upload.json()["id"]

    created = client.post(
        "/api/v1/datasets/views",
        headers=headers,
        json={
            "name": "north-orders",
            "source_dataset_id": dataset_id,
            "definition": {
                "kind": "sql",
                "sql": 'SELECT * FROM orders WHERE region = \'north\'',
            },
        },
    )
    assert created.status_code == 201
    assert created.json()["row_count"] == 1

    unsafe = client.post(
        "/api/v1/datasets/views",
        headers=headers,
        json={
            "name": "unsafe-view",
            "source_dataset_id": dataset_id,
            "definition": {
                "kind": "sql",
                "sql": "SELECT * FROM read_csv_auto('/etc/passwd')",
            },
        },
    )
    assert unsafe.status_code == 400
    assert "forbidden external function" in unsafe.json()["detail"]
