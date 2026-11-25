"""Actual API defaults, both TabICLv2 tasks and a >50 MiB browser upload."""
import io,json,tempfile,time
from pathlib import Path
import httpx,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
key=json.loads((ROOT/'.credentials/owner.json').read_text())['api_key']
base=(ROOT/'deploy/public-url.txt').read_text().strip()
c=httpx.Client(base_url='http://127.0.0.1:3000',headers={'Authorization':'Bearer '+key},timeout=180)
info=c.get('/info').json();assert info['default_backend']=='tabicl' and info['default_model']=='TabICLv2'
assert info['limits']['file_size_limit'] is None
# Upload genuinely exceeds former byte limit, but holds a small legal table.
with tempfile.TemporaryFile(dir=ROOT/'data/uploads') as f:
 f.write(b'x,y\n')
 for i in range(20):f.write(f'{i},{i%2}\n'.encode())
 for _ in range(51):f.write(b'\n'*1024*1024)
 size=f.tell();f.seek(0)
 from app import security
 user=security.authenticate(key);ticket=security.ticket(user,'upload')
 with httpx.Client(timeout=180) as public:
  r=public.post(base+'/upload/'+ticket,files={'file':('large.csv',f,'text/csv')})
 assert r.is_success,(r.status_code,r.text[:200]);assert 'Uploaded' in r.text
print('PUBLIC UPLOAD',size,'bytes passed')
from sklearn.datasets import make_classification,make_regression
reports=[]
for task in ('classification','regression'):
 if task=='classification':X,y=make_classification(n_samples=100,n_features=5,n_informative=3,random_state=42)
 else:X,y=make_regression(n_samples=100,n_features=5,random_state=42)
 frame=pd.DataFrame(X,columns=['x'+str(i) for i in range(5)]);frame['target']=y
 r=c.post('/datasets',files={'file':('default.csv',frame.to_csv(index=False).encode(),'text/csv')});r.raise_for_status();ident=r.json()['dataset_id']
 spec={'train':ident,'target':'target','task':task} # deliberately omit backend
 r=c.post('/evaluate',json=spec);r.raise_for_status();jid=r.json()['job_id']
 for _ in range(80):
  j=c.get('/jobs/'+jid).json()
  if j['state'] in ('succeeded','failed'):break
  time.sleep(1)
 assert j['state']=='succeeded',j
 assert j['spec']['backend']=='tabicl' and j['result']['backend']=='tabicl'
 assert j['result']['checkpoint']=='tabicl-v2-20260212'
 reports.append({'task':task,'backend':j['result']['backend'],'checkpoint':j['result']['checkpoint'],'metrics':j['result']['metrics']})
print(json.dumps(reports,indent=2))
out=ROOT/'benchmarks/kaggle/defaults.json';out.write_text(json.dumps({'upload_bytes':size,'public_upload_status':200,'default_backend':info['default_backend'],'runs':reports},indent=2))
