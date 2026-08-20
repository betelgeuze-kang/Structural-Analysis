use std::collections::BTreeSet;
use std::fmt::Write as _;
use std::fs;
use std::path::Path;

use serde_json::Value;
use structural_contracts::model_ir::parse_model_ir_v2;
use structural_contracts::model_modal_product::parse_model_ir_modal_analysis_request_v1;
use structural_contracts::product_ir::sha256_identity;
use structural_contracts::spectral_product::{
    dense_spectral_execution_hash_v1, dense_spectral_model_hash_v1,
    parse_dense_spectral_report_ir_v1, parse_dense_spectral_request_v1,
    parse_dense_spectral_result_ir_v1, SpectralAnalysisKindV1, SpectralModeV1,
};
use structural_runtime::{
    DenseSpectralCheckpointV1, ModelIrModalCheckpointBindingsV1, ModelIrModalCheckpointV1,
};

use crate::{
    read_bounded_regular_file, verify_self_hashed_json, WorkbenchError, WorkbenchReportLocaleV1,
    MAX_PRODUCT_ARTIFACT_BYTES,
};

pub(crate) const MODAL_RESULT_VIEW_SCHEMA_V1: &str =
    "structural-native-workbench-model-ir-modal-result-view.v1";
pub const WORKBENCH_MODAL_RESULT_VIEW_DEFAULT_COUNT_V1: u32 = 16;
pub const WORKBENCH_MODAL_RESULT_VIEW_MAX_COUNT_V1: u32 = 128;
const CLAIM_BOUNDARY: &str = "bounded_read_only_verified_modelir_frame3d_truss3d_cpu_modal_mode_table_not_geometric_deformed_shape_animation_participation_mass_response_spectrum_buckling_shell_sparse_engineering_acceptance_or_code_compliance";
const EXPECTED_FILES: [&str; 11] = [
    "assembly-receipt.json",
    "checkpoint.eigcp",
    "checkpoint.mmcp",
    "dense-run-receipt.json",
    "generated-dense-request.json",
    "model-ir.json",
    "model-modal-request.json",
    "report-ir.json",
    "report.md",
    "result-ir.json",
    "run-receipt.json",
];

struct VerifiedModalResult {
    model_id: String,
    model_content_hash: String,
    model_semantic_hash: String,
    model_provenance_hash: String,
    analysis_request_hash: String,
    assembly_hash: String,
    generated_request_hash: String,
    outer_checkpoint_hash: String,
    result: structural_contracts::spectral_product::DenseSpectralResultIrV1,
}

/// Verify one complete model-modal product directory and render a bounded deterministic mode table.
///
/// # Errors
///
/// Rejects noncanonical, missing, extra, symlinked, hash-drifted, identity-mismatched, non-modal,
/// fallback-bearing, unsafe, or out-of-window inputs before returning any view text.
pub fn render_model_ir_modal_result_view_directory(
    directory: &Path,
    locale: WorkbenchReportLocaleV1,
    start_mode: u32,
    count: u32,
) -> Result<String, WorkbenchError> {
    verify_directory_inventory(directory)?;
    let verified = verify_modal_result(directory)?;
    render_modal_result_view(&verified, locale, start_mode, count)
}

fn verify_directory_inventory(directory: &Path) -> Result<(), WorkbenchError> {
    let metadata = fs::symlink_metadata(directory).map_err(|error| {
        view_error(
            "workbench_modal_result_view_directory_invalid",
            &error.to_string(),
        )
    })?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(view_error(
            "workbench_modal_result_view_directory_invalid",
            "modal result path must be a non-symlink directory",
        ));
    }
    let mut names = BTreeSet::new();
    for entry in fs::read_dir(directory).map_err(|error| {
        view_error(
            "workbench_modal_result_view_directory_invalid",
            &error.to_string(),
        )
    })? {
        let entry = entry.map_err(|error| {
            view_error(
                "workbench_modal_result_view_directory_invalid",
                &error.to_string(),
            )
        })?;
        let name = entry.file_name().into_string().map_err(|_| {
            view_error(
                "workbench_modal_result_view_directory_invalid",
                "modal result artifact names must be valid UTF-8",
            )
        })?;
        names.insert(name);
    }
    let expected = EXPECTED_FILES
        .iter()
        .map(|value| (*value).to_owned())
        .collect::<BTreeSet<_>>();
    if names != expected {
        return Err(view_error(
            "workbench_modal_result_view_inventory_mismatch",
            "modal result directory must contain the exact eleven-artifact product inventory",
        ));
    }
    Ok(())
}

#[allow(clippy::too_many_lines)]
fn verify_modal_result(directory: &Path) -> Result<VerifiedModalResult, WorkbenchError> {
    let artifacts = EXPECTED_FILES
        .iter()
        .map(|name| {
            read_bounded_regular_file(&directory.join(name), MAX_PRODUCT_ARTIFACT_BYTES)
                .map(|bytes| ((*name).to_owned(), bytes))
        })
        .collect::<Result<std::collections::BTreeMap<_, _>, _>>()?;
    let bytes = |name: &str| {
        artifacts.get(name).map(Vec::as_slice).ok_or_else(|| {
            view_error(
                "workbench_modal_result_view_inventory_mismatch",
                "verified artifact inventory changed while it was being read",
            )
        })
    };

    let run_receipt = verify_self_hashed_json(bytes("run-receipt.json")?, "receipt_hash")?;
    verify_run_artifact_bindings(&run_receipt, &artifacts)?;
    let model = parse_model_ir_v2(bytes("model-ir.json")?).map_err(|error| {
        view_error(
            "workbench_modal_result_view_model_invalid",
            &error.to_string(),
        )
    })?;
    let request = parse_model_ir_modal_analysis_request_v1(bytes("model-modal-request.json")?)
        .map_err(|error| {
            view_error(
                "workbench_modal_result_view_request_invalid",
                &error.to_string(),
            )
        })?;
    let generated = parse_dense_spectral_request_v1(bytes("generated-dense-request.json")?)
        .map_err(|error| {
            view_error(
                "workbench_modal_result_view_request_invalid",
                &error.to_string(),
            )
        })?;
    let assembly = verify_self_hashed_json(bytes("assembly-receipt.json")?, "assembly_hash")?;
    let assembly_hash = string_field(&assembly, "assembly_hash")?.to_owned();
    let checkpoint =
        ModelIrModalCheckpointV1::from_bytes(bytes("checkpoint.mmcp")?).map_err(|error| {
            view_error(
                "workbench_modal_result_view_checkpoint_invalid",
                &error.to_string(),
            )
        })?;
    let dense_checkpoint = DenseSpectralCheckpointV1::from_bytes(bytes("checkpoint.eigcp")?)
        .map_err(|error| {
            view_error(
                "workbench_modal_result_view_checkpoint_invalid",
                &error.to_string(),
            )
        })?;
    if checkpoint.inner().as_bytes() != dense_checkpoint.as_bytes() {
        return Err(view_error(
            "workbench_modal_result_view_checkpoint_mismatch",
            "outer checkpoint does not contain the published dense checkpoint",
        ));
    }
    checkpoint
        .verify_bindings(&ModelIrModalCheckpointBindingsV1 {
            model_content_hash: model.content_hash().to_owned(),
            model_semantic_hash: model.semantic_hash().to_owned(),
            model_provenance_hash: model.provenance_hash().to_owned(),
            analysis_request_hash: request.request_hash().to_owned(),
            assembly_hash: assembly_hash.clone(),
            generated_request_hash: generated.request_hash().to_owned(),
        })
        .map_err(|error| {
            view_error(
                "workbench_modal_result_view_checkpoint_mismatch",
                &error.to_string(),
            )
        })?;

    let supplied_identity = &request.request().model_identity;
    if supplied_identity.content_hash != model.content_hash()
        || supplied_identity.semantic_hash != model.semantic_hash()
        || supplied_identity.provenance_hash != model.provenance_hash()
        || request.request().case_id != generated.request().case_id
        || generated.request().analysis_kind != SpectralAnalysisKindV1::Modal
    {
        return Err(view_error(
            "workbench_modal_result_view_identity_mismatch",
            "model, outer request and generated modal request identities do not match",
        ));
    }

    let result = parse_dense_spectral_result_ir_v1(bytes("result-ir.json")?).map_err(|error| {
        view_error(
            "workbench_modal_result_view_result_invalid",
            &error.to_string(),
        )
    })?;
    let dense_receipt = dense_checkpoint.receipt();
    let source = result.result();
    if source.analysis_kind != SpectralAnalysisKindV1::Modal
        || source.case_id != request.request().case_id
        || source.identity.request_hash != generated.request_hash()
        || source.identity.model_hash
            != dense_spectral_model_hash_v1(&generated).map_err(|error| {
                view_error(
                    "workbench_modal_result_view_identity_mismatch",
                    &error.to_string(),
                )
            })?
        || source.identity.state_hash != dense_receipt.state_hash
        || source.identity.execution_hash
            != dense_spectral_execution_hash_v1(&generated).map_err(|error| {
                view_error(
                    "workbench_modal_result_view_identity_mismatch",
                    &error.to_string(),
                )
            })?
        || source.identity.checkpoint_hash != dense_receipt.checkpoint_hash
        || source.backend_receipt.fallback_count != 0
    {
        return Err(view_error(
            "workbench_modal_result_view_identity_mismatch",
            "ResultIR does not match the verified generated request and checkpoint",
        ));
    }

    let report = parse_dense_spectral_report_ir_v1(bytes("report-ir.json")?).map_err(|error| {
        view_error(
            "workbench_modal_result_view_report_invalid",
            &error.to_string(),
        )
    })?;
    if report.report().source_result_hash != source.result_hash
        || report.report().identity != source.identity
        || report.report().document_source_hash != sha256_identity(bytes("report.md")?)
        || report.report().summary.mode_count != source.summary.mode_count
    {
        return Err(view_error(
            "workbench_modal_result_view_report_mismatch",
            "ReportIR does not match the verified ResultIR and Markdown",
        ));
    }
    let dense_run_receipt =
        verify_self_hashed_json(bytes("dense-run-receipt.json")?, "receipt_hash")?;
    if string_field(&dense_run_receipt, "request_hash")? != generated.request_hash() {
        return Err(view_error(
            "workbench_modal_result_view_receipt_mismatch",
            "dense run receipt does not match the generated request",
        ));
    }
    verify_outer_receipt(
        &run_receipt,
        &model,
        request.request_hash(),
        &assembly_hash,
        generated.request_hash(),
        &checkpoint.receipt().checkpoint_hash,
    )?;

    Ok(VerifiedModalResult {
        model_id: model.model_id().to_owned(),
        model_content_hash: model.content_hash().to_owned(),
        model_semantic_hash: model.semantic_hash().to_owned(),
        model_provenance_hash: model.provenance_hash().to_owned(),
        analysis_request_hash: request.request_hash().to_owned(),
        assembly_hash,
        generated_request_hash: generated.request_hash().to_owned(),
        outer_checkpoint_hash: checkpoint.receipt().checkpoint_hash,
        result: source.clone(),
    })
}

fn verify_run_artifact_bindings(
    receipt: &Value,
    artifacts: &std::collections::BTreeMap<String, Vec<u8>>,
) -> Result<(), WorkbenchError> {
    let rows = receipt
        .get("artifacts")
        .and_then(Value::as_array)
        .ok_or_else(|| {
            view_error(
                "workbench_modal_result_view_receipt_invalid",
                "run receipt artifacts are missing",
            )
        })?;
    let mut bound = BTreeSet::new();
    for row in rows {
        let file = string_field(row, "file")?;
        let content_hash = string_field(row, "content_hash")?;
        let byte_length = row
            .get("byte_length")
            .and_then(Value::as_u64)
            .ok_or_else(|| {
                view_error(
                    "workbench_modal_result_view_receipt_invalid",
                    "run receipt artifact byte length is invalid",
                )
            })?;
        let artifact = artifacts.get(file).ok_or_else(|| {
            view_error(
                "workbench_modal_result_view_receipt_mismatch",
                "run receipt references an artifact outside the verified inventory",
            )
        })?;
        if file == "run-receipt.json"
            || !bound.insert(file.to_owned())
            || content_hash != sha256_identity(artifact)
            || byte_length != u64::try_from(artifact.len()).unwrap_or(u64::MAX)
        {
            return Err(view_error(
                "workbench_modal_result_view_receipt_mismatch",
                "run receipt artifact identity does not match the verified bytes",
            ));
        }
    }
    let expected = EXPECTED_FILES
        .iter()
        .filter(|name| **name != "run-receipt.json")
        .map(|name| (*name).to_owned())
        .collect::<BTreeSet<_>>();
    if bound != expected {
        return Err(view_error(
            "workbench_modal_result_view_receipt_mismatch",
            "run receipt does not bind every non-receipt product artifact exactly once",
        ));
    }
    Ok(())
}

fn verify_outer_receipt(
    receipt: &Value,
    model: &structural_contracts::model_ir::ModelIrV2Document,
    request_hash: &str,
    assembly_hash: &str,
    generated_hash: &str,
    checkpoint_hash: &str,
) -> Result<(), WorkbenchError> {
    let checkpoint = receipt.get("model_ir_modal_checkpoint").ok_or_else(|| {
        view_error(
            "workbench_modal_result_view_receipt_invalid",
            "outer checkpoint receipt is missing",
        )
    })?;
    if string_field(receipt, "schema_version")? != "structural-model-ir-modal-run-receipt.v1"
        || string_field(receipt, "status")? != "completed"
        || string_field(receipt, "model_id")? != model.model_id()
        || string_field(receipt, "analysis_request_hash")? != request_hash
        || string_field(receipt, "assembly_hash")? != assembly_hash
        || string_field(receipt, "generated_dense_request_hash")? != generated_hash
        || string_field(checkpoint, "checkpoint_hash")? != checkpoint_hash
        || receipt.get("fallback_count").and_then(Value::as_u64) != Some(0)
    {
        return Err(view_error(
            "workbench_modal_result_view_receipt_mismatch",
            "outer run receipt identities do not match the verified modal product",
        ));
    }
    Ok(())
}

#[allow(clippy::too_many_lines)]
fn render_modal_result_view(
    verified: &VerifiedModalResult,
    locale: WorkbenchReportLocaleV1,
    start_mode: u32,
    count: u32,
) -> Result<String, WorkbenchError> {
    if start_mode == 0 || count == 0 || count > WORKBENCH_MODAL_RESULT_VIEW_MAX_COUNT_V1 {
        return Err(view_error(
            "workbench_modal_result_view_window_invalid",
            "start mode must be at least 1 and count must be in 1..=128",
        ));
    }
    let start = usize::try_from(start_mode - 1).map_err(|_| {
        view_error(
            "workbench_modal_result_view_window_invalid",
            "start mode does not fit the native address space",
        )
    })?;
    if start >= verified.result.modes.len() {
        return Err(view_error(
            "workbench_modal_result_view_window_invalid",
            "start mode exceeds the verified result mode count",
        ));
    }
    let end = start
        .saturating_add(usize::try_from(count).unwrap_or(usize::MAX))
        .min(verified.result.modes.len());
    let mut output = String::new();
    let ko = locale == WorkbenchReportLocaleV1::KoKr;
    push_line(
        &mut output,
        if ko {
            "Structural Native Workbench - ModelIR 모달 결과"
        } else {
            "Structural Native Workbench - ModelIR modal result"
        },
    );
    push_field(
        &mut output,
        if ko { "스키마" } else { "Schema" },
        MODAL_RESULT_VIEW_SCHEMA_V1,
    );
    push_field(
        &mut output,
        if ko { "로케일" } else { "Locale" },
        locale.label(),
    );
    push_field(
        &mut output,
        if ko { "권한" } else { "Authority" },
        "bounded candidate",
    );
    push_field(
        &mut output,
        if ko { "모델" } else { "Model" },
        &verified.model_id,
    );
    push_field(
        &mut output,
        if ko { "해석 사례" } else { "Case" },
        &verified.result.case_id,
    );
    push_field(
        &mut output,
        if ko { "모드 수" } else { "Modes" },
        &verified.result.summary.mode_count.to_string(),
    );
    push_field(
        &mut output,
        if ko {
            "표시 모드"
        } else {
            "Displayed modes"
        },
        &format!("{}-{} / {}", start + 1, end, verified.result.modes.len()),
    );
    push_field(
        &mut output,
        if ko { "백엔드" } else { "Backend" },
        "cpu / fp64 / fallback 0",
    );
    push_field(
        &mut output,
        if ko {
            "모델 콘텐츠 해시"
        } else {
            "Model content hash"
        },
        &verified.model_content_hash,
    );
    push_field(
        &mut output,
        if ko {
            "모델 의미 해시"
        } else {
            "Model semantic hash"
        },
        &verified.model_semantic_hash,
    );
    push_field(
        &mut output,
        if ko {
            "모델 출처 해시"
        } else {
            "Model provenance hash"
        },
        &verified.model_provenance_hash,
    );
    push_field(
        &mut output,
        if ko {
            "분석 요청 해시"
        } else {
            "Analysis request hash"
        },
        &verified.analysis_request_hash,
    );
    push_field(
        &mut output,
        if ko { "조립 해시" } else { "Assembly hash" },
        &verified.assembly_hash,
    );
    push_field(
        &mut output,
        if ko {
            "밀집 요청 해시"
        } else {
            "Dense request hash"
        },
        &verified.generated_request_hash,
    );
    push_field(
        &mut output,
        if ko { "결과 해시" } else { "Result hash" },
        &verified.result.result_hash,
    );
    push_field(
        &mut output,
        if ko {
            "체크포인트 해시"
        } else {
            "Checkpoint hash"
        },
        &verified.outer_checkpoint_hash,
    );
    push_line(&mut output, "");
    push_line(
        &mut output,
        if ko {
            "모드   고유값(rad2/s2)       각진동수(rad/s)       주파수(Hz)            주기(s)               상대 잔차             우세 활성 자유도/진폭"
        } else {
            "Mode   Eigenvalue(rad2/s2)   Omega(rad/s)          Frequency(Hz)          Period(s)             Relative residual     Dominant active DOF/amplitude"
        },
    );
    for (offset, mode) in verified.result.modes[start..end].iter().enumerate() {
        let SpectralModeV1::Modal {
            eigenvalue_rad2_per_s2,
            omega_rad_per_s,
            frequency_hz,
            period_s,
            max_component_normalized_shape,
            residual_relative_inf,
            ..
        } = mode
        else {
            return Err(view_error(
                "workbench_modal_result_view_result_invalid",
                "verified modal ResultIR contains a non-modal row",
            ));
        };
        let (dominant, amplitude) = max_component_normalized_shape
            .iter()
            .copied()
            .enumerate()
            .max_by(|left, right| left.1.abs().total_cmp(&right.1.abs()))
            .ok_or_else(|| {
                view_error(
                    "workbench_modal_result_view_result_invalid",
                    "verified modal shape has no active components",
                )
            })?;
        writeln!(
            output,
            "{:04}   {:+.17e} {:+.17e} {:+.17e} {:+.17e} {:+.17e} {:04}/{:+.17e}",
            start + offset + 1,
            eigenvalue_rad2_per_s2,
            omega_rad_per_s,
            frequency_hz,
            period_s,
            residual_relative_inf,
            dominant + 1,
            amplitude,
        )
        .expect("writing to a String cannot fail");
    }
    push_line(&mut output, "");
    push_field(
        &mut output,
        if ko {
            "주장 경계"
        } else {
            "Claim boundary"
        },
        CLAIM_BOUNDARY,
    );
    let view_hash = sha256_identity(output.as_bytes());
    push_field(
        &mut output,
        if ko { "보기 해시" } else { "View hash" },
        &view_hash,
    );
    if output.as_bytes().contains(&0x1b) {
        return Err(view_error(
            "workbench_modal_result_view_unsafe",
            "modal result view unexpectedly contains an escape byte",
        ));
    }
    Ok(output)
}

fn string_field<'a>(value: &'a Value, field: &str) -> Result<&'a str, WorkbenchError> {
    value.get(field).and_then(Value::as_str).ok_or_else(|| {
        view_error(
            "workbench_modal_result_view_receipt_invalid",
            &format!("verified receipt field {field} is missing or invalid"),
        )
    })
}

fn push_line(output: &mut String, value: &str) {
    output.push_str(value);
    output.push('\n');
}

fn push_field(output: &mut String, label: &str, value: &str) {
    writeln!(output, "{label}: {value}").expect("writing to a String cannot fail");
}

fn view_error(code: &'static str, detail: &str) -> WorkbenchError {
    WorkbenchError::new(code, detail)
}
