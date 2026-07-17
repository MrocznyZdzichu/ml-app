from __future__ import annotations

import unittest
from typing import Any

from examples.bootstrap_estates_sell_prices import bootstrap
from ml_app_client import AuthorizationError, Dataset


class FakeBootstrapClient:
    def __init__(self, *, access_role: str = "owner") -> None:
        self.access_role = access_role
        self.business_case: dict[str, Any] | None = None
        self.datasets: list[dict[str, Any]] = []
        self.attachments: list[dict[str, Any]] = []
        self.pipelines: list[dict[str, Any]] = []
        self.upload_count = 0
        self.pipeline_create_count = 0

    def ensure_business_case(self, **definition: Any):
        created = self.business_case is None
        if created:
            self.business_case = {
                **definition,
                "id": "bc-demo",
                "access_role": self.access_role,
            }
        return self.business_case, created

    def list_business_case_attachments(self, _business_case_id: str):
        return self.attachments

    def list_datasets(self):
        return self.datasets

    def upload_dataset(self, path, *, name, description, tags):
        self.upload_count += 1
        payload = {
            "id": f"dataset-{self.upload_count}",
            "logical_id": f"logical-{self.upload_count}",
            "name": name,
            "version_number": 1,
            "row_count": 10,
            "format": "parquet" if str(path).endswith(".parquet") else "csv",
        }
        self.datasets.append(payload)
        return Dataset.from_api(payload)

    def attach_dataset(self, _business_case_id, dataset_id, **_kwargs):
        self.attachments.append({"data_asset_id": dataset_id})
        return {"id": f"attachment-{len(self.attachments)}"}

    def list_pipelines(self, _business_case_id):
        return self.pipelines

    def create_pipeline(self, **payload):
        self.pipeline_create_count += 1
        pipeline = {
            "id": "pipeline-demo",
            "name": payload["name"],
            "published_version_count": 0,
            "draft_version_number": 1,
        }
        self.pipelines.append(pipeline)
        return pipeline

    def publish_pipeline_draft(self, pipeline_id):
        pipeline = next(item for item in self.pipelines if item["id"] == pipeline_id)
        pipeline.update({
            "published_version_count": 1,
            "latest_published_version_number": 1,
            "draft_version_number": None,
        })
        return {"id": "version-demo", "version_number": 1, "status": "published"}


class EstatesBootstrapTests(unittest.TestCase):
    def test_bootstrap_creates_static_prerequisites_once(self) -> None:
        client = FakeBootstrapClient()

        first = bootstrap(client)  # type: ignore[arg-type]
        second = bootstrap(client)  # type: ignore[arg-type]

        self.assertTrue(first["created_business_case"])
        self.assertFalse(second["created_business_case"])
        self.assertEqual(client.upload_count, 3)
        self.assertEqual(len(client.attachments), 3)
        self.assertEqual(client.pipeline_create_count, 1)

    def test_bootstrap_requires_contributor_for_repairs(self) -> None:
        client = FakeBootstrapClient(access_role="reader")
        with self.assertRaisesRegex(AuthorizationError, "contributor access"):
            bootstrap(client)  # type: ignore[arg-type]
        self.assertEqual(client.upload_count, 0)


if __name__ == "__main__":
    unittest.main()
