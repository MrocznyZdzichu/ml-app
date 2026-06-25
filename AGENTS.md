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
- Na start wystarczy metadata-only model registry jako placeholder, bez realnego treningu.
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

### Uprawnienia i audyt

- Na obecnym etapie ignoruj pełny model uprawnień. Stosuj placeholdery `owner`, `created_by`, `updated_by`.
- W przyszłości aplikacja ma mieć model uprawnień, udostępnianie obiektów oraz globalnego admina/kontrolera.
- Właściciel BC jest domyślnym właścicielem pipeline'ów w BC, ale właściciel biznesowy nie zawsze jest twórcą lub modyfikującym. Audyt `created_by` i `updated_by` jest obowiązkowy.

### Pierwszy zakres implementacyjny

- Pierwszy skeleton powinien obejmować minimalne `Business Cases` + `Pipelines` + endpointy API + frontend placeholder.
- Nie zaczynaj od trenowania modeli. Modele i operacjonalizacja są następną warstwą po stabilnym szkielecie: pipeline, version, run, artifact, lineage.
- Nie dodawaj mockowanych danych demonstracyjnych tylko po to, aby zapełnić UI. Aplikacja ma już przygotowane datasety pokrywające standardowe przypadki ML i to na nich użytkownik będzie testował kolejne etapy.
