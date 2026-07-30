# Frontend

- UI jest klientem publicznego REST API. Nie implementuj w React logiki
  analitycznej, metryk ani alternatywnej semantyki domenowej.
- Duże dane pozostają w backendzie. Tabele używają paginacji/kursorów, a wykresy
  ograniczonych agregatów lub jawnie oznaczonego renderingu.
- Funkcje pełnozbiorowe nie mogą po cichu przechodzić na preview.
- Dziel kod według feature: panel → hook/controller → domenowy klient API →
  kontrakty. Nie importuj komponentów z panelu innej domeny.
- `src/data/DataWorkspacePanels.tsx` jest wyłącznie fasadą kompatybilności.
  Koordynację analizy, browsing i profilowanie rozwijaj odpowiednio w
  `src/data/analysis`, `src/data/browser` i `src/data/profile`; współdzielone
  formatery danych pozostają modułem-liściem.
- Kontrakty umieszczaj w `src/api/contracts`; `api/client.ts` pozostaje fasadą
  kompatybilności. Nie twórz cykli importów — build uruchamia ich kontrolę.
- Współdzielone prezentacje, np. raporty, są modułami-liśćmi i nie importują
  kontrolerów ekranów.
- Zachowuj GUI i dostępność podczas refaktoryzacji. Paginacja API i UI musi być
  rozwijana razem.
- Przed zakończeniem uruchom `npm run build`; build obejmuje TypeScript, kontrolę
  architektury i produkcyjny bundle.
