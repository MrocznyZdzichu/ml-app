# Wytyczne dla agenta

Niniejsze instrukcje obowiązują podczas wszystkich prac w tym repozytorium.

## Automatyzacja UI w lokalnym środowisku

- Nie próbuj automatyzować ani klikać lokalnego UI przez integrację `browser`,
  dopóki użytkownik nie poprosi o to jawnie albo nie potwierdzi, że integracja
  została naprawiona. W tym środowisku połączenie regularnie kończy się błędem
  `codex/sandbox-state-meta: missing field sandboxPolicy`, więc takie próby tylko
  zużywają czas i tokeny.
- Weryfikuj frontend przez kompilację, testy automatyczne, healthchecki i logi.
  Braku testu przeglądarkowego nie raportuj jako problemu przy każdym zadaniu;
  wspomnij o nim tylko wtedy, gdy ręczna interakcja UI jest konieczna do oceny
  poprawności zmiany.

## Obowiązkowy workflow

- Domyślną gałęzią roboczą zespołu przed pierwszym wydaniem jest `dev`. Nie twórz standardowo osobnych feature branchy, chyba że użytkownik wyraźnie poprosi o wyjątek.
- Zmiany integrujemy na `dev`, a do `master` przenosimy je okresowo jako świadome podbicie stabilniejszego stanu.
- Traktuj gałąź `dev` jako gałąź trwałą; nie planuj jej usuwania po merge'ach.
- Po każdej zmianie w repozytorium uruchom `rebuild-run.bat` i sprawdź, czy zakończył się powodzeniem.
- Weryfikuj zmiany proporcjonalnie do ryzyka: wykonuj odpowiednie testy, kompilację, kontrolę typów i test działającej aplikacji.
- Nie uznawaj zadania za zakończone, jeśli aplikacja po zmianach nie została uruchomiona lub istotna ścieżka nie została zweryfikowana.
- Dbaj o testy zmian, dążymy do pokrycia całości funkcjonalności testami.
- Jeśli podczas pracy uznasz, że cokolwiek powinno zostać szczególnie zapamiętane pod kątem kolejnych zadań, możesz edytować `AGENTS.md` i dopisywać tutaj informacje, wytyczne, rekomendacje lub założenia. Przy każdej takiej zmianie jawnie informuj użytkownika.

## Cel produktu i skala danych

- Projektuj aplikację jako platformę data science i machine learning przeznaczoną dla big data.
- Architektura powinna działać wydajnie także dla datasetów zawierających dziesiątki milionów wierszy i więcej.
- Nie przenoś dużych zbiorów do przeglądarki ani pamięci procesu, jeśli obliczenie może zostać wykonane strumieniowo, kolumnowo, asynchronicznie albo bliżej miejsca przechowywania danych.
- Preferuj ograniczone kontrakty wynikowe: agregaty, histogramy, binning, paginację, projekcję kolumn i predicate pushdown zamiast materializowania pełnych tabel po stronie klienta.

## Sztuczne datasety i scenariusze demonstracyjne

- Każdy sztuczny dataset musi mieć opisany realistyczny business case, cel analizy, znaczenie kolumn oraz właściwy podział train/validation/test, jeżeli ma zastosowanie.
- Generator danych musi być deterministyczny (stały, udokumentowany seed), przechowywany w repozytorium i umożliwiać dokładne odtworzenie dołączonego pliku.
- Mechanizm generujący powinien odzwierciedlać zależności istotne dla danego problemu, takie jak dynamika, opóźnienia, autokorelacja, interakcje, nakładające się klastry lub realistyczny szum; unikaj zbiorów będących wyłącznie niezależnymi losowaniami kolumn.
- Nie dodawaj przecieku targetu ani identyfikatorów udających cechy. W scenariuszach nienadzorowanych nie ujawniaj ukrytej etykiety klastra w podstawowym datasecie; dane walidacyjne przechowuj osobno, jeżeli są potrzebne.
- Dokumentuj liczbę wierszy, zakres, jednostki, brakujące dane, przybliżenia i ograniczenia. Próbki demonstracyjne muszą być jawnie oznaczone i nie mogą być przedstawiane jako wynik pełnozbiorowy.
- Generator powinien korzystać z lekkich zależności, zapisywać format odpowiedni do skali (CSV dla małych przykładów, Parquet dla dużych) oraz mieć automatyczny test kontraktu: schemat, liczebność, reprodukowalność i podstawowe własności statystyczne.

## Pełnozbiorowe analizy

- Analizy zlecane przez użytkownika mają domyślnie obejmować pełny, wskazany zakres danych.
- Aplikacja może oferować filtry, partycje i świadomie wybrany zakres, ale nie może arbitralnie uniemożliwiać pełnej analizy ani po cichu zastępować jej próbką.
- Próbkowanie jest dopuszczalne jedynie jako jawnie oznaczony tryb podglądu, renderowania lub eksploracji. Nie przedstawiaj wyniku z próbki jako wyniku pełnozbiorowego.
- Gdy dokładne obliczenie wymaga czasu, stosuj zadania asynchroniczne, raportowanie postępu, cache i wyniki inkrementalne zamiast automatycznego przechodzenia na próbkę.
- Zawsze komunikuj użytkownikowi zakres analizy, liczbę przetworzonych wierszy oraz ewentualne przybliżenia lub ograniczenia wyniku.

## Jakość architektury

- Stosuj dobre praktyki inżynierskie, zasady SOLID, modularną budowę, czytelne granice odpowiedzialności i testowalne kontrakty.
- Unikaj dublowania logiki między frontendem i backendem. Obliczenia analityczne wykonuj w warstwie przeznaczonej do pracy z danymi, a frontend traktuj jako warstwę konfiguracji i prezentacji.
- Dbaj o bezpieczeństwo zapytań, kontrolę zasobów, odporność na współbieżność, obserwowalność i możliwość skalowania horyzontalnego.

## Optymalizacja i dobór technologii

- Jeśli zauważysz uzasadnione pole do optymalizacji architektury, logiki lub technologii, możesz zaproponować i wdrożyć usprawnienie w zakresie bieżącego zadania, pod warunkiem zachowania kompatybilności i odpowiedniej weryfikacji.
- Dobieraj technologię do rzeczywistego profilu obciążenia. Rozważaj m.in. DuckDB, Parquet, silniki kolumnowe, obliczenia po stronie baz danych, query pushdown, Spark lub inne systemy rozproszone.
- Nie wprowadzaj Sparka ani innej ciężkiej infrastruktury wyłącznie ze względu na skalę deklarowaną w wymaganiach. Użyj jej wtedy, gdy pojedynczy węzeł, istniejący silnik zapytań lub pushdown nie zapewniają wymaganej przepustowości, pamięci, odporności albo czasu wykonania.
- Każdą większą zmianę technologiczną uzasadnij mierzalną potrzebą i uwzględnij koszt operacyjny, wdrożeniowy oraz utrzymaniowy.

## Ustalenia produktowe: Business Cases, Pipelines, ML Ops

Poniższe ustalenia są obowiązującym kierunkiem rozwoju platformy po rozmowie z użytkownikiem. Traktuj je jako pamięć projektową dla kolejnych zadań i innych chatów.

### Business Case

- `Business Case` jest kontekstem biznesowym i organizacyjnym, który spina artefakty, ale nie zastępuje datasetów, pipeline'ów, modeli, deploymentów ani monitoringów.
- `Business Case` jest obowiązkowy dla `ML`, `Serving` i `Monitoring`, a opcjonalny dla `Data` i `Analysis`.
- `Business Case` może istnieć bez datasetów; datasety i data views mogą być dopinane później.
- Minimalne pola BC: nazwa, opis, typ problemu ML, status, właściciel biznesowy, metryka główna, target column jeśli dotyczy, cel biznesowy, kryterium sukcesu, daty utworzenia i aktualizacji.
- Statusy BC:
  - `draft`: szkic, konfiguracja nie musi być kompletna.
  - `active`: przypadek jest realnie używany analitycznie lub eksperymentalnie.
  - `production`: przypadek ma aktywny produkcyjny deployment/champion używany do scoringu.
  - `archived`: przypadek historyczny, co do zasady tylko do odczytu.
- BC powinien mieć widok szczegółowy z zakładkami: `Overview`, `Data`, `Analysis`, `Pipelines`, `Experiments`, `Models`, `Scoring`, `Monitoring`.
- Nie dodawaj osobnego `primary_dataset_attachment`; znaczenie danych wynika z roli przypięcia datasetu/data view do BC.

### Datasety, data views i role w BC

- Jeden dataset lub data view może być podpięty do wielu BC. Relacja jest wiele-do-wielu.
- `DataView` powinien dawać takie same możliwości przypinania do BC jak fizyczny dataset.
- W ramach jednego przypięcia do BC dataset/data view ma jedną rolę.
- Role datasetów/data views w pierwszej wersji: `source`, `training`, `validation`, `test`, `scoring_input`, `scoring_output`, `monitoring_actuals`, `reference`.
- Przypięcie datasetu/data view do BC może mieć opcjonalny opis kontekstu, np. "dane scoringowe za Q1" albo "target dołączony po 60 dniach".
- Dataset poza BC może mieć target, ale nie jest to obowiązkowe. W BC target zależy od typu problemu: dla klasyfikacji/regresji jest istotny, dla klasteryzacji zwykle nie.
- Klucz główny/row ID wymagaj dopiero w realnym przypadku użycia, szczególnie dla scoringu i późniejszego dołączania targetu. Nie blokuj prostego uploadu i profilowania danych brakiem MLOps-metadanych.

### Analysis

- W `Analysis` wybór BC powinien filtrować dostępne datasety/data views i ustawiać domyślny kontekst analizy, np. target, typ problemu i sugerowane metryki.
- Użytkownik musi móc zmienić domyślne ustawienia analizy wynikające z BC.
- Wyniki/raporty analizy zapisuj do BC tylko po jawnej akcji użytkownika.
- Analiza zawsze powinna komunikować zakres danych, liczbę przetworzonych wierszy oraz ewentualne przybliżenia lub ograniczenia.

### Pipelines

- `Pipelines` to osobna sekcja w głównym menu oraz zakładka w szczegółach BC.
- Globalny widok `Pipelines` pokazuje pipeline'y dostępne użytkownikowi i ich mapowania na BC.
- Widok `Pipelines` w ramach BC pokazuje tylko pipeline'y tego BC i ich role/kontekst w danym BC.
- Pipeline zawsze ma właścicielski BC. Globalne, luźne pipeline'y bez BC nie powinny powstawać.
- Użytkownik może rozpocząć tworzenie pipeline'u z globalnej sekcji, ale pierwszy krok musi wymusić wybór BC.
- Docelowo pipeline powinien dać się sklonować lub ponownie użyć w innym BC, ale nie wprowadzaj globalnych pipeline'ów na starcie.
- Typy pipeline'ów w pierwszej wersji: `data_preparation`, `feature_engineering`, `training`, `batch_scoring`, `monitoring`, `custom`.
- Pipeline ma status i historię wersji. Statusy pipeline'u: `draft`, `published`, `deprecated`, `abandoned`, `archived`.
- `deprecated` oznacza zastąpiony, ale historycznie używany pipeline. `abandoned` oznacza rozpoczęty i porzucony/nieukończony pipeline. `archived` oznacza zamknięty artefakt historyczny.
- Ról `champion`, `shadow`, `challenger` nie przypisuj do pipeline'u jako takiego. Te role dotyczą modelu/deploymentu albo zestawu: model version + pipeline version + kanały servingowe.

### Data Engineering i ETL

- Nie tworz osobnego bytu `ETL Job` konkurujacego z `Pipeline`. Data Engineering jest rodzina wykonywalnych pipeline'ow i korzysta z tego samego wersjonowania, runow, audytu, artifact registry oraz lineage.
- Pipeline'y typu `data_preparation` i `feature_engineering` sa pierwszym zakresem DE. W przyszlosci katalog moze zostac rozszerzony o wyspecjalizowane typy `ingestion` i `data_quality`, bez tworzenia drugiego silnika orkiestracji.
- Aktualnie wspierane plikowe wejścia pipeline'ów to datasety CSV i Parquet już załadowane do platformy oraz materializowane Data Views. Kolejne źródła dodawaj przez adaptery.
- Projektuj warstwe danych przez adaptery zrodel i materializacji. Architektura nie moze zakladac, ze wszystkie przyszle assety sa plikami; musi pozwolic pozniej dodac Parquet, tabele bazodanowe, object storage i query pushdown bez zmiany kontraktu definicji pipeline'u.
- CSV jest poczatkowym formatem wejscia, a Parquet preferowanym formatem materializowanego outputu. PostgreSQL i inne bazy maja byc pozniej obslugiwane przez adaptery i pushdown, a nie przez kopiowanie calych tabel do procesu aplikacji.
- Pierwszy execution engine powinien wykorzystywac DuckDB do kolumnowych transformacji plikow oraz zapisu Parquet. Ukryj silnik za kontraktem wykonawczym, aby w przyszlosci mozna bylo dodac wykonanie bazodanowe lub rozproszone bez zmiany API pipeline'ow.
- Runy DE projektuj jako asynchroniczne i odporne na duze dane. Nie laduj calego CSV do pamieci backendu ani przegladarki; wykorzystuj skanowanie kolumnowe, projekcje, predicate pushdown, streaming i materializacje po stronie silnika.
- Definicja DE pozostaje DAG-iem z wezlami/rolami `source`, `transform`, `quality_check` i `sink`. Pierwszy edytor UI moze prezentowac uporzadkowana liste krokow, ale backend musi obslugiwac wiele wejsc, joiny, rozgalezienia i wiele wyjsc.
- Kazdy wezel i port wejscia/wyjscia musi miec stabilny identyfikator. Definicja musi jawnie opisywac zaleznosci miedzy krokami, a nie polegac jedynie na kolejnosci elementow tablicy.
- Pierwszy realny katalog operacji DE powinien obejmowac: wybor kolumn, zmiane nazw i typow, filtrowanie, sortowanie, deduplikacje, obsluge brakow, wyliczanie kolumn, agregacje, operacje okienkowe, join, union, mapowanie kategorii oraz kontrole schematu i jakosci.
- Architektura od poczatku ma uwzgledniac transformacje szeregow czasowych, takie jak lag, rolling window i resampling, ale ich wykonanie nalezy do drugiej paczki operacji.
- Uzytkownik powinien miec dwa sposoby definiowania transformacji: standardowe, walidowane klocki oraz zaawansowany krok z wlasnym kodem.
- W pierwszej wersji `user written code` oznacza kontrolowany krok SQL. Nie uruchamiaj dowolnego kodu Python na tym etapie.
- Custom SQL musi miec ograniczenia bezpieczenstwa i zasobow, jasno okreslone wejscia/wyjscia oraz oznaczenie, ze automatyczny column lineage moze byc niepelny. Nie pozwalaj mu obchodzic kontroli dostepu do assetow.
- Edytor powinien oferowac formularz/liste krokow oraz zaawansowany widok JSON tej samej definicji. Oba widoki musza korzystac z jednego kontraktu backendowego i zachowywac stabilne `step_id`.
- Pipeline DE moze miec wiele wejsc od pierwszej wersji, w tym join wielu datasetow. Nie upraszczaj modelu wykonawczego do jednego inputu.
- Output jest wybierany jawnie przez uzytkownika. Dozwolone tryby materializacji powinny obejmowac co najmniej `dataset`, `data_view` oraz `temporary`; domyslnym trwalym wynikiem jest nowy dataset Parquet.
- Sposob zapisu wyniku powinien poczatkowo obslugiwac `replace`. Kontrakty przygotuj pod `append`, `incremental` i `merge/upsert`, ale nie implementuj ich bez ustalenia kluczy, watermarkow, idempotencji i obslugi spoznionych danych.
- Kazdy trwaly output jest nowym artefaktem z lineage. Test/dry-run moze utworzyc tylko output tymczasowy i nie moze udawac oficjalnego datasetu.
- Wejscia i wyjscia powinny wspierac data contracts: wymagane kolumny, typy, nullable, unikalnosc, zakresy lub dozwolone wartosci oraz opcjonalne primary key i event timestamp.
- Polityka blednych rekordow jest konfigurowalna per walidacja lub output: `fail`, `warn`, `reject`; domyslnie `fail`. Tryb `reject` tworzy osobny output rejected records z identyfikatorem rekordu i powodem odrzucenia.
- Lineage powinien obejmowac artefakty i, dla standardowych operacji, pochodzenie kolumn: kopiowanie, rename, derive, join i agregacje. Nie obiecuj pelnego column lineage dla dowolnego SQL.
- Harmonogramy nie naleza do pierwszej dzialajacej wersji DE. Najpierw zapewnij poprawne reczne runy, powtarzalnosc, liczniki, logi, walidacje i artefakty wynikowe; kontrakt `trigger_type` nadal zachowuje przyszle `api` i `schedule`.
- Zapisany pipeline feature engineering nie jest jeszcze feature store'em. Na tym etapie buduj wersjonowane feature pipelines i feature datasets.
- Feature store wymaga osobnego przyszlego zakresu: encji, event time, point-in-time correctness, offline/online store, definicji cech oraz spojnosci training-serving.
- Transformacje uczone na danych, np. imputacja, encoding, scaling i PCA, zapisują fitted state jako wersjonowany `feature_transform` artifact i są fitowane tylko na danych treningowych. Rozszerzając katalog zachowuj ten kontrakt; nie dopuszczaj refitu na validation, test ani scoring input.
- Nie dodawaj osobnej glownej sekcji `Data Engineering` na pierwszym etapie. Rozwijaj globalna sekcje `Pipelines` o widoki definicji i runow, a pozniej harmonogramow i connectorow. Typ/szablon pipeline'u steruje katalogiem operacji i walidacjami UI.

### Historyczna kolejność wdrażania Data Engineering

Poniższe etapy opisują pierwotny plan. Etapy 1-3 oraz część etapu 4 zostały już w dużej mierze wdrożone; przed wyborem kolejnego zakresu sprawdzaj bieżący kod, testy i sekcje „Aktualny status”.

- Etap 1: formalny kontrakt DAG i walidacja definicji, adapter wejscia CSV, execution engine DuckDB, podstawowe operacje, wiele wejsc i join, reczny run oraz tymczasowy test run.
- Etap 2: materializacja Parquet/DataView, artifact i lineage, data contracts, polityki `fail/warn/reject`, rejected records, liczniki i diagnostyka runu.
- Etap 3: wygodny edytor krokow zsynchronizowany z JSON, custom SQL z ograniczeniami, podglad schematu i planu wykonania.
- Etap 4: operacje szeregow czasowych, fitted transformations dla FE oraz ponowne wykorzystanie opublikowanej wersji w treningu i scoringu.
- Etap 5: adaptery baz danych i pushdown, zapisy `append`/`incremental`/`merge`, harmonogramy i connector management. Dodawaj je dopiero wraz z konkretnymi wymaganiami dotyczacymi kluczy, watermarkow, sekretow i idempotencji.
- Wykonywalny, wersjonowany przepływ DE istnieje, a realne FE, Training, AutoML, Test Scoring i Monitoring zostały już nad nim zbudowane. Nie cofaj projektu do etapu szkieletu; dalszy rozwój zachowuje te kontrakty.

### PipelineVersion

- Rozdzielaj `Pipeline` i `PipelineVersion` od początku.
- `Pipeline` to kontener: nazwa, opis, BC, typ, status, właściciel/creator, daty.
- `PipelineVersion` to konkretna definicja: wejścia, kroki, wyjścia, parametry, numer wersji, status, hash definicji i audyt.
- Numeracja wersji ma być prosta: `1`, `2`, `3`, a w UI można prezentować ją jako `v1`, `v2`, `v3`.
- W ramach jednego pipeline'u na start dopuszczaj tylko jedną wersję `draft`.
- Wersję `draft` można edytować.
- Wersja `published` jest niemutowalna. Zmiana opublikowanej wersji tworzy nową wersję.
- Po utworzeniu pipeline'u UX powinien od razu utworzyć pierwszą roboczą wersję draft, nawet jeśli technicznie pipeline bez opublikowanej wersji jest dopuszczalny.
- `PipelineVersion` musi mieć `definition_hash`, aby wspierać powtarzalność, audyt i wykrywanie realnych zmian definicji.
- Definicję pipeline'u przechowuj jako formalny JSON przetwarzalny przez API i UI, np. `inputs`, `steps`, `outputs`, `parameters`.
- Backendowo projektuj definicję jako DAG, ale pierwsze UI może pokazywać uporządkowaną listę kroków. Nie zamykaj architektury na joiny, rozgałęzienia, wiele wejść i wiele wyjść.
- Każdy step musi mieć stabilny `step_id` niezależny od nazwy.
- Startowy katalog typów kroków: `select_columns`, `filter_rows`, `join`, `derive_column`, `impute_missing`, `encode_categorical`, `scale_numeric`, `train_model`, `score_model`, `evaluate_model`, `quality_check`, `custom`.
- Docelowo pipeline'y muszą być zarządzalne zarówno przez API/JSON, jak i przez UI w przeglądarce.

### PipelineRun

- `PipelineRun` jest osobnym bytem od początku.
- Każdy run musi wskazywać konkretną `PipelineVersion`, nigdy tylko `Pipeline`.
- Run może mieć parametry runtime nadpisujące domyślne parametry wersji, ale nadpisania muszą być zapisane dla audytu i powtarzalności.
- Statusy runu: `queued`, `running`, `succeeded`, `failed`, `cancelled`.
- `trigger_type` runu: `manual`, `api`, `schedule`. Na start może działać tylko `manual`, ale kontrakt powinien przewidywać pozostałe.
- Run powinien mieć liczniki: `input_row_count`, `processed_row_count`, `output_row_count`, `rejected_row_count`.
- Run powinien zapisywać ostrzeżenia walidacyjne, nie tylko binarny status sukces/porażka.
- Draft pipeline może mieć testowy/dry-run bez oficjalnego artefaktu wynikowego. Taki run musi być wyraźnie oznaczony i audytowalny.
- Opublikowany pipeline może być uruchamiany ręcznie z UI. Ograniczenia uprawnień zostaną rozważone dopiero przy późniejszym modelu RBAC/admin.
- Równoległe runy są dozwolone. Frontend musi izolować stan submit/polling/result per run albo per sesja modala; poller runu działającego w tle nie może przejąć nowo otwartego formularza ani blokować uruchomienia innego pipeline'u. Faktyczna równoległość jest ograniczana konfiguracją workera, a nadmiarowe runy pozostają w kolejce.

### Artifact i lineage

- Wprowadź lekką techniczną warstwę `Artifact` jako wspólny rejestr artefaktów dla lineage. Nie eksponuj jej użytkownikowi jako osobnego pojęcia w UI.
- Użytkownik widzi datasety, data views, modele, raporty, deploymenty, pipeline runs itd., a nie "artifact registry".
- `Artifact` powinien mieć co najmniej: `id`, `type`, `reference_id`, `business_case_id` jeśli dotyczy, `origin`, `created_by`, `created_at`.
- Typy artefaktów powinny obsługiwać co najmniej: `dataset`, `data_view`, `model_version`, `report`, `metrics`, `deployment`, `prediction_dataset`.
- `origin` jest obowiązkowy. Dozwolone wartości na start: `platform_generated`, `uploaded`, `external_registered`.
- Dla `external_registered` wymagaj jawnego opisu źródła/notatki, np. `external_notes` lub `source_description`. Zewnętrzne blackboxy muszą zostawiać czytelny ślad audytowy.
- Każdy artefakt tworzony przez platformę musi mieć lineage bez wyjątków.
- Minimalny lineage: input artifact IDs, pipeline version ID, run ID, timestamp, row count, output schema, creator.
- Artefakty stworzone poza BC mogą później zostać przypięte do BC, ale musi być pełna audytowalność i jawne oznaczenie zewnętrznego pochodzenia.

### Modele, deployment i serving

- Model należy do Business Case.
- Eksperymenty ML są osobnym bytem między BC a modelem: `Business Case -> Experiment -> Model Version`.
- Registry modeli obsługuje realne, niemutowalne model artifacts tworzone przez pipeline Training/AutoML, wersje logicznych rodzin, metryki i lineage. Legacy standalone training pozostaje prototypem metadata-only i nie jest właściwą ścieżką treningu.
- Statusy modelu: `candidate`, `validated`, `rejected`, `promoted`, `archived`.
- Statusy deploymentu: `draft`, `active`, `shadow`, `paused`, `retired`.
- Dla jednego BC dopuszczaj tylko jeden champion/produkcyjny deployment i tylko jeden shadow deployment, ale dowolną liczbę challengerów/kandydatów.
- Produkcyjny deployment powinien reprezentować decyzję operacyjną: model version + pipeline version + kanały servingowe.
- Serving ma docelowo obsługiwać zarówno scoring punktowy online, jak i batch scoring.
- Na start online scoring może być placeholderem. Realny endpoint wprowadzaj dopiero po ustaleniu schematu wejścia, walidacji, artefaktów modelu i spójności FE między treningiem a inferencją.
- Batch scoring powinien tworzyć dataset wynikowy/prediction dataset jako artefakt z lineage.
- Scoring output musi zawierać referencję do input row ID/klucza głównego, aby umożliwić późniejsze dołączenie targetu i monitoring skuteczności.

### Monitoring

- Monitoring powinien być najpierw zakładką w BC, a później także globalną sekcją dla administratora/operatora.
- Rozdzielaj monitoring jakości danych wejściowych od monitoringu wyjść i skuteczności modelu.
- Monitoring jakości danych wejściowych powinien docelowo działać automatycznie dla każdego scoring runu.
- Monitoring skuteczności modelu/performance wymaga targetu i może działać dopiero po dostarczeniu danych z rzeczywistymi etykietami/wartościami.
- Platforma powinna automatycznie dobierać metryki do typu problemu ML, początkowo jako placeholder/reguła UI.

### Scoring Reports

- `Scoring Report` jest widocznym dla uzytkownika, wersjonowanym obiektem nalezacym do Business Case.
- Jedna logiczna rodzina raportow odpowiada parze pipeline + krok scoringowy. Kazdy udany pelny run tworzy nowa, niemutowalna wersje.
- Wersja raportu jest technicznie artefaktem typu `report` i przechowuje ograniczone agregaty, metryki i dane do wykresow oraz lineage do modelu, prediction datasetu, wersji pipeline'u i runu. Nie kopiuje danych wierszowych.
- Dry-run nie rejestruje raportu, modelu ani datasetu. Udostepnia tylko tymczasowy podglad tych obiektow.
- Kontrakt raportu musi pozostac przydatny jako baseline dla przyszlego monitoringu. Porownania produkcyjne powinny bazowac na wersjach raportow, a nie na logice metryk odtworzonej w frontendzie.
- Nazwa prediction datasetu i nazwa Scoring Report sa niezaleznymi polami konfiguracji kroku scoringowego. Zmiana nazwy raportu nie zmienia logicznej rodziny raportow, ktora nadal wynika z pipeline + stabilnego step_id.

### Batch scoring a monitoring skutecznosci

- Batch scoring i monitoring skutecznosci sa dwoma odrebnymi pipeline'ami.
- Pipeline `batch_scoring` przyjmuje jawnie wybrana wersje datasetu bez targetu, stosuje inference-safe DE, przypiety fitted state FE i konkretna wersje modelu, a wynikiem jest niemutowalny prediction dataset. Nie tworzy metryk skutecznosci ani Scoring Report.
- Prediction dataset zachowuje stabilny identyfikator rekordu i lineage do input datasetu, fitted transform, model version, pipeline version oraz runu.
- Pozniejszy pipeline `monitoring` przyjmuje prediction dataset i actuals, wykonuje jawny join targetow oraz dopiero wtedy wylicza metryki i tworzy raport skutecznosci.
- Nie modyfikuj prediction datasetu po nadejsciu targetow; target joining tworzy nowy wersjonowany artefakt.
- DE w automatycznie tworzonym pipeline batch scoringowym zawiera tylko deterministyczne, inference-safe przygotowanie wymagane przez kontrakt modelu. Nie przenos training-only splitow, operacji zaleznych od targetu ani transformacji fitowanych na biezacym batchu.
- Tworzenie pipeline'u rozroznia `purpose` (metadane/kontekst) od `template` (poczatkowy edytowalny szkielet). UI sugeruje template na podstawie purpose, ale zapisuje wybrany template w parametrach definicji.
- Dostępne szablony obejmują `training`, `automl`, `batch_scoring`, `custom` i `monitoring`. Monitoring ma wykonywalne kroki jawnego Process & Join/Target Join oraz KPI report; nie przedstawiaj go jako samego placeholdera. Batch scoring i monitoring skuteczności pozostają odrębnymi pipeline'ami.
- Batch scoring konfiguruj akcja `Infer from training pipeline`. Sam pipeline i numer jego wersji nie identyfikuja artefaktow, bo wersja moze miec wiele runow. Uzytkownik wybiera pipeline, opublikowana PipelineVersion i konkretny Model Version/run.
- Inferowany draft przypina konkretny model artifact oraz fitted transform artifact z tego samego runu, kopiuje recepture FE w trybie transform i tylko inference-safe kroki DE. Pominiete kroki training-only komunikuj jawnie; nie wybieraj po cichu `latest`.
- Runtime selection wersji modelu w batch scoringu rozwiązuje atomowy inference bundle: konkretny model artifact, dokładną recepturę FE i fitted transform artifact z tego samego runu treningowego. Backend zapisuje cały bundle w parametrach runu, nadpisuje nim zarówno krok FE, jak i scoring oraz odrzuca run przed wykonaniem, jeśli fitted state nie istnieje albo kontrakt cech nie zgadza się z modelem. Nie dodawaj niezależnego wyboru fitted transform, który pozwalałby tworzyć niespójne pary.
- W pipeline batch scoringowym nie wymagaj recznego wklejania identyfikatora fitted state ani nie pokazuj krokow Training/Test Scoring jako sugerowanych operacji.

### Dynamiczne cechy i portowe lineage

- Training domyslnie konsumuje upstream Feature Manifest zamiast statycznej listy nazw. Jest to wymagane dla one-hot encodingu, PCA i innych transformacji, ktorych finalny schemat zalezy od fitted state.
- Model zawsze zapisuje rozwiazana w runtime, konkretna liste cech uzyta przez estimator. Reczny, jawny wybor kolumn pozostaje opcjonalnym trybem.
- Lineage pomiedzy krokami musi byc przypisane do konkretnej pary step_id + port_id. Nie wolno laczyc wszystkich artefaktow kroku jako inputu kazdego downstream portu.
- Widoki governance modeli i raportow powinny korzystac z backendowego resolvera grafu artefaktow, zwracajacego nazwy, wersje, role i identyfikatory datasetow. Frontend nie rekonstruuje lineage samodzielnie.

### Uprawnienia i audyt

- Na obecnym etapie ignoruj pełny model uprawnień. Stosuj placeholdery `owner`, `created_by`, `updated_by`.
- W przyszłości aplikacja ma mieć model uprawnień, udostępnianie obiektów oraz globalnego admina/kontrolera.
- Właściciel BC jest domyślnym właścicielem pipeline'ów w BC, ale właściciel biznesowy nie zawsze jest twórcą lub modyfikującym. Audyt `created_by` i `updated_by` jest obowiązkowy.

### Historyczny pierwszy zakres implementacyjny

Ten zakres został przekroczony i pozostaje wyłącznie kontekstem decyzji architektonicznych.

- Szkielet `Business Cases` + `Pipelines`, endpointy API i frontend są wdrożone.
- Realny trening, AutoML, Test Scoring, model/metrics artifacts i monitoring są wdrożone jako kroki pipeline'u. Rozwijaj je przyrostowo na istniejącym `PipelineVersion`, `PipelineRun`, `PipelineStepRun`, Artifact i lineage.
- Nie dodawaj mockowanych danych demonstracyjnych tylko po to, aby zapełnić UI. Aplikacja ma już przygotowane datasety pokrywające standardowe przypadki ML i to na nich użytkownik będzie testował kolejne etapy.

### Aktualne ustalenia: pipeline wysokopoziomowy i kroki

- `Pipeline` jest elastycznym, wysokopoziomowym workflow DAG należącym do Business Case, a nie pojedynczym jobem DE, FE, treningowym albo scoringowym.
- Jeden Business Case może i zwykle powinien mieć wiele niezależnych pipeline'ów, np. `train & operate`, `train challenger`, `production scoring`, `actuals joining` i `monitoring`.
- Pipeline nie musi zawierać określonego zestawu kroków. Rodzaj/purpose pipeline'u jest szablonem i metadanymi, a nie ograniczeniem katalogu dozwolonych kroków.
- Rozróżniaj dwa poziomy definicji:
  - wysokopoziomowy `PipelineStep`, np. Data Engineering, Feature Engineering, Training, Approval Gate, Deployment, Scoring, Target Joining albo Monitoring;
  - wewnętrzny klocek operacyjny danego kroku, np. `select_columns`, `filter_rows`, `join` lub `custom_sql` wewnątrz kroku Data Engineering.
- Backendowa definicja pipeline'u pozostaje DAG-iem ze stabilnymi identyfikatorami kroków i portów, nawet jeśli pierwsze UI prezentuje prostą sekwencję.
- Pipeline'y wymieniają dane przez wersjonowane artefakty, datasety, modele i deploymenty. Nie twórz bezpośrednich zależności wykonawczych między odrębnymi pipeline'ami.
- Użytkownik może uruchomić cały pipeline oraz krok wraz z wymaganymi przodkami; każdy wykonany krok ma `PipelineStepRun`. Dalsze tryby uruchamiania pojedynczego kroku muszą jawnie wskazywać inputy lub artefakty z konkretnego runu; nie wybieraj po cichu „najnowszego” wyniku.
- Operationalization/deployment ma być poprzedzony osobnym ręcznym `Approval Gate`. PipelineRun oczekujący na decyzję nie jest zakończony ani failed; docelowo ma status oczekiwania i po zatwierdzeniu wznawia ten sam run.
- Każdy wykonywany krok workflow ma osobny `PipelineStepRun`, status, czasy, liczniki, warnings, output manifest i izolowany błąd; zachowuj i rozwijaj ten kontrakt.
- Wykonywalne kroki wysokopoziomowe obejmują obecnie Data Engineering, Feature Engineering, Training, AutoML, Test/Batch Scoring i Monitoring. Dodając kolejne typy nie pokazuj funkcji bez działającego backendu jako gotowych.
- Edytor DE jest zagnieżdżoną konfiguracją kroku Data Engineering. Wewnątrz obsługuje źródła danych, standardowe klocki transformacji oraz kontrolowany `User Written SQL`; nie eksponuj operacji DE jako kroków wysokopoziomowego lifecycle.
- Dry-run kroku DE tworzy wyłącznie tymczasowy Parquet i jawnie ograniczony preview. Zwykły run opublikowanej wersji tworzy trwały dataset Parquet, Artifact, minimalny lineage i przypięcie do Business Case.
- Pierwsze UI ma rozdzielać listę/tworzenie pipeline'ów od edytora wybranego pipeline'u. Edytor pokazuje DAG kroków wysokopoziomowych, a konfiguracja wybranego kroku otwiera właściwy edytor domenowy.

### Ustalenia architektoniczne: AutoML i AutoFE

- Bieżący zakres AutoML + AutoFE obejmuje klasyfikację binarną, klasyfikację wieloklasową i regresję dla danych tabelarycznych. Klasteryzację i szeregi czasowe pomijamy do osobnych przyszłych etapów.
- AutoML ma docelowo optymalizować spójną ścieżkę Feature Engineering -> selekcja cech -> model -> walidacja, a nie wyłącznie rodzinę estymatora i hiperparametry.
- Zachowuj osobne, audytowalne artefakty receptury FE, fitted transform, Feature Manifest, modelu i metryk. Automatyzacja nie może ukrywać finalnej konfiguracji potrzebnej do odtworzenia scoringu.
- Historyczny pierwszy etap wybierał jedną deterministyczną recepturę. Obecna implementacja wykonuje model-aware joint search maksymalnie trzech profili receptur; dalszy plan rozszerzenia przestrzeni opisuje sekcja poniżej.
- AutoFE fituje stan wyłącznie na partycji treningowej i stosuje go bez ponownego fitowania do validation/test/scoring.
- Cross-validation całej ścieżki jest dozwolone wyłącznie przez wdrożony executor fold-local: receptura FE jest fitowana osobno na train każdego foldu. Zintegrowany AutoFE nadal odrzuca CV dla wejścia zawierającego stan FE fitowany globalnie; human-made FE pozostaje wspierane z holdoutem albo poza zintegrowanym fold-local AutoFE.
- Planner AutoFE może używać ograniczonych przybliżeń do decyzji planistycznych, np. approximate distinct count, ale musi zapisać rodzaj przybliżenia, pełny zakres profilowania i liczbę przetworzonych wierszy.
- Pipeline z purpose/template `automl` powinien umożliwiać akcję `Infer Data Engineering`: użytkownik jawnie wybiera pipeline typu `training` z tego samego Business Case i konkretną jego wersję, a aplikacja kopiuje definicję kroku DE do edytowalnego draftu AutoML. Jest to kopia w czasie projektowania, nie zależność wykonawcza między pipeline'ami; zachowuj stabilne step ID i połączenia pipeline'u docelowego oraz zapisuj identyfikatory, numer wersji i hash źródła dla audytu.
- Edytor `custom` pokazuje pełny katalog aktualnie wykonywalnych kroków wysokopoziomowych: Data Engineering, Feature Engineering, Training, AutoML, Test Scoring i Monitoring. Training i AutoML są alternatywami w jednym workflow.
- Zielone wyróżnienie akcji w edytorze pipeline'u oznacza następny zalecany krok wynikający z aktualnego DAG-u, a nie stały typ kroku. Standardowa rekomendacja to `DE -> FE -> Training albo AutoML -> Test Scoring -> Monitoring`; dla pustego workflow rekomendowane jest DE.
- Monitoring może bezpośrednio następować po Test Scoring w tym samym lifecycle pipeline, ponieważ testowy prediction dataset zawiera target. Produkcyjny monitoring po późniejszym dostarczeniu actuals nadal pozostaje osobnym pipeline'em z jawnym Target Join/Process & Join.
- Model-aware AutoFE grupuje algorytmy według jawnych capability profiles i wspólnie porównuje pary `receptura FE + algorytm/hiperparametry` na tym samym leakage-safe holdoucie albo wspólnym planie surowych foldów. Profile co najmniej rozróżniają modele wymagające skalowania, rodziny drzewiaste bez skalowania oraz estymatory wymagające cech nieujemnych.
- Wszystkie kandydackie receptury w jednym joint study muszą korzystać z jednego pełnozbiorowego profilu danych i wspólnego, podzielonego budżetu triali/czasu. Kandydackie macierze i modele są tymczasowe; po wyborze zwycięzcy wykonuj finalny refit i utrwalaj tylko zwycięski fitted transform, Feature Manifest, model oraz pełne provenance porównania.

### Aktualny status i plan rozwoju AutoML / AutoFE (lipiec 2026)

Ta sekcja jest nadrzędną pamięcią projektową dla kolejnych prac nad AutoML. Starsze punkty opisujące „pierwszy etap” są historią rozwoju, a nie bieżącym stanem.

#### Bieżący stan

- AutoML jest działającym, zarządzanym MVP dla tabelarycznej klasyfikacji binarnej, wieloklasowej i regresji, ale nie jest jeszcze kompleksowym autonomicznym AutoFE/AutoML.
- Backendowy katalog zawiera około 52 wykonywalne algorytmy, zależnie od dostępności opcjonalnych bibliotek. AutoML przeszukuje rodziny estymatorów i ich warunkowe hiperparametry z limitami triali, czasu, pamięci i równoległości.
- AutoFE profiluje pełny zadeklarowany zakres w DuckDB bez cichego samplingu. `approx_count_distinct` służy tylko decyzjom planistycznym, a przybliżenie i liczba wierszy są zapisywane.
- Obecne transformacje obejmują medianową imputację liczb, opcjonalne wskaźniki braków, skalowanie, bounded one-hot, frequency encoding, proste cechy kalendarzowe oraz odrzucanie prawdopodobnych identyfikatorów i niewspieranych typów.
- Joint search porównuje bazowe profile `scaled_dense`, `tree_unscaled`, `non_negative` oraz warunkową przestrzeń numeryczną v2 dla nowych draftów: baseline, samą winsoryzację, same signed-log1p features i wariant łączony. Dla `scaled_dense` niezależnie porównuje standard, robust, min-max i brak skalowania; profile drzewiaste nie generują redundantnych skalowań, a `non_negative` odrzuca signed-log. Constant/low-variance selection działa dla receptur generowanych. Optymalizowana jest pełna ścieżka `receptura FE + selektor + model/hiperparametry` na leakage-safe holdoucie albo fold-local CV.
- Stan FE jest fitowany tylko na train i stosowany bez refitu do validation/test. Zwycięzca jest refitowany; utrwalane są receptura, fitted transform, Feature Manifest, model, metryki i provenance.
- Zintegrowany AutoFE obsługuje jawne fold-local CV dla tabelarycznej klasyfikacji i regresji: surowe foldy są deterministyczne, a pełna receptura wraz z winsoryzacją i selektorem wariancji jest fitowana osobno na train każdego foldu. Wynik zapisuje fold scores, pełnozakresowe bounded OOF summary, liczebności, seed, etap przypisania, wersjonowany `recipe_contract`, `recipe_hash` i fitted-state signatures. Run-scoped cache materializuje FE tylko raz per `recipe + raw fold + seed + input scope`, a kolejne triale ponownie używają fold Parquetów. Brakuje persisted row-level OOF predictions, group/time CV dla AutoFE, supervised feature selection, target encodingu, szerszego feature generation, learned interactions, kategorii natywnych, ensemble/stackingu i wielokryterialnego wyboru championa.
- `max_trials` w joint AutoFE jest globalnym limitem dla wszystkich faz, nie gwarantowaną liczbą ukończonych prób. Nowe drafty używają dwufazowego schedulera: każda wykonywalna receptura otrzymuje mały gwarantowany budżet eksploracji, a deterministycznie wybrane top-K dzieli pozostałe triale i czas w pogłębieniu. Starsze definicje bez flagi zachowują płaski podział. Timeout może zakończyć fazę wcześniej i zachować najlepszą udaną próbę; nieudane pogłębienie zachowuje wynik eksploracji. Koszt CV szacuj jako `ukończone triale × liczba foldów` fitów modeli plus przygotowanie FE i finalny refit; UI ma komunikować limity, przydział i wykorzystanie per faza oraz faktycznie ukończone triale.
- Kolumny techniczne platformy z prefiksem `__mlapp_`, w szczególności `__mlapp_cv_fold`, nigdy nie są kandydatami na cechy ani wejściami transformacji AutoFE. Przestrzeń AutoML może losować tylko kompletne, wykonywalne kombinacje parametrów; wariant HGBR `loss=quantile` pozostaje ręczny, dopóki search-space nie modeluje warunkowego parametru `quantile`.
- Klasteryzacja, szeregi czasowe i zaawansowane przetwarzanie tekstu pozostają poza obecnym zakresem.

#### Ograniczenie technologiczne

- Pozostajemy przy obecnym stosie: Python/backend aplikacji, DuckDB, Parquet, obecny worker/kolejka, istniejące biblioteki ML i React frontend.
- Nie wprowadzaj Sparka, Ray, Dask, zewnętrznej platformy AutoML ani nowego orkiestratora bez osobnej decyzji użytkownika popartej pomiarami.
- DuckDB pozostaje silnikiem profilowania, relacyjnych transformacji i materializacji. Transformacje uczone oraz trening pozostają za obecnymi kontraktami executorów, z kontrolą pamięci, strumieniowaniem gdzie możliwe i run-scoped Parquet.

#### Docelowy kontrakt AutoFE Experiment Engine

- Jednostką eksperymentu jest cała ścieżka `receptura FE -> feature selection -> estimator -> hiperparametry -> walidacja`, nie sam estymator.
- Przestrzeń poszukiwań jest formalna, wersjonowana, audytowalna, deterministyczna dla seeda oraz warunkowa względem schematu i capabilities modelu.
- Każda próba zapisuje: recipe ID/hash i definicję, selektor, model i parametry, foldy/seed, zakres i liczbę wierszy, score per fold i OOF, czas/zasoby, liczbę cech, warnings, failure/pruning reason i lineage.
- Kandydackie macierze, fold-local state i modele są tymczasowe. Utrwalaj zwycięską recepturę, finalny fitted state, Feature Manifest, model oraz ograniczone provenance badania bez kopiowania danych wierszowych.
- Każdą transformację zależną od danych lub targetu fituj wewnątrz foldu. Globalny fit przed CV jest zabroniony dla imputacji uczonej, skalowania, encodingu, selekcji, redukcji wymiaru i agregatów.
- Test pozostaje nietknięty podczas optymalizacji. Finalny refit zwycięskiej ścieżki wykonuj na pełnym dozwolonym train scope.

#### Kolejność wdrażania

1. **Etap A — fold-local FE i CV foundation**
   - Status: zakończony dla bieżącego zakresu tabelarycznej klasyfikacji i regresji. Działają deterministyczne stratified K-fold dla klasyfikacji i K-fold dla regresji, fold-local fit/transform każdej receptury, wspólne foldy kandydatów, fold scores, bounded full-scope OOF summary per trial, bezpieczny run-scoped fold cache, finalny refit oraz ochrona przed globalnie fitowanym human-made FE.
   - Klucz cache obejmuje recipe hash, surowe relacje train/validation foldu, fold ID i seed. Cache jest wyłącznie run-scoped i usuwany wraz z tymczasowymi kandydatami.
   - Test negatywny potwierdza, że zmiana wartości wyłącznie w validation fold nie zmienia fitted-state hash tego foldu, podczas gdy zmienia stany foldów, w których te wiersze należą do train.
   - Row-level OOF predictions dla wszystkich przegranych triali nie są utrwalane, aby nie mnożyć dużych artefaktów; provenance jawnie zapisuje `predictions_persisted: false`. Ewentualne utrwalenie OOF zwycięzcy wymaga osobnego kontraktu artefaktu i polityki retencji. Group/time fold-local AutoFE jest osobnym rozszerzeniem po podstawie.

2. **Etap B — formalna przestrzeń receptur i orkiestracja**
   - Status: częściowo wdrożony. Receptury mają wersjonowany kontrakt `2.0`, deterministyczny `recipe_hash`, warunkową przestrzeń wariantów numerycznych i skalowania oraz jawny selektor. Działa dwufazowy scheduler exploration/deepening ze wspólnym globalnym budżetem, deterministyczną promocją top-K, nowym seedem pogłębienia, fallbackiem po jego błędzie oraz statusami `promoted`, `pruned`, `explored`, `failed`, `skipped`. Leaderboard zapisuje pełną ścieżkę, fazy, budżety i liczbę receptur wygenerowanych/skonfigurowanych/wykonanych. Nadal należy rozdzielić profiler, generator, evaluator, scheduler i champion selector na osobne komponenty oraz dodać statystyczny pruning wewnątrz fazy.
   - Rozdzielić profiler/planner, generator kandydatów, evaluator, scheduler budżetu i champion selector za testowalnymi kontraktami.
   - Wprowadzić warunkową przestrzeń receptur i stabilny `recipe_hash`; generować różnorodne kandydatury zamiast tylko profili skalowania.
   - Budżet dzielić na eksplorację rodzin FE i pogłębianie najlepszych; używać Optuna/pruningu z zachowaniem audytu.
   - Kandydatów pominiętych przez budżet/capabilities oznaczać jako skipped, nie jako przegrane.
   - Kryterium zakończenia: leaderboard porównuje pełne ścieżki, a ten sam dataset/version, katalog, zakres i seed odtwarzają foldy i przestrzeń kandydatów.

3. **Etap C — bogate, typowane feature generation**
   - Status: rozpoczęty. Działa fold-local winsoryzacja oraz tworzenie signed-log1p features z fitted state, lineage przez Feature Manifest i identycznym zastosowaniem w scoringu. Pozostałe rodziny z listy poniżej nie są jeszcze wdrożone w AutoFE search space.
   - Numeryczne: warianty imputacji, missing indicators, clipping/winsorization, log/signed-log, Yeo-Johnson, quantile, binning oraz ograniczone polynomial/interactions.
   - Kategorie: one-hot, ordinal, frequency, hashing, a następnie leakage-safe out-of-fold target encoding z kontraktem smoothing/unknown.
   - Daty: kalendarz, cykliczność, elapsed time i jawnie skonfigurowane różnice; nie zgadywać semantyki czasu.
   - Tekst: tylko jawnie ograniczony wariant hashing/TF-IDF; bez deklarowania kompleksowego NLP.
   - Obowiązkowe limity wymiarowości, memory preflight, sparse/dense capability, pruning przed eksplozją macierzy i column lineage każdej cechy.
   - Kryterium zakończenia: wiele typowanych rodzin receptur daje się odtworzyć i identycznie zastosować w batch scoringu.

4. **Etap D — feature selection i redukcja wymiaru**
   - Status: rozpoczęty. Działa fold-local constant/low-variance filter jako element formalnej receptury; zapisuje wariancje, próg, wybrane i odrzucone kolumny w fitted state. Selekcja nadzorowana i redukcja wymiaru pozostają kolejnym zakresem.
   - Filtry: constant/variance, brakowość, redundancja/korelacje, univariate tests i mutual information.
   - Selekcja modelowa: L1, tree importance i ograniczone RFE; permutation importance głównie diagnostycznie lub z jawnym budżetem.
   - PCA/SVD tylko dla kompatybilnych reprezentacji, z fitted state i lineage komponentów.
   - Supervised selection zawsze fold-local; metoda, próg i liczba cech należą do search space.
   - Kryterium zakończenia: AutoML wspólnie wybiera recepturę, selektor i model, pokazuje stabilność między foldami i utrwala rozwiązaną listę cech.

5. **Etap E — kategorie natywne**
   - Rozszerzyć kontrakt model input o typowaną reprezentację categorical i mapowanie kolumn.
   - Dodać adaptery/capabilities dla CatBoost, LightGBM i, jeśli wspiera to używana wersja, XGBoost.
   - One-hot/frequency nie mogą być oznaczane jako native. Zachować surowe kategorie oraz identyczny missing/unknown contract w scoringu.
   - Porównywać native categorical i kodowane warianty jako różne receptury na tych samych foldach.
   - Kryterium zakończenia: model native categorical daje się zarejestrować, odtworzyć i uruchomić w test/batch scoring bez refitu encoderów.

6. **Etap F — champion selection, ensemble i UX**
   - Ensemble/blending/stacking wdrażać dopiero po stabilizacji OOF predictions; meta-model trenuje wyłącznie na OOF.
   - Dodać opcjonalną optymalizację wielokryterialną: primary metric oraz ograniczenia/cel czasu, pamięci, rozmiaru modelu i liczby cech.
   - UI pokazuje leaderboard pełnych ścieżek, recepturę i lineage, foldy/wariancję, koszty, failures/pruning, zakres danych, przybliżenia i powód wyboru.
   - Użytkownik może skopiować zwycięską recepturę do edytowalnego FE i świadomie wybrać innego kandydata.
   - Kryterium zakończenia: eksperyment jest zrozumiały, audytowalny i operacjonalizowalny, a scoring używa dokładnie artefaktów zwycięskiej ścieżki.

#### Skala i uczciwość wyników

- Pełnozbiorowa analiza pozostaje domyślna. Nie wolno po cichu przejść na próbkę, zmniejszyć liczby foldów ani pominąć kosztownych kandydatów.
- Dla dużych danych użytkownik jawnie wybiera: pełnozbiorowy holdout, pełnozbiorowe CV, oznaczoną eksplorację na próbce z obowiązkową pełnozbiorową walidacją finalistów albo progresywny zakres z pełnozbiorowym finałem.
- Wynik pokazuje zakres, liczbę unikalnych wierszy, łączną liczbę przetworzeń przez foldy/triale/refit, przybliżenia oraz timeout/pruning.
- Przed materializacją wykonuj dimensionality i memory preflight; preferuj sparse representation, DuckDB, bounded batches, run-scoped Parquet i usuwanie tymczasowych kandydatów.
- Najpierw mierz i optymalizuj obecny single-node stack. Cięższą infrastrukturę rozważaj tylko po pomiarach i osobnej decyzji.

#### Reguły dla kolejnych zakresów

- Fold-local foundation i pionowy fragment B/C/D (recipe contract 2.0, niezależne warianty winsoryzacji/signed-log1p, search skalowania, low-variance selection, dwufazowy scheduler i audytowalny leaderboard ścieżek) są zakończone. Najlepszy następny krok funkcjonalny to typowane transformacje Yeo-Johnson/quantile/binning; refaktoryzacyjnie należy wydzielić scheduler i evaluator z handlera przed dalszym wzrostem złożoności. Target encoding, supervised selection, RFE, PCA i stacking muszą korzystać z istniejącego fold-local executora.
- Każdy etap dziel na małe pionowe zakresy: kontrakt backendowy, wykonanie, artifact/provenance, minimalne API/UI i testy end-to-end.
- Nie dodawaj aktywnej kontrolki UI bez działającego backendu; funkcje planowane oznaczaj jako planowane.
- Zachowuj kompatybilność opublikowanych PipelineVersion i modeli. Migracje draftów są deterministyczne; opublikowanych definicji nie mutuj.
- Po każdym zakresie aktualizuj tę sekcję: przenieś ukończone elementy do statusu, zapisz realne ograniczenia i wskaż następny najmniejszy krok.
