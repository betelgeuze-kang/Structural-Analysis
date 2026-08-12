//! Strict bounded canonical-CSR sparse PCG product wire contracts.

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

use crate::model_ir::{canonicalize_model_ir_v2, decode_json_strict};
use crate::product_ir::{
    sha256_identity, ProductIrContractError, ResultAuthorityV1, ResultIdentityV1,
};

pub const SPARSE_LINEAR_REQUEST_V1: &str = "structural-sparse-linear-request.v1";
pub const SPARSE_LINEAR_RESULT_IR_V1: &str = "structural-sparse-linear-result-ir.v1";
pub const SPARSE_LINEAR_REPORT_IR_V1: &str = "structural-sparse-linear-report-ir.v1";
pub const SPARSE_LINEAR_MAXIMUM_ORDER: u32 = 100_000;
pub const SPARSE_LINEAR_MAXIMUM_NONZEROS: usize = 5_000_000;
pub const SPARSE_LINEAR_MAXIMUM_REQUEST_BYTES: usize = 64 * 1024 * 1024;

const REQUEST_OPERATION: &str = "solve_sparse_spd_pcg";
const MAXIMUM_ITERATIONS: u32 = 1_000_000;
const RESULT_CLAIM_BOUNDARY: &str = "bounded_canonical_csr_cpu_pcg_candidate_not_whole_model_assembly_hip_or_engineering_acceptance";
const REPORT_CLAIM_BOUNDARY: &str = "deterministic_projection_of_one_bounded_sparse_cpu_candidate_not_engineering_acceptance_or_design_code_compliance";

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum SparseLinearBackendV1 {
    Cpu,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SparseLinearConfigV1 {
    pub max_iterations: u32,
    pub absolute_residual_tolerance: f64,
    pub relative_residual_tolerance: f64,
    pub maximum_increment: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SparseLinearAnalysisRequestV1 {
    pub schema_version: String,
    pub operation: String,
    pub case_id: String,
    pub backend: SparseLinearBackendV1,
    pub order: u32,
    pub row_offsets: Vec<u64>,
    pub column_indices: Vec<u32>,
    pub values: Vec<f64>,
    pub right_hand_side: Vec<f64>,
    /// Empty means the all-zero vector; otherwise exactly `order` finite values.
    pub initial_guess: Vec<f64>,
    pub config: SparseLinearConfigV1,
}

#[derive(Clone, Debug)]
pub struct SparseLinearAnalysisRequestDocumentV1 {
    request: SparseLinearAnalysisRequestV1,
    canonical_json: String,
    request_hash: String,
}

impl SparseLinearAnalysisRequestDocumentV1 {
    #[must_use]
    pub const fn request(&self) -> &SparseLinearAnalysisRequestV1 {
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
pub struct SparseLinearUnitsV1 {
    pub solution: String,
    pub residual: String,
    pub coordinate_frame: String,
}

impl Default for SparseLinearUnitsV1 {
    fn default() -> Self {
        Self {
            solution: "caller_dof_units".to_owned(),
            residual: "right_hand_side_units".to_owned(),
            coordinate_frame: "caller_canonical_csr_dof_order".to_owned(),
        }
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SparseLinearCpuExecutionReceiptV1 {
    pub backend: SparseLinearBackendV1,
    pub precision: String,
    pub abi_version: String,
    pub deterministic_policy: String,
    pub fallback_count: u32,
    pub h2d_bytes: u64,
    pub d2h_bytes: u64,
    pub sync_count: u64,
}

impl Default for SparseLinearCpuExecutionReceiptV1 {
    fn default() -> Self {
        Self {
            backend: SparseLinearBackendV1::Cpu,
            precision: "fp64".to_owned(),
            abi_version: "0x0001000a".to_owned(),
            deterministic_policy: "serial_fixed_order_jacobi_pcg_restart".to_owned(),
            fallback_count: 0,
            h2d_bytes: 0,
            d2h_bytes: 0,
            sync_count: 0,
        }
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SparseLinearResultSummaryV1 {
    pub order: u32,
    pub nonzero_count: u64,
    pub iterations: u32,
    pub initial_residual_inf: f64,
    pub final_residual_inf: f64,
    pub final_residual_l2: f64,
    pub last_increment_inf: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SparseLinearResultIrV1 {
    pub schema_version: String,
    pub case_id: String,
    pub authority: ResultAuthorityV1,
    pub units: SparseLinearUnitsV1,
    pub identity: ResultIdentityV1,
    pub backend_receipt: SparseLinearCpuExecutionReceiptV1,
    pub summary: SparseLinearResultSummaryV1,
    pub solution: Vec<f64>,
    pub claim_boundary: String,
    pub result_hash: String,
}

#[derive(Clone, Debug)]
pub struct SparseLinearResultIrDocumentV1 {
    result: SparseLinearResultIrV1,
    canonical_json: String,
}

impl SparseLinearResultIrDocumentV1 {
    #[must_use]
    pub const fn result(&self) -> &SparseLinearResultIrV1 {
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
pub struct SparseLinearReportSummaryV1 {
    pub order: u32,
    pub nonzero_count: u64,
    pub iterations: u32,
    pub final_residual_inf: f64,
    pub maximum_absolute_solution: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SparseLinearReportIrV1 {
    pub schema_version: String,
    pub report_kind: String,
    pub case_id: String,
    pub authority: ResultAuthorityV1,
    pub source_result_hash: String,
    pub identity: ResultIdentityV1,
    pub summary: SparseLinearReportSummaryV1,
    pub document_source_hash: String,
    pub claim_boundary: String,
    pub report_hash: String,
}

#[derive(Clone, Debug)]
pub struct SparseLinearReportIrDocumentV1 {
    report: SparseLinearReportIrV1,
    canonical_json: String,
}

impl SparseLinearReportIrDocumentV1 {
    #[must_use]
    pub const fn report(&self) -> &SparseLinearReportIrV1 {
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

/// Strictly decode, validate, canonicalize, and hash a bounded sparse request.
///
/// # Errors
///
/// Returns a stable contract error for malformed, duplicate, unknown, oversized, non-finite,
/// dimensionally inconsistent, or noncanonical sparse request data.
pub fn parse_sparse_linear_request_v1(
    bytes: &[u8],
) -> Result<SparseLinearAnalysisRequestDocumentV1, ProductIrContractError> {
    if bytes.is_empty() || bytes.len() > SPARSE_LINEAR_MAXIMUM_REQUEST_BYTES {
        return Err(error(
            "sparse_request_size_invalid",
            "/",
            "sparse request bytes are outside the bounded product domain",
        ));
    }
    let value = strict_value(bytes, "sparse_request")?;
    let request: SparseLinearAnalysisRequestV1 =
        serde_json::from_value(value.clone()).map_err(|_| {
            error(
                "sparse_request_decode_failed",
                "/",
                "sparse request has unknown, missing, or mistyped fields",
            )
        })?;
    validate_request(&request)?;
    let canonical_json = canonical_value(&value, "sparse_request_canonicalization_failed")?;
    validate_canonical_request_size(&canonical_json)?;
    Ok(SparseLinearAnalysisRequestDocumentV1 {
        request_hash: sha256_identity(canonical_json.as_bytes()),
        request,
        canonical_json,
    })
}

/// Build one canonical sparse request from typed values.
///
/// # Errors
///
/// Returns a stable contract error when the typed values violate the bounded sparse contract or
/// cannot be represented within its canonical request limit.
pub fn build_sparse_linear_request_v1(
    request: SparseLinearAnalysisRequestV1,
) -> Result<SparseLinearAnalysisRequestDocumentV1, ProductIrContractError> {
    validate_request(&request)?;
    let canonical_json = canonical_struct(&request, "sparse_request_canonicalization_failed")?;
    validate_canonical_request_size(&canonical_json)?;
    Ok(SparseLinearAnalysisRequestDocumentV1 {
        request_hash: sha256_identity(canonical_json.as_bytes()),
        request,
        canonical_json,
    })
}

/// Exact operator, forcing, and initial-iterate identity.
///
/// # Errors
///
/// Returns a contract error only if the already validated request cannot be canonicalized.
pub fn sparse_linear_model_hash_v1(
    request: &SparseLinearAnalysisRequestDocumentV1,
) -> Result<String, ProductIrContractError> {
    let value = json!({
        "domain": "structural-sparse-linear-model.v1",
        "order": request.request.order,
        "row_offsets": &request.request.row_offsets,
        "column_indices": &request.request.column_indices,
        "values": &request.request.values,
        "right_hand_side": &request.request.right_hand_side,
        "initial_guess": &request.request.initial_guess,
    });
    Ok(sha256_identity(
        canonical_value(&value, "sparse_model_hash_failed")?.as_bytes(),
    ))
}

/// Exact backend, configuration, ABI, and algorithm identity.
///
/// # Errors
///
/// Returns a contract error only if the already validated execution description cannot be
/// canonicalized.
pub fn sparse_linear_execution_hash_v1(
    request: &SparseLinearAnalysisRequestDocumentV1,
) -> Result<String, ProductIrContractError> {
    let value = json!({
        "domain": "structural-sparse-linear-execution.v1",
        "backend": request.request.backend,
        "config": request.request.config,
        "abi_version": "0x0001000a",
        "algorithm": "cpp-fp64-serial-jacobi-pcg-restart.v1",
    });
    Ok(sha256_identity(
        canonical_value(&value, "sparse_execution_hash_failed")?.as_bytes(),
    ))
}

/// Build a self-hashed `ResultIR` bound to one exact request and checkpoint.
///
/// # Errors
///
/// Returns a stable contract error when identity bindings, result dimensions, finite-value
/// constraints, convergence metrics, or the recomputed true residual disagree.
pub fn build_sparse_linear_result_ir_v1(
    request: &SparseLinearAnalysisRequestDocumentV1,
    identity: ResultIdentityV1,
    summary: SparseLinearResultSummaryV1,
    solution: Vec<f64>,
) -> Result<SparseLinearResultIrDocumentV1, ProductIrContractError> {
    if identity.request_hash != request.request_hash {
        return Err(error(
            "sparse_result_request_hash_mismatch",
            "/identity/request_hash",
            "sparse ResultIR request hash differs from the supplied request",
        ));
    }
    if identity.model_hash != sparse_linear_model_hash_v1(request)? {
        return Err(error(
            "sparse_result_model_hash_mismatch",
            "/identity/model_hash",
            "sparse ResultIR model hash differs from the exact operator and vectors",
        ));
    }
    if identity.execution_hash != sparse_linear_execution_hash_v1(request)? {
        return Err(error(
            "sparse_result_execution_hash_mismatch",
            "/identity/execution_hash",
            "sparse ResultIR execution hash differs from the exact configuration",
        ));
    }
    let mut result = SparseLinearResultIrV1 {
        schema_version: SPARSE_LINEAR_RESULT_IR_V1.to_owned(),
        case_id: request.request.case_id.clone(),
        authority: ResultAuthorityV1::BoundedCandidate,
        units: SparseLinearUnitsV1::default(),
        identity,
        backend_receipt: SparseLinearCpuExecutionReceiptV1::default(),
        summary,
        solution,
        claim_boundary: RESULT_CLAIM_BOUNDARY.to_owned(),
        result_hash: String::new(),
    };
    validate_result(&result, Some(request.request()))?;
    result.result_hash = hash_without_field(&result, "result_hash", "sparse_result_hash_failed")?;
    let canonical_json = canonical_struct(&result, "sparse_result_canonicalization_failed")?;
    Ok(SparseLinearResultIrDocumentV1 {
        result,
        canonical_json,
    })
}

/// Strictly decode and self-verify one sparse `ResultIR`.
///
/// # Errors
///
/// Returns a stable contract error for malformed or noncanonical data, invalid typed invariants,
/// or a mismatched self-hash.
pub fn parse_sparse_linear_result_ir_v1(
    bytes: &[u8],
) -> Result<SparseLinearResultIrDocumentV1, ProductIrContractError> {
    let value = strict_value(bytes, "sparse_result")?;
    let result: SparseLinearResultIrV1 = serde_json::from_value(value).map_err(|_| {
        error(
            "sparse_result_decode_failed",
            "/",
            "sparse ResultIR fields do not satisfy the typed v1 contract",
        )
    })?;
    validate_result(&result, None)?;
    let expected = hash_without_field(&result, "result_hash", "sparse_result_hash_failed")?;
    if result.result_hash != expected {
        return Err(error(
            "sparse_result_hash_mismatch",
            "/result_hash",
            "sparse ResultIR self-hash does not match its canonical payload",
        ));
    }
    let canonical_json = canonical_struct(&result, "sparse_result_canonicalization_failed")?;
    Ok(SparseLinearResultIrDocumentV1 {
        result,
        canonical_json,
    })
}

/// Build a self-hashed `ReportIR` bound to exact result and document bytes.
///
/// # Errors
///
/// Returns a stable contract error if the report projection violates its fixed authority,
/// identity, summary, or canonicalization contract.
pub fn build_sparse_linear_report_ir_v1(
    result: &SparseLinearResultIrDocumentV1,
    document_source: &[u8],
) -> Result<SparseLinearReportIrDocumentV1, ProductIrContractError> {
    let source = result.result();
    let maximum_absolute_solution = source
        .solution
        .iter()
        .map(|value| value.abs())
        .fold(0.0_f64, f64::max);
    let mut report = SparseLinearReportIrV1 {
        schema_version: SPARSE_LINEAR_REPORT_IR_V1.to_owned(),
        report_kind: "sparse_linear_summary".to_owned(),
        case_id: source.case_id.clone(),
        authority: ResultAuthorityV1::BoundedCandidate,
        source_result_hash: source.result_hash.clone(),
        identity: source.identity.clone(),
        summary: SparseLinearReportSummaryV1 {
            order: source.summary.order,
            nonzero_count: source.summary.nonzero_count,
            iterations: source.summary.iterations,
            final_residual_inf: source.summary.final_residual_inf,
            maximum_absolute_solution,
        },
        document_source_hash: sha256_identity(document_source),
        claim_boundary: REPORT_CLAIM_BOUNDARY.to_owned(),
        report_hash: String::new(),
    };
    validate_report(&report)?;
    report.report_hash = hash_without_field(&report, "report_hash", "sparse_report_hash_failed")?;
    let canonical_json = canonical_struct(&report, "sparse_report_canonicalization_failed")?;
    Ok(SparseLinearReportIrDocumentV1 {
        report,
        canonical_json,
    })
}

/// Strictly decode and self-verify one sparse `ReportIR`.
///
/// # Errors
///
/// Returns a stable contract error for malformed data, invalid report invariants, or a mismatched
/// self-hash.
pub fn parse_sparse_linear_report_ir_v1(
    bytes: &[u8],
) -> Result<SparseLinearReportIrDocumentV1, ProductIrContractError> {
    let value = strict_value(bytes, "sparse_report")?;
    let report: SparseLinearReportIrV1 = serde_json::from_value(value).map_err(|_| {
        error(
            "sparse_report_decode_failed",
            "/",
            "sparse ReportIR fields do not satisfy the typed v1 contract",
        )
    })?;
    validate_report(&report)?;
    let expected = hash_without_field(&report, "report_hash", "sparse_report_hash_failed")?;
    if report.report_hash != expected {
        return Err(error(
            "sparse_report_hash_mismatch",
            "/report_hash",
            "sparse ReportIR self-hash does not match its canonical payload",
        ));
    }
    let canonical_json = canonical_struct(&report, "sparse_report_canonicalization_failed")?;
    Ok(SparseLinearReportIrDocumentV1 {
        report,
        canonical_json,
    })
}

fn validate_request(request: &SparseLinearAnalysisRequestV1) -> Result<(), ProductIrContractError> {
    if request.schema_version != SPARSE_LINEAR_REQUEST_V1 {
        return Err(error(
            "sparse_request_schema_version_invalid",
            "/schema_version",
            "sparse request schema version is unsupported",
        ));
    }
    if request.operation != REQUEST_OPERATION {
        return Err(error(
            "sparse_request_operation_invalid",
            "/operation",
            "sparse request operation is unsupported",
        ));
    }
    if !valid_case_id(&request.case_id) {
        return Err(error(
            "sparse_request_case_id_invalid",
            "/case_id",
            "case_id must be 1..128 portable identifier bytes",
        ));
    }
    if !(1..=SPARSE_LINEAR_MAXIMUM_ORDER).contains(&request.order) {
        return Err(error(
            "sparse_request_order_invalid",
            "/order",
            "sparse matrix order is outside the bounded product domain",
        ));
    }
    let order = usize::try_from(request.order).map_err(|_| {
        error(
            "sparse_request_order_invalid",
            "/order",
            "sparse matrix order exceeds the address space",
        )
    })?;
    let nonzero_count = request.values.len();
    let dimensions_valid = request.row_offsets.len() == order + 1
        && request.column_indices.len() == nonzero_count
        && nonzero_count <= SPARSE_LINEAR_MAXIMUM_NONZEROS
        && request.right_hand_side.len() == order
        && (request.initial_guess.is_empty() || request.initial_guess.len() == order)
        && request.row_offsets.first() == Some(&0)
        && usize::try_from(*request.row_offsets.last().unwrap_or(&u64::MAX)) == Ok(nonzero_count);
    if !dimensions_valid {
        return Err(error(
            "sparse_request_dimensions_invalid",
            "/",
            "CSR arrays and vectors do not match the declared bounded order",
        ));
    }
    validate_finite_slice(&request.values, "/values")?;
    validate_finite_slice(&request.right_hand_side, "/right_hand_side")?;
    validate_finite_slice(&request.initial_guess, "/initial_guess")?;
    for row in 0..order {
        let begin = usize::try_from(request.row_offsets[row]).map_err(|_| {
            error(
                "sparse_request_row_offset_invalid",
                "/row_offsets",
                "CSR row offset exceeds the address space",
            )
        })?;
        let end = usize::try_from(request.row_offsets[row + 1]).map_err(|_| {
            error(
                "sparse_request_row_offset_invalid",
                "/row_offsets",
                "CSR row offset exceeds the address space",
            )
        })?;
        if begin > end || end > nonzero_count {
            return Err(error(
                "sparse_request_row_offset_invalid",
                "/row_offsets",
                "CSR row offsets must be monotonic and bounded",
            ));
        }
        let mut previous = None;
        for column in &request.column_indices[begin..end] {
            if usize::try_from(*column).map_or(true, |value| value >= order)
                || previous.is_some_and(|value| *column <= value)
            {
                return Err(error(
                    "sparse_request_column_invalid",
                    "/column_indices",
                    "CSR columns must be in range and strictly increasing per row",
                ));
            }
            previous = Some(*column);
        }
    }
    validate_config(request.config)
}

fn validate_config(config: SparseLinearConfigV1) -> Result<(), ProductIrContractError> {
    let valid = (1..=MAXIMUM_ITERATIONS).contains(&config.max_iterations)
        && config.absolute_residual_tolerance.is_finite()
        && config.relative_residual_tolerance.is_finite()
        && config.maximum_increment.is_finite()
        && config.absolute_residual_tolerance >= 0.0
        && config.relative_residual_tolerance >= 0.0
        && (config.absolute_residual_tolerance > 0.0 || config.relative_residual_tolerance > 0.0)
        && config.maximum_increment >= 0.0;
    if valid {
        Ok(())
    } else {
        Err(error(
            "sparse_request_config_invalid",
            "/config",
            "sparse PCG configuration is outside the bounded product domain",
        ))
    }
}

fn validate_result(
    result: &SparseLinearResultIrV1,
    request: Option<&SparseLinearAnalysisRequestV1>,
) -> Result<(), ProductIrContractError> {
    if result.schema_version != SPARSE_LINEAR_RESULT_IR_V1
        || result.claim_boundary != RESULT_CLAIM_BOUNDARY
        || result.authority != ResultAuthorityV1::BoundedCandidate
        || result.units != SparseLinearUnitsV1::default()
        || result.backend_receipt != SparseLinearCpuExecutionReceiptV1::default()
        || !valid_case_id(&result.case_id)
    {
        return Err(error(
            "sparse_result_authority_invalid",
            "/",
            "sparse ResultIR fixed authority, units, or CPU receipt is invalid",
        ));
    }
    validate_hashes(&result.identity)?;
    validate_hash(&result.result_hash, "/result_hash", true)?;
    let summary = &result.summary;
    let metrics = [
        summary.initial_residual_inf,
        summary.final_residual_inf,
        summary.final_residual_l2,
        summary.last_increment_inf,
    ];
    if summary.order == 0
        || summary.order > SPARSE_LINEAR_MAXIMUM_ORDER
        || usize::try_from(summary.order).ok() != Some(result.solution.len())
        || usize::try_from(summary.nonzero_count)
            .map_or(true, |value| value > SPARSE_LINEAR_MAXIMUM_NONZEROS)
        || summary.iterations > MAXIMUM_ITERATIONS
        || metrics
            .iter()
            .any(|value| !value.is_finite() || *value < 0.0)
        || result.solution.iter().any(|value| !value.is_finite())
    {
        return Err(error(
            "sparse_result_shape_invalid",
            "/",
            "sparse ResultIR shape or finite metrics are invalid",
        ));
    }
    if let Some(request) = request {
        let expected_nonzeros = u64::try_from(request.values.len()).unwrap_or(u64::MAX);
        if result.case_id != request.case_id
            || summary.order != request.order
            || summary.nonzero_count != expected_nonzeros
            || summary.iterations > request.config.max_iterations
        {
            return Err(error(
                "sparse_result_request_shape_mismatch",
                "/summary",
                "sparse ResultIR does not match the exact request dimensions",
            ));
        }
        let true_residual = true_residual(request, &result.solution)?;
        let true_inf = norm_inf(&true_residual);
        let true_l2 = norm_l2(&true_residual);
        let initial = if request.initial_guess.is_empty() {
            vec![0.0; result.solution.len()]
        } else {
            request.initial_guess.clone()
        };
        let initial_inf = norm_inf(&true_residual_for(request, &initial)?);
        let convergence_limit = request.config.absolute_residual_tolerance
            + request.config.relative_residual_tolerance * norm_inf(&request.right_hand_side);
        if !close(summary.final_residual_inf, true_inf)
            || !close(summary.final_residual_l2, true_l2)
            || !close(summary.initial_residual_inf, initial_inf)
            || summary.final_residual_inf > convergence_limit
        {
            return Err(error(
                "sparse_result_residual_invalid",
                "/summary",
                "sparse ResultIR residual metrics are inconsistent with Kx-b",
            ));
        }
    }
    Ok(())
}

fn validate_report(report: &SparseLinearReportIrV1) -> Result<(), ProductIrContractError> {
    if report.schema_version != SPARSE_LINEAR_REPORT_IR_V1
        || report.report_kind != "sparse_linear_summary"
        || report.claim_boundary != REPORT_CLAIM_BOUNDARY
        || report.authority != ResultAuthorityV1::BoundedCandidate
        || !valid_case_id(&report.case_id)
        || report.summary.order == 0
        || report.summary.order > SPARSE_LINEAR_MAXIMUM_ORDER
        || report.summary.nonzero_count == 0
        || !report.summary.final_residual_inf.is_finite()
        || report.summary.final_residual_inf < 0.0
        || !report.summary.maximum_absolute_solution.is_finite()
        || report.summary.maximum_absolute_solution < 0.0
    {
        return Err(error(
            "sparse_report_invariant_invalid",
            "/",
            "sparse ReportIR fixed fields or summary are invalid",
        ));
    }
    validate_hash(&report.source_result_hash, "/source_result_hash", false)?;
    validate_hash(&report.document_source_hash, "/document_source_hash", false)?;
    validate_hash(&report.report_hash, "/report_hash", true)?;
    validate_hashes(&report.identity)
}

fn true_residual(
    request: &SparseLinearAnalysisRequestV1,
    solution: &[f64],
) -> Result<Vec<f64>, ProductIrContractError> {
    true_residual_for(request, solution)
}

fn true_residual_for(
    request: &SparseLinearAnalysisRequestV1,
    values: &[f64],
) -> Result<Vec<f64>, ProductIrContractError> {
    let order = usize::try_from(request.order).map_err(|_| {
        error(
            "sparse_result_order_invalid",
            "/summary/order",
            "sparse result order exceeds the address space",
        )
    })?;
    if values.len() != order {
        return Err(error(
            "sparse_result_solution_length_invalid",
            "/solution",
            "sparse result solution length differs from request order",
        ));
    }
    let mut residual = vec![0.0; order];
    for (row, output) in residual.iter_mut().enumerate() {
        let begin = usize::try_from(request.row_offsets[row]).unwrap_or(usize::MAX);
        let end = usize::try_from(request.row_offsets[row + 1]).unwrap_or(usize::MAX);
        let mut product = 0.0;
        for index in begin..end {
            let column = usize::try_from(request.column_indices[index]).unwrap_or(usize::MAX);
            product += request.values[index] * values[column];
        }
        *output = request.right_hand_side[row] - product;
    }
    Ok(residual)
}

fn norm_inf(values: &[f64]) -> f64 {
    values
        .iter()
        .map(|value| value.abs())
        .fold(0.0_f64, f64::max)
}

fn norm_l2(values: &[f64]) -> f64 {
    let mut scale = 0.0_f64;
    let mut sum_squares = 1.0_f64;
    for value in values {
        let magnitude = value.abs();
        if magnitude == 0.0 {
            continue;
        }
        if scale < magnitude {
            let ratio = scale / magnitude;
            sum_squares = 1.0 + sum_squares * ratio * ratio;
            scale = magnitude;
        } else {
            let ratio = magnitude / scale;
            sum_squares += ratio * ratio;
        }
    }
    if scale == 0.0 {
        0.0
    } else {
        scale * sum_squares.sqrt()
    }
}

fn close(left: f64, right: f64) -> bool {
    (left - right).abs() <= 1.0e-12 * left.abs().max(right.abs()).max(1.0)
}

fn validate_canonical_request_size(value: &str) -> Result<(), ProductIrContractError> {
    if value.is_empty() || value.len() > SPARSE_LINEAR_MAXIMUM_REQUEST_BYTES {
        Err(error(
            "sparse_request_size_invalid",
            "/",
            "canonical sparse request exceeds the bounded product size",
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
            "sparse_nonfinite_value",
            path,
            "sparse product contracts accept only finite binary64 values",
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
            "sparse_hash_invalid",
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
            "sparse value cannot be represented as canonical JSON",
        )
    })
}

fn canonical_struct<T: Serialize>(value: &T, code: &str) -> Result<String, ProductIrContractError> {
    let value = serde_json::to_value(value).map_err(|_| {
        error(
            code,
            "/",
            "typed sparse value cannot be represented as JSON",
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
            "typed sparse value cannot be represented as JSON",
        )
    })?;
    value
        .as_object_mut()
        .and_then(|object| object.remove(field))
        .ok_or_else(|| error(code, "/", "sparse self-hash field is missing"))?;
    Ok(sha256_identity(canonical_value(&value, code)?.as_bytes()))
}

fn error(code: &str, path: &str, detail: &str) -> ProductIrContractError {
    ProductIrContractError {
        code: code.to_owned(),
        path: path.to_owned(),
        detail: detail.to_owned(),
    }
}
