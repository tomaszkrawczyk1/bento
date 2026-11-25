import asyncio,json,time
from pathlib import Path
import httpx
from fastmcp import Client
root=Path.cwd();cred=json.loads((root/'.credentials/owner.json').read_text());headers={'Authorization':'Bearer '+cred['api_key']}
c=httpx.Client(base_url='http://127.0.0.1:3000',headers=headers,timeout=30)
for source in ('demo','postgres_demo'):
 r=c.get('/sources/'+source);r.raise_for_status();assert len(r.json())==2
 r=c.post('/datasets',json={'source':source,'sql':'SELECT * FROM regression_data LIMIT 120'});r.raise_for_status();d=r.json();assert d['rows']==120
 blocked=c.post('/datasets',json={'source':source,'sql':'DELETE FROM regression_data'});assert blocked.status_code==400
 print(source,'schema, SELECT and rejected DELETE passed')
# Real separate-test prediction and cached repeated request.
train=c.post('/datasets',files={'file':('train.csv',(root/'demo/regression-train.csv').read_bytes())}).json()['dataset_id']
test=c.post('/datasets',files={'file':('test.csv',(root/'demo/regression-test.csv').read_bytes())}).json()['dataset_id']
def wait(job):
 for _ in range(120):
  r=c.get('/jobs/'+job).json()
  if r['state'] in ('succeeded','failed'):break
  time.sleep(1)
 assert r['state']=='succeeded',r;return r['result']
spec={'train':train,'test':test,'target':'target','task':'regression','use_cache':True}
a=wait(c.post('/predict',json=spec).json()['job_id']);b=wait(c.post('/predict',json=spec).json()['job_id'])
assert b['cache_hit'] and b['cache_type']=='result';assert a['rows']==89
r=c.delete('/cache/'+a['context_id']);r.raise_for_status();assert r.json()['removed']>=1
print('Separate test data, result cache hit and scoped cache eviction passed')
async def browser_upload():
 async with Client('http://127.0.0.1:3000/mcp/',auth=cred['api_key']) as m:
  response=await m.call_tool('create_upload_link',{})
  data=response.data
  if not isinstance(data,dict):data=json.loads(response.content[0].text)
  url=data['upload_url'];r=httpx.get(url);r.raise_for_status()
  r=httpx.post(url,files={'file':('demo.csv',b'a,target\n1,0\n2,1\n')});r.raise_for_status()
  assert httpx.get(url).status_code==400
  print('Public browser upload and one-use ticket passed')
asyncio.run(browser_upload())
public=(root/'deploy/public-url.txt').read_text().strip()
assert httpx.get(public+'/datasets').status_code==404
assert httpx.get(public+'/info').status_code==404
print('Public proxy denies private REST routes')
