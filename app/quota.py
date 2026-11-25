"""Limits for shared/public workspaces: total GPU job quota and per-file byte cap."""
import contextvars,os,shutil
from app import store

LIMITED=set(x for x in os.environ.get('LIMITED_WORKSPACES','public').split(',') if x)
JOB_QUOTA=int(os.environ.get('LIMITED_JOB_QUOTA','100'))
MAX_BYTES=int(os.environ.get('LIMITED_MAX_BYTES',str(100*1024*1024)))
_limit=contextvars.ContextVar('bento_max_bytes',default=0)

def limited(user):return user['workspace'] in LIMITED

def take_job(user,conn):
 """Atomically consume one GPU job from the workspace quota inside the enqueue transaction."""
 if not limited(user):return
 conn.execute('INSERT OR IGNORE INTO quota(workspace,used) VALUES(?,0)',(user['workspace'],))
 cur=conn.execute('UPDATE quota SET used=used+1 WHERE workspace=? AND used<?',(user['workspace'],JOB_QUOTA))
 if cur.rowcount!=1:raise ValueError(f'Public demo GPU quota exhausted ({JOB_QUOTA} jobs in total). Self-host the project to continue.')

def usage(user):
 if not limited(user):return None
 with store.db() as c:r=c.execute('SELECT used FROM quota WHERE workspace=?',(user['workspace'],)).fetchone()
 used=r['used'] if r else 0
 return {'gpu_jobs_used':used,'gpu_jobs_total':JOB_QUOTA,'max_file_bytes':MAX_BYTES}

def bind(user):
 """Apply this user's byte cap to the current context (inherited by asyncio.to_thread)."""
 _limit.set(MAX_BYTES if limited(user) else 0)

def cap():return _limit.get()

def check(size):
 c=cap()
 if c and size>c:raise ValueError(f'File exceeds the public demo limit of {c//(1024*1024)} MB')

def copy(source,out,chunk=1024*1024):
 c=cap()
 if not c:return shutil.copyfileobj(source,out,chunk)
 total=0
 while block:=source.read(chunk):
  total+=len(block);check(total);out.write(block)

def upload_size(upload,user):
 if not limited(user):return
 f=upload.file;pos=f.tell();f.seek(0,2);size=f.tell();f.seek(pos)
 if size>MAX_BYTES:raise ValueError(f'File exceeds the public demo limit of {MAX_BYTES//(1024*1024)} MB')
