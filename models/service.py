"""GPU model process. Only the authenticated gateway can reach this service."""
import gc, hashlib, json, os, threading, time
from collections import OrderedDict
from pathlib import Path
import bentoml, numpy as np, pandas as pd
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score, mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from app.store import ROOT,db

BACKEND=os.environ.get('MODEL_BACKEND','tabicl')
WEIGHTS=Path(os.environ.get('MODEL_WEIGHTS','/home/pc/sandbox/bento/weights'))
MAX_CONTEXTS=int(os.environ.get('MAX_CONTEXTS','2'))
LOCK=threading.Lock()
CONTEXTS=OrderedDict()
OWNERS={}
RESULTS=OrderedDict()
CACHE_TTL=1800

def clear_cache():
 CONTEXTS.clear();RESULTS.clear();OWNERS.clear();gc.collect()
 import torch
 torch.cuda.empty_cache()

def get_data(ident,workspace):
 with db() as c:r=c.execute('SELECT path,sha FROM datasets WHERE id=? AND workspace=? AND expires>?',(ident,workspace,time.time())).fetchone()
 if not r:raise ValueError('Dataset missing or expired')
 return pd.read_parquet(r['path']),r['sha']

def estimate(spec,X,y):
 import torch
 if BACKEND=='tabicl':
  from tabicl import TabICLClassifier,TabICLRegressor
  task=spec.get('task','classification');file='tabicl-classifier-v2-20260212.ckpt' if task=='classification' else 'tabicl-regressor-v2-20260212.ckpt'
  cls=TabICLClassifier if task=='classification' else TabICLRegressor
  estimator=cls(model_path=str(WEIGHTS/'tabicl'/file),allow_auto_download=False,device='cuda',n_estimators=4,batch_size=1,kv_cache='repr' if spec.get('use_cache') else False,random_state=spec['seed'],n_jobs=4)
  estimator.fit(X,y)
  return estimator,'tabicl-v2-20260212'
 # Mitra v2: classification without fine-tuning uses AutoGluon's native Mitra.
 # The official fine-tune wrapper trains during predict, not during fit.
 task=spec.get('task','classification')
 if spec.get('fine_tune') or task=='regression':
  if task=='regression' and not spec.get('fine_tune'):
   raise ValueError('Mitra-v2 regression currently requires fine_tune=true via the verified official wrapper')
  from mitra_finetune import MitraFinetune
  model=MitraFinetune(checkpoint_dir=str(WEIGHTS/('mitra-classifier' if task=='classification' else 'mitra-regressor')),problem_type=task,device='cuda',time_limit=spec['time_limit'],random_state=spec['seed'],num_bag_folds=2)
  model.fit(X,y)
  return model,'mitra-v2-finetune-2fold-demo'
 from autogluon.tabular import TabularPredictor
 data=X.copy();data['__target__']=y.to_numpy()
 output=ROOT/'artifacts'/spec['_job_id'];output.mkdir(exist_ok=True)
 model=TabularPredictor(label='__target__',path=str(output),verbosity=1).fit(data,hyperparameters={'MITRA':{'hf_model':str(WEIGHTS/'mitra-classifier'),'fine_tune':False}},fit_weighted_ensemble=False,num_gpus=1,num_cpus=4,time_limit=spec['time_limit'])
 return model,'mitra-classifier-2-icl'

def process(spec):
 started=time.monotonic()
 train,train_hash=get_data(spec['train'],spec['workspace'])
 target=spec['target'];features=spec['features'];task=spec.get('task','classification')
 X=train[features].copy();y=train[target]
 if y.isna().any():raise ValueError('Target has missing values')
 if len(X)<10:raise ValueError('At least 10 training rows are required')
 if task=='classification' and y.nunique()<2:raise ValueError('Classification requires at least two classes')
 # TabICL accepts categorical DataFrame columns; fit sees training data only.
 X=X.replace({None:np.nan})
 for c in X:
  if X[c].dtype=='object':X[c]=X[c].astype('category')
 if spec['operation']=='evaluate':
  X,XT,y,yT=train_test_split(X,y,test_size=spec['test_size'],random_state=spec['seed'],stratify=y if task=='classification' else None)
  test_hash='holdout:'+str(spec['seed'])+':'+str(spec['test_size'])
 else:
  test,test_hash=get_data(spec['test'],spec['workspace'])
  missing=set(features)-set(test.columns)
  if missing:raise ValueError('Missing test features: '+', '.join(sorted(missing)))
  XT=test[features].copy();yT=None
 key_fields={k:spec.get(k) for k in ('workspace','target','features','backend','task','fine_tune','seed','operation','test_size')}
 key_fields.update(train_hash=train_hash,checkpoint='tabicl-v2-20260212' if BACKEND=='tabicl' else 'mitra-v2',estimators=4,time_limit=spec['time_limit'],recipe='demo-2fold-v1')
 context_key=hashlib.sha256(json.dumps(key_fields,sort_keys=True).encode()).hexdigest()
 result_key=context_key+':'+test_hash
 use_cache=spec.get('use_cache',False)
 OWNERS[context_key]=spec['workspace']
 for k in list(CONTEXTS):
  if time.time()-CONTEXTS[k][0]>CACHE_TTL:CONTEXTS.pop(k)
 for k in list(RESULTS):
  if time.time()-RESULTS[k][0]>CACHE_TTL:RESULTS.pop(k)
 cache_hit=False;cache_type=None
 # Separate cached results from reusable model state, especially for MitraFinetune.
 if use_cache and result_key in RESULTS and time.time()-RESULTS[result_key][0]<CACHE_TTL:
  saved=RESULTS[result_key][1];return {**saved,'cache_hit':True,'cache_type':'result','duration_seconds':time.monotonic()-started}
 cacheable_context=BACKEND=='tabicl' or (task=='classification' and not spec.get('fine_tune'))
 if use_cache and context_key in CONTEXTS and time.time()-CONTEXTS[context_key][0]<CACHE_TTL:
  _,model,checkpoint=CONTEXTS.pop(context_key);CONTEXTS[context_key]=(time.time(),model,checkpoint);cache_hit=True;cache_type='context'
 else:
  if len(CONTEXTS)>=MAX_CONTEXTS:
   CONTEXTS.popitem(last=False);gc.collect()
   import torch;torch.cuda.empty_cache()
  model,checkpoint=estimate(spec,X,y)
  if use_cache and cacheable_context:CONTEXTS[context_key]=(time.time(),model,checkpoint)
 for c in features:
  if str(X[c].dtype)=='category':XT[c]=XT[c].astype('category')
 if task=='classification':
  proba=np.asarray(model.predict_proba(XT));classes=np.asarray(model.classes_ if hasattr(model,'classes_') else model.class_labels if hasattr(model,'class_labels') else sorted(y.unique()))
  pred=classes[proba.argmax(axis=1)]
  result=pd.DataFrame({'prediction':pred})
  for i,label in enumerate(classes):result['probability_'+str(label)]=proba[:,i]
  metrics={}
  if yT is not None:
   metrics={'accuracy':float(accuracy_score(yT,pred)),'f1_macro':float(f1_score(yT,pred,average='macro',zero_division=0))}
   if len(classes)==2:metrics['roc_auc']=float(roc_auc_score((yT==classes[1]).astype(int),proba[:,1]))
   result['actual']=yT.to_numpy()
 else:
  pred=np.asarray(model.predict(XT));result=pd.DataFrame({'prediction':pred});metrics={}
  if yT is not None:
   metrics={'rmse':float(np.sqrt(mean_squared_error(yT,pred))),'mae':float(mean_absolute_error(yT,pred)),'r2':float(r2_score(yT,pred))};result['actual']=yT.to_numpy()
 result.insert(0,'input_row',XT.index.to_numpy())
 payload={'predictions':json.loads(result.to_json(orient='records')),'metrics':metrics,'backend':BACKEND,'checkpoint':checkpoint,'train_rows':len(X),'test_rows':len(XT),'features':features,'cache_hit':cache_hit,'cache_type':cache_type,'context_id':context_key if use_cache and cacheable_context else None,'duration_seconds':time.monotonic()-started,'recipe':{'n_estimators':4,'mitra_bag_folds':2,'time_limit':spec['time_limit'],'benchmark_parity':False}}
 if use_cache:
  RESULTS[result_key]=(time.time(),payload)
  while len(RESULTS)>8:RESULTS.popitem(last=False)
 if not use_cache:
  del model;gc.collect()
  import torch;torch.cuda.empty_cache()
 return payload

@bentoml.service(resources={'gpu':1},workers=1,traffic={'timeout':1200,'concurrency':1})
class ModelService:
 @bentoml.api
 def run(self,request:dict)->dict:
  with LOCK:return process(request)
 @bentoml.api
 def info(self)->dict:
  import torch
  return {'backend':BACKEND,'cuda':torch.cuda.is_available(),'gpu':torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,'contexts':len(CONTEXTS)}
 @bentoml.api
 def evict(self,context_id:str,workspace:str)->dict:
  with LOCK:
   if OWNERS.get(context_id)!=workspace:return {'removed':0}
   removed=int(CONTEXTS.pop(context_id,None) is not None)
   for k in list(RESULTS):
    if k.startswith(context_id+':'):RESULTS.pop(k);removed+=1
   OWNERS.pop(context_id,None);gc.collect()
   import torch;torch.cuda.empty_cache()
   return {'removed':removed}
 @bentoml.api
 def clear(self)->dict:
  with LOCK:clear_cache()
  return {'cleared':True}
