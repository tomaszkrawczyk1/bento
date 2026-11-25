"""Cross former row/column/class limits via actual service; test one-use JSON upload."""
import asyncio,json,time,io
from pathlib import Path
import httpx,numpy as np,pandas as pd
from fastmcp import Client
ROOT=Path(__file__).resolve().parents[1]
key=json.loads((ROOT/'.credentials/owner.json').read_text())['api_key']
base=(ROOT/'deploy/public-url.txt').read_text().strip()
c=httpx.Client(base_url='http://127.0.0.1:3000',headers={'Authorization':'Bearer '+key},timeout=90)
async def main():
 async with Client(base+'/mcp',auth=key,timeout=90) as m:
  r=await m.call_tool('model_info',{});assert r.data['limits']['rows'] is None and r.data['limits']['columns'] is None
  r=await m.call_tool('create_upload_link',{});ticket=r.data
  df=pd.DataFrame(np.arange(20001*301,dtype=np.int32).reshape(20001,301),columns=['x'+str(i) for i in range(301)])
  data=io.BytesIO();df.to_parquet(data,index=False);data.seek(0)
  with httpx.Client(timeout=90) as public:
   r=public.post(ticket['upload_endpoint'],files={'file':('beyond-old-limits.parquet',data,'application/octet-stream')})
   r.raise_for_status();d=r.json();assert d['rows']==20001 and len(d['columns'])==301
   assert public.post(ticket['upload_endpoint'],files={'file':('reuse.csv',b'x\n1\n','text/csv')}).status_code==400
  # >30 classes supported by TabICLv2's native many-class support. Small GPU test.
  rng=np.random.default_rng(42);x=rng.normal(size=(310,5));labels=np.repeat(np.arange(31),10)
  frame=pd.DataFrame(x,columns=['x'+str(i) for i in range(5)]);frame['target']=labels
  r=c.post('/datasets',files={'file':('many-classes.csv',frame.to_csv(index=False).encode(),'text/csv')});r.raise_for_status()
  j=c.post('/evaluate',json={'train':r.json()['dataset_id'],'target':'target','task':'classification'});j.raise_for_status();jid=j.json()['job_id']
  for _ in range(120):
   job=c.get('/jobs/'+jid).json()
   if job['state'] in ('succeeded','failed'):break
   await asyncio.sleep(1)
  assert job['state']=='succeeded',job
  report={'rows':d['rows'],'columns':len(d['columns']),'public_json_upload':True,'ticket_reuse_blocked':True,'classes':31,'default_backend':job['result']['backend'],'checkpoint':job['result']['checkpoint'],'job_id':jid}
  out=ROOT/'benchmarks/unlimited';out.mkdir(exist_ok=True,parents=True);(out/'smoke.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
asyncio.run(main())
