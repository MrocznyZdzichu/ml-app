# ML App

ML App is a containerized analytics workbench for CSV ingestion, metadata
management, exploratory analysis, reusable SQL/browser views, full-dataset
profiling, and visualization. It also contains prototype interfaces for future
model-training, serving, sharing, and export workflows.

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
- compose reusable interactive dashboards over full datasets and Data Views,
- exercise placeholder model registry, deployment, sharing, and export contracts.

The analytics paths described as full-dataset below execute against all rows.
The explicitly identified preview and prototype paths have important limitations;
see [Current Implementation Boundaries](#current-implementation-boundaries).

## Repository Layout

- `backend` - FastAPI API, domain modules, services, repositories, tests.
- `frontend` - React/TypeScript UI.
- `services/model-runtime` - template runtime for future model serving.
- `infra` - local infrastructure bootstrap assets.
- `examples/data` - sample CSV datasets for manual testing.
- `docs` - architecture, development, and feature reference notes.

## Quick Start

Prerequisites are Docker with the Compose v2 plugin and available default ports
`5173`, `8000`, `5432`, `6379`, `9000`, and `9001`.

Start the local stack:

```powershell
docker compose up --build
```

Then open:

- Frontend: `http://localhost:5173`
- API docs: `http://localhost:8000/docs`
- MinIO console: `http://localhost:9001`

The checked-in `.env.example` supplies local-development container settings.
Create a root `.env` only to override variables interpolated by
`docker-compose.yml`, such as ports, database connection values, worker
concurrency, or the frontend API URL. The shipped credentials and secret are for
local development only.

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

- UTF-8 CSV upload with delimiter/header detection, a streaming row/schema scan,
  file metadata, tags, and status.
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

The interactive table operates on a bounded preview (up to 50,000 returned rows),
and its browser-side filtering, grouping, aggregation, and sorting therefore do
not represent rows outside that preview. Saving its state as a Data View
recompiles those operations into DuckDB and applies them to the complete source
relation. Custom SQL results are also bounded, but the current Custom SQL
execution path runs in DuckDB over the complete Parquet-backed relation. The API
returns at most the requested preview limit together with the exact total result
row count; the full result is never transferred to the browser.

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

- line, bar, scatter/density-bin, KDE distribution, grouped box plot, and KPI views,
- KPI segment filters and configurable equality/range targets with pass/fail status,
- drag-and-drop positioning, fine-grained resizing, snapping guides, collision
  detection, Tidy layout, and Clear canvas,
- numeric-only scatter axes, per-chart X-epsilon bucketing for line/bar/scatter,
  independent scatter Y epsilon, contextual epsilon help, grouping,
  full-dataset aggregations, multiple metrics per group, and explicit group
  selection,
- optional straight-line, spline, degree 2–5 polynomial, and exponential scatter
  fits calculated per group, with equations, fitted-row counts, coefficients,
  and R-squared diagnostics,
- grouped Category bars with side-by-side or per-metric stacked presentation,
- adaptive axes, tooltips, zoom, pan, and scrollable mark-aware legends,
- double-click Drill on chart marks that opens Data Browsing with the exact
  source range and series filters applied over the full dataset or Data View,
- stable high-contrast series colors for bar/scatter views, plus group colors
  and metric-specific line styles for trend lines,
- session-scoped layouts restored independently for each dataset.

Chart queries run in DuckDB over the complete Parquet-backed relation. React
receives only bounded aggregates. Scatter views use full-dataset spatial binning
rather than silently substituting a row sample. The UI reports the number of
rows scanned and labels the execution mode as full-dataset server analytics.
Drill queries also execute in DuckDB before a bounded set of matching records is
returned to the browser; the total match count remains visible.

### Data Views

Data Views are saved, reusable transformations over source datasets. They can be
created from a clicked Data Browser state or Custom SQL. SQL and Browser
definitions are compiled into DuckDB queries and materialized as reusable,
definition-versioned Parquet artifacts. Nested views are supported with bounded
recursion, and caches are invalidated when the definition or source changes.

Views are shown in Overview, Data, and Analysis, and they can be used in Data
Roles, Data Browsing, Visualization and Trends, and Descriptive Analysis.
Visualization queries operate on the full transformed relation. Descriptive
Analysis for a Data View currently uses its explicitly bounded preview range and
must not be interpreted as a full-view profile.

When possible, data roles are inherited from the source dataset for columns that
survive in the view.

Deleted datasets and views remain visible in the Data workspace deletion history
but are excluded from Overview metrics, Recent assets, and Analysis selectors.

### Prototype ML, Serving, Sharing, and Export

The Models, Serving, and Share tabs expose the intended API and UI contracts,
but they are scaffolding rather than production workflows:

- training requests create in-memory job and model metadata; no estimator is
  fitted and no artifact is written,
- deployment requests create in-memory metadata but do not start a runtime,
- online scoring returns placeholder `0.0` predictions,
- sharing grants, batch-score jobs, and export jobs are metadata-only and are
  lost when the API process restarts.

The optional `model-runtime` Compose service can load a joblib artifact and
expose `/health` and `/score`, but it is not wired automatically to deployment
records created in the main API.

## Current Implementation Boundaries

- Local ingestion supports UTF-8 CSV files only. Parquet, XLSX, remote databases,
  and object-storage ingestion are not implemented.
- Users and dataset metadata are durable in PostgreSQL. Uploaded files and
  generated Parquet sidecars are stored in `data/repository`; MinIO is started
  for future object-storage work but is not the active dataset store.
- Full-dataset descriptive profiling is implemented for uploaded CSV datasets
  and materialized SQL/Browser Data Views.
- Visualization, chart drill-down, and Data View materialization use DuckDB over
  the complete physical or transformed relation and return bounded results.
- Scatter trend output is capped at 80 render points per curve and 100 selected
  groups. Spline fits smooth at most 24 full-data aggregate nodes per group and
  are explicitly marked as approximate; other supported fits use full-data
  regression aggregates or sufficient statistics.
- Interactive Data Browsing is a bounded client-side exploration path. Custom
  SQL is a full-dataset DuckDB path with a bounded result contract.
- Analytics scalability is currently single-node. There is no distributed query
  engine, persisted query cancellation, quota enforcement, or production job
  scheduler yet.

## Example Data

Use these files for manual testing:

- `examples/data/iris.csv`
- `examples/data/general-example.csv`
- `examples/data/regression-example.csv`
- `examples/data/dynamic-reactor-timeseries.csv`
- `examples/data/equipment-operating-regimes.csv`

`general-example.csv` contains 10,000 synthetic customer-churn-like rows with
mixed numeric and categorical columns, useful for testing filtering, grouping,
aggregation, sorting, Custom SQL, and Data Views.

`regression-example.csv` contains 10,000 synthetic real-estate transaction rows
for a regression task where the target is `sale_price_pln`.

`dynamic-reactor-timeseries.csv` is a dynamic, delayed thermal-process forecasting
case. `equipment-operating-regimes.csv` is an unlabeled machine-telemetry clustering
case. Their business context, modeling cautions, and deterministic generator are
documented in `docs/synthetic-ml-scenarios.md`.

## Verification

Run backend tests:

```powershell
docker exec --user app ml-app-api-1 pytest tests
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

Its default host endpoint is `http://localhost:8010`; this standalone runtime is
separate from the placeholder deployment records in the application UI.

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
