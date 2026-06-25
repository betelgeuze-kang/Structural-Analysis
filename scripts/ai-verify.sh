#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

json_out=""
full_mode="${AI_VERIFY_FULL:-0}"

usage() {
  cat <<'EOF'
usage: bash scripts/ai-verify.sh [--full|--contract] [--json-out <path>]

Modes:
  --contract  Run the lightweight AI orchestration contract checks (default).
  --full      Run contract checks plus npm build, pytest, and compileall.

Options:
  --json-out  Write a machine-readable ai-verify-result.v1 receipt.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --json-out)
      if [ "$#" -lt 2 ] || [ -z "${2:-}" ]; then
        echo "missing value for --json-out" >&2
        usage >&2
        exit 2
      fi
      json_out="$2"
      shift 2
      ;;
    --full)
      full_mode="1"
      shift
      ;;
    --contract)
      full_mode="0"
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "unexpected argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "$full_mode" in
  1|true|TRUE|yes|YES) full_mode="1" ;;
  *) full_mode="0" ;;
esac

checks_file="$(mktemp)"
warnings_file="$(mktemp)"
cleanup() {
  rm -f "$checks_file" "$warnings_file"
}
trap cleanup EXIT

pass_count=0
fail_count=0

record_check() {
  local id="$1"
  local scope="$2"
  local label="$3"
  local passed="$4"
  printf '%s\t%s\t%s\t%s\n' "$id" "$scope" "$passed" "$label" >>"$checks_file"
  if [ "$passed" = "true" ]; then
    pass_count=$((pass_count + 1))
    echo "  PASS $label"
  else
    fail_count=$((fail_count + 1))
    echo "  FAIL $label" >&2
  fi
}

run_check() {
  local id="$1"
  local scope="$2"
  local label="$3"
  shift 3
  echo "==> $label"
  if "$@"; then
    record_check "$id" "$scope" "$label" true
  else
    record_check "$id" "$scope" "$label" false
  fi
}

add_warning() {
  local message="$*"
  printf '%s\n' "$message" >>"$warnings_file"
  echo "  WARN $message"
}

check_shell_syntax() {
  bash -n scripts/ai-dangerous-command-check.sh \
    scripts/ai-run-kiro-design.sh \
    scripts/ai-worker-kiro.sh \
    scripts/ai-worker-cursor.sh \
    scripts/ai-worker-cursor-host-bridge.sh \
    scripts/ai-worker-opencode.sh \
    scripts/ai-preflight.sh \
    scripts/ai-verify.sh
}

check_json_files() {
  python3 -m json.tool package.json >/dev/null \
    && python3 -m json.tool opencode.json >/dev/null \
    && python3 -m json.tool .betelgeuze/verification.json >/dev/null
}

check_required_files() {
  local missing=0
  local required=(
    AGENTS.md
    docs/ai/ORCHESTRATION.md
    docs/ai/prompts/codex_goal_start.md
    docs/ai/prompts/kiro_design_slice.md
    docs/ai/prompts/cursor_worker_slice.md
    docs/ai/prompts/opencode_worker_slice.md
    docs/ai/checklists/ai-agent-security.md
    docs/ai/checklists/pre-review.md
    docs/ai/checklists/pre-merge.md
    docs/ai/goal/GOAL.md
    opencode.json
    scripts/validate-ai-worker-output.mjs
    scripts/ai-run-kiro-design.sh
    scripts/ai-worker-kiro.sh
    scripts/ai-worker-cursor.sh
    scripts/ai-worker-cursor-host-bridge.sh
    scripts/ai-worker-opencode.sh
    scripts/ai-preflight.sh
    scripts/ai-verify.sh
    tests/ai-worker-output-validator.test.mjs
    tests/ai-verify-contract.test.mjs
  )
  local path
  for path in "${required[@]}"; do
    if [ ! -f "$path" ]; then
      echo "missing required file: $path" >&2
      missing=1
    fi
  done
  return "$missing"
}

warn_non_executable_scripts() {
  local scripts=(
    scripts/ai-worker-cursor.sh
    scripts/ai-worker-opencode.sh
    scripts/ai-preflight.sh
    scripts/ai-verify.sh
  )
  local script
  for script in "${scripts[@]}"; do
    if [ -f "$script" ] && [ ! -x "$script" ]; then
      add_warning "$script is not executable; invoke it with bash"
    fi
  done
}

check_worker_output_validator() {
  node --test \
    tests/ai-worker-output-validator.test.mjs \
    tests/ai-verify-contract.test.mjs
}

check_package_scripts() {
  node -e "const p=require('./package.json'); for (const s of ['ai:kiro-design','ai:preflight','ai:verify','ai:verify:contract','ai:verify:full','ai:validate-worker-output']) { if (!p.scripts || !p.scripts[s]) throw new Error('missing script '+s); }"
}

run_check shell_syntax contract "shell syntax" check_shell_syntax
run_check json contract "JSON contracts" check_json_files
run_check required_files contract "required files" check_required_files
warn_non_executable_scripts
run_check worker_output_validator contract "worker output validator" check_worker_output_validator
run_check package_scripts contract "package scripts" check_package_scripts

echo "==> worker CLI availability"
if ! command -v cursor-agent >/dev/null 2>&1 && [ -x "${HOME}/.local/bin/cursor-agent" ]; then
  export PATH="${HOME}/.local/bin:${PATH}"
fi
if command -v cursor-agent >/dev/null 2>&1; then
  echo "cursor worker cli: cursor-agent"
elif command -v cursor >/dev/null 2>&1; then
  echo "cursor worker cli: cursor"
else
  add_warning "cursor worker CLI missing (worker disabled until installed)"
fi

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
if command -v opencode >/dev/null 2>&1; then
  echo "opencode worker cli: $(opencode --version)"
else
  add_warning "opencode worker CLI missing (worker disabled until installed)"
fi

if [ "$full_mode" = "1" ]; then
  run_check full_build full "full project build" npm run build
  run_check full_pytest full "full pytest" pytest
  run_check full_compileall full "Python compileall" python3 -m compileall .
fi

write_result() {
  [ -n "$json_out" ] || return 0
  local output_dir
  output_dir="$(dirname "$json_out")"
  mkdir -p "$output_dir"
  local source_commit
  source_commit="$(git rev-parse HEAD 2>/dev/null || true)"
  python3 - "$checks_file" "$warnings_file" "$json_out" "$source_commit" "$full_mode" <<'PY'
import datetime as dt
import json
import pathlib
import sys

checks_path, warnings_path, out_path, source_commit, full_mode = sys.argv[1:]
checks = []
for raw in pathlib.Path(checks_path).read_text(encoding="utf-8").splitlines():
    if not raw:
        continue
    check_id, scope, passed, label = raw.split("\t", 3)
    checks.append({
        "id": check_id,
        "scope": scope,
        "label": label,
        "passed": passed == "true",
    })
warnings = [
    line for line in pathlib.Path(warnings_path).read_text(encoding="utf-8").splitlines()
    if line
]
contract_checks = [row for row in checks if row["scope"] == "contract"]
full_checks = [row for row in checks if row["scope"] == "full"]
payload = {
    "schema_version": "ai-verify-result.v1",
    "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    "source_commit_sha": source_commit,
    "contract_pass": bool(contract_checks) and all(row["passed"] for row in contract_checks),
    "full_mode": full_mode == "1",
    "full_pass": (all(row["passed"] for row in full_checks) if full_checks else None),
    "checks": checks,
    "warnings": warnings,
    "claim_boundary": (
        "This receipt verifies repository AI orchestration contracts and, in full mode, "
        "local project checks. It does not authorize product-readiness promotion, release, "
        "deployment, billing mutation, or external claims."
    ),
}
pathlib.Path(out_path).write_text(
    json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY
  python3 -m json.tool "$json_out" >/dev/null
  echo "AI verify receipt: $json_out"
}

if ! write_result; then
  fail_count=$((fail_count + 1))
  echo "  FAIL machine-readable result" >&2
fi

echo "==> summary: ${pass_count} passed, ${fail_count} failed, $(wc -l <"$warnings_file" | tr -d ' ') warning(s)"
if [ "$fail_count" -gt 0 ]; then
  echo "verify failed" >&2
  exit 1
fi

echo "verify ok"
