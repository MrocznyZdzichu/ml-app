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
docker exec ml-app-api-1 pytest tests
```

Run the focused full-dataset profiling tests:

```powershell
docker exec ml-app-api-1 pytest tests/test_full_profile.py tests/test_profile_jobs.py tests/test_visualizations.py
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

Uploaded CSV datasets are profiled asynchronously by the Celery worker. The
first full profile creates a reusable Zstandard-compressed Parquet sidecar next
to the source file under `data/repository`; later profiles reuse it while the
source file is unchanged. DuckDB scans all rows and may spill intermediate work
to the dataset-local temporary directory.

The main local tuning variables are documented in `.env.example`:

- `DESCRIPTIVE_PROFILE_DUCKDB_THREADS` controls DuckDB threads per profiling job.
- `PROFILE_WORKER_CONCURRENCY` controls concurrent Celery jobs.
- `DESCRIPTIVE_PROFILE_RESULT_EXPIRES_SECONDS` controls Redis result lifetime.

Keep the product of DuckDB threads and worker concurrency appropriate for the
host CPU and memory. The defaults favor predictable local development over
maximum throughput.

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
X coordinates so multi-series lines are not split during zoom and pan. Keep the
request lifecycle in `frontend/src/analysis/useVisualizationResult.ts`; chart
components should consume its state rather than duplicate debounce, cancellation,
and error handling. Chart-mark double-click Drill requests must remain
server-side: compile mark ranges and group values through
`ColumnarDatasetStore.compile_browser_query`, count the complete match set in the same
windowed query, and bound only the returned record window. Preserve explicit
upper-bound inclusion for final histogram and scatter bins, and test the same
path against Data Views. When changing this path, run:

```powershell
docker exec ml-app-api-1 pytest tests/test_visualizations.py tests/test_datasets_upload.py tests/test_full_profile.py
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

## Intended Next Steps

- Add Alembic migrations and SQLAlchemy repositories.
- Add database connection testing and external source adapters.
- Add parquet and xlsx source adapters.
- Move the live Data Browser preview and Custom SQL execution to paged DuckDB
  query pushdown instead of bounded frontend/Python records.
- Add query cancellation, quotas, and persisted observability for long-running analytics.
- Add remote query-engine adapters for datasets that exceed a single-node DuckDB deployment.
- Implement model training workers and artifact registration.
- Add deployment adapter for Docker Compose or Kubernetes.
