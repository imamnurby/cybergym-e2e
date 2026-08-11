#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

usage() {
    cat <<'EOF'
Usage:
  ./run_e2e.sh <preset> [tasks_file] [max_parallel]
  ./run_e2e.sh --list

Presets:
  qwen              OpenHands with Qwen 3.6 27B
  openhands-gpt55   OpenHands with GPT-5.5
  codex-gpt55       Codex with GPT-5.5
  deepseek          OpenHands with DeepSeek V4 Pro
  opus45            OpenHands with Claude Opus 4.5
  opus46            OpenHands with Claude Opus 4.6
  sonnet5           OpenHands with Claude Sonnet 5

Defaults:
  tasks_file        instance.txt
  max_parallel      2

Environment overrides:
  AGENT_OUTPUT_DIR, MAX_ATTEMPTS, MAX_BUDGET_PER_TASK, TIMEOUT
  OPENAI_BASE_URL, OPENAI_API_KEY, OPENAI_MODEL_ID
  DEEPSEEK_BASE_URL, DEEPSEEK_API_KEY, DEEPSEEK_MODEL_ID
  ANTHROPIC_BASE_URL, ANTHROPIC_API_KEY, ANTHROPIC_MODEL_ID
  PREFLIGHT_ONLY=1 checks access without starting an experiment.
EOF
}

list_presets() {
    printf '%s\n' qwen openhands-gpt55 codex-gpt55 deepseek opus45 opus46 sonnet5
}

if [[ $# -eq 0 ]]; then
    usage >&2
    exit 2
fi

case "$1" in
    -h|--help)
        usage
        exit 0
        ;;
    --list)
        list_presets
        exit 0
        ;;
esac

PRESET="$1"
TASKS_FILE="${2:-$SCRIPT_DIR/instance.txt}"
MAX_PARALLEL="${3:-${MAX_PARALLEL:-2}}"

if [[ $# -gt 3 ]]; then
    echo "ERROR: Too many arguments." >&2
    usage >&2
    exit 2
fi

if [[ ! "$MAX_PARALLEL" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: max_parallel must be a positive integer: $MAX_PARALLEL" >&2
    exit 2
fi

export MODE=e2e
export MODEL_PROVIDER
export AGENT
export MAX_ATTEMPTS="${MAX_ATTEMPTS:-1}"
export TIMEOUT="${TIMEOUT:-5400}"

case "$PRESET" in
    qwen)
        PRESET_NAME="OpenHands with Qwen 3.6 27B"
        export AGENT=openhands
        export MODEL_PROVIDER=openai
        export OPENAI_BASE_URL="${OPENAI_BASE_URL:-http://172.17.0.1:8100/v1}"
        export OPENAI_API_KEY="${OPENAI_API_KEY:-EMPTY}"
        export OPENAI_MODEL_ID="${OPENAI_MODEL_ID:-Qwen/Qwen3.6-27B}"
        export MAX_BUDGET_PER_TASK="${MAX_BUDGET_PER_TASK:-0}"
        export AGENT_OUTPUT_DIR="${AGENT_OUTPUT_DIR:-agent_output_openhands_qwen}"
        PREFLIGHT_KIND=qwen
        ;;
    openhands-gpt55)
        PRESET_NAME="OpenHands with GPT-5.5"
        export AGENT=openhands
        export MODEL_PROVIDER=openai
        export OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://api.openai.com/v1}"
        export OPENAI_MODEL_ID="${OPENAI_MODEL_ID:-gpt-5.5}"
        export MAX_BUDGET_PER_TASK="${MAX_BUDGET_PER_TASK:-10}"
        export AGENT_OUTPUT_DIR="${AGENT_OUTPUT_DIR:-agent_output_openhands_gpt55}"
        PREFLIGHT_KIND=openai
        ;;
    codex-gpt55)
        PRESET_NAME="Codex with GPT-5.5"
        export AGENT=codex
        export MODEL_PROVIDER=openai
        export OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://api.openai.com/v1}"
        export OPENAI_MODEL_ID="${OPENAI_MODEL_ID:-gpt-5.5}"
        export MAX_BUDGET_PER_TASK="${MAX_BUDGET_PER_TASK:-10}"
        export AGENT_OUTPUT_DIR="${AGENT_OUTPUT_DIR:-agent_output_codex_gpt55}"
        PREFLIGHT_KIND=openai
        ;;
    deepseek)
        PRESET_NAME="OpenHands with DeepSeek V4 Pro"
        export AGENT=openhands
        export MODEL_PROVIDER=deepseek
        export DEEPSEEK_BASE_URL="${DEEPSEEK_BASE_URL:-https://api.deepseek.com}"
        export DEEPSEEK_MODEL_ID="${DEEPSEEK_MODEL_ID:-deepseek-v4-pro}"
        export MAX_BUDGET_PER_TASK="${MAX_BUDGET_PER_TASK:-10}"
        export AGENT_OUTPUT_DIR="${AGENT_OUTPUT_DIR:-agent_output_openhands_deepseek}"
        PREFLIGHT_KIND=deepseek
        ;;
    opus45)
        PRESET_NAME="OpenHands with Claude Opus 4.5"
        export AGENT=openhands
        export MODEL_PROVIDER=anthropic
        export ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-https://api.anthropic.com}"
        export ANTHROPIC_MODEL_ID="${ANTHROPIC_MODEL_ID:-claude-opus-4-5}"
        export MAX_BUDGET_PER_TASK="${MAX_BUDGET_PER_TASK:-10}"
        export AGENT_OUTPUT_DIR="${AGENT_OUTPUT_DIR:-agent_output_openhands_opus45}"
        PREFLIGHT_KIND=anthropic
        ;;
    opus46)
        PRESET_NAME="OpenHands with Claude Opus 4.6"
        export AGENT=openhands
        export MODEL_PROVIDER=anthropic
        export ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-https://api.anthropic.com}"
        export ANTHROPIC_MODEL_ID="${ANTHROPIC_MODEL_ID:-claude-opus-4-6}"
        export MAX_BUDGET_PER_TASK="${MAX_BUDGET_PER_TASK:-10}"
        export AGENT_OUTPUT_DIR="${AGENT_OUTPUT_DIR:-agent_output_openhands_opus46}"
        PREFLIGHT_KIND=anthropic
        ;;
    sonnet5)
        PRESET_NAME="OpenHands with Claude Sonnet 5"
        export AGENT=openhands
        export MODEL_PROVIDER=anthropic
        export ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-https://api.anthropic.com}"
        export ANTHROPIC_MODEL_ID="${ANTHROPIC_MODEL_ID:-claude-sonnet-5}"
        export MAX_BUDGET_PER_TASK="${MAX_BUDGET_PER_TASK:-10}"
        export AGENT_OUTPUT_DIR="${AGENT_OUTPUT_DIR:-agent_output_openhands_sonnet5}"
        PREFLIGHT_KIND=anthropic
        ;;
    *)
        echo "ERROR: Unknown preset: $PRESET" >&2
        echo "Available presets:" >&2
        list_presets >&2
        exit 2
        ;;
esac

if [[ ! -f "$TASKS_FILE" ]]; then
    echo "ERROR: Task file does not exist: $TASKS_FILE" >&2
    exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
    echo "ERROR: curl is required for the model preflight check." >&2
    exit 1
fi

case "$PREFLIGHT_KIND" in
    qwen)
        MODELS_URL="${OPENAI_BASE_URL%/}/models"
        MODEL_LIST="$(curl -fsS --max-time 15 "$MODELS_URL")" || {
            echo "ERROR: Cannot reach the Qwen API at $OPENAI_BASE_URL" >&2
            exit 1
        }
        if ! grep -Eq "\"id\"[[:space:]]*:[[:space:]]*\"$OPENAI_MODEL_ID\"" <<<"$MODEL_LIST"; then
            echo "ERROR: Model $OPENAI_MODEL_ID is not served by $OPENAI_BASE_URL" >&2
            exit 1
        fi
        MODEL_ID="$OPENAI_MODEL_ID"
        ENDPOINT="$OPENAI_BASE_URL"
        ;;
    openai)
        if [[ -z "${OPENAI_API_KEY:-}" ]]; then
            echo "ERROR: OPENAI_API_KEY is not set." >&2
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
        MODEL_ID="$OPENAI_MODEL_ID"
        ENDPOINT="$OPENAI_BASE_URL"
        ;;
    deepseek)
        if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
            echo "ERROR: DEEPSEEK_API_KEY is not set." >&2
            exit 1
        fi
        MODELS_URL="${DEEPSEEK_BASE_URL%/}/models"
        MODEL_LIST="$(curl -fsS --max-time 30 \
            -H "Authorization: Bearer $DEEPSEEK_API_KEY" \
            "$MODELS_URL")" || {
            echo "ERROR: Cannot query the DeepSeek models endpoint at $MODELS_URL" >&2
            exit 1
        }
        if ! grep -Eq "\"id\"[[:space:]]*:[[:space:]]*\"$DEEPSEEK_MODEL_ID\"" <<<"$MODEL_LIST"; then
            echo "ERROR: Model $DEEPSEEK_MODEL_ID is not available to this DeepSeek account." >&2
            exit 1
        fi
        MODEL_ID="$DEEPSEEK_MODEL_ID"
        ENDPOINT="$DEEPSEEK_BASE_URL"
        ;;
    anthropic)
        if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
            echo "ERROR: ANTHROPIC_API_KEY is not set." >&2
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
        if ! grep -Eq '"type"[[:space:]]*:[[:space:]]*"model"' <<<"$MODEL_INFO"; then
            echo "ERROR: Unexpected response from the Anthropic model endpoint: $MODEL_URL" >&2
            exit 1
        fi
        MODEL_ID="$ANTHROPIC_MODEL_ID"
        ENDPOINT="$ANTHROPIC_BASE_URL"
        ;;
esac

echo "Preset: $PRESET_NAME"
echo "Agent: $AGENT"
echo "Provider: $MODEL_PROVIDER"
echo "Endpoint: $ENDPOINT"
echo "Model: $MODEL_ID"
echo "Tasks: $TASKS_FILE"
echo "Parallel tasks: $MAX_PARALLEL"
echo "Maximum budget per task: $MAX_BUDGET_PER_TASK"
echo "Output: $AGENT_OUTPUT_DIR"

if [[ "${PREFLIGHT_ONLY:-0}" == "1" ]]; then
    echo "Preflight passed. The experiment was not started."
    exit 0
fi

exec bash "$SCRIPT_DIR/scripts/batch_run.sh" "$TASKS_FILE" "$MAX_PARALLEL" "$MAX_ATTEMPTS"
