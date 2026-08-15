//! Strict result contract for constrained reactions recovered from a linear `ModelIR` state.

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::model_ir::{canonicalize_model_ir_v2, decode_json_strict};
use crate::model_linear_recovery::ModelIrLinearResultRecoveryDocumentV1;
use crate::product_ir::{
    sha256_identity, ModelIrIdentityV1, ProductIrContractError, ResultIdentityV1,
};
use crate::sparse_product::SparseLinearResultIrDocumentV1;

pub const MODEL_IR_LINEAR_REACTION_RESULT_IR_V1: &str =
    "structural-model-ir-linear-reaction-result-ir.v1";
pub const MODEL_IR_LINEAR_MAXIMUM_REACTION_RESULT_BYTES: usize = 128 * 1024 * 1024;

const MAXIMUM_GLOBAL_DOF_COUNT: usize = 1_000_000;
const CLAIM_BOUNDARY: &str = "bounded_typed_modelir_frame3d_truss3d_cpu_constrained_reaction_projection_not_sequential_c2_hip_shell_nonlinear_or_engineering_acceptance";

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ModelIrLinearReactionUnitsV1 {
    pub translational_components: String,
    pub rotational_components: String,
    pub coordinate_frame: String,
}

impl Default for ModelIrLinearReactionUnitsV1 {
    fn default() -> Self {
        Self {
            translational_components: "N".to_owned(),
            rotational_components: "N*m".to_owned(),
            coordinate_frame: "model_global".to_owned(),
        }
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ModelIrLinearReactionCpuReceiptV1 {
    pub backend: String,
    pub precision: String,
    pub abi_version: String,
    pub deterministic_policy: String,
    pub fallback_count: u32,
    pub h2d_bytes: u64,
    pub d2h_bytes: u64,
    pub sync_count: u64,
}

impl Default for ModelIrLinearReactionCpuReceiptV1 {
    fn default() -> Self {
        Self {
            backend: "cpu".to_owned(),
            precision: "fp64".to_owned(),
            abi_version: "0x0001000e".to_owned(),
            deterministic_policy: "stable_element_order_constrained_projection".to_owned(),
            fallback_count: 0,
            h2d_bytes: 0,
            d2h_bytes: 0,
            sync_count: 0,
        }
    }
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ModelIrLinearReactionSummaryV1 {
    pub constrained_dof_count: u64,
    pub maximum_absolute_reaction_component: f64,
    pub component_sums: [f64; 6],
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ModelIrLinearReactionResultIrV1 {
    pub schema_version: String,
    pub case_id: String,
    pub model_id: String,
    pub model_identity: ModelIrIdentityV1,
    pub analysis_request_hash: String,
    pub assembly_hash: String,
    pub source_result_hash: String,
    pub source_recovery_hash: String,
    pub identity: ResultIdentityV1,
    pub load_pattern_id: String,
    pub load_pattern_index: u64,
    pub global_dof_count: u64,
    pub dof_order_per_node: [String; 6],
    pub constrained_dof_indices: Vec<u32>,
    pub constrained_internal_force: Vec<f64>,
    pub constrained_external_load: Vec<f64>,
    pub reactions: Vec<f64>,
    pub summary: ModelIrLinearReactionSummaryV1,
    pub units: ModelIrLinearReactionUnitsV1,
    pub backend_receipt: ModelIrLinearReactionCpuReceiptV1,
    pub claim_boundary: String,
    pub result_hash: String,
}

#[derive(Clone, Debug)]
pub struct ModelIrLinearReactionResultDocumentV1 {
    result: ModelIrLinearReactionResultIrV1,
    canonical_json: String,
}

impl ModelIrLinearReactionResultDocumentV1 {
    #[must_use]
    pub const fn result(&self) -> &ModelIrLinearReactionResultIrV1 {
        &self.result
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
    pub fn result_hash(&self) -> &str {
        &self.result.result_hash
    }
}

/// Native reaction arrays and identities before product-wire publication.
#[derive(Clone, Debug)]
pub struct ModelIrLinearReactionProjectionV1 {
    pub model_identity: ModelIrIdentityV1,
    pub load_pattern_index: u64,
    pub global_dof_count: u64,
    pub constrained_dof_indices: Vec<u32>,
    pub constrained_internal_force: Vec<f64>,
    pub constrained_external_load: Vec<f64>,
    pub reactions: Vec<f64>,
    pub fallback_count: u32,
}

/// Build a self-hashed reaction `ResultIR` bound to the exact sparse result and recovery artifact.
///
/// # Errors
///
/// Rejects native identity, load-case, partition, numerical, source-hash, or checkpoint-identity
/// drift before canonical publication.
pub fn build_model_ir_linear_reaction_result_ir_v1(
    source_result: &SparseLinearResultIrDocumentV1,
    source_recovery: &ModelIrLinearResultRecoveryDocumentV1,
    projection: ModelIrLinearReactionProjectionV1,
) -> Result<ModelIrLinearReactionResultDocumentV1, ProductIrContractError> {
    let recovery = source_recovery.recovery();
    let summary = derive_summary(&projection.constrained_dof_indices, &projection.reactions)?;
    let mut result = ModelIrLinearReactionResultIrV1 {
        schema_version: MODEL_IR_LINEAR_REACTION_RESULT_IR_V1.to_owned(),
        case_id: recovery.case_id.clone(),
        model_id: recovery.model_id.clone(),
        model_identity: projection.model_identity,
        analysis_request_hash: recovery.analysis_request_hash.clone(),
        assembly_hash: recovery.assembly_hash.clone(),
        source_result_hash: source_result.result_hash().to_owned(),
        source_recovery_hash: source_recovery.recovery_hash().to_owned(),
        identity: source_result.result().identity.clone(),
        load_pattern_id: recovery.load_pattern_id.clone(),
        load_pattern_index: projection.load_pattern_index,
        global_dof_count: projection.global_dof_count,
        dof_order_per_node: [
            "UX".to_owned(),
            "UY".to_owned(),
            "UZ".to_owned(),
            "RX".to_owned(),
            "RY".to_owned(),
            "RZ".to_owned(),
        ],
        constrained_dof_indices: projection.constrained_dof_indices,
        constrained_internal_force: projection.constrained_internal_force,
        constrained_external_load: projection.constrained_external_load,
        reactions: projection.reactions,
        summary,
        units: ModelIrLinearReactionUnitsV1::default(),
        backend_receipt: ModelIrLinearReactionCpuReceiptV1 {
            fallback_count: projection.fallback_count,
            ..ModelIrLinearReactionCpuReceiptV1::default()
        },
        claim_boundary: CLAIM_BOUNDARY.to_owned(),
        result_hash: String::new(),
    };
    validate_result(&result)?;
    verify_source_bindings(source_result, source_recovery, &result)?;
    result.result_hash = hash_without_field(&result, "result_hash")?;
    let canonical_json = canonical_struct(&result)?;
    Ok(ModelIrLinearReactionResultDocumentV1 {
        result,
        canonical_json,
    })
}

/// Strictly decode, validate, canonicalize, and self-verify one reaction `ResultIR`.
///
/// # Errors
///
/// Rejects duplicate/unknown fields, noncanonical bytes, invalid dimensions or values, derived
/// summary drift, unsupported execution metadata, and self-hash mismatch.
pub fn parse_model_ir_linear_reaction_result_ir_v1(
    bytes: &[u8],
) -> Result<ModelIrLinearReactionResultDocumentV1, ProductIrContractError> {
    if bytes.is_empty() || bytes.len() > MODEL_IR_LINEAR_MAXIMUM_REACTION_RESULT_BYTES {
        return Err(error(
            "model_ir_linear_reaction_result_size_invalid",
            "/",
            "reaction ResultIR bytes are outside the bounded product domain",
        ));
    }
    let value = decode_json_strict(bytes).map_err(|source| {
        error(
            "model_ir_linear_reaction_result_json_invalid",
            &source.path,
            &source.detail,
        )
    })?;
    let result: ModelIrLinearReactionResultIrV1 =
        serde_json::from_value(value.clone()).map_err(|source| {
            error(
                "model_ir_linear_reaction_result_decode_failed",
                "/",
                &format!("reaction ResultIR has unknown, missing, or mistyped fields: {source}"),
            )
        })?;
    validate_result(&result)?;
    let expected_hash = hash_without_value_field(&value, "result_hash")?;
    if result.result_hash != expected_hash {
        return Err(error(
            "model_ir_linear_reaction_result_hash_mismatch",
            "/result_hash",
            "reaction ResultIR self-hash does not match its canonical payload",
        ));
    }
    let canonical_json = canonicalize_model_ir_v2(&value).map_err(|source| {
        error(
            "model_ir_linear_reaction_result_canonicalization_failed",
            &source.path,
            &source.detail,
        )
    })?;
    if canonical_json.as_bytes() != bytes {
        return Err(error(
            "model_ir_linear_reaction_result_noncanonical",
            "/",
            "reaction ResultIR bytes are not the exact canonical representation",
        ));
    }
    Ok(ModelIrLinearReactionResultDocumentV1 {
        result,
        canonical_json,
    })
}

/// Verify exact sparse-result, recovery, active/constrained partition, and checkpoint bindings.
///
/// # Errors
///
/// Rejects any source hash, model/request/assembly/load identity, terminal checkpoint identity, or
/// complementary DOF-partition drift.
pub fn verify_model_ir_linear_reaction_result_v1(
    source_result: &SparseLinearResultIrDocumentV1,
    source_recovery: &ModelIrLinearResultRecoveryDocumentV1,
    reaction_result: &ModelIrLinearReactionResultDocumentV1,
) -> Result<(), ProductIrContractError> {
    verify_source_bindings(source_result, source_recovery, reaction_result.result())
}

fn verify_source_bindings(
    source_result: &SparseLinearResultIrDocumentV1,
    source_recovery: &ModelIrLinearResultRecoveryDocumentV1,
    result: &ModelIrLinearReactionResultIrV1,
) -> Result<(), ProductIrContractError> {
    let sparse = source_result.result();
    let recovery = source_recovery.recovery();
    let identities_match = result.source_result_hash == source_result.result_hash()
        && result.source_recovery_hash == source_recovery.recovery_hash()
        && result.identity == sparse.identity
        && result.case_id == sparse.case_id
        && result.case_id == recovery.case_id
        && result.model_id == recovery.model_id
        && result.model_identity == recovery.model_identity
        && result.analysis_request_hash == recovery.analysis_request_hash
        && result.assembly_hash == recovery.assembly_hash
        && result.load_pattern_id == recovery.load_pattern_id
        && result.load_pattern_index == u64::from(recovery.load_pattern_index)
        && result.global_dof_count == recovery.global_dof_count;
    if !identities_match {
        return Err(error(
            "model_ir_linear_reaction_result_source_mismatch",
            "/",
            "reaction ResultIR differs from its exact sparse result or recovery source",
        ));
    }
    if !partition_is_complete(
        &recovery.active_dof_indices,
        &result.constrained_dof_indices,
        result.global_dof_count,
    ) {
        return Err(error(
            "model_ir_linear_reaction_result_partition_mismatch",
            "/constrained_dof_indices",
            "active and constrained indices do not form the exact global DOF partition",
        ));
    }
    Ok(())
}

fn validate_result(result: &ModelIrLinearReactionResultIrV1) -> Result<(), ProductIrContractError> {
    if result.schema_version != MODEL_IR_LINEAR_REACTION_RESULT_IR_V1
        || result.claim_boundary != CLAIM_BOUNDARY
        || result.backend_receipt != ModelIrLinearReactionCpuReceiptV1::default()
        || result.units != ModelIrLinearReactionUnitsV1::default()
        || result.dof_order_per_node != ["UX", "UY", "UZ", "RX", "RY", "RZ"]
    {
        return Err(error(
            "model_ir_linear_reaction_result_identity_invalid",
            "/",
            "reaction schema, units, DOF order, execution receipt, or claim boundary is unsupported",
        ));
    }
    validate_identity_fields(result)?;
    validate_dimensions_and_mapping(result)?;
    validate_numerics(result)?;
    let expected_summary = derive_summary(&result.constrained_dof_indices, &result.reactions)?;
    if result.summary.constrained_dof_count != expected_summary.constrained_dof_count
        || result.summary.maximum_absolute_reaction_component.to_bits()
            != expected_summary
                .maximum_absolute_reaction_component
                .to_bits()
        || !bits_equal(
            &result.summary.component_sums,
            &expected_summary.component_sums,
        )
    {
        return Err(error(
            "model_ir_linear_reaction_result_summary_invalid",
            "/summary",
            "reaction summary differs from its exact vector derivation",
        ));
    }
    Ok(())
}

fn validate_identity_fields(
    result: &ModelIrLinearReactionResultIrV1,
) -> Result<(), ProductIrContractError> {
    for (path, id) in [
        ("/case_id", result.case_id.as_str()),
        ("/model_id", result.model_id.as_str()),
        ("/load_pattern_id", result.load_pattern_id.as_str()),
    ] {
        validate_id(id, path)?;
    }
    for (path, hash) in [
        (
            "/model_identity/content_hash",
            result.model_identity.content_hash.as_str(),
        ),
        (
            "/model_identity/semantic_hash",
            result.model_identity.semantic_hash.as_str(),
        ),
        (
            "/model_identity/provenance_hash",
            result.model_identity.provenance_hash.as_str(),
        ),
        (
            "/analysis_request_hash",
            result.analysis_request_hash.as_str(),
        ),
        ("/assembly_hash", result.assembly_hash.as_str()),
        ("/source_result_hash", result.source_result_hash.as_str()),
        (
            "/source_recovery_hash",
            result.source_recovery_hash.as_str(),
        ),
        (
            "/identity/request_hash",
            result.identity.request_hash.as_str(),
        ),
        ("/identity/model_hash", result.identity.model_hash.as_str()),
        ("/identity/state_hash", result.identity.state_hash.as_str()),
        (
            "/identity/execution_hash",
            result.identity.execution_hash.as_str(),
        ),
        (
            "/identity/checkpoint_hash",
            result.identity.checkpoint_hash.as_str(),
        ),
        ("/result_hash", result.result_hash.as_str()),
    ] {
        validate_hash(hash, path, path == "/result_hash")?;
    }
    Ok(())
}

fn validate_dimensions_and_mapping(
    result: &ModelIrLinearReactionResultIrV1,
) -> Result<(), ProductIrContractError> {
    let global_count = usize::try_from(result.global_dof_count).map_err(|_| {
        error(
            "model_ir_linear_reaction_result_global_count_invalid",
            "/global_dof_count",
            "global DOF count exceeds the host representation",
        )
    })?;
    let count = result.constrained_dof_indices.len();
    if global_count == 0
        || global_count > MAXIMUM_GLOBAL_DOF_COUNT
        || global_count % 6 != 0
        || count == 0
        || count >= global_count
        || result.constrained_internal_force.len() != count
        || result.constrained_external_load.len() != count
        || result.reactions.len() != count
        || result.summary.constrained_dof_count != u64::try_from(count).unwrap_or(u64::MAX)
    {
        return Err(error(
            "model_ir_linear_reaction_result_dimension_invalid",
            "/constrained_dof_indices",
            "reaction vector dimensions are inconsistent or outside the bounded domain",
        ));
    }
    let mut previous = None;
    for (position, index) in result.constrained_dof_indices.iter().copied().enumerate() {
        if usize::try_from(index).map_or(true, |index| index >= global_count)
            || previous.is_some_and(|previous| index <= previous)
        {
            return Err(error(
                "model_ir_linear_reaction_result_mapping_invalid",
                &format!("/constrained_dof_indices/{position}"),
                "constrained DOF indices must be strictly increasing and globally bounded",
            ));
        }
        previous = Some(index);
    }
    Ok(())
}

fn validate_numerics(
    result: &ModelIrLinearReactionResultIrV1,
) -> Result<(), ProductIrContractError> {
    if result
        .constrained_internal_force
        .iter()
        .chain(&result.constrained_external_load)
        .chain(&result.reactions)
        .any(|value| !value.is_finite())
    {
        return Err(error(
            "model_ir_linear_reaction_result_nonfinite",
            "/reactions",
            "reaction arrays must contain only finite FP64 values",
        ));
    }
    for (position, ((internal, external), reaction)) in result
        .constrained_internal_force
        .iter()
        .zip(&result.constrained_external_load)
        .zip(&result.reactions)
        .enumerate()
    {
        let derived = normalize_zero(*internal - *external);
        if reaction.to_bits() != derived.to_bits() {
            return Err(error(
                "model_ir_linear_reaction_result_sign_mismatch",
                &format!("/reactions/{position}"),
                "reaction must exactly equal constrained internal minus external load",
            ));
        }
    }
    Ok(())
}

fn derive_summary(
    indices: &[u32],
    reactions: &[f64],
) -> Result<ModelIrLinearReactionSummaryV1, ProductIrContractError> {
    if indices.len() != reactions.len() {
        return Err(error(
            "model_ir_linear_reaction_result_dimension_invalid",
            "/summary",
            "reaction summary inputs have inconsistent lengths",
        ));
    }
    let mut component_sums = [0.0_f64; 6];
    let mut maximum = 0.0_f64;
    for (index, reaction) in indices.iter().zip(reactions) {
        if !reaction.is_finite() {
            return Err(error(
                "model_ir_linear_reaction_result_nonfinite",
                "/reactions",
                "reaction summary inputs must be finite",
            ));
        }
        maximum = maximum.max(reaction.abs());
        let component = usize::try_from(*index).map_err(|_| {
            error(
                "model_ir_linear_reaction_result_mapping_invalid",
                "/constrained_dof_indices",
                "constrained DOF index exceeds the host representation",
            )
        })? % 6;
        component_sums[component] += reaction;
        if !component_sums[component].is_finite() {
            return Err(error(
                "model_ir_linear_reaction_result_summary_invalid",
                "/summary/component_sums",
                "reaction component accumulation exceeds the finite domain",
            ));
        }
    }
    for value in &mut component_sums {
        *value = normalize_zero(*value);
    }
    Ok(ModelIrLinearReactionSummaryV1 {
        constrained_dof_count: u64::try_from(indices.len()).map_err(|_| {
            error(
                "model_ir_linear_reaction_result_dimension_invalid",
                "/summary/constrained_dof_count",
                "constrained DOF count exceeds the wire representation",
            )
        })?,
        maximum_absolute_reaction_component: normalize_zero(maximum),
        component_sums,
    })
}

fn partition_is_complete(active: &[u32], constrained: &[u32], global_count: u64) -> bool {
    let Ok(global_count) = usize::try_from(global_count) else {
        return false;
    };
    if active.len().checked_add(constrained.len()) != Some(global_count) {
        return false;
    }
    let mut active_cursor = 0_usize;
    let mut constrained_cursor = 0_usize;
    for expected in 0..global_count {
        let Ok(expected) = u32::try_from(expected) else {
            return false;
        };
        if active.get(active_cursor) == Some(&expected) {
            active_cursor += 1;
        } else if constrained.get(constrained_cursor) == Some(&expected) {
            constrained_cursor += 1;
        } else {
            return false;
        }
    }
    active_cursor == active.len() && constrained_cursor == constrained.len()
}

fn normalize_zero(value: f64) -> f64 {
    if value == 0.0 {
        0.0
    } else {
        value
    }
}

fn bits_equal<const N: usize>(left: &[f64; N], right: &[f64; N]) -> bool {
    left.iter()
        .zip(right)
        .all(|(left, right)| left.to_bits() == right.to_bits())
}

fn canonical_struct(
    value: &ModelIrLinearReactionResultIrV1,
) -> Result<String, ProductIrContractError> {
    let value = serde_json::to_value(value).map_err(|_| {
        error(
            "model_ir_linear_reaction_result_canonicalization_failed",
            "/",
            "typed reaction ResultIR cannot be represented as JSON",
        )
    })?;
    canonicalize_model_ir_v2(&value).map_err(|source| {
        error(
            "model_ir_linear_reaction_result_canonicalization_failed",
            &source.path,
            &source.detail,
        )
    })
}

fn hash_without_field(
    value: &ModelIrLinearReactionResultIrV1,
    field: &str,
) -> Result<String, ProductIrContractError> {
    let value = serde_json::to_value(value).map_err(|_| {
        error(
            "model_ir_linear_reaction_result_hash_failed",
            "/",
            "typed reaction ResultIR cannot be represented as JSON",
        )
    })?;
    hash_without_value_field(&value, field)
}

fn hash_without_value_field(value: &Value, field: &str) -> Result<String, ProductIrContractError> {
    let mut unsigned = value.clone();
    unsigned
        .as_object_mut()
        .and_then(|object| object.remove(field))
        .ok_or_else(|| {
            error(
                "model_ir_linear_reaction_result_hash_missing",
                &format!("/{field}"),
                "reaction ResultIR has no self-hash field",
            )
        })?;
    let canonical = canonicalize_model_ir_v2(&unsigned).map_err(|source| {
        error(
            "model_ir_linear_reaction_result_hash_failed",
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
            "model_ir_linear_reaction_result_identifier_invalid",
            path,
            "identifier must be 1..128 portable bytes and begin with an alphanumeric byte",
        ))
    }
}

fn validate_hash(value: &str, path: &str, allow_empty: bool) -> Result<(), ProductIrContractError> {
    if allow_empty && value.is_empty() {
        return Ok(());
    }
    let digest = value.strip_prefix("sha256:").unwrap_or_default();
    if digest.len() == 64
        && digest
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        Ok(())
    } else {
        Err(error(
            "model_ir_linear_reaction_result_hash_invalid",
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

#[cfg(test)]
mod tests {
    use super::{derive_summary, partition_is_complete};

    #[test]
    fn partition_and_component_summary_are_exact_and_ordered() {
        assert!(partition_is_complete(&[1, 3, 5], &[0, 2, 4], 6));
        assert!(!partition_is_complete(&[1, 3], &[0, 2, 4], 6));
        assert!(!partition_is_complete(&[1, 3, 5], &[0, 3, 4], 6));

        let summary = derive_summary(&[0, 6, 11], &[-4.0, 1.5, 2.0]).expect("summary");
        assert_eq!(summary.constrained_dof_count, 3);
        assert_eq!(
            summary.maximum_absolute_reaction_component.to_bits(),
            4.0_f64.to_bits()
        );
        assert_eq!(summary.component_sums[0].to_bits(), (-2.5_f64).to_bits());
        assert_eq!(summary.component_sums[5].to_bits(), 2.0_f64.to_bits());
    }
}
