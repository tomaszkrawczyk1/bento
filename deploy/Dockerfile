FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv libgomp1 ca-certificates curl && rm -rf /var/lib/apt/lists/*
WORKDIR /home/pc/sandbox/bento
COPY app app
COPY models models
COPY scripts scripts
ENV PYTHONUNBUFFERED=1 HF_HUB_OFFLINE=1 OMP_NUM_THREADS=4 BENTO_DATA=/home/pc/sandbox/bento/data
USER 1000:1000
