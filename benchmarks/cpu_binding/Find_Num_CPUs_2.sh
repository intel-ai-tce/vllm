#!/bin/bash
set -uo pipefail

#export MODEL="meta-llama/Llama-3.1-405B-Instruct"
export MODEL="meta-llama/Llama-3.1-8B-Instruct"
export PROMPTS_PER_CONCURRENCY=1
export VLLM_FOLDER_PATH="/home/louie/work/aitce/vllm"

declare -a TOK_PAIRS=(
  "2048:2048"
)

CPU_LIST=(2 4 6 8 10 12 14 16 24)
#CPU_LIST=(12)

RESULTS_DIR="results"

# ---- Create timestamped RESULT directory ----
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
RESULT_ROOT="RESULT"
RESULT_DIR="${RESULT_ROOT}/${TIMESTAMP}"

mkdir -p "${RESULT_DIR}"
echo "Results will be collected under: ${RESULT_DIR}"

for pair in "${TOK_PAIRS[@]}"; do
  IFS=":" read -r INPUT_TOK OUTPUT_TOK <<< "$pair"
  export INPUT_TOK OUTPUT_TOK

  echo "=== Running benchmarks for INPUT_TOK=$INPUT_TOK, OUTPUT_TOK=$OUTPUT_TOK ==="

  for NUMCPU in "${CPU_LIST[@]}"; do
    export NUM_CPUS="$NUMCPU"
    echo "--- Generating CPU binding for NUMCPU=$NUMCPU ---"

    python3 generate_cpu_binding_from_csv.py       --output ./docker-compose.override.yml

    echo "--- Launching benchmark (NUMCPU=$NUMCPU) ---"
    docker compose -f docker-compose.yml -f docker-compose.override.yml --profile benchmark up --abort-on-container-exit


    # ---- Fix ownership (Docker runs as root) ----
    if command -v sudo >/dev/null 2>&1; then
      sudo chown -R "$(id -u)":"$(id -g)" .
    fi

    # ---- Rename results directory ----
    SRC_DIR="${RESULTS_DIR}"
    DST_DIR="${RESULTS_DIR}_cpu${NUMCPU}"

    if [[ -d "$SRC_DIR" ]]; then
      if [[ -e "$DST_DIR" ]]; then
        echo "Error: $DST_DIR already exists — refusing to overwrite"
        exit 1
      fi
      mv "$SRC_DIR" "$DST_DIR"
      echo "Renamed results dir: $DST_DIR"
    else
      echo "Warning: expected results directory '$SRC_DIR' not found"
    fi

    echo "--- Closing benchmark (NUMCPU=$NUMCPU) ---"
    docker compose -f docker-compose.yml -f docker-compose.override.yml --profile benchmark down

    echo "--- Completed NUMCPU=$NUMCPU ---"
  done
done

# ---- Move all generated results_cpu* folders into RESULT/<timestamp> ----
echo "=== Collecting result folders into ${RESULT_DIR} ==="

for NUMCPU in "${CPU_LIST[@]}"; do
  DIR="${RESULTS_DIR}_cpu${NUMCPU}"
  if [[ -d "$DIR" ]]; then
    mv "$DIR" "${RESULT_DIR}/"
    echo "Moved $DIR -> ${RESULT_DIR}/"
  else
    echo "Warning: $DIR not found, skipping"
  fi
done

echo "✅ All benchmarks completed."
echo "📁 Final results stored in: ${RESULT_DIR}"
