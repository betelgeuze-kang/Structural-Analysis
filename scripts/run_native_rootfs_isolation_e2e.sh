#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 --bundle DIR --receipt FILE" >&2
}

bundle=""
receipt=""
while (($# > 0)); do
  if (($# < 2)); then
    usage
    exit 2
  fi
  case "$1" in
    --bundle) bundle="$2" ;;
    --receipt) receipt="$2" ;;
    *) usage; exit 2 ;;
  esac
  shift 2
done

if [[ ! -d "$bundle" || -L "$bundle" || -z "$receipt" ]]; then
  usage
  exit 2
fi
for command_name in unshare bwrap; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "required local rootfs isolation command is unavailable: $command_name" >&2
    exit 1
  fi
done

receipt_parent="$(dirname "$receipt")"
if [[ ! -d "$receipt_parent" || -L "$receipt_parent" || -e "$receipt" || -L "$receipt" ]]; then
  echo "receipt parent must be real and receipt output must not exist" >&2
  exit 1
fi
receipt="$(cd "$receipt_parent" && pwd -P)/$(basename "$receipt")"
bundle="$(cd "$bundle" && pwd -P)"
repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
installer="$bundle/payload/bin/structural-installer"
if [[ ! -x "$installer" ]]; then
  echo "bundle does not contain structural-installer" >&2
  exit 1
fi
"$installer" bundle-verify --bundle "$bundle" >/dev/null

e2e_root="$(mktemp -d "${TMPDIR:-/tmp}/structural-native-rootfs-e2e.XXXXXX")"
cleanup() {
  if [[ -n "$e2e_root" && -d "$e2e_root" ]]; then
    rm -rf -- "$e2e_root"
  fi
}
trap cleanup EXIT

model="$repository_root/native/tests/fixtures/model_ir_adapter/fixed_guided_frame3d_x.json"
request="$repository_root/native/tests/fixtures/model_ir_adapter/fixed_guided_ndtha_request.json"
external="$repository_root/native/tests/fixtures/external_comparison/reference_oracle_ndtha_v1.json"
source_artifact="$repository_root/native/tests/fixtures/solver_cpu/nonlinear_ndtha_one_story_elastic_python_c1.json"
mgt_source="$repository_root/native/tests/fixtures/mgt_import/workbench_fixed_guided_frame3d_x.mgt"
mgt_request="$repository_root/native/tests/fixtures/mgt_import/workbench_fixed_guided_ndtha_request.json"
evidence_bundle="$repository_root/native/tests/fixtures/workbench_evidence"
linear_model="$repository_root/tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
linear_request="$repository_root/native/tests/fixtures/model_ir_linear/frame_cantilever_weak_request.json"
linear_external="$repository_root/native/tests/fixtures/model_ir_linear/frame_cantilever_external_v1.json"
linear_source_artifact="$repository_root/native/tests/fixtures/model_ir_linear/frame_cantilever_language_neutral_oracle_v1.txt"

unshare -Urn bwrap \
  --ro-bind / / \
  --proc /proc \
  --dev /dev \
  --ro-bind "$bundle" /opt \
  --bind "$e2e_root" /mnt \
  --tmpfs /tmp \
  --unshare-user \
  --uid 65532 \
  --gid 65532 \
  --clearenv \
  --setenv PATH /nonexistent \
  --chdir /mnt \
  -- /bin/sh -eu -c '
    /opt/payload/bin/structural-workbench workflow "$1" "$2" \
      --external-result "$3" --source-artifact "$4" \
      --workspace /mnt/modelir-workbench --step-budget 1 \
      > /mnt/modelir-workflow.json
    /opt/payload/bin/structural-workbench inspect --workspace /mnt/modelir-workbench \
      > /mnt/modelir-inspect-before-review.json
    /opt/payload/bin/structural-workbench review --workspace /mnt/modelir-workbench \
      --decision review --reviewer native-rootfs-c5 \
      --comment "Explicit isolated C5 handoff review; no engineering approval is inferred." \
      > /mnt/modelir-review-publish.json
    /opt/payload/bin/structural-workbench review-show --workspace /mnt/modelir-workbench \
      > /mnt/modelir-review-show.json
    /opt/payload/bin/structural-workbench inspect --workspace /mnt/modelir-workbench \
      > /mnt/modelir-inspect-after-review.json
    /opt/payload/bin/structural-workbench export --workspace /mnt/modelir-workbench \
      > /mnt/modelir-export.json
    /opt/payload/bin/structural-workbench workflow-mgt "$5" "$6" \
      --model-id workbench-mgt-fixed-guided-v1 \
      --external-result "$3" --source-artifact "$4" \
      --workspace /mnt/mgt-workbench --step-budget 1 \
      > /mnt/mgt-workflow.json
    /opt/payload/bin/structural-workbench inspect --workspace /mnt/mgt-workbench \
      > /mnt/mgt-inspect-before-review.json
    /opt/payload/bin/structural-workbench review --workspace /mnt/mgt-workbench \
      --decision review --reviewer native-rootfs-c5 \
      --comment "Explicit isolated C5 handoff review; no engineering approval is inferred." \
      > /mnt/mgt-review-publish.json
    /opt/payload/bin/structural-workbench review-show --workspace /mnt/mgt-workbench \
      > /mnt/mgt-review-show.json
    /opt/payload/bin/structural-workbench inspect --workspace /mnt/mgt-workbench \
      > /mnt/mgt-inspect-after-review.json
    /opt/payload/bin/structural-workbench export --workspace /mnt/mgt-workbench \
      > /mnt/mgt-export.json
    /opt/payload/bin/structural-workbench workflow-model-linear "$8" "$9" \
      --external-result "${10}" --source-artifact "${11}" \
      --workspace /mnt/model-ir-linear-workbench --step-budget 1 \
      > /mnt/model-ir-linear-workflow.json
    /opt/payload/bin/structural-workbench inspect --workspace /mnt/model-ir-linear-workbench \
      > /mnt/model-ir-linear-inspect-before-review.json
    /opt/payload/bin/structural-workbench review --workspace /mnt/model-ir-linear-workbench \
      --decision review --reviewer native-rootfs-c5 \
      --comment "Explicit isolated C5 handoff review; no engineering approval is inferred." \
      > /mnt/model-ir-linear-review-publish.json
    /opt/payload/bin/structural-workbench review-show --workspace /mnt/model-ir-linear-workbench \
      > /mnt/model-ir-linear-review-show.json
    /opt/payload/bin/structural-workbench inspect --workspace /mnt/model-ir-linear-workbench \
      > /mnt/model-ir-linear-inspect-after-review.json
    /opt/payload/bin/structural-workbench export --workspace /mnt/model-ir-linear-workbench \
      > /mnt/model-ir-linear-export.json
    /bin/cp /mnt/model-ir-linear-workbench/workbench-session.json \
      /mnt/model-ir-linear-session-before-localized-pdf.json
    for locale in en-US ko-KR; do
      for repeat in first second; do
        output="/mnt/model-ir-linear-localized-pdf-$locale-$repeat"
        /opt/payload/bin/structural-workbench report-export-pdf \
          --workspace /mnt/model-ir-linear-workbench --output-dir "$output" \
          --locale "$locale" > "$output.stdout.json"
      done
      /usr/bin/cmp "/mnt/model-ir-linear-localized-pdf-$locale-first/report.pdf" \
        "/mnt/model-ir-linear-localized-pdf-$locale-second/report.pdf"
      /usr/bin/cmp "/mnt/model-ir-linear-localized-pdf-$locale-first/pdf-receipt.json" \
        "/mnt/model-ir-linear-localized-pdf-$locale-second/pdf-receipt.json"
    done
    if /usr/bin/cmp -s /mnt/model-ir-linear-localized-pdf-en-US-first/report.pdf \
      /mnt/model-ir-linear-localized-pdf-ko-KR-first/report.pdf; then
      exit 1
    fi
    /usr/bin/cmp /mnt/model-ir-linear-session-before-localized-pdf.json \
      /mnt/model-ir-linear-workbench/workbench-session.json
    /opt/payload/bin/structural-workbench catalog --truth geometry_only --size large \
      > /mnt/workbench-catalog.json
    IFS= read -r catalog_line < /mnt/workbench-catalog.json
    case "$catalog_line" in
      *\"schema_version\":\"structural-native-benchmark-catalog-view.v1\"*) ;;
      *) exit 1 ;;
    esac
    /opt/payload/bin/structural-workbench evidence --bundle "$7" \
      --as-of-unix 1786579200 > /mnt/workbench-evidence.json
    IFS= read -r evidence_line < /mnt/workbench-evidence.json
    case "$evidence_line" in
      *\"schema_version\":\"structural-native-evidence-bundle-view.v1\"*) ;;
      *) exit 1 ;;
    esac
    /opt/payload/bin/structural-installer runtime-probe \
      --bundle /opt --payload-root /opt/payload --workspace /mnt \
      --workbench-root /mnt/modelir-workbench \
      --mgt-workbench-root /mnt/mgt-workbench \
      --model-ir-linear-workbench-root /mnt/model-ir-linear-workbench \
      --workbench-inspect-before-review /mnt/modelir-inspect-before-review.json \
      --workbench-review-show /mnt/modelir-review-show.json \
      --workbench-inspect-after-review /mnt/modelir-inspect-after-review.json \
      --workbench-export /mnt/modelir-export.json \
      --mgt-workbench-inspect-before-review /mnt/mgt-inspect-before-review.json \
      --mgt-workbench-review-show /mnt/mgt-review-show.json \
      --mgt-workbench-inspect-after-review /mnt/mgt-inspect-after-review.json \
      --mgt-workbench-export /mnt/mgt-export.json \
      --model-ir-linear-workbench-inspect-before-review \
        /mnt/model-ir-linear-inspect-before-review.json \
      --model-ir-linear-workbench-review-show /mnt/model-ir-linear-review-show.json \
      --model-ir-linear-workbench-inspect-after-review \
        /mnt/model-ir-linear-inspect-after-review.json \
      --model-ir-linear-workbench-export /mnt/model-ir-linear-export.json \
      --model-ir-linear-workbench-session-before-localized-pdf \
        /mnt/model-ir-linear-session-before-localized-pdf.json \
      --model-ir-linear-localized-pdf-en-us-first-root \
        /mnt/model-ir-linear-localized-pdf-en-US-first \
      --model-ir-linear-localized-pdf-en-us-second-root \
        /mnt/model-ir-linear-localized-pdf-en-US-second \
      --model-ir-linear-localized-pdf-ko-kr-first-root \
        /mnt/model-ir-linear-localized-pdf-ko-KR-first \
      --model-ir-linear-localized-pdf-ko-kr-second-root \
        /mnt/model-ir-linear-localized-pdf-ko-KR-second \
      --workbench-catalog /mnt/workbench-catalog.json \
      --workbench-evidence /mnt/workbench-evidence.json \
      --receipt /mnt/rootfs-isolation-receipt.json \
      > /mnt/runtime-probe-result.json
  ' structural-rootfs-e2e \
    "$model" "$request" "$external" "$source_artifact" "$mgt_source" "$mgt_request" \
    "$evidence_bundle" "$linear_model" "$linear_request" "$linear_external" \
    "$linear_source_artifact"

"$installer" runtime-receipt-verify \
  --receipt "$e2e_root/rootfs-isolation-receipt.json" \
  --bundle "$bundle" > "$e2e_root/runtime-receipt-validation.json"

receipt_stage="$(mktemp "$receipt_parent/.structural-rootfs-receipt.XXXXXX")"
cp "$e2e_root/rootfs-isolation-receipt.json" "$receipt_stage"
chmod 0444 "$receipt_stage"
if ! ln "$receipt_stage" "$receipt"; then
  rm -f -- "$receipt_stage"
  echo "receipt output appeared while publishing" >&2
  exit 1
fi
rm -f -- "$receipt_stage"
cat "$e2e_root/runtime-receipt-validation.json"
