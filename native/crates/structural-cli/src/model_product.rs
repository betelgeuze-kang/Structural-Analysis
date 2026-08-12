use std::path::Path;

use serde_json::{json, Value};
use structural_contracts::model_ir::{parse_model_ir_v2, ModelIrContractError};
use structural_contracts::product_ir::{
    build_native_analysis_request_v1, parse_model_ir_ndtha_analysis_request_v1, sha256_identity,
    ModelIrNdthaAdapterProfileV1, NativeAnalysisRequestV1, ProductIrContractError,
    NATIVE_ANALYSIS_REQUEST_V1,
};
use structural_runtime::{
    ModelIrNdthaAdapterRequest, ModelIrNdthaCheckpointBindingsV1, ModelIrNdthaCheckpointV1, Runtime,
};

use crate::product::{
    artifact_entry, canonicalize_value, execute_native_analysis, publish_artifact_directory,
    NativeAnalysisProductError, NativeAnalysisRunOutcomeV1,
};

/// Product artifacts from one ModelIR-derived bounded NDTHA advancement.
#[derive(Clone, Debug)]
pub struct ModelIrNativeAnalysisOutcomeV1 {
    model_ir_json: String,
    adapter_request_json: String,
    generated_request_json: String,
    checkpoint: ModelIrNdthaCheckpointV1,
    native_outcome: NativeAnalysisRunOutcomeV1,
    run_receipt_json: String,
}

impl ModelIrNativeAnalysisOutcomeV1 {
    #[must_use]
    pub fn is_terminal(&self) -> bool {
        self.native_outcome.is_terminal()
    }

    #[must_use]
    pub fn run_receipt_json(&self) -> &str {
        &self.run_receipt_json
    }
}

/// Parse `ModelIR` and its explicit analysis request, derive the native problem and advance it.
///
/// A resumed call first verifies the outer checkpoint's exact `ModelIR` three-hash identity,
/// adapter-request hash and generated native-request hash. Structurally different inputs cannot
/// reuse a checkpoint merely because they happen to reduce to equal scalar properties.
///
/// # Errors
///
/// Returns a contract error before FFI for invalid wire or identity mismatch, a checkpoint error
/// for corrupt/mismatched resume state, or a native error for model readiness and execution.
pub fn execute_model_ir_native_analysis(
    model_ir_bytes: &[u8],
    adapter_request_bytes: &[u8],
    checkpoint_bytes: Option<&[u8]>,
    step_budget: u32,
) -> Result<ModelIrNativeAnalysisOutcomeV1, NativeAnalysisProductError> {
    let document =
        parse_model_ir_v2(model_ir_bytes).map_err(|error| model_contract_error(&error))?;
    let adapter_request = parse_model_ir_ndtha_analysis_request_v1(adapter_request_bytes)?;
    let requested = adapter_request.request();
    let identity_matches = requested.model_identity.content_hash == document.content_hash()
        && requested.model_identity.semantic_hash == document.semantic_hash()
        && requested.model_identity.provenance_hash == document.provenance_hash();
    if !identity_matches {
        return Err(contract_error(
            "model_ir_ndtha_model_identity_mismatch",
            "/model_identity",
            "adapter request identities do not match the exact ModelIR bytes",
        ));
    }
    if requested.profile != ModelIrNdthaAdapterProfileV1::FixedGuidedFrame3dX {
        return Err(contract_error(
            "model_ir_ndtha_profile_unsupported",
            "/profile",
            "adapter request profile is unsupported",
        ));
    }

    let runtime = Runtime::new()?;
    let adapted = runtime.adapt_model_ir_ndtha(
        &document,
        &ModelIrNdthaAdapterRequest {
            element_id: requested.element_id.clone(),
            base_node_id: requested.base_node_id.clone(),
            floor_node_id: requested.floor_node_id.clone(),
            load_pattern_id: requested.load_pattern_id.clone(),
            damping_ratio: requested.damping_ratio,
            elastic_guard_yield_drift_m: requested.elastic_guard_yield_drift_m,
            config: requested.config.clone(),
            acceleration_g: requested.acceleration_g.clone(),
        },
    )?;
    let generated = build_native_analysis_request_v1(NativeAnalysisRequestV1 {
        schema_version: NATIVE_ANALYSIS_REQUEST_V1.to_owned(),
        operation: "nonlinear_ndtha".to_owned(),
        case_id: requested.case_id.clone(),
        backend: requested.backend,
        config: adapted.config,
        inputs: adapted.inputs,
    })?;
    let bindings = ModelIrNdthaCheckpointBindingsV1 {
        model_content_hash: document.content_hash().to_owned(),
        model_semantic_hash: document.semantic_hash().to_owned(),
        model_provenance_hash: document.provenance_hash().to_owned(),
        adapter_request_hash: adapter_request.request_hash().to_owned(),
        generated_request_hash: generated.request_hash().to_owned(),
    };
    let restored_envelope = if let Some(bytes) = checkpoint_bytes {
        let envelope = ModelIrNdthaCheckpointV1::from_bytes(bytes)?;
        envelope.verify_bindings(&bindings)?;
        Some(envelope)
    } else {
        None
    };
    let restored = restored_envelope
        .as_ref()
        .map(|envelope| envelope.inner().as_bytes());
    let native_outcome =
        execute_native_analysis(generated.canonical_bytes(), restored, step_budget)?;
    let checkpoint =
        ModelIrNdthaCheckpointV1::create(native_outcome.checkpoint().clone(), &bindings)?;
    let run_receipt_json = build_model_run_receipt(
        &document,
        &adapter_request,
        &generated,
        &adapted.receipt,
        &checkpoint,
        &native_outcome,
    )?;
    Ok(ModelIrNativeAnalysisOutcomeV1 {
        model_ir_json: document.canonical_json().to_owned(),
        adapter_request_json: adapter_request.canonical_json().to_owned(),
        generated_request_json: generated.canonical_json().to_owned(),
        checkpoint,
        native_outcome,
        run_receipt_json,
    })
}

/// Atomically publish the complete ModelIR-derived product advancement into a new directory.
///
/// # Errors
///
/// Returns a stable I/O error without overwriting an existing path or exposing a partial set.
pub fn publish_model_ir_native_analysis(
    output_directory: &Path,
    outcome: &ModelIrNativeAnalysisOutcomeV1,
) -> Result<(), NativeAnalysisProductError> {
    let mut artifacts = vec![
        ("model-ir.json", outcome.model_ir_json.as_bytes()),
        (
            "model-analysis-request.json",
            outcome.adapter_request_json.as_bytes(),
        ),
        (
            "generated-request.json",
            outcome.generated_request_json.as_bytes(),
        ),
        ("checkpoint.ndcp", outcome.checkpoint.as_bytes()),
        (
            "native-run-receipt.json",
            outcome.native_outcome.run_receipt_json().as_bytes(),
        ),
    ];
    if let (Some(result), Some(report), Some(document)) = (
        outcome.native_outcome.result_ir_json(),
        outcome.native_outcome.report_ir_json(),
        outcome.native_outcome.report_document(),
    ) {
        artifacts.push(("result-ir.json", result.as_bytes()));
        artifacts.push(("report-ir.json", report.as_bytes()));
        artifacts.push(("report.md", document.as_bytes()));
    }
    artifacts.push(("run-receipt.json", outcome.run_receipt_json.as_bytes()));
    publish_artifact_directory(output_directory, &artifacts)
}

// The receipt enumerates each artifact and identity in wire order for an auditable self-hash.
#[allow(clippy::too_many_lines)]
fn build_model_run_receipt(
    document: &structural_contracts::model_ir::ModelIrV2Document,
    adapter_request: &structural_contracts::product_ir::ModelIrNdthaAnalysisRequestDocumentV1,
    generated: &structural_contracts::product_ir::NativeAnalysisRequestDocumentV1,
    derivation: &structural_runtime::ModelIrNdthaAdapterReceipt,
    checkpoint: &ModelIrNdthaCheckpointV1,
    native: &NativeAnalysisRunOutcomeV1,
) -> Result<String, NativeAnalysisProductError> {
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
            adapter_request.canonical_bytes(),
        )?,
        artifact_entry(
            "generated_native_request",
            "generated-request.json",
            "application/json",
            generated.canonical_bytes(),
        )?,
        artifact_entry(
            "checkpoint",
            "checkpoint.ndcp",
            "application/vnd.structural.model-ir-ndtha-checkpoint",
            checkpoint.as_bytes(),
        )?,
        artifact_entry(
            "native_run_receipt",
            "native-run-receipt.json",
            "application/json",
            native.run_receipt_json().as_bytes(),
        )?,
    ];
    if let (Some(result), Some(report), Some(document_source)) = (
        native.result_ir_json(),
        native.report_ir_json(),
        native.report_document(),
    ) {
        artifacts.push(artifact_entry(
            "result_ir",
            "result-ir.json",
            "application/json",
            result.as_bytes(),
        )?);
        artifacts.push(artifact_entry(
            "report_ir",
            "report-ir.json",
            "application/json",
            report.as_bytes(),
        )?);
        artifacts.push(artifact_entry(
            "report_document",
            "report.md",
            "text/markdown; charset=utf-8",
            document_source.as_bytes(),
        )?);
    }
    let native_receipt: Value = serde_json::from_str(native.run_receipt_json()).map_err(|_| {
        contract_error(
            "model_ir_ndtha_native_receipt_invalid",
            "/native_run_receipt",
            "native run receipt is not valid JSON",
        )
    })?;
    let status = native_receipt["status"].as_str().ok_or_else(|| {
        contract_error(
            "model_ir_ndtha_native_receipt_invalid",
            "/native_run_receipt/status",
            "native run receipt has no status",
        )
    })?;
    if !matches!(status, "checkpointed" | "completed" | "collapsed")
        || (native.is_terminal() && status == "checkpointed")
        || (!native.is_terminal() && status != "checkpointed")
    {
        return Err(contract_error(
            "model_ir_ndtha_native_receipt_invalid",
            "/native_run_receipt/status",
            "native run receipt status is inconsistent with artifacts",
        ));
    }
    let mut receipt = json!({
        "schema_version": "structural-model-ir-ndtha-run-receipt.v1",
        "case_id": adapter_request.request().case_id,
        "status": status,
        "model_id": document.model_id(),
        "model_identity": {
            "content_hash": document.content_hash(),
            "semantic_hash": document.semantic_hash(),
            "provenance_hash": document.provenance_hash()
        },
        "adapter_request_hash": adapter_request.request_hash(),
        "generated_request_hash": generated.request_hash(),
        "native_run_receipt_hash": sha256_identity(native.run_receipt_json().as_bytes()),
        "derivation": derivation,
        "checkpoint": checkpoint.receipt(),
        "artifacts": artifacts,
        "claim_boundary": "exact_fixed_guided_frame3d_x_modelir_to_bounded_cpu_ndtha_c5_not_arbitrary_topology_or_hip",
        "receipt_hash": ""
    });
    receipt
        .as_object_mut()
        .and_then(|object| object.remove("receipt_hash"))
        .ok_or_else(|| {
            contract_error(
                "model_ir_ndtha_run_receipt_invariant_failed",
                "/",
                "ModelIR NDTHA run receipt is not an object",
            )
        })?;
    let unsigned = canonicalize_value(
        &receipt,
        "model_ir_ndtha_run_receipt_canonicalization_failed",
    )?;
    receipt
        .as_object_mut()
        .expect("receipt object was checked")
        .insert(
            "receipt_hash".to_owned(),
            Value::String(sha256_identity(unsigned.as_bytes())),
        );
    canonicalize_value(
        &receipt,
        "model_ir_ndtha_run_receipt_canonicalization_failed",
    )
}

fn model_contract_error(error: &ModelIrContractError) -> NativeAnalysisProductError {
    contract_error(&error.code, &error.path, &error.detail)
}

fn contract_error(code: &str, path: &str, detail: &str) -> NativeAnalysisProductError {
    NativeAnalysisProductError::Contract(ProductIrContractError {
        code: code.to_owned(),
        path: path.to_owned(),
        detail: detail.to_owned(),
    })
}
