
Full Monitoring Stack (CPU + GPU + vLLM)

This stack launches everything with:

    docker compose up -d

Services included
-----------------
Prometheus      : metrics collection
Grafana         : dashboards
Node Exporter   : CPU / memory / disk metrics
DCGM Exporter   : NVIDIA GPU metrics

URLs
----
Grafana:
http://localhost:3000
login: admin / admin

Prometheus:
http://localhost:9090

Metrics endpoints
-----------------
Node exporter:
http://localhost:9100/metrics

GPU exporter:
http://localhost:9400/metrics

vLLM metrics:
http://localhost:8000/metrics
http://localhost:8001/metrics

Example Grafana Queries
-----------------------

CPU usage:
100 - (avg by(instance)(rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)

GPU utilization:
DCGM_FI_DEV_GPU_UTIL

GPU memory usage:
DCGM_FI_DEV_FB_USED

Start stack
-----------
docker compose up -d
