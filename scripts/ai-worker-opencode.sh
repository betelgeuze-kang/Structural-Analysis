#!/usr/bin/env bash
set -euo pipefail
prompt_file="${1:?usage: ai-worker-opencode.sh <prompt-file>}"

if [[ ! -f "$prompt_file" ]]; then
  echo "Prompt file not found: $prompt_file" >&2
  exit 2
fi

OPENCODE_DEFAULT_MODEL="opencode-go/deepseek-v4-pro"
OPENCODE_DEEPSEEK_V4_PRO_MODEL="opencode-go/deepseek-v4-pro"
OPENCODE_MINIMAX_M3_MODEL="opencode-go/minimax-m3"
OPENCODE_GLM52_MODEL="opencode-go/glm-5.2"
OPENCODE_MODEL="${OPENCODE_MODEL:-${AI_WORKER_OPENCODE_MODEL:-$OPENCODE_DEFAULT_MODEL}}"
case "$OPENCODE_MODEL" in
  minimax/m3|minimax-m3|minimaxm3|minimax3|minimax\ m3|minimax\ 3|m3)
    OPENCODE_MODEL="$OPENCODE_MINIMAX_M3_MODEL"
    ;;
  glm/5.2|glm-5.2|glm5.2|glm\ 5.2|kimi/k2.7|kimi-k2.7|k2.7|kimi-k2.7-code)
    OPENCODE_MODEL="$OPENCODE_GLM52_MODEL"
    ;;
  deepseek/v4/pro|deepseek-v4-pro|deepseekv4pro|deepseek\ v4\ pro|v4-pro)
    OPENCODE_MODEL="$OPENCODE_DEEPSEEK_V4_PRO_MODEL"
    ;;
esac
OPENCODE_TIMEOUT_SECONDS="${AI_WORKER_OPENCODE_TIMEOUT_SECONDS:-600}"
OPENCODE_USAGE_FALLBACK_ENABLED="${AI_WORKER_OPENCODE_USAGE_FALLBACK_ENABLED:-1}"
OPENCODE_USAGE_FALLBACK_CURSOR_MODEL="${AI_WORKER_OPENCODE_USAGE_FALLBACK_CURSOR_MODEL:-composer-2.5}"
OPENCODE_ASSIGNMENT_CURSOR_MODEL="${AI_WORKER_OPENCODE_ASSIGNMENT_CURSOR_MODEL:-composer-2.5}"
case "$OPENCODE_TIMEOUT_SECONDS" in
  ""|*[!0-9]*)
    echo "AI_WORKER_OPENCODE_TIMEOUT_SECONDS must be a positive integer number of seconds." >&2
    exit 2
    ;;
esac

# Compatibility entrypoint: current OpenCode task assignment is routed directly
# to Cursor composer-2.5, preserving prompt-file handoff and summary validation.
./scripts/ai-dangerous-command-check.sh "CURSOR_AGENT_MODEL=${OPENCODE_ASSIGNMENT_CURSOR_MODEL} ./scripts/ai-worker-cursor.sh <prompt-file>"
echo "OpenCode worker assignment is routed to Cursor model ${OPENCODE_ASSIGNMENT_CURSOR_MODEL}." >&2
CURSOR_AGENT_MODEL="$OPENCODE_ASSIGNMENT_CURSOR_MODEL" ./scripts/ai-worker-cursor.sh "$prompt_file"
exit $?

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

opencode_usage_exhausted() {
  [ -f "$raw_output" ] || return 1
  LC_ALL=C grep -Eiq \
    '((quota|usage|credit|credits|limit|limits).*(exhaust|exceeded|reached|depleted|spent|used up|insufficient|unavailable))|((exhaust|exceeded|reached|depleted|spent|used up|insufficient).*(quota|usage|credit|credits|limit|limits))|payment required|402' \
    "$raw_output"
}

run_cursor_usage_fallback() {
  if [ "$OPENCODE_USAGE_FALLBACK_ENABLED" = "0" ]; then
    return 1
  fi
  echo "OpenCode usage/quota appears exhausted; delegating same prompt to Cursor model ${OPENCODE_USAGE_FALLBACK_CURSOR_MODEL}." >&2
  CURSOR_AGENT_MODEL="$OPENCODE_USAGE_FALLBACK_CURSOR_MODEL" ./scripts/ai-worker-cursor.sh "$prompt_file"
}

# VS Code snap sessions can set XDG_DATA_HOME to the active OpenCode account
# store. Prefer it when writable so provider/model registry state is preserved;
# for OpenCode Go, mirror auth/account symlinks into a private writable /tmp
# data home when the account store itself is read-only in the Codex sandbox.
opencode_go_source_data_home() {
  if [ -n "${AI_WORKER_OPENCODE_GO_SOURCE_DATA_HOME:-}" ] \
    && [ -f "${AI_WORKER_OPENCODE_GO_SOURCE_DATA_HOME}/opencode/auth.json" ] \
    && [ -f "${AI_WORKER_OPENCODE_GO_SOURCE_DATA_HOME}/opencode/account.json" ]; then
    printf '%s\n' "$AI_WORKER_OPENCODE_GO_SOURCE_DATA_HOME"
    return
  fi
  for candidate in \
    "${XDG_DATA_HOME:-}" \
    "${HOME}/snap/code/247/.local/share" \
    "${HOME}/.local/share" \
    "${HOME}"/snap/code/*/.local/share; do
    [ -n "$candidate" ] || continue
    if [ -f "${candidate}/opencode/auth.json" ] && [ -f "${candidate}/opencode/account.json" ]; then
      printf '%s\n' "$candidate"
      return
    fi
  done
}

link_opencode_go_credential() {
  source_file="$1"
  link_file="$2"
  if [ -L "$link_file" ]; then
    if [ "$(readlink "$link_file" 2>/dev/null || true)" != "$source_file" ]; then
      ln -sfn "$source_file" "$link_file"
    fi
  elif [ -e "$link_file" ]; then
    echo "OpenCode Go mirror credential path already exists and is not a symlink: ${link_file}" >&2
    return 1
  else
    ln -s "$source_file" "$link_file"
  fi
}

prepare_opencode_go_mirror_data_home() {
  source_home="$(opencode_go_source_data_home || true)"
  [ -n "$source_home" ] || return 1
  mirror_home="${AI_WORKER_OPENCODE_GO_MIRROR_XDG_DATA_HOME:-${TMPDIR:-/tmp}/codex-opencode-go-xdg-data}"
  mkdir -p "$mirror_home/opencode/log"
  chmod 700 "$mirror_home" "$mirror_home/opencode" 2>/dev/null || true
  link_opencode_go_credential "$source_home/opencode/auth.json" "$mirror_home/opencode/auth.json"
  link_opencode_go_credential "$source_home/opencode/account.json" "$mirror_home/opencode/account.json"
  printf '%s\n' "$mirror_home"
}

select_opencode_xdg_data_home() {
  if [ -n "${AI_WORKER_OPENCODE_XDG_DATA_HOME:-}" ]; then
    printf '%s\n' "$AI_WORKER_OPENCODE_XDG_DATA_HOME"
    return
  fi
  if [ -n "${XDG_DATA_HOME:-}" ]; then
    candidate="$XDG_DATA_HOME"
    if mkdir -p "$candidate/opencode/log" 2>/dev/null \
      && touch "$candidate/opencode/log/.codex-write-test" 2>/dev/null; then
      rm -f "$candidate/opencode/log/.codex-write-test" 2>/dev/null || true
      printf '%s\n' "$candidate"
      return
    fi
  fi
  case "$OPENCODE_MODEL" in
    opencode-go/*)
      if go_mirror_home="$(prepare_opencode_go_mirror_data_home)"; then
        printf '%s\n' "$go_mirror_home"
        return
      fi
      ;;
  esac
  printf '%s\n' "${TMPDIR:-/tmp}/codex-opencode-xdg-data"
}

opencode_xdg_data_home="$(select_opencode_xdg_data_home)"
mkdir -p "$opencode_xdg_data_home/opencode/log"
export XDG_DATA_HOME="$opencode_xdg_data_home"

if [ "${AI_WORKER_OPENCODE_MODEL_CHECK:-1}" != "0" ]; then
  if ! opencode_models="$(opencode models 2>/dev/null)"; then
    echo "OpenCode model registry query failed for XDG_DATA_HOME=${XDG_DATA_HOME}." >&2
    exit 2
  fi
  if ! printf '%s\n' "$opencode_models" | grep -Fx -- "$OPENCODE_MODEL" >/dev/null; then
    echo "OpenCode model '${OPENCODE_MODEL}' is not registered for XDG_DATA_HOME=${XDG_DATA_HOME}." >&2
    echo "Set AI_WORKER_OPENCODE_XDG_DATA_HOME to a writable OpenCode account store or choose a registered OPENCODE_MODEL." >&2
    exit 2
  fi
fi

codex_terminal_network_restricted() {
  proc_cmdline="$(tr '\0' ' ' </proc/1/cmdline 2>/dev/null || true)"
  case "$proc_cmdline" in
    *"--unshare-net"*|*"\"network\":\"restricted\""*) return 0 ;;
    *) return 1 ;;
  esac
}

if [ "${AI_WORKER_OPENCODE_NETWORK_PREFLIGHT:-1}" != "0" ]; then
  case "$OPENCODE_MODEL" in
    opencode-go/*)
      if codex_terminal_network_restricted; then
        rm -f "$raw_output"
        echo "OpenCode worker cannot run from this Codex terminal sandbox: outbound network is restricted (--unshare-net/network:restricted)." >&2
        echo "CLI/model registry are local checks; OpenCode Go inference still requires network access." >&2
        echo "Run this wrapper from a host/Cursor terminal with network access, or start a Codex session whose terminal tools allow outbound network." >&2
        exit 2
      fi
      ;;
  esac
fi

# Do not pass --dangerously-skip-permissions in worker runs.
# Do not read the prompt file into a shell variable or pass the prompt body as argv.
set +e
opencode_command=(
  opencode run
  --model "$OPENCODE_MODEL" \
  --dir . \
  --file "$prompt_file" \
  --title "codex-goal-worker" \
  "Read the attached prompt file and execute its instructions. Do not echo the full prompt body. Return only: Changed files, Test results, Failed tests, Core diff summary, Blockers. Do not include full logs or full diffs."
)
if command -v timeout >/dev/null 2>&1; then
  timeout "${OPENCODE_TIMEOUT_SECONDS}s" "${opencode_command[@]}" > "$raw_output" 2>&1
else
  "${opencode_command[@]}" > "$raw_output" 2>&1
fi
worker_status=$?
set -e

if [ "$worker_status" -eq 124 ]; then
  echo "OpenCode worker timed out after ${OPENCODE_TIMEOUT_SECONDS}s. Raw output captured at ${raw_output}; not printing raw output." >&2
  exit "$worker_status"
fi

if [ "$worker_status" -ne 0 ]; then
  if opencode_usage_exhausted; then
    run_cursor_usage_fallback
    exit $?
  fi
  echo "OpenCode worker failed with exit status ${worker_status}. Raw output captured at ${raw_output}; not printing raw output." >&2
  exit "$worker_status"
fi

if ! node scripts/validate-ai-worker-output.mjs --sanitize-out "$summary_output" "$raw_output"; then
  if opencode_usage_exhausted; then
    run_cursor_usage_fallback
    exit $?
  fi
  echo "OpenCode worker output failed format validation. Raw output captured at ${raw_output}; not printing raw output." >&2
  exit 3
fi

if [ "${AI_WORKER_KEEP_RAW:-0}" != "1" ]; then
  rm -f "$raw_output"
fi

cat "$summary_output"
