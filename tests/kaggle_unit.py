"""Cache/privacy tests with a fake upstream; no Kaggle key/network is used."""
import concurrent.futures, io, json, os, tempfile, time, unittest, zipfile
from contextlib import nullcontext
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

temporary=tempfile.TemporaryDirectory(prefix='kaggle-test-',dir='data')
os.environ['BENTO_DATA']=temporary.name
os.environ['KAGGLE_WORKSPACES']='a,b'
from app import kaggle_source as k, store
RealSource=k.KaggleSource

class Upstream:
 downloads=0
 def info(self,ref,version):
  return {'reference':ref,'version':version or 2,'license':'CC0','files':[{'name':'table.csv','bytes':16,'supported':True}]}
 def download(self,ref,version,file,destination):
  type(self).downloads+=1
  destination.write_bytes(b'x,y\n1,0\n2,1\n')

class Tests(unittest.TestCase):
 def setUp(self):
  self.mock=patch.object(k,'KaggleSource',Upstream);self.mock.start()
  self.user={'id':'u','workspace':'a'}
  self.ref='owner/'+self._testMethodName.lower()
 def tearDown(self):self.mock.stop()
 def load(self,**kw):return k.import_dataset(self.ref,self.user,'table.csv',2,**kw)
 def test_cache_and_privacy(self):
  count=Upstream.downloads;a=self.load();b=self.load()
  self.assertFalse(a['cache_hit']);self.assertTrue(b['cache_hit'])
  self.assertEqual(a['dataset_id'],b['dataset_id']);self.assertEqual(Upstream.downloads,count+1)
  self.assertEqual(store.describe(a['dataset_id'],self.user)['preview'],[])
  # Cached pinned imports need neither credentials nor metadata access.
  with patch.object(k,'KaggleSource',side_effect=AssertionError('network')):self.assertTrue(self.load()['cache_hit'])
 def test_versions_and_teams(self):
  a=self.load();b=k.import_dataset(self.ref,self.user,'table.csv',1)
  other={'id':'v','workspace':'b'};c=k.import_dataset(self.ref,other,'table.csv',2)
  self.assertFalse(b['cache_hit']);self.assertFalse(c['cache_hit'])
  with self.assertRaises(ValueError):store.dataset(a['dataset_id'],other)
  with self.assertRaises(ValueError):k.import_dataset(self.ref,{'id':'z','workspace':'disabled'})
 def test_expired_identifier_reuses_bytes(self):
  a=self.load();n=Upstream.downloads
  with store.db() as db:db.execute('UPDATE datasets SET expires=0 WHERE id=?',(a['dataset_id'],))
  b=self.load();self.assertTrue(b['cache_hit']);self.assertNotEqual(a['dataset_id'],b['dataset_id']);self.assertEqual(n,Upstream.downloads)
 def test_concurrent_fill(self):
  n=Upstream.downloads
  with concurrent.futures.ThreadPoolExecutor(4) as pool:answers=list(pool.map(lambda _:self.load(),range(4)))
  self.assertEqual(Upstream.downloads,n+1);self.assertEqual(len({r['dataset_id'] for r in answers}),1)
 def test_integrity(self):
  self.load();n=Upstream.downloads
  key=store.digest(json.dumps(['a',self.ref,2,'table.csv']))
  (k.CACHE/key/'payload').write_bytes(b'corrupted')
  self.assertFalse(self.load()['cache_hit']);self.assertEqual(Upstream.downloads,n+1)
 def test_projection(self):
  a=self.load(row_limit=1,columns=['y']);self.assertEqual(a['rows'],1);self.assertEqual([c['name'] for c in a['columns']],['y'])
  with self.assertRaises(ValueError):self.load(row_limit=0)
  self.assertTrue(self.load()['cache_hit'])
 def test_quota(self):
  with patch.object(k,'MAX_CACHE',1):
   with self.assertRaisesRegex(ValueError,'quota'):self.load()
 def test_file_larger_than_old_limit(self):
  def large_download(source,ref,version,file,destination):
   with destination.open('wb') as f:
    f.write(b'x,y\n1,0\n')
    for _ in range(51): f.write(b'\n'*1024*1024)
  with patch.object(Upstream,'download',large_download):
   r=self.load(row_limit=1)
  self.assertGreater(r['kaggle']['bytes'],50*1024*1024)
  self.assertEqual(r['rows'],1);self.assertEqual(r['preview'],[])
  self.assertTrue(self.load(row_limit=1)['cache_hit'])
 def sdk_download(self,raw):
  class Response:
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def raise_for_status(self):pass
   def iter_content(self,size):yield raw
  source=object.__new__(RealSource)
  client=SimpleNamespace(datasets=SimpleNamespace(dataset_api_client=SimpleNamespace(download_dataset=lambda _:Response())))
  source.client=lambda:nullcontext(client)
  destination=Path(temporary.name)/'download.part'
  source.download('owner/dataset',2,'table.csv',destination)
  return destination
 def test_sdk_wrapped_zip(self):
  buffer=io.BytesIO()
  with zipfile.ZipFile(buffer,'w') as z:z.writestr('table.csv',b'x,y\n1,0\n')
  self.assertEqual(self.sdk_download(buffer.getvalue()).read_bytes(),b'x,y\n1,0\n')
 def test_sdk_rejects_unexpected_zip(self):
  buffer=io.BytesIO()
  with zipfile.ZipFile(buffer,'w') as z:z.writestr('../table.csv',b'x,y\n1,0\n')
  with self.assertRaisesRegex(ValueError,'archive'):self.sdk_download(buffer.getvalue())
 def test_references_and_paths(self):
  self.assertEqual(k.reference('https://www.kaggle.com/datasets/uciml/iris/versions/2'),('uciml/iris',2))
  for ref in ('https://evil.com/datasets/u/s','https://www.kaggle.com/competitions/a','owner/../secret','owner/slug/0'):
   with self.assertRaises(ValueError):k.reference(ref)
  for f in ('../table.csv','/table.csv','dir/../table.csv','a\\b.csv'):
   with self.assertRaises(ValueError):k.safe_file(f)

if __name__=='__main__':
 try:unittest.main()
 finally:temporary.cleanup()
