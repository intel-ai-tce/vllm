#!/usr/bin/env bash
set -euo pipefail

RESULTS_DIR="${RESULTS_DIR:-/workspace/benchmarks/results}"
CLOS_ID="${CLOS_ID:-0}"
CLOS_CPU_FILE="${CLOS_CPU_FILE:-${RESULTS_DIR}/clos${CLOS_ID}_cpulist.txt}"

PERFSPECT_ARGS="${PERFSPECT_ARGS:---speed --frequency --no-summary}"

OUT_DIR="${RESULTS_DIR}/perfspect_clos${CLOS_ID}_$(date +%Y%m%d_%H%M%S)"
mkdir -p "${OUT_DIR}"

echo "------------------------------------------------------------"
echo "PerfSpect benchmark on CLOS${CLOS_ID} CPUs"
echo "------------------------------------------------------------"
echo "CLOS_ID=${CLOS_ID}"
echo "CLOS_CPU_FILE=${CLOS_CPU_FILE}"
echo "PERFSPECT_ARGS=${PERFSPECT_ARGS}"
echo "OUT_DIR=${OUT_DIR}"
echo

if ! command -v perfspect >/dev/null 2>&1; then
  echo "ERROR: perfspect not found in container PATH."
  echo "Install PerfSpect in Dockerfile.sst or mount a host perfspect binary into the container."
  exit 1
fi

if [[ ! -f "${CLOS_CPU_FILE}" ]]; then
  echo "ERROR: ${CLOS_CPU_FILE} not found."
  echo
  echo "Run this first:"
  echo "  docker compose --profile check up --abort-on-container-exit"
  exit 1
fi

CLOS_CPUS="$(tr -d '[:space:]' < "${CLOS_CPU_FILE}")"

if [[ -z "${CLOS_CPUS}" ]]; then
  echo "ERROR: empty CLOS CPU list from ${CLOS_CPU_FILE}"
  exit 1
fi

echo "Using CLOS${CLOS_ID} CPUs:"
echo "${CLOS_CPUS}"
echo

echo "${CLOS_CPUS}" > "${OUT_DIR}/clos${CLOS_ID}_cpulist.txt"

echo "------------------------------------------------------------"
echo "Run PerfSpect pinned to CLOS${CLOS_ID} CPUs"
echo "------------------------------------------------------------"

PERFSPECT_OUTPUT="${OUT_DIR}/perfspect"

echo "Command:"
echo "taskset -c ${CLOS_CPUS} perfspect benchmark ${PERFSPECT_ARGS} --output ${PERFSPECT_OUTPUT}"
echo

set +e
taskset -c "${CLOS_CPUS}" perfspect benchmark ${PERFSPECT_ARGS} \
  --output "${PERFSPECT_OUTPUT}" \
  2>&1 | tee "${OUT_DIR}/perfspect_benchmark.log"
RC=${PIPESTATUS[0]}
set -e

echo
echo "------------------------------------------------------------"
echo "PerfSpect benchmark completed"
echo "------------------------------------------------------------"
echo "Exit code: ${RC}"
