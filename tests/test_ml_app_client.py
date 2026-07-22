from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from typing import Any

from ml_app_client import (
    ApiError,
    AuthorizationError,
    ConflictError,
    Dataset,
    Deployment,
    MLAppClient,
    PipelineRun,
    ResourceAmbiguousError,
    ResourceNotFoundError,
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
    def test_me_returns_authenticated_profile(self) -> None:
        session = FakeSession([FakeResponse({
            "user_id": "user-1", "login_name": "alice", "roles": ["user"],
        })])

        profile = MLAppClient(session=session).me()

        self.assertEqual(profile["user_id"], "user-1")
        self.assertIn("/auth/me", session.requests[-1][1])

    def test_connect_prompts_for_normal_user_without_persisting_password(self) -> None:
        session = FakeSession([FakeResponse({"access_token": "user-token"})])

        with patch.dict("os.environ", {"ML_APP_ACCESS_TOKEN": "", "ML_APP_LOGIN": ""}):
            client = MLAppClient.connect(
                session=session,
                prompt=lambda message: "analyst@example.com",
                password_prompt=lambda message: "secret-password",
            )

        self.assertEqual(session.headers["Authorization"], "Bearer user-token")
        self.assertEqual(session.requests[0][2]["json"], {
            "login": "analyst@example.com", "password": "secret-password",
        })
        client.close()

    def test_list_model_serving_usage_returns_typed_assignments(self) -> None:
        session = FakeSession([FakeResponse([{
            "model_id": "model-v11", "deployment_id": "service-1",
            "deployment_name": "Estates Service", "deployment_status": "running",
            "revision_version": 3, "role": "champion", "endpoint_url": "/predictions",
        }])])

        usage = MLAppClient(session=session).list_model_serving_usage("family/estates")

        self.assertEqual(usage[0].role, "champion")
        self.assertEqual(usage[0].revision_version, 3)
        self.assertIn("/model-families/family%2Festates/usage", session.requests[-1][1])

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

    def test_ensure_dataset_reuses_newest_attached_family_version(self) -> None:
        session = FakeSession([
            FakeResponse([{"id": "bc-1", "name": "Example"}]),
            FakeResponse([{"data_asset_id": "dataset-v1"}]),
            FakeResponse([
                dataset_payload(id="dataset-v1", version_number=1),
                dataset_payload(id="dataset-v3", version_number=3),
            ]),
        ])

        dataset, created = MLAppClient(session=session).ensure_dataset(
            "unused.csv",
            business_case_name="Example",
            dataset_name="sales",
            role="training",
        )

        self.assertEqual(dataset.id, "dataset-v3")
        self.assertFalse(created)
        self.assertEqual([item[0] for item in session.requests], ["GET", "GET", "GET"])

    def test_ensure_pipeline_reuses_latest_published_version(self) -> None:
        session = FakeSession([
            FakeResponse([{"id": "bc-1", "name": "Example"}]),
            FakeResponse([{"id": "pipeline-1", "name": "Train", "status": "published"}]),
            FakeResponse([
                {"id": "v1", "status": "published", "version_number": 1},
                {"id": "v2", "status": "published", "version_number": 2},
            ]),
        ])

        pipeline, version, created = MLAppClient(session=session).ensure_pipeline(
            business_case_name="Example",
            name="Train",
            pipeline_type="automl",
            definition={"contract_version": "2.0"},
        )

        self.assertEqual(pipeline["id"], "pipeline-1")
        self.assertEqual(version["id"], "v2")
        self.assertFalse(created)

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

    def test_ensure_pipeline_run_reuses_matching_success(self) -> None:
        existing = run_payload(
            "succeeded",
            runtime_parameters={"client_operation_key": "example01-training-v1"},
            is_dry_run=False,
        )
        session = FakeSession([
            FakeResponse([{"id": "bc-1", "name": "Example"}]),
            FakeResponse([{"id": "pipeline-1", "name": "Train"}]),
            FakeResponse([{"id": "version-2", "status": "published", "version_number": 2}]),
            FakeResponse([existing]),
        ])

        run, created = MLAppClient(session=session).ensure_pipeline_run_by_name(
            business_case_name="Example",
            pipeline_name="Train",
            operation_key="example01-training-v1",
        )

        self.assertEqual(run.status, "succeeded")
        self.assertFalse(created)
        self.assertEqual([item[0] for item in session.requests], ["GET", "GET", "GET", "GET"])

    def test_pipeline_run_by_operation_key_reports_preceding_notebook(self) -> None:
        session = FakeSession([
            FakeResponse([{"id": "bc-1", "name": "Example"}]),
            FakeResponse([{"id": "pipeline-1", "name": "Train"}]),
            FakeResponse([]),
        ])

        with self.assertRaisesRegex(ResourceNotFoundError, "preceding example notebook"):
            MLAppClient(session=session).pipeline_run_by_operation_key(
                business_case_name="Example",
                pipeline_name="Train",
                operation_key="example01-training-v1",
            )

    def test_model_for_pipeline_run_resolves_provenance(self) -> None:
        session = FakeSession([FakeResponse([
            {"id": "model-1", "pipeline_run_id": "run-1"},
            {"id": "model-2", "pipeline_run_id": "run-2"},
        ])])

        model = MLAppClient(session=session).model_for_pipeline_run("run-2")

        self.assertEqual(model["id"], "model-2")

    def test_model_by_name_scopes_to_business_case_and_selects_latest_version(self) -> None:
        session = FakeSession([
            FakeResponse([{"id": "bc-1", "name": "Sales"}]),
            FakeResponse([
                {"id": "other-v9", "business_case_id": "bc-2", "name": "Churn", "logical_id": "other", "version": "v9", "version_number": 9},
                {"id": "model-v1", "business_case_id": "bc-1", "name": "Churn", "logical_id": "churn", "version": "v1", "version_number": 1},
                {"id": "model-v2", "business_case_id": "bc-1", "name": "Churn", "logical_id": "churn", "version": "v2", "version_number": 2},
            ]),
        ])

        model = MLAppClient(session=session).model_by_name(
            business_case_name="Sales", model_name="Churn"
        )

        self.assertEqual(model["id"], "model-v2")

    def test_model_by_name_accepts_explicit_numeric_version(self) -> None:
        session = FakeSession([
            FakeResponse([{"id": "bc-1", "name": "Sales"}]),
            FakeResponse([
                {"id": "model-v1", "business_case_id": "bc-1", "name": "Churn", "logical_id": "churn", "version": "v1", "version_number": 1},
                {"id": "model-v2", "business_case_id": "bc-1", "name": "Churn", "logical_id": "churn", "version": "v2", "version_number": 2},
            ]),
        ])

        model = MLAppClient(session=session).model_by_name(
            business_case_name="Sales", model_name="Churn", version=1
        )

        self.assertEqual(model["id"], "model-v1")

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

    def test_ensure_deployment_reuses_matching_champion(self) -> None:
        deployment = {
            "id": "deployment-1", "name": "Example Service", "slug": "example-service",
            "business_case_id": "bc-1", "status": "running", "endpoint_url": "/predictions",
            "active_revision": {
                "id": "revision-1",
                "assignments": [{"model_id": "model-1", "role": "champion"}],
            },
        }
        session = FakeSession([FakeResponse([deployment])])

        result, created = MLAppClient(session=session).ensure_deployment(
            name="Example Service",
            model_id="model-1",
        )

        self.assertEqual(result.id, "deployment-1")
        self.assertFalse(created)

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
        self.assertEqual((method, url), ("PATCH", "http://localhost:8000/api/v1/models/model-v10/stage"))
        self.assertEqual(kwargs["json"], {"stage": "staging"})

    def test_promote_model_normalizes_display_punctuation_in_friendly_name(self) -> None:
        session = FakeSession([
            FakeResponse([{
                "id": "model-v1",
                "logical_id": "churn-family",
                "name": "Storage Subscription Churn - Experiment 3 - AutoML+ champion",
                "version": "v1",
                "version_number": 1,
            }]),
            FakeResponse([{
                "id": "model-v1",
                "logical_id": "churn-family",
                "name": "Storage Subscription Churn - Experiment 3 - AutoML+ champion",
                "version": "v1",
                "version_number": 1,
            }]),
            FakeResponse({"id": "model-v1", "stage": "archived"}),
        ])

        archived = MLAppClient(session=session).promote_model(
            "Storage Subscription Churn - Experiment 3- AutoML champion",
            "archived",
            version="v1",
        )

        self.assertEqual(archived["stage"], "archived")
        self.assertIn("/models/model-v1/stage", session.requests[-1][1])

    def test_promote_model_prefers_exact_name_before_punctuation_fallback(self) -> None:
        session = FakeSession([
            FakeResponse([
                {
                    "id": "automl-plus-v4", "logical_id": "automl-plus",
                    "name": "Storage Subscription Churn - Experiment 3- AutoML+ champion",
                    "version": "v4", "version_number": 4,
                },
                {
                    "id": "automl-v4", "logical_id": "automl",
                    "name": "Storage Subscription Churn - Experiment 3- AutoML champion",
                    "version": "v4", "version_number": 4,
                },
            ]),
            FakeResponse([{
                "id": "automl-v4", "logical_id": "automl",
                "name": "Storage Subscription Churn - Experiment 3- AutoML champion",
                "version": "v4", "version_number": 4,
            }]),
            FakeResponse({"id": "automl-v4", "stage": "archived"}),
        ])

        archived = MLAppClient(session=session).promote_model(
            "Storage Subscription Churn - Experiment 3- AutoML champion",
            "archived",
            version="v4",
        )

        self.assertEqual(archived["id"], "automl-v4")
        self.assertIn("/models/automl-v4/stage", session.requests[-1][1])

    def test_promote_model_resolves_old_version_from_complete_family_history(self) -> None:
        session = FakeSession([
            FakeResponse([{
                "id": "model-v9", "logical_id": "churn-family",
                "name": "Storage Subscription Churn - Experiment 3- AutoML champion",
                "version": "v9", "version_number": 9,
            }]),
            FakeResponse([
                {
                    "id": "model-v1", "logical_id": "churn-family",
                    "name": "Storage Subscription Churn - Experiment 3 - AutoML champion",
                    "version": "v1", "version_number": 1,
                },
                {
                    "id": "model-v9", "logical_id": "churn-family",
                    "name": "Storage Subscription Churn - Experiment 3- AutoML champion",
                    "version": "v9", "version_number": 9,
                },
            ]),
            FakeResponse({"id": "model-v1", "stage": "archived"}),
        ])

        archived = MLAppClient(session=session).promote_model(
            "Storage Subscription Churn - Experiment 3- AutoML champion",
            "archived",
            version="v1",
        )

        self.assertEqual(archived["id"], "model-v1")
        self.assertIn("/models/churn-family/versions", session.requests[1][1])
        self.assertIn("/models/model-v1/stage", session.requests[-1][1])

    def test_promote_model_versions_resolves_family_once_and_preserves_order(self) -> None:
        session = FakeSession([
            FakeResponse([{
                "id": "model-v3", "logical_id": "churn-family",
                "name": "Churn Model", "version": "v3", "version_number": 3,
            }]),
            FakeResponse([
                {"id": "model-v1", "logical_id": "churn-family", "name": "Old Churn", "version": "v1", "version_number": 1},
                {"id": "model-v2", "logical_id": "churn-family", "name": "Churn Model", "version": "v2", "version_number": 2},
                {"id": "model-v3", "logical_id": "churn-family", "name": "Churn Model", "version": "v3", "version_number": 3},
            ]),
            FakeResponse({"id": "model-v2", "stage": "archived"}),
            FakeResponse({"id": "model-v1", "stage": "archived"}),
        ])

        updated = MLAppClient(session=session).promote_model_versions(
            "Churn Model", "archived", versions=["v2", 1]
        )

        self.assertEqual([item["id"] for item in updated], ["model-v2", "model-v1"])
        self.assertEqual(
            [request[0] for request in session.requests],
            ["GET", "GET", "PATCH", "PATCH"],
        )
        self.assertEqual(
            sum("/models/churn-family/versions" in request[1] for request in session.requests),
            1,
        )

    def test_promote_model_uses_latest_version_and_validates_stage(self) -> None:
        session = FakeSession([FakeResponse([
            {"id": "model-v1", "name": "Churn Model", "version_number": 1},
            {"id": "model-v3", "name": "Churn Model", "version_number": 3},
        ]), FakeResponse({"id": "model-v3", "stage": "production"})])
        client = MLAppClient(session=session)

        client.promote_model("Churn Model", "production")
        self.assertIn("/models/model-v3/stage", session.requests[-1][1])
        with self.assertRaises(ValueError):
            client.promote_model("Churn Model", "champion")

    def test_candidate_stage_is_sent_as_developed_compatibility_alias(self) -> None:
        session = FakeSession([
            FakeResponse([{"id": "model-v1", "name": "Churn Model", "version_number": 1}]),
            FakeResponse({"id": "model-v1", "stage": "developed"}),
        ])
        with self.assertWarns(DeprecationWarning):
            MLAppClient(session=session).promote_model("Churn Model", "candidate")
        self.assertEqual(session.requests[-1][2]["json"], {"stage": "developed"})

    def test_service_lifecycle_revision_history_and_rollback_paths(self) -> None:
        deployment = {
            "id": "deployment-1", "name": "Estates Service", "slug": "estates-service",
            "business_case_id": "bc-1", "status": "running", "endpoint_url": "/predictions",
            "active_revision": {"id": "revision-2"},
        }
        session = FakeSession([
            FakeResponse([deployment]),
            FakeResponse([{"id": "revision-2", "version_number": 2}]),
            FakeResponse([deployment]),
            FakeResponse({"id": "revision-3", "version_number": 3}, 201),
            FakeResponse([deployment]),
            FakeResponse({**deployment, "status": "stopped"}),
        ])
        client = MLAppClient(session=session)

        self.assertEqual(client.deployment_revisions("Estates Service")[0]["version_number"], 2)
        client.rollback_deployment(
            "Estates Service", revision_id="revision-1", reason="Regression"
        )
        stopped = client.set_deployment_status(
            "Estates Service", status="stopped", reason="Maintenance"
        )

        self.assertEqual(stopped.status, "stopped")
        self.assertIn("/revisions/revision-1/rollback", session.requests[3][1])
        self.assertEqual(session.requests[-1][2]["json"]["reason"], "Maintenance")

    def test_deployment_input_contract_uses_same_target_contract_as_ui(self) -> None:
        deployment = Deployment.from_api({
            "id": "deployment-1", "name": "Churn", "slug": "churn",
            "business_case_id": "bc-1", "status": "running", "endpoint_url": "/predictions",
            "active_revision": {"id": "revision-1"},
        })
        contract = {
            "deployment_id": "deployment-1", "model_id": "challenger-1",
            "role": "challenger", "fields": [], "example_features": {},
        }
        session = FakeSession([FakeResponse(contract)])

        result = MLAppClient(session=session).deployment_input_contract(
            deployment, challenger_model_id="challenger-1"
        )

        self.assertEqual(result["model_id"], "challenger-1")
        self.assertEqual(
            session.requests[-1][2]["params"],
            {"challenger_model_id": "challenger-1"},
        )

    def test_online_monitoring_run_uses_typed_objects_and_full_time_window(self) -> None:
        deployment = Deployment.from_api({
            "id": "deployment-1", "name": "Churn", "slug": "churn",
            "business_case_id": "bc-1", "status": "running",
            "endpoint_url": "/predictions", "active_revision": {"id": "revision-1"},
        })
        actuals = Dataset.from_api(dataset_payload(id="actuals-v4", name="churn_actuals"))
        response = {
            "id": "monitoring-1", "deployment_id": deployment.id, "status": "queued",
            "since": "2026-07-20T00:00:00+00:00", "until": "2026-07-21T00:00:00+00:00",
            "actuals_dataset_id": actuals.id, "report": {}, "error_message": "",
        }
        session = FakeSession([FakeResponse(response, 202)])

        run = MLAppClient(session=session).run_deployment_monitoring(
            deployment,
            actuals=actuals,
            since="2026-07-20T00:00:00Z",
            until="2026-07-21T00:00:00Z",
            actuals_target_column="churned",
            actuals_record_id_column="customer_id",
        )

        self.assertEqual(run.id, "monitoring-1")
        method, url, kwargs = session.requests[-1]
        self.assertEqual((method, url), (
            "POST", "http://localhost:8000/api/v1/serving/deployments/deployment-1/monitoring-runs",
        ))
        self.assertEqual(kwargs["json"]["actuals_dataset_id"], "actuals-v4")
        self.assertEqual(kwargs["json"]["join"], {
            "strategy": "auto", "actuals_record_id_column": "customer_id",
        })

    def test_online_monitoring_default_since_is_relative_to_explicit_until(self) -> None:
        deployment = Deployment.from_api({
            "id": "deployment-1", "name": "Churn", "slug": "churn",
            "business_case_id": "bc-1", "status": "running",
            "endpoint_url": "/predictions", "active_revision": {"id": "revision-1"},
        })
        actuals = Dataset.from_api(dataset_payload(id="actuals-v4"))
        session = FakeSession([FakeResponse({
            "id": "monitoring-1", "deployment_id": deployment.id, "status": "queued",
            "since": "2026-07-20T12:00:00+00:00", "until": "2026-07-21T12:00:00+00:00",
            "actuals_dataset_id": actuals.id, "report": {}, "error_message": "",
        }, 202)])

        MLAppClient(session=session).run_deployment_monitoring(
            deployment, actuals=actuals, until="2026-07-21T12:00:00Z",
        )

        self.assertEqual(
            session.requests[-1][2]["json"]["since"],
            "2026-07-20T12:00:00+00:00",
        )

    def test_online_monitoring_can_run_without_actuals(self) -> None:
        deployment = Deployment.from_api({
            "id": "deployment-1", "name": "Churn", "slug": "churn",
            "business_case_id": "bc-1", "status": "running",
            "endpoint_url": "/predictions", "active_revision": {"id": "revision-1"},
        })
        session = FakeSession([FakeResponse({
            "id": "monitoring-1", "deployment_id": deployment.id, "status": "queued",
            "since": "2026-07-20T00:00:00+00:00", "until": "2026-07-21T00:00:00+00:00",
            "actuals_dataset_id": "", "report": {}, "error_message": "",
        }, 202)])

        run = MLAppClient(session=session).run_deployment_monitoring(
            deployment,
            since="2026-07-20T00:00:00Z",
            until="2026-07-21T00:00:00Z",
            aggregation_granularity="hour",
        )

        self.assertEqual(run.actuals_dataset_id, "")
        self.assertNotIn("actuals_dataset_id", session.requests[-1][2]["json"])
        self.assertEqual(session.requests[-1][2]["json"]["aggregation_granularity"], "hour")

    def test_archive_monitoring_run_preserves_a_typed_archived_result(self) -> None:
        response = {
            "id": "monitoring-1", "deployment_id": "deployment-1", "status": "succeeded",
            "since": "2026-07-20T00:00:00+00:00", "until": "2026-07-21T00:00:00+00:00",
            "actuals_dataset_id": "", "aggregation_granularity": "day",
            "archived_at": "2026-07-22T12:00:00+00:00", "report": {}, "error_message": "",
        }
        session = FakeSession([FakeResponse(response)])

        archived = MLAppClient(session=session).archive_online_monitoring_run(
            "monitoring-1", reason="Clean dashboard"
        )

        self.assertEqual(archived.archived_at, "2026-07-22T12:00:00+00:00")
        self.assertEqual(session.requests[-1][2]["json"], {"reason": "Clean dashboard"})

    def test_deployment_model_options_exposes_api_contract(self) -> None:
        deployment = Deployment.from_api({
            "id": "deployment-1", "name": "Churn", "slug": "churn",
            "business_case_id": "bc-1", "status": "running", "endpoint_url": "/predictions",
            "active_revision": {"id": "revision-1"},
        })
        session = FakeSession([FakeResponse([{
            "model_id": "model-1", "stage": "staging",
            "contract_signature": "abc", "compatible_with_active_champion": True,
            "allowed_roles": ["challenger", "shadow"],
        }])])

        options = MLAppClient(session=session).deployment_model_options(deployment)

        self.assertEqual(options[0]["allowed_roles"], ["challenger", "shadow"])
        self.assertIn("/deployments/deployment-1/model-options", session.requests[-1][1])


if __name__ == "__main__":
    unittest.main()
