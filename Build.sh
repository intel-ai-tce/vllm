docker build -f docker/Dockerfile.cpu \
        --build-arg VLLM_CPU_AVX512=true \
        --build-arg VLLM_CPU_AVX512BF16=true \
        --build-arg VLLM_CPU_AVX512VNNI=true \
        --build-arg VLLM_CPU_AMXBF16=false \
	--build-arg ONEDNN_ENABLE_CPU_ISA_HINTS=ON \
	--build-arg ONEDNN_ENABLE_MAX_CPU_ISA=ON \
        --tag vllm-cpu-env \
        --target vllm-openai .
