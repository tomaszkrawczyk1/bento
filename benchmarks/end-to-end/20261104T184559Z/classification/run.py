import io
import json
import time
from pathlib import Path

import httpx
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.datasets import load_breast_cancer
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score, roc_curve, ConfusionMatrixDisplay

ROOT = Path('/home/pc/sandbox/bento')
OUT = ROOT / 'benchmarks/end-to-end/20261104T184559Z/classification'
OUT.mkdir(parents=True, exist_ok=True)
def save(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False))

data = load_breast_cancer(as_frame=True)
df = data.frame.copy()
assert df.shape == (569, 31) and 'target' not in data.feature_names
df.to_csv(OUT / 'input.csv', index=False)
key = json.loads((ROOT / '.credentials/owner.json').read_text())['api_key']
client = httpx.Client(base_url='http://127.0.0.1:3000', headers={'Authorization': 'Bearer ' + key}, timeout=120)
def request(method, path, **kwargs):
    response = client.request(method, path, **kwargs)
    if response.is_error:
        raise RuntimeError(f'{method} {path}: {response.status_code} {response.text}')
    return response

upload = request('POST', '/datasets', files={'file': ('breast-cancer-fresh.csv', (OUT / 'input.csv').read_bytes(), 'text/csv')}).json()
save('upload.json', upload)
spec = dict(train=upload['dataset_id'], target='target', backend='tabicl', task='classification', use_cache=False, seed=42, test_size=0.2, time_limit=30)
save('request.json', spec)
submission = request('POST', '/evaluate', json=spec).json()
save('submission.json', submission)
job_id = submission['job_id']
print('NEW JOB', job_id, flush=True)
deadline = time.monotonic() + 600
while True:
    job = request('GET', '/jobs/' + job_id).json()
    save('job.json', job)
    if job['state'] in ('succeeded', 'failed', 'cancelled'):
        break
    if time.monotonic() > deadline:
        raise RuntimeError('Job timed out after 600 seconds')
    time.sleep(0.75)
assert job['state'] == 'succeeded', job
result = job['result']
print('RESULT METADATA', json.dumps(result), flush=True)
assert result['cache_hit'] is False
assert result['train_rows'] == 455 and result['test_rows'] == 114
assert len(result['features']) == 30 and 'target' not in result['features']
assert set(result['features']) == set(data.feature_names)
result_id = result['result_id']
raw = request('GET', '/results/' + result_id + '/download').content
(OUT / 'result.parquet').write_bytes(raw)
pred = pd.read_parquet(io.BytesIO(raw))
print('COLUMNS', list(pred.columns), 'ROWS', len(pred), flush=True)
assert len(pred) == 114
assert {'prediction', 'actual', 'probability_0', 'probability_1'} <= set(pred.columns)
assert pred[['prediction', 'actual', 'probability_0', 'probability_1']].notna().all().all()
assert np.allclose(pred[['probability_0', 'probability_1']].sum(axis=1), 1, atol=1e-5)
assert pred[['probability_0', 'probability_1']].ge(0).all().all() and pred[['probability_0', 'probability_1']].le(1).all().all()
pred.to_csv(OUT / 'result.csv', index=False)
y = pred.actual.astype(int)
yp = pred.prediction.astype(int)
accuracy = accuracy_score(y, yp)
f1 = f1_score(y, yp, average='macro')
auc = roc_auc_score(y, pred.probability_1)
metrics = dict(task='classification', job_id=job_id, result_id=result_id, input_rows=569, train_rows=455, test_rows=114, feature_count=30, server_duration_seconds=result['duration_seconds'], queue_seconds=job['started']-job['created'], worker_seconds=job['finished']-job['started'], cache_hit=result['cache_hit'], accuracy=accuracy, f1_macro=f1, roc_auc=auc, seed=42, positive_class='benign (1)', source='sklearn.datasets.load_breast_cancer', duration_scope='TabICL preparation/fit/predict, not forward-only')
save('metrics.json', metrics)
fig, axes = plt.subplots(1, 2, figsize=(13, 6.7), constrained_layout=True)
ConfusionMatrixDisplay.from_predictions(y, yp, labels=[0, 1], display_labels=data.target_names, ax=axes[0], colorbar=False, cmap='Blues')
axes[0].set_title('Confusion matrix (114 held-out samples)')
axes[0].set_xlabel('Predicted class')
axes[0].set_ylabel('True class')
fpr, tpr, _ = roc_curve(y, pred.probability_1)
axes[1].plot(fpr, tpr, linewidth=2.5, label=f'TabICL: AUC = {auc:.4f}')
axes[1].plot([0, 1], [0, 1], '--', color='gray', label='Random classifier')
axes[1].set(xlabel='False positive rate', ylabel='True positive rate', xlim=(0, 1), ylim=(0, 1.03), title='ROC curve — positive class: benign (1)')
axes[1].grid(alpha=0.25)
axes[1].legend(loc='lower right')
fig.suptitle(f'TabICL • breast_cancer demonstration\n30 features • 455/114 train/test • accuracy {accuracy:.3f} • macro F1 {f1:.3f}', fontsize=15)
fig.supxlabel('Source: sklearn.datasets.load_breast_cancer • seed 42 • fresh API evaluation • demonstration, not medical advice', fontsize=10)
fig.savefig(OUT / 'chart.png', dpi=150)
fig.savefig(OUT / 'chart.svg')
plt.close(fig)
(OUT / 'description.md').write_text(f'# Breast cancer classification demonstration\n\nFresh TabICL REST evaluation on the complete sklearn breast_cancer dataset (569 rows, 30 features). Seed 42, 455 training and 114 held-out rows; target excluded from features.\n\nAccuracy: {accuracy:.6f}; macro F1: {f1:.6f}; ROC AUC: {auc:.6f}, with benign (1) as the positive class. Class 0 is malignant. The chart describes a demonstration dataset and is not medical advice.\n\nQueue: {metrics["queue_seconds"]:.3f} s; worker: {metrics["worker_seconds"]:.3f} s; server preparation/fit/predict: {metrics["server_duration_seconds"]:.3f} s. Cache disabled and cache_hit=false.\n')
print('ARTIFACTS READY', json.dumps(metrics), flush=True)
