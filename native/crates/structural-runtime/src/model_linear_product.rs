use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use structural_contracts::model_ir::{canonicalize_model_ir_v2, ModelIrV2Document};
use structural_contracts::model_linear_product::{
    ModelIrLinearAnalysisRequestDocumentV1, MODEL_IR_LINEAR_MAXIMUM_RECOVERY_RECORDS,
};
use structural_contracts::product_ir::sha256_identity;
use structural_contracts::sparse_product::{
    build_sparse_linear_request_v1, SparseLinearAnalysisRequestDocumentV1,
    SparseLinearAnalysisRequestV1, SparseLinearBackendV1, SparseLinearResultIrDocumentV1,
    SPARSE_LINEAR_MAXIMUM_NONZEROS, SPARSE_LINEAR_MAXIMUM_ORDER, SPARSE_LINEAR_REQUEST_V1,
};

use crate::{ModelIrLinearAssembly, ModelIrLinearAssemblyRequest, Runtime, RuntimeError};

/// Exact ABI assembly projection and derived sparse request shared by CLI and durable jobs.
#[derive(Clone, Debug)]
pub struct PreparedModelIrLinearProductV1 {
    pub assembly: ModelIrLinearAssembly,
    pub assembly_receipt_json: String,
    pub assembly_hash: String,
    pub generated_request: SparseLinearAnalysisRequestDocumentV1,
}

impl Runtime {
    /// Prepare the one authoritative typed-`ModelIR` CPU operator used by product execution.
    ///
    /// # Errors
    ///
    /// Returns a stable runtime error when model identity, ABI output, product bounds, canonical
    /// receipt construction, or generated sparse-request validation fails.
    pub fn prepare_model_ir_linear_product(
        &self,
        document: &ModelIrV2Document,
        request: &ModelIrLinearAnalysisRequestDocumentV1,
    ) -> Result<PreparedModelIrLinearProductV1, RuntimeError> {
        verify_model_identity(document, request)?;
        let assembly =
            self.assemble_model_ir_linear(document, request.request().load_pattern_id.as_str())?;
        let (assembly_receipt_json, assembly_hash) =
            build_assembly_receipt(document, request, &assembly)?;
        let generated_request = generated_sparse_request(request, &assembly)?;
        Ok(PreparedModelIrLinearProductV1 {
            assembly,
            assembly_receipt_json,
            assembly_hash,
            generated_request,
        })
    }

    /// Re-enter ABI v1.13 at a converged displacement and construct exact recovery bytes.
    ///
    /// # Errors
    ///
    /// Returns a stable runtime error for result/map drift, native recovery failure, nonfinite
    /// output, or any immutable operator and same-source JVP invariant violation.
    #[allow(clippy::too_many_lines)]
    pub fn recover_model_ir_linear_product(
        &self,
        document: &ModelIrV2Document,
        request: &ModelIrLinearAnalysisRequestDocumentV1,
        prepared: &PreparedModelIrLinearProductV1,
        result: &SparseLinearResultIrDocumentV1,
    ) -> Result<String, RuntimeError> {
        let initial = &prepared.assembly;
        let global_count = usize::try_from(initial.global_dof_count).map_err(|_| {
            product_error("ModelIR linear global DOF count exceeds the address space")
        })?;
        let solution = &result.result().solution;
        if solution.len() != initial.active_dof_indices.len() {
            return Err(product_error(
                "ModelIR linear solution does not match the active DOF map",
            ));
        }
        let mut global_displacement = allocate_f64(global_count, "global displacement")?;
        for (active, value) in initial.active_dof_indices.iter().zip(solution) {
            let index = usize::try_from(*active)
                .map_err(|_| product_error("ModelIR linear active DOF exceeds address space"))?;
            let slot = global_displacement.get_mut(index).ok_or_else(|| {
                product_error("ModelIR linear active DOF exceeds global displacement")
            })?;
            *slot = *value;
        }
        let recovered = self.assemble_model_ir_linear_state(
            document,
            &ModelIrLinearAssemblyRequest {
                load_pattern_id: request.request().load_pattern_id.clone(),
                direction: try_clone_slice(&global_displacement, "recovery direction")?,
                displacement: try_clone_slice(&global_displacement, "global displacement")?,
            },
        )?;
        verify_recovered_operator(initial, &recovered)?;
        if !f64_bits_equal(&recovered.internal_force, &recovered.jvp) {
            return Err(product_error(
                "ModelIR linear internal force and same-state JVP differ",
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
            "assembly_hash": prepared.assembly_hash,
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
            .ok_or_else(|| product_error("ModelIR linear recovery is not a JSON object"))?;
        let unsigned = canonicalize_value(&value, "recovery")?;
        value
            .as_object_mut()
            .ok_or_else(|| product_error("ModelIR linear recovery is not a JSON object"))?
            .insert(
                "recovery_hash".to_owned(),
                Value::String(sha256_identity(unsigned.as_bytes())),
            );
        canonicalize_value(&value, "recovery")
    }
}

#[allow(clippy::too_many_lines)]
fn build_assembly_receipt(
    document: &ModelIrV2Document,
    request: &ModelIrLinearAnalysisRequestDocumentV1,
    assembly: &ModelIrLinearAssembly,
) -> Result<(String, String), RuntimeError> {
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
        return Err(product_error(
            "ModelIR linear assembly is outside the bounded zero-state product domain",
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
        .ok_or_else(|| product_error("ModelIR linear assembly receipt is not a JSON object"))?;
    let unsigned = canonicalize_value(&value, "assembly receipt")?;
    let assembly_hash = sha256_identity(unsigned.as_bytes());
    value
        .as_object_mut()
        .ok_or_else(|| product_error("ModelIR linear assembly receipt is not a JSON object"))?
        .insert(
            "assembly_hash".to_owned(),
            Value::String(assembly_hash.clone()),
        );
    Ok((
        canonicalize_value(&value, "assembly receipt")?,
        assembly_hash,
    ))
}

fn generated_sparse_request(
    request: &ModelIrLinearAnalysisRequestDocumentV1,
    assembly: &ModelIrLinearAssembly,
) -> Result<SparseLinearAnalysisRequestDocumentV1, RuntimeError> {
    let order = u32::try_from(assembly.active_dof_indices.len())
        .map_err(|_| product_error("ModelIR linear active DOF count exceeds sparse order"))?;
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

fn verify_model_identity(
    document: &ModelIrV2Document,
    request: &ModelIrLinearAnalysisRequestDocumentV1,
) -> Result<(), RuntimeError> {
    let supplied = &request.request().model_identity;
    if supplied.content_hash == document.content_hash()
        && supplied.semantic_hash == document.semantic_hash()
        && supplied.provenance_hash == document.provenance_hash()
    {
        Ok(())
    } else {
        Err(product_error(
            "ModelIR linear request identities do not match the exact model",
        ))
    }
}

fn verify_recovered_operator(
    initial: &ModelIrLinearAssembly,
    recovered: &ModelIrLinearAssembly,
) -> Result<(), RuntimeError> {
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
        Err(product_error(
            "ModelIR linear terminal recovery changed the immutable operator or mapping",
        ))
    }
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

fn try_clone_slice<T: Clone>(values: &[T], label: &str) -> Result<Vec<T>, RuntimeError> {
    let mut output = Vec::new();
    output
        .try_reserve_exact(values.len())
        .map_err(|_| allocation_error(label))?;
    output.extend_from_slice(values);
    Ok(output)
}

fn allocate_f64(length: usize, label: &str) -> Result<Vec<f64>, RuntimeError> {
    let mut output = Vec::new();
    output
        .try_reserve_exact(length)
        .map_err(|_| allocation_error(label))?;
    output.resize(length, 0.0);
    Ok(output)
}

fn canonicalize_value(value: &Value, label: &str) -> Result<String, RuntimeError> {
    canonicalize_model_ir_v2(value)
        .map_err(|_| product_error(&format!("ModelIR linear {label} cannot be canonicalized")))
}

fn product_error(message: &str) -> RuntimeError {
    RuntimeError {
        code: 1100,
        message: message.to_owned(),
    }
}

fn allocation_error(label: &str) -> RuntimeError {
    RuntimeError {
        code: 1900,
        message: format!("ModelIR linear {label} allocation failed"),
    }
}
