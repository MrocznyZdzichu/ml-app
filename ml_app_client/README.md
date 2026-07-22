# ML App Python client

`ml_app_client` is the supported, deliberately small integration interface for
dataset ingestion and pipeline execution. It streams CSV/Parquet uploads from
disk, resolves human-readable Business Case, dataset and pipeline names, starts
published pipeline versions, and polls bounded run metadata.

```python
from ml_app_client import MLAppClient

client = MLAppClient.connect()
dataset = client.upload_dataset_version(
    "training.parquet",
    business_case_name="Estates Sell Prices",
    dataset_name="sale-prices",
)
run = client.run_pipeline_by_name(
    business_case_name="Estates Sell Prices",
    pipeline_name="Estates Sell Prices - AutoFEML",
)
finished = client.wait_for_pipeline_run(run, timeout=3600)

# For a scoring run, inspect a bounded preview or stream the full output.
prediction_id = client.prediction_dataset_id(finished)
preview = client.preview_dataset(prediction_id, limit=20)
client.download_dataset(prediction_id, "predictions.parquet")

# Monitoring runs expose both a joined dataset and a bounded report artifact.
joined_id = client.output_dataset_id(finished)
report = client.scoring_report_for_run(finished, business_case_name="Estates Sell Prices")
```

Set `ML_APP_API_URL` (default: `http://localhost:8000/api/v1`) and optionally
`ML_APP_ACCESS_TOKEN`. `MLAppClient.connect()` uses that token when present and
otherwise prompts for a normal user's login and password without displaying or
persisting the password. Uploading with a `logical_id` creates
an immutable next version. Pipeline execution selects the newest published
version and the backend records the resolved input versions, row counts and
lineage. Dataset previews are bounded to at most 50,000 rows. Downloads stream
the authorized persistent CSV/Parquet file to disk without buffering the full
dataset in client memory.

## Online model serving

The same client creates versioned model services, scores through their stable
champion endpoint, and reads bounded pages from the durable inference log. A
model must first be promoted to the `production` stage.

Change the lifecycle stage by a friendly model name. The newest version is
selected unless an explicit version is provided:

```python
client.promote_model(
    "Estates Sell Prices - AutoFEML - Model",
    "staging",
    version="v11",
)

client.promote_model(
    "Estates Sell Prices - AutoFEML - Model",
    "production",
    version=11,
)

# Resolve the registry and family only once when changing several versions.
client.promote_model_versions(
    "Estates Sell Prices - AutoFEML - Model",
    "archived",
    versions=["v1", "v2", "v3"],
)
```

Allowed stages are `developed`, `staging`, `production`, and `archived`.
The previous input value `candidate` remains a deprecated compatibility alias.

Model services expose complete lifecycle operations through the same REST
contract: `deployment_revisions(...)`, `rollback_deployment(...)`, and
`set_deployment_status(...)` list history, create an auditable rollback revision,
and start, stop or archive an endpoint. Archiving is terminal: it removes the
service from default listings and active model usage while preserving revisions,
Inference Log and audit records. Use `list_deployments(include_archived=True)`
when archived services must be inspected.
Lifecycle stage describes model readiness; `champion`, `challenger`, `shadow`,
and `fallback` remain separate roles configured on a serving deployment.

```python
from ml_app_client import MLAppClient

client = MLAppClient.connect()
service = client.create_deployment(
    name="Estates Sell Prices Service",
    model_name="Estates Sell Prices - AutoFEML - Model",
)

result = client.predict(
    service,
    record_id="estate-2026-0001",
    features={"area": 84.0, "rooms": 4, "year_built": 2018},
    idempotency_key="valuation-2026-0001",
)
print(result.predictions[0]["prediction"])

page = client.inference_history(service, record_id="estate-2026-0001")

# Later, attach an actuals dataset to the Business Case as monitoring_actuals.
monitoring = client.run_deployment_monitoring(
    service,
    actuals="estates_actuals",
    since="2026-07-01T00:00:00Z",
    until="2026-07-08T00:00:00Z",
    actuals_target_column="sale_price",
    actuals_record_id_column="estate_id",
)
completed_monitoring = client.wait_for_online_monitoring_run(monitoring)
print(completed_monitoring.report["performance"])

# Retire a trial service without destroying its governed history.
client.set_deployment_status(
    service,
    status="archived",
    reason="Trial endpoint is no longer needed",
)
```

The equivalent REST operation is
`POST /api/v1/serving/deployments/{deployment_id}/status` with
`{"status":"archived","reason":"Trial endpoint is no longer needed"}`.

For machine integrations, create a revocable credential once and store only
the returned token in a secret manager. The credential authenticates the same
account and therefore uses the existing Business Case group grants.

```python
credential = client.create_api_credential("estates-production", expires_at="2027-01-01T00:00:00Z")
print(credential["token"])  # shown only in this response
```

## Estates demo bootstrap

For the complete lifecycle with explicit, user-chosen resource names, start with
`examples/API-usage/Example01_01_setup_business_case.ipynb` and continue in
filename order through training, batch scoring, monitoring and online serving.
The series is idempotent and uses only public client/REST operations.

Run the portable bootstrap after starting a new installation:

```powershell
python examples/bootstrap_estates_sell_prices.py
```

The script is idempotent. It verifies or creates the globally named Business
Case, attaches the three deterministic source dataset families, and publishes
the executable AutoFEML pipeline. If the name exists but is inaccessible, it
stops with `AuthorizationError` and asks for a grant rather than creating a
duplicate. It never copies model, fitted-transform, prediction, or report UUIDs
from another installation.
