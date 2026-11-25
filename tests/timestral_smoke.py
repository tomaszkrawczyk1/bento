"""Real GPU forecasts, HTTP/MCP, chronological holdout, quantiles and cache."""
import asyncio,io,json,time
from pathlib import Path
import httpx,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'benchmarks/timestral';OUT.mkdir(parents=True,exist_ok=True)
key=json.loads((ROOT/'.credentials/owner.json').read_text())['api_key']
c=httpx.Client(base_url='http://127.0.0.1:3000',headers={'Authorization':'Bearer '+key},timeout=40)
for _ in range(60):
 try:
  if c.get('/health').is_success:break
 except httpx.HTTPError:pass
 time.sleep(1)
def upload(df,name):
 df.to_csv(OUT/name,index=False)
 r=c.post('/datasets',files={'file':(name,df.to_csv(index=False).encode(),'text/csv')});r.raise_for_status();return r.json()['dataset_id']
async def mcp_submit(spec):
 from fastmcp import Client
 base=(ROOT/'deploy/public-url.txt').read_text().strip()
 async with Client(base+'/mcp',auth=key,timeout=40) as m:
  assert 'forecast' in [t.name for t in await m.list_tools()]
  result=await m.call_tool('forecast',spec)
  assert not result.is_error
  return result.data
runs=[]
def execute(name,spec,truth,via_mcp=False):
 start=time.perf_counter()
 if via_mcp:job=asyncio.run(mcp_submit(spec))
 else:
  r=c.post('/forecast',json=spec);r.raise_for_status();job=r.json()
 for _ in range(240):
  j=c.get('/jobs/'+job['job_id']).json()
  if j['state'] in ('failed','succeeded'):break
  time.sleep(1)
 wall=time.perf_counter()-start
 assert j['state']=='succeeded',j
 r=j['result'];response=c.get('/results/'+r['result_id']+'/download');response.raise_for_status();pred=pd.read_parquet(io.BytesIO(response.content))
 pred.to_parquet(OUT/(name+'.parquet'),index=False)
 cols=['q_'+str(q) for q in r['quantile_levels']]
 assert np.isfinite(pred[cols]).all().all() and (np.diff(pred[cols].to_numpy(),axis=1)>=-1e-6).all()
 assert np.allclose(pred['prediction'],pred['q_0.5'])
 assert len(pred)==len(truth)
 actual=pred.merge(truth,on=['series_id','timestamp','target'],validate='one_to_one')
 assert len(actual)==len(truth)
 delta=actual['prediction']-actual['actual']
 record={'name':name,'job_id':j['id'],'transport':'public MCP + REST polling' if via_mcp else 'REST HTTP loopback','context_rows':r['context_rows'],'context_steps_per_series':r['context_steps_per_series'],'series_count':r['series_count'],'targets':r['target_count'],'numeric_input_columns':r['feature_count'],'horizon':r['prediction_length'],'forecast_rows':len(pred),'load_seconds':r['load_model_seconds'],'inference_seconds':r['inference_seconds'],'api_duration_seconds':r['duration_seconds'],'worker_seconds':j['finished']-j['started'],'queue_seconds':j['started']-j['created'],'client_seconds':wall,'cache_hit':r['cache_hit'],'cache_type':r['cache_type'],'inference_executed':r['inference_executed'],'gpu_peak_allocated_mib':r['gpu_peak_allocated_mib'],'rmse':float(np.sqrt(np.mean(delta**2))),'mae':float(np.mean(abs(delta))),'context_id':r['context_id']}
 runs.append(record);(OUT/'summary.json').write_text(json.dumps(runs,indent=2));(OUT/(name+'-job.json')).write_text(json.dumps(j,indent=2));print(json.dumps(record),flush=True)
 return pred,r

def dataset(steps,horizon,groups,targets,covariates):
 histories=[];futures=[];truth=[]
 for group in range(groups):
  t=np.arange(steps+horizon);times=pd.date_range('2026-01-01',periods=len(t),freq='h',tz='UTC');d={'timestamp':[x.isoformat() for x in times],'series_id':'series_'+str(group)}
  for k in range(targets):d['y'+str(k)]=20+3*group+k+5*np.sin(2*np.pi*t/24+k*.3)+2*np.cos(2*np.pi*t/168)+.005*t
  if covariates:d.update(sin_day=np.sin(2*np.pi*t/24),cos_day=np.cos(2*np.pi*t/24),observed_temp=15+8*np.sin(2*np.pi*t/24-.5))
  df=pd.DataFrame(d);histories.append(df.iloc[:steps]);future=df.iloc[steps:].drop(columns=['y'+str(k) for k in range(targets)]+(['observed_temp'] if covariates else []));futures.append(future)
  for k in range(targets):
   for i in range(steps,len(t)):truth.append({'series_id':'series_'+str(group),'timestamp':times[i].isoformat(),'target':'y'+str(k),'actual':float(df.iloc[i]['y'+str(k)])})
 return pd.concat(histories),pd.concat(futures),pd.DataFrame(truth)
for name,steps,horizon,groups,targets,cov in [('univariate',512,48,1,1,False),('multivariate',1024,96,2,3,True)]:
 history,future,truth=dataset(steps,horizon,groups,targets,cov);truth.to_csv(OUT/(name+'-truth.csv'),index=False)
 data_id=upload(history,name+'-history.csv');future_id=upload(future,name+'-future.csv')
 spec={'dataset':data_id,'targets':['y'+str(k) for k in range(targets)],'timestamp':'timestamp','series_id':'series_id','prediction_length':horizon,'future':future_id,'use_cache':False}
 if cov:spec.update(past_covariates=['observed_temp'],known_covariates=['sin_day','cos_day'])
 pred,_=execute(name+'-uncached',spec,truth,via_mcp=cov)
 spec['use_cache']=True
 b,br=execute(name+'-cache-first',spec,truth)
 d,dr=execute(name+'-cache-hit',spec,truth)
 assert not br['cache_hit'] and dr['cache_hit'] and not dr['inference_executed'] and dr['inference_seconds']==0
 pd.testing.assert_frame_equal(b,d)
 if cov:
  # Supplying garbage future target labels must have no effect on the forecast.
  for k in range(targets):future['y'+str(k)]=1e9
  other=upload(future,'future-target-sentinel.csv')
  sentinel,_=execute(name+'-future-target-ignored',{**spec,'future':other,'use_cache':False},truth)
  assert np.allclose(pred['prediction'],sentinel['prediction'],rtol=1e-5,atol=1e-5)
  bad=c.post('/forecast',json={**spec,'future':None});assert bad.status_code==400
 assert c.post('/forecast',json={**spec,'prediction_length':0}).status_code==400
 assert c.post('/forecast',json={**spec,'targets':['timestamp']}).status_code==400
print('TIMESTRAL PASSED: real CUDA, 21 ordered quantiles, chronological holdout, multivariate covariates, public MCP, exact cache, future-label isolation, invalid requests',flush=True)
