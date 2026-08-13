//! Strict typed contract for recovered `ModelIR` linear-static results.

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::model_ir::{canonicalize_model_ir_v2, decode_json_strict};
use crate::model_linear_product::MODEL_IR_LINEAR_MAXIMUM_RECOVERY_RECORDS;
use crate::product_ir::{sha256_identity, ModelIrIdentityV1, ProductIrContractError};
use crate::sparse_product::{SparseLinearResultIrDocumentV1, SPARSE_LINEAR_MAXIMUM_ORDER};

pub const MODEL_IR_LINEAR_RESULT_RECOVERY_IR_V1: &str =
    "structural-model-ir-linear-result-recovery-ir.v1";
pub const MODEL_IR_LINEAR_MAXIMUM_RECOVERY_BYTES: usize = 256 * 1024 * 1024;

const MAXIMUM_GLOBAL_DOF_COUNT: usize = 1_000_000;
const MAXIMUM_RECOVERY_VALUES_PER_RECORD: usize = 64;
const CLAIM_BOUNDARY: &str = "bounded_active_dof_and_element_recovery_not_constrained_reactions_shell_nonlinear_hip_or_engineering_acceptance";

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ModelIrLinearRecoveryUnitsV1 {
    pub global_displacement: String,
    pub active_force: String,
    pub frame3d_recovery: String,
    pub truss3d_recovery: [String; 3],
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ModelIrLinearRecoveryCoordinateFrameV1 {
    pub global_displacement_and_active_force: String,
    pub frame3d_recovery: String,
    pub truss3d_recovery: String,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ModelIrLinearRecoverySummaryV1 {
    pub maximum_absolute_displacement: f64,
    pub active_residual_inf: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ModelIrLinearResultRecoveryIrV1 {
    pub schema_version: String,
    pub case_id: String,
    pub model_id: String,
    pub model_identity: ModelIrIdentityV1,
    pub analysis_request_hash: String,
    pub assembly_hash: String,
    pub source_result_hash: String,
    pub load_pattern_id: String,
    pub load_pattern_index: u32,
    pub global_dof_count: u64,
    pub dof_order_per_node: [String; 6],
    pub active_dof_indices: Vec<u32>,
    pub global_displacement: Vec<f64>,
    pub active_internal_force: Vec<f64>,
    pub active_external_load: Vec<f64>,
    pub active_equilibrium_residual: Vec<f64>,
    pub same_state_jvp: Vec<f64>,
    pub recovery_stable_indices: Vec<u32>,
    pub recovery_element_types: Vec<u32>,
    pub recovery_offsets: Vec<u64>,
    pub recovery_values: Vec<f64>,
    pub summary: ModelIrLinearRecoverySummaryV1,
    pub units: ModelIrLinearRecoveryUnitsV1,
    pub coordinate_frame: ModelIrLinearRecoveryCoordinateFrameV1,
    pub backend: String,
    pub precision: String,
    pub fallback_count: u32,
    pub claim_boundary: String,
    pub recovery_hash: String,
}

#[derive(Clone, Debug)]
pub struct ModelIrLinearResultRecoveryDocumentV1 {
    recovery: ModelIrLinearResultRecoveryIrV1,
    canonical_json: String,
}

impl ModelIrLinearResultRecoveryDocumentV1 {
    #[must_use]
    pub const fn recovery(&self) -> &ModelIrLinearResultRecoveryIrV1 {
        &self.recovery
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
    pub fn recovery_hash(&self) -> &str {
        &self.recovery.recovery_hash
    }
}

/// Strictly decode, validate, canonicalize, and verify one recovered linear result.
///
/// # Errors
///
/// Rejects duplicate/unknown fields, noncanonical bytes, malformed bindings, inconsistent
/// dimensions, non-finite values, derived-summary drift, and self-hash mismatch.
pub fn parse_model_ir_linear_result_recovery_ir_v1(
    bytes: &[u8],
) -> Result<ModelIrLinearResultRecoveryDocumentV1, ProductIrContractError> {
    if bytes.is_empty() || bytes.len() > MODEL_IR_LINEAR_MAXIMUM_RECOVERY_BYTES {
        return Err(error(
            "model_ir_linear_recovery_size_invalid",
            "/",
            "recovery IR bytes are outside the bounded product domain",
        ));
    }
    let value = decode_json_strict(bytes).map_err(|source| {
        error(
            "model_ir_linear_recovery_json_invalid",
            &source.path,
            &source.detail,
        )
    })?;
    let recovery: ModelIrLinearResultRecoveryIrV1 =
        serde_json::from_value(value.clone()).map_err(|source| {
            error(
                "model_ir_linear_recovery_decode_failed",
                "/",
                &format!("recovery IR has unknown, missing, or mistyped fields: {source}"),
            )
        })?;
    validate_recovery(&recovery)?;
    let expected_hash = hash_without_field(&value, "recovery_hash")?;
    if recovery.recovery_hash != expected_hash {
        return Err(error(
            "model_ir_linear_recovery_hash_mismatch",
            "/recovery_hash",
            "recovery IR self-hash does not match its canonical payload",
        ));
    }
    let canonical_json = canonicalize_model_ir_v2(&value).map_err(|source| {
        error(
            "model_ir_linear_recovery_canonicalization_failed",
            &source.path,
            &source.detail,
        )
    })?;
    if canonical_json.as_bytes() != bytes {
        return Err(error(
            "model_ir_linear_recovery_noncanonical",
            "/",
            "recovery IR bytes are not the exact canonical representation",
        ));
    }
    Ok(ModelIrLinearResultRecoveryDocumentV1 {
        recovery,
        canonical_json,
    })
}

/// Verify one typed recovery against the exact sparse `ResultIR` it claims to project.
///
/// # Errors
///
/// Rejects source hash/case/order drift, a non-bitwise active solution mapping, or residual-summary
/// drift outside the sparse product's bounded FP64 parity tolerance. This check deliberately
/// supplements the recovery's standalone exact structural self-check.
pub fn verify_model_ir_linear_result_recovery_v1(
    result: &SparseLinearResultIrDocumentV1,
    recovery: &ModelIrLinearResultRecoveryDocumentV1,
) -> Result<(), ProductIrContractError> {
    let source = result.result();
    let recovered = recovery.recovery();
    if recovered.source_result_hash != result.result_hash() || recovered.case_id != source.case_id {
        return Err(error(
            "model_ir_linear_recovery_result_binding_mismatch",
            "/source_result_hash",
            "recovery source hash or case differs from the exact sparse ResultIR",
        ));
    }
    if recovered.active_dof_indices.len() != source.solution.len()
        || usize::try_from(source.summary.order).ok() != Some(source.solution.len())
        || recovered
            .active_dof_indices
            .iter()
            .zip(&source.solution)
            .any(|(global_index, solution)| {
                usize::try_from(*global_index)
                    .ok()
                    .and_then(|index| recovered.global_displacement.get(index))
                    .map_or(true, |value| value.to_bits() != solution.to_bits())
            })
    {
        return Err(error(
            "model_ir_linear_recovery_solution_mismatch",
            "/global_displacement",
            "recovered active global displacement does not exactly reproduce the sparse solution",
        ));
    }
    if !recovery_residual_metrics_close(
        recovered.summary.active_residual_inf,
        source.summary.final_residual_inf,
        recovered,
    ) {
        return Err(error(
            "model_ir_linear_recovery_residual_mismatch",
            "/summary/active_residual_inf",
            "recovery residual summary differs from the sparse ResultIR outside the bounded FP64 parity tolerance",
        ));
    }
    Ok(())
}

fn recovery_residual_metrics_close(
    recovered_residual: f64,
    sparse_residual: f64,
    recovery: &ModelIrLinearResultRecoveryIrV1,
) -> bool {
    let force_scale = recovery
        .active_internal_force
        .iter()
        .chain(&recovery.active_external_load)
        .map(|value| value.abs())
        .fold(1.0_f64, f64::max);
    let metric_scale = recovered_residual.abs().max(sparse_residual.abs()).max(1.0);
    let tolerance = 1.0e-12 * metric_scale + 64.0 * f64::EPSILON * force_scale;
    (recovered_residual - sparse_residual).abs() <= tolerance
}

fn validate_recovery(
    recovery: &ModelIrLinearResultRecoveryIrV1,
) -> Result<(), ProductIrContractError> {
    validate_recovery_identity(recovery)?;
    validate_units_and_frames(recovery)?;

    let global_dof_count = usize::try_from(recovery.global_dof_count).map_err(|_| {
        error(
            "model_ir_linear_recovery_global_dof_count_invalid",
            "/global_dof_count",
            "global DOF count does not fit the bounded host representation",
        )
    })?;
    if global_dof_count == 0
        || global_dof_count > MAXIMUM_GLOBAL_DOF_COUNT
        || global_dof_count % 6 != 0
        || recovery.global_displacement.len() != global_dof_count
    {
        return Err(error(
            "model_ir_linear_recovery_global_dof_count_invalid",
            "/global_dof_count",
            "global DOF count and displacement length are inconsistent or out of bounds",
        ));
    }
    validate_active_vectors(recovery, global_dof_count)?;
    validate_element_recovery(recovery)?;
    validate_summary(recovery)
}

fn validate_recovery_identity(
    recovery: &ModelIrLinearResultRecoveryIrV1,
) -> Result<(), ProductIrContractError> {
    if recovery.schema_version != MODEL_IR_LINEAR_RESULT_RECOVERY_IR_V1
        || recovery.claim_boundary != CLAIM_BOUNDARY
        || recovery.backend != "cpu"
        || recovery.precision != "fp64"
        || recovery.fallback_count != 0
    {
        return Err(error(
            "model_ir_linear_recovery_identity_invalid",
            "/",
            "recovery schema, backend, precision, fallback, or claim boundary is unsupported",
        ));
    }
    validate_id(&recovery.case_id, "/case_id")?;
    validate_id(&recovery.model_id, "/model_id")?;
    validate_id(&recovery.load_pattern_id, "/load_pattern_id")?;
    for (path, hash) in [
        (
            "/model_identity/content_hash",
            recovery.model_identity.content_hash.as_str(),
        ),
        (
            "/model_identity/semantic_hash",
            recovery.model_identity.semantic_hash.as_str(),
        ),
        (
            "/model_identity/provenance_hash",
            recovery.model_identity.provenance_hash.as_str(),
        ),
        (
            "/analysis_request_hash",
            recovery.analysis_request_hash.as_str(),
        ),
        ("/assembly_hash", recovery.assembly_hash.as_str()),
        ("/source_result_hash", recovery.source_result_hash.as_str()),
        ("/recovery_hash", recovery.recovery_hash.as_str()),
    ] {
        validate_hash(hash, path)?;
    }
    if recovery.dof_order_per_node != ["UX", "UY", "UZ", "RX", "RY", "RZ"] {
        return Err(error(
            "model_ir_linear_recovery_dof_order_invalid",
            "/dof_order_per_node",
            "recovery DOF order must be the fixed six-DOF node order",
        ));
    }
    Ok(())
}

fn validate_active_vectors(
    recovery: &ModelIrLinearResultRecoveryIrV1,
    global_dof_count: usize,
) -> Result<(), ProductIrContractError> {
    let active_count = recovery.active_dof_indices.len();
    if active_count == 0
        || active_count > SPARSE_LINEAR_MAXIMUM_ORDER as usize
        || recovery.active_internal_force.len() != active_count
        || recovery.active_external_load.len() != active_count
        || recovery.active_equilibrium_residual.len() != active_count
        || recovery.same_state_jvp.len() != active_count
    {
        return Err(error(
            "model_ir_linear_recovery_active_dimension_invalid",
            "/active_dof_indices",
            "active DOF and vector dimensions are inconsistent or out of bounds",
        ));
    }
    let mut previous = None;
    for (index, value) in recovery.active_dof_indices.iter().copied().enumerate() {
        if usize::try_from(value).map_or(true, |value| value >= global_dof_count)
            || previous.is_some_and(|previous| value <= previous)
        {
            return Err(error(
                "model_ir_linear_recovery_active_mapping_invalid",
                &format!("/active_dof_indices/{index}"),
                "active DOF indices must be unique, strictly increasing, and globally bounded",
            ));
        }
        previous = Some(value);
    }
    validate_finite_slice(&recovery.global_displacement, "/global_displacement")?;
    let mut active_cursor = 0_usize;
    for (global_index, value) in recovery.global_displacement.iter().enumerate() {
        if recovery
            .active_dof_indices
            .get(active_cursor)
            .and_then(|value| usize::try_from(*value).ok())
            == Some(global_index)
        {
            active_cursor += 1;
        } else if value.to_bits() != 0.0_f64.to_bits() {
            return Err(error(
                "model_ir_linear_recovery_inactive_displacement_nonzero",
                &format!("/global_displacement/{global_index}"),
                "inactive or constrained global DOFs must retain canonical positive zero",
            ));
        }
    }
    validate_finite_slice(&recovery.active_internal_force, "/active_internal_force")?;
    validate_finite_slice(&recovery.active_external_load, "/active_external_load")?;
    validate_finite_slice(
        &recovery.active_equilibrium_residual,
        "/active_equilibrium_residual",
    )?;
    validate_finite_slice(&recovery.same_state_jvp, "/same_state_jvp")?;
    if !bits_equal(&recovery.active_internal_force, &recovery.same_state_jvp) {
        return Err(error(
            "model_ir_linear_recovery_jvp_mismatch",
            "/same_state_jvp",
            "same-state JVP must exactly match the recovered linear internal force",
        ));
    }
    for (index, ((internal, external), residual)) in recovery
        .active_internal_force
        .iter()
        .zip(&recovery.active_external_load)
        .zip(&recovery.active_equilibrium_residual)
        .enumerate()
    {
        let derived = internal - external;
        let derived = if derived == 0.0 { 0.0 } else { derived };
        if residual.to_bits() != derived.to_bits() {
            return Err(error(
                "model_ir_linear_recovery_equilibrium_mismatch",
                &format!("/active_equilibrium_residual/{index}"),
                "equilibrium residual must exactly equal recovered internal minus external force",
            ));
        }
    }
    Ok(())
}

fn validate_units_and_frames(
    recovery: &ModelIrLinearResultRecoveryIrV1,
) -> Result<(), ProductIrContractError> {
    let units = &recovery.units;
    let frames = &recovery.coordinate_frame;
    if units.global_displacement != "translations_m_rotations_rad"
        || units.active_force != "forces_n_moments_n_m"
        || units.frame3d_recovery != "local_end_forces_n_and_moments_n_m"
        || units.truss3d_recovery != ["axial_strain_1", "axial_stress_pa", "axial_force_n"]
        || frames.global_displacement_and_active_force != "model_global"
        || frames.frame3d_recovery != "element_local"
        || frames.truss3d_recovery != "element_axis"
    {
        return Err(error(
            "model_ir_linear_recovery_units_invalid",
            "/units",
            "recovery units or coordinate frames differ from the fixed SI contract",
        ));
    }
    Ok(())
}

fn validate_element_recovery(
    recovery: &ModelIrLinearResultRecoveryIrV1,
) -> Result<(), ProductIrContractError> {
    let count = recovery.recovery_stable_indices.len();
    if count == 0
        || count > MODEL_IR_LINEAR_MAXIMUM_RECOVERY_RECORDS
        || recovery.recovery_element_types.len() != count
        || recovery.recovery_offsets.len() != count.saturating_add(1)
        || recovery.recovery_offsets.first().copied() != Some(0)
    {
        return Err(error(
            "model_ir_linear_recovery_record_dimension_invalid",
            "/recovery_offsets",
            "element recovery record dimensions are inconsistent or out of bounds",
        ));
    }
    let maximum_values = count
        .checked_mul(MAXIMUM_RECOVERY_VALUES_PER_RECORD)
        .ok_or_else(|| {
            error(
                "model_ir_linear_recovery_record_dimension_invalid",
                "/recovery_values",
                "element recovery value bound overflowed",
            )
        })?;
    if recovery.recovery_values.len() > maximum_values {
        return Err(error(
            "model_ir_linear_recovery_record_dimension_invalid",
            "/recovery_values",
            "element recovery values exceed the bounded per-record domain",
        ));
    }
    let expected_last = u64::try_from(recovery.recovery_values.len()).map_err(|_| {
        error(
            "model_ir_linear_recovery_record_dimension_invalid",
            "/recovery_values",
            "element recovery value length does not fit the wire contract",
        )
    })?;
    if recovery.recovery_offsets.last().copied() != Some(expected_last)
        || recovery
            .recovery_offsets
            .windows(2)
            .any(|window| window[0] > window[1])
    {
        return Err(error(
            "model_ir_linear_recovery_offsets_invalid",
            "/recovery_offsets",
            "element recovery offsets must be monotonic and terminate at the value length",
        ));
    }
    let mut previous_stable_index = None;
    for (index, (stable_index, element_type)) in recovery
        .recovery_stable_indices
        .iter()
        .zip(&recovery.recovery_element_types)
        .enumerate()
    {
        let expected_values = match *element_type {
            1 => 12_u64,
            2 => 3_u64,
            _ => 0_u64,
        };
        let actual_values = recovery.recovery_offsets[index + 1]
            .checked_sub(recovery.recovery_offsets[index])
            .unwrap_or(u64::MAX);
        if previous_stable_index.is_some_and(|previous| *stable_index <= previous)
            || expected_values == 0
            || actual_values != expected_values
        {
            return Err(error(
                "model_ir_linear_recovery_record_invalid",
                &format!("/recovery_stable_indices/{index}"),
                "element recovery records require strictly increasing indices, supported type codes, and exact value counts",
            ));
        }
        previous_stable_index = Some(*stable_index);
    }
    validate_finite_slice(&recovery.recovery_values, "/recovery_values")
}

fn validate_summary(
    recovery: &ModelIrLinearResultRecoveryIrV1,
) -> Result<(), ProductIrContractError> {
    let maximum_absolute_displacement = recovery
        .global_displacement
        .iter()
        .map(|value| value.abs())
        .fold(0.0_f64, f64::max);
    let active_residual_inf = recovery
        .active_equilibrium_residual
        .iter()
        .map(|value| value.abs())
        .fold(0.0_f64, f64::max);
    if !recovery.summary.maximum_absolute_displacement.is_finite()
        || !recovery.summary.active_residual_inf.is_finite()
        || recovery.summary.maximum_absolute_displacement.to_bits()
            != maximum_absolute_displacement.to_bits()
        || recovery.summary.active_residual_inf.to_bits() != active_residual_inf.to_bits()
    {
        return Err(error(
            "model_ir_linear_recovery_summary_invalid",
            "/summary",
            "recovery summary is non-finite or differs from its exact vector derivation",
        ));
    }
    Ok(())
}

fn validate_finite_slice(values: &[f64], path: &str) -> Result<(), ProductIrContractError> {
    if values.iter().all(|value| value.is_finite()) {
        Ok(())
    } else {
        Err(error(
            "model_ir_linear_recovery_non_finite",
            path,
            "recovery numeric arrays must contain only finite FP64 values",
        ))
    }
}

fn bits_equal(left: &[f64], right: &[f64]) -> bool {
    left.len() == right.len()
        && left
            .iter()
            .zip(right)
            .all(|(left, right)| left.to_bits() == right.to_bits())
}

fn hash_without_field(value: &Value, field: &str) -> Result<String, ProductIrContractError> {
    let mut unsigned = value.clone();
    unsigned
        .as_object_mut()
        .and_then(|object| object.remove(field))
        .ok_or_else(|| {
            error(
                "model_ir_linear_recovery_hash_missing",
                &format!("/{field}"),
                "recovery IR has no self-hash field",
            )
        })?;
    let canonical = canonicalize_model_ir_v2(&unsigned).map_err(|source| {
        error(
            "model_ir_linear_recovery_canonicalization_failed",
            &source.path,
            &source.detail,
        )
    })?;
    Ok(sha256_identity(canonical.as_bytes()))
}

fn validate_id(value: &str, path: &str) -> Result<(), ProductIrContractError> {
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
            "model_ir_linear_recovery_identifier_invalid",
            path,
            "identifier must be 1..128 portable bytes and begin with an alphanumeric byte",
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
            "model_ir_linear_recovery_hash_invalid",
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
