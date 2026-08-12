//! Compatibility conversion from the frozen raw ABI v3 into language-neutral wire types.

use structural_contracts::legacy_runtime::{
    InplaceScaleCaseV3, InplaceScaleStatsV3, NdthaResponseV3, NdthaStoryInputsV3,
    NonlinearNdthaCaseV3, NonlinearNdthaConfigV3, NonlinearNdthaResultV3, NonlinearStaticCaseV3,
    NonlinearStaticConfigV3, NonlinearStaticResultV3, StaticStoryInputsV3, TrackCaseV3,
    TrackConfigV3, TrackResultV3, TrackSupportType, TrackTheory, LEGACY_RUNTIME_SCHEMA_V3,
};
use structural_ffi_sys::legacy_runtime_v3::{
    InplaceScaleStats, NlFrameNdthaConfig, NlFrameNdthaResult, NlFrameSolveConfig,
    NlFrameSolveResult, TrackSolveConfig, TrackSolveResult,
};

/// One bounded conversion failure. No pointer value is included in diagnostics.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ContractAdapterError {
    pub code: &'static str,
    pub field: &'static str,
}

impl std::fmt::Display for ContractAdapterError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(formatter, "{} at {}", self.code, self.field)
    }
}

impl std::error::Error for ContractAdapterError {}

/// Borrowed arrays used by the static nonlinear compatibility operation.
#[derive(Clone, Copy)]
pub struct NonlinearStaticBuffers<'a> {
    pub story_k_n_per_m: &'a [f64],
    pub story_h_m: &'a [f64],
    pub story_axial_n: &'a [f64],
    pub story_yield_drift_m: &'a [f64],
    pub floor_load_n: &'a [f64],
    pub u_story_m: &'a [f64],
}

/// Borrowed arrays used by the NDTHA compatibility operation.
#[derive(Clone, Copy)]
pub struct NonlinearNdthaBuffers<'a> {
    pub story_k_n_per_m: &'a [f64],
    pub story_h_m: &'a [f64],
    pub story_axial_n: &'a [f64],
    pub story_yield_drift_m: &'a [f64],
    pub story_mass_kg: &'a [f64],
    pub story_damping_n_s_per_m: &'a [f64],
    pub floor_load_base_n: &'a [f64],
    pub ag_g: &'a [f64],
    pub top_displacement_m: &'a [f64],
    pub drift_ratio_pct: &'a [f64],
    pub base_shear_kn: &'a [f64],
    pub core_drift_pct: &'a [f64],
    pub core_shear_kn: &'a [f64],
    pub step_converged: &'a [u8],
    pub step_iterations: &'a [u32],
    pub step_plastic_story_count: &'a [u32],
    pub step_residual_inf: &'a [f64],
    pub story_drift_envelope_pct: &'a [f64],
    pub final_story_drift_pct: &'a [f64],
}

/// Convert one raw track invocation into the neutral v3 compatibility contract.
///
/// # Errors
///
/// Rejects unknown raw enum/flag values and vector lengths that disagree with `node_count`.
pub fn track_case_v3(
    config: &TrackSolveConfig,
    result: &TrackSolveResult,
    displacement_m: &[f64],
    rotation_rad: &[f64],
) -> Result<TrackCaseV3, ContractAdapterError> {
    let expected = usize::try_from(config.node_count).map_err(|_| length_error("node_count"))?;
    require_lengths(
        &[displacement_m.len(), rotation_rad.len()],
        expected,
        "track_vectors",
    )?;
    Ok(TrackCaseV3 {
        schema_version: LEGACY_RUNTIME_SCHEMA_V3.to_owned(),
        operation: "track_point_load".to_owned(),
        config: TrackConfigV3 {
            length_m: config.length_m,
            node_count: config.node_count,
            support_type: match config.support_type {
                0 => TrackSupportType::Pinned,
                1 => TrackSupportType::Fixed,
                _ => return Err(enum_error("support_type")),
            },
            theory: match config.theory {
                0 => TrackTheory::Euler,
                1 => TrackTheory::Timoshenko,
                _ => return Err(enum_error("theory")),
            },
            bending_stiffness_n_m2: config.bending_stiffness_n_m2,
            shear_stiffness_n: config.shear_stiffness_n,
            winkler_k_n_per_m2: config.winkler_k_n_per_m2,
            pasternak_g_n: config.pasternak_g_n,
            tolerance: config.tolerance,
            cg_max_iter: config.cg_max_iter,
            point_force_n: config.point_force_n,
            point_position_m: config.point_position_m,
        },
        result: TrackResultV3 {
            converged: bool_flag(result.converged, "converged")?,
            iterations: result.iterations,
            residual_inf: result.residual_inf,
            max_abs_displacement_m: result.max_abs_displacement_m,
            mid_displacement_m: result.mid_displacement_m,
            status_code: result.status_code,
            displacement_m: displacement_m.to_vec(),
            rotation_rad: rotation_rad.to_vec(),
        },
    })
}

/// Convert one in-place f32 operation without serializing process-specific pointer addresses.
///
/// # Errors
///
/// Rejects inconsistent input/output/stat lengths.
pub fn inplace_scale_case_v3(
    input: &[f32],
    output: &[f32],
    stats: &InplaceScaleStats,
) -> Result<InplaceScaleCaseV3, ContractAdapterError> {
    let expected = usize::try_from(stats.len).map_err(|_| length_error("length"))?;
    require_lengths(&[input.len(), output.len()], expected, "scale_vectors")?;
    Ok(InplaceScaleCaseV3 {
        schema_version: LEGACY_RUNTIME_SCHEMA_V3.to_owned(),
        operation: "inplace_scale_f32".to_owned(),
        input: input.iter().copied().map(f64::from).collect(),
        alpha: stats.alpha,
        output: output.iter().copied().map(f64::from).collect(),
        stats: InplaceScaleStatsV3 {
            length: stats.len,
            alpha: stats.alpha,
            sum_before: stats.sum_before,
            sum_after: stats.sum_after,
            max_abs_before: stats.max_abs_before,
            max_abs_after: stats.max_abs_after,
            status_code: stats.status_code,
            shared_storage: stats.ptr_before == stats.ptr_after,
        },
    })
}

/// Convert one static nonlinear invocation into the neutral v3 compatibility contract.
///
/// # Errors
///
/// Rejects unknown boolean flags and vector lengths that disagree with `story_count`.
pub fn nonlinear_static_case_v3(
    config: &NlFrameSolveConfig,
    result: &NlFrameSolveResult,
    buffers: NonlinearStaticBuffers<'_>,
) -> Result<NonlinearStaticCaseV3, ContractAdapterError> {
    let expected = usize::try_from(config.story_count).map_err(|_| length_error("story_count"))?;
    require_lengths(
        &[
            buffers.story_k_n_per_m.len(),
            buffers.story_h_m.len(),
            buffers.story_axial_n.len(),
            buffers.story_yield_drift_m.len(),
            buffers.floor_load_n.len(),
            buffers.u_story_m.len(),
        ],
        expected,
        "static_story_vectors",
    )?;
    Ok(NonlinearStaticCaseV3 {
        schema_version: LEGACY_RUNTIME_SCHEMA_V3.to_owned(),
        operation: "nonlinear_static".to_owned(),
        config: NonlinearStaticConfigV3 {
            story_count: config.story_count,
            tolerance: config.tolerance,
            max_iter: config.max_iter,
            hardening_ratio: config.hardening_ratio,
            line_search_decay: config.line_search_decay,
            line_search_min: config.line_search_min,
            pdelta_factor: config.pdelta_factor,
        },
        inputs: StaticStoryInputsV3 {
            story_k_n_per_m: buffers.story_k_n_per_m.to_vec(),
            story_h_m: buffers.story_h_m.to_vec(),
            story_axial_n: buffers.story_axial_n.to_vec(),
            story_yield_drift_m: buffers.story_yield_drift_m.to_vec(),
            floor_load_n: buffers.floor_load_n.to_vec(),
        },
        result: NonlinearStaticResultV3 {
            converged: bool_flag(result.converged, "converged")?,
            iterations: result.iterations,
            residual_inf: result.residual_inf,
            residual_l2: result.residual_l2,
            max_abs_displacement_m: result.max_abs_displacement_m,
            top_displacement_m: result.top_displacement_m,
            base_shear_kn: result.base_shear_kn,
            plastic_story_count: result.plastic_story_count,
            line_search_backtracks: result.line_search_backtracks,
            status_code: result.status_code,
            u_story_m: buffers.u_story_m.to_vec(),
        },
    })
}

/// Convert one NDTHA invocation into the neutral v3 compatibility contract.
///
/// # Errors
///
/// Rejects unknown boolean flags and story/step vectors that disagree with declared counts.
pub fn nonlinear_ndtha_case_v3(
    config: &NlFrameNdthaConfig,
    result: &NlFrameNdthaResult,
    buffers: NonlinearNdthaBuffers<'_>,
) -> Result<NonlinearNdthaCaseV3, ContractAdapterError> {
    let stories = usize::try_from(config.story_count).map_err(|_| length_error("story_count"))?;
    require_lengths(
        &[
            buffers.story_k_n_per_m.len(),
            buffers.story_h_m.len(),
            buffers.story_axial_n.len(),
            buffers.story_yield_drift_m.len(),
            buffers.story_mass_kg.len(),
            buffers.story_damping_n_s_per_m.len(),
            buffers.floor_load_base_n.len(),
            buffers.story_drift_envelope_pct.len(),
            buffers.final_story_drift_pct.len(),
        ],
        stories,
        "ndtha_story_vectors",
    )?;
    let steps = usize::try_from(config.step_count).map_err(|_| length_error("step_count"))?;
    require_lengths(
        &[
            buffers.ag_g.len(),
            buffers.top_displacement_m.len(),
            buffers.drift_ratio_pct.len(),
            buffers.base_shear_kn.len(),
            buffers.core_drift_pct.len(),
            buffers.core_shear_kn.len(),
            buffers.step_converged.len(),
            buffers.step_iterations.len(),
            buffers.step_plastic_story_count.len(),
            buffers.step_residual_inf.len(),
        ],
        steps,
        "ndtha_step_vectors",
    )?;
    let step_converged = buffers
        .step_converged
        .iter()
        .copied()
        .map(|value| bool_flag(value, "step_converged"))
        .collect::<Result<Vec<_>, _>>()?;
    Ok(NonlinearNdthaCaseV3 {
        schema_version: LEGACY_RUNTIME_SCHEMA_V3.to_owned(),
        operation: "nonlinear_ndtha".to_owned(),
        config: NonlinearNdthaConfigV3 {
            story_count: config.story_count,
            step_count: config.step_count,
            dt_s: config.dt_s,
            newmark_beta: config.newmark_beta,
            newmark_gamma: config.newmark_gamma,
            tolerance: config.tolerance,
            max_step_iterations: config.max_step_iterations,
            adaptive_load_decay: config.adaptive_load_decay,
            damping_force_cap_ratio: config.damping_force_cap_ratio,
            newton_max_iter: config.newton_max_iter,
            line_search_decay: config.line_search_decay,
            line_search_min: config.line_search_min,
            hardening_ratio: config.hardening_ratio,
            pdelta_factor: config.pdelta_factor,
            collapse_drift_threshold_pct: config.collapse_drift_threshold_pct,
        },
        inputs: NdthaStoryInputsV3 {
            story_k_n_per_m: buffers.story_k_n_per_m.to_vec(),
            story_h_m: buffers.story_h_m.to_vec(),
            story_axial_n: buffers.story_axial_n.to_vec(),
            story_yield_drift_m: buffers.story_yield_drift_m.to_vec(),
            story_mass_kg: buffers.story_mass_kg.to_vec(),
            story_damping_n_s_per_m: buffers.story_damping_n_s_per_m.to_vec(),
            floor_load_base_n: buffers.floor_load_base_n.to_vec(),
            ag_g: buffers.ag_g.to_vec(),
        },
        result: NonlinearNdthaResultV3 {
            converged_all_steps: bool_flag(result.converged_all_steps, "converged_all_steps")?,
            rust_backend_all_steps: bool_flag(
                result.rust_backend_all_steps,
                "rust_backend_all_steps",
            )?,
            collapsed: bool_flag(result.collapsed, "collapsed")?,
            collapse_step: result.collapse_step,
            collapse_time_s: result.collapse_time_s,
            collapse_drift_ratio_pct: result.collapse_drift_ratio_pct,
            collapse_top_displacement_m: result.collapse_top_displacement_m,
            step_count_completed: result.step_count_completed,
            max_plastic_story_count: result.max_plastic_story_count,
            max_drift_ratio_pct: result.max_drift_ratio_pct,
            avg_step_iterations: result.avg_step_iterations,
            residual_top_displacement_m: result.residual_top_displacement_m,
            residual_drift_ratio_pct: result.residual_drift_ratio_pct,
            status_code: result.status_code,
            response: NdthaResponseV3 {
                top_displacement_m: buffers.top_displacement_m.to_vec(),
                drift_ratio_pct: buffers.drift_ratio_pct.to_vec(),
                base_shear_kn: buffers.base_shear_kn.to_vec(),
                core_drift_pct: buffers.core_drift_pct.to_vec(),
                core_shear_kn: buffers.core_shear_kn.to_vec(),
                step_converged,
                step_iterations: buffers.step_iterations.to_vec(),
                step_plastic_story_count: buffers.step_plastic_story_count.to_vec(),
                step_residual_inf: buffers.step_residual_inf.to_vec(),
                story_drift_envelope_pct: buffers.story_drift_envelope_pct.to_vec(),
                final_story_drift_pct: buffers.final_story_drift_pct.to_vec(),
            },
        },
    })
}

fn bool_flag(value: u8, field: &'static str) -> Result<bool, ContractAdapterError> {
    match value {
        0 => Ok(false),
        1 => Ok(true),
        _ => Err(ContractAdapterError {
            code: "legacy_runtime_invalid_boolean_flag",
            field,
        }),
    }
}

fn require_lengths(
    lengths: &[usize],
    expected: usize,
    field: &'static str,
) -> Result<(), ContractAdapterError> {
    if expected == 0 || lengths.iter().any(|length| *length != expected) {
        return Err(length_error(field));
    }
    Ok(())
}

const fn enum_error(field: &'static str) -> ContractAdapterError {
    ContractAdapterError {
        code: "legacy_runtime_unknown_enum",
        field,
    }
}

const fn length_error(field: &'static str) -> ContractAdapterError {
    ContractAdapterError {
        code: "legacy_runtime_vector_length_mismatch",
        field,
    }
}
