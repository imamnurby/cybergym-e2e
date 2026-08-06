#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

TASKS_FILE="${1:-$SCRIPT_DIR/medium_instances.txt}"
MAX_PARALLEL="${2:-${MAX_PARALLEL:-2}}"

export OPENAI_BASE_URL="${OPENAI_BASE_URL:-http://172.17.0.1:8100/v1}"
export OPENAI_API_KEY="${OPENAI_API_KEY:-EMPTY}"
export OPENAI_MODEL_ID="${OPENAI_MODEL_ID:-Qwen/Qwen3.6-27B}"

export AGENT=openhands
export MODE=e2e
export MODEL_PROVIDER=openai
export MAX_ATTEMPTS="${MAX_ATTEMPTS:-1}"
export MAX_BUDGET_PER_TASK="${MAX_BUDGET_PER_TASK:-0}"
export TIMEOUT="${TIMEOUT:-5400}"
export AGENT_OUTPUT_DIR="${AGENT_OUTPUT_DIR:-agent_output_openhands_qwen}"

if [[ ! -f "$TASKS_FILE" ]]; then
    echo "ERROR: Task file does not exist: $TASKS_FILE" >&2
    exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
    echo "ERROR: curl is required for the model preflight check." >&2
    exit 1
fi

MODEL_LIST="$(curl -fsS --max-time 15 "$OPENAI_BASE_URL/models")" || {
    echo "ERROR: Cannot reach the Qwen API at $OPENAI_BASE_URL" >&2
    exit 1
}

if ! grep -Fq "\"id\":\"$OPENAI_MODEL_ID\"" <<<"$MODEL_LIST"; then
    echo "ERROR: Model $OPENAI_MODEL_ID is not served by $OPENAI_BASE_URL" >&2
    echo "Response: $MODEL_LIST" >&2
    exit 1
fi

echo "Qwen endpoint: $OPENAI_BASE_URL"
echo "Qwen model: $OPENAI_MODEL_ID"
echo "Tasks: $TASKS_FILE"
echo "Parallel tasks: $MAX_PARALLEL"
echo "Output: $AGENT_OUTPUT_DIR"

if [[ "${PREFLIGHT_ONLY:-0}" == "1" ]]; then
    echo "Preflight passed. The experiment was not started."
    exit 0
fi

exec bash "$SCRIPT_DIR/scripts/batch_run.sh" "$TASKS_FILE" "$MAX_PARALLEL" "$MAX_ATTEMPTS"
