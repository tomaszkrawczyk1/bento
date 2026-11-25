"""Read tabular bytes independently of URL spelling or HTTP filename hints."""
import bz2,csv,fnmatch,gzip,io,json,lzma,re,shutil,sqlite3,tarfile,tempfile,zipfile
from pathlib import Path,PurePosixPath
import numpy as np,pandas as pd,pyarrow as pa,pyarrow.parquet as pq
from app import quota,store
from app.url_sources import supported

FORMATS=['csv','tsv','json','jsonl','geojson','parquet','xlsx','xls','xlsb','ods','html','xml','feather','arrow','orc','avro','sqlite','npy','npz','hdf5']
COMPRESSIONS=['zip','tar','tar.gz','gzip','bz2','xz','zstd']

class Selection(ValueError):
 def __init__(self,kind,choices,option):
  self.kind,self.choices,self.option=kind,choices,option
  super().__init__('Select '+option)
 def response(self):return {'status':'selection_required','kind':self.kind,'option':self.option,'choices':self.choices,'instruction':'Call dataset_from_url again with the same URL and the chosen option; downloaded bytes are cached.'}

def json_path(data,path):
 if not path:return data
 if path.startswith('/'):
  keys=[x.replace('~1','/').replace('~0','~') for x in path.split('/')[1:]]
 else:keys=path.split('.')
 for key in keys:data=data[int(key)] if isinstance(data,list) else data[key]
 return data

def sniff(path,name='',mime='',requested=None):
 with Path(path).open('rb') as f:head=f.read(4096)
 if requested and requested!='auto':
  fmt=requested.lower().replace('ndjson','jsonl').replace('excel','xlsx').replace('pq','parquet')
  if fmt not in FORMATS+COMPRESSIONS:raise ValueError('Unsupported format; see model_info URL import formats')
  return fmt
 if head.startswith(b'PAR1'):return 'parquet'
 if head.startswith(b'SQLite format 3\0'):return 'sqlite'
 if head.startswith(b'\x93NUMPY'):return 'npy'
 if head.startswith(b'\x89HDF\r\n\x1a\n'):return 'hdf5'
 if head.startswith(b'\x1f\x8b'):return 'gzip'
 if head.startswith(b'BZh'):return 'bz2'
 if head.startswith(b'\xfd7zXZ\0'):return 'xz'
 if head.startswith(b'\x28\xb5\x2f\xfd'):return 'zstd'
 if head.startswith(b'ARROW1') or head.startswith(b'\xff\xff\xff\xff'):return 'arrow'
 if head.startswith(b'FEA1'):return 'feather'
 if head.startswith(b'ORC'):return 'orc'
 if head.startswith(b'Obj\x01'):return 'avro'
 if head.startswith(b'\xd0\xcf\x11\xe0'):return 'xls'
 if zipfile.is_zipfile(path):
  with zipfile.ZipFile(path) as z:
   names=set(z.namelist())
   if '[Content_Types].xml' in names and ('xl/workbook.xml' in names or 'xl/workbook.bin' in names):return 'xlsx'
   if 'mimetype' in names and z.read('mimetype')==b'application/vnd.oasis.opendocument.spreadsheet':return 'ods'
   if name.lower().endswith('.npz'):return 'npz'
  return 'zip'
 if len(head)>262 and head[257:262]==b'ustar':return 'tar'
 lower=name.lower().split('?',1)[0]
 for fmt,extensions in [('jsonl',('.jsonl','.ndjson')),('json',('.json','.geojson')),('tsv',('.tsv','.tab')),('html',('.html','.htm')),('xml',('.xml',)),('parquet',('.parquet','.pq')),('xlsx',('.xlsx','.xlsb')),('ods',('.ods',)),('arrow',('.arrow','.feather')),('hdf5',('.h5','.hdf5'))]:
  if lower.endswith(extensions):return fmt
 text=head.lstrip(b'\xef\xbb\xbf \t\r\n').lower()
 if text.startswith((b'<!doctype html',b'<html',b'<table')) or 'text/html' in mime:return 'html'
 if text.startswith((b'{',b'[')) or 'json' in mime:return 'json'
 if text.startswith(b'<?xml'):return 'xml'
 if 'parquet' in mime:return 'parquet'
 return 'csv'

def text_encoding(path,option=None):
 if option:return option
 with Path(path).open('rb') as f:raw=f.read(65536)
 if raw.startswith((b'\xff\xfe\x00\x00',b'\x00\x00\xfe\xff')):return 'utf-32'
 if raw.startswith((b'\xff\xfe',b'\xfe\xff')):return 'utf-16'
 try:raw.decode('utf-8-sig');return 'utf-8-sig'
 except UnicodeDecodeError:
  from charset_normalizer import from_bytes
  best=from_bytes(raw).best()
  return best.encoding if best else 'cp1252'

def csv_frame(path,fmt,options):
 enc=text_encoding(path,options.get('encoding'))
 with Path(path).open('r',encoding=enc) as f:sample=f.read(65536)
 skip=options.get('csv_skiprows',options.get('skiprows'))
 lines=sample.splitlines()
 if skip is None:
  # Recognize a separate two-line metadata table only when the following
  # block has a different, consistent width. Ordinary blank CSV rows stay.
  skip=0
  for i in range(2,min(len(lines)-3,50)):
   if lines[i].strip() or any(not x.strip() for x in lines[:i]):continue
   for delimiter in (',',';','\t','|'):
    before=list(csv.reader(lines[:i],delimiter=delimiter));after=list(csv.reader(lines[i+1:i+5],delimiter=delimiter))
    if i==2 and len(before[0])==len(before[1]) and len(after)>=3 and len({len(x) for x in after})==1 and len(after[0])>1 and len(after[0])!=len(before[0]):
     skip=i+1;break
   if skip:break
 if not isinstance(skip,int) or isinstance(skip,bool) or skip<0:raise ValueError('csv_skiprows must be nonnegative')
 useful='\n'.join(x for x in lines[skip:] if x.strip() and not x.startswith('#'))
 sep=options.get('delimiter') or ('\t' if fmt=='tsv' else None)
 if sep is None:
  try:sep=csv.Sniffer().sniff(useful[:8192],delimiters=',;\t|').delimiter
  except csv.Error:sep=','
 if not isinstance(sep,str) or len(sep)!=1:raise ValueError('delimiter must be one character')
 kwargs={'encoding':enc,'sep':sep,'skiprows':skip,'comment':options.get('comment'),'decimal':options.get('decimal','.'),'nrows':options.get('row_limit')}
 if 'header' in options:kwargs['header']=options['header']
 if options.get('columns'):kwargs['usecols']=options['columns']
 if options.get('na_values') is not None:kwargs['na_values']=options['na_values']
 return pd.read_csv(path,**kwargs)

def json_frame(data,options):
 data=json_path(data,options.get('json_path'))
 if isinstance(data,dict) and data.get('type')=='FeatureCollection':
  data=[{**f.get('properties',{}),'geometry':f.get('geometry')} for f in data.get('features',[])]
 if isinstance(data,dict) and {'columns','data'}<=set(data):return pd.DataFrame(data['data'],columns=data['columns'])
 if isinstance(data,dict):
  for key in ('records','results','data','value','items','hourly','result'):
   value=data.get(key)
   if isinstance(value,list):data=value;break
   if isinstance(value,dict):
    if isinstance(value.get('records'),list):data=value['records'];break
    arrays={k:v for k,v in value.items() if isinstance(v,list)}
    if arrays and len({len(v) for v in arrays.values()})==1:data=arrays;break
 if isinstance(data,list):
  if not data:return pd.DataFrame()
  return pd.json_normalize(data) if isinstance(data[0],dict) else pd.DataFrame(data)
 if isinstance(data,dict):
  arrays={k:v for k,v in data.items() if isinstance(v,list)}
  if arrays and len({len(v) for v in arrays.values()})==1:return pd.DataFrame(arrays)
  if data and all(isinstance(v,dict) for v in data.values()):return pd.DataFrame.from_dict(data,orient='index').reset_index(names='key')
  return pd.json_normalize(data)
 raise ValueError('JSON must contain records or equally sized column arrays; use json_path to select the table')

def safe_member(name):
 name=name.replace('\\','/')
 if name.startswith('/') or any(x=='..' for x in name.split('/')) or re.match(r'^[A-Za-z]:',name):raise ValueError('Archive has an unsafe member path')
 return name

def choose(names,option,options,kind):
 requested=options.get(option)
 if requested is None:
  if len(names)==1:return names[0]
  raise Selection(kind,[{'name':str(x)} for x in names],option)
 if requested in names:return requested
 if isinstance(requested,int) and 0<=requested<len(names):return names[requested]
 raise ValueError('Requested '+option+' not found')

def postprocess(df,options):
 if options.get('columns'):
  if not set(options['columns'])<=set(df.columns):raise ValueError('Requested columns not found')
  df=df[options['columns']]
 if options.get('row_limit') is not None:df=df.head(options['row_limit'])
 if options.get('rename'):df=df.rename(columns=options['rename'])
 for c in options.get('parse_dates',[]):df[c]=pd.to_datetime(df[c],utc=True,errors='raise')
 for c in (c for c in df.columns if df[c].dtype==object):
  if df[c].map(lambda x:isinstance(x,(list,dict))).any():df[c]=df[c].map(lambda x:json.dumps(x) if isinstance(x,(list,dict)) else x)
 df.columns=[str(c) if not isinstance(c,tuple) else '.'.join(map(str,c)) for c in df.columns]
 return df

def read(path,name='',mime='',options=None,depth=0):
 options=dict(options or {});path=Path(path)
 if options.get('row_limit') is not None and (isinstance(options['row_limit'],bool) or not isinstance(options['row_limit'],int) or options['row_limit']<1):raise ValueError('row_limit must be a positive integer')
 if depth>8:raise ValueError('More than eight nested archive/compression layers')
 fmt=sniff(path,name,mime,options.get('format'))
 if fmt in ('gzip','bz2','xz','zstd','tar.gz'):
  with tempfile.TemporaryDirectory(dir=store.ROOT/'uploads') as tmp:
   dest=Path(tmp)/'unpacked';inner_name=re.sub(r'\.(gz|bz2|xz|zst|zstd)$','',name,flags=re.I)
   if fmt in ('gzip','tar.gz'):source=gzip.open(path,'rb')
   elif fmt=='bz2':source=bz2.open(path,'rb')
   elif fmt=='xz':source=lzma.open(path,'rb')
   else:
    import zstandard
    source=zstandard.open(path,'rb')
   with source as f,dest.open('wb') as out:quota.copy(f,out)
   opts={**options};opts.pop('format',None)
   return read(dest,inner_name,'',opts,depth+1)
 if fmt in ('zip','tar'):
  with tempfile.TemporaryDirectory(dir=store.ROOT/'uploads') as tmp:
   archive=zipfile.ZipFile(path) if fmt=='zip' else tarfile.open(path,'r:*')
   with archive as z:
    names=[x.filename for x in z.infolist() if not x.is_dir() and supported(x.filename)] if fmt=='zip' else [x.name for x in z.getmembers() if x.isfile() and supported(x.name)]
    requested=options.get('member')
    if isinstance(requested,list):
     selected=requested
     if not selected or not all(x in names for x in selected):raise ValueError('Requested member not found')
    elif isinstance(requested,str) and any(x in requested for x in '*?['):
     selected=[x for x in names if fnmatch.fnmatchcase(x,requested)]
     if not selected:raise ValueError('Requested member pattern matched no supported files')
    else:selected=[choose(names,'member',options,'archive_members')]
    frames=[]
    for index,name in enumerate(selected):
     safe_member(name);dest=Path(tmp)/str(index)
     with (z.open(name) if fmt=='zip' else z.extractfile(name)) as source,dest.open('wb') as out:quota.copy(source,out)
     opts={**options};opts.pop('format',None);opts.pop('member',None);opts.pop('row_limit',None)
     frames.append(read(dest,name,'',opts,depth+1)[0])
    if len(frames)>1 and any(list(f.columns)!=list(frames[0].columns) for f in frames[1:]):raise ValueError('Archive members have different columns; select compatible shards')
    frame=pd.concat(frames,ignore_index=True) if len(frames)>1 else frames[0]
    return postprocess(frame,{k:v for k,v in options.items() if k not in ('rename','parse_dates','columns')}),fmt
 if fmt in ('csv','tsv'):df=csv_frame(path,fmt,options)
 elif fmt=='parquet':df=pq.read_table(path,columns=options.get('columns')).to_pandas()
 elif fmt in ('json','jsonl','geojson'):
  enc=text_encoding(path,options.get('encoding'))
  with path.open(encoding=enc) as f:
   if fmt=='jsonl':data=[json.loads(line) for line in f if line.strip()]
   else:
    try:data=json.load(f)
    except json.JSONDecodeError:
     f.seek(0);data=[json.loads(line) for line in f if line.strip()]
  df=json_frame(data,options)
 elif fmt in ('xlsx','xls','xlsb','ods'):
  with pd.ExcelFile(path,engine='calamine') as book:
   sheet=choose(book.sheet_names,'sheet',options,'workbook_sheets')
   df=pd.read_excel(book,sheet_name=sheet,skiprows=options.get('csv_skiprows',0),nrows=options.get('row_limit'))
 elif fmt=='html':
  with path.open('rb') as f:tables=pd.read_html(f)
  i=choose(list(range(len(tables))),'table',options,'html_tables');df=tables[i]
 elif fmt=='xml':
  from defusedxml import ElementTree as ET
  root=ET.parse(path).getroot();rows=[]
  for node in root.findall(options.get('xml_path','./*')):
   row=dict(node.attrib)
   for child in node:row[child.tag.rsplit('}',1)[-1]]=child.text
   if row:rows.append(row)
  df=pd.DataFrame(rows)
 elif fmt in ('feather','arrow'):
  if fmt=='feather':df=pd.read_feather(path)
  else:
   with pa.memory_map(str(path),'r') as source:
    try:table=pa.ipc.open_file(source).read_all()
    except pa.ArrowInvalid:source.seek(0);table=pa.ipc.open_stream(source).read_all()
    df=table.to_pandas()
 elif fmt=='orc':df=pd.read_orc(path)
 elif fmt=='avro':
  from fastavro import reader
  with path.open('rb') as f:df=pd.json_normalize(list(reader(f)))
 elif fmt=='sqlite':
  c=sqlite3.connect(path.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
  try:
   c.execute('PRAGMA query_only=ON');c.execute('PRAGMA trusted_schema=OFF')
   tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND upper(sql) NOT LIKE 'CREATE VIRTUAL TABLE%'")]
   table=choose(tables,'table',options,'sqlite_tables');df=pd.read_sql_query('SELECT * FROM "'+table.replace('"','""')+'"',c)
  finally:c.close()
 elif fmt in ('npy','npz'):
  a=np.load(path,allow_pickle=False)
  if fmt=='npz':
   try:key=choose(list(a.files),'array',options,'numpy_arrays');arr=a[key]
   finally:a.close()
  else:arr=a
  df=pd.DataFrame.from_records(arr) if arr.dtype.names else pd.DataFrame(arr)
 elif fmt=='hdf5':
  import h5py
  with h5py.File(path,'r') as f:
   datasets=[]
   def visit(name,obj):
    if isinstance(obj,h5py.Dataset) and obj.ndim in (1,2) and not obj.external and not obj.is_virtual:datasets.append(name)
   f.visititems(visit);key=choose(datasets,'array',options,'hdf5_datasets');arr=f[key][()]
   df=pd.DataFrame.from_records(arr) if arr.dtype.names else pd.DataFrame(arr)
 else:raise ValueError('No supported tabular reader for this file')
 return postprocess(df,options),fmt
