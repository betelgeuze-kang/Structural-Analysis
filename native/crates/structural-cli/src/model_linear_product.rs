use std::fmt;
use std::path::Path;

use serde_json::{json, Value};
use structural_contracts::model_ir::{parse_model_ir_v2, ModelIrContractError, ModelIrV2Document};
use structural_contracts::model_linear_product::{
    parse_model_ir_linear_analysis_request_v1, ModelIrLinearAnalysisRequestDocumentV1,
};
use structural_contracts::model_linear_recovery::{
    parse_model_ir_linear_result_recovery_ir_v1, verify_model_ir_linear_result_recovery_v1,
};
use structural_contracts::product_ir::{sha256_identity, ProductIrContractError};
use structural_contracts::sparse_product::SparseLinearAnalysisRequestDocumentV1;
use structural_runtime::{
    ModelIrLinearCheckpointBindingsV1, ModelIrLinearCheckpointReceiptV1, ModelIrLinearCheckpointV1,
    Runtime, RuntimeError,
};

use crate::product::{artifact_entry, canonicalize_value, publish_artifact_directory};
use crate::sparse_product::{
    execute_sparse_linear_analysis, SparseLinearProductError, SparseLinearRunOutcomeV1,
};

/// Stable failure boundary for one typed-`ModelIR` linear product advancement.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ModelIrLinearProductError {
    Contract(ProductIrContractError),
    Runtime(RuntimeError),
    Io { code: u32, message: String },
}

impl ModelIrLinearProductError {
    #[must_use]
    pub const fn is_contract_error(&self) -> bool {
        matches!(self, Self::Contract(_))
    }
}

impl fmt::Display for ModelIrLinearProductError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Contract(error) => write!(formatter, "{error}"),
            Self::Runtime(error) => write!(formatter, "{error}"),
            Self::Io { code, message } => {
                write!(
                    formatter,
                    "ModelIR linear product I/O error {code}: {message}"
                )
            }
        }
    }
}

impl std::error::Error for ModelIrLinearProductError {}

impl From<ProductIrContractError> for ModelIrLinearProductError {
    fn from(error: ProductIrContractError) -> Self {
        Self::Contract(error)
    }
}

impl From<RuntimeError> for ModelIrLinearProductError {
    fn from(error: RuntimeError) -> Self {
        Self::Runtime(error)
    }
}

impl From<SparseLinearProductError> for ModelIrLinearProductError {
    fn from(error: SparseLinearProductError) -> Self {
        match error {
            SparseLinearProductError::Contract(error) => Self::Contract(error),
            SparseLinearProductError::Runtime(error) => Self::Runtime(error),
            SparseLinearProductError::Io { code, message } => Self::Io { code, message },
        }
    }
}

impl From<crate::product::NativeAnalysisProductError> for ModelIrLinearProductError {
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

/// Deterministic artifacts for one active, converged, or numerically failed `ModelIR`/PCG boundary.
#[derive(Clone, Debug)]
pub struct ModelIrLinearAnalysisOutcomeV1 {
    model_ir_json: String,
    analysis_request_json: String,
    assembly_receipt_json: String,
    generated_request_json: String,
    checkpoint: ModelIrLinearCheckpointV1,
    checkpoint_receipt: ModelIrLinearCheckpointReceiptV1,
    checkpoint_receipt_json: String,
    sparse_outcome: SparseLinearRunOutcomeV1,
    result_recovery_json: Option<String>,
    run_receipt_json: String,
}

impl ModelIrLinearAnalysisOutcomeV1 {
    #[must_use]
    pub fn checkpoint_bytes(&self) -> &[u8] {
        self.checkpoint.as_bytes()
    }

    #[must_use]
    pub const fn checkpoint_receipt(&self) -> &ModelIrLinearCheckpointReceiptV1 {
        &self.checkpoint_receipt
    }

    #[must_use]
    pub fn run_receipt_json(&self) -> &str {
        &self.run_receipt_json
    }

    #[must_use]
    pub fn result_ir_json(&self) -> Option<&str> {
        self.sparse_outcome.result_ir_json()
    }

    #[must_use]
    pub fn result_recovery_ir_json(&self) -> Option<&str> {
        self.result_recovery_json.as_deref()
    }

    #[must_use]
    pub fn report_ir_json(&self) -> Option<&str> {
        self.sparse_outcome.report_ir_json()
    }

    #[must_use]
    pub fn report_document(&self) -> Option<&str> {
        self.sparse_outcome.report_document()
    }

    #[must_use]
    pub fn is_terminal_failure(&self) -> bool {
        self.sparse_outcome.is_terminal_failure()
    }

    #[must_use]
    pub fn is_complete(&self) -> bool {
        self.sparse_outcome.is_complete() && self.result_recovery_json.is_some()
    }
}

struct AssemblyReceipt {
    canonical_json: String,
    assembly_hash: String,
}

/// Assemble an exact typed `ModelIR` graph, advance its derived PCG problem, and recover results.
///
/// A resumed call reconstructs the assembly and generated sparse request before accepting the
/// outer checkpoint. No pointer, native handle, or inferred structural value crosses restart.
///
/// # Errors
///
/// Returns a strict contract error before FFI, a native/runtime error for assembly or solve, or a
/// deterministic projection error when any identity/operator/recovery invariant drifts.
pub fn execute_model_ir_linear_analysis(
    model_ir_bytes: &[u8],
    analysis_request_bytes: &[u8],
    checkpoint_bytes: Option<&[u8]>,
    iteration_budget: u32,
) -> Result<ModelIrLinearAnalysisOutcomeV1, ModelIrLinearProductError> {
    let document =
        parse_model_ir_v2(model_ir_bytes).map_err(|error| model_contract_error(&error))?;
    let request = parse_model_ir_linear_analysis_request_v1(analysis_request_bytes)?;
    verify_model_identity(&document, &request)?;

    let runtime = Runtime::new()?;
    let prepared = runtime.prepare_model_ir_linear_product(&document, &request)?;
    let assembly_receipt = AssemblyReceipt {
        canonical_json: prepared.assembly_receipt_json.clone(),
        assembly_hash: prepared.assembly_hash.clone(),
    };
    let generated = &prepared.generated_request;
    let bindings = ModelIrLinearCheckpointBindingsV1 {
        model_content_hash: document.content_hash().to_owned(),
        model_semantic_hash: document.semantic_hash().to_owned(),
        model_provenance_hash: document.provenance_hash().to_owned(),
        analysis_request_hash: request.request_hash().to_owned(),
        assembly_hash: prepared.assembly_hash.clone(),
        generated_request_hash: generated.request_hash().to_owned(),
    };
    let restored = if let Some(bytes) = checkpoint_bytes {
        let envelope = ModelIrLinearCheckpointV1::from_bytes(bytes)?;
        envelope.verify_bindings(&bindings)?;
        Some(envelope)
    } else {
        None
    };
    let sparse_outcome = execute_sparse_linear_analysis(
        generated.canonical_bytes(),
        restored.as_ref().map(|value| value.inner().as_bytes()),
        iteration_budget,
    )?;
    let checkpoint =
        ModelIrLinearCheckpointV1::create(sparse_outcome.checkpoint().clone(), &bindings)?;
    let checkpoint_receipt = checkpoint.receipt();
    let checkpoint_receipt_json = canonicalize_value(
        &serde_json::to_value(&checkpoint_receipt).map_err(|_| {
            contract_error(
                "model_ir_linear_checkpoint_receipt_encode_failed",
                "/checkpoint",
                "checkpoint receipt could not be represented as JSON",
            )
        })?,
        "model_ir_linear_checkpoint_receipt_canonicalization_failed",
    )?;
    let result_recovery_json = sparse_outcome
        .result_ir()
        .map(|result| -> Result<String, ModelIrLinearProductError> {
            let recovery = runtime
                .recover_model_ir_linear_product(&document, &request, &prepared, result)
                .map_err(ModelIrLinearProductError::from)?;
            let parsed = parse_model_ir_linear_result_recovery_ir_v1(recovery.as_bytes())?;
            verify_model_ir_linear_result_recovery_v1(result, &parsed)?;
            let value = parsed.recovery();
            if value.model_identity != request.request().model_identity
                || value.analysis_request_hash != request.request_hash()
                || value.assembly_hash != prepared.assembly_hash
                || value.case_id != request.request().case_id
                || value.load_pattern_id != request.request().load_pattern_id
            {
                return Err(contract_error(
                    "model_ir_linear_recovery_outer_binding_mismatch",
                    "/result_recovery_ir",
                    "typed recovery differs from the exact ModelIR, analysis request, or assembly",
                ));
            }
            Ok(parsed.canonical_json().to_owned())
        })
        .transpose()?;
    let run_receipt_json = build_run_receipt(
        &document,
        &request,
        &assembly_receipt,
        generated,
        &checkpoint,
        &checkpoint_receipt,
        &checkpoint_receipt_json,
        &sparse_outcome,
        result_recovery_json.as_deref(),
    )?;
    Ok(ModelIrLinearAnalysisOutcomeV1 {
        model_ir_json: document.canonical_json().to_owned(),
        analysis_request_json: request.canonical_json().to_owned(),
        assembly_receipt_json: assembly_receipt.canonical_json,
        generated_request_json: prepared.generated_request.canonical_json().to_owned(),
        checkpoint,
        checkpoint_receipt,
        checkpoint_receipt_json,
        sparse_outcome,
        result_recovery_json,
        run_receipt_json,
    })
}

/// Atomically publish the complete `ModelIR`-derived linear artifact set into a new directory.
///
/// # Errors
///
/// Returns a stable I/O error without overwriting an existing path or exposing a partial set.
pub fn publish_model_ir_linear_analysis(
    output_directory: &Path,
    outcome: &ModelIrLinearAnalysisOutcomeV1,
) -> Result<(), ModelIrLinearProductError> {
    let mut artifacts = vec![
        ("model-ir.json", outcome.model_ir_json.as_bytes()),
        (
            "model-analysis-request.json",
            outcome.analysis_request_json.as_bytes(),
        ),
        (
            "assembly-receipt.json",
            outcome.assembly_receipt_json.as_bytes(),
        ),
        (
            "generated-sparse-request.json",
            outcome.generated_request_json.as_bytes(),
        ),
        ("checkpoint.mlpcp", outcome.checkpoint_bytes()),
        (
            "model-checkpoint-receipt.json",
            outcome.checkpoint_receipt_json.as_bytes(),
        ),
        (
            "checkpoint.pcgcp",
            outcome.sparse_outcome.checkpoint_bytes(),
        ),
        (
            "checkpoint-receipt.json",
            outcome.sparse_outcome.checkpoint_receipt_json().as_bytes(),
        ),
        (
            "sparse-run-receipt.json",
            outcome.sparse_outcome.run_receipt_json().as_bytes(),
        ),
        ("run-receipt.json", outcome.run_receipt_json.as_bytes()),
    ];
    if let (Some(result), Some(recovery), Some(report), Some(document)) = (
        outcome.sparse_outcome.result_ir_json(),
        outcome.result_recovery_json.as_deref(),
        outcome.sparse_outcome.report_ir_json(),
        outcome.sparse_outcome.report_document(),
    ) {
        artifacts.push(("result-ir.json", result.as_bytes()));
        artifacts.push(("result-recovery-ir.json", recovery.as_bytes()));
        artifacts.push(("report-ir.json", report.as_bytes()));
        artifacts.push(("report.md", document.as_bytes()));
    }
    publish_artifact_directory(output_directory, &artifacts).map_err(Into::into)
}

fn verify_model_identity(
    document: &ModelIrV2Document,
    request: &ModelIrLinearAnalysisRequestDocumentV1,
) -> Result<(), ModelIrLinearProductError> {
    let supplied = &request.request().model_identity;
    if supplied.content_hash == document.content_hash()
        && supplied.semantic_hash == document.semantic_hash()
        && supplied.provenance_hash == document.provenance_hash()
    {
        Ok(())
    } else {
        Err(contract_error(
            "model_ir_linear_model_identity_mismatch",
            "/model_identity",
            "analysis request identities do not match the exact ModelIR bytes",
        ))
    }
}

#[allow(clippy::too_many_arguments, clippy::too_many_lines)]
fn build_run_receipt(
    document: &ModelIrV2Document,
    request: &ModelIrLinearAnalysisRequestDocumentV1,
    assembly: &AssemblyReceipt,
    generated: &SparseLinearAnalysisRequestDocumentV1,
    checkpoint: &ModelIrLinearCheckpointV1,
    checkpoint_receipt: &ModelIrLinearCheckpointReceiptV1,
    checkpoint_receipt_json: &str,
    sparse: &SparseLinearRunOutcomeV1,
    recovery: Option<&str>,
) -> Result<String, ModelIrLinearProductError> {
    let mut artifacts = vec![
        artifact_entry(
            "model_ir",
            "model-ir.json",
            "application/json",
            document.canonical_bytes(),
        )?,
        artifact_entry(
            "model_analysis_request",
            "model-analysis-request.json",
            "application/json",
            request.canonical_bytes(),
        )?,
        artifact_entry(
            "assembly_receipt",
            "assembly-receipt.json",
            "application/json",
            assembly.canonical_json.as_bytes(),
        )?,
        artifact_entry(
            "generated_sparse_request",
            "generated-sparse-request.json",
            "application/json",
            generated.canonical_bytes(),
        )?,
        artifact_entry(
            "model_checkpoint",
            "checkpoint.mlpcp",
            "application/vnd.structural.model-ir-linear-checkpoint",
            checkpoint.as_bytes(),
        )?,
        artifact_entry(
            "model_checkpoint_receipt",
            "model-checkpoint-receipt.json",
            "application/json",
            checkpoint_receipt_json.as_bytes(),
        )?,
        artifact_entry(
            "sparse_checkpoint",
            "checkpoint.pcgcp",
            "application/vnd.structural.sparse-linear-checkpoint",
            sparse.checkpoint_bytes(),
        )?,
        artifact_entry(
            "sparse_checkpoint_receipt",
            "checkpoint-receipt.json",
            "application/json",
            sparse.checkpoint_receipt_json().as_bytes(),
        )?,
        artifact_entry(
            "sparse_run_receipt",
            "sparse-run-receipt.json",
            "application/json",
            sparse.run_receipt_json().as_bytes(),
        )?,
    ];
    if let (Some(result), Some(recovery), Some(report), Some(document_source)) = (
        sparse.result_ir_json(),
        recovery,
        sparse.report_ir_json(),
        sparse.report_document(),
    ) {
        artifacts.push(artifact_entry(
            "result_ir",
            "result-ir.json",
            "application/json",
            result.as_bytes(),
        )?);
        artifacts.push(artifact_entry(
            "result_recovery_ir",
            "result-recovery-ir.json",
            "application/json",
            recovery.as_bytes(),
        )?);
        artifacts.push(artifact_entry(
            "report_ir",
            "report-ir.json",
            "application/json",
            report.as_bytes(),
        )?);
        artifacts.push(artifact_entry(
            "report_document_source",
            "report.md",
            "text/markdown; charset=utf-8",
            document_source.as_bytes(),
        )?);
    }
    let status = if sparse.is_complete() {
        "completed"
    } else if sparse.is_terminal_failure() {
        "failed"
    } else {
        "active"
    };
    let mut value = json!({
        "schema_version": "structural-model-ir-linear-run-receipt.v1",
        "case_id": request.request().case_id,
        "status": status,
        "solver_status": sparse.checkpoint_receipt().solver_status,
        "model_id": document.model_id(),
        "model_identity": {
            "content_hash": document.content_hash(),
            "semantic_hash": document.semantic_hash(),
            "provenance_hash": document.provenance_hash()
        },
        "analysis_request_hash": request.request_hash(),
        "assembly_hash": assembly.assembly_hash,
        "generated_request_hash": generated.request_hash(),
        "sparse_run_receipt_hash": sha256_identity(sparse.run_receipt_json().as_bytes()),
        "checkpoint": checkpoint_receipt,
        "artifacts": artifacts,
        "claim_boundary": "bounded_typed_modelir_frame3d_truss3d_cpu_assembly_pcg_restart_and_active_dof_recovery_not_sequential_c2_hip_reactions_shell_nonlinear_or_engineering_acceptance",
        "receipt_hash": ""
    });
    value
        .as_object_mut()
        .and_then(|object| object.remove("receipt_hash"))
        .ok_or_else(|| {
            contract_error(
                "model_ir_linear_run_receipt_invariant_failed",
                "/",
                "run receipt is not an object",
            )
        })?;
    let unsigned = canonicalize_value(
        &value,
        "model_ir_linear_run_receipt_canonicalization_failed",
    )?;
    value
        .as_object_mut()
        .expect("run receipt object was checked")
        .insert(
            "receipt_hash".to_owned(),
            Value::String(sha256_identity(unsigned.as_bytes())),
        );
    canonicalize_value(
        &value,
        "model_ir_linear_run_receipt_canonicalization_failed",
    )
    .map_err(Into::into)
}

fn model_contract_error(error: &ModelIrContractError) -> ModelIrLinearProductError {
    contract_error(&error.code, &error.path, &error.detail)
}

fn contract_error(code: &str, path: &str, detail: &str) -> ModelIrLinearProductError {
    ModelIrLinearProductError::Contract(ProductIrContractError {
        code: code.to_owned(),
        path: path.to_owned(),
        detail: detail.to_owned(),
    })
}
