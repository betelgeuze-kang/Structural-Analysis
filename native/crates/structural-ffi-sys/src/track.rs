//! Raw deterministic track point-load CPU operation introduced by C ABI v1.2.

use core::ffi::c_void;

use crate::{SaErrorBufferV1, SaStatusCodeV1};

pub const SA_ABI_V1_2: u32 = 0x0001_0002;
pub const SA_ABI_V1_CURRENT: u32 = SA_ABI_V1_2;

pub const SA_CAPABILITY_TRACK_POINT_LOAD_CPU: u64 = 1 << 3;
pub const SA_TRACK_POINT_LOAD_MAX_NODE_COUNT: u32 = 1_000_000;

pub const SA_TRACK_SUPPORT_PINNED: u32 = 0;
pub const SA_TRACK_SUPPORT_FIXED: u32 = 1;
pub const SA_TRACK_THEORY_EULER: u32 = 0;
pub const SA_TRACK_THEORY_TIMOSHENKO_REDUCED: u32 = 1;
pub const SA_EXECUTION_BACKEND_CPU: u32 = 1;
pub const SA_EXECUTION_BACKEND_HIP: u32 = 2;

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaMutBufferViewV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub data: *mut c_void,
    pub length: u64,
    pub stride_bytes: u64,
    pub element_type: u32,
    pub memory_space: u32,
    pub device_id: i32,
    pub flags: u32,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaTrackPointLoadConfigV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub length_m: f64,
    pub node_count: u32,
    pub support_type: u32,
    pub theory: u32,
    pub flags: u32,
    pub bending_stiffness_n_m2: f64,
    pub shear_stiffness_n: f64,
    pub winkler_k_n_per_m2: f64,
    pub pasternak_g_n: f64,
    pub tolerance: f64,
    pub cg_max_iter: u32,
    pub reserved_u32: u32,
    pub point_force_n: f64,
    pub point_position_m: f64,
    pub reserved: [u64; 2],
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaTrackPointLoadResultV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub converged: u32,
    pub iterations: u32,
    pub residual_inf: f64,
    pub max_abs_displacement_m: f64,
    pub mid_displacement_m: f64,
    pub output_length: u64,
    pub execution_backend: u32,
    pub fallback_count: u32,
    pub reserved: u64,
}

pub type SaTrackPointLoadSolveFnV1 = unsafe extern "C" fn(
    config: *const SaTrackPointLoadConfigV1,
    displacement_m: *const SaMutBufferViewV1,
    rotation_rad: *const SaMutBufferViewV1,
    result: *mut SaTrackPointLoadResultV1,
    error: *mut SaErrorBufferV1,
) -> SaStatusCodeV1;

#[cfg(test)]
mod tests {
    use super::{SaMutBufferViewV1, SaTrackPointLoadConfigV1, SaTrackPointLoadResultV1};
    use core::mem::{align_of, offset_of, size_of};

    #[test]
    fn rust_track_layout_matches_the_public_c_header_contract() {
        assert_eq!(size_of::<SaMutBufferViewV1>(), 48);
        assert_eq!(align_of::<SaMutBufferViewV1>(), 8);
        assert_eq!(offset_of!(SaMutBufferViewV1, data), 8);
        assert_eq!(offset_of!(SaMutBufferViewV1, flags), 44);

        assert_eq!(size_of::<SaTrackPointLoadConfigV1>(), 112);
        assert_eq!(align_of::<SaTrackPointLoadConfigV1>(), 8);
        assert_eq!(offset_of!(SaTrackPointLoadConfigV1, length_m), 8);
        assert_eq!(
            offset_of!(SaTrackPointLoadConfigV1, bending_stiffness_n_m2),
            32
        );
        assert_eq!(offset_of!(SaTrackPointLoadConfigV1, point_force_n), 80);
        assert_eq!(offset_of!(SaTrackPointLoadConfigV1, reserved), 96);

        assert_eq!(size_of::<SaTrackPointLoadResultV1>(), 64);
        assert_eq!(align_of::<SaTrackPointLoadResultV1>(), 8);
        assert_eq!(offset_of!(SaTrackPointLoadResultV1, residual_inf), 16);
        assert_eq!(offset_of!(SaTrackPointLoadResultV1, output_length), 40);
        assert_eq!(offset_of!(SaTrackPointLoadResultV1, execution_backend), 48);
    }
}
