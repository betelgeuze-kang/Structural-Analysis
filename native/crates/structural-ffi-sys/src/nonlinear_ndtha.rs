//! Raw deterministic nonlinear NDTHA story-frame CPU operation introduced by C ABI v1.4.

use crate::{SaBufferViewV1, SaErrorBufferV1, SaMutBufferViewV1, SaStatusCodeV1};

pub const SA_ABI_V1_4: u32 = 0x0001_0004;
pub const SA_CAPABILITY_NONLINEAR_NDTHA_CPU: u64 = 1 << 5;
pub const SA_NONLINEAR_NDTHA_MAX_STORY_COUNT: u32 = 1_000_000;
pub const SA_NONLINEAR_NDTHA_MAX_STEP_COUNT: u32 = 1_000_000;

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaNonlinearNdthaConfigV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub story_count: u32,
    pub step_count: u32,
    pub dt_s: f64,
    pub newmark_beta: f64,
    pub newmark_gamma: f64,
    pub tolerance: f64,
    pub max_step_iterations: u32,
    pub reserved_iteration_u32: u32,
    pub adaptive_load_decay: f64,
    pub damping_force_cap_ratio: f64,
    pub newton_max_iter: u32,
    pub reserved_newton_u32: u32,
    pub line_search_decay: f64,
    pub line_search_min: f64,
    pub hardening_ratio: f64,
    pub pdelta_factor: f64,
    pub collapse_drift_threshold_pct: f64,
    pub flags: u32,
    pub reserved_u32: u32,
    pub reserved: [u64; 2],
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaNonlinearNdthaInputsV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub story_stiffness_n_per_m: SaBufferViewV1,
    pub story_height_m: SaBufferViewV1,
    pub story_axial_n: SaBufferViewV1,
    pub story_yield_drift_m: SaBufferViewV1,
    pub story_mass_kg: SaBufferViewV1,
    pub story_damping_n_s_per_m: SaBufferViewV1,
    pub floor_load_base_n: SaBufferViewV1,
    pub acceleration_g: SaBufferViewV1,
    pub reserved: [u64; 2],
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaNonlinearNdthaOutputsV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub top_displacement_m: SaMutBufferViewV1,
    pub drift_ratio_pct: SaMutBufferViewV1,
    pub base_shear_kn: SaMutBufferViewV1,
    pub core_drift_pct: SaMutBufferViewV1,
    pub core_shear_kn: SaMutBufferViewV1,
    pub step_converged: SaMutBufferViewV1,
    pub step_iterations: SaMutBufferViewV1,
    pub step_plastic_story_count: SaMutBufferViewV1,
    pub step_residual_inf: SaMutBufferViewV1,
    pub story_drift_envelope_pct: SaMutBufferViewV1,
    pub final_story_drift_pct: SaMutBufferViewV1,
    pub reserved: [u64; 2],
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaNonlinearNdthaResultV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub converged_all_steps: u32,
    pub collapsed: u32,
    pub collapse_step: i32,
    pub step_count_completed: u32,
    pub collapse_time_s: f64,
    pub collapse_drift_ratio_pct: f64,
    pub collapse_top_displacement_m: f64,
    pub max_drift_ratio_pct: f64,
    pub avg_step_iterations: f64,
    pub residual_top_displacement_m: f64,
    pub residual_drift_ratio_pct: f64,
    pub max_plastic_story_count: u32,
    pub total_line_search_backtracks: u32,
    pub output_story_count: u64,
    pub output_step_count: u64,
    pub execution_backend: u32,
    pub fallback_count: u32,
    pub reserved: [u64; 2],
}

pub type SaNonlinearNdthaSolveFnV1 = unsafe extern "C" fn(
    config: *const SaNonlinearNdthaConfigV1,
    inputs: *const SaNonlinearNdthaInputsV1,
    outputs: *const SaNonlinearNdthaOutputsV1,
    result: *mut SaNonlinearNdthaResultV1,
    error: *mut SaErrorBufferV1,
) -> SaStatusCodeV1;

#[cfg(test)]
mod tests {
    use super::{
        SaNonlinearNdthaConfigV1, SaNonlinearNdthaInputsV1, SaNonlinearNdthaOutputsV1,
        SaNonlinearNdthaResultV1,
    };
    use core::mem::{align_of, offset_of, size_of};

    #[test]
    fn rust_nonlinear_ndtha_layout_matches_the_public_c_header_contract() {
        assert_eq!(size_of::<SaNonlinearNdthaConfigV1>(), 144);
        assert_eq!(align_of::<SaNonlinearNdthaConfigV1>(), 8);
        assert_eq!(offset_of!(SaNonlinearNdthaConfigV1, story_count), 8);
        assert_eq!(offset_of!(SaNonlinearNdthaConfigV1, dt_s), 16);
        assert_eq!(
            offset_of!(SaNonlinearNdthaConfigV1, max_step_iterations),
            48
        );
        assert_eq!(
            offset_of!(SaNonlinearNdthaConfigV1, adaptive_load_decay),
            56
        );
        assert_eq!(offset_of!(SaNonlinearNdthaConfigV1, newton_max_iter), 72);
        assert_eq!(
            offset_of!(SaNonlinearNdthaConfigV1, collapse_drift_threshold_pct),
            112
        );
        assert_eq!(offset_of!(SaNonlinearNdthaConfigV1, reserved), 128);

        assert_eq!(size_of::<SaNonlinearNdthaInputsV1>(), 408);
        assert_eq!(align_of::<SaNonlinearNdthaInputsV1>(), 8);
        assert_eq!(
            offset_of!(SaNonlinearNdthaInputsV1, story_stiffness_n_per_m),
            8
        );
        assert_eq!(offset_of!(SaNonlinearNdthaInputsV1, acceleration_g), 344);
        assert_eq!(offset_of!(SaNonlinearNdthaInputsV1, reserved), 392);

        assert_eq!(size_of::<SaNonlinearNdthaOutputsV1>(), 552);
        assert_eq!(align_of::<SaNonlinearNdthaOutputsV1>(), 8);
        assert_eq!(offset_of!(SaNonlinearNdthaOutputsV1, top_displacement_m), 8);
        assert_eq!(offset_of!(SaNonlinearNdthaOutputsV1, step_converged), 248);
        assert_eq!(
            offset_of!(SaNonlinearNdthaOutputsV1, story_drift_envelope_pct),
            440
        );
        assert_eq!(offset_of!(SaNonlinearNdthaOutputsV1, reserved), 536);

        assert_eq!(size_of::<SaNonlinearNdthaResultV1>(), 128);
        assert_eq!(align_of::<SaNonlinearNdthaResultV1>(), 8);
        assert_eq!(offset_of!(SaNonlinearNdthaResultV1, collapse_step), 16);
        assert_eq!(offset_of!(SaNonlinearNdthaResultV1, collapse_time_s), 24);
        assert_eq!(
            offset_of!(SaNonlinearNdthaResultV1, max_plastic_story_count),
            80
        );
        assert_eq!(offset_of!(SaNonlinearNdthaResultV1, output_story_count), 88);
        assert_eq!(offset_of!(SaNonlinearNdthaResultV1, execution_backend), 104);
        assert_eq!(offset_of!(SaNonlinearNdthaResultV1, reserved), 112);
    }
}
