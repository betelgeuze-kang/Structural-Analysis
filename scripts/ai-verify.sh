#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "==> shell syntax"
bash -n scripts/ai-dangerous-command-check.sh \
  scripts/ai-worker-cursor.sh \
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
test -f docs/ai/prompts/cursor_worker_slice.md
test -f docs/ai/prompts/opencode_worker_slice.md
test -f docs/ai/checklists/ai-agent-security.md
test -f docs/ai/checklists/pre-review.md
test -f docs/ai/checklists/pre-merge.md
test -f docs/ai/goal/GOAL.md
test -f opencode.json
test -f scripts/validate-ai-worker-output.mjs
test -x scripts/ai-worker-cursor.sh
test -x scripts/ai-worker-opencode.sh
test -x scripts/ai-preflight.sh
test -x scripts/ai-verify.sh

echo "==> worker output validator"
node --test tests/ai-worker-output-validator.test.mjs

echo "==> package scripts"
node -e "const p=require('./package.json'); for (const s of ['ai:preflight','ai:verify','ai:validate-worker-output']) { if (!p.scripts || !p.scripts[s]) throw new Error('missing script '+s); }"

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
