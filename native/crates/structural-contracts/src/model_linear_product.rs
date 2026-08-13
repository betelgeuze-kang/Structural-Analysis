//! Strict product request binding typed `ModelIR` assembly to sparse CPU execution.

use serde::{Deserialize, Serialize};

use crate::model_ir::{canonicalize_model_ir_v2, decode_json_strict};
use crate::product_ir::{sha256_identity, ModelIrIdentityV1, ProductIrContractError};
use crate::sparse_product::SparseLinearConfigV1;

pub const MODEL_IR_LINEAR_ANALYSIS_REQUEST_V1: &str =
    "structural-model-ir-linear-analysis-request.v1";
pub const MODEL_IR_LINEAR_MAXIMUM_REQUEST_BYTES: usize = 4 * 1024 * 1024;
pub const MODEL_IR_LINEAR_MAXIMUM_RECOVERY_RECORDS: usize = 100_000;

const OPERATION: &str = "solve_model_ir_linear_static";

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ModelIrLinearBackendV1 {
    Cpu,
}

/// Explicit analysis controls kept separate from the immutable structural model.
#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ModelIrLinearAnalysisRequestV1 {
    pub schema_version: String,
    pub operation: String,
    pub case_id: String,
    pub backend: ModelIrLinearBackendV1,
    pub model_identity: ModelIrIdentityV1,
    pub load_pattern_id: String,
    pub config: SparseLinearConfigV1,
}

/// Canonical request and its exact SHA-256 identity.
#[derive(Clone, Debug)]
pub struct ModelIrLinearAnalysisRequestDocumentV1 {
    request: ModelIrLinearAnalysisRequestV1,
    canonical_json: String,
    request_hash: String,
}

impl ModelIrLinearAnalysisRequestDocumentV1 {
    #[must_use]
    pub const fn request(&self) -> &ModelIrLinearAnalysisRequestV1 {
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

/// Strictly decode, validate, canonicalize, and hash one bounded analysis request.
///
/// # Errors
///
/// Returns a stable product-contract error for malformed JSON, duplicate/unknown fields,
/// noncanonical identities, invalid selectors, or an invalid bounded PCG configuration.
pub fn parse_model_ir_linear_analysis_request_v1(
    bytes: &[u8],
) -> Result<ModelIrLinearAnalysisRequestDocumentV1, ProductIrContractError> {
    if bytes.is_empty() || bytes.len() > MODEL_IR_LINEAR_MAXIMUM_REQUEST_BYTES {
        return Err(error(
            "model_ir_linear_request_size_invalid",
            "/",
            "ModelIR linear analysis request is outside the bounded size",
        ));
    }
    let value = decode_json_strict(bytes).map_err(|source| {
        error(
            "model_ir_linear_request_json_invalid",
            &source.path,
            &source.detail,
        )
    })?;
    let request: ModelIrLinearAnalysisRequestV1 =
        serde_json::from_value(value.clone()).map_err(|_| {
            error(
                "model_ir_linear_request_decode_failed",
                "/",
                "request has unknown, missing, or mistyped fields",
            )
        })?;
    validate_request(&request)?;
    let canonical_json = canonicalize_model_ir_v2(&value).map_err(|source| {
        error(
            "model_ir_linear_request_canonicalization_failed",
            &source.path,
            &source.detail,
        )
    })?;
    if canonical_json.len() > MODEL_IR_LINEAR_MAXIMUM_REQUEST_BYTES {
        return Err(error(
            "model_ir_linear_request_size_invalid",
            "/",
            "canonical ModelIR linear request exceeds the bounded size",
        ));
    }
    Ok(ModelIrLinearAnalysisRequestDocumentV1 {
        request_hash: sha256_identity(canonical_json.as_bytes()),
        request,
        canonical_json,
    })
}

fn validate_request(
    request: &ModelIrLinearAnalysisRequestV1,
) -> Result<(), ProductIrContractError> {
    if request.schema_version != MODEL_IR_LINEAR_ANALYSIS_REQUEST_V1
        || request.operation != OPERATION
    {
        return Err(error(
            "model_ir_linear_request_identity_invalid",
            "/",
            "request schema or operation is unsupported",
        ));
    }
    validate_case_id(&request.case_id)?;
    validate_stable_id(&request.load_pattern_id, "/load_pattern_id")?;
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
    validate_sparse_config(request.config)
}

fn validate_sparse_config(config: SparseLinearConfigV1) -> Result<(), ProductIrContractError> {
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
            "model_ir_linear_request_config_invalid",
            "/config",
            "PCG configuration is outside the bounded product domain",
        ))
    }
}

fn validate_stable_id(value: &str, path: &str) -> Result<(), ProductIrContractError> {
    let bytes = value.as_bytes();
    let valid = !bytes.is_empty()
        && bytes.len() <= 128
        && bytes[0].is_ascii_alphanumeric()
        && bytes
            .iter()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(*byte, b'_' | b'-' | b'.' | b':'));
    if valid {
        Ok(())
    } else {
        Err(error(
            "model_ir_linear_request_identifier_invalid",
            path,
            "identifier must be 1..128 portable bytes and begin with an alphanumeric byte",
        ))
    }
}

fn validate_case_id(value: &str) -> Result<(), ProductIrContractError> {
    let bytes = value.as_bytes();
    let valid = !bytes.is_empty()
        && bytes.len() <= 128
        && bytes[0].is_ascii_alphanumeric()
        && bytes
            .iter()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(*byte, b'_' | b'-' | b'.'));
    if valid {
        Ok(())
    } else {
        Err(error(
            "model_ir_linear_request_case_id_invalid",
            "/case_id",
            "case_id must be 1..128 portable sparse-product identifier bytes",
        ))
    }
}

fn validate_hash(value: &str, path: &str) -> Result<(), ProductIrContractError> {
    let digest = value.strip_prefix("sha256:").unwrap_or_default();
    if digest.len() == 64
        && digest
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        Ok(())
    } else {
        Err(error(
            "model_ir_linear_request_hash_invalid",
            path,
            "identity must be lowercase sha256:<64 hex>",
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
    use serde_json::json;

    use super::parse_model_ir_linear_analysis_request_v1;

    fn request() -> Vec<u8> {
        serde_json::to_vec(&json!({
            "schema_version": "structural-model-ir-linear-analysis-request.v1",
            "operation": "solve_model_ir_linear_static",
            "case_id": "frame-linear-c5",
            "backend": "cpu",
            "model_identity": {
                "content_hash": format!("sha256:{}", "1".repeat(64)),
                "semantic_hash": format!("sha256:{}", "2".repeat(64)),
                "provenance_hash": format!("sha256:{}", "3".repeat(64))
            },
            "load_pattern_id": "LC_WEAK",
            "config": {
                "max_iterations": 100,
                "absolute_residual_tolerance": 1e-12,
                "relative_residual_tolerance": 1e-12,
                "maximum_increment": 0.0
            }
        }))
        .expect("request JSON")
    }

    #[test]
    fn strict_request_is_canonical_and_self_identified() {
        let first = parse_model_ir_linear_analysis_request_v1(&request()).expect("request");
        let repeated = parse_model_ir_linear_analysis_request_v1(first.canonical_bytes())
            .expect("canonical request");
        assert_eq!(first.canonical_json(), repeated.canonical_json());
        assert_eq!(first.request_hash(), repeated.request_hash());
        assert_eq!(first.request().load_pattern_id, "LC_WEAK");
    }

    #[test]
    fn duplicate_unknown_and_invalid_identity_fail_closed() {
        let duplicate = br#"{"schema_version":"structural-model-ir-linear-analysis-request.v1","schema_version":"structural-model-ir-linear-analysis-request.v1"}"#;
        assert_eq!(
            parse_model_ir_linear_analysis_request_v1(duplicate)
                .expect_err("duplicate key")
                .code,
            "model_ir_linear_request_json_invalid"
        );

        let mut value: serde_json::Value = serde_json::from_slice(&request()).expect("JSON");
        value["unknown"] = json!(true);
        assert_eq!(
            parse_model_ir_linear_analysis_request_v1(
                &serde_json::to_vec(&value).expect("unknown JSON")
            )
            .expect_err("unknown field")
            .code,
            "model_ir_linear_request_decode_failed"
        );
        value.as_object_mut().expect("object").remove("unknown");
        value["case_id"] = json!("invalid:case");
        assert_eq!(
            parse_model_ir_linear_analysis_request_v1(
                &serde_json::to_vec(&value).expect("bad case JSON")
            )
            .expect_err("bad case")
            .code,
            "model_ir_linear_request_case_id_invalid"
        );
        value["case_id"] = json!("frame-linear-c5");
        value["model_identity"]["content_hash"] = json!("sha256:ABC");
        assert_eq!(
            parse_model_ir_linear_analysis_request_v1(
                &serde_json::to_vec(&value).expect("bad hash JSON")
            )
            .expect_err("bad hash")
            .code,
            "model_ir_linear_request_hash_invalid"
        );
    }
}
