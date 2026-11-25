"""Small PKCE authorization-code server for this project, persistent opaque tokens."""
import base64,hashlib,html,json,secrets,time
from urllib.parse import urlencode,urlparse
from fastapi import APIRouter,Request,HTTPException
from fastapi.responses import HTMLResponse,JSONResponse,RedirectResponse
from app.store import db,digest,uid
from app.security import check_password
router=APIRouter()
ACCESS_TTL=3600
REFRESH_TTL=30*86400
TOKEN_HEADERS={'Cache-Control':'no-store','Pragma':'no-cache'}

def metadata(base):
 return {'issuer':base,'authorization_endpoint':base+'/oauth/authorize','token_endpoint':base+'/oauth/token','registration_endpoint':base+'/oauth/register','response_types_supported':['code'],'grant_types_supported':['authorization_code','refresh_token'],'code_challenge_methods_supported':['S256'],'token_endpoint_auth_methods_supported':['none'],'scopes_supported':['bento']}

@router.get('/.well-known/oauth-authorization-server')
async def server_meta(request:Request):return metadata(request.app.state.base_url())
@router.get('/.well-known/oauth-protected-resource')
@router.get('/.well-known/oauth-protected-resource/mcp')
async def resource_meta(request:Request):
 b=request.app.state.base_url();return {'resource':b+'/mcp','authorization_servers':[b],'scopes_supported':['bento'],'bearer_methods_supported':['header']}

@router.post('/oauth/register')
async def register(request:Request):
 data=await request.json();redirects=data.get('redirect_uris',[])
 if not redirects or len(redirects)>5:raise HTTPException(400,'redirect_uris required')
 for uri in redirects:
  u=urlparse(uri)
  if u.fragment or u.username or (u.scheme!='https' and not (u.scheme=='http' and u.hostname in ('localhost','127.0.0.1','::1'))):raise HTTPException(400,'Invalid redirect URI')
 grants=data.get('grant_types',['authorization_code','refresh_token'])
 if not isinstance(grants,list) or not grants or not set(grants)<={'authorization_code','refresh_token'}:raise HTTPException(400,'Unsupported grant_types')
 client=uid('client');record={'client_id':client,'client_name':str(data.get('client_name','MCP client'))[:100],'redirect_uris':redirects,'grant_types':list(dict.fromkeys(grants)),'response_types':['code'],'token_endpoint_auth_method':'none'}
 with db() as c:
  if c.execute('SELECT count(*) FROM oauth_clients').fetchone()[0]>=1000:raise HTTPException(429,'Client registration limit reached')
  c.execute('INSERT INTO oauth_clients VALUES(?,?)',(client,json.dumps(record)))
 return JSONResponse(record,status_code=201)

@router.get('/oauth/authorize',response_class=HTMLResponse)
async def authorize(request:Request):
 q=dict(request.query_params)
 with db() as c:r=c.execute('SELECT data FROM oauth_clients WHERE id=?',(q.get('client_id'),)).fetchone()
 if not r:raise HTTPException(400,'Unknown client; register first')
 client=json.loads(r[0])
 if q.get('redirect_uri') not in client['redirect_uris'] or q.get('response_type')!='code' or q.get('code_challenge_method')!='S256' or len(q.get('code_challenge',''))<43:raise HTTPException(400,'Invalid authorization request; PKCE S256 required')
 resource=q.get('resource')
 if resource and resource.rstrip('/')!=(request.app.state.base_url()+'/mcp'):raise HTTPException(400,'Invalid resource')
 pending=secrets.token_urlsafe(32)
 with db() as c:c.execute('INSERT INTO oauth_codes VALUES(?,?,?)',(digest(pending),json.dumps({'pending':True,**q}),time.time()+300))
 return HTMLResponse('<!doctype html><meta name="viewport" content="width=device-width"><title>Bento Tabular — sign in</title><style>body{font:17px system-ui;max-width:480px;margin:8vh auto;padding:24px}input,button{display:block;padding:12px;margin:16px 0;width:90%}</style><h1>Bento Tabular</h1><p>Allow '+html.escape(client['client_name'])+' to work with datasets and GPU jobs in your workspace.</p><form method="post" action="/oauth/approve"><input type="hidden" name="pending" value="'+pending+'"><label>Email<input type="email" name="email" required autocomplete="username"></label><label>Password<input type="password" name="password" required autocomplete="current-password"></label><button>Sign in and allow access</button></form>')

@router.post('/oauth/approve')
async def approve(request:Request):
 form=await request.form();pending=str(form.get('pending',''))
 with db() as c:
  c.execute('BEGIN IMMEDIATE')
  r=c.execute('SELECT data FROM oauth_codes WHERE hash=? AND expires>?',(digest(pending),time.time())).fetchone()
  u=c.execute('SELECT * FROM users WHERE email=? AND active=1',(str(form.get('email','')).lower(),)).fetchone()
  if not r or not u or not check_password(str(form.get('password','')),u['password']):raise HTTPException(401,'Invalid login or expired request')
  q=json.loads(r[0]);c.execute('DELETE FROM oauth_codes WHERE hash=?',(digest(pending),))
  code=secrets.token_urlsafe(32)
  c.execute('INSERT INTO oauth_codes VALUES(?,?,?)',(digest(code),json.dumps({**q,'pending':False,'user_id':u['id']}),time.time()+60))
 return RedirectResponse(q['redirect_uri']+('' if q['redirect_uri'].endswith('?') else '&' if '?' in q['redirect_uri'] else '?')+urlencode({'code':code,'state':q.get('state','')}),status_code=303)

@router.post('/oauth/token')
async def token(request:Request):
 f=dict(await request.form())
 def error(name='invalid_grant'):return JSONResponse({'error':name},400,headers=TOKEN_HEADERS)
 grant=f.get('grant_type')
 if grant not in ('authorization_code','refresh_token'):return error('unsupported_grant_type')
 if f.get('scope') and f['scope']!='bento':return error('invalid_scope')
 now=time.time()
 with db() as c:
  c.execute('BEGIN IMMEDIATE')
  client=c.execute('SELECT data FROM oauth_clients WHERE id=?',(f.get('client_id',''),)).fetchone()
  if not client:return error()
  registered=json.loads(client['data'])
  if grant=='authorization_code':
   if 'authorization_code' not in registered.get('grant_types',[]):return error('unauthorized_client')
   r=c.execute('SELECT data FROM oauth_codes WHERE hash=? AND expires>?',(digest(f.get('code','')),now)).fetchone()
   if not r:return error()
   q=json.loads(r[0]);challenge=base64.urlsafe_b64encode(hashlib.sha256(f.get('code_verifier','').encode()).digest()).decode().rstrip('=')
   if q.get('pending') or q.get('client_id')!=f.get('client_id') or q.get('redirect_uri')!=f.get('redirect_uri') or not secrets.compare_digest(challenge,q.get('code_challenge','')):return error()
   user_id=q['user_id'];resource=q.get('resource');family=uid('refresh');expires=now+REFRESH_TTL
  else:
   r=c.execute('SELECT * FROM oauth_refresh_tokens WHERE hash=?',(digest(f.get('refresh_token','')),)).fetchone()
   if not r or r['client_id']!=f.get('client_id') or r['expires']<=now:return error()
   if r['used']:
    # Replay indicates a stolen rotating token: invalidate the entire grant.
    c.execute('DELETE FROM oauth_tokens WHERE hash IN (SELECT access_hash FROM oauth_refresh_tokens WHERE family=?)',(r['family'],))
    c.execute('DELETE FROM oauth_refresh_tokens WHERE family=?',(r['family'],))
    return error()
   user_id=r['user_id'];resource=r['resource'];family=r['family'];expires=r['expires']
  if not c.execute('SELECT 1 FROM users WHERE id=? AND active=1',(user_id,)).fetchone():return error()
  if f.get('resource') and f['resource'].rstrip('/')!=(resource or request.app.state.base_url()+'/mcp'):return error('invalid_target')
  if grant=='authorization_code':c.execute('DELETE FROM oauth_codes WHERE hash=?',(digest(f['code']),))
  else:c.execute('UPDATE oauth_refresh_tokens SET used=1 WHERE hash=?',(digest(f['refresh_token']),))
  access=secrets.token_urlsafe(40);refresh=secrets.token_urlsafe(48)
  c.execute('INSERT INTO oauth_tokens VALUES(?,?,?,?)',(digest(access),user_id,f['client_id'],now+ACCESS_TTL))
  # Existing registered clients can upgrade after reauthorization; old access tokens stay valid.
  c.execute('INSERT INTO oauth_refresh_tokens(hash,user_id,client_id,expires,family,access_hash,resource) VALUES(?,?,?,?,?,?,?)',(digest(refresh),user_id,f['client_id'],expires,family,digest(access),resource))
 return JSONResponse({'access_token':access,'refresh_token':refresh,'token_type':'Bearer','expires_in':ACCESS_TTL,'scope':'bento'},headers=TOKEN_HEADERS)
