# Prompt → gotowy wykres: trzech agentów Paseo

Run `20261104T184559Z`. GPT-6.1-Sol, medium, 3 niezależni agenci uruchomieni równolegle. Usługa GPU i dokumentacja były już gotowe. Agenci mogli korzystać z istniejącego kodu klientów; pisanie/adaptacja kodu i wszystkie operacje po wysłaniu promptu są wliczone. W nowej sesji przydzielono full-access do autoryzowanego zadania, więc nie było postojów na pytania o zwykłe operacje.

Start: lokalny monotoniczny zegar tuż przed wywołaniem Paseo z promptem. Koniec: pierwszy odczyt done.json=success, kompletnego lokalnego PNG (sprawdzone nagłówek, rozmiar i IEND) i metrics.json. Poll 0,25 s, więc opóźnienie detekcji do około 0,25 s. done.json agent publikował po walidacji i skopiowaniu artefaktów. Wliczone: start agenta, rozumowanie, narzędzia, dane, wspólna kolejka GPU, API, rysowanie, walidacja i transfer. Koniec nie zależy od zegara PC ani ukończenia finalnej wiadomości w Paseo. To pojedynczy przebieg każdego zadania, nie mediana ani p95.

| Zadanie | Prompt → wykres [s] | Wejście / kontekst | Train/test lub prognoza | Cechy | Przetwarzanie modelu [s] | Kolejka [s] | Wykres |
|---|---:|---:|---|---:|---:|---:|---|
| Timestral — pogoda + Interia | 82.91 | 720 | 720 h → 29 h, z czego 24 h jutra | 1 | 0.0360 | 0.2040 | [PNG](weather/chart.png) / [SVG](weather/chart.svg) |
| TabICL — klasyfikacja | 78.41 | 569 | 455/114 | 30 | 0.3739 | 0.2784 | [PNG](classification/chart.png) / [SVG](classification/chart.svg) |
| TabICL — regresja | 84.16 | 2500 | 2000/500 | 20 | 0.4322 | 0.1249 | [PNG](regression/chart.png) / [SVG](regression/chart.svg) |

Wszystkie trzy wykresy: 84.16 s od równoległego wysłania promptów. Od pierwszego odczytu zegara podczas obsługi polecenia użytkownika do ostatniego wykresu: około 268.4 s; przygotowanie uruchomienia pomiaru przed promptami zajęło 184.3 s. Dokładny timestamp samego przyjścia wiadomości użytkownika nie jest dostępny, więc ten drugi pomiar jest przybliżony.

Każde zadanie miało nowe job_id i cache_hit=false. Timestral miał już załadowane wagi (load_model_seconds=0), a nowa inferencja wyniosła 0,0312 s. To brak cache wyników przy rozgrzanym procesie, nie zimny start. TabICL duration_seconds obejmuje przygotowanie/fit/predict, nie tylko forward. Nie porównuj liczb z kolumny czasu modelu jak zadań o tej samej semantyce.

Pogoda: świeże obserwacje IEM EPKT, 720 h, świeży odczyt 24 godzin Interii przez BrowserOS; porównanie dwóch prognoz, nie ich błędu względem pomiarów. Klasyfikacja: sklearn breast_cancer, 569 × 30, holdout 455/114, accuracy 0,9737, ROC AUC 0,9964; wykres macierzy pomyłek i ROC. Regresja: nowo wygenerowane dane syntetyczne 2500 × 20, split 2000/500, RMSE 10,4277, MAE 8,2915, R² 0,9972; wykres predykcji i residuali.

W każdym podkatalogu: prompt.md, launch.json, kod klienta, wejściowe dane, nowy job.json, CSV wyników, metrics.json, chart.png/.svg, done.json. Konfiguracja i dokładne czasy wszystkich agentów: timings.json.
