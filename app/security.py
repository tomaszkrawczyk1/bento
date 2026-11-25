import base64, hashlib, hmac, os, secrets, time
from app.store import db,digest,uid

def hash_password(password,salt=None):
 salt=salt or secrets.token_hex(16)
 return salt+':'+hashlib.scrypt(password.encode(),salt=salt.encode(),n=16384,r=8,p=1).hex()

def check_password(password,stored):
 return hmac.compare_digest(hash_password(password,stored.split(':')[0]),stored)

def authenticate(token):
 if not token:return None
 with db() as c:
  r=c.execute('SELECT id,email,workspace FROM users WHERE api_hash=? AND active=1',(digest(token),)).fetchone()
  if r:return dict(r)
  r=c.execute('SELECT u.id,u.email,u.workspace FROM oauth_tokens t JOIN users u ON u.id=t.user_id WHERE t.hash=? AND t.expires>? AND u.active=1',(digest(token),time.time())).fetchone()
  return dict(r) if r else None

def ticket(user,kind,object_id='',ttl=600):
 raw=secrets.token_urlsafe(32)
 with db() as c:c.execute('INSERT INTO tickets(hash,user_id,kind,object_id,expires) VALUES(?,?,?,?,?)',(digest(raw),user['id'],kind,object_id,time.time()+ttl))
 return raw

def read_ticket(raw,kind,consume=False):
 with db() as c:
  c.execute('BEGIN IMMEDIATE')
  r=c.execute('SELECT t.*,u.email,u.workspace FROM tickets t JOIN users u ON u.id=t.user_id WHERE t.hash=? AND t.kind=? AND t.expires>? AND t.used=0 AND u.active=1',(digest(raw),kind,time.time())).fetchone()
  if not r:raise ValueError('Link is invalid, used or expired')
  if consume:c.execute('UPDATE tickets SET used=1 WHERE hash=?',(digest(raw),))
  return {'id':r['user_id'],'email':r['email'],'workspace':r['workspace']},r['object_id']
