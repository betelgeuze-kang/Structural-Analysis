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
exercise_model_linear_request_create_surface() {
  local linear_model_before_hash label linear_request_directory
  linear_model_before_hash="$(sha256sum "$linear_model" | awk '{print $1}')"
  for label in first second; do
    linear_request_directory="$e2e_root/model-linear-request-create-$label"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$linear_model" \
      --case model-frame-linear-c5 --load-pattern LC_WEAK \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$linear_request_directory" \
      > "$e2e_root/model-linear-request-create-$label.stdout.json"
    grep -Fq '"schema_version":"structural-native-model-linear-request-create-receipt.v1"' \
      "$linear_request_directory/request-receipt.json"
    grep -Fq '"operation":"create_model_ir_linear_analysis_request"' \
      "$linear_request_directory/request-receipt.json"
    grep -Fq '"load_pattern_id":"LC_WEAK"' \
      "$linear_request_directory/request-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' \
      "$linear_request_directory/request-receipt.json"
    grep -Fq '"cpp_linear_assembly_preflight_verified":true' \
      "$linear_request_directory/request-receipt.json"
    grep -Fq '"execution_started":false' \
      "$linear_request_directory/request-receipt.json"
    grep -Eq '"assembly_hash":"sha256:[0-9a-f]{64}"' \
      "$linear_request_directory/request-receipt.json"
    grep -Eq '"generated_sparse_request_hash":"sha256:[0-9a-f]{64}"' \
      "$linear_request_directory/request-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' \
      "$linear_request_directory/request-receipt.json"
    grep -Fq "\"source_input_sha256\":\"sha256:$linear_model_before_hash\"" \
      "$linear_request_directory/request-receipt.json"
  done
  diff -r "$e2e_root/model-linear-request-create-first" \
    "$e2e_root/model-linear-request-create-second" \
    > "$e2e_root/model-linear-request-create-diff.txt"
  cmp "$e2e_root/model-linear-request-create-first.stdout.json" \
    "$e2e_root/model-linear-request-create-second.stdout.json"
  if [[ "$(sha256sum "$linear_model" | awk '{print $1}')" != "$linear_model_before_hash" ]]; then
    echo "installed ModelIR linear request creation mutated its source ModelIR" >&2
    exit 1
  fi
}

exercise_model_linear_request_create_surface
linear_request="$e2e_root/model-linear-request-create-first/analysis-request.json"
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

exercise_frame3d_member_add_surface() {
  local source_model="$repository_root/tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"
  local label added_directory request_directory run_directory
  for label in first second; do
    added_directory="$e2e_root/frame3d-member-add-$label"
    request_directory="$e2e_root/frame3d-member-add-$label-linear-request"
    run_directory="$e2e_root/frame3d-member-add-$label-linear-run"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-add-frame3d-member "$source_model" --node N3 \
      --coordinates 4 0 0 --element E2 --from-node N2 \
      --material M1 --section S1 --output-dir "$added_directory" \
      > "$e2e_root/frame3d-member-add-$label.stdout.json"
    test -s "$added_directory/model-ir.json"
    test -s "$added_directory/edit-receipt.json"
    grep -Fq '"schema_version":"structural-native-model-edit-receipt.v1"' \
      "$added_directory/edit-receipt.json"
    grep -Fq '"operation":"frame3d_member_add"' \
      "$added_directory/edit-receipt.json"
    grep -Fq '"node_id":"N3"' "$added_directory/edit-receipt.json"
    grep -Fq '"node_index":2' "$added_directory/edit-receipt.json"
    grep -Fq '"element_id":"E2"' "$added_directory/edit-receipt.json"
    grep -Fq '"element_index":1' "$added_directory/edit-receipt.json"
    grep -Fq '"element_type":"frame_3d"' \
      "$added_directory/edit-receipt.json"
    grep -Fq '"formulation":"euler_bernoulli_3d"' \
      "$added_directory/edit-receipt.json"
    grep -Fq '"node_ids":["N2","N3"]' \
      "$added_directory/edit-receipt.json"
    grep -Fq '"material_id":"M1"' "$added_directory/edit-receipt.json"
    grep -Fq '"section_id":"S1"' "$added_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' \
      "$added_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$added_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' \
      "$added_directory/edit-receipt.json"
    grep -Fq "\"source_input_sha256\":\"sha256:$source_before_hash\"" \
      "$added_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-add-frame3d-member.v1"' \
      "$added_directory/model-ir.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$added_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/frame3d-member-add-$label-validation.json"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" model-view \
      "$added_directory/model-ir.json" \
      > "$e2e_root/frame3d-member-add-$label-view.txt"
    grep -Fq 'nodes=3 elements=2' \
      "$e2e_root/frame3d-member-add-$label-view.txt"
    grep -Fq 'C++ semantic snapshot: verified' \
      "$e2e_root/frame3d-member-add-$label-view.txt"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$added_directory/model-ir.json" \
      --case added-frame3d-member-linear-c5 --load-pattern LC_WEAK \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/frame3d-member-add-$label-linear-request.stdout.json"
    grep -Fq '"cpp_linear_assembly_preflight_verified":true' \
      "$request_directory/request-receipt.json"
    grep -Fq '"execution_started":false' \
      "$request_directory/request-receipt.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$added_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$run_directory" \
      > "$e2e_root/frame3d-member-add-$label-linear-run.stdout.json"
    test -s "$run_directory/result-ir.json"
    test -s "$run_directory/result-recovery-ir.json"
    grep -Fq '"status":"completed"' "$run_directory/run-receipt.json"
    grep -Fq '"schema_version":"structural-sparse-linear-result-ir.v1"' \
      "$run_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$run_directory/result-ir.json"
    grep -Fq '"schema_version":"structural-model-ir-linear-result-recovery-ir.v1"' \
      "$run_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$run_directory/result-recovery-ir.json"
  done
  diff -r "$e2e_root/frame3d-member-add-first" \
    "$e2e_root/frame3d-member-add-second" \
    > "$e2e_root/frame3d-member-add-diff.txt"
  diff -r "$e2e_root/frame3d-member-add-first-linear-request" \
    "$e2e_root/frame3d-member-add-second-linear-request" \
    > "$e2e_root/frame3d-member-add-linear-request-diff.txt"
  diff -r "$e2e_root/frame3d-member-add-first-linear-run" \
    "$e2e_root/frame3d-member-add-second-linear-run" \
    > "$e2e_root/frame3d-member-add-linear-run-diff.txt"
  cmp "$e2e_root/frame3d-member-add-first.stdout.json" \
    "$e2e_root/frame3d-member-add-second.stdout.json"
  cmp "$e2e_root/frame3d-member-add-first-validation.json" \
    "$e2e_root/frame3d-member-add-second-validation.json"
  cmp "$e2e_root/frame3d-member-add-first-view.txt" \
    "$e2e_root/frame3d-member-add-second-view.txt"
  cmp "$e2e_root/frame3d-member-add-first-linear-request.stdout.json" \
    "$e2e_root/frame3d-member-add-second-linear-request.stdout.json"
  cmp "$e2e_root/frame3d-member-add-first-linear-run.stdout.json" \
    "$e2e_root/frame3d-member-add-second-linear-run.stdout.json"
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed frame3d-member addition mutated its source ModelIR" >&2
    exit 1
  fi
}
exercise_frame3d_member_add_surface

exercise_nodal_load_target_edit_surface() {
  local source_model="$e2e_root/frame3d-member-add-first/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"
  local label edit_directory request_directory direct_directory partial_directory
  local resumed_directory
  for label in first second; do
    edit_directory="$e2e_root/nodal-load-target-edit-$label"
    request_directory="$e2e_root/nodal-load-target-edit-$label-request"
    direct_directory="$e2e_root/nodal-load-target-edit-$label-direct"
    partial_directory="$e2e_root/nodal-load-target-edit-$label-partial"
    resumed_directory="$e2e_root/nodal-load-target-edit-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-edit-nodal-load-target "$source_model" \
      --load-pattern LC_WEAK --load L_WEAK_N2 --node N3 \
      --output-dir "$edit_directory" \
      > "$e2e_root/nodal-load-target-edit-$label.stdout.json"
    grep -Fq '"schema_version":"structural-native-model-edit-receipt.v1"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"operation":"nodal_load_target"' "$edit_directory/edit-receipt.json"
    grep -Fq '"load_pattern_id":"LC_WEAK"' "$edit_directory/edit-receipt.json"
    grep -Fq '"load_pattern_index":1' "$edit_directory/edit-receipt.json"
    grep -Fq '"analysis_type":"linear_static"' "$edit_directory/edit-receipt.json"
    grep -Fq '"nodal_load_id":"L_WEAK_N2"' "$edit_directory/edit-receipt.json"
    grep -Fq '"nodal_load_index":0' "$edit_directory/edit-receipt.json"
    grep -Fq '"previous_node_id":"N2"' "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_node_id":"N3"' "$edit_directory/edit-receipt.json"
    grep -Fq '"components_si":{"FX":0,"FY":-10000,"FZ":0,"MX":0,"MY":0,"MZ":0}' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"retained_source_id":"generated:L_WEAK_N2"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"retained_extensions":{}' "$edit_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' "$edit_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$edit_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' "$edit_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-edit-nodal-load-target.v1"' \
      "$edit_directory/model-ir.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$edit_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/nodal-load-target-edit-$label-validation.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$edit_directory/model-ir.json" \
      --case nodal-load-target-edit-c5 --load-pattern LC_WEAK \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/nodal-load-target-edit-$label-request.stdout.json"
    grep -Fq '"cpp_linear_assembly_preflight_verified":true' \
      "$request_directory/request-receipt.json"
    grep -Fq '"execution_started":false' "$request_directory/request-receipt.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/nodal-load-target-edit-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"active_dof_indices":[6,7,8,9,10,11,12,13,14,15,16,17]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[0,0,0,0,0,0,0,-10000,0,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 0 \
      > "$e2e_root/nodal-load-target-edit-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/nodal-load-target-edit-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/nodal-load-target-edit-$label-restart-diff.txt"
  done

  local suffix
  for suffix in '' -request -direct -partial -resumed; do
    diff -r "$e2e_root/nodal-load-target-edit-first$suffix" \
      "$e2e_root/nodal-load-target-edit-second$suffix" \
      > "$e2e_root/nodal-load-target-edit$suffix-diff.txt"
  done
  cmp "$e2e_root/nodal-load-target-edit-first.stdout.json" \
    "$e2e_root/nodal-load-target-edit-second.stdout.json"
  cmp "$e2e_root/nodal-load-target-edit-first-validation.json" \
    "$e2e_root/nodal-load-target-edit-second-validation.json"
  for suffix in request direct partial resumed; do
    cmp "$e2e_root/nodal-load-target-edit-first-$suffix.stdout.json" \
      "$e2e_root/nodal-load-target-edit-second-$suffix.stdout.json"
  done
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed nodal-load target edit mutated its source ModelIR" >&2
    exit 1
  fi

  local no_op_destination="$e2e_root/nodal-load-target-edit-no-op-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-edit-nodal-load-target "$source_model" --load-pattern LC_WEAK \
    --load L_WEAK_N2 --node N2 --output-dir "$no_op_destination" \
    > "$e2e_root/nodal-load-target-edit-no-op-rejected.stdout.json"; then
    echo "installed nodal-load target edit accepted a no-op" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_edit_nodal_load_target_no_change' \
    "$e2e_root/nodal-load-target-edit-no-op-rejected.stdout.json"
  test ! -e "$no_op_destination"

  local missing_node_destination="$e2e_root/nodal-load-target-edit-node-missing-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-edit-nodal-load-target "$source_model" --load-pattern LC_WEAK \
    --load L_WEAK_N2 --node N_MISSING --output-dir "$missing_node_destination" \
    > "$e2e_root/nodal-load-target-edit-node-missing-rejected.stdout.json"; then
    echo "installed nodal-load target edit accepted a missing node" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_edit_nodal_load_target_node_missing' \
    "$e2e_root/nodal-load-target-edit-node-missing-rejected.stdout.json"
  test ! -e "$missing_node_destination"

  local missing_load_destination="$e2e_root/nodal-load-target-edit-load-missing-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-edit-nodal-load-target "$source_model" --load-pattern LC_WEAK \
    --load L_MISSING --node N3 --output-dir "$missing_load_destination" \
    > "$e2e_root/nodal-load-target-edit-load-missing-rejected.stdout.json"; then
    echo "installed nodal-load target edit accepted a missing load" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_edit_nodal_load_target_load_missing' \
    "$e2e_root/nodal-load-target-edit-load-missing-rejected.stdout.json"
  test ! -e "$missing_load_destination"

  local missing_pattern_destination="$e2e_root/nodal-load-target-edit-pattern-missing-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-edit-nodal-load-target "$source_model" --load-pattern LC_MISSING \
    --load L_WEAK_N2 --node N3 --output-dir "$missing_pattern_destination" \
    > "$e2e_root/nodal-load-target-edit-pattern-missing-rejected.stdout.json"; then
    echo "installed nodal-load target edit accepted a missing pattern" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_edit_nodal_load_target_pattern_missing' \
    "$e2e_root/nodal-load-target-edit-pattern-missing-rejected.stdout.json"
  test ! -e "$missing_pattern_destination"
}
exercise_nodal_load_target_edit_surface

exercise_nodal_load_add_surface() {
  local source_model="$e2e_root/frame3d-member-add-first/model-ir.json"
  local source_before_hash baseline_recovery baseline_maximum_displacement
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"
  baseline_recovery="$e2e_root/frame3d-member-add-first-linear-run/result-recovery-ir.json"
  baseline_maximum_displacement="$(sed -n 's/.*"maximum_absolute_displacement":\([^,}]*\).*/\1/p' "$baseline_recovery")"
  if [[ -z "$baseline_maximum_displacement" ]]; then
    echo "installed frame3d-member baseline recovery has no displacement summary" >&2
    exit 1
  fi
  local label added_directory request_directory run_directory loaded_maximum_displacement
  for label in first second; do
    added_directory="$e2e_root/nodal-load-add-$label"
    request_directory="$e2e_root/nodal-load-add-$label-linear-request"
    run_directory="$e2e_root/nodal-load-add-$label-linear-run"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-add-nodal-load "$source_model" --load-pattern LC_WEAK \
      --load L_WEAK_N3 --node N3 --components 0 -1000 0 0 0 0 \
      --output-dir "$added_directory" \
      > "$e2e_root/nodal-load-add-$label.stdout.json"
    test -s "$added_directory/model-ir.json"
    test -s "$added_directory/edit-receipt.json"
    grep -Fq '"schema_version":"structural-native-model-edit-receipt.v1"' \
      "$added_directory/edit-receipt.json"
    grep -Fq '"operation":"nodal_load_add"' \
      "$added_directory/edit-receipt.json"
    grep -Fq '"load_pattern_id":"LC_WEAK"' \
      "$added_directory/edit-receipt.json"
    grep -Fq '"load_pattern_index":1' "$added_directory/edit-receipt.json"
    grep -Fq '"analysis_type":"linear_static"' \
      "$added_directory/edit-receipt.json"
    grep -Fq '"nodal_load_id":"L_WEAK_N3"' \
      "$added_directory/edit-receipt.json"
    grep -Fq '"nodal_load_index":1' "$added_directory/edit-receipt.json"
    grep -Fq '"node_id":"N3"' "$added_directory/edit-receipt.json"
    grep -Fq '"components_si":{"FX":0,"FY":-1000,"FZ":0,"MX":0,"MY":0,"MZ":0}' \
      "$added_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' \
      "$added_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$added_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' \
      "$added_directory/edit-receipt.json"
    grep -Fq "\"source_input_sha256\":\"sha256:$source_before_hash\"" \
      "$added_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-add-nodal-load.v1"' \
      "$added_directory/model-ir.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$added_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/nodal-load-add-$label-validation.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$added_directory/model-ir.json" \
      --case added-nodal-load-linear-c5 --load-pattern LC_WEAK \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/nodal-load-add-$label-linear-request.stdout.json"
    grep -Fq '"cpp_linear_assembly_preflight_verified":true' \
      "$request_directory/request-receipt.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$added_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$run_directory" \
      > "$e2e_root/nodal-load-add-$label-linear-run.stdout.json"
    grep -Fq '"status":"completed"' "$run_directory/run-receipt.json"
    grep -Fq '"active_external_load":[0,-10000,0,0,0,0,0,-1000,0,0,0,0]' \
      "$run_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$run_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$run_directory/result-recovery-ir.json"
    loaded_maximum_displacement="$(sed -n 's/.*"maximum_absolute_displacement":\([^,}]*\).*/\1/p' "$run_directory/result-recovery-ir.json")"
    if [[ -z "$loaded_maximum_displacement" \
      || "$loaded_maximum_displacement" == "$baseline_maximum_displacement" ]]; then
      echo "installed nodal-load addition did not change recovered displacement" >&2
      exit 1
    fi
  done
  diff -r "$e2e_root/nodal-load-add-first" \
    "$e2e_root/nodal-load-add-second" \
    > "$e2e_root/nodal-load-add-diff.txt"
  diff -r "$e2e_root/nodal-load-add-first-linear-request" \
    "$e2e_root/nodal-load-add-second-linear-request" \
    > "$e2e_root/nodal-load-add-linear-request-diff.txt"
  diff -r "$e2e_root/nodal-load-add-first-linear-run" \
    "$e2e_root/nodal-load-add-second-linear-run" \
    > "$e2e_root/nodal-load-add-linear-run-diff.txt"
  cmp "$e2e_root/nodal-load-add-first.stdout.json" \
    "$e2e_root/nodal-load-add-second.stdout.json"
  cmp "$e2e_root/nodal-load-add-first-validation.json" \
    "$e2e_root/nodal-load-add-second-validation.json"
  cmp "$e2e_root/nodal-load-add-first-linear-request.stdout.json" \
    "$e2e_root/nodal-load-add-second-linear-request.stdout.json"
  cmp "$e2e_root/nodal-load-add-first-linear-run.stdout.json" \
    "$e2e_root/nodal-load-add-second-linear-run.stdout.json"
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed nodal-load addition mutated its source ModelIR" >&2
    exit 1
  fi
}
exercise_nodal_load_add_surface

exercise_nodal_load_deletion_surface() {
  local source_model="$e2e_root/nodal-load-add-first/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"

  local label delete_directory request_directory direct_directory
  local partial_directory resumed_directory
  for label in first second; do
    delete_directory="$e2e_root/nodal-load-delete-$label"
    request_directory="$e2e_root/nodal-load-delete-$label-request"
    direct_directory="$e2e_root/nodal-load-delete-$label-direct"
    partial_directory="$e2e_root/nodal-load-delete-$label-partial"
    resumed_directory="$e2e_root/nodal-load-delete-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-delete-nodal-load "$source_model" \
      --load-pattern LC_WEAK --load L_WEAK_N3 --output-dir "$delete_directory" \
      > "$e2e_root/nodal-load-delete-$label.stdout.json"
    grep -Fq '"operation":"nodal_load_delete"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"load_pattern_id":"LC_WEAK"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"load_pattern_index":1' "$delete_directory/edit-receipt.json"
    grep -Fq '"analysis_type":"linear_static"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_nodal_load_id":"L_WEAK_N3"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_nodal_load_index":1' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_node_id":"N3"' "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_components_si":{"FX":0,"FY":-1000,"FZ":0,"MX":0,"MY":0,"MZ":0}' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$delete_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-delete-nodal-load.v1"' \
      "$delete_directory/model-ir.json"
    if grep -Fq '"id":"L_WEAK_N3"' "$delete_directory/model-ir.json"; then
      echo "installed nodal-load deletion retained L_WEAK_N3" >&2
      exit 1
    fi
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$delete_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/nodal-load-delete-$label-validation.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$delete_directory/model-ir.json" \
      --case nodal-load-delete-c5 --load-pattern LC_WEAK \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/nodal-load-delete-$label-request.stdout.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/nodal-load-delete-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"active_dof_indices":[6,7,8,9,10,11,12,13,14,15,16,17]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[0,-10000,0,0,0,0,0,0,0,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"recovery_element_types":[1,1]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"recovery_offsets":[0,12,24]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 1 \
      > "$e2e_root/nodal-load-delete-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/nodal-load-delete-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/nodal-load-delete-$label-restart-diff.txt"
  done

  local suffix diff_label
  for suffix in '' -request -direct -partial -resumed; do
    diff_label="${suffix#-}"
    if [[ -z "$diff_label" ]]; then
      diff_label=model
    fi
    diff -r "$e2e_root/nodal-load-delete-first$suffix" \
      "$e2e_root/nodal-load-delete-second$suffix" \
      > "$e2e_root/nodal-load-delete-$diff_label-diff.txt"
  done
  for suffix in '' -request -direct -partial -resumed; do
    cmp "$e2e_root/nodal-load-delete-first$suffix.stdout.json" \
      "$e2e_root/nodal-load-delete-second$suffix.stdout.json"
  done
  cmp "$e2e_root/nodal-load-delete-first-validation.json" \
    "$e2e_root/nodal-load-delete-second-validation.json"
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed nodal-load deletion mutated its source ModelIR" >&2
    exit 1
  fi

  local rejected_destination="$e2e_root/nodal-load-delete-nonterminal-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-delete-nodal-load "$source_model" --load-pattern LC_WEAK --load L_WEAK_N2 \
    --output-dir "$rejected_destination" \
    > "$e2e_root/nodal-load-delete-nonterminal-rejected.stdout.json"; then
    echo "installed nodal-load deletion accepted a nonterminal row" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_delete_nodal_load_not_terminal' \
    "$e2e_root/nodal-load-delete-nonterminal-rejected.stdout.json"
  test ! -e "$rejected_destination"
}
exercise_nodal_load_deletion_surface

exercise_fixed_constraint_add_surface() {
  local source_model="$e2e_root/nodal-load-add-first/model-ir.json"
  local source_before_hash baseline_recovery baseline_maximum_displacement
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"
  baseline_recovery="$e2e_root/nodal-load-add-first-linear-run/result-recovery-ir.json"
  baseline_maximum_displacement="$(sed -n 's/.*"maximum_absolute_displacement":\([^,}]*\).*/\1/p' "$baseline_recovery")"
  if [[ -z "$baseline_maximum_displacement" ]]; then
    echo "installed nodal-load baseline recovery has no displacement summary" >&2
    exit 1
  fi
  local label added_directory request_directory run_directory supported_maximum_displacement
  for label in first second; do
    added_directory="$e2e_root/fixed-constraint-add-$label"
    request_directory="$e2e_root/fixed-constraint-add-$label-linear-request"
    run_directory="$e2e_root/fixed-constraint-add-$label-linear-run"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-add-fixed-constraint "$source_model" --constraint BC_N3 --node N3 \
      --output-dir "$added_directory" \
      > "$e2e_root/fixed-constraint-add-$label.stdout.json"
    test -s "$added_directory/model-ir.json"
    test -s "$added_directory/edit-receipt.json"
    grep -Fq '"schema_version":"structural-native-model-edit-receipt.v1"' \
      "$added_directory/edit-receipt.json"
    grep -Fq '"operation":"fixed_constraint_add"' \
      "$added_directory/edit-receipt.json"
    grep -Fq '"constraint_id":"BC_N3"' "$added_directory/edit-receipt.json"
    grep -Fq '"constraint_index":1' "$added_directory/edit-receipt.json"
    grep -Fq '"constraint_type":"fixed_dofs"' \
      "$added_directory/edit-receipt.json"
    grep -Fq '"node_id":"N3"' "$added_directory/edit-receipt.json"
    grep -Fq '"dofs":["UX","UY","UZ","RX","RY","RZ"]' \
      "$added_directory/edit-receipt.json"
    grep -Fq '"prescribed_values_si":{"RX":0,"RY":0,"RZ":0,"UX":0,"UY":0,"UZ":0}' \
      "$added_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' \
      "$added_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$added_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' \
      "$added_directory/edit-receipt.json"
    grep -Fq "\"source_input_sha256\":\"sha256:$source_before_hash\"" \
      "$added_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-add-fixed-constraint.v1"' \
      "$added_directory/model-ir.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$added_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/fixed-constraint-add-$label-validation.json"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" model-view \
      "$added_directory/model-ir.json" \
      > "$e2e_root/fixed-constraint-add-$label-view.txt"
    grep -Fq 'constraints=2' "$e2e_root/fixed-constraint-add-$label-view.txt"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$added_directory/model-ir.json" \
      --case added-fixed-constraint-linear-c5 --load-pattern LC_WEAK \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/fixed-constraint-add-$label-linear-request.stdout.json"
    grep -Fq '"cpp_linear_assembly_preflight_verified":true' \
      "$request_directory/request-receipt.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$added_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$run_directory" \
      > "$e2e_root/fixed-constraint-add-$label-linear-run.stdout.json"
    grep -Fq '"status":"completed"' "$run_directory/run-receipt.json"
    grep -Fq '"active_dof_indices":[6,7,8,9,10,11]' \
      "$run_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[0,-10000,0,0,0,0]' \
      "$run_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$run_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$run_directory/result-recovery-ir.json"
    supported_maximum_displacement="$(sed -n 's/.*"maximum_absolute_displacement":\([^,}]*\).*/\1/p' "$run_directory/result-recovery-ir.json")"
    if [[ -z "$supported_maximum_displacement" \
      || "$supported_maximum_displacement" == "$baseline_maximum_displacement" ]]; then
      echo "installed fixed-constraint addition did not change recovered displacement" >&2
      exit 1
    fi
  done
  diff -r "$e2e_root/fixed-constraint-add-first" \
    "$e2e_root/fixed-constraint-add-second" \
    > "$e2e_root/fixed-constraint-add-diff.txt"
  diff -r "$e2e_root/fixed-constraint-add-first-linear-request" \
    "$e2e_root/fixed-constraint-add-second-linear-request" \
    > "$e2e_root/fixed-constraint-add-linear-request-diff.txt"
  diff -r "$e2e_root/fixed-constraint-add-first-linear-run" \
    "$e2e_root/fixed-constraint-add-second-linear-run" \
    > "$e2e_root/fixed-constraint-add-linear-run-diff.txt"
  cmp "$e2e_root/fixed-constraint-add-first.stdout.json" \
    "$e2e_root/fixed-constraint-add-second.stdout.json"
  cmp "$e2e_root/fixed-constraint-add-first-validation.json" \
    "$e2e_root/fixed-constraint-add-second-validation.json"
  cmp "$e2e_root/fixed-constraint-add-first-view.txt" \
    "$e2e_root/fixed-constraint-add-second-view.txt"
  cmp "$e2e_root/fixed-constraint-add-first-linear-request.stdout.json" \
    "$e2e_root/fixed-constraint-add-second-linear-request.stdout.json"
  cmp "$e2e_root/fixed-constraint-add-first-linear-run.stdout.json" \
    "$e2e_root/fixed-constraint-add-second-linear-run.stdout.json"
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed fixed-constraint addition mutated its source ModelIR" >&2
    exit 1
  fi
}
exercise_fixed_constraint_add_surface

exercise_constraint_target_edit_surface() {
  local source_model="$e2e_root/fixed-constraint-add-first/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"
  local label edit_directory request_directory direct_directory partial_directory
  local resumed_directory
  for label in first second; do
    edit_directory="$e2e_root/constraint-target-edit-$label"
    request_directory="$e2e_root/constraint-target-edit-$label-request"
    direct_directory="$e2e_root/constraint-target-edit-$label-direct"
    partial_directory="$e2e_root/constraint-target-edit-$label-partial"
    resumed_directory="$e2e_root/constraint-target-edit-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-edit-constraint-target "$source_model" \
      --constraint BC_N3 --node N2 --output-dir "$edit_directory" \
      > "$e2e_root/constraint-target-edit-$label.stdout.json"
    grep -Fq '"schema_version":"structural-native-model-edit-receipt.v1"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"operation":"constraint_target"' "$edit_directory/edit-receipt.json"
    grep -Fq '"constraint_id":"BC_N3"' "$edit_directory/edit-receipt.json"
    grep -Fq '"constraint_index":1' "$edit_directory/edit-receipt.json"
    grep -Fq '"constraint_type":"fixed_dofs"' "$edit_directory/edit-receipt.json"
    grep -Fq '"previous_node_id":"N3"' "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_node_id":"N2"' "$edit_directory/edit-receipt.json"
    grep -Fq '"dofs":["UX","UY","UZ","RX","RY","RZ"]' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"prescribed_values_si":{"RX":0,"RY":0,"RZ":0,"UX":0,"UY":0,"UZ":0}' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"retained_source_id":null' "$edit_directory/edit-receipt.json"
    grep -Fq '"retained_extensions":{}' "$edit_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' "$edit_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$edit_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' "$edit_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-edit-constraint-target.v1"' \
      "$edit_directory/model-ir.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$edit_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/constraint-target-edit-$label-validation.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$edit_directory/model-ir.json" \
      --case constraint-target-edit-c5 --load-pattern LC_WEAK \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/constraint-target-edit-$label-request.stdout.json"
    grep -Fq '"cpp_linear_assembly_preflight_verified":true' \
      "$request_directory/request-receipt.json"
    grep -Fq '"execution_started":false' "$request_directory/request-receipt.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/constraint-target-edit-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"active_dof_indices":[12,13,14,15,16,17]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[0,-1000,0,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 0 \
      > "$e2e_root/constraint-target-edit-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/constraint-target-edit-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/constraint-target-edit-$label-restart-diff.txt"
  done

  local suffix
  for suffix in '' -request -direct -partial -resumed; do
    diff -r "$e2e_root/constraint-target-edit-first$suffix" \
      "$e2e_root/constraint-target-edit-second$suffix" \
      > "$e2e_root/constraint-target-edit$suffix-diff.txt"
  done
  cmp "$e2e_root/constraint-target-edit-first.stdout.json" \
    "$e2e_root/constraint-target-edit-second.stdout.json"
  cmp "$e2e_root/constraint-target-edit-first-validation.json" \
    "$e2e_root/constraint-target-edit-second-validation.json"
  for suffix in request direct partial resumed; do
    cmp "$e2e_root/constraint-target-edit-first-$suffix.stdout.json" \
      "$e2e_root/constraint-target-edit-second-$suffix.stdout.json"
  done
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed constraint target edit mutated its source ModelIR" >&2
    exit 1
  fi

  local no_op_destination="$e2e_root/constraint-target-edit-no-op-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-edit-constraint-target "$source_model" --constraint BC_N3 --node N3 \
    --output-dir "$no_op_destination" \
    > "$e2e_root/constraint-target-edit-no-op-rejected.stdout.json"; then
    echo "installed constraint target edit accepted a no-op" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_edit_constraint_target_no_change' \
    "$e2e_root/constraint-target-edit-no-op-rejected.stdout.json"
  test ! -e "$no_op_destination"

  local missing_node_destination="$e2e_root/constraint-target-edit-node-missing-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-edit-constraint-target "$source_model" --constraint BC_N3 --node N_MISSING \
    --output-dir "$missing_node_destination" \
    > "$e2e_root/constraint-target-edit-node-missing-rejected.stdout.json"; then
    echo "installed constraint target edit accepted a missing node" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_edit_constraint_target_node_missing' \
    "$e2e_root/constraint-target-edit-node-missing-rejected.stdout.json"
  test ! -e "$missing_node_destination"

  local missing_constraint_destination="$e2e_root/constraint-target-edit-constraint-missing-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-edit-constraint-target "$source_model" --constraint BC_MISSING --node N2 \
    --output-dir "$missing_constraint_destination" \
    > "$e2e_root/constraint-target-edit-constraint-missing-rejected.stdout.json"; then
    echo "installed constraint target edit accepted a missing constraint" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_edit_constraint_target_constraint_missing' \
    "$e2e_root/constraint-target-edit-constraint-missing-rejected.stdout.json"
  test ! -e "$missing_constraint_destination"

  local overlap_destination="$e2e_root/constraint-target-edit-overlap-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-edit-constraint-target "$source_model" --constraint BC_N3 --node N1 \
    --output-dir "$overlap_destination" \
    > "$e2e_root/constraint-target-edit-overlap-rejected.stdout.json"; then
    echo "installed constraint target edit accepted overlapping restrained DOFs" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_edit_constraint_target_dof_overlap' \
    "$e2e_root/constraint-target-edit-overlap-rejected.stdout.json"
  test ! -e "$overlap_destination"
}
exercise_constraint_target_edit_surface

exercise_fixed_constraint_dof_delete_surface() {
  local source_model="$e2e_root/constraint-target-edit-first/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"
  local label edit_directory request_directory direct_directory partial_directory
  local resumed_directory
  for label in first second; do
    edit_directory="$e2e_root/fixed-constraint-dof-delete-$label"
    request_directory="$e2e_root/fixed-constraint-dof-delete-$label-request"
    direct_directory="$e2e_root/fixed-constraint-dof-delete-$label-direct"
    partial_directory="$e2e_root/fixed-constraint-dof-delete-$label-partial"
    resumed_directory="$e2e_root/fixed-constraint-dof-delete-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-delete-fixed-constraint-dof "$source_model" \
      --constraint BC_N3 --dof RZ --output-dir "$edit_directory" \
      > "$e2e_root/fixed-constraint-dof-delete-$label.stdout.json"
    grep -Fq '"schema_version":"structural-native-model-edit-receipt.v1"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"operation":"fixed_constraint_dof_delete"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"constraint_id":"BC_N3"' "$edit_directory/edit-receipt.json"
    grep -Fq '"constraint_index":1' "$edit_directory/edit-receipt.json"
    grep -Fq '"constraint_type":"fixed_dofs"' "$edit_directory/edit-receipt.json"
    grep -Fq '"node_id":"N2"' "$edit_directory/edit-receipt.json"
    grep -Fq '"removed_dof":"RZ"' "$edit_directory/edit-receipt.json"
    grep -Fq '"removed_prescribed_value_explicit":true' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"removed_prescribed_value_si":0' "$edit_directory/edit-receipt.json"
    grep -Fq '"retained_dofs":["UX","UY","UZ","RX","RY"]' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"retained_prescribed_values_si":{"RX":0,"RY":0,"UX":0,"UY":0,"UZ":0}' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"retained_source_id":null' "$edit_directory/edit-receipt.json"
    grep -Fq '"retained_extensions":{}' "$edit_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' "$edit_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$edit_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' "$edit_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-delete-fixed-constraint-dof.v1"' \
      "$edit_directory/model-ir.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$edit_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/fixed-constraint-dof-delete-$label-validation.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$edit_directory/model-ir.json" \
      --case fixed-constraint-dof-delete-c5 --load-pattern LC_WEAK \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/fixed-constraint-dof-delete-$label-request.stdout.json"
    grep -Fq '"cpp_linear_assembly_preflight_verified":true' \
      "$request_directory/request-receipt.json"
    grep -Fq '"execution_started":false' "$request_directory/request-receipt.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/fixed-constraint-dof-delete-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"active_dof_indices":[11,12,13,14,15,16,17]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[0,0,-1000,0,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 0 \
      > "$e2e_root/fixed-constraint-dof-delete-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/fixed-constraint-dof-delete-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/fixed-constraint-dof-delete-$label-restart-diff.txt"
  done

  local suffix
  for suffix in '' -request -direct -partial -resumed; do
    diff -r "$e2e_root/fixed-constraint-dof-delete-first$suffix" \
      "$e2e_root/fixed-constraint-dof-delete-second$suffix" \
      > "$e2e_root/fixed-constraint-dof-delete$suffix-diff.txt"
  done
  cmp "$e2e_root/fixed-constraint-dof-delete-first.stdout.json" \
    "$e2e_root/fixed-constraint-dof-delete-second.stdout.json"
  cmp "$e2e_root/fixed-constraint-dof-delete-first-validation.json" \
    "$e2e_root/fixed-constraint-dof-delete-second-validation.json"
  for suffix in request direct partial resumed; do
    cmp "$e2e_root/fixed-constraint-dof-delete-first-$suffix.stdout.json" \
      "$e2e_root/fixed-constraint-dof-delete-second-$suffix.stdout.json"
  done
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed fixed-constraint DOF deletion mutated its source ModelIR" >&2
    exit 1
  fi

  local missing_destination="$e2e_root/fixed-constraint-dof-delete-missing-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-delete-fixed-constraint-dof "$source_model" --constraint BC_MISSING --dof RZ \
    --output-dir "$missing_destination" \
    > "$e2e_root/fixed-constraint-dof-delete-missing-rejected.stdout.json"; then
    echo "installed fixed-constraint DOF deletion accepted a missing constraint" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_delete_fixed_constraint_dof_constraint_missing' \
    "$e2e_root/fixed-constraint-dof-delete-missing-rejected.stdout.json"
  test ! -e "$missing_destination"

  local unrestrained_destination="$e2e_root/fixed-constraint-dof-delete-unrestrained-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-delete-fixed-constraint-dof \
    "$e2e_root/fixed-constraint-dof-delete-first/model-ir.json" \
    --constraint BC_N3 --dof RZ --output-dir "$unrestrained_destination" \
    > "$e2e_root/fixed-constraint-dof-delete-unrestrained-rejected.stdout.json"; then
    echo "installed fixed-constraint DOF deletion accepted an unrestrained DOF" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_delete_fixed_constraint_dof_not_restrained' \
    "$e2e_root/fixed-constraint-dof-delete-unrestrained-rejected.stdout.json"
  test ! -e "$unrestrained_destination"
}
exercise_fixed_constraint_dof_delete_surface

exercise_fixed_constraint_dof_add_surface() {
  local source_model="$e2e_root/fixed-constraint-dof-delete-first/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"
  local label edit_directory request_directory direct_directory partial_directory
  local resumed_directory
  for label in first second; do
    edit_directory="$e2e_root/fixed-constraint-dof-add-$label"
    request_directory="$e2e_root/fixed-constraint-dof-add-$label-request"
    direct_directory="$e2e_root/fixed-constraint-dof-add-$label-direct"
    partial_directory="$e2e_root/fixed-constraint-dof-add-$label-partial"
    resumed_directory="$e2e_root/fixed-constraint-dof-add-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-add-fixed-constraint-dof "$source_model" \
      --constraint BC_N3 --dof RZ --value 0 --output-dir "$edit_directory" \
      > "$e2e_root/fixed-constraint-dof-add-$label.stdout.json"
    grep -Fq '"schema_version":"structural-native-model-edit-receipt.v1"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"operation":"fixed_constraint_dof_add"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"constraint_id":"BC_N3"' "$edit_directory/edit-receipt.json"
    grep -Fq '"constraint_index":1' "$edit_directory/edit-receipt.json"
    grep -Fq '"constraint_type":"fixed_dofs"' "$edit_directory/edit-receipt.json"
    grep -Fq '"node_id":"N2"' "$edit_directory/edit-receipt.json"
    grep -Fq '"added_dof":"RZ"' "$edit_directory/edit-receipt.json"
    grep -Fq '"added_prescribed_value_si":0' "$edit_directory/edit-receipt.json"
    grep -Fq '"unit":"rad"' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_dofs":["UX","UY","UZ","RX","RY"]' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"source_prescribed_values_si":{"RX":0,"RY":0,"UX":0,"UY":0,"UZ":0}' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_dofs":["UX","UY","UZ","RX","RY","RZ"]' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_prescribed_values_si":{"RX":0,"RY":0,"RZ":0,"UX":0,"UY":0,"UZ":0}' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"retained_source_id":null' "$edit_directory/edit-receipt.json"
    grep -Fq '"retained_extensions":{}' "$edit_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' "$edit_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$edit_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' "$edit_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-add-fixed-constraint-dof.v1"' \
      "$edit_directory/model-ir.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$edit_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/fixed-constraint-dof-add-$label-validation.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$edit_directory/model-ir.json" \
      --case fixed-constraint-dof-add-c5 --load-pattern LC_WEAK \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/fixed-constraint-dof-add-$label-request.stdout.json"
    grep -Fq '"cpp_linear_assembly_preflight_verified":true' \
      "$request_directory/request-receipt.json"
    grep -Fq '"execution_started":false' "$request_directory/request-receipt.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/fixed-constraint-dof-add-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"active_dof_indices":[12,13,14,15,16,17]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[0,-1000,0,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 0 \
      > "$e2e_root/fixed-constraint-dof-add-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/fixed-constraint-dof-add-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/fixed-constraint-dof-add-$label-restart-diff.txt"
  done

  local suffix
  for suffix in '' -request -direct -partial -resumed; do
    diff -r "$e2e_root/fixed-constraint-dof-add-first$suffix" \
      "$e2e_root/fixed-constraint-dof-add-second$suffix" \
      > "$e2e_root/fixed-constraint-dof-add$suffix-diff.txt"
  done
  cmp "$e2e_root/fixed-constraint-dof-add-first.stdout.json" \
    "$e2e_root/fixed-constraint-dof-add-second.stdout.json"
  cmp "$e2e_root/fixed-constraint-dof-add-first-validation.json" \
    "$e2e_root/fixed-constraint-dof-add-second-validation.json"
  for suffix in request direct partial resumed; do
    cmp "$e2e_root/fixed-constraint-dof-add-first-$suffix.stdout.json" \
      "$e2e_root/fixed-constraint-dof-add-second-$suffix.stdout.json"
  done
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed fixed-constraint DOF addition mutated its source ModelIR" >&2
    exit 1
  fi

  local missing_destination="$e2e_root/fixed-constraint-dof-add-missing-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-add-fixed-constraint-dof "$source_model" --constraint BC_MISSING --dof RZ --value 0 \
    --output-dir "$missing_destination" \
    > "$e2e_root/fixed-constraint-dof-add-missing-rejected.stdout.json"; then
    echo "installed fixed-constraint DOF addition accepted a missing constraint" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_add_fixed_constraint_dof_constraint_missing' \
    "$e2e_root/fixed-constraint-dof-add-missing-rejected.stdout.json"
  test ! -e "$missing_destination"

  local restrained_destination="$e2e_root/fixed-constraint-dof-add-restrained-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-add-fixed-constraint-dof \
    "$e2e_root/fixed-constraint-dof-add-first/model-ir.json" \
    --constraint BC_N3 --dof RZ --value 0 --output-dir "$restrained_destination" \
    > "$e2e_root/fixed-constraint-dof-add-restrained-rejected.stdout.json"; then
    echo "installed fixed-constraint DOF addition accepted an already restrained DOF" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_add_fixed_constraint_dof_already_restrained' \
    "$e2e_root/fixed-constraint-dof-add-restrained-rejected.stdout.json"
  test ! -e "$restrained_destination"
}
exercise_fixed_constraint_dof_add_surface

exercise_fixed_constraint_dof_reorder_surface() {
  local source_model="$e2e_root/fixed-constraint-dof-add-first/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"
  local label edit_directory request_directory direct_directory partial_directory
  local resumed_directory
  for label in first second; do
    edit_directory="$e2e_root/fixed-constraint-dof-reorder-$label"
    request_directory="$e2e_root/fixed-constraint-dof-reorder-$label-request"
    direct_directory="$e2e_root/fixed-constraint-dof-reorder-$label-direct"
    partial_directory="$e2e_root/fixed-constraint-dof-reorder-$label-partial"
    resumed_directory="$e2e_root/fixed-constraint-dof-reorder-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-reorder-fixed-constraint-dof "$source_model" \
      --constraint BC_N3 --dof RZ --to-index 0 --output-dir "$edit_directory" \
      > "$e2e_root/fixed-constraint-dof-reorder-$label.stdout.json"
    grep -Fq '"schema_version":"structural-native-model-edit-receipt.v1"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"operation":"fixed_constraint_dof_reorder"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"constraint_id":"BC_N3"' "$edit_directory/edit-receipt.json"
    grep -Fq '"constraint_index":1' "$edit_directory/edit-receipt.json"
    grep -Fq '"constraint_type":"fixed_dofs"' "$edit_directory/edit-receipt.json"
    grep -Fq '"node_id":"N2"' "$edit_directory/edit-receipt.json"
    grep -Fq '"moved_dof":"RZ"' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_dof_index":5' "$edit_directory/edit-receipt.json"
    grep -Fq '"target_dof_index":0' "$edit_directory/edit-receipt.json"
    grep -Fq '"prescribed_value_explicit":true' "$edit_directory/edit-receipt.json"
    grep -Fq '"prescribed_value_si":0' "$edit_directory/edit-receipt.json"
    grep -Fq '"unit":"rad"' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_dofs":["UX","UY","UZ","RX","RY","RZ"]' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_dofs":["RZ","UX","UY","UZ","RX","RY"]' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"retained_prescribed_values_si":{"RX":0,"RY":0,"RZ":0,"UX":0,"UY":0,"UZ":0}' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"retained_source_id":null' "$edit_directory/edit-receipt.json"
    grep -Fq '"retained_extensions":{}' "$edit_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' "$edit_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$edit_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' "$edit_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-reorder-fixed-constraint-dof.v1"' \
      "$edit_directory/model-ir.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$edit_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/fixed-constraint-dof-reorder-$label-validation.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$edit_directory/model-ir.json" \
      --case fixed-constraint-dof-reorder-c5 --load-pattern LC_WEAK \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/fixed-constraint-dof-reorder-$label-request.stdout.json"
    grep -Fq '"cpp_linear_assembly_preflight_verified":true' \
      "$request_directory/request-receipt.json"
    grep -Fq '"execution_started":false' "$request_directory/request-receipt.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/fixed-constraint-dof-reorder-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"active_dof_indices":[12,13,14,15,16,17]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[0,-1000,0,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 0 \
      > "$e2e_root/fixed-constraint-dof-reorder-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/fixed-constraint-dof-reorder-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/fixed-constraint-dof-reorder-$label-restart-diff.txt"
  done

  local suffix
  for suffix in '' -request -direct -partial -resumed; do
    diff -r "$e2e_root/fixed-constraint-dof-reorder-first$suffix" \
      "$e2e_root/fixed-constraint-dof-reorder-second$suffix" \
      > "$e2e_root/fixed-constraint-dof-reorder$suffix-diff.txt"
  done
  cmp "$e2e_root/fixed-constraint-dof-reorder-first.stdout.json" \
    "$e2e_root/fixed-constraint-dof-reorder-second.stdout.json"
  cmp "$e2e_root/fixed-constraint-dof-reorder-first-validation.json" \
    "$e2e_root/fixed-constraint-dof-reorder-second-validation.json"
  for suffix in request direct partial resumed; do
    cmp "$e2e_root/fixed-constraint-dof-reorder-first-$suffix.stdout.json" \
      "$e2e_root/fixed-constraint-dof-reorder-second-$suffix.stdout.json"
  done
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed fixed-constraint DOF reorder mutated its source ModelIR" >&2
    exit 1
  fi

  local missing_destination="$e2e_root/fixed-constraint-dof-reorder-missing-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-reorder-fixed-constraint-dof "$source_model" \
    --constraint BC_MISSING --dof RZ --to-index 0 --output-dir "$missing_destination" \
    > "$e2e_root/fixed-constraint-dof-reorder-missing-rejected.stdout.json"; then
    echo "installed fixed-constraint DOF reorder accepted a missing constraint" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_reorder_fixed_constraint_dof_constraint_missing' \
    "$e2e_root/fixed-constraint-dof-reorder-missing-rejected.stdout.json"
  test ! -e "$missing_destination"

  local unrestrained_destination="$e2e_root/fixed-constraint-dof-reorder-unrestrained-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-reorder-fixed-constraint-dof \
    "$e2e_root/fixed-constraint-dof-delete-first/model-ir.json" \
    --constraint BC_N3 --dof RZ --to-index 0 --output-dir "$unrestrained_destination" \
    > "$e2e_root/fixed-constraint-dof-reorder-unrestrained-rejected.stdout.json"; then
    echo "installed fixed-constraint DOF reorder accepted an unrestrained DOF" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_reorder_fixed_constraint_dof_not_restrained' \
    "$e2e_root/fixed-constraint-dof-reorder-unrestrained-rejected.stdout.json"
  test ! -e "$unrestrained_destination"

  local no_op_destination="$e2e_root/fixed-constraint-dof-reorder-no-op-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-reorder-fixed-constraint-dof "$source_model" \
    --constraint BC_N3 --dof RZ --to-index 5 --output-dir "$no_op_destination" \
    > "$e2e_root/fixed-constraint-dof-reorder-no-op-rejected.stdout.json"; then
    echo "installed fixed-constraint DOF reorder accepted a no-op" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_edit_no_change' \
    "$e2e_root/fixed-constraint-dof-reorder-no-op-rejected.stdout.json"
  test ! -e "$no_op_destination"

  local index_destination="$e2e_root/fixed-constraint-dof-reorder-index-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-reorder-fixed-constraint-dof "$source_model" \
    --constraint BC_N3 --dof RZ --to-index 6 --output-dir "$index_destination" \
    > "$e2e_root/fixed-constraint-dof-reorder-index-rejected.stdout.json"; then
    echo "installed fixed-constraint DOF reorder accepted target index six" >&2
    exit 1
  fi
  grep -Fq 'workbench_usage_error' \
    "$e2e_root/fixed-constraint-dof-reorder-index-rejected.stdout.json"
  test ! -e "$index_destination"
}
exercise_fixed_constraint_dof_reorder_surface

exercise_fixed_constraint_identity_edit_surface() {
  local source_model="$e2e_root/fixed-constraint-dof-reorder-first/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"
  local label edit_directory request_directory direct_directory partial_directory
  local resumed_directory
  for label in first second; do
    edit_directory="$e2e_root/fixed-constraint-identity-edit-$label"
    request_directory="$e2e_root/fixed-constraint-identity-edit-$label-request"
    direct_directory="$e2e_root/fixed-constraint-identity-edit-$label-direct"
    partial_directory="$e2e_root/fixed-constraint-identity-edit-$label-partial"
    resumed_directory="$e2e_root/fixed-constraint-identity-edit-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-edit-fixed-constraint-identity "$source_model" \
      --constraint BC_N3 --new-constraint BC_N3_RENAMED \
      --output-dir "$edit_directory" \
      > "$e2e_root/fixed-constraint-identity-edit-$label.stdout.json"
    grep -Fq '"schema_version":"structural-native-model-edit-receipt.v1"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"operation":"fixed_constraint_identity_edit"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"source_constraint_id":"BC_N3"' "$edit_directory/edit-receipt.json"
    grep -Fq '"replacement_constraint_id":"BC_N3_RENAMED"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"constraint_index":1' "$edit_directory/edit-receipt.json"
    grep -Fq '"constraint_type":"fixed_dofs"' "$edit_directory/edit-receipt.json"
    grep -Fq '"node_id":"N2"' "$edit_directory/edit-receipt.json"
    grep -Fq '"retained_dofs":["RZ","UX","UY","UZ","RX","RY"]' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"retained_prescribed_values_si":{"RX":0,"RY":0,"RZ":0,"UX":0,"UY":0,"UZ":0}' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"retained_source_id":null' "$edit_directory/edit-receipt.json"
    grep -Fq '"retained_extensions":{}' "$edit_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' "$edit_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$edit_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' "$edit_directory/edit-receipt.json"
    grep -Fq '"id":"BC_N3_RENAMED"' "$edit_directory/model-ir.json"
    grep -Fq '"structural-native:model-edit-fixed-constraint-identity.v1"' \
      "$edit_directory/model-ir.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$edit_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/fixed-constraint-identity-edit-$label-validation.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$edit_directory/model-ir.json" \
      --case fixed-constraint-identity-edit-c5 --load-pattern LC_WEAK \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/fixed-constraint-identity-edit-$label-request.stdout.json"
    grep -Fq '"cpp_linear_assembly_preflight_verified":true' \
      "$request_directory/request-receipt.json"
    grep -Fq '"execution_started":false' "$request_directory/request-receipt.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/fixed-constraint-identity-edit-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"active_dof_indices":[12,13,14,15,16,17]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[0,-1000,0,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 0 \
      > "$e2e_root/fixed-constraint-identity-edit-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/fixed-constraint-identity-edit-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/fixed-constraint-identity-edit-$label-restart-diff.txt"
  done

  local suffix
  for suffix in '' -request -direct -partial -resumed; do
    diff -r "$e2e_root/fixed-constraint-identity-edit-first$suffix" \
      "$e2e_root/fixed-constraint-identity-edit-second$suffix" \
      > "$e2e_root/fixed-constraint-identity-edit$suffix-diff.txt"
  done
  cmp "$e2e_root/fixed-constraint-identity-edit-first.stdout.json" \
    "$e2e_root/fixed-constraint-identity-edit-second.stdout.json"
  cmp "$e2e_root/fixed-constraint-identity-edit-first-validation.json" \
    "$e2e_root/fixed-constraint-identity-edit-second-validation.json"
  for suffix in request direct partial resumed; do
    cmp "$e2e_root/fixed-constraint-identity-edit-first-$suffix.stdout.json" \
      "$e2e_root/fixed-constraint-identity-edit-second-$suffix.stdout.json"
  done
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed fixed-constraint identity edit mutated its source ModelIR" >&2
    exit 1
  fi

  local missing_destination="$e2e_root/fixed-constraint-identity-edit-missing-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-edit-fixed-constraint-identity "$source_model" \
    --constraint BC_MISSING --new-constraint BC_NEW --output-dir "$missing_destination" \
    > "$e2e_root/fixed-constraint-identity-edit-missing-rejected.stdout.json"; then
    echo "installed fixed-constraint identity edit accepted a missing constraint" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_edit_fixed_constraint_identity_constraint_missing' \
    "$e2e_root/fixed-constraint-identity-edit-missing-rejected.stdout.json"
  test ! -e "$missing_destination"

  local collision_destination="$e2e_root/fixed-constraint-identity-edit-collision-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-edit-fixed-constraint-identity "$source_model" \
    --constraint BC_N3 --new-constraint BC1 --output-dir "$collision_destination" \
    > "$e2e_root/fixed-constraint-identity-edit-collision-rejected.stdout.json"; then
    echo "installed fixed-constraint identity edit accepted a colliding identity" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_edit_fixed_constraint_identity_replacement_exists' \
    "$e2e_root/fixed-constraint-identity-edit-collision-rejected.stdout.json"
  test ! -e "$collision_destination"

  local no_op_destination="$e2e_root/fixed-constraint-identity-edit-no-op-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-edit-fixed-constraint-identity "$source_model" \
    --constraint BC_N3 --new-constraint BC_N3 --output-dir "$no_op_destination" \
    > "$e2e_root/fixed-constraint-identity-edit-no-op-rejected.stdout.json"; then
    echo "installed fixed-constraint identity edit accepted a no-op" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_edit_no_change' \
    "$e2e_root/fixed-constraint-identity-edit-no-op-rejected.stdout.json"
  test ! -e "$no_op_destination"

  local invalid_destination="$e2e_root/fixed-constraint-identity-edit-invalid-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-edit-fixed-constraint-identity "$source_model" \
    --constraint BC_N3 --new-constraint 1_INVALID --output-dir "$invalid_destination" \
    > "$e2e_root/fixed-constraint-identity-edit-invalid-rejected.stdout.json"; then
    echo "installed fixed-constraint identity edit accepted an invalid stable identity" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_edit_fixed_constraint_identity_replacement_invalid' \
    "$e2e_root/fixed-constraint-identity-edit-invalid-rejected.stdout.json"
  test ! -e "$invalid_destination"
}
exercise_fixed_constraint_identity_edit_surface

exercise_nodal_load_identity_edit_surface() {
  local source_model="$e2e_root/fixed-constraint-identity-edit-first/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"
  local label edit_directory request_directory direct_directory partial_directory
  local resumed_directory
  for label in first second; do
    edit_directory="$e2e_root/nodal-load-identity-edit-$label"
    request_directory="$e2e_root/nodal-load-identity-edit-$label-request"
    direct_directory="$e2e_root/nodal-load-identity-edit-$label-direct"
    partial_directory="$e2e_root/nodal-load-identity-edit-$label-partial"
    resumed_directory="$e2e_root/nodal-load-identity-edit-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-edit-nodal-load-identity "$source_model" \
      --load-pattern LC_WEAK --load L_WEAK_N3 --new-load L_WEAK_N3_RENAMED \
      --output-dir "$edit_directory" \
      > "$e2e_root/nodal-load-identity-edit-$label.stdout.json"
    grep -Fq '"schema_version":"structural-native-model-edit-receipt.v1"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"operation":"nodal_load_identity_edit"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"load_pattern_id":"LC_WEAK"' "$edit_directory/edit-receipt.json"
    grep -Fq '"load_pattern_index":1' "$edit_directory/edit-receipt.json"
    grep -Fq '"analysis_type":"linear_static"' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_nodal_load_id":"L_WEAK_N3"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"replacement_nodal_load_id":"L_WEAK_N3_RENAMED"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"nodal_load_index":1' "$edit_directory/edit-receipt.json"
    grep -Fq '"node_id":"N3"' "$edit_directory/edit-receipt.json"
    grep -Fq '"retained_components_si":{"FX":0,"FY":-1000,"FZ":0,"MX":0,"MY":0,"MZ":0}' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"retained_source_id":null' "$edit_directory/edit-receipt.json"
    grep -Fq '"retained_extensions":{}' "$edit_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' "$edit_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$edit_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' "$edit_directory/edit-receipt.json"
    grep -Fq '"id":"L_WEAK_N3_RENAMED"' "$edit_directory/model-ir.json"
    grep -Fq '"structural-native:model-edit-nodal-load-identity.v1"' \
      "$edit_directory/model-ir.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$edit_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/nodal-load-identity-edit-$label-validation.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$edit_directory/model-ir.json" \
      --case nodal-load-identity-edit-c5 --load-pattern LC_WEAK \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/nodal-load-identity-edit-$label-request.stdout.json"
    grep -Fq '"cpp_linear_assembly_preflight_verified":true' \
      "$request_directory/request-receipt.json"
    grep -Fq '"execution_started":false' "$request_directory/request-receipt.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/nodal-load-identity-edit-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"active_dof_indices":[12,13,14,15,16,17]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[0,-1000,0,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 0 \
      > "$e2e_root/nodal-load-identity-edit-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/nodal-load-identity-edit-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/nodal-load-identity-edit-$label-restart-diff.txt"
  done

  local suffix
  for suffix in '' -request -direct -partial -resumed; do
    diff -r "$e2e_root/nodal-load-identity-edit-first$suffix" \
      "$e2e_root/nodal-load-identity-edit-second$suffix" \
      > "$e2e_root/nodal-load-identity-edit$suffix-diff.txt"
  done
  cmp "$e2e_root/nodal-load-identity-edit-first.stdout.json" \
    "$e2e_root/nodal-load-identity-edit-second.stdout.json"
  cmp "$e2e_root/nodal-load-identity-edit-first-validation.json" \
    "$e2e_root/nodal-load-identity-edit-second-validation.json"
  for suffix in request direct partial resumed; do
    cmp "$e2e_root/nodal-load-identity-edit-first-$suffix.stdout.json" \
      "$e2e_root/nodal-load-identity-edit-second-$suffix.stdout.json"
  done
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed nodal-load identity edit mutated its source ModelIR" >&2
    exit 1
  fi

  local missing_pattern_destination="$e2e_root/nodal-load-identity-edit-pattern-missing-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-edit-nodal-load-identity "$source_model" --load-pattern LC_MISSING \
    --load L_WEAK_N3 --new-load L_NEW --output-dir "$missing_pattern_destination" \
    > "$e2e_root/nodal-load-identity-edit-pattern-missing-rejected.stdout.json"; then
    echo "installed nodal-load identity edit accepted a missing pattern" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_edit_nodal_load_identity_pattern_missing' \
    "$e2e_root/nodal-load-identity-edit-pattern-missing-rejected.stdout.json"
  test ! -e "$missing_pattern_destination"

  local missing_load_destination="$e2e_root/nodal-load-identity-edit-load-missing-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-edit-nodal-load-identity "$source_model" --load-pattern LC_WEAK \
    --load L_MISSING --new-load L_NEW --output-dir "$missing_load_destination" \
    > "$e2e_root/nodal-load-identity-edit-load-missing-rejected.stdout.json"; then
    echo "installed nodal-load identity edit accepted a missing load" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_edit_nodal_load_identity_load_missing' \
    "$e2e_root/nodal-load-identity-edit-load-missing-rejected.stdout.json"
  test ! -e "$missing_load_destination"

  local collision_destination="$e2e_root/nodal-load-identity-edit-collision-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-edit-nodal-load-identity "$source_model" --load-pattern LC_WEAK \
    --load L_WEAK_N3 --new-load L_AXIAL_N2 --output-dir "$collision_destination" \
    > "$e2e_root/nodal-load-identity-edit-collision-rejected.stdout.json"; then
    echo "installed nodal-load identity edit accepted a global collision" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_edit_nodal_load_identity_replacement_exists' \
    "$e2e_root/nodal-load-identity-edit-collision-rejected.stdout.json"
  test ! -e "$collision_destination"

  local no_op_destination="$e2e_root/nodal-load-identity-edit-no-op-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-edit-nodal-load-identity "$source_model" --load-pattern LC_WEAK \
    --load L_WEAK_N3 --new-load L_WEAK_N3 --output-dir "$no_op_destination" \
    > "$e2e_root/nodal-load-identity-edit-no-op-rejected.stdout.json"; then
    echo "installed nodal-load identity edit accepted a no-op" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_edit_no_change' \
    "$e2e_root/nodal-load-identity-edit-no-op-rejected.stdout.json"
  test ! -e "$no_op_destination"

  local invalid_destination="$e2e_root/nodal-load-identity-edit-invalid-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-edit-nodal-load-identity "$source_model" --load-pattern LC_WEAK \
    --load L_WEAK_N3 --new-load 1_INVALID --output-dir "$invalid_destination" \
    > "$e2e_root/nodal-load-identity-edit-invalid-rejected.stdout.json"; then
    echo "installed nodal-load identity edit accepted an invalid stable identity" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_edit_nodal_load_identity_replacement_invalid' \
    "$e2e_root/nodal-load-identity-edit-invalid-rejected.stdout.json"
  test ! -e "$invalid_destination"
}
exercise_nodal_load_identity_edit_surface

exercise_linear_load_pattern_identity_edit_surface() {
  local source_model="$e2e_root/nodal-load-identity-edit-first/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"
  local label edit_directory request_directory direct_directory partial_directory
  local resumed_directory
  for label in first second; do
    edit_directory="$e2e_root/linear-load-pattern-identity-edit-$label"
    request_directory="$e2e_root/linear-load-pattern-identity-edit-$label-request"
    direct_directory="$e2e_root/linear-load-pattern-identity-edit-$label-direct"
    partial_directory="$e2e_root/linear-load-pattern-identity-edit-$label-partial"
    resumed_directory="$e2e_root/linear-load-pattern-identity-edit-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-edit-linear-load-pattern-identity "$source_model" \
      --load-pattern LC_WEAK --new-load-pattern LC_WEAK_RENAMED \
      --output-dir "$edit_directory" \
      > "$e2e_root/linear-load-pattern-identity-edit-$label.stdout.json"
    grep -Fq '"schema_version":"structural-native-model-edit-receipt.v1"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"operation":"linear_load_pattern_identity_edit"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"source_load_pattern_id":"LC_WEAK"' "$edit_directory/edit-receipt.json"
    grep -Fq '"replacement_load_pattern_id":"LC_WEAK_RENAMED"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"load_pattern_index":1' "$edit_directory/edit-receipt.json"
    grep -Fq '"analysis_type":"linear_static"' "$edit_directory/edit-receipt.json"
    grep -Fq '"retained_self_weight":[0,0,0]' "$edit_directory/edit-receipt.json"
    grep -Fq '"retained_nodal_loads":[' "$edit_directory/edit-receipt.json"
    grep -Fq '"id":"L_WEAK_N3_RENAMED"' "$edit_directory/edit-receipt.json"
    grep -Fq '"retained_source_id":"generated:LC_WEAK"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"retained_extensions":{}' "$edit_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' "$edit_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$edit_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' "$edit_directory/edit-receipt.json"
    grep -Fq '"id":"LC_WEAK_RENAMED"' "$edit_directory/model-ir.json"
    grep -Fq '"structural-native:model-edit-linear-load-pattern-identity.v1"' \
      "$edit_directory/model-ir.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$edit_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/linear-load-pattern-identity-edit-$label-validation.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$edit_directory/model-ir.json" \
      --case linear-load-pattern-identity-edit-c5 --load-pattern LC_WEAK_RENAMED \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/linear-load-pattern-identity-edit-$label-request.stdout.json"
    grep -Fq '"cpp_linear_assembly_preflight_verified":true' \
      "$request_directory/request-receipt.json"
    grep -Fq '"execution_started":false' "$request_directory/request-receipt.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/linear-load-pattern-identity-edit-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"active_dof_indices":[12,13,14,15,16,17]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[0,-1000,0,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 0 \
      > "$e2e_root/linear-load-pattern-identity-edit-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/linear-load-pattern-identity-edit-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/linear-load-pattern-identity-edit-$label-restart-diff.txt"
  done

  local suffix
  for suffix in '' -request -direct -partial -resumed; do
    diff -r "$e2e_root/linear-load-pattern-identity-edit-first$suffix" \
      "$e2e_root/linear-load-pattern-identity-edit-second$suffix" \
      > "$e2e_root/linear-load-pattern-identity-edit$suffix-diff.txt"
  done
  cmp "$e2e_root/linear-load-pattern-identity-edit-first.stdout.json" \
    "$e2e_root/linear-load-pattern-identity-edit-second.stdout.json"
  cmp "$e2e_root/linear-load-pattern-identity-edit-first-validation.json" \
    "$e2e_root/linear-load-pattern-identity-edit-second-validation.json"
  for suffix in request direct partial resumed; do
    cmp "$e2e_root/linear-load-pattern-identity-edit-first-$suffix.stdout.json" \
      "$e2e_root/linear-load-pattern-identity-edit-second-$suffix.stdout.json"
  done
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed load-pattern identity edit mutated its source ModelIR" >&2
    exit 1
  fi

  local missing_destination="$e2e_root/linear-load-pattern-identity-edit-missing-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-edit-linear-load-pattern-identity "$source_model" \
    --load-pattern LC_MISSING --new-load-pattern LC_NEW --output-dir "$missing_destination" \
    > "$e2e_root/linear-load-pattern-identity-edit-missing-rejected.stdout.json"; then
    echo "installed load-pattern identity edit accepted a missing pattern" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_edit_linear_load_pattern_identity_pattern_missing' \
    "$e2e_root/linear-load-pattern-identity-edit-missing-rejected.stdout.json"
  test ! -e "$missing_destination"

  local collision_destination="$e2e_root/linear-load-pattern-identity-edit-collision-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-edit-linear-load-pattern-identity "$source_model" \
    --load-pattern LC_WEAK --new-load-pattern LC_AXIAL --output-dir "$collision_destination" \
    > "$e2e_root/linear-load-pattern-identity-edit-collision-rejected.stdout.json"; then
    echo "installed load-pattern identity edit accepted a colliding identity" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_edit_linear_load_pattern_identity_replacement_exists' \
    "$e2e_root/linear-load-pattern-identity-edit-collision-rejected.stdout.json"
  test ! -e "$collision_destination"

  local no_op_destination="$e2e_root/linear-load-pattern-identity-edit-no-op-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-edit-linear-load-pattern-identity "$source_model" \
    --load-pattern LC_WEAK --new-load-pattern LC_WEAK --output-dir "$no_op_destination" \
    > "$e2e_root/linear-load-pattern-identity-edit-no-op-rejected.stdout.json"; then
    echo "installed load-pattern identity edit accepted a no-op" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_edit_no_change' \
    "$e2e_root/linear-load-pattern-identity-edit-no-op-rejected.stdout.json"
  test ! -e "$no_op_destination"

  local invalid_destination="$e2e_root/linear-load-pattern-identity-edit-invalid-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-edit-linear-load-pattern-identity "$source_model" \
    --load-pattern LC_WEAK --new-load-pattern 1_INVALID --output-dir "$invalid_destination" \
    > "$e2e_root/linear-load-pattern-identity-edit-invalid-rejected.stdout.json"; then
    echo "installed load-pattern identity edit accepted an invalid stable identity" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_edit_linear_load_pattern_identity_replacement_invalid' \
    "$e2e_root/linear-load-pattern-identity-edit-invalid-rejected.stdout.json"
  test ! -e "$invalid_destination"
}
exercise_linear_load_pattern_identity_edit_surface

exercise_fixed_constraint_deletion_surface() {
  local source_model="$e2e_root/fixed-constraint-add-first/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"

  local label delete_directory request_directory direct_directory
  local partial_directory resumed_directory
  for label in first second; do
    delete_directory="$e2e_root/fixed-constraint-delete-$label"
    request_directory="$e2e_root/fixed-constraint-delete-$label-request"
    direct_directory="$e2e_root/fixed-constraint-delete-$label-direct"
    partial_directory="$e2e_root/fixed-constraint-delete-$label-partial"
    resumed_directory="$e2e_root/fixed-constraint-delete-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-delete-fixed-constraint "$source_model" \
      --constraint BC_N3 --output-dir "$delete_directory" \
      > "$e2e_root/fixed-constraint-delete-$label.stdout.json"
    grep -Fq '"operation":"fixed_constraint_delete"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_constraint_id":"BC_N3"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_constraint_index":1' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_constraint_type":"fixed_dofs"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_node_id":"N3"' "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_dofs":["UX","UY","UZ","RX","RY","RZ"]' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_prescribed_values_si":{"RX":0,"RY":0,"RZ":0,"UX":0,"UY":0,"UZ":0}' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$delete_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-delete-fixed-constraint.v1"' \
      "$delete_directory/model-ir.json"
    if grep -Fq '"id":"BC_N3"' "$delete_directory/model-ir.json"; then
      echo "installed fixed-constraint deletion retained BC_N3" >&2
      exit 1
    fi
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$delete_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/fixed-constraint-delete-$label-validation.json"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" model-view \
      "$delete_directory/model-ir.json" \
      > "$e2e_root/fixed-constraint-delete-$label-view.txt"
    grep -Fq 'constraints=1' "$e2e_root/fixed-constraint-delete-$label-view.txt"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$delete_directory/model-ir.json" \
      --case fixed-constraint-delete-c5 --load-pattern LC_WEAK \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/fixed-constraint-delete-$label-request.stdout.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/fixed-constraint-delete-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"active_dof_indices":[6,7,8,9,10,11,12,13,14,15,16,17]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[0,-10000,0,0,0,0,0,-1000,0,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"recovery_element_types":[1,1]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"recovery_offsets":[0,12,24]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 1 \
      > "$e2e_root/fixed-constraint-delete-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/fixed-constraint-delete-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/fixed-constraint-delete-$label-restart-diff.txt"
  done

  local suffix diff_label
  for suffix in '' -request -direct -partial -resumed; do
    diff_label="${suffix#-}"
    if [[ -z "$diff_label" ]]; then
      diff_label=model
    fi
    diff -r "$e2e_root/fixed-constraint-delete-first$suffix" \
      "$e2e_root/fixed-constraint-delete-second$suffix" \
      > "$e2e_root/fixed-constraint-delete-$diff_label-diff.txt"
  done
  for suffix in '' -request -direct -partial -resumed; do
    cmp "$e2e_root/fixed-constraint-delete-first$suffix.stdout.json" \
      "$e2e_root/fixed-constraint-delete-second$suffix.stdout.json"
  done
  cmp "$e2e_root/fixed-constraint-delete-first-validation.json" \
    "$e2e_root/fixed-constraint-delete-second-validation.json"
  cmp "$e2e_root/fixed-constraint-delete-first-view.txt" \
    "$e2e_root/fixed-constraint-delete-second-view.txt"
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed fixed-constraint deletion mutated its source ModelIR" >&2
    exit 1
  fi

  local rejected_destination="$e2e_root/fixed-constraint-delete-nonterminal-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-delete-fixed-constraint "$source_model" --constraint BC1 \
    --output-dir "$rejected_destination" \
    > "$e2e_root/fixed-constraint-delete-nonterminal-rejected.stdout.json"; then
    echo "installed fixed-constraint deletion accepted a nonterminal row" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_delete_fixed_constraint_not_terminal' \
    "$e2e_root/fixed-constraint-delete-nonterminal-rejected.stdout.json"
  test ! -e "$rejected_destination"
}
exercise_fixed_constraint_deletion_surface

exercise_linear_load_pattern_add_surface() {
  local source_model="$e2e_root/fixed-constraint-add-first/model-ir.json"
  local source_before_hash baseline_recovery baseline_maximum_displacement
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"
  baseline_recovery="$e2e_root/fixed-constraint-add-first-linear-run/result-recovery-ir.json"
  baseline_maximum_displacement="$(sed -n 's/.*"maximum_absolute_displacement":\([^,}]*\).*/\1/p' "$baseline_recovery")"
  if [[ -z "$baseline_maximum_displacement" ]]; then
    echo "installed fixed-constraint baseline recovery has no displacement summary" >&2
    exit 1
  fi
  local label added_directory request_directory run_directory custom_maximum_displacement
  for label in first second; do
    added_directory="$e2e_root/linear-load-pattern-add-$label"
    request_directory="$e2e_root/linear-load-pattern-add-$label-linear-request"
    run_directory="$e2e_root/linear-load-pattern-add-$label-linear-run"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-add-linear-load-pattern "$source_model" \
      --load-pattern LC_CUSTOM --load L_CUSTOM_N2 --node N2 \
      --components 2500 0 0 0 0 0 --output-dir "$added_directory" \
      > "$e2e_root/linear-load-pattern-add-$label.stdout.json"
    test -s "$added_directory/model-ir.json"
    test -s "$added_directory/edit-receipt.json"
    grep -Fq '"schema_version":"structural-native-model-edit-receipt.v1"' \
      "$added_directory/edit-receipt.json"
    grep -Fq '"operation":"linear_load_pattern_add"' \
      "$added_directory/edit-receipt.json"
    grep -Fq '"load_pattern_id":"LC_CUSTOM"' "$added_directory/edit-receipt.json"
    grep -Fq '"load_pattern_index":4' "$added_directory/edit-receipt.json"
    grep -Fq '"analysis_type":"linear_static"' "$added_directory/edit-receipt.json"
    grep -Fq '"self_weight":[0,0,0]' "$added_directory/edit-receipt.json"
    grep -Fq '"nodal_load_id":"L_CUSTOM_N2"' "$added_directory/edit-receipt.json"
    grep -Fq '"nodal_load_index":0' "$added_directory/edit-receipt.json"
    grep -Fq '"node_id":"N2"' "$added_directory/edit-receipt.json"
    grep -Fq '"components_si":{"FX":2500,"FY":0,"FZ":0,"MX":0,"MY":0,"MZ":0}' \
      "$added_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' \
      "$added_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$added_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' \
      "$added_directory/edit-receipt.json"
    grep -Fq "\"source_input_sha256\":\"sha256:$source_before_hash\"" \
      "$added_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-add-linear-load-pattern.v1"' \
      "$added_directory/model-ir.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$added_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/linear-load-pattern-add-$label-validation.json"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" model-view \
      "$added_directory/model-ir.json" \
      > "$e2e_root/linear-load-pattern-add-$label-view.txt"
    grep -Fq 'load_patterns=5' "$e2e_root/linear-load-pattern-add-$label-view.txt"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$added_directory/model-ir.json" \
      --case added-linear-load-pattern-c5 --load-pattern LC_CUSTOM \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/linear-load-pattern-add-$label-linear-request.stdout.json"
    grep -Fq '"cpp_linear_assembly_preflight_verified":true' \
      "$request_directory/request-receipt.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$added_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$run_directory" \
      > "$e2e_root/linear-load-pattern-add-$label-linear-run.stdout.json"
    grep -Fq '"status":"completed"' "$run_directory/run-receipt.json"
    grep -Fq '"active_dof_indices":[6,7,8,9,10,11]' \
      "$run_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[2500,0,0,0,0,0]' \
      "$run_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$run_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$run_directory/result-recovery-ir.json"
    custom_maximum_displacement="$(sed -n 's/.*"maximum_absolute_displacement":\([^,}]*\).*/\1/p' "$run_directory/result-recovery-ir.json")"
    if [[ -z "$custom_maximum_displacement" \
      || "$custom_maximum_displacement" == "$baseline_maximum_displacement" ]]; then
      echo "installed linear-load-pattern addition did not change recovered displacement" >&2
      exit 1
    fi
  done
  diff -r "$e2e_root/linear-load-pattern-add-first" \
    "$e2e_root/linear-load-pattern-add-second" \
    > "$e2e_root/linear-load-pattern-add-diff.txt"
  diff -r "$e2e_root/linear-load-pattern-add-first-linear-request" \
    "$e2e_root/linear-load-pattern-add-second-linear-request" \
    > "$e2e_root/linear-load-pattern-add-linear-request-diff.txt"
  diff -r "$e2e_root/linear-load-pattern-add-first-linear-run" \
    "$e2e_root/linear-load-pattern-add-second-linear-run" \
    > "$e2e_root/linear-load-pattern-add-linear-run-diff.txt"
  cmp "$e2e_root/linear-load-pattern-add-first.stdout.json" \
    "$e2e_root/linear-load-pattern-add-second.stdout.json"
  cmp "$e2e_root/linear-load-pattern-add-first-validation.json" \
    "$e2e_root/linear-load-pattern-add-second-validation.json"
  cmp "$e2e_root/linear-load-pattern-add-first-view.txt" \
    "$e2e_root/linear-load-pattern-add-second-view.txt"
  cmp "$e2e_root/linear-load-pattern-add-first-linear-request.stdout.json" \
    "$e2e_root/linear-load-pattern-add-second-linear-request.stdout.json"
  cmp "$e2e_root/linear-load-pattern-add-first-linear-run.stdout.json" \
    "$e2e_root/linear-load-pattern-add-second-linear-run.stdout.json"
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed linear-load-pattern addition mutated its source ModelIR" >&2
    exit 1
  fi
}
exercise_linear_load_pattern_add_surface

exercise_linear_load_pattern_deletion_surface() {
  local source_model="$e2e_root/linear-load-pattern-add-first/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"

  local label delete_directory request_directory direct_directory
  local partial_directory resumed_directory
  for label in first second; do
    delete_directory="$e2e_root/linear-load-pattern-delete-$label"
    request_directory="$e2e_root/linear-load-pattern-delete-$label-request"
    direct_directory="$e2e_root/linear-load-pattern-delete-$label-direct"
    partial_directory="$e2e_root/linear-load-pattern-delete-$label-partial"
    resumed_directory="$e2e_root/linear-load-pattern-delete-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-delete-linear-load-pattern "$source_model" \
      --load-pattern LC_CUSTOM --output-dir "$delete_directory" \
      > "$e2e_root/linear-load-pattern-delete-$label.stdout.json"
    grep -Fq '"operation":"linear_load_pattern_delete"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_load_pattern_id":"LC_CUSTOM"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_load_pattern_index":4' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_analysis_type":"linear_static"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_self_weight":[0,0,0]' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_nodal_load_id":"L_CUSTOM_N2"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_nodal_load_index":0' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_node_id":"N2"' "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_components_si":{"FX":2500,"FY":0,"FZ":0,"MX":0,"MY":0,"MZ":0}' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$delete_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-delete-linear-load-pattern.v1"' \
      "$delete_directory/model-ir.json"
    if grep -Fq '"id":"LC_CUSTOM"' "$delete_directory/model-ir.json" \
      || grep -Fq '"id":"L_CUSTOM_N2"' "$delete_directory/model-ir.json"; then
      echo "installed linear-load-pattern deletion retained deleted identities" >&2
      exit 1
    fi
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$delete_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/linear-load-pattern-delete-$label-validation.json"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" model-view \
      "$delete_directory/model-ir.json" \
      > "$e2e_root/linear-load-pattern-delete-$label-view.txt"
    grep -Fq 'load_patterns=4' "$e2e_root/linear-load-pattern-delete-$label-view.txt"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$delete_directory/model-ir.json" \
      --case linear-load-pattern-delete-c5 --load-pattern LC_WEAK \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/linear-load-pattern-delete-$label-request.stdout.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/linear-load-pattern-delete-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"active_dof_indices":[6,7,8,9,10,11]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[0,-10000,0,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"recovery_element_types":[1,1]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"recovery_offsets":[0,12,24]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 0 \
      > "$e2e_root/linear-load-pattern-delete-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/linear-load-pattern-delete-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/linear-load-pattern-delete-$label-restart-diff.txt"
  done

  local suffix diff_label
  for suffix in '' -request -direct -partial -resumed; do
    diff_label="${suffix#-}"
    if [[ -z "$diff_label" ]]; then
      diff_label=model
    fi
    diff -r "$e2e_root/linear-load-pattern-delete-first$suffix" \
      "$e2e_root/linear-load-pattern-delete-second$suffix" \
      > "$e2e_root/linear-load-pattern-delete-$diff_label-diff.txt"
  done
  for suffix in '' -request -direct -partial -resumed; do
    cmp "$e2e_root/linear-load-pattern-delete-first$suffix.stdout.json" \
      "$e2e_root/linear-load-pattern-delete-second$suffix.stdout.json"
  done
  cmp "$e2e_root/linear-load-pattern-delete-first-validation.json" \
    "$e2e_root/linear-load-pattern-delete-second-validation.json"
  cmp "$e2e_root/linear-load-pattern-delete-first-view.txt" \
    "$e2e_root/linear-load-pattern-delete-second-view.txt"
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed linear-load-pattern deletion mutated its source ModelIR" >&2
    exit 1
  fi

  local rejected_destination="$e2e_root/linear-load-pattern-delete-nonterminal-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-delete-linear-load-pattern "$source_model" --load-pattern LC_WEAK \
    --output-dir "$rejected_destination" \
    > "$e2e_root/linear-load-pattern-delete-nonterminal-rejected.stdout.json"; then
    echo "installed linear-load-pattern deletion accepted a nonterminal pattern" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_delete_linear_load_pattern_not_terminal' \
    "$e2e_root/linear-load-pattern-delete-nonterminal-rejected.stdout.json"
  test ! -e "$rejected_destination"
}
exercise_linear_load_pattern_deletion_surface

exercise_linear_material_add_surface() {
  local source_model="$linear_model"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"

  local baseline_member="$e2e_root/linear-material-add-baseline-member"
  local baseline_supported="$e2e_root/linear-material-add-baseline-supported"
  local baseline_request="$e2e_root/linear-material-add-baseline-linear-request"
  local baseline_run="$e2e_root/linear-material-add-baseline-linear-run"
  env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-add-frame3d-member "$source_model" --node N3 \
    --coordinates 4 0 0 --element E2 --from-node N2 \
    --material M1 --section S1 --output-dir "$baseline_member" \
    > "$e2e_root/linear-material-add-baseline-member.stdout.json"
  env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-add-fixed-constraint "$baseline_member/model-ir.json" \
    --constraint BC_N3 --node N3 --output-dir "$baseline_supported" \
    > "$e2e_root/linear-material-add-baseline-supported.stdout.json"
  env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-create-linear-analysis-request "$baseline_supported/model-ir.json" \
    --case added-linear-material-c5 --load-pattern LC_WEAK \
    --max-iterations 100 --absolute-residual-tolerance 1e-11 \
    --relative-residual-tolerance 1e-13 --maximum-increment 0 \
    --output-dir "$baseline_request" \
    > "$e2e_root/linear-material-add-baseline-linear-request.stdout.json"
  env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
    model-linear-run "$baseline_supported/model-ir.json" \
    "$baseline_request/analysis-request.json" --output-dir "$baseline_run" \
    > "$e2e_root/linear-material-add-baseline-linear-run.stdout.json"
  grep -Fq '"status":"completed"' "$baseline_run/run-receipt.json"
  grep -Fq '"active_dof_indices":[6,7,8,9,10,11]' \
    "$baseline_run/result-recovery-ir.json"
  grep -Fq '"active_external_load":[0,-10000,0,0,0,0]' \
    "$baseline_run/result-recovery-ir.json"
  grep -Fq '"fallback_count":0' "$baseline_run/result-ir.json"
  grep -Fq '"fallback_count":0' "$baseline_run/result-recovery-ir.json"
  local baseline_maximum_displacement
  baseline_maximum_displacement="$(sed -n 's/.*"maximum_absolute_displacement":\([^,}]*\).*/\1/p' "$baseline_run/result-recovery-ir.json")"
  if [[ -z "$baseline_maximum_displacement" ]]; then
    echo "installed original-material baseline recovery has no displacement summary" >&2
    exit 1
  fi

  local label material_directory member_directory supported_directory request_directory
  local run_directory material_maximum_displacement
  for label in first second; do
    material_directory="$e2e_root/linear-material-add-$label"
    member_directory="$e2e_root/linear-material-add-$label-member"
    supported_directory="$e2e_root/linear-material-add-$label-supported"
    request_directory="$e2e_root/linear-material-add-$label-linear-request"
    run_directory="$e2e_root/linear-material-add-$label-linear-run"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-add-linear-material "$source_model" --material M2 \
      --elastic-modulus-pa 100000000000 --poisson-ratio 0.3 \
      --density-kg-m3 2700 --output-dir "$material_directory" \
      > "$e2e_root/linear-material-add-$label.stdout.json"
    test -s "$material_directory/model-ir.json"
    test -s "$material_directory/edit-receipt.json"
    grep -Fq '"schema_version":"structural-native-model-edit-receipt.v1"' \
      "$material_directory/edit-receipt.json"
    grep -Fq '"operation":"linear_material_add"' \
      "$material_directory/edit-receipt.json"
    grep -Fq '"material_id":"M2"' "$material_directory/edit-receipt.json"
    grep -Fq '"material_index":1' "$material_directory/edit-receipt.json"
    grep -Fq '"law_id":"linear_elastic_isotropic"' \
      "$material_directory/edit-receipt.json"
    grep -Fq '"parameter_set_version":"1"' \
      "$material_directory/edit-receipt.json"
    grep -Fq '"density_kg_m3":2700' "$material_directory/edit-receipt.json"
    grep -Fq '"elastic_modulus_pa":100000000000' \
      "$material_directory/edit-receipt.json"
    grep -Fq '"poisson_ratio":0.3' "$material_directory/edit-receipt.json"
    grep -Fq '"state_update_epoch":"none"' \
      "$material_directory/edit-receipt.json"
    grep -Fq '"stateful":false' "$material_directory/edit-receipt.json"
    grep -Fq '"supports_trial_commit_rollback":true' \
      "$material_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' \
      "$material_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$material_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' \
      "$material_directory/edit-receipt.json"
    grep -Fq "\"source_input_sha256\":\"sha256:$source_before_hash\"" \
      "$material_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-add-linear-material.v1"' \
      "$material_directory/model-ir.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$material_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/linear-material-add-$label-validation.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-add-frame3d-member "$material_directory/model-ir.json" --node N3 \
      --coordinates 4 0 0 --element E2 --from-node N2 \
      --material M2 --section S1 --output-dir "$member_directory" \
      > "$e2e_root/linear-material-add-$label-member.stdout.json"
    grep -Fq '"material_id":"M2"' "$member_directory/edit-receipt.json"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-add-fixed-constraint "$member_directory/model-ir.json" \
      --constraint BC_N3 --node N3 --output-dir "$supported_directory" \
      > "$e2e_root/linear-material-add-$label-supported.stdout.json"
    grep -Fq '"material_id":"M2"' "$supported_directory/model-ir.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$supported_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/linear-material-add-$label-supported-validation.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$supported_directory/model-ir.json" \
      --case added-linear-material-c5 --load-pattern LC_WEAK \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/linear-material-add-$label-linear-request.stdout.json"
    grep -Fq '"cpp_linear_assembly_preflight_verified":true' \
      "$request_directory/request-receipt.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$supported_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$run_directory" \
      > "$e2e_root/linear-material-add-$label-linear-run.stdout.json"
    grep -Fq '"status":"completed"' "$run_directory/run-receipt.json"
    grep -Fq '"active_dof_indices":[6,7,8,9,10,11]' \
      "$run_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[0,-10000,0,0,0,0]' \
      "$run_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$run_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$run_directory/result-recovery-ir.json"
    material_maximum_displacement="$(sed -n 's/.*"maximum_absolute_displacement":\([^,}]*\).*/\1/p' "$run_directory/result-recovery-ir.json")"
    if [[ -z "$material_maximum_displacement" \
      || "$material_maximum_displacement" == "$baseline_maximum_displacement" ]]; then
      echo "installed linear-material addition did not change recovered displacement" >&2
      exit 1
    fi
  done
  diff -r "$e2e_root/linear-material-add-first" \
    "$e2e_root/linear-material-add-second" \
    > "$e2e_root/linear-material-add-diff.txt"
  diff -r "$e2e_root/linear-material-add-first-member" \
    "$e2e_root/linear-material-add-second-member" \
    > "$e2e_root/linear-material-add-member-diff.txt"
  diff -r "$e2e_root/linear-material-add-first-supported" \
    "$e2e_root/linear-material-add-second-supported" \
    > "$e2e_root/linear-material-add-supported-diff.txt"
  diff -r "$e2e_root/linear-material-add-first-linear-request" \
    "$e2e_root/linear-material-add-second-linear-request" \
    > "$e2e_root/linear-material-add-linear-request-diff.txt"
  diff -r "$e2e_root/linear-material-add-first-linear-run" \
    "$e2e_root/linear-material-add-second-linear-run" \
    > "$e2e_root/linear-material-add-linear-run-diff.txt"
  cmp "$e2e_root/linear-material-add-first.stdout.json" \
    "$e2e_root/linear-material-add-second.stdout.json"
  cmp "$e2e_root/linear-material-add-first-validation.json" \
    "$e2e_root/linear-material-add-second-validation.json"
  cmp "$e2e_root/linear-material-add-first-member.stdout.json" \
    "$e2e_root/linear-material-add-second-member.stdout.json"
  cmp "$e2e_root/linear-material-add-first-supported.stdout.json" \
    "$e2e_root/linear-material-add-second-supported.stdout.json"
  cmp "$e2e_root/linear-material-add-first-supported-validation.json" \
    "$e2e_root/linear-material-add-second-supported-validation.json"
  cmp "$e2e_root/linear-material-add-first-linear-request.stdout.json" \
    "$e2e_root/linear-material-add-second-linear-request.stdout.json"
  cmp "$e2e_root/linear-material-add-first-linear-run.stdout.json" \
    "$e2e_root/linear-material-add-second-linear-run.stdout.json"
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed linear-material addition mutated its source ModelIR" >&2
    exit 1
  fi
}
exercise_linear_material_add_surface

exercise_linear_material_identity_edit_surface() {
  local source_model="$e2e_root/linear-material-add-first/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"

  local label edit_directory request_directory direct_directory
  local partial_directory resumed_directory
  for label in first second; do
    edit_directory="$e2e_root/linear-material-identity-edit-$label"
    request_directory="$e2e_root/linear-material-identity-edit-$label-request"
    direct_directory="$e2e_root/linear-material-identity-edit-$label-direct"
    partial_directory="$e2e_root/linear-material-identity-edit-$label-partial"
    resumed_directory="$e2e_root/linear-material-identity-edit-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-edit-linear-material-identity "$source_model" \
      --material M2 --new-material M2_RENAMED --output-dir "$edit_directory" \
      > "$e2e_root/linear-material-identity-edit-$label.stdout.json"
    grep -Fq '"schema_version":"structural-native-model-edit-receipt.v1"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"operation":"linear_material_identity_edit"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"source_material_id":"M2"' "$edit_directory/edit-receipt.json"
    grep -Fq '"replacement_material_id":"M2_RENAMED"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"material_index":1' "$edit_directory/edit-receipt.json"
    grep -Fq '"law_id":"linear_elastic_isotropic"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"parameter_set_version":"1"' "$edit_directory/edit-receipt.json"
    grep -Fq '"retained_parameters_si":{"density_kg_m3":2700,"elastic_modulus_pa":100000000000,"poisson_ratio":0.3}' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"retained_state_schema":{"state_update_epoch":"none","stateful":false,"supports_trial_commit_rollback":true}' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"retained_source_id":null' "$edit_directory/edit-receipt.json"
    grep -Fq '"retained_extensions":{}' "$edit_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$edit_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"id":"M2_RENAMED","index":1,"law_id":"linear_elastic_isotropic"' \
      "$edit_directory/model-ir.json"
    grep -Fq '"structural-native:model-edit-linear-material-identity.v1"' \
      "$edit_directory/model-ir.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$edit_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/linear-material-identity-edit-$label-validation.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$edit_directory/model-ir.json" \
      --case linear-material-identity-edit-c5 --load-pattern LC_WEAK \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/linear-material-identity-edit-$label-request.stdout.json"
    grep -Fq '"cpp_linear_assembly_preflight_verified":true' \
      "$request_directory/request-receipt.json"
    grep -Fq '"execution_started":false' "$request_directory/request-receipt.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/linear-material-identity-edit-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"active_dof_indices":[6,7,8,9,10,11]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[0,-10000,0,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 0 \
      > "$e2e_root/linear-material-identity-edit-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/linear-material-identity-edit-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/linear-material-identity-edit-$label-restart-diff.txt"
  done

  local suffix
  for suffix in '' -request -direct -partial -resumed; do
    diff -r "$e2e_root/linear-material-identity-edit-first$suffix" \
      "$e2e_root/linear-material-identity-edit-second$suffix" \
      > "$e2e_root/linear-material-identity-edit$suffix-diff.txt"
  done
  cmp "$e2e_root/linear-material-identity-edit-first.stdout.json" \
    "$e2e_root/linear-material-identity-edit-second.stdout.json"
  cmp "$e2e_root/linear-material-identity-edit-first-validation.json" \
    "$e2e_root/linear-material-identity-edit-second-validation.json"
  for suffix in request direct partial resumed; do
    cmp "$e2e_root/linear-material-identity-edit-first-$suffix.stdout.json" \
      "$e2e_root/linear-material-identity-edit-second-$suffix.stdout.json"
  done
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed linear-material identity edit mutated its source ModelIR" >&2
    exit 1
  fi

  local missing_destination="$e2e_root/linear-material-identity-edit-missing-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-edit-linear-material-identity "$source_model" \
    --material M404 --new-material M3 --output-dir "$missing_destination" \
    > "$e2e_root/linear-material-identity-edit-missing-rejected.stdout.json"; then
    echo "installed linear-material identity edit accepted a missing material" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_edit_linear_material_identity_material_missing' \
    "$e2e_root/linear-material-identity-edit-missing-rejected.stdout.json"
  test ! -e "$missing_destination"

  local collision_destination="$e2e_root/linear-material-identity-edit-collision-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-edit-linear-material-identity "$source_model" \
    --material M2 --new-material M1 --output-dir "$collision_destination" \
    > "$e2e_root/linear-material-identity-edit-collision-rejected.stdout.json"; then
    echo "installed linear-material identity edit accepted a colliding identity" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_edit_linear_material_identity_replacement_exists' \
    "$e2e_root/linear-material-identity-edit-collision-rejected.stdout.json"
  test ! -e "$collision_destination"

  local no_op_destination="$e2e_root/linear-material-identity-edit-no-op-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-edit-linear-material-identity "$source_model" \
    --material M2 --new-material M2 --output-dir "$no_op_destination" \
    > "$e2e_root/linear-material-identity-edit-no-op-rejected.stdout.json"; then
    echo "installed linear-material identity edit accepted a no-op" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_edit_no_change' \
    "$e2e_root/linear-material-identity-edit-no-op-rejected.stdout.json"
  test ! -e "$no_op_destination"

  local invalid_destination="$e2e_root/linear-material-identity-edit-invalid-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-edit-linear-material-identity "$source_model" \
    --material M2 --new-material 1_INVALID --output-dir "$invalid_destination" \
    > "$e2e_root/linear-material-identity-edit-invalid-rejected.stdout.json"; then
    echo "installed linear-material identity edit accepted an invalid stable identity" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_edit_linear_material_identity_replacement_invalid' \
    "$e2e_root/linear-material-identity-edit-invalid-rejected.stdout.json"
  test ! -e "$invalid_destination"
}
exercise_linear_material_identity_edit_surface

exercise_linear_material_deletion_surface() {
  local source_model="$e2e_root/linear-material-add-first/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"

  local label delete_directory request_directory direct_directory
  local partial_directory resumed_directory
  for label in first second; do
    delete_directory="$e2e_root/linear-material-delete-$label"
    request_directory="$e2e_root/linear-material-delete-$label-request"
    direct_directory="$e2e_root/linear-material-delete-$label-direct"
    partial_directory="$e2e_root/linear-material-delete-$label-partial"
    resumed_directory="$e2e_root/linear-material-delete-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-delete-linear-material "$source_model" \
      --material M2 --output-dir "$delete_directory" \
      > "$e2e_root/linear-material-delete-$label.stdout.json"
    grep -Fq '"operation":"linear_material_delete"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_material_id":"M2"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_material_index":1' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_law_id":"linear_elastic_isotropic"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_parameter_set_version":"1"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_parameters_si":{"density_kg_m3":2700,"elastic_modulus_pa":100000000000,"poisson_ratio":0.3}' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_state_schema":{"state_update_epoch":"none","stateful":false,"supports_trial_commit_rollback":true}' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$delete_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-delete-linear-material.v1"' \
      "$delete_directory/model-ir.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$delete_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/linear-material-delete-$label-validation.json"
    grep -Fq '"entity_counts":{"nodes":2,"materials":1' \
      "$e2e_root/linear-material-delete-$label-validation.json"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" model-view \
      "$delete_directory/model-ir.json" \
      > "$e2e_root/linear-material-delete-$label-view.txt"
    grep -Fq 'Inventory: nodes=2 elements=1 constraints=1 load_patterns=4' \
      "$e2e_root/linear-material-delete-$label-view.txt"
    grep -Fq '"id":"M1","index":0,"law_id":"linear_elastic_isotropic"' \
      "$delete_directory/model-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$delete_directory/model-ir.json" \
      --case linear-material-delete-c5 --load-pattern LC_WEAK \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/linear-material-delete-$label-request.stdout.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/linear-material-delete-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"active_dof_indices":[6,7,8,9,10,11]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[0,-10000,0,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"recovery_element_types":[1]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"recovery_offsets":[0,12]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 0 \
      > "$e2e_root/linear-material-delete-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/linear-material-delete-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/linear-material-delete-$label-restart-diff.txt"
  done

  local suffix diff_label
  for suffix in '' -request -direct -partial -resumed; do
    diff_label="${suffix#-}"
    if [[ -z "$diff_label" ]]; then
      diff_label=model
    fi
    diff -r "$e2e_root/linear-material-delete-first$suffix" \
      "$e2e_root/linear-material-delete-second$suffix" \
      > "$e2e_root/linear-material-delete-$diff_label-diff.txt"
  done
  for suffix in '' -request -direct -partial -resumed; do
    cmp "$e2e_root/linear-material-delete-first$suffix.stdout.json" \
      "$e2e_root/linear-material-delete-second$suffix.stdout.json"
  done
  cmp "$e2e_root/linear-material-delete-first-validation.json" \
    "$e2e_root/linear-material-delete-second-validation.json"
  cmp "$e2e_root/linear-material-delete-first-view.txt" \
    "$e2e_root/linear-material-delete-second-view.txt"
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed linear-material deletion mutated its source ModelIR" >&2
    exit 1
  fi

  local referenced_source="$e2e_root/linear-material-delete-referenced-source"
  env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-add-frame3d-member "$source_model" --node N3 \
    --coordinates 4 0 0 --element E2 --from-node N2 \
    --material M2 --section S1 --output-dir "$referenced_source" \
    > "$e2e_root/linear-material-delete-referenced-source.stdout.json"
  local referenced_destination="$e2e_root/linear-material-delete-referenced-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-delete-linear-material "$referenced_source/model-ir.json" --material M2 \
    --output-dir "$referenced_destination" \
    > "$e2e_root/linear-material-delete-referenced-rejected.stdout.json"; then
    echo "installed linear-material deletion accepted an element-referenced material" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_delete_linear_material_referenced_by_element' \
    "$e2e_root/linear-material-delete-referenced-rejected.stdout.json"
  test ! -e "$referenced_destination"

  local later_source="$e2e_root/linear-material-delete-later-source"
  env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-add-linear-material "$source_model" --material M3 \
    --elastic-modulus-pa 70000000000 --poisson-ratio 0.33 --density-kg-m3 2700 \
    --output-dir "$later_source" \
    > "$e2e_root/linear-material-delete-later-source.stdout.json"
  local nonterminal_destination="$e2e_root/linear-material-delete-nonterminal-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-delete-linear-material "$later_source/model-ir.json" --material M2 \
    --output-dir "$nonterminal_destination" \
    > "$e2e_root/linear-material-delete-nonterminal-rejected.stdout.json"; then
    echo "installed linear-material deletion accepted a nonterminal material" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_delete_linear_material_not_terminal' \
    "$e2e_root/linear-material-delete-nonterminal-rejected.stdout.json"
  test ! -e "$nonterminal_destination"
}
exercise_linear_material_deletion_surface

exercise_frame_section_add_surface() {
  local source_model="$linear_model"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"

  local baseline_member="$e2e_root/frame-section-add-baseline-member"
  local baseline_supported="$e2e_root/frame-section-add-baseline-supported"
  local baseline_request="$e2e_root/frame-section-add-baseline-linear-request"
  local baseline_run="$e2e_root/frame-section-add-baseline-linear-run"
  env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-add-frame3d-member "$source_model" --node N3 \
    --coordinates 4 0 0 --element E2 --from-node N2 \
    --material M1 --section S1 --output-dir "$baseline_member" \
    > "$e2e_root/frame-section-add-baseline-member.stdout.json"
  env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-add-fixed-constraint "$baseline_member/model-ir.json" \
    --constraint BC_N3 --node N3 --output-dir "$baseline_supported" \
    > "$e2e_root/frame-section-add-baseline-supported.stdout.json"
  env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-create-linear-analysis-request "$baseline_supported/model-ir.json" \
    --case added-frame-section-c5 --load-pattern LC_WEAK \
    --max-iterations 100 --absolute-residual-tolerance 1e-11 \
    --relative-residual-tolerance 1e-13 --maximum-increment 0 \
    --output-dir "$baseline_request" \
    > "$e2e_root/frame-section-add-baseline-linear-request.stdout.json"
  env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
    model-linear-run "$baseline_supported/model-ir.json" \
    "$baseline_request/analysis-request.json" --output-dir "$baseline_run" \
    > "$e2e_root/frame-section-add-baseline-linear-run.stdout.json"
  grep -Fq '"status":"completed"' "$baseline_run/run-receipt.json"
  grep -Fq '"active_dof_indices":[6,7,8,9,10,11]' \
    "$baseline_run/result-recovery-ir.json"
  grep -Fq '"active_external_load":[0,-10000,0,0,0,0]' \
    "$baseline_run/result-recovery-ir.json"
  grep -Fq '"fallback_count":0' "$baseline_run/result-ir.json"
  grep -Fq '"fallback_count":0' "$baseline_run/result-recovery-ir.json"
  local baseline_maximum_displacement
  baseline_maximum_displacement="$(sed -n 's/.*"maximum_absolute_displacement":\([^,}]*\).*/\1/p' "$baseline_run/result-recovery-ir.json")"
  if [[ -z "$baseline_maximum_displacement" ]]; then
    echo "installed original-section baseline recovery has no displacement summary" >&2
    exit 1
  fi

  local label section_directory member_directory supported_directory request_directory
  local run_directory section_maximum_displacement
  for label in first second; do
    section_directory="$e2e_root/frame-section-add-$label"
    member_directory="$e2e_root/frame-section-add-$label-member"
    supported_directory="$e2e_root/frame-section-add-$label-supported"
    request_directory="$e2e_root/frame-section-add-$label-linear-request"
    run_directory="$e2e_root/frame-section-add-$label-linear-run"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-add-frame-section "$source_model" --section S2 \
      --area-m2 0.01 --iy-m4 0.00004 --iz-m4 0.000025 \
      --torsional-constant-m4 0.000005 \
      --shear-area-y-m2 0.008 --shear-area-z-m2 0.008 \
      --output-dir "$section_directory" \
      > "$e2e_root/frame-section-add-$label.stdout.json"
    test -s "$section_directory/model-ir.json"
    test -s "$section_directory/edit-receipt.json"
    grep -Fq '"schema_version":"structural-native-model-edit-receipt.v1"' \
      "$section_directory/edit-receipt.json"
    grep -Fq '"operation":"frame_section_add"' \
      "$section_directory/edit-receipt.json"
    grep -Fq '"section_id":"S2"' "$section_directory/edit-receipt.json"
    grep -Fq '"section_index":1' "$section_directory/edit-receipt.json"
    grep -Fq '"family_id":"frame_3d"' "$section_directory/edit-receipt.json"
    grep -Fq '"parameter_set_version":"1"' \
      "$section_directory/edit-receipt.json"
    grep -Fq '"area_m2":0.01' "$section_directory/edit-receipt.json"
    grep -Fq '"iy_m4":4e-05' "$section_directory/edit-receipt.json"
    grep -Fq '"iz_m4":2.5e-05' "$section_directory/edit-receipt.json"
    grep -Fq '"torsional_constant_m4":5e-06' \
      "$section_directory/edit-receipt.json"
    grep -Fq '"shear_area_y_m2":0.008' "$section_directory/edit-receipt.json"
    grep -Fq '"shear_area_z_m2":0.008' "$section_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' \
      "$section_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$section_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' \
      "$section_directory/edit-receipt.json"
    grep -Fq "\"source_input_sha256\":\"sha256:$source_before_hash\"" \
      "$section_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-add-frame-section.v1"' \
      "$section_directory/model-ir.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$section_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/frame-section-add-$label-validation.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-add-frame3d-member "$section_directory/model-ir.json" --node N3 \
      --coordinates 4 0 0 --element E2 --from-node N2 \
      --material M1 --section S2 --output-dir "$member_directory" \
      > "$e2e_root/frame-section-add-$label-member.stdout.json"
    grep -Fq '"section_id":"S2"' "$member_directory/edit-receipt.json"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-add-fixed-constraint "$member_directory/model-ir.json" \
      --constraint BC_N3 --node N3 --output-dir "$supported_directory" \
      > "$e2e_root/frame-section-add-$label-supported.stdout.json"
    grep -Fq '"section_id":"S2"' "$supported_directory/model-ir.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$supported_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/frame-section-add-$label-supported-validation.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$supported_directory/model-ir.json" \
      --case added-frame-section-c5 --load-pattern LC_WEAK \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/frame-section-add-$label-linear-request.stdout.json"
    grep -Fq '"cpp_linear_assembly_preflight_verified":true' \
      "$request_directory/request-receipt.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$supported_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$run_directory" \
      > "$e2e_root/frame-section-add-$label-linear-run.stdout.json"
    grep -Fq '"status":"completed"' "$run_directory/run-receipt.json"
    grep -Fq '"active_dof_indices":[6,7,8,9,10,11]' \
      "$run_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[0,-10000,0,0,0,0]' \
      "$run_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$run_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$run_directory/result-recovery-ir.json"
    section_maximum_displacement="$(sed -n 's/.*"maximum_absolute_displacement":\([^,}]*\).*/\1/p' "$run_directory/result-recovery-ir.json")"
    if [[ -z "$section_maximum_displacement" \
      || "$section_maximum_displacement" == "$baseline_maximum_displacement" ]]; then
      echo "installed frame-section addition did not change recovered displacement" >&2
      exit 1
    fi
  done
  diff -r "$e2e_root/frame-section-add-first" \
    "$e2e_root/frame-section-add-second" \
    > "$e2e_root/frame-section-add-diff.txt"
  diff -r "$e2e_root/frame-section-add-first-member" \
    "$e2e_root/frame-section-add-second-member" \
    > "$e2e_root/frame-section-add-member-diff.txt"
  diff -r "$e2e_root/frame-section-add-first-supported" \
    "$e2e_root/frame-section-add-second-supported" \
    > "$e2e_root/frame-section-add-supported-diff.txt"
  diff -r "$e2e_root/frame-section-add-first-linear-request" \
    "$e2e_root/frame-section-add-second-linear-request" \
    > "$e2e_root/frame-section-add-linear-request-diff.txt"
  diff -r "$e2e_root/frame-section-add-first-linear-run" \
    "$e2e_root/frame-section-add-second-linear-run" \
    > "$e2e_root/frame-section-add-linear-run-diff.txt"
  cmp "$e2e_root/frame-section-add-first.stdout.json" \
    "$e2e_root/frame-section-add-second.stdout.json"
  cmp "$e2e_root/frame-section-add-first-validation.json" \
    "$e2e_root/frame-section-add-second-validation.json"
  cmp "$e2e_root/frame-section-add-first-member.stdout.json" \
    "$e2e_root/frame-section-add-second-member.stdout.json"
  cmp "$e2e_root/frame-section-add-first-supported.stdout.json" \
    "$e2e_root/frame-section-add-second-supported.stdout.json"
  cmp "$e2e_root/frame-section-add-first-supported-validation.json" \
    "$e2e_root/frame-section-add-second-supported-validation.json"
  cmp "$e2e_root/frame-section-add-first-linear-request.stdout.json" \
    "$e2e_root/frame-section-add-second-linear-request.stdout.json"
  cmp "$e2e_root/frame-section-add-first-linear-run.stdout.json" \
    "$e2e_root/frame-section-add-second-linear-run.stdout.json"
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed frame-section addition mutated its source ModelIR" >&2
    exit 1
  fi
}
exercise_frame_section_add_surface

exercise_frame_section_deletion_surface() {
  local source_model="$e2e_root/frame-section-add-first/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"

  local label delete_directory request_directory direct_directory
  local partial_directory resumed_directory
  for label in first second; do
    delete_directory="$e2e_root/frame-section-delete-$label"
    request_directory="$e2e_root/frame-section-delete-$label-request"
    direct_directory="$e2e_root/frame-section-delete-$label-direct"
    partial_directory="$e2e_root/frame-section-delete-$label-partial"
    resumed_directory="$e2e_root/frame-section-delete-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-delete-frame-section "$source_model" \
      --section S2 --output-dir "$delete_directory" \
      > "$e2e_root/frame-section-delete-$label.stdout.json"
    grep -Fq '"operation":"frame_section_delete"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_section_id":"S2"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_section_index":1' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_family_id":"frame_3d"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_parameter_set_version":"1"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_parameters_si":{"area_m2":0.01,"iy_m4":4e-05,"iz_m4":2.5e-05,"shear_area_y_m2":0.008,"shear_area_z_m2":0.008,"torsional_constant_m4":5e-06}' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$delete_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-delete-frame-section.v1"' \
      "$delete_directory/model-ir.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$delete_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/frame-section-delete-$label-validation.json"
    grep -Fq '"entity_counts":{"nodes":2,"materials":1,"sections":1' \
      "$e2e_root/frame-section-delete-$label-validation.json"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" model-view \
      "$delete_directory/model-ir.json" \
      > "$e2e_root/frame-section-delete-$label-view.txt"
    grep -Fq 'Inventory: nodes=2 elements=1 constraints=1 load_patterns=4' \
      "$e2e_root/frame-section-delete-$label-view.txt"
    grep -Fq '"family_id":"frame_3d","id":"S1","index":0' \
      "$delete_directory/model-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$delete_directory/model-ir.json" \
      --case frame-section-delete-c5 --load-pattern LC_WEAK \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/frame-section-delete-$label-request.stdout.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/frame-section-delete-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"active_dof_indices":[6,7,8,9,10,11]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[0,-10000,0,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"recovery_element_types":[1]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"recovery_offsets":[0,12]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 0 \
      > "$e2e_root/frame-section-delete-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/frame-section-delete-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/frame-section-delete-$label-restart-diff.txt"
  done

  local suffix diff_label
  for suffix in '' -request -direct -partial -resumed; do
    diff_label="${suffix#-}"
    if [[ -z "$diff_label" ]]; then
      diff_label=model
    fi
    diff -r "$e2e_root/frame-section-delete-first$suffix" \
      "$e2e_root/frame-section-delete-second$suffix" \
      > "$e2e_root/frame-section-delete-$diff_label-diff.txt"
    cmp "$e2e_root/frame-section-delete-first$suffix.stdout.json" \
      "$e2e_root/frame-section-delete-second$suffix.stdout.json"
  done
  cmp "$e2e_root/frame-section-delete-first-validation.json" \
    "$e2e_root/frame-section-delete-second-validation.json"
  cmp "$e2e_root/frame-section-delete-first-view.txt" \
    "$e2e_root/frame-section-delete-second-view.txt"
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed frame-section deletion mutated its source ModelIR" >&2
    exit 1
  fi

  local referenced_source="$e2e_root/frame-section-delete-referenced-source"
  env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-add-frame3d-member "$source_model" --node N3 \
    --coordinates 4 0 0 --element E2 --from-node N2 \
    --material M1 --section S2 --output-dir "$referenced_source" \
    > "$e2e_root/frame-section-delete-referenced-source.stdout.json"
  local referenced_destination="$e2e_root/frame-section-delete-referenced-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-delete-frame-section "$referenced_source/model-ir.json" --section S2 \
    --output-dir "$referenced_destination" \
    > "$e2e_root/frame-section-delete-referenced-rejected.stdout.json"; then
    echo "installed frame-section deletion accepted an element-referenced section" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_delete_frame_section_referenced_by_element' \
    "$e2e_root/frame-section-delete-referenced-rejected.stdout.json"
  test ! -e "$referenced_destination"

  local later_source="$e2e_root/frame-section-delete-later-source"
  env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-add-frame-section "$source_model" --section S3 \
    --area-m2 0.01 --iy-m4 0.00004 --iz-m4 0.000025 \
    --torsional-constant-m4 0.000005 \
    --shear-area-y-m2 0.008 --shear-area-z-m2 0.008 \
    --output-dir "$later_source" \
    > "$e2e_root/frame-section-delete-later-source.stdout.json"
  local nonterminal_destination="$e2e_root/frame-section-delete-nonterminal-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-delete-frame-section "$later_source/model-ir.json" --section S2 \
    --output-dir "$nonterminal_destination" \
    > "$e2e_root/frame-section-delete-nonterminal-rejected.stdout.json"; then
    echo "installed frame-section deletion accepted a nonterminal section" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_delete_frame_section_not_terminal' \
    "$e2e_root/frame-section-delete-nonterminal-rejected.stdout.json"
  test ! -e "$nonterminal_destination"
}
exercise_frame_section_deletion_surface

exercise_frame_element_properties_edit_surface() {
  local source_model="$linear_model"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"

  local baseline_request="$e2e_root/frame-element-properties-baseline-request"
  local baseline_run="$e2e_root/frame-element-properties-baseline-run"
  env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-create-linear-analysis-request "$source_model" \
    --case frame-element-properties-c5 --load-pattern LC_WEAK \
    --max-iterations 100 --absolute-residual-tolerance 1e-11 \
    --relative-residual-tolerance 1e-13 --maximum-increment 0 \
    --output-dir "$baseline_request" \
    > "$e2e_root/frame-element-properties-baseline-request.stdout.json"
  env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
    model-linear-run "$source_model" "$baseline_request/analysis-request.json" \
    --output-dir "$baseline_run" \
    > "$e2e_root/frame-element-properties-baseline-run.stdout.json"
  grep -Fq '"status":"completed"' "$baseline_run/run-receipt.json"
  grep -Fq '"active_dof_indices":[6,7,8,9,10,11]' \
    "$baseline_run/result-recovery-ir.json"
  grep -Fq '"active_external_load":[0,-10000,0,0,0,0]' \
    "$baseline_run/result-recovery-ir.json"
  grep -Fq '"fallback_count":0' "$baseline_run/result-ir.json"
  grep -Fq '"fallback_count":0' "$baseline_run/result-recovery-ir.json"
  local baseline_maximum_displacement
  baseline_maximum_displacement="$(sed -n 's/.*"maximum_absolute_displacement":\([^,}]*\).*/\1/p' "$baseline_run/result-recovery-ir.json")"
  if [[ -z "$baseline_maximum_displacement" ]]; then
    echo "installed property-assignment baseline recovery has no displacement summary" >&2
    exit 1
  fi

  local label material_directory section_directory edit_directory request_directory run_directory
  local edited_maximum_displacement
  for label in first second; do
    material_directory="$e2e_root/frame-element-properties-$label-material"
    section_directory="$e2e_root/frame-element-properties-$label-section"
    edit_directory="$e2e_root/frame-element-properties-edit-$label"
    request_directory="$e2e_root/frame-element-properties-$label-request"
    run_directory="$e2e_root/frame-element-properties-$label-run"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-add-linear-material "$source_model" --material M2 \
      --elastic-modulus-pa 100000000000 --poisson-ratio 0.3 --density-kg-m3 2700 \
      --output-dir "$material_directory" \
      > "$e2e_root/frame-element-properties-$label-material.stdout.json"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-add-frame-section "$material_directory/model-ir.json" --section S2 \
      --area-m2 0.01 --iy-m4 0.00004 --iz-m4 0.000025 \
      --torsional-constant-m4 0.000005 \
      --shear-area-y-m2 0.008 --shear-area-z-m2 0.008 \
      --output-dir "$section_directory" \
      > "$e2e_root/frame-element-properties-$label-section.stdout.json"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-edit-frame-element-properties "$section_directory/model-ir.json" \
      --element E1 --material M2 --section S2 --output-dir "$edit_directory" \
      > "$e2e_root/frame-element-properties-edit-$label.stdout.json"
    test -s "$edit_directory/model-ir.json"
    test -s "$edit_directory/edit-receipt.json"
    grep -Fq '"schema_version":"structural-native-model-edit-receipt.v1"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"operation":"frame_element_properties"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"element_id":"E1"' "$edit_directory/edit-receipt.json"
    grep -Fq '"element_type":"frame_3d"' "$edit_directory/edit-receipt.json"
    grep -Fq '"formulation":"euler_bernoulli_3d"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"previous_material_id":"M1"' "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_material_id":"M2"' "$edit_directory/edit-receipt.json"
    grep -Fq '"previous_section_id":"S1"' "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_section_id":"S2"' "$edit_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$edit_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-edit-frame-element-properties.v1"' \
      "$edit_directory/model-ir.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$edit_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/frame-element-properties-edit-$label-validation.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$edit_directory/model-ir.json" \
      --case frame-element-properties-c5 --load-pattern LC_WEAK \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/frame-element-properties-$label-request.stdout.json"
    grep -Fq '"cpp_linear_assembly_preflight_verified":true' \
      "$request_directory/request-receipt.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$run_directory" \
      > "$e2e_root/frame-element-properties-$label-run.stdout.json"
    grep -Fq '"status":"completed"' "$run_directory/run-receipt.json"
    grep -Fq '"active_dof_indices":[6,7,8,9,10,11]' \
      "$run_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[0,-10000,0,0,0,0]' \
      "$run_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$run_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$run_directory/result-recovery-ir.json"
    edited_maximum_displacement="$(sed -n 's/.*"maximum_absolute_displacement":\([^,}]*\).*/\1/p' "$run_directory/result-recovery-ir.json")"
    if [[ -z "$edited_maximum_displacement" \
      || "$edited_maximum_displacement" == "$baseline_maximum_displacement" ]]; then
      echo "installed frame-element property assignment did not change recovered displacement" >&2
      exit 1
    fi
  done
  for suffix in material section; do
    diff -r "$e2e_root/frame-element-properties-first-$suffix" \
      "$e2e_root/frame-element-properties-second-$suffix" \
      > "$e2e_root/frame-element-properties-$suffix-diff.txt"
    cmp "$e2e_root/frame-element-properties-first-$suffix.stdout.json" \
      "$e2e_root/frame-element-properties-second-$suffix.stdout.json"
  done
  diff -r "$e2e_root/frame-element-properties-edit-first" \
    "$e2e_root/frame-element-properties-edit-second" \
    > "$e2e_root/frame-element-properties-edit-diff.txt"
  diff -r "$e2e_root/frame-element-properties-first-request" \
    "$e2e_root/frame-element-properties-second-request" \
    > "$e2e_root/frame-element-properties-request-diff.txt"
  diff -r "$e2e_root/frame-element-properties-first-run" \
    "$e2e_root/frame-element-properties-second-run" \
    > "$e2e_root/frame-element-properties-run-diff.txt"
  cmp "$e2e_root/frame-element-properties-edit-first.stdout.json" \
    "$e2e_root/frame-element-properties-edit-second.stdout.json"
  cmp "$e2e_root/frame-element-properties-edit-first-validation.json" \
    "$e2e_root/frame-element-properties-edit-second-validation.json"
  cmp "$e2e_root/frame-element-properties-first-request.stdout.json" \
    "$e2e_root/frame-element-properties-second-request.stdout.json"
  cmp "$e2e_root/frame-element-properties-first-run.stdout.json" \
    "$e2e_root/frame-element-properties-second-run.stdout.json"
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed frame-element property assignment mutated its source ModelIR" >&2
    exit 1
  fi
}
exercise_frame_element_properties_edit_surface

exercise_truss3d_authoring_surface() {
  local source_model="$linear_model"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"

  local baseline_request="$e2e_root/truss3d-authoring-baseline-request"
  local baseline_run="$e2e_root/truss3d-authoring-baseline-run"
  env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-create-linear-analysis-request "$source_model" \
    --case truss3d-authoring-c5 --load-pattern LC_WEAK \
    --max-iterations 100 --absolute-residual-tolerance 1e-11 \
    --relative-residual-tolerance 1e-13 --maximum-increment 0 \
    --output-dir "$baseline_request" \
    > "$e2e_root/truss3d-authoring-baseline-request.stdout.json"
  env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
    model-linear-run "$source_model" "$baseline_request/analysis-request.json" \
    --output-dir "$baseline_run" \
    > "$e2e_root/truss3d-authoring-baseline-run.stdout.json"
  local baseline_displacement
  baseline_displacement="$(sed -n 's/.*"maximum_absolute_displacement":\([^,}]*\).*/\1/p' "$baseline_run/result-recovery-ir.json")"
  if [[ -z "$baseline_displacement" ]]; then
    echo "installed truss3d baseline recovery has no displacement summary" >&2
    exit 1
  fi

  local label section_directory member_directory composed_directory
  local request_directory direct_directory partial_directory resumed_directory
  local composed_displacement
  for label in first second; do
    section_directory="$e2e_root/truss3d-authoring-$label-section"
    member_directory="$e2e_root/truss3d-authoring-$label-member"
    composed_directory="$e2e_root/truss3d-authoring-$label-composed"
    request_directory="$e2e_root/truss3d-authoring-$label-request"
    direct_directory="$e2e_root/truss3d-authoring-$label-direct"
    partial_directory="$e2e_root/truss3d-authoring-$label-partial"
    resumed_directory="$e2e_root/truss3d-authoring-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-add-truss-section "$source_model" --section T1 --area-m2 0.005 \
      --output-dir "$section_directory" \
      > "$e2e_root/truss3d-authoring-$label-section.stdout.json"
    grep -Fq '"operation":"truss_section_add"' "$section_directory/edit-receipt.json"
    grep -Fq '"family_id":"truss_3d"' "$section_directory/edit-receipt.json"
    grep -Fq '"parameters_si":{"area_m2":0.005}' "$section_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-add-truss-section.v1"' \
      "$section_directory/model-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-add-truss3d-member "$section_directory/model-ir.json" \
      --node N3 --coordinates 2 1 0 --element E2 --from-node N2 \
      --material M1 --section T1 --output-dir "$member_directory" \
      > "$e2e_root/truss3d-authoring-$label-member.stdout.json"
    grep -Fq '"operation":"truss3d_member_add"' "$member_directory/edit-receipt.json"
    grep -Fq '"element_type":"truss_3d"' "$member_directory/edit-receipt.json"
    grep -Fq '"formulation":"linear_truss_3d"' "$member_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-add-truss3d-member.v1"' \
      "$member_directory/model-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-add-fixed-constraint "$member_directory/model-ir.json" \
      --constraint BC_N3 --node N3 --output-dir "$composed_directory" \
      > "$e2e_root/truss3d-authoring-$label-composed.stdout.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$composed_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/truss3d-authoring-$label-validation.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$composed_directory/model-ir.json" \
      --case truss3d-authoring-c5 --load-pattern LC_WEAK \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/truss3d-authoring-$label-request.stdout.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$composed_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/truss3d-authoring-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"active_dof_indices":[6,7,8,9,10,11]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[0,-10000,0,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"recovery_element_types":[1,2]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"recovery_offsets":[0,12,15]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"
    local recovery_values truss_axial_force
    recovery_values="$(sed -n 's/.*"recovery_values":\[\([^]]*\)\].*/\1/p' "$direct_directory/result-recovery-ir.json")"
    truss_axial_force="${recovery_values##*,}"
    if [[ -z "$recovery_values" || -z "$truss_axial_force" \
      || "$truss_axial_force" == "0" || "$truss_axial_force" == "0.0" ]]; then
      echo "installed truss3d recovery has no nonzero axial-force value" >&2
      exit 1
    fi
    composed_displacement="$(sed -n 's/.*"maximum_absolute_displacement":\([^,}]*\).*/\1/p' "$direct_directory/result-recovery-ir.json")"
    if [[ -z "$composed_displacement" || "$composed_displacement" == "$baseline_displacement" ]]; then
      echo "installed truss3d authoring did not change recovered displacement" >&2
      exit 1
    fi

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$composed_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 1 \
      > "$e2e_root/truss3d-authoring-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$composed_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/truss3d-authoring-$label-resumed.stdout.json"
    grep -Fq '"status":"completed"' "$resumed_directory/run-receipt.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/truss3d-authoring-$label-restart-diff.txt"
  done

  for suffix in section member composed request direct partial resumed; do
    diff -r "$e2e_root/truss3d-authoring-first-$suffix" \
      "$e2e_root/truss3d-authoring-second-$suffix" \
      > "$e2e_root/truss3d-authoring-$suffix-diff.txt"
  done
  for suffix in section member composed request direct partial resumed; do
    cmp "$e2e_root/truss3d-authoring-first-$suffix.stdout.json" \
      "$e2e_root/truss3d-authoring-second-$suffix.stdout.json"
  done
  cmp "$e2e_root/truss3d-authoring-first-validation.json" \
    "$e2e_root/truss3d-authoring-second-validation.json"
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed truss3d authoring mutated its source ModelIR" >&2
    exit 1
  fi
}
exercise_truss3d_authoring_surface

exercise_truss_section_deletion_surface() {
  local retained_model="$e2e_root/truss3d-authoring-first-composed/model-ir.json"
  local source_directory="$e2e_root/truss-section-delete-source"
  env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-add-truss-section "$retained_model" --section T2 --area-m2 0.0025 \
    --output-dir "$source_directory" \
    > "$e2e_root/truss-section-delete-source.stdout.json"

  local source_model="$source_directory/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"

  local label delete_directory request_directory direct_directory
  local partial_directory resumed_directory
  for label in first second; do
    delete_directory="$e2e_root/truss-section-delete-$label"
    request_directory="$e2e_root/truss-section-delete-$label-request"
    direct_directory="$e2e_root/truss-section-delete-$label-direct"
    partial_directory="$e2e_root/truss-section-delete-$label-partial"
    resumed_directory="$e2e_root/truss-section-delete-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-delete-truss-section "$source_model" \
      --section T2 --output-dir "$delete_directory" \
      > "$e2e_root/truss-section-delete-$label.stdout.json"
    grep -Fq '"operation":"truss_section_delete"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_section_id":"T2"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_section_index":2' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_family_id":"truss_3d"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_parameter_set_version":"1"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_parameters_si":{"area_m2":0.0025}' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$delete_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-delete-truss-section.v1"' \
      "$delete_directory/model-ir.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$delete_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/truss-section-delete-$label-validation.json"
    grep -Fq '"entity_counts":{"nodes":3,"materials":1,"sections":2' \
      "$e2e_root/truss-section-delete-$label-validation.json"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" model-view \
      "$delete_directory/model-ir.json" \
      > "$e2e_root/truss-section-delete-$label-view.txt"
    grep -Fq 'Inventory: nodes=3 elements=2 constraints=2 load_patterns=4' \
      "$e2e_root/truss-section-delete-$label-view.txt"
    grep -Fq '"family_id":"truss_3d","id":"T1","index":1' \
      "$delete_directory/model-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$delete_directory/model-ir.json" \
      --case truss-section-delete-c5 --load-pattern LC_WEAK \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/truss-section-delete-$label-request.stdout.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/truss-section-delete-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"active_dof_indices":[6,7,8,9,10,11]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[0,-10000,0,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"recovery_element_types":[1,2]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"recovery_offsets":[0,12,15]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 0 \
      > "$e2e_root/truss-section-delete-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/truss-section-delete-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/truss-section-delete-$label-restart-diff.txt"
  done

  local suffix diff_label
  for suffix in '' -request -direct -partial -resumed; do
    diff_label="${suffix#-}"
    if [[ -z "$diff_label" ]]; then
      diff_label=model
    fi
    diff -r "$e2e_root/truss-section-delete-first$suffix" \
      "$e2e_root/truss-section-delete-second$suffix" \
      > "$e2e_root/truss-section-delete-$diff_label-diff.txt"
    cmp "$e2e_root/truss-section-delete-first$suffix.stdout.json" \
      "$e2e_root/truss-section-delete-second$suffix.stdout.json"
  done
  cmp "$e2e_root/truss-section-delete-first-validation.json" \
    "$e2e_root/truss-section-delete-second-validation.json"
  cmp "$e2e_root/truss-section-delete-first-view.txt" \
    "$e2e_root/truss-section-delete-second-view.txt"
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed truss-section deletion mutated its source ModelIR" >&2
    exit 1
  fi

  local referenced_source="$e2e_root/truss-section-delete-referenced-source"
  env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-edit-truss-element-properties "$source_model" \
    --element E2 --material M1 --section T2 --output-dir "$referenced_source" \
    > "$e2e_root/truss-section-delete-referenced-source.stdout.json"
  local referenced_destination="$e2e_root/truss-section-delete-referenced-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-delete-truss-section "$referenced_source/model-ir.json" --section T2 \
    --output-dir "$referenced_destination" \
    > "$e2e_root/truss-section-delete-referenced-rejected.stdout.json"; then
    echo "installed truss-section deletion accepted an element-referenced section" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_delete_truss_section_referenced_by_element' \
    "$e2e_root/truss-section-delete-referenced-rejected.stdout.json"
  test ! -e "$referenced_destination"

  local later_source="$e2e_root/truss-section-delete-later-source"
  env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-add-truss-section "$source_model" --section T3 --area-m2 0.001 \
    --output-dir "$later_source" \
    > "$e2e_root/truss-section-delete-later-source.stdout.json"
  local nonterminal_destination="$e2e_root/truss-section-delete-nonterminal-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-delete-truss-section "$later_source/model-ir.json" --section T2 \
    --output-dir "$nonterminal_destination" \
    > "$e2e_root/truss-section-delete-nonterminal-rejected.stdout.json"; then
    echo "installed truss-section deletion accepted a nonterminal section" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_delete_truss_section_not_terminal' \
    "$e2e_root/truss-section-delete-nonterminal-rejected.stdout.json"
  test ! -e "$nonterminal_destination"

  local minimum_destination="$e2e_root/truss-section-delete-minimum-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-delete-truss-section "$retained_model" --section T1 \
    --output-dir "$minimum_destination" \
    > "$e2e_root/truss-section-delete-minimum-rejected.stdout.json"; then
    echo "installed truss-section deletion accepted the last truss section" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_delete_truss_section_minimum_family' \
    "$e2e_root/truss-section-delete-minimum-rejected.stdout.json"
  test ! -e "$minimum_destination"
}
exercise_truss_section_deletion_surface

exercise_truss3d_editing_surface() {
  local authored_model="$e2e_root/truss3d-authoring-first-composed/model-ir.json"
  local alternate_section="$e2e_root/truss3d-editing-alternate-section"
  local edit_source="$e2e_root/truss3d-editing-source"
  env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-add-truss-section "$authored_model" --section T2 --area-m2 0.0025 \
    --output-dir "$alternate_section" \
    > "$e2e_root/truss3d-editing-alternate-section.stdout.json"
  env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-add-linear-material "$alternate_section/model-ir.json" --material M2 \
    --elastic-modulus-pa 105000000000 --poisson-ratio 0.3 --density-kg-m3 7850 \
    --output-dir "$edit_source" \
    > "$e2e_root/truss3d-editing-source.stdout.json"

  local source_model="$edit_source/model-ir.json"
  local source_before_hash baseline_displacement
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"
  baseline_displacement="$(sed -n 's/.*"maximum_absolute_displacement":\([^,}]*\).*/\1/p' "$e2e_root/truss3d-authoring-first-direct/result-recovery-ir.json")"
  if [[ -z "$baseline_displacement" ]]; then
    echo "installed truss3d editing baseline has no displacement summary" >&2
    exit 1
  fi

  local label section_directory section_request section_run properties_directory
  local request_directory direct_directory partial_directory resumed_directory
  local section_displacement properties_displacement
  for label in first second; do
    section_directory="$e2e_root/truss3d-editing-$label-section"
    section_request="$e2e_root/truss3d-editing-$label-section-request"
    section_run="$e2e_root/truss3d-editing-$label-section-run"
    properties_directory="$e2e_root/truss3d-editing-$label-properties"
    request_directory="$e2e_root/truss3d-editing-$label-request"
    direct_directory="$e2e_root/truss3d-editing-$label-direct"
    partial_directory="$e2e_root/truss3d-editing-$label-partial"
    resumed_directory="$e2e_root/truss3d-editing-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-edit-truss-section "$source_model" --section T1 --area-m2 0.01 \
      --output-dir "$section_directory" \
      > "$e2e_root/truss3d-editing-$label-section.stdout.json"
    grep -Fq '"operation":"truss_section_parameters"' \
      "$section_directory/edit-receipt.json"
    grep -Fq '"previous_parameters_si":{"area_m2":0.005}' \
      "$section_directory/edit-receipt.json"
    grep -Fq '"edited_parameters_si":{"area_m2":0.01}' \
      "$section_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-edit-truss-section.v1"' \
      "$section_directory/model-ir.json"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$section_directory/model-ir.json" \
      --case truss3d-editing-c5 --load-pattern LC_WEAK \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$section_request" \
      > "$e2e_root/truss3d-editing-$label-section-request.stdout.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$section_directory/model-ir.json" \
      "$section_request/analysis-request.json" --output-dir "$section_run" \
      > "$e2e_root/truss3d-editing-$label-section-run.stdout.json"
    grep -Fq '"status":"completed"' "$section_run/run-receipt.json"
    section_displacement="$(sed -n 's/.*"maximum_absolute_displacement":\([^,}]*\).*/\1/p' "$section_run/result-recovery-ir.json")"
    if [[ -z "$section_displacement" || "$section_displacement" == "$baseline_displacement" ]]; then
      echo "installed truss-section edit did not change recovered displacement" >&2
      exit 1
    fi

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-edit-truss-element-properties "$section_directory/model-ir.json" \
      --element E2 --material M2 --section T2 --output-dir "$properties_directory" \
      > "$e2e_root/truss3d-editing-$label-properties.stdout.json"
    grep -Fq '"operation":"truss_element_properties"' \
      "$properties_directory/edit-receipt.json"
    grep -Fq '"previous_material_id":"M1"' "$properties_directory/edit-receipt.json"
    grep -Fq '"edited_material_id":"M2"' "$properties_directory/edit-receipt.json"
    grep -Fq '"previous_section_id":"T1"' "$properties_directory/edit-receipt.json"
    grep -Fq '"edited_section_id":"T2"' "$properties_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-edit-truss-element-properties.v1"' \
      "$properties_directory/model-ir.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$properties_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/truss3d-editing-$label-validation.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$properties_directory/model-ir.json" \
      --case truss3d-editing-c5 --load-pattern LC_WEAK \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/truss3d-editing-$label-request.stdout.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$properties_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/truss3d-editing-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"active_external_load":[0,-10000,0,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"recovery_element_types":[1,2]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"recovery_offsets":[0,12,15]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"
    properties_displacement="$(sed -n 's/.*"maximum_absolute_displacement":\([^,}]*\).*/\1/p' "$direct_directory/result-recovery-ir.json")"
    if [[ -z "$properties_displacement" \
      || "$properties_displacement" == "$section_displacement" \
      || "$properties_displacement" == "$baseline_displacement" ]]; then
      echo "installed truss property edit did not produce a distinct recovered displacement" >&2
      exit 1
    fi

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$properties_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 1 \
      > "$e2e_root/truss3d-editing-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$properties_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/truss3d-editing-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/truss3d-editing-$label-restart-diff.txt"
  done

  for suffix in section section-request section-run properties request direct partial resumed; do
    diff -r "$e2e_root/truss3d-editing-first-$suffix" \
      "$e2e_root/truss3d-editing-second-$suffix" \
      > "$e2e_root/truss3d-editing-$suffix-diff.txt"
    cmp "$e2e_root/truss3d-editing-first-$suffix.stdout.json" \
      "$e2e_root/truss3d-editing-second-$suffix.stdout.json"
  done
  cmp "$e2e_root/truss3d-editing-first-validation.json" \
    "$e2e_root/truss3d-editing-second-validation.json"
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed truss3d editing mutated its source ModelIR" >&2
    exit 1
  fi
}
exercise_truss3d_editing_surface

exercise_frame3d_leaf_deletion_surface() {
  local source_model="$e2e_root/frame3d-member-add-first/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"

  local label delete_directory request_directory direct_directory
  local partial_directory resumed_directory
  for label in first second; do
    delete_directory="$e2e_root/frame3d-leaf-deletion-$label"
    request_directory="$e2e_root/frame3d-leaf-deletion-$label-request"
    direct_directory="$e2e_root/frame3d-leaf-deletion-$label-direct"
    partial_directory="$e2e_root/frame3d-leaf-deletion-$label-partial"
    resumed_directory="$e2e_root/frame3d-leaf-deletion-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-delete-frame3d-leaf-member "$source_model" \
      --element E2 --node N3 --output-dir "$delete_directory" \
      > "$e2e_root/frame3d-leaf-deletion-$label.stdout.json"
    grep -Fq '"operation":"frame3d_leaf_member_delete"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_node_id":"N3"' "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_node_index":2' "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_element_id":"E2"' "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_element_index":1' "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_element_type":"frame_3d"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_formulation":"euler_bernoulli_3d"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_node_ids":["N2","N3"]' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_material_id":"M1"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_section_id":"S1"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_local_axis_rotation_rad":0' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_releases":{"i":[],"j":[]}' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$delete_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-delete-frame3d-leaf-member.v1"' \
      "$delete_directory/model-ir.json"
    if grep -Fq '"id":"E2"' "$delete_directory/model-ir.json" \
      || grep -Fq '"id":"N3"' "$delete_directory/model-ir.json"; then
      echo "installed frame3d leaf deletion retained E2 or N3" >&2
      exit 1
    fi
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$delete_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/frame3d-leaf-deletion-$label-validation.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$delete_directory/model-ir.json" \
      --case frame3d-leaf-deletion-c5 --load-pattern LC_WEAK \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/frame3d-leaf-deletion-$label-request.stdout.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/frame3d-leaf-deletion-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"active_dof_indices":[6,7,8,9,10,11]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[0,-10000,0,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"recovery_element_types":[1]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"recovery_offsets":[0,12]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 1 \
      > "$e2e_root/frame3d-leaf-deletion-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/frame3d-leaf-deletion-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/frame3d-leaf-deletion-$label-restart-diff.txt"
  done

  local suffix diff_label
  for suffix in '' -request -direct -partial -resumed; do
    diff_label="${suffix#-}"
    if [[ -z "$diff_label" ]]; then
      diff_label=model
    fi
    diff -r "$e2e_root/frame3d-leaf-deletion-first$suffix" \
      "$e2e_root/frame3d-leaf-deletion-second$suffix" \
      > "$e2e_root/frame3d-leaf-deletion-$diff_label-diff.txt"
  done
  for suffix in '' -request -direct -partial -resumed; do
    cmp "$e2e_root/frame3d-leaf-deletion-first$suffix.stdout.json" \
      "$e2e_root/frame3d-leaf-deletion-second$suffix.stdout.json"
  done
  cmp "$e2e_root/frame3d-leaf-deletion-first-validation.json" \
    "$e2e_root/frame3d-leaf-deletion-second-validation.json"
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed frame3d leaf deletion mutated its source ModelIR" >&2
    exit 1
  fi

  local referenced_source="$e2e_root/fixed-constraint-add-first/model-ir.json"
  local rejected_destination="$e2e_root/frame3d-leaf-deletion-referenced-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-delete-frame3d-leaf-member "$referenced_source" \
    --element E2 --node N3 --output-dir "$rejected_destination" \
    > "$e2e_root/frame3d-leaf-deletion-referenced-rejected.stdout.json"; then
    echo "installed frame3d leaf deletion accepted a constrained endpoint" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_delete_frame3d_leaf_node_referenced_by_constraint' \
    "$e2e_root/frame3d-leaf-deletion-referenced-rejected.stdout.json"
  test ! -e "$rejected_destination"
}
exercise_frame3d_leaf_deletion_surface

exercise_truss3d_leaf_deletion_surface() {
  local source_model="$e2e_root/truss3d-authoring-first-member/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"

  local label delete_directory request_directory direct_directory
  local partial_directory resumed_directory
  for label in first second; do
    delete_directory="$e2e_root/truss3d-leaf-deletion-$label"
    request_directory="$e2e_root/truss3d-leaf-deletion-$label-request"
    direct_directory="$e2e_root/truss3d-leaf-deletion-$label-direct"
    partial_directory="$e2e_root/truss3d-leaf-deletion-$label-partial"
    resumed_directory="$e2e_root/truss3d-leaf-deletion-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-delete-truss3d-leaf-member "$source_model" \
      --element E2 --node N3 --output-dir "$delete_directory" \
      > "$e2e_root/truss3d-leaf-deletion-$label.stdout.json"
    grep -Fq '"operation":"truss3d_leaf_member_delete"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_node_id":"N3"' "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_node_index":2' "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_element_id":"E2"' "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_element_index":1' "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_element_type":"truss_3d"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_formulation":"linear_truss_3d"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_node_ids":["N2","N3"]' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_material_id":"M1"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_section_id":"T1"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$delete_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-delete-truss3d-leaf-member.v1"' \
      "$delete_directory/model-ir.json"
    if grep -Fq '"id":"E2"' "$delete_directory/model-ir.json" \
      || grep -Fq '"id":"N3"' "$delete_directory/model-ir.json"; then
      echo "installed truss3d leaf deletion retained E2 or N3" >&2
      exit 1
    fi
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$delete_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/truss3d-leaf-deletion-$label-validation.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$delete_directory/model-ir.json" \
      --case truss3d-leaf-deletion-c5 --load-pattern LC_WEAK \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/truss3d-leaf-deletion-$label-request.stdout.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/truss3d-leaf-deletion-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"active_dof_indices":[6,7,8,9,10,11]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[0,-10000,0,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"recovery_element_types":[1]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"recovery_offsets":[0,12]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 1 \
      > "$e2e_root/truss3d-leaf-deletion-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/truss3d-leaf-deletion-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/truss3d-leaf-deletion-$label-restart-diff.txt"
  done

  local suffix diff_label
  for suffix in '' -request -direct -partial -resumed; do
    diff_label="${suffix#-}"
    if [[ -z "$diff_label" ]]; then
      diff_label=model
    fi
    diff -r "$e2e_root/truss3d-leaf-deletion-first$suffix" \
      "$e2e_root/truss3d-leaf-deletion-second$suffix" \
      > "$e2e_root/truss3d-leaf-deletion-$diff_label-diff.txt"
  done
  for suffix in '' -request -direct -partial -resumed; do
    cmp "$e2e_root/truss3d-leaf-deletion-first$suffix.stdout.json" \
      "$e2e_root/truss3d-leaf-deletion-second$suffix.stdout.json"
  done
  cmp "$e2e_root/truss3d-leaf-deletion-first-validation.json" \
    "$e2e_root/truss3d-leaf-deletion-second-validation.json"
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed truss3d leaf deletion mutated its source ModelIR" >&2
    exit 1
  fi

  local referenced_source="$e2e_root/truss3d-authoring-first-composed/model-ir.json"
  local rejected_destination="$e2e_root/truss3d-leaf-deletion-referenced-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-delete-truss3d-leaf-member "$referenced_source" \
    --element E2 --node N3 --output-dir "$rejected_destination" \
    > "$e2e_root/truss3d-leaf-deletion-referenced-rejected.stdout.json"; then
    echo "installed truss3d leaf deletion accepted a constrained endpoint" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_delete_truss3d_leaf_node_referenced_by_constraint' \
    "$e2e_root/truss3d-leaf-deletion-referenced-rejected.stdout.json"
  test ! -e "$rejected_destination"
}
exercise_truss3d_leaf_deletion_surface

exercise_node_add_surface() {
  local source_model="$linear_model"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"

  local label add_directory composed_directory request_directory direct_directory
  local partial_directory resumed_directory
  for label in first second; do
    add_directory="$e2e_root/node-add-$label"
    composed_directory="$e2e_root/node-add-$label-composed"
    request_directory="$e2e_root/node-add-$label-request"
    direct_directory="$e2e_root/node-add-$label-direct"
    partial_directory="$e2e_root/node-add-$label-partial"
    resumed_directory="$e2e_root/node-add-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-add-node "$source_model" --node N3 --coordinates 4 1 0 \
      --output-dir "$add_directory" \
      > "$e2e_root/node-add-$label.stdout.json"
    grep -Fq '"operation":"node_add"' "$add_directory/edit-receipt.json"
    grep -Fq '"node_id":"N3"' "$add_directory/edit-receipt.json"
    grep -Fq '"node_index":2' "$add_directory/edit-receipt.json"
    grep -Fq '"coordinates_m":[4,1,0]' "$add_directory/edit-receipt.json"
    grep -Fq '"source_id":null' "$add_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' "$add_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$add_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' \
      "$add_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-add-node.v1"' "$add_directory/model-ir.json"
    grep -Fq '"coordinates_m":[4,1,0],"extensions":{},"id":"N3","index":2,"source_id":null' \
      "$add_directory/model-ir.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$add_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/node-add-$label-validation.json"
    grep -Fq '"entity_counts":{"nodes":3,"materials":1,"sections":1,"elements":1,"constraints":1' \
      "$e2e_root/node-add-$label-validation.json"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" model-view \
      "$add_directory/model-ir.json" > "$e2e_root/node-add-$label-view.txt"
    grep -Fq 'Inventory: nodes=3 elements=1 constraints=1 load_patterns=4' \
      "$e2e_root/node-add-$label-view.txt"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-add-fixed-constraint "$add_directory/model-ir.json" \
      --constraint BC_N3 --node N3 --output-dir "$composed_directory" \
      > "$e2e_root/node-add-$label-composed.stdout.json"
    grep -Fq '"structural-native:model-add-node.v1"' "$composed_directory/model-ir.json"
    grep -Fq '"id":"BC_N3","index":1,"node_id":"N3"' \
      "$composed_directory/model-ir.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$composed_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/node-add-$label-composed-validation.json"
    grep -Fq '"entity_counts":{"nodes":3,"materials":1,"sections":1,"elements":1,"constraints":2' \
      "$e2e_root/node-add-$label-composed-validation.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$composed_directory/model-ir.json" \
      --case node-add-c5 --load-pattern LC_WEAK \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/node-add-$label-request.stdout.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$composed_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/node-add-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"active_dof_indices":[6,7,8,9,10,11]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[0,-10000,0,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"recovery_element_types":[1]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"recovery_offsets":[0,12]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$composed_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 0 > "$e2e_root/node-add-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$composed_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/node-add-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/node-add-$label-restart-diff.txt"
  done

  local suffix diff_label
  for suffix in '' -composed -request -direct -partial -resumed; do
    diff_label="${suffix#-}"
    if [[ -z "$diff_label" ]]; then
      diff_label=model
    fi
    diff -r "$e2e_root/node-add-first$suffix" "$e2e_root/node-add-second$suffix" \
      > "$e2e_root/node-add-$diff_label-diff.txt"
    cmp "$e2e_root/node-add-first$suffix.stdout.json" \
      "$e2e_root/node-add-second$suffix.stdout.json"
  done
  cmp "$e2e_root/node-add-first-validation.json" \
    "$e2e_root/node-add-second-validation.json"
  cmp "$e2e_root/node-add-first-composed-validation.json" \
    "$e2e_root/node-add-second-composed-validation.json"
  cmp "$e2e_root/node-add-first-view.txt" "$e2e_root/node-add-second-view.txt"
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed node addition mutated its source ModelIR" >&2
    exit 1
  fi

  local duplicate_id_destination="$e2e_root/node-add-duplicate-id-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-add-node "$source_model" --node N2 --coordinates 4 1 0 \
    --output-dir "$duplicate_id_destination" \
    > "$e2e_root/node-add-duplicate-id-rejected.stdout.json"; then
    echo "installed node addition accepted a duplicate identity" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_add_node_exists' \
    "$e2e_root/node-add-duplicate-id-rejected.stdout.json"
  test ! -e "$duplicate_id_destination"

  local duplicate_coordinate_destination="$e2e_root/node-add-duplicate-coordinate-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-add-node "$source_model" --node N3 --coordinates 2 -0 0 \
    --output-dir "$duplicate_coordinate_destination" \
    > "$e2e_root/node-add-duplicate-coordinate-rejected.stdout.json"; then
    echo "installed node addition accepted duplicate canonical coordinates" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_add_node_coordinate_exists' \
    "$e2e_root/node-add-duplicate-coordinate-rejected.stdout.json"
  test ! -e "$duplicate_coordinate_destination"
}
exercise_node_add_surface

exercise_orphan_node_delete_surface() {
  local source_model="$e2e_root/node-add-first/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"

  local label delete_directory request_directory direct_directory partial_directory
  local resumed_directory
  for label in first second; do
    delete_directory="$e2e_root/orphan-node-delete-$label"
    request_directory="$e2e_root/orphan-node-delete-$label-request"
    direct_directory="$e2e_root/orphan-node-delete-$label-direct"
    partial_directory="$e2e_root/orphan-node-delete-$label-partial"
    resumed_directory="$e2e_root/orphan-node-delete-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-delete-orphan-node "$source_model" --node N3 \
      --output-dir "$delete_directory" \
      > "$e2e_root/orphan-node-delete-$label.stdout.json"
    grep -Fq '"operation":"orphan_node_delete"' "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_node_id":"N3"' "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_node_index":2' "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_coordinates_m":[4,1,0]' "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_source_id":null' "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_extensions":{}' "$delete_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' "$delete_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$delete_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-delete-orphan-node.v1"' \
      "$delete_directory/model-ir.json"
    if grep -Fq '"id":"N3","index":2' "$delete_directory/model-ir.json"; then
      echo "installed orphan-node deletion retained the deleted node" >&2
      exit 1
    fi
    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$delete_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/orphan-node-delete-$label-validation.json"
    grep -Fq '"entity_counts":{"nodes":2,"materials":1,"sections":1,"elements":1,"constraints":1' \
      "$e2e_root/orphan-node-delete-$label-validation.json"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" model-view \
      "$delete_directory/model-ir.json" \
      > "$e2e_root/orphan-node-delete-$label-view.txt"
    grep -Fq 'Inventory: nodes=2 elements=1 constraints=1 load_patterns=4' \
      "$e2e_root/orphan-node-delete-$label-view.txt"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$delete_directory/model-ir.json" \
      --case orphan-node-delete-c5 --load-pattern LC_WEAK \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/orphan-node-delete-$label-request.stdout.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/orphan-node-delete-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"active_dof_indices":[6,7,8,9,10,11]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[0,-10000,0,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"recovery_element_types":[1]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"recovery_offsets":[0,12]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 0 > "$e2e_root/orphan-node-delete-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/orphan-node-delete-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/orphan-node-delete-$label-restart-diff.txt"
  done

  local suffix diff_label
  for suffix in '' -request -direct -partial -resumed; do
    diff_label="${suffix#-}"
    if [[ -z "$diff_label" ]]; then
      diff_label=model
    fi
    diff -r "$e2e_root/orphan-node-delete-first$suffix" \
      "$e2e_root/orphan-node-delete-second$suffix" \
      > "$e2e_root/orphan-node-delete-$diff_label-diff.txt"
    cmp "$e2e_root/orphan-node-delete-first$suffix.stdout.json" \
      "$e2e_root/orphan-node-delete-second$suffix.stdout.json"
  done
  cmp "$e2e_root/orphan-node-delete-first-validation.json" \
    "$e2e_root/orphan-node-delete-second-validation.json"
  cmp "$e2e_root/orphan-node-delete-first-view.txt" \
    "$e2e_root/orphan-node-delete-second-view.txt"
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed orphan-node deletion mutated its source ModelIR" >&2
    exit 1
  fi

  local nonterminal_destination="$e2e_root/orphan-node-delete-nonterminal-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-delete-orphan-node "$source_model" --node N2 \
    --output-dir "$nonterminal_destination" \
    > "$e2e_root/orphan-node-delete-nonterminal-rejected.stdout.json"; then
    echo "installed orphan-node deletion accepted a nonterminal node" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_delete_orphan_node_not_terminal' \
    "$e2e_root/orphan-node-delete-nonterminal-rejected.stdout.json"
  test ! -e "$nonterminal_destination"

  local minimum_destination="$e2e_root/orphan-node-delete-minimum-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-delete-orphan-node "$linear_model" --node N2 \
    --output-dir "$minimum_destination" \
    > "$e2e_root/orphan-node-delete-minimum-rejected.stdout.json"; then
    echo "installed orphan-node deletion accepted minimum topology" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_delete_orphan_node_minimum_topology' \
    "$e2e_root/orphan-node-delete-minimum-rejected.stdout.json"
  test ! -e "$minimum_destination"

  local referenced_destination="$e2e_root/orphan-node-delete-referenced-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-delete-orphan-node "$e2e_root/node-add-first-composed/model-ir.json" --node N3 \
    --output-dir "$referenced_destination" \
    > "$e2e_root/orphan-node-delete-referenced-rejected.stdout.json"; then
    echo "installed orphan-node deletion accepted a constraint-referenced node" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_delete_orphan_node_referenced_by_constraint' \
    "$e2e_root/orphan-node-delete-referenced-rejected.stdout.json"
  test ! -e "$referenced_destination"
}
exercise_orphan_node_delete_surface

exercise_linear_load_combination_add_surface() {
  local source_model="$linear_model"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"

  local label add_directory rejection_directory request_directory direct_directory
  local partial_directory resumed_directory
  for label in first second; do
    add_directory="$e2e_root/linear-load-combination-add-$label"
    rejection_directory="$e2e_root/linear-load-combination-add-$label-solver-rejected"
    request_directory="$e2e_root/linear-load-combination-add-$label-request"
    direct_directory="$e2e_root/linear-load-combination-add-$label-direct"
    partial_directory="$e2e_root/linear-load-combination-add-$label-partial"
    resumed_directory="$e2e_root/linear-load-combination-add-$label-resumed"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-add-linear-load-combination "$source_model" \
      --load-combination COMBO_SERVICE \
      --term LC_WEAK 1.2 --term LC_STRONG -0.5 \
      --output-dir "$add_directory" \
      > "$e2e_root/linear-load-combination-add-$label.stdout.json"
    grep -Fq '"operation":"linear_load_combination_add"' \
      "$add_directory/edit-receipt.json"
    grep -Fq '"load_combination_id":"COMBO_SERVICE"' \
      "$add_directory/edit-receipt.json"
    grep -Fq '"load_combination_index":0' "$add_directory/edit-receipt.json"
    grep -Fq '"combination_type":"linear"' "$add_directory/edit-receipt.json"
    grep -Fq '"terms":[{"factor":1.2,"ref_id":"LC_WEAK","ref_kind":"load_pattern"},{"factor":-0.5,"ref_id":"LC_STRONG","ref_kind":"load_pattern"}]' \
      "$add_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' \
      "$add_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$add_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' \
      "$add_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-add-linear-load-combination.v1"' \
      "$add_directory/model-ir.json"
    grep -Fq '"load_combinations":[{"combination_type":"linear","extensions":{},"id":"COMBO_SERVICE","index":0,"source_id":null,"terms":[{"factor":1.2,"ref_id":"LC_WEAK","ref_kind":"load_pattern"},{"factor":-0.5,"ref_id":"LC_STRONG","ref_kind":"load_pattern"}]' \
      "$add_directory/model-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$add_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/linear-load-combination-add-$label-validation.json"
    grep -Fq '"load_patterns":4,"load_combinations":1' \
      "$e2e_root/linear-load-combination-add-$label-validation.json"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" model-view \
      "$add_directory/model-ir.json" \
      > "$e2e_root/linear-load-combination-add-$label-view.txt"
    grep -Fq 'C++ semantic snapshot: verified' \
      "$e2e_root/linear-load-combination-add-$label-view.txt"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$add_directory/model-ir.json" \
      --case linear-load-combination-c5 --load-combination COMBO_SERVICE \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/linear-load-combination-add-$label-request.stdout.json"
    grep -Fq '"schema_version":"structural-native-model-linear-combination-request-create-receipt.v1"' \
      "$request_directory/request-receipt.json"
    grep -Fq '"load_selector_kind":"load_combination"' \
      "$request_directory/request-receipt.json"
    grep -Fq '"load_combination_id":"COMBO_SERVICE"' \
      "$request_directory/request-receipt.json"
    grep -Fq '"frozen_request_selector_field":"load_pattern_id"' \
      "$request_directory/request-receipt.json"
    grep -Fq '"cpp_linear_assembly_preflight_verified":true' \
      "$request_directory/request-receipt.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$add_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/linear-load-combination-add-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"load_pattern_id":"COMBO_SERVICE"' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"load_pattern_index":0' "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_dof_indices":[6,7,8,9,10,11]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[0,-12000,5000,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"recovery_element_types":[1]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"recovery_offsets":[0,12]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$add_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 0 \
      > "$e2e_root/linear-load-combination-add-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$add_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/linear-load-combination-add-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/linear-load-combination-add-$label-restart-diff.txt"

    if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$add_directory/model-ir.json" \
      --case linear-combination-missing-rejected --load-combination COMBO_MISSING \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$rejection_directory" \
      > "$e2e_root/linear-load-combination-add-$label-solver-rejection.json"; then
      echo "installed linear load-combination request accepted a missing selector" >&2
      exit 1
    fi
    grep -Fq 'workbench_model_linear_combination_request_missing' \
      "$e2e_root/linear-load-combination-add-$label-solver-rejection.json"
    test ! -e "$rejection_directory"
  done

  diff -r "$e2e_root/linear-load-combination-add-first" \
    "$e2e_root/linear-load-combination-add-second" \
    > "$e2e_root/linear-load-combination-add-model-diff.txt"
  cmp "$e2e_root/linear-load-combination-add-first.stdout.json" \
    "$e2e_root/linear-load-combination-add-second.stdout.json"
  cmp "$e2e_root/linear-load-combination-add-first-validation.json" \
    "$e2e_root/linear-load-combination-add-second-validation.json"
  cmp "$e2e_root/linear-load-combination-add-first-view.txt" \
    "$e2e_root/linear-load-combination-add-second-view.txt"
  cmp "$e2e_root/linear-load-combination-add-first-solver-rejection.json" \
    "$e2e_root/linear-load-combination-add-second-solver-rejection.json"
  local suffix
  for suffix in request direct partial resumed; do
    diff -r "$e2e_root/linear-load-combination-add-first-$suffix" \
      "$e2e_root/linear-load-combination-add-second-$suffix" \
      > "$e2e_root/linear-load-combination-add-$suffix-diff.txt"
    cmp "$e2e_root/linear-load-combination-add-first-$suffix.stdout.json" \
      "$e2e_root/linear-load-combination-add-second-$suffix.stdout.json"
  done
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed linear load-combination addition mutated its source ModelIR" >&2
    exit 1
  fi

  local appended_destination="$e2e_root/linear-load-combination-add-next-index"
  env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-add-linear-load-combination \
    "$e2e_root/linear-load-combination-add-first/model-ir.json" \
    --load-combination COMBO_STRENGTH \
    --term LC_AXIAL 1.4 --term LC_TORSION 0.7 \
    --output-dir "$appended_destination" \
    > "$e2e_root/linear-load-combination-add-next-index.stdout.json"
  grep -Fq '"load_combination_id":"COMBO_STRENGTH"' \
    "$appended_destination/edit-receipt.json"
  grep -Fq '"load_combination_index":1' "$appended_destination/edit-receipt.json"

  local duplicate_destination="$e2e_root/linear-load-combination-add-duplicate-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-add-linear-load-combination \
    "$e2e_root/linear-load-combination-add-first/model-ir.json" \
    --load-combination COMBO_SERVICE \
    --term LC_AXIAL 1 --term LC_TORSION 1 \
    --output-dir "$duplicate_destination" \
    > "$e2e_root/linear-load-combination-add-duplicate-rejected.stdout.json"; then
    echo "installed linear load-combination addition accepted a duplicate identity" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_add_linear_load_combination_identity_exists' \
    "$e2e_root/linear-load-combination-add-duplicate-rejected.stdout.json"
  test ! -e "$duplicate_destination"

  local missing_destination="$e2e_root/linear-load-combination-add-missing-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-add-linear-load-combination "$source_model" \
    --load-combination COMBO_MISSING \
    --term LC_WEAK 1 --term LC_MISSING 1 \
    --output-dir "$missing_destination" \
    > "$e2e_root/linear-load-combination-add-missing-rejected.stdout.json"; then
    echo "installed linear load-combination addition accepted a missing pattern" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_add_linear_load_combination_pattern_missing' \
    "$e2e_root/linear-load-combination-add-missing-rejected.stdout.json"
  test ! -e "$missing_destination"

  local repeated_destination="$e2e_root/linear-load-combination-add-repeated-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-add-linear-load-combination "$source_model" \
    --load-combination COMBO_REPEATED \
    --term LC_WEAK 1 --term LC_WEAK 2 \
    --output-dir "$repeated_destination" \
    > "$e2e_root/linear-load-combination-add-repeated-rejected.stdout.json"; then
    echo "installed linear load-combination addition accepted repeated patterns" >&2
    exit 1
  fi
  grep -Fq 'workbench_usage_error' \
    "$e2e_root/linear-load-combination-add-repeated-rejected.stdout.json"
  test ! -e "$repeated_destination"

  local zero_destination="$e2e_root/linear-load-combination-add-zero-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-add-linear-load-combination "$source_model" \
    --load-combination COMBO_ZERO \
    --term LC_WEAK 0 --term LC_STRONG 1 \
    --output-dir "$zero_destination" \
    > "$e2e_root/linear-load-combination-add-zero-rejected.stdout.json"; then
    echo "installed linear load-combination addition accepted a zero factor" >&2
    exit 1
  fi
  grep -Fq 'workbench_usage_error' \
    "$e2e_root/linear-load-combination-add-zero-rejected.stdout.json"
  test ! -e "$zero_destination"
}
exercise_linear_load_combination_add_surface

exercise_direct_linear_load_combination_surface() {
  local source_model="$linear_model"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"

  local label add_directory request_directory direct_directory partial_directory
  local resumed_directory
  for label in first second; do
    add_directory="$e2e_root/direct-linear-load-combination-$label"
    request_directory="$e2e_root/direct-linear-load-combination-$label-request"
    direct_directory="$e2e_root/direct-linear-load-combination-$label-direct"
    partial_directory="$e2e_root/direct-linear-load-combination-$label-partial"
    resumed_directory="$e2e_root/direct-linear-load-combination-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-add-linear-load-combination "$source_model" \
      --load-combination COMBO_DIRECT \
      --term LC_AXIAL 0.25 --term LC_WEAK 1.2 --term LC_STRONG -0.5 \
      --output-dir "$add_directory" \
      > "$e2e_root/direct-linear-load-combination-$label.stdout.json"
    grep -Fq '"operation":"direct_linear_load_combination_add"' \
      "$add_directory/edit-receipt.json"
    grep -Fq '"authoring_profile":"unique_direct_linear_static_patterns_2_to_64"' \
      "$add_directory/edit-receipt.json"
    grep -Fq '"term_count":3' "$add_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-add-direct-linear-load-combination.v2"' \
      "$add_directory/model-ir.json"
    grep -Fq '"terms":[{"factor":0.25,"ref_id":"LC_AXIAL","ref_kind":"load_pattern"},{"factor":1.2,"ref_id":"LC_WEAK","ref_kind":"load_pattern"},{"factor":-0.5,"ref_id":"LC_STRONG","ref_kind":"load_pattern"}]' \
      "$add_directory/edit-receipt.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$add_directory/model-ir.json" \
      --case direct-linear-load-combination-c5 --load-combination COMBO_DIRECT \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/direct-linear-load-combination-$label-request.stdout.json"
    grep -Fq '"schema_version":"structural-native-model-linear-direct-combination-request-create-receipt.v2"' \
      "$request_directory/request-receipt.json"
    grep -Fq '"request_profile":"unique_direct_linear_static_patterns_2_to_64"' \
      "$request_directory/request-receipt.json"
    grep -Fq '"combination_term_count":3' "$request_directory/request-receipt.json"
    grep -Fq '"cpp_linear_assembly_preflight_verified":true' \
      "$request_directory/request-receipt.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$add_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/direct-linear-load-combination-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"load_pattern_id":"COMBO_DIRECT"' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[25000,-12000,5000,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$add_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 0 \
      > "$e2e_root/direct-linear-load-combination-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$add_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/direct-linear-load-combination-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/direct-linear-load-combination-$label-restart-diff.txt"
  done

  local suffix
  for suffix in '' -request -direct -partial -resumed; do
    diff -r "$e2e_root/direct-linear-load-combination-first$suffix" \
      "$e2e_root/direct-linear-load-combination-second$suffix" \
      > "$e2e_root/direct-linear-load-combination$suffix-diff.txt"
  done
  cmp "$e2e_root/direct-linear-load-combination-first.stdout.json" \
    "$e2e_root/direct-linear-load-combination-second.stdout.json"
  for suffix in request direct partial resumed; do
    cmp "$e2e_root/direct-linear-load-combination-first-$suffix.stdout.json" \
      "$e2e_root/direct-linear-load-combination-second-$suffix.stdout.json"
  done
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed direct linear load-combination addition mutated its source ModelIR" >&2
    exit 1
  fi
}
exercise_direct_linear_load_combination_surface

exercise_direct_linear_load_combination_factor_edit_surface() {
  local source_model="$e2e_root/direct-linear-load-combination-first/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"

  local label edit_directory request_directory direct_directory partial_directory
  local resumed_directory
  for label in first second; do
    edit_directory="$e2e_root/direct-linear-load-combination-factor-edit-$label"
    request_directory="$e2e_root/direct-linear-load-combination-factor-edit-$label-request"
    direct_directory="$e2e_root/direct-linear-load-combination-factor-edit-$label-direct"
    partial_directory="$e2e_root/direct-linear-load-combination-factor-edit-$label-partial"
    resumed_directory="$e2e_root/direct-linear-load-combination-factor-edit-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-edit-linear-load-combination-factor "$source_model" \
      --load-combination COMBO_DIRECT --load-pattern LC_WEAK --factor 1.35 \
      --output-dir "$edit_directory" \
      > "$e2e_root/direct-linear-load-combination-factor-edit-$label.stdout.json"
    grep -Fq '"operation":"direct_linear_load_combination_factor_edit"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"editing_profile":"unique_direct_linear_static_patterns_2_to_64"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"load_pattern_id":"LC_WEAK"' "$edit_directory/edit-receipt.json"
    grep -Fq '"previous_factor":1.2' "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_factor":1.35' "$edit_directory/edit-receipt.json"
    grep -Fq '"term_index":1' "$edit_directory/edit-receipt.json"
    grep -Fq '"term_count":3' "$edit_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-edit-direct-linear-load-combination-factor.v1"' \
      "$edit_directory/model-ir.json"
    grep -Fq '"terms":[{"factor":0.25,"ref_id":"LC_AXIAL","ref_kind":"load_pattern"},{"factor":1.35,"ref_id":"LC_WEAK","ref_kind":"load_pattern"},{"factor":-0.5,"ref_id":"LC_STRONG","ref_kind":"load_pattern"}]' \
      "$edit_directory/model-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$edit_directory/model-ir.json" \
      --case direct-linear-load-combination-factor-edit-c5 \
      --load-combination COMBO_DIRECT \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/direct-linear-load-combination-factor-edit-$label-request.stdout.json"
    grep -Fq '"schema_version":"structural-native-model-linear-direct-combination-request-create-receipt.v2"' \
      "$request_directory/request-receipt.json"
    grep -Fq '"combination_term_count":3' "$request_directory/request-receipt.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/direct-linear-load-combination-factor-edit-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"load_pattern_id":"COMBO_DIRECT"' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[25000,-13500,5000,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 0 \
      > "$e2e_root/direct-linear-load-combination-factor-edit-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/direct-linear-load-combination-factor-edit-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/direct-linear-load-combination-factor-edit-$label-restart-diff.txt"
  done

  local suffix
  for suffix in '' -request -direct -partial -resumed; do
    diff -r "$e2e_root/direct-linear-load-combination-factor-edit-first$suffix" \
      "$e2e_root/direct-linear-load-combination-factor-edit-second$suffix" \
      > "$e2e_root/direct-linear-load-combination-factor-edit$suffix-diff.txt"
  done
  cmp "$e2e_root/direct-linear-load-combination-factor-edit-first.stdout.json" \
    "$e2e_root/direct-linear-load-combination-factor-edit-second.stdout.json"
  for suffix in request direct partial resumed; do
    cmp "$e2e_root/direct-linear-load-combination-factor-edit-first-$suffix.stdout.json" \
      "$e2e_root/direct-linear-load-combination-factor-edit-second-$suffix.stdout.json"
  done
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed direct load-combination factor edit mutated its source ModelIR" >&2
    exit 1
  fi

  local no_change_destination="$e2e_root/direct-linear-load-combination-factor-edit-no-change"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-edit-linear-load-combination-factor "$source_model" \
    --load-combination COMBO_DIRECT --load-pattern LC_WEAK --factor 1.2 \
    --output-dir "$no_change_destination" \
    > "$e2e_root/direct-linear-load-combination-factor-edit-no-change.stdout.json"; then
    echo "installed direct load-combination factor editor accepted a no-op" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_edit_no_change' \
    "$e2e_root/direct-linear-load-combination-factor-edit-no-change.stdout.json"
  test ! -e "$no_change_destination"
}
exercise_direct_linear_load_combination_factor_edit_surface

exercise_nested_linear_load_combination_surface() {
  local source_model="$e2e_root/linear-load-combination-add-first/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"

  local label add_directory request_directory direct_directory partial_directory
  local resumed_directory
  for label in first second; do
    add_directory="$e2e_root/nested-linear-load-combination-$label"
    request_directory="$e2e_root/nested-linear-load-combination-$label-request"
    direct_directory="$e2e_root/nested-linear-load-combination-$label-direct"
    partial_directory="$e2e_root/nested-linear-load-combination-$label-partial"
    resumed_directory="$e2e_root/nested-linear-load-combination-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-add-nested-linear-load-combination "$source_model" \
      --load-combination COMBO_NESTED \
      --combination-term COMBO_SERVICE 0.5 --pattern-term LC_AXIAL 0.25 \
      --output-dir "$add_directory" \
      > "$e2e_root/nested-linear-load-combination-$label.stdout.json"
    grep -Fq '"operation":"nested_linear_load_combination_add"' \
      "$add_directory/edit-receipt.json"
    grep -Fq '"authoring_profile":"acyclic_nested_linear_static_depth_8_expanded_terms_64"' \
      "$add_directory/edit-receipt.json"
    grep -Fq '"combination_depth":2' "$add_directory/edit-receipt.json"
    grep -Fq '"expanded_term_count":3' "$add_directory/edit-receipt.json"
    grep -Fq '"expanded_pattern_count":3' "$add_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-add-nested-linear-load-combination.v3"' \
      "$add_directory/model-ir.json"
    grep -Fq '"expanded_pattern_terms":[{"factor":0.6,"ref_id":"LC_WEAK","ref_kind":"load_pattern"},{"factor":-0.25,"ref_id":"LC_STRONG","ref_kind":"load_pattern"},{"factor":0.25,"ref_id":"LC_AXIAL","ref_kind":"load_pattern"}]' \
      "$add_directory/edit-receipt.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$add_directory/model-ir.json" \
      --case nested-linear-load-combination-c5 --load-combination COMBO_NESTED \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/nested-linear-load-combination-$label-request.stdout.json"
    grep -Fq '"schema_version":"structural-native-model-linear-nested-combination-request-create-receipt.v3"' \
      "$request_directory/request-receipt.json"
    grep -Fq '"request_profile":"acyclic_nested_linear_static_depth_8_expanded_terms_64"' \
      "$request_directory/request-receipt.json"
    grep -Fq '"combination_depth":2' "$request_directory/request-receipt.json"
    grep -Fq '"expanded_term_count":3' "$request_directory/request-receipt.json"
    grep -Fq '"cpp_linear_assembly_preflight_verified":true' \
      "$request_directory/request-receipt.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$add_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/nested-linear-load-combination-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"load_pattern_id":"COMBO_NESTED"' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[25000,-6000,2500,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$add_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 0 \
      > "$e2e_root/nested-linear-load-combination-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$add_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/nested-linear-load-combination-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/nested-linear-load-combination-$label-restart-diff.txt"
  done

  local suffix
  for suffix in '' -request -direct -partial -resumed; do
    diff -r "$e2e_root/nested-linear-load-combination-first$suffix" \
      "$e2e_root/nested-linear-load-combination-second$suffix" \
      > "$e2e_root/nested-linear-load-combination$suffix-diff.txt"
  done
  cmp "$e2e_root/nested-linear-load-combination-first.stdout.json" \
    "$e2e_root/nested-linear-load-combination-second.stdout.json"
  for suffix in request direct partial resumed; do
    cmp "$e2e_root/nested-linear-load-combination-first-$suffix.stdout.json" \
      "$e2e_root/nested-linear-load-combination-second-$suffix.stdout.json"
  done
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed nested linear load-combination addition mutated its source ModelIR" >&2
    exit 1
  fi
}
exercise_nested_linear_load_combination_surface

exercise_nested_linear_load_combination_factor_edit_surface() {
  local source_model="$e2e_root/nested-linear-load-combination-first/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"

  local label edit_directory request_directory direct_directory partial_directory
  local resumed_directory
  for label in first second; do
    edit_directory="$e2e_root/nested-linear-load-combination-factor-edit-$label"
    request_directory="$e2e_root/nested-linear-load-combination-factor-edit-$label-request"
    direct_directory="$e2e_root/nested-linear-load-combination-factor-edit-$label-direct"
    partial_directory="$e2e_root/nested-linear-load-combination-factor-edit-$label-partial"
    resumed_directory="$e2e_root/nested-linear-load-combination-factor-edit-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-edit-nested-linear-load-combination-factor "$source_model" \
      --load-combination COMBO_NESTED --ref-kind load_combination \
      --ref-id COMBO_SERVICE --factor 0.75 --output-dir "$edit_directory" \
      > "$e2e_root/nested-linear-load-combination-factor-edit-$label.stdout.json"
    grep -Fq '"operation":"nested_linear_load_combination_factor_edit"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"editing_profile":"acyclic_nested_linear_static_depth_8_expanded_terms_64"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"reference_kind":"load_combination"' "$edit_directory/edit-receipt.json"
    grep -Fq '"reference_id":"COMBO_SERVICE"' "$edit_directory/edit-receipt.json"
    grep -Fq '"previous_factor":0.5' "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_factor":0.75' "$edit_directory/edit-receipt.json"
    grep -Fq '"term_index":0' "$edit_directory/edit-receipt.json"
    grep -Fq '"term_count":2' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_combination_depth":2' "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_combination_depth":2' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_expanded_term_count":3' "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_expanded_term_count":3' "$edit_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-edit-nested-linear-load-combination-factor.v1"' \
      "$edit_directory/model-ir.json"
    grep -Fq '"terms":[{"factor":0.75,"ref_id":"COMBO_SERVICE","ref_kind":"load_combination"},{"factor":0.25,"ref_id":"LC_AXIAL","ref_kind":"load_pattern"}]' \
      "$edit_directory/model-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$edit_directory/model-ir.json" \
      --case nested-linear-load-combination-factor-edit-c5 \
      --load-combination COMBO_NESTED \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/nested-linear-load-combination-factor-edit-$label-request.stdout.json"
    grep -Fq '"schema_version":"structural-native-model-linear-nested-combination-request-create-receipt.v3"' \
      "$request_directory/request-receipt.json"
    grep -Fq '"combination_depth":2' "$request_directory/request-receipt.json"
    grep -Fq '"expanded_term_count":3' "$request_directory/request-receipt.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/nested-linear-load-combination-factor-edit-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"load_pattern_id":"COMBO_NESTED"' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[25000,-9000,3750,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 0 \
      > "$e2e_root/nested-linear-load-combination-factor-edit-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/nested-linear-load-combination-factor-edit-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/nested-linear-load-combination-factor-edit-$label-restart-diff.txt"
  done

  local suffix
  for suffix in '' -request -direct -partial -resumed; do
    diff -r "$e2e_root/nested-linear-load-combination-factor-edit-first$suffix" \
      "$e2e_root/nested-linear-load-combination-factor-edit-second$suffix" \
      > "$e2e_root/nested-linear-load-combination-factor-edit$suffix-diff.txt"
  done
  cmp "$e2e_root/nested-linear-load-combination-factor-edit-first.stdout.json" \
    "$e2e_root/nested-linear-load-combination-factor-edit-second.stdout.json"
  for suffix in request direct partial resumed; do
    cmp "$e2e_root/nested-linear-load-combination-factor-edit-first-$suffix.stdout.json" \
      "$e2e_root/nested-linear-load-combination-factor-edit-second-$suffix.stdout.json"
  done
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed nested load-combination factor edit mutated its source ModelIR" >&2
    exit 1
  fi

  local no_change_destination="$e2e_root/nested-linear-load-combination-factor-edit-no-change"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-edit-nested-linear-load-combination-factor "$source_model" \
    --load-combination COMBO_NESTED --ref-kind load_combination \
    --ref-id COMBO_SERVICE --factor 0.5 --output-dir "$no_change_destination" \
    > "$e2e_root/nested-linear-load-combination-factor-edit-no-change.stdout.json"; then
    echo "installed nested load-combination factor editor accepted a no-op" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_edit_no_change' \
    "$e2e_root/nested-linear-load-combination-factor-edit-no-change.stdout.json"
  test ! -e "$no_change_destination"

  local typed_mismatch_destination="$e2e_root/nested-linear-load-combination-factor-edit-typed-mismatch"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-edit-nested-linear-load-combination-factor "$source_model" \
    --load-combination COMBO_NESTED --ref-kind load_pattern \
    --ref-id COMBO_SERVICE --factor 0.75 --output-dir "$typed_mismatch_destination" \
    > "$e2e_root/nested-linear-load-combination-factor-edit-typed-mismatch.stdout.json"; then
    echo "installed nested load-combination factor editor accepted a typed mismatch" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_edit_nested_linear_load_combination_term_missing' \
    "$e2e_root/nested-linear-load-combination-factor-edit-typed-mismatch.stdout.json"
  test ! -e "$typed_mismatch_destination"
}
exercise_nested_linear_load_combination_factor_edit_surface

exercise_direct_linear_load_combination_reference_edit_surface() {
  local source_model="$e2e_root/linear-load-combination-add-first/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"

  local label edit_directory request_directory direct_directory partial_directory
  local resumed_directory
  for label in first second; do
    edit_directory="$e2e_root/direct-linear-load-combination-reference-edit-$label"
    request_directory="$e2e_root/direct-linear-load-combination-reference-edit-$label-request"
    direct_directory="$e2e_root/direct-linear-load-combination-reference-edit-$label-direct"
    partial_directory="$e2e_root/direct-linear-load-combination-reference-edit-$label-partial"
    resumed_directory="$e2e_root/direct-linear-load-combination-reference-edit-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-edit-linear-load-combination-reference "$source_model" \
      --load-combination COMBO_SERVICE --load-pattern LC_WEAK \
      --replacement-load-pattern LC_AXIAL --output-dir "$edit_directory" \
      > "$e2e_root/direct-linear-load-combination-reference-edit-$label.stdout.json"
    grep -Fq '"operation":"direct_linear_load_combination_reference_edit"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"editing_profile":"unique_direct_linear_static_patterns_2_to_64"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"load_pattern_id":"LC_WEAK"' "$edit_directory/edit-receipt.json"
    grep -Fq '"replacement_load_pattern_id":"LC_AXIAL"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"preserved_factor":1.2' "$edit_directory/edit-receipt.json"
    grep -Fq '"term_index":0' "$edit_directory/edit-receipt.json"
    grep -Fq '"term_count":2' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_terms":[{"factor":1.2,"ref_id":"LC_WEAK","ref_kind":"load_pattern"},{"factor":-0.5,"ref_id":"LC_STRONG","ref_kind":"load_pattern"}]' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_terms":[{"factor":1.2,"ref_id":"LC_AXIAL","ref_kind":"load_pattern"},{"factor":-0.5,"ref_id":"LC_STRONG","ref_kind":"load_pattern"}]' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-edit-direct-linear-load-combination-reference.v1"' \
      "$edit_directory/model-ir.json"
    grep -Fq '"terms":[{"factor":1.2,"ref_id":"LC_AXIAL","ref_kind":"load_pattern"},{"factor":-0.5,"ref_id":"LC_STRONG","ref_kind":"load_pattern"}]' \
      "$edit_directory/model-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$edit_directory/model-ir.json" \
      --case direct-linear-load-combination-reference-edit-c5 \
      --load-combination COMBO_SERVICE \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/direct-linear-load-combination-reference-edit-$label-request.stdout.json"
    grep -Fq '"schema_version":"structural-native-model-linear-combination-request-create-receipt.v1"' \
      "$request_directory/request-receipt.json"
    grep -Fq '"load_combination_id":"COMBO_SERVICE"' \
      "$request_directory/request-receipt.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/direct-linear-load-combination-reference-edit-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"load_pattern_id":"COMBO_SERVICE"' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[120000,0,5000,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 0 \
      > "$e2e_root/direct-linear-load-combination-reference-edit-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/direct-linear-load-combination-reference-edit-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/direct-linear-load-combination-reference-edit-$label-restart-diff.txt"
  done

  local suffix
  for suffix in '' -request -direct -partial -resumed; do
    diff -r "$e2e_root/direct-linear-load-combination-reference-edit-first$suffix" \
      "$e2e_root/direct-linear-load-combination-reference-edit-second$suffix" \
      > "$e2e_root/direct-linear-load-combination-reference-edit$suffix-diff.txt"
  done
  cmp "$e2e_root/direct-linear-load-combination-reference-edit-first.stdout.json" \
    "$e2e_root/direct-linear-load-combination-reference-edit-second.stdout.json"
  for suffix in request direct partial resumed; do
    cmp "$e2e_root/direct-linear-load-combination-reference-edit-first-$suffix.stdout.json" \
      "$e2e_root/direct-linear-load-combination-reference-edit-second-$suffix.stdout.json"
  done
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed direct load-combination reference edit mutated its source ModelIR" >&2
    exit 1
  fi

  local replacement expected_code destination
  for label in no-change duplicate missing; do
    case "$label" in
      no-change)
        replacement="LC_WEAK"
        expected_code="workbench_model_edit_no_change"
        ;;
      duplicate)
        replacement="LC_STRONG"
        expected_code="workbench_model_edit_linear_load_combination_replacement_pattern_duplicate"
        ;;
      missing)
        replacement="LC_MISSING"
        expected_code="workbench_model_edit_linear_load_combination_replacement_pattern_missing"
        ;;
    esac
    destination="$e2e_root/direct-linear-load-combination-reference-edit-$label-rejected"
    if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-edit-linear-load-combination-reference "$source_model" \
      --load-combination COMBO_SERVICE --load-pattern LC_WEAK \
      --replacement-load-pattern "$replacement" --output-dir "$destination" \
      > "$e2e_root/direct-linear-load-combination-reference-edit-$label-rejected.stdout.json"; then
      echo "installed direct load-combination reference editor accepted $label input" >&2
      exit 1
    fi
    grep -Fq "$expected_code" \
      "$e2e_root/direct-linear-load-combination-reference-edit-$label-rejected.stdout.json"
    test ! -e "$destination"
  done
}
exercise_direct_linear_load_combination_reference_edit_surface

exercise_direct_linear_load_combination_term_add_surface() {
  local source_model="$e2e_root/linear-load-combination-add-first/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"

  local label edit_directory request_directory direct_directory partial_directory
  local resumed_directory
  for label in first second; do
    edit_directory="$e2e_root/direct-linear-load-combination-term-add-$label"
    request_directory="$e2e_root/direct-linear-load-combination-term-add-$label-request"
    direct_directory="$e2e_root/direct-linear-load-combination-term-add-$label-direct"
    partial_directory="$e2e_root/direct-linear-load-combination-term-add-$label-partial"
    resumed_directory="$e2e_root/direct-linear-load-combination-term-add-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-add-linear-load-combination-term "$source_model" \
      --load-combination COMBO_SERVICE --load-pattern LC_AXIAL --factor 0.25 \
      --output-dir "$edit_directory" \
      > "$e2e_root/direct-linear-load-combination-term-add-$label.stdout.json"
    grep -Fq '"operation":"direct_linear_load_combination_term_add"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"editing_profile":"unique_direct_linear_static_patterns_3_to_64"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"load_pattern_id":"LC_AXIAL"' "$edit_directory/edit-receipt.json"
    grep -Fq '"factor":0.25' "$edit_directory/edit-receipt.json"
    grep -Fq '"term_index":2' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_term_count":2' "$edit_directory/edit-receipt.json"
    grep -Fq '"term_count":3' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_terms":[{"factor":1.2,"ref_id":"LC_WEAK","ref_kind":"load_pattern"},{"factor":-0.5,"ref_id":"LC_STRONG","ref_kind":"load_pattern"}]' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_terms":[{"factor":1.2,"ref_id":"LC_WEAK","ref_kind":"load_pattern"},{"factor":-0.5,"ref_id":"LC_STRONG","ref_kind":"load_pattern"},{"factor":0.25,"ref_id":"LC_AXIAL","ref_kind":"load_pattern"}]' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-add-direct-linear-load-combination-term.v1"' \
      "$edit_directory/model-ir.json"
    grep -Fq '"terms":[{"factor":1.2,"ref_id":"LC_WEAK","ref_kind":"load_pattern"},{"factor":-0.5,"ref_id":"LC_STRONG","ref_kind":"load_pattern"},{"factor":0.25,"ref_id":"LC_AXIAL","ref_kind":"load_pattern"}]' \
      "$edit_directory/model-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$edit_directory/model-ir.json" \
      --case direct-linear-load-combination-term-add-c5 \
      --load-combination COMBO_SERVICE \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/direct-linear-load-combination-term-add-$label-request.stdout.json"
    grep -Fq '"schema_version":"structural-native-model-linear-direct-combination-request-create-receipt.v2"' \
      "$request_directory/request-receipt.json"
    grep -Fq '"combination_term_count":3' "$request_directory/request-receipt.json"
    grep -Fq '"load_combination_id":"COMBO_SERVICE"' \
      "$request_directory/request-receipt.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/direct-linear-load-combination-term-add-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"load_pattern_id":"COMBO_SERVICE"' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[25000,-12000,5000,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 0 \
      > "$e2e_root/direct-linear-load-combination-term-add-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/direct-linear-load-combination-term-add-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/direct-linear-load-combination-term-add-$label-restart-diff.txt"
  done

  local suffix
  for suffix in '' -request -direct -partial -resumed; do
    diff -r "$e2e_root/direct-linear-load-combination-term-add-first$suffix" \
      "$e2e_root/direct-linear-load-combination-term-add-second$suffix" \
      > "$e2e_root/direct-linear-load-combination-term-add$suffix-diff.txt"
  done
  cmp "$e2e_root/direct-linear-load-combination-term-add-first.stdout.json" \
    "$e2e_root/direct-linear-load-combination-term-add-second.stdout.json"
  for suffix in request direct partial resumed; do
    cmp "$e2e_root/direct-linear-load-combination-term-add-first-$suffix.stdout.json" \
      "$e2e_root/direct-linear-load-combination-term-add-second-$suffix.stdout.json"
  done
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed direct load-combination term addition mutated its source ModelIR" >&2
    exit 1
  fi

  local pattern expected_code destination
  for label in duplicate missing; do
    case "$label" in
      duplicate)
        pattern="LC_WEAK"
        expected_code="workbench_model_add_direct_linear_load_combination_term_pattern_duplicate"
        ;;
      missing)
        pattern="LC_MISSING"
        expected_code="workbench_model_add_direct_linear_load_combination_term_pattern_missing"
        ;;
    esac
    destination="$e2e_root/direct-linear-load-combination-term-add-$label-rejected"
    if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-add-linear-load-combination-term "$source_model" \
      --load-combination COMBO_SERVICE --load-pattern "$pattern" --factor 0.25 \
      --output-dir "$destination" \
      > "$e2e_root/direct-linear-load-combination-term-add-$label-rejected.stdout.json"; then
      echo "installed direct load-combination term addition accepted $label input" >&2
      exit 1
    fi
    grep -Fq "$expected_code" \
      "$e2e_root/direct-linear-load-combination-term-add-$label-rejected.stdout.json"
    test ! -e "$destination"
  done
}
exercise_direct_linear_load_combination_term_add_surface

exercise_direct_linear_load_combination_term_delete_surface() {
  local source_model="$e2e_root/direct-linear-load-combination-term-add-first/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"

  local label edit_directory request_directory direct_directory partial_directory
  local resumed_directory
  for label in first second; do
    edit_directory="$e2e_root/direct-linear-load-combination-term-delete-$label"
    request_directory="$e2e_root/direct-linear-load-combination-term-delete-$label-request"
    direct_directory="$e2e_root/direct-linear-load-combination-term-delete-$label-direct"
    partial_directory="$e2e_root/direct-linear-load-combination-term-delete-$label-partial"
    resumed_directory="$e2e_root/direct-linear-load-combination-term-delete-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-delete-linear-load-combination-term "$source_model" \
      --load-combination COMBO_SERVICE --load-pattern LC_STRONG \
      --output-dir "$edit_directory" \
      > "$e2e_root/direct-linear-load-combination-term-delete-$label.stdout.json"
    grep -Fq '"operation":"direct_linear_load_combination_term_delete"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"editing_profile":"unique_direct_linear_static_patterns_2_to_63"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"load_pattern_id":"LC_STRONG"' "$edit_directory/edit-receipt.json"
    grep -Fq '"removed_factor":-0.5' "$edit_directory/edit-receipt.json"
    grep -Fq '"term_index":1' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_term_count":3' "$edit_directory/edit-receipt.json"
    grep -Fq '"term_count":2' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_terms":[{"factor":1.2,"ref_id":"LC_WEAK","ref_kind":"load_pattern"},{"factor":-0.5,"ref_id":"LC_STRONG","ref_kind":"load_pattern"},{"factor":0.25,"ref_id":"LC_AXIAL","ref_kind":"load_pattern"}]' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_terms":[{"factor":1.2,"ref_id":"LC_WEAK","ref_kind":"load_pattern"},{"factor":0.25,"ref_id":"LC_AXIAL","ref_kind":"load_pattern"}]' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-delete-direct-linear-load-combination-term.v1"' \
      "$edit_directory/model-ir.json"
    grep -Fq '"terms":[{"factor":1.2,"ref_id":"LC_WEAK","ref_kind":"load_pattern"},{"factor":0.25,"ref_id":"LC_AXIAL","ref_kind":"load_pattern"}]' \
      "$edit_directory/model-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$edit_directory/model-ir.json" \
      --case direct-linear-load-combination-term-delete-c5 \
      --load-combination COMBO_SERVICE \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/direct-linear-load-combination-term-delete-$label-request.stdout.json"
    grep -Fq '"schema_version":"structural-native-model-linear-combination-request-create-receipt.v1"' \
      "$request_directory/request-receipt.json"
    grep -Fq '"load_combination_id":"COMBO_SERVICE"' \
      "$request_directory/request-receipt.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/direct-linear-load-combination-term-delete-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"load_pattern_id":"COMBO_SERVICE"' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[25000,-12000,0,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 0 \
      > "$e2e_root/direct-linear-load-combination-term-delete-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/direct-linear-load-combination-term-delete-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/direct-linear-load-combination-term-delete-$label-restart-diff.txt"
  done

  local suffix
  for suffix in '' -request -direct -partial -resumed; do
    diff -r "$e2e_root/direct-linear-load-combination-term-delete-first$suffix" \
      "$e2e_root/direct-linear-load-combination-term-delete-second$suffix" \
      > "$e2e_root/direct-linear-load-combination-term-delete$suffix-diff.txt"
  done
  cmp "$e2e_root/direct-linear-load-combination-term-delete-first.stdout.json" \
    "$e2e_root/direct-linear-load-combination-term-delete-second.stdout.json"
  for suffix in request direct partial resumed; do
    cmp "$e2e_root/direct-linear-load-combination-term-delete-first-$suffix.stdout.json" \
      "$e2e_root/direct-linear-load-combination-term-delete-second-$suffix.stdout.json"
  done
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed direct load-combination term deletion mutated its source ModelIR" >&2
    exit 1
  fi

  local missing_destination="$e2e_root/direct-linear-load-combination-term-delete-missing-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-delete-linear-load-combination-term "$source_model" \
    --load-combination COMBO_SERVICE --load-pattern LC_MISSING \
    --output-dir "$missing_destination" \
    > "$e2e_root/direct-linear-load-combination-term-delete-missing-rejected.stdout.json"; then
    echo "installed direct load-combination term deletion accepted a missing term" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_delete_direct_linear_load_combination_term_pattern_missing' \
    "$e2e_root/direct-linear-load-combination-term-delete-missing-rejected.stdout.json"
  test ! -e "$missing_destination"

  local minimum_source="$e2e_root/linear-load-combination-add-first/model-ir.json"
  local minimum_destination="$e2e_root/direct-linear-load-combination-term-delete-minimum-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-delete-linear-load-combination-term "$minimum_source" \
    --load-combination COMBO_SERVICE --load-pattern LC_STRONG \
    --output-dir "$minimum_destination" \
    > "$e2e_root/direct-linear-load-combination-term-delete-minimum-rejected.stdout.json"; then
    echo "installed direct load-combination term deletion accepted a two-term source" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_delete_direct_linear_load_combination_term_count_invalid' \
    "$e2e_root/direct-linear-load-combination-term-delete-minimum-rejected.stdout.json"
  test ! -e "$minimum_destination"
}
exercise_direct_linear_load_combination_term_delete_surface

exercise_nested_linear_load_combination_term_add_surface() {
  local source_model="$e2e_root/nested-linear-load-combination-first/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"

  local label edit_directory request_directory direct_directory partial_directory
  local resumed_directory
  for label in first second; do
    edit_directory="$e2e_root/nested-linear-load-combination-term-add-$label"
    request_directory="$e2e_root/nested-linear-load-combination-term-add-$label-request"
    direct_directory="$e2e_root/nested-linear-load-combination-term-add-$label-direct"
    partial_directory="$e2e_root/nested-linear-load-combination-term-add-$label-partial"
    resumed_directory="$e2e_root/nested-linear-load-combination-term-add-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-add-nested-linear-load-combination-term "$source_model" \
      --load-combination COMBO_NESTED --ref-kind load_pattern \
      --ref-id LC_STRONG --factor 0.1 --output-dir "$edit_directory" \
      > "$e2e_root/nested-linear-load-combination-term-add-$label.stdout.json"
    grep -Fq '"operation":"nested_linear_load_combination_term_add"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"editing_profile":"acyclic_nested_linear_static_depth_8_expanded_terms_64"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"reference_kind":"load_pattern"' "$edit_directory/edit-receipt.json"
    grep -Fq '"reference_id":"LC_STRONG"' "$edit_directory/edit-receipt.json"
    grep -Fq '"factor":0.1' "$edit_directory/edit-receipt.json"
    grep -Fq '"term_index":2' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_term_count":2' "$edit_directory/edit-receipt.json"
    grep -Fq '"term_count":3' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_combination_depth":2' "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_combination_depth":2' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_expanded_term_count":3' "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_expanded_term_count":4' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_expanded_pattern_count":3' "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_expanded_pattern_count":3' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_terms":[{"factor":0.5,"ref_id":"COMBO_SERVICE","ref_kind":"load_combination"},{"factor":0.25,"ref_id":"LC_AXIAL","ref_kind":"load_pattern"}]' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_terms":[{"factor":0.5,"ref_id":"COMBO_SERVICE","ref_kind":"load_combination"},{"factor":0.25,"ref_id":"LC_AXIAL","ref_kind":"load_pattern"},{"factor":0.1,"ref_id":"LC_STRONG","ref_kind":"load_pattern"}]' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_expanded_pattern_terms":[{"factor":0.6,"ref_id":"LC_WEAK","ref_kind":"load_pattern"},{"factor":-0.15,"ref_id":"LC_STRONG","ref_kind":"load_pattern"},{"factor":0.25,"ref_id":"LC_AXIAL","ref_kind":"load_pattern"}]' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-add-nested-linear-load-combination-term.v1"' \
      "$edit_directory/model-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$edit_directory/model-ir.json" \
      --case nested-linear-load-combination-term-add-c5 \
      --load-combination COMBO_NESTED \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/nested-linear-load-combination-term-add-$label-request.stdout.json"
    grep -Fq '"schema_version":"structural-native-model-linear-nested-combination-request-create-receipt.v3"' \
      "$request_directory/request-receipt.json"
    grep -Fq '"load_combination_id":"COMBO_NESTED"' \
      "$request_directory/request-receipt.json"
    grep -Fq '"combination_depth":2' "$request_directory/request-receipt.json"
    grep -Fq '"expanded_term_count":4' "$request_directory/request-receipt.json"
    grep -Fq '"expanded_pattern_count":3' "$request_directory/request-receipt.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/nested-linear-load-combination-term-add-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"load_pattern_id":"COMBO_NESTED"' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[25000,-6000,1500,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 0 \
      > "$e2e_root/nested-linear-load-combination-term-add-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/nested-linear-load-combination-term-add-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/nested-linear-load-combination-term-add-$label-restart-diff.txt"
  done

  local suffix
  for suffix in '' -request -direct -partial -resumed; do
    diff -r "$e2e_root/nested-linear-load-combination-term-add-first$suffix" \
      "$e2e_root/nested-linear-load-combination-term-add-second$suffix" \
      > "$e2e_root/nested-linear-load-combination-term-add$suffix-diff.txt"
  done
  cmp "$e2e_root/nested-linear-load-combination-term-add-first.stdout.json" \
    "$e2e_root/nested-linear-load-combination-term-add-second.stdout.json"
  for suffix in request direct partial resumed; do
    cmp "$e2e_root/nested-linear-load-combination-term-add-first-$suffix.stdout.json" \
      "$e2e_root/nested-linear-load-combination-term-add-second-$suffix.stdout.json"
  done
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed nested load-combination term addition mutated its source ModelIR" >&2
    exit 1
  fi

  local duplicate_destination="$e2e_root/nested-linear-load-combination-term-add-duplicate-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-add-nested-linear-load-combination-term "$source_model" \
    --load-combination COMBO_NESTED --ref-kind load_pattern \
    --ref-id LC_AXIAL --factor 0.1 --output-dir "$duplicate_destination" \
    > "$e2e_root/nested-linear-load-combination-term-add-duplicate-rejected.stdout.json"; then
    echo "installed nested load-combination term addition accepted a duplicate reference" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_add_nested_linear_load_combination_term_reference_duplicate' \
    "$e2e_root/nested-linear-load-combination-term-add-duplicate-rejected.stdout.json"
  test ! -e "$duplicate_destination"

  local missing_destination="$e2e_root/nested-linear-load-combination-term-add-missing-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-add-nested-linear-load-combination-term "$source_model" \
    --load-combination COMBO_NESTED --ref-kind load_pattern \
    --ref-id LC_MISSING --factor 0.1 --output-dir "$missing_destination" \
    > "$e2e_root/nested-linear-load-combination-term-add-missing-rejected.stdout.json"; then
    echo "installed nested load-combination term addition accepted a missing reference" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_add_nested_linear_load_combination_term_pattern_missing' \
    "$e2e_root/nested-linear-load-combination-term-add-missing-rejected.stdout.json"
  test ! -e "$missing_destination"
}
exercise_nested_linear_load_combination_term_add_surface

exercise_nested_linear_load_combination_term_insert_surface() {
  local source_model="$e2e_root/nested-linear-load-combination-first/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"

  local label edit_directory request_directory direct_directory partial_directory
  local resumed_directory
  for label in first second; do
    edit_directory="$e2e_root/nested-linear-load-combination-term-insert-$label"
    request_directory="$e2e_root/nested-linear-load-combination-term-insert-$label-request"
    direct_directory="$e2e_root/nested-linear-load-combination-term-insert-$label-direct"
    partial_directory="$e2e_root/nested-linear-load-combination-term-insert-$label-partial"
    resumed_directory="$e2e_root/nested-linear-load-combination-term-insert-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-insert-nested-linear-load-combination-term "$source_model" \
      --load-combination COMBO_NESTED --ref-kind load_pattern \
      --ref-id LC_STRONG --factor 0.1 --at-index 1 --output-dir "$edit_directory" \
      > "$e2e_root/nested-linear-load-combination-term-insert-$label.stdout.json"
    grep -Fq '"operation":"nested_linear_load_combination_term_insert"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"editing_profile":"acyclic_nested_linear_static_depth_8_expanded_terms_64"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"reference_kind":"load_pattern"' "$edit_directory/edit-receipt.json"
    grep -Fq '"reference_id":"LC_STRONG"' "$edit_directory/edit-receipt.json"
    grep -Fq '"factor":0.1' "$edit_directory/edit-receipt.json"
    grep -Fq '"term_index":1' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_term_count":2' "$edit_directory/edit-receipt.json"
    grep -Fq '"term_count":3' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_combination_depth":2' "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_combination_depth":2' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_expanded_term_count":3' "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_expanded_term_count":4' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_expanded_pattern_count":3' "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_expanded_pattern_count":3' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_terms":[{"factor":0.5,"ref_id":"COMBO_SERVICE","ref_kind":"load_combination"},{"factor":0.25,"ref_id":"LC_AXIAL","ref_kind":"load_pattern"}]' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_terms":[{"factor":0.5,"ref_id":"COMBO_SERVICE","ref_kind":"load_combination"},{"factor":0.1,"ref_id":"LC_STRONG","ref_kind":"load_pattern"},{"factor":0.25,"ref_id":"LC_AXIAL","ref_kind":"load_pattern"}]' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_expanded_pattern_terms":[{"factor":0.6,"ref_id":"LC_WEAK","ref_kind":"load_pattern"},{"factor":-0.15,"ref_id":"LC_STRONG","ref_kind":"load_pattern"},{"factor":0.25,"ref_id":"LC_AXIAL","ref_kind":"load_pattern"}]' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-insert-nested-linear-load-combination-term.v1"' \
      "$edit_directory/model-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$edit_directory/model-ir.json" \
      --case nested-linear-load-combination-term-insert-c5 \
      --load-combination COMBO_NESTED \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/nested-linear-load-combination-term-insert-$label-request.stdout.json"
    grep -Fq '"schema_version":"structural-native-model-linear-nested-combination-request-create-receipt.v3"' \
      "$request_directory/request-receipt.json"
    grep -Fq '"load_combination_id":"COMBO_NESTED"' \
      "$request_directory/request-receipt.json"
    grep -Fq '"combination_depth":2' "$request_directory/request-receipt.json"
    grep -Fq '"expanded_term_count":4' "$request_directory/request-receipt.json"
    grep -Fq '"expanded_pattern_count":3' "$request_directory/request-receipt.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/nested-linear-load-combination-term-insert-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"load_pattern_id":"COMBO_NESTED"' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[25000,-6000,1500,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 0 \
      > "$e2e_root/nested-linear-load-combination-term-insert-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/nested-linear-load-combination-term-insert-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/nested-linear-load-combination-term-insert-$label-restart-diff.txt"
  done

  local suffix
  for suffix in '' -request -direct -partial -resumed; do
    diff -r "$e2e_root/nested-linear-load-combination-term-insert-first$suffix" \
      "$e2e_root/nested-linear-load-combination-term-insert-second$suffix" \
      > "$e2e_root/nested-linear-load-combination-term-insert$suffix-diff.txt"
  done
  cmp "$e2e_root/nested-linear-load-combination-term-insert-first.stdout.json" \
    "$e2e_root/nested-linear-load-combination-term-insert-second.stdout.json"
  for suffix in request direct partial resumed; do
    cmp "$e2e_root/nested-linear-load-combination-term-insert-first-$suffix.stdout.json" \
      "$e2e_root/nested-linear-load-combination-term-insert-second-$suffix.stdout.json"
  done
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed nested load-combination term insertion mutated its source ModelIR" >&2
    exit 1
  fi

  local duplicate_destination="$e2e_root/nested-linear-load-combination-term-insert-duplicate-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-insert-nested-linear-load-combination-term "$source_model" \
    --load-combination COMBO_NESTED --ref-kind load_pattern \
    --ref-id LC_AXIAL --factor 0.1 --at-index 1 --output-dir "$duplicate_destination" \
    > "$e2e_root/nested-linear-load-combination-term-insert-duplicate-rejected.stdout.json"; then
    echo "installed nested load-combination term insertion accepted a duplicate reference" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_insert_nested_linear_load_combination_term_reference_duplicate' \
    "$e2e_root/nested-linear-load-combination-term-insert-duplicate-rejected.stdout.json"
  test ! -e "$duplicate_destination"

  local range_destination="$e2e_root/nested-linear-load-combination-term-insert-range-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-insert-nested-linear-load-combination-term "$source_model" \
    --load-combination COMBO_NESTED --ref-kind load_pattern \
    --ref-id LC_STRONG --factor 0.1 --at-index 3 --output-dir "$range_destination" \
    > "$e2e_root/nested-linear-load-combination-term-insert-range-rejected.stdout.json"; then
    echo "installed nested load-combination term insertion accepted an out-of-range target" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_insert_nested_linear_load_combination_term_target_index_invalid' \
    "$e2e_root/nested-linear-load-combination-term-insert-range-rejected.stdout.json"
  test ! -e "$range_destination"

  local missing_destination="$e2e_root/nested-linear-load-combination-term-insert-missing-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-insert-nested-linear-load-combination-term "$source_model" \
    --load-combination COMBO_NESTED --ref-kind load_pattern \
    --ref-id LC_MISSING --factor 0.1 --at-index 1 --output-dir "$missing_destination" \
    > "$e2e_root/nested-linear-load-combination-term-insert-missing-rejected.stdout.json"; then
    echo "installed nested load-combination term insertion accepted a missing reference" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_insert_nested_linear_load_combination_term_pattern_missing' \
    "$e2e_root/nested-linear-load-combination-term-insert-missing-rejected.stdout.json"
  test ! -e "$missing_destination"
}
exercise_nested_linear_load_combination_term_insert_surface

exercise_nested_linear_load_combination_term_delete_surface() {
  local source_model="$e2e_root/nested-linear-load-combination-term-add-first/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"

  local label edit_directory request_directory direct_directory partial_directory
  local resumed_directory
  for label in first second; do
    edit_directory="$e2e_root/nested-linear-load-combination-term-delete-$label"
    request_directory="$e2e_root/nested-linear-load-combination-term-delete-$label-request"
    direct_directory="$e2e_root/nested-linear-load-combination-term-delete-$label-direct"
    partial_directory="$e2e_root/nested-linear-load-combination-term-delete-$label-partial"
    resumed_directory="$e2e_root/nested-linear-load-combination-term-delete-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-delete-nested-linear-load-combination-term "$source_model" \
      --load-combination COMBO_NESTED --ref-kind load_pattern \
      --ref-id LC_AXIAL --output-dir "$edit_directory" \
      > "$e2e_root/nested-linear-load-combination-term-delete-$label.stdout.json"
    grep -Fq '"operation":"nested_linear_load_combination_term_delete"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"editing_profile":"acyclic_nested_linear_static_depth_8_expanded_terms_64"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"reference_kind":"load_pattern"' "$edit_directory/edit-receipt.json"
    grep -Fq '"reference_id":"LC_AXIAL"' "$edit_directory/edit-receipt.json"
    grep -Fq '"removed_factor":0.25' "$edit_directory/edit-receipt.json"
    grep -Fq '"term_index":1' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_term_count":3' "$edit_directory/edit-receipt.json"
    grep -Fq '"term_count":2' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_combination_depth":2' "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_combination_depth":2' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_expanded_term_count":4' "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_expanded_term_count":3' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_expanded_pattern_count":3' "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_expanded_pattern_count":2' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_terms":[{"factor":0.5,"ref_id":"COMBO_SERVICE","ref_kind":"load_combination"},{"factor":0.25,"ref_id":"LC_AXIAL","ref_kind":"load_pattern"},{"factor":0.1,"ref_id":"LC_STRONG","ref_kind":"load_pattern"}]' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_terms":[{"factor":0.5,"ref_id":"COMBO_SERVICE","ref_kind":"load_combination"},{"factor":0.1,"ref_id":"LC_STRONG","ref_kind":"load_pattern"}]' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_expanded_pattern_terms":[{"factor":0.6,"ref_id":"LC_WEAK","ref_kind":"load_pattern"},{"factor":-0.15,"ref_id":"LC_STRONG","ref_kind":"load_pattern"}]' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-delete-nested-linear-load-combination-term.v1"' \
      "$edit_directory/model-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$edit_directory/model-ir.json" \
      --case nested-linear-load-combination-term-delete-c5 \
      --load-combination COMBO_NESTED \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/nested-linear-load-combination-term-delete-$label-request.stdout.json"
    grep -Fq '"schema_version":"structural-native-model-linear-nested-combination-request-create-receipt.v3"' \
      "$request_directory/request-receipt.json"
    grep -Fq '"load_combination_id":"COMBO_NESTED"' \
      "$request_directory/request-receipt.json"
    grep -Fq '"combination_depth":2' "$request_directory/request-receipt.json"
    grep -Fq '"expanded_term_count":3' "$request_directory/request-receipt.json"
    grep -Fq '"expanded_pattern_count":2' "$request_directory/request-receipt.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/nested-linear-load-combination-term-delete-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"load_pattern_id":"COMBO_NESTED"' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[0,-6000,1500,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 0 \
      > "$e2e_root/nested-linear-load-combination-term-delete-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/nested-linear-load-combination-term-delete-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/nested-linear-load-combination-term-delete-$label-restart-diff.txt"
  done

  local suffix
  for suffix in '' -request -direct -partial -resumed; do
    diff -r "$e2e_root/nested-linear-load-combination-term-delete-first$suffix" \
      "$e2e_root/nested-linear-load-combination-term-delete-second$suffix" \
      > "$e2e_root/nested-linear-load-combination-term-delete$suffix-diff.txt"
  done
  cmp "$e2e_root/nested-linear-load-combination-term-delete-first.stdout.json" \
    "$e2e_root/nested-linear-load-combination-term-delete-second.stdout.json"
  for suffix in request direct partial resumed; do
    cmp "$e2e_root/nested-linear-load-combination-term-delete-first-$suffix.stdout.json" \
      "$e2e_root/nested-linear-load-combination-term-delete-second-$suffix.stdout.json"
  done
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed nested load-combination term deletion mutated its source ModelIR" >&2
    exit 1
  fi

  local missing_destination="$e2e_root/nested-linear-load-combination-term-delete-missing-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-delete-nested-linear-load-combination-term "$source_model" \
    --load-combination COMBO_NESTED --ref-kind load_pattern \
    --ref-id LC_MISSING --output-dir "$missing_destination" \
    > "$e2e_root/nested-linear-load-combination-term-delete-missing-rejected.stdout.json"; then
    echo "installed nested load-combination term deletion accepted a missing typed term" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_delete_nested_linear_load_combination_term_reference_missing' \
    "$e2e_root/nested-linear-load-combination-term-delete-missing-rejected.stdout.json"
  test ! -e "$missing_destination"

  local minimum_source="$e2e_root/nested-linear-load-combination-first/model-ir.json"
  local minimum_destination="$e2e_root/nested-linear-load-combination-term-delete-minimum-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-delete-nested-linear-load-combination-term "$minimum_source" \
    --load-combination COMBO_NESTED --ref-kind load_pattern \
    --ref-id LC_AXIAL --output-dir "$minimum_destination" \
    > "$e2e_root/nested-linear-load-combination-term-delete-minimum-rejected.stdout.json"; then
    echo "installed nested load-combination term deletion accepted a two-term source" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_delete_nested_linear_load_combination_term_count_invalid' \
    "$e2e_root/nested-linear-load-combination-term-delete-minimum-rejected.stdout.json"
  test ! -e "$minimum_destination"

  local degradation_destination="$e2e_root/nested-linear-load-combination-term-delete-degradation-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-delete-nested-linear-load-combination-term "$source_model" \
    --load-combination COMBO_NESTED --ref-kind load_combination \
    --ref-id COMBO_SERVICE --output-dir "$degradation_destination" \
    > "$e2e_root/nested-linear-load-combination-term-delete-degradation-rejected.stdout.json"; then
    echo "installed nested load-combination term deletion accepted direct degradation" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_delete_nested_linear_load_combination_term_direct_degradation' \
    "$e2e_root/nested-linear-load-combination-term-delete-degradation-rejected.stdout.json"
  test ! -e "$degradation_destination"
}
exercise_nested_linear_load_combination_term_delete_surface

exercise_nested_linear_load_combination_term_reorder_surface() {
  local source_model="$e2e_root/nested-linear-load-combination-term-delete-first/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"

  local label edit_directory request_directory direct_directory partial_directory
  local resumed_directory
  for label in first second; do
    edit_directory="$e2e_root/nested-linear-load-combination-term-reorder-$label"
    request_directory="$e2e_root/nested-linear-load-combination-term-reorder-$label-request"
    direct_directory="$e2e_root/nested-linear-load-combination-term-reorder-$label-direct"
    partial_directory="$e2e_root/nested-linear-load-combination-term-reorder-$label-partial"
    resumed_directory="$e2e_root/nested-linear-load-combination-term-reorder-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-reorder-nested-linear-load-combination-term "$source_model" \
      --load-combination COMBO_NESTED --ref-kind load_pattern \
      --ref-id LC_STRONG --to-index 0 --output-dir "$edit_directory" \
      > "$e2e_root/nested-linear-load-combination-term-reorder-$label.stdout.json"
    grep -Fq '"operation":"nested_linear_load_combination_term_reorder"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"editing_profile":"acyclic_nested_linear_static_depth_8_expanded_terms_64"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"reference_kind":"load_pattern"' "$edit_directory/edit-receipt.json"
    grep -Fq '"reference_id":"LC_STRONG"' "$edit_directory/edit-receipt.json"
    grep -Fq '"factor":0.1' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_term_index":1' "$edit_directory/edit-receipt.json"
    grep -Fq '"target_term_index":0' "$edit_directory/edit-receipt.json"
    grep -Fq '"term_count":2' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_combination_depth":2' "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_combination_depth":2' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_expanded_term_count":3' "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_expanded_term_count":3' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_expanded_pattern_count":2' "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_expanded_pattern_count":2' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_terms":[{"factor":0.5,"ref_id":"COMBO_SERVICE","ref_kind":"load_combination"},{"factor":0.1,"ref_id":"LC_STRONG","ref_kind":"load_pattern"}]' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_terms":[{"factor":0.1,"ref_id":"LC_STRONG","ref_kind":"load_pattern"},{"factor":0.5,"ref_id":"COMBO_SERVICE","ref_kind":"load_combination"}]' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"source_expanded_pattern_terms":[{"factor":0.6,"ref_id":"LC_WEAK","ref_kind":"load_pattern"},{"factor":-0.15,"ref_id":"LC_STRONG","ref_kind":"load_pattern"}]' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_expanded_pattern_terms":[{"factor":-0.15,"ref_id":"LC_STRONG","ref_kind":"load_pattern"},{"factor":0.6,"ref_id":"LC_WEAK","ref_kind":"load_pattern"}]' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-reorder-nested-linear-load-combination-term.v1"' \
      "$edit_directory/model-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$edit_directory/model-ir.json" \
      --case nested-linear-load-combination-term-reorder-c5 \
      --load-combination COMBO_NESTED \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/nested-linear-load-combination-term-reorder-$label-request.stdout.json"
    grep -Fq '"schema_version":"structural-native-model-linear-nested-combination-request-create-receipt.v3"' \
      "$request_directory/request-receipt.json"
    grep -Fq '"load_combination_id":"COMBO_NESTED"' \
      "$request_directory/request-receipt.json"
    grep -Fq '"combination_depth":2' "$request_directory/request-receipt.json"
    grep -Fq '"expanded_term_count":3' "$request_directory/request-receipt.json"
    grep -Fq '"expanded_pattern_count":2' "$request_directory/request-receipt.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/nested-linear-load-combination-term-reorder-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"load_pattern_id":"COMBO_NESTED"' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[0,-6000,1500,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 0 \
      > "$e2e_root/nested-linear-load-combination-term-reorder-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/nested-linear-load-combination-term-reorder-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/nested-linear-load-combination-term-reorder-$label-restart-diff.txt"
  done

  local suffix
  for suffix in '' -request -direct -partial -resumed; do
    diff -r "$e2e_root/nested-linear-load-combination-term-reorder-first$suffix" \
      "$e2e_root/nested-linear-load-combination-term-reorder-second$suffix" \
      > "$e2e_root/nested-linear-load-combination-term-reorder$suffix-diff.txt"
  done
  cmp "$e2e_root/nested-linear-load-combination-term-reorder-first.stdout.json" \
    "$e2e_root/nested-linear-load-combination-term-reorder-second.stdout.json"
  for suffix in request direct partial resumed; do
    cmp "$e2e_root/nested-linear-load-combination-term-reorder-first-$suffix.stdout.json" \
      "$e2e_root/nested-linear-load-combination-term-reorder-second-$suffix.stdout.json"
  done
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed nested load-combination term reorder mutated its source ModelIR" >&2
    exit 1
  fi

  local no_op_destination="$e2e_root/nested-linear-load-combination-term-reorder-no-op-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-reorder-nested-linear-load-combination-term "$source_model" \
    --load-combination COMBO_NESTED --ref-kind load_pattern \
    --ref-id LC_STRONG --to-index 1 --output-dir "$no_op_destination" \
    > "$e2e_root/nested-linear-load-combination-term-reorder-no-op-rejected.stdout.json"; then
    echo "installed nested load-combination term reorder accepted a no-op" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_edit_no_change' \
    "$e2e_root/nested-linear-load-combination-term-reorder-no-op-rejected.stdout.json"
  test ! -e "$no_op_destination"

  local range_destination="$e2e_root/nested-linear-load-combination-term-reorder-range-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-reorder-nested-linear-load-combination-term "$source_model" \
    --load-combination COMBO_NESTED --ref-kind load_pattern \
    --ref-id LC_STRONG --to-index 2 --output-dir "$range_destination" \
    > "$e2e_root/nested-linear-load-combination-term-reorder-range-rejected.stdout.json"; then
    echo "installed nested load-combination term reorder accepted an out-of-range target" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_reorder_nested_linear_load_combination_term_target_index_invalid' \
    "$e2e_root/nested-linear-load-combination-term-reorder-range-rejected.stdout.json"
  test ! -e "$range_destination"

  local missing_destination="$e2e_root/nested-linear-load-combination-term-reorder-missing-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-reorder-nested-linear-load-combination-term "$source_model" \
    --load-combination COMBO_NESTED --ref-kind load_combination \
    --ref-id LC_STRONG --to-index 0 --output-dir "$missing_destination" \
    > "$e2e_root/nested-linear-load-combination-term-reorder-missing-rejected.stdout.json"; then
    echo "installed nested load-combination term reorder accepted a missing typed reference" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_reorder_nested_linear_load_combination_term_reference_missing' \
    "$e2e_root/nested-linear-load-combination-term-reorder-missing-rejected.stdout.json"
  test ! -e "$missing_destination"
}
exercise_nested_linear_load_combination_term_reorder_surface

exercise_direct_linear_load_combination_term_reorder_surface() {
  local source_model="$e2e_root/direct-linear-load-combination-term-delete-first/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"

  local label edit_directory request_directory direct_directory partial_directory
  local resumed_directory
  for label in first second; do
    edit_directory="$e2e_root/direct-linear-load-combination-term-reorder-$label"
    request_directory="$e2e_root/direct-linear-load-combination-term-reorder-$label-request"
    direct_directory="$e2e_root/direct-linear-load-combination-term-reorder-$label-direct"
    partial_directory="$e2e_root/direct-linear-load-combination-term-reorder-$label-partial"
    resumed_directory="$e2e_root/direct-linear-load-combination-term-reorder-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-reorder-linear-load-combination-term "$source_model" \
      --load-combination COMBO_SERVICE --load-pattern LC_AXIAL \
      --to-index 0 --output-dir "$edit_directory" \
      > "$e2e_root/direct-linear-load-combination-term-reorder-$label.stdout.json"
    grep -Fq '"operation":"direct_linear_load_combination_term_reorder"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"editing_profile":"unique_direct_linear_static_patterns_2_to_64"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"load_combination_id":"COMBO_SERVICE"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"load_pattern_id":"LC_AXIAL"' "$edit_directory/edit-receipt.json"
    grep -Fq '"factor":0.25' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_term_index":1' "$edit_directory/edit-receipt.json"
    grep -Fq '"target_term_index":0' "$edit_directory/edit-receipt.json"
    grep -Fq '"term_count":2' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_terms":[{"factor":1.2,"ref_id":"LC_WEAK","ref_kind":"load_pattern"},{"factor":0.25,"ref_id":"LC_AXIAL","ref_kind":"load_pattern"}]' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_terms":[{"factor":0.25,"ref_id":"LC_AXIAL","ref_kind":"load_pattern"},{"factor":1.2,"ref_id":"LC_WEAK","ref_kind":"load_pattern"}]' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-reorder-direct-linear-load-combination-term.v1"' \
      "$edit_directory/model-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$edit_directory/model-ir.json" \
      --case direct-linear-load-combination-term-reorder-c5 \
      --load-combination COMBO_SERVICE \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/direct-linear-load-combination-term-reorder-$label-request.stdout.json"
    grep -Fq '"schema_version":"structural-native-model-linear-combination-request-create-receipt.v1"' \
      "$request_directory/request-receipt.json"
    grep -Fq '"load_combination_id":"COMBO_SERVICE"' \
      "$request_directory/request-receipt.json"
    grep -Fq '"combination_terms":[{"factor":0.25,"ref_id":"LC_AXIAL","ref_kind":"load_pattern"},{"factor":1.2,"ref_id":"LC_WEAK","ref_kind":"load_pattern"}]' \
      "$request_directory/request-receipt.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/direct-linear-load-combination-term-reorder-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"load_pattern_id":"COMBO_SERVICE"' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[25000,-12000,0,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 0 \
      > "$e2e_root/direct-linear-load-combination-term-reorder-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/direct-linear-load-combination-term-reorder-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/direct-linear-load-combination-term-reorder-$label-restart-diff.txt"
  done

  local suffix
  for suffix in '' -request -direct -partial -resumed; do
    diff -r "$e2e_root/direct-linear-load-combination-term-reorder-first$suffix" \
      "$e2e_root/direct-linear-load-combination-term-reorder-second$suffix" \
      > "$e2e_root/direct-linear-load-combination-term-reorder$suffix-diff.txt"
  done
  cmp "$e2e_root/direct-linear-load-combination-term-reorder-first.stdout.json" \
    "$e2e_root/direct-linear-load-combination-term-reorder-second.stdout.json"
  for suffix in request direct partial resumed; do
    cmp "$e2e_root/direct-linear-load-combination-term-reorder-first-$suffix.stdout.json" \
      "$e2e_root/direct-linear-load-combination-term-reorder-second-$suffix.stdout.json"
  done
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed direct load-combination term reorder mutated its source ModelIR" >&2
    exit 1
  fi

  local no_op_destination="$e2e_root/direct-linear-load-combination-term-reorder-no-op-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-reorder-linear-load-combination-term "$source_model" \
    --load-combination COMBO_SERVICE --load-pattern LC_AXIAL \
    --to-index 1 --output-dir "$no_op_destination" \
    > "$e2e_root/direct-linear-load-combination-term-reorder-no-op-rejected.stdout.json"; then
    echo "installed direct load-combination term reorder accepted a no-op" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_edit_no_change' \
    "$e2e_root/direct-linear-load-combination-term-reorder-no-op-rejected.stdout.json"
  test ! -e "$no_op_destination"

  local range_destination="$e2e_root/direct-linear-load-combination-term-reorder-range-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-reorder-linear-load-combination-term "$source_model" \
    --load-combination COMBO_SERVICE --load-pattern LC_AXIAL \
    --to-index 2 --output-dir "$range_destination" \
    > "$e2e_root/direct-linear-load-combination-term-reorder-range-rejected.stdout.json"; then
    echo "installed direct load-combination term reorder accepted an out-of-range target" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_reorder_direct_linear_load_combination_term_target_index_invalid' \
    "$e2e_root/direct-linear-load-combination-term-reorder-range-rejected.stdout.json"
  test ! -e "$range_destination"

  local missing_destination="$e2e_root/direct-linear-load-combination-term-reorder-missing-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-reorder-linear-load-combination-term "$source_model" \
    --load-combination COMBO_SERVICE --load-pattern LC_MISSING \
    --to-index 0 --output-dir "$missing_destination" \
    > "$e2e_root/direct-linear-load-combination-term-reorder-missing-rejected.stdout.json"; then
    echo "installed direct load-combination term reorder accepted a missing pattern" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_reorder_direct_linear_load_combination_term_pattern_missing' \
    "$e2e_root/direct-linear-load-combination-term-reorder-missing-rejected.stdout.json"
  test ! -e "$missing_destination"
}
exercise_direct_linear_load_combination_term_reorder_surface

exercise_direct_linear_load_combination_term_insert_surface() {
  local source_model="$e2e_root/linear-load-combination-add-first/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"

  local label edit_directory request_directory direct_directory partial_directory
  local resumed_directory
  for label in first second; do
    edit_directory="$e2e_root/direct-linear-load-combination-term-insert-$label"
    request_directory="$e2e_root/direct-linear-load-combination-term-insert-$label-request"
    direct_directory="$e2e_root/direct-linear-load-combination-term-insert-$label-direct"
    partial_directory="$e2e_root/direct-linear-load-combination-term-insert-$label-partial"
    resumed_directory="$e2e_root/direct-linear-load-combination-term-insert-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-insert-linear-load-combination-term "$source_model" \
      --load-combination COMBO_SERVICE --load-pattern LC_AXIAL --factor 0.25 \
      --at-index 1 --output-dir "$edit_directory" \
      > "$e2e_root/direct-linear-load-combination-term-insert-$label.stdout.json"
    grep -Fq '"operation":"direct_linear_load_combination_term_insert"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"editing_profile":"unique_direct_linear_static_patterns_3_to_64"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"load_combination_id":"COMBO_SERVICE"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"load_pattern_id":"LC_AXIAL"' "$edit_directory/edit-receipt.json"
    grep -Fq '"factor":0.25' "$edit_directory/edit-receipt.json"
    grep -Fq '"term_index":1' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_term_count":2' "$edit_directory/edit-receipt.json"
    grep -Fq '"term_count":3' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_terms":[{"factor":1.2,"ref_id":"LC_WEAK","ref_kind":"load_pattern"},{"factor":-0.5,"ref_id":"LC_STRONG","ref_kind":"load_pattern"}]' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_terms":[{"factor":1.2,"ref_id":"LC_WEAK","ref_kind":"load_pattern"},{"factor":0.25,"ref_id":"LC_AXIAL","ref_kind":"load_pattern"},{"factor":-0.5,"ref_id":"LC_STRONG","ref_kind":"load_pattern"}]' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-insert-direct-linear-load-combination-term.v1"' \
      "$edit_directory/model-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$edit_directory/model-ir.json" \
      --case direct-linear-load-combination-term-insert-c5 \
      --load-combination COMBO_SERVICE \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/direct-linear-load-combination-term-insert-$label-request.stdout.json"
    grep -Fq '"schema_version":"structural-native-model-linear-direct-combination-request-create-receipt.v2"' \
      "$request_directory/request-receipt.json"
    grep -Fq '"load_combination_id":"COMBO_SERVICE"' \
      "$request_directory/request-receipt.json"
    grep -Fq '"combination_terms":[{"factor":1.2,"ref_id":"LC_WEAK","ref_kind":"load_pattern"},{"factor":0.25,"ref_id":"LC_AXIAL","ref_kind":"load_pattern"},{"factor":-0.5,"ref_id":"LC_STRONG","ref_kind":"load_pattern"}]' \
      "$request_directory/request-receipt.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/direct-linear-load-combination-term-insert-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"load_pattern_id":"COMBO_SERVICE"' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[25000,-12000,5000,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 0 \
      > "$e2e_root/direct-linear-load-combination-term-insert-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/direct-linear-load-combination-term-insert-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/direct-linear-load-combination-term-insert-$label-restart-diff.txt"
  done

  local suffix
  for suffix in '' -request -direct -partial -resumed; do
    diff -r "$e2e_root/direct-linear-load-combination-term-insert-first$suffix" \
      "$e2e_root/direct-linear-load-combination-term-insert-second$suffix" \
      > "$e2e_root/direct-linear-load-combination-term-insert$suffix-diff.txt"
  done
  cmp "$e2e_root/direct-linear-load-combination-term-insert-first.stdout.json" \
    "$e2e_root/direct-linear-load-combination-term-insert-second.stdout.json"
  for suffix in request direct partial resumed; do
    cmp "$e2e_root/direct-linear-load-combination-term-insert-first-$suffix.stdout.json" \
      "$e2e_root/direct-linear-load-combination-term-insert-second-$suffix.stdout.json"
  done
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed direct load-combination term insert mutated its source ModelIR" >&2
    exit 1
  fi

  local duplicate_destination="$e2e_root/direct-linear-load-combination-term-insert-duplicate-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-insert-linear-load-combination-term "$source_model" \
    --load-combination COMBO_SERVICE --load-pattern LC_WEAK --factor 0.25 \
    --at-index 1 --output-dir "$duplicate_destination" \
    > "$e2e_root/direct-linear-load-combination-term-insert-duplicate-rejected.stdout.json"; then
    echo "installed direct load-combination term insert accepted a duplicate pattern" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_insert_direct_linear_load_combination_term_pattern_duplicate' \
    "$e2e_root/direct-linear-load-combination-term-insert-duplicate-rejected.stdout.json"
  test ! -e "$duplicate_destination"

  local range_destination="$e2e_root/direct-linear-load-combination-term-insert-range-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-insert-linear-load-combination-term "$source_model" \
    --load-combination COMBO_SERVICE --load-pattern LC_AXIAL --factor 0.25 \
    --at-index 3 --output-dir "$range_destination" \
    > "$e2e_root/direct-linear-load-combination-term-insert-range-rejected.stdout.json"; then
    echo "installed direct load-combination term insert accepted an out-of-range target" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_insert_direct_linear_load_combination_term_target_index_invalid' \
    "$e2e_root/direct-linear-load-combination-term-insert-range-rejected.stdout.json"
  test ! -e "$range_destination"

  local missing_destination="$e2e_root/direct-linear-load-combination-term-insert-missing-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-insert-linear-load-combination-term "$source_model" \
    --load-combination COMBO_SERVICE --load-pattern LC_MISSING --factor 0.25 \
    --at-index 1 --output-dir "$missing_destination" \
    > "$e2e_root/direct-linear-load-combination-term-insert-missing-rejected.stdout.json"; then
    echo "installed direct load-combination term insert accepted a missing pattern" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_insert_direct_linear_load_combination_term_pattern_missing' \
    "$e2e_root/direct-linear-load-combination-term-insert-missing-rejected.stdout.json"
  test ! -e "$missing_destination"
}
exercise_direct_linear_load_combination_term_insert_surface

exercise_nested_linear_load_combination_reference_edit_surface() {
  local base_model="$e2e_root/linear-load-combination-add-first/model-ir.json"
  local alternate_directory="$e2e_root/nested-linear-load-combination-reference-edit-alternate-source"
  local source_directory="$e2e_root/nested-linear-load-combination-reference-edit-source"
  local base_before_hash
  base_before_hash="$(sha256sum "$base_model" | awk '{print $1}')"

  env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-add-linear-load-combination "$base_model" \
    --load-combination COMBO_ALTERNATE \
    --term LC_WEAK 0.8 --term LC_STRONG 0.2 \
    --output-dir "$alternate_directory" \
    > "$e2e_root/nested-linear-load-combination-reference-edit-alternate-source.stdout.json"
  env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-add-nested-linear-load-combination "$alternate_directory/model-ir.json" \
    --load-combination COMBO_NESTED \
    --combination-term COMBO_SERVICE 0.5 --pattern-term LC_AXIAL 0.25 \
    --output-dir "$source_directory" \
    > "$e2e_root/nested-linear-load-combination-reference-edit-source.stdout.json"
  if [[ "$(sha256sum "$base_model" | awk '{print $1}')" != "$base_before_hash" ]]; then
    echo "installed nested load-combination reference-edit setup mutated its base ModelIR" >&2
    exit 1
  fi

  local source_model="$source_directory/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"
  local label edit_directory request_directory direct_directory partial_directory
  local resumed_directory
  for label in first second; do
    edit_directory="$e2e_root/nested-linear-load-combination-reference-edit-$label"
    request_directory="$e2e_root/nested-linear-load-combination-reference-edit-$label-request"
    direct_directory="$e2e_root/nested-linear-load-combination-reference-edit-$label-direct"
    partial_directory="$e2e_root/nested-linear-load-combination-reference-edit-$label-partial"
    resumed_directory="$e2e_root/nested-linear-load-combination-reference-edit-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-edit-nested-linear-load-combination-reference "$source_model" \
      --load-combination COMBO_NESTED --ref-kind load_pattern --ref-id LC_AXIAL \
      --replacement-ref-kind load_combination --replacement-ref-id COMBO_ALTERNATE \
      --output-dir "$edit_directory" \
      > "$e2e_root/nested-linear-load-combination-reference-edit-$label.stdout.json"
    grep -Fq '"operation":"nested_linear_load_combination_reference_edit"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"editing_profile":"acyclic_nested_linear_static_depth_8_expanded_terms_64"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"reference_kind":"load_pattern"' "$edit_directory/edit-receipt.json"
    grep -Fq '"reference_id":"LC_AXIAL"' "$edit_directory/edit-receipt.json"
    grep -Fq '"replacement_reference_kind":"load_combination"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"replacement_reference_id":"COMBO_ALTERNATE"' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"preserved_factor":0.25' "$edit_directory/edit-receipt.json"
    grep -Fq '"term_index":1' "$edit_directory/edit-receipt.json"
    grep -Fq '"term_count":2' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_combination_depth":2' "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_combination_depth":2' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_expanded_term_count":3' "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_expanded_term_count":4' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_expanded_pattern_count":3' "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_expanded_pattern_count":2' "$edit_directory/edit-receipt.json"
    grep -Fq '"source_terms":[{"factor":0.5,"ref_id":"COMBO_SERVICE","ref_kind":"load_combination"},{"factor":0.25,"ref_id":"LC_AXIAL","ref_kind":"load_pattern"}]' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_terms":[{"factor":0.5,"ref_id":"COMBO_SERVICE","ref_kind":"load_combination"},{"factor":0.25,"ref_id":"COMBO_ALTERNATE","ref_kind":"load_combination"}]' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"edited_expanded_pattern_terms":[{"factor":0.8,"ref_id":"LC_WEAK","ref_kind":"load_pattern"},{"factor":-0.2,"ref_id":"LC_STRONG","ref_kind":"load_pattern"}]' \
      "$edit_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-edit-nested-linear-load-combination-reference.v1"' \
      "$edit_directory/model-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$edit_directory/model-ir.json" \
      --case nested-linear-load-combination-reference-edit-c5 \
      --load-combination COMBO_NESTED \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/nested-linear-load-combination-reference-edit-$label-request.stdout.json"
    grep -Fq '"schema_version":"structural-native-model-linear-nested-combination-request-create-receipt.v3"' \
      "$request_directory/request-receipt.json"
    grep -Fq '"combination_depth":2' "$request_directory/request-receipt.json"
    grep -Fq '"expanded_term_count":4' "$request_directory/request-receipt.json"
    grep -Fq '"expanded_pattern_count":2' "$request_directory/request-receipt.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/nested-linear-load-combination-reference-edit-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"load_pattern_id":"COMBO_NESTED"' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[0,-8000,2000,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 0 \
      > "$e2e_root/nested-linear-load-combination-reference-edit-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$edit_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/nested-linear-load-combination-reference-edit-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/nested-linear-load-combination-reference-edit-$label-restart-diff.txt"
  done

  local suffix
  for suffix in '' -request -direct -partial -resumed; do
    diff -r "$e2e_root/nested-linear-load-combination-reference-edit-first$suffix" \
      "$e2e_root/nested-linear-load-combination-reference-edit-second$suffix" \
      > "$e2e_root/nested-linear-load-combination-reference-edit$suffix-diff.txt"
  done
  cmp "$e2e_root/nested-linear-load-combination-reference-edit-first.stdout.json" \
    "$e2e_root/nested-linear-load-combination-reference-edit-second.stdout.json"
  for suffix in request direct partial resumed; do
    cmp "$e2e_root/nested-linear-load-combination-reference-edit-first-$suffix.stdout.json" \
      "$e2e_root/nested-linear-load-combination-reference-edit-second-$suffix.stdout.json"
  done
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed nested load-combination reference edit mutated its source ModelIR" >&2
    exit 1
  fi

  local replacement_kind replacement_id expected_code destination
  for label in no-change duplicate missing cycle; do
    case "$label" in
      no-change)
        replacement_kind="load_pattern"
        replacement_id="LC_AXIAL"
        expected_code="workbench_model_edit_no_change"
        ;;
      duplicate)
        replacement_kind="load_combination"
        replacement_id="COMBO_SERVICE"
        expected_code="workbench_model_edit_nested_linear_load_combination_replacement_reference_duplicate"
        ;;
      missing)
        replacement_kind="load_combination"
        replacement_id="COMBO_MISSING"
        expected_code="workbench_model_edit_nested_linear_load_combination_replacement_combination_missing"
        ;;
      cycle)
        replacement_kind="load_combination"
        replacement_id="COMBO_NESTED"
        expected_code="workbench_model_linear_nested_combination_cycle"
        ;;
    esac
    destination="$e2e_root/nested-linear-load-combination-reference-edit-$label-rejected"
    if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-edit-nested-linear-load-combination-reference "$source_model" \
      --load-combination COMBO_NESTED --ref-kind load_pattern --ref-id LC_AXIAL \
      --replacement-ref-kind "$replacement_kind" --replacement-ref-id "$replacement_id" \
      --output-dir "$destination" \
      > "$e2e_root/nested-linear-load-combination-reference-edit-$label-rejected.stdout.json"; then
      echo "installed nested load-combination reference editor accepted $label input" >&2
      exit 1
    fi
    grep -Fq "$expected_code" \
      "$e2e_root/nested-linear-load-combination-reference-edit-$label-rejected.stdout.json"
    test ! -e "$destination"
  done

  destination="$e2e_root/nested-linear-load-combination-reference-edit-direct-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-edit-nested-linear-load-combination-reference "$source_model" \
    --load-combination COMBO_NESTED --ref-kind load_combination --ref-id COMBO_SERVICE \
    --replacement-ref-kind load_pattern --replacement-ref-id LC_WEAK \
    --output-dir "$destination" \
    > "$e2e_root/nested-linear-load-combination-reference-edit-direct-rejected.stdout.json"; then
    echo "installed nested load-combination reference editor accepted direct degradation" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_edit_nested_linear_load_combination_direct_unsupported' \
    "$e2e_root/nested-linear-load-combination-reference-edit-direct-rejected.stdout.json"
  test ! -e "$destination"
}
exercise_nested_linear_load_combination_reference_edit_surface

exercise_nested_linear_load_combination_delete_surface() {
  local source_model="$e2e_root/nested-linear-load-combination-first/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"

  local label delete_directory request_directory direct_directory partial_directory
  local resumed_directory
  for label in first second; do
    delete_directory="$e2e_root/nested-linear-load-combination-delete-$label"
    request_directory="$e2e_root/nested-linear-load-combination-delete-$label-request"
    direct_directory="$e2e_root/nested-linear-load-combination-delete-$label-direct"
    partial_directory="$e2e_root/nested-linear-load-combination-delete-$label-partial"
    resumed_directory="$e2e_root/nested-linear-load-combination-delete-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-delete-linear-load-combination "$source_model" \
      --load-combination COMBO_NESTED --output-dir "$delete_directory" \
      > "$e2e_root/nested-linear-load-combination-delete-$label.stdout.json"
    grep -Fq '"operation":"nested_linear_load_combination_delete"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"deletion_profile":"acyclic_nested_linear_static_depth_8_expanded_terms_64"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"term_count":2' "$delete_directory/edit-receipt.json"
    grep -Fq '"combination_depth":2' "$delete_directory/edit-receipt.json"
    grep -Fq '"expanded_term_count":3' "$delete_directory/edit-receipt.json"
    grep -Fq '"expanded_pattern_count":3' "$delete_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-delete-nested-linear-load-combination.v3"' \
      "$delete_directory/model-ir.json"
    grep -Fq '"load_combinations":[{"combination_type":"linear","extensions":{},"id":"COMBO_SERVICE"' \
      "$delete_directory/model-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$delete_directory/model-ir.json" \
      --case nested-linear-load-combination-delete-c5 --load-combination COMBO_SERVICE \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/nested-linear-load-combination-delete-$label-request.stdout.json"
    grep -Fq '"schema_version":"structural-native-model-linear-combination-request-create-receipt.v1"' \
      "$request_directory/request-receipt.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/nested-linear-load-combination-delete-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"load_pattern_id":"COMBO_SERVICE"' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[0,-12000,5000,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 0 \
      > "$e2e_root/nested-linear-load-combination-delete-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/nested-linear-load-combination-delete-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/nested-linear-load-combination-delete-$label-restart-diff.txt"
  done

  local suffix
  for suffix in '' -request -direct -partial -resumed; do
    diff -r "$e2e_root/nested-linear-load-combination-delete-first$suffix" \
      "$e2e_root/nested-linear-load-combination-delete-second$suffix" \
      > "$e2e_root/nested-linear-load-combination-delete$suffix-diff.txt"
  done
  cmp "$e2e_root/nested-linear-load-combination-delete-first.stdout.json" \
    "$e2e_root/nested-linear-load-combination-delete-second.stdout.json"
  for suffix in request direct partial resumed; do
    cmp "$e2e_root/nested-linear-load-combination-delete-first-$suffix.stdout.json" \
      "$e2e_root/nested-linear-load-combination-delete-second-$suffix.stdout.json"
  done
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed nested linear load-combination deletion mutated its source ModelIR" >&2
    exit 1
  fi
}
exercise_nested_linear_load_combination_delete_surface

exercise_direct_linear_load_combination_delete_surface() {
  local source_model="$e2e_root/direct-linear-load-combination-first/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"

  local label delete_directory request_directory direct_directory partial_directory
  local resumed_directory
  for label in first second; do
    delete_directory="$e2e_root/direct-linear-load-combination-delete-$label"
    request_directory="$e2e_root/direct-linear-load-combination-delete-$label-request"
    direct_directory="$e2e_root/direct-linear-load-combination-delete-$label-direct"
    partial_directory="$e2e_root/direct-linear-load-combination-delete-$label-partial"
    resumed_directory="$e2e_root/direct-linear-load-combination-delete-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-delete-linear-load-combination "$source_model" \
      --load-combination COMBO_DIRECT --output-dir "$delete_directory" \
      > "$e2e_root/direct-linear-load-combination-delete-$label.stdout.json"
    grep -Fq '"operation":"direct_linear_load_combination_delete"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"deletion_profile":"unique_direct_linear_static_patterns_2_to_64"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"term_count":3' "$delete_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-delete-direct-linear-load-combination.v2"' \
      "$delete_directory/model-ir.json"
    grep -Fq '"load_combinations":[]' "$delete_directory/model-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$delete_directory/model-ir.json" \
      --case direct-linear-load-combination-delete-c5 --load-pattern LC_WEAK \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/direct-linear-load-combination-delete-$label-request.stdout.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/direct-linear-load-combination-delete-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"load_pattern_id":"LC_WEAK"' "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[0,-10000,0,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 0 \
      > "$e2e_root/direct-linear-load-combination-delete-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/direct-linear-load-combination-delete-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/direct-linear-load-combination-delete-$label-restart-diff.txt"
  done

  local suffix
  for suffix in '' -request -direct -partial -resumed; do
    diff -r "$e2e_root/direct-linear-load-combination-delete-first$suffix" \
      "$e2e_root/direct-linear-load-combination-delete-second$suffix" \
      > "$e2e_root/direct-linear-load-combination-delete$suffix-diff.txt"
  done
  cmp "$e2e_root/direct-linear-load-combination-delete-first.stdout.json" \
    "$e2e_root/direct-linear-load-combination-delete-second.stdout.json"
  for suffix in request direct partial resumed; do
    cmp "$e2e_root/direct-linear-load-combination-delete-first-$suffix.stdout.json" \
      "$e2e_root/direct-linear-load-combination-delete-second-$suffix.stdout.json"
  done
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed direct linear load-combination deletion mutated its source ModelIR" >&2
    exit 1
  fi
}
exercise_direct_linear_load_combination_delete_surface

exercise_linear_load_combination_delete_surface() {
  local source_model="$e2e_root/linear-load-combination-add-first/model-ir.json"
  local source_before_hash
  source_before_hash="$(sha256sum "$source_model" | awk '{print $1}')"

  local label delete_directory request_directory direct_directory partial_directory
  local resumed_directory
  for label in first second; do
    delete_directory="$e2e_root/linear-load-combination-delete-$label"
    request_directory="$e2e_root/linear-load-combination-delete-$label-request"
    direct_directory="$e2e_root/linear-load-combination-delete-$label-direct"
    partial_directory="$e2e_root/linear-load-combination-delete-$label-partial"
    resumed_directory="$e2e_root/linear-load-combination-delete-$label-resumed"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-delete-linear-load-combination "$source_model" \
      --load-combination COMBO_SERVICE --output-dir "$delete_directory" \
      > "$e2e_root/linear-load-combination-delete-$label.stdout.json"
    grep -Fq '"operation":"linear_load_combination_delete"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_load_combination_id":"COMBO_SERVICE"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_load_combination_index":0' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_combination_type":"linear"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"removed_terms":[{"factor":1.2,"ref_id":"LC_WEAK","ref_kind":"load_pattern"},{"factor":-0.5,"ref_id":"LC_STRONG","ref_kind":"load_pattern"}]' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"cpp_semantic_snapshot_verified":true' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"analysis_ready":true' "$delete_directory/edit-receipt.json"
    grep -Eq '"receipt_hash":"sha256:[0-9a-f]{64}"' \
      "$delete_directory/edit-receipt.json"
    grep -Fq '"structural-native:model-add-linear-load-combination.v1"' \
      "$delete_directory/model-ir.json"
    grep -Fq '"structural-native:model-delete-linear-load-combination.v1"' \
      "$delete_directory/model-ir.json"
    grep -Fq '"load_combinations":[]' "$delete_directory/model-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" model validate \
      "$delete_directory/model-ir.json" --require-analysis-ready \
      > "$e2e_root/linear-load-combination-delete-$label-validation.json"
    grep -Fq '"load_patterns":4,"load_combinations":0' \
      "$e2e_root/linear-load-combination-delete-$label-validation.json"
    env -i PATH="$empty_path" "$active/bin/structural-workbench" model-view \
      "$delete_directory/model-ir.json" \
      > "$e2e_root/linear-load-combination-delete-$label-view.txt"
    grep -Fq 'C++ semantic snapshot: verified' \
      "$e2e_root/linear-load-combination-delete-$label-view.txt"

    env -i PATH="$empty_path" "$active/bin/structural-workbench" \
      model-create-linear-analysis-request "$delete_directory/model-ir.json" \
      --case linear-load-combination-delete-c5 --load-pattern LC_WEAK \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir "$request_directory" \
      > "$e2e_root/linear-load-combination-delete-$label-request.stdout.json"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$direct_directory" \
      > "$e2e_root/linear-load-combination-delete-$label-direct.stdout.json"
    grep -Fq '"status":"completed"' "$direct_directory/run-receipt.json"
    grep -Fq '"active_dof_indices":[6,7,8,9,10,11]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"active_external_load":[0,-10000,0,0,0,0]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"recovery_element_types":[1]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"recovery_offsets":[0,12]' \
      "$direct_directory/result-recovery-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-ir.json"
    grep -Fq '"fallback_count":0' "$direct_directory/result-recovery-ir.json"

    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-run "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" --output-dir "$partial_directory" \
      --iteration-budget 0 \
      > "$e2e_root/linear-load-combination-delete-$label-partial.stdout.json"
    grep -Fq '"status":"active"' "$partial_directory/run-receipt.json"
    test -s "$partial_directory/checkpoint.mlpcp"
    env -i PATH="$empty_path" "$active/bin/structural-cli" analysis \
      model-linear-resume "$delete_directory/model-ir.json" \
      "$request_directory/analysis-request.json" "$partial_directory/checkpoint.mlpcp" \
      --output-dir "$resumed_directory" \
      > "$e2e_root/linear-load-combination-delete-$label-resumed.stdout.json"
    diff -r "$direct_directory" "$resumed_directory" \
      > "$e2e_root/linear-load-combination-delete-$label-restart-diff.txt"
  done

  local suffix diff_label
  for suffix in '' -request -direct -partial -resumed; do
    diff_label="${suffix#-}"
    if [[ -z "$diff_label" ]]; then
      diff_label=model
    fi
    diff -r "$e2e_root/linear-load-combination-delete-first$suffix" \
      "$e2e_root/linear-load-combination-delete-second$suffix" \
      > "$e2e_root/linear-load-combination-delete-$diff_label-diff.txt"
    cmp "$e2e_root/linear-load-combination-delete-first$suffix.stdout.json" \
      "$e2e_root/linear-load-combination-delete-second$suffix.stdout.json"
  done
  cmp "$e2e_root/linear-load-combination-delete-first-validation.json" \
    "$e2e_root/linear-load-combination-delete-second-validation.json"
  cmp "$e2e_root/linear-load-combination-delete-first-view.txt" \
    "$e2e_root/linear-load-combination-delete-second-view.txt"
  if [[ "$(sha256sum "$source_model" | awk '{print $1}')" != "$source_before_hash" ]]; then
    echo "installed linear load-combination deletion mutated its source ModelIR" >&2
    exit 1
  fi

  local nonterminal_destination="$e2e_root/linear-load-combination-delete-nonterminal-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-delete-linear-load-combination \
    "$e2e_root/linear-load-combination-add-next-index/model-ir.json" \
    --load-combination COMBO_SERVICE --output-dir "$nonterminal_destination" \
    > "$e2e_root/linear-load-combination-delete-nonterminal-rejected.stdout.json"; then
    echo "installed linear load-combination deletion accepted a nonterminal row" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_delete_linear_load_combination_not_terminal' \
    "$e2e_root/linear-load-combination-delete-nonterminal-rejected.stdout.json"
  test ! -e "$nonterminal_destination"

  local missing_destination="$e2e_root/linear-load-combination-delete-missing-rejected"
  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-delete-linear-load-combination "$linear_model" \
    --load-combination COMBO_SERVICE --output-dir "$missing_destination" \
    > "$e2e_root/linear-load-combination-delete-missing-rejected.stdout.json"; then
    echo "installed linear load-combination deletion accepted a missing row" >&2
    exit 1
  fi
  grep -Fq 'workbench_model_delete_linear_load_combination_missing' \
    "$e2e_root/linear-load-combination-delete-missing-rejected.stdout.json"
  test ! -e "$missing_destination"

  if env -i PATH="$empty_path" "$active/bin/structural-workbench" \
    model-delete-linear-load-combination "$source_model" \
    --load-combination COMBO_SERVICE \
    --output-dir "$e2e_root/linear-load-combination-delete-first" \
    > "$e2e_root/linear-load-combination-delete-existing-rejected.stdout.json"; then
    echo "installed linear load-combination deletion overwrote an existing destination" >&2
    exit 1
  fi
  grep -Fq 'workbench_stage_destination_exists' \
    "$e2e_root/linear-load-combination-delete-existing-rejected.stdout.json"
}
exercise_linear_load_combination_delete_surface

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
model_linear_request_create_request_hash="$(sha256sum "$e2e_root/model-linear-request-create-first/analysis-request.json" | awk '{print $1}')"
model_linear_request_create_receipt_hash="$(sha256sum "$e2e_root/model-linear-request-create-first/request-receipt.json" | awk '{print $1}')"
frame3d_member_add_model_hash="$(sha256sum "$e2e_root/frame3d-member-add-first/model-ir.json" | awk '{print $1}')"
frame3d_member_add_receipt_hash="$(sha256sum "$e2e_root/frame3d-member-add-first/edit-receipt.json" | awk '{print $1}')"
frame3d_member_add_request_hash="$(sha256sum "$e2e_root/frame3d-member-add-first-linear-request/analysis-request.json" | awk '{print $1}')"
frame3d_member_add_result_ir_hash="$(sha256sum "$e2e_root/frame3d-member-add-first-linear-run/result-ir.json" | awk '{print $1}')"
nodal_load_target_edit_model_hash="$(sha256sum "$e2e_root/nodal-load-target-edit-first/model-ir.json" | awk '{print $1}')"
nodal_load_target_edit_receipt_hash="$(sha256sum "$e2e_root/nodal-load-target-edit-first/edit-receipt.json" | awk '{print $1}')"
nodal_load_target_edit_request_receipt_hash="$(sha256sum "$e2e_root/nodal-load-target-edit-first-request/request-receipt.json" | awk '{print $1}')"
nodal_load_target_edit_request_hash="$(sha256sum "$e2e_root/nodal-load-target-edit-first-request/analysis-request.json" | awk '{print $1}')"
nodal_load_target_edit_assembly_receipt_hash="$(sha256sum "$e2e_root/nodal-load-target-edit-first-direct/assembly-receipt.json" | awk '{print $1}')"
nodal_load_target_edit_checkpoint_hash="$(sha256sum "$e2e_root/nodal-load-target-edit-first-direct/checkpoint.mlpcp" | awk '{print $1}')"
nodal_load_target_edit_result_ir_hash="$(sha256sum "$e2e_root/nodal-load-target-edit-first-direct/result-ir.json" | awk '{print $1}')"
nodal_load_target_edit_recovery_hash="$(sha256sum "$e2e_root/nodal-load-target-edit-first-direct/result-recovery-ir.json" | awk '{print $1}')"
nodal_load_target_edit_report_ir_hash="$(sha256sum "$e2e_root/nodal-load-target-edit-first-direct/report-ir.json" | awk '{print $1}')"
constraint_target_edit_model_hash="$(sha256sum "$e2e_root/constraint-target-edit-first/model-ir.json" | awk '{print $1}')"
constraint_target_edit_receipt_hash="$(sha256sum "$e2e_root/constraint-target-edit-first/edit-receipt.json" | awk '{print $1}')"
constraint_target_edit_request_receipt_hash="$(sha256sum "$e2e_root/constraint-target-edit-first-request/request-receipt.json" | awk '{print $1}')"
constraint_target_edit_request_hash="$(sha256sum "$e2e_root/constraint-target-edit-first-request/analysis-request.json" | awk '{print $1}')"
constraint_target_edit_assembly_receipt_hash="$(sha256sum "$e2e_root/constraint-target-edit-first-direct/assembly-receipt.json" | awk '{print $1}')"
constraint_target_edit_checkpoint_hash="$(sha256sum "$e2e_root/constraint-target-edit-first-direct/checkpoint.mlpcp" | awk '{print $1}')"
constraint_target_edit_result_ir_hash="$(sha256sum "$e2e_root/constraint-target-edit-first-direct/result-ir.json" | awk '{print $1}')"
constraint_target_edit_recovery_hash="$(sha256sum "$e2e_root/constraint-target-edit-first-direct/result-recovery-ir.json" | awk '{print $1}')"
constraint_target_edit_report_ir_hash="$(sha256sum "$e2e_root/constraint-target-edit-first-direct/report-ir.json" | awk '{print $1}')"
fixed_constraint_dof_delete_model_hash="$(sha256sum "$e2e_root/fixed-constraint-dof-delete-first/model-ir.json" | awk '{print $1}')"
fixed_constraint_dof_delete_receipt_hash="$(sha256sum "$e2e_root/fixed-constraint-dof-delete-first/edit-receipt.json" | awk '{print $1}')"
fixed_constraint_dof_delete_request_receipt_hash="$(sha256sum "$e2e_root/fixed-constraint-dof-delete-first-request/request-receipt.json" | awk '{print $1}')"
fixed_constraint_dof_delete_request_hash="$(sha256sum "$e2e_root/fixed-constraint-dof-delete-first-request/analysis-request.json" | awk '{print $1}')"
fixed_constraint_dof_delete_assembly_receipt_hash="$(sha256sum "$e2e_root/fixed-constraint-dof-delete-first-direct/assembly-receipt.json" | awk '{print $1}')"
fixed_constraint_dof_delete_checkpoint_hash="$(sha256sum "$e2e_root/fixed-constraint-dof-delete-first-direct/checkpoint.mlpcp" | awk '{print $1}')"
fixed_constraint_dof_delete_result_ir_hash="$(sha256sum "$e2e_root/fixed-constraint-dof-delete-first-direct/result-ir.json" | awk '{print $1}')"
fixed_constraint_dof_delete_recovery_hash="$(sha256sum "$e2e_root/fixed-constraint-dof-delete-first-direct/result-recovery-ir.json" | awk '{print $1}')"
fixed_constraint_dof_delete_report_ir_hash="$(sha256sum "$e2e_root/fixed-constraint-dof-delete-first-direct/report-ir.json" | awk '{print $1}')"
fixed_constraint_dof_add_model_hash="$(sha256sum "$e2e_root/fixed-constraint-dof-add-first/model-ir.json" | awk '{print $1}')"
fixed_constraint_dof_add_receipt_hash="$(sha256sum "$e2e_root/fixed-constraint-dof-add-first/edit-receipt.json" | awk '{print $1}')"
fixed_constraint_dof_add_request_receipt_hash="$(sha256sum "$e2e_root/fixed-constraint-dof-add-first-request/request-receipt.json" | awk '{print $1}')"
fixed_constraint_dof_add_request_hash="$(sha256sum "$e2e_root/fixed-constraint-dof-add-first-request/analysis-request.json" | awk '{print $1}')"
fixed_constraint_dof_add_assembly_receipt_hash="$(sha256sum "$e2e_root/fixed-constraint-dof-add-first-direct/assembly-receipt.json" | awk '{print $1}')"
fixed_constraint_dof_add_checkpoint_hash="$(sha256sum "$e2e_root/fixed-constraint-dof-add-first-direct/checkpoint.mlpcp" | awk '{print $1}')"
fixed_constraint_dof_add_result_ir_hash="$(sha256sum "$e2e_root/fixed-constraint-dof-add-first-direct/result-ir.json" | awk '{print $1}')"
fixed_constraint_dof_add_recovery_hash="$(sha256sum "$e2e_root/fixed-constraint-dof-add-first-direct/result-recovery-ir.json" | awk '{print $1}')"
fixed_constraint_dof_add_report_ir_hash="$(sha256sum "$e2e_root/fixed-constraint-dof-add-first-direct/report-ir.json" | awk '{print $1}')"
fixed_constraint_dof_reorder_model_hash="$(sha256sum "$e2e_root/fixed-constraint-dof-reorder-first/model-ir.json" | awk '{print $1}')"
fixed_constraint_dof_reorder_receipt_hash="$(sha256sum "$e2e_root/fixed-constraint-dof-reorder-first/edit-receipt.json" | awk '{print $1}')"
fixed_constraint_dof_reorder_request_receipt_hash="$(sha256sum "$e2e_root/fixed-constraint-dof-reorder-first-request/request-receipt.json" | awk '{print $1}')"
fixed_constraint_dof_reorder_request_hash="$(sha256sum "$e2e_root/fixed-constraint-dof-reorder-first-request/analysis-request.json" | awk '{print $1}')"
fixed_constraint_dof_reorder_assembly_receipt_hash="$(sha256sum "$e2e_root/fixed-constraint-dof-reorder-first-direct/assembly-receipt.json" | awk '{print $1}')"
fixed_constraint_dof_reorder_checkpoint_hash="$(sha256sum "$e2e_root/fixed-constraint-dof-reorder-first-direct/checkpoint.mlpcp" | awk '{print $1}')"
fixed_constraint_dof_reorder_result_ir_hash="$(sha256sum "$e2e_root/fixed-constraint-dof-reorder-first-direct/result-ir.json" | awk '{print $1}')"
fixed_constraint_dof_reorder_recovery_hash="$(sha256sum "$e2e_root/fixed-constraint-dof-reorder-first-direct/result-recovery-ir.json" | awk '{print $1}')"
fixed_constraint_dof_reorder_report_ir_hash="$(sha256sum "$e2e_root/fixed-constraint-dof-reorder-first-direct/report-ir.json" | awk '{print $1}')"
fixed_constraint_identity_edit_model_hash="$(sha256sum "$e2e_root/fixed-constraint-identity-edit-first/model-ir.json" | awk '{print $1}')"
fixed_constraint_identity_edit_receipt_hash="$(sha256sum "$e2e_root/fixed-constraint-identity-edit-first/edit-receipt.json" | awk '{print $1}')"
fixed_constraint_identity_edit_request_receipt_hash="$(sha256sum "$e2e_root/fixed-constraint-identity-edit-first-request/request-receipt.json" | awk '{print $1}')"
fixed_constraint_identity_edit_request_hash="$(sha256sum "$e2e_root/fixed-constraint-identity-edit-first-request/analysis-request.json" | awk '{print $1}')"
fixed_constraint_identity_edit_assembly_receipt_hash="$(sha256sum "$e2e_root/fixed-constraint-identity-edit-first-direct/assembly-receipt.json" | awk '{print $1}')"
fixed_constraint_identity_edit_checkpoint_hash="$(sha256sum "$e2e_root/fixed-constraint-identity-edit-first-direct/checkpoint.mlpcp" | awk '{print $1}')"
fixed_constraint_identity_edit_result_ir_hash="$(sha256sum "$e2e_root/fixed-constraint-identity-edit-first-direct/result-ir.json" | awk '{print $1}')"
fixed_constraint_identity_edit_recovery_hash="$(sha256sum "$e2e_root/fixed-constraint-identity-edit-first-direct/result-recovery-ir.json" | awk '{print $1}')"
fixed_constraint_identity_edit_report_ir_hash="$(sha256sum "$e2e_root/fixed-constraint-identity-edit-first-direct/report-ir.json" | awk '{print $1}')"
nodal_load_identity_edit_model_hash="$(sha256sum "$e2e_root/nodal-load-identity-edit-first/model-ir.json" | awk '{print $1}')"
nodal_load_identity_edit_receipt_hash="$(sha256sum "$e2e_root/nodal-load-identity-edit-first/edit-receipt.json" | awk '{print $1}')"
nodal_load_identity_edit_request_receipt_hash="$(sha256sum "$e2e_root/nodal-load-identity-edit-first-request/request-receipt.json" | awk '{print $1}')"
nodal_load_identity_edit_request_hash="$(sha256sum "$e2e_root/nodal-load-identity-edit-first-request/analysis-request.json" | awk '{print $1}')"
nodal_load_identity_edit_assembly_receipt_hash="$(sha256sum "$e2e_root/nodal-load-identity-edit-first-direct/assembly-receipt.json" | awk '{print $1}')"
nodal_load_identity_edit_checkpoint_hash="$(sha256sum "$e2e_root/nodal-load-identity-edit-first-direct/checkpoint.mlpcp" | awk '{print $1}')"
nodal_load_identity_edit_result_ir_hash="$(sha256sum "$e2e_root/nodal-load-identity-edit-first-direct/result-ir.json" | awk '{print $1}')"
nodal_load_identity_edit_recovery_hash="$(sha256sum "$e2e_root/nodal-load-identity-edit-first-direct/result-recovery-ir.json" | awk '{print $1}')"
nodal_load_identity_edit_report_ir_hash="$(sha256sum "$e2e_root/nodal-load-identity-edit-first-direct/report-ir.json" | awk '{print $1}')"
linear_load_pattern_identity_edit_model_hash="$(sha256sum "$e2e_root/linear-load-pattern-identity-edit-first/model-ir.json" | awk '{print $1}')"
linear_load_pattern_identity_edit_receipt_hash="$(sha256sum "$e2e_root/linear-load-pattern-identity-edit-first/edit-receipt.json" | awk '{print $1}')"
linear_load_pattern_identity_edit_request_receipt_hash="$(sha256sum "$e2e_root/linear-load-pattern-identity-edit-first-request/request-receipt.json" | awk '{print $1}')"
linear_load_pattern_identity_edit_request_hash="$(sha256sum "$e2e_root/linear-load-pattern-identity-edit-first-request/analysis-request.json" | awk '{print $1}')"
linear_load_pattern_identity_edit_assembly_receipt_hash="$(sha256sum "$e2e_root/linear-load-pattern-identity-edit-first-direct/assembly-receipt.json" | awk '{print $1}')"
linear_load_pattern_identity_edit_checkpoint_hash="$(sha256sum "$e2e_root/linear-load-pattern-identity-edit-first-direct/checkpoint.mlpcp" | awk '{print $1}')"
linear_load_pattern_identity_edit_result_ir_hash="$(sha256sum "$e2e_root/linear-load-pattern-identity-edit-first-direct/result-ir.json" | awk '{print $1}')"
linear_load_pattern_identity_edit_recovery_hash="$(sha256sum "$e2e_root/linear-load-pattern-identity-edit-first-direct/result-recovery-ir.json" | awk '{print $1}')"
linear_load_pattern_identity_edit_report_ir_hash="$(sha256sum "$e2e_root/linear-load-pattern-identity-edit-first-direct/report-ir.json" | awk '{print $1}')"
linear_material_identity_edit_model_hash="$(sha256sum "$e2e_root/linear-material-identity-edit-first/model-ir.json" | awk '{print $1}')"
linear_material_identity_edit_receipt_hash="$(sha256sum "$e2e_root/linear-material-identity-edit-first/edit-receipt.json" | awk '{print $1}')"
linear_material_identity_edit_request_receipt_hash="$(sha256sum "$e2e_root/linear-material-identity-edit-first-request/request-receipt.json" | awk '{print $1}')"
linear_material_identity_edit_request_hash="$(sha256sum "$e2e_root/linear-material-identity-edit-first-request/analysis-request.json" | awk '{print $1}')"
linear_material_identity_edit_assembly_receipt_hash="$(sha256sum "$e2e_root/linear-material-identity-edit-first-direct/assembly-receipt.json" | awk '{print $1}')"
linear_material_identity_edit_checkpoint_hash="$(sha256sum "$e2e_root/linear-material-identity-edit-first-direct/checkpoint.mlpcp" | awk '{print $1}')"
linear_material_identity_edit_result_ir_hash="$(sha256sum "$e2e_root/linear-material-identity-edit-first-direct/result-ir.json" | awk '{print $1}')"
linear_material_identity_edit_recovery_hash="$(sha256sum "$e2e_root/linear-material-identity-edit-first-direct/result-recovery-ir.json" | awk '{print $1}')"
linear_material_identity_edit_report_ir_hash="$(sha256sum "$e2e_root/linear-material-identity-edit-first-direct/report-ir.json" | awk '{print $1}')"
nodal_load_add_model_hash="$(sha256sum "$e2e_root/nodal-load-add-first/model-ir.json" | awk '{print $1}')"
nodal_load_add_receipt_hash="$(sha256sum "$e2e_root/nodal-load-add-first/edit-receipt.json" | awk '{print $1}')"
nodal_load_add_request_hash="$(sha256sum "$e2e_root/nodal-load-add-first-linear-request/analysis-request.json" | awk '{print $1}')"
nodal_load_add_result_ir_hash="$(sha256sum "$e2e_root/nodal-load-add-first-linear-run/result-ir.json" | awk '{print $1}')"
nodal_load_add_recovery_hash="$(sha256sum "$e2e_root/nodal-load-add-first-linear-run/result-recovery-ir.json" | awk '{print $1}')"
nodal_load_delete_model_hash="$(sha256sum "$e2e_root/nodal-load-delete-first/model-ir.json" | awk '{print $1}')"
nodal_load_delete_receipt_hash="$(sha256sum "$e2e_root/nodal-load-delete-first/edit-receipt.json" | awk '{print $1}')"
nodal_load_delete_request_hash="$(sha256sum "$e2e_root/nodal-load-delete-first-request/analysis-request.json" | awk '{print $1}')"
nodal_load_delete_result_ir_hash="$(sha256sum "$e2e_root/nodal-load-delete-first-direct/result-ir.json" | awk '{print $1}')"
nodal_load_delete_recovery_hash="$(sha256sum "$e2e_root/nodal-load-delete-first-direct/result-recovery-ir.json" | awk '{print $1}')"
fixed_constraint_add_model_hash="$(sha256sum "$e2e_root/fixed-constraint-add-first/model-ir.json" | awk '{print $1}')"
fixed_constraint_add_receipt_hash="$(sha256sum "$e2e_root/fixed-constraint-add-first/edit-receipt.json" | awk '{print $1}')"
fixed_constraint_add_request_hash="$(sha256sum "$e2e_root/fixed-constraint-add-first-linear-request/analysis-request.json" | awk '{print $1}')"
fixed_constraint_add_result_ir_hash="$(sha256sum "$e2e_root/fixed-constraint-add-first-linear-run/result-ir.json" | awk '{print $1}')"
fixed_constraint_add_recovery_hash="$(sha256sum "$e2e_root/fixed-constraint-add-first-linear-run/result-recovery-ir.json" | awk '{print $1}')"
fixed_constraint_delete_model_hash="$(sha256sum "$e2e_root/fixed-constraint-delete-first/model-ir.json" | awk '{print $1}')"
fixed_constraint_delete_receipt_hash="$(sha256sum "$e2e_root/fixed-constraint-delete-first/edit-receipt.json" | awk '{print $1}')"
fixed_constraint_delete_request_hash="$(sha256sum "$e2e_root/fixed-constraint-delete-first-request/analysis-request.json" | awk '{print $1}')"
fixed_constraint_delete_result_ir_hash="$(sha256sum "$e2e_root/fixed-constraint-delete-first-direct/result-ir.json" | awk '{print $1}')"
fixed_constraint_delete_recovery_hash="$(sha256sum "$e2e_root/fixed-constraint-delete-first-direct/result-recovery-ir.json" | awk '{print $1}')"
linear_load_pattern_add_model_hash="$(sha256sum "$e2e_root/linear-load-pattern-add-first/model-ir.json" | awk '{print $1}')"
linear_load_pattern_add_receipt_hash="$(sha256sum "$e2e_root/linear-load-pattern-add-first/edit-receipt.json" | awk '{print $1}')"
linear_load_pattern_add_request_hash="$(sha256sum "$e2e_root/linear-load-pattern-add-first-linear-request/analysis-request.json" | awk '{print $1}')"
linear_load_pattern_add_result_ir_hash="$(sha256sum "$e2e_root/linear-load-pattern-add-first-linear-run/result-ir.json" | awk '{print $1}')"
linear_load_pattern_add_recovery_hash="$(sha256sum "$e2e_root/linear-load-pattern-add-first-linear-run/result-recovery-ir.json" | awk '{print $1}')"
linear_load_pattern_delete_model_hash="$(sha256sum "$e2e_root/linear-load-pattern-delete-first/model-ir.json" | awk '{print $1}')"
linear_load_pattern_delete_receipt_hash="$(sha256sum "$e2e_root/linear-load-pattern-delete-first/edit-receipt.json" | awk '{print $1}')"
linear_load_pattern_delete_request_hash="$(sha256sum "$e2e_root/linear-load-pattern-delete-first-request/analysis-request.json" | awk '{print $1}')"
linear_load_pattern_delete_result_ir_hash="$(sha256sum "$e2e_root/linear-load-pattern-delete-first-direct/result-ir.json" | awk '{print $1}')"
linear_load_pattern_delete_recovery_hash="$(sha256sum "$e2e_root/linear-load-pattern-delete-first-direct/result-recovery-ir.json" | awk '{print $1}')"
linear_material_add_model_hash="$(sha256sum "$e2e_root/linear-material-add-first/model-ir.json" | awk '{print $1}')"
linear_material_add_receipt_hash="$(sha256sum "$e2e_root/linear-material-add-first/edit-receipt.json" | awk '{print $1}')"
linear_material_add_composed_model_hash="$(sha256sum "$e2e_root/linear-material-add-first-supported/model-ir.json" | awk '{print $1}')"
linear_material_add_request_hash="$(sha256sum "$e2e_root/linear-material-add-first-linear-request/analysis-request.json" | awk '{print $1}')"
linear_material_add_result_ir_hash="$(sha256sum "$e2e_root/linear-material-add-first-linear-run/result-ir.json" | awk '{print $1}')"
linear_material_add_recovery_hash="$(sha256sum "$e2e_root/linear-material-add-first-linear-run/result-recovery-ir.json" | awk '{print $1}')"
linear_material_delete_model_hash="$(sha256sum "$e2e_root/linear-material-delete-first/model-ir.json" | awk '{print $1}')"
linear_material_delete_receipt_hash="$(sha256sum "$e2e_root/linear-material-delete-first/edit-receipt.json" | awk '{print $1}')"
linear_material_delete_request_hash="$(sha256sum "$e2e_root/linear-material-delete-first-request/analysis-request.json" | awk '{print $1}')"
linear_material_delete_result_ir_hash="$(sha256sum "$e2e_root/linear-material-delete-first-direct/result-ir.json" | awk '{print $1}')"
linear_material_delete_recovery_hash="$(sha256sum "$e2e_root/linear-material-delete-first-direct/result-recovery-ir.json" | awk '{print $1}')"
frame_section_delete_model_hash="$(sha256sum "$e2e_root/frame-section-delete-first/model-ir.json" | awk '{print $1}')"
frame_section_delete_receipt_hash="$(sha256sum "$e2e_root/frame-section-delete-first/edit-receipt.json" | awk '{print $1}')"
frame_section_delete_request_hash="$(sha256sum "$e2e_root/frame-section-delete-first-request/analysis-request.json" | awk '{print $1}')"
frame_section_delete_result_ir_hash="$(sha256sum "$e2e_root/frame-section-delete-first-direct/result-ir.json" | awk '{print $1}')"
frame_section_delete_recovery_hash="$(sha256sum "$e2e_root/frame-section-delete-first-direct/result-recovery-ir.json" | awk '{print $1}')"
frame_section_add_model_hash="$(sha256sum "$e2e_root/frame-section-add-first/model-ir.json" | awk '{print $1}')"
frame_section_add_receipt_hash="$(sha256sum "$e2e_root/frame-section-add-first/edit-receipt.json" | awk '{print $1}')"
frame_section_add_composed_model_hash="$(sha256sum "$e2e_root/frame-section-add-first-supported/model-ir.json" | awk '{print $1}')"
frame_section_add_request_hash="$(sha256sum "$e2e_root/frame-section-add-first-linear-request/analysis-request.json" | awk '{print $1}')"
frame_section_add_result_ir_hash="$(sha256sum "$e2e_root/frame-section-add-first-linear-run/result-ir.json" | awk '{print $1}')"
frame_section_add_recovery_hash="$(sha256sum "$e2e_root/frame-section-add-first-linear-run/result-recovery-ir.json" | awk '{print $1}')"
frame_element_properties_edit_model_hash="$(sha256sum "$e2e_root/frame-element-properties-edit-first/model-ir.json" | awk '{print $1}')"
frame_element_properties_edit_receipt_hash="$(sha256sum "$e2e_root/frame-element-properties-edit-first/edit-receipt.json" | awk '{print $1}')"
frame_element_properties_edit_request_hash="$(sha256sum "$e2e_root/frame-element-properties-first-request/analysis-request.json" | awk '{print $1}')"
frame_element_properties_edit_result_ir_hash="$(sha256sum "$e2e_root/frame-element-properties-first-run/result-ir.json" | awk '{print $1}')"
frame_element_properties_edit_recovery_hash="$(sha256sum "$e2e_root/frame-element-properties-first-run/result-recovery-ir.json" | awk '{print $1}')"
truss3d_authoring_section_model_hash="$(sha256sum "$e2e_root/truss3d-authoring-first-section/model-ir.json" | awk '{print $1}')"
truss3d_authoring_section_receipt_hash="$(sha256sum "$e2e_root/truss3d-authoring-first-section/edit-receipt.json" | awk '{print $1}')"
truss3d_authoring_member_model_hash="$(sha256sum "$e2e_root/truss3d-authoring-first-member/model-ir.json" | awk '{print $1}')"
truss3d_authoring_member_receipt_hash="$(sha256sum "$e2e_root/truss3d-authoring-first-member/edit-receipt.json" | awk '{print $1}')"
truss3d_authoring_composed_model_hash="$(sha256sum "$e2e_root/truss3d-authoring-first-composed/model-ir.json" | awk '{print $1}')"
truss3d_authoring_request_hash="$(sha256sum "$e2e_root/truss3d-authoring-first-request/analysis-request.json" | awk '{print $1}')"
truss3d_authoring_result_ir_hash="$(sha256sum "$e2e_root/truss3d-authoring-first-direct/result-ir.json" | awk '{print $1}')"
truss3d_authoring_recovery_hash="$(sha256sum "$e2e_root/truss3d-authoring-first-direct/result-recovery-ir.json" | awk '{print $1}')"
truss_section_delete_model_hash="$(sha256sum "$e2e_root/truss-section-delete-first/model-ir.json" | awk '{print $1}')"
truss_section_delete_receipt_hash="$(sha256sum "$e2e_root/truss-section-delete-first/edit-receipt.json" | awk '{print $1}')"
truss_section_delete_request_hash="$(sha256sum "$e2e_root/truss-section-delete-first-request/analysis-request.json" | awk '{print $1}')"
truss_section_delete_result_ir_hash="$(sha256sum "$e2e_root/truss-section-delete-first-direct/result-ir.json" | awk '{print $1}')"
truss_section_delete_recovery_hash="$(sha256sum "$e2e_root/truss-section-delete-first-direct/result-recovery-ir.json" | awk '{print $1}')"
node_add_model_hash="$(sha256sum "$e2e_root/node-add-first/model-ir.json" | awk '{print $1}')"
node_add_receipt_hash="$(sha256sum "$e2e_root/node-add-first/edit-receipt.json" | awk '{print $1}')"
node_add_composed_model_hash="$(sha256sum "$e2e_root/node-add-first-composed/model-ir.json" | awk '{print $1}')"
node_add_request_hash="$(sha256sum "$e2e_root/node-add-first-request/analysis-request.json" | awk '{print $1}')"
node_add_result_ir_hash="$(sha256sum "$e2e_root/node-add-first-direct/result-ir.json" | awk '{print $1}')"
node_add_recovery_hash="$(sha256sum "$e2e_root/node-add-first-direct/result-recovery-ir.json" | awk '{print $1}')"
orphan_node_delete_model_hash="$(sha256sum "$e2e_root/orphan-node-delete-first/model-ir.json" | awk '{print $1}')"
orphan_node_delete_receipt_hash="$(sha256sum "$e2e_root/orphan-node-delete-first/edit-receipt.json" | awk '{print $1}')"
orphan_node_delete_request_hash="$(sha256sum "$e2e_root/orphan-node-delete-first-request/analysis-request.json" | awk '{print $1}')"
orphan_node_delete_result_ir_hash="$(sha256sum "$e2e_root/orphan-node-delete-first-direct/result-ir.json" | awk '{print $1}')"
orphan_node_delete_recovery_hash="$(sha256sum "$e2e_root/orphan-node-delete-first-direct/result-recovery-ir.json" | awk '{print $1}')"
linear_load_combination_add_model_hash="$(sha256sum "$e2e_root/linear-load-combination-add-first/model-ir.json" | awk '{print $1}')"
linear_load_combination_add_receipt_hash="$(sha256sum "$e2e_root/linear-load-combination-add-first/edit-receipt.json" | awk '{print $1}')"
linear_load_combination_add_validation_hash="$(sha256sum "$e2e_root/linear-load-combination-add-first-validation.json" | awk '{print $1}')"
linear_load_combination_add_view_hash="$(sha256sum "$e2e_root/linear-load-combination-add-first-view.txt" | awk '{print $1}')"
linear_load_combination_add_solver_rejection_hash="$(sha256sum "$e2e_root/linear-load-combination-add-first-solver-rejection.json" | awk '{print $1}')"
linear_load_combination_request_receipt_hash="$(sha256sum "$e2e_root/linear-load-combination-add-first-request/request-receipt.json" | awk '{print $1}')"
linear_load_combination_request_hash="$(sha256sum "$e2e_root/linear-load-combination-add-first-request/analysis-request.json" | awk '{print $1}')"
linear_load_combination_assembly_receipt_hash="$(sha256sum "$e2e_root/linear-load-combination-add-first-direct/assembly-receipt.json" | awk '{print $1}')"
linear_load_combination_checkpoint_hash="$(sha256sum "$e2e_root/linear-load-combination-add-first-direct/checkpoint.mlpcp" | awk '{print $1}')"
linear_load_combination_result_ir_hash="$(sha256sum "$e2e_root/linear-load-combination-add-first-direct/result-ir.json" | awk '{print $1}')"
linear_load_combination_recovery_hash="$(sha256sum "$e2e_root/linear-load-combination-add-first-direct/result-recovery-ir.json" | awk '{print $1}')"
linear_load_combination_report_ir_hash="$(sha256sum "$e2e_root/linear-load-combination-add-first-direct/report-ir.json" | awk '{print $1}')"
direct_linear_load_combination_model_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-first/model-ir.json" | awk '{print $1}')"
direct_linear_load_combination_edit_receipt_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-first/edit-receipt.json" | awk '{print $1}')"
direct_linear_load_combination_request_receipt_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-first-request/request-receipt.json" | awk '{print $1}')"
direct_linear_load_combination_request_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-first-request/analysis-request.json" | awk '{print $1}')"
direct_linear_load_combination_assembly_receipt_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-first-direct/assembly-receipt.json" | awk '{print $1}')"
direct_linear_load_combination_checkpoint_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-first-direct/checkpoint.mlpcp" | awk '{print $1}')"
direct_linear_load_combination_result_ir_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-first-direct/result-ir.json" | awk '{print $1}')"
direct_linear_load_combination_recovery_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-first-direct/result-recovery-ir.json" | awk '{print $1}')"
direct_linear_load_combination_report_ir_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-first-direct/report-ir.json" | awk '{print $1}')"
direct_linear_load_combination_factor_edit_model_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-factor-edit-first/model-ir.json" | awk '{print $1}')"
direct_linear_load_combination_factor_edit_receipt_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-factor-edit-first/edit-receipt.json" | awk '{print $1}')"
direct_linear_load_combination_factor_edit_request_receipt_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-factor-edit-first-request/request-receipt.json" | awk '{print $1}')"
direct_linear_load_combination_factor_edit_request_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-factor-edit-first-request/analysis-request.json" | awk '{print $1}')"
direct_linear_load_combination_factor_edit_assembly_receipt_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-factor-edit-first-direct/assembly-receipt.json" | awk '{print $1}')"
direct_linear_load_combination_factor_edit_checkpoint_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-factor-edit-first-direct/checkpoint.mlpcp" | awk '{print $1}')"
direct_linear_load_combination_factor_edit_result_ir_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-factor-edit-first-direct/result-ir.json" | awk '{print $1}')"
direct_linear_load_combination_factor_edit_recovery_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-factor-edit-first-direct/result-recovery-ir.json" | awk '{print $1}')"
direct_linear_load_combination_factor_edit_report_ir_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-factor-edit-first-direct/report-ir.json" | awk '{print $1}')"
nested_linear_load_combination_model_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-first/model-ir.json" | awk '{print $1}')"
nested_linear_load_combination_edit_receipt_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-first/edit-receipt.json" | awk '{print $1}')"
nested_linear_load_combination_request_receipt_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-first-request/request-receipt.json" | awk '{print $1}')"
nested_linear_load_combination_request_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-first-request/analysis-request.json" | awk '{print $1}')"
nested_linear_load_combination_assembly_receipt_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-first-direct/assembly-receipt.json" | awk '{print $1}')"
nested_linear_load_combination_checkpoint_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-first-direct/checkpoint.mlpcp" | awk '{print $1}')"
nested_linear_load_combination_result_ir_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-first-direct/result-ir.json" | awk '{print $1}')"
nested_linear_load_combination_recovery_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-first-direct/result-recovery-ir.json" | awk '{print $1}')"
nested_linear_load_combination_report_ir_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-first-direct/report-ir.json" | awk '{print $1}')"
nested_linear_load_combination_factor_edit_model_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-factor-edit-first/model-ir.json" | awk '{print $1}')"
nested_linear_load_combination_factor_edit_receipt_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-factor-edit-first/edit-receipt.json" | awk '{print $1}')"
nested_linear_load_combination_factor_edit_request_receipt_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-factor-edit-first-request/request-receipt.json" | awk '{print $1}')"
nested_linear_load_combination_factor_edit_request_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-factor-edit-first-request/analysis-request.json" | awk '{print $1}')"
nested_linear_load_combination_factor_edit_assembly_receipt_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-factor-edit-first-direct/assembly-receipt.json" | awk '{print $1}')"
nested_linear_load_combination_factor_edit_checkpoint_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-factor-edit-first-direct/checkpoint.mlpcp" | awk '{print $1}')"
nested_linear_load_combination_factor_edit_result_ir_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-factor-edit-first-direct/result-ir.json" | awk '{print $1}')"
nested_linear_load_combination_factor_edit_recovery_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-factor-edit-first-direct/result-recovery-ir.json" | awk '{print $1}')"
nested_linear_load_combination_factor_edit_report_ir_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-factor-edit-first-direct/report-ir.json" | awk '{print $1}')"
direct_linear_load_combination_reference_edit_model_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-reference-edit-first/model-ir.json" | awk '{print $1}')"
direct_linear_load_combination_reference_edit_receipt_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-reference-edit-first/edit-receipt.json" | awk '{print $1}')"
direct_linear_load_combination_reference_edit_request_receipt_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-reference-edit-first-request/request-receipt.json" | awk '{print $1}')"
direct_linear_load_combination_reference_edit_request_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-reference-edit-first-request/analysis-request.json" | awk '{print $1}')"
direct_linear_load_combination_reference_edit_assembly_receipt_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-reference-edit-first-direct/assembly-receipt.json" | awk '{print $1}')"
direct_linear_load_combination_reference_edit_checkpoint_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-reference-edit-first-direct/checkpoint.mlpcp" | awk '{print $1}')"
direct_linear_load_combination_reference_edit_result_ir_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-reference-edit-first-direct/result-ir.json" | awk '{print $1}')"
direct_linear_load_combination_reference_edit_recovery_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-reference-edit-first-direct/result-recovery-ir.json" | awk '{print $1}')"
direct_linear_load_combination_reference_edit_report_ir_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-reference-edit-first-direct/report-ir.json" | awk '{print $1}')"
direct_linear_load_combination_term_add_model_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-add-first/model-ir.json" | awk '{print $1}')"
direct_linear_load_combination_term_add_receipt_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-add-first/edit-receipt.json" | awk '{print $1}')"
direct_linear_load_combination_term_add_request_receipt_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-add-first-request/request-receipt.json" | awk '{print $1}')"
direct_linear_load_combination_term_add_request_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-add-first-request/analysis-request.json" | awk '{print $1}')"
direct_linear_load_combination_term_add_assembly_receipt_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-add-first-direct/assembly-receipt.json" | awk '{print $1}')"
direct_linear_load_combination_term_add_checkpoint_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-add-first-direct/checkpoint.mlpcp" | awk '{print $1}')"
direct_linear_load_combination_term_add_result_ir_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-add-first-direct/result-ir.json" | awk '{print $1}')"
direct_linear_load_combination_term_add_recovery_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-add-first-direct/result-recovery-ir.json" | awk '{print $1}')"
direct_linear_load_combination_term_add_report_ir_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-add-first-direct/report-ir.json" | awk '{print $1}')"
direct_linear_load_combination_term_delete_model_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-delete-first/model-ir.json" | awk '{print $1}')"
direct_linear_load_combination_term_delete_receipt_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-delete-first/edit-receipt.json" | awk '{print $1}')"
direct_linear_load_combination_term_delete_request_receipt_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-delete-first-request/request-receipt.json" | awk '{print $1}')"
direct_linear_load_combination_term_delete_request_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-delete-first-request/analysis-request.json" | awk '{print $1}')"
direct_linear_load_combination_term_delete_assembly_receipt_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-delete-first-direct/assembly-receipt.json" | awk '{print $1}')"
direct_linear_load_combination_term_delete_checkpoint_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-delete-first-direct/checkpoint.mlpcp" | awk '{print $1}')"
direct_linear_load_combination_term_delete_result_ir_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-delete-first-direct/result-ir.json" | awk '{print $1}')"
direct_linear_load_combination_term_delete_recovery_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-delete-first-direct/result-recovery-ir.json" | awk '{print $1}')"
direct_linear_load_combination_term_delete_report_ir_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-delete-first-direct/report-ir.json" | awk '{print $1}')"
nested_linear_load_combination_term_add_model_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-add-first/model-ir.json" | awk '{print $1}')"
nested_linear_load_combination_term_add_receipt_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-add-first/edit-receipt.json" | awk '{print $1}')"
nested_linear_load_combination_term_add_request_receipt_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-add-first-request/request-receipt.json" | awk '{print $1}')"
nested_linear_load_combination_term_add_request_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-add-first-request/analysis-request.json" | awk '{print $1}')"
nested_linear_load_combination_term_add_assembly_receipt_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-add-first-direct/assembly-receipt.json" | awk '{print $1}')"
nested_linear_load_combination_term_add_checkpoint_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-add-first-direct/checkpoint.mlpcp" | awk '{print $1}')"
nested_linear_load_combination_term_add_result_ir_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-add-first-direct/result-ir.json" | awk '{print $1}')"
nested_linear_load_combination_term_add_recovery_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-add-first-direct/result-recovery-ir.json" | awk '{print $1}')"
nested_linear_load_combination_term_add_report_ir_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-add-first-direct/report-ir.json" | awk '{print $1}')"
nested_linear_load_combination_term_insert_model_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-insert-first/model-ir.json" | awk '{print $1}')"
nested_linear_load_combination_term_insert_receipt_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-insert-first/edit-receipt.json" | awk '{print $1}')"
nested_linear_load_combination_term_insert_request_receipt_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-insert-first-request/request-receipt.json" | awk '{print $1}')"
nested_linear_load_combination_term_insert_request_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-insert-first-request/analysis-request.json" | awk '{print $1}')"
nested_linear_load_combination_term_insert_assembly_receipt_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-insert-first-direct/assembly-receipt.json" | awk '{print $1}')"
nested_linear_load_combination_term_insert_checkpoint_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-insert-first-direct/checkpoint.mlpcp" | awk '{print $1}')"
nested_linear_load_combination_term_insert_result_ir_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-insert-first-direct/result-ir.json" | awk '{print $1}')"
nested_linear_load_combination_term_insert_recovery_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-insert-first-direct/result-recovery-ir.json" | awk '{print $1}')"
nested_linear_load_combination_term_insert_report_ir_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-insert-first-direct/report-ir.json" | awk '{print $1}')"
nested_linear_load_combination_term_delete_model_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-delete-first/model-ir.json" | awk '{print $1}')"
nested_linear_load_combination_term_delete_receipt_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-delete-first/edit-receipt.json" | awk '{print $1}')"
nested_linear_load_combination_term_delete_request_receipt_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-delete-first-request/request-receipt.json" | awk '{print $1}')"
nested_linear_load_combination_term_delete_request_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-delete-first-request/analysis-request.json" | awk '{print $1}')"
nested_linear_load_combination_term_delete_assembly_receipt_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-delete-first-direct/assembly-receipt.json" | awk '{print $1}')"
nested_linear_load_combination_term_delete_checkpoint_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-delete-first-direct/checkpoint.mlpcp" | awk '{print $1}')"
nested_linear_load_combination_term_delete_result_ir_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-delete-first-direct/result-ir.json" | awk '{print $1}')"
nested_linear_load_combination_term_delete_recovery_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-delete-first-direct/result-recovery-ir.json" | awk '{print $1}')"
nested_linear_load_combination_term_delete_report_ir_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-delete-first-direct/report-ir.json" | awk '{print $1}')"
nested_linear_load_combination_term_reorder_model_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-reorder-first/model-ir.json" | awk '{print $1}')"
nested_linear_load_combination_term_reorder_receipt_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-reorder-first/edit-receipt.json" | awk '{print $1}')"
nested_linear_load_combination_term_reorder_request_receipt_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-reorder-first-request/request-receipt.json" | awk '{print $1}')"
nested_linear_load_combination_term_reorder_request_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-reorder-first-request/analysis-request.json" | awk '{print $1}')"
nested_linear_load_combination_term_reorder_assembly_receipt_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-reorder-first-direct/assembly-receipt.json" | awk '{print $1}')"
nested_linear_load_combination_term_reorder_checkpoint_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-reorder-first-direct/checkpoint.mlpcp" | awk '{print $1}')"
nested_linear_load_combination_term_reorder_result_ir_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-reorder-first-direct/result-ir.json" | awk '{print $1}')"
nested_linear_load_combination_term_reorder_recovery_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-reorder-first-direct/result-recovery-ir.json" | awk '{print $1}')"
nested_linear_load_combination_term_reorder_report_ir_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-term-reorder-first-direct/report-ir.json" | awk '{print $1}')"
direct_linear_load_combination_term_reorder_model_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-reorder-first/model-ir.json" | awk '{print $1}')"
direct_linear_load_combination_term_reorder_receipt_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-reorder-first/edit-receipt.json" | awk '{print $1}')"
direct_linear_load_combination_term_reorder_request_receipt_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-reorder-first-request/request-receipt.json" | awk '{print $1}')"
direct_linear_load_combination_term_reorder_request_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-reorder-first-request/analysis-request.json" | awk '{print $1}')"
direct_linear_load_combination_term_reorder_assembly_receipt_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-reorder-first-direct/assembly-receipt.json" | awk '{print $1}')"
direct_linear_load_combination_term_reorder_checkpoint_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-reorder-first-direct/checkpoint.mlpcp" | awk '{print $1}')"
direct_linear_load_combination_term_reorder_result_ir_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-reorder-first-direct/result-ir.json" | awk '{print $1}')"
direct_linear_load_combination_term_reorder_recovery_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-reorder-first-direct/result-recovery-ir.json" | awk '{print $1}')"
direct_linear_load_combination_term_reorder_report_ir_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-reorder-first-direct/report-ir.json" | awk '{print $1}')"
direct_linear_load_combination_term_insert_model_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-insert-first/model-ir.json" | awk '{print $1}')"
direct_linear_load_combination_term_insert_receipt_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-insert-first/edit-receipt.json" | awk '{print $1}')"
direct_linear_load_combination_term_insert_request_receipt_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-insert-first-request/request-receipt.json" | awk '{print $1}')"
direct_linear_load_combination_term_insert_request_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-insert-first-request/analysis-request.json" | awk '{print $1}')"
direct_linear_load_combination_term_insert_assembly_receipt_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-insert-first-direct/assembly-receipt.json" | awk '{print $1}')"
direct_linear_load_combination_term_insert_checkpoint_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-insert-first-direct/checkpoint.mlpcp" | awk '{print $1}')"
direct_linear_load_combination_term_insert_result_ir_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-insert-first-direct/result-ir.json" | awk '{print $1}')"
direct_linear_load_combination_term_insert_recovery_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-insert-first-direct/result-recovery-ir.json" | awk '{print $1}')"
direct_linear_load_combination_term_insert_report_ir_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-term-insert-first-direct/report-ir.json" | awk '{print $1}')"
nested_linear_load_combination_reference_edit_model_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-reference-edit-first/model-ir.json" | awk '{print $1}')"
nested_linear_load_combination_reference_edit_receipt_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-reference-edit-first/edit-receipt.json" | awk '{print $1}')"
nested_linear_load_combination_reference_edit_request_receipt_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-reference-edit-first-request/request-receipt.json" | awk '{print $1}')"
nested_linear_load_combination_reference_edit_request_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-reference-edit-first-request/analysis-request.json" | awk '{print $1}')"
nested_linear_load_combination_reference_edit_assembly_receipt_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-reference-edit-first-direct/assembly-receipt.json" | awk '{print $1}')"
nested_linear_load_combination_reference_edit_checkpoint_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-reference-edit-first-direct/checkpoint.mlpcp" | awk '{print $1}')"
nested_linear_load_combination_reference_edit_result_ir_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-reference-edit-first-direct/result-ir.json" | awk '{print $1}')"
nested_linear_load_combination_reference_edit_recovery_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-reference-edit-first-direct/result-recovery-ir.json" | awk '{print $1}')"
nested_linear_load_combination_reference_edit_report_ir_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-reference-edit-first-direct/report-ir.json" | awk '{print $1}')"
nested_linear_load_combination_delete_model_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-delete-first/model-ir.json" | awk '{print $1}')"
nested_linear_load_combination_delete_receipt_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-delete-first/edit-receipt.json" | awk '{print $1}')"
nested_linear_load_combination_delete_request_receipt_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-delete-first-request/request-receipt.json" | awk '{print $1}')"
nested_linear_load_combination_delete_request_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-delete-first-request/analysis-request.json" | awk '{print $1}')"
nested_linear_load_combination_delete_assembly_receipt_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-delete-first-direct/assembly-receipt.json" | awk '{print $1}')"
nested_linear_load_combination_delete_checkpoint_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-delete-first-direct/checkpoint.mlpcp" | awk '{print $1}')"
nested_linear_load_combination_delete_result_ir_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-delete-first-direct/result-ir.json" | awk '{print $1}')"
nested_linear_load_combination_delete_recovery_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-delete-first-direct/result-recovery-ir.json" | awk '{print $1}')"
nested_linear_load_combination_delete_report_ir_hash="$(sha256sum "$e2e_root/nested-linear-load-combination-delete-first-direct/report-ir.json" | awk '{print $1}')"
direct_linear_load_combination_delete_model_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-delete-first/model-ir.json" | awk '{print $1}')"
direct_linear_load_combination_delete_receipt_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-delete-first/edit-receipt.json" | awk '{print $1}')"
direct_linear_load_combination_delete_request_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-delete-first-request/analysis-request.json" | awk '{print $1}')"
direct_linear_load_combination_delete_assembly_receipt_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-delete-first-direct/assembly-receipt.json" | awk '{print $1}')"
direct_linear_load_combination_delete_checkpoint_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-delete-first-direct/checkpoint.mlpcp" | awk '{print $1}')"
direct_linear_load_combination_delete_result_ir_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-delete-first-direct/result-ir.json" | awk '{print $1}')"
direct_linear_load_combination_delete_recovery_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-delete-first-direct/result-recovery-ir.json" | awk '{print $1}')"
direct_linear_load_combination_delete_report_ir_hash="$(sha256sum "$e2e_root/direct-linear-load-combination-delete-first-direct/report-ir.json" | awk '{print $1}')"
linear_load_combination_delete_model_hash="$(sha256sum "$e2e_root/linear-load-combination-delete-first/model-ir.json" | awk '{print $1}')"
linear_load_combination_delete_receipt_hash="$(sha256sum "$e2e_root/linear-load-combination-delete-first/edit-receipt.json" | awk '{print $1}')"
linear_load_combination_delete_request_hash="$(sha256sum "$e2e_root/linear-load-combination-delete-first-request/analysis-request.json" | awk '{print $1}')"
linear_load_combination_delete_result_ir_hash="$(sha256sum "$e2e_root/linear-load-combination-delete-first-direct/result-ir.json" | awk '{print $1}')"
linear_load_combination_delete_recovery_hash="$(sha256sum "$e2e_root/linear-load-combination-delete-first-direct/result-recovery-ir.json" | awk '{print $1}')"
truss3d_editing_section_model_hash="$(sha256sum "$e2e_root/truss3d-editing-first-section/model-ir.json" | awk '{print $1}')"
truss3d_editing_section_receipt_hash="$(sha256sum "$e2e_root/truss3d-editing-first-section/edit-receipt.json" | awk '{print $1}')"
truss3d_editing_properties_model_hash="$(sha256sum "$e2e_root/truss3d-editing-first-properties/model-ir.json" | awk '{print $1}')"
truss3d_editing_properties_receipt_hash="$(sha256sum "$e2e_root/truss3d-editing-first-properties/edit-receipt.json" | awk '{print $1}')"
truss3d_editing_section_result_ir_hash="$(sha256sum "$e2e_root/truss3d-editing-first-section-run/result-ir.json" | awk '{print $1}')"
truss3d_editing_request_hash="$(sha256sum "$e2e_root/truss3d-editing-first-request/analysis-request.json" | awk '{print $1}')"
truss3d_editing_result_ir_hash="$(sha256sum "$e2e_root/truss3d-editing-first-direct/result-ir.json" | awk '{print $1}')"
truss3d_editing_recovery_hash="$(sha256sum "$e2e_root/truss3d-editing-first-direct/result-recovery-ir.json" | awk '{print $1}')"
truss3d_leaf_deletion_model_hash="$(sha256sum "$e2e_root/truss3d-leaf-deletion-first/model-ir.json" | awk '{print $1}')"
truss3d_leaf_deletion_receipt_hash="$(sha256sum "$e2e_root/truss3d-leaf-deletion-first/edit-receipt.json" | awk '{print $1}')"
truss3d_leaf_deletion_request_hash="$(sha256sum "$e2e_root/truss3d-leaf-deletion-first-request/analysis-request.json" | awk '{print $1}')"
truss3d_leaf_deletion_result_ir_hash="$(sha256sum "$e2e_root/truss3d-leaf-deletion-first-direct/result-ir.json" | awk '{print $1}')"
truss3d_leaf_deletion_recovery_hash="$(sha256sum "$e2e_root/truss3d-leaf-deletion-first-direct/result-recovery-ir.json" | awk '{print $1}')"
frame3d_leaf_deletion_model_hash="$(sha256sum "$e2e_root/frame3d-leaf-deletion-first/model-ir.json" | awk '{print $1}')"
frame3d_leaf_deletion_receipt_hash="$(sha256sum "$e2e_root/frame3d-leaf-deletion-first/edit-receipt.json" | awk '{print $1}')"
frame3d_leaf_deletion_request_hash="$(sha256sum "$e2e_root/frame3d-leaf-deletion-first-request/analysis-request.json" | awk '{print $1}')"
frame3d_leaf_deletion_result_ir_hash="$(sha256sum "$e2e_root/frame3d-leaf-deletion-first-direct/result-ir.json" | awk '{print $1}')"
frame3d_leaf_deletion_recovery_hash="$(sha256sum "$e2e_root/frame3d-leaf-deletion-first-direct/result-recovery-ir.json" | awk '{print $1}')"
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
v22_receipt_json="${v21_receipt_json/structural-native-distribution-e2e.v21/structural-native-distribution-e2e.v22}"
model_linear_request_create_receipt_fields="\"workbench_model_linear_request_create_surface_passed\":true,\"workbench_model_linear_request_create_request_sha256\":\"sha256:$model_linear_request_create_request_hash\",\"workbench_model_linear_request_create_receipt_sha256\":\"sha256:$model_linear_request_create_receipt_hash\","
v22_receipt_json="${v22_receipt_json/\"workbench_result_view_surface_passed\":true,/${model_linear_request_create_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v22_receipt_json" > "$temporary_receipt"
v23_receipt_json="${v22_receipt_json/structural-native-distribution-e2e.v22/structural-native-distribution-e2e.v23}"
frame3d_member_add_receipt_fields="\"workbench_frame3d_member_add_surface_passed\":true,\"workbench_frame3d_member_add_model_sha256\":\"sha256:$frame3d_member_add_model_hash\",\"workbench_frame3d_member_add_receipt_sha256\":\"sha256:$frame3d_member_add_receipt_hash\",\"workbench_frame3d_member_add_request_sha256\":\"sha256:$frame3d_member_add_request_hash\",\"workbench_frame3d_member_add_result_ir_sha256\":\"sha256:$frame3d_member_add_result_ir_hash\","
v23_receipt_json="${v23_receipt_json/\"workbench_result_view_surface_passed\":true,/${frame3d_member_add_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v23_receipt_json" > "$temporary_receipt"
v24_receipt_json="${v23_receipt_json/structural-native-distribution-e2e.v23/structural-native-distribution-e2e.v24}"
nodal_load_add_receipt_fields="\"workbench_nodal_load_add_surface_passed\":true,\"workbench_nodal_load_add_model_sha256\":\"sha256:$nodal_load_add_model_hash\",\"workbench_nodal_load_add_receipt_sha256\":\"sha256:$nodal_load_add_receipt_hash\",\"workbench_nodal_load_add_request_sha256\":\"sha256:$nodal_load_add_request_hash\",\"workbench_nodal_load_add_result_ir_sha256\":\"sha256:$nodal_load_add_result_ir_hash\",\"workbench_nodal_load_add_recovery_sha256\":\"sha256:$nodal_load_add_recovery_hash\","
v24_receipt_json="${v24_receipt_json/\"workbench_result_view_surface_passed\":true,/${nodal_load_add_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v24_receipt_json" > "$temporary_receipt"
v25_receipt_json="${v24_receipt_json/structural-native-distribution-e2e.v24/structural-native-distribution-e2e.v25}"
fixed_constraint_add_receipt_fields="\"workbench_fixed_constraint_add_surface_passed\":true,\"workbench_fixed_constraint_add_model_sha256\":\"sha256:$fixed_constraint_add_model_hash\",\"workbench_fixed_constraint_add_receipt_sha256\":\"sha256:$fixed_constraint_add_receipt_hash\",\"workbench_fixed_constraint_add_request_sha256\":\"sha256:$fixed_constraint_add_request_hash\",\"workbench_fixed_constraint_add_result_ir_sha256\":\"sha256:$fixed_constraint_add_result_ir_hash\",\"workbench_fixed_constraint_add_recovery_sha256\":\"sha256:$fixed_constraint_add_recovery_hash\","
v25_receipt_json="${v25_receipt_json/\"workbench_result_view_surface_passed\":true,/${fixed_constraint_add_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v25_receipt_json" > "$temporary_receipt"
v26_receipt_json="${v25_receipt_json/structural-native-distribution-e2e.v25/structural-native-distribution-e2e.v26}"
linear_load_pattern_add_receipt_fields="\"workbench_linear_load_pattern_add_surface_passed\":true,\"workbench_linear_load_pattern_add_model_sha256\":\"sha256:$linear_load_pattern_add_model_hash\",\"workbench_linear_load_pattern_add_receipt_sha256\":\"sha256:$linear_load_pattern_add_receipt_hash\",\"workbench_linear_load_pattern_add_request_sha256\":\"sha256:$linear_load_pattern_add_request_hash\",\"workbench_linear_load_pattern_add_result_ir_sha256\":\"sha256:$linear_load_pattern_add_result_ir_hash\",\"workbench_linear_load_pattern_add_recovery_sha256\":\"sha256:$linear_load_pattern_add_recovery_hash\","
v26_receipt_json="${v26_receipt_json/\"workbench_result_view_surface_passed\":true,/${linear_load_pattern_add_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v26_receipt_json" > "$temporary_receipt"
v27_receipt_json="${v26_receipt_json/structural-native-distribution-e2e.v26/structural-native-distribution-e2e.v27}"
linear_material_add_receipt_fields="\"workbench_linear_material_add_surface_passed\":true,\"workbench_linear_material_add_model_sha256\":\"sha256:$linear_material_add_model_hash\",\"workbench_linear_material_add_receipt_sha256\":\"sha256:$linear_material_add_receipt_hash\",\"workbench_linear_material_add_composed_model_sha256\":\"sha256:$linear_material_add_composed_model_hash\",\"workbench_linear_material_add_request_sha256\":\"sha256:$linear_material_add_request_hash\",\"workbench_linear_material_add_result_ir_sha256\":\"sha256:$linear_material_add_result_ir_hash\",\"workbench_linear_material_add_recovery_sha256\":\"sha256:$linear_material_add_recovery_hash\","
v27_receipt_json="${v27_receipt_json/\"workbench_result_view_surface_passed\":true,/${linear_material_add_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v27_receipt_json" > "$temporary_receipt"
v28_receipt_json="${v27_receipt_json/structural-native-distribution-e2e.v27/structural-native-distribution-e2e.v28}"
frame_section_add_receipt_fields="\"workbench_frame_section_add_surface_passed\":true,\"workbench_frame_section_add_model_sha256\":\"sha256:$frame_section_add_model_hash\",\"workbench_frame_section_add_receipt_sha256\":\"sha256:$frame_section_add_receipt_hash\",\"workbench_frame_section_add_composed_model_sha256\":\"sha256:$frame_section_add_composed_model_hash\",\"workbench_frame_section_add_request_sha256\":\"sha256:$frame_section_add_request_hash\",\"workbench_frame_section_add_result_ir_sha256\":\"sha256:$frame_section_add_result_ir_hash\",\"workbench_frame_section_add_recovery_sha256\":\"sha256:$frame_section_add_recovery_hash\","
v28_receipt_json="${v28_receipt_json/\"workbench_result_view_surface_passed\":true,/${frame_section_add_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v28_receipt_json" > "$temporary_receipt"
v29_receipt_json="${v28_receipt_json/structural-native-distribution-e2e.v28/structural-native-distribution-e2e.v29}"
frame_element_properties_edit_receipt_fields="\"workbench_frame_element_properties_edit_surface_passed\":true,\"workbench_frame_element_properties_edit_model_sha256\":\"sha256:$frame_element_properties_edit_model_hash\",\"workbench_frame_element_properties_edit_receipt_sha256\":\"sha256:$frame_element_properties_edit_receipt_hash\",\"workbench_frame_element_properties_edit_request_sha256\":\"sha256:$frame_element_properties_edit_request_hash\",\"workbench_frame_element_properties_edit_result_ir_sha256\":\"sha256:$frame_element_properties_edit_result_ir_hash\",\"workbench_frame_element_properties_edit_recovery_sha256\":\"sha256:$frame_element_properties_edit_recovery_hash\","
v29_receipt_json="${v29_receipt_json/\"workbench_result_view_surface_passed\":true,/${frame_element_properties_edit_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v29_receipt_json" > "$temporary_receipt"
v30_receipt_json="${v29_receipt_json/structural-native-distribution-e2e.v29/structural-native-distribution-e2e.v30}"
truss3d_authoring_receipt_fields="\"workbench_truss3d_authoring_surface_passed\":true,\"workbench_truss3d_authoring_section_model_sha256\":\"sha256:$truss3d_authoring_section_model_hash\",\"workbench_truss3d_authoring_section_receipt_sha256\":\"sha256:$truss3d_authoring_section_receipt_hash\",\"workbench_truss3d_authoring_member_model_sha256\":\"sha256:$truss3d_authoring_member_model_hash\",\"workbench_truss3d_authoring_member_receipt_sha256\":\"sha256:$truss3d_authoring_member_receipt_hash\",\"workbench_truss3d_authoring_composed_model_sha256\":\"sha256:$truss3d_authoring_composed_model_hash\",\"workbench_truss3d_authoring_request_sha256\":\"sha256:$truss3d_authoring_request_hash\",\"workbench_truss3d_authoring_result_ir_sha256\":\"sha256:$truss3d_authoring_result_ir_hash\",\"workbench_truss3d_authoring_recovery_sha256\":\"sha256:$truss3d_authoring_recovery_hash\","
v30_receipt_json="${v30_receipt_json/\"workbench_result_view_surface_passed\":true,/${truss3d_authoring_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v30_receipt_json" > "$temporary_receipt"
v31_receipt_json="${v30_receipt_json/structural-native-distribution-e2e.v30/structural-native-distribution-e2e.v31}"
truss3d_editing_receipt_fields="\"workbench_truss3d_editing_surface_passed\":true,\"workbench_truss3d_editing_section_model_sha256\":\"sha256:$truss3d_editing_section_model_hash\",\"workbench_truss3d_editing_section_receipt_sha256\":\"sha256:$truss3d_editing_section_receipt_hash\",\"workbench_truss3d_editing_properties_model_sha256\":\"sha256:$truss3d_editing_properties_model_hash\",\"workbench_truss3d_editing_properties_receipt_sha256\":\"sha256:$truss3d_editing_properties_receipt_hash\",\"workbench_truss3d_editing_section_result_ir_sha256\":\"sha256:$truss3d_editing_section_result_ir_hash\",\"workbench_truss3d_editing_request_sha256\":\"sha256:$truss3d_editing_request_hash\",\"workbench_truss3d_editing_result_ir_sha256\":\"sha256:$truss3d_editing_result_ir_hash\",\"workbench_truss3d_editing_recovery_sha256\":\"sha256:$truss3d_editing_recovery_hash\","
v31_receipt_json="${v31_receipt_json/\"workbench_result_view_surface_passed\":true,/${truss3d_editing_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v31_receipt_json" > "$temporary_receipt"
v32_receipt_json="${v31_receipt_json/structural-native-distribution-e2e.v31/structural-native-distribution-e2e.v32}"
truss3d_leaf_deletion_receipt_fields="\"workbench_truss3d_leaf_deletion_surface_passed\":true,\"workbench_truss3d_leaf_deletion_model_sha256\":\"sha256:$truss3d_leaf_deletion_model_hash\",\"workbench_truss3d_leaf_deletion_receipt_sha256\":\"sha256:$truss3d_leaf_deletion_receipt_hash\",\"workbench_truss3d_leaf_deletion_request_sha256\":\"sha256:$truss3d_leaf_deletion_request_hash\",\"workbench_truss3d_leaf_deletion_result_ir_sha256\":\"sha256:$truss3d_leaf_deletion_result_ir_hash\",\"workbench_truss3d_leaf_deletion_recovery_sha256\":\"sha256:$truss3d_leaf_deletion_recovery_hash\","
v32_receipt_json="${v32_receipt_json/\"workbench_result_view_surface_passed\":true,/${truss3d_leaf_deletion_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v32_receipt_json" > "$temporary_receipt"
v33_receipt_json="${v32_receipt_json/structural-native-distribution-e2e.v32/structural-native-distribution-e2e.v33}"
frame3d_leaf_deletion_receipt_fields="\"workbench_frame3d_leaf_deletion_surface_passed\":true,\"workbench_frame3d_leaf_deletion_model_sha256\":\"sha256:$frame3d_leaf_deletion_model_hash\",\"workbench_frame3d_leaf_deletion_receipt_sha256\":\"sha256:$frame3d_leaf_deletion_receipt_hash\",\"workbench_frame3d_leaf_deletion_request_sha256\":\"sha256:$frame3d_leaf_deletion_request_hash\",\"workbench_frame3d_leaf_deletion_result_ir_sha256\":\"sha256:$frame3d_leaf_deletion_result_ir_hash\",\"workbench_frame3d_leaf_deletion_recovery_sha256\":\"sha256:$frame3d_leaf_deletion_recovery_hash\","
v33_receipt_json="${v33_receipt_json/\"workbench_result_view_surface_passed\":true,/${frame3d_leaf_deletion_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v33_receipt_json" > "$temporary_receipt"
v34_receipt_json="${v33_receipt_json/structural-native-distribution-e2e.v33/structural-native-distribution-e2e.v34}"
fixed_constraint_delete_receipt_fields="\"workbench_fixed_constraint_delete_surface_passed\":true,\"workbench_fixed_constraint_delete_model_sha256\":\"sha256:$fixed_constraint_delete_model_hash\",\"workbench_fixed_constraint_delete_receipt_sha256\":\"sha256:$fixed_constraint_delete_receipt_hash\",\"workbench_fixed_constraint_delete_request_sha256\":\"sha256:$fixed_constraint_delete_request_hash\",\"workbench_fixed_constraint_delete_result_ir_sha256\":\"sha256:$fixed_constraint_delete_result_ir_hash\",\"workbench_fixed_constraint_delete_recovery_sha256\":\"sha256:$fixed_constraint_delete_recovery_hash\","
v34_receipt_json="${v34_receipt_json/\"workbench_result_view_surface_passed\":true,/${fixed_constraint_delete_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v34_receipt_json" > "$temporary_receipt"
v35_receipt_json="${v34_receipt_json/structural-native-distribution-e2e.v34/structural-native-distribution-e2e.v35}"
nodal_load_delete_receipt_fields="\"workbench_nodal_load_delete_surface_passed\":true,\"workbench_nodal_load_delete_model_sha256\":\"sha256:$nodal_load_delete_model_hash\",\"workbench_nodal_load_delete_receipt_sha256\":\"sha256:$nodal_load_delete_receipt_hash\",\"workbench_nodal_load_delete_request_sha256\":\"sha256:$nodal_load_delete_request_hash\",\"workbench_nodal_load_delete_result_ir_sha256\":\"sha256:$nodal_load_delete_result_ir_hash\",\"workbench_nodal_load_delete_recovery_sha256\":\"sha256:$nodal_load_delete_recovery_hash\","
v35_receipt_json="${v35_receipt_json/\"workbench_result_view_surface_passed\":true,/${nodal_load_delete_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v35_receipt_json" > "$temporary_receipt"
v36_receipt_json="${v35_receipt_json/structural-native-distribution-e2e.v35/structural-native-distribution-e2e.v36}"
linear_load_pattern_delete_receipt_fields="\"workbench_linear_load_pattern_delete_surface_passed\":true,\"workbench_linear_load_pattern_delete_model_sha256\":\"sha256:$linear_load_pattern_delete_model_hash\",\"workbench_linear_load_pattern_delete_receipt_sha256\":\"sha256:$linear_load_pattern_delete_receipt_hash\",\"workbench_linear_load_pattern_delete_request_sha256\":\"sha256:$linear_load_pattern_delete_request_hash\",\"workbench_linear_load_pattern_delete_result_ir_sha256\":\"sha256:$linear_load_pattern_delete_result_ir_hash\",\"workbench_linear_load_pattern_delete_recovery_sha256\":\"sha256:$linear_load_pattern_delete_recovery_hash\","
v36_receipt_json="${v36_receipt_json/\"workbench_result_view_surface_passed\":true,/${linear_load_pattern_delete_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v36_receipt_json" > "$temporary_receipt"
v37_receipt_json="${v36_receipt_json/structural-native-distribution-e2e.v36/structural-native-distribution-e2e.v37}"
linear_material_delete_receipt_fields="\"workbench_linear_material_delete_surface_passed\":true,\"workbench_linear_material_delete_model_sha256\":\"sha256:$linear_material_delete_model_hash\",\"workbench_linear_material_delete_receipt_sha256\":\"sha256:$linear_material_delete_receipt_hash\",\"workbench_linear_material_delete_request_sha256\":\"sha256:$linear_material_delete_request_hash\",\"workbench_linear_material_delete_result_ir_sha256\":\"sha256:$linear_material_delete_result_ir_hash\",\"workbench_linear_material_delete_recovery_sha256\":\"sha256:$linear_material_delete_recovery_hash\","
v37_receipt_json="${v37_receipt_json/\"workbench_result_view_surface_passed\":true,/${linear_material_delete_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v37_receipt_json" > "$temporary_receipt"
v38_receipt_json="${v37_receipt_json/structural-native-distribution-e2e.v37/structural-native-distribution-e2e.v38}"
frame_section_delete_receipt_fields="\"workbench_frame_section_delete_surface_passed\":true,\"workbench_frame_section_delete_model_sha256\":\"sha256:$frame_section_delete_model_hash\",\"workbench_frame_section_delete_receipt_sha256\":\"sha256:$frame_section_delete_receipt_hash\",\"workbench_frame_section_delete_request_sha256\":\"sha256:$frame_section_delete_request_hash\",\"workbench_frame_section_delete_result_ir_sha256\":\"sha256:$frame_section_delete_result_ir_hash\",\"workbench_frame_section_delete_recovery_sha256\":\"sha256:$frame_section_delete_recovery_hash\","
v38_receipt_json="${v38_receipt_json/\"workbench_result_view_surface_passed\":true,/${frame_section_delete_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v38_receipt_json" > "$temporary_receipt"
v39_receipt_json="${v38_receipt_json/structural-native-distribution-e2e.v38/structural-native-distribution-e2e.v39}"
truss_section_delete_receipt_fields="\"workbench_truss_section_delete_surface_passed\":true,\"workbench_truss_section_delete_model_sha256\":\"sha256:$truss_section_delete_model_hash\",\"workbench_truss_section_delete_receipt_sha256\":\"sha256:$truss_section_delete_receipt_hash\",\"workbench_truss_section_delete_request_sha256\":\"sha256:$truss_section_delete_request_hash\",\"workbench_truss_section_delete_result_ir_sha256\":\"sha256:$truss_section_delete_result_ir_hash\",\"workbench_truss_section_delete_recovery_sha256\":\"sha256:$truss_section_delete_recovery_hash\","
v39_receipt_json="${v39_receipt_json/\"workbench_result_view_surface_passed\":true,/${truss_section_delete_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v39_receipt_json" > "$temporary_receipt"
v40_receipt_json="${v39_receipt_json/structural-native-distribution-e2e.v39/structural-native-distribution-e2e.v40}"
node_add_receipt_fields="\"workbench_node_add_surface_passed\":true,\"workbench_node_add_model_sha256\":\"sha256:$node_add_model_hash\",\"workbench_node_add_receipt_sha256\":\"sha256:$node_add_receipt_hash\",\"workbench_node_add_composed_model_sha256\":\"sha256:$node_add_composed_model_hash\",\"workbench_node_add_request_sha256\":\"sha256:$node_add_request_hash\",\"workbench_node_add_result_ir_sha256\":\"sha256:$node_add_result_ir_hash\",\"workbench_node_add_recovery_sha256\":\"sha256:$node_add_recovery_hash\","
v40_receipt_json="${v40_receipt_json/\"workbench_result_view_surface_passed\":true,/${node_add_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v40_receipt_json" > "$temporary_receipt"
v41_receipt_json="${v40_receipt_json/structural-native-distribution-e2e.v40/structural-native-distribution-e2e.v41}"
orphan_node_delete_receipt_fields="\"workbench_orphan_node_delete_surface_passed\":true,\"workbench_orphan_node_delete_model_sha256\":\"sha256:$orphan_node_delete_model_hash\",\"workbench_orphan_node_delete_receipt_sha256\":\"sha256:$orphan_node_delete_receipt_hash\",\"workbench_orphan_node_delete_request_sha256\":\"sha256:$orphan_node_delete_request_hash\",\"workbench_orphan_node_delete_result_ir_sha256\":\"sha256:$orphan_node_delete_result_ir_hash\",\"workbench_orphan_node_delete_recovery_sha256\":\"sha256:$orphan_node_delete_recovery_hash\","
v41_receipt_json="${v41_receipt_json/\"workbench_result_view_surface_passed\":true,/${orphan_node_delete_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v41_receipt_json" > "$temporary_receipt"
v42_receipt_json="${v41_receipt_json/structural-native-distribution-e2e.v41/structural-native-distribution-e2e.v42}"
linear_load_combination_add_receipt_fields="\"workbench_linear_load_combination_add_surface_passed\":true,\"workbench_linear_load_combination_add_model_sha256\":\"sha256:$linear_load_combination_add_model_hash\",\"workbench_linear_load_combination_add_receipt_sha256\":\"sha256:$linear_load_combination_add_receipt_hash\",\"workbench_linear_load_combination_add_validation_sha256\":\"sha256:$linear_load_combination_add_validation_hash\",\"workbench_linear_load_combination_add_view_sha256\":\"sha256:$linear_load_combination_add_view_hash\",\"workbench_linear_load_combination_add_solver_rejection_sha256\":\"sha256:$linear_load_combination_add_solver_rejection_hash\","
v42_receipt_json="${v42_receipt_json/\"workbench_result_view_surface_passed\":true,/${linear_load_combination_add_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v42_receipt_json" > "$temporary_receipt"
v43_receipt_json="${v42_receipt_json/structural-native-distribution-e2e.v42/structural-native-distribution-e2e.v43}"
linear_load_combination_delete_receipt_fields="\"workbench_linear_load_combination_delete_surface_passed\":true,\"workbench_linear_load_combination_delete_model_sha256\":\"sha256:$linear_load_combination_delete_model_hash\",\"workbench_linear_load_combination_delete_receipt_sha256\":\"sha256:$linear_load_combination_delete_receipt_hash\",\"workbench_linear_load_combination_delete_request_sha256\":\"sha256:$linear_load_combination_delete_request_hash\",\"workbench_linear_load_combination_delete_result_ir_sha256\":\"sha256:$linear_load_combination_delete_result_ir_hash\",\"workbench_linear_load_combination_delete_recovery_sha256\":\"sha256:$linear_load_combination_delete_recovery_hash\","
v43_receipt_json="${v43_receipt_json/\"workbench_result_view_surface_passed\":true,/${linear_load_combination_delete_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v43_receipt_json" > "$temporary_receipt"
v44_receipt_json="${v43_receipt_json/structural-native-distribution-e2e.v43/structural-native-distribution-e2e.v44}"
linear_load_combination_execution_receipt_fields="\"workbench_linear_load_combination_execution_surface_passed\":true,\"workbench_linear_load_combination_request_receipt_sha256\":\"sha256:$linear_load_combination_request_receipt_hash\",\"workbench_linear_load_combination_request_sha256\":\"sha256:$linear_load_combination_request_hash\",\"workbench_linear_load_combination_assembly_receipt_sha256\":\"sha256:$linear_load_combination_assembly_receipt_hash\",\"workbench_linear_load_combination_checkpoint_sha256\":\"sha256:$linear_load_combination_checkpoint_hash\",\"workbench_linear_load_combination_result_ir_sha256\":\"sha256:$linear_load_combination_result_ir_hash\",\"workbench_linear_load_combination_recovery_sha256\":\"sha256:$linear_load_combination_recovery_hash\",\"workbench_linear_load_combination_report_ir_sha256\":\"sha256:$linear_load_combination_report_ir_hash\",\"workbench_linear_load_combination_restart_passed\":true,"
v44_receipt_json="${v44_receipt_json/\"workbench_result_view_surface_passed\":true,/${linear_load_combination_execution_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v44_receipt_json" > "$temporary_receipt"
v45_receipt_json="${v44_receipt_json/structural-native-distribution-e2e.v44/structural-native-distribution-e2e.v45}"
direct_linear_load_combination_receipt_fields="\"workbench_direct_linear_load_combination_surface_passed\":true,\"workbench_direct_linear_load_combination_model_sha256\":\"sha256:$direct_linear_load_combination_model_hash\",\"workbench_direct_linear_load_combination_edit_receipt_sha256\":\"sha256:$direct_linear_load_combination_edit_receipt_hash\",\"workbench_direct_linear_load_combination_request_receipt_sha256\":\"sha256:$direct_linear_load_combination_request_receipt_hash\",\"workbench_direct_linear_load_combination_request_sha256\":\"sha256:$direct_linear_load_combination_request_hash\",\"workbench_direct_linear_load_combination_assembly_receipt_sha256\":\"sha256:$direct_linear_load_combination_assembly_receipt_hash\",\"workbench_direct_linear_load_combination_checkpoint_sha256\":\"sha256:$direct_linear_load_combination_checkpoint_hash\",\"workbench_direct_linear_load_combination_result_ir_sha256\":\"sha256:$direct_linear_load_combination_result_ir_hash\",\"workbench_direct_linear_load_combination_recovery_sha256\":\"sha256:$direct_linear_load_combination_recovery_hash\",\"workbench_direct_linear_load_combination_report_ir_sha256\":\"sha256:$direct_linear_load_combination_report_ir_hash\",\"workbench_direct_linear_load_combination_restart_passed\":true,"
v45_receipt_json="${v45_receipt_json/\"workbench_result_view_surface_passed\":true,/${direct_linear_load_combination_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v45_receipt_json" > "$temporary_receipt"
v46_receipt_json="${v45_receipt_json/structural-native-distribution-e2e.v45/structural-native-distribution-e2e.v46}"
nested_linear_load_combination_receipt_fields="\"workbench_nested_linear_load_combination_surface_passed\":true,\"workbench_nested_linear_load_combination_model_sha256\":\"sha256:$nested_linear_load_combination_model_hash\",\"workbench_nested_linear_load_combination_edit_receipt_sha256\":\"sha256:$nested_linear_load_combination_edit_receipt_hash\",\"workbench_nested_linear_load_combination_request_receipt_sha256\":\"sha256:$nested_linear_load_combination_request_receipt_hash\",\"workbench_nested_linear_load_combination_request_sha256\":\"sha256:$nested_linear_load_combination_request_hash\",\"workbench_nested_linear_load_combination_assembly_receipt_sha256\":\"sha256:$nested_linear_load_combination_assembly_receipt_hash\",\"workbench_nested_linear_load_combination_checkpoint_sha256\":\"sha256:$nested_linear_load_combination_checkpoint_hash\",\"workbench_nested_linear_load_combination_result_ir_sha256\":\"sha256:$nested_linear_load_combination_result_ir_hash\",\"workbench_nested_linear_load_combination_recovery_sha256\":\"sha256:$nested_linear_load_combination_recovery_hash\",\"workbench_nested_linear_load_combination_report_ir_sha256\":\"sha256:$nested_linear_load_combination_report_ir_hash\",\"workbench_nested_linear_load_combination_restart_passed\":true,"
v46_receipt_json="${v46_receipt_json/\"workbench_result_view_surface_passed\":true,/${nested_linear_load_combination_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v46_receipt_json" > "$temporary_receipt"
v47_receipt_json="${v46_receipt_json/structural-native-distribution-e2e.v46/structural-native-distribution-e2e.v47}"
direct_linear_load_combination_delete_receipt_fields="\"workbench_direct_linear_load_combination_delete_surface_passed\":true,\"workbench_direct_linear_load_combination_delete_model_sha256\":\"sha256:$direct_linear_load_combination_delete_model_hash\",\"workbench_direct_linear_load_combination_delete_receipt_sha256\":\"sha256:$direct_linear_load_combination_delete_receipt_hash\",\"workbench_direct_linear_load_combination_delete_request_sha256\":\"sha256:$direct_linear_load_combination_delete_request_hash\",\"workbench_direct_linear_load_combination_delete_assembly_receipt_sha256\":\"sha256:$direct_linear_load_combination_delete_assembly_receipt_hash\",\"workbench_direct_linear_load_combination_delete_checkpoint_sha256\":\"sha256:$direct_linear_load_combination_delete_checkpoint_hash\",\"workbench_direct_linear_load_combination_delete_result_ir_sha256\":\"sha256:$direct_linear_load_combination_delete_result_ir_hash\",\"workbench_direct_linear_load_combination_delete_recovery_sha256\":\"sha256:$direct_linear_load_combination_delete_recovery_hash\",\"workbench_direct_linear_load_combination_delete_report_ir_sha256\":\"sha256:$direct_linear_load_combination_delete_report_ir_hash\",\"workbench_direct_linear_load_combination_delete_restart_passed\":true,"
v47_receipt_json="${v47_receipt_json/\"workbench_result_view_surface_passed\":true,/${direct_linear_load_combination_delete_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v47_receipt_json" > "$temporary_receipt"
v48_receipt_json="${v47_receipt_json/structural-native-distribution-e2e.v47/structural-native-distribution-e2e.v48}"
nested_linear_load_combination_delete_receipt_fields="\"workbench_nested_linear_load_combination_delete_surface_passed\":true,\"workbench_nested_linear_load_combination_delete_model_sha256\":\"sha256:$nested_linear_load_combination_delete_model_hash\",\"workbench_nested_linear_load_combination_delete_receipt_sha256\":\"sha256:$nested_linear_load_combination_delete_receipt_hash\",\"workbench_nested_linear_load_combination_delete_request_receipt_sha256\":\"sha256:$nested_linear_load_combination_delete_request_receipt_hash\",\"workbench_nested_linear_load_combination_delete_request_sha256\":\"sha256:$nested_linear_load_combination_delete_request_hash\",\"workbench_nested_linear_load_combination_delete_assembly_receipt_sha256\":\"sha256:$nested_linear_load_combination_delete_assembly_receipt_hash\",\"workbench_nested_linear_load_combination_delete_checkpoint_sha256\":\"sha256:$nested_linear_load_combination_delete_checkpoint_hash\",\"workbench_nested_linear_load_combination_delete_result_ir_sha256\":\"sha256:$nested_linear_load_combination_delete_result_ir_hash\",\"workbench_nested_linear_load_combination_delete_recovery_sha256\":\"sha256:$nested_linear_load_combination_delete_recovery_hash\",\"workbench_nested_linear_load_combination_delete_report_ir_sha256\":\"sha256:$nested_linear_load_combination_delete_report_ir_hash\",\"workbench_nested_linear_load_combination_delete_restart_passed\":true,"
v48_receipt_json="${v48_receipt_json/\"workbench_result_view_surface_passed\":true,/${nested_linear_load_combination_delete_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v48_receipt_json" > "$temporary_receipt"
v49_receipt_json="${v48_receipt_json/structural-native-distribution-e2e.v48/structural-native-distribution-e2e.v49}"
direct_linear_load_combination_factor_edit_receipt_fields="\"workbench_direct_linear_load_combination_factor_edit_surface_passed\":true,\"workbench_direct_linear_load_combination_factor_edit_model_sha256\":\"sha256:$direct_linear_load_combination_factor_edit_model_hash\",\"workbench_direct_linear_load_combination_factor_edit_receipt_sha256\":\"sha256:$direct_linear_load_combination_factor_edit_receipt_hash\",\"workbench_direct_linear_load_combination_factor_edit_request_receipt_sha256\":\"sha256:$direct_linear_load_combination_factor_edit_request_receipt_hash\",\"workbench_direct_linear_load_combination_factor_edit_request_sha256\":\"sha256:$direct_linear_load_combination_factor_edit_request_hash\",\"workbench_direct_linear_load_combination_factor_edit_assembly_receipt_sha256\":\"sha256:$direct_linear_load_combination_factor_edit_assembly_receipt_hash\",\"workbench_direct_linear_load_combination_factor_edit_checkpoint_sha256\":\"sha256:$direct_linear_load_combination_factor_edit_checkpoint_hash\",\"workbench_direct_linear_load_combination_factor_edit_result_ir_sha256\":\"sha256:$direct_linear_load_combination_factor_edit_result_ir_hash\",\"workbench_direct_linear_load_combination_factor_edit_recovery_sha256\":\"sha256:$direct_linear_load_combination_factor_edit_recovery_hash\",\"workbench_direct_linear_load_combination_factor_edit_report_ir_sha256\":\"sha256:$direct_linear_load_combination_factor_edit_report_ir_hash\",\"workbench_direct_linear_load_combination_factor_edit_restart_passed\":true,"
v49_receipt_json="${v49_receipt_json/\"workbench_result_view_surface_passed\":true,/${direct_linear_load_combination_factor_edit_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v49_receipt_json" > "$temporary_receipt"
v50_receipt_json="${v49_receipt_json/structural-native-distribution-e2e.v49/structural-native-distribution-e2e.v50}"
nested_linear_load_combination_factor_edit_receipt_fields="\"workbench_nested_linear_load_combination_factor_edit_surface_passed\":true,\"workbench_nested_linear_load_combination_factor_edit_model_sha256\":\"sha256:$nested_linear_load_combination_factor_edit_model_hash\",\"workbench_nested_linear_load_combination_factor_edit_receipt_sha256\":\"sha256:$nested_linear_load_combination_factor_edit_receipt_hash\",\"workbench_nested_linear_load_combination_factor_edit_request_receipt_sha256\":\"sha256:$nested_linear_load_combination_factor_edit_request_receipt_hash\",\"workbench_nested_linear_load_combination_factor_edit_request_sha256\":\"sha256:$nested_linear_load_combination_factor_edit_request_hash\",\"workbench_nested_linear_load_combination_factor_edit_assembly_receipt_sha256\":\"sha256:$nested_linear_load_combination_factor_edit_assembly_receipt_hash\",\"workbench_nested_linear_load_combination_factor_edit_checkpoint_sha256\":\"sha256:$nested_linear_load_combination_factor_edit_checkpoint_hash\",\"workbench_nested_linear_load_combination_factor_edit_result_ir_sha256\":\"sha256:$nested_linear_load_combination_factor_edit_result_ir_hash\",\"workbench_nested_linear_load_combination_factor_edit_recovery_sha256\":\"sha256:$nested_linear_load_combination_factor_edit_recovery_hash\",\"workbench_nested_linear_load_combination_factor_edit_report_ir_sha256\":\"sha256:$nested_linear_load_combination_factor_edit_report_ir_hash\",\"workbench_nested_linear_load_combination_factor_edit_restart_passed\":true,"
v50_receipt_json="${v50_receipt_json/\"workbench_result_view_surface_passed\":true,/${nested_linear_load_combination_factor_edit_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v50_receipt_json" > "$temporary_receipt"
v51_receipt_json="${v50_receipt_json/structural-native-distribution-e2e.v50/structural-native-distribution-e2e.v51}"
direct_linear_load_combination_reference_edit_receipt_fields="\"workbench_direct_linear_load_combination_reference_edit_surface_passed\":true,\"workbench_direct_linear_load_combination_reference_edit_model_sha256\":\"sha256:$direct_linear_load_combination_reference_edit_model_hash\",\"workbench_direct_linear_load_combination_reference_edit_receipt_sha256\":\"sha256:$direct_linear_load_combination_reference_edit_receipt_hash\",\"workbench_direct_linear_load_combination_reference_edit_request_receipt_sha256\":\"sha256:$direct_linear_load_combination_reference_edit_request_receipt_hash\",\"workbench_direct_linear_load_combination_reference_edit_request_sha256\":\"sha256:$direct_linear_load_combination_reference_edit_request_hash\",\"workbench_direct_linear_load_combination_reference_edit_assembly_receipt_sha256\":\"sha256:$direct_linear_load_combination_reference_edit_assembly_receipt_hash\",\"workbench_direct_linear_load_combination_reference_edit_checkpoint_sha256\":\"sha256:$direct_linear_load_combination_reference_edit_checkpoint_hash\",\"workbench_direct_linear_load_combination_reference_edit_result_ir_sha256\":\"sha256:$direct_linear_load_combination_reference_edit_result_ir_hash\",\"workbench_direct_linear_load_combination_reference_edit_recovery_sha256\":\"sha256:$direct_linear_load_combination_reference_edit_recovery_hash\",\"workbench_direct_linear_load_combination_reference_edit_report_ir_sha256\":\"sha256:$direct_linear_load_combination_reference_edit_report_ir_hash\",\"workbench_direct_linear_load_combination_reference_edit_restart_passed\":true,"
v51_receipt_json="${v51_receipt_json/\"workbench_result_view_surface_passed\":true,/${direct_linear_load_combination_reference_edit_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v51_receipt_json" > "$temporary_receipt"
v52_receipt_json="${v51_receipt_json/structural-native-distribution-e2e.v51/structural-native-distribution-e2e.v52}"
nested_linear_load_combination_reference_edit_receipt_fields="\"workbench_nested_linear_load_combination_reference_edit_surface_passed\":true,\"workbench_nested_linear_load_combination_reference_edit_model_sha256\":\"sha256:$nested_linear_load_combination_reference_edit_model_hash\",\"workbench_nested_linear_load_combination_reference_edit_receipt_sha256\":\"sha256:$nested_linear_load_combination_reference_edit_receipt_hash\",\"workbench_nested_linear_load_combination_reference_edit_request_receipt_sha256\":\"sha256:$nested_linear_load_combination_reference_edit_request_receipt_hash\",\"workbench_nested_linear_load_combination_reference_edit_request_sha256\":\"sha256:$nested_linear_load_combination_reference_edit_request_hash\",\"workbench_nested_linear_load_combination_reference_edit_assembly_receipt_sha256\":\"sha256:$nested_linear_load_combination_reference_edit_assembly_receipt_hash\",\"workbench_nested_linear_load_combination_reference_edit_checkpoint_sha256\":\"sha256:$nested_linear_load_combination_reference_edit_checkpoint_hash\",\"workbench_nested_linear_load_combination_reference_edit_result_ir_sha256\":\"sha256:$nested_linear_load_combination_reference_edit_result_ir_hash\",\"workbench_nested_linear_load_combination_reference_edit_recovery_sha256\":\"sha256:$nested_linear_load_combination_reference_edit_recovery_hash\",\"workbench_nested_linear_load_combination_reference_edit_report_ir_sha256\":\"sha256:$nested_linear_load_combination_reference_edit_report_ir_hash\",\"workbench_nested_linear_load_combination_reference_edit_restart_passed\":true,"
v52_receipt_json="${v52_receipt_json/\"workbench_result_view_surface_passed\":true,/${nested_linear_load_combination_reference_edit_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v52_receipt_json" > "$temporary_receipt"
v53_receipt_json="${v52_receipt_json/structural-native-distribution-e2e.v52/structural-native-distribution-e2e.v53}"
direct_linear_load_combination_term_add_receipt_fields="\"workbench_direct_linear_load_combination_term_add_surface_passed\":true,\"workbench_direct_linear_load_combination_term_add_model_sha256\":\"sha256:$direct_linear_load_combination_term_add_model_hash\",\"workbench_direct_linear_load_combination_term_add_receipt_sha256\":\"sha256:$direct_linear_load_combination_term_add_receipt_hash\",\"workbench_direct_linear_load_combination_term_add_request_receipt_sha256\":\"sha256:$direct_linear_load_combination_term_add_request_receipt_hash\",\"workbench_direct_linear_load_combination_term_add_request_sha256\":\"sha256:$direct_linear_load_combination_term_add_request_hash\",\"workbench_direct_linear_load_combination_term_add_assembly_receipt_sha256\":\"sha256:$direct_linear_load_combination_term_add_assembly_receipt_hash\",\"workbench_direct_linear_load_combination_term_add_checkpoint_sha256\":\"sha256:$direct_linear_load_combination_term_add_checkpoint_hash\",\"workbench_direct_linear_load_combination_term_add_result_ir_sha256\":\"sha256:$direct_linear_load_combination_term_add_result_ir_hash\",\"workbench_direct_linear_load_combination_term_add_recovery_sha256\":\"sha256:$direct_linear_load_combination_term_add_recovery_hash\",\"workbench_direct_linear_load_combination_term_add_report_ir_sha256\":\"sha256:$direct_linear_load_combination_term_add_report_ir_hash\",\"workbench_direct_linear_load_combination_term_add_restart_passed\":true,"
v53_receipt_json="${v53_receipt_json/\"workbench_result_view_surface_passed\":true,/${direct_linear_load_combination_term_add_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v53_receipt_json" > "$temporary_receipt"
v54_receipt_json="${v53_receipt_json/structural-native-distribution-e2e.v53/structural-native-distribution-e2e.v54}"
direct_linear_load_combination_term_delete_receipt_fields="\"workbench_direct_linear_load_combination_term_delete_surface_passed\":true,\"workbench_direct_linear_load_combination_term_delete_model_sha256\":\"sha256:$direct_linear_load_combination_term_delete_model_hash\",\"workbench_direct_linear_load_combination_term_delete_receipt_sha256\":\"sha256:$direct_linear_load_combination_term_delete_receipt_hash\",\"workbench_direct_linear_load_combination_term_delete_request_receipt_sha256\":\"sha256:$direct_linear_load_combination_term_delete_request_receipt_hash\",\"workbench_direct_linear_load_combination_term_delete_request_sha256\":\"sha256:$direct_linear_load_combination_term_delete_request_hash\",\"workbench_direct_linear_load_combination_term_delete_assembly_receipt_sha256\":\"sha256:$direct_linear_load_combination_term_delete_assembly_receipt_hash\",\"workbench_direct_linear_load_combination_term_delete_checkpoint_sha256\":\"sha256:$direct_linear_load_combination_term_delete_checkpoint_hash\",\"workbench_direct_linear_load_combination_term_delete_result_ir_sha256\":\"sha256:$direct_linear_load_combination_term_delete_result_ir_hash\",\"workbench_direct_linear_load_combination_term_delete_recovery_sha256\":\"sha256:$direct_linear_load_combination_term_delete_recovery_hash\",\"workbench_direct_linear_load_combination_term_delete_report_ir_sha256\":\"sha256:$direct_linear_load_combination_term_delete_report_ir_hash\",\"workbench_direct_linear_load_combination_term_delete_restart_passed\":true,"
v54_receipt_json="${v54_receipt_json/\"workbench_result_view_surface_passed\":true,/${direct_linear_load_combination_term_delete_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v54_receipt_json" > "$temporary_receipt"
v55_receipt_json="${v54_receipt_json/structural-native-distribution-e2e.v54/structural-native-distribution-e2e.v55}"
nested_linear_load_combination_term_add_receipt_fields="\"workbench_nested_linear_load_combination_term_add_surface_passed\":true,\"workbench_nested_linear_load_combination_term_add_model_sha256\":\"sha256:$nested_linear_load_combination_term_add_model_hash\",\"workbench_nested_linear_load_combination_term_add_receipt_sha256\":\"sha256:$nested_linear_load_combination_term_add_receipt_hash\",\"workbench_nested_linear_load_combination_term_add_request_receipt_sha256\":\"sha256:$nested_linear_load_combination_term_add_request_receipt_hash\",\"workbench_nested_linear_load_combination_term_add_request_sha256\":\"sha256:$nested_linear_load_combination_term_add_request_hash\",\"workbench_nested_linear_load_combination_term_add_assembly_receipt_sha256\":\"sha256:$nested_linear_load_combination_term_add_assembly_receipt_hash\",\"workbench_nested_linear_load_combination_term_add_checkpoint_sha256\":\"sha256:$nested_linear_load_combination_term_add_checkpoint_hash\",\"workbench_nested_linear_load_combination_term_add_result_ir_sha256\":\"sha256:$nested_linear_load_combination_term_add_result_ir_hash\",\"workbench_nested_linear_load_combination_term_add_recovery_sha256\":\"sha256:$nested_linear_load_combination_term_add_recovery_hash\",\"workbench_nested_linear_load_combination_term_add_report_ir_sha256\":\"sha256:$nested_linear_load_combination_term_add_report_ir_hash\",\"workbench_nested_linear_load_combination_term_add_restart_passed\":true,"
v55_receipt_json="${v55_receipt_json/\"workbench_result_view_surface_passed\":true,/${nested_linear_load_combination_term_add_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v55_receipt_json" > "$temporary_receipt"
v56_receipt_json="${v55_receipt_json/structural-native-distribution-e2e.v55/structural-native-distribution-e2e.v56}"
nested_linear_load_combination_term_delete_receipt_fields="\"workbench_nested_linear_load_combination_term_delete_surface_passed\":true,\"workbench_nested_linear_load_combination_term_delete_model_sha256\":\"sha256:$nested_linear_load_combination_term_delete_model_hash\",\"workbench_nested_linear_load_combination_term_delete_receipt_sha256\":\"sha256:$nested_linear_load_combination_term_delete_receipt_hash\",\"workbench_nested_linear_load_combination_term_delete_request_receipt_sha256\":\"sha256:$nested_linear_load_combination_term_delete_request_receipt_hash\",\"workbench_nested_linear_load_combination_term_delete_request_sha256\":\"sha256:$nested_linear_load_combination_term_delete_request_hash\",\"workbench_nested_linear_load_combination_term_delete_assembly_receipt_sha256\":\"sha256:$nested_linear_load_combination_term_delete_assembly_receipt_hash\",\"workbench_nested_linear_load_combination_term_delete_checkpoint_sha256\":\"sha256:$nested_linear_load_combination_term_delete_checkpoint_hash\",\"workbench_nested_linear_load_combination_term_delete_result_ir_sha256\":\"sha256:$nested_linear_load_combination_term_delete_result_ir_hash\",\"workbench_nested_linear_load_combination_term_delete_recovery_sha256\":\"sha256:$nested_linear_load_combination_term_delete_recovery_hash\",\"workbench_nested_linear_load_combination_term_delete_report_ir_sha256\":\"sha256:$nested_linear_load_combination_term_delete_report_ir_hash\",\"workbench_nested_linear_load_combination_term_delete_restart_passed\":true,"
v56_receipt_json="${v56_receipt_json/\"workbench_result_view_surface_passed\":true,/${nested_linear_load_combination_term_delete_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v56_receipt_json" > "$temporary_receipt"
v57_receipt_json="${v56_receipt_json/structural-native-distribution-e2e.v56/structural-native-distribution-e2e.v57}"
nested_linear_load_combination_term_reorder_receipt_fields="\"workbench_nested_linear_load_combination_term_reorder_surface_passed\":true,\"workbench_nested_linear_load_combination_term_reorder_model_sha256\":\"sha256:$nested_linear_load_combination_term_reorder_model_hash\",\"workbench_nested_linear_load_combination_term_reorder_receipt_sha256\":\"sha256:$nested_linear_load_combination_term_reorder_receipt_hash\",\"workbench_nested_linear_load_combination_term_reorder_request_receipt_sha256\":\"sha256:$nested_linear_load_combination_term_reorder_request_receipt_hash\",\"workbench_nested_linear_load_combination_term_reorder_request_sha256\":\"sha256:$nested_linear_load_combination_term_reorder_request_hash\",\"workbench_nested_linear_load_combination_term_reorder_assembly_receipt_sha256\":\"sha256:$nested_linear_load_combination_term_reorder_assembly_receipt_hash\",\"workbench_nested_linear_load_combination_term_reorder_checkpoint_sha256\":\"sha256:$nested_linear_load_combination_term_reorder_checkpoint_hash\",\"workbench_nested_linear_load_combination_term_reorder_result_ir_sha256\":\"sha256:$nested_linear_load_combination_term_reorder_result_ir_hash\",\"workbench_nested_linear_load_combination_term_reorder_recovery_sha256\":\"sha256:$nested_linear_load_combination_term_reorder_recovery_hash\",\"workbench_nested_linear_load_combination_term_reorder_report_ir_sha256\":\"sha256:$nested_linear_load_combination_term_reorder_report_ir_hash\",\"workbench_nested_linear_load_combination_term_reorder_restart_passed\":true,"
v57_receipt_json="${v57_receipt_json/\"workbench_result_view_surface_passed\":true,/${nested_linear_load_combination_term_reorder_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v57_receipt_json" > "$temporary_receipt"
v58_receipt_json="${v57_receipt_json/structural-native-distribution-e2e.v57/structural-native-distribution-e2e.v58}"
direct_linear_load_combination_term_reorder_receipt_fields="\"workbench_direct_linear_load_combination_term_reorder_surface_passed\":true,\"workbench_direct_linear_load_combination_term_reorder_model_sha256\":\"sha256:$direct_linear_load_combination_term_reorder_model_hash\",\"workbench_direct_linear_load_combination_term_reorder_receipt_sha256\":\"sha256:$direct_linear_load_combination_term_reorder_receipt_hash\",\"workbench_direct_linear_load_combination_term_reorder_request_receipt_sha256\":\"sha256:$direct_linear_load_combination_term_reorder_request_receipt_hash\",\"workbench_direct_linear_load_combination_term_reorder_request_sha256\":\"sha256:$direct_linear_load_combination_term_reorder_request_hash\",\"workbench_direct_linear_load_combination_term_reorder_assembly_receipt_sha256\":\"sha256:$direct_linear_load_combination_term_reorder_assembly_receipt_hash\",\"workbench_direct_linear_load_combination_term_reorder_checkpoint_sha256\":\"sha256:$direct_linear_load_combination_term_reorder_checkpoint_hash\",\"workbench_direct_linear_load_combination_term_reorder_result_ir_sha256\":\"sha256:$direct_linear_load_combination_term_reorder_result_ir_hash\",\"workbench_direct_linear_load_combination_term_reorder_recovery_sha256\":\"sha256:$direct_linear_load_combination_term_reorder_recovery_hash\",\"workbench_direct_linear_load_combination_term_reorder_report_ir_sha256\":\"sha256:$direct_linear_load_combination_term_reorder_report_ir_hash\",\"workbench_direct_linear_load_combination_term_reorder_restart_passed\":true,"
v58_receipt_json="${v58_receipt_json/\"workbench_result_view_surface_passed\":true,/${direct_linear_load_combination_term_reorder_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v58_receipt_json" > "$temporary_receipt"
v59_receipt_json="${v58_receipt_json/structural-native-distribution-e2e.v58/structural-native-distribution-e2e.v59}"
direct_linear_load_combination_term_insert_receipt_fields="\"workbench_direct_linear_load_combination_term_insert_surface_passed\":true,\"workbench_direct_linear_load_combination_term_insert_model_sha256\":\"sha256:$direct_linear_load_combination_term_insert_model_hash\",\"workbench_direct_linear_load_combination_term_insert_receipt_sha256\":\"sha256:$direct_linear_load_combination_term_insert_receipt_hash\",\"workbench_direct_linear_load_combination_term_insert_request_receipt_sha256\":\"sha256:$direct_linear_load_combination_term_insert_request_receipt_hash\",\"workbench_direct_linear_load_combination_term_insert_request_sha256\":\"sha256:$direct_linear_load_combination_term_insert_request_hash\",\"workbench_direct_linear_load_combination_term_insert_assembly_receipt_sha256\":\"sha256:$direct_linear_load_combination_term_insert_assembly_receipt_hash\",\"workbench_direct_linear_load_combination_term_insert_checkpoint_sha256\":\"sha256:$direct_linear_load_combination_term_insert_checkpoint_hash\",\"workbench_direct_linear_load_combination_term_insert_result_ir_sha256\":\"sha256:$direct_linear_load_combination_term_insert_result_ir_hash\",\"workbench_direct_linear_load_combination_term_insert_recovery_sha256\":\"sha256:$direct_linear_load_combination_term_insert_recovery_hash\",\"workbench_direct_linear_load_combination_term_insert_report_ir_sha256\":\"sha256:$direct_linear_load_combination_term_insert_report_ir_hash\",\"workbench_direct_linear_load_combination_term_insert_restart_passed\":true,"
v59_receipt_json="${v59_receipt_json/\"workbench_result_view_surface_passed\":true,/${direct_linear_load_combination_term_insert_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v59_receipt_json" > "$temporary_receipt"
v60_receipt_json="${v59_receipt_json/structural-native-distribution-e2e.v59/structural-native-distribution-e2e.v60}"
nested_linear_load_combination_term_insert_receipt_fields="\"workbench_nested_linear_load_combination_term_insert_surface_passed\":true,\"workbench_nested_linear_load_combination_term_insert_model_sha256\":\"sha256:$nested_linear_load_combination_term_insert_model_hash\",\"workbench_nested_linear_load_combination_term_insert_receipt_sha256\":\"sha256:$nested_linear_load_combination_term_insert_receipt_hash\",\"workbench_nested_linear_load_combination_term_insert_request_receipt_sha256\":\"sha256:$nested_linear_load_combination_term_insert_request_receipt_hash\",\"workbench_nested_linear_load_combination_term_insert_request_sha256\":\"sha256:$nested_linear_load_combination_term_insert_request_hash\",\"workbench_nested_linear_load_combination_term_insert_assembly_receipt_sha256\":\"sha256:$nested_linear_load_combination_term_insert_assembly_receipt_hash\",\"workbench_nested_linear_load_combination_term_insert_checkpoint_sha256\":\"sha256:$nested_linear_load_combination_term_insert_checkpoint_hash\",\"workbench_nested_linear_load_combination_term_insert_result_ir_sha256\":\"sha256:$nested_linear_load_combination_term_insert_result_ir_hash\",\"workbench_nested_linear_load_combination_term_insert_recovery_sha256\":\"sha256:$nested_linear_load_combination_term_insert_recovery_hash\",\"workbench_nested_linear_load_combination_term_insert_report_ir_sha256\":\"sha256:$nested_linear_load_combination_term_insert_report_ir_hash\",\"workbench_nested_linear_load_combination_term_insert_restart_passed\":true,"
v60_receipt_json="${v60_receipt_json/\"workbench_result_view_surface_passed\":true,/${nested_linear_load_combination_term_insert_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v60_receipt_json" > "$temporary_receipt"
v61_receipt_json="${v60_receipt_json/structural-native-distribution-e2e.v60/structural-native-distribution-e2e.v61}"
nodal_load_target_edit_receipt_fields="\"workbench_nodal_load_target_edit_surface_passed\":true,\"workbench_nodal_load_target_edit_model_sha256\":\"sha256:$nodal_load_target_edit_model_hash\",\"workbench_nodal_load_target_edit_receipt_sha256\":\"sha256:$nodal_load_target_edit_receipt_hash\",\"workbench_nodal_load_target_edit_request_receipt_sha256\":\"sha256:$nodal_load_target_edit_request_receipt_hash\",\"workbench_nodal_load_target_edit_request_sha256\":\"sha256:$nodal_load_target_edit_request_hash\",\"workbench_nodal_load_target_edit_assembly_receipt_sha256\":\"sha256:$nodal_load_target_edit_assembly_receipt_hash\",\"workbench_nodal_load_target_edit_checkpoint_sha256\":\"sha256:$nodal_load_target_edit_checkpoint_hash\",\"workbench_nodal_load_target_edit_result_ir_sha256\":\"sha256:$nodal_load_target_edit_result_ir_hash\",\"workbench_nodal_load_target_edit_recovery_sha256\":\"sha256:$nodal_load_target_edit_recovery_hash\",\"workbench_nodal_load_target_edit_report_ir_sha256\":\"sha256:$nodal_load_target_edit_report_ir_hash\",\"workbench_nodal_load_target_edit_restart_passed\":true,"
v61_receipt_json="${v61_receipt_json/\"workbench_result_view_surface_passed\":true,/${nodal_load_target_edit_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v61_receipt_json" > "$temporary_receipt"
v62_receipt_json="${v61_receipt_json/structural-native-distribution-e2e.v61/structural-native-distribution-e2e.v62}"
constraint_target_edit_receipt_fields="\"workbench_constraint_target_edit_surface_passed\":true,\"workbench_constraint_target_edit_model_sha256\":\"sha256:$constraint_target_edit_model_hash\",\"workbench_constraint_target_edit_receipt_sha256\":\"sha256:$constraint_target_edit_receipt_hash\",\"workbench_constraint_target_edit_request_receipt_sha256\":\"sha256:$constraint_target_edit_request_receipt_hash\",\"workbench_constraint_target_edit_request_sha256\":\"sha256:$constraint_target_edit_request_hash\",\"workbench_constraint_target_edit_assembly_receipt_sha256\":\"sha256:$constraint_target_edit_assembly_receipt_hash\",\"workbench_constraint_target_edit_checkpoint_sha256\":\"sha256:$constraint_target_edit_checkpoint_hash\",\"workbench_constraint_target_edit_result_ir_sha256\":\"sha256:$constraint_target_edit_result_ir_hash\",\"workbench_constraint_target_edit_recovery_sha256\":\"sha256:$constraint_target_edit_recovery_hash\",\"workbench_constraint_target_edit_report_ir_sha256\":\"sha256:$constraint_target_edit_report_ir_hash\",\"workbench_constraint_target_edit_restart_passed\":true,"
v62_receipt_json="${v62_receipt_json/\"workbench_result_view_surface_passed\":true,/${constraint_target_edit_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v62_receipt_json" > "$temporary_receipt"
v63_receipt_json="${v62_receipt_json/structural-native-distribution-e2e.v62/structural-native-distribution-e2e.v63}"
fixed_constraint_dof_delete_receipt_fields="\"workbench_fixed_constraint_dof_delete_surface_passed\":true,\"workbench_fixed_constraint_dof_delete_model_sha256\":\"sha256:$fixed_constraint_dof_delete_model_hash\",\"workbench_fixed_constraint_dof_delete_receipt_sha256\":\"sha256:$fixed_constraint_dof_delete_receipt_hash\",\"workbench_fixed_constraint_dof_delete_request_receipt_sha256\":\"sha256:$fixed_constraint_dof_delete_request_receipt_hash\",\"workbench_fixed_constraint_dof_delete_request_sha256\":\"sha256:$fixed_constraint_dof_delete_request_hash\",\"workbench_fixed_constraint_dof_delete_assembly_receipt_sha256\":\"sha256:$fixed_constraint_dof_delete_assembly_receipt_hash\",\"workbench_fixed_constraint_dof_delete_checkpoint_sha256\":\"sha256:$fixed_constraint_dof_delete_checkpoint_hash\",\"workbench_fixed_constraint_dof_delete_result_ir_sha256\":\"sha256:$fixed_constraint_dof_delete_result_ir_hash\",\"workbench_fixed_constraint_dof_delete_recovery_sha256\":\"sha256:$fixed_constraint_dof_delete_recovery_hash\",\"workbench_fixed_constraint_dof_delete_report_ir_sha256\":\"sha256:$fixed_constraint_dof_delete_report_ir_hash\",\"workbench_fixed_constraint_dof_delete_restart_passed\":true,"
v63_receipt_json="${v63_receipt_json/\"workbench_result_view_surface_passed\":true,/${fixed_constraint_dof_delete_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v63_receipt_json" > "$temporary_receipt"
v64_receipt_json="${v63_receipt_json/structural-native-distribution-e2e.v63/structural-native-distribution-e2e.v64}"
fixed_constraint_dof_add_receipt_fields="\"workbench_fixed_constraint_dof_add_surface_passed\":true,\"workbench_fixed_constraint_dof_add_model_sha256\":\"sha256:$fixed_constraint_dof_add_model_hash\",\"workbench_fixed_constraint_dof_add_receipt_sha256\":\"sha256:$fixed_constraint_dof_add_receipt_hash\",\"workbench_fixed_constraint_dof_add_request_receipt_sha256\":\"sha256:$fixed_constraint_dof_add_request_receipt_hash\",\"workbench_fixed_constraint_dof_add_request_sha256\":\"sha256:$fixed_constraint_dof_add_request_hash\",\"workbench_fixed_constraint_dof_add_assembly_receipt_sha256\":\"sha256:$fixed_constraint_dof_add_assembly_receipt_hash\",\"workbench_fixed_constraint_dof_add_checkpoint_sha256\":\"sha256:$fixed_constraint_dof_add_checkpoint_hash\",\"workbench_fixed_constraint_dof_add_result_ir_sha256\":\"sha256:$fixed_constraint_dof_add_result_ir_hash\",\"workbench_fixed_constraint_dof_add_recovery_sha256\":\"sha256:$fixed_constraint_dof_add_recovery_hash\",\"workbench_fixed_constraint_dof_add_report_ir_sha256\":\"sha256:$fixed_constraint_dof_add_report_ir_hash\",\"workbench_fixed_constraint_dof_add_restart_passed\":true,"
v64_receipt_json="${v64_receipt_json/\"workbench_result_view_surface_passed\":true,/${fixed_constraint_dof_add_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v64_receipt_json" > "$temporary_receipt"
v65_receipt_json="${v64_receipt_json/structural-native-distribution-e2e.v64/structural-native-distribution-e2e.v65}"
fixed_constraint_dof_reorder_receipt_fields="\"workbench_fixed_constraint_dof_reorder_surface_passed\":true,\"workbench_fixed_constraint_dof_reorder_model_sha256\":\"sha256:$fixed_constraint_dof_reorder_model_hash\",\"workbench_fixed_constraint_dof_reorder_receipt_sha256\":\"sha256:$fixed_constraint_dof_reorder_receipt_hash\",\"workbench_fixed_constraint_dof_reorder_request_receipt_sha256\":\"sha256:$fixed_constraint_dof_reorder_request_receipt_hash\",\"workbench_fixed_constraint_dof_reorder_request_sha256\":\"sha256:$fixed_constraint_dof_reorder_request_hash\",\"workbench_fixed_constraint_dof_reorder_assembly_receipt_sha256\":\"sha256:$fixed_constraint_dof_reorder_assembly_receipt_hash\",\"workbench_fixed_constraint_dof_reorder_checkpoint_sha256\":\"sha256:$fixed_constraint_dof_reorder_checkpoint_hash\",\"workbench_fixed_constraint_dof_reorder_result_ir_sha256\":\"sha256:$fixed_constraint_dof_reorder_result_ir_hash\",\"workbench_fixed_constraint_dof_reorder_recovery_sha256\":\"sha256:$fixed_constraint_dof_reorder_recovery_hash\",\"workbench_fixed_constraint_dof_reorder_report_ir_sha256\":\"sha256:$fixed_constraint_dof_reorder_report_ir_hash\",\"workbench_fixed_constraint_dof_reorder_restart_passed\":true,"
v65_receipt_json="${v65_receipt_json/\"workbench_result_view_surface_passed\":true,/${fixed_constraint_dof_reorder_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v65_receipt_json" > "$temporary_receipt"
v66_receipt_json="${v65_receipt_json/structural-native-distribution-e2e.v65/structural-native-distribution-e2e.v66}"
fixed_constraint_identity_edit_receipt_fields="\"workbench_fixed_constraint_identity_edit_surface_passed\":true,\"workbench_fixed_constraint_identity_edit_model_sha256\":\"sha256:$fixed_constraint_identity_edit_model_hash\",\"workbench_fixed_constraint_identity_edit_receipt_sha256\":\"sha256:$fixed_constraint_identity_edit_receipt_hash\",\"workbench_fixed_constraint_identity_edit_request_receipt_sha256\":\"sha256:$fixed_constraint_identity_edit_request_receipt_hash\",\"workbench_fixed_constraint_identity_edit_request_sha256\":\"sha256:$fixed_constraint_identity_edit_request_hash\",\"workbench_fixed_constraint_identity_edit_assembly_receipt_sha256\":\"sha256:$fixed_constraint_identity_edit_assembly_receipt_hash\",\"workbench_fixed_constraint_identity_edit_checkpoint_sha256\":\"sha256:$fixed_constraint_identity_edit_checkpoint_hash\",\"workbench_fixed_constraint_identity_edit_result_ir_sha256\":\"sha256:$fixed_constraint_identity_edit_result_ir_hash\",\"workbench_fixed_constraint_identity_edit_recovery_sha256\":\"sha256:$fixed_constraint_identity_edit_recovery_hash\",\"workbench_fixed_constraint_identity_edit_report_ir_sha256\":\"sha256:$fixed_constraint_identity_edit_report_ir_hash\",\"workbench_fixed_constraint_identity_edit_restart_passed\":true,"
v66_receipt_json="${v66_receipt_json/\"workbench_result_view_surface_passed\":true,/${fixed_constraint_identity_edit_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v66_receipt_json" > "$temporary_receipt"
v67_receipt_json="${v66_receipt_json/structural-native-distribution-e2e.v66/structural-native-distribution-e2e.v67}"
nodal_load_identity_edit_receipt_fields="\"workbench_nodal_load_identity_edit_surface_passed\":true,\"workbench_nodal_load_identity_edit_model_sha256\":\"sha256:$nodal_load_identity_edit_model_hash\",\"workbench_nodal_load_identity_edit_receipt_sha256\":\"sha256:$nodal_load_identity_edit_receipt_hash\",\"workbench_nodal_load_identity_edit_request_receipt_sha256\":\"sha256:$nodal_load_identity_edit_request_receipt_hash\",\"workbench_nodal_load_identity_edit_request_sha256\":\"sha256:$nodal_load_identity_edit_request_hash\",\"workbench_nodal_load_identity_edit_assembly_receipt_sha256\":\"sha256:$nodal_load_identity_edit_assembly_receipt_hash\",\"workbench_nodal_load_identity_edit_checkpoint_sha256\":\"sha256:$nodal_load_identity_edit_checkpoint_hash\",\"workbench_nodal_load_identity_edit_result_ir_sha256\":\"sha256:$nodal_load_identity_edit_result_ir_hash\",\"workbench_nodal_load_identity_edit_recovery_sha256\":\"sha256:$nodal_load_identity_edit_recovery_hash\",\"workbench_nodal_load_identity_edit_report_ir_sha256\":\"sha256:$nodal_load_identity_edit_report_ir_hash\",\"workbench_nodal_load_identity_edit_restart_passed\":true,"
v67_receipt_json="${v67_receipt_json/\"workbench_result_view_surface_passed\":true,/${nodal_load_identity_edit_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v67_receipt_json" > "$temporary_receipt"
v68_receipt_json="${v67_receipt_json/structural-native-distribution-e2e.v67/structural-native-distribution-e2e.v68}"
linear_load_pattern_identity_edit_receipt_fields="\"workbench_linear_load_pattern_identity_edit_surface_passed\":true,\"workbench_linear_load_pattern_identity_edit_model_sha256\":\"sha256:$linear_load_pattern_identity_edit_model_hash\",\"workbench_linear_load_pattern_identity_edit_receipt_sha256\":\"sha256:$linear_load_pattern_identity_edit_receipt_hash\",\"workbench_linear_load_pattern_identity_edit_request_receipt_sha256\":\"sha256:$linear_load_pattern_identity_edit_request_receipt_hash\",\"workbench_linear_load_pattern_identity_edit_request_sha256\":\"sha256:$linear_load_pattern_identity_edit_request_hash\",\"workbench_linear_load_pattern_identity_edit_assembly_receipt_sha256\":\"sha256:$linear_load_pattern_identity_edit_assembly_receipt_hash\",\"workbench_linear_load_pattern_identity_edit_checkpoint_sha256\":\"sha256:$linear_load_pattern_identity_edit_checkpoint_hash\",\"workbench_linear_load_pattern_identity_edit_result_ir_sha256\":\"sha256:$linear_load_pattern_identity_edit_result_ir_hash\",\"workbench_linear_load_pattern_identity_edit_recovery_sha256\":\"sha256:$linear_load_pattern_identity_edit_recovery_hash\",\"workbench_linear_load_pattern_identity_edit_report_ir_sha256\":\"sha256:$linear_load_pattern_identity_edit_report_ir_hash\",\"workbench_linear_load_pattern_identity_edit_restart_passed\":true,"
v68_receipt_json="${v68_receipt_json/\"workbench_result_view_surface_passed\":true,/${linear_load_pattern_identity_edit_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v68_receipt_json" > "$temporary_receipt"
v69_receipt_json="${v68_receipt_json/structural-native-distribution-e2e.v68/structural-native-distribution-e2e.v69}"
linear_material_identity_edit_receipt_fields="\"workbench_linear_material_identity_edit_surface_passed\":true,\"workbench_linear_material_identity_edit_model_sha256\":\"sha256:$linear_material_identity_edit_model_hash\",\"workbench_linear_material_identity_edit_receipt_sha256\":\"sha256:$linear_material_identity_edit_receipt_hash\",\"workbench_linear_material_identity_edit_request_receipt_sha256\":\"sha256:$linear_material_identity_edit_request_receipt_hash\",\"workbench_linear_material_identity_edit_request_sha256\":\"sha256:$linear_material_identity_edit_request_hash\",\"workbench_linear_material_identity_edit_assembly_receipt_sha256\":\"sha256:$linear_material_identity_edit_assembly_receipt_hash\",\"workbench_linear_material_identity_edit_checkpoint_sha256\":\"sha256:$linear_material_identity_edit_checkpoint_hash\",\"workbench_linear_material_identity_edit_result_ir_sha256\":\"sha256:$linear_material_identity_edit_result_ir_hash\",\"workbench_linear_material_identity_edit_recovery_sha256\":\"sha256:$linear_material_identity_edit_recovery_hash\",\"workbench_linear_material_identity_edit_report_ir_sha256\":\"sha256:$linear_material_identity_edit_report_ir_hash\",\"workbench_linear_material_identity_edit_restart_passed\":true,"
v69_receipt_json="${v69_receipt_json/\"workbench_result_view_surface_passed\":true,/${linear_material_identity_edit_receipt_fields}\"workbench_result_view_surface_passed\":true,}"
printf '%s\n' "$v69_receipt_json" > "$temporary_receipt"

backend_output_stage="$(mktemp "$backend_receipt_parent/.structural-installed-backend.XXXXXX")"
receipt_output_stage="$(mktemp "$receipt_parent/.structural-distribution-receipt.XXXXXX")"
cp "$e2e_root/installed-backend-receipt.json" "$backend_output_stage"
cp "$temporary_receipt" "$receipt_output_stage"
chmod 0444 "$backend_output_stage" "$receipt_output_stage"
mv "$backend_output_stage" "$installed_backend_receipt"
mv "$receipt_output_stage" "$receipt"
