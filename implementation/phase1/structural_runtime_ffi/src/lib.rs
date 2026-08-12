pub mod contracts;
mod ffi;
mod runtime;

pub use ffi::{
    phase1_rust_nonlinear_frame_ndtha_solve, phase1_rust_nonlinear_frame_solve,
    phase1_rust_scale_inplace_f32, phase1_rust_track_lf_solve_point_load, phase1_rust_version,
};
pub use structural_ffi_sys::legacy_runtime_v3::{
    InplaceScaleStats, NlFrameNdthaConfig, NlFrameNdthaResult, NlFrameSolveConfig,
    NlFrameSolveResult, TrackSolveConfig, TrackSolveResult,
};
