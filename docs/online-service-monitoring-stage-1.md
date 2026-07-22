# Online Service Monitoring — stage 1

Stage 1 creates an immutable report on demand from a retained deployment
Inference Log and, optionally, a later actuals dataset. It does not schedule runs, emit alerts
or make promotion, rollback, routing or other operational decisions.

## Contract

A run selects one deployment and a half-open scoring-time window
`[since, until)`.
The worker freezes the selection at run creation, processes the full matching
scope and reports request and row counts. It never silently replaces that scope
with a sample. The scoring timestamp is the current time basis; event time,
period identifiers and business dimensions remain extension points.

The optional `aggregation_granularity` is `none`, `hour`, `day`, `week` or
`month`. Aggregation uses `scored_at` in explicit UTC calendar buckets, runs over the complete selected snapshot
in DuckDB and returns one bounded row per calendar bucket, including empty
buckets. Every row includes its calendar boundaries and the effective observed
subrange when the requested window starts or ends inside that bucket.
When actuals are available, `time_aggregation.performance_series` additionally
contains classification or regression metric points calculated over every
matched row in each bucket. These are grouped full-bucket computations, not
samples. The UI presents numeric values as a bucket-by-metric table. Users can
select up to eight bucket rows and compare their curve, distribution or residual
diagnostics as separate chart series; the full-window view retains the complete
scoring-report diagnostics.

The visualization keeps operational charts in separate **Traffic**, **Latency**,
and **Failures / fallbacks** tabs. A **Classification** or **Regression** tab is
shown only when actuals were joined. That quality tab switches between the
complete window and the selected aggregation granularity. Bucket boundaries are
stored and requested in UTC; the browser renders their labels in its local time
zone without changing bucket identity.

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
  "until": "2026-07-08T00:00:00Z",
  "aggregation_granularity": "hour"
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
  "aggregation_granularity": "hour",
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

Chart diagnostics for explicitly selected aggregation buckets are available at:

```http
GET /api/v1/serving/monitoring-runs/{run_id}/bucket-evaluations?bucket_start=2026-07-01T00%3A00%3A00%2B00%3A00
```

Repeat `bucket_start` for up to eight buckets from the immutable report. Each
result uses every matched row in that bucket and is calculated from the
immutable joined Parquet dataset preserved by the successful run. Only bounded
chart payloads are returned, never row-level joined data. The endpoint requires
a successful run with joined actuals and accepts only bucket starts recorded in
that report.

Finished runs can be logically archived with
`POST /api/v1/serving/monitoring-runs/{run_id}/archive`. Archive every finished
run for one service with
`POST /api/v1/serving/deployments/{deployment_id}/monitoring-runs/archive`.
Archived runs disappear from default lists but remain individually readable,
audited and connected to their immutable report, snapshot and lineage. Pass
`include_archived=true` to either list endpoint to retrieve them.

## Python client

```python
from ml_app_client import MLAppClient

client = MLAppClient.connect()
operational = client.run_deployment_monitoring(
    "Estates Service",
    since="2026-07-01T00:00:00Z",
    until="2026-07-08T00:00:00Z",
    aggregation_granularity="hour",
)
operational_report = client.wait_for_online_monitoring_run(operational)

run = client.run_deployment_monitoring(
    "Estates Service",
    actuals="estates_actuals",
    since="2026-07-01T00:00:00Z",
    until="2026-07-08T00:00:00Z",
    aggregation_granularity="hour",
    actuals_target_column="sale_price",
    actuals_record_id_column="estate_id",
)
report = client.wait_for_online_monitoring_run(run)
bucket_charts = client.get_online_monitoring_bucket_evaluations(
    report,
    ["2026-07-01T00:00:00+00:00", "2026-07-01T01:00:00+00:00"],
)
print(report.report["performance"])

client.archive_online_monitoring_run(operational, reason="Dashboard cleanup")
archived = client.list_online_monitoring_runs(
    "Estates Service", include_archived=True
)
```

The client accepts typed `Deployment` and `Dataset` objects or discoverable
names/IDs. UI and client use the same REST semantics and access checks.

## Batch compatibility

Online monitoring does not modify the monitoring pipeline template. Batch
scoring still produces an immutable prediction dataset, and the batch monitoring
pipeline still joins it to actuals and creates its established report. Both
paths reuse backend evaluation concepts while retaining separate run and report
contracts.
