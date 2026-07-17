# ML App Python client

`ml_app_client` is the supported, deliberately small integration interface for
dataset ingestion and pipeline execution. It streams CSV/Parquet uploads from
disk, resolves human-readable Business Case, dataset and pipeline names, starts
published pipeline versions, and polls bounded run metadata.

```python
from ml_app_client import MLAppClient

client = MLAppClient.from_env()
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

Set `ML_APP_API_URL` (default: `http://localhost:8000/api/v1`) and
`ML_APP_ACCESS_TOKEN`. For interactive use, call `client.login(login, password)`;
the client does not persist credentials. Uploading with a `logical_id` creates
an immutable next version. Pipeline execution selects the newest published
version and the backend records the resolved input versions, row counts and
lineage. Dataset previews are bounded to at most 50,000 rows. Downloads stream
the authorized persistent CSV/Parquet file to disk without buffering the full
dataset in client memory.

## Estates demo bootstrap

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
