# Development workflow

## Run the full stack

Requirements are Docker with Compose v2 and the ports listed in the root
README. Start or build everything with:

```powershell
docker compose up --build
```

Create `.env` only for local overrides; `.env.example` is loaded by the
application services.

After ordinary code changes use the repository helper:

```powershell
.\rebuild-run.bat
```

Use `.\rebuild-run.bat build` after dependency, lock-file, Dockerfile, or image
changes. Use `.\rebuild-run.bat full` when a no-cache rebuild is intentional.

## Verify a change

Run checks proportional to the affected path:

```powershell
# Backend suite
docker exec --user app ml-app-api-1 pytest tests

# Frontend architecture, types, and production bundle
docker exec ml-app-frontend-1 npm run build

# Public Python client
python -m unittest tests.test_ml_app_client

# Runtime health
Invoke-WebRequest -UseBasicParsing http://localhost:8000/health
Invoke-WebRequest -UseBasicParsing http://localhost:5173
```

Useful focused backend suites:

```powershell
# Full-dataset analysis and visualization
docker exec --user app ml-app-api-1 pytest tests/test_full_profile.py tests/test_profile_jobs.py tests/test_visualizations.py

# Architectural boundaries
docker exec --user app ml-app-api-1 pytest tests/test_architecture.py
```

After Compose or environment changes validate the resolved topology:

```powershell
docker compose config
```

Inspect service state and logs when a rebuild succeeds but a path is unhealthy:

```powershell
docker compose ps
docker compose logs --tail 200 api worker frontend model-runtime
```

## Run one layer outside Compose

Backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The backend image installs `backend/requirements.lock`; regenerate it with
Python 3.12 on Linux after changing direct ranges in `requirements.txt`.

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

`npm run build` also runs `scripts/check-architecture.mjs`, so an import cycle
fails before TypeScript or Vite packaging.

## Data and runtime behavior

- Local uploads and generated artifacts are under `data/repository`; the
  directory is ignored by Git.
- CSV sources receive a reusable Zstandard Parquet sidecar on the first
  full-columnar operation. Uploaded Parquet is scanned directly.
- DuckDB performs full-relation analytics and may spill to a dataset-local
  temporary directory. APIs return bounded aggregates or pages.
- Celery owns profiling, pipeline, ML, replay, monitoring, and export jobs.
- PostgreSQL stores metadata, access control, lineage, and operational records.
- The private `model-runtime` loads immutable model files from the shared local
  repository.

The most relevant local tuning variables in `.env.example` are:

- `DUCKDB_THREADS` - threads per analytical connection;
- `DUCKDB_MEMORY_LIMIT` - memory cap per connection before spill;
- `VISUALIZATION_MAX_CONCURRENCY` - concurrent heavy chart work per API process;
- `PROFILE_WORKER_CONCURRENCY` - Celery worker concurrency;
- `DESCRIPTIVE_PROFILE_RESULT_EXPIRES_SECONDS` - Redis result lifetime.

Do not increase all concurrency controls independently. Their product must fit
the host CPU and memory.

Run the synthetic profiling benchmark inside the API container:

```powershell
docker exec ml-app-api-1 python tests/benchmark_full_profile.py --rows 1000000
```

See [Descriptive profiling performance](descriptive-profiling-performance.md)
for the benchmark method and [Architecture](architecture.md) for component
ownership. Implementation entry points are listed in
[`CODEMAP.md`](../CODEMAP.md).

## Repository hygiene

Do not commit runtime data, local `.env`, virtual environments, caches,
`node_modules`, Vite output, model artifacts, or the scratch `sandbox.ipynb`.
Keep reusable deterministic data in `examples/data`.

Before publishing:

```powershell
git status --short
git diff --check
git add --dry-run .
```

Integration tests create uniquely named accounts and remove only records tagged
for the current test. Do not broaden cleanup to email domains, time windows, or
all local users.

## Known engineering gaps

- managed migrations are not yet the primary schema-change path;
- XLSX, databases, object storage, and remote query engines lack active adapters;
- long-running analytics need stronger cancellation, quotas, and persisted
  resource accounting;
- serving uses one shared Compose runtime without per-service isolation or
  autoscaling;
- the frontend has architecture and production-build checks but no broad unit,
  component-test, or lint baseline.
