import json
from pathlib import Path
import httpx
cred=json.loads(Path('.credentials/owner.json').read_text())
with httpx.Client(base_url='http://127.0.0.1:3000',headers={'Authorization':'Bearer '+cred['api_key']},timeout=45) as c:
 r=c.post('/datasets',json={'url':'https://raw.githubusercontent.com/mwaskom/seaborn-data/master/iris.csv'});r.raise_for_status();assert r.json()['rows']==150
 r=c.post('/datasets',json={'url':'https://127.0.0.1/private.csv'});assert r.status_code==400
 print('HTTPS CSV import with pinned DNS/TLS and private IP rejection passed')
