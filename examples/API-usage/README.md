# Example 01 — complete ML lifecycle

Run the notebooks in filename order. The series starts from an empty installation
and demonstrates the same public REST contract through `ml_app_client`, ending
with one equivalent direct REST request.

1. `Example01_01_setup_business_case.ipynb`
2. `Example01_02_upload_datasets.ipynb`
3. `Example01_03_create_training_pipeline.ipynb`
4. `Example01_04_run_training.ipynb`
5. `Example01_05_create_batch_scoring_pipeline.ipynb`
6. `Example01_06_run_batch_scoring.ipynb`
7. `Example01_07_create_monitoring_pipeline.ipynb`
8. `Example01_08_run_monitoring.ipynb`
9. `Example01_09_promote_model.ipynb`
10. `Example01_10_create_model_service.ipynb`
11. `Example01_11_score_with_client.ipynb`
12. `Example01_12_score_with_rest_api.ipynb`

## Idempotency and scope

Each notebook exposes ordinary resource names as editable constants such as
`BUSINESS_CASE_NAME`, `TRAINING_PIPELINE_NAME`, and `MODEL_SERVICE_NAME`. Use
the same values throughout the series. Static resources are created only when absent. Pipeline runs reuse a
successful or active operation carrying the same stable operation key. Failed
attempts remain visible for audit and may be retried. Online predictions use an
`Idempotency-Key`.

For teaching purposes, idempotency is written out in the notebooks: first the
client searches for a resource and handles `ResourceNotFoundError`, then a
separate cell performs the upload, creation, attachment, or run. The examples do
not hide those platform operations behind `ensure_*` convenience methods.

The workflow never deletes Business Cases, models, predictions, reports,
deployments, lineage, or Inference Log history. It processes the complete
declared datasets: 10,000 training rows and 100,000 scoring/actual rows. Bounded
previews are used only for display.

Pipeline JSON in notebooks 01.03, 01.05 and 01.07 is deliberately fixed so the
automation path remains short and reproducible. The application frontend is the
recommended interface for flexible pipeline design and inference from existing
training and scoring runs.

Set `ML_APP_API_URL` when the API is not available at
`http://localhost:8000/api/v1`. Set `ML_APP_ACCESS_TOKEN` for non-interactive
authentication; otherwise the notebooks prompt for credentials.

The notebooks are generated deterministically by
`python examples/build_api_usage_notebooks.py`.
