"""Recreate the local checkpoints; run only during installation, never serving."""
import json
from pathlib import Path
from huggingface_hub import HfApi,hf_hub_download,snapshot_download
project=Path(__file__).resolve().parents[1]
root=project/'weights';api=HfApi();manifest=[]
pin_file=project/'deploy/checkpoint-manifest.json'
pins={x['repo']:x['revision'] for x in json.loads(pin_file.read_text())} if pin_file.exists() else {}
for repo,sub,files in [('jingang/TabICL','tabicl',['tabicl-classifier-v2-20260212.ckpt','tabicl-regressor-v2-20260212.ckpt']),('autogluon/mitra-classifier-2','mitra-classifier',None),('autogluon/mitra-regressor-2','mitra-regressor',None),('mistralai/Timestral-209M','timestral-209m',None)]:
 rev=pins.get(repo) or api.model_info(repo).sha
 if files:
  for name in files:hf_hub_download(repo,name,revision=rev,local_dir=root/sub)
 else:snapshot_download(repo,revision=rev,local_dir=root/sub,allow_patterns=['*.json','*.safetensors','*.pt','LICENSE*'])
 manifest.append({'repo':repo,'revision':rev,'directory':sub,'files':files})
(root/'manifest.json').write_text(json.dumps(manifest,indent=2))
