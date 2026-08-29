#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <directory-containing-five-pinned-external-assets>" >&2
  exit 2
fi

repo_root="$(git rev-parse --show-toplevel)"
git_common_dir="$(git -C "$repo_root" rev-parse --path-format=absolute --git-common-dir)"
git_repository_root="$(dirname "$git_common_dir")"
asset_dir="$(realpath "$1")"
output_dir="$repo_root/artifacts/vv/opensees_calculix_clean_runner"
host_code_reference="$output_dir/host_external_code_to_code_current_source_replay.json"
host_modal_reference="$output_dir/host_external_modal_buckling_current_source_replay.json"
runner_context="$repo_root/benchmarks/clean-runners/opensees-calculix"
image_tag="structural-analysis-external-vv-clean-runner:20260722"

if [[ ! -d "$asset_dir" ]]; then
  echo "asset directory does not exist: $asset_dir" >&2
  exit 2
fi

case "$asset_dir/" in
  "$git_repository_root/"*|"$repo_root/"*)
    echo "external solver assets must remain outside the repository: $asset_dir" >&2
    exit 2
    ;;
esac

mkdir -p "$output_dir"
cp \
  "$repo_root/implementation/phase1/release_evidence/productization/external_code_to_code_technical_execution_receipt.json" \
  "$host_code_reference"
cp \
  "$repo_root/implementation/phase1/release_evidence/productization/external_modal_buckling_technical_execution_receipt.json" \
  "$host_modal_reference"
python3 "$repo_root/scripts/run_external_code_to_code_technical_receipt.py" \
  --out "$host_code_reference" \
  --refresh-product-replay \
  --reuse-reason \
  "Exact-current host replay for clean-runner parity; retained external values receive no freshness credit."
python3 "$repo_root/scripts/run_external_modal_buckling_technical_receipt.py" \
  --out "$host_modal_reference" \
  --refresh-product-replay \
  --reuse-reason \
  "Exact-current host replay for clean-runner parity; retained external values receive no freshness credit."
python3 "$repo_root/scripts/run_external_code_to_code_technical_receipt.py" \
  --out "$host_code_reference" \
  --check
python3 "$repo_root/scripts/run_external_modal_buckling_technical_receipt.py" \
  --out "$host_modal_reference" \
  --check
docker build --provenance=false --tag "$image_tag" "$runner_context"
image_id="$(docker image inspect "$image_tag" --format '{{.Id}}')"

mount_args=(
  --mount "type=bind,src=$asset_dir,dst=/assets,readonly"
  --mount "type=bind,src=$output_dir,dst=$output_dir"
)

mount_args+=(--mount "type=bind,src=$repo_root,dst=$repo_root,readonly")
if [[ "$repo_root" != "$git_repository_root" ]]; then
  mount_args+=(--mount "type=bind,src=$git_common_dir,dst=$git_common_dir,readonly")
fi

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
  --host-code-reference "$host_code_reference" \
  --host-modal-reference "$host_modal_reference" \
  --derived-image-id "$image_id"

# Retain the exact-current host replays named by the summary. They are
# non-fresh parity inputs, not external-runtime evidence, but downstream
# isolated validation must be able to resolve and hash their recorded paths.
