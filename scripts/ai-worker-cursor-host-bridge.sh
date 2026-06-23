#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

export PATH="${HOME}/.local/bin:${PATH}"

bridge_dir="${AI_WORKER_CURSOR_HOST_BRIDGE_DIR:-.betelgeuze/cursor_worker_bridge}"
jobs_dir="$bridge_dir/jobs"
running_dir="$bridge_dir/running"
done_dir="$bridge_dir/done"
ready_file="$bridge_dir/host-bridge.ready"
mkdir -p "$jobs_dir" "$running_dir" "$done_dir"
chmod 700 "$bridge_dir" "$jobs_dir" "$running_dir" "$done_dir" 2>/dev/null || true

if ! command -v cursor-agent >/dev/null 2>&1 && ! command -v cursor >/dev/null 2>&1; then
  echo "Neither cursor-agent nor cursor was found on PATH." >&2
  exit 2
fi

if command -v cursor-agent >/dev/null 2>&1; then
  cursor_cmd=(cursor-agent)
else
  cursor_cmd=(cursor agent)
fi

printf '%s\n' "$$" > "$ready_file"
trap 'rm -f "$ready_file"' EXIT INT TERM

echo "Cursor host bridge ready: $bridge_dir"
echo "Leave this running in a host terminal with network access."

while true; do
  shopt -s nullglob
  jobs=("$jobs_dir"/*.job)
  shopt -u nullglob
  if [ "${#jobs[@]}" -eq 0 ]; then
    sleep "${AI_WORKER_CURSOR_HOST_BRIDGE_IDLE_SLEEP_SECONDS:-1}"
    continue
  fi
  for job_dir in "${jobs[@]}"; do
    job_name="$(basename "$job_dir")"
    running_job="$running_dir/$job_name"
    done_job="$done_dir/$job_name"
    if ! mv "$job_dir" "$running_job" 2>/dev/null; then
      continue
    fi

    prompt_path="$(cat "$running_job/prompt_path" 2>/dev/null || true)"
    model="$(cat "$running_job/model" 2>/dev/null || true)"
    sandbox="$(cat "$running_job/sandbox" 2>/dev/null || true)"
    raw_output="$(cat "$running_job/raw_output" 2>/dev/null || true)"
    model="${model:-auto}"
    sandbox="${sandbox:-enabled}"

    status=1
    if [ -z "$prompt_path" ] || [ -z "$raw_output" ] || [ ! -f "$prompt_path" ]; then
      if [ -n "$raw_output" ]; then
        mkdir -p "$(dirname "$raw_output")"
        printf '%s\n' "Cursor host bridge invalid job metadata." > "$raw_output"
      fi
      status=2
    else
      mkdir -p "$(dirname "$raw_output")"
      set +e
      "${cursor_cmd[@]}" \
        --print \
        --force \
        --trust \
        --sandbox "$sandbox" \
        --model "$model" < "$prompt_path" > "$raw_output" 2>&1
      status=$?
      set -e
    fi

    printf '%s\n' "$status" > "$running_job/exit_code"
    rm -rf "$done_job"
    mv "$running_job" "$done_job"
  done
done
