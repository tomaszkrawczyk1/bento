# Scenariusz na 15 minut

0–2 min: problem — skrypt z modelem staje się usługą dostępną dla kilku osób.
Pokaż granice: BentoML serwuje modele i API; registry, kolejka, auth i MCP są kodem
projektu. Twingate daje prywatną drogę sieciową; OAuth publiczne uwierzytelnienie.

2–4 min: schemat z README. Dwa środowiska modeli, jedna kolejka GPU, Parquet + ID.
Pokaż `docker compose ps` i lokalne checkpointy, bez otwierania plików sekretów.

4–8 min: Claude web z podpiętym Bento. Poproś:
„Sprawdź źródło postgres_demo i jego schemat. Utwórz zbiór z tabeli regression_data.
Oceń TabICL dla target, użyj wszystkich cech poza target, use_cache=true.
Czekaj na zakończenie zadania i pokaż RMSE oraz link do wyników”.
Następnie powtórz identyczną ewaluację: pokaż `cache_hit=true`, `cache_type=result`.
Wyjaśnij, że to cache dokładnego wyniku. Nowy test na tym samym treningu korzysta
z zachowanego kontekstu modelu.

8–11 min: druga ścieżka, plik. `create_upload_link`, upload `demo/classification-train.csv`,
`list_datasets`, TabICL holdout accuracy/F1. Nie wklejaj CSV do rozmowy.
Opcjonalnie pokaż Mitrę z zapisanych rzeczywistych wyników: `demo/*mitra-verification.json`.
Dostrajanie może poczekać w kolejce; nie rób z czasu obliczeń niespodzianki.

11–13 min: współpraca. Grupa Bento Project w Twingate oraz dwa niezależne konta
aplikacji w jednym workspace. Osobne klucze i możliwość cofnięcia dostępu.

13–15 min: ograniczenia. Losowy holdout nie gwarantuje braku leakage w czasie.
Fine-tune Mitry: oficjalny wrapper uczy podczas predict i ma cache wyniku.
2 foldy nie odtwarzają benchmarku. Publiczny demo URL zmienia się przy restarcie;
stały named tunnel to następny krok. MySQL nie przeszedł testu na żywej bazie.

Plan B: wyniki JSON w `demo/`, logi testów na PC i lokalne pliki CSV. Nagrania
nie wykonano; do prezentacji można je przygotować osobno.
