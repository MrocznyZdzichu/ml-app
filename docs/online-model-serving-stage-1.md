# Online model serving — Stage 1

Online serving exposes a stable service endpoint while pinning every execution
to an immutable deployment revision and training inference bundle.

## Lifecycle and roles

Model stage and service role are independent. `candidate`, `staging`,
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

History is cursor-paginated and may be filtered by record ID:

```http
GET /api/v1/serving/deployments/{deployment_id}/inference-log?limit=50&record_id=estate-1
```

## Audit and failure guarantees

Inference history is a logical log backed by request and searchable item rows,
not one platform artifact per prediction. It stores the full input and response,
the exact deployment revision and model, routing role, fallback use, warnings,
errors, and latency. Retention defaults to 365 days.

The request is durably accepted before model execution. A successful prediction
is returned only after its output is persisted. If this guarantee cannot be
met, the API returns `503`. Runtime containers log request IDs, counts, latency,
and artifact hashes without logging credentials.

Machine credentials authenticate existing accounts. Existing group and Business
Case grants remain the only authorization source. Raw credentials are returned
once; only their SHA-256 hashes are stored.

See `examples/API-usage/online_model_serving_via_client.ipynb` for the supported
Python workflow.
