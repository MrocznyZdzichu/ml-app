# Pipeline'y, Data/Feature Engineering i ML

## Pipeline i wykonanie

- Pipeline należy do jednego Business Case i jest wysokopoziomowym DAG-iem.
- `step_handlers.py` jest wyłącznie kompatybilną fasadą i rejestrem. Kontrakty
  wykonania oraz handlery DE/FE, Training, AutoML, Scoring i Monitoring rozwijaj
  w wyspecjalizowanych modułach; moduły te nie mogą importować fasady.
- Rozdzielaj edytowalny `Pipeline`, niemutowalny `PipelineVersion` i audytowalny
  `PipelineRun`. Zmiana published tworzy nową wersję.
- Definicja ma stabilne ID kroków i portów oraz hash. Krok wykonuje wymaganych
  przodków; nie rozwiązuj zależności przez niejawne `latest`.
- Każdy krok ma osobny run, czasy, liczniki, warnings, manifest wyników i
  izolowany błąd. Równoległe runy nie współdzielą stanu.
- Pipeline'y wymieniają wersjonowane artefakty, nie bezpośredni stan wykonawczy.
- Dry-run tworzy tylko jawnie tymczasowe wyniki.

## Data i Feature Engineering

- Nie twórz osobnego silnika ani bytu ETL Job. DE/FE używa wspólnych wersji,
  runów, artefaktów i lineage pipeline'u.
- Przepływ plikowy używa CSV/Parquet, DuckDB i domyślnie Parquet output.
  Przyszłe źródła korzystają z adapterów i pushdown.
- DE jest DAG-iem z wieloma wejściami, joinami, rozgałęzieniami i outputami.
- User Written SQL jest ograniczonym read-only SQL. Dowolny Python nie jest
  dozwolonym krokiem.
- Data contracts wspierają `fail`, `warn`, `reject`; rejected rows są osobnym
  wynikiem.
- Transformacje uczone zapisują wersjonowany fitted state. Fit tylko na train;
  validation, test i scoring wyłącznie stosują stan.
- Feature pipeline nie jest feature store'em bez entity/event time,
  point-in-time correctness oraz spójnego offline/online serving.

## Training i AutoML

- Model powstaje w eksperymencie przez Training/AutoML i zapisuje konkretną,
  uporządkowaną listę cech.
- AutoML/AutoFE optymalizuje recepturę FE, selekcję, model, hiperparametry i
  walidację. Operacje zależne od danych/targetu są fitowane wewnątrz train foldu.
- Test pozostaje nietknięty podczas search; zwycięzca jest refitowany na
  dozwolonym train scope.
- Search space jest wersjonowany i deterministyczny dla seeda. Wynik zapisuje
  zakres, foldy, koszty, warningi, pruning, pominięcia i błędy.
- Klasteryzacja, szeregi czasowe, kompleksowe NLP, ensemble/stacking i native
  categorical są poza aktualnym zakresem AutoML.
- Raport treningowy przechowuje pełnozbiorowe metryki i provenance.
  Explainability może używać jawnie opisanej deterministycznej próbki.
- Inference używa atomowego bundle: model, receptura FE i fitted state z jednego
  runu. Nigdy nie refituj transformacji na batchu scoringowym.
