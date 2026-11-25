"""Token-in-URL login: /t/<api_key>/mcp works without OAuth panel; bad token and plain /mcp are rejected."""
import asyncio,json
from pathlib import Path
import httpx
from fastmcp import Client
async def main():
 base=Path('deploy/public-url.txt').read_text().strip() if Path('deploy/public-url.txt').exists() else 'http://127.0.0.1:3000'
 key=json.loads(Path('.credentials/owner.json').read_text())['api_key']
 async with Client(f'{base}/t/{key}/mcp') as m:
  tools={t.name for t in await m.list_tools()};assert 'dataset_from_url' in tools
  assert not (await m.call_tool('list_datasets',{})).is_error
 async with httpx.AsyncClient(timeout=30) as c:
  assert (await c.post(f'{base}/t/{"x"*40}/mcp',json={})).status_code==401
  assert (await c.post(f'{base}/mcp',json={})).status_code==401
 print('token-in-URL MCP login passed',base)
asyncio.run(main())
