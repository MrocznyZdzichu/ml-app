# Online model serving — Stage 1

Online serving exposes a stable service endpoint while pinning every execution
to an immutable deployment revision and training inference bundle.

## Lifecycle and roles

Model stage and service role are independent. `developed`, `staging`,
`production`, and `archived` describe model readiness. One active service
revision contains exactly one `champion`, at most one `fallback`, and any number
of `challenger` and `shadow` assignments.

- The champion serves the stable public prediction endpoint.
- A shadow receives the same live input; its output is retained but does not
  change the response.
- A challenger has an explicit protected prediction endpoint and asynchronous
  replay over a pinned snapshot of champion/fallback history.
- The fallback is attempted once only for a technical champion failure. Input
  validation failures return `422` and never activate fallback.

Changing roles creates and atomically activates a new immutable revision. The
service URL does not change.

An active assignment constrains lifecycle changes. Champions and fallbacks must
remain `production`; challengers and shadows must remain `staging` or
`production`. An incompatible stage change returns `409` with the blocking
service and role. Operators should train a new immutable model version, activate
a new service revision, and only then downgrade or archive the detached version.
Historical inactive revisions remain reproducible and do not block lifecycle
changes.

Services can be stopped and started without deleting history. Starting validates
the active revision again. Rollback copies a selected historical configuration
into a new immutable revision rather than reactivating or mutating the old row.
Archiving is terminal: it disables the endpoint, removes active assignments and
hides the service from default listings while preserving revisions, Inference
Log and audit history.

## UI lifecycle test

Prepare three compatible immutable model versions in one Business Case before
starting: an initial `production` champion, a replacement `production` champion,
and a `staging` or `production` shadow. Also prepare one valid feature payload
matching the models' inference contract.

1. Open **Online inference > Model services**, choose **New service**, enter a
   unique name, select the initial champion, and create the service. Confirm that
   the Overview shows revision `v1`, status `running`, and the expected champion.
2. Open the **Test** tab. Enter a stable record ID and the JSON feature payload,
   leave the target set to `champion`, and run scoring. Record the request ID,
   returned model, prediction and revision. Confirm the request in Inference Log.
3. Return to **Overview** and select **Configure models**. Assign the replacement
   model as the only `champion`, assign the selected model as `shadow`, enter a
   reason, and activate the revision. Confirm revision `v2`; the endpoint URL
   must remain unchanged.
4. Return to **Test** and score the same feature payload again. Use a new request
   or idempotency key if the UI exposes it. Confirm the response used the new
   champion and the detailed Inference Log contains both `champion` and `shadow`
   executions. The shadow output must not replace the response.
5. Return to **All model services**, select **Archive**, enter a reason, and
   confirm. The service must disappear from the active table and its endpoint
   must no longer accept scoring. Its governed history remains available through
   `GET /serving/deployments?include_archived=true` or the Python client.

## REST contract

Create a service with a production model as its first champion:

```http
POST /api/v1/serving/deployments
Authorization: Bearer <token>
Content-Type: application/json

{"name":"Estates Sell Prices Service","model_id":"<model-version-id>","retention_days":365}
```

Score from 1 to 1,000 records:

```http
POST /api/v1/serving/deployments/estates-sell-prices-service/predictions
Authorization: Bearer <token>
Idempotency-Key: valuation-2026-0001
X-Correlation-ID: crm-request-123
Content-Type: application/json

{"instances":[{"record_id":"estate-1","features":{"area":84,"rooms":4}}]}
```

`record_id` is optional, but the platform returns a governance warning when it
has to generate one because future actuals cannot be joined reliably.

Manual effectiveness and data-quality reports built from this log are described
in [Online Service Monitoring](online-service-monitoring-stage-1.md). This is a
separate execution path from the existing batch monitoring pipeline.

History is cursor-paginated and may be filtered by record ID:

```http
GET /api/v1/serving/deployments/{deployment_id}/inference-log?limit=50&record_id=estate-1
```

List and roll back immutable revisions or control endpoint availability:

```http
GET  /api/v1/serving/deployments/{deployment_id}/revisions
POST /api/v1/serving/deployments/{deployment_id}/revisions/{revision_id}/rollback
{"reason":"Regression detected after revision v7"}

POST /api/v1/serving/deployments/{deployment_id}/status
{"status":"stopped","reason":"Scheduled maintenance"}

POST /api/v1/serving/deployments/{deployment_id}/status
{"status":"archived","reason":"Lifecycle test complete"}
```

## Audit and failure guarantees

Inference history is a logical log backed by request and searchable item rows,
not one platform artifact per prediction. It stores the full input and response,
the exact deployment revision and model, routing role, fallback use, warnings,
errors, and latency. Failed champion, fallback, and shadow executions are stored
as explicit execution rows. Retention defaults to 365 days and is enforced by a
daily maintenance task even when a service receives no new traffic.

An idempotency key is bound to the canonical request content, selected model,
role, and deployment revision. Reusing it for different content or a challenger
request returns `409` instead of returning an unrelated cached prediction.

The request is durably accepted before model execution. A successful prediction
is returned only after its output is persisted. If this guarantee cannot be
met, the API returns `503`. Runtime containers log request IDs, counts, latency,
and artifact hashes without logging credentials.

Machine credentials authenticate existing accounts. Existing group and Business
Case grants remain the only authorization source. Raw credentials are returned
once; only their SHA-256 hashes are stored.

See `examples/API-usage/Example01_10_create_model_service.ipynb`,
`Example01_11_score_with_client.ipynb`, and
`Example01_12_score_with_rest_api.ipynb` for the supported creation and scoring
workflow.
