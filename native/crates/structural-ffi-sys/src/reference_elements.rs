//! Raw bounded reference material/element operation introduced by C ABI v1.7.

use crate::{SaBufferViewV1, SaErrorBufferV1, SaMutBufferViewV1, SaStatusCodeV1};

pub const SA_ABI_V1_7: u32 = 0x0001_0007;
pub const SA_CAPABILITY_REFERENCE_ELEMENTS_CPU: u64 = 1 << 8;
pub const SA_REFERENCE_ELEMENT_TRUSS3D: u32 = 1;
pub const SA_REFERENCE_ELEMENT_FRAME3D: u32 = 2;
pub const SA_REFERENCE_ELEMENT_SHELL3_MEMBRANE: u32 = 3;

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaReferenceElementConfigV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub kind: u32,
    pub flags: u32,
    pub youngs_modulus_pa: f64,
    pub poisson_ratio: f64,
    pub density_kg_per_m3: f64,
    pub area_m2: f64,
    pub iy_m4: f64,
    pub iz_m4: f64,
    pub torsional_constant_m4: f64,
    pub thickness_m: f64,
    pub local_axis_rotation_rad: f64,
    pub node_coordinates_m: SaBufferViewV1,
    pub displacement: SaBufferViewV1,
    pub direction: SaBufferViewV1,
    pub reserved: [u64; 2],
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaReferenceElementOutputsV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub tangent: SaMutBufferViewV1,
    pub consistent_mass: SaMutBufferViewV1,
    pub residual: SaMutBufferViewV1,
    pub jvp: SaMutBufferViewV1,
    pub recovery: SaMutBufferViewV1,
    pub reserved: [u64; 2],
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaReferenceElementResultV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub kind: u32,
    pub dof_count: u32,
    pub recovery_count: u32,
    pub execution_backend: u32,
    pub fallback_count: u32,
    pub reserved_u32: u32,
    pub output_matrix_length: u64,
    pub reserved: [u64; 2],
}

pub type SaReferenceElementEvaluateFnV1 = unsafe extern "C" fn(
    config: *const SaReferenceElementConfigV1,
    outputs: *const SaReferenceElementOutputsV1,
    result: *mut SaReferenceElementResultV1,
    error: *mut SaErrorBufferV1,
) -> SaStatusCodeV1;

#[cfg(test)]
mod tests {
    use super::{
        SaReferenceElementConfigV1, SaReferenceElementOutputsV1, SaReferenceElementResultV1,
    };
    use core::mem::{align_of, offset_of, size_of};

    #[test]
    fn rust_reference_element_layout_matches_the_public_c_header_contract() {
        assert_eq!(size_of::<SaReferenceElementConfigV1>(), 248);
        assert_eq!(align_of::<SaReferenceElementConfigV1>(), 8);
        assert_eq!(
            offset_of!(SaReferenceElementConfigV1, youngs_modulus_pa),
            16
        );
        assert_eq!(
            offset_of!(SaReferenceElementConfigV1, node_coordinates_m),
            88
        );
        assert_eq!(offset_of!(SaReferenceElementConfigV1, reserved), 232);
        assert_eq!(size_of::<SaReferenceElementOutputsV1>(), 264);
        assert_eq!(offset_of!(SaReferenceElementOutputsV1, tangent), 8);
        assert_eq!(offset_of!(SaReferenceElementOutputsV1, recovery), 200);
        assert_eq!(offset_of!(SaReferenceElementOutputsV1, reserved), 248);
        assert_eq!(size_of::<SaReferenceElementResultV1>(), 56);
        assert_eq!(
            offset_of!(SaReferenceElementResultV1, output_matrix_length),
            32
        );
        assert_eq!(offset_of!(SaReferenceElementResultV1, reserved), 40);
    }
}
