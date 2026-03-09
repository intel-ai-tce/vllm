All-in-one Monitoring Stack

This package is preconfigured so you only need:

  docker compose up -d

What starts:
- Prometheus
- Grafana
- node-exporter
- dcgm-exporter

Assumptions:
- You run this on the same machine that has the GPU.
- vLLM GPU metrics are exposed on http://localhost:8000/metrics
- vLLM CPU metrics are exposed on http://localhost:8001/metrics

Open:
- Grafana:   http://localhost:3000
- Prometheus: http://localhost:9090

Grafana login:
- user: admin
- pass: admin

Preloaded dashboard:
- CPU + GPU + vLLM Overview

Notes:
- node-exporter provides CPU / memory / disk / network metrics.
- dcgm-exporter provides NVIDIA GPU metrics.
- If your vLLM ports differ from 8000 / 8001, edit prometheus/prometheus.yml.
- dcgm-exporter requires NVIDIA Docker runtime support on the host.
