use std::collections::{BTreeMap, BTreeSet};
use std::fmt::Write as _;
use std::fs;
use std::path::Path;

use serde_json::Value;
use structural_contracts::model_buckling_product::parse_model_ir_linear_buckling_analysis_request_v1;
use structural_contracts::model_ir::parse_model_ir_v2;
use structural_contracts::model_linear_product::parse_model_ir_linear_analysis_request_v1;
use structural_contracts::model_linear_reactions::{
    parse_model_ir_linear_reaction_result_ir_v1, verify_model_ir_linear_reaction_result_v1,
};
use structural_contracts::model_linear_recovery::{
    parse_model_ir_linear_result_recovery_ir_v1, verify_model_ir_linear_result_recovery_v1,
};
use structural_contracts::product_ir::sha256_identity;
use structural_contracts::sparse_product::parse_sparse_linear_result_ir_v1;
use structural_contracts::spectral_product::{
    dense_spectral_execution_hash_v1, dense_spectral_model_hash_v1,
    parse_dense_spectral_report_ir_v1, parse_dense_spectral_request_v1,
    parse_dense_spectral_result_ir_v1, SpectralAnalysisKindV1, SpectralModeV1,
};
use structural_runtime::{
    DenseSpectralCheckpointV1, ModelIrLinearBucklingCheckpointBindingsV1,
    ModelIrLinearBucklingCheckpointV1, ModelIrLinearCheckpointV1, SparseLinearCheckpointV1,
};

use crate::{
    read_bounded_regular_file, verify_self_hashed_json, WorkbenchError, WorkbenchReportLocaleV1,
    MAX_PRODUCT_ARTIFACT_BYTES,
};

pub(crate) const BUCKLING_RESULT_VIEW_SCHEMA_V1: &str =
    "structural-native-workbench-model-ir-linear-buckling-result-view.v1";
pub const WORKBENCH_BUCKLING_RESULT_VIEW_DEFAULT_COUNT_V1: u32 = 16;
pub const WORKBENCH_BUCKLING_RESULT_VIEW_MAX_COUNT_V1: u32 = 128;
const CLAIM_BOUNDARY: &str = "bounded_read_only_verified_modelir_frame3d_nodal_reference_load_cpu_linear_buckling_factor_table_not_mode_shape_animation_mixed_tension_member_load_self_weight_nonzero_prescribed_support_shell_sparse_nonlinear_external_validation_engineering_acceptance_or_code_compliance";
pub(crate) const BUCKLING_PRODUCT_FILES: [&str; 18] = [
    "buckling-assembly-receipt.json",
    "checkpoint.eigcp",
    "checkpoint.mbcp",
    "dense-run-receipt.json",
    "generated-dense-request.json",
    "generated-reference-request.json",
    "model-buckling-request.json",
    "model-ir.json",
    "reference-assembly-receipt.json",
    "reference-checkpoint.mlpcp",
    "reference-checkpoint.pcgcp",
    "reference-reaction-ir.json",
    "reference-recovery-ir.json",
    "reference-result-ir.json",
    "report-ir.json",
    "report.md",
    "result-ir.json",
    "run-receipt.json",
];

struct VerifiedBucklingResult {
    model_id: String,
    model_content_hash: String,
    model_semantic_hash: String,
    model_provenance_hash: String,
    analysis_request_hash: String,
    assembly_hash: String,
    generated_request_hash: String,
    outer_checkpoint_hash: String,
    reference_load_pattern_id: String,
    reference_result_hash: String,
    result: structural_contracts::spectral_product::DenseSpectralResultIrV1,
}

/// Verify one complete model-buckling product directory and render a deterministic factor table.
///
/// # Errors
///
/// Rejects noncanonical, missing, extra, symlinked, hash-drifted, identity-mismatched,
/// non-buckling, fallback-bearing, unsafe, or out-of-window inputs before returning text.
pub fn render_model_ir_linear_buckling_result_view_directory(
    directory: &Path,
    locale: WorkbenchReportLocaleV1,
    start_mode: u32,
    count: u32,
) -> Result<String, WorkbenchError> {
    verify_directory_inventory(directory)?;
    let verified = verify_buckling_result(directory)?;
    render_buckling_result_view(&verified, locale, start_mode, count)
}

fn verify_directory_inventory(directory: &Path) -> Result<(), WorkbenchError> {
    let metadata = fs::symlink_metadata(directory).map_err(|error| {
        view_error(
            "workbench_buckling_result_view_directory_invalid",
            &error.to_string(),
        )
    })?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(view_error(
            "workbench_buckling_result_view_directory_invalid",
            "buckling result path must be a non-symlink directory",
        ));
    }
    let mut names = BTreeSet::new();
    for entry in fs::read_dir(directory).map_err(|error| {
        view_error(
            "workbench_buckling_result_view_directory_invalid",
            &error.to_string(),
        )
    })? {
        let entry = entry.map_err(|error| {
            view_error(
                "workbench_buckling_result_view_directory_invalid",
                &error.to_string(),
            )
        })?;
        let name = entry.file_name().into_string().map_err(|_| {
            view_error(
                "workbench_buckling_result_view_directory_invalid",
                "buckling result artifact names must be valid UTF-8",
            )
        })?;
        names.insert(name);
    }
    let expected = BUCKLING_PRODUCT_FILES
        .iter()
        .map(|value| (*value).to_owned())
        .collect::<BTreeSet<_>>();
    if names != expected {
        return Err(view_error(
            "workbench_buckling_result_view_inventory_mismatch",
            "buckling result directory must contain the exact eighteen-artifact inventory",
        ));
    }
    Ok(())
}

#[allow(clippy::too_many_lines)]
fn verify_buckling_result(directory: &Path) -> Result<VerifiedBucklingResult, WorkbenchError> {
    let artifacts = BUCKLING_PRODUCT_FILES
        .iter()
        .map(|name| {
            read_bounded_regular_file(&directory.join(name), MAX_PRODUCT_ARTIFACT_BYTES)
                .map(|bytes| ((*name).to_owned(), bytes))
        })
        .collect::<Result<BTreeMap<_, _>, _>>()?;
    let bytes = |name: &str| {
        artifacts.get(name).map(Vec::as_slice).ok_or_else(|| {
            view_error(
                "workbench_buckling_result_view_inventory_mismatch",
                "verified artifact inventory changed while it was being read",
            )
        })
    };

    let run_receipt = verify_self_hashed_json(bytes("run-receipt.json")?, "receipt_hash")?;
    verify_run_artifact_bindings(&run_receipt, &artifacts)?;
    let model = parse_model_ir_v2(bytes("model-ir.json")?).map_err(|error| {
        view_error(
            "workbench_buckling_result_view_model_invalid",
            &error.to_string(),
        )
    })?;
    let request =
        parse_model_ir_linear_buckling_analysis_request_v1(bytes("model-buckling-request.json")?)
            .map_err(|error| {
            view_error(
                "workbench_buckling_result_view_request_invalid",
                &error.to_string(),
            )
        })?;
    let reference_request =
        parse_model_ir_linear_analysis_request_v1(bytes("generated-reference-request.json")?)
            .map_err(|error| {
                view_error(
                    "workbench_buckling_result_view_reference_invalid",
                    &error.to_string(),
                )
            })?;
    let supplied = &request.request().model_identity;
    if supplied.content_hash != model.content_hash()
        || supplied.semantic_hash != model.semantic_hash()
        || supplied.provenance_hash != model.provenance_hash()
        || reference_request.request().model_identity != *supplied
        || reference_request.request().case_id != request.request().case_id
        || reference_request.request().load_pattern_id
            != request.request().reference_load_pattern_id
        || reference_request.request().config != request.request().reference_linear_config
    {
        return Err(view_error(
            "workbench_buckling_result_view_identity_mismatch",
            "model, outer request, and generated reference request identities do not match",
        ));
    }
    let reference_assembly =
        verify_self_hashed_json(bytes("reference-assembly-receipt.json")?, "assembly_hash")?;
    let reference_assembly_hash = string_field(&reference_assembly, "assembly_hash")?.to_owned();
    let buckling_assembly =
        verify_self_hashed_json(bytes("buckling-assembly-receipt.json")?, "assembly_hash")?;
    let buckling_assembly_hash = string_field(&buckling_assembly, "assembly_hash")?.to_owned();

    let reference_result = parse_sparse_linear_result_ir_v1(bytes("reference-result-ir.json")?)
        .map_err(|error| {
            view_error(
                "workbench_buckling_result_view_reference_invalid",
                &error.to_string(),
            )
        })?;
    let reference_recovery = parse_model_ir_linear_result_recovery_ir_v1(bytes(
        "reference-recovery-ir.json",
    )?)
    .map_err(|error| {
        view_error(
            "workbench_buckling_result_view_reference_invalid",
            &error.to_string(),
        )
    })?;
    verify_model_ir_linear_result_recovery_v1(&reference_result, &reference_recovery).map_err(
        |error| {
            view_error(
                "workbench_buckling_result_view_reference_mismatch",
                &error.to_string(),
            )
        },
    )?;
    let reference_reaction = parse_model_ir_linear_reaction_result_ir_v1(bytes(
        "reference-reaction-ir.json",
    )?)
    .map_err(|error| {
        view_error(
            "workbench_buckling_result_view_reference_invalid",
            &error.to_string(),
        )
    })?;
    verify_model_ir_linear_reaction_result_v1(
        &reference_result,
        &reference_recovery,
        &reference_reaction,
    )
    .map_err(|error| {
        view_error(
            "workbench_buckling_result_view_reference_mismatch",
            &error.to_string(),
        )
    })?;
    let recovery = reference_recovery.recovery();
    if recovery.model_identity != *supplied
        || recovery.analysis_request_hash != reference_request.request_hash()
        || recovery.assembly_hash != reference_assembly_hash
        || recovery.source_result_hash != reference_result.result_hash()
        || recovery.load_pattern_id != request.request().reference_load_pattern_id
        || recovery.fallback_count != 0
    {
        return Err(view_error(
            "workbench_buckling_result_view_reference_mismatch",
            "reference ResultIR/recovery does not match the exact derivation",
        ));
    }

    let generated = parse_dense_spectral_request_v1(bytes("generated-dense-request.json")?)
        .map_err(|error| {
            view_error(
                "workbench_buckling_result_view_request_invalid",
                &error.to_string(),
            )
        })?;
    if generated.request().analysis_kind != SpectralAnalysisKindV1::LinearBuckling
        || generated.request().case_id != request.request().case_id
        || generated.request().config != request.request().buckling_config
    {
        return Err(view_error(
            "workbench_buckling_result_view_identity_mismatch",
            "generated dense request does not match the exact outer buckling request",
        ));
    }
    let checkpoint = ModelIrLinearBucklingCheckpointV1::from_bytes(bytes("checkpoint.mbcp")?)
        .map_err(|error| {
            view_error(
                "workbench_buckling_result_view_checkpoint_invalid",
                &error.to_string(),
            )
        })?;
    let reference_checkpoint = ModelIrLinearCheckpointV1::from_bytes(bytes(
        "reference-checkpoint.mlpcp",
    )?)
    .map_err(|error| {
        view_error(
            "workbench_buckling_result_view_checkpoint_invalid",
            &error.to_string(),
        )
    })?;
    let sparse_checkpoint = SparseLinearCheckpointV1::from_bytes(bytes(
        "reference-checkpoint.pcgcp",
    )?)
    .map_err(|error| {
        view_error(
            "workbench_buckling_result_view_checkpoint_invalid",
            &error.to_string(),
        )
    })?;
    let dense_checkpoint = DenseSpectralCheckpointV1::from_bytes(bytes("checkpoint.eigcp")?)
        .map_err(|error| {
            view_error(
                "workbench_buckling_result_view_checkpoint_invalid",
                &error.to_string(),
            )
        })?;
    if checkpoint.reference().as_bytes() != reference_checkpoint.as_bytes()
        || reference_checkpoint.inner().as_bytes() != sparse_checkpoint.as_bytes()
        || checkpoint.spectral().as_bytes() != dense_checkpoint.as_bytes()
    {
        return Err(view_error(
            "workbench_buckling_result_view_checkpoint_mismatch",
            "outer checkpoint does not contain the exact published reference and spectral phases",
        ));
    }
    checkpoint
        .verify_bindings(&ModelIrLinearBucklingCheckpointBindingsV1 {
            model_content_hash: model.content_hash().to_owned(),
            model_semantic_hash: model.semantic_hash().to_owned(),
            model_provenance_hash: model.provenance_hash().to_owned(),
            analysis_request_hash: request.request_hash().to_owned(),
            generated_reference_request_hash: reference_request.request_hash().to_owned(),
            reference_assembly_hash: reference_assembly_hash.clone(),
            buckling_assembly_hash: buckling_assembly_hash.clone(),
            generated_spectral_request_hash: generated.request_hash().to_owned(),
            reference_result_hash: reference_result.result_hash().to_owned(),
            reference_recovery_hash: reference_recovery.recovery_hash().to_owned(),
        })
        .map_err(|error| {
            view_error(
                "workbench_buckling_result_view_checkpoint_mismatch",
                &error.to_string(),
            )
        })?;

    let result = parse_dense_spectral_result_ir_v1(bytes("result-ir.json")?).map_err(|error| {
        view_error(
            "workbench_buckling_result_view_result_invalid",
            &error.to_string(),
        )
    })?;
    let source = result.result();
    let dense_receipt = dense_checkpoint.receipt();
    if source.analysis_kind != SpectralAnalysisKindV1::LinearBuckling
        || source.case_id != request.request().case_id
        || source.identity.request_hash != generated.request_hash()
        || source.identity.model_hash
            != dense_spectral_model_hash_v1(&generated).map_err(|error| {
                view_error(
                    "workbench_buckling_result_view_identity_mismatch",
                    &error.to_string(),
                )
            })?
        || source.identity.execution_hash
            != dense_spectral_execution_hash_v1(&generated).map_err(|error| {
                view_error(
                    "workbench_buckling_result_view_identity_mismatch",
                    &error.to_string(),
                )
            })?
        || source.identity.state_hash != dense_receipt.state_hash
        || source.identity.checkpoint_hash != dense_receipt.checkpoint_hash
        || source.backend_receipt.fallback_count != 0
    {
        return Err(view_error(
            "workbench_buckling_result_view_identity_mismatch",
            "buckling ResultIR does not match the verified request and checkpoint",
        ));
    }
    let report = parse_dense_spectral_report_ir_v1(bytes("report-ir.json")?).map_err(|error| {
        view_error(
            "workbench_buckling_result_view_report_invalid",
            &error.to_string(),
        )
    })?;
    if report.report().source_result_hash != source.result_hash
        || report.report().identity != source.identity
        || report.report().document_source_hash != sha256_identity(bytes("report.md")?)
        || report.report().summary.mode_count != source.summary.mode_count
    {
        return Err(view_error(
            "workbench_buckling_result_view_report_mismatch",
            "ReportIR does not match the verified buckling ResultIR and Markdown",
        ));
    }
    let dense_run_receipt =
        verify_self_hashed_json(bytes("dense-run-receipt.json")?, "receipt_hash")?;
    if string_field(&dense_run_receipt, "request_hash")? != generated.request_hash()
        || string_field(&run_receipt, "schema_version")?
            != "structural-model-ir-linear-buckling-run-receipt.v1"
        || string_field(&run_receipt, "status")? != "completed"
        || string_field(&run_receipt, "analysis_request_hash")? != request.request_hash()
        || string_field(&run_receipt, "buckling_assembly_hash")? != buckling_assembly_hash
        || string_field(&run_receipt, "generated_dense_request_hash")? != generated.request_hash()
        || run_receipt.get("fallback_count").and_then(Value::as_u64) != Some(0)
    {
        return Err(view_error(
            "workbench_buckling_result_view_receipt_mismatch",
            "run receipts do not match the verified product derivation",
        ));
    }

    Ok(VerifiedBucklingResult {
        model_id: model.model_id().to_owned(),
        model_content_hash: model.content_hash().to_owned(),
        model_semantic_hash: model.semantic_hash().to_owned(),
        model_provenance_hash: model.provenance_hash().to_owned(),
        analysis_request_hash: request.request_hash().to_owned(),
        assembly_hash: buckling_assembly_hash,
        generated_request_hash: generated.request_hash().to_owned(),
        outer_checkpoint_hash: checkpoint.receipt().checkpoint_hash,
        reference_load_pattern_id: request.request().reference_load_pattern_id.clone(),
        reference_result_hash: reference_result.result_hash().to_owned(),
        result: source.clone(),
    })
}

fn verify_run_artifact_bindings(
    receipt: &Value,
    artifacts: &BTreeMap<String, Vec<u8>>,
) -> Result<(), WorkbenchError> {
    let rows = receipt
        .get("artifacts")
        .and_then(Value::as_array)
        .ok_or_else(|| {
            view_error(
                "workbench_buckling_result_view_receipt_invalid",
                "run receipt has no artifact array",
            )
        })?;
    let expected = BUCKLING_PRODUCT_FILES
        .iter()
        .copied()
        .filter(|name| *name != "run-receipt.json")
        .collect::<BTreeSet<_>>();
    let mut seen = BTreeSet::new();
    for row in rows {
        let file = string_field(row, "file")?;
        let content_hash = string_field(row, "content_hash")?;
        let byte_length = row
            .get("byte_length")
            .and_then(Value::as_u64)
            .ok_or_else(|| {
                view_error(
                    "workbench_buckling_result_view_receipt_invalid",
                    "artifact byte length is missing",
                )
            })?;
        let bytes = artifacts.get(file).ok_or_else(|| {
            view_error(
                "workbench_buckling_result_view_receipt_mismatch",
                "run receipt names an absent artifact",
            )
        })?;
        if !seen.insert(file)
            || content_hash != sha256_identity(bytes)
            || byte_length != u64::try_from(bytes.len()).unwrap_or(u64::MAX)
        {
            return Err(view_error(
                "workbench_buckling_result_view_receipt_mismatch",
                "run receipt artifact identity does not match exact bytes",
            ));
        }
    }
    if seen != expected {
        return Err(view_error(
            "workbench_buckling_result_view_receipt_mismatch",
            "run receipt does not bind the complete product inventory",
        ));
    }
    Ok(())
}

#[allow(clippy::too_many_lines)] // Keep the localized deterministic wire-to-text projection auditable.
fn render_buckling_result_view(
    verified: &VerifiedBucklingResult,
    locale: WorkbenchReportLocaleV1,
    start_mode: u32,
    count: u32,
) -> Result<String, WorkbenchError> {
    if start_mode == 0 || count == 0 || count > WORKBENCH_BUCKLING_RESULT_VIEW_MAX_COUNT_V1 {
        return Err(view_error(
            "workbench_buckling_result_view_window_invalid",
            "start mode must be at least 1 and count must be in 1..=128",
        ));
    }
    let start = usize::try_from(start_mode - 1).map_err(|_| {
        view_error(
            "workbench_buckling_result_view_window_invalid",
            "start mode does not fit the native address space",
        )
    })?;
    if start >= verified.result.modes.len() {
        return Err(view_error(
            "workbench_buckling_result_view_window_invalid",
            "start mode exceeds the verified result mode count",
        ));
    }
    let end = start
        .saturating_add(usize::try_from(count).unwrap_or(usize::MAX))
        .min(verified.result.modes.len());
    let ko = locale == WorkbenchReportLocaleV1::KoKr;
    let mut output = String::new();
    push_line(
        &mut output,
        if ko {
            "Structural Native Workbench - ModelIR 선형 좌굴 결과"
        } else {
            "Structural Native Workbench - ModelIR linear buckling result"
        },
    );
    push_field(
        &mut output,
        if ko { "스키마" } else { "Schema" },
        BUCKLING_RESULT_VIEW_SCHEMA_V1,
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
        if ko {
            "기준 하중"
        } else {
            "Reference load"
        },
        &verified.reference_load_pattern_id,
    );
    push_field(
        &mut output,
        if ko {
            "임계 하중계수"
        } else {
            "Critical load factor"
        },
        &format!(
            "{:+.17e}",
            verified
                .result
                .summary
                .critical_load_factor
                .unwrap_or_default()
        ),
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
        if ko {
            "기준 결과 해시"
        } else {
            "Reference result hash"
        },
        &verified.reference_result_hash,
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
            "모드   하중계수              상대 잔차             일반화 K              일반화 Kg             우세 활성 자유도/진폭"
        } else {
            "Mode   Load factor           Relative residual     Generalized K          Generalized Kg         Dominant active DOF/amplitude"
        },
    );
    for (offset, mode) in verified.result.modes[start..end].iter().enumerate() {
        let SpectralModeV1::LinearBuckling {
            load_factor,
            max_component_normalized_shape,
            generalized_elastic_stiffness,
            generalized_geometric_stiffness,
            residual_relative_inf,
            ..
        } = mode
        else {
            return Err(view_error(
                "workbench_buckling_result_view_result_invalid",
                "verified buckling ResultIR contains a non-buckling row",
            ));
        };
        let (dominant, amplitude) = max_component_normalized_shape
            .iter()
            .copied()
            .enumerate()
            .max_by(|left, right| left.1.abs().total_cmp(&right.1.abs()))
            .ok_or_else(|| {
                view_error(
                    "workbench_buckling_result_view_result_invalid",
                    "verified buckling shape has no active components",
                )
            })?;
        writeln!(
            output,
            "{:04}   {:+.17e} {:+.17e} {:+.17e} {:+.17e} {:04}/{:+.17e}",
            start + offset + 1,
            load_factor,
            residual_relative_inf,
            generalized_elastic_stiffness,
            generalized_geometric_stiffness,
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
            "workbench_buckling_result_view_unsafe",
            "buckling result view unexpectedly contains an escape byte",
        ));
    }
    Ok(output)
}

fn string_field<'a>(value: &'a Value, field: &str) -> Result<&'a str, WorkbenchError> {
    value.get(field).and_then(Value::as_str).ok_or_else(|| {
        view_error(
            "workbench_buckling_result_view_receipt_invalid",
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
