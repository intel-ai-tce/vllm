#!/usr/bin/env bash
set -euo pipefail
source ./env_set.sh
uvicorn app:app --host 0.0.0.0 --port "${UI_PORT:-8080}"
