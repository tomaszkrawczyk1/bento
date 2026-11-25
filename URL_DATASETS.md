# Import datasetów przez URL

MCP: `dataset_from_url(url, options={...})`. REST: `POST /datasets` z JSON
`{"url":"…", "options":{…}}`. Pobieranie i cache działają na PC, także gdy Claude
nie ma własnego środowiska Python/sieci. Odpowiedź zawiera `dataset_id`, liczby,
schemat i SHA, bez rekordów źródłowych. Dataset można przekazać do zwykłych
`evaluate`, `predict` i `forecast`; importer nie zawiera logiki konkretnej dziedziny.

## Obsługiwane mechanizmy

| Sposób udostępnienia | Obsługa |
|---|---|
| Bezpośredni HTTP/HTTPS | Rozpoznawanie bajtów, MIME i Content-Disposition; rozszerzenie URL nie jest wymagane; przekierowania |
| Podpisany URL | S3 presigned, GCS signed, Azure SAS i analogiczne linki HTTP; query nie jest przebudowywane bez potrzeby adaptera |
| Object storage URI | `s3://bucket/key`, `gs://bucket/key`, `gcs://…`, `abfs[s]://container@account.dfs.core.windows.net/key` → HTTPS; prywatne obiekty wymagają podpisanego URL lub profilu |
| FTP/FTPS | Pobranie konkretnego pliku; anonimowo lub z profilem; FTPS weryfikuje certyfikat |
| SFTP | Konkretny plik; profil z użytkownikiem, hasłem/kluczem oraz przypiętym fingerprintem klucza hosta |
| GitHub/Gist | Link `blob`, raw, katalog repozytorium/ścieżki, API contents i gist; wybór pliku przez `resource` |
| GitLab/Bitbucket | Link GitLab `/-/blob/` → raw (także własny host z `provider=gitlab`); Bitbucket `src` → API |
| Hugging Face | Link blob/resolve, katalog datasetu, `hf://datasets/owner/repo[@revision]/file`; katalogi API ze stronicowaniem |
| Kaggle | `/datasets/owner/slug`, również `?select=file.csv`; istniejący wersjonowany cache/SDK; CSV i Parquet |
| Google Drive | `file/d/ID/view`, `open?id=ID`, link bezpośredni, publiczny formularz potwierdzenia pobrania; folder przez Drive API wymaga dostępu w profilu |
| Google Sheets | Link edycji → eksport CSV, `gid` z fragmentu/query/opcji; publikowane arkusze `/d/e/…/pub` |
| Dropbox | Linki `s` i `scl/fi` → `dl=1`; linki bezpośrednie |
| OneDrive/SharePoint | Publiczne linki pobrania, przekierowania `1drv.ms`, `download=1`; Graph shares dla `provider=onedrive` z autoryzacją profilu |
| Zenodo/Figshare | Strona rekordu/artykułu → API → wybór pliku |
| Dataverse | `dataset.xhtml?persistentId=…` → katalog plików API; `file.xhtml?fileId=…` → plik |
| OSF | Krótki link **pliku** → API → download; bezpośrednie linki download; link projektu nie jest linkiem pliku |
| DOI | `doi:10.…`/`https://doi.org/…` → przekierowania do repozytorium; końcowa strona musi udostępniać rozpoznawalny plik/metadane |
| CKAN/DCAT/JSON-LD | API resources/distribution; `provider=ckan` zamienia stronę datasetu/resource na API; rozpoznanie generatora CKAN i linków HTML |
| Socrata | `/resource/ID.json`, CSV i inne eksporty; `provider=socrata` zamienia stronę z końcowym ID na JSON; offset/limit przez `pagination` |
| API JSON/OData | Tablice rekordów, tablice kolumn, zagnieżdżone records/results/data/value/items/hourly; dowolny `json_path` |
| API eksportu przez POST | `request={"method":"POST","json":{…}}` lub `form`; GET domyślnie; bez dowolnych metod zapisu |
| WebDAV/Nextcloud/inne serwery | Bezpośredni publiczny link GET/download lub profil HTTP Basic/Bearer/cookies; znalezione linki HTML; brak klienta WebDAV PROPFIND |
| Strona HTML/katalog | Linki do plików/download/export, dane JSON-LD, meta refresh; kilka plików → wybór; opcjonalnie import samej tabeli HTML |

Nie istnieje uniwersalny protokół „każdy URL jest datasetem”. Strona za CAPTCHA,
niezaakceptowanym regulaminem, wygasłym podpisem lub bez prawa dostępu nie daje
się pobrać samym importerem. Aplikacje wymagające wykonania JS i własnego procesu
logowania mogą wymagać uzyskania URL eksportu przez agenta/przeglądarkę. Importer
nie wykonuje skryptów strony i nie przejmuje ciasteczek przeglądarki użytkownika.
Foldery SFTP/FTP, prywatne listowanie bucketów, projekty OSF oraz wieloplikowe
formaty takie jak Zarr/Delta/Iceberg nie są automatycznie materializowane.
Nie ma gwarancji działania każdego wariantu linku danej usługi: operator musi
zapewnić dostęp, a usługi mogą zmieniać endpointy/zasady.

## Format danych i opcje

- Tabele: CSV, TSV, tekst rozdzielany przecinkiem/średnikiem/tabulatorem/pionową kreską,
  JSON, JSONL/NDJSON, GeoJSON, Parquet, Excel XLS/XLSX/XLSB, ODS, Arrow IPC/Feather,
  ORC, Avro, XML, HTML, SQLite, NumPy NPY/NPZ i numeryczne/strukturalne HDF5.
- Kompresja/archiwa: ZIP, TAR, TAR.GZ/TGZ, GZIP, BZ2, XZ i Zstandard, również
  zagnieżdżone. Osiem warstw to ochrona struktury, nie limit rozmiaru danych.
  RAR/7z i formaty uruchamiające kod (np. pickle/joblib) nie są dekodowane.
- `selection_required` zwraca nazwy plików, arkuszy, tabel lub tablic. Powtórz
  wywołanie z `resource`, `member`, `sheet`, `table` lub `array`.
- `member` przyjmuje też listę albo glob, np. `data/*.parquet`: zgodne partycje
  są łączone pionowo; różne schematy powodują błąd zamiast cichego łączenia.
- `format` nadpisuje rozpoznanie; `encoding`, `delimiter`, `decimal`, `header`,
  `csv_skiprows`, `comment`, `na_values` opisują CSV. UTF BOM i separator są
  wykrywane. Typowy dwuwierszowy blok metadanych przed tabelą o innej szerokości
  jest rozpoznawany; przy innych preambułach ustaw `csv_skiprows`.
- `json_path` (np. `result.records` lub `/result/records`) i `xml_path` wybierają tabelę.
- `columns`, `rename`, `parse_dates` i `row_limit` służą jawnej selekcji/konwersji;
  `row_limit` oznacza pierwsze N rekordów. Brak domyślnego limitu pliku/wierszy/kolumn.
- `inspect=true` zwraca rozpoznany schemat bez rejestrowania datasetu (dla katalogu
  najpierw wybór pliku; dla Kaggle lista plików i wersja).
- Stronicowanie JSON: RFC Link `rel=next`, OData `@odata.nextLink`, JSON `next`,
  `links.next`, `pagination.next`, `result._links.next`; Drive `nextPageToken`.
  Offset/page: `pagination={"mode":"offset","parameter":"$offset",
  "limit_parameter":"$limit","page_size":1000,"start":0}`.
  Parametry pierwszej strony również zostaną ustawione. `paginate=false` jest
  świadomym wyborem pojedynczej strony. `max_pages` powoduje błąd, jeśli pozostają
  strony — nigdy nie przedstawia częściowego zbioru jako kompletnego.
- API POST: `request={"method":"POST","json":{"query":"…"}}`; opcjonalnie `form`.
  Zabezpieczenie odrzuca przenoszące body przekierowania POST na inny host.

```json
{"url":"https://github.com/mwaskom/seaborn-data/blob/master/iris.csv"}
```
```json
{"url":"https://example.org/export?id=123","options":{"json_path":"result.records","pagination":{"page_size":1000}}}
```
```json
{"url":"https://example.org/dataset.zip","options":{"member":"train/*.parquet"}}
```

## Cache i dostęp

Surowe pobrania są w `data/url-cache/`, oddzielnie dla workspace, URL, profilu i
opisu żądania. Domyślny TTL to 3600 s (`cache_ttl`), `refresh=true` wymusza
pobranie. Integralność sprawdzana SHA-256; zapis atomowy i blokada pobierania.
Bajty pobrania są strumieniowane na dysk. Nie ma narzuconego limitu rozmiaru
cache; operator monitoruje wolne miejsce. Rejestr datasetów ma dotychczasowy TTL
7 dni, niezależny od surowego cache. Parsowanie tabeli nadal wymaga RAM.
Podpisane URL są przechowywane wyłącznie w chronionym cache serwera i nie są
zwracane w opisie datasetu. Powtórny odczyt API może sprawdzać strony z cache,
żeby nie zwrócić starej połączonej tabeli po zmianie jednej strony.

Prywatne źródła: plik `.credentials/url-sources.json`, tylko sekret kontenera
gateway (`/run/secrets/url-sources.json`), nigdy modelu ani agenta:

```json
{"profiles":{"team-storage":{"workspaces":["bento-team"],"hosts":["files.example.org"],"bearer_token":"REPLACE_ON_SERVER"}}}
```

Wywołanie zawiera tylko `options.auth_profile="team-storage"`. Profil może mieć
`headers`, `bearer_token`, `basic:{username,password}`, `cookies`, `query`;
SFTP dodatkowo `username`, `password`/`private_key` i `host_key_sha256`.
Hosty to dokładne nazwy małymi literami, bez wildcardów. Sekrety nie przechodzą
na inne hosty przekierowania. `allow_private=true` dopuszcza prywatny adres tylko
dla wskazanego hosta; domyślnie prywatne IP są blokowane, DNS sprawdzany i IP
przypinane na każdym przekierowaniu. `URL_ALLOWED_HOSTS` może dodatkowo ograniczyć
ruch. `allow_insecure=true` umożliwia HTTP z profilem — domyślnie wymaga HTTPS.
Po zmianie sekretu zamontowanego przez Compose odtwórz kontener gateway.

## Weryfikacja

`python -m tests.url_unit`: 43 testy z prawdziwymi parserami i kontrolowanym HTTP:
formaty, kompresje, selekcja, łączenie partycji, stronicowanie, POST, cache,
współbieżność, izolacja workspace, przekierowania, SSRF i wyciek autoryzacji.
`python -m tests.kaggle_unit`: 11 istniejących testów cache/prywatności Kaggle.
`KAGGLE_CONFIG_DIR=.credentials python -m tests.url_live`: 8 udanych importów
rzeczywistych źródeł: GitHub blob i katalog, API JSON bez rozszerzenia, UCI ZIP,
Hugging Face blob i katalog, Google Sheets, Kaggle. Wyniki: `benchmarks/url-import/live.json`.
`python -m tests.url_mcp_smoke`: 5 importów przez publiczny HTTPS MCP, opcje REST,
blokada pobierania źródłowych rekordów i SSRF. Dodatkowo przeszły testy OAuth
PKCE i izolacji/revokacji kont.
Pozostałe serwisy mają testy adapterów lub wspólnego transportu; bez twierdzenia,
że zweryfikowano logowanie do każdego prywatnego konta/usługi.

## Dokumentacja źródłowa adapterów

- [GitHub contents API](https://docs.github.com/en/rest/repos/contents),
  [GitLab files API](https://docs.gitlab.com/api/repository_files/),
  [Bitbucket file download](https://support.atlassian.com/bitbucket-cloud/kb/how-to-download-specific-files-from-a-bitbucket-repository/).
- [Hugging Face downloads](https://huggingface.co/docs/hub/datasets-downloading),
  [Dropbox download URLs](https://help.dropbox.com/share/force-download),
  [OneDrive Graph shares](https://learn.microsoft.com/en-us/graph/api/shares-get),
  [Google Drive downloads](https://developers.google.com/workspace/drive/api/guides/manage-downloads).
- [S3 presigned URL](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html),
  [GCS public data](https://docs.cloud.google.com/storage/docs/access-public-data).
- [CKAN API](https://docs.ckan.org/en/latest/api/), [Socrata endpoints](https://dev.socrata.com/docs/endpoints),
  [Figshare API](https://docs.figshare.com/v2/), [Zenodo API](https://developers.zenodo.org/),
  [OSF API](https://developer.osf.io/), [Dataverse API](https://guides.dataverse.org/en/latest/api/dataaccess.html).
- [pandas readers and formats](https://pandas.pydata.org/docs/user_guide/io.html).
