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

MASTER_CLIENT_SETUP = """
from pathlib import Path
import getpass
import os
import requests
import sys

REPOSITORY_ROOT = next(
    (path for path in [Path.cwd(), *Path.cwd().parents] if (path / "ml_app_client").is_dir()),
    None,
)
if REPOSITORY_ROOT is None:
    raise RuntimeError("Start Jupyter inside the ml-app repository")
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from ml_app_client import ConflictError, MLAppClient, ResourceNotFoundError

API = os.getenv("ML_APP_API_URL", "http://localhost:8000/api/v1").rstrip("/")
token = os.getenv("ML_APP_ACCESS_TOKEN", "").strip()
if not token:
    response = requests.post(
        f"{API}/auth/login",
        json={
            "login": input("ML App login or email: ").strip(),
            "password": getpass.getpass("ML App password: "),
        },
        timeout=30,
    )
    response.raise_for_status()
    token = response.json()["access_token"]

client = MLAppClient(base_url=API, access_token=token)
rest_session = requests.Session()
rest_session.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/json"})
profile = client.me()
if not profile.get("is_active", True):
    raise RuntimeError("The authenticated test account is inactive")
print({
    "api": API,
    "login": profile["login_name"],
    "roles": profile["roles"],
    "ready": True,
})
"""

MASTER_RESOURCE_NAMES = """
# One explicit label isolates globally unique Business Case and service names.
# Reuse the same label to resume this scenario. Choose a new label for a clean run.
EXAMPLE_INSTANCE = os.getenv("ML_APP_EXAMPLE01_INSTANCE", "").strip()
if not EXAMPLE_INSTANCE:
    EXAMPLE_INSTANCE = input(
        "Unique Example01 label (for example test-alice-2026-07): "
    ).strip()
if not EXAMPLE_INSTANCE or len(EXAMPLE_INSTANCE) > 60:
    raise ValueError("Provide an EXAMPLE_INSTANCE label containing 1-60 characters")

BUSINESS_CASE_NAME = f"[MLAPP EXAMPLE 01 {EXAMPLE_INSTANCE}] Estates Lifecycle"
TRAINING_DATASET_NAME = "Example01 Estates - Training"
SCORING_DATASET_NAME = "Example01 Estates - Batch Input"
ACTUALS_DATASET_NAME = "Example01 Estates - Actuals"
TRAINING_PIPELINE_NAME = "Example01 03 - AutoML Training"
BATCH_PIPELINE_NAME = "Example01 05 - Batch Scoring"
MONITORING_PIPELINE_NAME = "Example01 07 - Performance Monitoring"
MODEL_NAME = "Example01 Estates Price Model"
OUTPUT_NAME_PREFIX = "Example01 Estates AutoML"
MODEL_SERVICE_NAME = f"Example01 10 - Estates Model Service - {EXAMPLE_INSTANCE}"

TRAINING_RUN_KEY = "Example01-training-v2"
BATCH_RUN_KEY = "Example01-batch-scoring-v2"
MONITORING_RUN_KEY = "Example01-monitoring-v2"

print({
    "instance": EXAMPLE_INSTANCE,
    "business_case": BUSINESS_CASE_NAME,
    "model_service": MODEL_SERVICE_NAME,
})
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

    write_notebook("Example01_master.ipynb", [
        markdown("""
        # Example 01 master — complete ML lifecycle

        This notebook combines the complete numbered Example 01 series into one
        end-to-end path for a newly created test user. It creates and owns a Business
        Case, uploads deterministic source data, trains a model over the complete
        training dataset, performs full-batch scoring and monitoring, promotes and
        serves the model, then verifies predictions made through both the Python client
        and direct REST API.

        The notebook never deletes governed history. Re-running it with the same
        `EXAMPLE_INSTANCE` reuses named resources and successful pipeline operations.
        """),
        markdown("""
        ## Before you run it

        1. Start the complete local stack, including API, worker, scheduler, PostgreSQL,
           Redis, MinIO and model runtime.
        2. Create an active test account through the UI or `POST /api/v1/auth/register`.
           The base platform role `user` is sufficient: the account becomes owner of the
           Business Case created below.
        3. Start Jupyter anywhere inside this repository. The three checked-in datasets
           are read from `examples/data`; no full dataset is loaded into notebook memory.
        4. Choose a unique `EXAMPLE_INSTANCE` label when prompted, or set
           `ML_APP_EXAMPLE01_INSTANCE`. Business Case and model-service names are global.

        AutoML can take several minutes. Batch scoring and monitoring each process all
        100,000 declared rows asynchronously. Only bounded previews and report metadata
        are returned to this notebook.
        """),
        markdown("## 0. Connect once and verify the test account"),
        code(MASTER_CLIENT_SETUP),
        markdown("## 1. Choose one reusable scenario instance"),
        code(MASTER_RESOURCE_NAMES),
        markdown("""
        ## 2. Create or discover the Business Case

        Business Case names are globally unique, including across resources invisible to
        this account. A conflict therefore means that another account already uses this
        instance label; choose another label and rerun from section 1.
        """),
        code("""
        try:
            business_case = client.business_case_by_name(BUSINESS_CASE_NAME)
            created = False
        except ResourceNotFoundError:
            try:
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
            except ConflictError as exc:
                raise RuntimeError(
                    "This EXAMPLE_INSTANCE is already used by an inaccessible Business Case. "
                    "Choose another label in section 1."
                ) from exc

        if business_case.get("access_role") not in {None, "owner"}:
            raise RuntimeError(
                "This test account does not own the selected Business Case; choose a fresh EXAMPLE_INSTANCE"
            )
        print({
            "action": "CREATED" if created else "FOUND",
            "business_case_id": business_case["id"],
            "access_role": business_case.get("access_role", "owner"),
        })
        """),
        markdown("""
        ## 3. Upload and attach all source datasets

        The training file contains 10,000 rows. Scoring input and delayed actuals each
        contain 100,000 rows and join one-to-one by `property_id`.
        """),
        code("""
        from examples.example01_lifecycle import SCENARIO_TAGS, data_file

        specifications = [
            {"name": TRAINING_DATASET_NAME, "file": "regression-example.csv", "role": "source", "row_id": "property_id", "target": "sale_price_pln", "expected_rows": 10_000},
            {"name": SCORING_DATASET_NAME, "file": "estates-sale-prices-batch-scoring-100k.parquet", "role": "scoring_input", "row_id": "property_id", "target": "", "expected_rows": 100_000},
            {"name": ACTUALS_DATASET_NAME, "file": "estates-sale-prices-batch-scoring-100k-actuals.parquet", "role": "monitoring_actuals", "row_id": "property_id", "target": "sale_price_pln", "expected_rows": 100_000},
        ]
        for specification in specifications:
            data_file(specification["file"])
        print("All three local source files are available")
        """),
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

        for specification in specifications:
            dataset = datasets[specification["name"]]
            if dataset.row_count != specification["expected_rows"]:
                raise RuntimeError(
                    f"{dataset.name} has {dataset.row_count} rows; expected {specification['expected_rows']}"
                )
        print("Dataset row-count contract verified")
        """),
        markdown("""
        ## 4. Create and publish the training pipeline

        The fixed tutorial definition runs AutoFE and six AutoML trials with three
        leakage-safe folds over the full 10,000-row training dataset. The frontend is the
        recommended interface for designing flexible pipeline definitions; this JSON path
        is intentionally deterministic for API automation.
        """),
        code("""
        from examples.example01_lifecycle import build_training_definition

        training = datasets[TRAINING_DATASET_NAME]
        training_definition = build_training_definition(
            training.logical_id,
            model_name=MODEL_NAME,
            output_name_prefix=OUTPUT_NAME_PREFIX,
        )
        try:
            training_pipeline = client.pipeline_by_name(
                business_case_name=BUSINESS_CASE_NAME,
                pipeline_name=TRAINING_PIPELINE_NAME,
            )
            training_version = client.latest_published_pipeline_version(str(training_pipeline["id"]))
            created = False
        except ResourceNotFoundError:
            training_pipeline = client.create_pipeline(
                business_case_id=str(business_case["id"]),
                name=TRAINING_PIPELINE_NAME,
                description="Fixed Example01 full-scope AutoML and AutoFE training workflow.",
                pipeline_type="automl",
                definition=training_definition,
            )
            training_version = client.publish_pipeline_draft(str(training_pipeline["id"]))
            created = True
        print({
            "action": "CREATED" if created else "FOUND",
            "pipeline": training_pipeline["name"],
            "published_version": training_version["version_number"],
        })
        """),
        markdown("## 5. Run full-scope training and resolve its model artifact"),
        code("""
        try:
            training_run = client.pipeline_run_by_operation_key(
                business_case_name=BUSINESS_CASE_NAME,
                pipeline_name=TRAINING_PIPELINE_NAME,
                operation_key=TRAINING_RUN_KEY,
            )
            started = False
        except ResourceNotFoundError:
            training_run = client.run_pipeline_by_name(
                business_case_name=BUSINESS_CASE_NAME,
                pipeline_name=TRAINING_PIPELINE_NAME,
                runtime_parameters={"client_operation_key": TRAINING_RUN_KEY},
            )
            started = True
        print(f"{'STARTED' if started else 'REUSED'} training run {training_run.id}; status={training_run.status}")

        training_finished = client.wait_for_pipeline_run(
            training_run,
            timeout=3600,
            on_update=lambda current: print(
                f"status={current.status}; current_terminal_rows={current.processed_row_count}"
            ),
        )
        model = client.model_for_pipeline_run(training_finished)
        if model["name"] != MODEL_NAME:
            raise RuntimeError(f"Expected model {MODEL_NAME!r}, got {model['name']!r}")
        print({
            "run_id": training_finished.id,
            "full_training_scope_rows": training.row_count,
            "terminal_holdout_output_rows": training_finished.processed_row_count,
            "model_id": model["id"],
            "model_version": model["version"],
            "stage": model["stage"],
        })
        """),
        markdown("""
        ## 6. Create the pinned batch-scoring pipeline

        Scoring uses the exact immutable model and fitted Feature Engineering state from
        the training run. It does not refit transformations on the scoring cohort.
        """),
        code("""
        from examples.example01_lifecycle import build_batch_scoring_definition

        scoring = datasets[SCORING_DATASET_NAME]
        batch_definition = build_batch_scoring_definition(
            model,
            scoring.logical_id,
            output_name_prefix=OUTPUT_NAME_PREFIX,
        )
        try:
            batch_pipeline = client.pipeline_by_name(
                business_case_name=BUSINESS_CASE_NAME,
                pipeline_name=BATCH_PIPELINE_NAME,
            )
            batch_version = client.latest_published_pipeline_version(str(batch_pipeline["id"]))
            created = False
        except ResourceNotFoundError:
            batch_pipeline = client.create_pipeline(
                business_case_id=str(business_case["id"]),
                name=BATCH_PIPELINE_NAME,
                description="Example01 full-scope batch inference with a pinned training bundle.",
                pipeline_type="batch_scoring",
                definition=batch_definition,
            )
            batch_version = client.publish_pipeline_draft(str(batch_pipeline["id"]))
            created = True
        print({
            "action": "CREATED" if created else "FOUND",
            "pipeline": batch_pipeline["name"],
            "published_version": batch_version["version_number"],
            "model_id": model["id"],
        })
        """),
        markdown("## 7. Score all 100,000 rows and inspect a bounded preview"),
        code("""
        try:
            batch_run = client.pipeline_run_by_operation_key(
                business_case_name=BUSINESS_CASE_NAME,
                pipeline_name=BATCH_PIPELINE_NAME,
                operation_key=BATCH_RUN_KEY,
            )
            started = False
        except ResourceNotFoundError:
            batch_run = client.run_pipeline_by_name(
                business_case_name=BUSINESS_CASE_NAME,
                pipeline_name=BATCH_PIPELINE_NAME,
                runtime_parameters={"client_operation_key": BATCH_RUN_KEY},
            )
            started = True
        print(f"{'STARTED' if started else 'REUSED'} batch run {batch_run.id}; status={batch_run.status}")
        batch_finished = client.wait_for_pipeline_run(batch_run, timeout=3600)

        prediction_dataset_id = client.prediction_dataset_id(batch_finished)
        prediction_preview = client.preview_dataset(prediction_dataset_id, limit=5)
        if prediction_preview["row_count"] != 100_000:
            raise RuntimeError(f"Expected 100,000 prediction rows, got {prediction_preview['row_count']}")
        print({
            "run_id": batch_finished.id,
            "processed_rows": batch_finished.processed_row_count,
            "prediction_dataset_id": prediction_dataset_id,
            "total_prediction_rows": prediction_preview["row_count"],
            "preview_rows": prediction_preview["returned_count"],
        })
        prediction_preview["records"]
        """),
        markdown("""
        ## 8. Create the performance-monitoring pipeline

        Monitoring pins the immutable prediction dataset and joins it with the delayed
        actuals family. The frontend remains the recommended interface for flexible join,
        quality-rule and monitoring design.
        """),
        code("""
        from examples.example01_lifecycle import build_monitoring_definition

        actuals = datasets[ACTUALS_DATASET_NAME]
        monitoring_definition = build_monitoring_definition(
            batch_finished,
            actuals.logical_id,
            output_name_prefix=OUTPUT_NAME_PREFIX,
        )
        try:
            monitoring_pipeline = client.pipeline_by_name(
                business_case_name=BUSINESS_CASE_NAME,
                pipeline_name=MONITORING_PIPELINE_NAME,
            )
            monitoring_version = client.latest_published_pipeline_version(str(monitoring_pipeline["id"]))
            created = False
        except ResourceNotFoundError:
            monitoring_pipeline = client.create_pipeline(
                business_case_id=str(business_case["id"]),
                name=MONITORING_PIPELINE_NAME,
                description="Example01 full-scope performance monitoring with delayed actuals.",
                pipeline_type="monitoring",
                definition=monitoring_definition,
            )
            monitoring_version = client.publish_pipeline_draft(str(monitoring_pipeline["id"]))
            created = True
        print({
            "action": "CREATED" if created else "FOUND",
            "pipeline": monitoring_pipeline["name"],
            "published_version": monitoring_version["version_number"],
        })
        """),
        markdown("## 9. Join all predictions with actuals and compute full-scope metrics"),
        code("""
        try:
            monitoring_run = client.pipeline_run_by_operation_key(
                business_case_name=BUSINESS_CASE_NAME,
                pipeline_name=MONITORING_PIPELINE_NAME,
                operation_key=MONITORING_RUN_KEY,
            )
            started = False
        except ResourceNotFoundError:
            monitoring_run = client.run_pipeline_by_name(
                business_case_name=BUSINESS_CASE_NAME,
                pipeline_name=MONITORING_PIPELINE_NAME,
                runtime_parameters={"client_operation_key": MONITORING_RUN_KEY},
            )
            started = True
        print(f"{'STARTED' if started else 'REUSED'} monitoring run {monitoring_run.id}; status={monitoring_run.status}")
        monitoring_finished = client.wait_for_pipeline_run(monitoring_run, timeout=3600)
        report = client.scoring_report_for_run(
            monitoring_finished,
            business_case_name=BUSINESS_CASE_NAME,
        )
        if report["evaluated_row_count"] != 100_000:
            raise RuntimeError(f"Expected 100,000 evaluated rows, got {report['evaluated_row_count']}")
        metrics = {
            metric["id"]: metric["value"]
            for metric in report["evaluation"].get("metrics", [])
        }
        print({
            "run_id": monitoring_finished.id,
            "processed_rows": monitoring_finished.processed_row_count,
            "evaluated_rows": report["evaluated_row_count"],
            "report_id": report["id"],
            "metrics": metrics,
        })
        """),
        markdown("## 10. Promote the trained model to production"),
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
        markdown("## 11. Create or resume a stable online model service"),
        code("""
        try:
            service = client.deployment_by_name(MODEL_SERVICE_NAME, include_archived=True)
            created = False
            if service.status == "archived":
                raise RuntimeError("This example service is archived; choose a new EXAMPLE_INSTANCE")
            champion = next(
                item for item in service.active_revision["assignments"]
                if item["role"] == "champion"
            )
            if str(champion["model_id"]) != str(promoted["id"]):
                raise RuntimeError("The existing example service uses a different champion model")
            if service.status == "stopped":
                service = client.set_deployment_status(
                    service,
                    status="running",
                    reason="Resume Example01 master service",
                )
        except ResourceNotFoundError:
            try:
                service = client.create_deployment(
                    name=MODEL_SERVICE_NAME,
                    model_id=str(promoted["id"]),
                    retention_days=365,
                )
                created = True
            except ConflictError as exc:
                raise RuntimeError(
                    "This EXAMPLE_INSTANCE is already used by an inaccessible model service. "
                    "Choose another label in section 1."
                ) from exc
        print({
            "action": "CREATED" if created else "FOUND",
            "service": service.name,
            "status": service.status,
            "endpoint": service.endpoint_url,
            "revision": service.active_revision.get("version_number"),
        })
        """),
        markdown("## 12. Score through `ml_app_client`"),
        code("""
        contract = client.deployment_input_contract(service)
        online_features = dict(contract["example_features"])
        client_prediction = client.predict(
            service,
            record_id="Example01-master-client-record-001",
            features=online_features,
            idempotency_key=f"Example01-master-client-{EXAMPLE_INSTANCE}",
            correlation_id=f"Example01-master-client-{EXAMPLE_INSTANCE}",
        )
        print({
            "request_id": client_prediction.request_id,
            "model_id": client_prediction.model_id,
            "served_role": client_prediction.served_role,
            "prediction": client_prediction.predictions[0]["prediction"],
            "warnings": list(client_prediction.warnings),
        })
        """),
        markdown("""
        ## 13. Score the same service through direct REST

        This uses the public token and `requests.Session` created in section 0. It does not
        depend on private internals of `MLAppClient` and does not ask for credentials again.
        """),
        code("""
        deployments_response = rest_session.get(f"{API}/serving/deployments", timeout=30)
        deployments_response.raise_for_status()
        matches = [
            item for item in deployments_response.json()
            if item["name"] == MODEL_SERVICE_NAME
        ]
        if len(matches) != 1:
            raise RuntimeError(f"Expected one visible service named {MODEL_SERVICE_NAME!r}")
        rest_service = matches[0]

        contract_response = rest_session.get(
            f"{API}/serving/deployments/{rest_service['id']}/input-contract",
            timeout=30,
        )
        contract_response.raise_for_status()
        rest_features = contract_response.json()["example_features"]

        prediction_response = rest_session.post(
            f"{API}/serving/deployments/{rest_service['id']}/predictions",
            headers={
                "Idempotency-Key": f"Example01-master-rest-{EXAMPLE_INSTANCE}",
                "X-Correlation-ID": f"Example01-master-rest-{EXAMPLE_INSTANCE}",
            },
            json={"instances": [{
                "record_id": "Example01-master-rest-record-001",
                "features": rest_features,
            }]},
            timeout=120,
        )
        prediction_response.raise_for_status()
        rest_prediction = prediction_response.json()
        print({
            "request_id": rest_prediction["request_id"],
            "model_id": rest_prediction["model_id"],
            "served_role": rest_prediction["served_role"],
            "prediction": rest_prediction["predictions"][0]["prediction"],
            "warnings": rest_prediction["warnings"],
        })
        """),
        markdown("## 14. Verify durable Inference Log entries and summarize the lifecycle"),
        code("""
        client_history = client.inference_history(
            service,
            record_id="Example01-master-client-record-001",
            limit=10,
        )
        rest_history = client.inference_history(
            service,
            record_id="Example01-master-rest-record-001",
            limit=10,
        )
        if not client_history.get("items") or not rest_history.get("items"):
            raise RuntimeError("Expected both online requests to be present in Inference Log")

        summary = {
            "test_account": profile["login_name"],
            "business_case_id": business_case["id"],
            "training_rows": training.row_count,
            "training_run_id": training_finished.id,
            "model_id": promoted["id"],
            "prediction_rows": prediction_preview["row_count"],
            "batch_run_id": batch_finished.id,
            "monitoring_evaluated_rows": report["evaluated_row_count"],
            "monitoring_run_id": monitoring_finished.id,
            "monitoring_report_id": report["id"],
            "deployment_id": service.id,
            "client_request_id": client_prediction.request_id,
            "rest_request_id": rest_prediction["request_id"],
            "inference_log_verified": True,
        }
        summary
        """),
        markdown("""
        ## What this proves

        A base test user can own and execute the complete public lifecycle without an
        administrator grant. The run covers every declared input row; sampling is used
        only for the five-row prediction preview. All long-running calculations execute
        in backend workers, and the notebook retains only bounded metadata and previews.
        """),
    ])


if __name__ == "__main__":
    build()
    print(f"Generated numbered API-usage notebooks in {OUTPUT}")
