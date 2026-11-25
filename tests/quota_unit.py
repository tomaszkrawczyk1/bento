"""Public-workspace limits: total GPU job quota, per-file byte cap. No GPU or network."""
import gzip,io,os,tempfile,unittest
os.environ['BENTO_DATA']=tempfile.mkdtemp()
os.environ['LIMITED_JOB_QUOTA']='3'
os.environ['LIMITED_MAX_BYTES']=str(1024)
import pandas as pd
from app import quota,store,tabular_io

PUBLIC={'id':'user_pub','email':'public@example.invalid','workspace':'public'}
TEAM={'id':'user_team','email':'team@example.invalid','workspace':'bento-team'}

class Upload:
 def __init__(self,data):self.file=io.BytesIO(data)

class QuotaTest(unittest.TestCase):
 def test_job_quota_is_total_and_workspace_scoped(self):
  for _ in range(3):store.enqueue({'time_limit':15},PUBLIC)
  with self.assertRaisesRegex(ValueError,'quota exhausted'):store.enqueue({'time_limit':15},PUBLIC)
  with store.db() as c:self.assertEqual(c.execute("SELECT COUNT(*) FROM jobs WHERE workspace='public'").fetchone()[0],3)
  self.assertEqual(quota.usage(PUBLIC)['gpu_jobs_used'],3)
  for _ in range(5):store.enqueue({'time_limit':15},TEAM)
  self.assertIsNone(quota.usage(TEAM))

 def test_upload_cap(self):
  quota.upload_size(Upload(b'x'*1024),PUBLIC)
  with self.assertRaisesRegex(ValueError,'limit'):quota.upload_size(Upload(b'x'*1025),PUBLIC)
  quota.upload_size(Upload(b'x'*10**6),TEAM)

 def test_decompression_cap(self):
  csv=('a,b\n'+'1,2\n'*2000).encode()
  path=os.path.join(os.environ['BENTO_DATA'],'bomb.csv.gz')
  with open(path,'wb') as f:f.write(gzip.compress(csv))
  quota.bind(PUBLIC)
  with self.assertRaisesRegex(ValueError,'limit'):tabular_io.read(path,'bomb.csv.gz')
  quota.bind(TEAM)
  df,_=tabular_io.read(path,'bomb.csv.gz');self.assertEqual(len(df),2000)

 def test_streaming_check(self):
  quota.bind(PUBLIC);quota.check(1024)
  with self.assertRaises(ValueError):quota.check(1025)
  quota.bind(TEAM);quota.check(10**12)

if __name__=='__main__':unittest.main()
