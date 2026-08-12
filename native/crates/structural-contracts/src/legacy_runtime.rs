//! Language-neutral compatibility wire for the frozen legacy structural runtime v3.

use std::fmt;
use std::sync::OnceLock;

use jsonschema::{Draft, JSONSchema};
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::model_ir::decode_json_strict;

pub const LEGACY_RUNTIME_SCHEMA_V3: &str = "structural-runtime-compat.v3";

const SCHEMA_TEXT: &str = include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/schemas/legacy_runtime_v3.schema.json"
));
static SCHEMA_VALIDATOR: OnceLock<Result<JSONSchema, String>> = OnceLock::new();

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum TrackSupportType {
    Pinned,
    Fixed,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum TrackTheory {
    Euler,
    Timoshenko,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TrackConfigV3 {
    pub length_m: f64,
    pub node_count: u32,
    pub support_type: TrackSupportType,
    pub theory: TrackTheory,
    pub bending_stiffness_n_m2: f64,
    pub shear_stiffness_n: f64,
    pub winkler_k_n_per_m2: f64,
    pub pasternak_g_n: f64,
    pub tolerance: f64,
    pub cg_max_iter: u32,
    pub point_force_n: f64,
    pub point_position_m: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TrackResultV3 {
    pub converged: bool,
    pub iterations: u32,
    pub residual_inf: f64,
    pub max_abs_displacement_m: f64,
    pub mid_displacement_m: f64,
    pub status_code: i32,
    pub displacement_m: Vec<f64>,
    pub rotation_rad: Vec<f64>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TrackCaseV3 {
    pub schema_version: String,
    pub operation: String,
    pub config: TrackConfigV3,
    pub result: TrackResultV3,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct InplaceScaleStatsV3 {
    pub length: u32,
    pub alpha: f32,
    pub sum_before: f64,
    pub sum_after: f64,
    pub max_abs_before: f64,
    pub max_abs_after: f64,
    pub status_code: i32,
    pub shared_storage: bool,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct InplaceScaleCaseV3 {
    pub schema_version: String,
    pub operation: String,
    pub input: Vec<f64>,
    pub alpha: f32,
    pub output: Vec<f64>,
    pub stats: InplaceScaleStatsV3,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NonlinearStaticConfigV3 {
    pub story_count: u32,
    pub tolerance: f64,
    pub max_iter: u32,
    pub hardening_ratio: f64,
    pub line_search_decay: f64,
    pub line_search_min: f64,
    pub pdelta_factor: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct StaticStoryInputsV3 {
    pub story_k_n_per_m: Vec<f64>,
    pub story_h_m: Vec<f64>,
    pub story_axial_n: Vec<f64>,
    pub story_yield_drift_m: Vec<f64>,
    pub floor_load_n: Vec<f64>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NonlinearStaticResultV3 {
    pub converged: bool,
    pub iterations: u32,
    pub residual_inf: f64,
    pub residual_l2: f64,
    pub max_abs_displacement_m: f64,
    pub top_displacement_m: f64,
    pub base_shear_kn: f64,
    pub plastic_story_count: u32,
    pub line_search_backtracks: u32,
    pub status_code: i32,
    pub u_story_m: Vec<f64>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NonlinearStaticCaseV3 {
    pub schema_version: String,
    pub operation: String,
    pub config: NonlinearStaticConfigV3,
    pub inputs: StaticStoryInputsV3,
    pub result: NonlinearStaticResultV3,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NonlinearNdthaConfigV3 {
    pub story_count: u32,
    pub step_count: u32,
    pub dt_s: f64,
    pub newmark_beta: f64,
    pub newmark_gamma: f64,
    pub tolerance: f64,
    pub max_step_iterations: u32,
    pub adaptive_load_decay: f64,
    pub damping_force_cap_ratio: f64,
    pub newton_max_iter: u32,
    pub line_search_decay: f64,
    pub line_search_min: f64,
    pub hardening_ratio: f64,
    pub pdelta_factor: f64,
    pub collapse_drift_threshold_pct: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NdthaStoryInputsV3 {
    pub story_k_n_per_m: Vec<f64>,
    pub story_h_m: Vec<f64>,
    pub story_axial_n: Vec<f64>,
    pub story_yield_drift_m: Vec<f64>,
    pub story_mass_kg: Vec<f64>,
    pub story_damping_n_s_per_m: Vec<f64>,
    pub floor_load_base_n: Vec<f64>,
    pub ag_g: Vec<f64>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NdthaResponseV3 {
    pub top_displacement_m: Vec<f64>,
    pub drift_ratio_pct: Vec<f64>,
    pub base_shear_kn: Vec<f64>,
    pub core_drift_pct: Vec<f64>,
    pub core_shear_kn: Vec<f64>,
    pub step_converged: Vec<bool>,
    pub step_iterations: Vec<u32>,
    pub step_plastic_story_count: Vec<u32>,
    pub step_residual_inf: Vec<f64>,
    pub story_drift_envelope_pct: Vec<f64>,
    pub final_story_drift_pct: Vec<f64>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NonlinearNdthaResultV3 {
    pub converged_all_steps: bool,
    pub rust_backend_all_steps: bool,
    pub collapsed: bool,
    pub collapse_step: i32,
    pub collapse_time_s: f64,
    pub collapse_drift_ratio_pct: f64,
    pub collapse_top_displacement_m: f64,
    pub step_count_completed: u32,
    pub max_plastic_story_count: u32,
    pub max_drift_ratio_pct: f64,
    pub avg_step_iterations: f64,
    pub residual_top_displacement_m: f64,
    pub residual_drift_ratio_pct: f64,
    pub status_code: i32,
    pub response: NdthaResponseV3,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NonlinearNdthaCaseV3 {
    pub schema_version: String,
    pub operation: String,
    pub config: NonlinearNdthaConfigV3,
    pub inputs: NdthaStoryInputsV3,
    pub result: NonlinearNdthaResultV3,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(untagged)]
pub enum LegacyRuntimeCaseV3 {
    Track(TrackCaseV3),
    InplaceScale(InplaceScaleCaseV3),
    NonlinearStatic(NonlinearStaticCaseV3),
    NonlinearNdtha(Box<NonlinearNdthaCaseV3>),
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct LegacyRuntimeContractError {
    pub code: String,
    pub path: String,
    pub detail: String,
}

impl fmt::Display for LegacyRuntimeContractError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{} at {}: {}", self.code, self.path, self.detail)
    }
}

impl std::error::Error for LegacyRuntimeContractError {}

/// Strictly decode and validate one language-neutral legacy runtime v3 case.
///
/// # Errors
///
/// Returns a stable error for duplicate keys, schema violations, non-finite values or
/// cross-vector length mismatches.
pub fn parse_legacy_runtime_case_v3(
    bytes: &[u8],
) -> Result<LegacyRuntimeCaseV3, LegacyRuntimeContractError> {
    let value = decode_json_strict(bytes).map_err(|error| LegacyRuntimeContractError {
        code: error
            .code
            .strip_prefix("model_ir_")
            .map_or(error.code.clone(), |suffix| {
                format!("legacy_runtime_{suffix}")
            }),
        path: error.path,
        detail: error.detail.replace("ModelIR", "legacy runtime"),
    })?;
    validate_schema(&value)?;
    let case: LegacyRuntimeCaseV3 = serde_json::from_value(value).map_err(|_| {
        contract_error(
            "legacy_runtime_wire_decode_failed",
            "/",
            "validated legacy runtime v3 case could not be decoded",
        )
    })?;
    validate_lengths(&case)?;
    Ok(case)
}

fn validate_schema(value: &Value) -> Result<(), LegacyRuntimeContractError> {
    let validator = SCHEMA_VALIDATOR.get_or_init(|| {
        let schema: Value = serde_json::from_str(SCHEMA_TEXT)
            .map_err(|error| format!("schema JSON invalid: {error}"))?;
        JSONSchema::options()
            .with_draft(Draft::Draft202012)
            .compile(&schema)
            .map_err(|error| format!("schema compile failed: {error}"))
    });
    let validator = validator.as_ref().map_err(|_| {
        contract_error(
            "legacy_runtime_schema_contract_invalid",
            "/",
            "embedded legacy runtime v3 schema could not be compiled",
        )
    })?;
    let mut issues = validator
        .validate(value)
        .err()
        .into_iter()
        .flatten()
        .map(|error| {
            let path = error.instance_path.to_string();
            if path.is_empty() {
                "/".to_owned()
            } else {
                path
            }
        })
        .collect::<Vec<_>>();
    issues.sort();
    if let Some(path) = issues.first() {
        return Err(contract_error(
            "legacy_runtime_schema_invalid",
            path,
            "legacy runtime case does not satisfy the v3 schema",
        ));
    }
    Ok(())
}

fn validate_lengths(case: &LegacyRuntimeCaseV3) -> Result<(), LegacyRuntimeContractError> {
    match case {
        LegacyRuntimeCaseV3::Track(case) => {
            let expected = usize::try_from(case.config.node_count).map_err(|_| length_error())?;
            require_lengths(
                &[
                    case.result.displacement_m.len(),
                    case.result.rotation_rad.len(),
                ],
                expected,
            )?;
        }
        LegacyRuntimeCaseV3::InplaceScale(case) => {
            let expected = usize::try_from(case.stats.length).map_err(|_| length_error())?;
            require_lengths(&[case.input.len(), case.output.len()], expected)?;
        }
        LegacyRuntimeCaseV3::NonlinearStatic(case) => {
            let expected = usize::try_from(case.config.story_count).map_err(|_| length_error())?;
            require_lengths(
                &[
                    case.inputs.story_k_n_per_m.len(),
                    case.inputs.story_h_m.len(),
                    case.inputs.story_axial_n.len(),
                    case.inputs.story_yield_drift_m.len(),
                    case.inputs.floor_load_n.len(),
                    case.result.u_story_m.len(),
                ],
                expected,
            )?;
        }
        LegacyRuntimeCaseV3::NonlinearNdtha(case) => {
            let stories = usize::try_from(case.config.story_count).map_err(|_| length_error())?;
            require_lengths(
                &[
                    case.inputs.story_k_n_per_m.len(),
                    case.inputs.story_h_m.len(),
                    case.inputs.story_axial_n.len(),
                    case.inputs.story_yield_drift_m.len(),
                    case.inputs.story_mass_kg.len(),
                    case.inputs.story_damping_n_s_per_m.len(),
                    case.inputs.floor_load_base_n.len(),
                    case.result.response.story_drift_envelope_pct.len(),
                    case.result.response.final_story_drift_pct.len(),
                ],
                stories,
            )?;
            let steps = usize::try_from(case.config.step_count).map_err(|_| length_error())?;
            require_lengths(
                &[
                    case.inputs.ag_g.len(),
                    case.result.response.top_displacement_m.len(),
                    case.result.response.drift_ratio_pct.len(),
                    case.result.response.base_shear_kn.len(),
                    case.result.response.core_drift_pct.len(),
                    case.result.response.core_shear_kn.len(),
                    case.result.response.step_converged.len(),
                    case.result.response.step_iterations.len(),
                    case.result.response.step_plastic_story_count.len(),
                    case.result.response.step_residual_inf.len(),
                ],
                steps,
            )?;
        }
    }
    Ok(())
}

fn require_lengths(lengths: &[usize], expected: usize) -> Result<(), LegacyRuntimeContractError> {
    if expected == 0 || lengths.iter().any(|length| *length != expected) {
        return Err(length_error());
    }
    Ok(())
}

fn length_error() -> LegacyRuntimeContractError {
    contract_error(
        "legacy_runtime_vector_length_mismatch",
        "/",
        "all vectors in one legacy runtime family must have the declared common length",
    )
}

fn contract_error(code: &str, path: &str, detail: &str) -> LegacyRuntimeContractError {
    LegacyRuntimeContractError {
        code: code.to_owned(),
        path: path.to_owned(),
        detail: detail.to_owned(),
    }
}
