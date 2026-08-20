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
mgt_linear_source="$repository_root/native/tests/fixtures/mgt_import/workbench_cantilever_frame3d_x.mgt"
mgt_linear_request="$repository_root/native/tests/fixtures/model_ir_linear/mgt_cantilever_request.json"
mgt_linear_external="$repository_root/native/tests/fixtures/model_ir_linear/mgt_cantilever_external_v1.json"
mgt_linear_source_artifact="$repository_root/native/tests/fixtures/model_ir_linear/mgt_cantilever_language_neutral_oracle_v1.txt"

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
    /opt/payload/bin/structural-workbench workflow-mgt-model-linear "${12}" "${13}" \
      --model-id workbench-mgt-linear-cantilever-v1 \
      --external-result "${14}" --source-artifact "${15}" \
      --workspace /mnt/mgt-model-ir-linear-workbench --step-budget 1 \
      > /mnt/mgt-model-ir-linear-workflow.json
    /opt/payload/bin/structural-workbench inspect \
      --workspace /mnt/mgt-model-ir-linear-workbench \
      > /mnt/mgt-model-ir-linear-inspect-before-review.json
    /opt/payload/bin/structural-workbench review \
      --workspace /mnt/mgt-model-ir-linear-workbench \
      --decision review --reviewer native-rootfs-c5 \
      --comment "Explicit isolated C5 handoff review; no engineering approval is inferred." \
      > /mnt/mgt-model-ir-linear-review-publish.json
    /opt/payload/bin/structural-workbench review-show \
      --workspace /mnt/mgt-model-ir-linear-workbench \
      > /mnt/mgt-model-ir-linear-review-show.json
    /opt/payload/bin/structural-workbench inspect \
      --workspace /mnt/mgt-model-ir-linear-workbench \
      > /mnt/mgt-model-ir-linear-inspect-after-review.json
    /opt/payload/bin/structural-workbench export \
      --workspace /mnt/mgt-model-ir-linear-workbench \
      > /mnt/mgt-model-ir-linear-export.json
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
    /bin/cp /mnt/model-ir-linear-workbench/workbench-session.json \
      /mnt/model-ir-linear-session-before-reaction-view.json
    /bin/cp /mnt/mgt-model-ir-linear-workbench/workbench-session.json \
      /mnt/mgt-model-ir-linear-session-before-reaction-view.json
    for profile in model-ir-linear mgt-model-ir-linear; do
      if [ "$profile" = model-ir-linear ]; then
        reaction_workspace=/mnt/model-ir-linear-workbench
      else
        reaction_workspace=/mnt/mgt-model-ir-linear-workbench
      fi
      for locale in en-US ko-KR; do
        for repeat in first second; do
          /opt/payload/bin/structural-workbench reaction-view \
            --workspace "$reaction_workspace" --locale "$locale" \
            > "/mnt/$profile-reaction-view-$locale-$repeat.txt"
        done
        /usr/bin/cmp "/mnt/$profile-reaction-view-$locale-first.txt" \
          "/mnt/$profile-reaction-view-$locale-second.txt"
      done
      if /usr/bin/cmp -s "/mnt/$profile-reaction-view-en-US-first.txt" \
        "/mnt/$profile-reaction-view-ko-KR-first.txt"; then
        exit 1
      fi
    done
    /opt/payload/bin/structural-workbench reaction-view \
      --workspace /mnt/model-ir-linear-workbench --locale en-US \
      --start-row 2 --count 2 > /mnt/model-ir-linear-reaction-view-window.txt
    if /opt/payload/bin/structural-workbench reaction-view \
      --workspace /mnt/modelir-workbench \
      > /mnt/reaction-view-wrong-profile-failure.json \
      2> /mnt/reaction-view-wrong-profile-stderr.txt; then
      exit 1
    fi
    test ! -s /mnt/reaction-view-wrong-profile-stderr.txt
    for profile in model-ir-linear mgt-model-ir-linear; do
      if [ "$profile" = model-ir-linear ]; then
        audit_workspace=/mnt/model-ir-linear-workbench
      else
        audit_workspace=/mnt/mgt-model-ir-linear-workbench
      fi
      for locale in en-US ko-KR; do
        for repeat in first second; do
          /opt/payload/bin/structural-workbench reaction-audit \
            --workspace "$audit_workspace" --locale "$locale" \
            > "/mnt/$profile-reaction-audit-$locale-$repeat.txt"
        done
        /usr/bin/cmp "/mnt/$profile-reaction-audit-$locale-first.txt" \
          "/mnt/$profile-reaction-audit-$locale-second.txt"
      done
      if /usr/bin/cmp -s "/mnt/$profile-reaction-audit-en-US-first.txt" \
        "/mnt/$profile-reaction-audit-ko-KR-first.txt"; then
        exit 1
      fi
    done
    if /opt/payload/bin/structural-workbench reaction-audit \
      --workspace /mnt/modelir-workbench \
      > /mnt/reaction-audit-wrong-profile-failure.json \
      2> /mnt/reaction-audit-wrong-profile-stderr.txt; then
      exit 1
    fi
    test ! -s /mnt/reaction-audit-wrong-profile-stderr.txt
    for profile in model-ir-linear mgt-model-ir-linear; do
      if [ "$profile" = model-ir-linear ]; then
        displacement_workspace=/mnt/model-ir-linear-workbench
      else
        displacement_workspace=/mnt/mgt-model-ir-linear-workbench
      fi
      for locale in en-US ko-KR; do
        for repeat in first second; do
          /opt/payload/bin/structural-workbench nodal-displacement-view \
            --workspace "$displacement_workspace" --locale "$locale" \
            > "/mnt/$profile-nodal-displacement-view-$locale-$repeat.txt"
        done
        /usr/bin/cmp "/mnt/$profile-nodal-displacement-view-$locale-first.txt" \
          "/mnt/$profile-nodal-displacement-view-$locale-second.txt"
      done
      if /usr/bin/cmp -s "/mnt/$profile-nodal-displacement-view-en-US-first.txt" \
        "/mnt/$profile-nodal-displacement-view-ko-KR-first.txt"; then
        exit 1
      fi
    done
    /opt/payload/bin/structural-workbench nodal-displacement-view \
      --workspace /mnt/model-ir-linear-workbench --locale en-US \
      --start-node 2 --count 1 \
      > /mnt/model-ir-linear-nodal-displacement-view-window.txt
    if /opt/payload/bin/structural-workbench nodal-displacement-view \
      --workspace /mnt/modelir-workbench \
      > /mnt/nodal-displacement-view-wrong-profile-failure.json \
      2> /mnt/nodal-displacement-view-wrong-profile-stderr.txt; then
      exit 1
    fi
    test ! -s /mnt/nodal-displacement-view-wrong-profile-stderr.txt
    for profile in model-ir-linear mgt-model-ir-linear; do
      if [ "$profile" = model-ir-linear ]; then
        deformed_workspace=/mnt/model-ir-linear-workbench
        deformed_projection=xy
      else
        deformed_workspace=/mnt/mgt-model-ir-linear-workbench
        deformed_projection=xz
      fi
      for locale in en-US ko-KR; do
        for repeat in first second; do
          /opt/payload/bin/structural-workbench result-deformed-view \
            --workspace "$deformed_workspace" --locale "$locale" \
            --projection "$deformed_projection" --scale 1000 \
            > "/mnt/$profile-deformed-view-$locale-$repeat.txt"
        done
        /usr/bin/cmp "/mnt/$profile-deformed-view-$locale-first.txt" \
          "/mnt/$profile-deformed-view-$locale-second.txt"
      done
      if /usr/bin/cmp -s "/mnt/$profile-deformed-view-en-US-first.txt" \
        "/mnt/$profile-deformed-view-ko-KR-first.txt"; then
        exit 1
      fi
    done
    /opt/payload/bin/structural-workbench result-deformed-view \
      --workspace /mnt/model-ir-linear-workbench --locale en-US \
      --projection xz --scale 1000 \
      > /mnt/model-ir-linear-deformed-view-projection.txt
    if /usr/bin/cmp -s /mnt/model-ir-linear-deformed-view-en-US-first.txt \
      /mnt/model-ir-linear-deformed-view-projection.txt; then
      exit 1
    fi
    if /opt/payload/bin/structural-workbench result-deformed-view \
      --workspace /mnt/model-ir-linear-workbench --step 2 \
      > /mnt/linear-deformed-view-invalid-step-failure.json \
      2> /mnt/linear-deformed-view-invalid-step-stderr.txt; then
      exit 1
    fi
    test ! -s /mnt/linear-deformed-view-invalid-step-stderr.txt
    for profile in model-ir-linear mgt-model-ir-linear; do
      if [ "$profile" = model-ir-linear ]; then
        element_workspace=/mnt/model-ir-linear-workbench
      else
        element_workspace=/mnt/mgt-model-ir-linear-workbench
      fi
      for locale in en-US ko-KR; do
        for repeat in first second; do
          /opt/payload/bin/structural-workbench element-recovery-view \
            --workspace "$element_workspace" --locale "$locale" \
            > "/mnt/$profile-element-recovery-view-$locale-$repeat.txt"
        done
        /usr/bin/cmp "/mnt/$profile-element-recovery-view-$locale-first.txt" \
          "/mnt/$profile-element-recovery-view-$locale-second.txt"
      done
      if /usr/bin/cmp -s "/mnt/$profile-element-recovery-view-en-US-first.txt" \
        "/mnt/$profile-element-recovery-view-ko-KR-first.txt"; then
        exit 1
      fi
    done
    if /usr/bin/cmp -s /mnt/model-ir-linear-element-recovery-view-en-US-first.txt \
      /mnt/mgt-model-ir-linear-element-recovery-view-en-US-first.txt; then
      exit 1
    fi
    if /opt/payload/bin/structural-workbench element-recovery-view \
      --workspace /mnt/model-ir-linear-workbench --start-element 2 \
      > /mnt/linear-element-recovery-view-invalid-window-failure.json \
      2> /mnt/linear-element-recovery-view-invalid-window-stderr.txt; then
      exit 1
    fi
    test ! -s /mnt/linear-element-recovery-view-invalid-window-stderr.txt
    /opt/payload/bin/structural-workbench model-create-modal-analysis-request "$8" \
      --case rootfs-frame-modal-c5 --assembly-load-pattern LC_WEAK \
      --mode-count 3 --maximum-sweeps 4096 \
      --symmetry-relative-tolerance 1e-12 \
      --positive-semidefinite-relative-tolerance 1e-12 \
      --mode-relative-tolerance 1e-10 --cluster-relative-tolerance 1e-9 \
      --residual-relative-tolerance 1e-9 --orthogonality-tolerance 1e-9 \
      --eigensolver-relative-tolerance 1e-12 \
      --output-dir /mnt/model-modal-request \
      > /mnt/model-modal-request.stdout.json
    /opt/payload/bin/structural-cli analysis model-modal-run "$8" \
      /mnt/model-modal-request/analysis-request.json \
      --output-dir /mnt/model-modal-direct \
      > /mnt/model-modal-direct.stdout.json
    /opt/payload/bin/structural-cli analysis model-modal-resume "$8" \
      /mnt/model-modal-request/analysis-request.json \
      /mnt/model-modal-direct/checkpoint.mmcp \
      --output-dir /mnt/model-modal-resumed \
      > /mnt/model-modal-resumed.stdout.json
    /usr/bin/diff -r /mnt/model-modal-direct /mnt/model-modal-resumed
    /usr/bin/cmp /mnt/model-modal-direct.stdout.json /mnt/model-modal-resumed.stdout.json
    /bin/cp -a /mnt/model-modal-direct /mnt/model-modal-view-source-before
    for locale in en-US ko-KR; do
      for repeat in first second; do
        /opt/payload/bin/structural-workbench modal-result-view \
          /mnt/model-modal-direct --locale "$locale" --count 16 \
          > "/mnt/model-modal-result-view-$locale-$repeat.txt"
      done
      /usr/bin/cmp "/mnt/model-modal-result-view-$locale-first.txt" \
        "/mnt/model-modal-result-view-$locale-second.txt"
    done
    if /usr/bin/cmp -s /mnt/model-modal-result-view-en-US-first.txt \
      /mnt/model-modal-result-view-ko-KR-first.txt; then
      exit 1
    fi
    if /opt/payload/bin/structural-workbench modal-result-view \
      /mnt/model-modal-direct --start-mode 4 --count 1 \
      > /mnt/model-modal-result-view-invalid-window-failure.json \
      2> /mnt/model-modal-result-view-invalid-window-stderr.txt; then
      exit 1
    fi
    test ! -s /mnt/model-modal-result-view-invalid-window-stderr.txt
    /usr/bin/diff -r /mnt/model-modal-view-source-before /mnt/model-modal-direct
    /opt/payload/bin/structural-workbench import-model-modal "$8" \
      /mnt/model-modal-request/analysis-request.json \
      --workspace /mnt/model-modal-workbench-restarted \
      > /mnt/model-modal-workbench-import.stdout.json
    /opt/payload/bin/structural-workbench modal-validate \
      --workspace /mnt/model-modal-workbench-restarted \
      > /mnt/model-modal-workbench-validate.stdout.json
    /bin/cp /mnt/model-modal-workbench-restarted/workbench-session.json \
      /mnt/model-modal-workbench-validated-session.json
    /opt/payload/bin/structural-workbench modal-run \
      --workspace /mnt/model-modal-workbench-restarted \
      > /mnt/model-modal-workbench-run.stdout.json
    /bin/cp /mnt/model-modal-workbench-validated-session.json \
      /mnt/model-modal-workbench-restarted/workbench-session.json
    /opt/payload/bin/structural-workbench modal-status \
      --workspace /mnt/model-modal-workbench-restarted \
      > /mnt/model-modal-workbench-reconciled.stdout.json
    /opt/payload/bin/structural-workbench modal-resume \
      --workspace /mnt/model-modal-workbench-restarted \
      > /mnt/model-modal-workbench-resume.stdout.json
    /opt/payload/bin/structural-workbench modal-report \
      --workspace /mnt/model-modal-workbench-restarted \
      > /mnt/model-modal-workbench-report.stdout.json
    /opt/payload/bin/structural-workbench modal-inspect \
      --workspace /mnt/model-modal-workbench-restarted \
      > /mnt/model-modal-workbench-inspect-first.json
    /opt/payload/bin/structural-workbench modal-inspect \
      --workspace /mnt/model-modal-workbench-restarted \
      > /mnt/model-modal-workbench-inspect-second.json
    /usr/bin/cmp /mnt/model-modal-workbench-inspect-first.json \
      /mnt/model-modal-workbench-inspect-second.json
    /opt/payload/bin/structural-workbench workflow-model-modal "$8" \
      /mnt/model-modal-request/analysis-request.json \
      --workspace /mnt/model-modal-workbench-direct \
      > /mnt/model-modal-workbench-direct.stdout.json
    /usr/bin/diff -r /mnt/model-modal-workbench-restarted \
      /mnt/model-modal-workbench-direct
    /usr/bin/diff -r /mnt/model-modal-workbench-direct/03-run \
      /mnt/model-modal-workbench-direct/04-resume
    /usr/bin/diff -r /mnt/model-modal-direct \
      /mnt/model-modal-workbench-direct/04-resume
    test ! -e /mnt/model-modal-workbench-direct/05-compare
    /bin/cp -a /mnt/model-modal-workbench-direct /mnt/model-modal-workbench-tampered
    printf X | /bin/dd of=/mnt/model-modal-workbench-tampered/03-run/checkpoint.mmcp \
      bs=1 seek=0 count=1 conv=notrunc status=none
    if /opt/payload/bin/structural-workbench modal-status \
      --workspace /mnt/model-modal-workbench-tampered \
      > /mnt/model-modal-workbench-tamper-failure.json \
      2> /mnt/model-modal-workbench-tamper-stderr.txt; then
      exit 1
    fi
    test ! -s /mnt/model-modal-workbench-tamper-stderr.txt
    /usr/bin/sed \
      -e "s/engine-v2-frame-cantilever/engine-v2-frame-cantilever-rigid-offset/" \
      -e "s/\"i_global_m\": \[0.0, 0.0, 0.0\]/\"i_global_m\": [0.1, 0.0, 0.0]/" \
      -e "s/\"j_global_m\": \[0.0, 0.0, 0.0\]/\"j_global_m\": [-0.1, 0.0, 0.0]/" \
      "$8" > /mnt/frame3d-rigid-offset-model-ir.json
    /opt/payload/bin/structural-workbench model-create-linear-analysis-request \
      /mnt/frame3d-rigid-offset-model-ir.json \
      --case model-frame-rigid-offset-linear-c5 --load-pattern LC_WEAK \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir /mnt/frame3d-rigid-offset-request \
      > /mnt/frame3d-rigid-offset-request.stdout.json
    /opt/payload/bin/structural-cli analysis model-linear-run \
      /mnt/frame3d-rigid-offset-model-ir.json \
      /mnt/frame3d-rigid-offset-request/analysis-request.json \
      --output-dir /mnt/frame3d-rigid-offset-direct \
      > /mnt/frame3d-rigid-offset-direct.stdout.json
    /opt/payload/bin/structural-cli analysis model-linear-run \
      /mnt/frame3d-rigid-offset-model-ir.json \
      /mnt/frame3d-rigid-offset-request/analysis-request.json \
      --output-dir /mnt/frame3d-rigid-offset-partial --iteration-budget 1 \
      > /mnt/frame3d-rigid-offset-partial.stdout.json
    /opt/payload/bin/structural-cli analysis model-linear-resume \
      /mnt/frame3d-rigid-offset-model-ir.json \
      /mnt/frame3d-rigid-offset-request/analysis-request.json \
      /mnt/frame3d-rigid-offset-partial/checkpoint.mlpcp \
      --output-dir /mnt/frame3d-rigid-offset-resumed \
      > /mnt/frame3d-rigid-offset-resumed.stdout.json
    /usr/bin/diff -r /mnt/frame3d-rigid-offset-direct \
      /mnt/frame3d-rigid-offset-resumed
    /usr/bin/sed \
      -e "s/engine-v2-frame-cantilever/engine-v2-frame-cantilever-end-release/" \
      -e "s/\"i_global_m\": \[0.0, 0.0, 0.0\]/\"i_global_m\": [0.1, 0.0, 0.0]/" \
      -e "s/\"j_global_m\": \[0.0, 0.0, 0.0\]/\"j_global_m\": [-0.1, 0.0, 0.0]/" \
      -e "s/\"i\": \[\]/\"i\": [\"RY\"]/" \
      -e "/\"source_id\": \"generated:BC1\"/,/^    }$/ { /^    }$/c\\
    },\\
    {\\
      \"id\": \"BC2\",\\
      \"index\": 1,\\
      \"type\": \"fixed_dofs\",\\
      \"node_id\": \"N2\",\\
      \"dofs\": [\"UZ\"],\\
      \"prescribed_values_si\": {\"UZ\": 0.0},\\
      \"source_id\": \"generated:BC2\",\\
      \"extensions\": {}\\
    }
  }" \
      "$8" > /mnt/frame3d-end-release-model-ir.json
    /opt/payload/bin/structural-workbench model-create-linear-analysis-request \
      /mnt/frame3d-end-release-model-ir.json \
      --case model-frame-end-release-linear-c5 --load-pattern LC_WEAK \
      --max-iterations 100 --absolute-residual-tolerance 1e-11 \
      --relative-residual-tolerance 1e-13 --maximum-increment 0 \
      --output-dir /mnt/frame3d-end-release-request \
      > /mnt/frame3d-end-release-request.stdout.json
    /opt/payload/bin/structural-cli analysis model-linear-run \
      /mnt/frame3d-end-release-model-ir.json \
      /mnt/frame3d-end-release-request/analysis-request.json \
      --output-dir /mnt/frame3d-end-release-direct \
      > /mnt/frame3d-end-release-direct.stdout.json
    /opt/payload/bin/structural-cli analysis model-linear-run \
      /mnt/frame3d-end-release-model-ir.json \
      /mnt/frame3d-end-release-request/analysis-request.json \
      --output-dir /mnt/frame3d-end-release-partial --iteration-budget 1 \
      > /mnt/frame3d-end-release-partial.stdout.json
    /opt/payload/bin/structural-cli analysis model-linear-resume \
      /mnt/frame3d-end-release-model-ir.json \
      /mnt/frame3d-end-release-request/analysis-request.json \
      /mnt/frame3d-end-release-partial/checkpoint.mlpcp \
      --output-dir /mnt/frame3d-end-release-resumed \
      > /mnt/frame3d-end-release-resumed.stdout.json
    /usr/bin/diff -r /mnt/frame3d-end-release-direct \
      /mnt/frame3d-end-release-resumed
    /usr/bin/cmp /mnt/model-ir-linear-session-before-reaction-view.json \
      /mnt/model-ir-linear-workbench/workbench-session.json
    /usr/bin/cmp /mnt/mgt-model-ir-linear-session-before-reaction-view.json \
      /mnt/mgt-model-ir-linear-workbench/workbench-session.json
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
      --mgt-model-ir-linear-workbench-root /mnt/mgt-model-ir-linear-workbench \
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
      --mgt-model-ir-linear-workbench-inspect-before-review \
        /mnt/mgt-model-ir-linear-inspect-before-review.json \
      --mgt-model-ir-linear-workbench-review-show \
        /mnt/mgt-model-ir-linear-review-show.json \
      --mgt-model-ir-linear-workbench-inspect-after-review \
        /mnt/mgt-model-ir-linear-inspect-after-review.json \
      --mgt-model-ir-linear-workbench-export /mnt/mgt-model-ir-linear-export.json \
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
      --model-ir-linear-workbench-session-before-reaction-view \
        /mnt/model-ir-linear-session-before-reaction-view.json \
      --mgt-model-ir-linear-workbench-session-before-reaction-view \
        /mnt/mgt-model-ir-linear-session-before-reaction-view.json \
      --model-ir-linear-reaction-view-en-us-first \
        /mnt/model-ir-linear-reaction-view-en-US-first.txt \
      --model-ir-linear-reaction-view-en-us-second \
        /mnt/model-ir-linear-reaction-view-en-US-second.txt \
      --model-ir-linear-reaction-view-ko-kr-first \
        /mnt/model-ir-linear-reaction-view-ko-KR-first.txt \
      --model-ir-linear-reaction-view-ko-kr-second \
        /mnt/model-ir-linear-reaction-view-ko-KR-second.txt \
      --model-ir-linear-reaction-view-window \
        /mnt/model-ir-linear-reaction-view-window.txt \
      --mgt-model-ir-linear-reaction-view-en-us-first \
        /mnt/mgt-model-ir-linear-reaction-view-en-US-first.txt \
      --mgt-model-ir-linear-reaction-view-en-us-second \
        /mnt/mgt-model-ir-linear-reaction-view-en-US-second.txt \
      --mgt-model-ir-linear-reaction-view-ko-kr-first \
        /mnt/mgt-model-ir-linear-reaction-view-ko-KR-first.txt \
      --mgt-model-ir-linear-reaction-view-ko-kr-second \
        /mnt/mgt-model-ir-linear-reaction-view-ko-KR-second.txt \
      --workbench-reaction-view-wrong-profile-failure \
        /mnt/reaction-view-wrong-profile-failure.json \
      --model-ir-linear-reaction-audit-en-us-first \
        /mnt/model-ir-linear-reaction-audit-en-US-first.txt \
      --model-ir-linear-reaction-audit-en-us-second \
        /mnt/model-ir-linear-reaction-audit-en-US-second.txt \
      --model-ir-linear-reaction-audit-ko-kr-first \
        /mnt/model-ir-linear-reaction-audit-ko-KR-first.txt \
      --model-ir-linear-reaction-audit-ko-kr-second \
        /mnt/model-ir-linear-reaction-audit-ko-KR-second.txt \
      --mgt-model-ir-linear-reaction-audit-en-us-first \
        /mnt/mgt-model-ir-linear-reaction-audit-en-US-first.txt \
      --mgt-model-ir-linear-reaction-audit-en-us-second \
        /mnt/mgt-model-ir-linear-reaction-audit-en-US-second.txt \
      --mgt-model-ir-linear-reaction-audit-ko-kr-first \
        /mnt/mgt-model-ir-linear-reaction-audit-ko-KR-first.txt \
      --mgt-model-ir-linear-reaction-audit-ko-kr-second \
        /mnt/mgt-model-ir-linear-reaction-audit-ko-KR-second.txt \
      --workbench-reaction-audit-wrong-profile-failure \
        /mnt/reaction-audit-wrong-profile-failure.json \
      --model-ir-linear-nodal-displacement-view-en-us-first \
        /mnt/model-ir-linear-nodal-displacement-view-en-US-first.txt \
      --model-ir-linear-nodal-displacement-view-en-us-second \
        /mnt/model-ir-linear-nodal-displacement-view-en-US-second.txt \
      --model-ir-linear-nodal-displacement-view-ko-kr-first \
        /mnt/model-ir-linear-nodal-displacement-view-ko-KR-first.txt \
      --model-ir-linear-nodal-displacement-view-ko-kr-second \
        /mnt/model-ir-linear-nodal-displacement-view-ko-KR-second.txt \
      --model-ir-linear-nodal-displacement-view-window \
        /mnt/model-ir-linear-nodal-displacement-view-window.txt \
      --mgt-model-ir-linear-nodal-displacement-view-en-us-first \
        /mnt/mgt-model-ir-linear-nodal-displacement-view-en-US-first.txt \
      --mgt-model-ir-linear-nodal-displacement-view-en-us-second \
        /mnt/mgt-model-ir-linear-nodal-displacement-view-en-US-second.txt \
      --mgt-model-ir-linear-nodal-displacement-view-ko-kr-first \
        /mnt/mgt-model-ir-linear-nodal-displacement-view-ko-KR-first.txt \
      --mgt-model-ir-linear-nodal-displacement-view-ko-kr-second \
        /mnt/mgt-model-ir-linear-nodal-displacement-view-ko-KR-second.txt \
      --workbench-nodal-displacement-view-wrong-profile-failure \
        /mnt/nodal-displacement-view-wrong-profile-failure.json \
      --model-ir-linear-deformed-view-en-us-first \
        /mnt/model-ir-linear-deformed-view-en-US-first.txt \
      --model-ir-linear-deformed-view-en-us-second \
        /mnt/model-ir-linear-deformed-view-en-US-second.txt \
      --model-ir-linear-deformed-view-ko-kr-first \
        /mnt/model-ir-linear-deformed-view-ko-KR-first.txt \
      --model-ir-linear-deformed-view-ko-kr-second \
        /mnt/model-ir-linear-deformed-view-ko-KR-second.txt \
      --model-ir-linear-deformed-view-projection \
        /mnt/model-ir-linear-deformed-view-projection.txt \
      --mgt-model-ir-linear-deformed-view-en-us-first \
        /mnt/mgt-model-ir-linear-deformed-view-en-US-first.txt \
      --mgt-model-ir-linear-deformed-view-en-us-second \
        /mnt/mgt-model-ir-linear-deformed-view-en-US-second.txt \
      --mgt-model-ir-linear-deformed-view-ko-kr-first \
        /mnt/mgt-model-ir-linear-deformed-view-ko-KR-first.txt \
      --mgt-model-ir-linear-deformed-view-ko-kr-second \
        /mnt/mgt-model-ir-linear-deformed-view-ko-KR-second.txt \
      --workbench-linear-deformed-view-invalid-step-failure \
        /mnt/linear-deformed-view-invalid-step-failure.json \
      --model-ir-linear-element-recovery-view-en-us-first \
        /mnt/model-ir-linear-element-recovery-view-en-US-first.txt \
      --model-ir-linear-element-recovery-view-en-us-second \
        /mnt/model-ir-linear-element-recovery-view-en-US-second.txt \
      --model-ir-linear-element-recovery-view-ko-kr-first \
        /mnt/model-ir-linear-element-recovery-view-ko-KR-first.txt \
      --model-ir-linear-element-recovery-view-ko-kr-second \
        /mnt/model-ir-linear-element-recovery-view-ko-KR-second.txt \
      --mgt-model-ir-linear-element-recovery-view-en-us-first \
        /mnt/mgt-model-ir-linear-element-recovery-view-en-US-first.txt \
      --mgt-model-ir-linear-element-recovery-view-en-us-second \
        /mnt/mgt-model-ir-linear-element-recovery-view-en-US-second.txt \
      --mgt-model-ir-linear-element-recovery-view-ko-kr-first \
        /mnt/mgt-model-ir-linear-element-recovery-view-ko-KR-first.txt \
      --mgt-model-ir-linear-element-recovery-view-ko-kr-second \
        /mnt/mgt-model-ir-linear-element-recovery-view-ko-KR-second.txt \
      --workbench-linear-element-recovery-view-invalid-window-failure \
        /mnt/linear-element-recovery-view-invalid-window-failure.json \
      --model-modal-request-root /mnt/model-modal-request \
      --model-modal-direct-root /mnt/model-modal-direct \
      --model-modal-resumed-root /mnt/model-modal-resumed \
      --model-modal-view-source-before /mnt/model-modal-view-source-before \
      --model-modal-direct-stdout /mnt/model-modal-direct.stdout.json \
      --model-modal-resumed-stdout /mnt/model-modal-resumed.stdout.json \
      --model-modal-result-view-en-us-first \
        /mnt/model-modal-result-view-en-US-first.txt \
      --model-modal-result-view-en-us-second \
        /mnt/model-modal-result-view-en-US-second.txt \
      --model-modal-result-view-ko-kr-first \
        /mnt/model-modal-result-view-ko-KR-first.txt \
      --model-modal-result-view-ko-kr-second \
        /mnt/model-modal-result-view-ko-KR-second.txt \
      --model-modal-result-view-invalid-window-failure \
        /mnt/model-modal-result-view-invalid-window-failure.json \
      --model-modal-workbench-restarted-root \
        /mnt/model-modal-workbench-restarted \
      --model-modal-workbench-direct-root /mnt/model-modal-workbench-direct \
      --model-modal-workbench-reconciled-stdout \
        /mnt/model-modal-workbench-reconciled.stdout.json \
      --model-modal-workbench-inspect-first \
        /mnt/model-modal-workbench-inspect-first.json \
      --model-modal-workbench-inspect-second \
        /mnt/model-modal-workbench-inspect-second.json \
      --model-modal-workbench-tamper-failure \
        /mnt/model-modal-workbench-tamper-failure.json \
      --frame3d-rigid-offset-model /mnt/frame3d-rigid-offset-model-ir.json \
      --frame3d-rigid-offset-request-root /mnt/frame3d-rigid-offset-request \
      --frame3d-rigid-offset-direct-root /mnt/frame3d-rigid-offset-direct \
      --frame3d-rigid-offset-partial-root /mnt/frame3d-rigid-offset-partial \
      --frame3d-rigid-offset-resumed-root /mnt/frame3d-rigid-offset-resumed \
      --frame3d-end-release-model /mnt/frame3d-end-release-model-ir.json \
      --frame3d-end-release-request-root /mnt/frame3d-end-release-request \
      --frame3d-end-release-direct-root /mnt/frame3d-end-release-direct \
      --frame3d-end-release-partial-root /mnt/frame3d-end-release-partial \
      --frame3d-end-release-resumed-root /mnt/frame3d-end-release-resumed \
      --workbench-catalog /mnt/workbench-catalog.json \
      --workbench-evidence /mnt/workbench-evidence.json \
      --receipt /mnt/rootfs-isolation-receipt.json \
      > /mnt/runtime-probe-result.json
  ' structural-rootfs-e2e \
    "$model" "$request" "$external" "$source_artifact" "$mgt_source" "$mgt_request" \
    "$evidence_bundle" "$linear_model" "$linear_request" "$linear_external" \
    "$linear_source_artifact" "$mgt_linear_source" "$mgt_linear_request" \
    "$mgt_linear_external" "$mgt_linear_source_artifact"

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
