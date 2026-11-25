# Testy demo w Claude web (connector „BentoML GPU token", 05.11.2026)
Prompty: `all-prompts.json`. Każdy scenariusz w osobnej rozmowie, serwer sam pobierał dane (dataset_from_url).

| Scenariusz | Wynik | job_id | czas modelu |
|---|---|---|---|
| tips (regresja total_bill) | R² 0.4087, RMSE 7.0805, MAE 5.8225; 244 wiersze, 195/49 | job_e4b6d9c2… | 0.286 s |
| mpg (regresja mpg) | R² 0.9181, RMSE 2.099, MAE 1.535; 398 wierszy, 318/80 | job_7237f744… | 0.301 s |
| insurance (regresja charges) | R² 0.8876, RMSE 4176.78, MAE 2412.59; 1338 wierszy, 1070/268 | job_7c018991… | 1.84 s |
| wine (regresja quality) | R² 0.5782, RMSE 0.5251, MAE 0.3698; 1599 wierszy, 1279/320 | job_9f956746… | 0.342 s |
| iris (klasyfikacja) | accuracy 1.000, F1 1.000; 120/30 | job_529314a5… | 0.244 s |
| airline (Timestral, 12 mies.) | prognoza 1961 ze szczytem lip–sie ≈667/662; 144 wiersze | job_97b7658c… | 0.430 s inferencja |
| melbourne (Timestral, 30 dni) | pełny zbiór odrzucony (3650 wierszy, brak 29 lutego), działa na samym 1990 (365 wierszy) | job_703e2206… | 0.020 s inferencja |
| pogoda Katowice, IMGW | działa, ale dane do 30.09 → błąd ≈11 °C względem Interii | job_3a90b723… | 0.039 s |
| pogoda Katowice, Open-Meteo | 1104 wierszy do 4.11, mediana 4.2–8.8 °C, Interia −1…6 °C (różnica ≈4 °C) | job_84f35bd3… | 0.035 s |

Uwagi: receptura demo (4 estymatory, benchmark_parity false). Wine wymagał ponowienia ("Too many responses in progress" – limit równoległych odpowiedzi Claude web).

## Krótkie prompty (po odświeżeniu connectora, 05.11.2026)

Connector „BentoML GPU token" odłączony i podłączony ponownie. Na stronie connectora widać 18 narzędzi, w tym Dataset Catalog i Weather History. W nowych rozmowach przełącznik connectora był włączony. Uprawnienia narzędzi ustawione na Always allow, żeby czat nie czekał na akceptację każdego wywołania. `app/guide.py` bez zmian: wino samo wyszło jako regresja `quality`.

Każdy prompt w nowej rozmowie. Limit Claude („Too many responses in progress") złapał pogodę i pasażerów przy starcie piątki naraz; ponowienie po zakończeniu pozostałych przeszło.

| Prompt | Wynik | job_id | czas modelu | narzędzia / wykres |
|---|---|---|---|---|
| Weź jakiś dataset cen domów, żeby przewidywało, i zrób regresję z tym MCP Bento. | California Housing, regresja `median_house_value`, R² 0,876, RMSE 40 324, MAE 24 946; 20 640 wierszy, 16 512/4 128, 9 cech. ds_579dccd1089698c850ad1be7 | job_a0017ab017be9ffad78525ae | 1,71 s | Dataset Catalog, wykres (iframe) |
| Przewidź mi, jaka będzie pogoda jutro w Katowicach, za pomocą MCP Bento. | Timestral, 1096 h ERA5 do 5.11 15:00 UTC (dziś, obcięte do pełnej godziny), jutro 6.11 czasu Europe/Warsaw (UTC+1) w krokach 8–31. Mediana ok. 0,5°C o 07:00 i 8,0°C o 14:00 (5,3–10,5). Porównania z Interią nie było (wyszukiwarka bez aktualnej strony). ds_631a312a20c586ce590f0a42 | job_13f368a8b43b13b20f026862 | 0,62 s | weather_history (świeże ERA5 + forecast_args), wykres godzinowy |
| Weź dataset z winami i przewidź jakość wina za pomocą MCP Bento. | REGRESJA `quality` (wine_red, 1599), R² 0,578, RMSE 0,525, MAE 0,370; 1279/320, 11 cech. ds_e2de6b06d9906612e05e2477 | job_312e841ec1a92497190b5156 | 0,28 s | katalog, artifact z wykresem |
| Przewidź liczbę pasażerów linii lotniczych na następne 12 miesięcy za pomocą MCP Bento. | Timestral, 144 miesiące 1949–1960, prognoza 1961, szczyt lipiec 667 / sierpień 662 (tys.). ds_824bfb5871ae3df4d2c840b7. Po wyniku dopisał, że to nie jest prognoza na 2026 i do niej potrzeba nowszych danych. | job_9df1fd9509369bf60b66dcc0 | ok. 0,03 s | katalog, wykres z pasmem 5–95% |
| Zrób klasyfikację: kto przeżył na Titanicu. Użyj MCP Bento. | accuracy 82,7%, F1 makro 81,3%, ROC AUC 85,6%; 891 wierszy, 712/179. Pominął `alive` i `alone`. ds_6885953d9d81c817b26e1fbd | job_6351003b1a265cec553ac357 | 0,32 s | katalog, artifact |
| Weź dataset ubezpieczeń i przewidź koszty medyczne za pomocą MCP Bento. | regresja `charges`, R² 0,888, RMSE 4177, MAE 2413; 1338 wierszy, 1070/268. ds_a99742f1dd1f4f92ceaffa20. Drugie, przypadkowe uruchomienie tego samego promptu dało te same metryki (job_06c1fd07c68585d764fe4b41, 0,29 s). | job_874bd9d36c5bd1ff8114d10c | 0,28 s | istniejący zbiór w workspace, wykres |
| Weź dataset irysów i zrób klasyfikację gatunku za pomocą MCP Bento. | accuracy 1,000, F1 makro 1,000; 150 wierszy, 120/30, 4 cechy. ds_59fa6846b82c26dae3830889 | job_956ed0d6c17ac51ff6225989 | 0,24 s | katalog, artifact |
| Weź dataset dziennych temperatur Melbourne i przewidź następne 30 dni za pomocą MCP Bento. | Timestral na ciągłym 1990 (365 dni, bez 29 lutego), horyzont 1–30.01.1991, mediana 13,8→15,3°C, pasmo 5–95% od 10,3 do 20,1°C. ds_953ac5214f4a93a5ed0684e9 | job_b88bb8caaeadc43548967cf8 | 0,64 s | katalog, wykres |

Prompt „Przewidź temperaturę w Melbourne na następne 30 dni za pomocą MCP Bento." poszedł w `weather_history` (2176 h do 5.11 15:00 UTC, job_7d98e3e9af7dfd19a14f23fc, 0,60 s, 741 h) i zatrzymał się z pytaniem o zgodę na pobranie CSV. Po zgodzie jest wykres dzienny 6.11–6.12.2026 (średnie dobowe ok. 15–17°C). Do klasycznego zbioru dziennego lepiej wkleić prompt z wiersza Melbourne powyżej.
