# Code map

Krótka mapa wejścia do kodu. Szczegóły kontraktów znajdują się w modułach i
`docs/`; ten plik nie jest kopią dokumentacji produktu.

## Uruchomienie i kompozycja

- `backend/app/main.py` — aplikacja FastAPI i adaptery globalne.
- `backend/app/api/router.py` — publiczny routing.
- `backend/app/core/container.py` — composition root i wiring portów.
- `backend/app/core/errors.py` + `backend/app/api/error_handlers.py` — błędy
  aplikacyjne i mapowanie HTTP.
- `backend/app/worker/tasks.py` — cienkie adaptery kolejki.

## Dane i analizy

- `backend/app/modules/datasets/` — lifecycle datasetów, Data Views, preview,
  SQL, wizualizacje i storage kolumnowy.
- `backend/app/modules/analysis/full_profile.py` — pełnozbiorowy profil DuckDB.
- `frontend/src/data/catalog/` — katalog i wersje datasetów.
- `frontend/src/data/analysis/` — koordynacja przestrzeni analiz i lazy loading.
- `frontend/src/data/browser/` — browsing, dialogi, kontrakty i operacje tabeli.
- `frontend/src/data/profile/` — profil opisowy, szczegóły i kontrakty.
- `frontend/src/data/DataWorkspacePanels.tsx` — cienka fasada kompatybilności.

## Business Cases i dostęp

- `backend/app/modules/business_cases/repository.py` — port i kompatybilna fasada.
- `backend/app/modules/business_cases/tables.py` — definicje tabel.
- `backend/app/modules/business_cases/repositories/` — adaptery memory/PostgreSQL.
- `backend/app/modules/sharing/policy.py` — centralna polityka dostępu.

## Pipeline'y i ML

- `backend/app/modules/pipelines/service.py` — publiczna fasada przypadków użycia.
- `backend/app/modules/pipelines/run_executor.py` — wykonanie runu.
- `backend/app/modules/pipelines/step_handlers.py` — kompatybilna fasada i rejestr
  wyspecjalizowanych handlerów.
- `backend/app/modules/pipelines/data_step_handlers.py` oraz
  `backend/app/modules/pipelines/{training,automl,scoring,monitoring}_step_handler.py`
  — wykonanie poszczególnych rodzin kroków.
- `backend/app/modules/pipelines/step_contracts.py` — kontrakty handlerów.
- `backend/app/modules/pipelines/feature_engineering.py` — kontrakt i silnik FE.
- `backend/app/modules/pipelines/modeling_catalog.py` — katalog algorytmów.
- `frontend/src/pipelines/` — edytory, wersje, runy i dry-run.

## Modele, raporty i serving

- `backend/app/modules/models/` — registry i modele.
- `backend/app/modules/scoring_reports/` — wersjonowane raporty scoringowe.
- `backend/app/modules/serving/service.py` — deployment i inference.
- `backend/app/modules/serving/monitoring.py` — monitoring online.
- `frontend/src/reports/` — współdzielone wizualizacje raportów.
- `frontend/src/operational/ServingPanel.tsx` — UI serving/monitoring.

## Klienci API

- `frontend/src/api/http.ts` — transport przeglądarkowy.
- `frontend/src/api/contracts/` — kontrakty domenowe.
- `frontend/src/api/client.ts` — kompatybilna fasada API.
- `ml_app_client/client.py` — cienka, kompatybilna fasada klienta Python.
- `ml_app_client/transport.py` — wspólny transport HTTP i mapowanie błędów.
- `ml_app_client/{datasets,business_cases,pipelines,model_registry,scoring_reports}.py`
  — workflow katalogu danych, BC, pipeline'ów, modeli i raportów.
- `ml_app_client/serving.py` — agregator klienta serving; implementacja jest w
  `deployments.py`, `inference.py` i `online_monitoring.py`.

## Testy i weryfikacja

- `backend/tests/test_architecture.py` — wykonywalne granice backendu.
- `frontend/scripts/check-architecture.mjs` — wykrywanie cykli importów.
- `frontend`: `npm run build`.
- `backend` w kontenerze: `python -m pytest tests/... -q`.
- cały runtime: `rebuild-run.bat`, następnie healthchecki i logi.
