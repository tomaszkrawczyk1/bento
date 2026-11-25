import argparse,json,secrets,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.store import db,digest,uid
from app.security import hash_password
p=argparse.ArgumentParser();p.add_argument('action',choices=['add-user','disable-user','list-users']);p.add_argument('--email');p.add_argument('--workspace',default='bento-team');a=p.parse_args()
if a.action=='add-user':
 if not a.email:p.error('--email required')
 password=secrets.token_urlsafe(20);key=secrets.token_urlsafe(32);ident=uid('user')
 with db() as c:c.execute('INSERT INTO users(id,email,password,api_hash,workspace) VALUES(?,?,?,?,?)',(ident,a.email.lower(),hash_password(password),digest(key),a.workspace))
 out=Path(__file__).resolve().parents[1]/'.credentials';out.mkdir(mode=0o700,exist_ok=True)
 dest=out/(a.email.lower().replace('/','_')+'.json');dest.write_text(json.dumps({'email':a.email,'password':password,'api_key':key,'workspace':a.workspace},indent=2));dest.chmod(0o600)
 print('Credentials stored privately in',dest)
elif a.action=='disable-user':
 with db() as c:c.execute('UPDATE users SET active=0 WHERE email=?',(a.email.lower(),))
 print('User disabled; API key and OAuth tokens no longer accepted')
else:
 with db() as c:print(json.dumps([dict(r) for r in c.execute('SELECT id,email,workspace,active FROM users')],indent=2))
