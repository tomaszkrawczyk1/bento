import json, logging, os, threading, time
import httpx,pandas as pd
from app.store import db,save_dataset,ROOT
LOG=logging.getLogger(__name__)
URLS={'tabicl':os.environ.get('TABICL_URL','http://127.0.0.1:3001'),'mitra':os.environ.get('MITRA_URL','http://127.0.0.1:3002'),'timestral':os.environ.get('TIMESTRAL_URL','http://127.0.0.1:3004')}

def run_forever():
 last_cleanup=0
 while True:
  r=None
  try:
   if time.time()-last_cleanup>60:
    from app.store import cleanup
    cleanup();last_cleanup=time.time()
   with db() as c:
    c.execute('BEGIN IMMEDIATE')
    r=c.execute("SELECT * FROM jobs WHERE state='queued' AND cancel=0 ORDER BY created LIMIT 1").fetchone()
    if r:c.execute("UPDATE jobs SET state='running',started=? WHERE id=?",(time.time(),r['id']))
   if not r:time.sleep(.5);continue
   spec=json.loads(r['spec']);spec['_job_id']=r['id'];backend=spec.get('backend','tabicl')
   # Only one dispatch thread across both GPU backends. Release inactive backend caches.
   with httpx.Client(timeout=15) as client:
    for other in URLS:
     if other!=backend:
      try:client.post(URLS[other]+'/clear',json={})
      except httpx.HTTPError:pass
   with httpx.Client(timeout=max(240,spec['time_limit']+240)) as client:
    response=client.post(URLS[backend]+'/run',json={'request':spec})
    if not response.is_success:raise RuntimeError(f'{backend} failed ({response.status_code}): '+response.text[:1500])
    result=response.json()
   with db() as c:cancel=c.execute('SELECT cancel FROM jobs WHERE id=?',(r['id'],)).fetchone()[0]
   if cancel:
    with db() as c:c.execute("UPDATE jobs SET state='cancelled',finished=? WHERE id=?",(time.time(),r['id']))
    continue
   user={'id':r['owner'],'workspace':r['workspace']}
   data=save_dataset(pd.DataFrame(result.pop('predictions')),user,r['id']+' predictions',{'job_id':r['id'],'spec':spec},kind='results')
   result.update(result_id=data['dataset_id'],preview=data['preview'],rows=data['rows'])
   with db() as c:c.execute("UPDATE jobs SET state='succeeded',result=?,finished=? WHERE id=?",(json.dumps(result),time.time(),r['id']))
  except Exception as e:
   LOG.exception('Job failed')
   if r:
    with db() as c:c.execute("UPDATE jobs SET state='failed',error=?,finished=? WHERE id=?",(str(e)[:2000],time.time(),r['id']))

def start():
 with db() as c:c.execute("UPDATE jobs SET state='failed',error='Gateway restarted during execution; submit again',finished=? WHERE state='running'",(time.time(),))
 t=threading.Thread(target=run_forever,daemon=True,name='single-gpu-dispatch');t.start()
 return t
