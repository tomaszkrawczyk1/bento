import asyncio,json
from pathlib import Path
from fastmcp import Client
async def main():
 key=json.loads(Path('.credentials/owner.json').read_text())['api_key']
 async with Client('http://127.0.0.1:3000/mcp/',auth=key) as c:
  tools=await c.list_tools();print('TOOLS',len(tools),[t.name for t in tools])
  result=await c.call_tool('list_datasets',{});assert not result.is_error;print('MCP authenticated data access passed')
  result=await c.call_tool('model_info',{});assert not result.is_error
asyncio.run(main())
