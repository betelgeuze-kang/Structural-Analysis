use std::fmt;
use std::path::Path;

use serde_json::{json, Value};
use structural_contracts::model_buckling_product::{
    parse_model_ir_linear_buckling_analysis_request_v1,
    ModelIrLinearBucklingAnalysisRequestDocumentV1,
};
use structural_contracts::model_ir::{parse_model_ir_v2, ModelIrContractError, ModelIrV2Document};
use structural_contracts::model_linear_reactions::{
    parse_model_ir_linear_reaction_result_ir_v1, verify_model_ir_linear_reaction_result_v1,
};
use structural_contracts::model_linear_recovery::{
    parse_model_ir_linear_result_recovery_ir_v1, verify_model_ir_linear_result_recovery_v1,
    ModelIrLinearResultRecoveryDocumentV1,
};
use structural_contracts::product_ir::{sha256_identity, ProductIrContractError};
use structural_runtime::{
    ModelIrLinearBucklingCheckpointBindingsV1, ModelIrLinearBucklingCheckpointReceiptV1,
    ModelIrLinearBucklingCheckpointV1, ModelIrLinearCheckpointBindingsV1,
    ModelIrLinearCheckpointV1, PreparedModelIrLinearBucklingReferenceV1,
    PreparedModelIrLinearBucklingSpectralV1, Runtime, RuntimeError,
};

use crate::product::{artifact_entry, canonicalize_value, publish_artifact_directory};
use crate::sparse_product::{
    execute_sparse_linear_analysis, SparseLinearProductError, SparseLinearRunOutcomeV1,
};
use crate::spectral_product::{
    execute_dense_spectral_analysis, DenseSpectralProductError, DenseSpectralRunOutcomeV1,
};

/// Stable failure boundary for one typed-`ModelIR` reference-static/buckling product.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ModelIrLinearBucklingProductError {
    Contract(ProductIrContractError),
    Runtime(RuntimeError),
    Io { code: u32, message: String },
}

impl ModelIrLinearBucklingProductError {
    #[must_use]
    pub const fn is_contract_error(&self) -> bool {
        matches!(self, Self::Contract(_))
    }
}

impl fmt::Display for ModelIrLinearBucklingProductError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Contract(error) => write!(formatter, "{error}"),
            Self::Runtime(error) => write!(formatter, "{error}"),
            Self::Io { code, message } => {
                write!(
                    formatter,
                    "ModelIR linear-buckling product I/O error {code}: {message}"
                )
            }
        }
    }
}

impl std::error::Error for ModelIrLinearBucklingProductError {}

impl From<ProductIrContractError> for ModelIrLinearBucklingProductError {
    fn from(error: ProductIrContractError) -> Self {
        Self::Contract(error)
    }
}

impl From<RuntimeError> for ModelIrLinearBucklingProductError {
    fn from(error: RuntimeError) -> Self {
        Self::Runtime(error)
    }
}

impl From<SparseLinearProductError> for ModelIrLinearBucklingProductError {
    fn from(error: SparseLinearProductError) -> Self {
        match error {
            SparseLinearProductError::Contract(error) => Self::Contract(error),
            SparseLinearProductError::Runtime(error) => Self::Runtime(error),
            SparseLinearProductError::Io { code, message } => Self::Io { code, message },
        }
    }
}

impl From<DenseSpectralProductError> for ModelIrLinearBucklingProductError {
    fn from(error: DenseSpectralProductError) -> Self {
        match error {
            DenseSpectralProductError::Contract(error) => Self::Contract(error),
            DenseSpectralProductError::Runtime(error) => Self::Runtime(error),
            DenseSpectralProductError::Io { code, message } => Self::Io { code, message },
        }
    }
}

impl From<crate::product::NativeAnalysisProductError> for ModelIrLinearBucklingProductError {
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

/// Complete local artifacts for one bounded typed-`ModelIR` CPU linear-buckling execution.
#[derive(Clone, Debug)]
pub struct ModelIrLinearBucklingAnalysisOutcomeV1 {
    model_ir_json: String,
    analysis_request_json: String,
    generated_reference_request_json: String,
    reference_assembly_receipt_json: String,
    reference_checkpoint: ModelIrLinearCheckpointV1,
    reference_sparse_outcome: SparseLinearRunOutcomeV1,
    reference_result_ir_json: String,
    reference_recovery_ir_json: String,
    reference_reaction_ir_json: String,
    buckling_assembly_receipt_json: String,
    generated_spectral_request_json: String,
    checkpoint: ModelIrLinearBucklingCheckpointV1,
    checkpoint_receipt: ModelIrLinearBucklingCheckpointReceiptV1,
    spectral_outcome: DenseSpectralRunOutcomeV1,
    run_receipt_json: String,
}

/// Identity and numerical summary from one non-publishing full compatibility preflight.
#[derive(Clone, Debug, PartialEq)]
pub struct ModelIrLinearBucklingCompatibilityV1 {
    pub generated_reference_request_hash: String,
    pub reference_assembly_hash: String,
    pub buckling_assembly_hash: String,
    pub generated_dense_request_hash: String,
    pub active_dof_count: u32,
    pub critical_load_factor: f64,
}

impl ModelIrLinearBucklingAnalysisOutcomeV1 {
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

    #[must_use]
    pub fn checkpoint_bytes(&self) -> &[u8] {
        self.checkpoint.as_bytes()
    }

    #[must_use]
    pub const fn checkpoint_receipt(&self) -> &ModelIrLinearBucklingCheckpointReceiptV1 {
        &self.checkpoint_receipt
    }
}

/// Execute the exact non-publishing reference and buckling preflight used by Workbench authoring.
///
/// # Errors
///
/// Returns the same strict contract/runtime errors as product execution. No artifact directory is
/// created, but the reference-static solve and buckling eigensolve do execute.
pub fn validate_model_ir_linear_buckling_analysis_compatibility(
    model_ir_bytes: &[u8],
    analysis_request_bytes: &[u8],
) -> Result<ModelIrLinearBucklingCompatibilityV1, ModelIrLinearBucklingProductError> {
    let outcome =
        execute_model_ir_linear_buckling_analysis(model_ir_bytes, analysis_request_bytes)?;
    let reference_request =
        structural_contracts::model_linear_product::parse_model_ir_linear_analysis_request_v1(
            outcome.generated_reference_request_json.as_bytes(),
        )?;
    let generated = structural_contracts::spectral_product::parse_dense_spectral_request_v1(
        outcome.generated_spectral_request_json.as_bytes(),
    )?;
    let result = structural_contracts::spectral_product::parse_dense_spectral_result_ir_v1(
        outcome.result_ir_json().as_bytes(),
    )?;
    let reference_assembly: Value = serde_json::from_str(&outcome.reference_assembly_receipt_json)
        .map_err(|_| {
            contract_error(
                "model_ir_linear_buckling_preflight_receipt_invalid",
                "/reference_assembly_receipt",
                "generated reference assembly receipt is invalid",
            )
        })?;
    let buckling_assembly: Value = serde_json::from_str(&outcome.buckling_assembly_receipt_json)
        .map_err(|_| {
            contract_error(
                "model_ir_linear_buckling_preflight_receipt_invalid",
                "/buckling_assembly_receipt",
                "generated buckling assembly receipt is invalid",
            )
        })?;
    let reference_assembly_hash = reference_assembly
        .get("assembly_hash")
        .and_then(Value::as_str)
        .ok_or_else(|| {
            contract_error(
                "model_ir_linear_buckling_preflight_receipt_invalid",
                "/reference_assembly_receipt/assembly_hash",
                "generated reference assembly hash is absent",
            )
        })?;
    let buckling_assembly_hash = buckling_assembly
        .get("assembly_hash")
        .and_then(Value::as_str)
        .ok_or_else(|| {
            contract_error(
                "model_ir_linear_buckling_preflight_receipt_invalid",
                "/buckling_assembly_receipt/assembly_hash",
                "generated buckling assembly hash is absent",
            )
        })?;
    let critical_load_factor = result
        .result()
        .summary
        .critical_load_factor
        .filter(|value| value.is_finite() && *value > 0.0)
        .ok_or_else(|| {
            contract_error(
                "model_ir_linear_buckling_preflight_result_invalid",
                "/result_ir/summary/critical_load_factor",
                "buckling preflight did not produce a finite positive critical factor",
            )
        })?;
    Ok(ModelIrLinearBucklingCompatibilityV1 {
        generated_reference_request_hash: reference_request.request_hash().to_owned(),
        reference_assembly_hash: reference_assembly_hash.to_owned(),
        buckling_assembly_hash: buckling_assembly_hash.to_owned(),
        generated_dense_request_hash: generated.request_hash().to_owned(),
        active_dof_count: generated.request().order,
        critical_load_factor,
    })
}

/// Strictly parse, solve the exact reference equilibrium, assemble K/Kg, and execute buckling.
///
/// # Errors
///
/// Returns a contract/runtime error before publication for any model, request, reference solve,
/// recovery/reaction, prestress assembly, eigensolve, checkpoint, or immutable binding drift.
pub fn execute_model_ir_linear_buckling_analysis(
    model_ir_bytes: &[u8],
    analysis_request_bytes: &[u8],
) -> Result<ModelIrLinearBucklingAnalysisOutcomeV1, ModelIrLinearBucklingProductError> {
    execute_model_ir_linear_buckling_analysis_with_checkpoint(
        model_ir_bytes,
        analysis_request_bytes,
        None,
    )
}

/// Reconstruct and resume both exact reference-static and spectral phase boundaries.
///
/// # Errors
///
/// Returns before publication unless all outer, generated, numerical and checkpoint bindings are
/// valid and both phases complete without fallback.
#[allow(clippy::too_many_lines)]
pub fn execute_model_ir_linear_buckling_analysis_with_checkpoint(
    model_ir_bytes: &[u8],
    analysis_request_bytes: &[u8],
    checkpoint_bytes: Option<&[u8]>,
) -> Result<ModelIrLinearBucklingAnalysisOutcomeV1, ModelIrLinearBucklingProductError> {
    let document =
        parse_model_ir_v2(model_ir_bytes).map_err(|error| model_contract_error(&error))?;
    let request = parse_model_ir_linear_buckling_analysis_request_v1(analysis_request_bytes)?;
    let runtime = Runtime::new()?;
    let reference = runtime.prepare_model_ir_linear_buckling_reference(&document, &request)?;
    let restored = checkpoint_bytes
        .map(ModelIrLinearBucklingCheckpointV1::from_bytes)
        .transpose()?;
    let reference_bindings = reference_checkpoint_bindings(&document, &reference);
    if let Some(checkpoint) = &restored {
        checkpoint
            .reference()
            .verify_bindings(&reference_bindings)?;
    }
    let reference_sparse_outcome = execute_sparse_linear_analysis(
        reference.product.generated_request.canonical_bytes(),
        restored
            .as_ref()
            .map(|checkpoint| checkpoint.reference().inner().as_bytes()),
        request.request().reference_linear_config.max_iterations,
    )?;
    if !reference_sparse_outcome.is_complete() || reference_sparse_outcome.is_terminal_failure() {
        return Err(product_error(
            "ModelIR buckling reference-static solve did not converge to a terminal ResultIR",
        ));
    }
    let reference_checkpoint = ModelIrLinearCheckpointV1::create(
        reference_sparse_outcome.checkpoint().clone(),
        &reference_bindings,
    )?;
    let reference_result = reference_sparse_outcome.result_ir().ok_or_else(|| {
        product_error("ModelIR buckling reference-static ResultIR is unavailable")
    })?;
    let recovered = runtime.recover_model_ir_linear_product_artifacts(
        &document,
        &reference.request,
        &reference.product,
        reference_result,
    )?;
    let reference_recovery =
        parse_model_ir_linear_result_recovery_ir_v1(recovered.result_recovery_json.as_bytes())?;
    verify_model_ir_linear_result_recovery_v1(reference_result, &reference_recovery)?;
    let reference_reaction =
        parse_model_ir_linear_reaction_result_ir_v1(recovered.reaction_result_json.as_bytes())?;
    verify_model_ir_linear_reaction_result_v1(
        reference_result,
        &reference_recovery,
        &reference_reaction,
    )?;
    verify_reference_binding(&document, &request, &reference, &reference_recovery)?;
    let spectral = runtime.prepare_model_ir_linear_buckling_spectral(
        &document,
        &request,
        &reference,
        &reference_recovery.recovery().global_displacement,
        reference_result.result_hash(),
        reference_recovery.recovery_hash(),
    )?;
    let bindings = buckling_checkpoint_bindings(
        &document,
        &request,
        &reference,
        &spectral,
        reference_result.result_hash(),
        reference_recovery.recovery_hash(),
    );
    if let Some(checkpoint) = &restored {
        checkpoint.verify_bindings(&bindings)?;
    }
    let spectral_outcome = execute_dense_spectral_analysis(
        spectral.generated_request.canonical_bytes(),
        restored
            .as_ref()
            .map(|checkpoint| checkpoint.spectral().as_bytes()),
    )?;
    let checkpoint = ModelIrLinearBucklingCheckpointV1::create(
        reference_checkpoint.clone(),
        spectral_outcome.checkpoint().clone(),
        &bindings,
    )?;
    let checkpoint_receipt = checkpoint.receipt();
    let run_receipt_json = build_run_receipt(
        &document,
        &request,
        &reference,
        &reference_checkpoint,
        &reference_sparse_outcome,
        &reference_recovery,
        reference_reaction.canonical_json(),
        &spectral,
        &checkpoint,
        &checkpoint_receipt,
        &spectral_outcome,
    )?;
    Ok(ModelIrLinearBucklingAnalysisOutcomeV1 {
        model_ir_json: document.canonical_json().to_owned(),
        analysis_request_json: request.canonical_json().to_owned(),
        generated_reference_request_json: reference.request.canonical_json().to_owned(),
        reference_assembly_receipt_json: reference.product.assembly_receipt_json,
        reference_checkpoint,
        reference_result_ir_json: reference_result.canonical_json().to_owned(),
        reference_recovery_ir_json: reference_recovery.canonical_json().to_owned(),
        reference_reaction_ir_json: reference_reaction.canonical_json().to_owned(),
        reference_sparse_outcome,
        buckling_assembly_receipt_json: spectral.assembly_receipt_json,
        generated_spectral_request_json: spectral.generated_request.canonical_json().to_owned(),
        checkpoint,
        checkpoint_receipt,
        spectral_outcome,
        run_receipt_json,
    })
}

/// Atomically publish the complete local reference-static plus buckling artifact inventory.
///
/// # Errors
///
/// Returns a stable I/O error without overwriting an existing destination or exposing a partial
/// artifact set.
pub fn publish_model_ir_linear_buckling_analysis(
    output_directory: &Path,
    outcome: &ModelIrLinearBucklingAnalysisOutcomeV1,
) -> Result<(), ModelIrLinearBucklingProductError> {
    let artifacts = [
        ("model-ir.json", outcome.model_ir_json.as_bytes()),
        (
            "model-buckling-request.json",
            outcome.analysis_request_json.as_bytes(),
        ),
        (
            "generated-reference-request.json",
            outcome.generated_reference_request_json.as_bytes(),
        ),
        (
            "reference-assembly-receipt.json",
            outcome.reference_assembly_receipt_json.as_bytes(),
        ),
        (
            "reference-checkpoint.pcgcp",
            outcome.reference_sparse_outcome.checkpoint_bytes(),
        ),
        (
            "reference-checkpoint.mlpcp",
            outcome.reference_checkpoint.as_bytes(),
        ),
        (
            "reference-result-ir.json",
            outcome.reference_result_ir_json.as_bytes(),
        ),
        (
            "reference-recovery-ir.json",
            outcome.reference_recovery_ir_json.as_bytes(),
        ),
        (
            "reference-reaction-ir.json",
            outcome.reference_reaction_ir_json.as_bytes(),
        ),
        (
            "buckling-assembly-receipt.json",
            outcome.buckling_assembly_receipt_json.as_bytes(),
        ),
        (
            "generated-dense-request.json",
            outcome.generated_spectral_request_json.as_bytes(),
        ),
        (
            "checkpoint.eigcp",
            outcome.spectral_outcome.checkpoint_bytes(),
        ),
        ("checkpoint.mbcp", outcome.checkpoint_bytes()),
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

fn reference_checkpoint_bindings(
    document: &ModelIrV2Document,
    reference: &PreparedModelIrLinearBucklingReferenceV1,
) -> ModelIrLinearCheckpointBindingsV1 {
    ModelIrLinearCheckpointBindingsV1 {
        model_content_hash: document.content_hash().to_owned(),
        model_semantic_hash: document.semantic_hash().to_owned(),
        model_provenance_hash: document.provenance_hash().to_owned(),
        analysis_request_hash: reference.request.request_hash().to_owned(),
        assembly_hash: reference.product.assembly_hash.clone(),
        generated_request_hash: reference
            .product
            .generated_request
            .request_hash()
            .to_owned(),
    }
}

fn buckling_checkpoint_bindings(
    document: &ModelIrV2Document,
    request: &ModelIrLinearBucklingAnalysisRequestDocumentV1,
    reference: &PreparedModelIrLinearBucklingReferenceV1,
    spectral: &PreparedModelIrLinearBucklingSpectralV1,
    reference_result_hash: &str,
    reference_recovery_hash: &str,
) -> ModelIrLinearBucklingCheckpointBindingsV1 {
    ModelIrLinearBucklingCheckpointBindingsV1 {
        model_content_hash: document.content_hash().to_owned(),
        model_semantic_hash: document.semantic_hash().to_owned(),
        model_provenance_hash: document.provenance_hash().to_owned(),
        analysis_request_hash: request.request_hash().to_owned(),
        generated_reference_request_hash: reference.request.request_hash().to_owned(),
        reference_assembly_hash: reference.product.assembly_hash.clone(),
        buckling_assembly_hash: spectral.assembly_hash.clone(),
        generated_spectral_request_hash: spectral.generated_request.request_hash().to_owned(),
        reference_result_hash: reference_result_hash.to_owned(),
        reference_recovery_hash: reference_recovery_hash.to_owned(),
    }
}

fn verify_reference_binding(
    document: &ModelIrV2Document,
    request: &ModelIrLinearBucklingAnalysisRequestDocumentV1,
    reference: &PreparedModelIrLinearBucklingReferenceV1,
    recovery: &ModelIrLinearResultRecoveryDocumentV1,
) -> Result<(), ModelIrLinearBucklingProductError> {
    let value = recovery.recovery();
    if value.model_identity == request.request().model_identity
        && value.model_id == document.model_id()
        && value.case_id == request.request().case_id
        && value.load_pattern_id == request.request().reference_load_pattern_id
        && value.analysis_request_hash == reference.request.request_hash()
        && value.assembly_hash == reference.product.assembly_hash
        && value.fallback_count == 0
    {
        Ok(())
    } else {
        Err(contract_error(
            "model_ir_linear_buckling_reference_binding_mismatch",
            "/reference_recovery_ir",
            "reference recovery differs from the exact model, outer request, or generated linear request",
        ))
    }
}

#[allow(clippy::too_many_arguments, clippy::too_many_lines)]
fn build_run_receipt(
    document: &ModelIrV2Document,
    request: &ModelIrLinearBucklingAnalysisRequestDocumentV1,
    reference: &PreparedModelIrLinearBucklingReferenceV1,
    reference_checkpoint: &ModelIrLinearCheckpointV1,
    reference_sparse: &SparseLinearRunOutcomeV1,
    reference_recovery: &ModelIrLinearResultRecoveryDocumentV1,
    reference_reaction_json: &str,
    spectral: &PreparedModelIrLinearBucklingSpectralV1,
    checkpoint: &ModelIrLinearBucklingCheckpointV1,
    checkpoint_receipt: &ModelIrLinearBucklingCheckpointReceiptV1,
    spectral_outcome: &DenseSpectralRunOutcomeV1,
) -> Result<String, ModelIrLinearBucklingProductError> {
    let reference_result = reference_sparse.result_ir_json().ok_or_else(|| {
        product_error("ModelIR buckling reference ResultIR disappeared before receipt")
    })?;
    let artifacts = vec![
        artifact_entry(
            "model_ir",
            "model-ir.json",
            "application/json",
            document.canonical_bytes(),
        )?,
        artifact_entry(
            "model_buckling_request",
            "model-buckling-request.json",
            "application/json",
            request.canonical_bytes(),
        )?,
        artifact_entry(
            "generated_reference_request",
            "generated-reference-request.json",
            "application/json",
            reference.request.canonical_bytes(),
        )?,
        artifact_entry(
            "reference_assembly_receipt",
            "reference-assembly-receipt.json",
            "application/json",
            reference.product.assembly_receipt_json.as_bytes(),
        )?,
        artifact_entry(
            "reference_sparse_checkpoint",
            "reference-checkpoint.pcgcp",
            "application/vnd.structural.sparse-linear-checkpoint",
            reference_sparse.checkpoint_bytes(),
        )?,
        artifact_entry(
            "reference_model_checkpoint",
            "reference-checkpoint.mlpcp",
            "application/vnd.structural.model-ir-linear-checkpoint",
            reference_checkpoint.as_bytes(),
        )?,
        artifact_entry(
            "reference_result_ir",
            "reference-result-ir.json",
            "application/json",
            reference_result.as_bytes(),
        )?,
        artifact_entry(
            "reference_recovery_ir",
            "reference-recovery-ir.json",
            "application/json",
            reference_recovery.canonical_bytes(),
        )?,
        artifact_entry(
            "reference_reaction_ir",
            "reference-reaction-ir.json",
            "application/json",
            reference_reaction_json.as_bytes(),
        )?,
        artifact_entry(
            "buckling_assembly_receipt",
            "buckling-assembly-receipt.json",
            "application/json",
            spectral.assembly_receipt_json.as_bytes(),
        )?,
        artifact_entry(
            "generated_dense_request",
            "generated-dense-request.json",
            "application/json",
            spectral.generated_request.canonical_bytes(),
        )?,
        artifact_entry(
            "dense_checkpoint",
            "checkpoint.eigcp",
            "application/vnd.structural.dense-spectral-checkpoint",
            spectral_outcome.checkpoint_bytes(),
        )?,
        artifact_entry(
            "model_ir_buckling_checkpoint",
            "checkpoint.mbcp",
            "application/vnd.structural.model-ir-linear-buckling-checkpoint",
            checkpoint.as_bytes(),
        )?,
        artifact_entry(
            "result_ir",
            "result-ir.json",
            "application/json",
            spectral_outcome.result_ir_json().as_bytes(),
        )?,
        artifact_entry(
            "report_ir",
            "report-ir.json",
            "application/json",
            spectral_outcome.report_ir_json().as_bytes(),
        )?,
        artifact_entry(
            "report_document_source",
            "report.md",
            "text/markdown",
            spectral_outcome.report_document().as_bytes(),
        )?,
        artifact_entry(
            "dense_run_receipt",
            "dense-run-receipt.json",
            "application/json",
            spectral_outcome.run_receipt_json().as_bytes(),
        )?,
    ];
    let mut receipt = json!({
        "schema_version": "structural-model-ir-linear-buckling-run-receipt.v1",
        "case_id": request.request().case_id,
        "status": "completed",
        "model_id": document.model_id(),
        "model_identity": request.request().model_identity,
        "analysis_request_hash": request.request_hash(),
        "generated_reference_request_hash": reference.request.request_hash(),
        "reference_linear_assembly_hash": reference.product.assembly_hash,
        "reference_result_hash": reference_sparse
            .result_ir()
            .map(structural_contracts::sparse_product::SparseLinearResultIrDocumentV1::result_hash),
        "reference_recovery_hash": reference_recovery.recovery_hash(),
        "buckling_assembly_hash": spectral.assembly_hash,
        "generated_dense_request_hash": spectral.generated_request.request_hash(),
        "model_ir_linear_buckling_checkpoint": checkpoint_receipt,
        "reference_checkpoint": reference_checkpoint.receipt(),
        "dense_checkpoint": spectral_outcome.checkpoint_receipt(),
        "artifacts": artifacts,
        "fallback_count": 0,
        "claim_boundary": "bounded_local_frame3d_nodal_reference_load_modelir_cpu_linear_buckling_product_exact_pcg_equilibrium_v1_15_k_kg_model_bound_dual_phase_restart_max_128_active_dofs_not_mixed_tension_member_load_self_weight_nonzero_prescribed_support_shell_sparse_nonlinear_durable_service_public_customer_distribution_publication_hip_external_validation_or_engineering_acceptance",
        "receipt_hash": ""
    });
    value_self_hash(&mut receipt)?;
    canonicalize_value(
        &receipt,
        "model_ir_linear_buckling_run_receipt_canonicalization_failed",
    )
    .map_err(Into::into)
}

fn value_self_hash(value: &mut Value) -> Result<(), ModelIrLinearBucklingProductError> {
    value
        .as_object_mut()
        .and_then(|object| object.remove("receipt_hash"))
        .ok_or_else(|| {
            contract_error(
                "model_ir_linear_buckling_run_receipt_invariant_failed",
                "/",
                "run receipt is not an object",
            )
        })?;
    let unsigned = canonicalize_value(
        value,
        "model_ir_linear_buckling_run_receipt_canonicalization_failed",
    )?;
    value
        .as_object_mut()
        .expect("run receipt object was checked")
        .insert(
            "receipt_hash".to_owned(),
            Value::String(sha256_identity(unsigned.as_bytes())),
        );
    Ok(())
}

fn product_error(message: &str) -> ModelIrLinearBucklingProductError {
    ModelIrLinearBucklingProductError::Runtime(RuntimeError {
        code: 1100,
        message: message.to_owned(),
    })
}

fn model_contract_error(error: &ModelIrContractError) -> ModelIrLinearBucklingProductError {
    contract_error(&error.code, &error.path, &error.detail)
}

fn contract_error(code: &str, path: &str, detail: &str) -> ModelIrLinearBucklingProductError {
    ModelIrLinearBucklingProductError::Contract(ProductIrContractError {
        code: code.to_owned(),
        path: path.to_owned(),
        detail: detail.to_owned(),
    })
}
