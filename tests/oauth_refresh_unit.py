"""Isolated OAuth integration checks, without GPU or production credentials."""
import asyncio,base64,hashlib,json,os,re,secrets,tempfile,time,unittest
from pathlib import Path
from urllib.parse import parse_qs,urlparse
import httpx
from fastapi import FastAPI

_tmp=tempfile.TemporaryDirectory(prefix='oauth-refresh-',dir=Path(__file__).resolve().parents[1]/'data')
os.environ['BENTO_DATA']=_tmp.name
from app import store,oauth
from app.security import hash_password,authenticate

class RefreshTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  with store.db() as c:
   for table in ('oauth_codes','oauth_refresh_tokens','oauth_tokens','oauth_clients','users'):c.execute('DELETE FROM '+table)
   c.execute('INSERT INTO users VALUES(?,?,?,?,?,?)',('user1','test@example.invalid',hash_password('test-only-password'),'unused','workspace1',1))
  app=FastAPI();app.state.base_url=lambda:'https://demo.invalid';app.include_router(oauth.router)
  self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://demo.invalid')
  self.redirect='http://127.0.0.1:49321/callback'
  self.client_id=(await self.client.post('/oauth/register',json={'redirect_uris':[self.redirect]})).json()['client_id']
 async def asyncTearDown(self):await self.client.aclose()
 async def code(self):
  verifier=secrets.token_urlsafe(48);challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
  p=await self.client.get('/oauth/authorize',params={'client_id':self.client_id,'redirect_uri':self.redirect,'response_type':'code','code_challenge_method':'S256','code_challenge':challenge,'resource':'https://demo.invalid/mcp','state':'original-state'})
  self.assertEqual(p.status_code,200)
  pending=re.search('name="pending" value="([^"]+)"',p.text)[1]
  approved=await self.client.post('/oauth/approve',data={'pending':pending,'email':'test@example.invalid','password':'test-only-password'})
  self.assertEqual(approved.status_code,303);query=parse_qs(urlparse(approved.headers['location']).query)
  self.assertEqual(query['state'],['original-state'])
  return dict(grant_type='authorization_code',code=query['code'][0],client_id=self.client_id,redirect_uri=self.redirect,code_verifier=verifier)
 async def issue(self):
  r=await self.client.post('/oauth/token',data=await self.code());self.assertEqual(r.status_code,200);return r.json()
 async def refresh(self,token,**kwargs):return await self.client.post('/oauth/token',data=dict(grant_type='refresh_token',client_id=self.client_id,refresh_token=token,**kwargs))
 async def test_original_pkce_and_code_replay(self):
  data=await self.code()
  self.assertEqual((await self.client.post('/oauth/token',data={**data,'code_verifier':'wrong'})).status_code,400)
  good=await self.client.post('/oauth/token',data=data);self.assertEqual(good.status_code,200)
  self.assertEqual(good.headers['cache-control'],'no-store');self.assertEqual(good.json()['expires_in'],3600)
  self.assertEqual((await self.client.post('/oauth/token',data=data)).status_code,400)
 async def test_rotation_hash_storage_and_replay_family_revocation(self):
  a=await self.issue();b=await self.refresh(a['refresh_token']);self.assertEqual(b.status_code,200);b=b.json()
  self.assertNotEqual(a['refresh_token'],b['refresh_token']);self.assertNotEqual(a['access_token'],b['access_token'])
  self.assertIsNotNone(authenticate(b['access_token']))
  with store.db() as c:
   rows=c.execute('SELECT * FROM oauth_refresh_tokens').fetchall()
   self.assertEqual(len(rows),2);self.assertEqual(sum(r['used'] for r in rows),1)
   self.assertTrue(all(r['hash'] not in (a['refresh_token'],b['refresh_token']) for r in rows))
   self.assertAlmostEqual(rows[0]['expires'],time.time()+30*86400,delta=5)
  self.assertEqual((await self.refresh(a['refresh_token'])).status_code,400)
  self.assertEqual((await self.refresh(b['refresh_token'])).status_code,400)
  self.assertIsNone(authenticate(b['access_token']));self.assertIsNone(authenticate(a['access_token']))
 async def test_wrong_client_does_not_consume_token(self):
  a=await self.issue()
  other=(await self.client.post('/oauth/register',json={'redirect_uris':[self.redirect]})).json()['client_id']
  wrong=await self.client.post('/oauth/token',data={'grant_type':'refresh_token','client_id':other,'refresh_token':a['refresh_token']})
  self.assertEqual(wrong.status_code,400);self.assertEqual((await self.refresh(a['refresh_token'])).status_code,200)
 async def test_expiry(self):
  a=await self.issue()
  with store.db() as c:c.execute('UPDATE oauth_refresh_tokens SET expires=?',(time.time()-1,))
  self.assertEqual((await self.refresh(a['refresh_token'])).status_code,400)
 async def test_revoked_user_refresh_and_code(self):
  a=await self.issue();code=await self.code()
  with store.db() as c:c.execute('UPDATE users SET active=0')
  self.assertEqual((await self.refresh(a['refresh_token'])).status_code,400)
  self.assertEqual((await self.client.post('/oauth/token',data=code)).status_code,400)
  self.assertIsNone(authenticate(a['access_token']))
 async def test_resource_and_scope_cannot_expand(self):
  a=await self.issue()
  self.assertEqual((await self.refresh(a['refresh_token'],resource='https://other.invalid/mcp')).json()['error'],'invalid_target')
  self.assertEqual((await self.refresh(a['refresh_token'],scope='admin')).json()['error'],'invalid_scope')
  self.assertEqual((await self.refresh(a['refresh_token'],resource='https://demo.invalid/mcp',scope='bento')).status_code,200)
 async def test_metadata_registration_and_legacy_client(self):
  meta=(await self.client.get('/.well-known/oauth-authorization-server')).json()
  self.assertIn('refresh_token',meta['grant_types_supported'])
  with store.db() as c:
   data=json.loads(c.execute('SELECT data FROM oauth_clients WHERE id=?',(self.client_id,)).fetchone()[0]);data['grant_types']=['authorization_code'];c.execute('UPDATE oauth_clients SET data=? WHERE id=?',(json.dumps(data),self.client_id))
  a=await self.issue();self.assertEqual((await self.refresh(a['refresh_token'])).status_code,200)
 async def test_expired_access_can_refresh(self):
  a=await self.issue()
  with store.db() as c:c.execute('UPDATE oauth_tokens SET expires=?',(time.time()-1,))
  self.assertIsNone(authenticate(a['access_token']));r=await self.refresh(a['refresh_token']);self.assertEqual(r.status_code,200);self.assertIsNotNone(authenticate(r.json()['access_token']))

if __name__=='__main__':unittest.main(verbosity=2)
