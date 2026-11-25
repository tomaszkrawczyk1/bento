"""Kaggle bytes stay on the host; MCP receives schema and immutable dataset IDs."""
import fcntl, hashlib, json, os, re, shutil, zipfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse, parse_qs
import pandas as pd
import pyarrow.parquet as pq
from app import store, ingest

CACHE = store.ROOT/'kaggle'
MAX_CACHE = int(os.environ.get('KAGGLE_CACHE_BYTES', '0')) # 0 = no application quota

def file_digest(path):
 with Path(path).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()

def check_access(user):
 allowed = os.environ.get('KAGGLE_WORKSPACES', 'bento-team').split(',')
 if user['workspace'] not in allowed: raise ValueError('Kaggle is not enabled for this workspace')

def reference(value, version=None):
 value=value.strip()
 if value.startswith('https://'):
  u=urlparse(value)
  if u.hostname not in ('kaggle.com','www.kaggle.com') or u.username or u.password or u.port not in (None,443):
   raise ValueError('Use a kaggle.com dataset URL or owner/slug')
  value=u.path.strip('/')
  if not value.startswith('datasets/'): raise ValueError('Only Kaggle datasets are supported, not competitions or notebooks')
  value=value[len('datasets/'):]
 m=re.fullmatch(r'([A-Za-z0-9_-]+/[A-Za-z0-9_-]+)(?:/(?:versions/)?([1-9][0-9]*))?',value)
 if not m: raise ValueError('Expected owner/slug, owner/slug/version or https://www.kaggle.com/datasets/owner/slug')
 embedded=int(m[2]) if m[2] else None
 if version is not None and (isinstance(version,bool) or not isinstance(version,int) or version<1): raise ValueError('Version must be a positive integer')
 if embedded and version and embedded!=version: raise ValueError('Conflicting dataset versions')
 return m[1].lower(), version or embedded

def safe_file(name):
 if not name or '\\' in name or any(x in ('','.','..') for x in name.split('/')) or PurePosixPath(name).is_absolute():
  raise ValueError('Invalid Kaggle file name')
 return name

class KaggleSource:
 """Use Kaggle's official authenticated SDK, never agent-supplied download URLs."""
 def __init__(self):
  config=Path(os.environ.get('KAGGLE_CONFIG_DIR',str(Path.home()/'.kaggle')))/'kaggle.json'
  if not config.exists(): raise ValueError('Kaggle credentials are not configured on the server')
  try:
   credentials=json.loads(config.read_text())
   if not credentials.get('username') or not credentials.get('key'): raise ValueError('Missing credentials')
   from kaggle.api.kaggle_api_extended import KaggleApi
   self.api=KaggleApi(); self.api.authenticate()
  except Exception: raise ValueError('Kaggle authentication could not be initialized') from None

 @contextmanager
 def client(self):
  # The pinned SDK otherwise leaves Requests without a socket timeout.
  from requests.adapters import HTTPAdapter
  class BoundedAdapter(HTTPAdapter):
   def send(self,request,**kwargs):
    if kwargs.get('timeout') is None: kwargs['timeout']=(5,15)
    return super().send(request,**kwargs)
  with self.api.build_kaggle_client() as c:
   http=c.http_client();http._init_session()
   http._session.mount('https://',BoundedAdapter())
   yield c

 def info(self, ref, version):
  from kagglesdk.datasets.types.dataset_api_service import ApiGetDatasetRequest,ApiListDatasetFilesRequest
  owner,slug=ref.split('/')
  q=ApiGetDatasetRequest();q.owner_slug=owner;q.dataset_slug=slug
  try:
   with self.client() as c:
    meta=json.loads(str(c.datasets.dataset_api_client.get_dataset(q)))
    version=version or int(meta['currentVersionNumber'])
    files=[];token=None
    for _ in range(5):
     q=ApiListDatasetFilesRequest();q.owner_slug=owner;q.dataset_slug=slug;q.dataset_version_number=version;q.page_size=200;q.page_token=token
     data=json.loads(str(c.datasets.dataset_api_client.list_dataset_files(q)))
     if data.get('errorMessage'): raise ValueError('Kaggle file listing failed')
     files.extend({'name':f['name'],'bytes':f.get('totalBytes') or 0,'supported':f['name'].lower().endswith(('.csv','.parquet'))} for f in data.get('datasetFiles',[]))
     token=data.get('nextPageToken')
     if not token: break
    if token: raise ValueError('Too many files; dataset file listing exceeds 1000 entries')
   return {'reference':ref,'version':version,'title':meta.get('title'),'license':meta.get('licenseName'),'private':bool(meta.get('isPrivate')),'files':files}
  except Exception: raise ValueError('Kaggle metadata unavailable; check reference, version, permissions and server credentials') from None

 def download(self, ref, version, filename, destination):
  from kagglesdk.datasets.types.dataset_api_service import ApiDownloadDatasetRequest
  q=ApiDownloadDatasetRequest();q.owner_slug,q.dataset_slug=ref.split('/');q.dataset_version_number=version;q.file_name=filename
  try:
   with self.client() as c:
    with c.datasets.dataset_api_client.download_dataset(q) as r:
     r.raise_for_status()
     with destination.open('wb') as output:
      for chunk in r.iter_content(1024*1024): output.write(chunk)
   if zipfile.is_zipfile(destination):
    with zipfile.ZipFile(destination) as z:
     candidates=[f for f in z.infolist() if not f.is_dir() and (f.filename==filename or f.filename==PurePosixPath(filename).name)]
     if len(candidates)!=1: raise ValueError('Unexpected Kaggle download archive')
     member=candidates[0]
     safe_file(member.filename)
     unpacked=destination.with_suffix('.unpacked')
     try:
      with z.open(member) as f, unpacked.open('wb') as output: shutil.copyfileobj(f,output,1024*1024)
      unpacked.replace(destination)
     finally: unpacked.unlink(missing_ok=True)
  except ValueError: raise
  except Exception: raise ValueError('Kaggle download failed; verify access and any required license acceptance on Kaggle') from None

def dataset_info(value,user,version=None):
 check_access(user);ref,version=reference(value,version)
 return KaggleSource().info(ref,version)

def frame(path,name,row_limit,columns):
 if row_limit is not None and (isinstance(row_limit,bool) or not isinstance(row_limit,int) or row_limit<1):
  raise ValueError('row_limit must be a positive integer')
 if columns is not None and (not columns or any(not isinstance(c,str) for c in columns) or len(set(columns))!=len(columns)):
  raise ValueError('Choose unique column names')
 try:
  if name.lower().endswith('.parquet'):
   f=pq.ParquetFile(path)
   if row_limit is None: return f.read(columns=columns).to_pandas()
   batch=next(f.iter_batches(batch_size=row_limit,columns=columns),None)
   return batch.to_pandas() if batch is not None else pd.DataFrame()
  return pd.read_csv(path,nrows=row_limit,usecols=columns)
 except Exception: raise ValueError('Cannot load tabular file/columns; check format and column names') from None

def import_dataset(value,user,file=None,version=None,row_limit=None,columns=None):
 check_access(user)
 ref,version=reference(value,version)
 if file is None and value.startswith('https://'): file=parse_qs(urlparse(value).query).get('select',[None])[0]
 if file: safe_file(file)
 # Serializes fills across requests/processes; partial bytes never become cache hits.
 CACHE.mkdir(mode=0o700,parents=True,exist_ok=True)
 with (CACHE/'.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  source=None;meta=None
  # An explicitly pinned file can be served with no Kaggle network calls at all.
  def key_for(v,f): return store.digest(json.dumps([user['workspace'],ref,v,f]))
  entry=CACHE/key_for(version,file) if version and file else None
  manifest=entry/'manifest.json' if entry else None
  if manifest and manifest.exists(): meta=json.loads(manifest.read_text())['metadata']
  if meta is None:
   source=KaggleSource();meta=source.info(ref,version);version=meta['version']
  supported=[f for f in meta['files'] if f['supported']]
  if not file:
   if len(supported)!=1: raise ValueError('Specify file from kaggle_dataset_info; dataset has zero or multiple CSV/Parquet files')
   file=supported[0]['name']
  selected=next((f for f in supported if f['name']==file),None)
  if not selected: raise ValueError('Select an existing CSV/Parquet file from kaggle_dataset_info')
  entry=CACHE/key_for(version,file);entry.mkdir(mode=0o700,exist_ok=True)
  manifest=entry/'manifest.json';payload=entry/'payload';hit=False;m={}
  if manifest.exists() and payload.exists():
   m=json.loads(manifest.read_text())
   hit=file_digest(payload)==m['sha256']
  if not hit:
   source=source or KaggleSource()
   tmp=entry/'payload.part'
   try:
    source.download(ref,version,file,tmp)
    if MAX_CACHE:
     used=sum(p.stat().st_size for p in CACHE.glob('*/payload') if p!=payload)
     if used+tmp.stat().st_size>MAX_CACHE: raise ValueError('Kaggle cache quota reached; ask server operator to remove unused cached files')
    tmp.replace(payload)
   finally: tmp.unlink(missing_ok=True)
   m={'metadata':meta,'sha256':file_digest(payload),'views':{}}
   # Raw download survives a rejected tabular selection (e.g. too many rows).
   tmp=entry/'manifest.part';tmp.write_text(json.dumps(m));tmp.replace(manifest)
  view=store.digest(json.dumps([row_limit,columns]))
  ident=m.get('views',{}).get(view)
  try: data=store.describe(ident,user) if ident else None
  except ValueError: data=None
  if data is None:
   df=frame(payload,file,row_limit,columns)
   data=store.save_dataset(df,user,f'{ref}/{version}/{file}',{'source':'kaggle','reference':ref,'version':version,'file':file,'license':meta.get('license'),'raw_access':'metadata_only','row_limit':row_limit,'selection':'first rows' if row_limit else 'all rows','columns':columns})
   m.setdefault('views',{})[view]=data['dataset_id']
  tmp=entry/'manifest.part';tmp.write_text(json.dumps(m));tmp.replace(manifest)
  return {**data,'cache_hit':hit,'kaggle':{'reference':ref,'version':version,'file':file,'bytes':payload.stat().st_size,'sha256':m['sha256']},'note':'Source records stay on the server. Use dataset_id for evaluate, predict or forecast; only schema is returned.'}
