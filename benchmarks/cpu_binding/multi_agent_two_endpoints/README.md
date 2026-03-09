# Multi-Agent App on 2 Endpoints

Routing:
- Researcher -> CPU endpoint (8B)
- Writer -> GPU endpoint (405B)
- Reviewer -> CPU endpoint (8B)

## Files
- `app.py` - colorful UI + SSE stream
- `agents.py` - 2-endpoint routing logic
- `vllm_client.py` - OpenAI-compatible streaming client
- `env_set.sh` - environment setup helper
- `requirements.txt`

## Dry-run mode
```bash
source ./env_set.sh
export DRY_RUN=1
uvicorn app:app --host 0.0.0.0 --port 8000
```

## Real vLLM mode
First start the two model endpoints.

### CPU 8B endpoint
```bash
VLLM_CPU_KVCACHE_SPACE=8 \
vllm serve meta-llama/Llama-3.1-8B-Instruct \
  --host 0.0.0.0 --port 8001 \
  --dtype bfloat16 \
  --max-model-len 8192
```

### GPU 405B endpoint
```bash
vllm serve meta-llama/Llama-3.1-405B-Instruct \
  --host 0.0.0.0 --port 8002 \
  --dtype bfloat16 \
  --max-model-len 8192
```

Then:
```bash
source ./env_set.sh
export DRY_RUN=0
export CPU_URL=http://<cpu-host>:8001
export GPU_URL=http://<gpu-host>:8002

pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`
