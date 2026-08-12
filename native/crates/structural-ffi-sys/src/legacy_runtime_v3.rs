//! Frozen raw ABI v3 declarations for the temporary structural runtime compatibility member.

pub const STRUCTURAL_RUNTIME_ABI_V3: u32 = 3;

pub const TRACK_STATUS_NULL_ARGUMENT: i32 = -1;
pub const TRACK_STATUS_OUTPUT_TOO_SMALL: i32 = -2;
pub const TRACK_STATUS_INVALID_LENGTH: i32 = -11;
pub const TRACK_STATUS_INVALID_NODE_COUNT: i32 = -12;
pub const TRACK_STATUS_INVALID_STIFFNESS: i32 = -13;
pub const TRACK_STATUS_INVALID_FOUNDATION: i32 = -14;
pub const TRACK_STATUS_INVALID_ITERATION_CONTROL: i32 = -15;
pub const TRACK_STATUS_INVALID_ENUM: i32 = -16;

pub const INPLACE_SCALE_STATUS_INVALID_ARGUMENT: i32 = -1;

pub const NONLINEAR_STATIC_STATUS_NULL_ARGUMENT: i32 = -21;
pub const NONLINEAR_STATIC_STATUS_OUTPUT_TOO_SMALL: i32 = -22;
pub const NONLINEAR_STATIC_STATUS_INVALID_STORY_COUNT: i32 = -31;
pub const NONLINEAR_STATIC_STATUS_INVALID_ITERATION_CONTROL: i32 = -32;
pub const NONLINEAR_STATIC_STATUS_INVALID_HARDENING: i32 = -33;
pub const NONLINEAR_STATIC_STATUS_INVALID_LINE_SEARCH_DECAY: i32 = -34;
pub const NONLINEAR_STATIC_STATUS_INVALID_LINE_SEARCH_MIN: i32 = -35;
pub const NONLINEAR_STATIC_STATUS_INVALID_PDELTA: i32 = -36;
pub const NONLINEAR_STATIC_STATUS_NONCONVERGENCE: i32 = -37;

pub const NDTHA_STATUS_NULL_ARGUMENT: i32 = -61;
pub const NDTHA_STATUS_NONCONVERGENCE_OR_COLLAPSE: i32 = -62;
pub const NDTHA_STATUS_INVALID_COUNTS: i32 = -41;
pub const NDTHA_STATUS_INVALID_TIME_STEP: i32 = -42;
pub const NDTHA_STATUS_INVALID_NEWMARK: i32 = -43;
pub const NDTHA_STATUS_INVALID_TOLERANCE: i32 = -44;
pub const NDTHA_STATUS_INVALID_ITERATION_CONTROL: i32 = -45;
pub const NDTHA_STATUS_INVALID_ADAPTIVE_DECAY: i32 = -46;
pub const NDTHA_STATUS_INVALID_DAMPING_CAP: i32 = -47;
pub const NDTHA_STATUS_INVALID_HARDENING: i32 = -48;
pub const NDTHA_STATUS_INVALID_PDELTA: i32 = -49;
pub const NDTHA_STATUS_INVALID_LINE_SEARCH_DECAY: i32 = -50;
pub const NDTHA_STATUS_INVALID_LINE_SEARCH_MIN: i32 = -51;
pub const NDTHA_STATUS_INVALID_COLLAPSE_DRIFT: i32 = -52;

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct TrackSolveConfig {
    pub length_m: f64,
    pub node_count: u32,
    /// `0` is pinned and `1` is fixed.
    pub support_type: u32,
    /// `0` is Euler and `1` is the reduced-correction Timoshenko mode.
    pub theory: u32,
    pub bending_stiffness_n_m2: f64,
    pub shear_stiffness_n: f64,
    pub winkler_k_n_per_m2: f64,
    pub pasternak_g_n: f64,
    pub tolerance: f64,
    pub cg_max_iter: u32,
    pub point_force_n: f64,
    pub point_position_m: f64,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct TrackSolveResult {
    pub converged: u8,
    pub iterations: u32,
    pub residual_inf: f64,
    pub max_abs_displacement_m: f64,
    pub mid_displacement_m: f64,
    pub status_code: i32,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct InplaceScaleStats {
    /// Process-local address used only to prove in-place identity at the raw ABI.
    pub ptr_before: u64,
    /// Process-local address used only to prove in-place identity at the raw ABI.
    pub ptr_after: u64,
    pub len: u32,
    pub alpha: f32,
    pub sum_before: f64,
    pub sum_after: f64,
    pub max_abs_before: f64,
    pub max_abs_after: f64,
    pub status_code: i32,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct NlFrameSolveConfig {
    pub story_count: u32,
    pub tolerance: f64,
    pub max_iter: u32,
    pub hardening_ratio: f64,
    pub line_search_decay: f64,
    pub line_search_min: f64,
    pub pdelta_factor: f64,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct NlFrameSolveResult {
    pub converged: u8,
    pub iterations: u32,
    pub residual_inf: f64,
    pub residual_l2: f64,
    pub max_abs_displacement_m: f64,
    pub top_displacement_m: f64,
    pub base_shear_kn: f64,
    pub plastic_story_count: u32,
    pub line_search_backtracks: u32,
    pub status_code: i32,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct NlFrameNdthaConfig {
    pub story_count: u32,
    pub step_count: u32,
    pub dt_s: f64,
    pub newmark_beta: f64,
    pub newmark_gamma: f64,
    pub tolerance: f64,
    /// Maximum adaptive load-retry attempts for one time step.
    pub max_step_iterations: u32,
    pub adaptive_load_decay: f64,
    pub damping_force_cap_ratio: f64,
    /// Maximum Newton iterations for one adaptive attempt.
    pub newton_max_iter: u32,
    pub line_search_decay: f64,
    pub line_search_min: f64,
    pub hardening_ratio: f64,
    pub pdelta_factor: f64,
    pub collapse_drift_threshold_pct: f64,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct NlFrameNdthaResult {
    pub converged_all_steps: u8,
    pub rust_backend_all_steps: u8,
    pub collapsed: u8,
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
}

#[cfg(test)]
mod tests {
    use super::{
        InplaceScaleStats, NlFrameNdthaConfig, NlFrameNdthaResult, NlFrameSolveConfig,
        NlFrameSolveResult, TrackSolveConfig, TrackSolveResult,
    };
    use core::mem::{align_of, offset_of, size_of};

    #[test]
    fn raw_runtime_v3_layout_matches_the_frozen_compatibility_inventory() {
        assert_eq!(
            (
                size_of::<TrackSolveConfig>(),
                align_of::<TrackSolveConfig>()
            ),
            (88, 8)
        );
        assert_eq!(offset_of!(TrackSolveConfig, node_count), 8);
        assert_eq!(offset_of!(TrackSolveConfig, bending_stiffness_n_m2), 24);
        assert_eq!(offset_of!(TrackSolveConfig, point_position_m), 80);

        assert_eq!(
            (
                size_of::<TrackSolveResult>(),
                align_of::<TrackSolveResult>()
            ),
            (40, 8)
        );
        assert_eq!(offset_of!(TrackSolveResult, iterations), 4);
        assert_eq!(offset_of!(TrackSolveResult, status_code), 32);

        assert_eq!(
            (
                size_of::<InplaceScaleStats>(),
                align_of::<InplaceScaleStats>()
            ),
            (64, 8)
        );
        assert_eq!(offset_of!(InplaceScaleStats, alpha), 20);
        assert_eq!(offset_of!(InplaceScaleStats, status_code), 56);

        assert_eq!(
            (
                size_of::<NlFrameSolveConfig>(),
                align_of::<NlFrameSolveConfig>()
            ),
            (56, 8)
        );
        assert_eq!(offset_of!(NlFrameSolveConfig, max_iter), 16);
        assert_eq!(offset_of!(NlFrameSolveConfig, pdelta_factor), 48);

        assert_eq!(
            (
                size_of::<NlFrameSolveResult>(),
                align_of::<NlFrameSolveResult>()
            ),
            (64, 8)
        );
        assert_eq!(offset_of!(NlFrameSolveResult, base_shear_kn), 40);
        assert_eq!(offset_of!(NlFrameSolveResult, status_code), 56);

        assert_eq!(
            (
                size_of::<NlFrameNdthaConfig>(),
                align_of::<NlFrameNdthaConfig>()
            ),
            (112, 8)
        );
        assert_eq!(offset_of!(NlFrameNdthaConfig, step_count), 4);
        assert_eq!(offset_of!(NlFrameNdthaConfig, newton_max_iter), 64);
        assert_eq!(
            offset_of!(NlFrameNdthaConfig, collapse_drift_threshold_pct),
            104
        );

        assert_eq!(
            (
                size_of::<NlFrameNdthaResult>(),
                align_of::<NlFrameNdthaResult>()
            ),
            (80, 8)
        );
        assert_eq!(offset_of!(NlFrameNdthaResult, collapse_step), 4);
        assert_eq!(offset_of!(NlFrameNdthaResult, avg_step_iterations), 48);
        assert_eq!(offset_of!(NlFrameNdthaResult, status_code), 72);
    }
}
