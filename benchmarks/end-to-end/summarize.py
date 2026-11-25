import csv,datetime,json,subprocess
from pathlib import Path
p=Path(Path(__file__).with_name('latest.txt').read_text().strip());data=json.loads((p/'timings.json').read_text())
assert len(data['records'])==3 and all(r['state']=='complete' for r in data['records'])
ids=[]
for r in data['records']:
 d=Path(r['local_dir']);job=json.loads((d/'job.json').read_text());m=r['metrics'];ids.append(job['id'])
 assert job['id']==m['job_id'] and job['state']=='succeeded' and not job['result']['cache_hit']
 assert all((d/f).exists() for f in ['chart.png','chart.svg','metrics.json','done.json'])
 if r['name']=='classification':assert len(list(csv.DictReader((d/'result.csv').open())))==114
 if r['name']=='regression':
  assert len(list(csv.DictReader((d/'predictions.csv').open())))==500
  assert 'target' not in next(csv.reader((d/'test.csv').open()))
 if r['name']=='weather':
  assert len(list(csv.DictReader((d/'hourly-comparison.csv').open())))==24
  assert job['result']['inference_executed']
assert len(set(ids))==3
# Verify that artifact trees contain neither application key nor account password.
credentials=json.loads(subprocess.check_output(['ssh','pc@pc','cat /home/pc/sandbox/bento/.credentials/owner.json']))
for f in p.rglob('*'):
 if f.is_file() and f.suffix in {'.json','.py','.md','.csv','.svg'}:
  content=f.read_text()
  assert all(secret not in content for secret in [credentials['api_key'],credentials['password']]),str(f)
first=datetime.datetime.fromisoformat('2026-11-04T18:42:55+00:00')
starts=[datetime.datetime.fromisoformat(r['prompt_sent_at_utc']) for r in data['records']];ends=[datetime.datetime.fromisoformat(r['chart_ready_at_utc']) for r in data['records']]
data['parent_first_clock_utc']=first.isoformat();data['preparation_before_agent_prompts_seconds']=(min(starts)-first).total_seconds();data['approximate_parent_first_clock_to_last_chart_seconds']=(max(ends)-first).total_seconds()
data['parallel_batch_seconds']=max(r['prompt_to_chart_seconds'] for r in data['records'])
data['validation']='3 unique fresh successful API jobs; no result cache; exact expected output rows; no regression target in test input; complete PNG/SVG; charts visually inspected; no app credentials in text artifacts'
(p/'timings.json').write_text(json.dumps(data,indent=2))
labels={'weather':'Timestral — pogoda + Interia','classification':'TabICL — klasyfikacja','regression':'TabICL — regresja'}
lines=['# Prompt → gotowy wykres: trzech agentów Paseo','',f"Run `{data['run_id']}`. GPT-6.1-Sol, medium, 3 niezależni agenci uruchomieni równolegle. Usługa GPU i dokumentacja były już gotowe. Agenci mogli korzystać z istniejącego kodu klientów; pisanie/adaptacja kodu i wszystkie operacje po wysłaniu promptu są wliczone. W nowej sesji przydzielono full-access do autoryzowanego zadania, więc nie było postojów na pytania o zwykłe operacje.",'','Start: lokalny monotoniczny zegar tuż przed wywołaniem Paseo z promptem. Koniec: pierwszy odczyt done.json=success, kompletnego lokalnego PNG (sprawdzone nagłówek, rozmiar i IEND) i metrics.json. Poll 0,25 s, więc opóźnienie detekcji do około 0,25 s. done.json agent publikował po walidacji i skopiowaniu artefaktów. Wliczone: start agenta, rozumowanie, narzędzia, dane, wspólna kolejka GPU, API, rysowanie, walidacja i transfer. Koniec nie zależy od zegara PC ani ukończenia finalnej wiadomości w Paseo. To pojedynczy przebieg każdego zadania, nie mediana ani p95.','','| Zadanie | Prompt → wykres [s] | Wejście / kontekst | Train/test lub prognoza | Cechy | Przetwarzanie modelu [s] | Kolejka [s] | Wykres |','|---|---:|---:|---|---:|---:|---:|---|']
for name in ['weather','classification','regression']:
 r=next(x for x in data['records'] if x['name']==name);m=r['metrics']
 shape='720 h → 29 h, z czego 24 h jutra' if name=='weather' else f"{m['train_rows']}/{m['test_rows']}"
 lines.append(f"| {labels[name]} | {r['prompt_to_chart_seconds']:.2f} | {m['input_rows']} | {shape} | {m['feature_count']} | {m['server_duration_seconds']:.4f} | {m['queue_seconds']:.4f} | [PNG]({name}/chart.png) / [SVG]({name}/chart.svg) |")
lines+=['',f"Wszystkie trzy wykresy: {data['parallel_batch_seconds']:.2f} s od równoległego wysłania promptów. Od pierwszego odczytu zegara podczas obsługi polecenia użytkownika do ostatniego wykresu: około {data['approximate_parent_first_clock_to_last_chart_seconds']:.1f} s; przygotowanie uruchomienia pomiaru przed promptami zajęło {data['preparation_before_agent_prompts_seconds']:.1f} s. Dokładny timestamp samego przyjścia wiadomości użytkownika nie jest dostępny, więc ten drugi pomiar jest przybliżony.",'','Każde zadanie miało nowe job_id i cache_hit=false. Timestral miał już załadowane wagi (load_model_seconds=0), a nowa inferencja wyniosła 0,0312 s. To brak cache wyników przy rozgrzanym procesie, nie zimny start. TabICL duration_seconds obejmuje przygotowanie/fit/predict, nie tylko forward. Nie porównuj liczb z kolumny czasu modelu jak zadań o tej samej semantyce.','','Pogoda: świeże obserwacje IEM EPKT, 720 h, świeży odczyt 24 godzin Interii przez BrowserOS; porównanie dwóch prognoz, nie ich błędu względem pomiarów. Klasyfikacja: sklearn breast_cancer, 569 × 30, holdout 455/114, accuracy 0,9737, ROC AUC 0,9964; wykres macierzy pomyłek i ROC. Regresja: nowo wygenerowane dane syntetyczne 2500 × 20, split 2000/500, RMSE 10,4277, MAE 8,2915, R² 0,9972; wykres predykcji i residuali.','','W każdym podkatalogu: prompt.md, launch.json, kod klienta, wejściowe dane, nowy job.json, CSV wyników, metrics.json, chart.png/.svg, done.json. Konfiguracja i dokładne czasy wszystkich agentów: timings.json.']
(p/'report.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({k:data[k] for k in ['parallel_batch_seconds','preparation_before_agent_prompts_seconds','approximate_parent_first_clock_to_last_chart_seconds','validation']},indent=2))
