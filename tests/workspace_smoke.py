import json,secrets,time
from pathlib import Path
import httpx
from app.store import db,uid,digest
from app.security import hash_password
cred=json.loads(Path('.credentials/owner.json').read_text());base='http://127.0.0.1:3000'
owner=httpx.Client(base_url=base,headers={'Authorization':'Bearer '+cred['api_key']})
dataset=owner.get('/datasets').json()[0]['id'];created=[]
try:
 for workspace,expected in [('bento-team',200),('isolated-test',400)]:
  ident=uid('test');key=secrets.token_urlsafe(32);created.append(ident)
  with db() as c:c.execute('INSERT INTO users(id,email,password,api_hash,workspace) VALUES(?,?,?,?,?)',(ident,ident+'@example.invalid',hash_password(secrets.token_urlsafe()),digest(key),workspace))
  client=httpx.Client(base_url=base,headers={'Authorization':'Bearer '+key})
  assert client.get('/datasets/'+dataset).status_code==expected
  with db() as c:c.execute('UPDATE users SET active=0 WHERE id=?',(ident,))
  assert client.get('/datasets').status_code==401
  client.close()
 print('Shared workspace, isolated workspace and immediate account revocation passed')
finally:
 with db() as c:
  for ident in created:c.execute('DELETE FROM users WHERE id=?',(ident,))
# No redirect for clients that remove the trailing slash from the MCP endpoint.
r=owner.post('/mcp',headers={'Accept':'application/json, text/event-stream'},json={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'canonical-path-test','version':'1'}}})
assert r.status_code==200,r.text
print('Canonical /mcp endpoint initializes without redirect')
