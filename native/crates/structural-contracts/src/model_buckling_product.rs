//! Strict product request binding a typed `ModelIR` reference equilibrium to bounded CPU
//! linear-buckling execution.

use serde::{Deserialize, Serialize};

use crate::model_ir::{canonicalize_model_ir_v2, decode_json_strict};
use crate::product_ir::{sha256_identity, ModelIrIdentityV1, ProductIrContractError};
use crate::sparse_product::SparseLinearConfigV1;
use crate::spectral_product::SpectralGeneralizedEigenConfigV1;

pub const MODEL_IR_LINEAR_BUCKLING_ANALYSIS_REQUEST_V1: &str =
    "structural-model-ir-linear-buckling-analysis-request.v1";
pub const MODEL_IR_LINEAR_BUCKLING_MAXIMUM_REQUEST_BYTES: usize = 1024 * 1024;

const OPERATION: &str = "solve_model_ir_linear_buckling";
const MAXIMUM_SWEEPS: u32 = 4_096;

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ModelIrLinearBucklingBackendV1 {
    Cpu,
}

/// Explicit controls for one bounded reference-static plus linear-buckling execution.
#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ModelIrLinearBucklingAnalysisRequestV1 {
    pub schema_version: String,
    pub operation: String,
    pub case_id: String,
    pub backend: ModelIrLinearBucklingBackendV1,
    pub model_identity: ModelIrIdentityV1,
    pub reference_load_pattern_id: String,
    pub reference_linear_config: SparseLinearConfigV1,
    pub buckling_config: SpectralGeneralizedEigenConfigV1,
}

/// Canonical request and exact SHA-256 identity.
#[derive(Clone, Debug)]
pub struct ModelIrLinearBucklingAnalysisRequestDocumentV1 {
    request: ModelIrLinearBucklingAnalysisRequestV1,
    canonical_json: String,
    request_hash: String,
}

impl ModelIrLinearBucklingAnalysisRequestDocumentV1 {
    #[must_use]
    pub const fn request(&self) -> &ModelIrLinearBucklingAnalysisRequestV1 {
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

/// Strictly decode, validate, canonicalize and hash one bounded request.
///
/// # Errors
///
/// Returns a stable contract error for malformed or duplicate JSON, unknown fields, invalid
/// identities/selectors, or solver controls outside the bounded CPU domain.
pub fn parse_model_ir_linear_buckling_analysis_request_v1(
    bytes: &[u8],
) -> Result<ModelIrLinearBucklingAnalysisRequestDocumentV1, ProductIrContractError> {
    if bytes.is_empty() || bytes.len() > MODEL_IR_LINEAR_BUCKLING_MAXIMUM_REQUEST_BYTES {
        return Err(error(
            "model_ir_linear_buckling_request_size_invalid",
            "/",
            "ModelIR linear-buckling request is outside the bounded size",
        ));
    }
    let value = decode_json_strict(bytes).map_err(|source| {
        error(
            "model_ir_linear_buckling_request_json_invalid",
            &source.path,
            &source.detail,
        )
    })?;
    let request: ModelIrLinearBucklingAnalysisRequestV1 = serde_json::from_value(value.clone())
        .map_err(|_| {
            error(
                "model_ir_linear_buckling_request_decode_failed",
                "/",
                "request has unknown, missing, or mistyped fields",
            )
        })?;
    finish(request, &value)
}

/// Validate, canonicalize and hash one typed request.
///
/// # Errors
///
/// Returns the same stable contract errors as the strict parser.
pub fn build_model_ir_linear_buckling_analysis_request_v1(
    request: ModelIrLinearBucklingAnalysisRequestV1,
) -> Result<ModelIrLinearBucklingAnalysisRequestDocumentV1, ProductIrContractError> {
    let value = serde_json::to_value(&request).map_err(|_| {
        error(
            "model_ir_linear_buckling_request_encode_failed",
            "/",
            "typed request could not be represented as JSON",
        )
    })?;
    finish(request, &value)
}

fn finish(
    request: ModelIrLinearBucklingAnalysisRequestV1,
    value: &serde_json::Value,
) -> Result<ModelIrLinearBucklingAnalysisRequestDocumentV1, ProductIrContractError> {
    validate_request(&request)?;
    let canonical_json = canonicalize_model_ir_v2(value).map_err(|source| {
        error(
            "model_ir_linear_buckling_request_canonicalization_failed",
            &source.path,
            &source.detail,
        )
    })?;
    if canonical_json.len() > MODEL_IR_LINEAR_BUCKLING_MAXIMUM_REQUEST_BYTES {
        return Err(error(
            "model_ir_linear_buckling_request_size_invalid",
            "/",
            "canonical ModelIR linear-buckling request exceeds the bounded size",
        ));
    }
    Ok(ModelIrLinearBucklingAnalysisRequestDocumentV1 {
        request_hash: sha256_identity(canonical_json.as_bytes()),
        request,
        canonical_json,
    })
}

fn validate_request(
    request: &ModelIrLinearBucklingAnalysisRequestV1,
) -> Result<(), ProductIrContractError> {
    if request.schema_version != MODEL_IR_LINEAR_BUCKLING_ANALYSIS_REQUEST_V1
        || request.operation != OPERATION
    {
        return Err(error(
            "model_ir_linear_buckling_request_identity_invalid",
            "/",
            "request schema or operation is unsupported",
        ));
    }
    validate_identifier(&request.case_id, "/case_id", false)?;
    validate_identifier(
        &request.reference_load_pattern_id,
        "/reference_load_pattern_id",
        true,
    )?;
    validate_hash(
        &request.model_identity.content_hash,
        "/model_identity/content_hash",
    )?;
    validate_hash(
        &request.model_identity.semantic_hash,
        "/model_identity/semantic_hash",
    )?;
    validate_hash(
        &request.model_identity.provenance_hash,
        "/model_identity/provenance_hash",
    )?;
    validate_linear_config(request.reference_linear_config)?;
    validate_buckling_config(request.buckling_config)
}

fn validate_linear_config(config: SparseLinearConfigV1) -> Result<(), ProductIrContractError> {
    let valid = (1..=1_000_000).contains(&config.max_iterations)
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
            "model_ir_linear_buckling_reference_config_invalid",
            "/reference_linear_config",
            "reference PCG configuration is outside the bounded CPU product domain",
        ))
    }
}

fn validate_buckling_config(
    config: SpectralGeneralizedEigenConfigV1,
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
    let valid = config.mode_count > 0
        && config.mode_count <= 128
        && config.maximum_sweeps > 0
        && config.maximum_sweeps <= MAXIMUM_SWEEPS
        && tolerances
            .iter()
            .all(|value| value.is_finite() && *value > 0.0);
    if valid {
        Ok(())
    } else {
        Err(error(
            "model_ir_linear_buckling_spectral_config_invalid",
            "/buckling_config",
            "buckling configuration is outside the bounded dense CPU product domain",
        ))
    }
}

fn validate_identifier(
    value: &str,
    path: &str,
    allow_colon: bool,
) -> Result<(), ProductIrContractError> {
    let bytes = value.as_bytes();
    let valid = !bytes.is_empty()
        && bytes.len() <= 128
        && bytes[0].is_ascii_alphanumeric()
        && bytes.iter().all(|byte| {
            byte.is_ascii_alphanumeric()
                || matches!(*byte, b'_' | b'-' | b'.')
                || (allow_colon && *byte == b':')
        });
    if valid {
        Ok(())
    } else {
        Err(error(
            "model_ir_linear_buckling_request_identifier_invalid",
            path,
            "identifier must be 1..128 portable bytes and begin with an alphanumeric byte",
        ))
    }
}

fn validate_hash(value: &str, path: &str) -> Result<(), ProductIrContractError> {
    let suffix = value.strip_prefix("sha256:");
    if suffix.is_some_and(|hex| {
        hex.len() == 64
            && hex
                .as_bytes()
                .iter()
                .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    }) {
        Ok(())
    } else {
        Err(error(
            "model_ir_linear_buckling_request_hash_invalid",
            path,
            "identity must use canonical lowercase sha256:<64 hex>",
        ))
    }
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
        build_model_ir_linear_buckling_analysis_request_v1,
        parse_model_ir_linear_buckling_analysis_request_v1, ModelIrLinearBucklingAnalysisRequestV1,
        ModelIrLinearBucklingBackendV1, MODEL_IR_LINEAR_BUCKLING_ANALYSIS_REQUEST_V1,
    };
    use crate::product_ir::ModelIrIdentityV1;
    use crate::sparse_product::SparseLinearConfigV1;
    use crate::spectral_product::SpectralGeneralizedEigenConfigV1;

    fn request() -> ModelIrLinearBucklingAnalysisRequestV1 {
        ModelIrLinearBucklingAnalysisRequestV1 {
            schema_version: MODEL_IR_LINEAR_BUCKLING_ANALYSIS_REQUEST_V1.to_owned(),
            operation: "solve_model_ir_linear_buckling".to_owned(),
            case_id: "frame-buckling-1".to_owned(),
            backend: ModelIrLinearBucklingBackendV1::Cpu,
            model_identity: ModelIrIdentityV1 {
                content_hash: format!("sha256:{}", "1".repeat(64)),
                semantic_hash: format!("sha256:{}", "2".repeat(64)),
                provenance_hash: format!("sha256:{}", "3".repeat(64)),
            },
            reference_load_pattern_id: "LC_COMPRESSION".to_owned(),
            reference_linear_config: SparseLinearConfigV1 {
                max_iterations: 128,
                absolute_residual_tolerance: 1e-12,
                relative_residual_tolerance: 1e-12,
                maximum_increment: 0.0,
            },
            buckling_config: SpectralGeneralizedEigenConfigV1 {
                mode_count: 2,
                maximum_sweeps: 128,
                symmetry_relative_tolerance: 1e-12,
                positive_semidefinite_relative_tolerance: 1e-12,
                mode_relative_tolerance: 1e-10,
                cluster_relative_tolerance: 1e-9,
                residual_relative_tolerance: 1e-9,
                orthogonality_tolerance: 1e-9,
                eigensolver_relative_tolerance: 1e-12,
            },
        }
    }

    #[test]
    fn typed_and_strict_request_round_trip_canonically() {
        let built = build_model_ir_linear_buckling_analysis_request_v1(request()).expect("request");
        let parsed = parse_model_ir_linear_buckling_analysis_request_v1(built.canonical_bytes())
            .expect("strict request");
        assert_eq!(parsed.canonical_json(), built.canonical_json());
        assert_eq!(parsed.request_hash(), built.request_hash());
    }

    #[test]
    fn unknown_fields_and_invalid_controls_fail_closed() {
        let built = build_model_ir_linear_buckling_analysis_request_v1(request()).expect("request");
        let unknown = built
            .canonical_json()
            .replacen('{', "{\"unexpected\":true,", 1);
        assert!(parse_model_ir_linear_buckling_analysis_request_v1(unknown.as_bytes()).is_err());

        let mut invalid = request();
        invalid.buckling_config.mode_count = 0;
        assert!(build_model_ir_linear_buckling_analysis_request_v1(invalid).is_err());
    }
}
