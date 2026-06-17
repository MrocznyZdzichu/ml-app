# Architecture

## Product Shape

The application is organized around a common analytics lifecycle:

1. Users authenticate and work inside isolated projects/workspaces.
2. Data assets are registered from files, databases, APIs, or future connectors.
3. Data profiling, descriptive statistics, and visualizations are created.
4. ML experiments train candidate models and record parameters, metrics, and artifacts.
5. Approved models are deployed as isolated scoring services.
6. Data, analyses, visualizations, models, and exports can be shared.

## Service Boundaries

- API: owns HTTP contracts, authorization checks, orchestration, and metadata.
- Worker: owns long-running jobs such as ingestion, profiling, training, export, and batch scoring.
- PostgreSQL: stores users, permissions, metadata, experiment runs, and audit events.
- MinIO/S3: stores raw datasets, generated reports, plots, trained models, and exports.
- Redis: broker/cache for background work.
- Model runtime: a small container image used to expose online scoring for a model artifact.

## Backend Modules

Each module follows the same direction:

- `schemas.py` contains API DTOs.
- `domain.py` contains domain entities and enums.
- `repository.py` contains persistence contracts and temporary in-memory adapters.
- `service.py` contains use-case oriented classes.
- `router.py` exposes FastAPI endpoints.

Dataset, auth, model, serving, sharing, analysis, and export modules follow this
layout. Dataset and auth metadata are currently backed by PostgreSQL
repositories.

## Dataset Architecture

Datasets are represented by `DataAsset` records. A data asset can point to a
physical file, a future external source, or a saved Data View.

The dataset module is split into these responsibilities:

- `DatasetService` handles use cases: upload, registration, metadata updates,
  deletion, preview, Custom SQL, and Data View creation.
- `DatasetQueryEngine` executes tabular previews, read-only SQL, browser view
  definitions, grouping, aggregation, sorting, and filtering.
- `DatasetSourceRegistry` selects a source adapter. CSV files are supported
  today; the adapter boundary is prepared for parquet, xlsx, databases, and APIs.
- `DatasetRepository` persists dataset metadata in PostgreSQL.

Uploaded CSV files are stored under the local development repository directory
mounted at `data/repository`. The CSV adapter validates that local file reads stay
inside that repository root.

## Data Roles Metadata

Analyst-defined data roles are stored in `DataAsset.metadata.data_roles`. This is
intentionally generic JSON metadata so later tools can use the same semantic
contract without schema churn for every new role.

Saved Data Views inherit source roles for columns that still exist in the view.
For example, if `plan_type` is ordinal in the source dataset and the view keeps
`plan_type`, the view receives the same role.

## Data Views

Data Views are stored as normal data assets with `source_type = "view"` and
`format = "view"`. Their executable definition is stored in
`metadata.data_view`.

Two definition shapes are supported:

- `kind = "browser"` for clicked Data Browser state: visible columns, search,
  filters, sort rules, grouping, aggregation, and aggregation filters.
- `kind = "sql"` for read-only Custom SQL.

Views are expanded at preview time. That keeps them lightweight and makes them
behave like dynamic sources for Analysis tools.

## Model Operationalization

The first version uses a reusable model runtime image. The registry stores model
artifact metadata, and a deployment spec points to the artifact and runtime image.
Online scoring calls `/score`; batch scoring is queued through the worker.

For production, the same contract can be backed by Docker Engine, Kubernetes,
ECS, or another scheduler without changing the user-facing API.
