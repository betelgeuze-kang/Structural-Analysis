#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
catalog="$repository_root/native/catalog/benchmark-catalog-v2.json"

if [[ "$#" -eq 1 && "$1" == "--check" ]]; then
  exec cargo run --quiet --locked --manifest-path "$repository_root/native/Cargo.toml" \
    -p structural-catalog -- check --root "$repository_root" --catalog "$catalog"
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
  -p structural-catalog -- build \
  --root "$repository_root" \
  --out "$catalog" \
  --generated-at "$generated_at"
