# Timestral-209M — rzeczywisty test GPU

RTX 5060 Ti 16 GB. Dane syntetyczne: dobowa i tygodniowa sezonowość + trend. Osobny przyszły odcinek do pomiaru RMSE/MAE. Pomiary pojedynczych przebiegów, nie oficjalny benchmark.

| Przebieg | Historia łącznie | Grupy | Targety/grupę | Kolumny numeryczne/grupę | Horyzont/grupę | Ładowanie [s] | Inferencja [s] | Przetwarzanie API [s] | Klient [s] | Cache | RMSE | Job |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|
| univariate-uncached | 512 | 1 | 1 | 1 | 48 | 1.1938 | 0.4415 | 1.6533 | 3.0209 | brak | 0.04375 | job_cf8f2db2331c75ab9903ad17 |
| univariate-cache-first | 512 | 1 | 1 | 1 | 48 | 0.0000 | 0.0256 | 0.0327 | 1.0190 | brak | 0.04375 | job_46fdd8987d61bf90b710f7c4 |
| univariate-cache-hit | 512 | 1 | 1 | 1 | 48 | 0.0000 | 0.0000 | 0.0065 | 1.0227 | result | 0.04375 | job_0cd88bd63f0a694db2ea4a96 |
| multivariate-uncached | 2048 | 2 | 3 | 6 | 96 | 0.0000 | 0.1416 | 0.1586 | 1.9477 | brak | 0.07492 | job_e91f80475bb15751704f4234 |
| multivariate-cache-first | 2048 | 2 | 3 | 6 | 96 | 0.0000 | 0.1129 | 0.1280 | 1.0247 | brak | 0.07492 | job_066634f060bc714958ea84b1 |
| multivariate-cache-hit | 2048 | 2 | 3 | 6 | 96 | 0.0000 | 0.0000 | 0.0095 | 1.0241 | result | 0.07492 | job_1af523401ee10b8733f5c1c3 |
| multivariate-future-target-ignored | 2048 | 2 | 3 | 6 | 96 | 0.0000 | 0.1130 | 0.1285 | 1.0174 | brak | 0.07492 | job_a276f0444877310be2e3a5bc |

Univariate: 512 obserwacji, jeden target, prognoza 48 godzin. Multivariate: dwie grupy po 1024 obserwacje, po 3 targety i 3 covariates (jedna historyczna, dwie znane w przyszłości), prognoza 96 godzin dla każdej grupy i targetu — 576 wynikowych wierszy.

Czas inferencji mierzy TimestralForecaster.forecast, z synchronizacją CUDA przed i po. Zawiera także wewnętrzne przygotowanie wejść przez wrapper; nie jest wyłącznie czasem kerneli GPU. Pierwszy przebieg obejmuje rozruch bibliotek i jest wolniejszy. Czas ładowania wag jest oddzielny. Klient obejmuje kolejkę i polling co sekundę; test multivariate-uncached składa zadanie przez publiczny MCP i odpytuje REST na PC. Pozostałe żądania używają REST loopback.

Cache hit oznacza brak ponownej inferencji: inference_executed=false i inference_seconds=0. Wszystkie predykcje cache zgadzają się dokładnie z poprzednim wynikiem. Podmiana przyszłych targetów na 1e9 nie zmieniła prognozy. Sprawdzono medianę i wszystkie 21 kwantyli, kompletność wyników i powiązanie timestamp/series/target. Odrzucono błędny horyzont, target timestamp oraz brak przyszłych covariates. Maksymalne przydzielenie pamięci PyTorch przy inferencji: 853.2 MiB (nie obejmuje całego narzutu sterownika CUDA).

Surowe metryki: summary.json; każdemu przebiegowi odpowiada *-job.json i plik Parquet. Skrypt: ../../tests/timestral_smoke.py.
