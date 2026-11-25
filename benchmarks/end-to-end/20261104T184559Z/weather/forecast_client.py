"""Fetch observed METAR history and submit ONE uncached Timestral API job.
No forecast reference is read by this script. Run with server .venv/bin/python.
"""
import io,json,math,time
from datetime import datetime,timezone
from pathlib import Path
import httpx,numpy as np,pandas as pd

ROOT=Path('/home/pc/sandbox/bento')
OUT=ROOT/'benchmarks/end-to-end/20261104T184559Z/weather'
OUT.mkdir(parents=True,exist_ok=True)
ASOF=pd.Timestamp.now(tz='UTC')
END=pd.Timestamp('2026-11-05T22:00:00Z')
params={'station':'EPKT','data':'tmpc','year1':2026,'month1':10,'day1':5,'year2':2026,'month2':11,'day2':5,'tz':'Etc/UTC','format':'onlycomma','latlon':'yes','elev':'yes','missing':'M','trace':'T','direct':'no','report_type':[3,4]}
url='https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py'
retrieved=datetime.now(timezone.utc).isoformat()
r=httpx.get(url,params=params,timeout=90);r.raise_for_status()
(OUT/'iem-epkt-raw.csv').write_bytes(r.content)
network_url='https://mesonet.agron.iastate.edu/geojson/network/PL__ASOS.geojson'
meta=httpx.get(network_url,timeout=40);meta.raise_for_status()
(OUT/'station-network-raw.geojson').write_bytes(meta.content)
stations=meta.json()['features']
station=next(f for f in stations if f['properties'].get('sid')=='EPKT' or f['properties'].get('station')=='EPKT' or f.get('id')=='EPKT')
(OUT/'station.json').write_text(json.dumps(station,indent=2))
df=pd.read_csv(io.BytesIO(r.content),na_values=['M'])
df['timestamp']=pd.to_datetime(df['valid'],utc=True)
df['tmpc']=pd.to_numeric(df['tmpc'],errors='coerce')
assert set(df.station)=={'EPKT'}
observed=df[(df.timestamp<=ASOF)&df.tmpc.notna()].copy()
# Use only fully elapsed UTC bins; no observations in current partial hour.
observed=observed[observed.timestamp<ASOF.floor('h')]
last=observed.timestamp.max().floor('h')
assert pd.Timedelta(0)<=ASOF-last<pd.Timedelta('24h'), 'Observations too old; do not silently extrapolate stale history'
start=last-pd.Timedelta(hours=719)
observed=observed[observed.timestamp>=start]
# Exact duplicate observation timestamps are averaged, then equal-weight hourly means.
values=observed.groupby('timestamp').tmpc.mean().resample('h').mean().reindex(pd.date_range(start,last,freq='h'))
history=pd.DataFrame({'timestamp':[t.isoformat() for t in values.index],'temperature_c':values.to_numpy()})
assert len(history)==720 and history.temperature_c.notna().sum()>=32
assert history.temperature_c.dropna().between(-50,50).all()
history.to_csv(OUT/'history-hourly-utc.csv',index=False)
observed.to_csv(OUT/'observations-used.csv',index=False)
horizon=int((END-last)/pd.Timedelta('1h'));assert 1<=horizon<=1024
lat=float(observed.lat.iloc[0]);lon=float(observed.lon.iloc[0])
center=(50.2649,19.0238)
a=math.sin(math.radians(lat-center[0])/2)**2+math.cos(math.radians(center[0]))*math.cos(math.radians(lat))*math.sin(math.radians(lon-center[1])/2)**2
source={'name':'Iowa Environmental Mesonet ASOS/METAR archive, station EPKT Katowice-Pyrzowice','kind':'surface temperature observations from METAR, not model reanalysis or forecast','request_url':str(r.url),'metadata_url':network_url,'retrieved_at_utc':retrieved,'as_of_cutoff_utc':ASOF.isoformat(),'station':station,'latitude':lat,'longitude':lon,'elevation_m':float(observed.elevation.iloc[0]),'katowice_center_approx':center,'distance_to_center_km':6371*2*math.atan2(math.sqrt(a),math.sqrt(1-a)),'raw_file_last_timestamp':df.timestamp.max().isoformat(),'last_observation_used_utc':observed.timestamp.max().isoformat(),'hourly_context_start_utc':start.isoformat(),'hourly_context_end_utc':last.isoformat(),'context_rows':len(history),'observed_hourly_values':int(history.temperature_c.notna().sum()),'missing_hourly_values':int(history.temperature_c.isna().sum()),'observation_rows_used':len(observed),'aggregation':'Deduplicate exact timestamps by arithmetic mean, then mean over completed [hour,hour+1h) UTC bins; label at left edge; regular hourly reindex; missing stays NaN; no future fill','prediction_length':horizon,'forecast_end_utc':END.isoformat()}
(OUT/'source.json').write_text(json.dumps(source,indent=2))
key=json.loads((ROOT/'.credentials/owner.json').read_text())['api_key']
client=httpx.Client(base_url='http://127.0.0.1:3000',headers={'Authorization':'Bearer '+key},timeout=40)
raw=[]
def req(method,path,**kwargs):
    response=client.request(method,path,**kwargs)
    raw.append({'method':method,'path':path,'status':response.status_code,'response':response.json()})
    (OUT/'api-raw.json').write_text(json.dumps(raw,indent=2))
    response.raise_for_status();return response.json()
with (OUT/'history-hourly-utc.csv').open('rb') as f:
    ds=req('POST','/datasets',files={'file':('history-hourly-utc.csv',f,'text/csv')})
description=req('GET','/datasets/'+ds['dataset_id'])
assert description['rows']==720
spec={'dataset':ds['dataset_id'],'targets':['temperature_c'],'timestamp':'timestamp','prediction_length':horizon,'past_covariates':[],'known_covariates':[],'use_cache':False}
(OUT/'request.json').write_text(json.dumps(spec,indent=2))
t=time.perf_counter();response=client.post('/forecast',json=spec);submit_s=time.perf_counter()-t
raw.append({'method':'POST','path':'/forecast','status':response.status_code,'response':response.json()});response.raise_for_status();submitted=response.json()
print('submitted '+submitted['job_id'],flush=True)
for _ in range(240):
    time.sleep(0.7)
    job=req('GET','/jobs/'+submitted['job_id'])
    if job['state'] in ('succeeded','failed','cancelled'):break
wall=time.perf_counter()-t
(OUT/'job.json').write_text(json.dumps(job,indent=2))
assert job['state']=='succeeded',job.get('error')
result=job['result'];assert not result['cache_hit'] and result['inference_executed'] and result['inference_seconds']>0
download=client.get('/results/'+result['result_id']+'/download');download.raise_for_status()
(OUT/'forecast-full.parquet').write_bytes(download.content)
prediction=pd.read_parquet(io.BytesIO(download.content));assert len(prediction)==horizon
prediction.to_csv(OUT/'forecast-full.csv',index=False)
prediction['timestamp_utc']=pd.to_datetime(prediction.timestamp,utc=True)
tomorrow=prediction[prediction.timestamp_utc.dt.tz_convert('Europe/Warsaw').dt.strftime('%Y-%m-%d')=='2026-11-05'].copy()
assert len(tomorrow)==24
tomorrow.to_csv(OUT/'timestral-tomorrow.csv',index=False)
summary={'transport':'REST HTTP loopback on PC via SSH; no public network inference timing','forecast_date':'2026-11-05','timezone':'Europe/Warsaw','job_id':submitted['job_id'],'dataset_ids':[ds['dataset_id']],'result_id':result['result_id'],'source':source,'request':spec,'result_metadata':result,'timing':{'load_model_seconds':result['load_model_seconds'],'inference_seconds':result['inference_seconds'],'api_duration_seconds':result['duration_seconds'],'worker_seconds':job['finished']-job['started'],'queue_seconds':job['started']-job['created'],'submit_http_seconds':submit_s,'client_wall_seconds':wall},'validation':'Success; use_cache=false; actual inference; 720 regular history hours; 24 tomorrow hours; no future targets or forecast reference submitted'}
(OUT/'model-summary.json').write_text(json.dumps(summary,indent=2))
print(json.dumps({k:v for k,v in summary.items() if k not in ('source','result_metadata')},indent=2),flush=True)
