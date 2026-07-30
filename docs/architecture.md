# Architecture

This document explains stable component boundaries. Use
[`CODEMAP.md`](../CODEMAP.md) for current file entry points and the feature
references for request/response details.

## System shape

```text
React UI ───────┐
                ├── FastAPI API ── PostgreSQL
Python client ──┘        │
                         ├── local artifact repository
                         ├── Redis/Celery workers ── DuckDB/Parquet
                         └── private model runtime
```

- FastAPI owns public HTTP contracts, authentication, authorization, validation,
  and use-case orchestration.
- PostgreSQL owns durable metadata, access control, lineage, run state, audit,
  deployment configuration, and the hot Inference Log.
- Celery executes profiling, pipelines, ML, replay, monitoring, and export jobs.
- DuckDB scans CSV/Parquet relations and returns bounded aggregates, previews,
  pages, or immutable Parquet outputs.
- `data/repository` is the active local artifact store. MinIO is present in
  Compose for future object-storage work but is not used as the primary store.
- The model runtime is private to the application network. The API validates and
  records an inference request before reporting success.

The current topology is a single-node development architecture. Component
interfaces allow future storage, queue, and runtime adapters, but those adapters
are not implemented merely by naming them here.

## Backend boundaries

Modules generally separate:

- `schemas.py` - transport DTOs;
- `domain.py` - entities, enums, and business rules;
- repository ports and persistence adapters;
- `service.py` - application use cases;
- `router.py` - FastAPI translation.

`ApplicationContainer` is the composition root. Routers resolve services from
it instead of constructing dependency graphs. Application services depend on a
`TaskQueue` port; the Celery adapter is selected at composition time.

Celery task functions are thin transport adapters. Pipeline lifecycle and step
binding belong to `PipelineRunExecutor`; individual step families use focused
handlers behind `PipelineStepHandlerRegistry`.

Application/domain code should raise typed errors from `app.core.errors`.
FastAPI maps them in `app.api.error_handlers`. This boundary is already enforced
for migrated authentication and user-administration services and should replace
legacy direct `HTTPException` usage incrementally.

Repository ports do not import SQLAlchemy. Large lists are filtered and
paginated in PostgreSQL, not after loading all visible objects into Python. The
Business Case repository and pipeline step-handler modules intentionally remain
small compatibility facades while implementations live in focused modules.

Executable checks in `backend/tests/test_architecture.py` protect these
boundaries.

## Clients and public contracts

The REST API is the shared product contract. React and `ml_app_client` are
peer clients and must preserve the same authorization, validation, pagination,
idempotency, warnings, and errors.

Potentially large catalogs provide bounded `/page` endpoints with an
`items`, `total`, `limit`, `offset`, and `has_next` response. Dataset, model, and
scoring-report discovery can return compact summary projections; full detail is
loaded only after a user opens a resource. Legacy list endpoints remain for
compatibility, not as the default scalable workflow.

The React client separates transport, pagination, domain contracts, and serving
operations. `api/client.ts` is a compatibility facade. Feature code is grouped
by domain, and heavy workspaces are lazy-loaded from the authenticated
`App.tsx` shell. The production build rejects import cycles before compiling
TypeScript and producing the Vite bundle.

`MLAppClient` is the stable Python facade. It composes authentication, datasets,
Business Cases, pipelines, reports, model registry, deployments, inference, and
monitoring modules. Name resolution uses bounded API search; raw IDs remain
available for deterministic automation.

## Identity and authorization

The installation is single-company. New users receive the `user` platform role.
The protected `root` administrator is bootstrapped idempotently; startup does
not restore its initial password after a change.

Business Case access is the union of ownership, direct user grants, active group
grants, and the administrator bypass. Roles are `report_viewer`, `reader`,
`contributor`, `manager`, and `owner`. A `report_viewer` cannot access row data,
datasets, pipeline definitions, models, or source drill-down.

Loose datasets and Data Views may use direct `reader`, `editor`, or `owner`
grants. ML, scoring, serving, and monitoring require a Business Case. Access is
checked for lists, details, files, lineage, jobs, and results; workers recheck
the submitting identity before expensive execution.

## Data and full-scope analytics

A dataset is a versioned `DataAsset` backed by a local CSV/Parquet file or a
saved Data View. Data Views store declarative Browser or read-only SQL
definitions. DuckDB resolves and materializes them to definition-hashed Parquet
while the definition and source remain unchanged.

The browser preview is deliberately bounded. Saving Browser state compiles its
projection, filters, grouping, aggregation, and sorting into a server-side query
over the complete relation. Custom SQL, profiling, visualization, and drill
queries also execute server-side; only their presentation payload is bounded.

CSV receives a reusable Parquet sidecar on its first columnar analysis. Parquet
is scanned natively. Connection settings cap threads and memory and permit
dataset-local spill. Process-local conversion locks prevent duplicate work
inside one process; cross-process coordination remains a known scaling gap.

Descriptive profiling and time-series analysis are explicit asynchronous jobs.
Headline statistics and reported evaluation metrics cover the full selected
scope. Only clearly labeled rendering or explainability payloads may use bounded
samples or bins.

## Pipelines, ML, and artifacts

A pipeline belongs to one Business Case. Editable drafts produce immutable
published versions; each run and step run records status, inputs, outputs,
warnings, row counts, and lineage. Steps exchange versioned artifacts rather
than shared in-memory state.

Data Engineering uses a nested DuckDB DAG. Feature Engineering fits state on
training data and applies the same immutable state to validation, test, and
scoring inputs. Training and AutoML create a consistent bundle containing the
model, fitted transform, feature manifest, evaluation report, and provenance.

Test Scoring evaluates labeled data and may create a Scoring Report. Batch
Scoring creates an immutable prediction dataset without inventing performance
metrics when actuals are absent. Monitoring later joins actuals into a new
immutable result; it never mutates prediction history.

Artifacts, published pipeline versions, models, prediction datasets, reports,
and monitoring results are immutable. Lineage identifies source artifacts,
pipeline/version/run, step and port, creator, time, schema, and row count.

## Online serving and monitoring

A service has a stable identity and immutable revisions. Assignments use
deployment roles (`champion`, `challenger`, `shadow`, `fallback`) independently
from model lifecycle stage. Revision changes and rollback are atomic and
auditable.

The API applies the pinned inference bundle, calls the private runtime, and
persists request/item history. Fallback is attempted once for a technical
champion failure, never for invalid input. Shadow output is retained without
changing the response; challengers use protected scoring or replay.

Manual online monitoring freezes a half-open UTC `scored_at` window and a log
cutoff, streams the complete selected history into an immutable Parquet
snapshot, optionally joins actuals, and returns bounded time-series and chart
diagnostics. Batch and online monitoring share concepts but retain separate
public contracts.

## Scaling decisions and current gaps

The architecture favors set-oriented PostgreSQL queries, bounded catalog
contracts, DuckDB/Parquet execution, asynchronous jobs, and compact client
payloads. Spark or another distributed engine is not justified without measured
single-node throughput, memory, resilience, or runtime failures.

Before horizontal or production scaling, the main gaps are:

- persisted resource telemetry, cancellation, and quotas for analytical jobs;
- cross-process materialization coordination;
- managed online database migrations;
- object-storage and remote-source adapters;
- model-runtime isolation, capacity testing, and autoscaling;
- broader automated frontend behavior tests.
