# Development Notes

## Run Locally

```powershell
docker compose up --build
```

Copy `.env.example` to `.env` only when local overrides are needed.

For the normal development loop after code edits:

```powershell
.\rebuild-run.bat
```

Use `.\rebuild-run.bat build` after dependency or Dockerfile changes.

## Backend Only

`backend/requirements.txt` documents supported direct dependency ranges.
Application images install the fully resolved `backend/requirements.lock`, so
local, CI, and deployment builds use the same tested dependency graph. After a
dependency change, regenerate the lock in Python 3.12 on Linux, rebuild the
images, and run the complete backend test suite.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Frontend Only

```powershell
cd frontend
npm install
npm run dev
```

## Tests and Checks

Backend tests:

```powershell
docker exec --user app ml-app-api-1 pytest tests
```

Run the focused full-dataset profiling tests:

```powershell
docker exec --user app ml-app-api-1 pytest tests/test_full_profile.py tests/test_profile_jobs.py tests/test_visualizations.py
```

Frontend production build:

```powershell
docker exec ml-app-frontend-1 npm run build
```

Health checks:

```powershell
Invoke-WebRequest -UseBasicParsing http://localhost:8000/health
Invoke-WebRequest -UseBasicParsing http://localhost:5173
```

Validate the resolved Compose configuration after changing environment variables:

```powershell
docker compose config
```

## Descriptive Profiling Runtime

Uploaded CSV and Parquet datasets are profiled asynchronously by the Celery
worker. CSV creates a reusable Zstandard-compressed Parquet sidecar on its first
full columnar analysis; uploaded Parquet is scanned natively. DuckDB scans all
rows and may spill intermediate work to the dataset-local temporary directory.

The main local tuning variables are documented in `.env.example`:

- `DUCKDB_THREADS` controls threads per DuckDB analytical connection. The legacy
  `DESCRIPTIVE_PROFILE_DUCKDB_THREADS` name remains accepted.
- `DUCKDB_MEMORY_LIMIT` caps memory per DuckDB connection; larger intermediates
  spill to the dataset-local temporary directory.
- `VISUALIZATION_MAX_CONCURRENCY` limits simultaneous heavy chart renders in
  each API process.
- `PROFILE_WORKER_CONCURRENCY` controls concurrent Celery jobs.
- `DESCRIPTIVE_PROFILE_RESULT_EXPIRES_SECONDS` controls Redis result lifetime.

Keep the product of DuckDB threads, worker concurrency, and visualization
concurrency appropriate for the host CPU and memory. The defaults favor
predictable local development over maximum throughput.

Run the synthetic full-profile benchmark inside the API container:

```powershell
docker exec ml-app-api-1 python tests/benchmark_full_profile.py --rows 1000000
```

See `descriptive-profiling-performance.md` for measured results and scaling
characteristics.

## Data View And Visualization Runtime

Saved SQL and Browser Data Views are materialized by DuckDB as reusable Parquet
relations. The cache filename includes a hash of the definition and is reused
only while it is newer than the source relation. Browser filters, search,
grouping, aggregation filters, projection, and sorting are pushed down instead
of being evaluated over Python records.

Visualization requests scan complete physical or view relations and return
bounded aggregate contracts. Continuous X bucketing is performed by DuckDB from
the per-chart `x_epsilon` request field; do not reproduce this aggregation in
React. Grouped queries calculate full valid-row and group counts before applying
the response limit. Keep that distinction intact: `valid_count` describes the
whole selected analytical range, while `truncated` describes only the bounded
display payload. The frontend aborts superseded requests and navigates by unique
X coordinates so multi-series lines are not split during zoom and pan. Scatter
also supports independent `y_epsilon` bucketing. Validate explicit epsilon
widths against the finite data range before creating signed 64-bit bin indices.
If the bounded output must be truncated, rank dense cells fairly across groups
instead of taking a coordinate-ordered prefix. Trend regression remains
server-side and should use native grouped aggregates or bounded sufficient
statistics, never browser points or materialized raw rows. Keep the request
lifecycle in `frontend/src/analysis/useVisualizationResult.ts`; chart
components should consume its state rather than duplicate debounce, cancellation,
and error handling. Chart-mark double-click Drill requests must remain
server-side: compile mark ranges and group values through
`ColumnarDatasetStore.compile_browser_query`, count the complete match set in the same
windowed query, and bound only the returned record window. Preserve explicit
upper-bound inclusion for final histogram and scatter bins, and test the same
path against Data Views.

Trend-fitting SQL and numerical helpers belong in
`backend/app/modules/datasets/visualization_trends.py`; keep chart orchestration,
binning, and drill metadata in `visualizations.py`. Trend response models are
typed in `schemas.py`, so new fit kinds must update backend literals, response
models, frontend API types, rendering, and this documentation together.
Keep fit-equation presentation in `TrendFitDetails.tsx` and reusable chart
number formatting in `visualizationFormatters.ts`; do not move model-specific
display branches back into the dashboard orchestration component.

When changing this path, run:

```powershell
docker exec --user app ml-app-api-1 pytest tests/test_visualizations.py tests/test_datasets_upload.py tests/test_full_profile.py
```

## Local Runtime Data

Uploaded local files are stored under `data/repository` when using Docker
Compose. This directory is intentionally ignored by Git. Keep reusable demo data
under `examples/data` instead.

Python bytecode, test caches, Vite output, node modules, local env files, model
artifacts, and runtime data should not be committed.

Integration tests create uniquely named accounts in the local PostgreSQL
database. The autouse fixture in `backend/tests/conftest.py` tags generated
accounts with a unique per-test token and removes only those accounts, their
dataset records, and their repository directories afterward. This remains safe
when tests run concurrently. Keep test account names within the explicit pattern
in that fixture; never broaden cleanup to all `example.com` accounts or all users
created during a time window.

The root-level `sandbox.ipynb` notebook is also ignored. It is intended for quick
local experiments and scratch calculations, not shared documentation.

## Git Hygiene

The project includes `.gitignore` and `.gitattributes` for a Windows + Docker
development workflow. Before publishing, check what will be committed:

```powershell
git status --short
git add --dry-run .
```

## Known development gaps

Keep product-roadmap decisions in `AGENTS.md`; this file lists only engineering
gaps that affect local development:

- Alembic-style managed migrations are not yet the primary migration path.
- XLSX, database, object-storage, and remote query-engine adapters are missing.
- Long-running analytics need stronger cancellation, quotas, and persisted
  resource accounting.
- Online serving uses one private shared Compose runtime; automatic per-service
  Docker/Kubernetes provisioning, isolation, and autoscaling are not implemented.
- The frontend has a production TypeScript build but no broad component-test and
  lint baseline yet.
