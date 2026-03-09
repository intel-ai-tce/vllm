Netdata Quick Monitoring (CPU + GPU)

This version enables GPU monitoring inside the container.

Requirements
------------
1. NVIDIA drivers installed
2. nvidia-container-toolkit installed
3. `docker run --gpus all nvidia/cuda:12.2.0-base nvidia-smi` works

Start monitoring:

    docker compose up -d

Open browser:

    http://localhost:19999

Netdata automatically detects:
- CPU utilization
- Memory usage
- Disk IO
- Network traffic
- NVIDIA GPU utilization

GPU panels appear under:

Metrics -> Hardware -> GPU

If GPU does not appear, test inside container:

    docker exec -it netdata nvidia-smi
