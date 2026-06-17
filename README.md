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
- run read-only Custom SQL,
- save reusable Data Views,
- use the same Data Roles and Data Browsing tools on saved views.

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

- full-dataset filtering/searching before preview limits are applied,
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

### Data Views

Data Views are saved, reusable transformations over source datasets. They can be
created from a clicked Data Browser state or Custom SQL. Views are shown in
Overview, Data, and Analysis, and they behave like normal datasets in Data Roles
and Data Browsing.

When possible, data roles are inherited from the source dataset for columns that
survive in the view.

## Example Data

Use these files for manual testing:

- `examples/data/iris.csv`
- `examples/data/general-example.csv`

`general-example.csv` contains 10,000 synthetic customer-churn-like rows with
mixed numeric and categorical columns, useful for testing filtering, grouping,
aggregation, sorting, Custom SQL, and Data Views.

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

## Git Notes

The repository is prepared to keep source code, docs, infrastructure, tests, and
example datasets in Git while excluding local runtime data, caches, build
outputs, virtual environments, secrets, and model artifacts.

This working tree has been initialized with `git init`. Before the first commit,
review:

```powershell
git status --short
```

Suggested first commit flow:

```powershell
git add .
git commit -m "Initial ML App workbench"
git branch -M main
git remote add origin <your-repository-url>
git push -u origin main
```
