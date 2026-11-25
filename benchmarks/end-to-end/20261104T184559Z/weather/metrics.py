import json
from pathlib import Path
P=Path(__file__).resolve().parent
s=json.loads((P/'report.json').read_text())
t=s['timing'];r=s['result_metadata'];src=s['source']
m={'task':'hourly_temperature_forecast','backend':'Timestral-209M','job_id':s['job_id'],'result_id':s['result_id'],'input_rows':720,'context_rows':720,'train_rows':720,'test_rows':src['prediction_length'],'horizon':src['prediction_length'],'comparison_hours':24,'feature_count':1,'server_duration_seconds':t['api_duration_seconds'],'queue_seconds':t['queue_seconds'],'worker_seconds':t['worker_seconds'],'cache_hit':r['cache_hit'],'inference_seconds':t['inference_seconds'],'load_model_seconds':t['load_model_seconds'],'as_of_cutoff_utc':src['as_of_cutoff_utc'],**s['comparison_metrics']}
(P/'metrics.json').write_text(json.dumps(m,indent=2,allow_nan=False))
