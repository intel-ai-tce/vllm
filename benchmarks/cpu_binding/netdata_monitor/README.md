Netdata Quick Monitoring (CPU + GPU)

This is the fastest way to see system utilization in a web browser.

Start monitoring:

    docker compose up -d

Open browser:

    http://localhost:19999

Netdata automatically detects:
- CPU utilization
- Memory usage
- Disk IO
- Network traffic
- NVIDIA GPU utilization (if nvidia-smi is available)

GPU monitoring works if:
- NVIDIA drivers are installed
- nvidia-smi works on the host

Example GPU metrics shown in UI:
- GPU utilization
- GPU memory
- GPU temperature
- GPU power

Stop stack:

    docker compose down
