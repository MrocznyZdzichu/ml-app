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

Frontend production build:

```powershell
docker exec ml-app-frontend-1 npm run build
```

Health checks:

```powershell
Invoke-WebRequest -UseBasicParsing http://localhost:8000/health
Invoke-WebRequest -UseBasicParsing http://localhost:5173
```

## Local Runtime Data

Uploaded local files are stored under `data/repository` when using Docker
Compose. This directory is intentionally ignored by Git. Keep reusable demo data
under `examples/data` instead.

Python bytecode, test caches, Vite output, node modules, local env files, model
artifacts, and runtime data should not be committed.

The root-level `sandbox.ipynb` notebook is also ignored. It is intended for quick
local experiments and scratch calculations, not shared documentation.

## First Git Publish

The project includes `.gitignore` and `.gitattributes` for a Windows + Docker
development workflow. Before publishing, check what will be committed:

```powershell
git status --short
git add --dry-run .
```

Then create the first commit and connect a remote:

```powershell
git add .
git commit -m "Initial ML App workbench"
git branch -M main
git remote add origin <your-repository-url>
git push -u origin main
```

## Intended Next Steps

- Add Alembic migrations and SQLAlchemy repositories.
- Add database connection testing and external source adapters.
- Add parquet and xlsx source adapters.
- Implement profiling with persisted artifacts.
- Implement model training workers and artifact registration.
- Add deployment adapter for Docker Compose or Kubernetes.
