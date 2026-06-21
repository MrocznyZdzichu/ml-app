# ML App

ML App is a containerized analytics workbench for dataset ingestion, metadata
management, exploratory analysis, custom SQL views, and future ML workflows.

> **AI-developed project:** This application has been designed and implemented
> with substantial AI assistance. Treat the codebase as an actively evolving
> prototype: review, test, and harden it before using it with sensitive data or
> production workloads.

The current product slice focuses on a practical analyst workflow:

- upload CSV datasets,
- assign durable data roles and column roles,
- browse, filter, sort, group, aggregate, and drill into data,
- profile datasets with descriptive, target-aware, and comparison summaries,
- run read-only Custom SQL,
- save reusable Data Views,
- continue from saved views into browsing, visualization, and descriptive analysis,
- compose reusable interactive dashboards over full datasets and Data Views.

## Repository Layout

- `backend` - FastAPI API, domain modules, services, repositories, tests.
- `frontend` - React/TypeScript UI.
- `services/model-runtime` - template runtime for future model serving.
- `infra` - local infrastructure bootstrap assets.
- `examples/data` - sample CSV datasets for manual testing.
- `docs` - architecture, development, and feature reference notes.

## Quick Start

Start the local stack:

```powershell
docker compose up --build
```

Then open:

- Frontend: `http://localhost:5173`
- API docs: `http://localhost:8000/docs`
- MinIO console: `http://localhost:9001`

Create `.env` from `.env.example` only when you want to override defaults.

## Refresh After Code Changes

For normal backend/frontend code changes:

```powershell
.\rebuild-run.bat
```

After dependency, Dockerfile, or image-level changes:

```powershell
.\rebuild-run.bat build
```

For a clean no-cache rebuild:

```powershell
.\rebuild-run.bat full
```

## Current Features

### Authentication

- Local user registration and login.
- Bearer token authentication in the frontend.
- User-owned datasets; other users cannot access private assets.

### Data Assets

- CSV upload with header detection, row count, file metadata, tags, and status.
- Dataset metadata persisted in PostgreSQL.
- Uploaded file content stored under local `data/repository` in development.
- Soft deletion of dataset metadata with physical local file cleanup.

### Analysis: Data Roles

The first Analysis tab lets an analyst persist semantic metadata for each
dataset:

- dataset roles such as training, validation, test, holdout, scoring,
  target-containing, reference/baseline, and monitoring,
- entity ID, timestamp, period/batch, and target columns,
- per-column roles such as identifier, timestamp, period/batch identifier,
  continuous feature, categorical feature, ordinal feature, target, sample
  weight, text feature, boolean feature, and ignored.

These settings are saved as `data_roles` in dataset metadata and can be reused
by later tools.

### Analysis: Data Browsing

Data Browsing supports:

- shared dataset selection with the Data Roles tab,
- bounded interactive preview filtering and searching with explicit returned-row
  and total-row counts,
- column selection with presets,
- multi-column sorting,
- flexible filters: equals, not equals, contains, regex, in, numeric
  comparisons, empty/not empty, starts/ends with,
- role-aware grouping and aggregation,
- aggregation filters similar to SQL `HAVING`,
- drill down from aggregated rows into matching detail records,
- top and bottom horizontal table scrolling,
- paging with direct page number input,
- Custom SQL with a helper sidebar and read-only execution,
- Save View for persisting the current analysis as a reusable Data View.

The interactive table remains a bounded exploratory preview. Saving its state as
a Data View recompiles the filters, search, grouping, aggregation, projection,
and sorting into DuckDB and applies them to the complete source relation.

### Analysis: Descriptive Analysis

Descriptive Analysis provides explicit, role-aware dataset profiling. Profiling
does not start automatically after dataset selection; analysts choose the
dataset, target, target type, and profiling range, then run profiling when ready.

The tab supports:

- smart dataset summary cards and quality notes based on Data Roles metadata,
- optional profiling scope controls for summary, univariate profiles,
  target/comparison relations, segment scans, graphic source-point limits, and
  graphic summaries,
- asynchronous full-row profiling of uploaded CSV datasets with DuckDB and
  reusable Parquet materialization instead of browser-side row processing,
- univariate profiles with collapsible UI, column selection, numeric summaries,
  categorical distributions, and optional histograms,
- comparison analysis that defaults to target vs features but can compare
  features against another selected column,
- continuous-feature vs categorical-comparison tables with rows, min, max,
  median, average, standard deviation, and optional KDE-like density plots,
- continuous-vs-continuous relation cards with Pearson, Spearman, R-squared,
  slope, intercept, covariance, and optional scatterplots,
- collapsible relation cards with Show all / Collapse all controls,
- session-scoped in-memory profile caching when switching between datasets,
- ranked multivariate segment scan across low-cardinality feature pairs, with
  support-aware impact, uncertainty, lift/WRAcc for categorical targets, and
  standardized effect size for continuous targets.

Full-dataset profiling runs in the Celery analytics worker and scans every row
for tabular statistics, relationships, and segments. Only bounded scatterplot
source points are sampled. See
[`docs/descriptive-profiling-performance.md`](docs/descriptive-profiling-performance.md)
for the architecture and benchmark results.

### Analysis: Visualization and Trends

Visualization and Trends is an interactive dashboard canvas. Analysts explicitly
choose a dataset, start with an empty canvas, and either add charts manually or
use Smart start. The workspace supports:

- line, bar, scatter/density-bin, histogram, and KPI views,
- drag-and-drop positioning, fine-grained resizing, snapping guides, collision
  detection, Tidy layout, and Clear canvas,
- configurable axes, per-chart X-epsilon bucketing for continuous variables,
  grouping, full-dataset aggregations, multiple metrics per group, and explicit
  group selection,
- adaptive axes, tooltips, zoom, pan, scrollable legends, stable high-contrast
  group colors, and metric-specific line styles,
- session-scoped layouts restored independently for each dataset.

Chart queries run in DuckDB over the complete Parquet-backed relation. React
receives only bounded aggregates. Scatter views use full-dataset spatial binning
rather than silently substituting a row sample. The UI reports the number of
rows scanned and labels the execution mode as full-dataset server analytics.

### Data Views

Data Views are saved, reusable transformations over source datasets. They can be
created from a clicked Data Browser state or Custom SQL. SQL and Browser
definitions are compiled into DuckDB queries and materialized as reusable,
definition-versioned Parquet artifacts. Nested views are supported with bounded
recursion, and caches are invalidated when the definition or source changes.

Views are shown in Overview, Data, and Analysis, and they behave like normal
datasets in Data Roles, Data Browsing, Visualization and Trends, and Descriptive
Analysis. Full-dataset downstream computations operate on the transformed view,
not on its browser preview.

When possible, data roles are inherited from the source dataset for columns that
survive in the view.

Deleted datasets and views remain visible in the Data workspace deletion history
but are excluded from Overview metrics, Recent assets, and Analysis selectors.

## Example Data

Use these files for manual testing:

- `examples/data/iris.csv`
- `examples/data/general-example.csv`
- `examples/data/regression-example.csv`

`general-example.csv` contains 10,000 synthetic customer-churn-like rows with
mixed numeric and categorical columns, useful for testing filtering, grouping,
aggregation, sorting, Custom SQL, and Data Views.

`regression-example.csv` contains 10,000 synthetic real-estate transaction rows
for a regression task where the target is `sale_price_pln`.

## Verification

Run backend tests:

```powershell
docker exec ml-app-api-1 pytest tests
```

Build the frontend:

```powershell
docker exec ml-app-frontend-1 npm run build
```

Check running services:

```powershell
Invoke-WebRequest -UseBasicParsing http://localhost:8000/health
Invoke-WebRequest -UseBasicParsing http://localhost:5173
```

## Local Services

`docker-compose.yml` starts:

- PostgreSQL for users and metadata,
- Redis for background work,
- MinIO for future object storage workflows,
- FastAPI API,
- Celery worker,
- Vite frontend.

The model runtime template can be run with the `serving` profile once a model
artifact is available:

```powershell
docker compose --profile serving up --build model-runtime
```

## Documentation

- [Architecture](docs/architecture.md)
- [Development notes](docs/development.md)
- [Analysis and Data Browser reference](docs/analysis-data-browser-reference.md)
- [Descriptive profiling performance](docs/descriptive-profiling-performance.md)

## Git Notes

The repository is prepared to keep source code, docs, infrastructure, tests, and
example datasets in Git while excluding local runtime data, caches, build
outputs, virtual environments, secrets, and model artifacts.

Before committing, review the working tree and staged file list:

```powershell
git status --short
git diff --check
git add --dry-run .
```
