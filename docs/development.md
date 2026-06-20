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
docker exec ml-app-api-1 pytest tests/test_full_profile.py tests/test_profile_jobs.py
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

See `descriptive-profiling-performance.md` for measured results, scaling
characteristics, and the current saved Data View limitation.

## Local Runtime Data

Uploaded local files are stored under `data/repository` when using Docker
Compose. This directory is intentionally ignored by Git. Keep reusable demo data
under `examples/data` instead.

Python bytecode, test caches, Vite output, node modules, local env files, model
artifacts, and runtime data should not be committed.

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
- Push saved Data View profiling into the full-row DuckDB execution path.
- Implement model training workers and artifact registration.
- Add deployment adapter for Docker Compose or Kubernetes.
