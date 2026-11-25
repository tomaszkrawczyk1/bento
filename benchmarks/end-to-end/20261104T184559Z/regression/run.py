import io,json,time
from pathlib import Path
from datetime import datetime,timezone
import httpx,numpy as np,pandas as pd
from sklearn.datasets import make_regression
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error,mean_absolute_error,r2_score
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path('/home/pc/sandbox/bento'); OUT=ROOT/'benchmarks/end-to-end/20261104T184559Z/regression';OUT.mkdir(parents=True,exist_ok=True)
def save(name,obj): (OUT/name).write_text(json.dumps(obj,indent=2))
key=json.loads((ROOT/'.credentials/owner.json').read_text())['api_key']
c=httpx.Client(base_url='http://127.0.0.1:3000',headers={'Authorization':'Bearer '+key},timeout=60)
def request(method,path,**kw):
 r=c.request(method,path,**kw)
 if r.is_error: raise RuntimeError(f'{r.status_code}: {r.text}')
 return r
X,y=make_regression(n_samples=2500,n_features=20,n_informative=15,noise=10,random_state=2026)
Xtr,Xte,ytr,yte=train_test_split(X,y,train_size=2000,test_size=500,random_state=2026)
cols=[f'feature_{i}' for i in range(20)]
train=pd.DataFrame(Xtr,columns=cols);train['target']=ytr
test=pd.DataFrame(Xte,columns=cols)
train.to_csv(OUT/'train.csv',index=False);test.to_csv(OUT/'test.csv',index=False)
pd.DataFrame({'input_row':np.arange(500),'target':yte}).to_csv(OUT/'test_truth.csv',index=False)
assert list(test.columns)==cols and 'target' not in test and test.shape==(500,20)
ids=[]
for name in ['train','test']:
 d=request('POST','/datasets',files={'file':(name+'.csv',(OUT/(name+'.csv')).read_bytes(),'text/csv')}).json();save(name+'_upload.json',d);ids.append(d['dataset_id'])
spec=dict(train=ids[0],test=ids[1],target='target',backend='tabicl',task='regression',fine_tune=False,use_cache=False,time_limit=30,seed=2026)
save('request.json',spec)
submission=request('POST','/predict',json=spec).json();save('submission.json',submission);jid=submission['job_id'];print('NEW JOB',jid,flush=True)
t0=time.monotonic()
while True:
 job=request('GET','/jobs/'+jid).json()
 save('job.json',job)
 if job['state'] in ['succeeded','failed','cancelled']:break
 if time.monotonic()-t0>900:raise TimeoutError('Job exceeded 900 seconds')
 time.sleep(.75)
assert job['state']=='succeeded',job
result=job['result'];assert result['cache_hit'] is False,result
rid=result['result_id'];blob=request('GET','/results/'+rid+'/download').content
(OUT/'result.parquet').write_bytes(blob)
pred=pd.read_parquet(io.BytesIO(blob));pred.to_csv(OUT/'predictions.csv',index=False)
print('RESULT',json.dumps(job), 'COLUMNS',list(pred.columns),flush=True)
assert len(pred)==500 and np.array_equal(pred.input_row.to_numpy(),np.arange(500))
yp=pred['prediction'].to_numpy();assert np.isfinite(yp).all()
residual=yte-yp
pd.DataFrame({'input_row':np.arange(500),'actual':yte,'prediction':yp,'residual_actual_minus_prediction':residual}).to_csv(OUT/'scored_predictions.csv',index=False)
def timestamp(v):
 if isinstance(v,(int,float)):return float(v)
 return datetime.fromisoformat(v.replace('Z','+00:00')).timestamp()
queue=timestamp(job['started'])-timestamp(job['created']);worker=timestamp(job['finished'])-timestamp(job['started'])
metrics=dict(task='regression',backend='tabicl',job_id=jid,result_id=rid,input_rows=2500,train_rows=2000,test_rows=500,feature_count=20,server_duration_seconds=result['duration_seconds'],queue_seconds=queue,worker_seconds=worker,cache_hit=result['cache_hit'],rmse=float(np.sqrt(mean_squared_error(yte,yp))),mae=float(mean_absolute_error(yte,yp)),r2=float(r2_score(yte,yp)),residual_definition='actual - prediction',duration_definition='Server duration includes preparation, fit and prediction; worker_seconds is finished minus started',source='New sklearn.make_regression: n_samples=2500, n_features=20, n_informative=15, noise=10, random_state=2026; train_test_split random_state=2026')
save('metrics.json',metrics)
fig,axes=plt.subplots(1,2,figsize=(13,6.8),dpi=130)
axes[0].scatter(yte,yp,s=15,alpha=.6,color='#286da8',edgecolors='none')
lo=min(yte.min(),yp.min());hi=max(yte.max(),yp.max());axes[0].plot([lo,hi],[lo,hi],'--',color='#c33c34',label='Ideal: y = x');axes[0].legend()
axes[0].set(xlabel='Actual target (synthetic units)',ylabel='Predicted target (synthetic units)',title='Actual vs predicted (500 test rows)');axes[0].grid(alpha=.2)
axes[1].hist(residual,bins=30,color='#286da8',edgecolor='white');axes[1].axvline(0,color='#c33c34',linestyle='--');axes[1].set(xlabel='Residual = actual − prediction (synthetic units)',ylabel='Test rows (count)',title='Residual distribution');axes[1].grid(axis='y',alpha=.2)
fig.suptitle('TabICL regression · synthetic data · 20 features · 2000 train / 500 test',fontsize=15)
fig.text(.5,.075,f"RMSE {metrics['rmse']:.2f}  |  MAE {metrics['mae']:.2f}  |  R² {metrics['r2']:.4f}  |  cache_hit = false",ha='center',fontsize=11)
fig.text(.5,.025,'Source: sklearn.make_regression (15 informative features, noise=10, seed=2026); new REST /predict job',ha='center',fontsize=9)
fig.tight_layout(rect=[0,.12,1,.93]);fig.savefig(OUT/'chart.png');fig.savefig(OUT/'chart.svg');plt.close(fig)
(OUT/'README.md').write_text(f"# Fresh TabICL regression\n\nNew API job: {jid}. Dataset generated with sklearn.make_regression, 2500 rows, 20 features, 15 informative, noise=10, random_state=2026. Split 2000/500 with random_state=2026. Test truth was saved separately and was not uploaded. Target uses arbitrary synthetic units. Residual = actual - prediction.\n\nRMSE: {metrics['rmse']:.4f}; MAE: {metrics['mae']:.4f}; R²: {metrics['r2']:.6f}. Cache hit: false. Server duration includes preparation/fit/predict. Queue and worker times use job timestamps.\n\nValidated 500 finite predictions, ordered input_row 0..499, 20 input features without target. See request.json, job.json and metrics.json for full details.\n")
print('ARTIFACTS READY',json.dumps(metrics),flush=True)
