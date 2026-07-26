#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <directory-containing-five-pinned-external-assets>" >&2
  exit 2
fi

repo_root="$(git rev-parse --show-toplevel)"
git_common_dir="$(git -C "$repo_root" rev-parse --path-format=absolute --git-common-dir)"
git_common_root="$(dirname "$git_common_dir")"
asset_dir="$(realpath "$1")"
output_dir="$repo_root/artifacts/vv/opensees_calculix_clean_runner"
runner_context="$repo_root/benchmarks/clean-runners/opensees-calculix"
image_tag="structural-analysis-external-vv-clean-runner:20260722"

if [[ ! -d "$asset_dir" ]]; then
  echo "asset directory does not exist: $asset_dir" >&2
  exit 2
fi

case "$asset_dir/" in
  "$git_common_root/"*|"$repo_root/"*)
    echo "external solver assets must remain outside the repository: $asset_dir" >&2
    exit 2
    ;;
esac

mkdir -p "$output_dir"
docker build --provenance=false --tag "$image_tag" "$runner_context"
image_id="$(docker image inspect "$image_tag" --format '{{.Id}}')"

mount_args=(
  --mount "type=bind,src=$git_common_root,dst=$git_common_root,readonly"
  --mount "type=bind,src=$asset_dir,dst=/assets,readonly"
  --mount "type=bind,src=$output_dir,dst=$output_dir"
)

case "$repo_root/" in
  "$git_common_root/"*) ;;
  *)
    mount_args+=(--mount "type=bind,src=$repo_root,dst=$repo_root,readonly")
    ;;
esac

docker run \
  --rm \
  --network none \
  --read-only \
  --user "$(id -u):$(id -g)" \
  --tmpfs /tmp:rw,exec,nosuid,size=1073741824 \
  "${mount_args[@]}" \
  "$image_tag" \
  --repo-root "$repo_root" \
  --asset-dir /assets \
  --output-dir "$output_dir" \
  --derived-image-id "$image_id"
