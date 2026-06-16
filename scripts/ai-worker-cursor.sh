#!/usr/bin/env bash
set -euo pipefail
prompt_file="${1:?usage: ai-worker-cursor.sh <prompt-file>}"

if [[ ! -f "$prompt_file" ]]; then
  echo "Prompt file not found: $prompt_file" >&2
  exit 2
fi

CURSOR_AGENT_MODEL="${CURSOR_AGENT_MODEL:-auto}"
CURSOR_AGENT_SANDBOX="${CURSOR_AGENT_SANDBOX:-enabled}"

if ! command -v cursor-agent >/dev/null 2>&1 && [ -x "${HOME}/.local/bin/cursor-agent" ]; then
  export PATH="${HOME}/.local/bin:${PATH}"
fi

if command -v cursor-agent >/dev/null 2>&1; then
  CURSOR_AGENT_CMD=(cursor-agent)
elif command -v cursor >/dev/null 2>&1; then
  CURSOR_AGENT_CMD=(cursor agent)
elif [ -x "${HOME}/.local/bin/cursor" ]; then
  CURSOR_AGENT_CMD=("${HOME}/.local/bin/cursor" agent)
else
  echo "Neither cursor-agent nor cursor was found on PATH." >&2
  exit 2
fi

# Static preflight only. Configure Cursor/Cursor Agent permissions separately.
./scripts/ai-dangerous-command-check.sh "${CURSOR_AGENT_CMD[*]} --model ${CURSOR_AGENT_MODEL} < prompt-file"

output_dir="${AI_WORKER_OUTPUT_DIR:-.betelgeuze/worker_outputs}"
mkdir -p "$output_dir"
safe_prompt_name="$(basename "$prompt_file" | tr -cd 'A-Za-z0-9._-')"
run_id="$(date -u +%Y%m%dT%H%M%SZ)-cursor-${safe_prompt_name:-worker}"
raw_output="$output_dir/${run_id}.raw.md"
summary_output="$output_dir/${run_id}.summary.md"
chmod 700 "$output_dir" 2>/dev/null || true
: > "$raw_output"
chmod 600 "$raw_output" 2>/dev/null || true

# Do not pass prompt text as argv. Keep the prompt body on stdin.
set +e
"${CURSOR_AGENT_CMD[@]}" \
  --print \
  --force \
  --trust \
  --sandbox "$CURSOR_AGENT_SANDBOX" \
  --model "$CURSOR_AGENT_MODEL" < "$prompt_file" > "$raw_output" 2>&1
worker_status=$?
set -e

if [ "$worker_status" -ne 0 ]; then
  echo "Cursor worker failed with exit status ${worker_status}. Raw output captured at ${raw_output}; not printing raw output." >&2
  exit "$worker_status"
fi

if ! node scripts/validate-ai-worker-output.mjs --sanitize-out "$summary_output" "$raw_output"; then
  echo "Cursor worker output failed format validation. Raw output captured at ${raw_output}; not printing raw output." >&2
  exit 3
fi

if [ "${AI_WORKER_KEEP_RAW:-0}" != "1" ]; then
  rm -f "$raw_output"
fi

cat "$summary_output"
