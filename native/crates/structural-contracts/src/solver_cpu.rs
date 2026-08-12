//! Language-neutral product goldens for bounded CPU solver capability gates.

use std::fmt;
use std::sync::OnceLock;

use jsonschema::{Draft, JSONSchema};
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::legacy_runtime::{NdthaResponseV3, NdthaStoryInputsV3, NonlinearNdthaConfigV3};
use crate::model_ir::decode_json_strict;

pub const NONLINEAR_NDTHA_CPU_SCHEMA_V1: &str = "structural-solver-cpu-nonlinear-ndtha.v1";

const SCHEMA_TEXT: &str = include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/schemas/nonlinear_ndtha_cpu_v1.schema.json"
));
static SCHEMA_VALIDATOR: OnceLock<Result<JSONSchema, String>> = OnceLock::new();

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ExecutionBackendV1 {
    Cpu,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NonlinearNdthaCpuResultV1 {
    pub converged_all_steps: bool,
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
    pub total_line_search_backtracks: u32,
    pub execution_backend: ExecutionBackendV1,
    pub fallback_count: u32,
    pub response: NdthaResponseV3,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NonlinearNdthaCpuCaseV1 {
    pub schema_version: String,
    pub operation: String,
    pub config: NonlinearNdthaConfigV3,
    pub inputs: NdthaStoryInputsV3,
    pub result: NonlinearNdthaCpuResultV1,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct SolverCpuContractError {
    pub code: String,
    pub path: String,
    pub detail: String,
}

impl fmt::Display for SolverCpuContractError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{} at {}: {}", self.code, self.path, self.detail)
    }
}

impl std::error::Error for SolverCpuContractError {}

/// Strictly decode and validate one nonlinear NDTHA CPU product golden.
///
/// # Errors
///
/// Returns a stable error for duplicate keys, schema violations, non-finite
/// values, cross-vector length mismatches or impossible terminal-state data.
pub fn parse_nonlinear_ndtha_cpu_case_v1(
    bytes: &[u8],
) -> Result<NonlinearNdthaCpuCaseV1, SolverCpuContractError> {
    let value = decode_json_strict(bytes).map_err(|error| SolverCpuContractError {
        code: error
            .code
            .strip_prefix("model_ir_")
            .map_or(error.code.clone(), |suffix| format!("solver_cpu_{suffix}")),
        path: error.path,
        detail: error.detail.replace("ModelIR", "solver CPU golden"),
    })?;
    validate_schema(&value)?;
    let case: NonlinearNdthaCpuCaseV1 = serde_json::from_value(value).map_err(|_| {
        contract_error(
            "solver_cpu_wire_decode_failed",
            "/",
            "validated nonlinear NDTHA CPU case could not be decoded",
        )
    })?;
    validate_case(&case)?;
    Ok(case)
}

fn validate_schema(value: &Value) -> Result<(), SolverCpuContractError> {
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
            "solver_cpu_schema_contract_invalid",
            "/",
            "embedded nonlinear NDTHA CPU schema could not be compiled",
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
            "solver_cpu_schema_invalid",
            path,
            "nonlinear NDTHA CPU case does not satisfy the v1 schema",
        ));
    }
    Ok(())
}

fn validate_case(case: &NonlinearNdthaCpuCaseV1) -> Result<(), SolverCpuContractError> {
    let stories = usize::try_from(case.config.story_count).map_err(|_| length_error())?;
    let steps = usize::try_from(case.config.step_count).map_err(|_| length_error())?;
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

    let result = &case.result;
    let terminal_valid = result.converged_all_steps != result.collapsed
        && if result.collapsed {
            result.collapse_step >= 0
                && u32::try_from(result.collapse_step).is_ok_and(|step| {
                    step < result.step_count_completed
                        && result.step_count_completed <= case.config.step_count
                })
        } else {
            result.collapse_step == -1 && result.step_count_completed == case.config.step_count
        };
    if !terminal_valid {
        return Err(contract_error(
            "solver_cpu_terminal_state_invalid",
            "/result",
            "nonlinear NDTHA terminal flags and completion counters disagree",
        ));
    }
    let completed = usize::try_from(result.step_count_completed).map_err(|_| length_error())?;
    if result.response.step_converged[..completed]
        .iter()
        .any(|value| !value)
        || result.response.step_converged[completed..]
            .iter()
            .any(|value| *value)
    {
        return Err(contract_error(
            "solver_cpu_step_state_invalid",
            "/result/response/step_converged",
            "completed and unexecuted response slots are inconsistent",
        ));
    }
    if result.max_plastic_story_count > case.config.story_count {
        return Err(contract_error(
            "solver_cpu_plastic_count_invalid",
            "/result/max_plastic_story_count",
            "plastic story count exceeds story_count",
        ));
    }
    Ok(())
}

fn require_lengths(lengths: &[usize], expected: usize) -> Result<(), SolverCpuContractError> {
    if expected == 0 || lengths.iter().any(|length| *length != expected) {
        return Err(length_error());
    }
    Ok(())
}

fn length_error() -> SolverCpuContractError {
    contract_error(
        "solver_cpu_vector_length_mismatch",
        "/",
        "all nonlinear NDTHA vectors must have the declared story or step length",
    )
}

fn contract_error(code: &str, path: &str, detail: &str) -> SolverCpuContractError {
    SolverCpuContractError {
        code: code.to_owned(),
        path: path.to_owned(),
        detail: detail.to_owned(),
    }
}
