"""Durable, immutable dataset registry and job state for a single GPU host."""
import hashlib, json, os, secrets, shutil, sqlite3, time
from pathlib import Path
import pandas as pd
ROOT = Path(os.environ.get('BENTO_DATA', '/home/pc/sandbox/bento/data'))
ROOT.mkdir(parents=True, exist_ok=True)
for name in ('datasets','results','uploads','artifacts'): (ROOT/name).mkdir(exist_ok=True)
TTL = 7*86400

def db():
 c=sqlite3.connect(ROOT/'registry.sqlite',timeout=30)
 c.row_factory=sqlite3.Row
 c.execute('PRAGMA journal_mode=WAL')
 return c

def init():
 with db() as c:
  c.executescript('''
CREATE TABLE IF NOT EXISTS datasets(id TEXT PRIMARY KEY, workspace TEXT NOT NULL, owner TEXT NOT NULL, name TEXT, path TEXT, sha TEXT, rows INTEGER, cols TEXT, created REAL, expires REAL, provenance TEXT);
CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, workspace TEXT NOT NULL, owner TEXT NOT NULL, state TEXT, spec TEXT, result TEXT, error TEXT, created REAL, started REAL, finished REAL, cancel INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, email TEXT UNIQUE, password TEXT, api_hash TEXT UNIQUE, workspace TEXT, active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS oauth_clients(id TEXT PRIMARY KEY, data TEXT);
CREATE TABLE IF NOT EXISTS oauth_codes(hash TEXT PRIMARY KEY, data TEXT, expires REAL);
CREATE TABLE IF NOT EXISTS oauth_tokens(hash TEXT PRIMARY KEY, user_id TEXT, client_id TEXT, expires REAL);
CREATE TABLE IF NOT EXISTS oauth_refresh_tokens(hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, client_id TEXT NOT NULL, expires REAL NOT NULL, family TEXT NOT NULL, used INTEGER NOT NULL DEFAULT 0, access_hash TEXT NOT NULL, resource TEXT);
CREATE INDEX IF NOT EXISTS oauth_refresh_family ON oauth_refresh_tokens(family);
CREATE TABLE IF NOT EXISTS quota(workspace TEXT PRIMARY KEY, used INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS tickets(hash TEXT PRIMARY KEY, user_id TEXT, kind TEXT, object_id TEXT, expires REAL, used INTEGER DEFAULT 0);
''')


def digest(s): return hashlib.sha256(s.encode()).hexdigest()
def uid(prefix): return prefix+'_'+secrets.token_hex(12)
def clean_json(value):
 return json.loads(json.dumps(value,default=str,allow_nan=False))

def frame_preview(df,n=5): return json.loads(df.head(n).to_json(orient='records',date_format='iso'))

def save_dataset(df, user, name='dataset', provenance=None, kind='datasets'):
 if not isinstance(df,pd.DataFrame) or not len(df) or not len(df.columns): raise ValueError('Dataset must contain rows and columns')
 df.columns=df.columns.astype(str)
 if df.columns.duplicated().any(): raise ValueError('Duplicate column names')
 ident=uid('ds' if kind=='datasets' else 'result')
 path=ROOT/kind/(ident+'.parquet')
 df.to_parquet(path,index=False)
 
 with path.open('rb') as f: sha=hashlib.file_digest(f,'sha256').hexdigest()
 cols=[{'name':str(k),'dtype':str(v),'missing':int(df[k].isna().sum())} for k,v in df.dtypes.items()]
 with db() as c:
  c.execute('INSERT INTO datasets VALUES(?,?,?,?,?,?,?,?,?,?,?)',(ident,user['workspace'],user['id'],name,str(path),sha,len(df),json.dumps(cols),time.time(),time.time()+TTL,json.dumps(provenance or {})))
 return describe(ident,user)

def dataset(ident,user):
 with db() as c: r=c.execute('SELECT * FROM datasets WHERE id=? AND workspace=?',(ident,user['workspace'])).fetchone()
 if not r or r['expires']<time.time(): raise ValueError('Dataset not found or expired')
 return dict(r)

def describe(ident,user,limit=5):
 r=dataset(ident,user)
 provenance=json.loads(r['provenance'])
 restricted=provenance.get('raw_access')=='metadata_only'
 return {'dataset_id':r['id'],'name':r['name'],'rows':r['rows'],'columns':json.loads(r['cols']),'sha256':r['sha'],'created':r['created'],'expires':r['expires'],'owner':r['owner'],'workspace':r['workspace'],'provenance':provenance,'preview':[] if restricted else frame_preview(pd.read_parquet(r['path']),min(limit,20)),'source_records_hidden':restricted}

def datasets(user):
 with db() as c: rows=c.execute('SELECT id,name,rows,created,expires,owner FROM datasets WHERE workspace=? AND expires>? ORDER BY created DESC LIMIT 100',(user['workspace'],time.time())).fetchall()
 return [dict(r) for r in rows]

def submit(spec,user,operation):
 spec={'backend':'tabicl','task':'classification','fine_tune':False,'use_cache':False,**spec}
 train=dataset(spec['train'],user)
 if operation=='predict' and not spec.get('test'): raise ValueError('predict requires test dataset_id; use evaluate for holdout scoring')
 if spec.get('test'): dataset(spec['test'],user)
 cols=[x['name'] for x in json.loads(train['cols'])]
 if spec.get('target') not in cols: raise ValueError('Target column does not exist')
 features=spec.get('features') or [x for x in cols if x!=spec['target']]
 if not features or spec['target'] in features or not set(features)<=set(cols): raise ValueError('Invalid features')
 spec={**spec,'features':features,'operation':operation,'workspace':user['workspace']}
 if spec.get('backend','tabicl') not in ('tabicl','mitra'): raise ValueError('Unknown backend')
 if spec.get('task','classification') not in ('classification','regression'): raise ValueError('Unknown task')
 if spec.get('fine_tune') and spec.get('backend','tabicl')!='mitra': raise ValueError('fine_tune is supported only by Mitra')
 spec['time_limit']=max(15,min(int(spec.get('time_limit',120)),900))
 spec['seed']=int(spec.get('seed',42));spec['test_size']=float(spec.get('test_size',0.2))
 if not .1<=spec['test_size']<=.5:raise ValueError('test_size must be between .1 and .5')
 return enqueue(spec,user)

def enqueue(spec,user):
 ident=uid('job')
 from app import quota
 with db() as c:
  quota.take_job(user,c)
  c.execute('INSERT INTO jobs(id,workspace,owner,state,spec,created) VALUES(?,?,?,?,?,?)',(ident,user['workspace'],user['id'],'queued',json.dumps(spec),time.time()))
 return {'job_id':ident,'state':'queued','time_limit':spec['time_limit'],'note':'Poll get_job. Mitra fine-tuning can take substantially longer than TabICL; no benchmark accuracy is guaranteed.'}

def job(ident,user):
 with db() as c:r=c.execute('SELECT * FROM jobs WHERE id=? AND workspace=?',(ident,user['workspace'])).fetchone()
 if not r:raise ValueError('Job not found')
 r=dict(r);r['spec']=json.loads(r['spec']);r['result']=json.loads(r['result']) if r['result'] else None
 return r

def cleanup():
 # Expired identifiers cannot be used even before this maintenance pass.
 with db() as c:
  expired=c.execute('SELECT id,path FROM datasets WHERE expires<?',(time.time(),)).fetchall()
  for r in expired:
   Path(r['path']).unlink(missing_ok=True)
   c.execute('DELETE FROM datasets WHERE id=?',(r['id'],))
  for artifact in (ROOT/'artifacts').iterdir():
   candidates=artifact.iterdir() if artifact.name=='AutogluonModels' and artifact.is_dir() else [artifact]
   for candidate in candidates:
    if candidate.is_dir() and candidate.stat().st_mtime<time.time()-TTL:shutil.rmtree(candidate)
  for table in ('tickets','oauth_codes','oauth_tokens'):c.execute(f'DELETE FROM {table} WHERE expires<?',(time.time(),))

init()
