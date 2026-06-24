#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "==> shell syntax"
bash -n scripts/ai-dangerous-command-check.sh \
  scripts/ai-run-kiro-design.sh \
  scripts/ai-worker-kiro.sh \
  scripts/ai-worker-cursor.sh \
  scripts/ai-worker-cursor-host-bridge.sh \
  scripts/ai-worker-opencode.sh \
  scripts/ai-preflight.sh \
  scripts/ai-verify.sh

echo "==> json"
python3 -m json.tool package.json >/dev/null
python3 -m json.tool opencode.json >/dev/null
python3 -m json.tool .betelgeuze/verification.json >/dev/null

echo "==> required files"
test -f AGENTS.md
test -f docs/ai/ORCHESTRATION.md
test -f docs/ai/prompts/codex_goal_start.md
test -f docs/ai/prompts/kiro_design_slice.md
test -f docs/ai/prompts/cursor_worker_slice.md
test -f docs/ai/prompts/opencode_worker_slice.md
test -f docs/ai/checklists/ai-agent-security.md
test -f docs/ai/checklists/pre-review.md
test -f docs/ai/checklists/pre-merge.md
test -f docs/ai/goal/GOAL.md
test -f opencode.json
test -f scripts/validate-ai-worker-output.mjs
test -x scripts/ai-run-kiro-design.sh
test -x scripts/ai-worker-kiro.sh
test -x scripts/ai-worker-cursor.sh
test -x scripts/ai-worker-cursor-host-bridge.sh
test -x scripts/ai-worker-opencode.sh
test -x scripts/ai-preflight.sh
test -x scripts/ai-verify.sh
./scripts/ai-worker-kiro.sh --check docs/ai/prompts/kiro_design_slice.md >/dev/null
grep -q -- 'ai-worker-kiro.sh --check "$prompt_file"' scripts/ai-run-kiro-design.sh
grep -q -- 'ai-worker-kiro.sh "$prompt_file"' scripts/ai-run-kiro-design.sh
grep -q -- 'wrapper_prelaunch_check_passed' scripts/ai-worker-kiro.sh
grep -q -- 'automatic_prelaunch_before_kiro_chat' scripts/ai-worker-kiro.sh
grep -q -- 'wrapper_enforced_model_confirmation' scripts/ai-worker-kiro.sh
grep -q -- "Confirm the prompt's \${required_kiro_model} target" scripts/ai-worker-kiro.sh
grep -q -- 'headless_stdout_capture_wired' scripts/ai-worker-kiro.sh
grep -q -- 'design_output_path' scripts/ai-worker-kiro.sh
grep -q -- 'codex_consumable_design_output' scripts/ai-worker-kiro.sh

echo "==> worker output validator"
node --test tests/ai-worker-output-validator.test.mjs

echo "==> package scripts"
node -e "const p=require('./package.json'); for (const s of ['ai:kiro-design','ai:preflight','ai:verify','ai:validate-worker-output']) { if (!p.scripts || !p.scripts[s]) throw new Error('missing script '+s); }"

echo "==> worker cli availability"
if ! command -v cursor-agent >/dev/null 2>&1 && [ -x "${HOME}/.local/bin/cursor-agent" ]; then
  export PATH="${HOME}/.local/bin:${PATH}"
fi
if command -v cursor-agent >/dev/null 2>&1; then
  cursor_status="cursor-agent"
elif command -v cursor >/dev/null 2>&1; then
  cursor_status="cursor"
else
  cursor_status="missing"
fi
echo "cursor worker cli: ${cursor_status}"

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
  echo "opencode worker cli: missing (worker disabled until installed)"
fi

if [ "${AI_VERIFY_FULL:-0}" = "1" ]; then
  echo "==> full project checks"
  npm run build
  pytest
  python3 -m compileall .
fi

echo "verify ok"
