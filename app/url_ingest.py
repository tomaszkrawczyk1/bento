"""Provider-neutral dataset import: resolve, stream/cache, inspect, decode, register."""
import base64,fcntl,fnmatch,ftplib,hashlib,io,json,logging,os,re,socket,ssl,tempfile,time
from email.message import Message
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlparse,urljoin,parse_qsl,urlencode,urlunparse,unquote
import httpx,pandas as pd
from app import quota,store,tabular_io as tabular,url_sources as providers

ROOT=store.ROOT/'url-cache';ROOT.mkdir(mode=0o700,exist_ok=True)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)

def profile_for(name,user):
 if not name:return {}
 path=Path(os.environ.get('URL_SOURCES_CONFIG','/run/secrets/url-sources.json'))
 if not path.exists():raise ValueError('URL authentication profiles are not configured')
 profiles=json.loads(path.read_text()).get('profiles',{})
 p=profiles.get(name)
 if not p or user['workspace'] not in p.get('workspaces',[]):raise ValueError('URL authentication profile not found in this workspace')
 if not p.get('hosts'):raise ValueError('URL authentication profile requires an exact host allowlist')
 return p

def addresses(u,profile):
 import ipaddress
 if not u.hostname:raise ValueError('URL must contain a hostname')
 permitted=profile.get('allow_private',False) and u.hostname.lower() in profile.get('hosts',[])
 found=socket.getaddrinfo(u.hostname,u.port or (443 if u.scheme=='https' else 22 if u.scheme=='sftp' else 21 if u.scheme in ('ftp','ftps') else 80),type=socket.SOCK_STREAM)
 if not found:raise ValueError('URL hostname did not resolve')
 for item in found:
  if not ipaddress.ip_address(item[4][0]).is_global and not permitted:raise ValueError('Private/local URL addresses are not accepted')
 return found

def auth_headers(u,profile):
 if u.hostname.lower() not in profile.get('hosts',[]):return {},{}
 if u.scheme=='http' and not profile.get('allow_insecure'):raise ValueError('This profile requires HTTPS')
 headers=dict(profile.get('headers',{}));query=dict(profile.get('query',{}))
 if profile.get('bearer_token'):headers['Authorization']='Bearer '+profile['bearer_token']
 basic=profile.get('basic')
 if basic:headers['Authorization']='Basic '+base64.b64encode((basic['username']+':'+basic['password']).encode()).decode()
 if profile.get('cookies'):headers['Cookie']='; '.join(k+'='+v for k,v in profile['cookies'].items())
 return headers,query

def network_download(url,destination,profile,request=None):
 """Every redirect is DNS-checked and IP-pinned. Secrets only go to configured hosts."""
 original=url;cookies={};seen=set();request=dict(request or {});method=request.get('method','GET').upper()
 if method not in ('GET','POST'):raise ValueError('Download request method must be GET or POST')
 body={'json':request['json']} if 'json' in request else {'data':request['form']} if 'form' in request else {}
 with httpx.Client(timeout=httpx.Timeout(60,connect=15),follow_redirects=False,trust_env=False) as client:
  for _ in range(16):
   url=providers.normalize(url,{})
   if url in seen:raise ValueError('URL redirect cycle')
   seen.add(url);u=urlparse(url)
   if u.scheme not in ('http','https','ftp','ftps','sftp'):raise ValueError('Supported URL schemes: http, https, ftp, ftps, sftp, s3, gs, abfs, hf and doi')
   if u.username or u.password:raise ValueError('Use a server-side auth_profile instead of credentials embedded in a URL')
   allowed=[x for x in os.environ.get('URL_ALLOWED_HOSTS','').split(',') if x]
   if allowed and u.hostname not in allowed:raise ValueError('Host is not on URL_ALLOWED_HOSTS')
   resolved=addresses(u,profile)
   if u.scheme in ('ftp','ftps','sftp'):return transfer_file(url,destination,profile,resolved)
   headers,params=auth_headers(u,profile);headers={'Accept':'*/*',**headers,'Host':u.netloc}
   if u.hostname=='api.github.com' and '/contents/' in u.path:headers['Accept']=headers.get('Accept') if headers.get('Accept')!='*/*' else 'application/vnd.github.raw+json'
   if cookies.get(u.hostname) and 'Cookie' not in headers:headers['Cookie']='; '.join(k+'='+v for k,v in cookies[u.hostname].items())
   request_url=url
   if params:
    q=dict(parse_qsl(u.query,keep_blank_values=True));q.update(params);request_url=urlunparse(u._replace(query=urlencode(q)))
   endpoint=httpx.URL(request_url).copy_with(host=resolved[0][4][0])
   client.cookies.clear() # Requests use pinned IPs. Cookies below are explicitly keyed by real host.
   extensions={'sni_hostname':u.hostname} if u.scheme=='https' else {}
   with client.stream(method,endpoint,headers=headers,extensions=extensions,**body) as response:
    for raw in response.headers.get_list('set-cookie'):
     parsed=SimpleCookie()
     try:parsed.load(raw)
     except Exception:continue
     cookies.setdefault(u.hostname,{}).update({k:v.value for k,v in parsed.items() if not v['domain'] or v['domain'].lstrip('.').lower()==u.hostname.lower()})
    if response.is_redirect:
     if 'location' not in response.headers:raise ValueError('Redirect lacks Location')
     target=urljoin(url,response.headers['location'])
     if method=='POST':
      if response.status_code in (301,302,303):method='GET';body={}
      elif urlparse(target).hostname!=u.hostname:raise ValueError('Cross-host POST redirect requires a direct export URL')
     url=target;continue
    if response.status_code in (401,403):raise ValueError('Source requires valid access/consent. Configure a scoped server-side auth_profile or use a public/signed download link')
    if not response.is_success:raise ValueError('Download returned HTTP '+str(response.status_code)+' from '+u.hostname)
    if response.headers.get('content-length','').isdigit():quota.check(int(response.headers['content-length']))
    with destination.open('wb') as f:
     total=0
     for chunk in response.iter_bytes(1024*1024):total+=len(chunk);quota.check(total);f.write(chunk)
    msg=Message();msg['Content-Disposition']=response.headers.get('content-disposition','')
    name=msg.get_filename() or unquote(Path(u.path).name) or 'download'
    return {'url':url,'host':u.hostname,'name':name,'mime':response.headers.get('content-type','').split(';')[0],'etag':response.headers.get('etag'),'link':response.headers.get('link'),'bytes':destination.stat().st_size}
 raise ValueError('Too many redirects')

def transfer_file(url,destination,profile,resolved):
 u=urlparse(url);host=u.hostname;matched=host in profile.get('hosts',[])
 if u.scheme in ('ftp','ftps'):
  ftp=ftplib.FTP_TLS(context=ssl.create_default_context()) if u.scheme=='ftps' else ftplib.FTP()
  try:
   ftp.connect(resolved[0][4][0],u.port or 21,timeout=30);ftp.host=host
   credentials=profile.get('basic',{}) if matched else {}
   ftp.login(credentials.get('username','anonymous'),credentials.get('password','bento-demo@example.invalid'))
   if u.scheme=='ftps':ftp.prot_p()
   ftp.trust_server_pasv_ipv4_address=False
   with destination.open('wb') as f:
    total=[0]
    def write(block):total[0]+=len(block);quota.check(total[0]);f.write(block)
    ftp.retrbinary('RETR '+unquote(u.path),write,blocksize=1024*1024)
  finally:ftp.close()
 else:
  if not matched or not profile.get('host_key_sha256'):raise ValueError('SFTP requires an auth_profile with username and a pinned host_key_sha256')
  import paramiko
  sock=socket.create_connection((resolved[0][4][0],u.port or 22),timeout=30);transport=paramiko.Transport(sock)
  try:
   transport.start_client(timeout=30)
   fingerprint='SHA256:'+base64.b64encode(hashlib.sha256(transport.get_remote_server_key().asbytes()).digest()).decode().rstrip('=')
   if fingerprint!=profile['host_key_sha256']:raise ValueError('SFTP host key mismatch')
   auth=profile.get('basic',{});username=profile.get('username') or auth.get('username')
   if profile.get('private_key'):
    key=None
    for cls in (paramiko.Ed25519Key,paramiko.RSAKey,paramiko.ECDSAKey):
     try:key=cls.from_private_key(io.StringIO(profile['private_key']),password=profile.get('key_passphrase'));break
     except paramiko.SSHException:pass
    if key is None:raise ValueError('SFTP private key could not be read')
    transport.auth_publickey(username,key)
   else:transport.auth_password(username,profile.get('password') or auth.get('password',''))
   sftp=paramiko.SFTPClient.from_transport(transport)
   try:sftp.get(unquote(u.path),str(destination))
   finally:sftp.close()
  finally:transport.close()
 return {'url':url,'host':host,'name':Path(unquote(u.path)).name,'mime':'','etag':None,'link':None,'bytes':destination.stat().st_size}

def download(url,user,options):
 profile=profile_for(options.get('auth_profile'),user)
 normalized=providers.normalize(url,options)
 key=store.digest(json.dumps([user['workspace'],normalized,profile,options.get('request')],sort_keys=True))
 entry=ROOT/key;entry.mkdir(mode=0o700,exist_ok=True)
 with (entry/'.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  manifest=entry/'manifest.json';payload=entry/'payload';meta=None
  ttl=options.get('cache_ttl',3600)
  if not isinstance(ttl,(int,float)) or ttl<0:raise ValueError('cache_ttl must be nonnegative seconds')
  if not options.get('refresh') and manifest.exists() and payload.exists():
   previous=json.loads(manifest.read_text())
   with payload.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
   if time.time()-previous['fetched_at']<ttl and sha==previous['sha256']:meta={**previous,'cache_hit':True}
  if meta is None:
   partial=entry/'download.part'
   try:
    data=network_download(normalized,partial,profile,options.get('request'))
    with partial.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
    partial.replace(payload)
   except ValueError:raise
   except Exception as e:raise ValueError('Source download failed ('+type(e).__name__+'); check network, authentication and the sharing link') from None
   finally:partial.unlink(missing_ok=True)
   meta={**data,'sha256':sha,'fetched_at':time.time(),'cache_hit':False}
   tmp=entry/'manifest.part';tmp.write_text(json.dumps(meta));tmp.replace(manifest)
 return payload,meta

def html_links(path,url,options):
 from bs4 import BeautifulSoup
 soup=BeautifulSoup(path.read_bytes(),'html.parser');out=[]
 # Google's public large-file confirmation is a download form, not a login form.
 if urlparse(url).hostname in ('drive.google.com','drive.usercontent.google.com'):
  form=soup.find('form',id='download-form')
  if form:
   action=urljoin(url,form.get('action',''));host=urlparse(action).hostname
   if host in ('drive.google.com','drive.usercontent.google.com'):
    data={x.get('name'):x.get('value','') for x in form.select('input[name]')}
    return [{'name':'confirmed-download','url':action+('?' if '?' not in action else '&')+urlencode(data),'confirmation':True}]
 for script in soup.select('script[type="application/ld+json"]'):
  try:data=json.loads(script.string or script.get_text())
  except ValueError:continue
  for obj in data if isinstance(data,list) else [data]:
   if isinstance(obj,dict):out.extend(providers.resources(obj,url))
 for a in soup.find_all('a',href=True):
  link=urljoin(url,a['href']);text=a.get_text(' ',strip=True)
  if link.startswith(('http://','https://','ftp://','ftps://','sftp://')) and (providers.supported(link) or a.has_attr('download') or re.search(r'download|export|raw',a['href'],re.I)):
   out.append({'name':a.get('download') or text or Path(urlparse(link).path).name,'url':link})
 # CKAN catalogs advertise their software in HTML, rather than in the URL.
 generator=soup.find('meta',attrs={'name':'generator'})
 if generator and 'ckan' in generator.get('content','').lower():
  api=providers.normalize(url,{**options,'provider':'ckan'})
  if api!=url:return [{'name':'CKAN dataset resources','url':api,'catalog':True}]
 refresh=soup.find('meta',attrs={'http-equiv':re.compile('refresh',re.I)})
 if refresh:
  m=re.search(r'url\s*=\s*[\'"]?([^\'"]+)',refresh.get('content',''),re.I)
  if m:out.append({'name':'redirected-download','url':urljoin(url,m[1]),'catalog':True})
 unique={item['url']:item for item in out if item['url']!=url}
 return list(unique.values())

def next_page(data,meta):
 if meta.get('link'):
  m=re.search(r'<([^>]+)>\s*;\s*rel=[\'"]?next',meta['link'])
  if m:return urljoin(meta['url'],m[1])
 if isinstance(data,dict):
  if data.get('nextPageToken'):return providers.query(meta['url'],pageToken=data['nextPageToken'])
  for path in ('@odata.nextLink','next','links.next','pagination.next','result._links.next','_links.next'):
   try:
    value=data.get(path) if path in data else tabular.json_path(data,path)
    if isinstance(value,dict):value=value.get('href')
    if isinstance(value,str) and value:return urljoin(meta['url'],value)
   except (KeyError,TypeError):pass
 return None

def select_resource(items,options):
 requested=options.get('resource')
 if requested is not None:
  matches=[x for x in items if x['name']==requested or x['url']==requested]
  if not matches:raise ValueError('Requested resource not found')
  return matches[0]
 candidates=[x for x in items if providers.supported(x['name']) or providers.supported(x['url']) or (x.get('format') or '').lower() in tabular.FORMATS]
 if len(candidates)==1:return candidates[0]
 if len(items)==1:return items[0]
 raise tabular.Selection('download_resources',[{'name':x['name'],'format':x.get('format'),'supported':x in candidates} for x in items],'resource')

def import_url(url,user,options=None,_seen=None):
 quota.bind(user)
 options=dict(options or {});seen=set(_seen or ())
 allowed={'inspect','resource','file','version','member','sheet','table','array','format','encoding','delimiter','decimal','header','csv_skiprows','skiprows','comment','na_values','json_path','xml_path','columns','rename','parse_dates','row_limit','provider','revision','gid','auth_profile','refresh','cache_ttl','paginate','pagination','max_pages','request'}
 if set(options)-allowed:raise ValueError('Unknown URL import option(s): '+', '.join(sorted(set(options)-allowed)))
 if options.get('columns') is not None and (not isinstance(options['columns'],list) or not all(isinstance(x,str) for x in options['columns'])):raise ValueError('columns must be a list of names')
 if options.get('request') is not None:
  request=options['request']
  if not isinstance(request,dict) or set(request)-{'method','json','form'}:raise ValueError('request supports only method, json or form; authentication belongs in a server profile')
  if 'json' in request and 'form' in request:raise ValueError('request must select either json or form')
 if options.get('pagination') is not None:
  pagination=options['pagination']
  if not isinstance(pagination,dict) or pagination.get('mode','offset') not in ('offset','page') or int(pagination.get('page_size',1000))<1:raise ValueError('pagination requires mode offset/page and a positive page_size')
 if options.get('max_pages') is not None and (not isinstance(options['max_pages'],int) or options['max_pages']<1):raise ValueError('max_pages must be a positive integer')
 if url in seen or len(seen)>16:raise ValueError('Dataset catalog/link cycle')
 seen.add(url)
 # A Kaggle dataset page is a catalog requiring Kaggle authentication, not HTML CSV.
 u=urlparse(url)
 if u.hostname in ('kaggle.com','www.kaggle.com') and u.path.startswith('/datasets/'):
  from app import kaggle_source
  if options.get('inspect'):return kaggle_source.dataset_info(url,user,options.get('version'))
  return kaggle_source.import_dataset(url,user,options.get('resource') or options.get('file'),options.get('version'),options.get('row_limit'),options.get('columns'))
 if options.get('pagination'):
  config=options['pagination'];url=providers.query(url,**{config.get('parameter','offset'):str(config.get('start',0)),config.get('limit_parameter','limit'):str(config.get('page_size',1000))})
 path,meta=download(url,user,options);fmt=tabular.sniff(path,meta['name'],meta['mime'],options.get('format'))
 data=None;items=[]
 if fmt=='json':
  try:
   with path.open(encoding=tabular.text_encoding(path,options.get('encoding'))) as f:data=json.load(f)
   if not options.get('json_path'):items=providers.resources(data,meta['url'])
  except (ValueError,UnicodeError):pass
 elif fmt=='html' and not options.get('format')=='html':items=html_links(path,meta['url'],options)
 try:
  if items:
   # Catalogs can themselves be paginated (HF, Drive, OSF, Bitbucket).
   catalog_urls={meta['url']};catalog_meta=meta;catalog_data=data
   while options.get('paginate',True):
    nxt=next_page(catalog_data,catalog_meta)
    if not nxt:break
    if nxt in catalog_urls:raise ValueError('API catalog pagination cycle')
    if options.get('max_pages') is not None and len(catalog_urls)>=options['max_pages']:raise ValueError('API catalog exceeds max_pages')
    catalog_urls.add(nxt);catalog_path,catalog_meta=download(nxt,user,options)
    with catalog_path.open(encoding=tabular.text_encoding(catalog_path)) as f:catalog_data=json.load(f)
    items.extend(providers.resources(catalog_data,catalog_meta['url']))
   selected=select_resource(items,options);opts={**options};opts.pop('resource',None);opts.pop('request',None);opts.pop('pagination',None)
   if selected.get('format') and selected['format'].lower() in tabular.FORMATS:opts.setdefault('format',selected['format'].lower())
   return import_url(selected['url'],user,opts,seen)
  view_key=store.digest(json.dumps({k:v for k,v in options.items() if k not in ('cache_ttl','refresh','inspect','auth_profile')},sort_keys=True)+meta['sha256'])
  view=path.parent/('view-'+view_key+'.json')
  if view.exists() and not options.get('inspect') and not options.get('refresh') and not (fmt=='json' and options.get('paginate',True)):
   try:
    stored=json.loads(view.read_text());description=store.describe(stored['dataset_id'],user)
    return {**description,'cache_hit':meta['cache_hit'],'format':stored['format'],'source_bytes':meta['bytes']}
   except ValueError:pass
  frame,fmt=tabular.read(path,meta['name'],meta['mime'],options)
  pagination=options.get('pagination');follow=options.get('paginate',True)
  frames=[frame];page_data=data;page_meta=meta;page_urls={meta['url']};page_hashes={meta['sha256']};pages=1
  # RFC Link, OData, JSON next links and explicitly described offset/page APIs.
  while fmt=='json' and follow:
   nxt=next_page(page_data,page_meta)
   if not nxt and pagination and len(frames[-1]):
    parameter=pagination.get('parameter','offset');size=int(pagination.get('page_size',1000));initial=int(pagination.get('start',0))
    if len(frames[-1])<size:break
    value=initial+pages*(1 if pagination.get('mode')=='page' else size)
    nxt=providers.query(meta['url'],**{parameter:str(value),pagination.get('limit_parameter','limit'):str(size)})
   if not nxt:break
   if nxt in page_urls:raise ValueError('API pagination cycle')
   maximum=options.get('max_pages')
   if maximum is not None and pages>=maximum:raise ValueError('API has more pages than requested max_pages; increase it or disable pagination explicitly')
   page_urls.add(nxt);p,m=download(nxt,user,options)
   if m['sha256'] in page_hashes:raise ValueError('API repeated an identical page; check pagination configuration')
   page_hashes.add(m['sha256'])
   with p.open(encoding=tabular.text_encoding(p)) as f:page_data=json.load(f)
   next_frame=tabular.postprocess(tabular.json_frame(page_data,options),options)
   if next_frame.empty:break
   frames.append(next_frame);pages+=1;page_meta=m
  if len(frames)>1:frame=tabular.postprocess(pd.concat(frames,ignore_index=True),options)
  if options.get('inspect'):
   return {'status':'ready','format':fmt,'rows':len(frame),'columns':[{'name':str(k),'dtype':str(v)} for k,v in frame.dtypes.items()],'cache_hit':meta['cache_hit'],'source_bytes':meta['bytes'],'pages':pages}
  provenance={'source':'url','host':meta['host'],'format':fmt,'raw_access':'metadata_only','source_sha256':meta['sha256'],'source_bytes':meta['bytes'],'pages':pages,'selection':{k:v for k,v in options.items() if k not in ('auth_profile','refresh','cache_ttl')}}
  result=store.save_dataset(frame,user,meta['name'],provenance)
  with tempfile.NamedTemporaryFile(mode='w',dir=view.parent,suffix='.part',delete=False) as f:
   json.dump({'dataset_id':result['dataset_id'],'format':fmt},f);temporary=Path(f.name)
  temporary.replace(view)
  return {**result,'cache_hit':meta['cache_hit'],'format':fmt,'source_bytes':meta['bytes'],'pages':pages}
 except tabular.Selection as e:return {**e.response(),'cache_hit':meta['cache_hit'],'source_bytes':meta['bytes']}
 except ValueError as e:
  # Do not leak malformed source rows or signed URLs in parser exception text.
  if type(e) is ValueError and str(e).startswith(('Requested ','row_limit','csv_skiprows','delimiter','JSON must','API ','Dataset ','Archive ','SFTP ')):raise
  raise ValueError('Could not decode the downloaded table ('+type(e).__name__+'). Set format, encoding, delimiter, csv_skiprows, json_path, member, sheet or table as needed; login/HTML pages require valid access or a direct download URL') from None
 except Exception as e:raise ValueError('Could not decode downloaded dataset ('+type(e).__name__+'); inspect format and parse options') from None
