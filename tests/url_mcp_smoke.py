"""Verify deployed REST and public HTTPS MCP ingestion, including tool schema."""
import asyncio,json,time
from pathlib import Path
import httpx
from fastmcp import Client
async def main():
 key=json.loads(Path('.credentials/owner.json').read_text())['api_key'];base=Path('deploy/public-url.txt').read_text().strip()
 report=[]
 async with Client(base+'/mcp',auth=key,timeout=120) as m:
  tools=await m.list_tools();tool=next(t for t in tools if t.name=='dataset_from_url');assert 'options' in tool.input_schema['properties']
  info=await m.call_tool('model_info',{});assert not info.is_error;assert info.data['version']=='0.5.0';assert info.data['limits']['rows'] is None
  checks=[('github-share','https://github.com/mwaskom/seaborn-data/blob/master/iris.csv',{},150),('google-sheets','https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit#gid=0',{},30),('json-api','https://api.open-meteo.com/v1/forecast?latitude=50.26&longitude=19.02&hourly=temperature_2m&forecast_days=1',{'json_path':'hourly'},24),('archive','https://archive.ics.uci.edu/static/public/53/iris.zip',{'member':'iris.data','header':None},150),('kaggle','https://www.kaggle.com/datasets/uciml/iris',{'resource':'Iris.csv'},150)]
  for name,url,options,rows in checks:
   start=time.perf_counter();r=await m.call_tool('dataset_from_url',{'url':url,'options':options});assert not r.is_error,r;data=r.data;assert data['rows']==rows;assert data['source_records_hidden'];assert data['preview']==[]
   report.append({'name':name,'seconds':round(time.perf_counter()-start,3),'rows':rows,'columns':len(data['columns']),'cache_hit':data['cache_hit']});print(json.dumps(report[-1]),flush=True)
 async with httpx.AsyncClient(base_url='http://127.0.0.1:3000',headers={'Authorization':'Bearer '+key},timeout=60) as c:
  r=await c.post('/datasets',json={'url':'https://raw.githubusercontent.com/mwaskom/seaborn-data/master/iris.csv','options':{'row_limit':7,'columns':['species']}});r.raise_for_status();data=r.json();assert data['rows']==7 and len(data['columns'])==1;assert data['preview']==[]
  r=await c.get('/results/'+data['dataset_id']);assert r.status_code==400 # no source-record download escape
  r=await c.post('/datasets',json={'url':'https://127.0.0.1/private.csv'});assert r.status_code==400
 out=Path('benchmarks/url-import');out.mkdir(parents=True,exist_ok=True);(out/'public-mcp.json').write_text(json.dumps(report,indent=2));print('Public MCP options, REST selection, privacy and SSRF checks passed')
asyncio.run(main())
