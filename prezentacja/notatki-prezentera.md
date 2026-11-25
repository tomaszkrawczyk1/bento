# BentoML: notatki prezentera

Około 15 minut. Slajdy 16–17 są zapasowe. W HTML: strzałki, F (pełny ekran), N (notatki), O (spis), ? (pomoc). Przycisk demo odtwarza zapis, nie uruchamia modelu.

## 1. BentoML (0:30)

Cel prezentacji: pokazać, jak BentoML pomaga uruchomić modele jako stale dostępną usługę. Modele są przykładami obciążeń. Głównym tematem jest warstwa serwowania i integracja. Projekt działa na jednym PC z GPU, do którego można podłączyć kilka klientów.

## 2. Po uruchomieniu modelu zaczyna się obsługa usługi (1:00)

Prosty skrypt wystarcza do jednego eksperymentu. W naszym projekcie chcemy obsłużyć laptop, klienta przeglądarkowego i współpracownika, a także kilka środowisk modeli. Te wymagania można zrealizować samodzielnie, również w FastAPI. BentoML daje gotową strukturę serwisu i mechanizmy jego uruchamiania. Nie twierdzimy, że sam framework poprawia jakość predykcji.

## 3. Czym jest BentoML (1:00)

BentoML dostarcza strukturę do serwowania modeli. Service jest podstawową jednostką. API udostępnia metodę przez HTTP. Bento to format pakowania aplikacji. W naszym wdrożeniu używamy runtime BentoML i własnych obrazów Docker, co rozróżnimy na slajdzie o wdrożeniu. Źródła: <a href="https://docs.bentoml.com/en/latest/build-with-bentoml/services.html" target="_blank" rel="noopener">BentoML Services</a> oraz <a href="https://docs.bentoml.com/en/latest/get-started/packaging-for-deployment.html" target="_blank" rel="noopener">Packaging for deployment</a>.

## 4. Serwis modelowy w naszym projekcie (1:15)

Pokaż prawdziwy kod. Dekorator service zawiera deklarację GPU, liczbę workerów i konfigurację ruchu. Dekorator api udostępnia metodę run. LOCK to już nasza blokada. Faktyczny dostęp do GPU przydziela Docker z NVIDIA Container Toolkit, a nie samo resources. Używamy jednego workera, aby nie mnożyć kopii modelu. Parametr request ma typ dict, dlatego szczegółowe walidacje pól wykonuje nasz kod. Źródła: models/service.py i <a href="https://docs.bentoml.com/en/latest/build-with-bentoml/services.html" target="_blank" rel="noopener">Service definitions</a>.

## 5. REST i MCP w serwisie BentoML (1:00)

MCP jest protokołem wywoływania narzędzi przez agenta. W tym projekcie daje dostęp do tych samych operacji, które mamy w REST. FastMCP implementuje protokół, a aplikacja FastAPI łączy trasy. BentoML może montować aplikacje ASGI, dzięki czemu te interfejsy działają pod bramką. To integracja przez ASGI, a nie automatyczne generowanie naszego MCP przez BentoML. Kod na slajdzie pomija dodatkowe ustawienia, aby pokazać sam mechanizm. Źródło: <a href="https://docs.bentoml.com/en/latest/build-with-bentoml/asgi.html" target="_blank" rel="noopener">Mount ASGI applications</a> i app/gateway.py.

## 6. Cztery serwisy, jeden serwer GPU (1:10)

Gateway jest jedynym wejściem dla użytkownika. Modele mają wewnętrzne adresy w sieci Compose. Mitra wymaga odmiennego zestawu zależności, dlatego ma osobne środowisko. Każdy backend działa jako serwis BentoML w osobnym kontenerze, lecz wszystkie używają fizycznie tej samej karty. Komunikacja odbywa się przez httpx i HTTP. Nie używamy tutaj bentoml.depends. Kolejka między backendami jest naszą implementacją w SQLite. Źródła: compose.yaml, app/worker.py.

## 7. Co obsługuje framework, a co kod projektu (1:00)

To kluczowe rozróżnienie w projekcie o BentoML. Framework nie rozwiązuje całego problemu aplikacyjnego. Autoryzacja, źródła danych i spójna kolejka wielu modeli to nasz kod. BentoML ma dalsze mechanizmy, na przykład batching, ale nie pokazujemy ich jako wdrożonych. Źródła: kod aplikacji oraz <a href="https://docs.bentoml.com/en/latest/build-with-bentoml/observability/metrics.html" target="_blank" rel="noopener">metryki BentoML</a>. Healthcheck /readyz sprawdza gotowość serwera, nie gwarantuje, że każdy model jest już w pamięci GPU.

## 8. Przebieg jednego zadania (1:00)

Wywołanie evaluate nie trzyma połączenia przez całą inferencję. Zwraca identyfikator zadania. Nasz worker odbiera rekord z SQLite i wywołuje API odpowiedniego modelu. Klient sprawdza status najwyżej raz na trzy sekundy. Domyślnie brak backend oznacza tabicl, czyli TabICLv2. Przy predict trzeba przekazać osobny zbiór testowy. Ewaluacja oddziela dane testowe od fit. Źródła: app/store.py, app/worker.py, app/gateway.py.

## 9. Dane z Kaggle zostają na serwerze (1:00)

Import Kaggle nie wymaga pobierania pliku przez LLM. Token jest sekretem serwera. Ponowne użycie tej samej wersji i pliku wykorzystuje cache. Strumieniowy zapis pozwala uniknąć wczytywania całego surowego pliku do RAM-u. Dla dużych zbiorów można wybrać row_limit i columns, aby ograniczyć zużycie pamięci. Row_limit wybiera początkowe wiersze, a nie próbę losową. Oddzielnie działają cache modelu i wyników. Wyniki ewaluacji mogą pokazywać rzeczywiste etykiety części testowej. Źródło: app/kaggle_source.py.

## 10. Uruchamianie i wdrożenie (1:00)

Ważne: nie nazywaj aktualnego obrazu samowystarczalnym Bento. Mamy własny Dockerfile z runtime, a wagi i środowiska są montowane z PC. To upraszcza pracę demonstracyjną i oszczędza miejsce, ale wiąże deployment ze ścieżką hosta. Standardowy cykl BentoML potrafi zbudować wersjonowany pakiet i skonteneryzować go. To naturalny następny krok. Docker faktycznie udostępnia GPU. Nie korzystamy z BentoCloud. Źródło: deploy/Dockerfile, compose.yaml i <a href="https://docs.bentoml.com/en/latest/get-started/packaging-for-deployment.html" target="_blank" rel="noopener">Packaging for deployment</a>.

## 11. Dostęp dla agentów i współpracownika (0:45)

Autoryzacja jest częścią aplikacji i infrastruktury, a nie funkcją samego dekoratora BentoML. Każdy współpracownik dostaje osobną tożsamość. Zbiory i zadania są filtrowane po workspace. Nie pokazuj tokenów podczas demo. W kliencie przeglądarkowym żądania wysyła serwer usługi, dlatego mamy publiczną drogę HTTPS. Stały adres obsługuje Caddy na własnym VPS, który łączy się z PC przez Tailscale. Pełniejszy dostawca tożsamości pozostaje dalszym usprawnieniem. Źródło: README, app/security.py, app/oauth.py, deploy/nginx.conf.

## 12. Demo: Kaggle i domyślny TabICLv2 (1:30)

Na żywo pokaż klienta MCP i wyślij widoczny prompt. Zacznij od model_info, potem kaggle_dataset_info oraz dataset_from_kaggle. Agent nie powinien używać kolumn id, diagnosis jako cechy ani Unnamed:32. Brak backend ma uruchamiać TabICLv2. Jeśli sieć lub klient nie działa, przycisk odtwarza statyczny zapis wcześniejszego realnego testu. Nie sugeruj, że animacja wykonuje inferencję. Pokazane accuracy pochodzi z pojedynczego holdoutu, nie z walidacji klinicznej. Źródło: benchmarks/kaggle/smoke.json, test z 4 listopada 2026.

## 13. Pomiary mają różne zakresy (1:00)

Nie odejmuj tych czasów i nie przedstawiaj jako jednego żądania. Pierwsze trzy pomiary są z testu Kaggle, ostatni zakres z wcześniejszego testu agentów. Czas modelu obejmuje przygotowanie, fit i predict, nie sam forward GPU. W testach od promptu do wykresu klasyfikacja trwała 78,41 s, regresja 84,16 s, pogoda 82,91 s. To pokazuje, że praca agenta i danych ma duży udział, ale nie rozdziela ilościowo wszystkich źródeł opóźnień. Źródła: benchmarks/kaggle/smoke.json oraz benchmarks/end-to-end/20261104T184559Z/timings.json.

## 14. Korzyści i ograniczenia (1:00)

BentoML nie zastępuje dobrego podziału danych, autoryzacji ani zarządzania miejscem na dysku. Nie poprawia samodzielnie accuracy. W projekcie jedna GPU i jedna kolejka upraszczają demo kosztem przepustowości. Runtime wystawia metryki, lecz nie mamy gotowego dashboardu ani monitoringu driftu. Zestaw zalet jest oceną architektury tego projektu, a nie twierdzeniem o przewadze wydajnościowej nad dowolnym innym frameworkiem.

## 15. Rola BentoML w tym projekcie (0:45)

Wróć do głównego tematu: BentoML odpowiada za serwowanie, a model jest obciążeniem wewnątrz usługi. Wykonaliśmy integrację z rzeczywistymi modelami i klientem MCP, a nie tylko prosty endpoint hello world. Można zakończyć pytaniem, które warstwy należałoby zmienić przy przejściu na kilka serwerów GPU. Zapasowe slajdy zawierają wykres z wcześniejszego testu i źródła.

## 16. Zapas: wynik z wcześniejszego testu agenta (Zapas)

Ten wykres jest oryginalnym artefaktem z wcześniejszego testu agenta, a nie ilustracją wygenerowaną dla prezentacji. Różnica accuracy względem testu Kaggle wynika z odrębnego przebiegu i reprezentacji danych. Nie porównuj obu wartości jako eksperymentu przewagi modeli. Źródło: benchmarks/end-to-end/20261104T184559Z/classification/.

## 17. Źródła i kod projektu (Zapas)

Checkpointy na serwerze: tabicl-classifier-v2-20260212.ckpt i tabicl-regressor-v2-20260212.ckpt. Oficjalne repozytorium wskazuje je jako bieżące wersje v2. Źródła zweryfikowano 4 listopada 2026. Wszystkie wartości pomiarów w prezentacji pochodzą z zapisanych plików projektu.