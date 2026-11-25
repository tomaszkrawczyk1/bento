"""URL provider adapters. Produce URLs, never execute downloaded page scripts."""
import base64,json,re
from urllib.parse import urlparse,urlunparse,urlencode,parse_qsl,unquote,quote

EXTENSIONS=('.csv','.data','.dat','.tab','.tsv','.txt','.json','.jsonl','.ndjson','.parquet','.pq','.xlsx','.xls','.xlsb','.ods','.feather','.arrow','.orc','.xml','.geojson','.avro','.sqlite','.sqlite3','.db','.npy','.npz','.h5','.hdf5','.zip','.gz','.bz2','.xz','.zst','.tar','.tgz')

def query(url,**values):
 u=urlparse(url);q=dict(parse_qsl(u.query,keep_blank_values=True));q.update(values)
 return urlunparse(u._replace(query=urlencode(q)))

def normalize(url,options):
 """Leave signed HTTP query strings byte-for-byte untouched unless adapting a share URL."""
 u=urlparse(url);host=(u.hostname or '').lower();parts=u.path.strip('/').split('/')
 if u.scheme=='s3':return 'https://s3.amazonaws.com/'+u.netloc+u.path+('?' + u.query if u.query else '')
 if u.scheme in ('gs','gcs'):return 'https://storage.googleapis.com/'+u.netloc+u.path+('?' + u.query if u.query else '')
 if u.scheme in ('abfs','abfss'):
  if not u.username or not host.endswith('.dfs.core.windows.net'):raise ValueError('Use abfs://container@account.dfs.core.windows.net/path')
  return 'https://'+host.replace('.dfs.','.blob.')+'/'+u.username+u.path+('?' + u.query if u.query else '')
 if u.scheme=='hf':
  path=(u.netloc+u.path).strip('/').split('/')
  if path[0]=='datasets':path=path[1:]
  if len(path)<2:raise ValueError('Use hf://datasets/owner/repo[/path]')
  repo,_,rev=path[1].partition('@');rev=rev or 'main'
  root='https://huggingface.co/datasets/'+path[0]+'/'+repo
  return root+'/resolve/'+quote(rev,safe='')+'/'+'/'.join(path[2:]) if len(path)>2 else root
 if u.scheme=='doi':return 'https://doi.org/'+(u.netloc+u.path)
 if host in ('github.com','www.github.com') and len(parts)>=4 and parts[2]=='blob':
  return urlunparse(u._replace(path=u.path.replace('/blob/','/raw/',1)))
 if host in ('github.com','www.github.com') and len(parts)>=2 and (len(parts)==2 or (len(parts)>=4 and parts[2]=='tree')):
  rev=parts[3] if len(parts)>=4 else options.get('revision','HEAD');path='/'.join(parts[4:])
  return 'https://api.github.com/repos/'+parts[0]+'/'+parts[1]+'/contents/'+path+'?'+urlencode({'ref':rev})
 if (host=='gitlab.com' or options.get('provider')=='gitlab') and '/-/blob/' in u.path:
  return urlunparse(u._replace(path=u.path.replace('/-/blob/','/-/raw/',1)))
 if host=='bitbucket.org' and len(parts)>=5 and parts[2]=='src':
  return 'https://api.bitbucket.org/2.0/repositories/'+parts[0]+'/'+parts[1]+'/src/'+'/'.join(parts[3:])
 if host in ('osf.io','www.osf.io') and len(parts)==1 and parts[0]:
  return 'https://api.osf.io/v2/files/'+parts[0]+'/'
 if u.path.endswith('/dataset.xhtml') and dict(parse_qsl(u.query)).get('persistentId'):
  return urlunparse(u._replace(path='/api/datasets/:persistentId/',query=urlencode({'persistentId':dict(parse_qsl(u.query))['persistentId']})))
 if u.path.endswith('/file.xhtml') and dict(parse_qsl(u.query)).get('fileId'):
  return urlunparse(u._replace(path='/api/access/datafile/'+dict(parse_qsl(u.query))['fileId'],query=''))
 if host=='gist.github.com' and len(parts)>=2:return 'https://api.github.com/gists/'+parts[1]
 if host in ('huggingface.co','hf.co'):
  if len(parts)>=6 and parts[0]=='datasets' and parts[3]=='blob':
   return urlunparse(u._replace(path=u.path.replace('/blob/','/resolve/',1)))
  if len(parts)>=3 and parts[0]=='datasets' and (len(parts)==3 or parts[3]=='tree'):
   rev=parts[4] if len(parts)>4 else options.get('revision','main')
   return 'https://huggingface.co/api/datasets/'+parts[1]+'/'+parts[2]+'/tree/'+quote(rev,safe='')+'?recursive=true&limit=1000'
 if host in ('www.dropbox.com','dropbox.com') and any(x in parts for x in ('s','scl')):return query(url,dl='1')
 if host in ('drive.google.com','www.drive.google.com'):
  m=re.search(r'/file/d/([^/]+)',u.path);q=dict(parse_qsl(u.query));ident=m[1] if m else q.get('id')
  if ident and not u.path.startswith('/uc'):return 'https://drive.google.com/uc?'+urlencode({'export':'download','id':ident,**({'resourcekey':q['resourcekey']} if q.get('resourcekey') else {})})
  m=re.search(r'/folders/([^/]+)',u.path)
  if m:return 'https://www.googleapis.com/drive/v3/files?'+urlencode({'q':"'"+m[1]+"' in parents and trashed=false",'fields':'files(id,name,mimeType,webContentLink),nextPageToken','pageSize':1000})
 if host=='docs.google.com' and len(parts)>=3 and parts[0]=='spreadsheets':
  q=dict(parse_qsl(u.query));frag=dict(parse_qsl(u.fragment));gid=q.get('gid',frag.get('gid',str(options.get('gid',0))))
  if len(parts)>3 and parts[1:3]==['d','e']:
   return 'https://docs.google.com/spreadsheets/d/e/'+parts[3]+'/pub?'+urlencode({'output':'csv','gid':gid})
  if parts[1]=='d' and not any(p in ('export','gviz') for p in parts):
   return 'https://docs.google.com/spreadsheets/d/'+parts[2]+'/export?'+urlencode({'format':'csv','gid':gid})
 if (host.endswith('.sharepoint.com') or host in ('onedrive.live.com','1drv.ms')) and host!='1drv.ms':
  if options.get('auth_profile') and options.get('provider')=='onedrive':
   encoded='u!'+base64.urlsafe_b64encode(url.encode()).decode().rstrip('=')
   return 'https://graph.microsoft.com/v1.0/shares/'+encoded+'/driveItem/content'
  if dict(parse_qsl(u.query)).get('download')!='1':return query(url,download='1')
 if host in ('zenodo.org','www.zenodo.org'):
  m=re.fullmatch(r'/records?/(\d+)/?',u.path)
  if m:return 'https://zenodo.org/api/records/'+m[1]
 if host.endswith('figshare.com') and host not in ('api.figshare.com','ndownloader.figshare.com'):
  m=re.search(r'/articles/(?:[^/]+/)*(\d+)(?:/(\d+))?/?$',u.path)
  if m:return 'https://api.figshare.com/v2/articles/'+m[1]+('/versions/'+m[2] if m[2] else '')
 if options.get('provider')=='ckan' and '/api/' not in u.path:
  if 'resource' in parts:
   ident=parts[parts.index('resource')+1];action='resource_show'
  else:ident=parts[-1];action='package_show'
  return urlunparse(u._replace(path='/api/3/action/'+action,query=urlencode({'id':ident})))
 if options.get('provider')=='socrata' and '/resource/' not in u.path and '/api/' not in u.path:
  ident=parts[-1]
  if re.fullmatch(r'[a-z0-9]{4}-[a-z0-9]{4}',ident):return urlunparse(u._replace(path='/resource/'+ident+'.json'))
 return url

def resources(data,url):
 """Recognize catalog metadata separately from tabular JSON records."""
 u=urlparse(url);out=[]
 def put(name,link,fmt=None):
  if isinstance(link,str) and link.startswith(('https://','http://','ftp://','ftps://','sftp://')):
   out.append({'name':str(name or link.rsplit('/',1)[-1]),'url':link,'format':fmt})
 if u.hostname=='huggingface.co' and u.path.startswith('/api/datasets/') and isinstance(data,list):
  root=u.path.split('/tree/')[0].replace('/api/datasets/','/datasets/');rev=u.path.split('/tree/',1)[1]
  for f in data:
   if f.get('type')=='file':put(f['path'],'https://huggingface.co'+root+'/resolve/'+rev+'/'+f['path'])
  return out
 if u.hostname=='api.github.com':
  if isinstance(data,list):
   for f in data:
    if f.get('type')=='file':put(f.get('path',f.get('name')),f.get('download_url'))
   return out
  if isinstance(data,dict) and data.get('type')=='file':put(data.get('name'),data.get('download_url'));return out
  if isinstance(data,dict) and isinstance(data.get('files'),dict):
   for name,f in data['files'].items():put(name,f.get('raw_url'))
   return out
 if not isinstance(data,dict):return []
 if u.hostname=='api.osf.io':
  entries=data.get('data',[]);entries=entries if isinstance(entries,list) else [entries]
  for entry in entries:
   if isinstance(entry,dict):put(entry.get('attributes',{}).get('name'),entry.get('links',{}).get('download'))
  if out:return out
 if u.hostname=='api.bitbucket.org' and isinstance(data.get('values'),list):
  for item in data['values']:
   if item.get('type')=='commit_file':put(item.get('path'),item.get('links',{}).get('self',{}).get('href'))
  return out
 version=data.get('data',{}).get('latestVersion',{}) if isinstance(data.get('data'),dict) else {}
 if isinstance(version,dict):
  for item in version.get('files',[]):
   file=item.get('dataFile',{});ident=file.get('id')
   if ident:put(file.get('filename'),urlunparse(u._replace(path='/api/access/datafile/'+str(ident),query='')),file.get('contentType'))
  if out:return out
 if data.get('@type')=='Dataset' or data.get('type')=='Dataset':
  links=data.get('contentUrl') or data.get('downloadURL') or []
  for link in links if isinstance(links,list) else [links]:put(data.get('name'),link,data.get('encodingFormat'))
 files=data.get('files')
 if isinstance(files,dict):files=list(files.get('entries',files).values())
 if isinstance(files,list):
  for f in files:
   if not isinstance(f,dict):continue
   links=f.get('links') or {};link=f.get('download_url') or f.get('webContentLink') or links.get('content') or links.get('self')
   if not link and f.get('id') and f.get('mimeType'):
    link='https://www.googleapis.com/drive/v3/files/'+f['id']+'?alt=media'
   put(f.get('key') or f.get('filename') or f.get('name'),link)
  if out:return out
 result=data.get('result',data)
 if isinstance(result,dict) and isinstance(result.get('resources'),list):
  for r in result['resources']:put(r.get('name') or r.get('id'),r.get('url'),r.get('format'))
 elif isinstance(result,dict) and result.get('url') and result.get('package_id'):put(result.get('name'),result['url'],result.get('format'))
 distributions=data.get('distribution',[])
 if isinstance(distributions,dict):distributions=[distributions]
 for f in distributions:
  if isinstance(f,dict):put(f.get('name'),f.get('contentUrl') or f.get('downloadURL') or f.get('downloadUrl'),f.get('encodingFormat'))
 return out

def supported(name):return name.lower().split('?',1)[0].endswith(EXTENSIONS)
