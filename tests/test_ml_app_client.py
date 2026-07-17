from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from ml_app_client import ApiError, MLAppClient, PipelineRun, ResourceAmbiguousError


class FakeResponse:
    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self) -> Any:
        return self.payload


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


if __name__ == "__main__":
    unittest.main()
