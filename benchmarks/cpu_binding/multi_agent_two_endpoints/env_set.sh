#!/usr/bin/env bash
set -uo pipefail

# -----------------------------------------------------------------------------
# Multi-agent app using 2 physical endpoints:
#   - CPU endpoint (8B): Researcher + Reviewer
#   - GPU endpoint (405B): Writer
# -----------------------------------------------------------------------------

export DRY_RUN="${DRY_RUN:-0}"

export CPU_URL="${CPU_URL:-http://localhost:8001}"
export CPU_MODEL="${CPU_MODEL:-meta-llama/Llama-3.1-8B-Instruct}"
export CPU_API_KEY="${CPU_API_KEY:-}"

export GPU_URL="${GPU_URL:-https://api.sambanova.ai}"
export GPU_MODEL="${GPU_MODEL:-Meta-Llama-3.3-70B-Instruct}"
export GPU_API_KEY="${GPU_API_KEY:-cd0e31b2-b79c-4ab6-ad1c-197ab82ba3bf}"

export RESEARCHER_MAX_TOKENS="${RESEARCHER_MAX_TOKENS:-700}"
export RESEARCHER_TEMP="${RESEARCHER_TEMP:-0.2}"
export RESEARCHER_INITIAL_WAIT_S="${RESEARCHER_INITIAL_WAIT_S:-0.8}"

export WRITER_MAX_TOKENS="${WRITER_MAX_TOKENS:-2500}"
export WRITER_TEMP="${WRITER_TEMP:-0.4}"
export WRITER_TIMEOUT_S="${WRITER_TIMEOUT_S:-300}"

export REVIEWER_MAX_TOKENS="${REVIEWER_MAX_TOKENS:-400}"
export REVIEWER_TEMP="${REVIEWER_TEMP:-0.2}"
export REVIEW_START_CHARS="${REVIEW_START_CHARS:-1400}"

export CHUNK_CHARS="${CHUNK_CHARS:-220}"

unset OPENAI_API_KEY
#export OPENAI_API_KEY="${OPENAI_API_KEY:-}"

echo "Loaded environment for 2-endpoint multi-agent app:"
echo "  DRY_RUN=$DRY_RUN"
echo "  CPU_URL=$CPU_URL"
echo "  CPU_MODEL=$CPU_MODEL"
echo "  CPU_API_KEY=${CPU_API_KEY:+<set>}"
echo "  GPU_URL=$GPU_URL"
echo "  GPU_MODEL=$GPU_MODEL"
echo "  GPU_API_KEY=${GPU_API_KEY:+<set>}"
echo "  RESEARCHER_MAX_TOKENS=$RESEARCHER_MAX_TOKENS"
echo "  WRITER_MAX_TOKENS=$WRITER_MAX_TOKENS"
echo "  REVIEWER_MAX_TOKENS=$REVIEWER_MAX_TOKENS"
echo "  REVIEW_START_CHARS=$REVIEW_START_CHARS"

python3 -m uvicorn app:app --host 0.0.0.0 --port 65535
