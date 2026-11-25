"""Analyze saved results only: no API, network or model calls."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

P=Path(__file__).resolve().parent
s=json.loads((P/'model-summary.json').read_text())
ref=json.loads((P/'interia-reference.json').read_text())
t=pd.read_csv(P/'timestral-tomorrow.csv')
t['timestamp_utc']=pd.to_datetime(t.timestamp,utc=True)
t['timestamp_local']=t.timestamp_utc.dt.tz_convert('Europe/Warsaw')
t['hour']=t.timestamp_local.dt.hour
assert len(t)==24 and t.hour.tolist()==list(range(24))
assert set(t.timestamp_local.dt.strftime('%Y-%m-%d'))=={'2026-11-05'}
assert ref['forecast_date']=='2026-11-05'
i=pd.DataFrame(ref['hourly'])
i['timestamp_utc']=pd.to_datetime(i.timestamp,utc=True)
assert len(i)==24 and not i.timestamp_utc.duplicated().any()
q=sorted([c for c in t if c.startswith('q_')],key=lambda c:float(c[2:]))
assert np.isfinite(t[q]).all().all()
assert (np.diff(t[q].to_numpy(),axis=1)>=-1e-6).all()
assert np.allclose(t.prediction,t['q_0.5'])
df=t[['timestamp_utc','timestamp_local','hour','prediction','q_0.1','q_0.9']].rename(columns={'prediction':'timestral_median_c','q_0.1':'timestral_p10_c','q_0.9':'timestral_p90_c'})
df=df.merge(i[['timestamp_utc','temperature_c']].rename(columns={'temperature_c':'interia_c'}),on='timestamp_utc',how='left',validate='one_to_one')
df['difference_c']=df.timestral_median_c-df.interia_c
assert df.interia_c.notna().all()
df.to_csv(P/'hourly-comparison.csv',index=False)
metrics={'common_hours':len(df),'mean_difference_timestral_minus_interia_c':float(df.difference_c.mean()),'mae_between_forecasts_c':float(df.difference_c.abs().mean()),'timestral_min_c':float(df.timestral_median_c.min()),'timestral_max_c':float(df.timestral_median_c.max()),'interia_min_c':float(i.temperature_c.min()),'interia_max_c':float(i.temperature_c.max()),'selected_hours':df[df.hour.isin([0,6,12,18])][['hour','timestral_median_c','interia_c']].to_dict('records')}
history=pd.read_csv(P/'history-hourly-utc.csv')
ht=pd.to_datetime(history.timestamp,utc=True)
assert len(history)==720 and (ht.diff().dropna()==pd.Timedelta('1h')).all()
assert ht.max()<pd.Timestamp(s['source']['as_of_cutoff_utc'])
assert list(history.columns)==['timestamp','temperature_c']
assert s['request']['use_cache'] is False and s['result_metadata']['inference_executed']
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False})
fig,ax=plt.subplots(figsize=(12,6.4),layout='constrained')
ax.fill_between(df.hour,df.timestral_p10_c,df.timestral_p90_c,color='#2457a6',alpha=.12,label='Timestral p10–p90 (kwantyle modelu)')
ax.plot(df.hour,df.timestral_median_c,'o-',color='#2457a6',markersize=3,label='Timestral-209M · mediana')
ax.plot(i.hour,i.temperature_c,'o-',color='#d36b1f',markersize=4,label='Interia / AccuWeather · odczytane punkty')
ax.set(xlabel='Godzina · Europe/Warsaw (CET)',ylabel='Temperatura [°C]',xticks=range(0,24,2),xlim=(0,23))
ax.set_title('Katowice · 5 listopada 2026\nPorównanie dwóch prognoz godzinowych',loc='left',fontweight='bold')
ax.grid(axis='y',alpha=.2);ax.legend(frameon=False)
fig.supxlabel('Historia modelu: Katowice-Pyrzowice (EPKT), 23 km od centrum. Stan danych: ' + pd.Timestamp(s['source']['as_of_cutoff_utc']).tz_convert('Europe/Warsaw').strftime('%d.%m, %H:%M CET') + '.\nPas p10–p90: kwantyle modelu, bez sprawdzonej kalibracji meteorologicznej.\nPorównanie dwóch prognoz, nie błąd względem rzeczywistej pogody.',fontsize=9)
fig.savefig(P/'chart.png',dpi=180);fig.savefig(P/'chart.svg')
s['comparison_metrics']=metrics
s['interia_source']={k:v for k,v in ref.items() if k!='hourly'}
s['interpretation']='Disagreement of two forecasts, not error against actual future weather.'
s['additional_validation']='24 matching timestamps, no interpolation; ordered finite quantiles, median consistency; regular historical UTC context; no future temperatures in model input.'
(P/'report.json').write_text(json.dumps(s,indent=2,allow_nan=False))
src=s['source']
lines=['# Katowice: prognoza na 5 listopada 2026','',f"Timestral-209M przez POST /forecast. Job: `{s['job_id']}`; wynik: `{s['result_id']}`; historia: `{s['dataset_ids'][0]}`. Zero-shot, bez fine-tuningu, use_cache=false. REST HTTP loopback na PC przez SSH.",'',f"Historia: obserwacje METAR stacji EPKT Katowice-Pyrzowice, {src['latitude']:.4f}°N, {src['longitude']:.4f}°E, {src['elevation_m']:.0f} m n.p.m.; około {src['distance_to_center_km']:.1f} km od przyjętego centrum Katowic. [Źródło IEM]({src['request_url']}); [metadane]({src['metadata_url']}). Pobrano {src['retrieved_at_utc']}. Obserwacje stacji, nie reanaliza ani prognoza.",'',f"Cutoff: {src['as_of_cutoff_utc']}. Ostatnia użyta obserwacja: {src['last_observation_used_utc']}. Kontekst UTC: {src['hourly_context_start_utc']} – {src['hourly_context_end_utc']}, {src['context_rows']} godzin, {src['missing_hourly_values']} braków. Duplikaty timestampów uśredniono, potem wyliczono średnią w zakończonych przedziałach [h,h+1h), oznaczanych początkiem godziny. Odrzucono bieżącą niepełną godzinę. Braków nie wypełniano przyszłymi danymi.",'',f"Target i jedyna numeryczna cecha: temperature_c. Bez dodatkowych covariates. Horyzont: {src['prediction_length']} godzin do {src['forecast_end_utc']}. Wybrano dokładnie 24 godziny 2026-11-05 00–23 Europe/Warsaw (UTC+1). Żadna przyszła temperatura, w tym Interia, nie trafiła do modelu.",'',f"Interia: [{ref['source_name']}]({ref['source_url']}), pobrano {ref['retrieved_at_utc']}. 24 faktyczne punkty i 24 wspólne godziny, bez interpolacji.",'','| CET | Timestral mediana [°C] | Interia [°C] |','|---|---:|---:|']
for row in metrics['selected_hours']:lines.append(f"| {row['hour']:02d}:00 | {row['timestral_median_c']:.2f} | {row['interia_c']:.1f} |")
lines+=['',f"Min/max Timestral: {metrics['timestral_min_c']:.2f}/{metrics['timestral_max_c']:.2f} °C; Interia: {metrics['interia_min_c']:.1f}/{metrics['interia_max_c']:.1f} °C. Średnia różnica Timestral − Interia: {metrics['mean_difference_timestral_minus_interia_c']:.2f} °C; MAE między prognozami: {metrics['mae_between_forecasts_c']:.2f} °C.",'','To rozbieżność dwóch prognoz, nie błąd względem rzeczywistej pogody: prognozowany dzień jeszcze nie nastąpił. Timestral ekstrapoluje historię szeregu bez modelu atmosfery, przyszłych frontów i pól meteorologicznych. Stacja lotniskowa może nie odzwierciedlać temperatury centrum miasta. To eksperyment, nie oficjalna prognoza meteorologiczna. Kwantyle p10–p90 są wynikiem modelu, bez zweryfikowanej kalibracji dla tej stacji.','','| Pomiar | Sekundy |','|---|---:|']
for key,value in s['timing'].items():lines.append(f'| {key} | {value:.6f} |')
lines+=['','Inference_seconds: rzeczywista inferencja z synchronizacją CUDA. Load_model_seconds: ładowanie wag. API duration: całe przetwarzanie. Worker = finished−started, kolejka = started−created. Klient: perf_counter od wysłania /forecast do odebrania zakończonego zadania, w tym polling co >=1,1 s i zapis odpowiedzi.','','![Porównanie prognoz](chart.png)','','Artefakty: forecast_client.py, compare.py, surowe obserwacje i metadane IEM, source.json, history-hourly-utc.csv, request.json, api-raw.json, job.json, forecast-full.csv/.parquet, timestral-tomorrow.csv, interia-reference.json, hourly-comparison.csv, model-summary.json, report.json, chart.png/.svg.']
(P/'report.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(metrics,indent=2,allow_nan=False))
