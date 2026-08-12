//! Strict bounded nonlinear-static Newton product wire contracts.

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

use crate::legacy_runtime::{NonlinearStaticConfigV3, StaticStoryInputsV3};
use crate::model_ir::{canonicalize_model_ir_v2, decode_json_strict};
use crate::product_ir::{
    sha256_identity, ProductIrContractError, ResultAuthorityV1, ResultIdentityV1,
};

pub const NONLINEAR_STATIC_REQUEST_V1: &str = "structural-nonlinear-static-request.v1";
pub const NONLINEAR_STATIC_RESULT_IR_V1: &str = "structural-nonlinear-static-result-ir.v1";
pub const NONLINEAR_STATIC_REPORT_IR_V1: &str = "structural-nonlinear-static-report-ir.v1";
pub const NONLINEAR_STATIC_MAXIMUM_STORIES: u32 = 100_000;
pub const NONLINEAR_STATIC_MAXIMUM_REQUEST_BYTES: usize = 64 * 1024 * 1024;

const REQUEST_OPERATION: &str = "solve_nonlinear_static_newton";
const MAXIMUM_ITERATIONS: u32 = 1_000_000;
const RESULT_CLAIM_BOUNDARY: &str = "bounded_story_frame_cpu_newton_candidate_not_general_whole_model_shell_assembly_hip_or_engineering_acceptance";
const REPORT_CLAIM_BOUNDARY: &str = "deterministic_projection_of_one_bounded_story_frame_cpu_newton_candidate_not_engineering_acceptance_or_design_code_compliance";

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum NonlinearStaticBackendV1 {
    Cpu,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NonlinearStaticAnalysisRequestV1 {
    pub schema_version: String,
    pub operation: String,
    pub case_id: String,
    pub backend: NonlinearStaticBackendV1,
    pub config: NonlinearStaticConfigV3,
    pub inputs: StaticStoryInputsV3,
}

#[derive(Clone, Debug)]
pub struct NonlinearStaticAnalysisRequestDocumentV1 {
    request: NonlinearStaticAnalysisRequestV1,
    canonical_json: String,
    request_hash: String,
}

impl NonlinearStaticAnalysisRequestDocumentV1 {
    #[must_use]
    pub const fn request(&self) -> &NonlinearStaticAnalysisRequestV1 {
        &self.request
    }

    #[must_use]
    pub fn canonical_json(&self) -> &str {
        &self.canonical_json
    }

    #[must_use]
    pub fn canonical_bytes(&self) -> &[u8] {
        self.canonical_json.as_bytes()
    }

    #[must_use]
    pub fn request_hash(&self) -> &str {
        &self.request_hash
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NonlinearStaticUnitsV1 {
    pub displacement: String,
    pub force: String,
    pub stiffness: String,
    pub coordinate_frame: String,
}

impl Default for NonlinearStaticUnitsV1 {
    fn default() -> Self {
        Self {
            displacement: "m".to_owned(),
            force: "N".to_owned(),
            stiffness: "N_per_m".to_owned(),
            coordinate_frame: "global_story_axis".to_owned(),
        }
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NonlinearStaticCpuExecutionReceiptV1 {
    pub backend: NonlinearStaticBackendV1,
    pub precision: String,
    pub abi_version: String,
    pub deterministic_policy: String,
    pub fallback_count: u32,
    pub h2d_bytes: u64,
    pub d2h_bytes: u64,
    pub sync_count: u64,
}

impl Default for NonlinearStaticCpuExecutionReceiptV1 {
    fn default() -> Self {
        Self {
            backend: NonlinearStaticBackendV1::Cpu,
            precision: "fp64".to_owned(),
            abi_version: "0x0001000b".to_owned(),
            deterministic_policy: "serial_fixed_order_story_frame_newton_restart".to_owned(),
            fallback_count: 0,
            h2d_bytes: 0,
            d2h_bytes: 0,
            sync_count: 0,
        }
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NonlinearStaticResultSummaryV1 {
    pub story_count: u32,
    pub iterations: u32,
    pub residual_inf: f64,
    pub residual_l2: f64,
    pub max_abs_displacement_m: f64,
    pub top_displacement_m: f64,
    pub base_shear_kn: f64,
    pub plastic_story_count: u32,
    pub line_search_backtracks: u32,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NonlinearStaticResultIrV1 {
    pub schema_version: String,
    pub case_id: String,
    pub authority: ResultAuthorityV1,
    pub units: NonlinearStaticUnitsV1,
    pub identity: ResultIdentityV1,
    pub backend_receipt: NonlinearStaticCpuExecutionReceiptV1,
    pub summary: NonlinearStaticResultSummaryV1,
    pub displacement_m: Vec<f64>,
    pub claim_boundary: String,
    pub result_hash: String,
}

#[derive(Clone, Debug)]
pub struct NonlinearStaticResultIrDocumentV1 {
    result: NonlinearStaticResultIrV1,
    canonical_json: String,
}

impl NonlinearStaticResultIrDocumentV1 {
    #[must_use]
    pub const fn result(&self) -> &NonlinearStaticResultIrV1 {
        &self.result
    }

    #[must_use]
    pub fn canonical_json(&self) -> &str {
        &self.canonical_json
    }

    #[must_use]
    pub fn canonical_bytes(&self) -> &[u8] {
        self.canonical_json.as_bytes()
    }

    #[must_use]
    pub fn result_hash(&self) -> &str {
        &self.result.result_hash
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NonlinearStaticReportSummaryV1 {
    pub story_count: u32,
    pub iterations: u32,
    pub residual_inf: f64,
    pub max_abs_displacement_m: f64,
    pub top_displacement_m: f64,
    pub base_shear_kn: f64,
    pub plastic_story_count: u32,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NonlinearStaticReportIrV1 {
    pub schema_version: String,
    pub report_kind: String,
    pub case_id: String,
    pub authority: ResultAuthorityV1,
    pub source_result_hash: String,
    pub identity: ResultIdentityV1,
    pub summary: NonlinearStaticReportSummaryV1,
    pub document_source_hash: String,
    pub claim_boundary: String,
    pub report_hash: String,
}

#[derive(Clone, Debug)]
pub struct NonlinearStaticReportIrDocumentV1 {
    report: NonlinearStaticReportIrV1,
    canonical_json: String,
}

impl NonlinearStaticReportIrDocumentV1 {
    #[must_use]
    pub const fn report(&self) -> &NonlinearStaticReportIrV1 {
        &self.report
    }

    #[must_use]
    pub fn canonical_json(&self) -> &str {
        &self.canonical_json
    }

    #[must_use]
    pub fn report_hash(&self) -> &str {
        &self.report.report_hash
    }
}

/// Strictly decode, validate, canonicalize, and hash one bounded story-frame request.
///
/// # Errors
///
/// Returns a stable contract error for malformed, duplicate, unknown, oversized, non-finite, or
/// dimensionally inconsistent input.
pub fn parse_nonlinear_static_request_v1(
    bytes: &[u8],
) -> Result<NonlinearStaticAnalysisRequestDocumentV1, ProductIrContractError> {
    if bytes.is_empty() || bytes.len() > NONLINEAR_STATIC_MAXIMUM_REQUEST_BYTES {
        return Err(error(
            "static_request_size_invalid",
            "/",
            "nonlinear-static request bytes are outside the bounded product domain",
        ));
    }
    let value = strict_value(bytes, "static_request")?;
    let request: NonlinearStaticAnalysisRequestV1 =
        serde_json::from_value(value.clone()).map_err(|_| {
            error(
                "static_request_decode_failed",
                "/",
                "nonlinear-static request has unknown, missing, or mistyped fields",
            )
        })?;
    validate_request(&request)?;
    let canonical_json = canonical_value(&value, "static_request_canonicalization_failed")?;
    validate_canonical_request_size(&canonical_json)?;
    Ok(NonlinearStaticAnalysisRequestDocumentV1 {
        request_hash: sha256_identity(canonical_json.as_bytes()),
        request,
        canonical_json,
    })
}

/// Build one canonical nonlinear-static request from typed values.
///
/// # Errors
///
/// Returns a stable contract error when typed values violate the bounded domain.
pub fn build_nonlinear_static_request_v1(
    request: NonlinearStaticAnalysisRequestV1,
) -> Result<NonlinearStaticAnalysisRequestDocumentV1, ProductIrContractError> {
    validate_request(&request)?;
    let canonical_json = canonical_struct(&request, "static_request_canonicalization_failed")?;
    validate_canonical_request_size(&canonical_json)?;
    Ok(NonlinearStaticAnalysisRequestDocumentV1 {
        request_hash: sha256_identity(canonical_json.as_bytes()),
        request,
        canonical_json,
    })
}

/// Exact story model, material law, forcing, and units identity.
///
/// # Errors
///
/// Returns a contract error if canonical identity construction fails.
pub fn nonlinear_static_model_hash_v1(
    request: &NonlinearStaticAnalysisRequestDocumentV1,
) -> Result<String, ProductIrContractError> {
    let value = json!({
        "domain": "structural-nonlinear-static-model.v1",
        "story_count": request.request.config.story_count,
        "hardening_ratio": request.request.config.hardening_ratio,
        "pdelta_factor": request.request.config.pdelta_factor,
        "inputs": &request.request.inputs,
        "units": NonlinearStaticUnitsV1::default(),
    });
    Ok(sha256_identity(
        canonical_value(&value, "static_model_hash_failed")?.as_bytes(),
    ))
}

/// Exact backend, Newton controls, ABI, and algorithm identity.
///
/// # Errors
///
/// Returns a contract error if canonical identity construction fails.
pub fn nonlinear_static_execution_hash_v1(
    request: &NonlinearStaticAnalysisRequestDocumentV1,
) -> Result<String, ProductIrContractError> {
    let config = &request.request.config;
    let value = json!({
        "domain": "structural-nonlinear-static-execution.v1",
        "backend": request.request.backend,
        "max_iter": config.max_iter,
        "tolerance": config.tolerance,
        "line_search_decay": config.line_search_decay,
        "line_search_min": config.line_search_min,
        "abi_version": "0x0001000b",
        "algorithm": "cpp-fp64-serial-story-frame-newton-restart.v1",
    });
    Ok(sha256_identity(
        canonical_value(&value, "static_execution_hash_failed")?.as_bytes(),
    ))
}

/// Build a self-hashed `ResultIR` bound to one exact request and checkpoint.
///
/// # Errors
///
/// Returns a stable contract error when bindings, result shape, convergence, or constitutive
/// recovery disagree with the request.
pub fn build_nonlinear_static_result_ir_v1(
    request: &NonlinearStaticAnalysisRequestDocumentV1,
    identity: ResultIdentityV1,
    summary: NonlinearStaticResultSummaryV1,
    displacement_m: Vec<f64>,
) -> Result<NonlinearStaticResultIrDocumentV1, ProductIrContractError> {
    if identity.request_hash != request.request_hash {
        return Err(error(
            "static_result_request_hash_mismatch",
            "/identity/request_hash",
            "nonlinear-static ResultIR request hash differs from the supplied request",
        ));
    }
    if identity.model_hash != nonlinear_static_model_hash_v1(request)? {
        return Err(error(
            "static_result_model_hash_mismatch",
            "/identity/model_hash",
            "nonlinear-static ResultIR model hash differs from the exact story model",
        ));
    }
    if identity.execution_hash != nonlinear_static_execution_hash_v1(request)? {
        return Err(error(
            "static_result_execution_hash_mismatch",
            "/identity/execution_hash",
            "nonlinear-static ResultIR execution hash differs from the exact Newton controls",
        ));
    }
    let mut result = NonlinearStaticResultIrV1 {
        schema_version: NONLINEAR_STATIC_RESULT_IR_V1.to_owned(),
        case_id: request.request.case_id.clone(),
        authority: ResultAuthorityV1::BoundedCandidate,
        units: NonlinearStaticUnitsV1::default(),
        identity,
        backend_receipt: NonlinearStaticCpuExecutionReceiptV1::default(),
        summary,
        displacement_m,
        claim_boundary: RESULT_CLAIM_BOUNDARY.to_owned(),
        result_hash: String::new(),
    };
    validate_result(&result, Some(request.request()))?;
    result.result_hash = hash_without_field(&result, "result_hash", "static_result_hash_failed")?;
    let canonical_json = canonical_struct(&result, "static_result_canonicalization_failed")?;
    Ok(NonlinearStaticResultIrDocumentV1 {
        result,
        canonical_json,
    })
}

/// Strictly decode and self-verify one nonlinear-static `ResultIR`.
///
/// # Errors
///
/// Returns a stable contract error for malformed/noncanonical data or a mismatched self-hash.
pub fn parse_nonlinear_static_result_ir_v1(
    bytes: &[u8],
) -> Result<NonlinearStaticResultIrDocumentV1, ProductIrContractError> {
    let value = strict_value(bytes, "static_result")?;
    let result: NonlinearStaticResultIrV1 = serde_json::from_value(value).map_err(|_| {
        error(
            "static_result_decode_failed",
            "/",
            "nonlinear-static ResultIR fields do not satisfy the typed v1 contract",
        )
    })?;
    validate_result(&result, None)?;
    let expected = hash_without_field(&result, "result_hash", "static_result_hash_failed")?;
    if result.result_hash != expected {
        return Err(error(
            "static_result_hash_mismatch",
            "/result_hash",
            "nonlinear-static ResultIR self-hash does not match its canonical payload",
        ));
    }
    let canonical_json = canonical_struct(&result, "static_result_canonicalization_failed")?;
    Ok(NonlinearStaticResultIrDocumentV1 {
        result,
        canonical_json,
    })
}

/// Build a self-hashed `ReportIR` bound to exact result and document bytes.
///
/// # Errors
///
/// Returns a stable contract error when report authority or identity is invalid.
pub fn build_nonlinear_static_report_ir_v1(
    result: &NonlinearStaticResultIrDocumentV1,
    document_source: &[u8],
) -> Result<NonlinearStaticReportIrDocumentV1, ProductIrContractError> {
    let source = result.result();
    let mut report = NonlinearStaticReportIrV1 {
        schema_version: NONLINEAR_STATIC_REPORT_IR_V1.to_owned(),
        report_kind: "nonlinear_static_summary".to_owned(),
        case_id: source.case_id.clone(),
        authority: ResultAuthorityV1::BoundedCandidate,
        source_result_hash: source.result_hash.clone(),
        identity: source.identity.clone(),
        summary: NonlinearStaticReportSummaryV1 {
            story_count: source.summary.story_count,
            iterations: source.summary.iterations,
            residual_inf: source.summary.residual_inf,
            max_abs_displacement_m: source.summary.max_abs_displacement_m,
            top_displacement_m: source.summary.top_displacement_m,
            base_shear_kn: source.summary.base_shear_kn,
            plastic_story_count: source.summary.plastic_story_count,
        },
        document_source_hash: sha256_identity(document_source),
        claim_boundary: REPORT_CLAIM_BOUNDARY.to_owned(),
        report_hash: String::new(),
    };
    validate_report(&report)?;
    report.report_hash = hash_without_field(&report, "report_hash", "static_report_hash_failed")?;
    let canonical_json = canonical_struct(&report, "static_report_canonicalization_failed")?;
    Ok(NonlinearStaticReportIrDocumentV1 {
        report,
        canonical_json,
    })
}

/// Strictly decode and self-verify one nonlinear-static `ReportIR`.
///
/// # Errors
///
/// Returns a stable contract error for invalid typed fields or self-hash mismatch.
pub fn parse_nonlinear_static_report_ir_v1(
    bytes: &[u8],
) -> Result<NonlinearStaticReportIrDocumentV1, ProductIrContractError> {
    let value = strict_value(bytes, "static_report")?;
    let report: NonlinearStaticReportIrV1 = serde_json::from_value(value).map_err(|_| {
        error(
            "static_report_decode_failed",
            "/",
            "nonlinear-static ReportIR fields do not satisfy the typed v1 contract",
        )
    })?;
    validate_report(&report)?;
    let expected = hash_without_field(&report, "report_hash", "static_report_hash_failed")?;
    if report.report_hash != expected {
        return Err(error(
            "static_report_hash_mismatch",
            "/report_hash",
            "nonlinear-static ReportIR self-hash does not match its canonical payload",
        ));
    }
    let canonical_json = canonical_struct(&report, "static_report_canonicalization_failed")?;
    Ok(NonlinearStaticReportIrDocumentV1 {
        report,
        canonical_json,
    })
}

fn validate_request(
    request: &NonlinearStaticAnalysisRequestV1,
) -> Result<(), ProductIrContractError> {
    if request.schema_version != NONLINEAR_STATIC_REQUEST_V1 {
        return Err(error(
            "static_request_schema_version_invalid",
            "/schema_version",
            "nonlinear-static request schema version is unsupported",
        ));
    }
    if request.operation != REQUEST_OPERATION {
        return Err(error(
            "static_request_operation_invalid",
            "/operation",
            "nonlinear-static request operation is unsupported",
        ));
    }
    if !valid_case_id(&request.case_id) {
        return Err(error(
            "static_request_case_id_invalid",
            "/case_id",
            "case_id must be 1..128 portable identifier bytes",
        ));
    }
    let config = &request.config;
    if !(1..=NONLINEAR_STATIC_MAXIMUM_STORIES).contains(&config.story_count) {
        return Err(error(
            "static_request_story_count_invalid",
            "/config/story_count",
            "story_count is outside the bounded product domain",
        ));
    }
    let count = usize::try_from(config.story_count).map_err(|_| {
        error(
            "static_request_story_count_invalid",
            "/config/story_count",
            "story_count exceeds the address space",
        )
    })?;
    let inputs = &request.inputs;
    if [
        inputs.story_k_n_per_m.len(),
        inputs.story_h_m.len(),
        inputs.story_axial_n.len(),
        inputs.story_yield_drift_m.len(),
        inputs.floor_load_n.len(),
    ]
    .into_iter()
    .any(|length| length != count)
    {
        return Err(error(
            "static_request_dimensions_invalid",
            "/inputs",
            "all story vectors must exactly match story_count",
        ));
    }
    let scalars = [
        config.tolerance,
        config.hardening_ratio,
        config.line_search_decay,
        config.line_search_min,
        config.pdelta_factor,
    ];
    let config_valid = (1..=MAXIMUM_ITERATIONS).contains(&config.max_iter)
        && scalars.into_iter().all(f64::is_finite)
        && config.tolerance > 0.0
        && (0.0..=1.0).contains(&config.hardening_ratio)
        && config.line_search_decay > 0.0
        && config.line_search_decay < 1.0
        && config.line_search_min > 0.0
        && config.line_search_min <= 1.0
        && config.pdelta_factor >= 0.0;
    if !config_valid {
        return Err(error(
            "static_request_config_invalid",
            "/config",
            "nonlinear-static Newton configuration is outside the bounded domain",
        ));
    }
    for (values, path) in [
        (&inputs.story_k_n_per_m, "/inputs/story_k_n_per_m"),
        (&inputs.story_h_m, "/inputs/story_h_m"),
        (&inputs.story_axial_n, "/inputs/story_axial_n"),
        (&inputs.story_yield_drift_m, "/inputs/story_yield_drift_m"),
        (&inputs.floor_load_n, "/inputs/floor_load_n"),
    ] {
        validate_finite_slice(values, path)?;
    }
    if inputs.story_k_n_per_m.iter().any(|value| *value <= 0.0)
        || inputs.story_h_m.iter().any(|value| *value <= 0.0)
    {
        return Err(error(
            "static_request_physical_input_invalid",
            "/inputs",
            "story stiffness and height must be positive",
        ));
    }
    Ok(())
}

fn validate_result(
    result: &NonlinearStaticResultIrV1,
    request: Option<&NonlinearStaticAnalysisRequestV1>,
) -> Result<(), ProductIrContractError> {
    if result.schema_version != NONLINEAR_STATIC_RESULT_IR_V1
        || result.claim_boundary != RESULT_CLAIM_BOUNDARY
        || result.authority != ResultAuthorityV1::BoundedCandidate
        || result.units != NonlinearStaticUnitsV1::default()
        || result.backend_receipt != NonlinearStaticCpuExecutionReceiptV1::default()
        || !valid_case_id(&result.case_id)
    {
        return Err(error(
            "static_result_authority_invalid",
            "/",
            "nonlinear-static ResultIR authority, units, or CPU receipt is invalid",
        ));
    }
    validate_hashes(&result.identity)?;
    validate_hash(&result.result_hash, "/result_hash", true)?;
    let summary = &result.summary;
    let metrics = [
        summary.residual_inf,
        summary.residual_l2,
        summary.max_abs_displacement_m,
        summary.top_displacement_m,
        summary.base_shear_kn,
    ];
    if summary.story_count == 0
        || summary.story_count > NONLINEAR_STATIC_MAXIMUM_STORIES
        || usize::try_from(summary.story_count).ok() != Some(result.displacement_m.len())
        || summary.iterations == 0
        || summary.iterations > MAXIMUM_ITERATIONS
        || summary.plastic_story_count > summary.story_count
        || metrics.into_iter().any(|value| !value.is_finite())
        || summary.residual_inf < 0.0
        || summary.residual_l2 < 0.0
        || summary.max_abs_displacement_m < 0.0
        || summary.base_shear_kn < 0.0
        || result.displacement_m.iter().any(|value| !value.is_finite())
    {
        return Err(error(
            "static_result_shape_invalid",
            "/",
            "nonlinear-static ResultIR shape or finite metrics are invalid",
        ));
    }
    if let Some(request) = request {
        if result.case_id != request.case_id
            || summary.story_count != request.config.story_count
            || summary.iterations > request.config.max_iter
            || summary.residual_inf > request.config.tolerance
        {
            return Err(error(
                "static_result_request_shape_mismatch",
                "/summary",
                "nonlinear-static ResultIR does not match the exact converged request",
            ));
        }
        let expected = derived_response(request, &result.displacement_m)?;
        let recovered = summary.residual_inf.to_bits() == expected.residual_inf.to_bits()
            && summary.residual_l2.to_bits() == expected.residual_l2.to_bits()
            && summary.max_abs_displacement_m.to_bits()
                == expected.max_abs_displacement_m.to_bits()
            && summary.top_displacement_m.to_bits() == expected.top_displacement_m.to_bits()
            && summary.base_shear_kn.to_bits() == expected.base_shear_kn.to_bits()
            && summary.plastic_story_count == expected.plastic_story_count;
        if !recovered {
            return Err(error(
                "static_result_recovery_invalid",
                "/summary",
                "nonlinear-static result metrics disagree with deterministic constitutive recovery",
            ));
        }
    }
    Ok(())
}

fn validate_report(report: &NonlinearStaticReportIrV1) -> Result<(), ProductIrContractError> {
    let summary = &report.summary;
    let metrics = [
        summary.residual_inf,
        summary.max_abs_displacement_m,
        summary.top_displacement_m,
        summary.base_shear_kn,
    ];
    if report.schema_version != NONLINEAR_STATIC_REPORT_IR_V1
        || report.report_kind != "nonlinear_static_summary"
        || report.claim_boundary != REPORT_CLAIM_BOUNDARY
        || report.authority != ResultAuthorityV1::BoundedCandidate
        || !valid_case_id(&report.case_id)
        || summary.story_count == 0
        || summary.story_count > NONLINEAR_STATIC_MAXIMUM_STORIES
        || summary.iterations == 0
        || summary.plastic_story_count > summary.story_count
        || metrics.into_iter().any(|value| !value.is_finite())
        || summary.residual_inf < 0.0
        || summary.max_abs_displacement_m < 0.0
        || summary.base_shear_kn < 0.0
    {
        return Err(error(
            "static_report_invariant_invalid",
            "/",
            "nonlinear-static ReportIR fixed fields or summary are invalid",
        ));
    }
    validate_hash(&report.source_result_hash, "/source_result_hash", false)?;
    validate_hash(&report.document_source_hash, "/document_source_hash", false)?;
    validate_hash(&report.report_hash, "/report_hash", true)?;
    validate_hashes(&report.identity)
}

struct DerivedResponse {
    residual_inf: f64,
    residual_l2: f64,
    max_abs_displacement_m: f64,
    top_displacement_m: f64,
    base_shear_kn: f64,
    plastic_story_count: u32,
}

fn derived_response(
    request: &NonlinearStaticAnalysisRequestV1,
    displacement_m: &[f64],
) -> Result<DerivedResponse, ProductIrContractError> {
    let count = usize::try_from(request.config.story_count).map_err(|_| {
        error(
            "static_result_story_count_invalid",
            "/summary/story_count",
            "story_count exceeds the address space",
        )
    })?;
    if displacement_m.len() != count {
        return Err(error(
            "static_result_displacement_length_invalid",
            "/displacement_m",
            "displacement length differs from story_count",
        ));
    }
    let mut spring_force = vec![0.0; count];
    let mut plastic_story_count = 0_u32;
    for index in 0..count {
        let previous = if index == 0 {
            0.0
        } else {
            displacement_m[index - 1]
        };
        let drift = displacement_m[index] - previous;
        let initial = request.inputs.story_k_n_per_m[index].max(1.0e-12);
        let yield_drift = request.inputs.story_yield_drift_m[index].abs().max(1.0e-9);
        if drift.abs() <= yield_drift {
            spring_force[index] = initial * drift;
        } else {
            let sign = if drift >= 0.0 { 1.0 } else { -1.0 };
            spring_force[index] = sign
                * (initial * yield_drift
                    + request.config.hardening_ratio * initial * (drift.abs() - yield_drift));
            plastic_story_count += 1;
        }
    }
    let mut residual_inf = 0.0_f64;
    let mut residual_square_sum = 0.0_f64;
    for index in 0..count {
        let internal = if index < count - 1 {
            spring_force[index] - spring_force[index + 1]
        } else {
            spring_force[index]
        };
        let residual = request.inputs.floor_load_n[index] - internal;
        residual_inf = residual_inf.max(residual.abs());
        residual_square_sum += residual * residual;
    }
    Ok(DerivedResponse {
        residual_inf,
        residual_l2: residual_square_sum.sqrt(),
        max_abs_displacement_m: displacement_m
            .iter()
            .fold(0.0_f64, |maximum, value| maximum.max(value.abs())),
        top_displacement_m: displacement_m[count - 1],
        base_shear_kn: spring_force[0].abs() / 1000.0,
        plastic_story_count,
    })
}

fn validate_canonical_request_size(value: &str) -> Result<(), ProductIrContractError> {
    if value.is_empty() || value.len() > NONLINEAR_STATIC_MAXIMUM_REQUEST_BYTES {
        Err(error(
            "static_request_size_invalid",
            "/",
            "canonical nonlinear-static request exceeds the bounded product size",
        ))
    } else {
        Ok(())
    }
}

fn valid_case_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.'))
}

fn validate_finite_slice(values: &[f64], path: &str) -> Result<(), ProductIrContractError> {
    if values.iter().any(|value| !value.is_finite()) {
        Err(error(
            "static_nonfinite_value",
            path,
            "nonlinear-static product contracts accept only finite binary64 values",
        ))
    } else {
        Ok(())
    }
}

fn validate_hashes(identity: &ResultIdentityV1) -> Result<(), ProductIrContractError> {
    validate_hash(&identity.request_hash, "/identity/request_hash", false)?;
    validate_hash(&identity.model_hash, "/identity/model_hash", false)?;
    validate_hash(&identity.state_hash, "/identity/state_hash", false)?;
    validate_hash(&identity.execution_hash, "/identity/execution_hash", false)?;
    validate_hash(
        &identity.checkpoint_hash,
        "/identity/checkpoint_hash",
        false,
    )
}

fn validate_hash(value: &str, path: &str, allow_empty: bool) -> Result<(), ProductIrContractError> {
    if allow_empty && value.is_empty() {
        return Ok(());
    }
    let digest = value.strip_prefix("sha256:").unwrap_or_default();
    if digest.len() == 64
        && digest
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        Ok(())
    } else {
        Err(error(
            "static_hash_invalid",
            path,
            "hash must be sha256 plus 64 lowercase hexadecimal digits",
        ))
    }
}

fn strict_value(bytes: &[u8], family: &str) -> Result<Value, ProductIrContractError> {
    decode_json_strict(bytes).map_err(|source| {
        error(
            &format!("{family}_wire_invalid"),
            &source.path,
            &source.detail,
        )
    })
}

fn canonical_value(value: &Value, code: &str) -> Result<String, ProductIrContractError> {
    canonicalize_model_ir_v2(value).map_err(|_| {
        error(
            code,
            "/",
            "nonlinear-static value cannot be represented as canonical JSON",
        )
    })
}

fn canonical_struct<T: Serialize>(value: &T, code: &str) -> Result<String, ProductIrContractError> {
    let value = serde_json::to_value(value).map_err(|_| {
        error(
            code,
            "/",
            "typed nonlinear-static value cannot be represented as JSON",
        )
    })?;
    canonical_value(&value, code)
}

fn hash_without_field<T: Serialize>(
    value: &T,
    field: &str,
    code: &str,
) -> Result<String, ProductIrContractError> {
    let mut value = serde_json::to_value(value).map_err(|_| {
        error(
            code,
            "/",
            "typed nonlinear-static value cannot be represented as JSON",
        )
    })?;
    value
        .as_object_mut()
        .and_then(|object| object.remove(field))
        .ok_or_else(|| error(code, "/", "nonlinear-static self-hash field is missing"))?;
    Ok(sha256_identity(canonical_value(&value, code)?.as_bytes()))
}

fn error(code: &str, path: &str, detail: &str) -> ProductIrContractError {
    ProductIrContractError {
        code: code.to_owned(),
        path: path.to_owned(),
        detail: detail.to_owned(),
    }
}
