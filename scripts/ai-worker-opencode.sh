#!/usr/bin/env bash
set -euo pipefail
prompt_file="${1:?usage: ai-worker-opencode.sh <prompt-file>}"

if [[ ! -f "$prompt_file" ]]; then
  echo "Prompt file not found: $prompt_file" >&2
  exit 2
fi

OPENCODE_MODEL="${OPENCODE_MODEL:-opencode-go/minimax-m3}"

if ! command -v opencode >/dev/null 2>&1; then
  if [ -x "${HOME}/.local/bin/opencode" ]; then
    export PATH="${HOME}/.local/bin:${PATH}"
  elif command -v npm >/dev/null 2>&1; then
    npm_prefix="$(npm prefix -g 2>/dev/null || true)"
    if [ -n "$npm_prefix" ] && [ -x "${npm_prefix}/bin/opencode" ]; then
      export PATH="${npm_prefix}/bin:${PATH}"
    fi
  fi
fi

if ! command -v opencode >/dev/null 2>&1; then
  echo "opencode CLI was not found on PATH. Install with: npm install -g opencode-ai" >&2
  exit 2
fi

# Static preflight only. Actual OpenCode tool execution must be constrained by opencode.json permissions.
./scripts/ai-dangerous-command-check.sh "opencode run --model ${OPENCODE_MODEL} --dir . --file <prompt-file>"

output_dir="${AI_WORKER_OUTPUT_DIR:-.betelgeuze/worker_outputs}"
mkdir -p "$output_dir"
safe_prompt_name="$(basename "$prompt_file" | tr -cd 'A-Za-z0-9._-')"
run_id="$(date -u +%Y%m%dT%H%M%SZ)-opencode-${safe_prompt_name:-worker}"
raw_output="$output_dir/${run_id}.raw.md"
summary_output="$output_dir/${run_id}.summary.md"
chmod 700 "$output_dir" 2>/dev/null || true
: > "$raw_output"
chmod 600 "$raw_output" 2>/dev/null || true

# Do not pass --dangerously-skip-permissions in worker runs.
# Do not read the prompt file into a shell variable or pass the prompt body as argv.
set +e
opencode run \
  --model "$OPENCODE_MODEL" \
  --dir . \
  --file "$prompt_file" \
  --title "codex-goal-worker" \
  "Read the attached prompt file and execute its instructions. Do not echo the full prompt body. Return only: Changed files, Test results, Failed tests, Core diff summary, Blockers. Do not include full logs or full diffs." > "$raw_output" 2>&1
worker_status=$?
set -e

if [ "$worker_status" -ne 0 ]; then
  echo "OpenCode worker failed with exit status ${worker_status}. Raw output captured at ${raw_output}; not printing raw output." >&2
  exit "$worker_status"
fi

if ! node scripts/validate-ai-worker-output.mjs --sanitize-out "$summary_output" "$raw_output"; then
  echo "OpenCode worker output failed format validation. Raw output captured at ${raw_output}; not printing raw output." >&2
  exit 3
fi

if [ "${AI_WORKER_KEEP_RAW:-0}" != "1" ]; then
  rm -f "$raw_output"
fi

cat "$summary_output"
