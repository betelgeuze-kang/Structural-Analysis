use std::fmt;
use std::path::Path;

use serde_json::{json, Value};
use structural_contracts::model_ir::{parse_model_ir_v2, ModelIrContractError};
use structural_contracts::model_modal_product::parse_model_ir_modal_analysis_request_v1;
use structural_contracts::product_ir::{sha256_identity, ProductIrContractError};
use structural_runtime::{PreparedModelIrModalProductV1, Runtime, RuntimeError};

use crate::product::{artifact_entry, canonicalize_value, publish_artifact_directory};
use crate::spectral_product::{
    execute_dense_spectral_analysis, DenseSpectralProductError, DenseSpectralRunOutcomeV1,
};

/// Stable failure boundary for one typed-`ModelIR` modal product execution.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ModelIrModalProductError {
    Contract(ProductIrContractError),
    Runtime(RuntimeError),
    Io { code: u32, message: String },
}

impl ModelIrModalProductError {
    #[must_use]
    pub const fn is_contract_error(&self) -> bool {
        matches!(self, Self::Contract(_))
    }
}

impl fmt::Display for ModelIrModalProductError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Contract(error) => write!(formatter, "{error}"),
            Self::Runtime(error) => write!(formatter, "{error}"),
            Self::Io { code, message } => {
                write!(
                    formatter,
                    "ModelIR modal product I/O error {code}: {message}"
                )
            }
        }
    }
}

impl std::error::Error for ModelIrModalProductError {}

impl From<ProductIrContractError> for ModelIrModalProductError {
    fn from(error: ProductIrContractError) -> Self {
        Self::Contract(error)
    }
}

impl From<RuntimeError> for ModelIrModalProductError {
    fn from(error: RuntimeError) -> Self {
        Self::Runtime(error)
    }
}

impl From<DenseSpectralProductError> for ModelIrModalProductError {
    fn from(error: DenseSpectralProductError) -> Self {
        match error {
            DenseSpectralProductError::Contract(error) => Self::Contract(error),
            DenseSpectralProductError::Runtime(error) => Self::Runtime(error),
            DenseSpectralProductError::Io { code, message } => Self::Io { code, message },
        }
    }
}

impl From<crate::product::NativeAnalysisProductError> for ModelIrModalProductError {
    fn from(error: crate::product::NativeAnalysisProductError) -> Self {
        match error {
            crate::product::NativeAnalysisProductError::Contract(error) => Self::Contract(error),
            crate::product::NativeAnalysisProductError::Runtime(error) => Self::Runtime(error),
            crate::product::NativeAnalysisProductError::Io { code, message } => {
                Self::Io { code, message }
            }
        }
    }
}

/// Complete local artifacts for one bounded typed-`ModelIR` CPU modal execution.
#[derive(Clone, Debug)]
pub struct ModelIrModalAnalysisOutcomeV1 {
    model_ir_json: String,
    analysis_request_json: String,
    assembly_receipt_json: String,
    generated_request_json: String,
    spectral_outcome: DenseSpectralRunOutcomeV1,
    run_receipt_json: String,
}

impl ModelIrModalAnalysisOutcomeV1 {
    #[must_use]
    pub fn result_ir_json(&self) -> &str {
        self.spectral_outcome.result_ir_json()
    }

    #[must_use]
    pub fn report_ir_json(&self) -> &str {
        self.spectral_outcome.report_ir_json()
    }

    #[must_use]
    pub fn report_document(&self) -> &str {
        self.spectral_outcome.report_document()
    }

    #[must_use]
    pub fn run_receipt_json(&self) -> &str {
        &self.run_receipt_json
    }
}

/// Strictly parse, assemble and execute one bounded typed-`ModelIR` modal request.
///
/// # Errors
///
/// Returns a contract error before native execution or a runtime error for assembly, dense
/// adaptation, modal solve, result projection, fallback, or immutable binding drift.
pub fn execute_model_ir_modal_analysis(
    model_ir_bytes: &[u8],
    analysis_request_bytes: &[u8],
) -> Result<ModelIrModalAnalysisOutcomeV1, ModelIrModalProductError> {
    let document =
        parse_model_ir_v2(model_ir_bytes).map_err(|error| model_contract_error(&error))?;
    let request = parse_model_ir_modal_analysis_request_v1(analysis_request_bytes)?;
    let runtime = Runtime::new()?;
    let prepared = runtime.prepare_model_ir_modal_product(&document, &request)?;
    let spectral_outcome =
        execute_dense_spectral_analysis(prepared.generated_request.canonical_bytes(), None)?;
    let run_receipt_json = build_run_receipt(&document, &request, &prepared, &spectral_outcome)?;
    Ok(ModelIrModalAnalysisOutcomeV1 {
        model_ir_json: document.canonical_json().to_owned(),
        analysis_request_json: request.canonical_json().to_owned(),
        assembly_receipt_json: prepared.assembly_receipt_json,
        generated_request_json: prepared.generated_request.canonical_json().to_owned(),
        spectral_outcome,
        run_receipt_json,
    })
}

/// Atomically publish the complete local `ModelIR` modal artifact set into a new directory.
///
/// # Errors
///
/// Returns a stable I/O error without overwriting an existing destination or exposing a partial
/// artifact set.
pub fn publish_model_ir_modal_analysis(
    output_directory: &Path,
    outcome: &ModelIrModalAnalysisOutcomeV1,
) -> Result<(), ModelIrModalProductError> {
    let artifacts = [
        ("model-ir.json", outcome.model_ir_json.as_bytes()),
        (
            "model-modal-request.json",
            outcome.analysis_request_json.as_bytes(),
        ),
        (
            "assembly-receipt.json",
            outcome.assembly_receipt_json.as_bytes(),
        ),
        (
            "generated-dense-request.json",
            outcome.generated_request_json.as_bytes(),
        ),
        (
            "checkpoint.eigcp",
            outcome.spectral_outcome.checkpoint_bytes(),
        ),
        ("result-ir.json", outcome.result_ir_json().as_bytes()),
        ("report-ir.json", outcome.report_ir_json().as_bytes()),
        ("report.md", outcome.report_document().as_bytes()),
        (
            "dense-run-receipt.json",
            outcome.spectral_outcome.run_receipt_json().as_bytes(),
        ),
        ("run-receipt.json", outcome.run_receipt_json.as_bytes()),
    ];
    publish_artifact_directory(output_directory, &artifacts).map_err(Into::into)
}

fn build_run_receipt(
    document: &structural_contracts::model_ir::ModelIrV2Document,
    request: &structural_contracts::model_modal_product::ModelIrModalAnalysisRequestDocumentV1,
    prepared: &PreparedModelIrModalProductV1,
    spectral: &DenseSpectralRunOutcomeV1,
) -> Result<String, ModelIrModalProductError> {
    let artifacts = vec![
        artifact_entry(
            "model_ir",
            "model-ir.json",
            "application/json",
            document.canonical_bytes(),
        )?,
        artifact_entry(
            "model_modal_request",
            "model-modal-request.json",
            "application/json",
            request.canonical_bytes(),
        )?,
        artifact_entry(
            "assembly_receipt",
            "assembly-receipt.json",
            "application/json",
            prepared.assembly_receipt_json.as_bytes(),
        )?,
        artifact_entry(
            "generated_dense_request",
            "generated-dense-request.json",
            "application/json",
            prepared.generated_request.canonical_bytes(),
        )?,
        artifact_entry(
            "dense_checkpoint",
            "checkpoint.eigcp",
            "application/vnd.structural.dense-spectral-checkpoint",
            spectral.checkpoint_bytes(),
        )?,
        artifact_entry(
            "result_ir",
            "result-ir.json",
            "application/json",
            spectral.result_ir_json().as_bytes(),
        )?,
        artifact_entry(
            "report_ir",
            "report-ir.json",
            "application/json",
            spectral.report_ir_json().as_bytes(),
        )?,
        artifact_entry(
            "report_document_source",
            "report.md",
            "text/markdown",
            spectral.report_document().as_bytes(),
        )?,
        artifact_entry(
            "dense_run_receipt",
            "dense-run-receipt.json",
            "application/json",
            spectral.run_receipt_json().as_bytes(),
        )?,
    ];
    let mut receipt = json!({
        "schema_version": "structural-model-ir-modal-run-receipt.v1",
        "case_id": request.request().case_id,
        "status": "completed",
        "model_id": document.model_id(),
        "model_identity": request.request().model_identity,
        "analysis_request_hash": request.request_hash(),
        "assembly_hash": prepared.assembly_hash,
        "generated_dense_request_hash": prepared.generated_request.request_hash(),
        "dense_checkpoint": spectral.checkpoint_receipt(),
        "artifacts": artifacts,
        "fallback_count": 0,
        "claim_boundary": "bounded_local_frame3d_truss3d_modelir_cpu_modal_product_max_128_active_dofs_not_sparse_buckling_shell_nonlinear_durable_service_distribution_hip_or_engineering_acceptance",
        "receipt_hash": ""
    });
    value_self_hash(&mut receipt)?;
    canonicalize_value(
        &receipt,
        "model_ir_modal_run_receipt_canonicalization_failed",
    )
    .map_err(Into::into)
}

fn value_self_hash(value: &mut Value) -> Result<(), ModelIrModalProductError> {
    value
        .as_object_mut()
        .and_then(|object| object.remove("receipt_hash"))
        .ok_or_else(|| {
            contract_error(
                "model_ir_modal_run_receipt_invariant_failed",
                "/",
                "run receipt is not an object",
            )
        })?;
    let unsigned = canonicalize_value(value, "model_ir_modal_run_receipt_canonicalization_failed")?;
    value
        .as_object_mut()
        .expect("run receipt object was checked")
        .insert(
            "receipt_hash".to_owned(),
            Value::String(sha256_identity(unsigned.as_bytes())),
        );
    Ok(())
}

fn model_contract_error(error: &ModelIrContractError) -> ModelIrModalProductError {
    contract_error(&error.code, &error.path, &error.detail)
}

fn contract_error(code: &str, path: &str, detail: &str) -> ModelIrModalProductError {
    ModelIrModalProductError::Contract(ProductIrContractError {
        code: code.to_owned(),
        path: path.to_owned(),
        detail: detail.to_owned(),
    })
}
