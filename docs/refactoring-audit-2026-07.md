# Repository refactoring audit — 2026-07

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

## Current hotspots

### P1 — split application containers incrementally

- `frontend/src/App.tsx`: approximately 8,700 lines.
- `frontend/src/styles.css`: approximately 7,500 lines.
- Pipeline editor/controller files are each above 1,000 lines.

Extract Business Cases and Pipelines into domain page containers first. Keep
API calls and state transitions unchanged during extraction. A wholesale UI
rewrite would have high regression risk and no data-plane benefit.

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

### P2 — decompose worker orchestration

`execute_pipeline_run` owns cancellation checks, step lifecycle, materialization,
relation binding, lineage, counters, report registration, and failure handling.
Extract a run executor and a step-result binder behind testable contracts before
adding approval gates or resumable runs.

## Deferred infrastructure decisions

- Cross-process materialization locking needs a known deployment topology
  before selecting PostgreSQL advisory locks, Redis leases, or object-store
  conditional writes.
- Spark remains unjustified until measured single-node throughput, memory,
  resilience, or execution time fails a concrete requirement.
