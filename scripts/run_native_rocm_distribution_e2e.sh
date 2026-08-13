#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 --bundle DIR --release-id ID --package-version VERSION --source-sha256 sha256:HEX --c2-receipt FILE --installed-backend-receipt FILE --receipt FILE" >&2
}

bundle=""
release_id=""
package_version=""
source_sha256=""
c2_receipt=""
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
    --source-sha256) source_sha256="$2" ;;
    --c2-receipt) c2_receipt="$2" ;;
    --installed-backend-receipt) installed_backend_receipt="$2" ;;
    --receipt) receipt="$2" ;;
    *) usage; exit 2 ;;
  esac
  shift 2
done

if [[ "${GITHUB_ACTIONS:-}" != "true" || "${RUNNER_ENVIRONMENT:-}" != "self-hosted" \
  || "${NATIVE_HIP_APPROVAL_ENVIRONMENT:-}" != "native-hip-approved" ]]; then
  echo "authoritative ROCm distribution E2E requires the approved self-hosted GitHub lane" >&2
  exit 1
fi
test -r /dev/kfd
test -d /dev/dri
if [[ ! -d "$bundle" || -L "$bundle" || ! -f "$c2_receipt" || -L "$c2_receipt" \
  || -z "$release_id" || -z "$package_version" || -z "$installed_backend_receipt" \
  || -z "$receipt" || ! "$source_sha256" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  usage
  exit 2
fi
for output in "$installed_backend_receipt" "$receipt"; do
  parent="$(dirname "$output")"
  if [[ ! -d "$parent" || -L "$parent" || -e "$output" || -L "$output" ]]; then
    echo "receipt parents must be real and receipt outputs must not exist" >&2
    exit 1
  fi
done

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
bundle="$(cd "$bundle" && pwd -P)"
c2_receipt="$(cd "$(dirname "$c2_receipt")" && pwd -P)/$(basename "$c2_receipt")"
installed_backend_parent="$(cd "$(dirname "$installed_backend_receipt")" && pwd -P)"
installed_backend_receipt="$installed_backend_parent/$(basename "$installed_backend_receipt")"
receipt_parent="$(cd "$(dirname "$receipt")" && pwd -P)"
receipt="$receipt_parent/$(basename "$receipt")"
installer="$bundle/payload/bin/structural-installer"
test -x "$installer"

e2e_root="$(mktemp -d "${TMPDIR:-/tmp}/structural-native-rocm-installed-e2e.XXXXXX")"
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
for executable in structural-cli structural-catalog structural-evidence structural-installer structural-workbench; do
  env -i PATH="$empty_path" "$active/bin/$executable" --version \
    > "$e2e_root/$executable-version.json"
done
localized_report_share="$active/share/structural-report"
localized_report_font="$localized_report_share/StructuralReportKoreanSubset.ttf"
localized_report_font_license="$localized_report_share/OFL-1.1.txt"
localized_report_font_provenance="$localized_report_share/StructuralReportKoreanSubset.provenance.json"
for asset in \
  "$localized_report_font" \
  "$localized_report_font_license" \
  "$localized_report_font_provenance" \
  "$localized_report_share/README.md"; do
  if [[ ! -f "$asset" || -L "$asset" ]]; then
    echo "installed localized-report asset is missing or is not a regular file: $asset" >&2
    exit 1
  fi
done
localized_report_font_hash="$(sha256sum "$localized_report_font" | awk '{print $1}')"
localized_report_font_license_hash="$(sha256sum "$localized_report_font_license" | awk '{print $1}')"
localized_report_font_provenance_hash="$(sha256sum "$localized_report_font_provenance" | awk '{print $1}')"
readelf -d "$active/bin/structural-cli" | grep -Fq 'ORIGIN/../lib'
ldd "$active/bin/structural-cli" | grep -Fq 'libstructural_c_abi_v1.so'
if ldd "$active/bin/structural-cli" | grep -Eiq 'python|node'; then
  echo "installed ROCm CLI has a forbidden Python or Node runtime dependency" >&2
  exit 1
fi
if ldd "$active/lib/libstructural_c_abi_v1.so" | grep -Fq 'not found'; then
  echo "ROCm product library has an unresolved runtime dependency" >&2
  exit 1
fi
if ! ldd "$active/lib/libstructural_c_abi_v1.so" | grep -Eiq 'hip|hsa|rocm'; then
  echo "ROCm product package is not linked to a ROCm/HIP runtime" >&2
  exit 1
fi
mapfile -t exported_symbols < <(nm -D --defined-only "$active/lib/libstructural_c_abi_v1.so" | awk '{print $3}')
if [[ "${exported_symbols[*]}" != "sa_get_api_v1" ]]; then
  echo "installed ROCm product library has unexpected ABI symbols: ${exported_symbols[*]}" >&2
  exit 1
fi

consumer_build="$e2e_root/package-consumer"
cmake -S "$repository_root/native/cpp/tests/package_consumer" -B "$consumer_build" \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="$active" > "$e2e_root/consumer-configure.txt"
cmake --build "$consumer_build" --parallel 2 > "$e2e_root/consumer-build.txt"
env -i PATH="$empty_path" "$consumer_build/structural_native_package_consumer"

backend_build="$e2e_root/backend-package-consumer"
cmake -S "$repository_root/native/cpp/tests/package_backend_consumer" -B "$backend_build" \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="$active" \
  > "$e2e_root/backend-consumer-configure.txt"
cmake --build "$backend_build" --parallel 2 > "$e2e_root/backend-consumer-build.txt"
env -i PATH="$empty_path" "$backend_build/structural_native_backend_package_consumer" hip \
  > "$e2e_root/installed-backend-receipt.json"
grep -Fq '"backend_profile":"rocm"' "$e2e_root/installed-backend-receipt.json"
grep -Fq '"operator_device_resident":true' "$e2e_root/installed-backend-receipt.json"

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
for stage in validate run resume compare report; do
  stage_arguments=("$stage" --workspace "$restarted")
  if [[ "$stage" == "run" ]]; then
    stage_arguments+=(--step-budget 1)
  elif [[ "$stage" == "compare" ]]; then
    stage_arguments+=(--require-pass)
  fi
  env -i PATH="$empty_path" "$active/bin/structural-workbench" "${stage_arguments[@]}" \
    > "$e2e_root/$stage.json"
done
grep -Fq '"stage":"reported"' "$e2e_root/report.json"
env -i PATH="$empty_path" "$active/bin/structural-workbench" workflow "$model" "$request" \
  --external-result "$external" --source-artifact "$source_artifact" \
  --workspace "$direct" --step-budget 1 > "$e2e_root/workflow.json"
diff -r "$restarted" "$direct" > "$e2e_root/workbench-diff.txt"

mgt_source="$repository_root/native/tests/fixtures/mgt_import/workbench_fixed_guided_frame3d_x.mgt"
mgt_request="$repository_root/native/tests/fixtures/mgt_import/workbench_fixed_guided_ndtha_request.json"
mgt_restarted="$e2e_root/mgt-workbench-restarted"
mgt_direct="$e2e_root/mgt-workbench-direct"
env -i PATH="$empty_path" "$active/bin/structural-workbench" import-mgt \
  "$mgt_source" "$mgt_request" --model-id workbench-mgt-fixed-guided-v1 \
  --external-result "$external" --source-artifact "$source_artifact" \
  --workspace "$mgt_restarted" > "$e2e_root/mgt-import.json"
for stage in validate run resume compare report; do
  stage_arguments=("$stage" --workspace "$mgt_restarted")
  if [[ "$stage" == "run" ]]; then
    stage_arguments+=(--step-budget 1)
  elif [[ "$stage" == "compare" ]]; then
    stage_arguments+=(--require-pass)
  fi
  env -i PATH="$empty_path" "$active/bin/structural-workbench" "${stage_arguments[@]}" \
    > "$e2e_root/mgt-$stage.json"
done
env -i PATH="$empty_path" "$active/bin/structural-workbench" workflow-mgt \
  "$mgt_source" "$mgt_request" --model-id workbench-mgt-fixed-guided-v1 \
  --external-result "$external" --source-artifact "$source_artifact" \
  --workspace "$mgt_direct" --step-budget 1 > "$e2e_root/mgt-workflow.json"
grep -Fq '"stage":"reported"' "$e2e_root/mgt-workflow.json"
diff -r "$mgt_restarted" "$mgt_direct" > "$e2e_root/mgt-workbench-diff.txt"

exercise_operator_surface() {
  local label="$1"
  local workspace="$2"
  env -i PATH="$empty_path" "$active/bin/structural-workbench" inspect \
    --workspace "$workspace" > "$e2e_root/$label-inspect-before-review.json"
  grep -Fq '"next_action":"review"' "$e2e_root/$label-inspect-before-review.json"
  env -i PATH="$empty_path" "$active/bin/structural-workbench" review \
    --workspace "$workspace" --decision review --reviewer native-c5-e2e \
    --comment 'Explicit C5 package handoff review; no engineering approval is inferred.' \
    > "$e2e_root/$label-review.json"
  env -i PATH="$empty_path" "$active/bin/structural-workbench" review-show \
    --workspace "$workspace" > "$e2e_root/$label-review-show.json"
  cmp "$e2e_root/$label-review.json" "$e2e_root/$label-review-show.json"
  env -i PATH="$empty_path" "$active/bin/structural-workbench" inspect \
    --workspace "$workspace" > "$e2e_root/$label-inspect-after-review.json"
  grep -Fq '"next_action":"export"' "$e2e_root/$label-inspect-after-review.json"
  env -i PATH="$empty_path" "$active/bin/structural-workbench" export \
    --workspace "$workspace" > "$e2e_root/$label-export.json"
  grep -Fq '"decision":"review"' "$e2e_root/$label-export.json"
}
exercise_operator_surface workbench "$direct"
exercise_operator_surface mgt-workbench "$mgt_direct"

exercise_localized_pdf_surface() {
  local workspace="$1"
  local workspace_before="$e2e_root/workbench-before-localized-pdf"
  cp -a -- "$workspace" "$workspace_before"
  for locale in en-US ko-KR; do
    local first="$e2e_root/localized-pdf-$locale-first"
    local second="$e2e_root/localized-pdf-$locale-second"
    local output_directory
    for output_directory in "$first" "$second"; do
      env -i PATH="$empty_path" "$active/bin/structural-workbench" report-export-pdf \
        --workspace "$workspace" --output-dir "$output_directory" --locale "$locale" \
        > "$output_directory.stdout.json"
      test -s "$output_directory/report.pdf"
      test -s "$output_directory/pdf-receipt.json"
      grep -Fq '"schema_version":"structural-native-localized-pdf-report-receipt.v2"' \
        "$output_directory/pdf-receipt.json"
      grep -Fq "\"locale\":\"$locale\"" "$output_directory/pdf-receipt.json"
      grep -Fq "\"content_hash\":\"sha256:$localized_report_font_hash\"" \
        "$output_directory/pdf-receipt.json"
      grep -Fq "\"content_hash\":\"sha256:$localized_report_font_license_hash\"" \
        "$output_directory/pdf-receipt.json"
      grep -Fq "\"content_hash\":\"sha256:$localized_report_font_provenance_hash\"" \
        "$output_directory/pdf-receipt.json"
      grep -Fq '"distribution_path":"share/structural-report/OFL-1.1.txt"' \
        "$output_directory/pdf-receipt.json"
      grep -Fq '"distribution_path":"share/structural-report/StructuralReportKoreanSubset.provenance.json"' \
        "$output_directory/pdf-receipt.json"
    done
    cmp "$first/report.pdf" "$second/report.pdf"
    cmp "$first/pdf-receipt.json" "$second/pdf-receipt.json"
  done
  if cmp -s "$e2e_root/localized-pdf-en-US-first/report.pdf" \
    "$e2e_root/localized-pdf-ko-KR-first/report.pdf"; then
    echo "installed localized PDF outputs must differ by locale" >&2
    exit 1
  fi
  diff -r "$workspace_before" "$workspace" > "$e2e_root/workbench-localized-pdf-diff.txt"
}
exercise_localized_pdf_surface "$direct"

catalog_source="$repository_root/native/catalog/benchmark-catalog-v2.json"
env -i PATH="$empty_path" "$active/bin/structural-catalog" check \
  --root "$repository_root" --catalog "$catalog_source" \
  > "$e2e_root/catalog-builder-check.json"
grep -Fq '"schema_version":"structural-native-benchmark-catalog-build-receipt.v1"' \
  "$e2e_root/catalog-builder-check.json"
grep -Fq '"action":"check"' "$e2e_root/catalog-builder-check.json"
generated_catalog="$e2e_root/generated-benchmark-catalog.json"
env -i PATH="$empty_path" "$active/bin/structural-catalog" build \
  --root "$repository_root" --out "$generated_catalog" \
  --generated-at 2026-08-13T00:00:00Z > "$e2e_root/catalog-builder-build.json"
grep -Fq '"action":"build"' "$e2e_root/catalog-builder-build.json"
test -f "$generated_catalog"

evidence_sources="$repository_root/native/tests/fixtures/evidence_builder_sources"
env -i PATH="$empty_path" "$active/bin/structural-evidence" check \
  --root "$evidence_sources" > "$e2e_root/evidence-builder-check.json"
grep -Fq '"schema_version":"structural-native-evidence-bundle-build-receipt.v1"' \
  "$e2e_root/evidence-builder-check.json"
grep -Fq '"action":"check"' "$e2e_root/evidence-builder-check.json"
evidence_bundle="$e2e_root/generated-evidence"
env -i PATH="$empty_path" "$active/bin/structural-evidence" build \
  --root "$evidence_sources" --out "$evidence_bundle" \
  --generated-at 2026-08-13T00:00:00Z > "$e2e_root/evidence-builder-build.json"
grep -Fq '"action":"build"' "$e2e_root/evidence-builder-build.json"
test -f "$evidence_bundle/manifest.json"
env -i PATH="$empty_path" "$active/bin/structural-workbench" catalog \
  --truth geometry_only --size large > "$e2e_root/workbench-catalog.json"
grep -Fq '"schema_version":"structural-native-benchmark-catalog-view.v1"' \
  "$e2e_root/workbench-catalog.json"
grep -Fq '"matched_case_count":4' "$e2e_root/workbench-catalog.json"
env -i PATH="$empty_path" "$active/bin/structural-workbench" evidence \
  --bundle "$evidence_bundle" --as-of-unix 1786579200 \
  > "$e2e_root/workbench-evidence.json"
grep -Fq '"schema_version":"structural-native-evidence-bundle-view.v1"' \
  "$e2e_root/workbench-evidence.json"
grep -Fq '"blocked_count":1' "$e2e_root/workbench-evidence.json"

updated_release="$release_id-update"
updated_bundle="$e2e_root/bundle-update"
"$installer" bundle-create --payload "$bundle/payload" --output "$updated_bundle" \
  --release-id "$updated_release" --package-version "$package_version" --backend rocm \
  --linkage shared --source-sha256 "$source_sha256" > "$e2e_root/bundle-update.json"
"$installer" update --bundle "$updated_bundle" --root "$install_root" > "$e2e_root/update.json"
grep -Fq "\"current_release\":\"$updated_release\"" "$e2e_root/update.json"
"$installer" rollback --root "$install_root" > "$e2e_root/rollback.json"
grep -Fq "\"current_release\":\"$release_id\"" "$e2e_root/rollback.json"

manifest_hash="$(sha256sum "$bundle/structural-distribution.json" | awk '{print $1}')"
installed_backend_hash="$(sha256sum "$e2e_root/installed-backend-receipt.json" | awk '{print $1}')"
c2_hash="$(sha256sum "$c2_receipt" | awk '{print $1}')"
result_hash="$(sha256sum "$direct/04-resume/result-ir.json" | awk '{print $1}')"
report_hash="$(sha256sum "$direct/06-report/report.pdf" | awk '{print $1}')"
mgt_source_hash="$(sha256sum "$mgt_direct/01-import/source.mgt" | awk '{print $1}')"
mgt_health_hash="$(sha256sum "$mgt_direct/01-import/import-health.json" | awk '{print $1}')"
mgt_result_hash="$(sha256sum "$mgt_direct/04-resume/result-ir.json" | awk '{print $1}')"
mgt_report_hash="$(sha256sum "$mgt_direct/06-report/report.pdf" | awk '{print $1}')"
workbench_review_hash="$(sha256sum "$direct/07-review/review.json" | awk '{print $1}')"
workbench_export_hash="$(sha256sum "$e2e_root/workbench-export.json" | awk '{print $1}')"
mgt_workbench_review_hash="$(sha256sum "$mgt_direct/07-review/review.json" | awk '{print $1}')"
mgt_workbench_export_hash="$(sha256sum "$e2e_root/mgt-workbench-export.json" | awk '{print $1}')"
workbench_catalog_hash="$(sha256sum "$e2e_root/workbench-catalog.json" | awk '{print $1}')"
workbench_evidence_hash="$(sha256sum "$e2e_root/workbench-evidence.json" | awk '{print $1}')"
catalog_builder_check_hash="$(sha256sum "$e2e_root/catalog-builder-check.json" | awk '{print $1}')"
catalog_builder_build_hash="$(sha256sum "$e2e_root/catalog-builder-build.json" | awk '{print $1}')"
catalog_builder_output_hash="$(sha256sum "$generated_catalog" | awk '{print $1}')"
evidence_builder_check_hash="$(sha256sum "$e2e_root/evidence-builder-check.json" | awk '{print $1}')"
evidence_builder_build_hash="$(sha256sum "$e2e_root/evidence-builder-build.json" | awk '{print $1}')"
evidence_builder_manifest_hash="$(sha256sum "$evidence_bundle/manifest.json" | awk '{print $1}')"
localized_pdf_en_us_hash="$(sha256sum "$e2e_root/localized-pdf-en-US-first/report.pdf" | awk '{print $1}')"
localized_pdf_ko_kr_hash="$(sha256sum "$e2e_root/localized-pdf-ko-KR-first/report.pdf" | awk '{print $1}')"
localized_pdf_en_us_receipt_hash="$(sha256sum "$e2e_root/localized-pdf-en-US-first/pdf-receipt.json" | awk '{print $1}')"
localized_pdf_ko_kr_receipt_hash="$(sha256sum "$e2e_root/localized-pdf-ko-KR-first/pdf-receipt.json" | awk '{print $1}')"
temporary_receipt="$e2e_root/distribution-receipt.json"
printf '%s\n' \
  "{\"schema_version\":\"structural-native-distribution-e2e.v7\",\"backend_profile\":\"rocm\",\"linkage\":\"shared\",\"release_id\":\"$release_id\",\"source_sha256\":\"$source_sha256\",\"bundle_manifest_sha256\":\"sha256:$manifest_hash\",\"installed_backend_receipt_sha256\":\"sha256:$installed_backend_hash\",\"c2_receipt_sha256\":\"sha256:$c2_hash\",\"approved_device_runner\":true,\"single_product_abi\":true,\"python_lookup_count\":0,\"node_lookup_count\":0,\"install_passed\":true,\"update_passed\":true,\"rollback_passed\":true,\"package_consumer_passed\":true,\"workbench_restart_passed\":true,\"workbench_direct_parity_passed\":true,\"mgt_workbench_restart_passed\":true,\"mgt_workbench_direct_parity_passed\":true,\"workbench_operator_surface_passed\":true,\"workbench_review_decision\":\"review\",\"workbench_review_sha256\":\"sha256:$workbench_review_hash\",\"workbench_export_sha256\":\"sha256:$workbench_export_hash\",\"mgt_workbench_operator_surface_passed\":true,\"mgt_workbench_review_decision\":\"review\",\"mgt_workbench_review_sha256\":\"sha256:$mgt_workbench_review_hash\",\"mgt_workbench_export_sha256\":\"sha256:$mgt_workbench_export_hash\",\"workbench_catalog_surface_passed\":true,\"workbench_catalog_sha256\":\"sha256:$workbench_catalog_hash\",\"workbench_evidence_surface_passed\":true,\"workbench_evidence_sha256\":\"sha256:$workbench_evidence_hash\",\"catalog_builder_check_passed\":true,\"catalog_builder_check_sha256\":\"sha256:$catalog_builder_check_hash\",\"catalog_builder_build_passed\":true,\"catalog_builder_build_sha256\":\"sha256:$catalog_builder_build_hash\",\"catalog_builder_output_sha256\":\"sha256:$catalog_builder_output_hash\",\"evidence_builder_check_passed\":true,\"evidence_builder_check_sha256\":\"sha256:$evidence_builder_check_hash\",\"evidence_builder_build_passed\":true,\"evidence_builder_build_sha256\":\"sha256:$evidence_builder_build_hash\",\"evidence_builder_manifest_sha256\":\"sha256:$evidence_builder_manifest_hash\",\"workbench_localized_pdf_surface_passed\":true,\"workbench_localized_pdf_en_us_sha256\":\"sha256:$localized_pdf_en_us_hash\",\"workbench_localized_pdf_ko_kr_sha256\":\"sha256:$localized_pdf_ko_kr_hash\",\"workbench_localized_pdf_en_us_receipt_sha256\":\"sha256:$localized_pdf_en_us_receipt_hash\",\"workbench_localized_pdf_ko_kr_receipt_sha256\":\"sha256:$localized_pdf_ko_kr_receipt_hash\",\"localized_report_font_sha256\":\"sha256:$localized_report_font_hash\",\"localized_report_font_license_sha256\":\"sha256:$localized_report_font_license_hash\",\"localized_report_font_provenance_sha256\":\"sha256:$localized_report_font_provenance_hash\",\"mgt_source_sha256\":\"sha256:$mgt_source_hash\",\"mgt_import_health_sha256\":\"sha256:$mgt_health_hash\",\"result_ir_sha256\":\"sha256:$result_hash\",\"report_pdf_sha256\":\"sha256:$report_hash\",\"mgt_result_ir_sha256\":\"sha256:$mgt_result_hash\",\"mgt_report_pdf_sha256\":\"sha256:$mgt_report_hash\",\"fallback_count\":0,\"authority\":\"approved_rocm_c5\"}" > "$temporary_receipt"

backend_output_stage="$(mktemp "$installed_backend_parent/.structural-installed-backend.XXXXXX")"
receipt_output_stage="$(mktemp "$receipt_parent/.structural-distribution-receipt.XXXXXX")"
cp "$e2e_root/installed-backend-receipt.json" "$backend_output_stage"
cp "$temporary_receipt" "$receipt_output_stage"
chmod 0444 "$backend_output_stage" "$receipt_output_stage"
mv "$backend_output_stage" "$installed_backend_receipt"
mv "$receipt_output_stage" "$receipt"
