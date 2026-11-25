import asyncio,base64,hashlib,json,re,secrets
from pathlib import Path
from urllib.parse import urlparse,parse_qs
import httpx
from fastmcp import Client
async def main():
 base=Path('deploy/public-url.txt').read_text().strip() if Path('deploy/public-url.txt').exists() else 'http://127.0.0.1:3000'
 creds=json.loads(Path('.credentials/owner.json').read_text())
 async with httpx.AsyncClient(base_url=base,timeout=30,follow_redirects=False) as c:
  r=await c.get('/.well-known/oauth-protected-resource/mcp');r.raise_for_status()
  redirect='http://127.0.0.1:49321/callback'
  reg=await c.post('/oauth/register',json={'redirect_uris':[redirect],'client_name':'Integration verification'});reg.raise_for_status();client=reg.json()['client_id']
  verifier=secrets.token_urlsafe(48);challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
  page=await c.get('/oauth/authorize',params={'client_id':client,'redirect_uri':redirect,'response_type':'code','code_challenge_method':'S256','code_challenge':challenge,'state':'verification','resource':base+'/mcp'});page.raise_for_status()
  pending=re.search('name="pending" value="([^"]+)"',page.text)[1]
  login=await c.post('/oauth/approve',data={'pending':pending,'email':creds['email'],'password':creds['password']});assert login.status_code==303,login.text
  params=parse_qs(urlparse(login.headers['location']).query);assert params['state']==['verification']
  data={'grant_type':'authorization_code','client_id':client,'redirect_uri':redirect,'code':params['code'][0],'code_verifier':verifier}
  bad=await c.post('/oauth/token',data={**data,'code_verifier':'invalid'});assert bad.status_code==400
  token=await c.post('/oauth/token',data=data);token.raise_for_status()
  replay=await c.post('/oauth/token',data=data);assert replay.status_code==400
  async with Client(base+'/mcp/',auth=token.json()['access_token']) as m:
   result=await m.call_tool('list_datasets',{});assert not result.is_error
  print('OAuth PKCE, wrong-verifier rejection, one-use code and authenticated MCP passed',base)
asyncio.run(main())
