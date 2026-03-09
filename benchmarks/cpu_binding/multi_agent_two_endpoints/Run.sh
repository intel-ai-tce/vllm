export GPU_MODEL="/root/.cache/huggingface/hub/models--meta-llama--Meta-Llama-3.1-405B-Instruct/snapshots/be673f326cab4cd22ccfef76109faf68e41aa5f1"
export WRITER_MAX_TOKENS=1200
uvicorn app:app --host 0.0.0.0 --port 8000
