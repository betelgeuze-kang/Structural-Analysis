use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use structural_contracts::model_ir::{canonicalize_model_ir_v2, ModelIrV2Document};
use structural_contracts::model_modal_product::ModelIrModalAnalysisRequestDocumentV1;
use structural_contracts::spectral_product::{
    build_dense_spectral_request_v1, DenseSpectralAnalysisRequestDocumentV1,
    DenseSpectralAnalysisRequestV1, SpectralAnalysisKindV1, SpectralBackendV1,
    DENSE_SPECTRAL_REQUEST_V1,
};

use crate::{ModelIrLinearAssembly, Runtime, RuntimeError};

const MAXIMUM_MODAL_ORDER: usize = 128;

/// Exact ABI assembly projection and generated dense modal request.
#[derive(Clone, Debug)]
pub struct PreparedModelIrModalProductV1 {
    pub assembly: ModelIrLinearAssembly,
    pub assembly_receipt_json: String,
    pub assembly_hash: String,
    pub generated_request: DenseSpectralAnalysisRequestDocumentV1,
}

impl Runtime {
    /// Assemble one bounded typed-`ModelIR` frame/truss graph and adapt its active `K/M` pair to
    /// the existing dense modal product boundary.
    ///
    /// # Errors
    ///
    /// Returns a stable runtime error for identity drift, unsupported assembly state, more than
    /// 128 active DOFs, malformed CSR, asymmetric operators, fallback, allocation failure, or a
    /// generated dense request outside the modal contract.
    pub fn prepare_model_ir_modal_product(
        &self,
        document: &ModelIrV2Document,
        request: &ModelIrModalAnalysisRequestDocumentV1,
    ) -> Result<PreparedModelIrModalProductV1, RuntimeError> {
        verify_model_identity(document, request)?;
        let assembly = self.assemble_model_ir_linear(
            document,
            request.request().assembly_load_pattern_id.as_str(),
        )?;
        let (assembly_receipt_json, assembly_hash) =
            build_assembly_receipt(document, request, &assembly)?;
        let order = assembly.active_dof_indices.len();
        let stiffness = csr_to_dense(&assembly, &assembly.tangent, "stiffness")?;
        let mass = csr_to_dense(&assembly, &assembly.consistent_mass, "mass")?;
        let generated_request = build_dense_spectral_request_v1(DenseSpectralAnalysisRequestV1 {
            schema_version: DENSE_SPECTRAL_REQUEST_V1.to_owned(),
            operation: "solve_dense_generalized_eigen".to_owned(),
            case_id: request.request().case_id.clone(),
            analysis_kind: SpectralAnalysisKindV1::Modal,
            backend: SpectralBackendV1::Cpu,
            order: u32::try_from(order)
                .map_err(|_| product_error("ModelIR modal order exceeds u32"))?,
            stiffness,
            secondary_matrix: mass,
            coordinate_recovery_scale: Vec::new(),
            config: request.request().config,
        })?;
        Ok(PreparedModelIrModalProductV1 {
            assembly,
            assembly_receipt_json,
            assembly_hash,
            generated_request,
        })
    }
}

fn build_assembly_receipt(
    document: &ModelIrV2Document,
    request: &ModelIrModalAnalysisRequestDocumentV1,
    assembly: &ModelIrLinearAssembly,
) -> Result<(String, String), RuntimeError> {
    let order = assembly.active_dof_indices.len();
    let bounded = (1..=MAXIMUM_MODAL_ORDER).contains(&order)
        && request.request().config.mode_count <= u32::try_from(order).unwrap_or(0)
        && assembly.row_offsets.len() == order + 1
        && assembly.column_indices.len() == assembly.tangent.len()
        && assembly.consistent_mass.len() == assembly.tangent.len()
        && assembly.model_content_hash == document.content_hash()
        && assembly.model_semantic_hash == document.semantic_hash()
        && assembly.model_provenance_hash == document.provenance_hash()
        && assembly.execution_backend == 1
        && assembly.fallback_count == 0
        && assembly.internal_force.iter().all(|value| *value == 0.0)
        && assembly.jvp.iter().all(|value| *value == 0.0)
        && assembly.recovery_values.iter().all(|value| *value == 0.0);
    if !bounded {
        return Err(product_error(
            "ModelIR modal assembly is outside the bounded zero-state product domain",
        ));
    }
    let mut value = json!({
        "schema_version": "structural-model-ir-modal-assembly-receipt.v1",
        "assembly_abi_version": "0x0001000e",
        "modal_abi_version": "0x00010009",
        "case_id": request.request().case_id,
        "model_id": document.model_id(),
        "model_identity": {
            "content_hash": assembly.model_content_hash,
            "semantic_hash": assembly.model_semantic_hash,
            "provenance_hash": assembly.model_provenance_hash
        },
        "analysis_request_hash": request.request_hash(),
        "assembly_load_pattern_id": request.request().assembly_load_pattern_id,
        "assembly_load_pattern_index": assembly.load_pattern_index,
        "load_vector_consumed_by_modal": false,
        "global_dof_count": assembly.global_dof_count,
        "active_dof_indices": &assembly.active_dof_indices,
        "active_dof_count": order,
        "row_offset_count": assembly.row_offsets.len(),
        "structural_entry_count": assembly.tangent.len(),
        "array_hashes": {
            "active_dof_indices": hash_u32("active_dof_indices", &assembly.active_dof_indices),
            "row_offsets": hash_u64("row_offsets", &assembly.row_offsets),
            "column_indices": hash_u32("column_indices", &assembly.column_indices),
            "stiffness": hash_f64("stiffness", &assembly.tangent),
            "consistent_mass": hash_f64("consistent_mass", &assembly.consistent_mass)
        },
        "backend": "cpu",
        "precision": "fp64",
        "fallback_count": assembly.fallback_count,
        "claim_boundary": "bounded_frame3d_truss3d_modelir_active_k_m_to_dense_cpu_modal_adapter_max_128_dofs_not_sparse_buckling_shell_nonlinear_hip_distribution_or_engineering_acceptance",
        "assembly_hash": ""
    });
    value
        .as_object_mut()
        .and_then(|object| object.remove("assembly_hash"))
        .ok_or_else(|| product_error("ModelIR modal assembly receipt is not an object"))?;
    let unsigned = canonicalize(&value, "assembly receipt")?;
    let assembly_hash = structural_contracts::product_ir::sha256_identity(unsigned.as_bytes());
    value
        .as_object_mut()
        .ok_or_else(|| product_error("ModelIR modal assembly receipt is not an object"))?
        .insert(
            "assembly_hash".to_owned(),
            Value::String(assembly_hash.clone()),
        );
    Ok((canonicalize(&value, "assembly receipt")?, assembly_hash))
}

fn csr_to_dense(
    assembly: &ModelIrLinearAssembly,
    values: &[f64],
    label: &str,
) -> Result<Vec<f64>, RuntimeError> {
    let order = assembly.active_dof_indices.len();
    if !(1..=MAXIMUM_MODAL_ORDER).contains(&order)
        || assembly.row_offsets.len() != order + 1
        || assembly.column_indices.len() != values.len()
        || values.iter().any(|value| !value.is_finite())
    {
        return Err(product_error(&format!(
            "ModelIR modal {label} CSR shape is invalid"
        )));
    }
    let length = order
        .checked_mul(order)
        .ok_or_else(|| product_error("ModelIR modal dense length overflowed"))?;
    let mut dense = Vec::new();
    dense
        .try_reserve_exact(length)
        .map_err(|_| allocation_error("dense modal operator"))?;
    dense.resize(length, 0.0);
    for row in 0..order {
        let begin = usize::try_from(assembly.row_offsets[row])
            .map_err(|_| product_error("ModelIR modal CSR row offset exceeds address space"))?;
        let end = usize::try_from(assembly.row_offsets[row + 1])
            .map_err(|_| product_error("ModelIR modal CSR row offset exceeds address space"))?;
        if begin > end || end > values.len() {
            return Err(product_error("ModelIR modal CSR row offsets are invalid"));
        }
        let mut previous = None;
        for (&column, &value) in assembly.column_indices[begin..end]
            .iter()
            .zip(&values[begin..end])
        {
            let column = usize::try_from(column)
                .map_err(|_| product_error("ModelIR modal CSR column exceeds address space"))?;
            if column >= order || previous.is_some_and(|value| column <= value) {
                return Err(product_error(
                    "ModelIR modal CSR columns are not strictly ordered and bounded",
                ));
            }
            dense[row * order + column] = value;
            previous = Some(column);
        }
    }
    for row in 0..order {
        for column in row + 1..order {
            if dense[row * order + column].to_bits() != dense[column * order + row].to_bits() {
                return Err(product_error(&format!(
                    "ModelIR modal {label} operator is not exactly symmetric"
                )));
            }
        }
    }
    Ok(dense)
}

fn verify_model_identity(
    document: &ModelIrV2Document,
    request: &ModelIrModalAnalysisRequestDocumentV1,
) -> Result<(), RuntimeError> {
    let supplied = &request.request().model_identity;
    if supplied.content_hash == document.content_hash()
        && supplied.semantic_hash == document.semantic_hash()
        && supplied.provenance_hash == document.provenance_hash()
    {
        Ok(())
    } else {
        Err(product_error(
            "ModelIR modal request identities do not match the exact model",
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
    hasher.update(b"structural-model-ir-modal-array.v1\0");
    hasher.update(label.as_bytes());
    hasher.update([0]);
    hasher.update(u64::try_from(length).unwrap_or(u64::MAX).to_le_bytes());
    update(&mut hasher);
    format!("sha256:{:x}", hasher.finalize())
}

fn canonicalize(value: &Value, label: &str) -> Result<String, RuntimeError> {
    canonicalize_model_ir_v2(value)
        .map_err(|_| product_error(&format!("ModelIR modal {label} cannot be canonicalized")))
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
        message: format!("ModelIR modal {label} allocation failed"),
    }
}

#[cfg(test)]
mod tests {
    use super::csr_to_dense;
    use crate::ModelIrLinearAssembly;

    fn assembly() -> ModelIrLinearAssembly {
        ModelIrLinearAssembly {
            model_content_hash: String::new(),
            model_semantic_hash: String::new(),
            model_provenance_hash: String::new(),
            load_pattern_index: 0,
            global_dof_count: 2,
            active_dof_indices: vec![0, 1],
            row_offsets: vec![0, 2, 4],
            column_indices: vec![0, 1, 0, 1],
            tangent: vec![2.0, -1.0, -1.0, 2.0],
            consistent_mass: vec![1.0, 0.0, 0.0, 1.0],
            internal_force: vec![0.0; 2],
            external_load: vec![0.0; 2],
            equilibrium_residual: vec![0.0; 2],
            jvp: vec![0.0; 2],
            recovery_stable_indices: Vec::new(),
            recovery_element_types: Vec::new(),
            recovery_offsets: vec![0],
            recovery_values: Vec::new(),
            execution_backend: 1,
            fallback_count: 0,
        }
    }

    #[test]
    fn canonical_csr_densifies_in_row_major_order() {
        assert_eq!(
            csr_to_dense(&assembly(), &assembly().tangent, "stiffness").expect("dense"),
            vec![2.0, -1.0, -1.0, 2.0]
        );
    }

    #[test]
    fn asymmetric_or_duplicate_csr_fails_closed() {
        let mut asymmetric = assembly();
        asymmetric.tangent[2] = -2.0;
        assert!(csr_to_dense(&asymmetric, &asymmetric.tangent, "stiffness").is_err());

        let mut duplicate = assembly();
        duplicate.column_indices[1] = 0;
        assert!(csr_to_dense(&duplicate, &duplicate.tangent, "stiffness").is_err());
    }
}
