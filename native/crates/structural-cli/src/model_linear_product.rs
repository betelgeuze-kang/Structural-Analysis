use std::fmt;
use std::path::Path;

use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use structural_contracts::model_ir::{parse_model_ir_v2, ModelIrContractError, ModelIrV2Document};
use structural_contracts::model_linear_product::{
    parse_model_ir_linear_analysis_request_v1, ModelIrLinearAnalysisRequestDocumentV1,
    MODEL_IR_LINEAR_MAXIMUM_RECOVERY_RECORDS,
};
use structural_contracts::product_ir::{sha256_identity, ProductIrContractError};
use structural_contracts::sparse_product::{
    build_sparse_linear_request_v1, SparseLinearAnalysisRequestDocumentV1,
    SparseLinearAnalysisRequestV1, SparseLinearBackendV1, SparseLinearResultIrDocumentV1,
    SPARSE_LINEAR_MAXIMUM_NONZEROS, SPARSE_LINEAR_MAXIMUM_ORDER, SPARSE_LINEAR_REQUEST_V1,
};
use structural_runtime::{
    ModelIrLinearAssembly, ModelIrLinearAssemblyRequest, ModelIrLinearCheckpointBindingsV1,
    ModelIrLinearCheckpointReceiptV1, ModelIrLinearCheckpointV1, Runtime, RuntimeError,
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
    let assembly =
        runtime.assemble_model_ir_linear(&document, request.request().load_pattern_id.as_str())?;
    let assembly_receipt = build_assembly_receipt(&document, &request, &assembly)?;
    let generated = generated_sparse_request(&request, &assembly)?;
    let bindings = ModelIrLinearCheckpointBindingsV1 {
        model_content_hash: document.content_hash().to_owned(),
        model_semantic_hash: document.semantic_hash().to_owned(),
        model_provenance_hash: document.provenance_hash().to_owned(),
        analysis_request_hash: request.request_hash().to_owned(),
        assembly_hash: assembly_receipt.assembly_hash.clone(),
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
        .map(|result| {
            recover_terminal_result(
                &runtime,
                &document,
                &request,
                &assembly,
                &assembly_receipt.assembly_hash,
                result,
            )
        })
        .transpose()?;
    let run_receipt_json = build_run_receipt(
        &document,
        &request,
        &assembly_receipt,
        &generated,
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
        generated_request_json: generated.canonical_json().to_owned(),
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

#[allow(clippy::too_many_lines)]
fn build_assembly_receipt(
    document: &ModelIrV2Document,
    request: &ModelIrLinearAnalysisRequestDocumentV1,
    assembly: &ModelIrLinearAssembly,
) -> Result<AssemblyReceipt, ModelIrLinearProductError> {
    let active_count = assembly.active_dof_indices.len();
    let entry_count = assembly.tangent.len();
    let recovery_count = assembly.recovery_stable_indices.len();
    let bounded = active_count > 0
        && active_count <= SPARSE_LINEAR_MAXIMUM_ORDER as usize
        && entry_count <= SPARSE_LINEAR_MAXIMUM_NONZEROS
        && recovery_count <= MODEL_IR_LINEAR_MAXIMUM_RECOVERY_RECORDS
        && assembly.model_content_hash == document.content_hash()
        && assembly.model_semantic_hash == document.semantic_hash()
        && assembly.model_provenance_hash == document.provenance_hash()
        && assembly.fallback_count == 0
        && assembly.internal_force.iter().all(|value| *value == 0.0)
        && assembly.jvp.iter().all(|value| *value == 0.0)
        && assembly.recovery_values.iter().all(|value| *value == 0.0);
    if !bounded {
        return Err(contract_error(
            "model_ir_linear_assembly_product_domain_invalid",
            "/assembly",
            "native assembly is outside the bounded sparse product or zero-state domain",
        ));
    }
    let mut value = json!({
        "schema_version": "structural-model-ir-linear-assembly-receipt.v1",
        "abi_version": "0x0001000d",
        "case_id": request.request().case_id,
        "model_id": document.model_id(),
        "model_identity": {
            "content_hash": assembly.model_content_hash,
            "semantic_hash": assembly.model_semantic_hash,
            "provenance_hash": assembly.model_provenance_hash
        },
        "analysis_request_hash": request.request_hash(),
        "load_pattern_id": request.request().load_pattern_id,
        "load_pattern_index": assembly.load_pattern_index,
        "global_dof_count": assembly.global_dof_count,
        "dof_order_per_node": ["UX", "UY", "UZ", "RX", "RY", "RZ"],
        "active_dof_indices": &assembly.active_dof_indices,
        "row_offset_count": assembly.row_offsets.len(),
        "structural_entry_count": entry_count,
        "recovery_stable_indices": &assembly.recovery_stable_indices,
        "recovery_element_types": &assembly.recovery_element_types,
        "recovery_offsets": &assembly.recovery_offsets,
        "recovery_value_count": assembly.recovery_values.len(),
        "array_hashes": {
            "active_dof_indices": hash_u32("active_dof_indices", &assembly.active_dof_indices),
            "row_offsets": hash_u64("row_offsets", &assembly.row_offsets),
            "column_indices": hash_u32("column_indices", &assembly.column_indices),
            "tangent": hash_f64("tangent", &assembly.tangent),
            "consistent_mass": hash_f64("consistent_mass", &assembly.consistent_mass),
            "internal_force": hash_f64("internal_force", &assembly.internal_force),
            "external_load": hash_f64("external_load", &assembly.external_load),
            "equilibrium_residual": hash_f64("equilibrium_residual", &assembly.equilibrium_residual),
            "jvp": hash_f64("jvp", &assembly.jvp),
            "recovery_stable_indices": hash_u64("recovery_stable_indices", &assembly.recovery_stable_indices),
            "recovery_element_types": hash_u32("recovery_element_types", &assembly.recovery_element_types),
            "recovery_offsets": hash_u64("recovery_offsets", &assembly.recovery_offsets),
            "recovery_values": hash_f64("recovery_values", &assembly.recovery_values)
        },
        "backend": "cpu",
        "precision": "fp64",
        "fallback_count": assembly.fallback_count,
        "claim_boundary": "bounded_frame3d_truss3d_zero_state_cpu_assembly_for_pcg_not_shell_nonlinear_hip_or_engineering_acceptance",
        "assembly_hash": ""
    });
    value
        .as_object_mut()
        .and_then(|object| object.remove("assembly_hash"))
        .ok_or_else(|| {
            contract_error(
                "model_ir_linear_assembly_receipt_invariant_failed",
                "/assembly",
                "assembly receipt is not an object",
            )
        })?;
    let unsigned = canonicalize_value(
        &value,
        "model_ir_linear_assembly_receipt_canonicalization_failed",
    )?;
    let assembly_hash = sha256_identity(unsigned.as_bytes());
    value
        .as_object_mut()
        .expect("assembly receipt object was checked")
        .insert(
            "assembly_hash".to_owned(),
            Value::String(assembly_hash.clone()),
        );
    Ok(AssemblyReceipt {
        canonical_json: canonicalize_value(
            &value,
            "model_ir_linear_assembly_receipt_canonicalization_failed",
        )?,
        assembly_hash,
    })
}

fn generated_sparse_request(
    request: &ModelIrLinearAnalysisRequestDocumentV1,
    assembly: &ModelIrLinearAssembly,
) -> Result<SparseLinearAnalysisRequestDocumentV1, ModelIrLinearProductError> {
    let order = u32::try_from(assembly.active_dof_indices.len()).map_err(|_| {
        contract_error(
            "model_ir_linear_generated_order_invalid",
            "/assembly/active_dof_indices",
            "active DOF count exceeds the sparse product order",
        )
    })?;
    build_sparse_linear_request_v1(SparseLinearAnalysisRequestV1 {
        schema_version: SPARSE_LINEAR_REQUEST_V1.to_owned(),
        operation: "solve_sparse_spd_pcg".to_owned(),
        case_id: request.request().case_id.clone(),
        backend: SparseLinearBackendV1::Cpu,
        order,
        row_offsets: try_clone_slice(&assembly.row_offsets, "row offsets")?,
        column_indices: try_clone_slice(&assembly.column_indices, "column indices")?,
        values: try_clone_slice(&assembly.tangent, "tangent")?,
        right_hand_side: try_clone_slice(&assembly.external_load, "external load")?,
        initial_guess: Vec::new(),
        config: request.request().config,
    })
    .map_err(Into::into)
}

#[allow(clippy::too_many_lines)]
fn recover_terminal_result(
    runtime: &Runtime,
    document: &ModelIrV2Document,
    request: &ModelIrLinearAnalysisRequestDocumentV1,
    initial: &ModelIrLinearAssembly,
    assembly_hash: &str,
    result: &SparseLinearResultIrDocumentV1,
) -> Result<String, ModelIrLinearProductError> {
    let global_count = usize::try_from(initial.global_dof_count).map_err(|_| {
        contract_error(
            "model_ir_linear_global_dof_count_invalid",
            "/assembly/global_dof_count",
            "global DOF count exceeds the address space",
        )
    })?;
    let solution = &result.result().solution;
    if solution.len() != initial.active_dof_indices.len() {
        return Err(contract_error(
            "model_ir_linear_solution_extent_invalid",
            "/result/solution",
            "terminal solution does not match the active DOF map",
        ));
    }
    let mut global_displacement = allocate_f64(global_count, "global displacement")?;
    for (active, value) in initial.active_dof_indices.iter().zip(solution) {
        let index = usize::try_from(*active).map_err(|_| {
            contract_error(
                "model_ir_linear_active_dof_invalid",
                "/assembly/active_dof_indices",
                "active DOF index exceeds the address space",
            )
        })?;
        let slot = global_displacement.get_mut(index).ok_or_else(|| {
            contract_error(
                "model_ir_linear_active_dof_invalid",
                "/assembly/active_dof_indices",
                "active DOF index exceeds the global displacement extent",
            )
        })?;
        *slot = *value;
    }
    let recovered = runtime.assemble_model_ir_linear_state(
        document,
        &ModelIrLinearAssemblyRequest {
            load_pattern_id: request.request().load_pattern_id.clone(),
            direction: try_clone_slice(&global_displacement, "recovery direction")?,
            displacement: try_clone_slice(&global_displacement, "global displacement")?,
        },
    )?;
    verify_recovered_operator(initial, &recovered)?;
    if !f64_bits_equal(&recovered.internal_force, &recovered.jvp) {
        return Err(contract_error(
            "model_ir_linear_recovery_source_drift",
            "/recovery/jvp",
            "linear internal force and same-state JVP are not bitwise identical",
        ));
    }
    let maximum_absolute_displacement = global_displacement
        .iter()
        .map(|value| value.abs())
        .fold(0.0_f64, f64::max);
    let residual_inf = recovered
        .equilibrium_residual
        .iter()
        .map(|value| value.abs())
        .fold(0.0_f64, f64::max);
    let mut value = json!({
        "schema_version": "structural-model-ir-linear-result-recovery-ir.v1",
        "case_id": request.request().case_id,
        "model_id": document.model_id(),
        "model_identity": {
            "content_hash": document.content_hash(),
            "semantic_hash": document.semantic_hash(),
            "provenance_hash": document.provenance_hash()
        },
        "analysis_request_hash": request.request_hash(),
        "assembly_hash": assembly_hash,
        "source_result_hash": result.result_hash(),
        "load_pattern_id": request.request().load_pattern_id,
        "load_pattern_index": recovered.load_pattern_index,
        "global_dof_count": recovered.global_dof_count,
        "dof_order_per_node": ["UX", "UY", "UZ", "RX", "RY", "RZ"],
        "active_dof_indices": &recovered.active_dof_indices,
        "global_displacement": global_displacement,
        "active_internal_force": &recovered.internal_force,
        "active_external_load": &recovered.external_load,
        "active_equilibrium_residual": &recovered.equilibrium_residual,
        "same_state_jvp": &recovered.jvp,
        "recovery_stable_indices": &recovered.recovery_stable_indices,
        "recovery_element_types": &recovered.recovery_element_types,
        "recovery_offsets": &recovered.recovery_offsets,
        "recovery_values": &recovered.recovery_values,
        "summary": {
            "maximum_absolute_displacement": maximum_absolute_displacement,
            "active_residual_inf": residual_inf
        },
        "units": {
            "global_displacement": "translations_m_rotations_rad",
            "active_force": "forces_n_moments_n_m",
            "frame3d_recovery": "local_end_forces_n_and_moments_n_m",
            "truss3d_recovery": ["axial_strain_1", "axial_stress_pa", "axial_force_n"]
        },
        "coordinate_frame": {
            "global_displacement_and_active_force": "model_global",
            "frame3d_recovery": "element_local",
            "truss3d_recovery": "element_axis"
        },
        "backend": "cpu",
        "precision": "fp64",
        "fallback_count": recovered.fallback_count,
        "claim_boundary": "bounded_active_dof_and_element_recovery_not_constrained_reactions_shell_nonlinear_hip_or_engineering_acceptance",
        "recovery_hash": ""
    });
    value
        .as_object_mut()
        .and_then(|object| object.remove("recovery_hash"))
        .ok_or_else(|| {
            contract_error(
                "model_ir_linear_recovery_invariant_failed",
                "/recovery",
                "recovery artifact is not an object",
            )
        })?;
    let unsigned = canonicalize_value(&value, "model_ir_linear_recovery_canonicalization_failed")?;
    value
        .as_object_mut()
        .expect("recovery object was checked")
        .insert(
            "recovery_hash".to_owned(),
            Value::String(sha256_identity(unsigned.as_bytes())),
        );
    canonicalize_value(&value, "model_ir_linear_recovery_canonicalization_failed")
        .map_err(Into::into)
}

fn verify_recovered_operator(
    initial: &ModelIrLinearAssembly,
    recovered: &ModelIrLinearAssembly,
) -> Result<(), ModelIrLinearProductError> {
    let fixed_equal = recovered.model_content_hash == initial.model_content_hash
        && recovered.model_semantic_hash == initial.model_semantic_hash
        && recovered.model_provenance_hash == initial.model_provenance_hash
        && recovered.load_pattern_index == initial.load_pattern_index
        && recovered.global_dof_count == initial.global_dof_count
        && recovered.active_dof_indices == initial.active_dof_indices
        && recovered.row_offsets == initial.row_offsets
        && recovered.column_indices == initial.column_indices
        && recovered.recovery_stable_indices == initial.recovery_stable_indices
        && recovered.recovery_element_types == initial.recovery_element_types
        && recovered.recovery_offsets == initial.recovery_offsets
        && recovered.execution_backend == initial.execution_backend
        && recovered.fallback_count == 0;
    let numeric_equal = f64_bits_equal(&recovered.tangent, &initial.tangent)
        && f64_bits_equal(&recovered.consistent_mass, &initial.consistent_mass)
        && f64_bits_equal(&recovered.external_load, &initial.external_load);
    if fixed_equal && numeric_equal {
        Ok(())
    } else {
        Err(contract_error(
            "model_ir_linear_recovery_operator_drift",
            "/recovery",
            "terminal recovery changed the immutable operator, load, or mapping",
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

fn hash_u32(label: &str, values: &[u32]) -> String {
    hash_array(label, values.len(), |hasher| {
        for value in values {
            hasher.update(value.to_le_bytes());
        }
    })
}

fn hash_u64(label: &str, values: &[u64]) -> String {
    hash_array(label, values.len(), |hasher| {
        for value in values {
            hasher.update(value.to_le_bytes());
        }
    })
}

fn hash_f64(label: &str, values: &[f64]) -> String {
    hash_array(label, values.len(), |hasher| {
        for value in values {
            hasher.update(value.to_bits().to_le_bytes());
        }
    })
}

fn hash_array(label: &str, length: usize, update: impl FnOnce(&mut Sha256)) -> String {
    let mut hasher = Sha256::new();
    hasher.update(b"structural-model-ir-linear-array.v1\0");
    hasher.update(label.as_bytes());
    hasher.update([0]);
    hasher.update(u64::try_from(length).unwrap_or(u64::MAX).to_le_bytes());
    update(&mut hasher);
    format!("sha256:{:x}", hasher.finalize())
}

fn f64_bits_equal(left: &[f64], right: &[f64]) -> bool {
    left.len() == right.len()
        && left
            .iter()
            .zip(right)
            .all(|(left, right)| left.to_bits() == right.to_bits())
}

fn try_clone_slice<T: Clone>(
    values: &[T],
    label: &str,
) -> Result<Vec<T>, ModelIrLinearProductError> {
    let mut output = Vec::new();
    output.try_reserve_exact(values.len()).map_err(|_| {
        contract_error(
            "model_ir_linear_allocation_failed",
            "/",
            &format!("{label} allocation failed"),
        )
    })?;
    output.extend_from_slice(values);
    Ok(output)
}

fn allocate_f64(length: usize, label: &str) -> Result<Vec<f64>, ModelIrLinearProductError> {
    let mut output = Vec::new();
    output.try_reserve_exact(length).map_err(|_| {
        contract_error(
            "model_ir_linear_allocation_failed",
            "/",
            &format!("{label} allocation failed"),
        )
    })?;
    output.resize(length, 0.0);
    Ok(output)
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
