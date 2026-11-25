#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$PWD" != /home/pc/sandbox/bento ]]; then
  echo 'This PC deployment uses /home/pc/sandbox/bento; adjust compose paths for another host.' >&2
  exit 1
fi
python3 -m venv .bootstrap
.bootstrap/bin/pip install uv==0.13.7
.bootstrap/bin/uv venv --python python3.12 .venv
.bootstrap/bin/uv venv --python python3.12 .venv-mitra
mkdir -p vendor
if [[ ! -d vendor/mitra-finetune/.git ]]; then
 git clone https://huggingface.co/autogluon/mitra-finetune vendor/mitra-finetune
fi
git -C vendor/mitra-finetune checkout b4701e8148dc33b00ed15d7086ff59816957cde4
if [[ ! -d vendor/timestral/.git ]]; then
 git clone https://github.com/mistralai/timestral.git vendor/timestral
fi
git -C vendor/timestral checkout a534bdbd244d64f3d9d743f46c7bf6fc330ed4ff
.bootstrap/bin/uv pip sync --python .venv/bin/python requirements-tabicl.lock
.bootstrap/bin/uv pip sync --python .venv-mitra/bin/python requirements-mitra.lock
.venv/bin/python scripts/download_weights.py
.venv/bin/python scripts/demo_data.py
mkdir -p data/artifacts/AutogluonModels
mkdir -p .credentials
if [[ ! -f .credentials/kaggle.json ]]; then
 (umask 077; printf '{}\n' > .credentials/kaggle.json)
 echo 'Kaggle is disabled until .credentials/kaggle.json contains valid credentials.' >&2
fi
if [[ ! -f .credentials/url-sources.json ]]; then
 (umask 077; printf '{"profiles":{}}\n' > .credentials/url-sources.json)
fi
test -f deploy/public-url.txt || printf '%s\n' http://127.0.0.1:3000 > deploy/public-url.txt
.venv/bin/python scripts/setup_postgres.py
docker compose up -d --build
