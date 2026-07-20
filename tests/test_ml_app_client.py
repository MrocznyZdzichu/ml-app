from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from ml_app_client import (
    ApiError,
    AuthorizationError,
    ConflictError,
    MLAppClient,
    PipelineRun,
    ResourceAmbiguousError,
)


class FakeResponse:
    def __init__(self, payload: Any, status_code: int = 200, content: bytes = b"") -> None:
        self.payload = payload
        self.status_code = status_code
        self.text = str(payload)
        self.content = content

    def json(self) -> Any:
        return self.payload

    def iter_content(self, chunk_size: int):
        for offset in range(0, len(self.content), chunk_size):
            yield self.content[offset:offset + chunk_size]


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.headers: dict[str, str] = {}
        self.responses = responses
        self.requests: list[tuple[str, str, dict[str, Any]]] = []
        self.closed = False

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.requests.append((method, url, kwargs))
        return self.responses.pop(0)

    def close(self) -> None:
        self.closed = True


def dataset_payload(**overrides: Any) -> dict[str, Any]:
    value = {
        "id": "dataset-v2", "logical_id": "dataset-family", "name": "sales",
        "version_number": 2, "row_count": 12, "format": "csv",
    }
    value.update(overrides)
    return value


def run_payload(status: str = "queued", **overrides: Any) -> dict[str, Any]:
    value = {
        "id": "run-1", "pipeline_id": "pipeline-1",
        "pipeline_version_id": "version-2", "status": status,
        "processed_row_count": None, "error_message": "",
    }
    value.update(overrides)
    return value


class MLAppClientTests(unittest.TestCase):
    def test_conflict_response_has_a_specific_client_error(self) -> None:
        session = FakeSession([FakeResponse(
            {"detail": "Business Case name 'Sales' is already in use"}, 409
        )])
        with self.assertRaisesRegex(ConflictError, "already in use"):
            MLAppClient(session=session)._request(
                "POST", "/business-cases", json={"name": "Sales"}
            )

    def test_ensure_business_case_is_idempotent_when_visible(self) -> None:
        session = FakeSession([FakeResponse([
            {"id": "bc-1", "name": "Sales", "access_role": "owner"}
        ])])
        business_case, created = MLAppClient(session=session).ensure_business_case(
            name="Sales", problem_type="regression"
        )
        self.assertEqual(business_case["id"], "bc-1")
        self.assertFalse(created)
        self.assertEqual(len(session.requests), 1)

    def test_ensure_business_case_reports_inaccessible_name_conflict(self) -> None:
        session = FakeSession([
            FakeResponse([]),
            FakeResponse({"detail": "already in use"}, 409),
            FakeResponse([]),
        ])
        with self.assertRaisesRegex(AuthorizationError, "not accessible"):
            MLAppClient(session=session).ensure_business_case(
                name="Sales", problem_type="regression"
            )

    def test_client_can_create_attach_and_publish_pipeline_prerequisites(self) -> None:
        session = FakeSession([
            FakeResponse({"id": "bc-1", "name": "Sales"}, 201),
            FakeResponse({"id": "attachment-1"}, 201),
            FakeResponse({"id": "pipeline-1", "name": "Train"}, 201),
            FakeResponse({"id": "version-1", "status": "published"}),
        ])
        client = MLAppClient(session=session)
        business_case = client.create_business_case(name="Sales")
        client.attach_dataset(business_case["id"], "dataset-1", role="training")
        pipeline = client.create_pipeline(
            business_case_id=business_case["id"],
            name="Train",
            pipeline_type="training",
            definition={"contract_version": "2.0", "steps": [], "outputs": [], "parameters": {}},
        )
        published = client.publish_pipeline_draft(pipeline["id"])

        self.assertEqual(published["status"], "published")
        self.assertEqual(session.requests[1][2]["json"]["role"], "training")
        self.assertEqual(session.requests[2][2]["json"]["type"], "training")

    def test_upload_streams_file_and_maps_dataset(self) -> None:
        session = FakeSession([FakeResponse(dataset_payload(), 201)])
        client = MLAppClient("http://platform/api/v1/", "secret", session=session)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sales.csv"
            path.write_text("id,value\n1,10\n", encoding="utf-8")
            dataset = client.upload_dataset(path, logical_id="dataset-family", tags=["train"])

        self.assertEqual(dataset.row_count, 12)
        method, url, kwargs = session.requests[0]
        self.assertEqual((method, url), ("POST", "http://platform/api/v1/datasets/upload"))
        self.assertEqual(kwargs["data"]["logical_id"], "dataset-family")
        self.assertEqual(kwargs["data"]["tags"], "train")
        self.assertEqual(kwargs["files"]["file"][0], "sales.csv")
        self.assertEqual(session.headers["Authorization"], "Bearer secret")

    def test_name_workflow_uploads_attached_dataset_version(self) -> None:
        session = FakeSession([
            FakeResponse([{"id": "bc-1", "name": "Sales"}]),
            FakeResponse([{"data_asset_id": "dataset-v1"}]),
            FakeResponse([dataset_payload(id="dataset-v1", version_number=1)]),
            FakeResponse(dataset_payload(), 201),
        ])
        client = MLAppClient(session=session)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sales.csv"
            path.write_text("id\n1\n", encoding="utf-8")
            result = client.upload_dataset_version(
                path, business_case_name="Sales", dataset_name="sales"
            )
        self.assertEqual(result.version_number, 2)
        self.assertEqual(session.requests[-1][2]["data"]["logical_id"], "dataset-family")

    def test_run_by_name_uses_latest_published_version(self) -> None:
        session = FakeSession([
            FakeResponse([{"id": "bc-1", "name": "Sales"}]),
            FakeResponse([{"id": "pipeline-1", "name": "Retrain"}]),
            FakeResponse([
                {"id": "draft", "status": "draft", "version_number": 3},
                {"id": "version-1", "status": "published", "version_number": 1},
                {"id": "version-2", "status": "published", "version_number": 2},
            ]),
            FakeResponse(run_payload(), 201),
        ])
        run = MLAppClient(session=session).run_pipeline_by_name(
            business_case_name="Sales", pipeline_name="Retrain"
        )
        self.assertEqual(run.pipeline_version_id, "version-2")
        self.assertEqual(session.requests[-1][2]["json"]["pipeline_version_id"], "version-2")

    def test_duplicate_business_case_name_is_rejected(self) -> None:
        session = FakeSession([FakeResponse([
            {"id": "bc-1", "name": "Sales"}, {"id": "bc-2", "name": "Sales"}
        ])])
        with self.assertRaises(ResourceAmbiguousError):
            MLAppClient(session=session).run_pipeline_by_name(
                business_case_name="Sales", pipeline_name="Retrain"
            )

    def test_wait_returns_row_counts_and_raises_on_failed_run(self) -> None:
        success_session = FakeSession([
            FakeResponse(run_payload("succeeded", processed_row_count=12))
        ])
        finished = MLAppClient(session=success_session).wait_for_pipeline_run(
            PipelineRun.from_api(run_payload()),
            poll_interval=0,
        )
        self.assertEqual(finished.processed_row_count, 12)

        failed_session = FakeSession([
            FakeResponse(run_payload("failed", error_message="training failed"))
        ])
        with self.assertRaisesRegex(ApiError, "training failed"):
            MLAppClient(session=failed_session).wait_for_pipeline_run(
                PipelineRun.from_api(run_payload()),
                poll_interval=0,
            )

    def test_prediction_output_can_be_previewed_and_streamed_to_disk(self) -> None:
        run = PipelineRun.from_api(run_payload(
            "succeeded",
            output_manifest=[{
                "artifact_type": "prediction_dataset",
                "dataset_id": "predictions-v1",
            }],
        ))
        session = FakeSession([
            FakeResponse({"row_count": 100_000, "returned_count": 1, "records": [{"prediction": 42.0}]}),
            FakeResponse(None, content=b"PAR1prediction-data"),
        ])
        client = MLAppClient(session=session)

        dataset_id = client.prediction_dataset_id(run)
        preview = client.preview_dataset(dataset_id, limit=1)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "predictions.parquet"
            downloaded = client.download_dataset(dataset_id, destination, chunk_size=4)
            self.assertEqual(downloaded.read_bytes(), b"PAR1prediction-data")

        self.assertEqual(preview["row_count"], 100_000)
        self.assertEqual(session.requests[0][2]["params"], {"limit": 1})
        self.assertTrue(session.requests[1][2]["stream"])

    def test_monitoring_outputs_resolve_dataset_and_report_by_run(self) -> None:
        run = PipelineRun.from_api(run_payload(
            "succeeded",
            output_manifest=[{
                "artifact_type": "dataset",
                "dataset_id": "joined-v1",
            }],
        ))
        session = FakeSession([
            FakeResponse([{"id": "bc-1", "name": "Sales"}]),
            FakeResponse([
                {"id": "other-report", "pipeline_run_id": "other-run"},
                {"id": "monitoring-report", "pipeline_run_id": run.id, "evaluation": {"metrics": []}},
            ]),
        ])
        client = MLAppClient(session=session)

        self.assertEqual(client.output_dataset_id(run), "joined-v1")
        report = client.scoring_report_for_run(run, business_case_name="Sales")
        self.assertEqual(report["id"], "monitoring-report")
        self.assertEqual(session.requests[1][1], "http://localhost:8000/api/v1/scoring-reports")
        self.assertEqual(session.requests[1][2]["params"], {"business_case_id": "bc-1"})

    def test_serving_prediction_resolves_name_and_sends_governance_headers(self) -> None:
        deployment = {
            "id": "deployment-1", "name": "Estates Service", "slug": "estates-service",
            "business_case_id": "bc-1", "status": "running", "endpoint_url": "/predictions",
            "active_revision": {"id": "revision-2"},
        }
        response = {
            "request_id": "request-1", "deployment_id": "deployment-1",
            "deployment_revision_id": "revision-2", "model_id": "model-1",
            "served_role": "champion", "fallback_used": False,
            "predictions": [{"record_id": "estate-1", "prediction": 42.0, "outputs": {}}],
            "warnings": [],
        }
        session = FakeSession([FakeResponse([deployment]), FakeResponse(response)])
        result = MLAppClient(session=session).predict(
            "Estates Service", record_id="estate-1", features={"area": 84},
            idempotency_key="valuation-1", correlation_id="crm-1",
        )

        self.assertEqual(result.predictions[0]["prediction"], 42.0)
        method, url, kwargs = session.requests[-1]
        self.assertEqual((method, url), ("POST", "http://localhost:8000/api/v1/serving/deployments/deployment-1/predictions"))
        self.assertEqual(kwargs["headers"]["Idempotency-Key"], "valuation-1")
        self.assertEqual(kwargs["json"]["instances"][0]["record_id"], "estate-1")

    def test_create_deployment_by_model_name_chooses_latest_production_version(self) -> None:
        session = FakeSession([
            FakeResponse([
                {"id": "candidate", "name": "Estates Model", "stage": "candidate", "version_number": 9},
                {"id": "production-v1", "name": "Estates Model", "stage": "production", "version_number": 1},
                {"id": "production-v3", "name": "Estates Model", "stage": "production", "version_number": 3},
            ]),
            FakeResponse({
                "id": "deployment-1", "name": "Estates Service", "slug": "estates-service",
                "business_case_id": "bc-1", "status": "running", "endpoint_url": "/predictions",
                "active_revision": {"id": "revision-1"},
            }, 201),
        ])
        deployment = MLAppClient(session=session).create_deployment(
            name="Estates Service", model_name="Estates Model"
        )
        self.assertEqual(deployment.slug, "estates-service")
        self.assertEqual(session.requests[-1][2]["json"]["model_id"], "production-v3")

    def test_promote_model_resolves_friendly_name_and_explicit_version(self) -> None:
        session = FakeSession([
            FakeResponse([
                {"id": "model-v10", "name": "Estates Model", "version": "v10", "version_number": 10},
                {"id": "model-v11", "name": "Estates Model", "version": "v11", "version_number": 11},
            ]),
            FakeResponse({"id": "model-v10", "name": "Estates Model", "version": "v10", "stage": "staging"}),
        ])

        promoted = MLAppClient(session=session).promote_model(
            "Estates Model", "staging", version=10
        )

        self.assertEqual(promoted["stage"], "staging")
        method, url, kwargs = session.requests[-1]
        self.assertEqual((method, url), ("POST", "http://localhost:8000/api/v1/models/model-v10/promote"))
        self.assertEqual(kwargs["json"], {"stage": "staging"})

    def test_promote_model_uses_latest_version_and_validates_stage(self) -> None:
        session = FakeSession([FakeResponse([
            {"id": "model-v1", "name": "Churn Model", "version_number": 1},
            {"id": "model-v3", "name": "Churn Model", "version_number": 3},
        ]), FakeResponse({"id": "model-v3", "stage": "production"})])
        client = MLAppClient(session=session)

        client.promote_model("Churn Model", "production")
        self.assertIn("/models/model-v3/promote", session.requests[-1][1])
        with self.assertRaises(ValueError):
            client.promote_model("Churn Model", "champion")


if __name__ == "__main__":
    unittest.main()
