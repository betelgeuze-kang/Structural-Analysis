use std::collections::BTreeMap;
use std::ffi::OsString;
use std::path::PathBuf;
use std::process::ExitCode;

use serde::Serialize;
use structural_distribution::{
    active_payload_path, create_bundle, create_rootfs_isolation_receipt, install_bundle,
    installation_status, recover_install, rollback_install, verify_bundle,
    verify_rootfs_isolation_receipt, BackendProfileV1, BundleCreateRequest, DistributionError,
    LinkageV1, RootfsIsolationProbeRequest,
};

const EXIT_FAILURE: u8 = 1;
const EXIT_USAGE: u8 = 2;

fn main() -> ExitCode {
    let arguments = std::env::args_os().skip(1).collect::<Vec<_>>();
    match run(&arguments) {
        Ok(value) => match serde_json::to_string(&value) {
            Ok(json) => {
                println!("{json}");
                ExitCode::SUCCESS
            }
            Err(error) => {
                eprintln!("distribution_json_encode_failed: {error}");
                ExitCode::from(EXIT_FAILURE)
            }
        },
        Err(CliError::Usage(detail)) => {
            eprintln!("{detail}\n{}", usage());
            ExitCode::from(EXIT_USAGE)
        }
        Err(CliError::Distribution(error)) => {
            eprintln!("{}: {}", error.code, error.detail);
            ExitCode::from(EXIT_FAILURE)
        }
    }
}

#[derive(Debug)]
enum CliError {
    Usage(String),
    Distribution(DistributionError),
}

impl From<DistributionError> for CliError {
    fn from(value: DistributionError) -> Self {
        Self::Distribution(value)
    }
}

#[derive(Serialize)]
struct CommandResult<T: Serialize> {
    schema_version: &'static str,
    action: &'static str,
    result: T,
}

fn run(arguments: &[OsString]) -> Result<serde_json::Value, CliError> {
    if arguments.len() == 1 && arguments[0] == "--version" {
        return Ok(serde_json::json!({
            "schema_version": "structural-installer-version.v1",
            "version": env!("CARGO_PKG_VERSION")
        }));
    }
    let command = arguments
        .first()
        .and_then(|value| value.to_str())
        .ok_or_else(|| usage_error("missing or non-UTF-8 command"))?;
    let options = parse_options(&arguments[1..])?;
    let value = match command {
        "bundle-create" => {
            require_exact_options(
                &options,
                &[
                    "--payload",
                    "--output",
                    "--release-id",
                    "--package-version",
                    "--backend",
                    "--linkage",
                    "--source-sha256",
                ],
            )?;
            let payload = required_path(&options, "--payload")?;
            let output = required_path(&options, "--output")?;
            let release_id = required(&options, "--release-id")?;
            let package_version = required(&options, "--package-version")?;
            let backend = parse_backend(required(&options, "--backend")?)?;
            let linkage = parse_linkage(required(&options, "--linkage")?)?;
            let source_sha256 = required(&options, "--source-sha256")?;
            let manifest = create_bundle(&BundleCreateRequest {
                payload_root: &payload,
                output: &output,
                release_id,
                package_version,
                backend_profile: backend,
                linkage,
                source_sha256,
            })?;
            json_result("bundle_create", manifest)?
        }
        "bundle-verify" => {
            require_exact_options(&options, &["--bundle"])?;
            let manifest = verify_bundle(&required_path(&options, "--bundle")?)?;
            json_result("bundle_verify", manifest)?
        }
        "runtime-probe" => run_runtime_probe(&options)?,
        "runtime-receipt-verify" => run_runtime_receipt_verify(&options)?,
        "install" | "update" => {
            require_exact_options(&options, &["--bundle", "--root"])?;
            let state = install_bundle(
                &required_path(&options, "--bundle")?,
                &required_path(&options, "--root")?,
            )?;
            json_result(
                if command == "install" {
                    "install"
                } else {
                    "update"
                },
                state,
            )?
        }
        "rollback" => {
            require_exact_options(&options, &["--root"])?;
            let state = rollback_install(&required_path(&options, "--root")?)?;
            json_result("rollback", state)?
        }
        "recover" => {
            require_exact_options(&options, &["--root"])?;
            let state = recover_install(&required_path(&options, "--root")?)?;
            json_result("recover", state)?
        }
        "status" => {
            require_exact_options(&options, &["--root"])?;
            let root = required_path(&options, "--root")?;
            let state = installation_status(&root)?;
            let payload = active_payload_path(&root)?;
            json_result(
                "status",
                serde_json::json!({"activation": state, "payload": payload}),
            )?
        }
        _ => return Err(usage_error("unknown command")),
    };
    Ok(value)
}

#[allow(clippy::too_many_lines)]
fn run_runtime_probe(options: &BTreeMap<String, String>) -> Result<serde_json::Value, CliError> {
    require_exact_options(
        options,
        &[
            "--bundle",
            "--payload-root",
            "--workspace",
            "--workbench-root",
            "--mgt-workbench-root",
            "--model-ir-linear-workbench-root",
            "--mgt-model-ir-linear-workbench-root",
            "--workbench-inspect-before-review",
            "--workbench-review-show",
            "--workbench-inspect-after-review",
            "--workbench-export",
            "--mgt-workbench-inspect-before-review",
            "--mgt-workbench-review-show",
            "--mgt-workbench-inspect-after-review",
            "--mgt-workbench-export",
            "--model-ir-linear-workbench-inspect-before-review",
            "--model-ir-linear-workbench-review-show",
            "--model-ir-linear-workbench-inspect-after-review",
            "--model-ir-linear-workbench-export",
            "--mgt-model-ir-linear-workbench-inspect-before-review",
            "--mgt-model-ir-linear-workbench-review-show",
            "--mgt-model-ir-linear-workbench-inspect-after-review",
            "--mgt-model-ir-linear-workbench-export",
            "--model-ir-linear-workbench-session-before-localized-pdf",
            "--model-ir-linear-localized-pdf-en-us-first-root",
            "--model-ir-linear-localized-pdf-en-us-second-root",
            "--model-ir-linear-localized-pdf-ko-kr-first-root",
            "--model-ir-linear-localized-pdf-ko-kr-second-root",
            "--model-ir-linear-workbench-session-before-reaction-view",
            "--mgt-model-ir-linear-workbench-session-before-reaction-view",
            "--model-ir-linear-reaction-view-en-us-first",
            "--model-ir-linear-reaction-view-en-us-second",
            "--model-ir-linear-reaction-view-ko-kr-first",
            "--model-ir-linear-reaction-view-ko-kr-second",
            "--model-ir-linear-reaction-view-window",
            "--mgt-model-ir-linear-reaction-view-en-us-first",
            "--mgt-model-ir-linear-reaction-view-en-us-second",
            "--mgt-model-ir-linear-reaction-view-ko-kr-first",
            "--mgt-model-ir-linear-reaction-view-ko-kr-second",
            "--workbench-reaction-view-wrong-profile-failure",
            "--model-ir-linear-reaction-audit-en-us-first",
            "--model-ir-linear-reaction-audit-en-us-second",
            "--model-ir-linear-reaction-audit-ko-kr-first",
            "--model-ir-linear-reaction-audit-ko-kr-second",
            "--mgt-model-ir-linear-reaction-audit-en-us-first",
            "--mgt-model-ir-linear-reaction-audit-en-us-second",
            "--mgt-model-ir-linear-reaction-audit-ko-kr-first",
            "--mgt-model-ir-linear-reaction-audit-ko-kr-second",
            "--workbench-reaction-audit-wrong-profile-failure",
            "--model-ir-linear-nodal-displacement-view-en-us-first",
            "--model-ir-linear-nodal-displacement-view-en-us-second",
            "--model-ir-linear-nodal-displacement-view-ko-kr-first",
            "--model-ir-linear-nodal-displacement-view-ko-kr-second",
            "--model-ir-linear-nodal-displacement-view-window",
            "--mgt-model-ir-linear-nodal-displacement-view-en-us-first",
            "--mgt-model-ir-linear-nodal-displacement-view-en-us-second",
            "--mgt-model-ir-linear-nodal-displacement-view-ko-kr-first",
            "--mgt-model-ir-linear-nodal-displacement-view-ko-kr-second",
            "--workbench-nodal-displacement-view-wrong-profile-failure",
            "--model-ir-linear-deformed-view-en-us-first",
            "--model-ir-linear-deformed-view-en-us-second",
            "--model-ir-linear-deformed-view-ko-kr-first",
            "--model-ir-linear-deformed-view-ko-kr-second",
            "--model-ir-linear-deformed-view-projection",
            "--mgt-model-ir-linear-deformed-view-en-us-first",
            "--mgt-model-ir-linear-deformed-view-en-us-second",
            "--mgt-model-ir-linear-deformed-view-ko-kr-first",
            "--mgt-model-ir-linear-deformed-view-ko-kr-second",
            "--workbench-linear-deformed-view-invalid-step-failure",
            "--model-ir-linear-element-recovery-view-en-us-first",
            "--model-ir-linear-element-recovery-view-en-us-second",
            "--model-ir-linear-element-recovery-view-ko-kr-first",
            "--model-ir-linear-element-recovery-view-ko-kr-second",
            "--mgt-model-ir-linear-element-recovery-view-en-us-first",
            "--mgt-model-ir-linear-element-recovery-view-en-us-second",
            "--mgt-model-ir-linear-element-recovery-view-ko-kr-first",
            "--mgt-model-ir-linear-element-recovery-view-ko-kr-second",
            "--workbench-linear-element-recovery-view-invalid-window-failure",
            "--model-modal-request-root",
            "--model-modal-direct-root",
            "--model-modal-resumed-root",
            "--model-modal-view-source-before",
            "--model-modal-direct-stdout",
            "--model-modal-resumed-stdout",
            "--model-modal-result-view-en-us-first",
            "--model-modal-result-view-en-us-second",
            "--model-modal-result-view-ko-kr-first",
            "--model-modal-result-view-ko-kr-second",
            "--model-modal-result-view-invalid-window-failure",
            "--model-modal-workbench-restarted-root",
            "--model-modal-workbench-direct-root",
            "--model-modal-workbench-reconciled-stdout",
            "--model-modal-workbench-inspect-first",
            "--model-modal-workbench-inspect-second",
            "--model-modal-workbench-tamper-failure",
            "--frame3d-rigid-offset-model",
            "--frame3d-rigid-offset-request-root",
            "--frame3d-rigid-offset-direct-root",
            "--frame3d-rigid-offset-partial-root",
            "--frame3d-rigid-offset-resumed-root",
            "--frame3d-end-release-model",
            "--frame3d-end-release-request-root",
            "--frame3d-end-release-direct-root",
            "--frame3d-end-release-partial-root",
            "--frame3d-end-release-resumed-root",
            "--frame3d-self-weight-model",
            "--frame3d-self-weight-request-root",
            "--frame3d-self-weight-direct-root",
            "--frame3d-self-weight-partial-root",
            "--frame3d-self-weight-resumed-root",
            "--frame3d-member-distributed-load-model",
            "--frame3d-member-distributed-load-request-root",
            "--frame3d-member-distributed-load-direct-root",
            "--frame3d-member-distributed-load-partial-root",
            "--frame3d-member-distributed-load-resumed-root",
            "--workbench-catalog",
            "--workbench-evidence",
            "--receipt",
        ],
    )?;
    let bundle = required_path(options, "--bundle")?;
    let payload_root = required_path(options, "--payload-root")?;
    let workspace = required_path(options, "--workspace")?;
    let workbench_root = required_path(options, "--workbench-root")?;
    let mgt_workbench_root = required_path(options, "--mgt-workbench-root")?;
    let model_ir_linear_workbench_root =
        required_path(options, "--model-ir-linear-workbench-root")?;
    let mgt_model_ir_linear_workbench_root =
        required_path(options, "--mgt-model-ir-linear-workbench-root")?;
    let workbench_inspect_before_review =
        required_path(options, "--workbench-inspect-before-review")?;
    let workbench_review_show = required_path(options, "--workbench-review-show")?;
    let workbench_inspect_after_review =
        required_path(options, "--workbench-inspect-after-review")?;
    let workbench_export = required_path(options, "--workbench-export")?;
    let mgt_workbench_inspect_before_review =
        required_path(options, "--mgt-workbench-inspect-before-review")?;
    let mgt_workbench_review_show = required_path(options, "--mgt-workbench-review-show")?;
    let mgt_workbench_inspect_after_review =
        required_path(options, "--mgt-workbench-inspect-after-review")?;
    let mgt_workbench_export = required_path(options, "--mgt-workbench-export")?;
    let model_ir_linear_workbench_inspect_before_review =
        required_path(options, "--model-ir-linear-workbench-inspect-before-review")?;
    let model_ir_linear_workbench_review_show =
        required_path(options, "--model-ir-linear-workbench-review-show")?;
    let model_ir_linear_workbench_inspect_after_review =
        required_path(options, "--model-ir-linear-workbench-inspect-after-review")?;
    let model_ir_linear_workbench_export =
        required_path(options, "--model-ir-linear-workbench-export")?;
    let mgt_model_ir_linear_workbench_inspect_before_review = required_path(
        options,
        "--mgt-model-ir-linear-workbench-inspect-before-review",
    )?;
    let mgt_model_ir_linear_workbench_review_show =
        required_path(options, "--mgt-model-ir-linear-workbench-review-show")?;
    let mgt_model_ir_linear_workbench_inspect_after_review = required_path(
        options,
        "--mgt-model-ir-linear-workbench-inspect-after-review",
    )?;
    let mgt_model_ir_linear_workbench_export =
        required_path(options, "--mgt-model-ir-linear-workbench-export")?;
    let model_ir_linear_workbench_session_before_localized_pdf = required_path(
        options,
        "--model-ir-linear-workbench-session-before-localized-pdf",
    )?;
    let model_ir_linear_localized_pdf_en_us_first_root =
        required_path(options, "--model-ir-linear-localized-pdf-en-us-first-root")?;
    let model_ir_linear_localized_pdf_en_us_second_root =
        required_path(options, "--model-ir-linear-localized-pdf-en-us-second-root")?;
    let model_ir_linear_localized_pdf_ko_kr_first_root =
        required_path(options, "--model-ir-linear-localized-pdf-ko-kr-first-root")?;
    let model_ir_linear_localized_pdf_ko_kr_second_root =
        required_path(options, "--model-ir-linear-localized-pdf-ko-kr-second-root")?;
    let model_ir_linear_workbench_session_before_reaction_view = required_path(
        options,
        "--model-ir-linear-workbench-session-before-reaction-view",
    )?;
    let mgt_model_ir_linear_workbench_session_before_reaction_view = required_path(
        options,
        "--mgt-model-ir-linear-workbench-session-before-reaction-view",
    )?;
    let model_ir_linear_reaction_view_en_us_first =
        required_path(options, "--model-ir-linear-reaction-view-en-us-first")?;
    let model_ir_linear_reaction_view_en_us_second =
        required_path(options, "--model-ir-linear-reaction-view-en-us-second")?;
    let model_ir_linear_reaction_view_ko_kr_first =
        required_path(options, "--model-ir-linear-reaction-view-ko-kr-first")?;
    let model_ir_linear_reaction_view_ko_kr_second =
        required_path(options, "--model-ir-linear-reaction-view-ko-kr-second")?;
    let model_ir_linear_reaction_view_window =
        required_path(options, "--model-ir-linear-reaction-view-window")?;
    let mgt_model_ir_linear_reaction_view_en_us_first =
        required_path(options, "--mgt-model-ir-linear-reaction-view-en-us-first")?;
    let mgt_model_ir_linear_reaction_view_en_us_second =
        required_path(options, "--mgt-model-ir-linear-reaction-view-en-us-second")?;
    let mgt_model_ir_linear_reaction_view_ko_kr_first =
        required_path(options, "--mgt-model-ir-linear-reaction-view-ko-kr-first")?;
    let mgt_model_ir_linear_reaction_view_ko_kr_second =
        required_path(options, "--mgt-model-ir-linear-reaction-view-ko-kr-second")?;
    let workbench_reaction_view_wrong_profile_failure =
        required_path(options, "--workbench-reaction-view-wrong-profile-failure")?;
    let model_ir_linear_reaction_audit_en_us_first =
        required_path(options, "--model-ir-linear-reaction-audit-en-us-first")?;
    let model_ir_linear_reaction_audit_en_us_second =
        required_path(options, "--model-ir-linear-reaction-audit-en-us-second")?;
    let model_ir_linear_reaction_audit_ko_kr_first =
        required_path(options, "--model-ir-linear-reaction-audit-ko-kr-first")?;
    let model_ir_linear_reaction_audit_ko_kr_second =
        required_path(options, "--model-ir-linear-reaction-audit-ko-kr-second")?;
    let mgt_model_ir_linear_reaction_audit_en_us_first =
        required_path(options, "--mgt-model-ir-linear-reaction-audit-en-us-first")?;
    let mgt_model_ir_linear_reaction_audit_en_us_second =
        required_path(options, "--mgt-model-ir-linear-reaction-audit-en-us-second")?;
    let mgt_model_ir_linear_reaction_audit_ko_kr_first =
        required_path(options, "--mgt-model-ir-linear-reaction-audit-ko-kr-first")?;
    let mgt_model_ir_linear_reaction_audit_ko_kr_second =
        required_path(options, "--mgt-model-ir-linear-reaction-audit-ko-kr-second")?;
    let workbench_reaction_audit_wrong_profile_failure =
        required_path(options, "--workbench-reaction-audit-wrong-profile-failure")?;
    let model_ir_linear_nodal_displacement_view_en_us_first = required_path(
        options,
        "--model-ir-linear-nodal-displacement-view-en-us-first",
    )?;
    let model_ir_linear_nodal_displacement_view_en_us_second = required_path(
        options,
        "--model-ir-linear-nodal-displacement-view-en-us-second",
    )?;
    let model_ir_linear_nodal_displacement_view_ko_kr_first = required_path(
        options,
        "--model-ir-linear-nodal-displacement-view-ko-kr-first",
    )?;
    let model_ir_linear_nodal_displacement_view_ko_kr_second = required_path(
        options,
        "--model-ir-linear-nodal-displacement-view-ko-kr-second",
    )?;
    let model_ir_linear_nodal_displacement_view_window =
        required_path(options, "--model-ir-linear-nodal-displacement-view-window")?;
    let mgt_model_ir_linear_nodal_displacement_view_en_us_first = required_path(
        options,
        "--mgt-model-ir-linear-nodal-displacement-view-en-us-first",
    )?;
    let mgt_model_ir_linear_nodal_displacement_view_en_us_second = required_path(
        options,
        "--mgt-model-ir-linear-nodal-displacement-view-en-us-second",
    )?;
    let mgt_model_ir_linear_nodal_displacement_view_ko_kr_first = required_path(
        options,
        "--mgt-model-ir-linear-nodal-displacement-view-ko-kr-first",
    )?;
    let mgt_model_ir_linear_nodal_displacement_view_ko_kr_second = required_path(
        options,
        "--mgt-model-ir-linear-nodal-displacement-view-ko-kr-second",
    )?;
    let workbench_nodal_displacement_view_wrong_profile_failure = required_path(
        options,
        "--workbench-nodal-displacement-view-wrong-profile-failure",
    )?;
    let model_ir_linear_deformed_view_en_us_first =
        required_path(options, "--model-ir-linear-deformed-view-en-us-first")?;
    let model_ir_linear_deformed_view_en_us_second =
        required_path(options, "--model-ir-linear-deformed-view-en-us-second")?;
    let model_ir_linear_deformed_view_ko_kr_first =
        required_path(options, "--model-ir-linear-deformed-view-ko-kr-first")?;
    let model_ir_linear_deformed_view_ko_kr_second =
        required_path(options, "--model-ir-linear-deformed-view-ko-kr-second")?;
    let model_ir_linear_deformed_view_projection =
        required_path(options, "--model-ir-linear-deformed-view-projection")?;
    let mgt_model_ir_linear_deformed_view_en_us_first =
        required_path(options, "--mgt-model-ir-linear-deformed-view-en-us-first")?;
    let mgt_model_ir_linear_deformed_view_en_us_second =
        required_path(options, "--mgt-model-ir-linear-deformed-view-en-us-second")?;
    let mgt_model_ir_linear_deformed_view_ko_kr_first =
        required_path(options, "--mgt-model-ir-linear-deformed-view-ko-kr-first")?;
    let mgt_model_ir_linear_deformed_view_ko_kr_second =
        required_path(options, "--mgt-model-ir-linear-deformed-view-ko-kr-second")?;
    let workbench_linear_deformed_view_invalid_step_failure = required_path(
        options,
        "--workbench-linear-deformed-view-invalid-step-failure",
    )?;
    let model_ir_linear_element_recovery_view_en_us_first = required_path(
        options,
        "--model-ir-linear-element-recovery-view-en-us-first",
    )?;
    let model_ir_linear_element_recovery_view_en_us_second = required_path(
        options,
        "--model-ir-linear-element-recovery-view-en-us-second",
    )?;
    let model_ir_linear_element_recovery_view_ko_kr_first = required_path(
        options,
        "--model-ir-linear-element-recovery-view-ko-kr-first",
    )?;
    let model_ir_linear_element_recovery_view_ko_kr_second = required_path(
        options,
        "--model-ir-linear-element-recovery-view-ko-kr-second",
    )?;
    let mgt_model_ir_linear_element_recovery_view_en_us_first = required_path(
        options,
        "--mgt-model-ir-linear-element-recovery-view-en-us-first",
    )?;
    let mgt_model_ir_linear_element_recovery_view_en_us_second = required_path(
        options,
        "--mgt-model-ir-linear-element-recovery-view-en-us-second",
    )?;
    let mgt_model_ir_linear_element_recovery_view_ko_kr_first = required_path(
        options,
        "--mgt-model-ir-linear-element-recovery-view-ko-kr-first",
    )?;
    let mgt_model_ir_linear_element_recovery_view_ko_kr_second = required_path(
        options,
        "--mgt-model-ir-linear-element-recovery-view-ko-kr-second",
    )?;
    let workbench_linear_element_recovery_view_invalid_window_failure = required_path(
        options,
        "--workbench-linear-element-recovery-view-invalid-window-failure",
    )?;
    let model_modal_request_root = required_path(options, "--model-modal-request-root")?;
    let model_modal_direct_root = required_path(options, "--model-modal-direct-root")?;
    let model_modal_resumed_root = required_path(options, "--model-modal-resumed-root")?;
    let model_modal_view_source_before =
        required_path(options, "--model-modal-view-source-before")?;
    let model_modal_direct_stdout = required_path(options, "--model-modal-direct-stdout")?;
    let model_modal_resumed_stdout = required_path(options, "--model-modal-resumed-stdout")?;
    let model_modal_result_view_en_us_first =
        required_path(options, "--model-modal-result-view-en-us-first")?;
    let model_modal_result_view_en_us_second =
        required_path(options, "--model-modal-result-view-en-us-second")?;
    let model_modal_result_view_ko_kr_first =
        required_path(options, "--model-modal-result-view-ko-kr-first")?;
    let model_modal_result_view_ko_kr_second =
        required_path(options, "--model-modal-result-view-ko-kr-second")?;
    let model_modal_result_view_invalid_window_failure =
        required_path(options, "--model-modal-result-view-invalid-window-failure")?;
    let model_modal_workbench_restarted_root =
        required_path(options, "--model-modal-workbench-restarted-root")?;
    let model_modal_workbench_direct_root =
        required_path(options, "--model-modal-workbench-direct-root")?;
    let model_modal_workbench_reconciled_stdout =
        required_path(options, "--model-modal-workbench-reconciled-stdout")?;
    let model_modal_workbench_inspect_first =
        required_path(options, "--model-modal-workbench-inspect-first")?;
    let model_modal_workbench_inspect_second =
        required_path(options, "--model-modal-workbench-inspect-second")?;
    let model_modal_workbench_tamper_failure =
        required_path(options, "--model-modal-workbench-tamper-failure")?;
    let frame3d_rigid_offset_model = required_path(options, "--frame3d-rigid-offset-model")?;
    let frame3d_rigid_offset_request_root =
        required_path(options, "--frame3d-rigid-offset-request-root")?;
    let frame3d_rigid_offset_direct_root =
        required_path(options, "--frame3d-rigid-offset-direct-root")?;
    let frame3d_rigid_offset_partial_root =
        required_path(options, "--frame3d-rigid-offset-partial-root")?;
    let frame3d_rigid_offset_resumed_root =
        required_path(options, "--frame3d-rigid-offset-resumed-root")?;
    let frame3d_end_release_model = required_path(options, "--frame3d-end-release-model")?;
    let frame3d_end_release_request_root =
        required_path(options, "--frame3d-end-release-request-root")?;
    let frame3d_end_release_direct_root =
        required_path(options, "--frame3d-end-release-direct-root")?;
    let frame3d_end_release_partial_root =
        required_path(options, "--frame3d-end-release-partial-root")?;
    let frame3d_end_release_resumed_root =
        required_path(options, "--frame3d-end-release-resumed-root")?;
    let frame3d_self_weight_model = required_path(options, "--frame3d-self-weight-model")?;
    let frame3d_self_weight_request_root =
        required_path(options, "--frame3d-self-weight-request-root")?;
    let frame3d_self_weight_direct_root =
        required_path(options, "--frame3d-self-weight-direct-root")?;
    let frame3d_self_weight_partial_root =
        required_path(options, "--frame3d-self-weight-partial-root")?;
    let frame3d_self_weight_resumed_root =
        required_path(options, "--frame3d-self-weight-resumed-root")?;
    let frame3d_member_distributed_load_model =
        required_path(options, "--frame3d-member-distributed-load-model")?;
    let frame3d_member_distributed_load_request_root =
        required_path(options, "--frame3d-member-distributed-load-request-root")?;
    let frame3d_member_distributed_load_direct_root =
        required_path(options, "--frame3d-member-distributed-load-direct-root")?;
    let frame3d_member_distributed_load_partial_root =
        required_path(options, "--frame3d-member-distributed-load-partial-root")?;
    let frame3d_member_distributed_load_resumed_root =
        required_path(options, "--frame3d-member-distributed-load-resumed-root")?;
    let workbench_catalog = required_path(options, "--workbench-catalog")?;
    let workbench_evidence = required_path(options, "--workbench-evidence")?;
    let receipt = required_path(options, "--receipt")?;
    let result = create_rootfs_isolation_receipt(&RootfsIsolationProbeRequest {
        bundle: &bundle,
        payload_root: &payload_root,
        workspace: &workspace,
        workbench_root: &workbench_root,
        mgt_workbench_root: &mgt_workbench_root,
        model_ir_linear_workbench_root: &model_ir_linear_workbench_root,
        mgt_model_ir_linear_workbench_root: &mgt_model_ir_linear_workbench_root,
        workbench_inspect_before_review: &workbench_inspect_before_review,
        workbench_review_show: &workbench_review_show,
        workbench_inspect_after_review: &workbench_inspect_after_review,
        workbench_export: &workbench_export,
        mgt_workbench_inspect_before_review: &mgt_workbench_inspect_before_review,
        mgt_workbench_review_show: &mgt_workbench_review_show,
        mgt_workbench_inspect_after_review: &mgt_workbench_inspect_after_review,
        mgt_workbench_export: &mgt_workbench_export,
        model_ir_linear_workbench_inspect_before_review:
            &model_ir_linear_workbench_inspect_before_review,
        model_ir_linear_workbench_review_show: &model_ir_linear_workbench_review_show,
        model_ir_linear_workbench_inspect_after_review:
            &model_ir_linear_workbench_inspect_after_review,
        model_ir_linear_workbench_export: &model_ir_linear_workbench_export,
        mgt_model_ir_linear_workbench_inspect_before_review:
            &mgt_model_ir_linear_workbench_inspect_before_review,
        mgt_model_ir_linear_workbench_review_show: &mgt_model_ir_linear_workbench_review_show,
        mgt_model_ir_linear_workbench_inspect_after_review:
            &mgt_model_ir_linear_workbench_inspect_after_review,
        mgt_model_ir_linear_workbench_export: &mgt_model_ir_linear_workbench_export,
        model_ir_linear_workbench_session_before_localized_pdf:
            &model_ir_linear_workbench_session_before_localized_pdf,
        model_ir_linear_localized_pdf_en_us_first_root:
            &model_ir_linear_localized_pdf_en_us_first_root,
        model_ir_linear_localized_pdf_en_us_second_root:
            &model_ir_linear_localized_pdf_en_us_second_root,
        model_ir_linear_localized_pdf_ko_kr_first_root:
            &model_ir_linear_localized_pdf_ko_kr_first_root,
        model_ir_linear_localized_pdf_ko_kr_second_root:
            &model_ir_linear_localized_pdf_ko_kr_second_root,
        model_ir_linear_workbench_session_before_reaction_view:
            &model_ir_linear_workbench_session_before_reaction_view,
        mgt_model_ir_linear_workbench_session_before_reaction_view:
            &mgt_model_ir_linear_workbench_session_before_reaction_view,
        model_ir_linear_reaction_view_en_us_first: &model_ir_linear_reaction_view_en_us_first,
        model_ir_linear_reaction_view_en_us_second: &model_ir_linear_reaction_view_en_us_second,
        model_ir_linear_reaction_view_ko_kr_first: &model_ir_linear_reaction_view_ko_kr_first,
        model_ir_linear_reaction_view_ko_kr_second: &model_ir_linear_reaction_view_ko_kr_second,
        model_ir_linear_reaction_view_window: &model_ir_linear_reaction_view_window,
        mgt_model_ir_linear_reaction_view_en_us_first:
            &mgt_model_ir_linear_reaction_view_en_us_first,
        mgt_model_ir_linear_reaction_view_en_us_second:
            &mgt_model_ir_linear_reaction_view_en_us_second,
        mgt_model_ir_linear_reaction_view_ko_kr_first:
            &mgt_model_ir_linear_reaction_view_ko_kr_first,
        mgt_model_ir_linear_reaction_view_ko_kr_second:
            &mgt_model_ir_linear_reaction_view_ko_kr_second,
        workbench_reaction_view_wrong_profile_failure:
            &workbench_reaction_view_wrong_profile_failure,
        model_ir_linear_reaction_audit_en_us_first: &model_ir_linear_reaction_audit_en_us_first,
        model_ir_linear_reaction_audit_en_us_second: &model_ir_linear_reaction_audit_en_us_second,
        model_ir_linear_reaction_audit_ko_kr_first: &model_ir_linear_reaction_audit_ko_kr_first,
        model_ir_linear_reaction_audit_ko_kr_second: &model_ir_linear_reaction_audit_ko_kr_second,
        mgt_model_ir_linear_reaction_audit_en_us_first:
            &mgt_model_ir_linear_reaction_audit_en_us_first,
        mgt_model_ir_linear_reaction_audit_en_us_second:
            &mgt_model_ir_linear_reaction_audit_en_us_second,
        mgt_model_ir_linear_reaction_audit_ko_kr_first:
            &mgt_model_ir_linear_reaction_audit_ko_kr_first,
        mgt_model_ir_linear_reaction_audit_ko_kr_second:
            &mgt_model_ir_linear_reaction_audit_ko_kr_second,
        workbench_reaction_audit_wrong_profile_failure:
            &workbench_reaction_audit_wrong_profile_failure,
        model_ir_linear_nodal_displacement_view_en_us_first:
            &model_ir_linear_nodal_displacement_view_en_us_first,
        model_ir_linear_nodal_displacement_view_en_us_second:
            &model_ir_linear_nodal_displacement_view_en_us_second,
        model_ir_linear_nodal_displacement_view_ko_kr_first:
            &model_ir_linear_nodal_displacement_view_ko_kr_first,
        model_ir_linear_nodal_displacement_view_ko_kr_second:
            &model_ir_linear_nodal_displacement_view_ko_kr_second,
        model_ir_linear_nodal_displacement_view_window:
            &model_ir_linear_nodal_displacement_view_window,
        mgt_model_ir_linear_nodal_displacement_view_en_us_first:
            &mgt_model_ir_linear_nodal_displacement_view_en_us_first,
        mgt_model_ir_linear_nodal_displacement_view_en_us_second:
            &mgt_model_ir_linear_nodal_displacement_view_en_us_second,
        mgt_model_ir_linear_nodal_displacement_view_ko_kr_first:
            &mgt_model_ir_linear_nodal_displacement_view_ko_kr_first,
        mgt_model_ir_linear_nodal_displacement_view_ko_kr_second:
            &mgt_model_ir_linear_nodal_displacement_view_ko_kr_second,
        workbench_nodal_displacement_view_wrong_profile_failure:
            &workbench_nodal_displacement_view_wrong_profile_failure,
        model_ir_linear_deformed_view_en_us_first: &model_ir_linear_deformed_view_en_us_first,
        model_ir_linear_deformed_view_en_us_second: &model_ir_linear_deformed_view_en_us_second,
        model_ir_linear_deformed_view_ko_kr_first: &model_ir_linear_deformed_view_ko_kr_first,
        model_ir_linear_deformed_view_ko_kr_second: &model_ir_linear_deformed_view_ko_kr_second,
        model_ir_linear_deformed_view_projection: &model_ir_linear_deformed_view_projection,
        mgt_model_ir_linear_deformed_view_en_us_first:
            &mgt_model_ir_linear_deformed_view_en_us_first,
        mgt_model_ir_linear_deformed_view_en_us_second:
            &mgt_model_ir_linear_deformed_view_en_us_second,
        mgt_model_ir_linear_deformed_view_ko_kr_first:
            &mgt_model_ir_linear_deformed_view_ko_kr_first,
        mgt_model_ir_linear_deformed_view_ko_kr_second:
            &mgt_model_ir_linear_deformed_view_ko_kr_second,
        workbench_linear_deformed_view_invalid_step_failure:
            &workbench_linear_deformed_view_invalid_step_failure,
        model_ir_linear_element_recovery_view_en_us_first:
            &model_ir_linear_element_recovery_view_en_us_first,
        model_ir_linear_element_recovery_view_en_us_second:
            &model_ir_linear_element_recovery_view_en_us_second,
        model_ir_linear_element_recovery_view_ko_kr_first:
            &model_ir_linear_element_recovery_view_ko_kr_first,
        model_ir_linear_element_recovery_view_ko_kr_second:
            &model_ir_linear_element_recovery_view_ko_kr_second,
        mgt_model_ir_linear_element_recovery_view_en_us_first:
            &mgt_model_ir_linear_element_recovery_view_en_us_first,
        mgt_model_ir_linear_element_recovery_view_en_us_second:
            &mgt_model_ir_linear_element_recovery_view_en_us_second,
        mgt_model_ir_linear_element_recovery_view_ko_kr_first:
            &mgt_model_ir_linear_element_recovery_view_ko_kr_first,
        mgt_model_ir_linear_element_recovery_view_ko_kr_second:
            &mgt_model_ir_linear_element_recovery_view_ko_kr_second,
        workbench_linear_element_recovery_view_invalid_window_failure:
            &workbench_linear_element_recovery_view_invalid_window_failure,
        model_modal_request_root: &model_modal_request_root,
        model_modal_direct_root: &model_modal_direct_root,
        model_modal_resumed_root: &model_modal_resumed_root,
        model_modal_view_source_before: &model_modal_view_source_before,
        model_modal_direct_stdout: &model_modal_direct_stdout,
        model_modal_resumed_stdout: &model_modal_resumed_stdout,
        model_modal_result_view_en_us_first: &model_modal_result_view_en_us_first,
        model_modal_result_view_en_us_second: &model_modal_result_view_en_us_second,
        model_modal_result_view_ko_kr_first: &model_modal_result_view_ko_kr_first,
        model_modal_result_view_ko_kr_second: &model_modal_result_view_ko_kr_second,
        model_modal_result_view_invalid_window_failure:
            &model_modal_result_view_invalid_window_failure,
        model_modal_workbench_restarted_root: &model_modal_workbench_restarted_root,
        model_modal_workbench_direct_root: &model_modal_workbench_direct_root,
        model_modal_workbench_reconciled_stdout: &model_modal_workbench_reconciled_stdout,
        model_modal_workbench_inspect_first: &model_modal_workbench_inspect_first,
        model_modal_workbench_inspect_second: &model_modal_workbench_inspect_second,
        model_modal_workbench_tamper_failure: &model_modal_workbench_tamper_failure,
        frame3d_rigid_offset_model: &frame3d_rigid_offset_model,
        frame3d_rigid_offset_request_root: &frame3d_rigid_offset_request_root,
        frame3d_rigid_offset_direct_root: &frame3d_rigid_offset_direct_root,
        frame3d_rigid_offset_partial_root: &frame3d_rigid_offset_partial_root,
        frame3d_rigid_offset_resumed_root: &frame3d_rigid_offset_resumed_root,
        frame3d_end_release_model: &frame3d_end_release_model,
        frame3d_end_release_request_root: &frame3d_end_release_request_root,
        frame3d_end_release_direct_root: &frame3d_end_release_direct_root,
        frame3d_end_release_partial_root: &frame3d_end_release_partial_root,
        frame3d_end_release_resumed_root: &frame3d_end_release_resumed_root,
        frame3d_self_weight_model: &frame3d_self_weight_model,
        frame3d_self_weight_request_root: &frame3d_self_weight_request_root,
        frame3d_self_weight_direct_root: &frame3d_self_weight_direct_root,
        frame3d_self_weight_partial_root: &frame3d_self_weight_partial_root,
        frame3d_self_weight_resumed_root: &frame3d_self_weight_resumed_root,
        frame3d_member_distributed_load_model: &frame3d_member_distributed_load_model,
        frame3d_member_distributed_load_request_root: &frame3d_member_distributed_load_request_root,
        frame3d_member_distributed_load_direct_root: &frame3d_member_distributed_load_direct_root,
        frame3d_member_distributed_load_partial_root: &frame3d_member_distributed_load_partial_root,
        frame3d_member_distributed_load_resumed_root: &frame3d_member_distributed_load_resumed_root,
        workbench_catalog: &workbench_catalog,
        workbench_evidence: &workbench_evidence,
        receipt: &receipt,
    })?;
    json_result("runtime_probe", result)
}

fn run_runtime_receipt_verify(
    options: &BTreeMap<String, String>,
) -> Result<serde_json::Value, CliError> {
    require_exact_options(options, &["--receipt", "--bundle"])?;
    let receipt = verify_rootfs_isolation_receipt(
        &required_path(options, "--receipt")?,
        &required_path(options, "--bundle")?,
    )?;
    json_result("runtime_receipt_verify", receipt)
}

fn json_result<T: Serialize>(
    action: &'static str,
    result: T,
) -> Result<serde_json::Value, CliError> {
    serde_json::to_value(CommandResult {
        schema_version: "structural-installer-result.v1",
        action,
        result,
    })
    .map_err(|error| usage_error(&format!("could not encode command result: {error}")))
}

fn parse_options(arguments: &[OsString]) -> Result<BTreeMap<String, String>, CliError> {
    if arguments.len() % 2 != 0 {
        return Err(usage_error("options must be --name VALUE pairs"));
    }
    let mut options = BTreeMap::new();
    for pair in arguments.chunks_exact(2) {
        let name = pair[0]
            .to_str()
            .ok_or_else(|| usage_error("option names must be UTF-8"))?;
        let value = pair[1]
            .to_str()
            .ok_or_else(|| usage_error("option values must be UTF-8"))?;
        if !name.starts_with("--") || options.insert(name.to_owned(), value.to_owned()).is_some() {
            return Err(usage_error("option names must be unique --name tokens"));
        }
    }
    Ok(options)
}

fn required<'a>(options: &'a BTreeMap<String, String>, name: &str) -> Result<&'a str, CliError> {
    options
        .get(name)
        .map(String::as_str)
        .ok_or_else(|| usage_error(&format!("missing required option {name}")))
}

fn required_path(options: &BTreeMap<String, String>, name: &str) -> Result<PathBuf, CliError> {
    required(options, name).map(PathBuf::from)
}

fn require_exact_options(
    options: &BTreeMap<String, String>,
    expected: &[&str],
) -> Result<(), CliError> {
    if options.len() != expected.len() || expected.iter().any(|name| !options.contains_key(*name)) {
        return Err(usage_error(
            "command options differ from the exact contract",
        ));
    }
    Ok(())
}

fn parse_backend(value: &str) -> Result<BackendProfileV1, CliError> {
    match value {
        "cpu-only" => Ok(BackendProfileV1::CpuOnly),
        "rocm" => Ok(BackendProfileV1::Rocm),
        _ => Err(usage_error("--backend must be cpu-only or rocm")),
    }
}

fn parse_linkage(value: &str) -> Result<LinkageV1, CliError> {
    match value {
        "shared" => Ok(LinkageV1::Shared),
        "static" => Ok(LinkageV1::Static),
        _ => Err(usage_error("--linkage must be shared or static")),
    }
}

fn usage_error(detail: &str) -> CliError {
    CliError::Usage(detail.to_owned())
}

fn usage() -> String {
    frozen_usage_v11().replace(
        " --workbench-catalog",
        " --model-ir-linear-element-recovery-view-en-us-first FILE --model-ir-linear-element-recovery-view-en-us-second FILE --model-ir-linear-element-recovery-view-ko-kr-first FILE --model-ir-linear-element-recovery-view-ko-kr-second FILE --mgt-model-ir-linear-element-recovery-view-en-us-first FILE --mgt-model-ir-linear-element-recovery-view-en-us-second FILE --mgt-model-ir-linear-element-recovery-view-ko-kr-first FILE --mgt-model-ir-linear-element-recovery-view-ko-kr-second FILE --workbench-linear-element-recovery-view-invalid-window-failure FILE --frame3d-rigid-offset-model FILE --frame3d-rigid-offset-request-root DIR --frame3d-rigid-offset-direct-root DIR --frame3d-rigid-offset-partial-root DIR --frame3d-rigid-offset-resumed-root DIR --frame3d-end-release-model FILE --frame3d-end-release-request-root DIR --frame3d-end-release-direct-root DIR --frame3d-end-release-partial-root DIR --frame3d-end-release-resumed-root DIR --workbench-catalog",
    )
}

fn frozen_usage_v11() -> String {
    frozen_usage_v10().replace(
        " --workbench-catalog",
        " --model-ir-linear-deformed-view-en-us-first FILE --model-ir-linear-deformed-view-en-us-second FILE --model-ir-linear-deformed-view-ko-kr-first FILE --model-ir-linear-deformed-view-ko-kr-second FILE --model-ir-linear-deformed-view-projection FILE --mgt-model-ir-linear-deformed-view-en-us-first FILE --mgt-model-ir-linear-deformed-view-en-us-second FILE --mgt-model-ir-linear-deformed-view-ko-kr-first FILE --mgt-model-ir-linear-deformed-view-ko-kr-second FILE --workbench-linear-deformed-view-invalid-step-failure FILE --workbench-catalog",
    )
}

fn frozen_usage_v10() -> String {
    frozen_usage_v9().replace(
        " --workbench-catalog",
        " --model-ir-linear-nodal-displacement-view-en-us-first FILE --model-ir-linear-nodal-displacement-view-en-us-second FILE --model-ir-linear-nodal-displacement-view-ko-kr-first FILE --model-ir-linear-nodal-displacement-view-ko-kr-second FILE --model-ir-linear-nodal-displacement-view-window FILE --mgt-model-ir-linear-nodal-displacement-view-en-us-first FILE --mgt-model-ir-linear-nodal-displacement-view-en-us-second FILE --mgt-model-ir-linear-nodal-displacement-view-ko-kr-first FILE --mgt-model-ir-linear-nodal-displacement-view-ko-kr-second FILE --workbench-nodal-displacement-view-wrong-profile-failure FILE --workbench-catalog",
    )
}

fn frozen_usage_v9() -> String {
    frozen_usage_v8().replace(
        " --workbench-catalog",
        " --model-ir-linear-reaction-audit-en-us-first FILE --model-ir-linear-reaction-audit-en-us-second FILE --model-ir-linear-reaction-audit-ko-kr-first FILE --model-ir-linear-reaction-audit-ko-kr-second FILE --mgt-model-ir-linear-reaction-audit-en-us-first FILE --mgt-model-ir-linear-reaction-audit-en-us-second FILE --mgt-model-ir-linear-reaction-audit-ko-kr-first FILE --mgt-model-ir-linear-reaction-audit-ko-kr-second FILE --workbench-reaction-audit-wrong-profile-failure FILE --workbench-catalog",
    )
}

fn frozen_usage_v8() -> &'static str {
    "usage:\n  structural-distribution bundle-create --payload DIR --output DIR --release-id ID --package-version VERSION --backend cpu-only|rocm --linkage shared|static --source-sha256 sha256:HEX\n  structural-distribution bundle-verify --bundle DIR\n  structural-distribution runtime-probe --bundle DIR --payload-root DIR --workspace DIR --workbench-root DIR --mgt-workbench-root DIR --model-ir-linear-workbench-root DIR --mgt-model-ir-linear-workbench-root DIR --workbench-inspect-before-review FILE --workbench-review-show FILE --workbench-inspect-after-review FILE --workbench-export FILE --mgt-workbench-inspect-before-review FILE --mgt-workbench-review-show FILE --mgt-workbench-inspect-after-review FILE --mgt-workbench-export FILE --model-ir-linear-workbench-inspect-before-review FILE --model-ir-linear-workbench-review-show FILE --model-ir-linear-workbench-inspect-after-review FILE --model-ir-linear-workbench-export FILE --mgt-model-ir-linear-workbench-inspect-before-review FILE --mgt-model-ir-linear-workbench-review-show FILE --mgt-model-ir-linear-workbench-inspect-after-review FILE --mgt-model-ir-linear-workbench-export FILE --model-ir-linear-workbench-session-before-localized-pdf FILE --model-ir-linear-localized-pdf-en-us-first-root DIR --model-ir-linear-localized-pdf-en-us-second-root DIR --model-ir-linear-localized-pdf-ko-kr-first-root DIR --model-ir-linear-localized-pdf-ko-kr-second-root DIR --model-ir-linear-workbench-session-before-reaction-view FILE --mgt-model-ir-linear-workbench-session-before-reaction-view FILE --model-ir-linear-reaction-view-en-us-first FILE --model-ir-linear-reaction-view-en-us-second FILE --model-ir-linear-reaction-view-ko-kr-first FILE --model-ir-linear-reaction-view-ko-kr-second FILE --model-ir-linear-reaction-view-window FILE --mgt-model-ir-linear-reaction-view-en-us-first FILE --mgt-model-ir-linear-reaction-view-en-us-second FILE --mgt-model-ir-linear-reaction-view-ko-kr-first FILE --mgt-model-ir-linear-reaction-view-ko-kr-second FILE --workbench-reaction-view-wrong-profile-failure FILE --workbench-catalog FILE --workbench-evidence FILE --receipt FILE\n  structural-distribution runtime-receipt-verify --receipt FILE --bundle DIR\n  structural-distribution install --bundle DIR --root DIR\n  structural-distribution update --bundle DIR --root DIR\n  structural-distribution rollback --root DIR\n  structural-distribution recover --root DIR\n  structural-distribution status --root DIR"
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parser_rejects_duplicate_options() {
        let arguments = [
            OsString::from("status"),
            OsString::from("--root"),
            OsString::from("one"),
            OsString::from("--root"),
            OsString::from("two"),
        ];
        assert!(matches!(run(&arguments), Err(CliError::Usage(_))));
    }

    #[test]
    fn parser_rejects_unknown_options() {
        let arguments = [
            OsString::from("status"),
            OsString::from("--root"),
            OsString::from("one"),
            OsString::from("--typo"),
            OsString::from("ignored"),
        ];
        assert!(matches!(run(&arguments), Err(CliError::Usage(_))));
    }

    #[test]
    fn version_is_machine_readable() {
        let value = run(&[OsString::from("--version")]).expect("version result");
        assert_eq!(value["schema_version"], "structural-installer-version.v1");
    }
}
