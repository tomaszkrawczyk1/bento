"""URL import integration tests with real file readers and deterministic HTTP upstreams."""
import bz2,gzip,io,json,lzma,os,sqlite3,tarfile,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import httpx,numpy as np,pandas as pd,pyarrow as pa,pyarrow.feather as feather,pyarrow.orc as orc
sandbox=tempfile.TemporaryDirectory(prefix='url-tests-',dir='data');os.environ['BENTO_DATA']=sandbox.name
from app import store,tabular_io as t,url_sources as s,url_ingest as u
store.init();USER={'id':'url-test','workspace':'a'};CSV=b'x,y\n1,2\n3,4\n'
class Readers(unittest.TestCase):
 def setUp(self):self.dir=tempfile.TemporaryDirectory(dir=store.ROOT/'uploads');self.root=Path(self.dir.name)
 def tearDown(self):self.dir.cleanup()
 def read(self,data,name='download',**opts):
  path=self.root/'input';path.write_bytes(data);return t.read(path,name,options=opts)[0]
 def test_csv_extensionless(self):self.assertEqual(self.read(CSV).shape,(2,2))
 def test_csv_delimiters_and_encoding(self):
  for sep in ['\t',';','|']:
   self.assertEqual(self.read(('a'+sep+'b\nżółć'+sep+'2\n').encode('utf-16')).shape,(1,2))
 def test_blank_lines_keep_rows(self):self.assertEqual(self.read(b'x,y\n1,2\n\n3,4\n').shape,(2,2))
 def test_preamble_explicit(self):self.assertEqual(self.read(b'metadata\n\nx,y\n1,2\n',csv_skiprows=2).shape,(1,2))
 def test_metadata_table_preamble_auto(self):self.assertEqual(self.read(b'lat,lon,elevation\n50,19,200\n\ntime,value\na,1\nb,2\nc,3\n').shape,(3,2))
 def test_json_orientations(self):
  cases=[[{'x':1,'y':2}],{'x':[1],'y':[2]},{'records':[{'x':1,'y':2}]},{'hourly':{'x':[1],'y':[2]}},{'columns':['x','y'],'data':[[1,2]]},{'type':'FeatureCollection','features':[{'properties':{'x':1},'geometry':None}]}]
  for obj in cases:self.assertEqual(len(self.read(json.dumps(obj).encode())),1)
 def test_json_path(self):self.assertEqual(self.read(b'{"nested":{"rows":[{"x":1}]}}',json_path='/nested/rows').shape,(1,1))
 def test_jsonl(self):self.assertEqual(self.read(b'{"x":1}\n{"x":2}\n').shape,(2,1))
 def test_compression(self):
  import zstandard
  for compress in [gzip.compress,bz2.compress,lzma.compress,zstandard.compress]:self.assertEqual(self.read(compress(CSV)).shape,(2,2))
 def test_zip_selection(self):
  out=io.BytesIO()
  with zipfile.ZipFile(out,'w') as z:z.writestr('a.csv',CSV);z.writestr('b.csv',CSV)
  with self.assertRaises(t.Selection):self.read(out.getvalue())
  self.assertEqual(self.read(out.getvalue(),member='a.csv').shape,(2,2))
  self.assertEqual(self.read(out.getvalue(),member='*.csv').shape,(4,2))
  self.assertEqual(self.read(out.getvalue(),member=['a.csv','b.csv'],row_limit=3).shape,(3,2))
 def test_zip_traversal(self):
  out=io.BytesIO()
  with zipfile.ZipFile(out,'w') as z:z.writestr('../escape.csv',CSV)
  with self.assertRaisesRegex(ValueError,'unsafe'):self.read(out.getvalue())
 def test_tar(self):
  out=io.BytesIO()
  with tarfile.open(fileobj=out,mode='w') as z:
   info=tarfile.TarInfo('table.csv');info.size=len(CSV);z.addfile(info,io.BytesIO(CSV))
  self.assertEqual(self.read(out.getvalue()).shape,(2,2))
 def test_parquet(self):
  out=io.BytesIO();pd.DataFrame({'x':[1,2]}).to_parquet(out);self.assertEqual(self.read(out.getvalue()).shape,(2,1))
 def test_excel(self):
  out=io.BytesIO()
  with pd.ExcelWriter(out,engine='openpyxl') as writer:
   pd.DataFrame({'x':[1]}).to_excel(writer,sheet_name='one',index=False);pd.DataFrame({'y':[2]}).to_excel(writer,sheet_name='two',index=False)
  with self.assertRaises(t.Selection):self.read(out.getvalue())
  self.assertEqual(list(self.read(out.getvalue(),sheet='two').columns),['y'])
 def test_arrow(self):
  table=pa.table({'x':[1,2]})
  for stream in [False,True]:
   out=pa.BufferOutputStream()
   with (pa.ipc.new_stream if stream else pa.ipc.new_file)(out,table.schema) as writer:writer.write_table(table)
   self.assertEqual(self.read(out.getvalue().to_pybytes()).shape,(2,1))
 def test_feather_orc_avro(self):
  table=pa.table({'x':[1,2]});out=io.BytesIO();feather.write_feather(table,out);self.assertEqual(self.read(out.getvalue()).shape,(2,1))
  out=io.BytesIO();orc.write_table(table,out);self.assertEqual(self.read(out.getvalue()).shape,(2,1))
  from fastavro import writer
  out=io.BytesIO();writer(out,{'type':'record','name':'r','fields':[{'name':'x','type':'long'}]},[{'x':1}]);self.assertEqual(self.read(out.getvalue()).shape,(1,1))
 def test_sqlite(self):
  path=self.root/'db';c=sqlite3.connect(path);c.execute('create table samples(x int)');c.execute('insert into samples values(1)');c.commit();c.close();self.assertEqual(t.read(path)[0].shape,(1,1))
 def test_numpy_hdf5(self):
  out=io.BytesIO();np.save(out,np.array([[1,2],[3,4]]));self.assertEqual(self.read(out.getvalue()).shape,(2,2))
  out=io.BytesIO();np.savez(out,x=np.array([[1,2]]));self.assertEqual(self.read(out.getvalue(),name='test.npz').shape,(1,2))
  import h5py
  path=self.root/'hdf'
  with h5py.File(path,'w') as f:f['rows']=np.array([[1,2],[3,4]])
  self.assertEqual(t.read(path)[0].shape,(2,2))
 def test_numpy_pickle_rejected(self):
  out=io.BytesIO();np.save(out,np.array([{'x':1}],dtype=object))
  with self.assertRaises(ValueError):self.read(out.getvalue())
 def test_html_xml(self):
  self.assertEqual(self.read(b'<table><tr><th>x</th></tr><tr><td>1</td></tr></table>').shape,(1,1))
  self.assertEqual(self.read(b'<?xml version="1.0"?><rows><row><x>1</x></row></rows>').shape,(1,1))
 def test_projection(self):self.assertEqual(self.read(CSV,columns=['x'],row_limit=1,rename={'x':'value'}).to_dict('list'),{'value':[1]})
class Providers(unittest.TestCase):
 def test_normalizers(self):
  cases={
   's3://bucket/a.csv':'https://s3.amazonaws.com/bucket/a.csv',
   'gs://bucket/a.csv':'https://storage.googleapis.com/bucket/a.csv',
   'abfss://files@account.dfs.core.windows.net/a.csv':'https://account.blob.core.windows.net/files/a.csv',
   'github.com':'github.com',
   'https://github.com/a/b/blob/main/a.csv':'https://github.com/a/b/raw/main/a.csv',
   'https://gitlab.com/a/b/-/blob/main/a.csv':'https://gitlab.com/a/b/-/raw/main/a.csv',
   'https://bitbucket.org/a/b/src/main/a.csv':'https://api.bitbucket.org/2.0/repositories/a/b/src/main/a.csv',
   'hf://datasets/a/b/a.csv':'https://huggingface.co/datasets/a/b/resolve/main/a.csv',
   'https://huggingface.co/datasets/a/b/blob/main/a.csv':'https://huggingface.co/datasets/a/b/resolve/main/a.csv',
   'https://drive.google.com/file/d/abc/view':'https://drive.google.com/uc?export=download&id=abc',
   'https://docs.google.com/spreadsheets/d/abc/edit#gid=2':'https://docs.google.com/spreadsheets/d/abc/export?format=csv&gid=2',
   'https://www.dropbox.com/s/abc/file.csv?dl=0':'https://www.dropbox.com/s/abc/file.csv?dl=1',
   'https://zenodo.org/records/123':'https://zenodo.org/api/records/123',
   'https://figshare.com/articles/dataset/sample/123':'https://api.figshare.com/v2/articles/123',
   'https://osf.io/abcde/':'https://api.osf.io/v2/files/abcde/',
   'doi:10.123/x':'https://doi.org/10.123/x'}
  for a,b in cases.items():self.assertEqual(s.normalize(a,{}),b)
 def test_signed_url_unchanged(self):
  url='https://bucket.s3.example/a?X-Signature=a%2Fb&X-Test=x+y&dup=1&dup=2';self.assertEqual(s.normalize(url,{}),url)
 def test_catalogs(self):
  cases=[({'files':[{'name':'a.csv','download_url':'https://files.test/a'}]},'https://api.figshare.com/x'),({'result':{'resources':[{'name':'a','url':'https://files.test/a.csv','format':'CSV'}]}},'https://ckan.test/api'),({'data':{'latestVersion':{'files':[{'dataFile':{'id':1,'filename':'a.csv'}}]}}},'https://dataverse.test/api/x'),({'@type':'Dataset','distribution':[{'contentUrl':'https://files.test/a.csv'}]},'https://catalog.test/x')]
  for data,url in cases:self.assertEqual(len(s.resources(data,url)),1)
class Network(unittest.TestCase):
 def setUp(self):
  self.calls=[];self.routes={};real_client=httpx.Client
  def handle(req):
   host=req.headers['host'];key=host+req.url.path+('?' + req.url.query.decode() if req.url.query else '')
   self.calls.append((key,dict(req.headers)));value=self.routes.get(key)
   if callable(value):return value(req)
   if value is None:return httpx.Response(404)
   if isinstance(value,bytes):return httpx.Response(200,content=value)
   return httpx.Response(value[0],**value[1])
  self.client=patch.object(u.httpx,'Client',lambda **kw:real_client(transport=httpx.MockTransport(handle),**kw));self.client.start()
  self.dns=patch.object(u.socket,'getaddrinfo',return_value=[(2,1,6,'',('8.8.8.8',443))]);self.dns.start()
  self.base='https://'+self._testMethodName+'.test'
 def tearDown(self):self.client.stop();self.dns.stop()
 def route(self,path,value):self.routes[self.base.removeprefix('https://')+path]=value
 def load(self,path='/data',**options):return u.import_url(self.base+path,USER,options)
 def test_cache_privacy_and_isolation(self):
  self.route('/data',CSV);a=self.load();b=self.load();self.assertEqual(a['dataset_id'],b['dataset_id']);self.assertEqual(len(self.calls),1);self.assertTrue(b['cache_hit']);self.assertEqual(a['preview'],[])
  c=u.import_url(self.base+'/data',{'id':'other','workspace':'b'});self.assertNotEqual(a['dataset_id'],c['dataset_id']);self.assertEqual(len(self.calls),2)
 def test_refresh(self):
  self.route('/data',CSV);a=self.load();self.route('/data',b'x,y\n9,8\n');b=self.load(refresh=True);self.assertNotEqual(a['sha256'],b['sha256']);self.assertEqual(b['rows'],1)
 def test_redirect_filename(self):
  self.route('/data',(302,{'headers':{'location':'/export'}}));self.route('/export',(200,{'content':CSV,'headers':{'content-disposition':'attachment; filename="table.csv"'}}));self.assertEqual(self.load()['rows'],2)
 def test_html_discovery(self):
  self.route('/data',b'<html><a href="/file.csv">Download</a></html>');self.route('/file.csv',CSV);self.assertEqual(self.load()['rows'],2)
 def test_catalog_selection(self):
  self.route('/data',(200,{'json':{'files':[{'name':x+'.csv','download_url':self.base+'/'+x} for x in ['a','b']]}}));self.route('/a',CSV);self.assertEqual(self.load()['status'],'selection_required');self.assertEqual(self.load(resource='a.csv')['rows'],2)
 def test_pagination_odata(self):
  self.route('/data',(200,{'json':{'value':[{'x':1}],'@odata.nextLink':'/page2'}}));self.route('/page2',(200,{'json':{'value':[{'x':2}]}}));self.assertEqual(self.load()['rows'],2)
 def test_pagination_link(self):
  self.route('/data',(200,{'json':[{'x':1}],'headers':{'link':'</page2>; rel="next"'}}));self.route('/page2',(200,{'json':[{'x':2}]}));self.assertEqual(self.load()['rows'],2)
 def test_pagination_offset(self):
  for offset,rows in [(0,[{'x':1},{'x':2}]),(2,[{'x':3}])]:self.route('/data?offset='+str(offset)+'&limit=2',(200,{'json':rows}))
  self.assertEqual(self.load(pagination={'page_size':2})['rows'],3)
 def test_pagination_repetition(self):
  for n in [0,2]:self.route('/data?offset='+str(n)+'&limit=2',(200,{'json':[{'x':1},{'x':2}]}))
  with self.assertRaisesRegex(ValueError,'identical'):self.load(pagination={'page_size':2})
 def test_auth_does_not_follow_to_other_host(self):
  self.route('/data',(302,{'headers':{'location':'https://other.test/file'}}));self.routes['other.test/file']=CSV
  with patch.object(u,'profile_for',return_value={'hosts':[self.base[8:]],'bearer_token':'secret'}):self.load(auth_profile='test')
  self.assertEqual(self.calls[0][1]['authorization'],'Bearer secret');self.assertNotIn('authorization',self.calls[1][1])
 def test_ssrf_and_redirect_ssrf(self):
  with patch.object(u.socket,'getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
   with self.assertRaisesRegex(ValueError,'Private'):self.load()
  self.route('/data',(302,{'headers':{'location':'https://localhost/x'}}))
  with patch.object(u.socket,'getaddrinfo',side_effect=[[(2,1,6,'',('8.8.8.8',443))],[(2,1,6,'',('127.0.0.1',443))]]):
   with self.assertRaisesRegex(ValueError,'Private'):self.load()
 def test_inspect(self):
  self.route('/data',CSV);r=self.load(inspect=True);self.assertEqual(r['status'],'ready');self.assertNotIn('dataset_id',r);self.assertNotIn('preview',r)
 def test_post_json_export(self):
  def handler(req):
   self.assertEqual(req.method,'POST');self.assertEqual(json.loads(req.content),{'query':'select x'})
   return httpx.Response(200,json=[{'x':1}])
  self.route('/data',handler);self.assertEqual(self.load(request={'method':'POST','json':{'query':'select x'}})['rows'],1)
 def test_profile_redirect_cannot_forward_post_body(self):
  self.route('/data',(307,{'headers':{'location':'https://other.test/export'}}))
  with self.assertRaisesRegex(ValueError,'Cross-host'):self.load(request={'method':'POST','json':{'query':'x'}})
 def test_catalog_pagination(self):
  self.route('/data',(200,{'json':{'files':[{'name':'a.csv','download_url':self.base+'/a'}],'next':'/page2'}}))
  self.route('/page2',(200,{'json':{'files':[{'name':'b.csv','download_url':self.base+'/b'}]}}));self.route('/b',CSV)
  self.assertEqual(self.load(resource='b.csv')['rows'],2)
 def test_max_pages_never_returns_partial_success(self):
  self.route('/data',(200,{'json':{'value':[{'x':1}],'next':'/page2'}}))
  with self.assertRaisesRegex(ValueError,'max_pages'):self.load(max_pages=1)
 def test_concurrent_imports(self):
  import concurrent.futures
  self.route('/data',CSV)
  with concurrent.futures.ThreadPoolExecutor(4) as pool:results=list(pool.map(lambda _:self.load(),range(4)))
  self.assertTrue(all(x['rows']==2 for x in results));self.assertEqual(len(self.calls),1)
 def test_unsupported_scheme(self):
  with self.assertRaisesRegex(ValueError,'schemes'):u.import_url('file:///etc/passwd',USER)
 def test_auth_profiles_workspace_scope(self):
  cfg=Path(sandbox.name)/'auth.json';cfg.write_text(json.dumps({'profiles':{'private':{'hosts':['files.test'],'workspaces':['a'],'bearer_token':'secret'}}}))
  with patch.dict(os.environ,URL_SOURCES_CONFIG=str(cfg)):
   self.assertEqual(u.profile_for('private',USER)['hosts'],['files.test'])
   with self.assertRaisesRegex(ValueError,'workspace'):u.profile_for('private',{'workspace':'b'})
if __name__=='__main__':
 try:unittest.main(verbosity=2)
 finally:sandbox.cleanup()
