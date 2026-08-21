//! Language-neutral durable submission envelope for typed-`ModelIR` linear-buckling execution.

use serde::Deserialize;
use serde_json::{json, Value};

use crate::model_buckling_product::{
    parse_model_ir_linear_buckling_analysis_request_v1,
    ModelIrLinearBucklingAnalysisRequestDocumentV1, MODEL_IR_LINEAR_BUCKLING_MAXIMUM_REQUEST_BYTES,
};
use crate::model_ir::{
    canonicalize_model_ir_v2, decode_json_strict, parse_model_ir_v2, ModelIrContractError,
    ModelIrV2Document,
};
use crate::model_linear_job::MODEL_IR_LINEAR_MAXIMUM_MODEL_BYTES;
use crate::product_ir::{sha256_identity, ProductIrContractError};

pub const MODEL_IR_LINEAR_BUCKLING_DURABLE_JOB_REQUEST_V1: &str =
    "structural-model-ir-linear-buckling-durable-job-request.v1";
pub const MODEL_IR_LINEAR_BUCKLING_DURABLE_JOB_PROFILE_V1: &str = "model_ir_linear_buckling_cpu_v1";
pub const MODEL_IR_LINEAR_BUCKLING_MAXIMUM_JOB_REQUEST_BYTES: usize = 72 * 1024 * 1024;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ModelIrLinearBucklingDurableJobWireV1 {
    schema_version: String,
    analysis_profile: String,
    model_ir: Value,
    analysis_request: Value,
}

/// Canonical immutable model plus exact reference-static and spectral controls for one job.
#[derive(Clone, Debug)]
pub struct ModelIrLinearBucklingDurableJobRequestDocumentV1 {
    model_ir: ModelIrV2Document,
    analysis_request: ModelIrLinearBucklingAnalysisRequestDocumentV1,
    canonical_json: String,
    request_hash: String,
}

impl ModelIrLinearBucklingDurableJobRequestDocumentV1 {
    #[must_use]
    pub const fn model_ir(&self) -> &ModelIrV2Document {
        &self.model_ir
    }

    #[must_use]
    pub const fn analysis_request(&self) -> &ModelIrLinearBucklingAnalysisRequestDocumentV1 {
        &self.analysis_request
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

/// Build a canonical durable buckling request from independently supplied documents.
///
/// # Errors
///
/// Returns a stable contract error for size, strict schema, canonicalization or model-identity
/// drift. The request must bind the exact three identities of the supplied model.
pub fn build_model_ir_linear_buckling_durable_job_request_v1(
    model_ir_bytes: &[u8],
    analysis_request_bytes: &[u8],
) -> Result<ModelIrLinearBucklingDurableJobRequestDocumentV1, ProductIrContractError> {
    if model_ir_bytes.is_empty() || model_ir_bytes.len() > MODEL_IR_LINEAR_MAXIMUM_MODEL_BYTES {
        return Err(error(
            "model_ir_linear_buckling_job_model_size_invalid",
            "/model_ir",
            "durable buckling job ModelIR is outside the bounded size",
        ));
    }
    if analysis_request_bytes.is_empty()
        || analysis_request_bytes.len() > MODEL_IR_LINEAR_BUCKLING_MAXIMUM_REQUEST_BYTES
    {
        return Err(error(
            "model_ir_linear_buckling_job_analysis_request_size_invalid",
            "/analysis_request",
            "durable buckling job analysis request is outside the bounded size",
        ));
    }
    let model_ir = parse_model_ir_v2(model_ir_bytes).map_err(model_error)?;
    let analysis_request =
        parse_model_ir_linear_buckling_analysis_request_v1(analysis_request_bytes)?;
    finish(model_ir, analysis_request)
}

/// Strictly parse and re-canonicalize one self-contained durable buckling envelope.
///
/// # Errors
///
/// Returns a stable contract error for duplicate/unknown fields, unsupported profile, invalid
/// nested documents, identity drift, or an oversized canonical envelope.
pub fn parse_model_ir_linear_buckling_durable_job_request_v1(
    bytes: &[u8],
) -> Result<ModelIrLinearBucklingDurableJobRequestDocumentV1, ProductIrContractError> {
    if bytes.is_empty() || bytes.len() > MODEL_IR_LINEAR_BUCKLING_MAXIMUM_JOB_REQUEST_BYTES {
        return Err(error(
            "model_ir_linear_buckling_job_request_size_invalid",
            "/",
            "durable buckling job request envelope is outside the bounded size",
        ));
    }
    let value = decode_json_strict(bytes).map_err(model_error)?;
    let wire: ModelIrLinearBucklingDurableJobWireV1 =
        serde_json::from_value(value).map_err(|_| {
            error(
                "model_ir_linear_buckling_job_request_decode_failed",
                "/",
                "durable buckling job request has unknown, missing, or mistyped fields",
            )
        })?;
    if wire.schema_version != MODEL_IR_LINEAR_BUCKLING_DURABLE_JOB_REQUEST_V1
        || wire.analysis_profile != MODEL_IR_LINEAR_BUCKLING_DURABLE_JOB_PROFILE_V1
    {
        return Err(error(
            "model_ir_linear_buckling_job_request_identity_invalid",
            "/",
            "durable buckling job request schema or analysis profile is unsupported",
        ));
    }
    let model_json = canonicalize_model_ir_v2(&wire.model_ir).map_err(model_error)?;
    if model_json.len() > MODEL_IR_LINEAR_MAXIMUM_MODEL_BYTES {
        return Err(error(
            "model_ir_linear_buckling_job_model_size_invalid",
            "/model_ir",
            "canonical durable buckling job ModelIR exceeds the bounded size",
        ));
    }
    let request_json = canonicalize_model_ir_v2(&wire.analysis_request).map_err(model_error)?;
    if request_json.len() > MODEL_IR_LINEAR_BUCKLING_MAXIMUM_REQUEST_BYTES {
        return Err(error(
            "model_ir_linear_buckling_job_analysis_request_size_invalid",
            "/analysis_request",
            "canonical durable buckling analysis request exceeds the bounded size",
        ));
    }
    let model_ir = parse_model_ir_v2(model_json.as_bytes()).map_err(model_error)?;
    let analysis_request =
        parse_model_ir_linear_buckling_analysis_request_v1(request_json.as_bytes())?;
    finish(model_ir, analysis_request)
}

fn finish(
    model_ir: ModelIrV2Document,
    analysis_request: ModelIrLinearBucklingAnalysisRequestDocumentV1,
) -> Result<ModelIrLinearBucklingDurableJobRequestDocumentV1, ProductIrContractError> {
    let supplied = &analysis_request.request().model_identity;
    if supplied.content_hash != model_ir.content_hash()
        || supplied.semantic_hash != model_ir.semantic_hash()
        || supplied.provenance_hash != model_ir.provenance_hash()
    {
        return Err(error(
            "model_ir_linear_buckling_job_model_identity_mismatch",
            "/analysis_request/model_identity",
            "buckling analysis request identities do not match the durable job ModelIR",
        ));
    }
    let model_value = decode_json_strict(model_ir.canonical_bytes()).map_err(model_error)?;
    let request_value =
        decode_json_strict(analysis_request.canonical_bytes()).map_err(model_error)?;
    let canonical_json = canonicalize_model_ir_v2(&json!({
        "schema_version": MODEL_IR_LINEAR_BUCKLING_DURABLE_JOB_REQUEST_V1,
        "analysis_profile": MODEL_IR_LINEAR_BUCKLING_DURABLE_JOB_PROFILE_V1,
        "model_ir": model_value,
        "analysis_request": request_value,
    }))
    .map_err(model_error)?;
    if canonical_json.len() > MODEL_IR_LINEAR_BUCKLING_MAXIMUM_JOB_REQUEST_BYTES {
        return Err(error(
            "model_ir_linear_buckling_job_request_size_invalid",
            "/",
            "canonical durable buckling job request envelope exceeds the bounded size",
        ));
    }
    Ok(ModelIrLinearBucklingDurableJobRequestDocumentV1 {
        request_hash: sha256_identity(canonical_json.as_bytes()),
        model_ir,
        analysis_request,
        canonical_json,
    })
}

fn model_error(source: ModelIrContractError) -> ProductIrContractError {
    ProductIrContractError {
        code: source.code,
        path: source.path,
        detail: source.detail,
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
    use serde_json::{json, Value};

    use crate::model_buckling_product::{
        build_model_ir_linear_buckling_analysis_request_v1, ModelIrLinearBucklingAnalysisRequestV1,
        ModelIrLinearBucklingBackendV1, MODEL_IR_LINEAR_BUCKLING_ANALYSIS_REQUEST_V1,
    };
    use crate::model_ir::parse_model_ir_v2;
    use crate::product_ir::ModelIrIdentityV1;
    use crate::sparse_product::SparseLinearConfigV1;
    use crate::spectral_product::SpectralGeneralizedEigenConfigV1;

    use super::{
        build_model_ir_linear_buckling_durable_job_request_v1,
        parse_model_ir_linear_buckling_durable_job_request_v1,
    };

    fn inputs() -> (Vec<u8>, Vec<u8>) {
        let source = std::fs::read(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/../../../tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
        ))
        .expect("ModelIR fixture");
        let source = parse_model_ir_v2(&source).expect("source model");
        let mut value = source.value().clone();
        value["load_patterns"][0]["nodal_loads"][0]["components_si"]["FX"] = json!(-100_000.0);
        let model = parse_model_ir_v2(&serde_json::to_vec(&value).expect("model JSON"))
            .expect("compression model");
        let request = build_model_ir_linear_buckling_analysis_request_v1(
            ModelIrLinearBucklingAnalysisRequestV1 {
                schema_version: MODEL_IR_LINEAR_BUCKLING_ANALYSIS_REQUEST_V1.to_owned(),
                operation: "solve_model_ir_linear_buckling".to_owned(),
                case_id: "contract-buckling".to_owned(),
                backend: ModelIrLinearBucklingBackendV1::Cpu,
                model_identity: ModelIrIdentityV1 {
                    content_hash: model.content_hash().to_owned(),
                    semantic_hash: model.semantic_hash().to_owned(),
                    provenance_hash: model.provenance_hash().to_owned(),
                },
                reference_load_pattern_id: "LC_AXIAL".to_owned(),
                reference_linear_config: SparseLinearConfigV1 {
                    max_iterations: 64,
                    absolute_residual_tolerance: 1e-12,
                    relative_residual_tolerance: 1e-12,
                    maximum_increment: 0.0,
                },
                buckling_config: SpectralGeneralizedEigenConfigV1 {
                    mode_count: 2,
                    maximum_sweeps: 4_096,
                    symmetry_relative_tolerance: 1e-12,
                    positive_semidefinite_relative_tolerance: 1e-12,
                    mode_relative_tolerance: 1e-10,
                    cluster_relative_tolerance: 1e-9,
                    residual_relative_tolerance: 1e-9,
                    orthogonality_tolerance: 1e-9,
                    eigensolver_relative_tolerance: 1e-12,
                },
            },
        )
        .expect("buckling request");
        (
            model.canonical_bytes().to_vec(),
            request.canonical_bytes().to_vec(),
        )
    }

    #[test]
    fn built_and_parsed_envelope_is_canonical_and_identity_bound() {
        let (model, request) = inputs();
        let built = build_model_ir_linear_buckling_durable_job_request_v1(&model, &request)
            .expect("built durable request");
        let parsed = parse_model_ir_linear_buckling_durable_job_request_v1(built.canonical_bytes())
            .expect("parsed durable request");
        assert_eq!(parsed.canonical_json(), built.canonical_json());
        assert_eq!(parsed.request_hash(), built.request_hash());
    }

    #[test]
    fn duplicate_unknown_and_identity_drift_fail_closed() {
        let duplicate = br#"{"schema_version":"structural-model-ir-linear-buckling-durable-job-request.v1","schema_version":"structural-model-ir-linear-buckling-durable-job-request.v1"}"#;
        assert!(parse_model_ir_linear_buckling_durable_job_request_v1(duplicate).is_err());
        let (model, request) = inputs();
        let built = build_model_ir_linear_buckling_durable_job_request_v1(&model, &request)
            .expect("built durable request");
        let mut value: Value = serde_json::from_slice(built.canonical_bytes()).expect("JSON");
        value["unknown"] = json!(true);
        assert_eq!(
            parse_model_ir_linear_buckling_durable_job_request_v1(
                &serde_json::to_vec(&value).expect("unknown JSON")
            )
            .expect_err("unknown field")
            .code,
            "model_ir_linear_buckling_job_request_decode_failed"
        );
        value.as_object_mut().expect("object").remove("unknown");
        value["analysis_request"]["model_identity"]["content_hash"] =
            json!(format!("sha256:{}", "0".repeat(64)));
        assert_eq!(
            parse_model_ir_linear_buckling_durable_job_request_v1(
                &serde_json::to_vec(&value).expect("drift JSON")
            )
            .expect_err("identity drift")
            .code,
            "model_ir_linear_buckling_job_model_identity_mismatch"
        );
    }
}
