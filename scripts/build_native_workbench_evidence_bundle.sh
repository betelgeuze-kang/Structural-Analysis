#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

if [[ "$#" -eq 1 && "$1" == "--check" ]]; then
  exec cargo run --quiet --locked --manifest-path "$repository_root/native/Cargo.toml" \
    -p structural-evidence -- check --root "$repository_root"
fi

if [[ "$#" -ne 0 ]]; then
  echo "usage: $0 [--check]" >&2
  exit 2
fi

generated_at="$(git -C "$repository_root" show -s --format=%cI HEAD)"
if [[ -z "$generated_at" ]]; then
  echo "source commit timestamp could not be resolved" >&2
  exit 1
fi

exec cargo run --quiet --locked --manifest-path "$repository_root/native/Cargo.toml" \
  -p structural-evidence -- build \
  --root "$repository_root" \
  --out public/evidence \
  --generated-at "$generated_at"
