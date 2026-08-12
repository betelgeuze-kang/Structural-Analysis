//! Strict bounded-product request, `ResultIR` and `ReportIR` wire contracts.

use std::fmt;
use std::sync::OnceLock;

use jsonschema::{Draft, JSONSchema};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};

use crate::legacy_runtime::{NdthaResponseV3, NdthaStoryInputsV3, NonlinearNdthaConfigV3};
use crate::model_ir::{canonicalize_model_ir_v2, decode_json_strict};

pub const NATIVE_ANALYSIS_REQUEST_V1: &str = "structural-native-analysis-request.v1";
pub const NONLINEAR_NDTHA_RESULT_IR_V1: &str = "structural-native-nonlinear-ndtha-result-ir.v1";
pub const NONLINEAR_NDTHA_REPORT_IR_V1: &str = "structural-native-nonlinear-ndtha-report-ir.v1";

const REQUEST_SCHEMA_TEXT: &str = include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/schemas/native_analysis_request_v1.schema.json"
));
const RESULT_CLAIM_BOUNDARY: &str = "bounded_candidate_for_the_declared_cpu_nonlinear_ndtha_profile_not_broader_solver_or_hip_authority";
const REPORT_CLAIM_BOUNDARY: &str = "deterministic_projection_of_one_bounded_candidate_result_not_engineering_acceptance_or_design_code_compliance";
static REQUEST_SCHEMA_VALIDATOR: OnceLock<Result<JSONSchema, String>> = OnceLock::new();

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ProductIrContractError {
    pub code: String,
    pub path: String,
    pub detail: String,
}

impl fmt::Display for ProductIrContractError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{} at {}: {}", self.code, self.path, self.detail)
    }
}

impl std::error::Error for ProductIrContractError {}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum NativeAnalysisBackendV1 {
    Cpu,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NativeAnalysisRequestV1 {
    pub schema_version: String,
    pub operation: String,
    pub case_id: String,
    pub backend: NativeAnalysisBackendV1,
    pub config: NonlinearNdthaConfigV3,
    pub inputs: NdthaStoryInputsV3,
}

#[derive(Clone, Debug)]
pub struct NativeAnalysisRequestDocumentV1 {
    request: NativeAnalysisRequestV1,
    canonical_json: String,
    request_hash: String,
}

impl NativeAnalysisRequestDocumentV1 {
    #[must_use]
    pub fn request(&self) -> &NativeAnalysisRequestV1 {
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

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ResultAuthorityV1 {
    BoundedCandidate,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum NonlinearNdthaTerminalStatusV1 {
    Completed,
    Collapsed,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ResultUnitsV1 {
    pub displacement: String,
    pub force: String,
    pub mass: String,
    pub time: String,
    pub drift_ratio: String,
    pub coordinate_frame: String,
}

impl Default for ResultUnitsV1 {
    fn default() -> Self {
        Self {
            displacement: "m".to_owned(),
            force: "N".to_owned(),
            mass: "kg".to_owned(),
            time: "s".to_owned(),
            drift_ratio: "percent".to_owned(),
            coordinate_frame: "global_story_axis".to_owned(),
        }
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ResultIdentityV1 {
    pub request_hash: String,
    pub model_hash: String,
    pub state_hash: String,
    pub execution_hash: String,
    pub checkpoint_hash: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CpuExecutionReceiptV1 {
    pub backend: NativeAnalysisBackendV1,
    pub precision: String,
    pub abi_version: String,
    pub deterministic_policy: String,
    pub fallback_count: u32,
    pub h2d_bytes: u64,
    pub d2h_bytes: u64,
    pub sync_count: u64,
}

impl Default for CpuExecutionReceiptV1 {
    fn default() -> Self {
        Self {
            backend: NativeAnalysisBackendV1::Cpu,
            precision: "fp64".to_owned(),
            abi_version: "0x00010005".to_owned(),
            deterministic_policy: "serial_fixed_order".to_owned(),
            fallback_count: 0,
            h2d_bytes: 0,
            d2h_bytes: 0,
            sync_count: 0,
        }
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NonlinearNdthaResultSummaryV1 {
    pub terminal_status: NonlinearNdthaTerminalStatusV1,
    pub step_count_completed: u32,
    pub max_plastic_story_count: u32,
    pub max_drift_ratio_pct: f64,
    pub adaptive_iteration_sum: u64,
    pub avg_step_iterations: f64,
    pub total_line_search_backtracks: u32,
    pub collapse_step: i32,
    pub collapse_time_s: f64,
    pub collapse_drift_ratio_pct: f64,
    pub collapse_top_displacement_m: f64,
    pub residual_top_displacement_m: f64,
    pub residual_drift_ratio_pct: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NonlinearNdthaResultIrV1 {
    pub schema_version: String,
    pub analysis_kind: String,
    pub case_id: String,
    pub authority: ResultAuthorityV1,
    pub units: ResultUnitsV1,
    pub identity: ResultIdentityV1,
    pub backend_receipt: CpuExecutionReceiptV1,
    pub summary: NonlinearNdthaResultSummaryV1,
    pub response: NdthaResponseV3,
    pub claim_boundary: String,
    pub result_hash: String,
}

#[derive(Clone, Debug)]
pub struct NonlinearNdthaResultIrDocumentV1 {
    result: NonlinearNdthaResultIrV1,
    canonical_json: String,
}

impl NonlinearNdthaResultIrDocumentV1 {
    #[must_use]
    pub fn result(&self) -> &NonlinearNdthaResultIrV1 {
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
pub struct NonlinearNdthaReportSummaryV1 {
    pub terminal_status: NonlinearNdthaTerminalStatusV1,
    pub step_count_completed: u32,
    pub max_drift_ratio_pct: f64,
    pub max_plastic_story_count: u32,
    pub residual_top_displacement_m: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NonlinearNdthaReportIrV1 {
    pub schema_version: String,
    pub report_kind: String,
    pub case_id: String,
    pub authority: ResultAuthorityV1,
    pub source_result_hash: String,
    pub identity: ResultIdentityV1,
    pub summary: NonlinearNdthaReportSummaryV1,
    pub document_source_hash: String,
    pub claim_boundary: String,
    pub report_hash: String,
}

#[derive(Clone, Debug)]
pub struct NonlinearNdthaReportIrDocumentV1 {
    report: NonlinearNdthaReportIrV1,
    canonical_json: String,
}

impl NonlinearNdthaReportIrDocumentV1 {
    #[must_use]
    pub fn report(&self) -> &NonlinearNdthaReportIrV1 {
        &self.report
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
    pub fn report_hash(&self) -> &str {
        &self.report.report_hash
    }
}

/// Decode, schema-check and canonicalize one bounded CPU analysis request.
///
/// # Errors
///
/// Returns a stable error for malformed UTF-8/JSON, duplicate or unknown fields, schema
/// violations, non-finite values or count/vector disagreement.
pub fn parse_native_analysis_request_v1(
    bytes: &[u8],
) -> Result<NativeAnalysisRequestDocumentV1, ProductIrContractError> {
    let value = strict_value(bytes, "request")?;
    validate_request_schema(&value)?;
    let request: NativeAnalysisRequestV1 = serde_json::from_value(value.clone()).map_err(|_| {
        contract_error(
            "native_analysis_request_decode_failed",
            "/",
            "validated native analysis request could not be decoded",
        )
    })?;
    validate_request_lengths(&request)?;
    let canonical_json = canonicalize(&value, "native_analysis_request_canonicalization_failed")?;
    Ok(NativeAnalysisRequestDocumentV1 {
        request_hash: sha256_identity(canonical_json.as_bytes()),
        request,
        canonical_json,
    })
}

/// Build immutable canonical `ResultIR` from one terminal native state projection.
///
/// # Errors
///
/// Returns a stable error for invalid identities, terminal-state inconsistency, response length
/// drift, non-finite values or canonical serialization failure.
pub fn build_nonlinear_ndtha_result_ir_v1(
    request: &NativeAnalysisRequestDocumentV1,
    identity: ResultIdentityV1,
    summary: NonlinearNdthaResultSummaryV1,
    response: NdthaResponseV3,
) -> Result<NonlinearNdthaResultIrDocumentV1, ProductIrContractError> {
    if identity.request_hash != request.request_hash {
        return Err(contract_error(
            "result_ir_request_hash_mismatch",
            "/identity/request_hash",
            "ResultIR request hash is not bound to the supplied request",
        ));
    }
    let mut result = NonlinearNdthaResultIrV1 {
        schema_version: NONLINEAR_NDTHA_RESULT_IR_V1.to_owned(),
        analysis_kind: "nonlinear_ndtha".to_owned(),
        case_id: request.request.case_id.clone(),
        authority: ResultAuthorityV1::BoundedCandidate,
        units: ResultUnitsV1::default(),
        identity,
        backend_receipt: CpuExecutionReceiptV1::default(),
        summary,
        response,
        claim_boundary: RESULT_CLAIM_BOUNDARY.to_owned(),
        result_hash: String::new(),
    };
    validate_result(&result, Some(request.request()))?;
    result.result_hash = hash_without_field(&result, "result_hash", "result_ir_hash_failed")?;
    let canonical_json = canonical_struct(&result, "result_ir_canonicalization_failed")?;
    Ok(NonlinearNdthaResultIrDocumentV1 {
        result,
        canonical_json,
    })
}

/// Strictly decode a `ResultIR` and verify its self-hash and internal invariants.
///
/// # Errors
///
/// Returns a stable error for wire, identity, terminal-state or self-hash failure.
pub fn parse_nonlinear_ndtha_result_ir_v1(
    bytes: &[u8],
) -> Result<NonlinearNdthaResultIrDocumentV1, ProductIrContractError> {
    let value = strict_value(bytes, "result_ir")?;
    let result: NonlinearNdthaResultIrV1 = serde_json::from_value(value).map_err(|_| {
        contract_error(
            "result_ir_decode_failed",
            "/",
            "ResultIR fields do not satisfy the typed v1 contract",
        )
    })?;
    validate_result(&result, None)?;
    let expected = hash_without_field(&result, "result_hash", "result_ir_hash_failed")?;
    if result.result_hash != expected {
        return Err(contract_error(
            "result_ir_hash_mismatch",
            "/result_hash",
            "ResultIR self-hash does not match its canonical payload",
        ));
    }
    let canonical_json = canonical_struct(&result, "result_ir_canonicalization_failed")?;
    Ok(NonlinearNdthaResultIrDocumentV1 {
        result,
        canonical_json,
    })
}

/// Build immutable canonical `ReportIR` bound to exact `ResultIR` and document-source bytes.
///
/// # Errors
///
/// Returns a stable error for invalid source identity or canonical serialization failure.
pub fn build_nonlinear_ndtha_report_ir_v1(
    result: &NonlinearNdthaResultIrDocumentV1,
    document_source: &[u8],
) -> Result<NonlinearNdthaReportIrDocumentV1, ProductIrContractError> {
    let source = result.result();
    let mut report = NonlinearNdthaReportIrV1 {
        schema_version: NONLINEAR_NDTHA_REPORT_IR_V1.to_owned(),
        report_kind: "nonlinear_ndtha_summary".to_owned(),
        case_id: source.case_id.clone(),
        authority: ResultAuthorityV1::BoundedCandidate,
        source_result_hash: source.result_hash.clone(),
        identity: source.identity.clone(),
        summary: NonlinearNdthaReportSummaryV1 {
            terminal_status: source.summary.terminal_status,
            step_count_completed: source.summary.step_count_completed,
            max_drift_ratio_pct: source.summary.max_drift_ratio_pct,
            max_plastic_story_count: source.summary.max_plastic_story_count,
            residual_top_displacement_m: source.summary.residual_top_displacement_m,
        },
        document_source_hash: sha256_identity(document_source),
        claim_boundary: REPORT_CLAIM_BOUNDARY.to_owned(),
        report_hash: String::new(),
    };
    validate_report(&report)?;
    report.report_hash = hash_without_field(&report, "report_hash", "report_ir_hash_failed")?;
    let canonical_json = canonical_struct(&report, "report_ir_canonicalization_failed")?;
    Ok(NonlinearNdthaReportIrDocumentV1 {
        report,
        canonical_json,
    })
}

/// Strictly decode `ReportIR` and verify its self-hash and fixed authority boundary.
///
/// # Errors
///
/// Returns a stable error for malformed wire data, invariant drift or a self-hash mismatch.
pub fn parse_nonlinear_ndtha_report_ir_v1(
    bytes: &[u8],
) -> Result<NonlinearNdthaReportIrDocumentV1, ProductIrContractError> {
    let value = strict_value(bytes, "report_ir")?;
    let report: NonlinearNdthaReportIrV1 = serde_json::from_value(value).map_err(|_| {
        contract_error(
            "report_ir_decode_failed",
            "/",
            "ReportIR fields do not satisfy the typed v1 contract",
        )
    })?;
    validate_report(&report)?;
    let expected = hash_without_field(&report, "report_hash", "report_ir_hash_failed")?;
    if report.report_hash != expected {
        return Err(contract_error(
            "report_ir_hash_mismatch",
            "/report_hash",
            "ReportIR self-hash does not match its canonical payload",
        ));
    }
    let canonical_json = canonical_struct(&report, "report_ir_canonicalization_failed")?;
    Ok(NonlinearNdthaReportIrDocumentV1 {
        report,
        canonical_json,
    })
}

#[must_use]
pub fn sha256_identity(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    format!("sha256:{digest:x}")
}

/// Compute the deterministic average used by the bounded `ResultIR` summary.
///
/// # Errors
///
/// Returns a contract error for a zero step count or a sum beyond the bounded exact-integer
/// range accepted by this v1 profile.
pub fn average_step_iterations(
    iteration_sum: u64,
    step_count: u32,
) -> Result<f64, ProductIrContractError> {
    if step_count == 0 || iteration_sum > 1_000_000_000_000 {
        return Err(contract_error(
            "result_ir_iteration_counter_invalid",
            "/summary/adaptive_iteration_sum",
            "ResultIR iteration counters exceed the bounded exact-average profile",
        ));
    }
    // The profile caps the integer at 1e12, below f64's exact integer limit of 2^53.
    #[allow(clippy::cast_precision_loss)]
    let numerator = iteration_sum as f64;
    Ok(numerator / f64::from(step_count))
}

fn validate_request_schema(value: &Value) -> Result<(), ProductIrContractError> {
    let compiled = REQUEST_SCHEMA_VALIDATOR.get_or_init(|| {
        let schema: Value = serde_json::from_str(REQUEST_SCHEMA_TEXT)
            .map_err(|error| format!("schema JSON invalid: {error}"))?;
        JSONSchema::options()
            .with_draft(Draft::Draft202012)
            .compile(&schema)
            .map_err(|error| format!("schema compile failed: {error}"))
    });
    let validator = compiled.as_ref().map_err(|_| {
        contract_error(
            "native_analysis_request_schema_contract_invalid",
            "/",
            "embedded native analysis request schema could not be compiled",
        )
    })?;
    let mut paths = validator
        .validate(value)
        .err()
        .into_iter()
        .flatten()
        .map(|error| {
            let path = error.instance_path.to_string();
            if path.is_empty() {
                "/".to_owned()
            } else {
                path
            }
        })
        .collect::<Vec<_>>();
    paths.sort();
    if let Some(path) = paths.first() {
        return Err(contract_error(
            "native_analysis_request_schema_invalid",
            path,
            "native analysis request does not satisfy the v1 schema",
        ));
    }
    Ok(())
}

fn validate_request_lengths(
    request: &NativeAnalysisRequestV1,
) -> Result<(), ProductIrContractError> {
    let stories = usize::try_from(request.config.story_count).map_err(|_| length_error())?;
    let steps = usize::try_from(request.config.step_count).map_err(|_| length_error())?;
    if stories == 0
        || steps == 0
        || [
            request.inputs.story_k_n_per_m.len(),
            request.inputs.story_h_m.len(),
            request.inputs.story_axial_n.len(),
            request.inputs.story_yield_drift_m.len(),
            request.inputs.story_mass_kg.len(),
            request.inputs.story_damping_n_s_per_m.len(),
            request.inputs.floor_load_base_n.len(),
        ]
        .into_iter()
        .any(|length| length != stories)
        || request.inputs.ag_g.len() != steps
    {
        return Err(length_error());
    }
    Ok(())
}

fn validate_result(
    result: &NonlinearNdthaResultIrV1,
    request: Option<&NativeAnalysisRequestV1>,
) -> Result<(), ProductIrContractError> {
    if result.schema_version != NONLINEAR_NDTHA_RESULT_IR_V1
        || result.analysis_kind != "nonlinear_ndtha"
        || result.authority != ResultAuthorityV1::BoundedCandidate
        || result.claim_boundary != RESULT_CLAIM_BOUNDARY
    {
        return Err(contract_error(
            "result_ir_contract_identity_invalid",
            "/",
            "ResultIR contract identity or authority boundary is invalid",
        ));
    }
    validate_units(&result.units)?;
    validate_identity(&result.identity)?;
    validate_cpu_receipt(&result.backend_receipt)?;
    if !result.result_hash.is_empty() {
        validate_hash(&result.result_hash, "/result_hash")?;
    }
    if let Some(request) = request {
        if result.case_id != request.case_id {
            return Err(contract_error(
                "result_ir_case_mismatch",
                "/case_id",
                "ResultIR case id does not match its request",
            ));
        }
        validate_response_and_summary(
            &result.summary,
            &result.response,
            request.config.story_count,
            request.config.step_count,
        )?;
    } else {
        let stories = u32::try_from(result.response.final_story_drift_pct.len())
            .map_err(|_| length_error())?;
        let steps =
            u32::try_from(result.response.step_converged.len()).map_err(|_| length_error())?;
        validate_response_and_summary(&result.summary, &result.response, stories, steps)?;
    }
    Ok(())
}

fn validate_response_and_summary(
    summary: &NonlinearNdthaResultSummaryV1,
    response: &NdthaResponseV3,
    story_count: u32,
    step_count: u32,
) -> Result<(), ProductIrContractError> {
    let stories = usize::try_from(story_count).map_err(|_| length_error())?;
    let steps = usize::try_from(step_count).map_err(|_| length_error())?;
    validate_response_lengths(response, stories, steps)?;
    validate_terminal_summary(summary, response, story_count, steps)?;
    canonical_struct(summary, "result_ir_non_finite_summary")?;
    canonical_struct(response, "result_ir_non_finite_response")?;
    Ok(())
}

fn validate_response_lengths(
    response: &NdthaResponseV3,
    stories: usize,
    steps: usize,
) -> Result<(), ProductIrContractError> {
    if stories == 0
        || steps == 0
        || [
            response.story_drift_envelope_pct.len(),
            response.final_story_drift_pct.len(),
        ]
        .into_iter()
        .any(|length| length != stories)
        || [
            response.top_displacement_m.len(),
            response.drift_ratio_pct.len(),
            response.base_shear_kn.len(),
            response.core_drift_pct.len(),
            response.core_shear_kn.len(),
            response.step_converged.len(),
            response.step_iterations.len(),
            response.step_plastic_story_count.len(),
            response.step_residual_inf.len(),
        ]
        .into_iter()
        .any(|length| length != steps)
    {
        return Err(length_error());
    }
    Ok(())
}

fn validate_terminal_summary(
    summary: &NonlinearNdthaResultSummaryV1,
    response: &NdthaResponseV3,
    story_count: u32,
    steps: usize,
) -> Result<(), ProductIrContractError> {
    let completed = usize::try_from(summary.step_count_completed).map_err(|_| length_error())?;
    if completed == 0 || completed > steps {
        return Err(contract_error(
            "result_ir_completion_count_invalid",
            "/summary/step_count_completed",
            "ResultIR completed step count is outside the response extent",
        ));
    }
    let terminal_valid = match summary.terminal_status {
        NonlinearNdthaTerminalStatusV1::Completed => {
            completed == steps
                && summary.collapse_step == -1
                && summary.collapse_time_s.to_bits() == 0.0_f64.to_bits()
                && summary.collapse_drift_ratio_pct.to_bits() == 0.0_f64.to_bits()
                && summary.collapse_top_displacement_m.to_bits() == 0.0_f64.to_bits()
        }
        NonlinearNdthaTerminalStatusV1::Collapsed => {
            summary.collapse_step >= 0
                && usize::try_from(summary.collapse_step).is_ok_and(|step| step < completed)
        }
    };
    if !terminal_valid {
        return Err(contract_error(
            "result_ir_terminal_state_invalid",
            "/summary/terminal_status",
            "ResultIR terminal status and collapse fields disagree",
        ));
    }
    if response.step_converged[..completed]
        .iter()
        .any(|value| !value)
        || response.step_converged[completed..]
            .iter()
            .any(|value| *value)
    {
        return Err(contract_error(
            "result_ir_step_state_invalid",
            "/response/step_converged",
            "ResultIR completed and unexecuted step flags disagree",
        ));
    }
    if summary.max_plastic_story_count > story_count {
        return Err(contract_error(
            "result_ir_plastic_count_invalid",
            "/summary/max_plastic_story_count",
            "ResultIR plastic story count exceeds story count",
        ));
    }
    validate_executed_summary(summary, response, completed)?;
    let expected_average =
        average_step_iterations(summary.adaptive_iteration_sum, summary.step_count_completed)?;
    if summary.avg_step_iterations.to_bits() != expected_average.to_bits() {
        return Err(contract_error(
            "result_ir_iteration_average_invalid",
            "/summary/avg_step_iterations",
            "ResultIR average iteration count does not match its exact counters",
        ));
    }
    let last = completed - 1;
    if summary.residual_top_displacement_m.to_bits() != response.top_displacement_m[last].to_bits()
    {
        return Err(contract_error(
            "result_ir_residual_displacement_invalid",
            "/summary/residual_top_displacement_m",
            "ResultIR residual displacement does not match the terminal response",
        ));
    }
    let residual_drift = response
        .final_story_drift_pct
        .iter()
        .map(|value| value.abs())
        .fold(0.0_f64, f64::max);
    if summary.residual_drift_ratio_pct.to_bits() != residual_drift.to_bits() {
        return Err(contract_error(
            "result_ir_residual_drift_invalid",
            "/summary/residual_drift_ratio_pct",
            "ResultIR residual drift does not match final story recovery",
        ));
    }
    Ok(())
}

fn validate_executed_summary(
    summary: &NonlinearNdthaResultSummaryV1,
    response: &NdthaResponseV3,
    completed: usize,
) -> Result<(), ProductIrContractError> {
    let iteration_sum = response.step_iterations[..completed]
        .iter()
        .try_fold(0_u64, |sum, value| sum.checked_add(u64::from(*value)))
        .ok_or_else(|| {
            contract_error(
                "result_ir_iteration_counter_invalid",
                "/summary/adaptive_iteration_sum",
                "ResultIR step iteration sum overflowed",
            )
        })?;
    let max_plastic = response.step_plastic_story_count[..completed]
        .iter()
        .copied()
        .max()
        .unwrap_or(0);
    let max_drift = response.drift_ratio_pct[..completed]
        .iter()
        .copied()
        .fold(0.0_f64, f64::max);
    if summary.adaptive_iteration_sum != iteration_sum
        || summary.max_plastic_story_count != max_plastic
        || summary.max_drift_ratio_pct.to_bits() != max_drift.to_bits()
    {
        return Err(contract_error(
            "result_ir_summary_recovery_invalid",
            "/summary",
            "ResultIR counters or envelopes do not match executed response channels",
        ));
    }
    if matches!(
        summary.terminal_status,
        NonlinearNdthaTerminalStatusV1::Collapsed
    ) {
        let collapse_step = usize::try_from(summary.collapse_step).map_err(|_| {
            contract_error(
                "result_ir_terminal_state_invalid",
                "/summary/collapse_step",
                "ResultIR collapse step is outside the response extent",
            )
        })?;
        if collapse_step != completed - 1
            || summary.collapse_drift_ratio_pct.to_bits()
                != response.drift_ratio_pct[collapse_step].to_bits()
            || summary.collapse_top_displacement_m.to_bits()
                != response.top_displacement_m[collapse_step].to_bits()
        {
            return Err(contract_error(
                "result_ir_collapse_recovery_invalid",
                "/summary/collapse_step",
                "ResultIR collapse summary does not match its terminal response",
            ));
        }
    }
    for values in [
        &response.top_displacement_m,
        &response.drift_ratio_pct,
        &response.base_shear_kn,
        &response.core_drift_pct,
        &response.core_shear_kn,
        &response.step_residual_inf,
    ] {
        if values[completed..]
            .iter()
            .any(|value| value.to_bits() != 0.0_f64.to_bits())
        {
            return Err(contract_error(
                "result_ir_unexecuted_tail_invalid",
                "/response",
                "ResultIR unexecuted response tail must remain canonical zero",
            ));
        }
    }
    if response.step_iterations[completed..]
        .iter()
        .any(|value| *value != 0)
        || response.step_plastic_story_count[completed..]
            .iter()
            .any(|value| *value != 0)
    {
        return Err(contract_error(
            "result_ir_unexecuted_tail_invalid",
            "/response",
            "ResultIR unexecuted response counters must remain zero",
        ));
    }
    Ok(())
}

fn validate_units(units: &ResultUnitsV1) -> Result<(), ProductIrContractError> {
    if units != &ResultUnitsV1::default() {
        return Err(contract_error(
            "result_ir_units_invalid",
            "/units",
            "ResultIR units/frame are not the fixed SI story-axis contract",
        ));
    }
    Ok(())
}

fn validate_identity(identity: &ResultIdentityV1) -> Result<(), ProductIrContractError> {
    for (path, value) in [
        ("/identity/request_hash", &identity.request_hash),
        ("/identity/model_hash", &identity.model_hash),
        ("/identity/state_hash", &identity.state_hash),
        ("/identity/execution_hash", &identity.execution_hash),
        ("/identity/checkpoint_hash", &identity.checkpoint_hash),
    ] {
        validate_hash(value, path)?;
    }
    Ok(())
}

fn validate_cpu_receipt(receipt: &CpuExecutionReceiptV1) -> Result<(), ProductIrContractError> {
    if receipt != &CpuExecutionReceiptV1::default() {
        return Err(contract_error(
            "result_ir_backend_receipt_invalid",
            "/backend_receipt",
            "ResultIR backend receipt is not the bounded CPU/fallback-zero contract",
        ));
    }
    Ok(())
}

fn validate_report(report: &NonlinearNdthaReportIrV1) -> Result<(), ProductIrContractError> {
    if report.schema_version != NONLINEAR_NDTHA_REPORT_IR_V1
        || report.report_kind != "nonlinear_ndtha_summary"
        || report.authority != ResultAuthorityV1::BoundedCandidate
        || report.claim_boundary != REPORT_CLAIM_BOUNDARY
    {
        return Err(contract_error(
            "report_ir_contract_identity_invalid",
            "/",
            "ReportIR contract identity or authority boundary is invalid",
        ));
    }
    validate_hash(&report.source_result_hash, "/source_result_hash")?;
    validate_hash(&report.document_source_hash, "/document_source_hash")?;
    validate_identity(&report.identity)?;
    if !report.report_hash.is_empty() {
        validate_hash(&report.report_hash, "/report_hash")?;
    }
    canonical_struct(&report.summary, "report_ir_non_finite_summary")?;
    Ok(())
}

fn validate_hash(value: &str, path: &str) -> Result<(), ProductIrContractError> {
    if value.len() == 71
        && value.starts_with("sha256:")
        && value[7..]
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        Ok(())
    } else {
        Err(contract_error(
            "product_ir_hash_invalid",
            path,
            "identity must be lowercase sha256:<64 hex>",
        ))
    }
}

fn strict_value(bytes: &[u8], family: &str) -> Result<Value, ProductIrContractError> {
    decode_json_strict(bytes).map_err(|error| ProductIrContractError {
        code: error.code.replacen("model_ir", family, 1),
        path: error.path,
        detail: error.detail.replace("ModelIR", family),
    })
}

fn canonical_struct<T: Serialize>(value: &T, code: &str) -> Result<String, ProductIrContractError> {
    let value = serde_json::to_value(value)
        .map_err(|_| contract_error(code, "/", "typed value could not be represented as JSON"))?;
    canonicalize(&value, code)
}

fn canonicalize(value: &Value, code: &str) -> Result<String, ProductIrContractError> {
    canonicalize_model_ir_v2(value).map_err(|_| {
        contract_error(
            code,
            "/",
            "value could not be represented by the canonical JSON contract",
        )
    })
}

fn hash_without_field<T: Serialize>(
    value: &T,
    field: &str,
    code: &str,
) -> Result<String, ProductIrContractError> {
    let mut value = serde_json::to_value(value)
        .map_err(|_| contract_error(code, "/", "typed value could not be represented as JSON"))?;
    value
        .as_object_mut()
        .and_then(|object| object.remove(field))
        .ok_or_else(|| contract_error(code, "/", "self-hash field is missing"))?;
    let canonical = canonicalize(&value, code)?;
    Ok(sha256_identity(canonical.as_bytes()))
}

fn length_error() -> ProductIrContractError {
    contract_error(
        "native_analysis_vector_length_mismatch",
        "/",
        "declared story/step counts and vector lengths disagree",
    )
}

fn contract_error(code: &str, path: &str, detail: &str) -> ProductIrContractError {
    ProductIrContractError {
        code: code.to_owned(),
        path: path.to_owned(),
        detail: detail.to_owned(),
    }
}

#[cfg(test)]
mod tests {
    use super::{sha256_identity, validate_hash};

    #[test]
    fn product_hash_identity_is_fixed_width_and_lowercase() {
        let identity = sha256_identity(b"native-product");
        assert_eq!(identity.len(), 71);
        validate_hash(&identity, "/hash").expect("valid product hash");
        assert!(validate_hash("sha256:ABC", "/hash").is_err());
    }
}
