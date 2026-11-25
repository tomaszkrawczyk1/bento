# Bento Tabular GPU

## Publiczne demo — wypróbuj bez konta

Serwer MCP działa na prawdziwym GPU (RTX 5060 Ti) i jest dostępny dla każdego
przez ten adres. Token w URL jest **celowo publiczny**:

```
https://vmi3696773.contaboserver.net/t/8kC0m5YMyRpNqoX8v4TU-CLGZMDMKcdySwwbmgm2fhE/mcp
```

- **Claude (web/desktop):** Settings → Connectors → *Add custom connector*, wklej adres,
  bez logowania. Potem w rozmowie np. „weź dataset cen domów i zrób regresję” albo
  „jaka będzie jutro pogoda w Katowicach”.
- **Claude Code:** `claude mcp add --transport http bento-demo 'https://vmi3696773.contaboserver.net/t/8kC0m5YMyRpNqoX8v4TU-CLGZMDMKcdySwwbmgm2fhE/mcp'`

Limity publicznego workspace `public` (osobnego od właściciela):
**100 zadań GPU łącznie** dla wszystkich użytkowników razem, **100 MB na plik**
(pobranie, rozpakowanie i upload), 30 żądań/min na IP, brak dostępu do Kaggle.
Zbiory w tym workspace są wspólne dla wszystkich korzystających z demo, więc nie
wgrywaj prywatnych danych. Wykorzystanie limitu pokazuje narzędzie `model_info`
(`public_demo_quota`). Demo działa, gdy domowy PC jest włączony; nie ma gwarancji
dostępności. Gdy limit się skończy, uruchom projekt u siebie (sekcje niżej).
Konfiguracja limitów: `LIMITED_WORKSPACES` (domyślnie `public`), `LIMITED_JOB_QUOTA`
(100), `LIMITED_MAX_BYTES` (104857600); kod w `app/quota.py`, test `tests.quota_unit`.
Nowy publiczny token: `scripts/manage.py add-user --email <adres> --workspace public`.

Działające wdrożenie na `pc@pc`, `/home/pc/sandbox/bento`.
BentoML udostępnia REST i Streamable HTTP MCP oraz trzy izolowane procesy GPU:
TabICLv2 (domyślny backend `tabicl`), Mitra-v2 i Timestral-209M. Jedna trwała kolejka wykonuje zadania kolejno na RTX 5060 Ti.
Zbiory i wyniki są niezmiennymi plikami Parquet z identyfikatorami, metadanymi
w SQLite i ważnością 7 dni. Modele korzystają z lokalnych wag, `HF_HUB_OFFLINE=1`.

## Dane z Kaggle

Agent wywołuje `kaggle_dataset_info(reference="uciml/iris")`, wybiera plik
i przekazuje `dataset_from_kaggle(reference="uciml/iris", file="Iris.csv", version=2)`.
Może też podać link `https://www.kaggle.com/datasets/uciml/iris`.
Serwer korzysta z oficjalnego SDK Kaggle, pobiera wybrany CSV/Parquet i zwraca
`dataset_id`, schemat, liczbę wierszy, wersję, licencję i `cache_hit`.
Agent przekazuje identyfikator do `evaluate`, `predict` lub `forecast`.
Nie pobiera zbioru na swoją maszynę. Przykładowe rekordy źródłowe i linki do ich
pobrania są zablokowane również przez `describe_dataset` i endpointy wyników.
Wyniki modeli pozostają dostępne: prognozy, predykcje, metryki i wartości
docelowe testowego podzbioru w ewaluacji. To kontrola interfejsu aplikacji;
administrator z SSH ma dostęp do plików na serwerze.

Poświadczenia właściciela: `.credentials/kaggle.json`, tryb 600, poza repozytorium.
Docker montuje je jako `/run/secrets/kaggle.json` **wyłącznie w gateway**.
Nie trafiają do obrazu, modeli ani odpowiedzi MCP. Korzystają z nich członkowie
workspace `bento-team`; pozostałe zespoły mają domyślnie wyłączony Kaggle.
Każdy dopuszczony zespół może importować także prywatne zbiory dostępne temu kontu,
jeśli zna ich identyfikatory. Nie włączaj tej funkcji dla niezaufanych zespołów.
Zmiany listy dopuszczonych workspace: `KAGGLE_WORKSPACES` w compose.
Na nowym serwerze bootstrap tworzy pusty plik `{}`; import pozostaje wyłączony,
dopóki operator nie umieści w nim poprawnych `username` i `key` z konta Kaggle.

Cache: `data/kaggle/`, osobny klucz dla zespołu, zbioru, wersji i pliku.
Ponowne wywołanie z tą samą wersją i plikiem nie wymaga połączenia z Kaggle.
Bez wersji serwer sprawdza aktualną wersję; zmiana tworzy nowy wpis.
Pliki są zapisywane atomowo, sprawdzane SHA-256 i chronione blokadą przed
równoległym pobieraniem. Identyfikator zaimportowanej tabeli wygasa po 7 dniach,
ale jest odtwarzany z cache bez ponownego pobierania. Cache surowych plików jest
trwały, bez domyślnego limitu aplikacyjnego (`KAGGLE_CACHE_BYTES=0`). Operator może
ustawić dodatnią kwotę. Pobieranie, rozpakowywanie i SHA-256 działają strumieniowo
na dysku. Niepotrzebne katalogi można usuwać przy zatrzymanym gateway. Nie usuwaj `.lock`.

Obsługiwane są **datasets**, bez competitions, obrazów, archiwów użytkownika
i automatycznego akceptowania warunków dostępu. Pobierany jest wybrany plik,
nie całe archiwum zbioru. Aplikacja nie narzuca limitu rozmiaru pliku, również
po rozpakowaniu. Pozostają dostępne miejsce na dysku i limity zewnętrznego proxy/klienta.
Brak aplikacyjnego limitu liczby wierszy i kolumn. `columns` wybiera kolumny, a jawny
`row_limit` wybiera pierwsze N wierszy; nie jest to próba losowa.

REST w prywatnej sieci: GET `/kaggle/info?reference=uciml/iris`, POST `/datasets`
z JSON `{"kaggle":"uciml/iris","file":"Iris.csv","version":2}`.
Testy: `.venv/bin/python -m tests.kaggle_unit` (bez sieci) oraz
`.venv/bin/python -m tests.kaggle_smoke` (publiczny MCP, Kaggle i prawdziwy GPU).

## Połączenie

Twingate: grupa **Bento Project**, zasób **Bento Tabular GPU**.
Adres `http://bento.internal:3000`; dozwolony TCP 3000, UDP i ICMP zablokowane.
Connector Twingate działa na PC w kontenerze `bento-twingate`.
Zainstaluj klienta Twingate i zaloguj się kontem dodanym do grupy.
Każdy użytkownik aplikacji otrzymuje własny klucz i hasło.

Dane właściciela są wyłącznie na PC:
`.credentials/owner.json` (uprawnienia 600).
Nie dodawaj tego pliku do repozytorium. Pole `api_key` służy do REST/MCP klienta,
`password` do formularza OAuth w przeglądarce.

Claude Code, przez Twingate:
```bash
claude mcp add --transport http bento http://bento.internal:3000/mcp/ \
  --header "Authorization: Bearer $BENTO_API_KEY"
```
OpenCode v2 (wersja na laptopie: 2.0.32) — fragment konfiguracji:
```json
{
  "mcp": {
    "servers": {
      "bento": {
        "type": "remote",
        "url": "http://bento.internal:3000/mcp/",
        "oauth": false,
        "headers": {"Authorization": "Bearer {env:BENTO_API_KEY}"}
      }
    }
  }
}
```
Gotowy przykład: `deploy/opencode.example.json`. OpenCode v1 używa wpisu
bezpośrednio pod `mcp`, bez pośredniego `servers`.
Dokumentacja: https://opencode.ai/v2/docs/mcp-servers

Jeśli używasz publicznego MCP, skopiuj aktualną bazę z `deploy/public-url.txt`
i dopisz `/mcp/`. Dla Claude web dodaj custom connector z tym adresem i przejdź
logowanie OAuth. Metadane OAuth i rejestracja klienta są dostępne publicznie.

**Stały adres publiczny:** `https://vmi3696773.contaboserver.net/mcp`.
Na `srv@srv` działa Caddy z automatycznym certyfikatem HTTPS. Proxy łączy się
przez Tailscale do `pc` (`100.77.87.6:3003`), a następnie nginx kieruje ruch do
BentoML. Stary Cloudflare Quick Tunnel jest wyłączony, żeby nie nadpisywał adresu.
Proxy udostępnia tylko MCP/OAuth, upload, download i health. REST i porty modeli
pozostają prywatne. Caddy startuje automatycznie po restarcie VPS.
Konfiguracja: `deploy/vps/Caddyfile`, na VPS w `/etc/caddy/Caddyfile`.

To projekt demonstracyjny; własny serwer OAuth obsługuje kod PKCE i tokeny dostępu ważne
1 godzinę z rotowanymi refresh tokenami (30 dni). Nie zastępuje pełnego dostawcy tożsamości.

## Dodanie współpracownika

1. Twingate → Team → Users → dodaj osobę, a następnie do grupy **Bento Project**.
   Grupa ma już dostęp do jednego zasobu aplikacji. Nie wymaga nadawania Admina.
2. Na PC utwórz osobne konto w tym samym workspace:
   ```bash
   cd /home/pc/sandbox/bento
   .venv/bin/python scripts/manage.py add-user --email kolega@example.org --workspace bento-team
   ```
3. Przekaż tej osobie jej własny plik `.credentials/kolega@example.org.json`
   bezpiecznym kanałem. Nie przekazuj klucza właściciela ani tokenów connectora.
4. Osoba instaluje klienta Twingate i podpina MCP albo używa publicznego MCP z OAuth.
   Użytkownicy tego samego workspace widzą wspólne zbiory, wyniki i zadania.

Cofnięcie dostępu wymaga usunięcia z grupy Twingate i wykonania
`manage.py disable-user --email ...`, co unieważnia także dostęp publiczny.
Twingate i konto aplikacji to dwa niezależne uprawnienia.

## Obsługa

```bash
cd /home/pc/sandbox/bento
docker compose ps
docker compose logs --tail 100 gateway
docker compose up -d --build
# Stop bez usuwania danych:
docker compose stop
docker stop bento-twingate bento-public-proxy
systemctl --user stop bento-public-tunnel
```
Kontenery mają `restart: unless-stopped`. Tunel działa jako usługa użytkownika,
`Linger=yes`. Wznowienie: `docker compose start`, `docker start bento-twingate
bento-public-proxy`, ``.
Nie uruchamiaj drugiej bramki dla tej samej kolejki/bazy.

Obraz `bento-runtime:local` zawiera system i kod. Sprawdzone środowiska Pythona,
wagi i dane są montowane z katalogu projektu. Ułatwia to lokalne wdrożenie bez
kopiowania ponad 10 GB zależności do warstw obrazu. Klient MCP nie pobiera modeli.
Przeniesienie całego serwera wymaga Ubuntu 24.04, Python 3.12, Dockera, NVIDIA
Container Toolkit i zgodnego sterownika GPU; następnie `scripts/bootstrap.sh`.
Ścieżki w compose są dopasowane do wskazanego PC. Locki zapisują dokładne wersje.
Manifest checkpointów: `deploy/checkpoint-manifest.json`. Pobieranie wag jest
osobnym krokiem instalacji; runtime ich nie pobiera.

PostgreSQL demo działa w `bento-postgres-1`, bez opublikowanego portu.
`demo/compose.postgres.yaml` i `scripts/setup_postgres.py` tworzą dwie tabele
z przykładowych danych sklearn oraz użytkownika z SELECT. Sekrety są w `.env`.
Zatrzymanie: `docker compose --env-file .env -f demo/compose.postgres.yaml stop`.
Ponowne wykonanie skryptu resetuje wyłącznie te dwie demonstracyjne tabele.

## Przepływ pracy

1. `model_info`, następnie automatyczny import Kaggle/HTTPS URL lub SELECT.
   Dane wymagające przygotowania agent może sam przetworzyć i przesłać programowo.
2. `describe_dataset` i wybór target/features; nie używaj ID ani cech z przyszłości.
3. `evaluate`: zwraca `job_id`; `get_job` zwraca metryki i `result_id` po zakończeniu.
4. `predict`: train z targetem i osobny test bez targetu.
5. `get_result`: krótki podgląd oraz link do kompletnego CSV/Parquet, ważny 10 min.

Przeglądarkowy upload: `create_upload_link`, użytkownik otwiera jednorazowy link,
wgrywa plik i wraca do rozmowy. Pełne dane nie przechodzą przez kontekst agenta.
Skill z przykładami curl: [skill/bento-tabular/SKILL.md](skill/bento-tabular/SKILL.md).

Bez aplikacyjnego limitu wierszy, kolumn i maksymalnej liczby klas.
Klasyfikacja wymaga co najmniej dwóch klas. Rozmiar wykonalnej inferencji zależy od RAM/VRAM modelu.
Rozmiar pliku: bez limitu aplikacyjnego. Import dużego pliku z Kaggle może użyć
`row_limit` i `columns`, jeżeli chcesz ograniczyć zużycie pamięci przez wybraną tabelę.
Długie pobieranie może przekroczyć timeout klienta MCP; ponowienie wykorzysta
ukończony cache serwera. Gateway ma timeout 3600 s.
Budżet treningu 15–900 s; nie jest ścisłym limitem czasu całego zadania.
Przerwanie aktywnego zadania odrzuca jego wynik po zakończeniu obliczeń.
Automatyczny holdout jest losowy; podziały czasowe/grupowe przygotuj zewnętrznie.
SQL: jedna SELECT, allowlista tabel/funkcji, timeout i konto read-only. DSN jest
konfiguracją operatora, nie argumentem narzędzia. SQLite/PostgreSQL są sprawdzone;
MySQL jest zaimplementowany, bez testu integracyjnego z żywą bazą.
Import URL obsługuje linki bezpośrednie i udostępniania, API JSON, katalogi, archiwa
i wiele formatów tabel. Szczegóły, opcje i granice: [URL_DATASETS.md](URL_DATASETS.md).
`URL_ALLOWED_HOSTS` opcjonalnie ogranicza domeny importu.

## Modele i cache

- TabICL: klasyfikacja/regresja, 4 estymatory, natywny kontekst `repr`.
- Mitra: klasyfikacja ICL, opcjonalne dostrajanie; regresja wymaga
  `fine_tune=true`. Dostrajanie używa oficjalnego wrappera i 2 foldów.
- To konfiguracja demo, nie odtworzenie opublikowanego benchmarku.
- `use_cache=false` domyślnie. Cache jest ograniczony do 2 kontekstów na proces,
  8 dokładnych wyników i 30 min TTL; konteksty są usuwane przy zmianie backendu.
- Wrapper Mitry trenuje podczas `predict`, więc fine-tuning ma wyłącznie cache
  dokładnych wyników. Odpowiedź rozróżnia `cache_type=result` i `context`.
- DELETE `/cache/{context_id}` usuwa wpisy tylko danego workspace.

## Weryfikacja

`tests/smoke.py`, `tests/mitra_smoke.py`: rzeczywiste klasyfikacja i regresja GPU.
`tests/mcp_smoke.py`: wykrycie narzędzi i uwierzytelniony odczyt przez MCP.
`tests/oauth_smoke.py`: PKCE, błędny verifier, jednorazowość kodu, MCP przez HTTPS.
`tests/workspace_smoke.py`: współdzielenie i izolacja workspace, cofnięcie dostępu
oraz `/mcp` bez przekierowania. `tests/url_smoke.py`: HTTPS i blokada adresów lokalnych.
`tests/data_smoke.py`: SQL obu baz, odrzucenie DELETE, osobny test, cache i jego
usuwanie, jednorazowy upload i blokada publicznego REST.
Wyniki przykładowych ewaluacji: `demo/*verification.json`.

Różnice względem pierwotnego szkicu: SQL używa sterowników SQLite/psycopg/PyMySQL,
zamiast rozszerzeń DuckDB; ograniczenia zapytań i kont pozostają po stronie źródła.
Procesy BentoML porozumiewają się przez prywatne HTTP, mając osobne środowiska.
Upload plików odbywa się przez `/datasets` lub link uploadu; `/predict` przyjmuje ID.

Sprawdzono również rzeczywisty connector Claude web: logowanie zakończone,
13 narzędzi wykrytych przy pierwotnym wdrożeniu; obecnie MCP udostępnia 14, w tym forecast. Uprawnienia narzędzi pozostawiono na domyślnym „Needs approval”.
Konfiguracja OpenCode jest przykładem dla v2; działający w tle daemon nie przyjął
odrębnego `OPENCODE_CONFIG` użytego w izolowanej próbie CLI. Sam protokół MCP
jest zweryfikowany niezależnym klientem i przez Claude web.

## Timestral-209M: prognozowanie szeregów czasowych

Oficjalny model Mistrala: https://huggingface.co/mistralai/Timestral-209M
Kod: https://github.com/mistralai/timestral
Wagi (~837 MB) są lokalnie w `weights/timestral-209m`; wersja kodu i checkpointu
są przypięte w bootstrapie i manifeście. Model ma osobny kontener, współdzieli
kolejkę GPU i istniejący rejestr zbiorów. Runtime działa offline.

REST POST `/forecast`, MCP `forecast`. Przykład treści żądania:
```json
{
  "dataset": "ds_HISTORY",
  "targets": ["sales"],
  "timestamp": "timestamp",
  "series_id": "store_id",
  "prediction_length": 96,
  "past_covariates": ["observed_temperature"],
  "known_covariates": ["holiday"],
  "future": "ds_FUTURE",
  "use_cache": true
}
```
Historia: CSV/Parquet z regularnie rozmieszczonymi timestampami, opcjonalnym ID
szeregu i kolumnami numerycznymi. Co najmniej 32 zaobserwowane wartości na target.
Każda grupa series_id jest niezależnym szeregiem; wiele targetów w grupie jest
prognozowanych wspólnie. Horyzont 1–1024. Brak aplikacyjnego limitu grup, targetów, kolumn numerycznych i liczby wynikowych wierszy. Covariates są opcjonalne.

`past_covariates` są czytane wyłącznie z historii. `known_covariates` wymagają
zbioru future z dokładnie następnymi timestampami dla każdej grupy i wartościami
rzeczywiście znanymi w chwili prognozowania (np. kalendarz). Targety w future
są ignorowane. API wymaga stałego kroku czasu; covariates kategoryczne i
fine-tuning nie są obecnie udostępnione. Nie stosuj losowego holdoutu czasowego.

Po job_id użyj `/jobs/{id}` i `get_result`. Wynik ma timestamp, ID grupy, nazwę
targetu, medianę `prediction` oraz 21 kolumn kwantyli `q_*`. Dla wielu targetów
wynik jest w układzie długim: grupy × targety × horyzont.

Odpowiedź zawiera `load_model_seconds`, `inference_seconds` (CUDA zsynchronizowana),
`duration_seconds` całego przetwarzania, liczby wierszy/grup/zmiennych oraz
`gpu_peak_allocated_mib` PyTorch. Pierwsza inferencja może być wolniejsza od
kolejnej z powodu inicjalizacji bibliotek. Wagi pozostają w pamięci między
zadaniami Timestral; przejście do innego backendu je zwalnia. `use_cache=true`
przechowuje dokładny wynik, nie kontekst wytrenowanego modelu. Cache hit ma
`inference_executed=false` i `inference_seconds=0`; to odczyt, a nie nowa prognoza.

Test: `tests/timestral_smoke.py`. Wyniki i dane: `benchmarks/timestral/report.md`.
Sprawdzono rzeczywiste GPU, REST i publiczny MCP, wiele targetów/grup, obydwa
rodzaje covariates, chronologiczny holdout, 21 uporządkowanych kwantyli, cache oraz
brak wpływu przyszłych etykiet targetu. Są to testy integracyjne na syntetycznych
szeregach, nie odtworzenie oficjalnych benchmarków i nie porównanie accuracy
z tabularną klasyfikacją/regresją.

## Prezentacja projektu

[Prezentacja HTML](prezentacja/bentoml.html): 15 slajdów na około 15 minut i 2 zapasowe,
z naciskiem na BentoML. Działa offline. Klawisze: strzałki, F (pełny ekran),
N (notatki prezentera), O (spis). Przycisk demo odtwarza zapis wcześniejszego testu.
[Notatki prezentera](prezentacja/notatki-prezentera.md).

## Automatyczne pobieranie przez Claude web

Connector: **BentoML GPU**, URL `https://vmi3696773.contaboserver.net/mcp`.
Claude otrzymuje link lub nazwę zbioru. Dla Kaggle wywołuje `kaggle_dataset_info`
i `dataset_from_kaggle`, a dla linków plików, udostępniania i API `dataset_from_url(url, options)`.
Plik pobiera serwer. Dane Kaggle są cachowane po wersji i pliku, a agent dostaje
ID i schemat. Dla bezpośredniego importu URL/Kaggle nie potrzeba sieci w kontenerze Claude.
Twingate nie jest potrzebny dla Claude web: publiczny VPS przekazuje ruch MCP
przez Tailscale do PC. Własne klucze użytkowników pozostają na serwerze.

Jeżeli dane wymagają przygotowania, Claude może sam pobrać plik w środowisku
wykonawczym, przekształcić go i automatycznie przesłać wynik przez jednorazowy
`upload_endpoint` z `create_upload_link`. Nie wymaga to ręcznego uploadu użytkownika.
W Claude włączono dostęp do internetu przy pracy z plikami i tryb Any website.
MCP pozostaje ogólne: wybór danych, transformacje i zadanie należą do agenta.
Nie ma dedykowanego skryptu ani narzędzia pogodowego na serwerze.

## Logowanie tokenem (Claude web, bez panelu OAuth)

Connector dodaj jako *Add custom connector* z adresem
`https://<host>/t/<api_key>/mcp` i uwierzytelnieniem „No sign-in”. Klucz API to pole
`api_key` z `.credentials/<email>.json`. Gateway zamienia ścieżkę na nagłówek
`Authorization: Bearer`, więc nie pojawia się ekran logowania ani wygasanie po
godzinie. Klucz jest w URL: traktuj go jak hasło. Test: `tests/token_url_smoke.py`.
Caddy (VPS) i nginx (PC) przepuszczają `/t/*/mcp`.
