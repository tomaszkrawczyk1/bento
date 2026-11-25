# Claude web – dodatkowe scenariusze Timestral

## Pasażerowie – 12 miesięcy

Test demonstracyjny BentoML + MCP: sam pobierz na serwer przez connector BentoML GPU zbiór https://raw.githubusercontent.com/jbrownlee/Datasets/master/airline-passengers.csv i modelem Timestral-209M przewidź następne 12 miesięcy liczby pasażerów. Kolumna czasu Month, cel Passengers. Użyj rzeczywistych narzędzi dataset_from_url, forecast i odbierz wynik zadania (job_status/job_result). Nie wymyślaj predykcji, nie trenuj własnego modelu. Następnie pokaż czytelny wykres prognozy, tabelkę 12 punktów i krótki opis sezonowości. Możesz użyć narzędzi tworzenia wykresu/artifact HTML/SVG, jeśli Python nie jest dostępny. Na końcu podaj dataset_id, job_id, liczbę wierszy wejściowych, serii, targetów, horyzont i czasy backendu z odpowiedzi API. Nie czekaj na dodatkowe zgody, wykonaj cały przebieg.

Pierwsze wysłanie: 2026-11-05 14:25:06.533 UTC.
Rozmowa: https://claude.ai/chat/5700444d-c0c2-4015-a16c-f98e6b2f9083

## Melbourne – historyczny benchmark, 30 dni

Test demonstracyjny BentoML + MCP: sam pobierz na serwer przez connector BentoML GPU zbiór https://raw.githubusercontent.com/jbrownlee/Datasets/master/daily-min-temperatures.csv i modelem Timestral-209M przewidź następne 30 dni minimalnej temperatury Melbourne po końcu tego historycznego zbioru. To benchmark historyczny, NIE prognoza bieżącej pogody. Kolumna czasu Date, cel Temp. Użyj rzeczywistych narzędzi dataset_from_url, forecast i odbierz wynik zadania (job_status/job_result). Jeśli dane mają lukę daty, nie uzupełniaj jej wymyślonym pomiarem: opisz problem i spróbuj importu odpowiedniego ciągłego okresu przez ogólne opcje importera, jeśli są dostępne. Nie wymyślaj predykcji ani nie trenuj własnego modelu. Pokaż wykres prognozy, tabelkę 30 punktów, daty i krótki komentarz. Możesz stworzyć artifact HTML/SVG, jeśli brak Pythona. Na końcu podaj dataset_id, job_id, liczbę wierszy wejściowych, serii, targetów, horyzont i czasy backendu z API. Wykonaj cały przebieg.

Pierwsze wysłanie: 2026-11-05 14:25:14.228 UTC.
Rozmowa: https://claude.ai/chat/93d0d29c-8a1f-4b6b-a76d-7b5107f1223c

Pierwsze podejście w obu rozmowach zatrzymane przez Claude na żądaniu ponownego połączenia OAuth connectora BentoML GPU. Oczekiwanie na przywrócenie połączenia nie jest czasem inferencji modelu.
