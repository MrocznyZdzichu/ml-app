# Repository refactoring audit — 2026-07

> Dated engineering snapshot. Priorities describe the repository at audit time
> and may no longer match the current implementation.

> **Post-audit status:** the Data/Analysis workspace, Business Case repository,
> pipeline step handlers, frontend API contracts, Python client, and serving
> client have since been split into focused modules. Typed application errors
> are now wired globally and used by the migrated auth/user services. Treat the
> hotspot list below as decision history; use
> [`CODEMAP.md`](../CODEMAP.md), [Architecture](architecture.md), and executable
> architecture checks for the current structure.

## Executive summary

The backend data plane is directionally sound for large datasets: CSV/Parquet
relations stay in DuckDB, pipeline scoring is batched, browser responses are
bounded, and persistent outputs are materialized as Parquet. No justification
was found for introducing Spark at the current stage.

The highest current engineering risk is contract and UI-controller drift, not
the columnar execution engine. Recent defects around `monitoring_input`,
`pinned`, and run-time dataset selection all came from repeated handwritten
lists and duplicated resolvers.

## Refactors completed in this audit

- Added one frontend contract for Business Case data roles and dataset-version
  policies.
- Added one frontend resolver for workflow run inputs. Business Case and global
  pipeline run dialogs no longer reconstruct nested input contracts separately.
- Made `pinned` a first-class policy in both DE and FE contracts and render it
  as an exact immutable version rather than a run-time selection.
- Added one backend `DatasetVersionPolicy` enum shared by DE and FE Pydantic
  definitions.
- Reused common role and version-policy options in pipeline, feature engineering,
  and Business Case editors.

These changes are behavior-preserving except for correcting inconsistent
`pinned` handling.

## Refactoring implementation follow-up

The high-priority structural work from this snapshot was implemented without
changing the public REST contracts or the visible UI:

- `ApplicationContainer` is now the backend composition root. Routers resolve
  use-case services from it instead of constructing service graphs locally.
- Queue access is expressed through the `TaskQueue` port. Celery is an outer
  adapter selected by the composition root, so application modules no longer
  import worker implementations.
- Authentication identity moved to a transport-independent `Principal` module,
  removing the security/API-credential import cycle.
- Pipeline execution moved from the Celery task module to
  `PipelineRunExecutor`. The task is now a thin adapter, while the executor can
  be tested synchronously with injected repositories.
- The former frontend application monolith was split into domain panels for
  Business Cases, Pipelines, Data/Analysis, Jobs, Models and Serving. `App.tsx`
  is now the workspace shell and navigation coordinator.
- Heavy domain panels are loaded on demand. In the production build measured
  during the refactor, the initial application chunk decreased from about
  324 kB (80 kB gzip) to about 100 kB (24 kB gzip).
- Browser API transport, pagination and serving operations are separate modules.
  The supported Python client now separates response models, errors, resource
  resolution and serving workflows while preserving its import surface.
- Executable architecture tests prevent application-to-worker imports, service
  construction in routers, HTTP coupling in `Principal`, and renewed growth of
  the pipeline task wrapper.

## Hotspots identified at audit time

### P1 — continue splitting the Data/Analysis workspace

`App.tsx` is no longer the controller hotspot. The largest remaining UI module
is `frontend/src/data/DataWorkspacePanels.tsx`, which still combines catalog,
roles, descriptive analysis and the record browser. Split these along existing
API boundaries before adding new analysis modes. `styles.css` and the pipeline
editor/controller files also remain large and should be divided by domain
without changing class names or visual behavior.

The frontend API DTO registry is also still handwritten and broad. Generate
transport DTOs from OpenAPI before duplicating more schema definitions.

### P1 — measure and reduce repeated model-report scans

`ModelEvaluationSnapshotBuilder` runs separate full-relation queries for scope,
class summaries, confusion matrix, ranking metrics, curve bins, score bounds,
score histogram, calibration, and probability losses. All results are exact and
bounded at the response boundary, but binary classification can scan the same
Parquet columns several times.

Before changing SQL:

1. persist per-query wall time, rows scanned, bytes read/written, and spill;
2. benchmark representative 1M, 10M, and 50M row prediction datasets;
3. compare the current plan with a projected temporary evaluation relation and
   combined aggregate queries;
4. retain exact full-scope headline metrics and bounded chart contracts.

Do not replace exact reporting with sampling.

### P1 — add resource accounting to pipeline step runs

`StepRun` records row counters and warnings but not duration, bytes, spill, or
peak memory. These measurements should drive worker concurrency, DuckDB limits,
and any future distributed-engine decision.

### P2 — generate transport DTOs

Frontend API DTOs and backend Pydantic schemas are still independently
handwritten. Generate transport types from OpenAPI/JSON Schema while keeping
editor-only state handwritten. The shared role/policy module introduced here is
an immediate guard, not a replacement for generated DTOs.

### P2 — establish frontend reducer/hook tests

The frontend has a production TypeScript build but no unit-test baseline.
Prioritize:

- workflow normalization and template creation;
- run-input resolution for `latest`, `pinned`, and run-selected policies;
- category-mapping row identity and upstream dataset resolution;
- scoring-report chart contract rendering.

### Completed — decompose worker orchestration

`execute_pipeline_run` now delegates to `PipelineRunExecutor`. Further
decomposition should focus inside the executor on step-result binding and
materialization policies only when those responsibilities need independent
evolution.

### P2 — isolate HTTP errors from remaining application services

Several mature services still raise FastAPI `HTTPException` directly. New
domain/application code should use typed exceptions and translate them in the
router layer. Migrate existing modules incrementally with regression coverage;
changing every error contract at once would create unnecessary compatibility
risk.

## Deferred infrastructure decisions

- Cross-process materialization locking needs a known deployment topology
  before selecting PostgreSQL advisory locks, Redis leases, or object-store
  conditional writes.
- Spark remains unjustified until measured single-node throughput, memory,
  resilience, or execution time fails a concrete requirement.
