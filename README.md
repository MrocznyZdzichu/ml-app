# ML App

ML App is a local, containerized data-science and machine-learning platform. It
covers governed data access, full-dataset analytics, versioned pipelines,
Training/AutoML, batch scoring, model registry, online serving, and monitoring.

The project is actively evolving and has been developed with substantial AI
assistance. Review, test, and harden it before using sensitive data or running
production workloads.

## Start here

Requirements:

- Docker with Compose v2;
- free local ports `5173`, `8000`, `5432`, `6379`, `9000`, and `9001`.

Start the stack:

```powershell
docker compose up --build
```

Open:

- UI: `http://localhost:5173`
- REST API and Swagger: `http://localhost:8000/docs`
- MinIO console: `http://localhost:9001`

For local administration, the first startup creates `root` with the initial
password `toor`. Change it after signing in; later restarts do not reset a
changed password.

The checked-in `.env.example` contains local defaults. Create `.env` only when
you need to override Compose variables. The shipped passwords and secret are
for local development only.

After normal code changes run:

```powershell
.\rebuild-run.bat
```

Use `.\rebuild-run.bat build` after dependency or Dockerfile changes, and
`.\rebuild-run.bat full` only when a no-cache rebuild is needed.

## First useful workflow

1. Sign in or register a user.
2. Create a Business Case.
3. Upload a CSV or Parquet dataset from `examples/data`.
4. Assign target, identifier, timestamp, and feature roles when the workflow
   needs them.
5. Run descriptive profiling or build a Data View.
6. Create and publish a pipeline, then run Training or AutoML.
7. Use Test Scoring for labeled evaluation or Batch Scoring for production-like
   predictions.
8. Promote a model version, create a service, and score through its stable
   endpoint.

For an executable API-first version of this lifecycle, install the client with
`pip install -e .` and follow
[`examples/API-usage`](examples/API-usage/README.md). The numbered notebooks use
stable names and are designed to be rerun.

## What is implemented

- authentication, protected `root` administration, users, groups, Business Case
  roles, direct loose-data grants, and audit events;
- CSV and flat tabular Parquet upload, dataset versions, metadata, Data Roles,
  bounded preview, read-only SQL, and reusable Data Views;
- full-row DuckDB profiling, server-side visualizations, trends, drill-down, and
  asynchronous analytical jobs;
- versioned Data Engineering and Feature Engineering DAGs with immutable
  outputs, fitted state, lineage, and data contracts;
- Training and tabular AutoML for binary classification, multiclass
  classification, and regression;
- immutable models, evaluation reports, prediction datasets, batch monitoring,
  and the public Python client;
- versioned online services with champion, challenger, shadow, and fallback
  roles, a durable Inference Log, replay, and manual online monitoring.

Full-dataset operations scan the selected relation and return bounded aggregates
or paginated projections. Preview and rendering limits are reported separately
and must not be interpreted as the analyzed row scope.

## Important boundaries

- Ingestion supports local UTF-8 CSV and flat tabular Parquet. XLSX, databases,
  APIs, and object-storage sources are not connected yet.
- Files and generated artifacts use `data/repository` in the local Compose
  runtime. MinIO is running but is not the active artifact store.
- Analytics are single-node DuckDB/Parquet jobs. There is no distributed query
  engine, persisted cancellation, or production quota scheduler.
- Data Browser is a bounded exploration surface. Saved views, Custom SQL,
  profiling, and chart aggregation execute on the full server-side relation and
  return bounded results.
- Online serving uses one private shared model-runtime container. It does not
  provision or autoscale a container per service.
- Export and legacy standalone analysis/training paths remain provisional.

See the feature references for exact contracts and limits rather than relying on
this overview.

## Repository map

- `backend/` - FastAPI API, domain/application modules, persistence, workers,
  migrations, and backend tests.
- `frontend/` - React/TypeScript UI and API client.
- `ml_app_client/` - supported Python integration client.
- `services/model-runtime/` - private runtime for online model execution.
- `examples/` - deterministic datasets and executable API notebooks.
- `docs/` - architecture, development instructions, feature references, and
  dated engineering audits.
- [`CODEMAP.md`](CODEMAP.md) - short guide to current source-code entry points.

The current module boundaries are summarized in
[`docs/architecture.md`](docs/architecture.md). Start from
[`docs/README.md`](docs/README.md) when looking for a specific feature.

## Verification

Rebuild and start the whole application after code, configuration, dependency,
image, or schema changes:

```powershell
.\rebuild-run.bat
```

Then run checks proportional to the change:

```powershell
docker exec --user app ml-app-api-1 pytest tests
docker exec ml-app-frontend-1 npm run build
Invoke-WebRequest -UseBasicParsing http://localhost:8000/health
Invoke-WebRequest -UseBasicParsing http://localhost:5173
```

The frontend build includes TypeScript compilation, an import-cycle architecture
check, and the production Vite bundle. More focused commands and runtime tuning
are documented in [`docs/development.md`](docs/development.md).

## Documentation

- [Documentation map](docs/README.md)
- [Architecture](docs/architecture.md)
- [Development workflow](docs/development.md)
- [Python client](ml_app_client/README.md)
- [Executable API examples](examples/API-usage/README.md)
- [Data and Analysis reference](docs/analysis-data-browser-reference.md)
- [AutoML and AutoFE](docs/automl-autofe-stage-1.md)
- [Online model serving](docs/online-model-serving-stage-1.md)
- [Online service monitoring](docs/online-service-monitoring-stage-1.md)
