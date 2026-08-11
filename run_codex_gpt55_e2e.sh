#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

TASKS_FILE="${1:-$SCRIPT_DIR/medium_instances.txt}"
MAX_PARALLEL="${2:-${MAX_PARALLEL:-2}}"

export OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://api.openai.com/v1}"
export OPENAI_MODEL_ID="${OPENAI_MODEL_ID:-gpt-5.5}"

export AGENT=codex
export MODE=e2e
export MODEL_PROVIDER=openai
export MAX_ATTEMPTS="${MAX_ATTEMPTS:-1}"
export TIMEOUT="${TIMEOUT:-5400}"
export AGENT_OUTPUT_DIR="${AGENT_OUTPUT_DIR:-agent_output_codex_gpt55}"

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
    echo "ERROR: OPENAI_API_KEY is not set." >&2
    exit 1
fi

if [[ ! -f "$TASKS_FILE" ]]; then
    echo "ERROR: Task file does not exist: $TASKS_FILE" >&2
    exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
    echo "ERROR: curl is required for the model preflight check." >&2
    exit 1
fi

MODELS_URL="${OPENAI_BASE_URL%/}/models"
MODEL_LIST="$(curl -fsS --max-time 30 \
    -H "Authorization: Bearer $OPENAI_API_KEY" \
    "$MODELS_URL")" || {
    echo "ERROR: Cannot query the OpenAI models endpoint at $MODELS_URL" >&2
    exit 1
}

if ! grep -Eq "\"id\"[[:space:]]*:[[:space:]]*\"$OPENAI_MODEL_ID\"" <<<"$MODEL_LIST"; then
    echo "ERROR: Model $OPENAI_MODEL_ID is not available to this OpenAI account." >&2
    exit 1
fi

echo "Agent harness: Codex"
echo "OpenAI endpoint: $OPENAI_BASE_URL"
echo "OpenAI model: $OPENAI_MODEL_ID"
echo "Tasks: $TASKS_FILE"
echo "Parallel tasks: $MAX_PARALLEL"
echo "Output: $AGENT_OUTPUT_DIR"

if [[ "${PREFLIGHT_ONLY:-0}" == "1" ]]; then
    echo "Preflight passed. The experiment was not started."
    exit 0
fi

exec bash "$SCRIPT_DIR/scripts/batch_run.sh" "$TASKS_FILE" "$MAX_PARALLEL" "$MAX_ATTEMPTS"
