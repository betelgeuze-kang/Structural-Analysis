#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

usage() {
  echo "usage: $0 [--check] <kiro-design-prompt-file> [launch-receipt-json]" >&2
}

check_only=0
if [ "${1:-}" = "--check" ]; then
  check_only=1
  shift
fi

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  usage
  exit 2
fi

prompt_file="$1"
launch_receipt="${2:-${prompt_file%.md}.kiro-launch.json}"
required_kiro_model="opus-4.8"
required_model_line="model \`${required_kiro_model}\`"
required_no_edit_boundary="Do not edit files"
required_no_closure_boundary="Do not claim readiness closure"
instruction="Run the attached Kiro design slice as design-only architect on ${required_kiro_model}. Confirm the prompt's ${required_kiro_model} target in your answer, do not edit files, do not claim readiness closure, and return only the required sections from the attached prompt."

if [ ! -f "$prompt_file" ]; then
  echo "kiro worker: prompt file not found: $prompt_file" >&2
  exit 2
fi

validate_kiro_prompt() {
  local file="$1"
  if ! grep -Fq -- "$required_model_line" "$file"; then
    echo "kiro worker: prompt must explicitly target Kiro model ${required_kiro_model}" >&2
    return 2
  fi
  if ! grep -Fq -- "$required_no_edit_boundary" "$file"; then
    echo "kiro worker: prompt must include design-only no-edit boundary" >&2
    return 2
  fi
  if ! grep -Fq -- "$required_no_closure_boundary" "$file"; then
    echo "kiro worker: prompt must forbid readiness closure claims" >&2
    return 2
  fi
}

validate_kiro_prompt "$prompt_file"
wrapper_validation_mode="automatic_prelaunch_before_kiro_chat"

if [ "$check_only" -eq 1 ]; then
  echo "kiro worker: prompt validation passed for ${required_kiro_model}"
  exit 0
fi

mkdir -p "$(dirname "$launch_receipt")"

write_launch_receipt() {
  local status="$1"
  local kiro_path="$2"
  local kiro_cli_found="$3"
  local kiro_chat_command_available="$4"
  local stdout_size="$5"
  local stderr_size="$6"
  local design_output_path="$7"
  python3 - "$prompt_file" "$launch_receipt" "$status" "$kiro_path" "$required_kiro_model" "$wrapper_validation_mode" "$kiro_cli_found" "$kiro_chat_command_available" "$stdout_size" "$stderr_size" "$instruction" "$design_output_path" <<'PY'
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

prompt_file = Path(sys.argv[1])
launch_receipt = Path(sys.argv[2])
status_arg = sys.argv[3]
status = None if status_arg == "null" else int(status_arg)
kiro_path = sys.argv[4]
required_kiro_model = sys.argv[5]
wrapper_validation_mode = sys.argv[6]
kiro_cli_found = sys.argv[7] == "true"
kiro_chat_command_available = sys.argv[8] == "true"
stdout_size = int(sys.argv[9])
stderr_size = int(sys.argv[10])
instruction = sys.argv[11]
design_output_arg = sys.argv[12]
design_output_path = Path(design_output_arg) if design_output_arg else None
design_output_exists = bool(design_output_path and design_output_path.is_file())
design_output_text = (
    design_output_path.read_text(encoding="utf-8", errors="replace")
    if design_output_exists
    else ""
)
required_sections = [
    "Design summary",
    "Implementation order",
    "Candidate files",
    "Verification plan",
    "Risks and claim boundary",
    "Cursor handoff prompt",
]
design_output_sha256 = (
    "sha256:" + hashlib.sha256(design_output_text.encode("utf-8")).hexdigest()
    if design_output_exists
    else None
)
prompt_text = prompt_file.read_text(encoding="utf-8")
required_model_line = f"model `{required_kiro_model}`"
required_confirmation_phrase = f"Confirm the prompt's {required_kiro_model} target"
prompt_validation = {
    "required_kiro_model": required_kiro_model,
    "model_line_verified": required_model_line in prompt_text,
    "model_target_verified": required_kiro_model in prompt_text,
    "design_only_boundary_verified": "Do not edit files" in prompt_text,
    "readiness_closure_claim_forbidden": "Do not claim readiness closure" in prompt_text,
}
wrapper_validation_passed = all(prompt_validation.values())

payload = {
    "schema_version": "kiro-design-worker-launch.v1",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "prompt_file": str(prompt_file),
    "kiro_cli_path": kiro_path,
    "kiro_cli_found": kiro_cli_found,
    "kiro_chat_command_available": kiro_chat_command_available,
    "kiro_chat_mode": "ask",
    "kiro_model_target": required_kiro_model,
    "model_target_source": "ai-worker-kiro.sh required_kiro_model",
    "kiro_chat_instruction_contains_model_target": required_kiro_model in instruction,
    "kiro_chat_instruction_requires_model_confirmation": required_confirmation_phrase
    in instruction,
    "wrapper_enforced_model_confirmation": required_confirmation_phrase in instruction,
    "model_target_verified_in_prompt": prompt_validation["model_target_verified"],
    "design_only_boundary_verified_in_prompt": prompt_validation["design_only_boundary_verified"],
    "readiness_closure_claim_forbidden_in_prompt": prompt_validation[
        "readiness_closure_claim_forbidden"
    ],
    "prompt_validation": prompt_validation,
    "wrapper_validation_mode": wrapper_validation_mode,
    "wrapper_validation_passed": wrapper_validation_passed,
    "wrapper_prelaunch_check_passed": wrapper_validation_passed,
    "equivalent_prompt_check_command": [
        "scripts/ai-worker-kiro.sh",
        "--check",
        str(prompt_file),
    ],
    "kiro_chat_launch_attempted": status is not None,
    "kiro_chat_exit_status": status,
    "kiro_chat_launch_passed": status == 0 if status is not None else False,
    "headless_stdout_capture": design_output_exists and stdout_size > 0,
    "headless_stdout_capture_wired": True,
    "stdout_bytes": stdout_size,
    "stderr_bytes": stderr_size,
    "design_output_path": str(design_output_path) if design_output_path else None,
    "design_output_bytes": len(design_output_text.encode("utf-8"))
    if design_output_exists
    else 0,
    "design_output_sha256": design_output_sha256,
    "design_output_contains_required_sections": (
        all(section in design_output_text for section in required_sections)
        if design_output_exists
        else False
    ),
    "codex_consumable_design_output": design_output_exists and stdout_size > 0,
    "output_capture_boundary": (
        "The wrapper captured Kiro stdout into a design output file for Codex review."
        if design_output_exists and stdout_size > 0
        else (
            "The wrapper is wired to capture Kiro stdout, but this Kiro chat "
            "launch did not emit a machine-readable design brief on stdout. "
            "Treat this receipt as launch evidence only, not as proof that "
            "Kiro produced or Codex consumed a design."
        )
    ),
    "claim_boundary": (
        f"This receipt verifies prompt-file based Kiro invocation targeting {required_kiro_model} "
        "with design-only/no-edit and no-readiness-closure prompt boundaries. It does not "
        "claim readiness closure, file edits, or model credential validity. "
        + (
            "It includes a captured design-output file because stdout was non-empty."
            if design_output_exists and stdout_size > 0
            else "It does not include captured design content for this launch."
        )
    ),
}
launch_receipt.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

echo "kiro worker: wrapper prelaunch validation passed for ${required_kiro_model}"

if ! command -v kiro >/dev/null 2>&1; then
  write_launch_receipt "null" "" "false" "false" "0" "0" ""
  echo "kiro worker: kiro CLI not found; validation receipt: $launch_receipt" >&2
  exit 2
fi

kiro_path="$(command -v kiro)"
if ! kiro chat --help >/dev/null 2>&1; then
  write_launch_receipt "null" "$kiro_path" "true" "false" "0" "0" ""
  echo "kiro worker: kiro chat command unavailable; validation receipt: $launch_receipt" >&2
  exit 2
fi

set +e
kiro chat --mode ask --reuse-window --add-file "$prompt_file" "$instruction" >/tmp/kiro-worker-stdout.$$ 2>/tmp/kiro-worker-stderr.$$
status="$?"
set -e

stdout_size="$(wc -c <"/tmp/kiro-worker-stdout.$$" 2>/dev/null || echo 0)"
stderr_size="$(wc -c <"/tmp/kiro-worker-stderr.$$" 2>/dev/null || echo 0)"
case "$launch_receipt" in
  *.kiro-launch.json)
    design_output="${launch_receipt%.kiro-launch.json}.kiro-design.md"
    ;;
  *.json)
    design_output="${launch_receipt%.json}.design.md"
    ;;
  *)
    design_output="${launch_receipt}.design.md"
    ;;
esac
captured_design_output=""
if [ "$stdout_size" -gt 0 ]; then
  cp "/tmp/kiro-worker-stdout.$$" "$design_output"
  captured_design_output="$design_output"
fi
rm -f "/tmp/kiro-worker-stdout.$$" "/tmp/kiro-worker-stderr.$$"
write_launch_receipt "$status" "$kiro_path" "true" "true" "$stdout_size" "$stderr_size" "$captured_design_output"

if [ "$status" -ne 0 ]; then
  echo "kiro worker: kiro chat failed with exit status $status; launch receipt: $launch_receipt" >&2
  exit "$status"
fi

echo "kiro worker: launched ${required_kiro_model} design prompt via kiro chat"
echo "kiro worker: launch receipt: $launch_receipt"
if [ -n "$captured_design_output" ]; then
  echo "kiro worker: captured design output: $captured_design_output"
fi
echo "kiro worker: stdout_bytes=${stdout_size} stderr_bytes=${stderr_size} headless_stdout_capture=$([ -n "$captured_design_output" ] && echo true || echo false)"
