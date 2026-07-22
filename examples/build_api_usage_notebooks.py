"""Generate the deterministic, numbered API-usage notebook series."""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent


OUTPUT = Path(__file__).resolve().parent / "API-usage"


def markdown(source: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": _lines(source)}


def code(source: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": _lines(source),
    }


def _lines(source: str) -> list[str]:
    normalized = dedent(source).strip() + "\n"
    return normalized.splitlines(keepends=True)


def write_notebook(filename: str, cells: list[dict]) -> None:
    payload = {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.12"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path = OUTPUT / filename
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


CLIENT_SETUP = """
from pathlib import Path
import sys

REPOSITORY_ROOT = next(
    (path for path in [Path.cwd(), *Path.cwd().parents] if (path / "ml_app_client").is_dir()),
    None,
)
if REPOSITORY_ROOT is None:
    raise RuntimeError("Start Jupyter inside the ml-app repository")
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from ml_app_client import MLAppClient, ResourceNotFoundError

client = MLAppClient.connect()
print("Connected to ML App")
"""

RESOURCE_NAMES = """
# These are ordinary platform resource names. Change the two globally unique
# names (Business Case and model service) when sharing one installation.
BUSINESS_CASE_NAME = "[MLAPP EXAMPLE 01 v2] Estates Lifecycle - demo"
TRAINING_DATASET_NAME = "Example01 Estates - Training"
SCORING_DATASET_NAME = "Example01 Estates - Batch Input"
ACTUALS_DATASET_NAME = "Example01 Estates - Actuals"
TRAINING_PIPELINE_NAME = "Example01 03 - AutoML Training"
BATCH_PIPELINE_NAME = "Example01 05 - Batch Scoring"
MONITORING_PIPELINE_NAME = "Example01 07 - Performance Monitoring"
MODEL_NAME = "Example01 Estates Price Model"
OUTPUT_NAME_PREFIX = "Example01 Estates AutoML"
MODEL_SERVICE_NAME = "Example01 10 - Estates Model Service - demo"

TRAINING_RUN_KEY = "Example01-training-v2"
BATCH_RUN_KEY = "Example01-batch-scoring-v2"
MONITORING_RUN_KEY = "Example01-monitoring-v2"

print("Resource names configured for:", BUSINESS_CASE_NAME)
"""

RESOURCE_NAMES_MARKDOWN = """
## Choose resource names

These are normal names passed to `ml_app_client`. Edit them directly and use the
same values in the following notebooks. Dataset and pipeline names are resolved
inside the selected Business Case. Business Case and service names are globally
unique on one ML App installation.
"""


def build() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_notebook("Example01_01_setup_business_case.ipynb", [
        markdown("""
        # Example 01.01 — set up the Business Case

        Creates a deterministic, clearly marked Business Case for the authenticated user.
        Re-running the notebook reuses the same BC and never deletes governed history.
        """),
        markdown("""
        ## Connect

        `MLAppClient.connect()` uses `ML_APP_ACCESS_TOKEN` when configured. Otherwise it
        asks for a login and password without storing the password in the notebook.
        """),
        code(CLIENT_SETUP),
        markdown(RESOURCE_NAMES_MARKDOWN),
        code(RESOURCE_NAMES),
        markdown("## 1. Check whether the Business Case exists"),
        code("""
        try:
            business_case = client.business_case_by_name(BUSINESS_CASE_NAME)
            created = False
            print(f"FOUND: {business_case['name']}")
        except ResourceNotFoundError:
            business_case = None
            print("NOT FOUND: the Business Case will be created in the next cell")
        """),
        markdown("## 2. Create it only when it is missing"),
        code("""
        if business_case is None:
            business_case = client.create_business_case(
                name=BUSINESS_CASE_NAME,
                description="Deterministic Example 01: training, batch scoring, monitoring, and online serving.",
                problem_type="regression",
                status="draft",
                primary_metric="MAPE",
                target_column="sale_price_pln",
                business_goal="Demonstrate the complete ML lifecycle through the public API and Python client.",
                success_criteria="Process every declared row and retain reproducible lineage for every result.",
            )
            created = True
        if business_case.get("access_role") not in {None, "owner"}:
            raise RuntimeError("The named example BC exists but is not owned by this account; choose another BUSINESS_CASE_NAME")
        print(f"{'CREATED' if created else 'FOUND'}: {business_case['name']} ({business_case['id']})")
        """),
    ])

    write_notebook("Example01_02_upload_datasets.ipynb", [
        markdown("""
        # Example 01.02 — upload and attach datasets

        Uploads three deterministic datasets: training data, an unlabeled batch-scoring
        cohort, and delayed actuals. Existing attached families are reused without creating
        duplicate immutable versions.

        Prerequisite: run `Example01_01_setup_business_case.ipynb`.
        """),
        code(CLIENT_SETUP),
        markdown(RESOURCE_NAMES_MARKDOWN),
        code(RESOURCE_NAMES),
        markdown("## 1. Describe the datasets we need"),
        code("""
        from examples.example01_lifecycle import SCENARIO_TAGS, data_file

        specifications = [
            {"name": TRAINING_DATASET_NAME, "file": "regression-example.csv", "role": "source", "row_id": "property_id", "target": "sale_price_pln"},
            {"name": SCORING_DATASET_NAME, "file": "estates-sale-prices-batch-scoring-100k.parquet", "role": "scoring_input", "row_id": "property_id", "target": ""},
            {"name": ACTUALS_DATASET_NAME, "file": "estates-sale-prices-batch-scoring-100k-actuals.parquet", "role": "monitoring_actuals", "row_id": "property_id", "target": "sale_price_pln"},
        ]
        business_case = client.business_case_by_name(BUSINESS_CASE_NAME)
        """),
        markdown("## 2. Check which datasets already exist in this Business Case"),
        code("""
        datasets = {}
        missing = []
        for specification in specifications:
            try:
                dataset = client.dataset_by_name(
                    business_case_name=BUSINESS_CASE_NAME,
                    dataset_name=specification["name"],
                )
                datasets[specification["name"]] = dataset
                print(f"FOUND {dataset.name} v{dataset.version_number}; rows={dataset.row_count:,}")
            except ResourceNotFoundError:
                missing.append(specification)
                print(f"NOT FOUND {specification['name']}")
        """),
        markdown("## 3. Upload every missing file"),
        code("""
        for specification in missing:
            dataset = client.upload_dataset(
                data_file(specification["file"]),
                name=specification["name"],
                description=f"Deterministic Example 01 dataset: {specification['role']}",
                tags=SCENARIO_TAGS,
            )
            datasets[specification["name"]] = dataset
            print(f"UPLOADED {dataset.name} v{dataset.version_number}; rows={dataset.row_count:,}")
        """),
        markdown("## 4. Attach newly uploaded datasets to the Business Case"),
        code("""
        for specification in missing:
            dataset = datasets[specification["name"]]
            client.attach_dataset(
                str(business_case["id"]),
                dataset.id,
                role=specification["role"],
                context_note="Example01 contract v1.0",
                primary_key_column=specification["row_id"],
                target_column=specification["target"],
            )
            print(f"ATTACHED {dataset.name} as {specification['role']}")

        if not missing:
            print("Nothing to upload or attach")
        """),
        markdown("All three operations stream files or bounded metadata; no full dataset is loaded into notebook memory."),
    ])

    write_notebook("Example01_03_create_training_pipeline.ipynb", [
        markdown("""
        # Example 01.03 — create the AutoML/AutoFE training pipeline

        This notebook intentionally uses a fixed pipeline JSON so an integration user can
        automate a known workflow through `ml_app_client`. For normal interactive work,
        use the application frontend: its visual editor is the recommended, flexible way
        to configure Data Engineering, Feature Engineering, AutoML, validation, and outputs.

        Prerequisite: run notebooks 01.01–01.02.
        """),
        code(CLIENT_SETUP),
        markdown(RESOURCE_NAMES_MARKDOWN),
        code(RESOURCE_NAMES),
        code("""
        from examples.example01_lifecycle import build_training_definition

        training = client.dataset_by_name(
            business_case_name=BUSINESS_CASE_NAME,
            dataset_name=TRAINING_DATASET_NAME,
        )
        definition = build_training_definition(
            training.logical_id,
            model_name=MODEL_NAME,
            output_name_prefix=OUTPUT_NAME_PREFIX,
        )
        try:
            pipeline = client.pipeline_by_name(business_case_name=BUSINESS_CASE_NAME, pipeline_name=TRAINING_PIPELINE_NAME)
            version = client.latest_published_pipeline_version(str(pipeline["id"]))
            created = False
        except ResourceNotFoundError:
            business_case = client.business_case_by_name(BUSINESS_CASE_NAME)
            pipeline = client.create_pipeline(business_case_id=str(business_case["id"]), name=TRAINING_PIPELINE_NAME, description="Fixed Example01 full-scope AutoML and AutoFE training workflow.", pipeline_type="automl", definition=definition)
            version = client.publish_pipeline_draft(str(pipeline["id"]))
            created = True
        print(
            f"{'CREATED' if created else 'FOUND'} {pipeline['name']}; "
            f"published version={version['version_number']}"
        )
        """),
        markdown("The tutorial budget is six trials and three leakage-safe folds over the full 10,000-row training dataset. It does not silently sample rows."),
    ])

    write_notebook("Example01_04_run_training.ipynb", [
        markdown("""
        # Example 01.04 — run training

        Starts the published AutoML pipeline and waits for completion. A successful run with
        the same operation key is reused on later notebook executions.

        Prerequisite: run notebooks 01.01–01.03.
        """),
        code(CLIENT_SETUP),
        markdown(RESOURCE_NAMES_MARKDOWN),
        code(RESOURCE_NAMES),
        code("""
        training = client.dataset_by_name(
            business_case_name=BUSINESS_CASE_NAME,
            dataset_name=TRAINING_DATASET_NAME,
        )
        try:
            run = client.pipeline_run_by_operation_key(business_case_name=BUSINESS_CASE_NAME, pipeline_name=TRAINING_PIPELINE_NAME, operation_key=TRAINING_RUN_KEY)
            started = False
        except ResourceNotFoundError:
            run = client.run_pipeline_by_name(business_case_name=BUSINESS_CASE_NAME, pipeline_name=TRAINING_PIPELINE_NAME, runtime_parameters={"client_operation_key": TRAINING_RUN_KEY})
            started = True
        print(f"{'STARTED' if started else 'REUSED'} run {run.id}; status={run.status}")

        finished = client.wait_for_pipeline_run(
            run,
            timeout=3600,
            on_update=lambda current: print(
                f"status={current.status}; current_terminal_rows={current.processed_row_count}"
            ),
        )
        model = client.model_for_pipeline_run(finished)
        if model["name"] != MODEL_NAME:
            raise RuntimeError(f"Expected model {MODEL_NAME!r}, got {model['name']!r}")
        print({
            "run_id": finished.id,
            "full_training_scope_rows": training.row_count,
            "terminal_holdout_output_rows": finished.processed_row_count,
            "model_id": model["id"],
            "model_name": model["name"],
            "model_version": model["version"],
            "stage": model["stage"],
        })
        """),
    ])

    write_notebook("Example01_05_create_batch_scoring_pipeline.ipynb", [
        markdown("""
        # Example 01.05 — create the batch-scoring pipeline

        Builds a fixed scoring workflow from the exact model and fitted AutoFE state created
        by notebook 01.04. It never refits transformations on scoring data.

        This JSON is a reproducible automation example. Use the frontend's pipeline editor
        to design or infer more flexible production workflows.
        """),
        code(CLIENT_SETUP),
        markdown(RESOURCE_NAMES_MARKDOWN),
        code(RESOURCE_NAMES),
        code("""
        from examples.example01_lifecycle import build_batch_scoring_definition

        model = client.model_by_name(
            business_case_name=BUSINESS_CASE_NAME,
            model_name=MODEL_NAME,
        )
        scoring = client.dataset_by_name(
            business_case_name=BUSINESS_CASE_NAME,
            dataset_name=SCORING_DATASET_NAME,
        )
        definition = build_batch_scoring_definition(
            model,
            scoring.logical_id,
            output_name_prefix=OUTPUT_NAME_PREFIX,
        )
        try:
            pipeline = client.pipeline_by_name(business_case_name=BUSINESS_CASE_NAME, pipeline_name=BATCH_PIPELINE_NAME)
            version = client.latest_published_pipeline_version(str(pipeline["id"]))
            created = False
        except ResourceNotFoundError:
            business_case = client.business_case_by_name(BUSINESS_CASE_NAME)
            pipeline = client.create_pipeline(business_case_id=str(business_case["id"]), name=BATCH_PIPELINE_NAME, description="Example01 full-scope batch inference with a pinned training bundle.", pipeline_type="batch_scoring", definition=definition)
            version = client.publish_pipeline_draft(str(pipeline["id"]))
            created = True
        print(
            f"{'CREATED' if created else 'FOUND'} {pipeline['name']}; "
            f"published version={version['version_number']}; model={model['id']}"
        )
        """),
    ])

    write_notebook("Example01_06_run_batch_scoring.ipynb", [
        markdown("""
        # Example 01.06 — run batch scoring

        Scores all 100,000 rows and stores an immutable prediction dataset. Re-running the
        notebook reuses the successful operation rather than producing duplicate predictions.
        """),
        code(CLIENT_SETUP),
        markdown(RESOURCE_NAMES_MARKDOWN),
        code(RESOURCE_NAMES),
        code("""
        try:
            run = client.pipeline_run_by_operation_key(business_case_name=BUSINESS_CASE_NAME, pipeline_name=BATCH_PIPELINE_NAME, operation_key=BATCH_RUN_KEY)
            started = False
        except ResourceNotFoundError:
            run = client.run_pipeline_by_name(business_case_name=BUSINESS_CASE_NAME, pipeline_name=BATCH_PIPELINE_NAME, runtime_parameters={"client_operation_key": BATCH_RUN_KEY})
            started = True
        print(f"{'STARTED' if started else 'REUSED'} run {run.id}; status={run.status}")
        finished = client.wait_for_pipeline_run(run, timeout=3600)

        prediction_dataset_id = client.prediction_dataset_id(finished)
        preview = client.preview_dataset(prediction_dataset_id, limit=5)
        print({
            "run_id": finished.id,
            "processed_rows": finished.processed_row_count,
            "prediction_dataset_id": prediction_dataset_id,
            "total_prediction_rows": preview["row_count"],
            "preview_rows": preview["returned_count"],
        })
        preview["records"]
        """),
    ])

    write_notebook("Example01_07_create_monitoring_pipeline.ipynb", [
        markdown("""
        # Example 01.07 — create the monitoring pipeline

        Pins the immutable prediction dataset from notebook 01.06 and joins it with the
        delayed actuals family. This is a fixed API automation example; use the frontend
        for flexible join preparation, quality rules, and monitoring configuration.
        """),
        code(CLIENT_SETUP),
        markdown(RESOURCE_NAMES_MARKDOWN),
        code(RESOURCE_NAMES),
        code("""
        from examples.example01_lifecycle import build_monitoring_definition

        batch_run = client.pipeline_run_by_operation_key(
            business_case_name=BUSINESS_CASE_NAME,
            pipeline_name=BATCH_PIPELINE_NAME,
            operation_key=BATCH_RUN_KEY,
        )
        actuals = client.dataset_by_name(
            business_case_name=BUSINESS_CASE_NAME,
            dataset_name=ACTUALS_DATASET_NAME,
        )
        definition = build_monitoring_definition(
            batch_run,
            actuals.logical_id,
            output_name_prefix=OUTPUT_NAME_PREFIX,
        )
        try:
            pipeline = client.pipeline_by_name(business_case_name=BUSINESS_CASE_NAME, pipeline_name=MONITORING_PIPELINE_NAME)
            version = client.latest_published_pipeline_version(str(pipeline["id"]))
            created = False
        except ResourceNotFoundError:
            business_case = client.business_case_by_name(BUSINESS_CASE_NAME)
            pipeline = client.create_pipeline(business_case_id=str(business_case["id"]), name=MONITORING_PIPELINE_NAME, description="Example01 full-scope performance monitoring with delayed actuals.", pipeline_type="monitoring", definition=definition)
            version = client.publish_pipeline_draft(str(pipeline["id"]))
            created = True
        print(
            f"{'CREATED' if created else 'FOUND'} {pipeline['name']}; "
            f"published version={version['version_number']}"
        )
        """),
    ])

    write_notebook("Example01_08_run_monitoring.ipynb", [
        markdown("""
        # Example 01.08 — run performance monitoring

        Joins all predictions with actuals and computes full-scope regression metrics.
        Only bounded report metadata is returned to the notebook.
        """),
        code(CLIENT_SETUP),
        markdown(RESOURCE_NAMES_MARKDOWN),
        code(RESOURCE_NAMES),
        code("""
        try:
            run = client.pipeline_run_by_operation_key(business_case_name=BUSINESS_CASE_NAME, pipeline_name=MONITORING_PIPELINE_NAME, operation_key=MONITORING_RUN_KEY)
            started = False
        except ResourceNotFoundError:
            run = client.run_pipeline_by_name(business_case_name=BUSINESS_CASE_NAME, pipeline_name=MONITORING_PIPELINE_NAME, runtime_parameters={"client_operation_key": MONITORING_RUN_KEY})
            started = True
        print(f"{'STARTED' if started else 'REUSED'} run {run.id}; status={run.status}")
        finished = client.wait_for_pipeline_run(run, timeout=3600)
        report = client.scoring_report_for_run(
            finished,
            business_case_name=BUSINESS_CASE_NAME,
        )
        metrics = {
            metric["id"]: metric["value"]
            for metric in report["evaluation"].get("metrics", [])
        }
        print({
            "run_id": finished.id,
            "processed_rows": finished.processed_row_count,
            "evaluated_rows": report["evaluated_row_count"],
            "report_id": report["id"],
            "metrics": metrics,
        })
        """),
    ])

    write_notebook("Example01_09_promote_model.ipynb", [
        markdown("""
        # Example 01.09 — promote the trained model

        Changes the immutable model version's lifecycle stage to `production`. Re-running
        the notebook detects the existing stage and performs no redundant mutation.

        The model is resolved inside the Business Case. By default this selects its newest
        immutable version; pass `version="vN"` to `model_by_name` when automation must pin
        an older version explicitly.
        """),
        code(CLIENT_SETUP),
        markdown(RESOURCE_NAMES_MARKDOWN),
        code(RESOURCE_NAMES),
        code("""
        model = client.model_by_name(
            business_case_name=BUSINESS_CASE_NAME,
            model_name=MODEL_NAME,
        )
        if model["stage"] == "production":
            promoted = model
            action = "FOUND"
        else:
            promoted = client.promote_model(str(model["id"]), "production")
            action = "PROMOTED"
        print(f"{action} {promoted['name']} {promoted['version']}; stage={promoted['stage']}")
        """),
    ])

    write_notebook("Example01_10_create_model_service.ipynb", [
        markdown("""
        # Example 01.10 — create an online model service

        Creates one stable service endpoint with the promoted model as champion. A matching
        running service is reused. An archived service keeps its governed name reserved and
        produces a clear conflict instead of silently replacing history.

        `MODEL_SERVICE_NAME` is the user-chosen service name used later for discovery and
        online scoring.
        """),
        code(CLIENT_SETUP),
        markdown(RESOURCE_NAMES_MARKDOWN),
        code(RESOURCE_NAMES),
        code("""
        model = client.model_by_name(
            business_case_name=BUSINESS_CASE_NAME,
            model_name=MODEL_NAME,
        )
        if model["stage"] != "production":
            raise RuntimeError("Run Example01_09_promote_model.ipynb first")

        try:
            service = client.deployment_by_name(MODEL_SERVICE_NAME, include_archived=True)
            created = False
            if service.status == "archived":
                raise RuntimeError("The example service is archived; choose a new scenario version")
            champion = next(item for item in service.active_revision["assignments"] if item["role"] == "champion")
            if str(champion["model_id"]) != str(model["id"]):
                raise RuntimeError("The existing example service uses a different champion model")
            if service.status == "stopped":
                service = client.set_deployment_status(service, status="running", reason="Resume Example01 service")
        except ResourceNotFoundError:
            service = client.create_deployment(name=MODEL_SERVICE_NAME, model_id=str(model["id"]), retention_days=365)
            created = True
        print({
            "action": "CREATED" if created else "FOUND",
            "service": service.name,
            "status": service.status,
            "endpoint": service.endpoint_url,
            "revision": service.active_revision.get("version_number"),
        })
        """),
    ])

    write_notebook("Example01_11_score_with_client.ipynb", [
        markdown("""
        # Example 01.11 — score through `ml_app_client`

        Reads the champion's input contract and scores one record through the stable service.
        The deterministic idempotency key makes repeated execution return the same governed
        operation instead of duplicating the Inference Log entry.
        """),
        code(CLIENT_SETUP),
        markdown(RESOURCE_NAMES_MARKDOWN),
        code(RESOURCE_NAMES),
        code("""
        service = client.deployment_by_name(MODEL_SERVICE_NAME)
        contract = client.deployment_input_contract(service)
        features = dict(contract["example_features"])

        result = client.predict(
            service,
            record_id="Example01-client-record-001",
            features=features,
            idempotency_key="Example01-client-score-v2",
            correlation_id="Example01-client-demo",
        )
        print({
            "request_id": result.request_id,
            "model_id": result.model_id,
            "served_role": result.served_role,
            "prediction": result.predictions[0]["prediction"],
            "warnings": list(result.warnings),
        })
        """),
    ])

    write_notebook("Example01_12_score_with_rest_api.ipynb", [
        markdown("""
        # Example 01.12 — score with direct REST requests

        Performs the same discovery and prediction flow without `ml_app_client`. This is the
        low-level equivalent of notebook 01.11 and uses only public REST endpoints.
        """),
        code("""
        import getpass
        import os
        import requests

        API = os.getenv("ML_APP_API_URL", "http://localhost:8000/api/v1").rstrip("/")
        token = os.getenv("ML_APP_ACCESS_TOKEN", "").strip()
        if not token:
            response = requests.post(
                f"{API}/auth/login",
                json={
                    "login": input("ML App login or email: "),
                    "password": getpass.getpass("ML App password: "),
                },
                timeout=30,
            )
            response.raise_for_status()
            token = response.json()["access_token"]

        session = requests.Session()
        session.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/json"})
        print("Authenticated against", API)
        """),
        code("""
        from pathlib import Path
        import sys

        REPOSITORY_ROOT = next(
            (path for path in [Path.cwd(), *Path.cwd().parents] if (path / "examples").is_dir()),
            None,
        )
        if REPOSITORY_ROOT is None:
            raise RuntimeError("Start Jupyter inside the ml-app repository")
        if str(REPOSITORY_ROOT) not in sys.path:
            sys.path.insert(0, str(REPOSITORY_ROOT))

        MODEL_SERVICE_NAME = "Example01 10 - Estates Model Service - demo"
        deployments_response = session.get(f"{API}/serving/deployments", timeout=30)
        deployments_response.raise_for_status()
        matches = [item for item in deployments_response.json() if item["name"] == MODEL_SERVICE_NAME]
        if len(matches) != 1:
            raise RuntimeError("Run Example01_10_create_model_service.ipynb first")
        service = matches[0]

        contract_response = session.get(
            f"{API}/serving/deployments/{service['id']}/input-contract",
            timeout=30,
        )
        contract_response.raise_for_status()
        features = contract_response.json()["example_features"]
        """),
        code("""
        response = session.post(
            f"{API}/serving/deployments/{service['id']}/predictions",
            headers={
                "Idempotency-Key": "Example01-rest-score-v2",
                "X-Correlation-ID": "Example01-rest-demo",
            },
            json={"instances": [{
                "record_id": "Example01-rest-record-001",
                "features": features,
            }]},
            timeout=120,
        )
        response.raise_for_status()
        result = response.json()
        print({
            "request_id": result["request_id"],
            "model_id": result["model_id"],
            "served_role": result["served_role"],
            "prediction": result["predictions"][0]["prediction"],
            "warnings": result["warnings"],
        })
        """),
    ])


if __name__ == "__main__":
    build()
    print(f"Generated numbered API-usage notebooks in {OUTPUT}")
