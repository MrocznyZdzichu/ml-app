# Publiczny klient Python

- `MLAppClient` zachowuje kompatybilną fasadę i deleguje do domenowych modułów.
- `client.py` pozostaje wyłącznie composition rootem. Nowe operacje umieszczaj w
  module domenowym; `serving.py` agreguje deployment, inference i monitoring.
- Wysokopoziomowe resolvery nazw używają wyszukiwania i paginacji po stronie
  API. Pełne `list_*` zachowuj tylko jako jawny kontrakt kompatybilności lub
  udokumentowany fallback dla legacy, nigdy jako domyślny krok workflow.
- Oferuj typowane operacje wysokiego poziomu dla całych workflow, nie tylko
  cienkie odpowiedniki requestów.
- Użytkownik może wskazać zasób nazwą lub typowanym obiektem. Niejednoznaczność
  zgłaszaj z listą rozwiązań; surowe ID pozostaje opcją automatyzacji.
- REST i klient mają identyczne zasady autoryzacji, idempotencji, paginacji,
  warningów, błędów, limitów i zadań asynchronicznych.
- Stabilne kody API mapuj na typowane wyjątki bez ujawniania sekretów.
- Publiczny workflow dokumentuj minimalnym przykładem REST/Python oraz
  realistycznym przykładem end-to-end w `examples/API-usage`.
- Online serving obejmuje usługi i rewizje, role, promocję/rollback, scoring,
  challengera, replay, kursorowy Inference Log i monitoring.
- Po zmianie klienta uruchom jego testy kontraktowe oraz przykłady zależne od
  zmienionego API.
