#!/usr/bin/env bash
set -euo pipefail

# Static command-string guard.
# This catches forbidden strings in wrapper/configured commands before launch.
# It is NOT a sandbox and cannot inspect commands executed inside Cursor/OpenCode/Codex agents.

cmd="${*:-}"
for pat in \
  "git push" \
  "git merge" \
  "git reset --hard" \
  "git clean -fd" \
  "npm publish" \
  "pnpm publish" \
  "yarn publish" \
  "docker push" \
  "kubectl apply" \
  "terraform apply" \
  "vercel deploy --prod" \
  "railway up" \
  "fly deploy" \
  "stripe refunds create" \
  "prisma migrate deploy" \
  "supabase db push"; do
  if printf '%s' "$cmd" | grep -qi "$pat"; then
    echo "Blocked dangerous command pattern in wrapper/config command: $pat" >&2
    exit 2
  fi
done
