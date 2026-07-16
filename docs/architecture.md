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
- Local repository (`data/repository`): currently stores uploaded datasets,
  generated Parquet, fitted transforms, reports, and trained model files.
- MinIO/S3: started in local Compose as future object-storage infrastructure;
  it is not yet the active artifact store.
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
- `FullDatasetProfiler` and `FullDatasetSqlQuery` execute bounded previews and
  read-only SQL directly over columnar relations. Registered external sources
  remain metadata-only until a pushdown-capable adapter is available.
- `ColumnarDatasetStore` owns reusable physical Parquet relations, recursive
  Data View resolution, browser-definition pushdown, SQL-view materialization,
  cache invalidation, and concurrency-safe first-run conversion.
- `FullDatasetVisualization` executes bounded visualization queries over full
  relations and returns compact chart contracts rather than raw tables.
- `DatasetSourceRegistry` selects source-specific inspection. UTF-8 CSV and flat
  tabular Parquet files are supported today; databases and APIs require future
  adapters and are never implicitly copied into application memory.
- `DatasetRepository` persists dataset metadata in PostgreSQL.

Uploaded CSV and Parquet files are stored under the local development repository
directory mounted at `data/repository`. Source inspectors validate that local
file reads stay inside that repository root. Parquet is scanned natively;
CSV receives a reusable Parquet sidecar when full columnar analytics first need it.

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
charts use exact full-data aggregates; distributions use bounded KDE source
bins; box plots use full-data quartiles and Tukey whiskers; scatter plots use
full-data two-dimensional bins so browser cost does not scale with row
count. Group-value selectors also query the complete relation. A window over the
grouped result records the complete valid-row and group counts before the output
cap is applied, so bounded transport never makes partial results look complete.
Chart navigation slices the X domain rather than the flat point array, preserving
all returned series for each visible coordinate.

Uploaded files and materialized Data Views carry an immutable row count, so
chart responses reuse that metadata instead of issuing a redundant full
`count(*)` scan for every card. DuckDB connections have a configurable memory
limit and dataset-local spill directory, while each API process bounds parallel
chart renders. KDE and box-plot comparisons reject excessive group cardinality
before running their expensive statistical aggregates.
Category bars consume the same grouped aggregate contract as trend lines. Their
side-by-side and stacked layouts are presentation concerns in React; stacked
mode creates one stack per aggregation and maintains separate positive and
negative baselines without rerunning or approximating the analytical query.
Axis domains and ticks are derived in React from the bounded result contract.
Numeric scales use nice-number steps with step-aware precision; categorical
scales first run label-width collision detection and use all labels that fit,
falling back to the smallest collision-free regular integer stride. Zero is
mandatory for magnitude-encoding bars and histograms but optional for positional
line and scatter encodings.
Visualization measures remain numeric, including when `count` is selected;
DuckDB then counts their non-null values in each analytical partition.
Categorical dimensions are represented through the grouped series contract
rather than overloaded as measures. These type rules are validated server-side.
Numeric line/bar/scatter specifications may include an X epsilon, and scatter
may independently include a Y epsilon. DuckDB converts each configured axis into
deterministic, non-overlapping `2 × epsilon` buckets and aggregates every row in
each bucket. Only the bucket centers, ranges, counts, and requested metrics are
returned to React.

Chart-mark double-click Drill uses mark metadata to build parameterized source
predicates. The API compiles them through the columnar Browser query builder and
uses one windowed DuckDB query to count all matches while returning only a
bounded record window. Histogram and scatter bin
contracts carry explicit upper-bound inclusion flags, so navigation reproduces
the precise analytical partition for physical datasets and recursively resolved
Data Views without moving the full relation into the API process or React.
Frontend translation from chart marks to API filters and then to visible Browser
filter controls is centralized in `frontend/src/analysis/drillContext.ts`; chart
components and the general application shell do not duplicate that contract.

Scatter bounds and group cardinality are calculated in one pass. The binned
query computes full valid-row and bin counts with window functions, applies its
point limit in SQL, and never materializes overflow bins as Python dictionaries.
When an explicit epsilon produces more cells than the response contract, cells
are ranked by density within each group before the global limit is applied. This
keeps the bounded view representative across series instead of returning only a
low-coordinate prefix. Non-finite coordinates are excluded, and epsilon widths
that cannot produce safe 64-bit bucket indices are rejected explicitly.
Optional scatter trends are calculated from the full filtered relation and
partitioned by the selected series. Regression fits transfer only sufficient
statistics to Python; splines transfer at most 24 aggregate nodes per group.
Every returned curve is bounded to 80 points and carries its fitted-row count.
Regression curve metadata contains original-axis coefficients and R² alongside
the bounded render points, so React presents fit diagnostics without repeating
statistical calculations in the browser.
Straight-line and exponential fits use DuckDB's native `regr_*` aggregates in a
single grouped pass. Polynomial and spline fits use compact per-group bounds
joined back to the projected X/Y relation, avoiding full-row partition windows.
`FullDatasetVisualization` owns chart orchestration, validation, bounded binning,
and drill contracts. `ScatterTrendFitter` in
`backend/app/modules/datasets/visualization_trends.py` owns regression SQL,
polynomial sufficient-statistic solving, spline interpolation, and the typed
bounded trend contract. This keeps numerical fitting independent from endpoint
and chart-kind orchestration.

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

Pipeline Training and AutoML runs materialize immutable model, metrics, fitted
feature-transform, Feature Manifest, and training-report artifacts. A shared
report envelope distinguishes `training_evaluation_report` from the reserved
`monitoring_performance_report`; the report types have separate builders and UI
templates rather than one overloaded schema. Training metrics refer to the full
evaluation scope, while SHAP/permutation explainability carries its own bounded
sample scope. AutoML creates explainability only for the final selected winner.

Batch/Test Scoring and Monitoring retain separate contracts. A prediction
dataset is row-level and lineage-backed; a report contains bounded aggregates,
diagnostics and provenance rather than copied prediction rows.

The first version uses a reusable model runtime image. The registry stores model
artifact metadata, and a deployment spec points to the artifact and runtime image.
Online scoring calls `/score`; batch scoring is queued through the worker.

For production, the same contract can be backed by Docker Engine, Kubernetes,
ECS, or another scheduler without changing the user-facing API.
