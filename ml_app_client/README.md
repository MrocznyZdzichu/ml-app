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
```

Set `ML_APP_API_URL` (default: `http://localhost:8000/api/v1`) and
`ML_APP_ACCESS_TOKEN`. For interactive use, call `client.login(login, password)`;
the client does not persist credentials. Uploading with a `logical_id` creates
an immutable next version. Pipeline execution selects the newest published
version and the backend records the resolved input versions, row counts and
lineage.
