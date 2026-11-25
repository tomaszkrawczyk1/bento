"""Local offline Timestral-209M, reached only by the authenticated job gateway."""
import gc,hashlib,json,threading,time
from collections import OrderedDict
from pathlib import Path
import bentoml,numpy as np,torch
from app.forecast import prepare

MODEL=None
RESULTS=OrderedDict()
LOCK=threading.Lock()
WEIGHTS=Path('/home/pc/sandbox/bento/weights/timestral-209m')

def process(spec):
 global MODEL
 started=time.perf_counter();history,future,groups=prepare(spec,{'workspace':spec['workspace']})
 key=hashlib.sha256(json.dumps({**{k:spec.get(k) for k in ('workspace','targets','timestamp','prediction_length','series_id','past_covariates','known_covariates')},'history_sha':history['sha'],'future_sha':future['sha'] if future else None,'checkpoint':'Timestral-209M'},sort_keys=True).encode()).hexdigest()
 for k in list(RESULTS):
  if time.time()-RESULTS[k][0]>1800:RESULTS.pop(k)
 if spec['use_cache'] and key in RESULTS:
  _,workspace,saved=RESULTS.pop(key);RESULTS[key]=(time.time(),workspace,saved)
  return {**saved,'cache_hit':True,'cache_type':'result','load_model_seconds':0.0,'inference_seconds':0.0,'inference_executed':False,'duration_seconds':time.perf_counter()-started}
 load_started=time.perf_counter();loaded=MODEL is None
 if loaded:
  from timestral import TimestralForecaster
  MODEL=TimestralForecaster.from_pretrained(WEIGHTS,device='cuda',local_files_only=True)
 torch.cuda.synchronize();load_seconds=time.perf_counter()-load_started if loaded else 0.0
 torch.cuda.reset_peak_memory_stats();rows=[];infer_seconds=0.0;targets=spec['targets'];past=spec['past_covariates'];known=spec['known_covariates'];horizon=spec['prediction_length']
 for ident,part,tail,times in groups:
  context=part[targets].to_numpy(dtype=np.float32).T[None,:,:]
  past_values=part[past].to_numpy(dtype=np.float32).T[None,:,:] if past else None
  known_values=np.concatenate([part[known].to_numpy(dtype=np.float32),tail[known].to_numpy(dtype=np.float32)],axis=0).T[None,:,:] if known else None
  torch.cuda.synchronize();inference_start=time.perf_counter()
  with torch.inference_mode():forecast=MODEL.forecast(context,prediction_length=horizon,past_covariates=past_values,known_covariates=known_values)
  torch.cuda.synchronize();infer_seconds+=time.perf_counter()-inference_start
  values=forecast.quantiles.detach().cpu().numpy()[0];levels=forecast.quantile_levels
  if not np.isfinite(values).all():raise ValueError('Model produced non-finite forecasts')
  for v,target in enumerate(targets):
   for step,stamp in enumerate(times):
    row={'series_id':ident,'timestamp':stamp.isoformat(),'target':target,'horizon_step':step+1,'prediction':float(values[v,step,levels.index(.5)])}
    row.update({'q_'+str(q):float(values[v,step,i]) for i,q in enumerate(levels)});rows.append(row)
 result={'predictions':rows,'metrics':{},'backend':'timestral','checkpoint':'Timestral-209M','task':'forecast','context_rows':history['rows'],'context_steps_per_series':[len(g[1]) for g in groups],'series_count':len(groups),'target_count':len(targets),'feature_count':len(targets)+len(past)+len(known),'features':targets+past+known,'prediction_length':horizon,'quantile_levels':list(levels),'cache_hit':False,'cache_type':None,'context_id':key if spec['use_cache'] else None,'load_model_seconds':load_seconds,'inference_seconds':infer_seconds,'inference_executed':True,'duration_seconds':time.perf_counter()-started,'gpu_peak_allocated_mib':torch.cuda.max_memory_allocated()/1024**2,'recipe':{'zero_shot':True,'fine_tune':False,'benchmark_parity':False,'device':'cuda','weights_offline':True}}
 if spec['use_cache']:
  RESULTS[key]=(time.time(),spec['workspace'],result)
  while len(RESULTS)>8:RESULTS.popitem(last=False)
 return result

@bentoml.service(resources={'gpu':1},workers=1,traffic={'timeout':1200,'concurrency':1})
class TimestralService:
 @bentoml.api
 def run(self,request:dict)->dict:
  with LOCK:return process(request)
 @bentoml.api
 def clear(self)->dict:
  global MODEL
  with LOCK:MODEL=None;RESULTS.clear();gc.collect();torch.cuda.empty_cache()
  return {'cleared':True}
 @bentoml.api
 def evict(self,context_id:str,workspace:str)->dict:
  with LOCK:
   item=RESULTS.get(context_id)
   if item and item[1]==workspace:RESULTS.pop(context_id);return {'removed':1}
   return {'removed':0}
 @bentoml.api
 def info(self)->dict:return {'backend':'timestral','checkpoint':'Timestral-209M','cuda':torch.cuda.is_available(),'loaded':MODEL is not None}
