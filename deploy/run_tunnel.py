"""Demo tunnel supervisor: update the advertised URL whenever cloudflared starts."""
import re,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=subprocess.Popen(['/usr/local/bin/cloudflared','tunnel','--url','http://127.0.0.1:3003','--no-autoupdate'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
for line in p.stdout:
 print(line,end='',flush=True)
 match=re.search(r'https://[a-z0-9-]+\.trycloudflare\.com',line)
 if match:
  (root/'deploy/public-url.txt').write_text(match[0]+'\n')
  print('MCP URL updated: '+match[0]+'/mcp',flush=True)
sys.exit(p.wait())
