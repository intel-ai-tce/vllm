#export MODEL=/root/.cache/huggingface/hub/models--meta-llama--Meta-Llama-3.1-405B-Instruct/snapshots/be673f326cab4cd22ccfef76109faf68e41aa5f1
#MODE=deploy PORT=8000 CPU_MODEL=meta-llama/Llama-3.1-8B-Instruct CPU_PORT=8001 docker compose -f docker-compose.yml -f docker-compose.cpu.yml -f docker-compose.override.yml --profile deploy up

PROMPTS_PER_CONCURRENCY=200 MODE=benchmark MODEL=/root/.cache/huggingface/hub/models--meta-llama--Meta-Llama-3.1-405B-Instruct/snapshots/be673f326cab4cd22ccfef76109faf68e41aa5f1   PORT=8000  docker compose -f docker-compose.yml -f docker-compose.cpu.yml -f docker-compose.override.yml --profile benchmark up
