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
- Do `reference/index.html` dodawaj wyłącznie moduły zweryfikowane i świadomie
  opublikowane dla użytkowników. Gdy moduł zostaje zaakceptowany do publikacji,
  jego strona musi obejmować każdą publiczną metodę modułu. Moduły techniczne
  oraz agregaty bez własnych metod publicznych (np. `transport.py` i
  `serving.py`) nie wymagają osobnej strony.
- Nową stronę reference twórz z `reference/module-template.html` i renderera
  `reference/module-reference.js`, chyba że rozszerzasz stronę historycznie
  pisaną ręcznie. Zachowaj pełną strukturę `reference/access-requests.html`:
  wprowadzenie domenowe, rozwijane `Accepted values` z objaśnieniami, metody w
  `.methods` z opisem argumentów, przykładem Python oraz rozwijanym przykładem
  bezpośredniego REST. Udokumentuj każdą publiczną metodę modułu; dla metody
  czysto klienckiej wyraźnie wskaż, że nie ma osobnego endpointu HTTP.
- Używaj wspólnego `reference/module.css` i dołączaj `reference/copy-code.js`;
  każdy blok przykładowego kodu, również na stronie indeksu, musi mieć ikonowy
  przycisk kopiowania. Nie twórz uproszczonych stron referencji pozbawionych
  tych elementów. Reference opisuje wyłącznie aktualne publiczne API, podaje
  limity i dopuszczalne wartości oraz wskazuje odpowiadający notebook modułowy
  albo najbliższy notebook end-to-end, jeśli moduł jest przekrojowy.
- Online serving obejmuje usługi i rewizje, role, promocję/rollback, scoring,
  challengera, replay, kursorowy Inference Log i monitoring.
- Po zmianie klienta uruchom jego testy kontraktowe oraz przykłady zależne od
  zmienionego API.
