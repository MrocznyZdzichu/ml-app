from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = ROOT / "examples" / "API-usage"
EXPECTED = [
    "Example01_01_setup_business_case.ipynb",
    "Example01_02_upload_datasets.ipynb",
    "Example01_03_create_training_pipeline.ipynb",
    "Example01_04_run_training.ipynb",
    "Example01_05_create_batch_scoring_pipeline.ipynb",
    "Example01_06_run_batch_scoring.ipynb",
    "Example01_07_create_monitoring_pipeline.ipynb",
    "Example01_08_run_monitoring.ipynb",
    "Example01_09_promote_model.ipynb",
    "Example01_10_create_model_service.ipynb",
    "Example01_11_score_with_client.ipynb",
    "Example01_12_score_with_rest_api.ipynb",
    "Example01_master.ipynb",
]


class ApiUsageNotebookTests(unittest.TestCase):
    def test_numbered_series_is_complete_and_code_cells_compile(self) -> None:
        actual = sorted(path.name for path in NOTEBOOKS.glob("*.ipynb"))
        self.assertEqual(actual, EXPECTED)

        for filename in EXPECTED:
            payload = json.loads((NOTEBOOKS / filename).read_text(encoding="utf-8"))
            self.assertEqual(payload["nbformat"], 4)
            self.assertTrue(payload["cells"])
            for index, cell in enumerate(payload["cells"]):
                if cell["cell_type"] != "code":
                    continue
                self.assertIsNone(cell["execution_count"])
                self.assertEqual(cell["outputs"], [])
                compile("".join(cell["source"]), f"{filename}:cell-{index}", "exec")

    def test_pipeline_notebooks_recommend_the_visual_editor(self) -> None:
        for filename in (
            EXPECTED[2],
            EXPECTED[4],
            EXPECTED[6],
        ):
            payload = json.loads((NOTEBOOKS / filename).read_text(encoding="utf-8"))
            markdown = "\n".join(
                "".join(cell["source"])
                for cell in payload["cells"]
                if cell["cell_type"] == "markdown"
            )
            self.assertIn("frontend", markdown.lower())

    def test_master_notebook_covers_the_complete_test_user_lifecycle(self) -> None:
        payload = json.loads((NOTEBOOKS / "Example01_master.ipynb").read_text(encoding="utf-8"))
        source = "\n".join("".join(cell["source"]) for cell in payload["cells"])

        for operation in (
            "client.me()",
            "client.create_business_case(",
            "client.upload_dataset(",
            "client.attach_dataset(",
            "build_training_definition(",
            "client.run_pipeline_by_name(",
            "build_batch_scoring_definition(",
            "build_monitoring_definition(",
            "client.promote_model(",
            "client.create_deployment(",
            "client.predict(",
            "rest_session.post(",
            "client.inference_history(",
        ):
            self.assertIn(operation, source)
        self.assertIn("ML_APP_EXAMPLE01_INSTANCE", source)
        self.assertIn('report["evaluated_row_count"] != 100_000', source)

    def test_dataset_notebook_teaches_discovery_upload_and_attachment_explicitly(self) -> None:
        payload = json.loads((NOTEBOOKS / EXPECTED[1]).read_text(encoding="utf-8"))
        source = "\n".join("".join(cell["source"]) for cell in payload["cells"])

        self.assertIn("client.dataset_by_name(", source)
        self.assertIn("client.upload_dataset(", source)
        self.assertIn("client.attach_dataset(", source)
        self.assertNotIn("ensure_dataset", source)

    def test_notebooks_do_not_hide_lifecycle_in_ensure_helpers(self) -> None:
        source = "\n".join(
            (NOTEBOOKS / filename).read_text(encoding="utf-8")
            for filename in EXPECTED
        )
        for helper in (
            "ensure_business_case",
            "ensure_dataset",
            "ensure_pipeline(",
            "ensure_pipeline_run_by_name",
            "ensure_deployment",
        ):
            self.assertNotIn(helper, source)

    def test_notebooks_expose_resource_names_without_profile_derived_namespace(self) -> None:
        source = "\n".join(
            (NOTEBOOKS / filename).read_text(encoding="utf-8")
            for filename in EXPECTED
        )

        self.assertNotIn("names_for_user", source)
        self.assertNotIn('profile["user_id"]', source)
        for name in (
            "BUSINESS_CASE_NAME",
            "TRAINING_DATASET_NAME",
            "TRAINING_PIPELINE_NAME",
            "MODEL_NAME",
            "MODEL_SERVICE_NAME",
        ):
            self.assertIn(name, source)


if __name__ == "__main__":
    unittest.main()
