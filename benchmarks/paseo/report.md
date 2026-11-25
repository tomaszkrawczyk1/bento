# Niezależny test klienta Bento Tabular

Dwa zadania, 12 nowych zadań API: 8 uruchomień modelu i 4 odczyty cache, wszystkie zakończone sukcesem. REST przez HTTP loopback `127.0.0.1:3000` na PC, klient uruchomiony przez SSH. Nie jest to pomiar opóźnienia publicznego internetu ani odtworzenie benchmarku publikacji. Publiczny MCP sprawdzono osobnym, rzeczywistym i uwierzytelnionym `model_info` przez HTTPS.

Klasyfikacja: istniejące `demo/classification-train.csv` i `demo/classification-test.csv`, osobne uploady i odczyty schematu przez API, 455/114 wierszy i 30 cech bez targetu; oba backendy ICL, fine_tune=false. Regresja: sklearn.make_regression(1250,20,n_informative=15,noise=10,random_state=2026), podział train_test_split(random_state=2026) na 1000/250 wierszy. Trening zawiera target, test go nie zawiera; prawda w osobnym regression-truth.csv służy wyłącznie do metryk klienta. Wszystkie predykcje przez POST /predict, pełne wyniki pobrane przez HTTP.

Ograniczenie API: TabICL z fine_tune=true został odrzucony HTTP 400 (odpowiedź w raw.json). Jego regresję zmierzono z false. Mitra: regresja z true i time_limit=30. Ten limit jest budżetem dostrajania, nie twardym limitem czasu całego zadania. Wszystkie zaakceptowane żądania mają time_limit=30 i seed=2026.

A: use_cache=false. B: pierwsze use_cache=true (we wszystkich parach cache_hit=false). C: identyczne B, bez zmiany backendu pomiędzy B/C; we wszystkich parach cache_hit=true, cache_type=result i predykcje dokładnie zgodne z B. C odczytuje gotowy wynik, nie mierzy ponownej inferencji. Klient nie czyścił globalnego cache i nie musiał usuwać żadnego kontekstu. API samo zarządza cache przy przełączaniu backendów.

Czas API = duration_seconds: przygotowanie danych + dopasowanie/dostrajanie + predykcja; dla C odczyt cache. Nie jest to wyizolowany forward/predict. Worker = finished-started, kolejka = started-created. Klient = perf_counter od rozpoczęcia wysyłania /predict do odebrania zakończonego zadania, z kolejką i pollingiem co co najmniej 1,05 s. Submit jest osobnym pomiarem perf_counter wokół helpera HTTP i obejmuje też parsowanie oraz lokalny zapis odpowiedzi; nie jest czystym czasem sieciowym. Zapis odpowiedzi pollingowych również wnosi mały narzut do czasu klienta. Pełne wyniki pobierano po zakończeniu pomiaru klienta.

Sprawdzono schematy i liczby wierszy z API, sukces wszystkich 12 jobów, train/test rows oraz listę cech w odpowiedzi modelu, brak targetu w features, kompletność i skończoność predykcji, kolejność input_row i identyczność B/C. Zadania uruchamiano sekwencyjnie. Każdy wiersz poniżej pochodzi z nowego job_id, zapisanego w surowych odpowiedziach.

| Zadanie | Backend | A/B/C | fine_tune | Cechy | Train/test | cache_hit/type | API [s] | Worker [s] | Kolejka [s] | Submit [s] | Klient [s] | RMSE | MAE | job_id | result_id |
|---|---|---|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| classification | tabicl | A | false | 30 | 455/114 | false/none | 0.423579 | 0.642466 | 0.204058 | 0.009559 | 1.063686 | — | — | job_5f7b172a2f6f5984164de058 | result_8d09900ce136537f44cd98f4 |
| classification | tabicl | B | false | 30 | 455/114 | false/none | 0.392592 | 0.513707 | 0.265995 | 0.013735 | 1.068199 | — | — | job_b8aa56baf53c8637ef98ff1a | result_a4b347490b5be9ff157e6a08 |
| classification | tabicl | C | false | 30 | 455/114 | true/result | 0.005305 | 0.129190 | 0.201172 | 0.013098 | 1.067807 | — | — | job_6e42469c9c97f145bce3c2bb | result_eed9f43a3ed35df5c1edf0dc |
| classification | mitra | A | false | 30 | 455/114 | false/none | 3.131632 | 3.439607 | 0.252926 | 0.013532 | 4.231729 | — | — | job_d2e775c42e2d3103a5a42cea | result_c11db105c827980126afaad5 |
| classification | mitra | B | false | 30 | 455/114 | false/none | 0.955400 | 1.095326 | 0.451934 | 0.012168 | 2.126536 | — | — | job_30b85a774ebc0918eef791bd | result_20a04b549514bdbe7028d857 |
| classification | mitra | C | false | 30 | 455/114 | true/result | 0.005238 | 0.130118 | 0.410455 | 0.013379 | 1.069352 | — | — | job_e93460fe13347118f5e97aaa | result_76c8771162622863628b87a2 |
| regression | tabicl | A | false | 20 | 1000/250 | false/none | 0.394131 | 0.688167 | 0.462602 | 0.014293 | 2.124701 | 10.889168 | 8.765527 | job_2ce711bbaac3d02d5f27d566 | result_4c03627680fe8e3fdb2ba26e |
| regression | tabicl | B | false | 20 | 1000/250 | false/none | 0.393686 | 0.577461 | 0.016271 | 0.010206 | 1.065313 | 10.889166 | 8.765529 | job_3fc610223be82b279982e828 | result_54626dffdaef09f1d880e49b |
| regression | tabicl | C | false | 20 | 1000/250 | true/result | 0.004404 | 0.191486 | 0.022182 | 0.010677 | 1.065378 | 10.889166 | 8.765529 | job_8b40a9ce595a0ef697fed8fb | result_812b31f9695a200ba4964558 |
| regression | mitra | A | true | 20 | 1000/250 | false/none | 34.297527 | 34.575264 | 0.143890 | 0.011070 | 34.876058 | 16.998962 | 11.089953 | job_21423005a72eede9e49e8ec7 | result_a116238b025ac2f850b99be1 |
| regression | mitra | B | true | 20 | 1000/250 | false/none | 34.234386 | 34.503008 | 0.337691 | 0.014279 | 34.883982 | 17.433158 | 10.946255 | job_9f3d975c5be81bfd659b432b | result_a110908f7e51d3295c07391d |
| regression | mitra | C | true | 20 | 1000/250 | true/result | 0.004311 | 0.150462 | 0.447147 | 0.031164 | 1.087484 | 17.433158 | 10.946255 | job_a4fdc84f2acd9848f56f4198 | result_ff4799706406dc2f6ad9a4df |

Artefakty: client.py (samodzielny klient), report.py (generowanie raportu i walidacja B/C), raw.json (odpowiedzi API/MCP bez kluczy, haseł i linków z tokenami), summary.json (pełne metryki), regression-*.csv (dane i osobna prawda), job_*.parquet (pełne predykcje).

Czas wykonania klienta: 86.94 s. Konfiguracji usług, kont i agenta nie zmieniano.
