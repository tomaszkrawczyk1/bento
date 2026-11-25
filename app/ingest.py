import io, ipaddress, os, re, socket, sqlite3, time, tempfile
from pathlib import Path
from urllib.parse import urlparse
import httpx, pandas as pd, pyarrow.parquet as pq, sqlglot, yaml
from sqlglot import exp
from app.store import ROOT,save_dataset
def load_bytes(data,name):
 return load_file(io.BytesIO(data),name)

def load_file(file,name):
 if name.lower().endswith('.parquet'):
  f=pq.ParquetFile(file)
  return f.read().to_pandas()
 if not name.lower().endswith('.csv'):raise ValueError('Supported uploads: .csv and .parquet')
 return pd.read_csv(file)

def fetch_url(url,user,options=None):
 from app.url_ingest import import_url
 return import_url(url,user,options)

def source_config():
 path=Path(os.environ.get('SOURCES_CONFIG','sources.yaml'))
 return yaml.safe_load(path.read_text()).get('sources',{}) if path.exists() else {}

def list_sources():
 return [{'name':name,'type':c['type'],'tables':c.get('tables',[])} for name,c in source_config().items()]

def connect(name):
 cfg=source_config().get(name)
 if not cfg:raise ValueError('Unknown source')
 if cfg['type']=='sqlite':
  path=Path(cfg['path']).resolve()
  c=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
  c.execute('PRAGMA query_only=ON');deadline=time.monotonic()+10
  c.set_progress_handler(lambda:int(time.monotonic()>deadline),10000)
 elif cfg['type']=='postgres':
  import psycopg
  c=psycopg.connect(os.environ[cfg['dsn_env']],options='-c default_transaction_read_only=on -c statement_timeout=10000')
 elif cfg['type']=='mysql':
  import pymysql
  from urllib.parse import unquote
  u=urlparse(os.environ[cfg['dsn_env']]);c=pymysql.connect(host=u.hostname,port=u.port or 3306,user=unquote(u.username),password=unquote(u.password or ''),database=u.path.lstrip('/'),read_timeout=10,write_timeout=10,connect_timeout=5)
  with c.cursor() as cur:cur.execute('SET TRANSACTION READ ONLY')
 else:raise ValueError('Unsupported source')
 return c,cfg

def validate_sql(sql,cfg):
 dialect={'postgres':'postgres','mysql':'mysql','sqlite':'sqlite'}[cfg['type']]
 trees=sqlglot.parse(sql,read=dialect)
 if len(trees)!=1 or not isinstance(trees[0],(exp.Select,exp.Union)):raise ValueError('One SELECT query is required')
 tree=trees[0]
 blocked=(exp.Insert,exp.Update,exp.Delete,exp.Create,exp.Drop,exp.Command,exp.Copy,exp.Into)
 if any(tree.find(t) for t in blocked):raise ValueError('Only read-only SELECT is allowed')
 ctes={x.alias for x in tree.find_all(exp.CTE)}
 tables=set(cfg.get('tables',[]))
 for table in tree.find_all(exp.Table):
  full='.'.join(x for x in (table.db,table.name) if x)
  if table.catalog or not isinstance(table.this,exp.Identifier) or (full not in tables and full not in ctes):raise ValueError('Query references a table outside the source allowlist')
 allowed={'COUNT','SUM','AVG','MIN','MAX','COALESCE','CAST','TRY_CAST','ROUND','ABS','LOWER','UPPER','LENGTH','SUBSTRING','NULLIF','CASE','IF','DATE_TRUNC','EXTRACT'}
 for fn in tree.find_all(exp.Func):
  name=fn.name.upper() if isinstance(fn,exp.Anonymous) else fn.sql_name().upper()
  if name not in allowed:raise ValueError('SQL function is not allowed: '+name)
 return tree.sql(dialect=dialect)

def query_source(name,sql,user):
 c,cfg=connect(name)
 try:
  query=validate_sql(sql,cfg)
  with_cursor=c.cursor()
  try:
   with_cursor.execute(f'SELECT * FROM ({query}) AS bento_input')
   rows=with_cursor.fetchall();cols=[x[0] for x in with_cursor.description]
  finally:with_cursor.close()
  return save_dataset(pd.DataFrame(rows,columns=cols),user,name,{'source':name,'sql':query})
 finally:c.close()

def describe_source(name):
 c,cfg=connect(name)
 try:
  result=[]
  for table in cfg.get('tables',[]):
   if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?',table):raise ValueError('Invalid configured table')
   cur=c.cursor();cur.execute(f'SELECT * FROM {table} LIMIT 3')
   result.append({'table':table,'columns':[x[0] for x in cur.description],'sample':[dict(zip([x[0] for x in cur.description],r)) for r in cur.fetchall()]});cur.close()
  return result
 finally:c.close()
