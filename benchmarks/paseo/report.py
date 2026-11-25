"""Render benchmark summary and check B/C equality from downloaded artifacts."""
import json
from pathlib import Path
import pandas as pd

p = Path(__file__).resolve().parent
s = json.loads((p/'summary.json').read_text())
raw = json.loads((p/'raw.json').read_text())
runs = s['runs']
checks = []
for task in ('classification','regression'):
    for backend in ('tabicl','mitra'):
        group = [r for r in runs if r['task']==task and r['backend']==backend]
        b = next(r for r in group if r['stage']=='B')
        c = next(r for r in group if r['stage']=='C')
        assert b['cache_hit'] is False
        assert c['cache_hit'] is True and c['cache_type']=='result'
        assert pd.read_parquet(p/(b['job_id']+'.parquet')).equals(pd.read_parquet(p/(c['job_id']+'.parquet')))
        checks.append({'task':task,'backend':backend,'B_C_predictions_exactly_equal':True,'B_cache_miss':True,'C_exact_result_hit':True})
assert len(runs)==12 and all(r['state']=='succeeded' for r in runs)
mcp = [r for r in raw if r.get('tool')=='model_info']
assert len(mcp)==1
mcp_response = mcp[0]['response']
if isinstance(mcp_response, str):
    assert 'is_error=False' in mcp_response and 'Bento Tabular' in mcp_response
else:
    assert mcp_response.get('is_error',mcp_response.get('isError',False)) is False
s['validation'] = checks
s['public_mcp_model_info'] = 'success; real authenticated call over public HTTPS MCP'
s['measurement_note'] = 'submit_http_seconds is perf_counter around HTTP submission helper, including JSON parsing and local response recording; client wall also includes polling and its local recording overhead. Poll interval >=1.05 s.'
(p/'summary.json').write_text(json.dumps(s,indent=2,allow_nan=False))
lines = ['# Niezależny test klienta Bento Tabular', '',
'Dwa zadania, 12 nowych zadań API: 8 uruchomień modelu i 4 odczyty cache, wszystkie zakończone sukcesem. REST przez HTTP loopback `127.0.0.1:3000` na PC, klient uruchomiony przez SSH. Nie jest to pomiar opóźnienia publicznego internetu ani odtworzenie benchmarku publikacji. Publiczny MCP sprawdzono osobnym, rzeczywistym i uwierzytelnionym `model_info` przez HTTPS.', '',
'Klasyfikacja: istniejące `demo/classification-train.csv` i `demo/classification-test.csv`, osobne uploady i odczyty schematu przez API, 455/114 wierszy i 30 cech bez targetu; oba backendy ICL, fine_tune=false. Regresja: sklearn.make_regression(1250,20,n_informative=15,noise=10,random_state=2026), podział train_test_split(random_state=2026) na 1000/250 wierszy. Trening zawiera target, test go nie zawiera; prawda w osobnym regression-truth.csv służy wyłącznie do metryk klienta. Wszystkie predykcje przez POST /predict, pełne wyniki pobrane przez HTTP.', '',
'Ograniczenie API: TabICL z fine_tune=true został odrzucony HTTP 400 (odpowiedź w raw.json). Jego regresję zmierzono z false. Mitra: regresja z true i time_limit=30. Ten limit jest budżetem dostrajania, nie twardym limitem czasu całego zadania. Wszystkie zaakceptowane żądania mają time_limit=30 i seed=2026.', '',
'A: use_cache=false. B: pierwsze use_cache=true (we wszystkich parach cache_hit=false). C: identyczne B, bez zmiany backendu pomiędzy B/C; we wszystkich parach cache_hit=true, cache_type=result i predykcje dokładnie zgodne z B. C odczytuje gotowy wynik, nie mierzy ponownej inferencji. Klient nie czyścił globalnego cache i nie musiał usuwać żadnego kontekstu. API samo zarządza cache przy przełączaniu backendów.', '',
'Czas API = duration_seconds: przygotowanie danych + dopasowanie/dostrajanie + predykcja; dla C odczyt cache. Nie jest to wyizolowany forward/predict. Worker = finished-started, kolejka = started-created. Klient = perf_counter od rozpoczęcia wysyłania /predict do odebrania zakończonego zadania, z kolejką i pollingiem co co najmniej 1,05 s. Submit jest osobnym pomiarem perf_counter wokół helpera HTTP i obejmuje też parsowanie oraz lokalny zapis odpowiedzi; nie jest czystym czasem sieciowym. Zapis odpowiedzi pollingowych również wnosi mały narzut do czasu klienta. Pełne wyniki pobierano po zakończeniu pomiaru klienta.', '',
'Sprawdzono schematy i liczby wierszy z API, sukces wszystkich 12 jobów, train/test rows oraz listę cech w odpowiedzi modelu, brak targetu w features, kompletność i skończoność predykcji, kolejność input_row i identyczność B/C. Zadania uruchamiano sekwencyjnie. Każdy wiersz poniżej pochodzi z nowego job_id, zapisanego w surowych odpowiedziach.', '',
'| Zadanie | Backend | A/B/C | fine_tune | Cechy | Train/test | cache_hit/type | API [s] | Worker [s] | Kolejka [s] | Submit [s] | Klient [s] | RMSE | MAE | job_id | result_id |',
'|---|---|---|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|']
for r in runs:
    n=lambda key: f'{r[key]:.6f}' if r.get(key) is not None else '—'
    lines.append('| '+' | '.join([r['task'],r['backend'],r['stage'],str(r['fine_tune']).lower(),str(r['feature_count']),f"{r['train_rows']}/{r['test_rows']}",f"{str(r['cache_hit']).lower()}/{r['cache_type'] or 'none'}",n('model_preparation_fit_and_prediction_seconds'),n('worker_seconds'),n('queue_seconds'),n('submit_http_seconds'),n('client_wall_seconds'),n('rmse'),n('mae'),r['job_id'],r['result_id']])+' |')
lines += ['', 'Artefakty: client.py (samodzielny klient), report.py (generowanie raportu i walidacja B/C), raw.json (odpowiedzi API/MCP bez kluczy, haseł i linków z tokenami), summary.json (pełne metryki), regression-*.csv (dane i osobna prawda), job_*.parquet (pełne predykcje).', '',f"Czas wykonania klienta: {s['elapsed_seconds']:.2f} s. Konfiguracji usług, kont i agenta nie zmieniano."]
(p/'report.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({'runs':len(runs),'mcp':'success','checks':checks,'elapsed_seconds':s['elapsed_seconds']},indent=2))
