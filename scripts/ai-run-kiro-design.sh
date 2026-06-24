#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

usage() {
  echo "usage: $0 <kiro-design-prompt-file> [launch-receipt-json]" >&2
}

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  usage
  exit 2
fi

prompt_file="$1"
launch_receipt="${2:-}"

if [ -n "$launch_receipt" ]; then
  ./scripts/ai-worker-kiro.sh --check "$prompt_file"
  exec ./scripts/ai-worker-kiro.sh "$prompt_file" "$launch_receipt"
fi

./scripts/ai-worker-kiro.sh --check "$prompt_file"
exec ./scripts/ai-worker-kiro.sh "$prompt_file"
