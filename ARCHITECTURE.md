**Najważniejsza zmiana po punkcie 4:** Claude w przeglądarce nie połączy się przez Twingate. Custom connector łączy się z serwerów Anthropic, więc serwer MCP musi być dostępny z publicznego internetu, z zakresów IP Anthropic. Potrzebujesz więc dwóch dróg dostępu do tego samego bento. Druga zmiana: przeglądarkowy Claude nie przekaże pliku z czatu do narzędzia inaczej niż przepisując go w argumentach. Dlatego dane trafiają na serwer osobną drogą, a modele dostają tylko **identyfikator zbioru**.

## Architektura

```
Laptop (Claude Code/opencode) ──Twingate──┐
                                          ▼
Claude.ai (web) ──HTTPS + auth──▶ proxy ──▶ Bento na serwerze z GPU
   (tylko /mcp, /upload, /download)        ├─ REST API (+ skill)
                                           ├─ MCP /mcp
                                           ├─ rejestr zbiorów (Parquet)
                                           ├─ DuckDB → Postgres/MySQL/SQLite
                                           └─ TabICLv2 | Mitra-v2 + cache
```

Publiczne wystawienie robisz przez reverse proxy albo Cloudflare Tunnel. Na zewnątrz idą tylko ścieżki MCP i uploadu, a REST zostaje w Twingate.

## 1. Rejestr zbiorów (rdzeń całości)

Każde źródło danych zamienia się w `dataset_id`. Pod spodem jest Parquet na dysku serwera plus metadane: schemat, liczba wierszy, właściciel, TTL. Modele, cache i wyniki operują wyłącznie na tych identyfikatorach.

Zbiór może powstać na cztery sposoby:

| Sposób | Kto używa |
|---|---|
| upload multipart (`curl -F`) | agent na laptopie |
| strona uploadu z jednorazowym linkiem | użytkownik Claude web (przeciąga plik w przeglądarce) |
| `url` (S3 presigned, publiczny link, Drive) | oba |
| `source` + SQL do bazy | oba |

Wyniki predykcji też są zbiorami (`result_id`), z linkiem do pobrania.

## 2. Bazy danych

- `sources.yaml` zawiera nazwy źródeł, a DSN-y idą w zmiennych środowiskowych. Dla każdego źródła użyj użytkownika **read-only**.
- DuckDB (rozszerzenia `postgres`, `mysql`, `sqlite`) obsługuje wszystkie trzy typy. Rozszerzenia instaluj **przy budowie obrazu**, bo inaczej DuckDB próbuje je pobrać w runtime.
- Zabezpieczenia: dopuszczaj tylko `SELECT` (parsowanie np. przez `sqlglot`), stosuj timeout zapytania; nie narzucaj limitu wierszy.
- Agent dostaje do dyspozycji `list_sources`, `describe_source` (tabele, kolumny, typy) i kilka przykładowych wierszy, żeby mógł sam napisać SQL.
- Opcjonalnie później: Snowflake, BigQuery i zapis wyników z powrotem do bazy.

## 3. Dwa modele

- Parametr `backend: "tabicl" | "mitra"`, domyślnie `tabicl`.
- `fine_tune: bool` dotyczy tylko Mitry. Jest wolniejszy, ale tak liczono wyniki z benchmarku, więc w odpowiedzi API zwracaj szacowany czas.
- Regresja w Mitrze wymaga pakietu `mitra-finetune` z Hugging Face.
- **Ryzyko zależności:** AutoGluon i `tabicl` w jednym środowisku mogą kolidować. Plan: dwa serwisy modelowe i serwis-bramka spięte przez `bentoml.depends`. Jeśli wersje się pogryzą, robisz dwa osobne bento za tą samą bramką. Sprawdź to **jako pierwszy krok budowy**.
- Wagi obu modeli są wpieczone w obraz, a runtime ma ustawione `HF_HUB_OFFLINE=1`.

## 4. Cache (`use_cache: bool = false`)

- Klucz to hash z `train_id + target + backend + features + fine_tune`.
- Gdy `use_cache=true`, dopasowany model zostaje w pamięci, a odpowiedź zawiera `context_id`. Kolejne `predict` z tym samym kluczem pomijają `fit`.
- Dla TabICL cache jest natywny (zapisany kontekst). Dla Mitry trzymasz obiekt po `fit`, co przy `fine_tune=true` oszczędza najwięcej czasu.
- Polityka: LRU, limit pamięci GPU/RAM, TTL i endpoint `DELETE /cache/{id}`.
- W odpowiedzi zawsze podawaj `cache_hit: true/false`. Dobrze to wygląda na demo.

## 5. Interfejsy

**REST (dla skilla, przez Twingate):**

| Endpoint | Opis |
|---|---|
| `POST /datasets` | upload pliku, `url` albo `source`+`sql`, zwraca `dataset_id` |
| `GET /datasets/{id}` | schemat, braki, kilka wierszy |
| `GET /sources`, `GET /sources/{name}` | lista baz i ich schemat |
| `POST /predict` | `train`, `target`, `test?`, `backend`, `task`, `use_cache`, `fine_tune`, `features?` |
| `POST /evaluate` | holdout score dla tych samych parametrów |
| `GET /results/{id}/download` | CSV/Parquet z wynikami |
| `GET /info` | modele, limity, formaty |

Dla wygody `/predict` przyjmuje też plik bezpośrednio, a zbiór tworzy się wtedy w tle. Jeden `curl` nadal wystarcza.

**MCP (Streamable HTTP pod `/mcp`, te same funkcje pod spodem):**

| Narzędzie | Argumenty |
|---|---|
| `create_upload_link` | brak; zwraca link do strony uploadu |
| `list_datasets` | brak; pozwala znaleźć świeżo wgrany plik bez wklejania ID |
| `dataset_from_url` | `url` |
| `list_sources` / `describe_source` | `source?`, `table?` |
| `dataset_from_query` | `source`, `sql` |
| `describe_dataset` | `dataset_id` |
| `predict` / `evaluate` | jak w REST, ale z `dataset_id` |
| `get_result` | `result_id`, `limit` (podgląd do ~20 wierszy) |

Wynik `predict` zawiera streszczenie, krótki podgląd i link do pobrania. Pełne dane nie trafiają do kontekstu.

MCP serwujesz z tego samego bento, montując aplikację ASGI (FastMCP). Jeden artefakt obsługuje wtedy REST i MCP. Składnię montowania sprawdź w aktualnej dokumentacji BentoML.

## 6. Autoryzacja ścieżki publicznej

- Claude obsługuje serwery bez autoryzacji oraz z OAuth. Docelowo wybierz OAuth (FastMCP ma gotowe providery). Callback to `https://claude.ai/api/mcp/auth_callback`.
- Na demo prościej: dokumentacja wspomina też uwierzytelnianie nagłówkami żądania, więc sprawdź, czy jest dostępne w Twoim planie.
- Anthropic odradza allowlistę IP jako jedyne zabezpieczenie, choć dopuszcza ją, gdy OAuth nie jest wykonalny.
- Link uploadu ma być jednorazowy, krótko ważny, bez aplikacyjnego limitu rozmiaru. Zbiory przypisuj do właściciela (tożsamość z OAuth).

## 7. Skill

`SKILL.md` opisuje: kiedy użyć narzędzia, przepływ (`/info`, zbiór, `describe`, `evaluate`, `predict`), przykłady `curl` dla pliku, URL i SQL, parametry `backend`/`use_cache`/`fine_tune` oraz zasadę *„nigdy nie przepisuj rekordów, zawsze plik albo SQL"*.

## 8. Repo

```
bento-tabular/
├── service.py        # bramka: REST + montaż MCP
├── models/tabicl_svc.py, mitra_svc.py
├── core/datasets.py  # rejestr, Parquet, TTL
├── core/sources.py   # DuckDB, walidacja SQL
├── core/cache.py
├── mcp_app.py        # FastMCP, auth
├── upload_page/      # prosta strona HTML
├── sources.yaml, bentofile.yaml, download_weights.py
├── deploy/           # docker compose: bento, Twingate connector, tunel/proxy
├── skill/SKILL.md
└── demo/             # CSV + baza Postgres z danymi testowymi
```

## 9. Kolejność budowy

1. Test zależności: TabICL i Mitra w jednym środowisku czy osobno. To decyduje o architekturze serwisów.
2. Rejestr zbiorów i loader DuckDB (pliki, potem bazy).
3. Serwisy modelowe i `/predict`, `/evaluate` lokalnie na CPU.
4. Cache.
5. Build i containerize, wdrożenie na GPU.
6. Twingate i skill, test z Claude Code.
7. MCP, strona uploadu, auth, publiczny tunel, test z Claude web.
8. Demo na Postgresie z danymi testowymi i nagranie planu B.

Uwaga do prezentacji: w 15 minutach pokaż najwyżej dwie ścieżki, np. skill z plikiem i Claude web z SQL. Reszta może zostać na slajdzie „co jeszcze potrafi".

Sources:
- [Building custom connectors via remote MCP servers](https://support.claude.com/en/articles/11503834-building-custom-connectors-via-remote-mcp-servers)
- [FAQ katalogu MCP (wymagania sieciowe)](https://support.claude.com/fr/articles/11596036-faq-du-repertoire-mcp-distant-d-anthropic)
- [Custom connectors: autoryzacja](https://claude.com/docs/connectors/custom)
