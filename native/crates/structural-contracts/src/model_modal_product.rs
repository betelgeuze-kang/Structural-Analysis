//! Strict product request binding typed `ModelIR` assembly to bounded CPU modal execution.

use serde::{Deserialize, Serialize};

use crate::model_ir::{canonicalize_model_ir_v2, decode_json_strict};
use crate::product_ir::{sha256_identity, ModelIrIdentityV1, ProductIrContractError};
use crate::spectral_product::SpectralGeneralizedEigenConfigV1;

pub const MODEL_IR_MODAL_ANALYSIS_REQUEST_V1: &str =
    "structural-model-ir-modal-analysis-request.v1";
pub const MODEL_IR_MODAL_MAXIMUM_REQUEST_BYTES: usize = 1024 * 1024;

const OPERATION: &str = "solve_model_ir_modal";
const MAXIMUM_SWEEPS: u32 = 4_096;

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ModelIrModalBackendV1 {
    Cpu,
}

/// Explicit controls for one bounded typed-`ModelIR` modal execution.
///
/// `assembly_load_pattern_id` is an existing linear load selector required by the current
/// append-only assembly ABI. Its load vector is not consumed by modal execution.
#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ModelIrModalAnalysisRequestV1 {
    pub schema_version: String,
    pub operation: String,
    pub case_id: String,
    pub backend: ModelIrModalBackendV1,
    pub model_identity: ModelIrIdentityV1,
    pub assembly_load_pattern_id: String,
    pub config: SpectralGeneralizedEigenConfigV1,
}

/// Canonical request and exact SHA-256 identity.
#[derive(Clone, Debug)]
pub struct ModelIrModalAnalysisRequestDocumentV1 {
    request: ModelIrModalAnalysisRequestV1,
    canonical_json: String,
    request_hash: String,
}

impl ModelIrModalAnalysisRequestDocumentV1 {
    #[must_use]
    pub const fn request(&self) -> &ModelIrModalAnalysisRequestV1 {
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

/// Strictly decode, validate, canonicalize and hash one bounded `ModelIR` modal request.
///
/// # Errors
///
/// Returns a stable contract error for malformed or duplicate JSON, unknown fields, invalid
/// identities/selectors, or modal controls outside the bounded dense CPU domain.
pub fn parse_model_ir_modal_analysis_request_v1(
    bytes: &[u8],
) -> Result<ModelIrModalAnalysisRequestDocumentV1, ProductIrContractError> {
    if bytes.is_empty() || bytes.len() > MODEL_IR_MODAL_MAXIMUM_REQUEST_BYTES {
        return Err(error(
            "model_ir_modal_request_size_invalid",
            "/",
            "ModelIR modal request is outside the bounded size",
        ));
    }
    let value = decode_json_strict(bytes).map_err(|source| {
        error(
            "model_ir_modal_request_json_invalid",
            &source.path,
            &source.detail,
        )
    })?;
    let request: ModelIrModalAnalysisRequestV1 =
        serde_json::from_value(value.clone()).map_err(|_| {
            error(
                "model_ir_modal_request_decode_failed",
                "/",
                "request has unknown, missing, or mistyped fields",
            )
        })?;
    finish(request, &value)
}

/// Validate, canonicalize and hash one typed `ModelIR` modal request.
///
/// # Errors
///
/// Returns the same stable contract errors as the strict parser.
pub fn build_model_ir_modal_analysis_request_v1(
    request: ModelIrModalAnalysisRequestV1,
) -> Result<ModelIrModalAnalysisRequestDocumentV1, ProductIrContractError> {
    let value = serde_json::to_value(&request).map_err(|_| {
        error(
            "model_ir_modal_request_encode_failed",
            "/",
            "typed request could not be represented as JSON",
        )
    })?;
    finish(request, &value)
}

fn finish(
    request: ModelIrModalAnalysisRequestV1,
    value: &serde_json::Value,
) -> Result<ModelIrModalAnalysisRequestDocumentV1, ProductIrContractError> {
    validate_request(&request)?;
    let canonical_json = canonicalize_model_ir_v2(value).map_err(|source| {
        error(
            "model_ir_modal_request_canonicalization_failed",
            &source.path,
            &source.detail,
        )
    })?;
    if canonical_json.len() > MODEL_IR_MODAL_MAXIMUM_REQUEST_BYTES {
        return Err(error(
            "model_ir_modal_request_size_invalid",
            "/",
            "canonical ModelIR modal request exceeds the bounded size",
        ));
    }
    Ok(ModelIrModalAnalysisRequestDocumentV1 {
        request_hash: sha256_identity(canonical_json.as_bytes()),
        request,
        canonical_json,
    })
}

fn validate_request(request: &ModelIrModalAnalysisRequestV1) -> Result<(), ProductIrContractError> {
    if request.schema_version != MODEL_IR_MODAL_ANALYSIS_REQUEST_V1
        || request.operation != OPERATION
    {
        return Err(error(
            "model_ir_modal_request_identity_invalid",
            "/",
            "request schema or operation is unsupported",
        ));
    }
    validate_identifier(&request.case_id, "/case_id", false)?;
    validate_identifier(
        &request.assembly_load_pattern_id,
        "/assembly_load_pattern_id",
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
    validate_config(request.config)
}

fn validate_config(config: SpectralGeneralizedEigenConfigV1) -> Result<(), ProductIrContractError> {
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
            "model_ir_modal_request_config_invalid",
            "/config",
            "modal configuration is outside the bounded dense CPU product domain",
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
            "model_ir_modal_request_identifier_invalid",
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
            "model_ir_modal_request_hash_invalid",
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
        build_model_ir_modal_analysis_request_v1, parse_model_ir_modal_analysis_request_v1,
        ModelIrModalAnalysisRequestV1, ModelIrModalBackendV1, MODEL_IR_MODAL_ANALYSIS_REQUEST_V1,
    };
    use crate::product_ir::ModelIrIdentityV1;
    use crate::spectral_product::SpectralGeneralizedEigenConfigV1;

    fn request() -> ModelIrModalAnalysisRequestV1 {
        ModelIrModalAnalysisRequestV1 {
            schema_version: MODEL_IR_MODAL_ANALYSIS_REQUEST_V1.to_owned(),
            operation: "solve_model_ir_modal".to_owned(),
            case_id: "frame-modal-1".to_owned(),
            backend: ModelIrModalBackendV1::Cpu,
            model_identity: ModelIrIdentityV1 {
                content_hash: format!("sha256:{}", "1".repeat(64)),
                semantic_hash: format!("sha256:{}", "2".repeat(64)),
                provenance_hash: format!("sha256:{}", "3".repeat(64)),
            },
            assembly_load_pattern_id: "LC_WEAK".to_owned(),
            config: SpectralGeneralizedEigenConfigV1 {
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
        let built = build_model_ir_modal_analysis_request_v1(request()).expect("request");
        let parsed = parse_model_ir_modal_analysis_request_v1(built.canonical_bytes())
            .expect("strict request");
        assert_eq!(parsed.canonical_json(), built.canonical_json());
        assert_eq!(parsed.request_hash(), built.request_hash());
    }

    #[test]
    fn unknown_fields_and_invalid_modal_controls_fail_closed() {
        let built = build_model_ir_modal_analysis_request_v1(request()).expect("request");
        let unknown = built
            .canonical_json()
            .replacen('{', "{\"unexpected\":true,", 1);
        assert!(parse_model_ir_modal_analysis_request_v1(unknown.as_bytes()).is_err());

        let mut invalid = request();
        invalid.config.mode_count = 0;
        assert!(build_model_ir_modal_analysis_request_v1(invalid).is_err());
    }
}
