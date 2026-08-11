#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

TASKS_FILE="${1:-$SCRIPT_DIR/medium_instances.txt}"
MAX_PARALLEL="${2:-${MAX_PARALLEL:-2}}"

export ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-https://api.anthropic.com}"
export ANTHROPIC_MODEL_ID="${ANTHROPIC_MODEL_ID:-claude-sonnet-5}"

export AGENT=openhands
export MODE=e2e
export MODEL_PROVIDER=anthropic
export MAX_ATTEMPTS="${MAX_ATTEMPTS:-1}"
# Keep the OpenHands cost limit fixed at $10 per task.
export MAX_BUDGET_PER_TASK=10
export TIMEOUT="${TIMEOUT:-5400}"
export AGENT_OUTPUT_DIR="${AGENT_OUTPUT_DIR:-agent_output_openhands_sonnet5}"

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    echo "ERROR: ANTHROPIC_API_KEY is not set." >&2
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

MODEL_URL="${ANTHROPIC_BASE_URL%/}/v1/models/$ANTHROPIC_MODEL_ID"
MODEL_INFO="$(curl -fsS --max-time 30 \
    -H "x-api-key: $ANTHROPIC_API_KEY" \
    -H "anthropic-version: 2023-06-01" \
    "$MODEL_URL")" || {
    echo "ERROR: Model $ANTHROPIC_MODEL_ID is not available to this Anthropic account." >&2
    exit 1
}

# Aliases can resolve to a dated canonical ID, so do not require the returned
# ID to exactly match the requested alias.
if ! grep -Eq '"type"[[:space:]]*:[[:space:]]*"model"' <<<"$MODEL_INFO"; then
    echo "ERROR: Unexpected response from the Anthropic model endpoint: $MODEL_URL" >&2
    exit 1
fi

echo "Anthropic endpoint: $ANTHROPIC_BASE_URL"
echo "Anthropic model: $ANTHROPIC_MODEL_ID"
echo "Tasks: $TASKS_FILE"
echo "Parallel tasks: $MAX_PARALLEL"
echo "Maximum budget per task: $MAX_BUDGET_PER_TASK USD"
echo "Output: $AGENT_OUTPUT_DIR"

if [[ "${PREFLIGHT_ONLY:-0}" == "1" ]]; then
    echo "Preflight passed. The experiment was not started."
    exit 0
fi

exec bash "$SCRIPT_DIR/scripts/batch_run.sh" "$TASKS_FILE" "$MAX_PARALLEL" "$MAX_ATTEMPTS"
