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
for executable in structural-cli structural-catalog structural-evidence structural-installer structural-workbench; do
  test -x "$active/bin/$executable"
  env -i PATH="$empty_path" "$active/bin/$executable" --version > "$e2e_root/$executable-version.json"
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

linear_model="$repository_root/tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
linear_request="$repository_root/native/tests/fixtures/model_ir_linear/frame_cantilever_weak_request.json"
linear_external="$repository_root/native/tests/fixtures/model_ir_linear/frame_cantilever_external_v1.json"
linear_source_artifact="$repository_root/native/tests/fixtures/model_ir_linear/frame_cantilever_language_neutral_oracle_v1.txt"
linear_restarted="$e2e_root/model-ir-linear-workbench-restarted"
linear_direct="$e2e_root/model-ir-linear-workbench-direct"
env -i PATH="$empty_path" "$active/bin/structural-workbench" import-model-linear \
  "$linear_model" "$linear_request" --external-result "$linear_external" \
  --source-artifact "$linear_source_artifact" --workspace "$linear_restarted" \
  > "$e2e_root/model-ir-linear-import.json"
for stage in validate run resume compare report; do
  stage_arguments=("$stage" --workspace "$linear_restarted")
  if [[ "$stage" == "run" ]]; then
    stage_arguments+=(--step-budget 1)
  elif [[ "$stage" == "compare" ]]; then
    stage_arguments+=(--require-pass)
  fi
  env -i PATH="$empty_path" "$active/bin/structural-workbench" "${stage_arguments[@]}" \
    > "$e2e_root/model-ir-linear-$stage.json"
done
env -i PATH="$empty_path" "$active/bin/structural-workbench" workflow-model-linear \
  "$linear_model" "$linear_request" --external-result "$linear_external" \
  --source-artifact "$linear_source_artifact" --workspace "$linear_direct" --step-budget 1 \
  > "$e2e_root/model-ir-linear-workflow.json"
grep -Fq '"stage":"reported"' "$e2e_root/model-ir-linear-workflow.json"
grep -Fq '"schema_version":"structural-native-sparse-linear-pdf-report-receipt.v1"' \
  "$linear_direct/06-report/pdf-receipt.json"
grep -Fq '"schema_version":"structural-native-model-ir-linear-pdf-report-receipt.v1"' \
  "$linear_direct/06-report/report-receipt.json"
diff -r "$linear_restarted" "$linear_direct" > "$e2e_root/model-ir-linear-workbench-diff.txt"

mgt_linear_source="$repository_root/native/tests/fixtures/mgt_import/workbench_cantilever_frame3d_x.mgt"
mgt_linear_request="$repository_root/native/tests/fixtures/model_ir_linear/mgt_cantilever_request.json"
mgt_linear_external="$repository_root/native/tests/fixtures/model_ir_linear/mgt_cantilever_external_v1.json"
mgt_linear_source_artifact="$repository_root/native/tests/fixtures/model_ir_linear/mgt_cantilever_language_neutral_oracle_v1.txt"
mgt_linear_restarted="$e2e_root/mgt-model-ir-linear-workbench-restarted"
mgt_linear_direct="$e2e_root/mgt-model-ir-linear-workbench-direct"
env -i PATH="$empty_path" "$active/bin/structural-workbench" import-mgt-model-linear \
  "$mgt_linear_source" "$mgt_linear_request" \
  --model-id workbench-mgt-linear-cantilever-v1 \
  --external-result "$mgt_linear_external" \
  --source-artifact "$mgt_linear_source_artifact" --workspace "$mgt_linear_restarted" \
  > "$e2e_root/mgt-model-ir-linear-import.json"
env -i PATH="$empty_path" "$active/bin/structural-workbench" validate \
  --workspace "$mgt_linear_restarted" > "$e2e_root/mgt-model-ir-linear-validate.json"
cp -- "$mgt_linear_restarted/workbench-session.json" \
  "$e2e_root/mgt-model-ir-linear-validated-session.json"
env -i PATH="$empty_path" "$active/bin/structural-workbench" run \
  --workspace "$mgt_linear_restarted" --step-budget 1 \
  > "$e2e_root/mgt-model-ir-linear-run.json"
test -s "$mgt_linear_restarted/03-run/checkpoint.mlpcp"
cp -- "$e2e_root/mgt-model-ir-linear-validated-session.json" \
  "$mgt_linear_restarted/workbench-session.json"
for stage in resume compare report; do
  stage_arguments=("$stage" --workspace "$mgt_linear_restarted")
  if [[ "$stage" == "compare" ]]; then
    stage_arguments+=(--require-pass)
  fi
  env -i PATH="$empty_path" "$active/bin/structural-workbench" "${stage_arguments[@]}" \
    > "$e2e_root/mgt-model-ir-linear-$stage.json"
done
env -i PATH="$empty_path" "$active/bin/structural-workbench" workflow-mgt-model-linear \
  "$mgt_linear_source" "$mgt_linear_request" \
  --model-id workbench-mgt-linear-cantilever-v1 \
  --external-result "$mgt_linear_external" \
  --source-artifact "$mgt_linear_source_artifact" --workspace "$mgt_linear_direct" \
  --step-budget 1 > "$e2e_root/mgt-model-ir-linear-workflow.json"
grep -Fq '"stage":"reported"' "$e2e_root/mgt-model-ir-linear-workflow.json"
grep -Fq '"analysis_profile":"model_ir_linear_cpu_v1"' \
  "$mgt_linear_direct/workbench-session.json"
grep -Fq '"status":"normalized"' "$mgt_linear_direct/01-import/import-health.json"
grep -Fq '"schema_version":"structural-native-sparse-linear-pdf-report-receipt.v1"' \
  "$mgt_linear_direct/06-report/pdf-receipt.json"
grep -Fq '"schema_version":"structural-native-model-ir-linear-pdf-report-receipt.v1"' \
  "$mgt_linear_direct/06-report/report-receipt.json"
cmp "$mgt_linear_source" "$mgt_linear_direct/01-import/source.mgt"
diff -r "$mgt_linear_restarted" "$mgt_linear_direct" \
  > "$e2e_root/mgt-model-ir-linear-workbench-diff.txt"

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
exercise_operator_surface model-ir-linear-workbench "$linear_direct"
exercise_operator_surface mgt-model-ir-linear-workbench "$mgt_linear_direct"
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

exercise_model_ir_linear_localized_pdf_surface() {
  local workspace="$1"
  local workspace_before="$e2e_root/model-ir-linear-workbench-before-localized-pdf"
  cp -a -- "$workspace" "$workspace_before"
  for locale in en-US ko-KR; do
    local first="$e2e_root/model-ir-linear-localized-pdf-$locale-first"
    local second="$e2e_root/model-ir-linear-localized-pdf-$locale-second"
    local output_directory
    for output_directory in "$first" "$second"; do
      env -i PATH="$empty_path" "$active/bin/structural-workbench" report-export-pdf \
        --workspace "$workspace" --output-dir "$output_directory" --locale "$locale" \
        > "$output_directory.stdout.json"
      test -s "$output_directory/report.pdf"
      test -s "$output_directory/pdf-receipt.json"
      grep -Fq '"schema_version":"structural-native-sparse-linear-localized-pdf-report-receipt.v2"' \
        "$output_directory/pdf-receipt.json"
      grep -Fq '"profile":"sparse_linear_cpu_v1"' \
        "$output_directory/pdf-receipt.json"
      grep -Fq "\"locale\":\"$locale\"" "$output_directory/pdf-receipt.json"
      grep -Fq "\"content_hash\":\"sha256:$localized_report_font_hash\"" \
        "$output_directory/pdf-receipt.json"
      grep -Fq "\"content_hash\":\"sha256:$localized_report_font_license_hash\"" \
        "$output_directory/pdf-receipt.json"
      grep -Fq "\"content_hash\":\"sha256:$localized_report_font_provenance_hash\"" \
        "$output_directory/pdf-receipt.json"
    done
    cmp "$first/report.pdf" "$second/report.pdf"
    cmp "$first/pdf-receipt.json" "$second/pdf-receipt.json"
  done
  if cmp -s "$e2e_root/model-ir-linear-localized-pdf-en-US-first/report.pdf" \
    "$e2e_root/model-ir-linear-localized-pdf-ko-KR-first/report.pdf"; then
    echo "installed ModelIR-linear localized PDF outputs must differ by locale" >&2
    exit 1
  fi
  diff -r "$workspace_before" "$workspace" \
    > "$e2e_root/model-ir-linear-workbench-localized-pdf-diff.txt"
}
exercise_model_ir_linear_localized_pdf_surface "$linear_direct"

exercise_model_view_surface() {
  local topology_model="$repository_root/examples/bounded_planar_frame_alpha.model-ir.v2.json"
  local projections=(isometric xy xz yz)
  local projection
  for projection in "${projections[@]}"; do
    local first="$e2e_root/model-view-$projection-first.txt"
    local second="$e2e_root/model-view-$projection-second.txt"
    local output
    for output in "$first" "$second"; do
      env -i PATH="$empty_path" "$active/bin/structural-workbench" model-view \
        "$topology_model" --projection "$projection" > "$output"
      grep -Fq 'Schema: structural-native-model-topology-view.v1' "$output"
      grep -Fq "Projection: $projection" "$output"
      grep -Fq 'C++ semantic snapshot: verified' "$output"
      grep -Fq 'Analysis ready: true' "$output"
      if LC_ALL=C grep -q $'\033' "$output"; then
        echo "installed model topology view contains an ANSI escape" >&2
        exit 1
      fi
    done
    cmp "$first" "$second"
  done
  local left right
  for ((left = 0; left < ${#projections[@]}; left++)); do
    for ((right = left + 1; right < ${#projections[@]}; right++)); do
      if cmp -s \
        "$e2e_root/model-view-${projections[$left]}-first.txt" \
        "$e2e_root/model-view-${projections[$right]}-first.txt"; then
        echo "installed model topology projections must have distinct identities" >&2
        exit 1
      fi
    done
  done
  local english_explicit="$e2e_root/model-view-en-US-explicit.txt"
  env -i PATH="$empty_path" "$active/bin/structural-workbench" model-view \
    "$topology_model" --locale en-US --projection isometric > "$english_explicit"
  cmp "$e2e_root/model-view-isometric-first.txt" "$english_explicit"

  local korean_first="$e2e_root/model-view-ko-KR-first.txt"
  local korean_second="$e2e_root/model-view-ko-KR-second.txt"
  local korean_output
  for korean_output in "$korean_first" "$korean_second"; do
    env -i PATH="$empty_path" "$active/bin/structural-workbench" model-view \
      "$topology_model" --locale ko-KR --projection isometric > "$korean_output"
    grep -Fq 'Structural Native Workbench - 모델 위상 뷰' "$korean_output"
    grep -Fq '로케일: ko-KR' "$korean_output"
    grep -Fq '투영: isometric' "$korean_output"
    grep -Fq 'C++ 의미 스냅샷: verified' "$korean_output"
    grep -Fq '해석 준비: true' "$korean_output"
    grep -Eq '보기 해시: sha256:[0-9a-f]{64}' "$korean_output"
    if LC_ALL=C grep -q $'\033' "$korean_output"; then
      echo "installed Korean model topology view contains an ANSI escape" >&2
      exit 1
    fi
  done
  cmp "$korean_first" "$korean_second"
  if cmp -s "$e2e_root/model-view-isometric-first.txt" "$korean_first"; then
    echo "installed en-US and ko-KR model topology views must differ" >&2
    exit 1
  fi
}
exercise_model_view_surface

exercise_model_edit_surface() {
  local edit_source="$repository_root/tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$edit_source" | awk '{print $1}')"
  local label output_directory
  for label in first second; do
    output_directory="$e2e_root/model-edit-$label"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" model-edit-node \
      "$edit_source" --node N2 --coordinates 2 1 1 --output-dir "$output_directory" \
      > "$e2e_root/model-edit-$label.stdout.json"
    test -s "$output_directory/model-ir.json"
    test -s "$output_directory/edit-receipt.json"
    grep -Fq '"schema_version":"structural-native-model-edit-receipt.v1"' \
      "$output_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' \
      "$output_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$output_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' \
      "$output_directory/edit-receipt.json"
    grep -Fq "\"source_input_sha256\":\"sha256:$source_before_hash\"" \
      "$output_directory/edit-receipt.json"
    grep -Fq '"normalizer_id":"structural-native-model-editor"' \
      "$output_directory/model-ir.json"
    grep -Fq '"structural-native:model-edit-node.v1"' "$output_directory/model-ir.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$output_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/model-edit-$label-validation.json"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" model-view \
      "$output_directory/model-ir.json" > "$e2e_root/model-edit-$label-view.txt"
    grep -Fq 'C++ semantic snapshot: verified' "$e2e_root/model-edit-$label-view.txt"
  done
  diff -r "$e2e_root/model-edit-first" "$e2e_root/model-edit-second" \
    > "$e2e_root/model-edit-diff.txt"
  cmp "$e2e_root/model-edit-first.stdout.json" "$e2e_root/model-edit-second.stdout.json"
  cmp "$e2e_root/model-edit-first-validation.json" \
    "$e2e_root/model-edit-second-validation.json"
  cmp "$e2e_root/model-edit-first-view.txt" "$e2e_root/model-edit-second-view.txt"
  if [[ "$(sha256sum "$edit_source" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed model edit mutated its source ModelIR" >&2
    exit 1
  fi
}
exercise_model_edit_surface

exercise_nodal_load_edit_surface() {
  local edit_source="$repository_root/tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$edit_source" | awk '{print $1}')"
  local label output_directory
  for label in first second; do
    output_directory="$e2e_root/nodal-load-edit-$label"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" model-edit-nodal-load \
      "$edit_source" --load-pattern LC_WEAK --load L_WEAK_N2 \
      --components 0 -20000 0 0 0 0 --output-dir "$output_directory" \
      > "$e2e_root/nodal-load-edit-$label.stdout.json"
    test -s "$output_directory/model-ir.json"
    test -s "$output_directory/edit-receipt.json"
    grep -Fq '"schema_version":"structural-native-model-edit-receipt.v1"' \
      "$output_directory/edit-receipt.json"
    grep -Fq '"operation":"nodal_load_components"' \
      "$output_directory/edit-receipt.json"
    grep -Fq '"load_pattern_id":"LC_WEAK"' \
      "$output_directory/edit-receipt.json"
    grep -Fq '"nodal_load_id":"L_WEAK_N2"' \
      "$output_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' \
      "$output_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$output_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' \
      "$output_directory/edit-receipt.json"
    grep -Fq "\"source_input_sha256\":\"sha256:$source_before_hash\"" \
      "$output_directory/edit-receipt.json"
    grep -Fq '"normalizer_id":"structural-native-model-editor"' \
      "$output_directory/model-ir.json"
    grep -Fq '"structural-native:model-edit-nodal-load.v1"' \
      "$output_directory/model-ir.json"
    grep -Fq '"FY":-20000' "$output_directory/model-ir.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$output_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/nodal-load-edit-$label-validation.json"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" model-view \
      "$output_directory/model-ir.json" > "$e2e_root/nodal-load-edit-$label-view.txt"
    grep -Fq 'C++ semantic snapshot: verified' \
      "$e2e_root/nodal-load-edit-$label-view.txt"
  done
  diff -r "$e2e_root/nodal-load-edit-first" "$e2e_root/nodal-load-edit-second" \
    > "$e2e_root/nodal-load-edit-diff.txt"
  cmp "$e2e_root/nodal-load-edit-first.stdout.json" \
    "$e2e_root/nodal-load-edit-second.stdout.json"
  cmp "$e2e_root/nodal-load-edit-first-validation.json" \
    "$e2e_root/nodal-load-edit-second-validation.json"
  cmp "$e2e_root/nodal-load-edit-first-view.txt" \
    "$e2e_root/nodal-load-edit-second-view.txt"
  if [[ "$(sha256sum "$edit_source" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed nodal-load edit mutated its source ModelIR" >&2
    exit 1
  fi
}
exercise_nodal_load_edit_surface

exercise_constraint_value_edit_surface() {
  local edit_source="$repository_root/examples/bounded_planar_settlement.model-ir.v2.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$edit_source" | awk '{print $1}')"
  local label output_directory
  for label in first second; do
    output_directory="$e2e_root/constraint-value-edit-$label"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-edit-constraint-value "$edit_source" --constraint BC2 --dof UY \
      --value -0.0002 --output-dir "$output_directory" \
      > "$e2e_root/constraint-value-edit-$label.stdout.json"
    test -s "$output_directory/model-ir.json"
    test -s "$output_directory/edit-receipt.json"
    grep -Fq '"schema_version":"structural-native-model-edit-receipt.v1"' \
      "$output_directory/edit-receipt.json"
    grep -Fq '"operation":"constraint_prescribed_value"' \
      "$output_directory/edit-receipt.json"
    grep -Fq '"constraint_id":"BC2"' "$output_directory/edit-receipt.json"
    grep -Fq '"dof":"UY"' "$output_directory/edit-receipt.json"
    grep -Fq '"unit":"m"' "$output_directory/edit-receipt.json"
    grep -Fq '"previous_value_si":-0.0001' "$output_directory/edit-receipt.json"
    grep -Fq '"edited_value_si":-0.0002' "$output_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' \
      "$output_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$output_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' \
      "$output_directory/edit-receipt.json"
    grep -Fq "\"source_input_sha256\":\"sha256:$source_before_hash\"" \
      "$output_directory/edit-receipt.json"
    grep -Fq '"normalizer_id":"structural-native-model-editor"' \
      "$output_directory/model-ir.json"
    grep -Fq '"structural-native:model-edit-constraint-value.v1"' \
      "$output_directory/model-ir.json"
    grep -Fq '"UY":-0.0002' "$output_directory/model-ir.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$output_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/constraint-value-edit-$label-validation.json"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" model-view \
      "$output_directory/model-ir.json" \
      > "$e2e_root/constraint-value-edit-$label-view.txt"
    grep -Fq 'C++ semantic snapshot: verified' \
      "$e2e_root/constraint-value-edit-$label-view.txt"
  done
  diff -r "$e2e_root/constraint-value-edit-first" \
    "$e2e_root/constraint-value-edit-second" \
    > "$e2e_root/constraint-value-edit-diff.txt"
  cmp "$e2e_root/constraint-value-edit-first.stdout.json" \
    "$e2e_root/constraint-value-edit-second.stdout.json"
  cmp "$e2e_root/constraint-value-edit-first-validation.json" \
    "$e2e_root/constraint-value-edit-second-validation.json"
  cmp "$e2e_root/constraint-value-edit-first-view.txt" \
    "$e2e_root/constraint-value-edit-second-view.txt"
  if [[ "$(sha256sum "$edit_source" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed constraint-value edit mutated its source ModelIR" >&2
    exit 1
  fi
}
exercise_constraint_value_edit_surface

exercise_linear_material_edit_surface() {
  local edit_source="$repository_root/tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$edit_source" | awk '{print $1}')"
  local label output_directory
  for label in first second; do
    output_directory="$e2e_root/linear-material-edit-$label"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-edit-linear-material "$edit_source" --material M1 \
      --elastic-modulus-pa 210000000000 --poisson-ratio 0.29 \
      --density-kg-m3 7850 --output-dir "$output_directory" \
      > "$e2e_root/linear-material-edit-$label.stdout.json"
    test -s "$output_directory/model-ir.json"
    test -s "$output_directory/edit-receipt.json"
    grep -Fq '"schema_version":"structural-native-model-edit-receipt.v1"' \
      "$output_directory/edit-receipt.json"
    grep -Fq '"operation":"linear_elastic_material_parameters"' \
      "$output_directory/edit-receipt.json"
    grep -Fq '"material_id":"M1"' "$output_directory/edit-receipt.json"
    grep -Fq '"law_id":"linear_elastic_isotropic"' \
      "$output_directory/edit-receipt.json"
    grep -Fq '"parameter_set_version":"1"' \
      "$output_directory/edit-receipt.json"
    grep -Fq '"elastic_modulus_pa":210000000000' \
      "$output_directory/edit-receipt.json"
    grep -Fq '"poisson_ratio":0.29' "$output_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' \
      "$output_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$output_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' \
      "$output_directory/edit-receipt.json"
    grep -Fq "\"source_input_sha256\":\"sha256:$source_before_hash\"" \
      "$output_directory/edit-receipt.json"
    grep -Fq '"normalizer_id":"structural-native-model-editor"' \
      "$output_directory/model-ir.json"
    grep -Fq '"structural-native:model-edit-linear-material.v1"' \
      "$output_directory/model-ir.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$output_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/linear-material-edit-$label-validation.json"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" model-view \
      "$output_directory/model-ir.json" \
      > "$e2e_root/linear-material-edit-$label-view.txt"
    grep -Fq 'C++ semantic snapshot: verified' \
      "$e2e_root/linear-material-edit-$label-view.txt"
  done
  diff -r "$e2e_root/linear-material-edit-first" \
    "$e2e_root/linear-material-edit-second" \
    > "$e2e_root/linear-material-edit-diff.txt"
  cmp "$e2e_root/linear-material-edit-first.stdout.json" \
    "$e2e_root/linear-material-edit-second.stdout.json"
  cmp "$e2e_root/linear-material-edit-first-validation.json" \
    "$e2e_root/linear-material-edit-second-validation.json"
  cmp "$e2e_root/linear-material-edit-first-view.txt" \
    "$e2e_root/linear-material-edit-second-view.txt"
  if [[ "$(sha256sum "$edit_source" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed linear-material edit mutated its source ModelIR" >&2
    exit 1
  fi
}
exercise_linear_material_edit_surface

exercise_frame_section_edit_surface() {
  local edit_source="$repository_root/tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$edit_source" | awk '{print $1}')"
  local label output_directory
  for label in first second; do
    output_directory="$e2e_root/frame-section-edit-$label"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-edit-frame-section "$edit_source" --section S1 \
      --area-m2 0.025 --iy-m4 0.00009 --iz-m4 0.00006 \
      --torsional-constant-m4 0.000012 --shear-area-y-m2 0.02 \
      --shear-area-z-m2 0.02 --output-dir "$output_directory" \
      > "$e2e_root/frame-section-edit-$label.stdout.json"
    test -s "$output_directory/model-ir.json"
    test -s "$output_directory/edit-receipt.json"
    grep -Fq '"schema_version":"structural-native-model-edit-receipt.v1"' \
      "$output_directory/edit-receipt.json"
    grep -Fq '"operation":"frame_section_parameters"' \
      "$output_directory/edit-receipt.json"
    grep -Fq '"section_id":"S1"' "$output_directory/edit-receipt.json"
    grep -Fq '"family_id":"frame_3d"' "$output_directory/edit-receipt.json"
    grep -Fq '"parameter_set_version":"1"' \
      "$output_directory/edit-receipt.json"
    grep -Fq '"area_m2":0.025' "$output_directory/edit-receipt.json"
    grep -Fq '"torsional_constant_m4":1.2e-05' \
      "$output_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' \
      "$output_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$output_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' \
      "$output_directory/edit-receipt.json"
    grep -Fq "\"source_input_sha256\":\"sha256:$source_before_hash\"" \
      "$output_directory/edit-receipt.json"
    grep -Fq '"normalizer_id":"structural-native-model-editor"' \
      "$output_directory/model-ir.json"
    grep -Fq '"structural-native:model-edit-frame-section.v1"' \
      "$output_directory/model-ir.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$output_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/frame-section-edit-$label-validation.json"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" model-view \
      "$output_directory/model-ir.json" \
      > "$e2e_root/frame-section-edit-$label-view.txt"
    grep -Fq 'C++ semantic snapshot: verified' \
      "$e2e_root/frame-section-edit-$label-view.txt"
  done
  diff -r "$e2e_root/frame-section-edit-first" \
    "$e2e_root/frame-section-edit-second" \
    > "$e2e_root/frame-section-edit-diff.txt"
  cmp "$e2e_root/frame-section-edit-first.stdout.json" \
    "$e2e_root/frame-section-edit-second.stdout.json"
  cmp "$e2e_root/frame-section-edit-first-validation.json" \
    "$e2e_root/frame-section-edit-second-validation.json"
  cmp "$e2e_root/frame-section-edit-first-view.txt" \
    "$e2e_root/frame-section-edit-second-view.txt"
  if [[ "$(sha256sum "$edit_source" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed frame-section edit mutated its source ModelIR" >&2
    exit 1
  fi
}
exercise_frame_section_edit_surface

exercise_frame_element_orientation_edit_surface() {
  local edit_source="$repository_root/tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$edit_source" | awk '{print $1}')"
  local label output_directory
  for label in first second; do
    output_directory="$e2e_root/frame-element-orientation-edit-$label"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-edit-frame-element-orientation "$edit_source" --element E1 \
      --rotation-rad 0.25 --output-dir "$output_directory" \
      > "$e2e_root/frame-element-orientation-edit-$label.stdout.json"
    test -s "$output_directory/model-ir.json"
    test -s "$output_directory/edit-receipt.json"
    grep -Fq '"schema_version":"structural-native-model-edit-receipt.v1"' \
      "$output_directory/edit-receipt.json"
    grep -Fq '"operation":"frame_element_local_axis_rotation"' \
      "$output_directory/edit-receipt.json"
    grep -Fq '"element_id":"E1"' "$output_directory/edit-receipt.json"
    grep -Fq '"element_type":"frame_3d"' "$output_directory/edit-receipt.json"
    grep -Fq '"formulation":"euler_bernoulli_3d"' \
      "$output_directory/edit-receipt.json"
    grep -Fq '"previous_local_axis_rotation_rad":0' \
      "$output_directory/edit-receipt.json"
    grep -Fq '"edited_local_axis_rotation_rad":0.25' \
      "$output_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' \
      "$output_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$output_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' \
      "$output_directory/edit-receipt.json"
    grep -Fq "\"source_input_sha256\":\"sha256:$source_before_hash\"" \
      "$output_directory/edit-receipt.json"
    grep -Fq '"normalizer_id":"structural-native-model-editor"' \
      "$output_directory/model-ir.json"
    grep -Fq '"structural-native:model-edit-frame-element-orientation.v1"' \
      "$output_directory/model-ir.json"
    grep -Fq '"local_axis_rotation_rad":0.25' \
      "$output_directory/model-ir.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$output_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/frame-element-orientation-edit-$label-validation.json"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" model-view \
      "$output_directory/model-ir.json" \
      > "$e2e_root/frame-element-orientation-edit-$label-view.txt"
    grep -Fq 'C++ semantic snapshot: verified' \
      "$e2e_root/frame-element-orientation-edit-$label-view.txt"
  done
  diff -r "$e2e_root/frame-element-orientation-edit-first" \
    "$e2e_root/frame-element-orientation-edit-second" \
    > "$e2e_root/frame-element-orientation-edit-diff.txt"
  cmp "$e2e_root/frame-element-orientation-edit-first.stdout.json" \
    "$e2e_root/frame-element-orientation-edit-second.stdout.json"
  cmp "$e2e_root/frame-element-orientation-edit-first-validation.json" \
    "$e2e_root/frame-element-orientation-edit-second-validation.json"
  cmp "$e2e_root/frame-element-orientation-edit-first-view.txt" \
    "$e2e_root/frame-element-orientation-edit-second-view.txt"
  if [[ "$(sha256sum "$edit_source" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed frame-element orientation edit mutated its source ModelIR" >&2
    exit 1
  fi
}
exercise_frame_element_orientation_edit_surface

exercise_element_connectivity_edit_surface() {
  local edit_source="$repository_root/tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$edit_source" | awk '{print $1}')"
  local label output_directory
  for label in first second; do
    output_directory="$e2e_root/element-connectivity-edit-$label"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-edit-element-connectivity "$edit_source" --element E1 \
      --nodes N2 N1 --output-dir "$output_directory" \
      > "$e2e_root/element-connectivity-edit-$label.stdout.json"
    test -s "$output_directory/model-ir.json"
    test -s "$output_directory/edit-receipt.json"
    grep -Fq '"schema_version":"structural-native-model-edit-receipt.v1"' \
      "$output_directory/edit-receipt.json"
    grep -Fq '"operation":"element_connectivity"' \
      "$output_directory/edit-receipt.json"
    grep -Fq '"element_id":"E1"' "$output_directory/edit-receipt.json"
    grep -Fq '"element_type":"frame_3d"' "$output_directory/edit-receipt.json"
    grep -Fq '"formulation":"euler_bernoulli_3d"' \
      "$output_directory/edit-receipt.json"
    grep -Fq '"previous_node_ids":["N1","N2"]' \
      "$output_directory/edit-receipt.json"
    grep -Fq '"edited_node_ids":["N2","N1"]' \
      "$output_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' \
      "$output_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$output_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' \
      "$output_directory/edit-receipt.json"
    grep -Fq "\"source_input_sha256\":\"sha256:$source_before_hash\"" \
      "$output_directory/edit-receipt.json"
    grep -Fq '"normalizer_id":"structural-native-model-editor"' \
      "$output_directory/model-ir.json"
    grep -Fq '"structural-native:model-edit-element-connectivity.v1"' \
      "$output_directory/model-ir.json"
    grep -Fq '"node_ids":["N2","N1"]' "$output_directory/model-ir.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$output_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/element-connectivity-edit-$label-validation.json"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" model-view \
      "$output_directory/model-ir.json" \
      > "$e2e_root/element-connectivity-edit-$label-view.txt"
    grep -Fq 'C++ semantic snapshot: verified' \
      "$e2e_root/element-connectivity-edit-$label-view.txt"
  done
  diff -r "$e2e_root/element-connectivity-edit-first" \
    "$e2e_root/element-connectivity-edit-second" \
    > "$e2e_root/element-connectivity-edit-diff.txt"
  cmp "$e2e_root/element-connectivity-edit-first.stdout.json" \
    "$e2e_root/element-connectivity-edit-second.stdout.json"
  cmp "$e2e_root/element-connectivity-edit-first-validation.json" \
    "$e2e_root/element-connectivity-edit-second-validation.json"
  cmp "$e2e_root/element-connectivity-edit-first-view.txt" \
    "$e2e_root/element-connectivity-edit-second-view.txt"
  if [[ "$(sha256sum "$edit_source" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed element-connectivity edit mutated its source ModelIR" >&2
    exit 1
  fi
}
exercise_element_connectivity_edit_surface

exercise_result_view_surface() {
  local workspace="$1"
  local workspace_before="$e2e_root/workbench-before-result-view"
  cp -a -- "$workspace" "$workspace_before"
  local channels=(top-displacement drift-ratio base-shear residual-inf)
  local channel label output
  for channel in "${channels[@]}"; do
    for label in first second; do
      output="$e2e_root/result-view-$channel-$label.txt"
      env -i PATH="$empty_path" "$active/bin/structural-workbench" result-view \
        --workspace "$workspace" --channel "$channel" > "$output"
      grep -Fq 'Schema: structural-native-workbench-ndtha-response-view.v1' "$output"
      grep -Fq "Channel: $channel" "$output"
      grep -Fq 'Displayed steps: 1-5 of 5' "$output"
      grep -Fq 'ResultIR v1 does not carry dt_s' "$output"
      grep -Eq 'View hash: sha256:[0-9a-f]{64}' "$output"
      if LC_ALL=C grep -q $'\033' "$output"; then
        echo "installed NDTHA response view contains an ANSI escape" >&2
        exit 1
      fi
    done
    cmp "$e2e_root/result-view-$channel-first.txt" \
      "$e2e_root/result-view-$channel-second.txt"
  done
  local left right
  for ((left = 0; left < ${#channels[@]}; left++)); do
    for ((right = left + 1; right < ${#channels[@]}; right++)); do
      if cmp -s "$e2e_root/result-view-${channels[$left]}-first.txt" \
        "$e2e_root/result-view-${channels[$right]}-first.txt"; then
        echo "installed NDTHA response channels must have distinct identities" >&2
        exit 1
      fi
    done
  done
  for label in first second; do
    output="$e2e_root/result-view-window-$label.txt"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" result-view \
      --workspace "$workspace" --channel drift-ratio --start-step 2 --count 2 > "$output"
    grep -Fq 'Displayed steps: 2-3 of 5' "$output"
  done
  cmp "$e2e_root/result-view-window-first.txt" "$e2e_root/result-view-window-second.txt"
  for label in first second; do
    output="$e2e_root/result-view-ko-KR-$label.txt"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" result-view \
      --workspace "$workspace" --locale ko-KR --channel top-displacement > "$output"
    grep -Fq '로케일: ko-KR' "$output"
    grep -Fq '채널: 최상단 변위 [top-displacement]' "$output"
    grep -Fq '시간값을 추론하지 않습니다' "$output"
    grep -Eq '보기 해시: sha256:[0-9a-f]{64}' "$output"
    if LC_ALL=C grep -q $'\033' "$output"; then
      echo "installed Korean NDTHA response view contains an ANSI escape" >&2
      exit 1
    fi
  done
  cmp "$e2e_root/result-view-ko-KR-first.txt" "$e2e_root/result-view-ko-KR-second.txt"
  if cmp -s "$e2e_root/result-view-top-displacement-first.txt" \
    "$e2e_root/result-view-ko-KR-first.txt"; then
    echo "installed en-US and ko-KR response views must have distinct identities" >&2
    exit 1
  fi
  env -i PATH="$empty_path" "$active/bin/structural-workbench" result-view \
    --workspace "$workspace" --locale en-US --channel top-displacement \
    > "$e2e_root/result-view-en-US-explicit.txt"
  cmp "$e2e_root/result-view-top-displacement-first.txt" \
    "$e2e_root/result-view-en-US-explicit.txt"
  diff -r "$workspace_before" "$workspace" > "$e2e_root/workbench-result-view-diff.txt"
}
exercise_result_view_surface "$direct"

exercise_deformed_view_surface() {
  local workspace="$1"
  local workspace_before="$e2e_root/workbench-before-deformed-view"
  cp -a -- "$workspace" "$workspace_before"
  local projections=(isometric xy xz yz)
  local projection label output
  for projection in "${projections[@]}"; do
    for label in first second; do
      output="$e2e_root/deformed-view-$projection-$label.txt"
      env -i PATH="$empty_path" "$active/bin/structural-workbench" result-deformed-view \
        --workspace "$workspace" --projection "$projection" > "$output"
      grep -Fq 'Schema: structural-native-workbench-fixed-guided-deformed-view.v1' "$output"
      grep -Fq 'Profile: fixed_guided_frame3d_x' "$output"
      grep -Fq "Projection: $projection" "$output"
      grep -Fq 'Selected step: 5' "$output"
      grep -Fq 'C++ semantic snapshot: verified' "$output"
      grep -Fq 'C++ fixed-guided adapter execution: verified by durable terminal receipt' "$output"
      grep -Eq 'View hash: sha256:[0-9a-f]{64}' "$output"
      if LC_ALL=C grep -q $'\033' "$output"; then
        echo "installed fixed-guided deformed view contains an ANSI escape" >&2
        exit 1
      fi
    done
    cmp "$e2e_root/deformed-view-$projection-first.txt" \
      "$e2e_root/deformed-view-$projection-second.txt"
  done
  local left right
  for ((left = 0; left < ${#projections[@]}; left++)); do
    for ((right = left + 1; right < ${#projections[@]}; right++)); do
      if cmp -s "$e2e_root/deformed-view-${projections[$left]}-first.txt" \
        "$e2e_root/deformed-view-${projections[$right]}-first.txt"; then
        echo "installed deformed-shape projections must have distinct identities" >&2
        exit 1
      fi
    done
  done
  for label in first second; do
    output="$e2e_root/deformed-view-explicit-$label.txt"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" result-deformed-view \
      --workspace "$workspace" --projection xz --step 2 --scale 250 > "$output"
    grep -Fq 'Selected step: 2' "$output"
    grep -Fq 'Visual magnification: 2.50000000000000000e2' "$output"
  done
  cmp "$e2e_root/deformed-view-explicit-first.txt" \
    "$e2e_root/deformed-view-explicit-second.txt"
  if cmp -s "$e2e_root/deformed-view-xz-first.txt" \
    "$e2e_root/deformed-view-explicit-first.txt"; then
    echo "installed explicit deformed-shape view must have a distinct identity" >&2
    exit 1
  fi
  for label in first second; do
    output="$e2e_root/deformed-view-ko-KR-$label.txt"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" result-deformed-view \
      --workspace "$workspace" --locale ko-KR --projection isometric > "$output"
    grep -Fq '로케일: ko-KR' "$output"
    grep -Fq '프로파일: fixed_guided_frame3d_x' "$output"
    grep -Fq 'C++ 의미 스냅샷: verified' "$output"
    grep -Eq '보기 해시: sha256:[0-9a-f]{64}' "$output"
    if LC_ALL=C grep -q $'\033' "$output"; then
      echo "installed Korean fixed-guided deformed view contains an ANSI escape" >&2
      exit 1
    fi
  done
  cmp "$e2e_root/deformed-view-ko-KR-first.txt" \
    "$e2e_root/deformed-view-ko-KR-second.txt"
  if cmp -s "$e2e_root/deformed-view-isometric-first.txt" \
    "$e2e_root/deformed-view-ko-KR-first.txt"; then
    echo "installed en-US and ko-KR deformed views must have distinct identities" >&2
    exit 1
  fi
  env -i PATH="$empty_path" "$active/bin/structural-workbench" result-deformed-view \
    --workspace "$workspace" --locale en-US --projection isometric \
    > "$e2e_root/deformed-view-en-US-explicit.txt"
  cmp "$e2e_root/deformed-view-isometric-first.txt" \
    "$e2e_root/deformed-view-en-US-explicit.txt"
  diff -r "$workspace_before" "$workspace" > "$e2e_root/workbench-deformed-view-diff.txt"
}
exercise_deformed_view_surface "$direct"

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
linear_result_hash="$(sha256sum "$linear_direct/04-resume/result-ir.json" | awk '{print $1}')"
linear_recovery_hash="$(sha256sum "$linear_direct/04-resume/result-recovery-ir.json" | awk '{print $1}')"
linear_report_hash="$(sha256sum "$linear_direct/06-report/report.pdf" | awk '{print $1}')"
linear_pdf_receipt_hash="$(sha256sum "$linear_direct/06-report/pdf-receipt.json" | awk '{print $1}')"
linear_report_receipt_hash="$(sha256sum "$linear_direct/06-report/report-receipt.json" | awk '{print $1}')"
linear_workbench_review_hash="$(sha256sum "$linear_direct/07-review/review.json" | awk '{print $1}')"
linear_workbench_export_hash="$(sha256sum "$e2e_root/model-ir-linear-workbench-export.json" | awk '{print $1}')"
linear_localized_pdf_en_us_hash="$(sha256sum "$e2e_root/model-ir-linear-localized-pdf-en-US-first/report.pdf" | awk '{print $1}')"
linear_localized_pdf_ko_kr_hash="$(sha256sum "$e2e_root/model-ir-linear-localized-pdf-ko-KR-first/report.pdf" | awk '{print $1}')"
linear_localized_pdf_en_us_receipt_hash="$(sha256sum "$e2e_root/model-ir-linear-localized-pdf-en-US-first/pdf-receipt.json" | awk '{print $1}')"
linear_localized_pdf_ko_kr_receipt_hash="$(sha256sum "$e2e_root/model-ir-linear-localized-pdf-ko-KR-first/pdf-receipt.json" | awk '{print $1}')"
mgt_linear_source_hash="$(sha256sum "$mgt_linear_direct/01-import/source.mgt" | awk '{print $1}')"
mgt_linear_health_hash="$(sha256sum "$mgt_linear_direct/01-import/import-health.json" | awk '{print $1}')"
mgt_linear_result_hash="$(sha256sum "$mgt_linear_direct/04-resume/result-ir.json" | awk '{print $1}')"
mgt_linear_recovery_hash="$(sha256sum "$mgt_linear_direct/04-resume/result-recovery-ir.json" | awk '{print $1}')"
mgt_linear_report_hash="$(sha256sum "$mgt_linear_direct/06-report/report.pdf" | awk '{print $1}')"
mgt_linear_pdf_receipt_hash="$(sha256sum "$mgt_linear_direct/06-report/pdf-receipt.json" | awk '{print $1}')"
mgt_linear_report_receipt_hash="$(sha256sum "$mgt_linear_direct/06-report/report-receipt.json" | awk '{print $1}')"
mgt_linear_workbench_review_hash="$(sha256sum "$mgt_linear_direct/07-review/review.json" | awk '{print $1}')"
mgt_linear_workbench_export_hash="$(sha256sum "$e2e_root/mgt-model-ir-linear-workbench-export.json" | awk '{print $1}')"
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
model_view_isometric_hash="$(sha256sum "$e2e_root/model-view-isometric-first.txt" | awk '{print $1}')"
model_view_xy_hash="$(sha256sum "$e2e_root/model-view-xy-first.txt" | awk '{print $1}')"
model_view_xz_hash="$(sha256sum "$e2e_root/model-view-xz-first.txt" | awk '{print $1}')"
model_view_yz_hash="$(sha256sum "$e2e_root/model-view-yz-first.txt" | awk '{print $1}')"
model_view_ko_kr_hash="$(sha256sum "$e2e_root/model-view-ko-KR-first.txt" | awk '{print $1}')"
model_edit_model_hash="$(sha256sum "$e2e_root/model-edit-first/model-ir.json" | awk '{print $1}')"
model_edit_receipt_hash="$(sha256sum "$e2e_root/model-edit-first/edit-receipt.json" | awk '{print $1}')"
nodal_load_edit_model_hash="$(sha256sum "$e2e_root/nodal-load-edit-first/model-ir.json" | awk '{print $1}')"
nodal_load_edit_receipt_hash="$(sha256sum "$e2e_root/nodal-load-edit-first/edit-receipt.json" | awk '{print $1}')"
constraint_value_edit_model_hash="$(sha256sum "$e2e_root/constraint-value-edit-first/model-ir.json" | awk '{print $1}')"
constraint_value_edit_receipt_hash="$(sha256sum "$e2e_root/constraint-value-edit-first/edit-receipt.json" | awk '{print $1}')"
linear_material_edit_model_hash="$(sha256sum "$e2e_root/linear-material-edit-first/model-ir.json" | awk '{print $1}')"
linear_material_edit_receipt_hash="$(sha256sum "$e2e_root/linear-material-edit-first/edit-receipt.json" | awk '{print $1}')"
frame_section_edit_model_hash="$(sha256sum "$e2e_root/frame-section-edit-first/model-ir.json" | awk '{print $1}')"
frame_section_edit_receipt_hash="$(sha256sum "$e2e_root/frame-section-edit-first/edit-receipt.json" | awk '{print $1}')"
frame_element_orientation_edit_model_hash="$(sha256sum "$e2e_root/frame-element-orientation-edit-first/model-ir.json" | awk '{print $1}')"
frame_element_orientation_edit_receipt_hash="$(sha256sum "$e2e_root/frame-element-orientation-edit-first/edit-receipt.json" | awk '{print $1}')"
element_connectivity_edit_model_hash="$(sha256sum "$e2e_root/element-connectivity-edit-first/model-ir.json" | awk '{print $1}')"
element_connectivity_edit_receipt_hash="$(sha256sum "$e2e_root/element-connectivity-edit-first/edit-receipt.json" | awk '{print $1}')"
result_view_top_displacement_hash="$(sha256sum "$e2e_root/result-view-top-displacement-first.txt" | awk '{print $1}')"
result_view_drift_ratio_hash="$(sha256sum "$e2e_root/result-view-drift-ratio-first.txt" | awk '{print $1}')"
result_view_base_shear_hash="$(sha256sum "$e2e_root/result-view-base-shear-first.txt" | awk '{print $1}')"
result_view_residual_inf_hash="$(sha256sum "$e2e_root/result-view-residual-inf-first.txt" | awk '{print $1}')"
result_view_window_hash="$(sha256sum "$e2e_root/result-view-window-first.txt" | awk '{print $1}')"
result_view_ko_kr_hash="$(sha256sum "$e2e_root/result-view-ko-KR-first.txt" | awk '{print $1}')"
deformed_view_isometric_hash="$(sha256sum "$e2e_root/deformed-view-isometric-first.txt" | awk '{print $1}')"
deformed_view_xy_hash="$(sha256sum "$e2e_root/deformed-view-xy-first.txt" | awk '{print $1}')"
deformed_view_xz_hash="$(sha256sum "$e2e_root/deformed-view-xz-first.txt" | awk '{print $1}')"
deformed_view_yz_hash="$(sha256sum "$e2e_root/deformed-view-yz-first.txt" | awk '{print $1}')"
deformed_view_explicit_hash="$(sha256sum "$e2e_root/deformed-view-explicit-first.txt" | awk '{print $1}')"
deformed_view_ko_kr_hash="$(sha256sum "$e2e_root/deformed-view-ko-KR-first.txt" | awk '{print $1}')"
installed_backend_hash="$(sha256sum "$e2e_root/installed-backend-receipt.json" | awk '{print $1}')"
temporary_receipt="$e2e_root/distribution-receipt.json"
printf '%s\n' \
  "{\"schema_version\":\"structural-native-distribution-e2e.v13\",\"backend_profile\":\"cpu_only\",\"linkage\":\"$linkage\",\"release_id\":\"$release_id\",\"source_sha256\":\"$source_sha256\",\"bundle_manifest_sha256\":\"sha256:$manifest_hash\",\"installed_backend_receipt_sha256\":\"sha256:$installed_backend_hash\",\"c2_receipt_sha256\":null,\"approved_device_runner\":false,\"single_product_abi\":true,\"python_lookup_count\":0,\"node_lookup_count\":0,\"install_passed\":true,\"update_passed\":true,\"rollback_passed\":true,\"package_consumer_passed\":true,\"workbench_restart_passed\":true,\"workbench_direct_parity_passed\":true,\"mgt_workbench_restart_passed\":true,\"mgt_workbench_direct_parity_passed\":true,\"workbench_operator_surface_passed\":true,\"workbench_review_decision\":\"review\",\"workbench_review_sha256\":\"sha256:$workbench_review_hash\",\"workbench_export_sha256\":\"sha256:$workbench_export_hash\",\"mgt_workbench_operator_surface_passed\":true,\"mgt_workbench_review_decision\":\"review\",\"mgt_workbench_review_sha256\":\"sha256:$mgt_workbench_review_hash\",\"mgt_workbench_export_sha256\":\"sha256:$mgt_workbench_export_hash\",\"workbench_catalog_surface_passed\":true,\"workbench_catalog_sha256\":\"sha256:$workbench_catalog_hash\",\"workbench_evidence_surface_passed\":true,\"workbench_evidence_sha256\":\"sha256:$workbench_evidence_hash\",\"catalog_builder_check_passed\":true,\"catalog_builder_check_sha256\":\"sha256:$catalog_builder_check_hash\",\"catalog_builder_build_passed\":true,\"catalog_builder_build_sha256\":\"sha256:$catalog_builder_build_hash\",\"catalog_builder_output_sha256\":\"sha256:$catalog_builder_output_hash\",\"evidence_builder_check_passed\":true,\"evidence_builder_check_sha256\":\"sha256:$evidence_builder_check_hash\",\"evidence_builder_build_passed\":true,\"evidence_builder_build_sha256\":\"sha256:$evidence_builder_build_hash\",\"evidence_builder_manifest_sha256\":\"sha256:$evidence_builder_manifest_hash\",\"workbench_localized_pdf_surface_passed\":true,\"workbench_localized_pdf_en_us_sha256\":\"sha256:$localized_pdf_en_us_hash\",\"workbench_localized_pdf_ko_kr_sha256\":\"sha256:$localized_pdf_ko_kr_hash\",\"workbench_localized_pdf_en_us_receipt_sha256\":\"sha256:$localized_pdf_en_us_receipt_hash\",\"workbench_localized_pdf_ko_kr_receipt_sha256\":\"sha256:$localized_pdf_ko_kr_receipt_hash\",\"localized_report_font_sha256\":\"sha256:$localized_report_font_hash\",\"localized_report_font_license_sha256\":\"sha256:$localized_report_font_license_hash\",\"localized_report_font_provenance_sha256\":\"sha256:$localized_report_font_provenance_hash\",\"workbench_model_view_surface_passed\":true,\"workbench_model_view_isometric_sha256\":\"sha256:$model_view_isometric_hash\",\"workbench_model_view_xy_sha256\":\"sha256:$model_view_xy_hash\",\"workbench_model_view_xz_sha256\":\"sha256:$model_view_xz_hash\",\"workbench_model_view_yz_sha256\":\"sha256:$model_view_yz_hash\",\"workbench_localized_model_view_surface_passed\":true,\"workbench_model_view_ko_kr_sha256\":\"sha256:$model_view_ko_kr_hash\",\"workbench_model_edit_surface_passed\":true,\"workbench_model_edit_model_sha256\":\"sha256:$model_edit_model_hash\",\"workbench_model_edit_receipt_sha256\":\"sha256:$model_edit_receipt_hash\",\"workbench_result_view_surface_passed\":true,\"workbench_result_view_top_displacement_sha256\":\"sha256:$result_view_top_displacement_hash\",\"workbench_result_view_drift_ratio_sha256\":\"sha256:$result_view_drift_ratio_hash\",\"workbench_result_view_base_shear_sha256\":\"sha256:$result_view_base_shear_hash\",\"workbench_result_view_residual_inf_sha256\":\"sha256:$result_view_residual_inf_hash\",\"workbench_result_view_window_sha256\":\"sha256:$result_view_window_hash\",\"workbench_localized_result_views_surface_passed\":true,\"workbench_result_view_ko_kr_sha256\":\"sha256:$result_view_ko_kr_hash\",\"workbench_deformed_view_ko_kr_sha256\":\"sha256:$deformed_view_ko_kr_hash\",\"workbench_deformed_view_surface_passed\":true,\"workbench_deformed_view_isometric_sha256\":\"sha256:$deformed_view_isometric_hash\",\"workbench_deformed_view_xy_sha256\":\"sha256:$deformed_view_xy_hash\",\"workbench_deformed_view_xz_sha256\":\"sha256:$deformed_view_xz_hash\",\"workbench_deformed_view_yz_sha256\":\"sha256:$deformed_view_yz_hash\",\"workbench_deformed_view_explicit_sha256\":\"sha256:$deformed_view_explicit_hash\",\"mgt_source_sha256\":\"sha256:$mgt_source_hash\",\"mgt_import_health_sha256\":\"sha256:$mgt_health_hash\",\"result_ir_sha256\":\"sha256:$result_hash\",\"report_pdf_sha256\":\"sha256:$report_hash\",\"mgt_result_ir_sha256\":\"sha256:$mgt_result_hash\",\"mgt_report_pdf_sha256\":\"sha256:$mgt_report_hash\",\"fallback_count\":0,\"authority\":\"hosted_cpu_c5\"}" > "$temporary_receipt"
v13_receipt_json="$(<"$temporary_receipt")"
v14_receipt_json="${v13_receipt_json/structural-native-distribution-e2e.v13/structural-native-distribution-e2e.v14}"
linear_receipt_fields="\"model_ir_linear_workbench_restart_passed\":true,\"model_ir_linear_workbench_direct_parity_passed\":true,\"model_ir_linear_workbench_operator_surface_passed\":true,\"model_ir_linear_workbench_review_decision\":\"review\",\"model_ir_linear_workbench_review_sha256\":\"sha256:$linear_workbench_review_hash\",\"model_ir_linear_workbench_export_sha256\":\"sha256:$linear_workbench_export_hash\",\"model_ir_linear_result_ir_sha256\":\"sha256:$linear_result_hash\",\"model_ir_linear_result_recovery_ir_sha256\":\"sha256:$linear_recovery_hash\",\"model_ir_linear_report_pdf_sha256\":\"sha256:$linear_report_hash\",\"model_ir_linear_pdf_receipt_sha256\":\"sha256:$linear_pdf_receipt_hash\",\"model_ir_linear_report_receipt_sha256\":\"sha256:$linear_report_receipt_hash\","
v14_receipt_json="${v14_receipt_json/\"mgt_workbench_restart_passed\":true,/${linear_receipt_fields}\"mgt_workbench_restart_passed\":true,}"
printf '%s\n' "$v14_receipt_json" > "$temporary_receipt"
v15_receipt_json="${v14_receipt_json/structural-native-distribution-e2e.v14/structural-native-distribution-e2e.v15}"
linear_localized_pdf_fields="\"model_ir_linear_localized_pdf_surface_passed\":true,\"model_ir_linear_localized_pdf_en_us_sha256\":\"sha256:$linear_localized_pdf_en_us_hash\",\"model_ir_linear_localized_pdf_ko_kr_sha256\":\"sha256:$linear_localized_pdf_ko_kr_hash\",\"model_ir_linear_localized_pdf_en_us_receipt_sha256\":\"sha256:$linear_localized_pdf_en_us_receipt_hash\",\"model_ir_linear_localized_pdf_ko_kr_receipt_sha256\":\"sha256:$linear_localized_pdf_ko_kr_receipt_hash\","
v15_receipt_json="${v15_receipt_json/\"mgt_workbench_restart_passed\":true,/${linear_localized_pdf_fields}\"mgt_workbench_restart_passed\":true,}"
printf '%s\n' "$v15_receipt_json" > "$temporary_receipt"
v16_receipt_json="${v15_receipt_json/structural-native-distribution-e2e.v15/structural-native-distribution-e2e.v16}"
mgt_linear_receipt_fields="\"mgt_model_ir_linear_workbench_restart_passed\":true,\"mgt_model_ir_linear_workbench_direct_parity_passed\":true,\"mgt_model_ir_linear_workbench_operator_surface_passed\":true,\"mgt_model_ir_linear_workbench_review_decision\":\"review\",\"mgt_model_ir_linear_workbench_review_sha256\":\"sha256:$mgt_linear_workbench_review_hash\",\"mgt_model_ir_linear_workbench_export_sha256\":\"sha256:$mgt_linear_workbench_export_hash\",\"mgt_model_ir_linear_source_sha256\":\"sha256:$mgt_linear_source_hash\",\"mgt_model_ir_linear_import_health_sha256\":\"sha256:$mgt_linear_health_hash\",\"mgt_model_ir_linear_result_ir_sha256\":\"sha256:$mgt_linear_result_hash\",\"mgt_model_ir_linear_result_recovery_ir_sha256\":\"sha256:$mgt_linear_recovery_hash\",\"mgt_model_ir_linear_report_pdf_sha256\":\"sha256:$mgt_linear_report_hash\",\"mgt_model_ir_linear_pdf_receipt_sha256\":\"sha256:$mgt_linear_pdf_receipt_hash\",\"mgt_model_ir_linear_report_receipt_sha256\":\"sha256:$mgt_linear_report_receipt_hash\","
v16_receipt_json="${v16_receipt_json/\"mgt_workbench_restart_passed\":true,/${mgt_linear_receipt_fields}\"mgt_workbench_restart_passed\":true,}"
printf '%s\n' "$v16_receipt_json" > "$temporary_receipt"
v17_receipt_json="${v16_receipt_json/structural-native-distribution-e2e.v16/structural-native-distribution-e2e.v17}"
nodal_load_edit_receipt_fields="\"workbench_nodal_load_edit_surface_passed\":true,\"workbench_nodal_load_edit_model_sha256\":\"sha256:$nodal_load_edit_model_hash\",\"workbench_nodal_load_edit_receipt_sha256\":\"sha256:$nodal_load_edit_receipt_hash\","
v17_receipt_json="${v17_receipt_json/\"workbench_result_view_surface_passed\":true,/${nodal_load_edit_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v17_receipt_json" > "$temporary_receipt"
v18_receipt_json="${v17_receipt_json/structural-native-distribution-e2e.v17/structural-native-distribution-e2e.v18}"
constraint_value_edit_receipt_fields="\"workbench_constraint_value_edit_surface_passed\":true,\"workbench_constraint_value_edit_model_sha256\":\"sha256:$constraint_value_edit_model_hash\",\"workbench_constraint_value_edit_receipt_sha256\":\"sha256:$constraint_value_edit_receipt_hash\","
v18_receipt_json="${v18_receipt_json/\"workbench_result_view_surface_passed\":true,/${constraint_value_edit_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v18_receipt_json" > "$temporary_receipt"
v19_receipt_json="${v18_receipt_json/structural-native-distribution-e2e.v18/structural-native-distribution-e2e.v19}"
property_edit_receipt_fields="\"workbench_linear_material_edit_surface_passed\":true,\"workbench_linear_material_edit_model_sha256\":\"sha256:$linear_material_edit_model_hash\",\"workbench_linear_material_edit_receipt_sha256\":\"sha256:$linear_material_edit_receipt_hash\",\"workbench_frame_section_edit_surface_passed\":true,\"workbench_frame_section_edit_model_sha256\":\"sha256:$frame_section_edit_model_hash\",\"workbench_frame_section_edit_receipt_sha256\":\"sha256:$frame_section_edit_receipt_hash\","
v19_receipt_json="${v19_receipt_json/\"workbench_result_view_surface_passed\":true,/${property_edit_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v19_receipt_json" > "$temporary_receipt"
v20_receipt_json="${v19_receipt_json/structural-native-distribution-e2e.v19/structural-native-distribution-e2e.v20}"
frame_element_orientation_edit_receipt_fields="\"workbench_frame_element_orientation_edit_surface_passed\":true,\"workbench_frame_element_orientation_edit_model_sha256\":\"sha256:$frame_element_orientation_edit_model_hash\",\"workbench_frame_element_orientation_edit_receipt_sha256\":\"sha256:$frame_element_orientation_edit_receipt_hash\","
v20_receipt_json="${v20_receipt_json/\"workbench_result_view_surface_passed\":true,/${frame_element_orientation_edit_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v20_receipt_json" > "$temporary_receipt"
v21_receipt_json="${v20_receipt_json/structural-native-distribution-e2e.v20/structural-native-distribution-e2e.v21}"
element_connectivity_edit_receipt_fields="\"workbench_element_connectivity_edit_surface_passed\":true,\"workbench_element_connectivity_edit_model_sha256\":\"sha256:$element_connectivity_edit_model_hash\",\"workbench_element_connectivity_edit_receipt_sha256\":\"sha256:$element_connectivity_edit_receipt_hash\","
v21_receipt_json="${v21_receipt_json/\"workbench_result_view_surface_passed\":true,/${element_connectivity_edit_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v21_receipt_json" > "$temporary_receipt"

backend_output_stage="$(mktemp "$backend_receipt_parent/.structural-installed-backend.XXXXXX")"
receipt_output_stage="$(mktemp "$receipt_parent/.structural-distribution-receipt.XXXXXX")"
cp "$e2e_root/installed-backend-receipt.json" "$backend_output_stage"
cp "$temporary_receipt" "$receipt_output_stage"
chmod 0444 "$backend_output_stage" "$receipt_output_stage"
mv "$backend_output_stage" "$installed_backend_receipt"
mv "$receipt_output_stage" "$receipt"
