# Zadanie dla Groka (przejęcie od Claude, 05.11.2026)

Folder: /home/laptop/studia/chmura (AGENTS.md w nim obowiązuje). Kod MCP: materialy/bento. Serwer PC: `ssh pc@pc`, /home/pc/sandbox/bento (docker compose, gateway na :3000, publiczny https://vmi3696773.contaboserver.net).

## Stan (zrobione i sprawdzone)
- Logowanie tokenem: connector Claude web „BentoML GPU token" = `https://vmi3696773.contaboserver.net/t/<api_key>/mcp`, „No sign-in" (api_key w pc:/home/pc/sandbox/bento/.credentials/owner.json). Działa (tests/token_url_smoke.py).
- Nowe w MCP (app/guide.py + app/gateway.py, wdrożone na PC): `instructions` serwera (playbook: autonomia, defaults evaluate test_size .2 seed 42, raport, wykres), narzędzia `dataset_catalog(topic)` i `weather_history(city)` (Open-Meteo, ucina do „teraz", zwraca forecast_args na jutro).
- 8 długich scenariuszy przeszło (WYNIKI-05-11.md).

## Do zrobienia
1. Claude web cache'uje listę narzędzi i instructions connectora: nowe narzędzia/instructions NIE są widoczne w istniejącym connectorze (test: Claude odpowiedział „Serwer nie ma weather_history", wino zrobił jako klasyfikację). Odśwież: w BrowserOS (narzędzia mcp__browseros-neo__*, sesja własna, NIE ruszaj cudzych kart) strona https://claude.ai/customize/connectors/yours/id/ab19c021-81fe-4dc2-ad52-d2ed248069f4 → Disconnect → Connect (albo usuń connector i dodaj od nowa z tym samym URL, No sign-in). Potwierdź w nowej rozmowie, że widać `weather_history` i `dataset_catalog`; włącz przełącznik connectora w menu „+" → Connectors.
2. Przetestuj KRÓTKIE prompty w nowych rozmowach claude.ai (max 5 naraz, inaczej „Too many responses in progress"):
   - Weź jakiś dataset cen domów, żeby przewidywało, i zrób regresję z tym MCP Bento.
   - Przewidź mi, jaka będzie pogoda jutro w Katowicach, za pomocą MCP Bento.
   - Weź dataset z winami i przewidź jakość wina za pomocą MCP Bento.  (oczekiwane: REGRESJA quality; jeśli wychodzi klasyfikacja, popraw instructions w app/guide.py: dla wartości porządkowych/numerycznych target → regression)
   - Przewidź liczbę pasażerów linii lotniczych na następne 12 miesięcy za pomocą MCP Bento.
   - Zrób klasyfikację: kto przeżył na Titanicu. Użyj MCP Bento.
   - dodatkowo: ubezpieczenia (koszty), irysy, Melbourne.
   Dla każdego sprawdź: czy sam użył narzędzi (dataset_catalog/weather_history), nie pytał o nic, podał metryki/dataset_id/job_id/czasy, zrobił wykres. Pogoda: sprawdź, czy ostatni pomiar jest dzisiejszy i czy wynik obejmuje 6.11 (jutro) w czasie Europe/Warsaw.
3. Po zmianach w app/guide.py: rsync na PC (`rsync -a app/guide.py app/gateway.py pc@pc:/home/pc/sandbox/bento/app/`), `ssh pc@pc 'cd /home/pc/sandbox/bento && docker compose build gateway && docker compose up -d --no-deps gateway'`, potem ODŚWIEŻ connector (pkt 1) bo cache.
4. Wpisz wyniki do WYNIKI-05-11.md (sekcja „krótkie prompty") i wyślij userowi gotową listę promptów do wklejenia (te powyżej + ewentualne poprawki).
Nie zmieniaj cudzych kart przeglądarki. Nie wypisuj api_key w odpowiedziach dla usera.
