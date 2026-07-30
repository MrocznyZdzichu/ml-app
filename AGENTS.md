# Wytyczne dla agenta

Instrukcje obowiązują w całym repozytorium. Szczegółowe zasady domenowe są
umieszczone w zakresowych plikach `AGENTS.md`; przed zmianą pliku przeczytaj
instrukcje obowiązujące w jego katalogu. Aktualną implementację opisują kod,
[CODEMAP.md](CODEMAP.md) oraz [dokumentacja](docs/README.md).

## Workflow

- Trwałą gałęzią roboczą jest `dev`. Nie twórz feature branchy bez prośby.
- Po zmianie kodu, konfiguracji, zależności, obrazu albo schematu uruchom
  `rebuild-run.bat`, a następnie testy proporcjonalne do ryzyka.
- Zmiany wyłącznie dokumentacyjne weryfikuj przez diff; nie wymagają rebuildu.
- Nie uznawaj funkcji za gotową bez sprawdzenia istotnej ścieżki.
- Nie automatyzuj lokalnego UI przez integrację `browser`, dopóki użytkownik
  jawnie o to nie poprosi. Frontend sprawdzaj kompilacją, healthcheckami i logami.
- Nie nadpisuj ani nie usuwaj niezwiązanych zmian użytkownika.

## Cel i skala platformy

- Buduj spójną platformę data science i ML: dane, analizy, pipeline'y,
  eksperymenty, modele, scoring, serving i monitoring.
- Projektuj dla dziesiątek milionów wierszy i więcej. Preferuj DuckDB, Parquet,
  PostgreSQL, wykonanie kolumnowe, streaming, zadania asynchroniczne i pushdown.
- Nie przenoś dużych zbiorów do przeglądarki ani pamięci procesu, gdy wystarczy
  agregat, histogram, binning, projekcja kolumn, paginacja lub predicate pushdown.
- Analizy domyślnie obejmują pełny wskazany zakres. Próbka może być wyłącznie
  jawnie oznaczonym preview/renderingiem i nie może udawać wyniku pełnozbiorowego.
- Wynik analizy podaje zakres, liczbę przetworzonych wierszy, przybliżenia,
  warningi i ograniczenia.
- Ciężką infrastrukturę, np. Spark, wprowadzaj dopiero po wykazaniu mierzalnej
  potrzeby i kosztu operacyjnego.

## Architektura

- Stosuj SOLID, moduły o jednej odpowiedzialności, jawne porty i adaptery oraz
  jednokierunkowe zależności.
- REST API jest źródłem kontraktu. UI i `ml_app_client` są równorzędnymi
  klientami; logika domenowa i analityczna nie może istnieć wyłącznie w UI.
- Publiczne API, frontend i klient Python rozwijaj razem, zachowując identyczną
  autoryzację, walidację, paginację, idempotencję, warningi i błędy.
- Warstwa aplikacyjna używa typowanych błędów z `app.core.errors`; FastAPI
  tłumaczy je wyłącznie w adapterze HTTP. Starsze moduły migruj inkrementalnie.
- Obliczenia i zapytania umieszczaj blisko danych. Frontend konfiguruje i
  prezentuje ograniczone kontrakty.
- Uwzględniaj bezpieczeństwo zapytań, limity zasobów, współbieżność,
  obserwowalność, audyt, idempotencję i skalowanie horyzontalne.
- Nie pokazuj funkcji jako gotowej, jeśli backend jej rzeczywiście nie wykonuje.

## Globalne niezmienniki produktu

- `Business Case` spina artefakty; jest obowiązkowy dla ML, scoringu, servingu i
  monitoringu, a opcjonalny dla danych i analiz.
- Artefakty, opublikowane wersje pipeline'ów, modele, prediction datasety,
  raporty i wyniki monitoringu są niemutowalne i zachowują lineage.
- Dataset i Data View mogą należeć do wielu Business Cases. Nie wymagaj targetu
  ani row ID przy prostym uploadzie i profilowaniu.
- Instalacja jest jednofirmowa. Role platformowe to `user`,
  `governance_steward`, `administrator`; role dostępu do zasobów są odrębne.
- Konto `root` jest chronionym administratorem, bootstrapowanym idempotentnie.
  Nie wolno go usunąć, dezaktywować ani zdegradować ani przywrócić hasła `toor`
  po jego zmianie.
- Administrator ma audytowany globalny bypass. Pozostali użytkownicy widzą listy
  i obiekty wyłącznie przez centralną politykę dostępu.
- Nazwa Business Case jest globalnie unikalna bez uwzględniania wielkości liter.

## Instrukcje zakresowe

- Ogólne moduły backendu, Business Cases, artefakty i dostęp:
  `backend/app/modules/AGENTS.md`.
- Pipeline'y, Data/Feature Engineering, ML i AutoML:
  `backend/app/modules/pipelines/AGENTS.md`.
- Scoring, deployment i monitoring online:
  `backend/app/modules/serving/AGENTS.md`.
- Frontend i zasady skalowalnego UI: `frontend/AGENTS.md`.
- Publiczny klient Python: `ml_app_client/AGENTS.md`.

Nie kopiuj tych reguł do nowych dokumentów. Rozszerz właściwy zakresowy
`AGENTS.md` tylko wtedy, gdy powstaje trwała decyzja projektowa.
