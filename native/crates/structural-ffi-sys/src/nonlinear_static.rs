//! Raw deterministic nonlinear static story-frame CPU operation introduced by C ABI v1.3.

use crate::{SaBufferViewV1, SaErrorBufferV1, SaMutBufferViewV1, SaStatusCodeV1};

pub const SA_ABI_V1_3: u32 = 0x0001_0003;
pub const SA_CAPABILITY_NONLINEAR_STATIC_CPU: u64 = 1 << 4;
pub const SA_NONLINEAR_STATIC_MAX_STORY_COUNT: u32 = 1_000_000;

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaNonlinearStaticConfigV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub story_count: u32,
    pub max_iter: u32,
    pub tolerance: f64,
    pub hardening_ratio: f64,
    pub line_search_decay: f64,
    pub line_search_min: f64,
    pub pdelta_factor: f64,
    pub flags: u32,
    pub reserved_u32: u32,
    pub reserved: [u64; 2],
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaNonlinearStaticResultV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub converged: u32,
    pub iterations: u32,
    pub residual_inf: f64,
    pub residual_l2: f64,
    pub max_abs_displacement_m: f64,
    pub top_displacement_m: f64,
    pub base_shear_kn: f64,
    pub plastic_story_count: u32,
    pub line_search_backtracks: u32,
    pub output_length: u64,
    pub execution_backend: u32,
    pub fallback_count: u32,
    pub reserved: u64,
}

pub type SaNonlinearStaticSolveFnV1 = unsafe extern "C" fn(
    config: *const SaNonlinearStaticConfigV1,
    story_stiffness_n_per_m: *const SaBufferViewV1,
    story_height_m: *const SaBufferViewV1,
    story_axial_n: *const SaBufferViewV1,
    story_yield_drift_m: *const SaBufferViewV1,
    floor_load_n: *const SaBufferViewV1,
    displacement_m: *const SaMutBufferViewV1,
    result: *mut SaNonlinearStaticResultV1,
    error: *mut SaErrorBufferV1,
) -> SaStatusCodeV1;

#[cfg(test)]
mod tests {
    use super::{SaNonlinearStaticConfigV1, SaNonlinearStaticResultV1};
    use core::mem::{align_of, offset_of, size_of};

    #[test]
    fn rust_nonlinear_static_layout_matches_the_public_c_header_contract() {
        assert_eq!(size_of::<SaNonlinearStaticConfigV1>(), 80);
        assert_eq!(align_of::<SaNonlinearStaticConfigV1>(), 8);
        assert_eq!(offset_of!(SaNonlinearStaticConfigV1, story_count), 8);
        assert_eq!(offset_of!(SaNonlinearStaticConfigV1, tolerance), 16);
        assert_eq!(offset_of!(SaNonlinearStaticConfigV1, pdelta_factor), 48);
        assert_eq!(offset_of!(SaNonlinearStaticConfigV1, reserved), 64);

        assert_eq!(size_of::<SaNonlinearStaticResultV1>(), 88);
        assert_eq!(align_of::<SaNonlinearStaticResultV1>(), 8);
        assert_eq!(offset_of!(SaNonlinearStaticResultV1, residual_inf), 16);
        assert_eq!(offset_of!(SaNonlinearStaticResultV1, base_shear_kn), 48);
        assert_eq!(offset_of!(SaNonlinearStaticResultV1, output_length), 64);
        assert_eq!(offset_of!(SaNonlinearStaticResultV1, execution_backend), 72);
    }
}
