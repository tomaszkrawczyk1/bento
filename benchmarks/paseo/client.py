"""Independent HTTP client; execute with server .venv/bin/python. No model imports."""
import asyncio, io, json, math, time
from pathlib import Path
import httpx
import numpy as np
import pandas as pd
from sklearn.datasets import make_regression
from sklearn.model_selection import train_test_split

ROOT = Path('/home/pc/sandbox/bento')
OUT = ROOT / 'data/benchmarks/paseo'
OUT.mkdir(parents=True, exist_ok=True)
BEGIN = time.perf_counter()
DEADLINE = BEGIN + 650
KEY = json.loads((ROOT/'.credentials/owner.json').read_text())['api_key']
CLIENT = httpx.Client(base_url='http://127.0.0.1:3000', headers={'Authorization': 'Bearer '+KEY}, timeout=40)
RAW, RUNS, ISSUES = [], [], []

def save():
    (OUT/'raw.json').write_text(json.dumps(RAW, indent=2, allow_nan=False))
    (OUT/'summary.json').write_text(json.dumps({'transport':'HTTP loopback on PC; public MCP tested separately', 'elapsed_seconds':time.perf_counter()-BEGIN, 'issues':ISSUES, 'runs':RUNS}, indent=2, allow_nan=False))

def request(method, path, **kw):
    r = CLIENT.request(method, path, **kw)
    try: body = r.json()
    except ValueError: body = {'body':r.text[:2000]}
    # Download tickets are credentials; do not persist them.
    def scrub(v):
        if isinstance(v, dict): return {k:scrub(x) for k,x in v.items() if k not in ('download_url','csv_download_url','api_key','password','access_token')}
        if isinstance(v, list): return [scrub(x) for x in v]
        return v.replace(KEY,'[REDACTED]') if isinstance(v,str) else v
    RAW.append({'method':method,'path':path,'status':r.status_code,'response':scrub(body)})
    save()
    r.raise_for_status()
    return body

async def public_mcp():
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport
    url = (ROOT/'deploy/public-url.txt').read_text().strip().rstrip('/')+'/mcp/'
    async with Client(StreamableHttpTransport(url, headers={'Authorization':'Bearer '+KEY}), timeout=30) as c:
        result = await c.call_tool('model_info', {})
        RAW.append({'public_mcp_url':url,'tool':'model_info','response':json.loads(result.model_dump_json()) if hasattr(result,'model_dump_json') else str(result)})
        save()

def upload(path):
    with path.open('rb') as f:
        d = request('POST','/datasets',files={'file':(path.name,f,'text/csv')})
    inspected = request('GET','/datasets/'+d['dataset_id'])
    assert inspected['rows']==len(pd.read_csv(path))
    assert [c['name'] for c in inspected['columns']]==list(pd.read_csv(path,nrows=0).columns)
    return inspected

def run(task, backend, stage, train, test, features, truth=None):
    if time.perf_counter()>DEADLINE: raise TimeoutError('Overall benchmark deadline reached')
    fine = task=='regression' and backend=='mitra'
    spec = dict(train=train['dataset_id'],test=test['dataset_id'],target='target',features=features,backend=backend,task=task,fine_tune=fine,time_limit=30,seed=2026,use_cache=stage!='A')
    start=time.perf_counter()
    submitted=request('POST','/predict',json=spec)
    submit_seconds=time.perf_counter()-start
    ident=submitted['job_id']
    while True:
        time.sleep(1.05)
        job=request('GET','/jobs/'+ident)
        if job['state'] in ('succeeded','failed','cancelled'): break
        if time.perf_counter()>DEADLINE:
            request('DELETE','/jobs/'+ident)
            raise TimeoutError('Deadline; cancellation requested for own job '+ident)
    wall=time.perf_counter()-start
    result=job.get('result') or {}
    record=dict(task=task,backend=backend,stage=stage,fine_tune=fine,feature_count=len(features),train_rows=train['rows'],test_rows=test['rows'],job_id=ident,result_id=result.get('result_id'),state=job['state'],cache_hit=result.get('cache_hit'),cache_type=result.get('cache_type'),context_id=result.get('context_id'),model_preparation_fit_and_prediction_seconds=result.get('duration_seconds'),worker_seconds=job['finished']-job['started'] if job.get('started') else None,queue_seconds=job['started']-job['created'] if job.get('started') else None,submit_http_seconds=submit_seconds,client_wall_seconds=wall,error=job.get('error'))
    RUNS.append(record);save()
    if job['state']!='succeeded':
        ISSUES.append('Failed '+ident);save();return record
    assert result['rows']==test['rows'] and result['test_rows']==test['rows'] and result['train_rows']==train['rows']
    assert result['features']==features and 'target' not in result['features']
    r=CLIENT.get('/results/'+result['result_id']+'/download');r.raise_for_status()
    (OUT/(ident+'.parquet')).write_bytes(r.content)
    pred=pd.read_parquet(io.BytesIO(r.content))
    assert len(pred)==test['rows'] and np.isfinite(pred['prediction'].to_numpy(dtype=float)).all()
    assert list(pred['input_row'])==list(range(test['rows']))
    record['validation']='success; rows, features, finite predictions and row order checked'
    if truth is not None:
        delta=pred['prediction'].to_numpy()-truth
        record.update(rmse=float(np.sqrt(np.mean(delta**2))),mae=float(np.mean(np.abs(delta))))
    print(json.dumps(record),flush=True);save()
    return record

def main():
    request('GET','/info')
    try: asyncio.run(public_mcp())
    except Exception as e:
        ISSUES.append('Public MCP error: '+type(e).__name__+': '+str(e).replace(KEY,'[REDACTED]'));save()
    ctr=upload(ROOT/'demo/classification-train.csv');cte=upload(ROOT/'demo/classification-test.csv')
    X,y=make_regression(n_samples=1250,n_features=20,n_informative=15,noise=10,random_state=2026)
    xt,xs,yt,ys=train_test_split(X,y,train_size=1000,test_size=250,random_state=2026)
    names=['feature_'+str(i) for i in range(20)]
    train=pd.DataFrame(xt,columns=names);train['target']=yt
    train.to_csv(OUT/'regression-train.csv',index=False)
    pd.DataFrame(xs,columns=names).to_csv(OUT/'regression-test.csv',index=False)
    pd.DataFrame({'target':ys}).to_csv(OUT/'regression-truth.csv',index=False)
    rtr=upload(OUT/'regression-train.csv');rte=upload(OUT/'regression-test.csv')
    assert 'target' not in [c['name'] for c in rte['columns']]
    try:
        request('POST','/predict',json=dict(train=rtr['dataset_id'],test=rte['dataset_id'],target='target',backend='tabicl',task='regression',fine_tune=True,time_limit=30))
        raise AssertionError('Unexpectedly accepted TabICL fine_tune=true; inspect API')
    except httpx.HTTPStatusError as e:
        assert e.response.status_code==400
        ISSUES.append('API rejects fine_tune=true for TabICL (HTTP 400); TabICL regression measured with false. Mitra regression uses true, time_limit=30.')
    for task,tr,te,truth in [('classification',ctr,cte,None),('regression',rtr,rte,ys)]:
        features=[c['name'] for c in tr['columns'] if c['name']!='target']
        assert set(features)<=set(c['name'] for c in te['columns'])
        for backend in ('tabicl','mitra'):
            run(task,backend,'A',tr,te,features,truth)
            b=run(task,backend,'B',tr,te,features,truth)
            if b['cache_hit']:
                if not b['context_id']: raise RuntimeError('Unexpected warm B without own evictable context; cannot claim cold inference')
                b['stage']='B_discarded_already_warm'
                request('DELETE','/cache/'+b['context_id'])
                b=run(task,backend,'B',tr,te,features,truth)
                assert not b['cache_hit']
            c=run(task,backend,'C',tr,te,features,truth)
            if c['state']=='succeeded' and not (c['cache_hit'] and c['cache_type']=='result'):
                ISSUES.append('C did not show exact-result cache: '+c['job_id'])
    save()

if __name__=='__main__':
    try: main()
    except Exception as e:
        ISSUES.append(type(e).__name__+': '+str(e).replace(KEY,'[REDACTED]'));save();raise
