#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 --bundle DIR --release-id ID --package-version VERSION --backend cpu-only --linkage shared|static --source-sha256 sha256:HEX --installed-backend-receipt FILE --receipt FILE" >&2
}

bundle=""
release_id=""
package_version=""
backend=""
linkage=""
source_sha256=""
installed_backend_receipt=""
receipt=""
while (($# > 0)); do
  if (($# < 2)); then
    usage
    exit 2
  fi
  case "$1" in
    --bundle) bundle="$2" ;;
    --release-id) release_id="$2" ;;
    --package-version) package_version="$2" ;;
    --backend) backend="$2" ;;
    --linkage) linkage="$2" ;;
    --source-sha256) source_sha256="$2" ;;
    --installed-backend-receipt) installed_backend_receipt="$2" ;;
    --receipt) receipt="$2" ;;
    *) usage; exit 2 ;;
  esac
  shift 2
done

if [[ ! -d "$bundle" || -L "$bundle" || -z "$release_id" || -z "$package_version" ]]; then
  usage
  exit 2
fi
if [[ "$backend" != "cpu-only" || ("$linkage" != "shared" && "$linkage" != "static") ]]; then
  echo "hosted distribution E2E accepts only CPU-only static/shared bundles" >&2
  exit 2
fi
if [[ ! "$source_sha256" =~ ^sha256:[0-9a-f]{64}$ || -z "$receipt" || -z "$installed_backend_receipt" ]]; then
  usage
  exit 2
fi
receipt_parent="$(dirname "$receipt")"
backend_receipt_parent="$(dirname "$installed_backend_receipt")"
if [[ ! -d "$receipt_parent" || -L "$receipt_parent" || -e "$receipt" || -L "$receipt" \
  || ! -d "$backend_receipt_parent" || -L "$backend_receipt_parent" \
  || -e "$installed_backend_receipt" || -L "$installed_backend_receipt" ]]; then
  echo "receipt parent must be real and receipt output must not exist" >&2
  exit 1
fi
receipt="$(cd "$receipt_parent" && pwd -P)/$(basename "$receipt")"
installed_backend_receipt="$(cd "$backend_receipt_parent" && pwd -P)/$(basename "$installed_backend_receipt")"

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
bundle="$(cd "$bundle" && pwd -P)"
installer="$bundle/payload/bin/structural-installer"
if [[ ! -x "$installer" ]]; then
  echo "bundle does not contain structural-installer" >&2
  exit 1
fi

e2e_root="$(mktemp -d "${TMPDIR:-/tmp}/structural-native-installed-e2e.XXXXXX")"
cleanup() {
  if [[ -n "$e2e_root" && -d "$e2e_root" ]]; then
    rm -rf -- "$e2e_root"
  fi
}
trap cleanup EXIT
empty_path="$e2e_root/empty-path"
install_root="$e2e_root/install"
mkdir "$empty_path"

"$installer" bundle-verify --bundle "$bundle" > "$e2e_root/bundle-verify.json"
"$installer" install --bundle "$bundle" --root "$install_root" > "$e2e_root/install.json"
active="$install_root/releases/$release_id/payload"
for executable in structural-cli structural-installer structural-workbench; do
  test -x "$active/bin/$executable"
  env -i PATH="$empty_path" "$active/bin/$executable" --version > "$e2e_root/$executable-version.json"
done

if [[ "$linkage" == "shared" ]]; then
  readelf -d "$active/bin/structural-cli" | grep -Fq 'ORIGIN/../lib'
  ldd "$active/bin/structural-cli" | grep -Fq 'libstructural_c_abi_v1.so'
fi
if ldd "$active/bin/structural-cli" | grep -Eiq 'python|node|hip|hsa|rocm'; then
  echo "CPU-only installed CLI has a forbidden runtime dependency" >&2
  exit 1
fi
mapfile -t exported_symbols < <(nm -D --defined-only "$active/lib/libstructural_c_abi_v1.so" 2>/dev/null | awk '{print $3}')
if [[ "$linkage" == "shared" && "${exported_symbols[*]}" != "sa_get_api_v1" ]]; then
  echo "installed shared product library has unexpected ABI symbols: ${exported_symbols[*]}" >&2
  exit 1
fi

model="$repository_root/native/tests/fixtures/model_ir_adapter/fixed_guided_frame3d_x.json"
request="$repository_root/native/tests/fixtures/model_ir_adapter/fixed_guided_ndtha_request.json"
external="$repository_root/native/tests/fixtures/external_comparison/reference_oracle_ndtha_v1.json"
source_artifact="$repository_root/native/tests/fixtures/solver_cpu/nonlinear_ndtha_one_story_elastic_python_c1.json"
env -i PATH="$empty_path" "$active/bin/structural-cli" model validate "$model" \
  --require-analysis-ready > "$e2e_root/model-validation.json"

restarted="$e2e_root/workbench-restarted"
direct="$e2e_root/workbench-direct"
env -i PATH="$empty_path" "$active/bin/structural-workbench" import "$model" "$request" \
  --external-result "$external" --source-artifact "$source_artifact" \
  --workspace "$restarted" > "$e2e_root/import.json"
env -i PATH="$empty_path" "$active/bin/structural-workbench" validate \
  --workspace "$restarted" > "$e2e_root/validate.json"
env -i PATH="$empty_path" "$active/bin/structural-workbench" run \
  --workspace "$restarted" --step-budget 1 > "$e2e_root/run.json"
env -i PATH="$empty_path" "$active/bin/structural-workbench" resume \
  --workspace "$restarted" > "$e2e_root/resume.json"
env -i PATH="$empty_path" "$active/bin/structural-workbench" compare \
  --workspace "$restarted" --require-pass > "$e2e_root/compare.json"
env -i PATH="$empty_path" "$active/bin/structural-workbench" report \
  --workspace "$restarted" > "$e2e_root/report.json"
grep -Fq '"stage":"reported"' "$e2e_root/report.json"

env -i PATH="$empty_path" "$active/bin/structural-workbench" workflow "$model" "$request" \
  --external-result "$external" --source-artifact "$source_artifact" \
  --workspace "$direct" --step-budget 1 > "$e2e_root/workflow.json"
grep -Fq '"stage":"reported"' "$e2e_root/workflow.json"
diff -r "$restarted" "$direct" > "$e2e_root/workbench-diff.txt"

consumer_build="$e2e_root/package-consumer"
cmake -S "$repository_root/native/cpp/tests/package_consumer" -B "$consumer_build" \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="$active" > "$e2e_root/consumer-configure.txt"
cmake --build "$consumer_build" --parallel 2 > "$e2e_root/consumer-build.txt"
env -i PATH="$empty_path" "$consumer_build/structural_native_package_consumer"

backend_consumer_build="$e2e_root/backend-package-consumer"
cmake -S "$repository_root/native/cpp/tests/package_backend_consumer" \
  -B "$backend_consumer_build" -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_PREFIX_PATH="$active" > "$e2e_root/backend-consumer-configure.txt"
cmake --build "$backend_consumer_build" --parallel 2 \
  > "$e2e_root/backend-consumer-build.txt"
env -i PATH="$empty_path" \
  "$backend_consumer_build/structural_native_backend_package_consumer" cpu \
  > "$e2e_root/installed-backend-receipt.json"
grep -Fq '"backend_profile":"cpu_only"' "$e2e_root/installed-backend-receipt.json"

updated_release="$release_id-update"
updated_bundle="$e2e_root/bundle-update"
"$installer" bundle-create --payload "$bundle/payload" --output "$updated_bundle" \
  --release-id "$updated_release" --package-version "$package_version" \
  --backend "$backend" --linkage "$linkage" --source-sha256 "$source_sha256" \
  > "$e2e_root/bundle-update.json"
"$installer" update --bundle "$updated_bundle" --root "$install_root" \
  > "$e2e_root/update.json"
grep -Fq "\"current_release\":\"$updated_release\"" "$e2e_root/update.json"
"$installer" rollback --root "$install_root" > "$e2e_root/rollback.json"
grep -Fq "\"current_release\":\"$release_id\"" "$e2e_root/rollback.json"
"$installer" status --root "$install_root" > "$e2e_root/status.json"

manifest_hash="$(sha256sum "$bundle/structural-distribution.json" | awk '{print $1}')"
result_hash="$(sha256sum "$direct/04-resume/result-ir.json" | awk '{print $1}')"
report_hash="$(sha256sum "$direct/06-report/report.pdf" | awk '{print $1}')"
installed_backend_hash="$(sha256sum "$e2e_root/installed-backend-receipt.json" | awk '{print $1}')"
temporary_receipt="$e2e_root/distribution-receipt.json"
printf '%s\n' "{\"schema_version\":\"structural-native-distribution-e2e.v1\",\"backend_profile\":\"cpu_only\",\"linkage\":\"$linkage\",\"release_id\":\"$release_id\",\"source_sha256\":\"$source_sha256\",\"bundle_manifest_sha256\":\"sha256:$manifest_hash\",\"installed_backend_receipt_sha256\":\"sha256:$installed_backend_hash\",\"c2_receipt_sha256\":null,\"approved_device_runner\":false,\"single_product_abi\":true,\"python_lookup_count\":0,\"node_lookup_count\":0,\"install_passed\":true,\"update_passed\":true,\"rollback_passed\":true,\"package_consumer_passed\":true,\"workbench_restart_passed\":true,\"workbench_direct_parity_passed\":true,\"result_ir_sha256\":\"sha256:$result_hash\",\"report_pdf_sha256\":\"sha256:$report_hash\",\"fallback_count\":0,\"authority\":\"hosted_cpu_c5\"}" > "$temporary_receipt"
backend_output_stage="$(mktemp "$backend_receipt_parent/.structural-installed-backend.XXXXXX")"
receipt_output_stage="$(mktemp "$receipt_parent/.structural-distribution-receipt.XXXXXX")"
cp "$e2e_root/installed-backend-receipt.json" "$backend_output_stage"
cp "$temporary_receipt" "$receipt_output_stage"
chmod 0444 "$backend_output_stage" "$receipt_output_stage"
mv "$backend_output_stage" "$installed_backend_receipt"
mv "$receipt_output_stage" "$receipt"
