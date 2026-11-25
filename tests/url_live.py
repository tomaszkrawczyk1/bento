"""Public upstream checks; no model or domain-specific server logic is used."""
import json,time
from pathlib import Path
from app import store,url_ingest as u
store.init();user={'id':'url-live-test','workspace':'bento-team'}
checks=[
 ('github-blob','https://github.com/mwaskom/seaborn-data/blob/master/iris.csv',{}),
 ('github-catalog','https://github.com/mwaskom/seaborn-data',{'resource':'iris.csv'}),
 ('json-api-no-extension','https://api.open-meteo.com/v1/forecast?latitude=50.26&longitude=19.02&hourly=temperature_2m&forecast_days=1',{'json_path':'hourly'}),
 ('uci-zip','https://archive.ics.uci.edu/static/public/53/iris.zip',{'member':'iris.data','header':None}),
 ('huggingface-blob','https://huggingface.co/datasets/scikit-learn/iris/blob/main/Iris.csv',{}),
 ('huggingface-catalog','https://huggingface.co/datasets/scikit-learn/iris',{'resource':'Iris.csv'}),
 ('google-sheets','https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit#gid=0',{}),
 ('kaggle-page','https://www.kaggle.com/datasets/uciml/iris',{'resource':'Iris.csv'}),
]
report=[]
for name,url,options in checks:
 start=time.perf_counter()
 try:
  result=u.import_url(url,user,options);row={'name':name,'seconds':round(time.perf_counter()-start,3),'status':result.get('status','ready'),'rows':result.get('rows'),'columns':len(result.get('columns',[])),'cache_hit':result.get('cache_hit'),'source_records_hidden':result.get('source_records_hidden')}
  if result.get('choices'):row['choices']=result['choices']
 except Exception as e:row={'name':name,'status':'failed','error':str(e),'seconds':round(time.perf_counter()-start,3)}
 report.append(row);print(json.dumps(row),flush=True)
out=Path('benchmarks/url-import');out.mkdir(parents=True,exist_ok=True);(out/'live.json').write_text(json.dumps(report,indent=2))
