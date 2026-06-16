#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PATH="${HOME}/.local/bin:${PATH}"
if command -v npm >/dev/null 2>&1; then
  npm_prefix="$(npm prefix -g 2>/dev/null || true)"
  if [ -n "$npm_prefix" ]; then
    export PATH="${npm_prefix}/bin:${PATH}"
  fi
fi

pass=0
warn=0
fail=0

ok() { echo "  OK   $*"; pass=$((pass + 1)); }
note() { echo "  WARN $*"; warn=$((warn + 1)); }
bad() { echo "  FAIL $*"; fail=$((fail + 1)); }

echo "=== Codex goal + Cursor/OpenCode worker preflight ==="
echo

echo "[1] Codex project files"
test -f AGENTS.md && ok "AGENTS.md present" || bad "AGENTS.md missing"
test -f .codex/config.toml && ok ".codex/config.toml present" || note ".codex/config.toml missing"
test -f docs/ai/ORCHESTRATION.md && ok "orchestration guide present" || bad "orchestration guide missing"
test -f docs/ai/prompts/codex_goal_start.md && ok "Codex goal start prompt present" || bad "Codex goal start prompt missing"
test -f docs/ai/prompts/cursor_worker_slice.md && ok "Cursor worker prompt template present" || bad "Cursor worker prompt template missing"
test -f docs/ai/prompts/opencode_worker_slice.md && ok "OpenCode worker prompt template present" || bad "OpenCode worker prompt template missing"
test -f opencode.json && ok "opencode.json present" || note "opencode.json missing"

echo
echo "[2] Cursor Agent"
if ! command -v cursor-agent >/dev/null 2>&1 && [ -x "${HOME}/.local/bin/cursor-agent" ]; then
  export PATH="${HOME}/.local/bin:${PATH}"
fi
if command -v cursor-agent >/dev/null 2>&1; then
  ok "cursor-agent found: $(command -v cursor-agent)"
elif command -v cursor >/dev/null 2>&1; then
  ok "cursor found: $(command -v cursor)"
else
  note "neither cursor-agent nor cursor found"
fi

echo
echo "[3] OpenCode CLI"
if command -v opencode >/dev/null 2>&1; then
  ok "opencode found: $(command -v opencode)"
  ok "opencode version: $(opencode --version)"
else
  note "opencode not found; OpenCode worker wrapper will fail until installed"
fi

echo
echo "[4] Worker wrappers"
if bash -n scripts/ai-worker-cursor.sh scripts/ai-worker-opencode.sh scripts/ai-dangerous-command-check.sh scripts/ai-verify.sh; then
  ok "worker shell syntax ok"
else
  bad "worker shell syntax failed"
fi

if grep -q -- '--model "$CURSOR_AGENT_MODEL"' scripts/ai-worker-cursor.sh; then
  ok "cursor worker uses configured model"
else
  bad "cursor worker model wiring missing"
fi

if grep -q -- '--file "$prompt_file"' scripts/ai-worker-opencode.sh; then
  ok "opencode worker passes prompt by file"
else
  bad "opencode worker does not appear to pass prompt by file"
fi

if grep -q -- 'validate-ai-worker-output.mjs' scripts/ai-worker-cursor.sh \
  && grep -q -- 'validate-ai-worker-output.mjs' scripts/ai-worker-opencode.sh; then
  ok "worker wrappers validate output before printing summaries"
else
  bad "worker output validation wiring missing"
fi

echo
echo "[5] Local verify"
if ./scripts/ai-verify.sh >/dev/null 2>&1; then
  ok "ai-verify.sh passed"
else
  bad "ai-verify.sh failed"
fi

echo
echo "=== Summary: ${pass} ok, ${warn} warn, ${fail} fail ==="
if [ "$fail" -gt 0 ]; then
  exit 1
fi
