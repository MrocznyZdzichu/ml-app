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
  definitions, grouping, aggregation, sorting, and filtering for the bounded
  interactive browser path. Moving this live preview path to pushdown is a
  remaining scalability task.
- `ColumnarDatasetStore` owns reusable physical Parquet relations, recursive
  Data View resolution, browser-definition pushdown, SQL-view materialization,
  cache invalidation, and concurrency-safe first-run conversion.
- `FullDatasetVisualization` executes bounded visualization queries over full
  relations and returns compact chart contracts rather than raw tables.
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

## Descriptive Analysis

Descriptive Analysis for uploaded CSV assets runs as a Celery task over a DuckDB
relation. The first explicit run converts the source CSV to a reusable,
Zstandard-compressed Parquet sidecar. DuckDB performs full-column aggregates,
relationships, contingency tables, graphic bins, and segment grouping over all
rows and can spill to a dataset-local temporary directory. The API and Redis
carry only compact profile results; raw profile rows are not sent to React.

Profiling is explicitly started by the analyst. Dataset selection reads a small
CSV schema sample plus stored upload metadata and does not create Parquet. After
`Run profiling`, the API queues work and the unchanged frontend progress state
polls for completion. Worker concurrency is deliberately limited and prefetch is
one so multiple large scans do not multiply memory pressure unpredictably.
Queue ownership and result lifecycle are isolated in `DescriptiveProfileJobs`;
`DatasetService` only validates dataset access and delegates job orchestration.

Successful computed summaries and UI snapshots are cached in an App-owned,
session-scoped in-memory map keyed by dataset ID. The cache
survives Analysis tab and workspace navigation, is invalidated when dataset
metadata has a newer `updated_at`, and is cleared during logout. No profiling
records are persisted to browser storage.

The UI supports univariate profiles, target/comparison relations, optional
histograms, KDE-like density plots, scatterplots, and a multivariate subgroup
scan over eligible low-cardinality feature pairs. Segment results are ranked by
coverage-adjusted impact (WRAcc for categorical targets and support-weighted
Cohen's d for continuous targets) and cached with the rest of the computed
profile. Only scatterplot observations are reservoir-sampled; metrics and
aggregate graphics use all rows. Saved Data Views use the same columnar execution
path after their transformations have been pushed down and cached as Parquet.

## Visualization and Trends

The dashboard layout is a 48-column session-scoped grid stored in browser
session storage per dataset. React owns layout and presentation state, while
analytical computation remains server-side.

Each chart sends a declarative specification to the dataset visualization API.
DuckDB scans the complete physical dataset or materialized Data View and returns
only bounded points, series metadata, counts, or KPI values. Grouped line/bar
charts use exact full-data aggregates; histograms use full-data bins; scatter
plots use full-data two-dimensional bins so browser cost does not scale with row
count. Group-value selectors also query the complete relation.
Numeric line/bar specifications may include an X epsilon. DuckDB converts the
continuous X expression into deterministic, non-overlapping `2 × epsilon`
buckets and aggregates Y over every row in each bucket. Only the bucket centers,
ranges, counts, and requested metrics are returned to React.

## Data Views

Data Views are stored as normal data assets with `source_type = "view"` and
`format = "view"`. Their executable definition is stored in
`metadata.data_view`.

Two definition shapes are supported:

- `kind = "browser"` for clicked Data Browser state: visible columns, search,
  filters, sort rules, grouping, aggregation, and aggregation filters.
- `kind = "sql"` for read-only Custom SQL.

Views are recursively resolved to their physical source. Browser definitions
are compiled into parameterized DuckDB SQL; saved SQL definitions execute
against a temporary relation named after the source dataset. Results are
materialized to definition-hashed Parquet files and reused while both definition
and source remain unchanged. This makes views first-class sources for preview,
visualization, and descriptive profiling without loading full tables into Python
or React.

## Model Operationalization

The first version uses a reusable model runtime image. The registry stores model
artifact metadata, and a deployment spec points to the artifact and runtime image.
Online scoring calls `/score`; batch scoring is queued through the worker.

For production, the same contract can be backed by Docker Engine, Kubernetes,
ECS, or another scheduler without changing the user-facing API.
