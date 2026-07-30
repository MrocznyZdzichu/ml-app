# Scoring, deployment i monitoring online

## Scoring i deployment

- Test Scoring z targetem może tworzyć Scoring Report. Batch Scoring bez targetu
  tworzy prediction dataset, ale nie metryki skuteczności.
- Prediction dataset zachowuje row ID i lineage do inputu, modelu, bundle,
  wersji pipeline'u i runu.
- `ModelStage`: `developed`, `staging`, `production`, `archived`. Role usługi:
  `champion`, `challenger`, `shadow`, `fallback`; nie mieszaj tych pojęć.
- Aktywna rewizja ma jednego championa, najwyżej jeden fallback i dowolną liczbę
  challengerów/shadow. Zmiana ról lub rollback tworzy nową niemutowalną rewizję.
- Challenger ma chroniony endpoint/replay, shadow nie wpływa na odpowiedź.
  Fallback uruchamia się raz tylko przy błędzie technicznym, nigdy walidacyjnym.
- Centralne API uwierzytelnia, autoryzuje, waliduje i limituje; prywatny runtime
  nie jest publicznym endpointem.
- Online scoring przyjmuje najwyżej 1000 rekordów. Brak record_id generuje
  techniczne ID i warning o ograniczeniu późniejszego joinu.

## Inference Log

- Deployment ma jeden logiczny, partycjonowany Inference Log, dostępny przez
  REST i klienta. Używa filtrowania, paginacji kursorowej i eksportu.
- Zapis obejmuje request/correlation/idempotency ID, konto, rewizję, model,
  bundle, rolę, fallback, wejścia, odpowiedzi, status, warningi i latency.
- Domyślna retencja pełnych wejść/odpowiedzi to 365 dni per deployment.
- Trwały zapis jest częścią sukcesu scoringu. Jeśli nie można go zagwarantować,
  zwróć 503 i nie przedstawiaj predykcji jako udanej.

## Monitoring online

- Monitoring uruchamia się ręcznie z API, klienta lub UI jako asynchroniczny,
  audytowalny run. Harmonogramy, alerty i automatyczne decyzje są poza zakresem.
- `scored_at` jest obowiązkową osią UTC. Run materializuje niemutowalny Parquet
  snapshot i wykonuje pełnozakresowe obliczenia strumieniowo/DuckDB.
- Join actuals preferuje `prediction_id`, następnie `request_id + record_id`.
  Sam `record_id` jest dozwolony wyłącznie, gdy jest jednoznaczny.
- Nulle, duplikaty i many-to-many zatrzymują run. Raport pokazuje pełny
  mianownik, coverage, brakujące actuals i actuals bez predykcji.
- Skuteczność usługi i poszczególnych modeli raportuj oddzielnie. Challenger bez
  actuals nie jest pomiarem skuteczności.
- Buckety są półotwartymi kalendarzowymi zakresami UTC. Diagnostyki wykresowe
  backend liczy najwyżej dla ośmiu jawnie wybranych okresów.
- Dashboard jest read modelem nad ograniczonymi agregatami. Nie łącz metryk o
  niezgodnej semantyce, targetach, jednostkach lub wersjach.
- Batchowy template monitoring zachowuje dotychczasowy kontrakt; online
  monitoring dodaje adapter Inference Log, ale go nie zastępuje.
