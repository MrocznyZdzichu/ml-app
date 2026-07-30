# Moduły backendu

## Granice warstw

- Router waliduje transport i mapuje schematy; przypadek użycia należy do
  serwisu, reguła biznesowa do domeny, a trwałość do portu repozytorium.
- Serwisy nie importują FastAPI. Zgłaszają typowane `ApplicationError` ze
  stabilnym kodem; `app.api.error_handlers` mapuje je na HTTP.
- Port repozytorium, adapter pamięciowy, adapter PostgreSQL i read modele są
  osobnymi modułami. Listy filtruj i stronicuj już w PostgreSQL.
- Kontrole dostępu obowiązują listy, detale, pliki, lineage, zadania i wyniki.
  Worker ponownie sprawdza dostęp przed rozpoczęciem kosztownego wykonania.

## Business Case, artefakty i dane

- Business Case ma globalnie unikalną nazwę case-insensitive. Konflikt tworzenia
  lub zmiany nazwy zwraca 409 również dla niewidocznego BC.
- Dataset/Data View może być przypięty do wielu BC z jedną rolą i opisem.
  Grant przez jeden BC nie ujawnia innych BC ani ich lineage.
- `Artifact` jest technicznym rejestrem, nie osobnym głównym bytem UI.
- Lineage jest portowe (`step_id + port_id`) i zawiera inputy, wersję pipeline'u,
  run, twórcę, czas, schemat oraz liczbę wierszy.
- Zewnętrzny artefakt wymaga jawnego źródła i opisu. Artefakty platformy są
  niemutowalne.

## Użytkownicy i współdzielenie

- Rejestracja daje wyłącznie rolę platformową `user`.
- `governance_steward` nie ma niejawnego globalnego odczytu ani bypassu.
- Administrator może zarządzać rolami, kontami, grupami, grantami i transferem
  własności, ale nigdy nie poznaje istniejących haseł.
- Hierarchia BC: `report_viewer`, `reader`, `contributor`, `manager`, `owner`.
  `report_viewer` nie widzi danych rekordowych, datasetów, konfiguracji
  pipeline'ów ani drill-down do źródeł.
- Dostęp jest sumą administracji, własności, grantu użytkownika, grupy i BC.
  Nie ma jawnych grantów deny. Odebranie jednej ścieżki nie usuwa pozostałych.
- Bezpośrednie granty `reader/editor/owner` są wyjątkiem dla luźnych datasetów,
  Data Views i świadomie samodzielnych analiz/raportów.
- Grupy mają własnego managera/właściciela. Manager BC może nadać grupie dostęp,
  ale nie zmienia jej członkostwa bez osobnych uprawnień.
- Zmiana roli, blokada konta, hasła lub istotnego dostępu unieważnia albo
  wersjonuje sesję; nie ufaj bezterminowo rolom zapisanym w JWT.
- Audytuj logowania root, hasła, role, blokady, grupy, granty, owner/manager,
  transfer własności oraz administracyjny dostęp do cudzych zasobów.
