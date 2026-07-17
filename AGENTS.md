# Wytyczne dla agenta

Instrukcje obowiązują podczas wszystkich prac w tym repozytorium. `AGENTS.md`
przechowuje trwałe zasady pracy i decyzje architektoniczne. Szczegóły aktualnej
implementacji znajdują się w kodzie i w [dokumentacji](docs/README.md); przed
zmianą funkcji zawsze je zweryfikuj.

## Workflow

- Domyślną, trwałą gałęzią roboczą jest `dev`. Nie twórz feature branchy bez
  wyraźnej prośby. `master` służy do okresowego utrwalania stabilnego stanu.
- Po zmianach wpływających na działanie aplikacji, jej konfigurację uruchomieniową,
  zależności, obrazy lub schemat danych uruchom `rebuild-run.bat` i sprawdź
  aplikację. Nie uruchamiaj przebudowy po zmianach wyłącznie dokumentacyjnych,
  komentarzach, formatowaniu lub innych modyfikacjach, które nie mogą wpłynąć na
  wykonanie aplikacji; zweryfikuj wtedy diff i spójność zmienionych materiałów.
  Dobierz testy, kompilację i kontrolę typów proporcjonalnie do rzeczywistego
  ryzyka. Jawna dyspozycja użytkownika dotycząca sposobu weryfikacji ma
  pierwszeństwo dla danego zadania.
- Nie uznawaj zmiany funkcjonalnej za gotową bez sprawdzenia istotnej ścieżki.
- Nie automatyzuj lokalnego UI przez integrację `browser`, dopóki użytkownik
  jawnie o to nie poprosi lub nie potwierdzi naprawy integracji. Frontend
  weryfikuj testami, kompilacją, healthcheckami i logami.
- Możesz aktualizować ten plik, gdy pojawi się nowa trwała decyzja projektowa.
  Zawsze poinformuj użytkownika o takiej zmianie. Nie zapisuj tu historii prac,
  tymczasowych planów ani katalogów aktualnie zaimplementowanych opcji.

## Cel i jakość platformy

- Buduj spójną platformę data science i machine learning obejmującą dane,
  analizy, pipeline'y, eksperymenty, modele, scoring i monitoring.
- Projektuj dla zbiorów liczących dziesiątki milionów wierszy i więcej. Dużych
  danych nie przenoś do przeglądarki ani nie materializuj w pamięci procesu, gdy
  można użyć wykonania kolumnowego, strumieniowego, asynchronicznego lub pushdown.
- Domyślnie analizuj pełny wskazany zakres. Próbka jest dozwolona wyłącznie jako
  jawnie oznaczony preview lub tryb eksploracyjny. Wynik musi podawać zakres,
  liczbę przetworzonych wierszy oraz przybliżenia i ograniczenia.
- Preferuj ograniczone kontrakty wynikowe: agregaty, histogramy, binning,
  projekcję kolumn i paginację zamiast pełnych tabel.
- Zachowuj modularne, testowalne kontrakty i czytelne granice odpowiedzialności.
  Logika danych i metryk należy do backendu; frontend konfiguruje i prezentuje.
- Uwzględniaj bezpieczeństwo zapytań, limity zasobów, współbieżność,
  obserwowalność, idempotencję i możliwość skalowania horyzontalnego.
- Najpierw mierz i optymalizuj obecny stos: Python, DuckDB, Parquet, PostgreSQL,
  kolejkę workerów i React. Spark lub inną ciężką infrastrukturę wprowadzaj tylko
  po wykazaniu mierzalnej potrzeby i uwzględnieniu kosztu operacyjnego.

## Business Case i dane

- `Business Case` jest kontekstem biznesowym spinającym artefakty. Jest
  obowiązkowy dla ML, scoringu/servingu i monitoringu, a opcjonalny dla danych i
  analiz. Nie zastępuje datasetów, pipeline'ów, modeli ani deploymentów.
- Dataset i `DataView` mogą należeć do wielu Business Cases. Przypięcie ma jedną
  rolę, np. `source`, `training`, `validation`, `test`, `scoring_input`,
  `scoring_output`, `monitoring_actuals` lub `reference`, oraz opcjonalny opis.
- Nie wymagaj targetu ani row ID przy prostym uploadzie i profilowaniu. Stabilny
  identyfikator rekordu jest wymagany tam, gdzie potrzebuje go scoring, target
  joining lub monitoring.
- Analiza w kontekście Business Case może odziedziczyć target, typ problemu i
  metryki, ale użytkownik może je zmienić. Raport zapisuj do BC tylko po jawnej
  akcji użytkownika.
- Nie dodawaj sztucznych danych wyłącznie dla zapełnienia UI. Generatory danych
  demonstracyjnych mają być deterministyczne, odtwarzalne, realistyczne,
  udokumentowane i wolne od leakage; powinny mieć test kontraktu.

## Pipeline'y i wykonanie

- Pipeline należy do jednego Business Case i jest elastycznym, wysokopoziomowym
  workflow DAG. `purpose` i template ułatwiają start, lecz nie ograniczają
  katalogu kroków.
- Rozdzielaj `Pipeline`, niemutowalne/opublikowane `PipelineVersion` oraz
  audytowalne `PipelineRun`. Draft można edytować; zmiana published tworzy nową
  wersję. Definicja ma stabilne identyfikatory kroków i portów oraz hash.
- Każdy wykonany krok ma `PipelineStepRun`, status, czasy, liczniki, warnings,
  output manifest i izolowany błąd. Uruchomienie kroku wykonuje wymaganych
  przodków. Nie rozwiązuj zależności przez niejawne „latest”.
- Pipeline'y wymieniają dane przez wersjonowane artefakty, nie przez bezpośrednie
  zależności wykonawcze między pipeline'ami. Równoległe runy muszą mieć
  odseparowany stan UI i backendu.
- Dry-run tworzy wyłącznie jawnie tymczasowe wyniki i nie rejestruje oficjalnych
  datasetów, modeli ani raportów.
- Wysokopoziomowe kroki lifecycle i wewnętrzne operacje domenowe to różne
  poziomy. Operacje takie jak select, join czy custom SQL pozostają wewnątrz
  kroku Data Engineering.
- Nie pokazuj funkcji jako gotowej, jeśli backend jej nie wykonuje. Zachowuj
  kompatybilność opublikowanych wersji; migracje draftów mają być
  deterministyczne.

## Data Engineering i Feature Engineering

- Nie twórz osobnego silnika ani bytu `ETL Job`. DE/FE korzystają z wersji,
  runów, artefaktów i lineage wspólnego mechanizmu pipeline.
- Źródła i materializacje obsługuj przez adaptery. Obecny przepływ plikowy używa
  CSV/Parquet i Data Views, DuckDB do transformacji oraz Parquet jako domyślnego
  trwałego outputu. Przyszłe bazy i object storage powinny używać pushdown, a nie
  kopiowania całych tabel do aplikacji.
- Definicja DE jest DAG-iem wspierającym wiele wejść, joiny, rozgałęzienia i
  wiele wyjść. UI może być formularzem/listą, ale korzysta z tego samego
  kontraktu JSON i zachowuje stabilne ID.
- `User Written SQL` jest kontrolowanym, ograniczonym zapytaniem read-only.
  Dowolny Python nie jest dozwolonym krokiem. Nie obiecuj pełnego column lineage
  dla custom SQL.
- Trwały output jest nowym artefaktem z lineage. Data contracts wspierają
  polityki `fail`, `warn` i `reject`; rejected records są osobnym wynikiem.
- Nie nazywaj wersjonowanego feature pipeline'u feature store'em. Feature store
  wymaga osobnego kontraktu encji, event time, point-in-time correctness oraz
  spójnego offline/online serving.
- Transformacje uczone na danych zapisują wersjonowany fitted state. Fit odbywa
  się wyłącznie na train; validation, test i scoring tylko stosują zapisany stan.

## Artefakty, lineage i audyt

- `Artifact` jest technicznym rejestrem lineage, nie osobnym pojęciem w UI.
  Użytkownik widzi datasety, Data Views, modele, raporty, deploymenty i runy.
- Każdy artefakt platformy ma lineage co najmniej do inputów, wersji pipeline'u,
  runu, kroku/portu, twórcy, czasu, schematu i liczby wierszy.
- Lineage jest portowe (`step_id + port_id`). Frontend nie rekonstruuje grafu;
  korzysta z backendowego resolvera.
- Artefakty i modele są niemutowalne. Zewnętrznie rejestrowany obiekt musi mieć
  jawne źródło i opis.
- Zachowuj pola audytowe `owner`, `created_by` i `updated_by`. Pełny RBAC jest
  wdrażany zgodnie z zasadami poniżej; brak kompletnego RBAC w przejściowym
  stanie implementacji nie zwalnia z kontroli dostępu do assetów.

## Użytkownicy, administracja i współdzielenie

- Instalacja jest jednofirmowa. Nie wprowadzaj tenantów, organizacji ani
  administratorów tenantów. Samodzielna rejestracja pozostaje otwarta, a każde
  nowo zarejestrowane konto otrzymuje wyłącznie bazową rolę platformową `user`.
- Rozdzielaj role platformowe od dostępu do zasobów. Role platformowe to `user`,
  `governance_steward` i `administrator`; nie używaj roli zasobowej `owner` jako
  roli platformowej. Administratorzy mogą podnosić role innych kont.
  `governance_steward` jest na razie wyłącznie przewidzianą rolą bez dodatkowych
  uprawnień; nie implementuj dla niej niejawnego globalnego odczytu ani bypassu.
- Platforma zawsze bootstrapuje zarezerwowane konto techniczne o loginie `root`,
  inicjalnym haśle `toor` i roli `administrator`. Konto root musi być tworzone
  idempotentnie, nie może zostać usunięte, dezaktywowane ani pozbawione roli
  administratora. Umożliwiaj zmianę jego hasła, ale na obecnym etapie jej nie
  wymuszaj. Restart, migracja ani ponowny bootstrap nigdy nie mogą przywrócić
  `toor`, jeżeli hasło zostało zmienione. Dopuszczalne jest nieblokujące
  ostrzeżenie, że aktywne pozostaje hasło inicjalne.
- Logowanie musi obsługiwać zarezerwowany login `root` mimo że zwykłe konta są
  rejestrowane adresem e-mail. Walidacja logowania nie może odrzucić istniejącego
  `toor` tylko dlatego, że polityka nowych haseł wymaga większej długości;
  politykę siły stosuj przy rejestracji i zmianie hasła, nie do wstępnego
  odrzucania poświadczeń podczas logowania.
- Administrator ma globalny, audytowany bypass kontroli dostępu i domyślnie może
  przeglądać wszystkich użytkowników, wszystkie Business Cases i wszystkie
  obiekty. Może zarządzać rolami platformowymi, stanem kont, grupami,
  członkostwem, dowolnymi grantami i transferem własności. Nie twórz dla niego
  osobnych grantów do każdego zasobu ani nie zmieniaj `owner_id` tylko po to,
  aby umożliwić administracyjny dostęp. Administrator nigdy nie poznaje
  istniejących haseł; może je wyłącznie resetować lub inicjować ich zmianę.
- Business Case jest podstawową granicą współdzielenia. Standardowe,
  hierarchiczne role dostępu do BC to:
  - `report_viewer`: widzi metadane BC i opublikowane raporty, w tym scoringowe
    i monitoringowe, ale nie widzi datasetów, Data Views, danych rekordowych,
    konfiguracji pipeline'ów, plików modeli ani drill-down do danych źródłowych;
  - `reader`: pełny odczyt BC i jego widocznych artefaktów, danych, lineage,
    wersji i runów, bez zmian i uruchamiania obliczeń;
  - `contributor`: uprawnienia readera oraz tworzenie, edycja draftów i
    uruchamianie analiz i pipeline'ów, bez zarządzania dostępem, transferu
    własności i usunięcia całego BC;
  - `manager`: uprawnienia contributora oraz zarządzanie dostępem do BC; może
    nadawać role najwyżej do `manager`, ale nie `owner`, nie przenosi własności
    i nie usuwa całego BC;
  - `owner`: pełna kontrola, w tym nadawanie ownera, transfer własności oraz
    archiwizacja lub usunięcie BC.
- Nazwa Business Case jest globalnie unikalna bez rozróżniania wielkości liter.
  Konflikt przy tworzeniu lub zmianie nazwy zwraca `409 Conflict`, także gdy
  istniejący BC nie jest widoczny dla użytkownika; jest to świadoma decyzja
  produktowa nadrzędna wobec non-disclosure dla tej konkretnej operacji.
- Grant do BC obejmuje jego metadane i powiązane datasety/Data Views, pipeline'y,
  wersje, runy, wyniki, eksperymenty, modele, raporty, prediction datasets,
  scoring, deploymenty, monitoring i widoczne lineage. Nie duplikuj grantów na
  każdym potomnym artefakcie; rozstrzygaj dostęp przez centralną politykę
  zasób-akcja i filtruj dostępne listy już w zapytaniach do PostgreSQL.
- Efektywny dostęp jest sumą ścieżek wynikających z administracji, własności,
  bezpośredniego grantu użytkownika, grantu grupowego i grantu przez BC. Na
  pierwszym etapie nie wprowadzaj jawnych grantów `deny`. Odebranie jednej
  ścieżki nie odbiera dostępu, jeżeli nadal istnieje inna aktywna ścieżka.
- Dataset lub DataView może należeć do wielu BC. Dostęp przez jeden BC nie
  ujawnia innych BC, ich metadanych, powiązań ani niedostępnych fragmentów
  lineage. Odpięcie od jednego BC nie odbiera dostępu zapewnianego przez inny BC
  lub grant bezpośredni.
- Bezpośrednie udostępnianie obiektu jest wyjątkową, jawnie oznaczoną ścieżką
  przeznaczoną przede wszystkim dla luźnych datasetów i Data Views, opcjonalnie
  samodzielnych analiz lub raportów, jeżeli istnieją poza BC. Używa ról
  `reader`, `editor` i `owner`. Modele, pipeline'y ML, scoring, monitoring i
  deploymenty współdziel przez obowiązkowy Business Case. Przypięcie luźnego
  obiektu do BC nie może po cichu usunąć jego wcześniejszych grantów
  bezpośrednich; pokaż je jako niezależne ścieżki i pozwól jawnie je wycofać.
- Grant może wskazywać użytkownika albo grupę. Grupy są rekomendowaną ścieżką i
  mają nazwę, opis, status, członków, managera/właściciela oraz pola audytowe.
  Zarządzanie grupą jest niezależne od zarządzania BC: manager BC może nadać
  grupie dostęp, lecz zmienia członkostwo tylko wtedy, gdy osobno zarządza grupą
  albo jest administratorem.
- Kontrole dostępu obowiązują wszystkie endpointy, pobieranie plików, resolver
  lineage, zadania asynchroniczne i wyniki workerów, a nie wyłącznie listy i UI.
  Dla zadań co najmniej ponownie sprawdzaj dostęp przed rozpoczęciem wykonania;
  wyniki pozostają chronione aktualną polityką BC. Zmiana roli platformowej,
  blokada konta, zmiana hasła i istotne odebranie dostępu muszą unieważniać lub
  wersjonować sesje tak, aby nie ufać bezterminowo rolom zapisanym w JWT.
- Audytuj logowania root, zmiany haseł i ról platformowych, blokady kont,
  resetowanie sesji, zmiany grup i członkostwa, wszystkie granty, nadawanie
  `manager`/`owner`, transfer własności oraz administracyjny dostęp do cudzych
  zasobów. Zdarzenie zawiera aktora, operację, podmiot docelowy, zasób, poprzedni
  i nowy stan, czas oraz identyfikator żądania; opcjonalnie powód i wygaśnięcie.

## ML, AutoML i raporty

- Modele należą do Business Case i powstają w eksperymencie. Pipeline
  Training/AutoML jest właściwą ścieżką tworzenia niemutowalnego model artifact;
  legacy standalone training pozostaje prototypem metadata-only.
- Training domyślnie konsumuje dynamiczny Feature Manifest, a model zapisuje
  konkretną, uporządkowaną listę cech użytych przez estimator.
- AutoML/AutoFE dla danych tabelarycznych optymalizuje całą ścieżkę: recepturę
  FE, selekcję, model, hiperparametry i walidację. Receptury, fitted state,
  Feature Manifest, model, metryki i provenance pozostają osobnymi,
  odtwarzalnymi artefaktami.
- Wszystkie operacje zależne od danych lub targetu są fitowane wewnątrz train
  foldu. Test pozostaje nietknięty podczas optymalizacji, a zwycięzca jest
  finalnie refitowany na dozwolonym train scope. Nie wolno używać globalnie
  fitowanego FE w fold-local CV.
- Przestrzeń eksperymentu jest wersjonowana i deterministyczna dla seeda.
  Kandydaci są tymczasowi; wynik zapisuje zakres danych, foldy, wyniki, koszty,
  ostrzeżenia oraz przyczyny pominięcia, pruningu i błędów.
- AutoML/AutoFE jest na obecnym etapie zamkniętym zakresem funkcjonalnym.
  Klasteryzacja, szeregi czasowe, kompleksowe NLP, ensemble/stacking i native
  categorical wymagają osobnej decyzji produktowej; nie traktuj ich jako
  aktywnego roadmapu.
- Raport treningowy jest artefaktem pipeline'u Training/AutoML i obejmuje
  metryki pełnozbiorowe, provenance walidacji/search oraz ograniczone
  explainability. SHAP lub permutation importance mogą używać jawnie opisanej,
  deterministycznej próbki bez zmiany zakresu głównych metryk.
- Raport monitoringu ma odrębny kontrakt i szablon od raportu treningowego.
  Logika metryk należy do backendu, frontend wyłącznie prezentuje kontrakt.

## Scoring, monitoring i deployment

- Test Scoring z targetem może tworzyć wersjonowany Scoring Report. Produkcyjny
  Batch Scoring bez targetu tworzy prediction dataset, ale nie metryki
  skuteczności ani Scoring Report.
- Batch Scoring i monitoring skuteczności są osobnymi pipeline'ami. Monitoring
  łączy niemutowalny prediction dataset z późniejszymi actuals i tworzy nowy
  artefakt oraz raport; nie modyfikuje wcześniejszych predykcji.
- Prediction dataset zachowuje stabilny row ID oraz lineage do inputu, modelu,
  fitted transform, wersji pipeline'u i runu.
- Inference używa atomowego bundle z jednego runu treningowego: modelu, receptury
  FE i fitted state. Nie pozwalaj niezależnie dobierać niezgodnych elementów ani
  refitować transformacji na batchu scoringowym.
- Role `champion`, `challenger` i `shadow` dotyczą modelu/deploymentu, nie
  pipeline'u. Produkcyjny deployment wiąże konkretny model, pipeline version i
  kanały servingowe; operationalization powinno mieć jawny Approval Gate.
- Monitoring danych wejściowych i monitoring skuteczności to odrębne problemy.
  Skuteczność można liczyć dopiero po dostarczeniu actuals.
