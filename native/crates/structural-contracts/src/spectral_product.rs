//! Strict bounded dense modal/buckling product wire contracts.

use std::fmt;

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

use crate::model_ir::{canonicalize_model_ir_v2, decode_json_strict};
use crate::product_ir::{
    sha256_identity, ProductIrContractError, ResultAuthorityV1, ResultIdentityV1,
};

pub const DENSE_SPECTRAL_REQUEST_V1: &str = "structural-dense-spectral-request.v1";
pub const DENSE_SPECTRAL_RESULT_IR_V1: &str = "structural-dense-spectral-result-ir.v1";
pub const DENSE_SPECTRAL_REPORT_IR_V1: &str = "structural-dense-spectral-report-ir.v1";

const REQUEST_OPERATION: &str = "solve_dense_generalized_eigen";
const RESULT_CLAIM_BOUNDARY: &str = "bounded_dense_cpu_modal_or_buckling_candidate_not_sparse_whole_model_hip_or_engineering_acceptance";
const REPORT_CLAIM_BOUNDARY: &str = "deterministic_projection_of_one_bounded_dense_spectral_candidate_not_engineering_acceptance_or_design_code_compliance";
const MAXIMUM_ORDER: u32 = 128;
const MAXIMUM_SWEEPS: u32 = 4_096;

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum SpectralAnalysisKindV1 {
    Modal,
    LinearBuckling,
}

impl fmt::Display for SpectralAnalysisKindV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(match self {
            Self::Modal => "modal",
            Self::LinearBuckling => "linear_buckling",
        })
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum SpectralBackendV1 {
    Cpu,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SpectralGeneralizedEigenConfigV1 {
    pub mode_count: u32,
    pub maximum_sweeps: u32,
    pub symmetry_relative_tolerance: f64,
    pub positive_semidefinite_relative_tolerance: f64,
    pub mode_relative_tolerance: f64,
    pub cluster_relative_tolerance: f64,
    pub residual_relative_tolerance: f64,
    pub orthogonality_tolerance: f64,
    pub eigensolver_relative_tolerance: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DenseSpectralAnalysisRequestV1 {
    pub schema_version: String,
    pub operation: String,
    pub case_id: String,
    pub analysis_kind: SpectralAnalysisKindV1,
    pub backend: SpectralBackendV1,
    pub order: u32,
    pub stiffness: Vec<f64>,
    /// Modal mass matrix or geometric stiffness per unit load, selected by `analysis_kind`.
    pub secondary_matrix: Vec<f64>,
    /// Empty means identity; otherwise exactly `order` finite positive values.
    pub coordinate_recovery_scale: Vec<f64>,
    pub config: SpectralGeneralizedEigenConfigV1,
}

#[derive(Clone, Debug)]
pub struct DenseSpectralAnalysisRequestDocumentV1 {
    request: DenseSpectralAnalysisRequestV1,
    canonical_json: String,
    request_hash: String,
}

impl DenseSpectralAnalysisRequestDocumentV1 {
    #[must_use]
    pub const fn request(&self) -> &DenseSpectralAnalysisRequestV1 {
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
pub struct SpectralUnitsV1 {
    pub eigenvalue: String,
    pub angular_frequency: String,
    pub frequency: String,
    pub period: String,
    pub load_factor: String,
    pub mode_shape: String,
    pub coordinate_frame: String,
}

impl SpectralUnitsV1 {
    fn for_kind(kind: SpectralAnalysisKindV1) -> Self {
        Self {
            eigenvalue: if kind == SpectralAnalysisKindV1::Modal {
                "rad2_per_s2".to_owned()
            } else {
                "not_applicable".to_owned()
            },
            angular_frequency: if kind == SpectralAnalysisKindV1::Modal {
                "rad_per_s".to_owned()
            } else {
                "not_applicable".to_owned()
            },
            frequency: if kind == SpectralAnalysisKindV1::Modal {
                "Hz".to_owned()
            } else {
                "not_applicable".to_owned()
            },
            period: if kind == SpectralAnalysisKindV1::Modal {
                "s".to_owned()
            } else {
                "not_applicable".to_owned()
            },
            load_factor: if kind == SpectralAnalysisKindV1::LinearBuckling {
                "dimensionless".to_owned()
            } else {
                "not_applicable".to_owned()
            },
            mode_shape: "normalized_dimensionless".to_owned(),
            coordinate_frame: "caller_dense_dof_order".to_owned(),
        }
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SpectralCpuExecutionReceiptV1 {
    pub backend: SpectralBackendV1,
    pub precision: String,
    pub abi_version: String,
    pub deterministic_policy: String,
    pub fallback_count: u32,
    pub h2d_bytes: u64,
    pub d2h_bytes: u64,
    pub sync_count: u64,
}

impl Default for SpectralCpuExecutionReceiptV1 {
    fn default() -> Self {
        Self {
            backend: SpectralBackendV1::Cpu,
            precision: "fp64".to_owned(),
            abi_version: "0x00010009".to_owned(),
            deterministic_policy: "serial_cyclic_jacobi_fixed_order".to_owned(),
            fallback_count: 0,
            h2d_bytes: 0,
            d2h_bytes: 0,
            sync_count: 0,
        }
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(tag = "mode_kind", rename_all = "snake_case")]
pub enum SpectralModeV1 {
    Modal {
        eigenvalue_rad2_per_s2: f64,
        omega_rad_per_s: f64,
        frequency_hz: f64,
        period_s: f64,
        mass_normalized_shape: Vec<f64>,
        max_component_normalized_shape: Vec<f64>,
        generalized_mass: f64,
        generalized_stiffness: f64,
        residual_relative_inf: f64,
    },
    LinearBuckling {
        load_factor: f64,
        stiffness_normalized_shape: Vec<f64>,
        max_component_normalized_shape: Vec<f64>,
        generalized_elastic_stiffness: f64,
        generalized_geometric_stiffness: f64,
        residual_relative_inf: f64,
    },
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SpectralResultSummaryV1 {
    pub mode_count: u32,
    pub rigid_mode_count: u32,
    pub finite_positive_eigenvalue_count: u32,
    pub geometric_stiffness_positive_rank: u32,
    pub eigensolver_sweeps: u32,
    pub critical_load_factor: Option<f64>,
    pub metric_orthogonality_error_inf: f64,
    pub operator_diagonalization_error_inf: f64,
    pub stiffness_relative_symmetry_error: f64,
    pub secondary_relative_symmetry_error: f64,
    pub stiffness_minimum_eigenvalue: f64,
    pub secondary_minimum_eigenvalue: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DenseSpectralResultIrV1 {
    pub schema_version: String,
    pub analysis_kind: SpectralAnalysisKindV1,
    pub case_id: String,
    pub authority: ResultAuthorityV1,
    pub units: SpectralUnitsV1,
    pub identity: ResultIdentityV1,
    pub backend_receipt: SpectralCpuExecutionReceiptV1,
    pub summary: SpectralResultSummaryV1,
    pub modes: Vec<SpectralModeV1>,
    pub claim_boundary: String,
    pub result_hash: String,
}

#[derive(Clone, Debug)]
pub struct DenseSpectralResultIrDocumentV1 {
    result: DenseSpectralResultIrV1,
    canonical_json: String,
}

impl DenseSpectralResultIrDocumentV1 {
    #[must_use]
    pub const fn result(&self) -> &DenseSpectralResultIrV1 {
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
pub struct SpectralReportSummaryV1 {
    pub analysis_kind: SpectralAnalysisKindV1,
    pub mode_count: u32,
    pub primary_value: f64,
    pub maximum_residual_relative_inf: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DenseSpectralReportIrV1 {
    pub schema_version: String,
    pub report_kind: String,
    pub case_id: String,
    pub authority: ResultAuthorityV1,
    pub source_result_hash: String,
    pub identity: ResultIdentityV1,
    pub summary: SpectralReportSummaryV1,
    pub document_source_hash: String,
    pub claim_boundary: String,
    pub report_hash: String,
}

#[derive(Clone, Debug)]
pub struct DenseSpectralReportIrDocumentV1 {
    report: DenseSpectralReportIrV1,
    canonical_json: String,
}

impl DenseSpectralReportIrDocumentV1 {
    #[must_use]
    pub const fn report(&self) -> &DenseSpectralReportIrV1 {
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

/// Strictly decode and canonicalize one bounded dense spectral request.
///
/// # Errors
///
/// Returns a stable contract error for malformed/duplicate/unknown JSON, invalid dimensions,
/// non-finite values, inconsistent matrix lengths, or invalid configuration.
pub fn parse_dense_spectral_request_v1(
    bytes: &[u8],
) -> Result<DenseSpectralAnalysisRequestDocumentV1, ProductIrContractError> {
    let value = strict_value(bytes, "spectral_request")?;
    let request: DenseSpectralAnalysisRequestV1 =
        serde_json::from_value(value.clone()).map_err(|_| {
            error(
                "spectral_request_decode_failed",
                "/",
                "spectral request has unknown, missing, or mistyped fields",
            )
        })?;
    validate_request(&request)?;
    let canonical_json = canonical_value(&value, "spectral_request_canonicalization_failed")?;
    Ok(DenseSpectralAnalysisRequestDocumentV1 {
        request_hash: sha256_identity(canonical_json.as_bytes()),
        request,
        canonical_json,
    })
}

/// Build a canonical request from typed caller-owned values.
///
/// # Errors
///
/// Returns a stable contract error when the typed values violate the bounded request contract.
pub fn build_dense_spectral_request_v1(
    request: DenseSpectralAnalysisRequestV1,
) -> Result<DenseSpectralAnalysisRequestDocumentV1, ProductIrContractError> {
    validate_request(&request)?;
    let canonical_json = canonical_struct(&request, "spectral_request_canonicalization_failed")?;
    Ok(DenseSpectralAnalysisRequestDocumentV1 {
        request_hash: sha256_identity(canonical_json.as_bytes()),
        request,
        canonical_json,
    })
}

/// Stable model-domain identity for exact matrices and recovery scale.
///
/// # Errors
///
/// Returns a contract error only if the already validated request cannot be canonicalized.
pub fn dense_spectral_model_hash_v1(
    request: &DenseSpectralAnalysisRequestDocumentV1,
) -> Result<String, ProductIrContractError> {
    let value = json!({
        "domain": "structural-dense-spectral-model.v1",
        "order": request.request.order,
        "stiffness": &request.request.stiffness,
        "secondary_matrix": &request.request.secondary_matrix,
        "coordinate_recovery_scale": &request.request.coordinate_recovery_scale,
    });
    Ok(sha256_identity(
        canonical_value(&value, "spectral_model_hash_failed")?.as_bytes(),
    ))
}

/// Stable execution-domain identity for analysis kind, backend, configuration and ABI.
///
/// # Errors
///
/// Returns a contract error only if the already validated request cannot be canonicalized.
pub fn dense_spectral_execution_hash_v1(
    request: &DenseSpectralAnalysisRequestDocumentV1,
) -> Result<String, ProductIrContractError> {
    let value = json!({
        "domain": "structural-dense-spectral-execution.v1",
        "analysis_kind": request.request.analysis_kind,
        "backend": request.request.backend,
        "config": request.request.config,
        "abi_version": "0x00010009",
        "algorithm": "cpp-fp64-dense-cyclic-jacobi.v1",
    });
    Ok(sha256_identity(
        canonical_value(&value, "spectral_execution_hash_failed")?.as_bytes(),
    ))
}

/// Build a self-hashed spectral `ResultIR` bound to one exact request and checkpoint identity.
///
/// # Errors
///
/// Returns a stable contract error for identity drift, result-shape mismatch, non-finite values,
/// analysis-kind mismatch, fallback, or canonical serialization failure.
pub fn build_dense_spectral_result_ir_v1(
    request: &DenseSpectralAnalysisRequestDocumentV1,
    identity: ResultIdentityV1,
    summary: SpectralResultSummaryV1,
    modes: Vec<SpectralModeV1>,
) -> Result<DenseSpectralResultIrDocumentV1, ProductIrContractError> {
    if identity.request_hash != request.request_hash {
        return Err(error(
            "spectral_result_request_hash_mismatch",
            "/identity/request_hash",
            "spectral ResultIR request hash is not bound to the supplied request",
        ));
    }
    if identity.model_hash != dense_spectral_model_hash_v1(request)? {
        return Err(error(
            "spectral_result_model_hash_mismatch",
            "/identity/model_hash",
            "spectral ResultIR model hash is not bound to the supplied matrices",
        ));
    }
    if identity.execution_hash != dense_spectral_execution_hash_v1(request)? {
        return Err(error(
            "spectral_result_execution_hash_mismatch",
            "/identity/execution_hash",
            "spectral ResultIR execution hash is not bound to the supplied analysis configuration",
        ));
    }
    let mut result = DenseSpectralResultIrV1 {
        schema_version: DENSE_SPECTRAL_RESULT_IR_V1.to_owned(),
        analysis_kind: request.request.analysis_kind,
        case_id: request.request.case_id.clone(),
        authority: ResultAuthorityV1::BoundedCandidate,
        units: SpectralUnitsV1::for_kind(request.request.analysis_kind),
        identity,
        backend_receipt: SpectralCpuExecutionReceiptV1::default(),
        summary,
        modes,
        claim_boundary: RESULT_CLAIM_BOUNDARY.to_owned(),
        result_hash: String::new(),
    };
    validate_result(&result, Some(request.request()))?;
    result.result_hash = hash_without_field(&result, "result_hash", "spectral_result_hash_failed")?;
    let canonical_json = canonical_struct(&result, "spectral_result_canonicalization_failed")?;
    Ok(DenseSpectralResultIrDocumentV1 {
        result,
        canonical_json,
    })
}

/// Strictly decode and self-verify one spectral `ResultIR`.
///
/// # Errors
///
/// Returns a stable contract error for wire, invariant, shape, finite-value, or self-hash drift.
pub fn parse_dense_spectral_result_ir_v1(
    bytes: &[u8],
) -> Result<DenseSpectralResultIrDocumentV1, ProductIrContractError> {
    let value = strict_value(bytes, "spectral_result")?;
    let result: DenseSpectralResultIrV1 = serde_json::from_value(value).map_err(|_| {
        error(
            "spectral_result_decode_failed",
            "/",
            "spectral ResultIR fields do not satisfy the typed v1 contract",
        )
    })?;
    validate_result(&result, None)?;
    let expected = hash_without_field(&result, "result_hash", "spectral_result_hash_failed")?;
    if result.result_hash != expected {
        return Err(error(
            "spectral_result_hash_mismatch",
            "/result_hash",
            "spectral ResultIR self-hash does not match its canonical payload",
        ));
    }
    let canonical_json = canonical_struct(&result, "spectral_result_canonicalization_failed")?;
    Ok(DenseSpectralResultIrDocumentV1 {
        result,
        canonical_json,
    })
}

/// Build a self-hashed `ReportIR` bound to exact result and Markdown bytes.
///
/// # Errors
///
/// Returns a stable contract error for empty modes, invalid identity or canonicalization failure.
pub fn build_dense_spectral_report_ir_v1(
    result: &DenseSpectralResultIrDocumentV1,
    document_source: &[u8],
) -> Result<DenseSpectralReportIrDocumentV1, ProductIrContractError> {
    let source = result.result();
    let primary_value = primary_mode_value(&source.modes[0]);
    let maximum_residual_relative_inf = source
        .modes
        .iter()
        .map(mode_residual)
        .fold(0.0_f64, f64::max);
    let mut report = DenseSpectralReportIrV1 {
        schema_version: DENSE_SPECTRAL_REPORT_IR_V1.to_owned(),
        report_kind: "dense_spectral_summary".to_owned(),
        case_id: source.case_id.clone(),
        authority: ResultAuthorityV1::BoundedCandidate,
        source_result_hash: source.result_hash.clone(),
        identity: source.identity.clone(),
        summary: SpectralReportSummaryV1 {
            analysis_kind: source.analysis_kind,
            mode_count: source.summary.mode_count,
            primary_value,
            maximum_residual_relative_inf,
        },
        document_source_hash: sha256_identity(document_source),
        claim_boundary: REPORT_CLAIM_BOUNDARY.to_owned(),
        report_hash: String::new(),
    };
    validate_report(&report)?;
    report.report_hash = hash_without_field(&report, "report_hash", "spectral_report_hash_failed")?;
    let canonical_json = canonical_struct(&report, "spectral_report_canonicalization_failed")?;
    Ok(DenseSpectralReportIrDocumentV1 {
        report,
        canonical_json,
    })
}

/// Strictly decode and self-verify one spectral `ReportIR`.
///
/// # Errors
///
/// Returns a stable contract error for wire, invariant, or self-hash drift.
pub fn parse_dense_spectral_report_ir_v1(
    bytes: &[u8],
) -> Result<DenseSpectralReportIrDocumentV1, ProductIrContractError> {
    let value = strict_value(bytes, "spectral_report")?;
    let report: DenseSpectralReportIrV1 = serde_json::from_value(value).map_err(|_| {
        error(
            "spectral_report_decode_failed",
            "/",
            "spectral ReportIR fields do not satisfy the typed v1 contract",
        )
    })?;
    validate_report(&report)?;
    let expected = hash_without_field(&report, "report_hash", "spectral_report_hash_failed")?;
    if report.report_hash != expected {
        return Err(error(
            "spectral_report_hash_mismatch",
            "/report_hash",
            "spectral ReportIR self-hash does not match its canonical payload",
        ));
    }
    let canonical_json = canonical_struct(&report, "spectral_report_canonicalization_failed")?;
    Ok(DenseSpectralReportIrDocumentV1 {
        report,
        canonical_json,
    })
}

fn validate_request(
    request: &DenseSpectralAnalysisRequestV1,
) -> Result<(), ProductIrContractError> {
    if request.schema_version != DENSE_SPECTRAL_REQUEST_V1 {
        return Err(error(
            "spectral_request_schema_version_invalid",
            "/schema_version",
            "spectral request schema version is unsupported",
        ));
    }
    if request.operation != REQUEST_OPERATION {
        return Err(error(
            "spectral_request_operation_invalid",
            "/operation",
            "spectral request operation is unsupported",
        ));
    }
    if !valid_case_id(&request.case_id) {
        return Err(error(
            "spectral_request_case_id_invalid",
            "/case_id",
            "case_id must be 1..128 portable identifier bytes",
        ));
    }
    if !(1..=MAXIMUM_ORDER).contains(&request.order) {
        return Err(error(
            "spectral_request_order_invalid",
            "/order",
            "spectral matrix order must be between 1 and 128",
        ));
    }
    let order = usize::try_from(request.order).map_err(|_| {
        error(
            "spectral_request_order_invalid",
            "/order",
            "spectral order exceeds the address space",
        )
    })?;
    let matrix_length = order.checked_mul(order).ok_or_else(|| {
        error(
            "spectral_request_matrix_length_invalid",
            "/",
            "spectral matrix length overflows the address space",
        )
    })?;
    if request.stiffness.len() != matrix_length || request.secondary_matrix.len() != matrix_length {
        return Err(error(
            "spectral_request_matrix_length_invalid",
            "/",
            "both dense matrix lengths must equal order squared",
        ));
    }
    if !request.coordinate_recovery_scale.is_empty()
        && request.coordinate_recovery_scale.len() != order
    {
        return Err(error(
            "spectral_request_scale_length_invalid",
            "/coordinate_recovery_scale",
            "recovery scale must be empty or match matrix order",
        ));
    }
    validate_finite_slice(&request.stiffness, "/stiffness")?;
    validate_finite_slice(&request.secondary_matrix, "/secondary_matrix")?;
    validate_finite_slice(
        &request.coordinate_recovery_scale,
        "/coordinate_recovery_scale",
    )?;
    if request
        .coordinate_recovery_scale
        .iter()
        .any(|value| *value <= 0.0)
    {
        return Err(error(
            "spectral_request_scale_invalid",
            "/coordinate_recovery_scale",
            "recovery scale values must be positive",
        ));
    }
    validate_config(request.config, request.order)
}

fn validate_config(
    config: SpectralGeneralizedEigenConfigV1,
    order: u32,
) -> Result<(), ProductIrContractError> {
    let tolerances = [
        config.symmetry_relative_tolerance,
        config.positive_semidefinite_relative_tolerance,
        config.mode_relative_tolerance,
        config.cluster_relative_tolerance,
        config.residual_relative_tolerance,
        config.orthogonality_tolerance,
        config.eigensolver_relative_tolerance,
    ];
    if config.mode_count == 0
        || config.mode_count > order
        || config.maximum_sweeps == 0
        || config.maximum_sweeps > MAXIMUM_SWEEPS
        || tolerances
            .iter()
            .any(|value| !value.is_finite() || *value < 0.0)
        || config.eigensolver_relative_tolerance <= 0.0
    {
        return Err(error(
            "spectral_request_config_invalid",
            "/config",
            "generalized-eigen configuration is outside the bounded domain",
        ));
    }
    Ok(())
}

fn validate_result(
    result: &DenseSpectralResultIrV1,
    request: Option<&DenseSpectralAnalysisRequestV1>,
) -> Result<(), ProductIrContractError> {
    if result.schema_version != DENSE_SPECTRAL_RESULT_IR_V1
        || result.claim_boundary != RESULT_CLAIM_BOUNDARY
        || result.authority != ResultAuthorityV1::BoundedCandidate
        || result.backend_receipt != SpectralCpuExecutionReceiptV1::default()
    {
        return Err(error(
            "spectral_result_authority_invalid",
            "/",
            "spectral ResultIR schema, claim, or CPU receipt is invalid",
        ));
    }
    validate_hashes(&result.identity)?;
    validate_hash(&result.result_hash, "/result_hash", true)?;
    if !valid_case_id(&result.case_id)
        || result.summary.mode_count == 0
        || result.summary.mode_count > MAXIMUM_ORDER
        || usize::try_from(result.summary.mode_count).ok() != Some(result.modes.len())
    {
        return Err(error(
            "spectral_result_mode_count_invalid",
            "/summary/mode_count",
            "spectral ResultIR must publish exactly its declared nonzero mode count",
        ));
    }
    let order = if let Some(request) = request {
        if result.analysis_kind != request.analysis_kind || result.case_id != request.case_id {
            return Err(error(
                "spectral_result_request_identity_mismatch",
                "/",
                "spectral result analysis kind or case differs from its request",
            ));
        }
        if result.summary.mode_count != request.config.mode_count {
            return Err(error(
                "spectral_result_requested_mode_count_mismatch",
                "/summary/mode_count",
                "spectral result mode count differs from the exact request",
            ));
        }
        usize::try_from(request.order).map_err(|_| {
            error(
                "spectral_result_shape_invalid",
                "/modes",
                "request order exceeds the address space",
            )
        })?
    } else {
        mode_shape_length(&result.modes[0])
    };
    if order == 0 || order > usize::try_from(MAXIMUM_ORDER).unwrap_or(usize::MAX) {
        return Err(error(
            "spectral_result_shape_invalid",
            "/modes",
            "spectral mode order must remain within the bounded 1..128 domain",
        ));
    }
    for (index, mode) in result.modes.iter().enumerate() {
        validate_mode(mode, result.analysis_kind, order, index)?;
    }
    for pair in result.modes.windows(2) {
        let left = primary_mode_value(&pair[0]);
        let right = primary_mode_value(&pair[1]);
        if right < left && !relative_close(left, right) {
            return Err(error(
                "spectral_result_mode_order_invalid",
                "/modes",
                "spectral modes must be ordered by nondecreasing primary value",
            ));
        }
    }
    validate_result_summary(result, order)?;
    if result.units != SpectralUnitsV1::for_kind(result.analysis_kind) {
        return Err(error(
            "spectral_result_units_invalid",
            "/units",
            "spectral ResultIR units do not match its analysis kind",
        ));
    }
    Ok(())
}

fn validate_result_summary(
    result: &DenseSpectralResultIrV1,
    order: usize,
) -> Result<(), ProductIrContractError> {
    let summary = &result.summary;
    let order = u32::try_from(order).unwrap_or(u32::MAX);
    let summary_values = [
        summary.metric_orthogonality_error_inf,
        summary.operator_diagonalization_error_inf,
        summary.stiffness_relative_symmetry_error,
        summary.secondary_relative_symmetry_error,
        summary.stiffness_minimum_eigenvalue,
        summary.secondary_minimum_eigenvalue,
    ];
    if summary_values.iter().any(|value| !value.is_finite())
        || summary.eigensolver_sweeps > 3 * MAXIMUM_SWEEPS
        || summary.rigid_mode_count > order
        || summary.finite_positive_eigenvalue_count > order
        || summary.geometric_stiffness_positive_rank > order
        || summary.metric_orthogonality_error_inf < 0.0
        || summary.operator_diagonalization_error_inf < 0.0
        || summary.stiffness_relative_symmetry_error < 0.0
        || summary.secondary_relative_symmetry_error < 0.0
    {
        return Err(error(
            "spectral_result_summary_invalid",
            "/summary",
            "spectral summary metrics are invalid",
        ));
    }
    match result.analysis_kind {
        SpectralAnalysisKindV1::Modal => {
            let total_modes = summary.rigid_mode_count.checked_add(summary.mode_count);
            if summary.critical_load_factor.is_some()
                || summary.finite_positive_eigenvalue_count != 0
                || summary.geometric_stiffness_positive_rank != 0
                || !matches!(total_modes, Some(count) if count <= order)
            {
                return Err(error(
                    "spectral_result_modal_summary_invalid",
                    "/summary",
                    "modal summary contains buckling-only or impossible count fields",
                ));
            }
        }
        SpectralAnalysisKindV1::LinearBuckling => {
            if summary.rigid_mode_count != 0
                || summary.finite_positive_eigenvalue_count < summary.mode_count
                || !matches!(
                    summary.critical_load_factor,
                    Some(value) if value.is_finite() && value > 0.0
                )
                || !relative_close(
                    summary.critical_load_factor.unwrap_or_default(),
                    primary_mode_value(&result.modes[0]),
                )
            {
                return Err(error(
                    "spectral_result_buckling_summary_invalid",
                    "/summary/critical_load_factor",
                    "buckling critical load factor must be finite, positive, and match mode zero",
                ));
            }
        }
    }
    Ok(())
}

fn validate_mode(
    mode: &SpectralModeV1,
    kind: SpectralAnalysisKindV1,
    order: usize,
    index: usize,
) -> Result<(), ProductIrContractError> {
    let path = format!("/modes/{index}");
    match (kind, mode) {
        (SpectralAnalysisKindV1::Modal, SpectralModeV1::Modal { .. }) => {
            validate_modal_mode(mode, order, &path)?;
        }
        (SpectralAnalysisKindV1::LinearBuckling, SpectralModeV1::LinearBuckling { .. }) => {
            validate_buckling_mode(mode, order, &path)?;
        }
        _ => {
            return Err(error(
                "spectral_result_mode_kind_mismatch",
                &path,
                "mode variant does not match result analysis kind",
            ));
        }
    }
    Ok(())
}

fn validate_modal_mode(
    mode: &SpectralModeV1,
    order: usize,
    path: &str,
) -> Result<(), ProductIrContractError> {
    let SpectralModeV1::Modal {
        eigenvalue_rad2_per_s2,
        omega_rad_per_s,
        frequency_hz,
        period_s,
        mass_normalized_shape,
        max_component_normalized_shape,
        generalized_mass,
        generalized_stiffness,
        residual_relative_inf,
    } = mode
    else {
        unreachable!("modal validator is called only for modal variants");
    };
    let metrics = [
        *eigenvalue_rad2_per_s2,
        *omega_rad_per_s,
        *frequency_hz,
        *period_s,
        *generalized_mass,
        *generalized_stiffness,
        *residual_relative_inf,
    ];
    validate_mode_values(
        &metrics,
        mass_normalized_shape,
        max_component_normalized_shape,
        order,
        path,
    )?;
    if metrics[..6].iter().any(|value| *value <= 0.0) || *residual_relative_inf < 0.0 {
        return Err(error(
            "spectral_result_modal_mode_invalid",
            path,
            "modal mode metrics must be positive with nonnegative residual",
        ));
    }
    let expected_omega = eigenvalue_rad2_per_s2.sqrt();
    let expected_frequency = expected_omega / (2.0 * std::f64::consts::PI);
    let expected_period = (2.0 * std::f64::consts::PI) / expected_omega;
    if !relative_close(*omega_rad_per_s, expected_omega)
        || !relative_close(*frequency_hz, expected_frequency)
        || !relative_close(*period_s, expected_period)
        || !relative_close(*generalized_mass, 1.0)
        || !relative_close(*generalized_stiffness, *eigenvalue_rad2_per_s2)
    {
        return Err(error(
            "spectral_result_modal_derived_value_invalid",
            path,
            "modal frequency, period, normalization, or Rayleigh values are inconsistent",
        ));
    }
    Ok(())
}

fn validate_buckling_mode(
    mode: &SpectralModeV1,
    order: usize,
    path: &str,
) -> Result<(), ProductIrContractError> {
    let SpectralModeV1::LinearBuckling {
        load_factor,
        stiffness_normalized_shape,
        max_component_normalized_shape,
        generalized_elastic_stiffness,
        generalized_geometric_stiffness,
        residual_relative_inf,
    } = mode
    else {
        unreachable!("buckling validator is called only for buckling variants");
    };
    let metrics = [
        *load_factor,
        *generalized_elastic_stiffness,
        *generalized_geometric_stiffness,
        *residual_relative_inf,
    ];
    validate_mode_values(
        &metrics,
        stiffness_normalized_shape,
        max_component_normalized_shape,
        order,
        path,
    )?;
    if metrics[..3].iter().any(|value| *value <= 0.0) || *residual_relative_inf < 0.0 {
        return Err(error(
            "spectral_result_buckling_mode_invalid",
            path,
            "buckling mode metrics must be positive with nonnegative residual",
        ));
    }
    if !relative_close(*generalized_elastic_stiffness, 1.0)
        || !relative_close(
            *load_factor,
            *generalized_elastic_stiffness / *generalized_geometric_stiffness,
        )
    {
        return Err(error(
            "spectral_result_buckling_derived_value_invalid",
            path,
            "buckling normalization or Rayleigh load factor is inconsistent",
        ));
    }
    Ok(())
}

fn validate_mode_values(
    metrics: &[f64],
    shape: &[f64],
    max_shape: &[f64],
    order: usize,
    path: &str,
) -> Result<(), ProductIrContractError> {
    if metrics.iter().any(|value| !value.is_finite())
        || shape.len() != order
        || max_shape.len() != order
    {
        return Err(error(
            "spectral_result_mode_shape_invalid",
            path,
            "mode metrics must be finite and both shapes must match matrix order",
        ));
    }
    validate_finite_slice(shape, path)?;
    validate_finite_slice(max_shape, path)?;
    let source_maximum = shape.iter().map(|value| value.abs()).fold(0.0, f64::max);
    let max_component = max_shape
        .iter()
        .map(|value| value.abs())
        .fold(0.0, f64::max);
    if source_maximum <= 0.0
        || (max_component - 1.0).abs() > 1.0e-10
        || shape
            .iter()
            .zip(max_shape)
            .any(|(source, normalized)| (*normalized - (*source / source_maximum)).abs() > 1.0e-10)
    {
        return Err(error(
            "spectral_result_max_shape_invalid",
            path,
            "max-component-normalized shape must have unit maximum magnitude",
        ));
    }
    Ok(())
}

fn validate_report(report: &DenseSpectralReportIrV1) -> Result<(), ProductIrContractError> {
    if report.schema_version != DENSE_SPECTRAL_REPORT_IR_V1
        || report.report_kind != "dense_spectral_summary"
        || report.claim_boundary != REPORT_CLAIM_BOUNDARY
        || report.authority != ResultAuthorityV1::BoundedCandidate
        || report.case_id.is_empty()
        || report.summary.mode_count == 0
        || !report.summary.primary_value.is_finite()
        || report.summary.primary_value <= 0.0
        || !report.summary.maximum_residual_relative_inf.is_finite()
        || report.summary.maximum_residual_relative_inf < 0.0
    {
        return Err(error(
            "spectral_report_invariant_invalid",
            "/",
            "spectral ReportIR fixed fields or summary are invalid",
        ));
    }
    validate_hash(&report.source_result_hash, "/source_result_hash", false)?;
    validate_hash(&report.document_source_hash, "/document_source_hash", false)?;
    validate_hash(&report.report_hash, "/report_hash", true)?;
    validate_hashes(&report.identity)
}

fn relative_close(left: f64, right: f64) -> bool {
    let scale = left.abs().max(right.abs()).max(1.0);
    (left - right).abs() <= 1.0e-10 * scale
}

fn valid_case_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.'))
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
    if digest.len() != 64
        || !digest
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Err(error(
            "spectral_hash_invalid",
            path,
            "hash must be sha256 plus 64 lowercase hexadecimal digits",
        ));
    }
    Ok(())
}

fn validate_finite_slice(values: &[f64], path: &str) -> Result<(), ProductIrContractError> {
    if values.iter().any(|value| !value.is_finite()) {
        Err(error(
            "spectral_nonfinite_value",
            path,
            "spectral contract accepts only finite binary64 values",
        ))
    } else {
        Ok(())
    }
}

fn mode_shape_length(mode: &SpectralModeV1) -> usize {
    match mode {
        SpectralModeV1::Modal {
            mass_normalized_shape,
            ..
        } => mass_normalized_shape.len(),
        SpectralModeV1::LinearBuckling {
            stiffness_normalized_shape,
            ..
        } => stiffness_normalized_shape.len(),
    }
}

fn primary_mode_value(mode: &SpectralModeV1) -> f64 {
    match mode {
        SpectralModeV1::Modal {
            eigenvalue_rad2_per_s2,
            ..
        } => *eigenvalue_rad2_per_s2,
        SpectralModeV1::LinearBuckling { load_factor, .. } => *load_factor,
    }
}

fn mode_residual(mode: &SpectralModeV1) -> f64 {
    match mode {
        SpectralModeV1::Modal {
            residual_relative_inf,
            ..
        }
        | SpectralModeV1::LinearBuckling {
            residual_relative_inf,
            ..
        } => *residual_relative_inf,
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
            "spectral value could not be represented as canonical JSON",
        )
    })
}

fn canonical_struct<T: Serialize>(value: &T, code: &str) -> Result<String, ProductIrContractError> {
    let value = serde_json::to_value(value).map_err(|_| {
        error(
            code,
            "/",
            "typed spectral value could not be represented as JSON",
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
            "typed spectral value could not be represented as JSON",
        )
    })?;
    value
        .as_object_mut()
        .and_then(|object| object.remove(field))
        .ok_or_else(|| error(code, "/", "spectral self-hash field is missing"))?;
    Ok(sha256_identity(canonical_value(&value, code)?.as_bytes()))
}

fn error(code: &str, path: &str, detail: &str) -> ProductIrContractError {
    ProductIrContractError {
        code: code.to_owned(),
        path: path.to_owned(),
        detail: detail.to_owned(),
    }
}

#[cfg(test)]
mod tests {
    use super::{
        build_dense_spectral_request_v1, parse_dense_spectral_request_v1,
        DenseSpectralAnalysisRequestV1, SpectralAnalysisKindV1, SpectralBackendV1,
        SpectralGeneralizedEigenConfigV1, DENSE_SPECTRAL_REQUEST_V1,
    };

    fn request() -> DenseSpectralAnalysisRequestV1 {
        DenseSpectralAnalysisRequestV1 {
            schema_version: DENSE_SPECTRAL_REQUEST_V1.to_owned(),
            operation: "solve_dense_generalized_eigen".to_owned(),
            case_id: "modal-two".to_owned(),
            analysis_kind: SpectralAnalysisKindV1::Modal,
            backend: SpectralBackendV1::Cpu,
            order: 2,
            stiffness: vec![2.0, -1.0, -1.0, 1.0],
            secondary_matrix: vec![1.0, 0.0, 0.0, 1.0],
            coordinate_recovery_scale: Vec::new(),
            config: SpectralGeneralizedEigenConfigV1 {
                mode_count: 2,
                maximum_sweeps: 128,
                symmetry_relative_tolerance: 1.0e-12,
                positive_semidefinite_relative_tolerance: 1.0e-12,
                mode_relative_tolerance: 1.0e-12,
                cluster_relative_tolerance: 1.0e-10,
                residual_relative_tolerance: 1.0e-10,
                orthogonality_tolerance: 1.0e-10,
                eigensolver_relative_tolerance: 1.0e-14,
            },
        }
    }

    #[test]
    fn typed_request_is_strict_canonical_and_hash_bound() {
        let built = build_dense_spectral_request_v1(request()).expect("build");
        let parsed = parse_dense_spectral_request_v1(built.canonical_bytes()).expect("parse");
        assert_eq!(parsed.request(), built.request());
        assert_eq!(parsed.request_hash(), built.request_hash());
        assert_eq!(parsed.canonical_bytes(), built.canonical_bytes());
    }

    #[test]
    fn duplicate_unknown_nonfinite_and_length_drift_fail_closed() {
        let built = build_dense_spectral_request_v1(request()).expect("build");
        let duplicate = built.canonical_json().replacen('{', "{\"order\":2,", 1);
        assert!(parse_dense_spectral_request_v1(duplicate.as_bytes()).is_err());
        let unknown = built.canonical_json().replacen('{', "{\"extra\":0,", 1);
        assert!(parse_dense_spectral_request_v1(unknown.as_bytes()).is_err());
        let mut nonfinite = request();
        nonfinite.stiffness[0] = f64::INFINITY;
        assert!(build_dense_spectral_request_v1(nonfinite).is_err());
        let mut invalid = request();
        invalid.stiffness.pop();
        assert!(build_dense_spectral_request_v1(invalid).is_err());
    }
}
