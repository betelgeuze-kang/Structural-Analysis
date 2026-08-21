use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use structural_contracts::model_buckling_product::ModelIrLinearBucklingAnalysisRequestDocumentV1;
use structural_contracts::model_ir::{canonicalize_model_ir_v2, ModelIrV2Document};
use structural_contracts::model_linear_product::{
    build_model_ir_linear_analysis_request_v1, ModelIrLinearAnalysisRequestDocumentV1,
    ModelIrLinearAnalysisRequestV1, ModelIrLinearBackendV1, MODEL_IR_LINEAR_ANALYSIS_REQUEST_V1,
};
use structural_contracts::spectral_product::{
    build_dense_spectral_request_v1, DenseSpectralAnalysisRequestDocumentV1,
    DenseSpectralAnalysisRequestV1, SpectralAnalysisKindV1, SpectralBackendV1,
    DENSE_SPECTRAL_REQUEST_V1,
};
use structural_ffi::{Api, ModelIrLinearBucklingAssembly, ModelIrLinearBucklingAssemblyRequest};

use crate::{PreparedModelIrLinearProductV1, Runtime, RuntimeError};

const MAXIMUM_BUCKLING_ORDER: usize = 128;

/// Deterministically generated reference-static request and exact native linear preparation.
#[derive(Clone, Debug)]
pub struct PreparedModelIrLinearBucklingReferenceV1 {
    pub request: ModelIrLinearAnalysisRequestDocumentV1,
    pub product: PreparedModelIrLinearProductV1,
}

/// Exact v1.15 prestress projection and generated dense buckling request.
#[derive(Clone, Debug)]
pub struct PreparedModelIrLinearBucklingSpectralV1 {
    pub geometric_assembly: ModelIrLinearBucklingAssembly,
    pub assembly_receipt_json: String,
    pub assembly_hash: String,
    pub generated_request: DenseSpectralAnalysisRequestDocumentV1,
}

impl Runtime {
    /// Generate and prepare the exact reference-static problem bound by a buckling request.
    ///
    /// # Errors
    ///
    /// Returns a stable contract/runtime error for identity drift, unsupported `ModelIR` state,
    /// reference selector failure, or an invalid generated sparse request.
    pub fn prepare_model_ir_linear_buckling_reference(
        &self,
        document: &ModelIrV2Document,
        request: &ModelIrLinearBucklingAnalysisRequestDocumentV1,
    ) -> Result<PreparedModelIrLinearBucklingReferenceV1, RuntimeError> {
        verify_model_identity(document, request)?;
        let generated =
            build_model_ir_linear_analysis_request_v1(ModelIrLinearAnalysisRequestV1 {
                schema_version: MODEL_IR_LINEAR_ANALYSIS_REQUEST_V1.to_owned(),
                operation: "solve_model_ir_linear_static".to_owned(),
                case_id: request.request().case_id.clone(),
                backend: ModelIrLinearBackendV1::Cpu,
                model_identity: request.request().model_identity.clone(),
                load_pattern_id: request.request().reference_load_pattern_id.clone(),
                config: request.request().reference_linear_config,
            })?;
        let product = self.prepare_model_ir_linear_product(document, &generated)?;
        Ok(PreparedModelIrLinearBucklingReferenceV1 {
            request: generated,
            product,
        })
    }

    /// Assemble prestress geometric stiffness at one exact reference equilibrium and adapt the
    /// verified K/Kg pair to the existing dense buckling solver.
    ///
    /// # Errors
    ///
    /// Returns a stable runtime error for non-equilibrium/tension/unsupported states, identity or
    /// topology drift, malformed/asymmetric operators, fallback, bounds, or generated-request
    /// contract failure.
    pub fn prepare_model_ir_linear_buckling_spectral(
        &self,
        document: &ModelIrV2Document,
        request: &ModelIrLinearBucklingAnalysisRequestDocumentV1,
        reference: &PreparedModelIrLinearBucklingReferenceV1,
        equilibrium_displacement: &[f64],
        reference_result_hash: &str,
        reference_recovery_hash: &str,
    ) -> Result<PreparedModelIrLinearBucklingSpectralV1, RuntimeError> {
        verify_model_identity(document, request)?;
        let geometric_assembly = Api::load_model_ir_linear_buckling_assembly()
            .map_err(RuntimeError::from)?
            .create_model_ir(document)
            .map_err(RuntimeError::from)?
            .assemble_linear_buckling_reference(&ModelIrLinearBucklingAssemblyRequest {
                load_pattern_id: request.request().reference_load_pattern_id.clone(),
                equilibrium_displacement: try_clone_slice(
                    equilibrium_displacement,
                    "buckling equilibrium displacement",
                )?,
            })
            .map_err(RuntimeError::from)?;
        verify_joint_assembly(document, request, reference, &geometric_assembly)?;
        let (assembly_receipt_json, assembly_hash) = build_assembly_receipt(
            document,
            request,
            reference,
            &geometric_assembly,
            equilibrium_displacement,
            reference_result_hash,
            reference_recovery_hash,
        )?;
        let order = reference.product.assembly.active_dof_indices.len();
        let stiffness = csr_to_dense(
            &reference.product.assembly.row_offsets,
            &reference.product.assembly.column_indices,
            &reference.product.assembly.tangent,
            order,
            "stiffness",
        )?;
        let geometric = csr_to_dense(
            &geometric_assembly.row_offsets,
            &geometric_assembly.column_indices,
            &geometric_assembly.geometric_stiffness,
            order,
            "geometric stiffness",
        )?;
        let generated_request = build_dense_spectral_request_v1(DenseSpectralAnalysisRequestV1 {
            schema_version: DENSE_SPECTRAL_REQUEST_V1.to_owned(),
            operation: "solve_dense_generalized_eigen".to_owned(),
            case_id: request.request().case_id.clone(),
            analysis_kind: SpectralAnalysisKindV1::LinearBuckling,
            backend: SpectralBackendV1::Cpu,
            order: u32::try_from(order)
                .map_err(|_| product_error("ModelIR buckling order exceeds u32"))?,
            stiffness,
            secondary_matrix: geometric,
            coordinate_recovery_scale: Vec::new(),
            config: request.request().buckling_config,
        })?;
        Ok(PreparedModelIrLinearBucklingSpectralV1 {
            geometric_assembly,
            assembly_receipt_json,
            assembly_hash,
            generated_request,
        })
    }
}

fn verify_joint_assembly(
    document: &ModelIrV2Document,
    request: &ModelIrLinearBucklingAnalysisRequestDocumentV1,
    reference: &PreparedModelIrLinearBucklingReferenceV1,
    geometric: &ModelIrLinearBucklingAssembly,
) -> Result<(), RuntimeError> {
    let elastic = &reference.product.assembly;
    let order = elastic.active_dof_indices.len();
    let valid = (1..=MAXIMUM_BUCKLING_ORDER).contains(&order)
        && request.request().buckling_config.mode_count <= u32::try_from(order).unwrap_or(0)
        && geometric.model_content_hash == document.content_hash()
        && geometric.model_semantic_hash == document.semantic_hash()
        && geometric.model_provenance_hash == document.provenance_hash()
        && geometric.load_pattern_index == elastic.load_pattern_index
        && geometric.global_dof_count == elastic.global_dof_count
        && geometric.active_dof_indices == elastic.active_dof_indices
        && geometric.row_offsets == elastic.row_offsets
        && geometric.column_indices == elastic.column_indices
        && geometric.geometric_stiffness.len() == elastic.tangent.len()
        && geometric.execution_backend == 1
        && geometric.fallback_count == 0
        && geometric.equilibrium_residual_inf_n.is_finite()
        && geometric.equilibrium_residual_inf_n >= 0.0
        && !geometric.frame_stable_indices.is_empty()
        && geometric.frame_stable_indices.len() == geometric.frame_axial_compression_n.len()
        && geometric
            .frame_stable_indices
            .windows(2)
            .all(|window| window[0] < window[1])
        && geometric
            .frame_axial_compression_n
            .iter()
            .all(|value| value.is_finite() && *value >= 0.0)
        && geometric
            .frame_axial_compression_n
            .iter()
            .any(|value| *value > 0.0);
    if valid {
        Ok(())
    } else {
        Err(product_error(
            "ModelIR reference-static and geometric assemblies do not form a bounded K/Kg product",
        ))
    }
}

#[allow(clippy::too_many_arguments)]
fn build_assembly_receipt(
    document: &ModelIrV2Document,
    request: &ModelIrLinearBucklingAnalysisRequestDocumentV1,
    reference: &PreparedModelIrLinearBucklingReferenceV1,
    geometric: &ModelIrLinearBucklingAssembly,
    equilibrium_displacement: &[f64],
    reference_result_hash: &str,
    reference_recovery_hash: &str,
) -> Result<(String, String), RuntimeError> {
    let elastic = &reference.product.assembly;
    let mut value = json!({
        "schema_version": "structural-model-ir-linear-buckling-assembly-receipt.v1",
        "reference_assembly_abi_version": "0x0001000d",
        "geometric_assembly_abi_version": "0x0001000f",
        "buckling_abi_version": "0x00010009",
        "case_id": request.request().case_id,
        "model_id": document.model_id(),
        "model_identity": {
            "content_hash": document.content_hash(),
            "semantic_hash": document.semantic_hash(),
            "provenance_hash": document.provenance_hash()
        },
        "analysis_request_hash": request.request_hash(),
        "generated_reference_request_hash": reference.request.request_hash(),
        "reference_linear_assembly_hash": reference.product.assembly_hash,
        "reference_result_hash": reference_result_hash,
        "reference_recovery_hash": reference_recovery_hash,
        "reference_load_pattern_id": request.request().reference_load_pattern_id,
        "reference_load_pattern_index": elastic.load_pattern_index,
        "global_dof_count": elastic.global_dof_count,
        "active_dof_indices": &elastic.active_dof_indices,
        "active_dof_count": elastic.active_dof_indices.len(),
        "row_offset_count": elastic.row_offsets.len(),
        "structural_entry_count": elastic.tangent.len(),
        "compressed_frame_stable_indices": &geometric.frame_stable_indices,
        "frame_axial_compression_n": &geometric.frame_axial_compression_n,
        "reference_equilibrium_residual_inf_n": geometric.equilibrium_residual_inf_n,
        "array_hashes": {
            "active_dof_indices": hash_u32("active_dof_indices", &elastic.active_dof_indices),
            "row_offsets": hash_u64("row_offsets", &elastic.row_offsets),
            "column_indices": hash_u32("column_indices", &elastic.column_indices),
            "stiffness": hash_f64("stiffness", &elastic.tangent),
            "geometric_stiffness": hash_f64("geometric_stiffness", &geometric.geometric_stiffness),
            "equilibrium_displacement": hash_f64("equilibrium_displacement", equilibrium_displacement),
            "frame_stable_indices": hash_u64("frame_stable_indices", &geometric.frame_stable_indices),
            "frame_axial_compression_n": hash_f64("frame_axial_compression_n", &geometric.frame_axial_compression_n)
        },
        "backend": "cpu",
        "precision": "fp64",
        "fallback_count": 0,
        "claim_boundary": "bounded_frame3d_nodal_reference_load_exact_native_pcg_equilibrium_to_v1_15_k_kg_dense_cpu_linear_buckling_max_128_active_dofs_not_mixed_tension_member_load_self_weight_prescribed_nonzero_shell_sparse_nonlinear_hip_external_validation_or_engineering_acceptance",
        "assembly_hash": ""
    });
    value
        .as_object_mut()
        .and_then(|object| object.remove("assembly_hash"))
        .ok_or_else(|| product_error("ModelIR buckling assembly receipt is not an object"))?;
    let unsigned = canonicalize(&value, "buckling assembly receipt")?;
    let assembly_hash = structural_contracts::product_ir::sha256_identity(unsigned.as_bytes());
    value
        .as_object_mut()
        .ok_or_else(|| product_error("ModelIR buckling assembly receipt is not an object"))?
        .insert(
            "assembly_hash".to_owned(),
            Value::String(assembly_hash.clone()),
        );
    Ok((
        canonicalize(&value, "buckling assembly receipt")?,
        assembly_hash,
    ))
}

fn csr_to_dense(
    row_offsets: &[u64],
    column_indices: &[u32],
    values: &[f64],
    order: usize,
    label: &str,
) -> Result<Vec<f64>, RuntimeError> {
    if !(1..=MAXIMUM_BUCKLING_ORDER).contains(&order)
        || row_offsets.len() != order + 1
        || column_indices.len() != values.len()
        || values.iter().any(|value| !value.is_finite())
    {
        return Err(product_error(&format!(
            "ModelIR buckling {label} CSR shape is invalid"
        )));
    }
    let length = order
        .checked_mul(order)
        .ok_or_else(|| product_error("ModelIR buckling dense length overflowed"))?;
    let mut dense = Vec::new();
    dense
        .try_reserve_exact(length)
        .map_err(|_| allocation_error("dense buckling operator"))?;
    dense.resize(length, 0.0);
    for row in 0..order {
        let begin = usize::try_from(row_offsets[row])
            .map_err(|_| product_error("ModelIR buckling CSR row offset exceeds address space"))?;
        let end = usize::try_from(row_offsets[row + 1])
            .map_err(|_| product_error("ModelIR buckling CSR row offset exceeds address space"))?;
        if begin > end || end > values.len() {
            return Err(product_error(
                "ModelIR buckling CSR row offsets are invalid",
            ));
        }
        let mut previous = None;
        for (&column, &value) in column_indices[begin..end].iter().zip(&values[begin..end]) {
            let column = usize::try_from(column)
                .map_err(|_| product_error("ModelIR buckling CSR column exceeds address space"))?;
            if column >= order || previous.is_some_and(|value| column <= value) {
                return Err(product_error(
                    "ModelIR buckling CSR columns are not strictly ordered and bounded",
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
                    "ModelIR buckling {label} operator is not exactly symmetric"
                )));
            }
        }
    }
    Ok(dense)
}

fn verify_model_identity(
    document: &ModelIrV2Document,
    request: &ModelIrLinearBucklingAnalysisRequestDocumentV1,
) -> Result<(), RuntimeError> {
    let supplied = &request.request().model_identity;
    if supplied.content_hash == document.content_hash()
        && supplied.semantic_hash == document.semantic_hash()
        && supplied.provenance_hash == document.provenance_hash()
    {
        Ok(())
    } else {
        Err(product_error(
            "ModelIR linear-buckling request identity does not match the exact model",
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
    hasher.update(b"structural-model-ir-linear-buckling-array.v1\0");
    hasher.update(label.as_bytes());
    hasher.update([0]);
    hasher.update(u64::try_from(length).unwrap_or(u64::MAX).to_le_bytes());
    update(&mut hasher);
    format!("sha256:{:x}", hasher.finalize())
}

fn canonicalize(value: &Value, label: &str) -> Result<String, RuntimeError> {
    canonicalize_model_ir_v2(value)
        .map_err(|_| product_error(&format!("ModelIR {label} canonicalization failed")))
}

fn try_clone_slice<T: Clone>(values: &[T], label: &str) -> Result<Vec<T>, RuntimeError> {
    let mut output = Vec::new();
    output
        .try_reserve_exact(values.len())
        .map_err(|_| allocation_error(label))?;
    output.extend_from_slice(values);
    Ok(output)
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
        message: format!("allocation failed for {label}"),
    }
}
