# Online Service Monitoring — stage 1

Stage 1 creates an immutable report on demand from a retained deployment
Inference Log and, optionally, a later actuals dataset. It does not schedule runs, emit alerts
or make promotion, rollback, routing or other operational decisions.

## Contract

A run selects one deployment and a closed scoring-time window (`since`, `until`).
The worker freezes the selection at run creation, processes the full matching
scope and reports request and row counts. It never silently replaces that scope
with a sample. The scoring timestamp is the current time basis; event time,
period identifiers and business dimensions remain extension points.

Without actuals, the report covers service health, traffic, latency, errors,
fallback use, input statistics and prediction distributions. Its
`evaluation_scope` is `operational`, `actuals.status` is `not_provided`, and
performance is explicitly marked as not evaluated. Missing actuals are never
presented as zero effectiveness or zero coverage.

When actuals are supplied, they must be attached to the deployment Business Case
with the `monitoring_actuals` role. The automatic join chooses, in order:

1. `prediction_id`;
2. `request_id` plus `record_id`;
3. `record_id`, only when it is unique on both sides.

The request can override the strategy and actuals key or target columns. Missing
or ambiguous keys fail with an actionable error rather than producing unreliable
metrics. A scoring request without a stable business `record_id` still succeeds,
but the generated technical ID is explicitly warned as unsuitable for reliable
actuals matching.

The report contains the selected scope, actuals coverage, serving errors and
latency, input and prediction statistics, overall effectiveness and breakdowns
by service revision, actually served model, bundle and role. Fallback traffic is
kept visible. Shadow outcomes can be compared when the actuals join makes that
possible. The prediction snapshot and report are always immutable, lineaged
artifacts; joined evaluation data is additionally created when actuals are
supplied. Re-running with newer actuals creates a new run and report.

## REST

An operational report needs only the retained scoring-time window:

```http
POST /api/v1/serving/deployments/{deployment_id}/monitoring-runs
Content-Type: application/json

{
  "since": "2026-07-01T00:00:00Z",
  "until": "2026-07-08T00:00:00Z"
}
```

Add actuals when performance metrics are required:

```http
POST /api/v1/serving/deployments/{deployment_id}/monitoring-runs
Content-Type: application/json

{
  "since": "2026-07-01T00:00:00Z",
  "until": "2026-07-08T00:00:00Z",
  "actuals_dataset_id": "dataset-version-id",
  "actuals_target_column": "outcome",
  "join": {"strategy": "auto", "actuals_record_id_column": "customer_id"}
}
```

The call returns `202 Accepted`. Poll
`GET /api/v1/serving/monitoring-runs/{run_id}` until `succeeded` or `failed`.
List one deployment's history at
`GET /api/v1/serving/deployments/{deployment_id}/monitoring-runs`; the global
bounded list used by the comparative dashboard is
`GET /api/v1/serving/monitoring-runs`.

## Python client

```python
from ml_app_client import MLAppClient

client = MLAppClient.connect()
operational = client.run_deployment_monitoring(
    "Estates Service",
    since="2026-07-01T00:00:00Z",
    until="2026-07-08T00:00:00Z",
)
operational_report = client.wait_for_online_monitoring_run(operational)

run = client.run_deployment_monitoring(
    "Estates Service",
    actuals="estates_actuals",
    since="2026-07-01T00:00:00Z",
    until="2026-07-08T00:00:00Z",
    actuals_target_column="sale_price",
    actuals_record_id_column="estate_id",
)
report = client.wait_for_online_monitoring_run(run)
print(report.report["performance"])
```

The client accepts typed `Deployment` and `Dataset` objects or discoverable
names/IDs. UI and client use the same REST semantics and access checks.

## Batch compatibility

Online monitoring does not modify the monitoring pipeline template. Batch
scoring still produces an immutable prediction dataset, and the batch monitoring
pipeline still joins it to actuals and creates its established report. Both
paths reuse backend evaluation concepts while retaining separate run and report
contracts.
