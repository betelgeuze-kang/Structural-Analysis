//! Strict bounded native linear `Frame3D` `ResultIR` wire contract.

use std::collections::BTreeSet;
use std::fmt;
use std::sync::OnceLock;

use jsonschema::{Draft, JSONSchema};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};

use crate::model_ir::{canonicalize_model_ir_v2, decode_json_strict};
use crate::FRAME3D_RESULT_IR_SCHEMA_V1;

const SCHEMA_TEXT: &str = include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/schemas/linear_frame3d_result_ir_v1.schema.json"
));
const HASH_PREFIX: &str = "sha256:";
const HASH_LENGTH: usize = 71;

static SCHEMA_VALIDATOR: OnceLock<Result<JSONSchema, String>> = OnceLock::new();

/// Stable contract failure for bounded native `ResultIR` construction or decoding.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Frame3dResultIrError {
    pub code: String,
    pub path: String,
    pub detail: String,
}

impl fmt::Display for Frame3dResultIrError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{} at {}: {}", self.code, self.path, self.detail)
    }
}

impl std::error::Error for Frame3dResultIrError {}

/// Model, load and native implementation identity bound into one `ResultIR`.
#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct Frame3dResultBindingsV1 {
    pub model_id: String,
    pub model_content_hash: String,
    pub model_semantic_hash: String,
    pub model_provenance_hash: String,
    pub load_pattern_id: String,
    pub native_abi_version: u32,
}

/// Solver profile that produced the bounded result.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct Frame3dResultSolverV1 {
    pub formulation: String,
    pub backend: String,
    pub residual_sign: String,
    pub unit_profile: String,
}

/// Independently observable gates required before `ResultIR` construction.
#[allow(clippy::struct_excessive_bools)]
#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct Frame3dResultGatesV1 {
    pub native_residual_gate_passed: bool,
    pub free_residual_scaled_linf: f64,
    pub free_residual_scaled_linf_tolerance: f64,
    pub global_force_balance_scaled_linf: f64,
    pub global_force_balance_scaled_linf_tolerance: f64,
    pub global_moment_balance_scaled_linf: f64,
    pub global_moment_balance_scaled_linf_tolerance: f64,
    pub global_resultant_gate_passed: bool,
    pub independent_recovery_replay_passed: bool,
    pub member_force_replay_scaled_linf: f64,
    pub member_force_replay_scaled_linf_tolerance: f64,
    pub zero_prescribed_displacement_gate_passed: bool,
    pub fallback_count: u32,
    pub regularization_count: u32,
}

/// One node row in canonical UX/UY/UZ/RX/RY/RZ order.
#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct Frame3dResultNodeV1 {
    pub node_id: String,
    pub displacement_m_rad: [f64; 6],
    pub reaction_n_nm: [f64; 6],
}

/// One member row in local N/Vy/Vz/T/My/Mz order at i then j.
#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct Frame3dResultMemberV1 {
    pub member_id: String,
    pub end_i_force_n_nm: [f64; 6],
    pub end_j_force_n_nm: [f64; 6],
}

/// Explicit authority axes; the bounded result cannot grant design or release authority.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct Frame3dResultAuthorityV1 {
    pub numerical_state: String,
    pub convergence: String,
    pub displacement: String,
    pub reaction: String,
    pub member_force: String,
    pub engineering_design: String,
    pub code_compliance: String,
    pub release_readiness: String,
    pub commercial_use: String,
}

/// Machine-readable boundary preventing promotion beyond the verified alpha domain.
#[allow(clippy::struct_excessive_bools)]
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct Frame3dResultClaimBoundaryV1 {
    pub bounded_linear_static_timoshenko_frame3d: bool,
    pub cpu_only: bool,
    pub zero_prescribed_displacement_only: bool,
    pub nodal_load_only: bool,
    pub uniform_member_load_initial_local: bool,
    pub self_weight_standard_gravity: bool,
    pub member_end_rotational_release: bool,
    pub rigid_member_end_offset: bool,
    pub reaction_from_global_residual: bool,
    pub member_force_from_native_local_recovery: bool,
    pub independent_recovery_replay: bool,
    pub cpu_hip_parity_established: bool,
    pub external_validation_established: bool,
    pub workbench_e2e: bool,
    pub release_readiness: bool,
    pub commercial_claim: bool,
}

/// Versioned, hash-bound bounded native `ResultIR`.
#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct LinearFrame3dResultIrV1 {
    pub schema_version: String,
    pub result_id: String,
    pub result_hash: String,
    pub result_kind: String,
    pub authority_profile: String,
    pub promotion_basis: String,
    pub bindings: Frame3dResultBindingsV1,
    pub solver: Frame3dResultSolverV1,
    pub gates: Frame3dResultGatesV1,
    pub nodes: Vec<Frame3dResultNodeV1>,
    pub members: Vec<Frame3dResultMemberV1>,
    pub authority: Frame3dResultAuthorityV1,
    pub claim_boundary: Frame3dResultClaimBoundaryV1,
}

impl LinearFrame3dResultIrV1 {
    /// Render compact sorted canonical JSON including the verified result hash.
    ///
    /// # Errors
    ///
    /// Returns a stable error if serialization or canonical number encoding fails.
    pub fn canonical_json(&self) -> Result<String, Frame3dResultIrError> {
        let value = serde_json::to_value(self).map_err(|_| {
            error(
                "frame3d_result_ir_serialization_failed",
                "/",
                "ResultIR could not be represented as JSON",
            )
        })?;
        canonicalize(&value)
    }
}

/// Checked input used to construct a bounded `ResultIR` after native solve and replay gates.
pub struct LinearFrame3dResultIrInput {
    pub result_id: String,
    pub bindings: Frame3dResultBindingsV1,
    pub gates: Frame3dResultGatesV1,
    pub nodes: Vec<Frame3dResultNodeV1>,
    pub members: Vec<Frame3dResultMemberV1>,
}

/// Construct and self-validate a bounded native `ResultIR`.
///
/// # Errors
///
/// Fails closed for invalid identities, shapes, non-finite values, duplicate entity IDs,
/// failed numerical/equilibrium gates, fallbacks, regularization or hash instability.
pub fn create_linear_frame3d_result_ir_v1(
    input: LinearFrame3dResultIrInput,
) -> Result<LinearFrame3dResultIrV1, Frame3dResultIrError> {
    let mut result = LinearFrame3dResultIrV1 {
        schema_version: FRAME3D_RESULT_IR_SCHEMA_V1.to_owned(),
        result_id: input.result_id,
        result_hash: format!("{HASH_PREFIX}{}", "0".repeat(64)),
        result_kind: "linear_static_frame3d".to_owned(),
        authority_profile: "bounded_native_cpu_result_candidate.v1".to_owned(),
        promotion_basis:
            "native_residual_free_residual_global_resultant_and_independent_recovery_gates.v1"
                .to_owned(),
        bindings: input.bindings,
        solver: Frame3dResultSolverV1 {
            formulation: "linear_timoshenko_frame3d".to_owned(),
            backend: "cpu_reference_dense".to_owned(),
            residual_sign: "internal_minus_external".to_owned(),
            unit_profile: "node_m_rad_force_n_nm_member_local_n_nm.v1".to_owned(),
        },
        gates: input.gates,
        nodes: input.nodes,
        members: input.members,
        authority: candidate_authority(),
        claim_boundary: claim_boundary(),
    };
    validate_content(&result)?;
    result.result_hash = result_hash(&result)?;
    validate_linear_frame3d_result_ir_v1(&result)?;
    Ok(result)
}

/// Strictly decode, schema-check and hash-check a bounded native `ResultIR`.
///
/// # Errors
///
/// Rejects invalid UTF-8/JSON, duplicate keys, schema violations, non-finite typed values,
/// stale hashes and any authority or claim-boundary mutation.
pub fn parse_linear_frame3d_result_ir_v1(
    bytes: &[u8],
) -> Result<LinearFrame3dResultIrV1, Frame3dResultIrError> {
    let value = decode_json_strict(bytes).map_err(|source| {
        error(
            "frame3d_result_ir_json_invalid",
            &source.path,
            &source.detail,
        )
    })?;
    validate_schema(&value)?;
    let result: LinearFrame3dResultIrV1 = serde_json::from_value(value).map_err(|_| {
        error(
            "frame3d_result_ir_decode_failed",
            "/",
            "ResultIR JSON could not be decoded into the typed contract",
        )
    })?;
    validate_linear_frame3d_result_ir_v1(&result)?;
    Ok(result)
}

/// Validate all fixed profiles, numerical domains, authority axes and the result hash.
///
/// # Errors
///
/// Returns a stable contract error for the first invalid boundary.
pub fn validate_linear_frame3d_result_ir_v1(
    result: &LinearFrame3dResultIrV1,
) -> Result<(), Frame3dResultIrError> {
    let value = serde_json::to_value(result).map_err(|_| {
        error(
            "frame3d_result_ir_serialization_failed",
            "/",
            "ResultIR could not be represented as JSON",
        )
    })?;
    validate_schema(&value)?;
    validate_content(result)?;
    let expected = result_hash(result)?;
    if result.result_hash != expected {
        return Err(error(
            "frame3d_result_ir_hash_mismatch",
            "/result_hash",
            "ResultIR hash does not match its canonical payload",
        ));
    }
    Ok(())
}

fn validate_content(result: &LinearFrame3dResultIrV1) -> Result<(), Frame3dResultIrError> {
    require_stable_id(&result.result_id, "/result_id")?;
    require_stable_id(&result.bindings.model_id, "/bindings/model_id")?;
    require_stable_id(
        &result.bindings.load_pattern_id,
        "/bindings/load_pattern_id",
    )?;
    for (path, hash) in [
        (
            "/bindings/model_content_hash",
            &result.bindings.model_content_hash,
        ),
        (
            "/bindings/model_semantic_hash",
            &result.bindings.model_semantic_hash,
        ),
        (
            "/bindings/model_provenance_hash",
            &result.bindings.model_provenance_hash,
        ),
    ] {
        require_hash(hash, path)?;
    }
    require_hash(&result.result_hash, "/result_hash")?;
    if result.bindings.native_abi_version != 0x0001_0005 {
        return Err(error(
            "frame3d_result_ir_abi_invalid",
            "/bindings/native_abi_version",
            "Bounded native ResultIR requires ABI v1.5",
        ));
    }
    if !(2..=16).contains(&result.nodes.len()) || !(1..=32).contains(&result.members.len()) {
        return Err(error(
            "frame3d_result_ir_shape_invalid",
            "/",
            "ResultIR entity counts exceed the bounded Frame Alpha profile",
        ));
    }
    let mut node_ids = BTreeSet::new();
    for (index, node) in result.nodes.iter().enumerate() {
        let path = format!("/nodes/{index}/node_id");
        require_stable_id(&node.node_id, &path)?;
        if !node_ids.insert(&node.node_id) {
            return Err(error(
                "frame3d_result_ir_duplicate_node",
                &path,
                "ResultIR node IDs must be unique",
            ));
        }
        require_finite(
            &node.displacement_m_rad,
            &format!("/nodes/{index}/displacement_m_rad"),
        )?;
        require_finite(
            &node.reaction_n_nm,
            &format!("/nodes/{index}/reaction_n_nm"),
        )?;
    }
    let mut member_ids = BTreeSet::new();
    for (index, member) in result.members.iter().enumerate() {
        let path = format!("/members/{index}/member_id");
        require_stable_id(&member.member_id, &path)?;
        if !member_ids.insert(&member.member_id) {
            return Err(error(
                "frame3d_result_ir_duplicate_member",
                &path,
                "ResultIR member IDs must be unique",
            ));
        }
        require_finite(
            &member.end_i_force_n_nm,
            &format!("/members/{index}/end_i_force_n_nm"),
        )?;
        require_finite(
            &member.end_j_force_n_nm,
            &format!("/members/{index}/end_j_force_n_nm"),
        )?;
    }
    validate_gates(&result.gates)?;
    if result.authority != candidate_authority() || result.claim_boundary != claim_boundary() {
        return Err(error(
            "frame3d_result_ir_authority_invalid",
            "/authority",
            "ResultIR authority or claim boundary was promoted outside Frame Alpha",
        ));
    }
    Ok(())
}

fn validate_gates(gates: &Frame3dResultGatesV1) -> Result<(), Frame3dResultIrError> {
    for (path, value, tolerance) in [
        (
            "/gates/free_residual_scaled_linf",
            gates.free_residual_scaled_linf,
            gates.free_residual_scaled_linf_tolerance,
        ),
        (
            "/gates/global_force_balance_scaled_linf",
            gates.global_force_balance_scaled_linf,
            gates.global_force_balance_scaled_linf_tolerance,
        ),
        (
            "/gates/global_moment_balance_scaled_linf",
            gates.global_moment_balance_scaled_linf,
            gates.global_moment_balance_scaled_linf_tolerance,
        ),
        (
            "/gates/member_force_replay_scaled_linf",
            gates.member_force_replay_scaled_linf,
            gates.member_force_replay_scaled_linf_tolerance,
        ),
    ] {
        if !value.is_finite() || !tolerance.is_finite() || value < 0.0 || tolerance <= 0.0 {
            return Err(error(
                "frame3d_result_ir_gate_domain_invalid",
                path,
                "ResultIR gate values require finite nonnegative metrics and positive tolerances",
            ));
        }
        if value > tolerance {
            return Err(error(
                "frame3d_result_ir_gate_failed",
                path,
                "ResultIR cannot be created from a failed numerical, equilibrium or recovery gate",
            ));
        }
    }
    if !gates.native_residual_gate_passed
        || !gates.global_resultant_gate_passed
        || !gates.independent_recovery_replay_passed
        || !gates.zero_prescribed_displacement_gate_passed
        || gates.fallback_count != 0
        || gates.regularization_count != 0
    {
        return Err(error(
            "frame3d_result_ir_promotion_gate_failed",
            "/gates",
            "All bounded native ResultIR promotion gates must pass without fallback or regularization",
        ));
    }
    Ok(())
}

fn validate_schema(value: &Value) -> Result<(), Frame3dResultIrError> {
    let validator = schema_validator()?;
    if let Err(errors) = validator.validate(value) {
        let mut issues = errors
            .map(|item| {
                let path = item.instance_path.to_string();
                if path.is_empty() {
                    "/".to_owned()
                } else {
                    path
                }
            })
            .collect::<Vec<_>>();
        issues.sort();
        return Err(error(
            "frame3d_result_ir_schema_invalid",
            issues.first().map_or("/", String::as_str),
            "ResultIR does not satisfy the bounded native v1 schema",
        ));
    }
    Ok(())
}

fn schema_validator() -> Result<&'static JSONSchema, Frame3dResultIrError> {
    let compiled = SCHEMA_VALIDATOR.get_or_init(|| {
        let schema: Value = serde_json::from_str(SCHEMA_TEXT).map_err(|item| item.to_string())?;
        JSONSchema::options()
            .with_draft(Draft::Draft202012)
            .compile(&schema)
            .map_err(|item| item.to_string())
    });
    compiled.as_ref().map_err(|_| {
        error(
            "frame3d_result_ir_schema_contract_invalid",
            "/",
            "Embedded bounded native ResultIR schema could not be compiled",
        )
    })
}

fn result_hash(result: &LinearFrame3dResultIrV1) -> Result<String, Frame3dResultIrError> {
    let mut value = serde_json::to_value(result).map_err(|_| {
        error(
            "frame3d_result_ir_serialization_failed",
            "/",
            "ResultIR could not be represented as JSON",
        )
    })?;
    value
        .as_object_mut()
        .ok_or_else(|| {
            error(
                "frame3d_result_ir_invariant",
                "/",
                "ResultIR root is not an object",
            )
        })?
        .remove("result_hash");
    let canonical = canonicalize(&value)?;
    let digest = Sha256::digest(canonical.as_bytes());
    Ok(format!("{HASH_PREFIX}{digest:x}"))
}

fn canonicalize(value: &Value) -> Result<String, Frame3dResultIrError> {
    canonicalize_model_ir_v2(value).map_err(|source| {
        error(
            "frame3d_result_ir_canonicalization_failed",
            &source.path,
            &source.detail,
        )
    })
}

fn require_hash(value: &str, path: &str) -> Result<(), Frame3dResultIrError> {
    if value.len() != HASH_LENGTH
        || !value.starts_with(HASH_PREFIX)
        || !value[HASH_PREFIX.len()..]
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Err(error(
            "frame3d_result_ir_hash_invalid",
            path,
            "Expected a lowercase sha256 identity",
        ));
    }
    Ok(())
}

fn require_stable_id(value: &str, path: &str) -> Result<(), Frame3dResultIrError> {
    let mut bytes = value.bytes();
    let first = bytes.next();
    let valid = value.len() <= 128
        && first.is_some_and(|byte| byte.is_ascii_alphabetic())
        && bytes
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'.' | b':' | b'-'));
    if !valid {
        return Err(error(
            "frame3d_result_ir_id_invalid",
            path,
            "Expected a stable ASCII identifier",
        ));
    }
    Ok(())
}

fn require_finite(values: &[f64], path: &str) -> Result<(), Frame3dResultIrError> {
    if values.iter().all(|value| value.is_finite()) {
        Ok(())
    } else {
        Err(error(
            "frame3d_result_ir_non_finite",
            path,
            "ResultIR arrays must contain only finite binary64 values",
        ))
    }
}

fn candidate_authority() -> Frame3dResultAuthorityV1 {
    Frame3dResultAuthorityV1 {
        numerical_state: "bounded_candidate".to_owned(),
        convergence: "bounded_candidate".to_owned(),
        displacement: "bounded_candidate".to_owned(),
        reaction: "bounded_candidate".to_owned(),
        member_force: "bounded_candidate".to_owned(),
        engineering_design: "not_authoritative".to_owned(),
        code_compliance: "not_authoritative".to_owned(),
        release_readiness: "not_authoritative".to_owned(),
        commercial_use: "not_authoritative".to_owned(),
    }
}

fn claim_boundary() -> Frame3dResultClaimBoundaryV1 {
    Frame3dResultClaimBoundaryV1 {
        bounded_linear_static_timoshenko_frame3d: true,
        cpu_only: true,
        zero_prescribed_displacement_only: true,
        nodal_load_only: false,
        uniform_member_load_initial_local: true,
        self_weight_standard_gravity: true,
        member_end_rotational_release: true,
        rigid_member_end_offset: true,
        reaction_from_global_residual: true,
        member_force_from_native_local_recovery: true,
        independent_recovery_replay: true,
        cpu_hip_parity_established: false,
        external_validation_established: false,
        workbench_e2e: false,
        release_readiness: false,
        commercial_claim: false,
    }
}

fn error(code: &str, path: &str, detail: &str) -> Frame3dResultIrError {
    Frame3dResultIrError {
        code: code.to_owned(),
        path: path.to_owned(),
        detail: detail.to_owned(),
    }
}
