"""Real REST/GPU integration, with no secrets in output."""
import json,time,sys
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
credentials=json.loads((ROOT/'.credentials/owner.json').read_text())
c=httpx.Client(base_url='http://127.0.0.1:3000',headers={'Authorization':'Bearer '+credentials['api_key']},timeout=30)
assert httpx.get('http://127.0.0.1:3000/datasets').status_code==401
for task in ['classification','regression']:
 with open(ROOT/'demo'/f'{task}-train.csv','rb') as f:
  r=c.post('/datasets',files={'file':(f'{task}.csv',f,'text/csv')})
  r.raise_for_status();dataset=r.json()['dataset_id']
 job=c.post('/evaluate',json={'train':dataset,'target':'target','task':task,'backend':'tabicl','use_cache':True,'time_limit':60}).json()
 print('SUBMITTED',task,json.dumps(job),flush=True)
 if 'job_id' not in job:raise RuntimeError(job)
 for _ in range(240):
  result=c.get('/jobs/'+job['job_id']).json()
  if result['state'] in ('succeeded','failed','cancelled'):break
  time.sleep(1)
 print('RESULT',task,json.dumps(result),flush=True)
 assert result['state']=='succeeded',result
 output=c.get('/results/'+result['result']['result_id']).json()
 assert len(output['preview'])<=20
 (ROOT/'demo'/f'{task}-verification.json').write_text(json.dumps(result,indent=2))
print('SMOKE PASSED',flush=True)
