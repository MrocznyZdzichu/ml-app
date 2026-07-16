# Repository refactoring audit

> Historical snapshot. Some follow-up items have since been implemented or
> superseded. Use current architecture and feature documents as the source of
> truth.

## Scope

This audit focuses on execution paths that must remain viable for tens of
millions of rows, boundaries needed by the future Training step, and modules
whose current size increases regression risk.

## Changes implemented

### Shared DuckDB runtime

DE, FE, and dataset analytics now use one connection factory with the same
thread, memory, temporary-directory, and insertion-order settings.

Atomic Parquet writes return the row count produced by DuckDB `COPY` and schema
metadata collected from the lazy relation. DE and FE no longer perform a second
full scan of every generated Parquet solely to build the output manifest.
Preview remains explicitly bounded to 50 rows.

### Fewer full-data FE scans

- numeric scaling computes statistics for all selected columns in one aggregate
  query instead of one full scan per column;
- mean and median imputation use one aggregate query per block;
- categorical encoding computes the training row count once per block;
- PCA computes row count, null count, means, and covariance in one aggregate
  query rather than four independent scans.

The NumPy portion of PCA remains bounded to the feature-by-feature covariance
matrix; full rows stay in DuckDB.

### Runtime dependency boundaries

Shared pipeline runtime types and helpers live outside the DE executor. FE and
the worker no longer import `SourceRelation` and SQL/runtime helpers from the DE
engine. This is the boundary future Training and Scoring executors should use.

### Bounded conversion-lock registry

CSV/DataView Parquet conversion locks are reference-counted and removed after
the last active or waiting user. A long-lived process no longer retains one
lock object for every dataset it has ever converted.

### Frontend workflow boundary

The high-level workflow diagram is an isolated component. New lifecycle nodes
and multi-output rendering can evolve without further growing the step
configuration controller.

### Removed in-memory dataset fallback

Supported CSV, Parquet, and Data View previews use the columnar DuckDB path.
The unused Python/SQLite fallback has been removed, including its full-file
decode, per-cell conversion, row duplication, and unbounded SQLite copy.
Registered source types without a columnar adapter now fail explicitly with
HTTP 415 instead of creating an accidental in-process materialization path.

## Ranked follow-up work

### P1 — split the frontend application shell

`frontend/src/App.tsx` is approximately 7,800 lines and `styles.css` is
approximately 6,900 lines. Extract route/page containers and colocate styles by
domain (`business-cases`, `datasets`, `pipelines`, `analysis`). Do this in
incremental, behavior-preserving changes; a wholesale rewrite would carry
unnecessary UI regression risk.

### P1 — generate frontend API contracts

Workflow and FE contracts are represented independently by Pydantic and
TypeScript. Generate TypeScript DTOs from OpenAPI/JSON Schema and keep only
UI-specific editor state handwritten. This prevents silent drift in roles,
ports, enum values, and required fields.

### P1 — cross-process materialization locks

Current conversion locking protects threads within one process. Horizontal
workers require a database advisory lock, Redis lease, or object-store
conditional write. Select the mechanism together with the deployment topology;
do not introduce distributed locking before that topology is known.

### P2 — frontend test and lint baseline

The frontend currently has a TypeScript production build but no unit-test or
lint command. Add focused tests for contract normalization and editor reducers,
then ESLint rules for hooks, imports, and unsafe casts.

### P2 — observability and resource accounting

Persist DuckDB wall time, bytes read/written, spill bytes, peak memory where
available, and per-step timing. These measurements should guide any future
decision to add Spark or another distributed engine.
