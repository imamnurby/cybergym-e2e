#!/bin/bash
# Unified batch runner for cybergym-e2e agents
#
# Usage:
#   bash scripts/batch_run.sh [tasks_file] [max_parallel] [OPTIONS]
#
# Options (via environment variables or positional args):
#   AGENT=claude-code|openhands    Agent backend (default: claude-code)
#   MODE=e2e|patch-only            Mode (default: e2e)
#   MAX_PARALLEL=N                 Parallel jobs (default: 4)
#   MAX_ATTEMPTS=N                 Retry attempts (default: 1)
#   MODEL_PROVIDER=anthropic|bedrock|deepseek|litellm|openai  Model provider (default: anthropic)
#   LITELLM_MODEL_ID=...           LiteLLM Model ID
#   OPENAI_MODEL_ID=...            Direct OpenAI-compatible model ID
#   CODEX_AUTH_MODE=...            api-key or chatgpt (default: api-key)
#   CODEX_AUTH_FILE=...            File-based Codex credentials for chatgpt mode
#   CODEX_REASONING_EFFORT=...      Optional Codex reasoning effort
#   CODEX_SUPPORTS_REASONING_SUMMARIES=auto|true|false
#   DEEPSEEK_MODEL_ID=...          DeepSeek model ID
#   MAX_BUDGET_PER_TASK=N          OpenHands cost limit; 0 disables it
#   BEDROCK_MODEL_ID=...           Bedrock Model ID
#   ANTHROPIC_MODEL_ID=...         Anthropic model ID (used with MODEL_PROVIDER=anthropic)
#   AWS_PROFILE=...                AWS profile
#   AWS_REGION=...                 AWS region (default: us-west-2)
#   AGENT_OUTPUT_DIR=...           Output directory
#   TIMEOUT=N                      Agent timeout in seconds (default: 5400)
#
# Examples:
#   # Claude Code (default)
#   bash scripts/batch_run.sh scripts/tasks_30.txt 50
#
#   # OpenHands
#   AGENT=openhands bash scripts/batch_run.sh scripts/tasks_30.txt 4
#
#   # With custom settings
#   AWS_PROFILE=my-profile MAX_ATTEMPTS=3 bash scripts/batch_run.sh tasks.txt
#
#   # Stop all running jobs
#   bash scripts/batch_run.sh --stop

set -euo pipefail

# Handle --stop first
if [[ "${1:-}" == "--stop" ]]; then
    echo "Stopping all batch processes..."

    # Kill batch_run.sh processes
    pkill -9 -f "batch_run.sh" 2>/dev/null || true

    # Kill run_agent.py processes
    pkill -9 -f "run_agent.py" 2>/dev/null || true

    # Kill Docker containers. Disable for now to avoid killing unrelated containers.
    docker ps -q --filter "name=claude-agent" 2>/dev/null | xargs -r docker kill 2>/dev/null || true
    # docker ps -q 2>/dev/null | head -20 | xargs -r docker kill 2>/dev/null || true

    echo "Done."
    exit 0
fi

# Configuration
TASKS_FILE="${1:-scripts/tasks.txt}"
MAX_PARALLEL="${2:-${MAX_PARALLEL:-4}}"
MAX_ATTEMPTS="${3:-${MAX_ATTEMPTS:-1}}"
MODEL_PROVIDER="${MODEL_PROVIDER:-anthropic}"
LITELLM_MODEL_ID="${LITELLM_MODEL_ID:-openai/gpt-5.2-codex}"
OPENAI_MODEL_ID="${OPENAI_MODEL_ID:-gpt-5.6-sol}"
CODEX_AUTH_MODE="${CODEX_AUTH_MODE:-api-key}"
CODEX_AUTH_FILE="${CODEX_AUTH_FILE:-}"
CODEX_REASONING_EFFORT="${CODEX_REASONING_EFFORT:-}"
CODEX_SUPPORTS_REASONING_SUMMARIES="${CODEX_SUPPORTS_REASONING_SUMMARIES:-auto}"
DEEPSEEK_MODEL_ID="${DEEPSEEK_MODEL_ID:-deepseek-v4-pro}"
MAX_BUDGET_PER_TASK="${MAX_BUDGET_PER_TASK:-10}"
BEDROCK_MODEL_ID="${BEDROCK_MODEL_ID:-us.anthropic.claude-sonnet-4-5-20250929-v1:0}"
ANTHROPIC_MODEL_ID="${ANTHROPIC_MODEL_ID:-claude-sonnet-4-5}"
MODE="${MODE:-e2e}"
AGENT="${AGENT:-claude-code}"
AWS_PROFILE="${AWS_PROFILE:-}"
AWS_REGION="${AWS_REGION:-us-west-2}"
TIMEOUT="${TIMEOUT:-5400}"

# Set output directory based on agent if not specified
if [ -z "${AGENT_OUTPUT_DIR:-}" ]; then
    AGENT_OUTPUT_DIR="agent_output_${AGENT}"
fi

# Set prompt style based on agent unless explicitly overridden
if [[ -z "${PROMPT_STYLE:-}" ]]; then
    if [[ "$AGENT" = "openhands" ]]; then
        PROMPT_STYLE="no-test"
    else
        PROMPT_STYLE="iterative"
    fi
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_VENV_PYTHON="$SCRIPT_DIR/../.venv/bin/python"
if [[ -z "${PYTHON_BIN:-}" ]]; then
    if [[ -x "$PROJECT_VENV_PYTHON" ]]; then
        PYTHON_BIN="$PROJECT_VENV_PYTHON"
    else
        PYTHON_BIN="$(command -v python3)"
    fi
fi

# Print all descendants of a process. Restricting cleanup to this process tree
# prevents Ctrl-C in one batch from terminating other concurrent batches.
get_descendants() {
    local parent="$1"
    local child

    while read -r child; do
        [[ -n "$child" ]] || continue
        echo "$child"
        get_descendants "$child"
    done < <(pgrep -P "$parent" 2>/dev/null || true)
}

# Cleanup function
CLEANUP_DONE=0
cleanup() {
    if [ "$CLEANUP_DONE" = "1" ]; then
        return
    fi
    CLEANUP_DONE=1

    echo ""
    echo "[$(date +%H:%M:%S)] Received shutdown signal, cleaning up..."

    # Signal only processes belonging to this batch. The previous process-name
    # match also selected run_agent.py processes from unrelated Qwen/Opus runs.
    local -a descendants=()
    mapfile -t descendants < <(get_descendants $$)
    if (( ${#descendants[@]} > 0 )); then
        # SIGINT lets run_agent.py execute its container cleanup in finally blocks.
        kill -INT "${descendants[@]}" 2>/dev/null || true
    fi

    echo "[$(date +%H:%M:%S)] Cleanup complete"
    exit 130
}

trap cleanup SIGTERM SIGINT SIGHUP

# Validate task file
if [ ! -f "$TASKS_FILE" ]; then
    echo "ERROR: Task file not found: $TASKS_FILE"
    exit 1
fi

TOTAL=$(wc -l < "$TASKS_FILE" | tr -d ' ')

echo "=========================================="
echo "Batch Runner"
echo "=========================================="
echo "Agent: $AGENT"
echo "Prompt style: $PROMPT_STYLE"
echo "Tasks file: $TASKS_FILE ($TOTAL tasks)"
echo "Max parallel: $MAX_PARALLEL"
echo "Max attempts: $MAX_ATTEMPTS"
echo "Timeout: ${TIMEOUT}s ($((TIMEOUT/60))m)"
echo "Model Provider: $MODEL_PROVIDER"
case "$MODEL_PROVIDER" in
    anthropic) echo "Model: $ANTHROPIC_MODEL_ID" ;;
    bedrock)   echo "Model: $BEDROCK_MODEL_ID" ;;
    litellm)   echo "Model: $LITELLM_MODEL_ID" ;;
    openai)    echo "Model: $OPENAI_MODEL_ID" ;;
    deepseek)  echo "Model: $DEEPSEEK_MODEL_ID" ;;
esac
echo "Max budget per task: $MAX_BUDGET_PER_TASK"
echo "Python: $PYTHON_BIN"
echo "Mode: $MODE"
echo "AWS Profile: $AWS_PROFILE"
echo "Output dir: $AGENT_OUTPUT_DIR"
echo "=========================================="
echo ""

mkdir -p "$AGENT_OUTPUT_DIR"

# Function to run a single task
run_task() {
    local task="$1"
    local task_safe="${task//\//_}"

    echo "[$(date +%H:%M:%S)] Starting: $task"

    # Run agent and redirect output directly to log file
    local log_file="$AGENT_OUTPUT_DIR/${task_safe}_run.log"
    "$PYTHON_BIN" "$SCRIPT_DIR/run_agent.py" "$task" \
        --agent "$AGENT" \
        --prompt-style "$PROMPT_STYLE" \
        --mode "$MODE" \
        --max-attempts "$MAX_ATTEMPTS" \
        --timeout "$TIMEOUT" \
        --model-provider "$MODEL_PROVIDER" \
        --litellm-model-id "$LITELLM_MODEL_ID" \
        --openai-model-id "$OPENAI_MODEL_ID" \
        --codex-auth-mode "$CODEX_AUTH_MODE" \
        --codex-auth-file "$CODEX_AUTH_FILE" \
        --codex-reasoning-effort "$CODEX_REASONING_EFFORT" \
        --codex-supports-reasoning-summaries "$CODEX_SUPPORTS_REASONING_SUMMARIES" \
        --deepseek-model-id "$DEEPSEEK_MODEL_ID" \
        --max-budget-per-task "$MAX_BUDGET_PER_TASK" \
        --bedrock-model-id "$BEDROCK_MODEL_ID" \
        --anthropic-model-id "$ANTHROPIC_MODEL_ID" \
        --aws-profile "$AWS_PROFILE" \
        --aws-region "$AWS_REGION" \
        --agent-output "$AGENT_OUTPUT_DIR" > "$log_file" 2>&1 || true

    local exit_code=$?

    # Extract result from log file
    if grep -q 'Status: SUCCESS' "$log_file" 2>/dev/null; then
        echo "[$(date +%H:%M:%S)] SUCCESS: $task"
    else
        echo "[$(date +%H:%M:%S)] FAILED:  $task"
    fi

    # Show stage summary from log file
    grep -E "Attempt [0-9]+: S[0-9]" "$log_file" 2>/dev/null | sed 's/^/    /' || true

    return $exit_code
}

export -f run_task
export SCRIPT_DIR PYTHON_BIN AGENT_OUTPUT_DIR MODE MAX_ATTEMPTS AWS_PROFILE AWS_REGION LITELLM_MODEL_ID OPENAI_MODEL_ID CODEX_AUTH_MODE CODEX_AUTH_FILE CODEX_REASONING_EFFORT CODEX_SUPPORTS_REASONING_SUMMARIES DEEPSEEK_MODEL_ID MAX_BUDGET_PER_TASK BEDROCK_MODEL_ID ANTHROPIC_MODEL_ID AGENT PROMPT_STYLE TIMEOUT MODEL_PROVIDER ANTHROPIC_API_KEY OPENAI_API_KEY OPENAI_BASE_URL DEEPSEEK_API_KEY DEEPSEEK_BASE_URL

# Run tasks in parallel
echo "Starting parallel execution..."
echo ""

START_TIME=$(date +%s)

xargs -P "$MAX_PARALLEL" -I {} bash -c 'run_task "$@"' _ {} < "$TASKS_FILE"

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo ""
echo "=========================================="
echo "Batch complete! (${DURATION}s / $((DURATION/60))m)"
echo "=========================================="

# Summarize results
"$PYTHON_BIN" -c "
import json
import os

tasks_file = '$TASKS_FILE'
output_dir = '$AGENT_OUTPUT_DIR'

# Read task list
with open(tasks_file) as f:
    tasks = [line.strip() for line in f if line.strip() and not line.startswith('#')]

exact = 0
other = 0
failed = 0

print('')
print('=== RESULTS ===')

for task in tasks:
    task_safe = task.replace('/', '_')
    task_dir = os.path.join(output_dir, task_safe)

    status = 'NO_RESULT'
    details = ''

    if os.path.exists(task_dir):
        runs = sorted([d for d in os.listdir(task_dir) if os.path.isdir(os.path.join(task_dir, d))], reverse=True)
        if runs:
            summary_path = os.path.join(task_dir, runs[0], 'summary.json')
            if os.path.exists(summary_path):
                with open(summary_path) as f:
                    data = json.load(f)
                status = data.get('status', 'error').upper()
                duration = data.get('duration_minutes', 0)
                attempts = data.get('attempts', [])

                # Check for other bug (found A bug but not THE GT bug)
                for a in attempts:
                    if a.get('agent_success') and not a.get('gt_success'):
                        status = 'OTHER'
                        break

                # Build stage summary
                if attempts:
                    att = attempts[-1]
                    stages = []
                    for s in ['stage1', 'stage2', 'stage3', 'stage4']:
                        if att.get(s):
                            stages.append(f'{s[-1]}:{att[s][:1].upper()}')
                    details = f'({duration:.1f}m) [{\" \".join(stages)}]'

    if status == 'SUCCESS':
        exact += 1
        print(f'  [OK] {task} {details}')
    elif status == 'OTHER':
        other += 1
        print(f'  [OK] {task} {details} (other vuln)')
    else:
        failed += 1
        print(f'  [XX] {task} {details}')

total_success = exact + other
print('')
print('=== SUMMARY ===')
print(f'Total: {len(tasks)} | Success: {total_success} ({exact} GT, {other} other) | Failed: {failed}')
print(f'Results in: {output_dir}')
"
