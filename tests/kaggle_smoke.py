"""Real Kaggle -> authenticated public MCP -> GPU, with no source records in MCP."""
import asyncio,json,time
from pathlib import Path
import httpx
from fastmcp import Client

ROOT=Path(__file__).resolve().parents[1]
async def main():
 key=json.loads((ROOT/'.credentials/owner.json').read_text())['api_key']
 base=(ROOT/'deploy/public-url.txt').read_text().strip()
 timings={}
 async with Client(base+'/mcp',auth=key,timeout=60) as m:
  async def call(name,args):
   r=await m.call_tool(name,args);assert not r.is_error,r;return r.data
  names=[t.name for t in await m.list_tools()]
  assert {'kaggle_dataset_info','dataset_from_kaggle'}<=set(names)
  reference='uciml/breast-cancer-wisconsin-data'
  meta=await call('kaggle_dataset_info',{'reference':reference})
  args={'reference':reference,'version':meta['version'],'file':'data.csv'}
  for n in ('first','repeat'):
   start=time.monotonic();r=await call('dataset_from_kaggle',args)
   timings[n]={'seconds':time.monotonic()-start,'cache_hit':r['cache_hit'],'dataset_id':r['dataset_id']}
   assert not r['preview'] and r['source_records_hidden']
  assert timings['repeat']['cache_hit']
  assert timings['first']['dataset_id']==timings['repeat']['dataset_id']
  ident=r['dataset_id']
  desc=await call('describe_dataset',{'dataset_id':ident});assert not desc['preview']
  with httpx.Client(base_url='http://127.0.0.1:3000',headers={'Authorization':'Bearer '+key}) as c:
   assert c.get(f'/results/{ident}/download').status_code==400
   assert c.get(f'/results/{ident}').status_code==400
   assert c.post('/datasets',json={'kaggle':reference,'version':meta['version'],'file':'data.csv','row_limit':100,'columns':['radius_mean','diagnosis']}).json()['rows']==100
  # Exclude row identifier, target and the empty trailing CSV column.
  features=[c['name'] for c in desc['columns'] if c['name'] not in ('id','diagnosis') and not c['name'].startswith('Unnamed:')]
  job=await call('evaluate',{'train':ident,'target':'diagnosis','features':features,'backend':'tabicl','task':'classification','use_cache':False})
  for _ in range(80):
   j=await call('get_job',{'job_id':job['job_id']})
   if j['state'] in ('succeeded','failed'):break
   await asyncio.sleep(3)
  assert j['state']=='succeeded',j
  result=await call('get_result',{'result_id':j['result']['result_id']})
  assert result['download_url']
  report={'reference':reference,'version':meta['version'],'rows':desc['rows'],'features':len(features),'imports':timings,'source_preview':desc['preview'],'raw_download_status':400,'job_id':job['job_id'],'metrics':j['result']['metrics'],'model_seconds':j['result']['duration_seconds'],'mcp_tool_count':len(names)}
  out=ROOT/'benchmarks/kaggle';out.mkdir(exist_ok=True,parents=True)
  (out/'smoke.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':asyncio.run(main())
