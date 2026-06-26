#!/usr/bin/env bash
set -euo pipefail
prompt_file="${1:?usage: ai-worker-cursor.sh <prompt-file>}"

if [[ ! -f "$prompt_file" ]]; then
  echo "Prompt file not found: $prompt_file" >&2
  exit 2
fi

CURSOR_AGENT_MODEL="${CURSOR_AGENT_MODEL:-auto}"
CURSOR_AGENT_SANDBOX="${CURSOR_AGENT_SANDBOX:-enabled}"
CURSOR_AGENT_RETRIES="${AI_WORKER_CURSOR_RETRIES:-3}"
CURSOR_AGENT_RETRY_DELAY_SECONDS="${AI_WORKER_CURSOR_RETRY_DELAY_SECONDS:-2}"
CURSOR_HOST_BRIDGE_MODE="${AI_WORKER_CURSOR_HOST_BRIDGE:-auto}"
CURSOR_HOST_BRIDGE_TIMEOUT_SECONDS="${AI_WORKER_CURSOR_HOST_BRIDGE_TIMEOUT_SECONDS:-1800}"
CURSOR_HOST_BRIDGE_POLL_SECONDS="${AI_WORKER_CURSOR_HOST_BRIDGE_POLL_SECONDS:-2}"

case "$CURSOR_AGENT_RETRIES" in
  ""|*[!0-9]*)
    echo "AI_WORKER_CURSOR_RETRIES must be a non-negative integer." >&2
    exit 2
    ;;
esac
case "$CURSOR_AGENT_RETRY_DELAY_SECONDS" in
  ""|*[!0-9]*)
    echo "AI_WORKER_CURSOR_RETRY_DELAY_SECONDS must be a non-negative integer." >&2
    exit 2
    ;;
esac
case "$CURSOR_HOST_BRIDGE_TIMEOUT_SECONDS" in
  ""|*[!0-9]*)
    echo "AI_WORKER_CURSOR_HOST_BRIDGE_TIMEOUT_SECONDS must be a non-negative integer." >&2
    exit 2
    ;;
esac
case "$CURSOR_HOST_BRIDGE_POLL_SECONDS" in
  ""|*[!0-9]*)
    echo "AI_WORKER_CURSOR_HOST_BRIDGE_POLL_SECONDS must be a non-negative integer." >&2
    exit 2
    ;;
esac

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
bridge_dir="${AI_WORKER_CURSOR_HOST_BRIDGE_DIR:-.betelgeuze/cursor_worker_bridge}"
bridge_jobs_dir="$bridge_dir/jobs"
bridge_done_dir="$bridge_dir/done"
bridge_ready_file="$bridge_dir/host-bridge.ready"

cursor_transient_network_failure() {
  [ -f "$raw_output" ] || return 1
  LC_ALL=C grep -Eiq \
    'getaddrinfo EAI_AGAIN|ENOTFOUND|ECONNRESET|ETIMEDOUT|network.*(unavailable|timeout)|api2[.]cursor[.]sh' \
    "$raw_output"
}

cursor_host_bridge_available() {
  case "$CURSOR_HOST_BRIDGE_MODE" in
    0|false|off|disabled) return 1 ;;
  esac
  [ -f "$bridge_ready_file" ] && [ -d "$bridge_jobs_dir" ] && [ -d "$bridge_done_dir" ]
}

cursor_host_bridge_wait() {
  cursor_host_bridge_available || return 1
  bridge_job_id="${run_id}-host"
  bridge_tmp_dir="$bridge_jobs_dir/.${bridge_job_id}.tmp"
  bridge_job_dir="$bridge_jobs_dir/${bridge_job_id}.job"
  bridge_done_job_dir="$bridge_done_dir/${bridge_job_id}.job"
  rm -rf "$bridge_tmp_dir" "$bridge_job_dir" "$bridge_done_job_dir"
  mkdir -p "$bridge_tmp_dir"
  printf '%s\n' "$(realpath "$prompt_file")" > "$bridge_tmp_dir/prompt_path"
  printf '%s\n' "$CURSOR_AGENT_MODEL" > "$bridge_tmp_dir/model"
  printf '%s\n' "$CURSOR_AGENT_SANDBOX" > "$bridge_tmp_dir/sandbox"
  printf '%s\n' "$(realpath -m "$raw_output")" > "$bridge_tmp_dir/raw_output"
  mv "$bridge_tmp_dir" "$bridge_job_dir"
  echo "Cursor worker routed to host bridge job ${bridge_job_id}; waiting for host Cursor Agent." >&2

  waited=0
  while [ ! -f "$bridge_done_job_dir/exit_code" ]; do
    if [ "$CURSOR_HOST_BRIDGE_TIMEOUT_SECONDS" -gt 0 ] \
      && [ "$waited" -ge "$CURSOR_HOST_BRIDGE_TIMEOUT_SECONDS" ]; then
      echo "Cursor host bridge timed out after ${CURSOR_HOST_BRIDGE_TIMEOUT_SECONDS}s for job ${bridge_job_id}." >&2
      return 124
    fi
    if [ "$CURSOR_HOST_BRIDGE_POLL_SECONDS" -gt 0 ]; then
      sleep "$CURSOR_HOST_BRIDGE_POLL_SECONDS"
      waited=$((waited + CURSOR_HOST_BRIDGE_POLL_SECONDS))
    else
      sleep 1
      waited=$((waited + 1))
    fi
  done
  bridge_status="$(cat "$bridge_done_job_dir/exit_code" 2>/dev/null || printf '1')"
  case "$bridge_status" in
    ""|*[!0-9]*) bridge_status=1 ;;
  esac
  return "$bridge_status"
}

# Do not pass prompt text as argv. Keep the prompt body on stdin.
attempt=0
worker_status=1
while [ "$attempt" -le "$CURSOR_AGENT_RETRIES" ]; do
  attempt=$((attempt + 1))
  : > "$raw_output"
  set +e
  "${CURSOR_AGENT_CMD[@]}" \
    --print \
    --force \
    --trust \
    --sandbox "$CURSOR_AGENT_SANDBOX" \
    --model "$CURSOR_AGENT_MODEL" < "$prompt_file" > "$raw_output" 2>&1
  worker_status=$?
  set -e
  if [ "$worker_status" -eq 0 ]; then
    break
  fi
  if [ "$attempt" -le "$CURSOR_AGENT_RETRIES" ] && cursor_transient_network_failure; then
    echo "Cursor worker transient network/DNS failure on attempt ${attempt}; retrying. Raw output captured at ${raw_output}; not printing raw output." >&2
    if [ "$CURSOR_AGENT_RETRY_DELAY_SECONDS" -gt 0 ]; then
      sleep "$CURSOR_AGENT_RETRY_DELAY_SECONDS"
    fi
    continue
  fi
  break
done

if [ "$worker_status" -ne 0 ]; then
  if cursor_transient_network_failure; then
    if cursor_host_bridge_available; then
      if cursor_host_bridge_wait; then
        worker_status=0
      else
        worker_status=$?
        echo "Cursor host bridge failed with exit status ${worker_status}. Raw output captured at ${raw_output}; not printing raw output." >&2
        exit "$worker_status"
      fi
    else
    echo "Cursor worker failed after ${attempt} attempt(s) due to network/DNS access to Cursor Agent API. Raw output captured at ${raw_output}; not printing raw output." >&2
    echo "Check host network/DNS access to api2.cursor.sh or run from a Cursor/host terminal with outbound network access." >&2
    echo "For automatic Codex-to-Cursor dispatch from this sandbox, start the host bridge in a host terminal: ./scripts/ai-worker-cursor-host-bridge.sh" >&2
    exit "$worker_status"
    fi
  fi
fi

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
