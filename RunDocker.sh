docker run -it --entrypoint /bin/bash -v /data/huggingface:/root/.cache/huggingface -v /data:/data  -v ${PWD}/benchmarks/results:/vllm-workspace/benchmarks/results -v ${PWD}/.buildkite:/vllm-workspace/.buildkite  -e HF_TOKEN  --shm-size=16g  --name vllm-env-latest vllm-cpu-env:latest

