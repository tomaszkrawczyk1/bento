"""Measure three independent Paseo prompts until validated charts arrive locally."""
import concurrent.futures,datetime,json,struct,subprocess,time
from pathlib import Path
ROOT=Path('/home/laptop/studia/chmura');BASE=ROOT/'materialy/bento/benchmarks/end-to-end'
RUN=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ');OUT=BASE/RUN;OUT.mkdir()
( BASE/'latest.txt').write_text(str(OUT)+'\n')
common='''Jesteś jednym z 3 równolegle uruchomionych agentów testowych. Model gpt-6.1-sol, reasoning medium. Użytkownik chce zmierzyć rzeczywisty czas PROMPT -> GOTOWY WYKRES. Wykonaj zadanie sprawnie do końca. Nie deleguj dalej, nie zmieniaj aplikacji ani usług ani konfiguracji agenta. Masz autoryzację użytkownika na odczyt/dane/skrypty/wywołania API w folderze przedmiotu i projektu PC. Brak nagrywania. Nowa sesja została uruchomiona w full-access dla wykonania tego konkretnego zadania bez sztucznych postojów. Nie ustawiaj sandbox_permissions, używaj zwykłego exec. Jeśli realna odmowa/limit/błąd nastąpi, raportuj dokładnie i nie udawaj sukcesu.

Serwer SSH pc@pc jest dostępny kluczem, /home/pc/sandbox/bento. Skrypty możesz przygotować lokalnie i wykonać na PC przez SSH; .venv-mitra/bin/python ma httpx, sklearn, pandas, numpy, pyarrow, matplotlib. Nie instaluj niczego. Usługa REST http://127.0.0.1:3000 z PC. Klucz czytaj na PC z .credentials/owner.json, pole api_key; nie wypisuj go, nie kopiuj credentials na laptopa. Wszystkie prognozy WYŁĄCZNIE przez API, żadnego bezpośredniego importu/wczytywania modelu. Nie używaj starych predykcji ani cache: wymagane NOWE job_id, use_cache=false, cache_hit=false.

API: POST /datasets multipart file=(name,CSVbytes,text/csv) -> dataset_id. POST /evaluate JSON {train:dataset_id,target:target,backend:tabicl,task:classification,use_cache:false,seed:42,test_size:0.2,time_limit:30} -> job_id. POST /predict JSON {train:train_id,test:test_id,target:target,backend:tabicl,task:regression,use_cache:false,seed:2026,time_limit:30}. GET /jobs/{id} -> state oraz result; poll co 0.5-1 s. Wynik result_id pobierz GET /results/{id}/download -> Parquet, bezpośredni endpoint autoryzowany zamiast linków z tokenami. Jobs zwracają created, started, finished, spec i result z duration_seconds. Zapisz surowe odpowiedzi bez sekretów. Błędy HTTP odczytaj i popraw własnego klienta, nie aplikację. Kolejka GPU wspólna dla 3 zadań, uwzględnij ją w pomiarze.

Możesz przeczytać wymagane fragmenty materialy/bento/README.md i istniejące testy jako dokumentację. Nie odtwarzaj gotowych starych PNG, CSV z predykcjami ani jobów. Zapisz NOWE dane wejściowe, wynikowe CSV, job.json, metrics.json, własny skrypt i chart.png/chart.svg. metrics.json ma zawierać co najmniej: task, job_id, result_id, input_rows, train_rows/context_rows, test_rows/horizon, feature_count, server_duration_seconds, queue_seconds, worker_seconds, cache_hit i przydatne metryki jakości; dla Timestral także inference_seconds i load_model_seconds. Timestral ma rozdzielone inferencję i ładowanie, TabICL duration_seconds obejmuje przygotowanie/fit/predict — nie nazywaj go samym forward.

Ważny warunek końca: SPRAWDŹ poprawność wyników i czytelność wykresu, prześlij wszystkie artefakty z PC do podanego własnego lokalnego katalogu, a DOPIERO NA KOŃCU zapisz w tym katalogu plik done.json z {status:"success",job_id:...,chart:"chart.png",finished_at_utc:...}. Rodzic mierzy monotoniczny czas od wysłania tego promptu do pojawienia się done.json i kompletnego PNG lokalnie. Nie zapisuj done przed faktycznym ukończeniem, nie używaj zegara PC do wyznaczania czasu end-to-end. Wykres standardowy matplotlib, PNG min. 1000x600 oraz SVG, godziny/jednostki i źródła poprawnie opisane. Plik PNG nazwij dokładnie chart.png, nawet jeśli wykres ma dwa panele. Równolegli agenci mają inne katalogi — używaj tylko własnego. W final podaj wynik i ścieżkę, ale nie czekaj z publikacją done na rozbudowaną odpowiedź.
'''
tasks={
 'weather':'''Zrób prognozę godzinowej temperatury w Katowicach na jutro, 2026-11-05 00–23 Europe/Warsaw, przez Timestral-209M API i wykres z porównaniem do Interii. Pobierz świeżo historię obserwacji METAR EPKT z IEM i świeżo referencję Interii; znasz już źródła i działający kod, możesz go adaptować.

Gotowe, sprawdzone źródła/kod: materialy/bento/benchmarks/weather-katowice-2026-11-05/forecast_client.py (pobiera METAR IEM, 720 godzin historii i woła /forecast) oraz compare.py (porównuje i rysuje). WOLNO ponownie wykorzystać ten kod, ale PRZED wykonaniem ZMIEŃ OUT/PATH na SWÓJ katalog, ASOF na bieżący czas UTC, pobierz aktualne dane i utwórz NOWY job. Nie nadpisuj poprzedniego eksperymentu. Na PC nazwy katalogów odpowiadają podanym poniżej ścieżkom. Horyzont od ostatniej pełnej godziny historii do 2026-11-05 22:00 UTC (23 CET); wybierz 24 jutrzejsze godziny. Co najmniej 32 obserwacje, preferuj 720, regularna siatka UTC; żadnych przyszłych temperatur na wejściu. API POST /forecast {dataset:id,targets:[temperature_c],timestamp:timestamp,prediction_length:h,use_cache:false}; job.result podaje inference_seconds/load_model_seconds.

Interię odczytaj przez BrowserOS neo (narzędzie run), stosując dostępne instrukcje browseros-neo: otwórz WŁASNĄ kartę https://pogoda.interia.pl/prognoza-szczegolowa-katowice,cId,13095 . Jeśli zgoda zasłania, wybierz Przypomnij później. Znane selektory po aktualnej stronie: .weather-forecast z klasą 2026-11-5, w niej .weather-entry; godzina .entry-hour .hour; temperatura .forecast-temp (bez °C). DOM evaluate służy tu do wydobycia 24 faktów. Sprawdź nagłówek 5 Listopada; nie używaj starych snippetów. Zapisz własny interia-reference.json ze source_url, source_name, retrieved_at_utc, forecast_date, timezone i hourly[{hour,temperature_c,timestampISO+01:00}]. Nie podawaj Interii modelowi. Model ma niezależnie ekstrapolować historię stacji EPKT. Wykres: mediana, p10–p90 i 24 faktyczne temperatury Interii; zaznacz stację ok.23 km od centrum, datę, CET i że to rozbieżność prognoz, nie błąd względem pomiarów. metrics.json ma też MAE rozbieżności dwóch prognoz. Działający compare.py można użyć po zmianie katalogu i nazw plików wyjściowych chart.png/.svg, ale sprawdź wszystkie 24 godziny i nowy cutoff. Jeśli BrowserOS natrafi na prawdziwy blok ludzki, zgłoś to rodzicowi; pozostałą niezależną pracę kontynuuj.
''',
 'classification':'''TabICL: klasyfikacja nowotworu na wbudowanym sklearn.datasets.load_breast_cancer(as_frame=True). Użyj CAŁEGO zbioru 569 wierszy, 30 cech, target. Wgraj świeży CSV przez /datasets i wykonaj POST /evaluate backend=tabicl, task=classification, test_size=0.2, seed=42, use_cache=false, time_limit=30. Oczekiwany split 455/114 z etykietami tylko w treningu. Nie importuj TabICL lokalnie.

Pobierz pełny wynik Parquet przez API: prediction, actual i probability_0/probability_1. Sprawdź 114 wyników, brak targetu w features, cache_hit=false, sukces i nowe job_id. Policz accuracy, F1 macro i ROC AUC z predykcji na holdoucie. Narysuj chart.png z dwoma panelami: macierz pomyłek z opisanymi prawdziwymi nazwami klas sklearn i krzywa ROC z linią losową i AUC. Podpisz, że to demonstracja na zbiorze breast_cancer, 30 features i 455/114 train/test. Zachowaj metrics.json i result.csv, wynik pełnego joba oraz krótki opis. Użyj matplotlib/sklearn na PC .venv-mitra. Opisz wynik modelu poprawnie; to dataset demonstracyjny, nie porada medyczna. Nie pobieraj zewnętrznych danych, bo źródło jest lokalnym zasobem sklearn.
''',
 'regression':'''TabICL: regresja na NOWYM syntetycznym sklearn.make_regression(n_samples=2500,n_features=20,n_informative=15,noise=10,random_state=2026). Podział train_test_split(train_size=2000,test_size=500,random_state=2026). Nazwy feature_0..19, target tylko w treningu; prawdę testową zachowaj OSOBNO i nie wysyłaj jej modelowi. Wgraj nowe train.csv i test.csv przez /datasets i uruchom /predict backend=tabicl,task=regression,fine_tune=false,use_cache=false,time_limit=30,seed=2026.

Pobierz pełne 500 predykcji z API, sprawdź kolejność input_row 0..499, skończone wyniki, 20 features bez targetu, cache_hit=false i nowe job_id. Policz RMSE, MAE i R² względem osobnej prawdy testowej. Wykres chart.png ma mieć dwa panele: rzeczywiste vs przewidywane z linią y=x oraz histogram residuali (zdefiniuj znak); podpisz syntetyczne dane, 20 cech i 2000/500 train/test. Zapisz metryki, predykcje i wejściowe dane, krótki opis i pełny job. Biblioteki są na PC .venv-mitra, bez dodatkowych instalacji.
'''
}
records={}
def launch(name):
 dest=OUT/name;dest.mkdir()
 remote='/home/pc/sandbox/bento/benchmarks/end-to-end/'+RUN+'/'+name
 prompt=common+'\nTWOJE LOKALNE ARTEFAKTY: '+str(dest)+'\nTWOJE ARTEFAKTY NA PC: '+remote+'\n\n'+tasks[name]
 (dest/'prompt.md').write_text(prompt)
 start=time.monotonic();utc=datetime.datetime.now(datetime.timezone.utc).isoformat()
 r=subprocess.run(['paseo','run','--no-wait','--title','E2E '+name+' '+RUN,'--provider','codex','--model','gpt-6.1-sol','--thinking','medium','--mode','full-access','--cwd',str(ROOT),'--json',prompt],capture_output=True,text=True)
 if r.returncode:raise RuntimeError(name+': '+r.stderr+r.stdout)
 agent=json.loads(r.stdout)
 record={'name':name,'agent_id':agent['agentId'],'prompt_sent_at_utc':utc,'prompt_sent_monotonic':start,'local_dir':str(dest),'remote_dir':remote,'state':'running'}
 records[name]=record
 (dest/'launch.json').write_text(json.dumps(record,indent=2));print('LAUNCHED '+json.dumps(record),flush=True)
 return record
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
 for _ in pool.map(launch,tasks):pass

def save():
 (OUT/'timings.json').write_text(json.dumps({'run_id':RUN,'model':'gpt-6.1-sol','thinking':'medium','permission_mode':'full-access','parallel_agents':3,'timer_definition':'local monotonic time immediately before Paseo prompt submission to first observation of successful done.json + complete local PNG, checked every 0.25 seconds; includes agent work, data fetching, shared GPU queue, plotting and artifact transfer','records':list(records.values())},indent=2))
def complete_png(path):
 try:
  b=path.read_bytes()
  return len(b)>1000 and b[:8]==b'\x89PNG\r\n\x1a\n' and b[-12:]==b'\x00\x00\x00\x00IEND\xaeB`\x82' and struct.unpack('>II',b[16:24])[0]>=1000
 except OSError:return False
save();deadline=time.monotonic()+1200;last_report=time.monotonic()
while any(x['state']=='running' for x in records.values()):
 for name,record in records.items():
  if record['state']!='running':continue
  directory=Path(record['local_dir']);done=directory/'done.json'
  if done.exists() and complete_png(directory/'chart.png') and (directory/'metrics.json').exists():
   try:d=json.loads(done.read_text());m=json.loads((directory/'metrics.json').read_text())
   except (OSError,json.JSONDecodeError):continue
   if d.get('status')=='success':
    record.update(state='complete',chart_ready_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),prompt_to_chart_seconds=time.monotonic()-record['prompt_sent_monotonic'],completion=d,metrics=m)
    print('COMPLETE '+json.dumps(record),flush=True);save()
 if time.monotonic()>deadline:
  for record in records.values():
   if record['state']=='running':record.update(state='timeout',elapsed_seconds=time.monotonic()-record['prompt_sent_monotonic'])
  save();break
 if time.monotonic()-last_report>30:
  print('PROGRESS '+json.dumps({n:{'state':r['state'],'elapsed':round(time.monotonic()-r['prompt_sent_monotonic'],1)} for n,r in records.items()}),flush=True);last_report=time.monotonic();save()
 time.sleep(.25)
save();print('FINISHED '+str(OUT),flush=True)
