# Performance audit — 2026-07

> **Dated snapshot:** this file records measurements and changes from the audit.
> It is not the current backlog. Since the snapshot, bounded page contracts have
> also been added for Business Cases, deployments, users, groups, grants,
> versions, runs, and model/report families. The frontend and public Python
> client use those contracts, and several large compatibility facades have been
> split. See [Architecture](architecture.md) and
> [UI scalability audit](ui-scalability-audit-2026-07.md) for current boundaries.

This is a code-level and local-runtime audit of the complete repository. It
covers the FastAPI API, PostgreSQL repositories and access policy, Celery
workers, DuckDB/Parquet analytics, model runtime, React client, Python client,
container startup, and the most important end-to-end execution paths.

The audit does not claim production latency or throughput improvements without
a representative production dataset and concurrency profile. The reductions
below are structural: fewer database round trips, fewer complete relation
passes, bounded file reads, and removal of synchronous maintenance work from
the inference request path.

## Execution model

The main data plane is directionally correct for large datasets:

- persistent pipeline outputs and reusable analytical conversions use Parquet;
- analytical work is delegated to DuckDB and returns bounded aggregates,
  histograms, summaries, or paginated projections;
- long-running analytics, pipelines, ML, export, replay, and monitoring work
  runs asynchronously in Celery;
- PostgreSQL stores metadata, access control, lineage, run state, and the hot
  Inference Log rather than materializing analytical datasets in API memory;
- online monitoring streams the selected log range into a columnar snapshot
  before full-scope DuckDB processing;
- the browser consumes bounded presentation contracts rather than complete
  datasets.

No evidence justified introducing Spark. The current PostgreSQL, DuckDB,
Parquet, Redis/Celery, and React stack should be measured and scaled first.

## Corrected bottlenecks

### Inference hot path

- Model artifacts were read in full and SHA-256 hashed on every scoring
  request, even when the deserialized model was already cached. Hashing now
  streams fixed-size chunks and is cached against filesystem identity and
  metadata. A changed artifact invalidates the cache key.
- Successful inference synchronously executed the retention DELETE operation.
  Retention remains a scheduled Celery task and is no longer part of request
  latency or database write contention.

### Catalog and access-control queries

- Business Case listing resolved access separately for every item. Effective
  roles are now resolved by one set-oriented union over ownership, direct
  grants, and group grants; the catalog query is restricted to accessible IDs.
- Business Case name uniqueness no longer materializes the complete catalog.
- dataset access through several Business Cases now resolves all candidate
  roles in one operation.
- deployment listing applies the visible Business Case set in PostgreSQL rather
  than loading all deployments and filtering with per-item access checks.
- model usage resolves active deployment assignments for all model versions in
  one query.
- effective resource access now uses one union over ownership, direct grants,
  active group grants, and Business Case inheritance instead of serial
  group/grant/attachment lookups;
- dataset catalogs are filtered by accessible IDs in PostgreSQL. Uploading a
  new family version and resolving `latest` no longer scan the global dataset
  catalog;
- repeated permission checks in dataset, Business Case, pipeline, serving, and
  run mutation paths were collapsed to one check at the required role.

### Pipeline polling and registry enrichment

- the Jobs screen polls run history while work is active. Its backend previously
  queried once per visible pipeline owner, merged all results, sorted them, and
  only then applied pagination. It now issues one globally ordered and paginated
  query over the visible pipeline IDs;
- pipeline and model catalogs now fetch all relevant pipeline versions in one
  query instead of one query per pipeline.
- pipeline catalog summaries aggregate version counts and load at most one
  selected definition per pipeline instead of deserializing every historical
  definition;
- run creation resolves the latest published version with a bounded query and
  resolves dataset families with logical-ID filters;
- model and fitted-transform artifacts used by a run are scoped to its Business
  Case, grouped once, and reused across scoring steps;
- the 750 ms UI and Python-client wait loops use a compact status projection.
  Full events, parameters, and output manifests are fetched once after
  completion or when the user opens run details;
- opening one generated model or report calls its detail endpoint instead of
  downloading its entire registry.

### Lineage and registry reads

- dataset lineage traversal changed from per-node artifact and dataset lookups
  to breadth-first batch reads;
- dependency resolution uses ID maps rather than repeated linear searches and
  correctly preserves legacy flat dependencies when port-aware lineage is also
  present;
- model enrichment fetches only referenced pipeline versions and fitted
  transforms from referenced training runs;
- scoring-report family/version reads are restricted by logical report ID
  instead of loading every visible report.

### Online serving

- calls from the API to the private model runtime reuse a bounded keep-alive
  connection pool instead of opening a new TCP connection for every prediction;
- deployment revision numbers are allocated with a scalar `MAX + 1` query under
  a deployment row lock instead of loading all historical revisions. The lock
  also prevents duplicate allocation under concurrent updates;
- lifecycle and bundle validation remains active for every request, but registry
  data for all assigned models is loaded in batches.

### Full-scope model evaluation

Exact metrics still cover the complete selected scope. Redundant scans were
removed without introducing sampling:

- binary-classification evaluation performs 7 instead of 9 complete relation
  passes by reusing score bounds and combining probability/calibration
  aggregates;
- regression evaluation performs 5 instead of 6 complete relation passes by
  reusing residual bounds;
- grouped numeric/categorical profiling derives group moments, the total, and
  between-group spread from one grouped relation pass instead of three;
- CV fold assignments are loaded only after the training memory preflight, so a
  job rejected for resource limits does not first materialize the fold vector.

### Database access paths

The migration adds composite indexes matching repeated filters and ordering:

- `pipeline_runs (pipeline_id, created_at DESC)`;
- `pipeline_versions (pipeline_id, version_number)`;
- `serving_deployments (business_case_id, updated_at DESC)`;
- `serving_inference_requests (deployment_id, requested_role, created_at, id)`.
- `pipelines (business_case_id, updated_at DESC)`;
- `artifacts (business_case_id, type, created_at DESC)` plus partial expression
  indexes for report families and fitted-transform lineage;
- grant and group-membership indexes matching effective-access unions;
- `business_case_data_attachments (business_case_id, data_asset_id)`.

### Smaller corrections

- reusable SHA-256 calculation in the backend is streaming rather than
  `read_bytes()` based;
- full-profile pair-count estimation no longer creates an intermediate list of
  all combinations;
- the cached rebuild path starts PostgreSQL, Redis, and MinIO before starting
  application containers, preventing a false application failure after the
  infrastructure was stopped.

## Structural impact

| Path | Before | After |
| --- | --- | --- |
| Model artifact hash | complete file read per request | one streamed read per observed file identity |
| Inference retention | one synchronous DELETE per success | scheduled background retention |
| Business Case catalog | approximately one role query per item | one role resolution plus one filtered catalog query |
| Resource access | serial group, direct-grant, and BC-family queries | one set-oriented union |
| Dataset family lookup | global dataset scan | logical-ID query plus accessible-ID filter |
| Jobs history | one run query per pipeline owner plus Python pagination | one filtered, ordered, paginated query |
| Active run polling | complete run JSON every 750 ms | compact scalar status; full result once |
| Pipeline catalog versions | every historical definition | aggregate counters plus one selected definition |
| Pipeline version enrichment | one query per pipeline | one query for referenced/visible version IDs |
| Dataset lineage | up to two point queries per traversed node | two batch queries per graph layer |
| Generated artifact opening | complete model/report catalog | one artifact detail query |
| Model deployment usage | one query per model version | one query for all versions |
| API to model runtime | new TCP connection per prediction | bounded keep-alive pool |
| Deployment revision allocation | load and count all revisions | scalar allocation under row lock |
| Binary evaluation | 9 full relation passes | 7 full relation passes |
| Regression evaluation | 6 full relation passes | 5 full relation passes |
| Group relation profile | 3 full relation passes | 1 grouped pass |

## Priority risks identified at audit time

1. Add persisted resource telemetry for DuckDB jobs: bytes read/written, spill
   bytes, peak memory, relation size, phase timings, and cache hit/miss state.
   This is required before choosing further engine or infrastructure changes.
2. Benchmark model evaluation on representative wide and large Parquet inputs.
   Seven and five exact passes are improved but still material; a reusable
   projected temporary relation is the next candidate when measurements justify
   its storage and cleanup cost.
3. Add cursor pagination or explicit bounded summary contracts to remaining
   potentially unbounded catalogs, especially Business Cases, deployments,
   users, groups, and sharing principals.
4. Replace process-local conversion locks and remaining legacy process-local
   stores with shared, idempotent coordination before horizontally scaling API
   replicas.
5. Load-test the single model-runtime service and the new connection pool. Scale
   runtime replicas only from measured concurrency, latency, model-size, and
   memory-residency data.
6. Move large production index creation out of application startup into an
   online migration process. Plain startup `CREATE INDEX` can hold locks and
   make a deployment exceed its availability budget on a large table.
7. Split and lazy-load additional frontend workbench code when bundle and
   interaction profiling identifies a real user-visible delay. The current
   production build already creates several feature chunks, but the main
   application bundle remains substantial.
8. Keep exact high-cardinality profiling asynchronous and observable. Exact
   distinct counts, medians, and wide correlations can be intrinsically
   expensive; preview sampling must remain explicitly separate from full-scope
   results.
9. Replace the remaining owner-wide artifact scan in the generic dependency
   resolver with indexed JSONB dependency projections after measuring real graph
   fan-out and validating compatibility with legacy lineage shapes.
10. Benchmark CSV ingestion separately. The current schema inspection is
    streaming and bounded in memory, but it still parses every CSV cell in
    Python; a DuckDB-native validation/conversion path is a candidate only if it
    preserves duplicate-header, mixed-type, encoding, and error semantics.
11. Consider a versioned workspace-catalog endpoint if request tracing shows
    that six parallel summary calls and their repeated access-set resolution
    dominate login refresh latency. It should add pagination and preserve the
    public REST/Python-client contract rather than becoming a UI-only shortcut.

## Verification

- cached and regular `rebuild-run.bat` paths complete with the full stack;
- 274 backend tests pass;
- 52 Python client and executable-example tests pass;
- the React TypeScript production build passes;
- all 12 performance indexes introduced by the two audit migrations are present;
- the model-runtime hash cache records a hit on the second load;
- API, frontend, PostgreSQL, Redis, MinIO, worker, scheduler, and model runtime
  are running, and service logs show successful startup and worker execution.
