//! Raw bounded ModelIR-to-NDTHA adapter introduced by C ABI v1.6.

use crate::{
    SaBufferViewV1, SaErrorBufferV1, SaModelIrHandleV1, SaMutBufferViewV1,
    SaNonlinearNdthaConfigV1, SaStatusCodeV1, SaStringViewV1,
};

pub const SA_ABI_V1_6: u32 = 0x0001_0006;
pub const SA_CAPABILITY_MODEL_IR_NDTHA_ADAPTER: u64 = 1 << 7;
pub const SA_MODEL_IR_NDTHA_ADAPTER_FIXED_GUIDED_FRAME3D_X_V1: u32 = 1;

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaModelIrNdthaAdapterRequestV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub profile: u32,
    pub flags: u32,
    pub element_id: SaStringViewV1,
    pub base_node_id: SaStringViewV1,
    pub floor_node_id: SaStringViewV1,
    pub load_pattern_id: SaStringViewV1,
    pub damping_ratio: f64,
    pub elastic_guard_yield_drift_m: f64,
    pub config: SaNonlinearNdthaConfigV1,
    pub acceleration_g: SaBufferViewV1,
    pub reserved: [u64; 2],
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaModelIrNdthaAdapterOutputsV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub story_stiffness_n_per_m: SaMutBufferViewV1,
    pub story_height_m: SaMutBufferViewV1,
    pub story_axial_n: SaMutBufferViewV1,
    pub story_yield_drift_m: SaMutBufferViewV1,
    pub story_mass_kg: SaMutBufferViewV1,
    pub story_damping_n_s_per_m: SaMutBufferViewV1,
    pub floor_load_base_n: SaMutBufferViewV1,
    pub reserved: [u64; 2],
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaModelIrNdthaAdapterResultV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub profile: u32,
    pub story_count: u32,
    pub element_index: u64,
    pub load_pattern_index: u64,
    pub story_height_m: f64,
    pub youngs_modulus_pa: f64,
    pub section_area_m2: f64,
    pub section_iy_m4: f64,
    pub story_stiffness_n_per_m: f64,
    pub story_mass_kg: f64,
    pub story_damping_n_s_per_m: f64,
    pub floor_load_base_n: f64,
    pub damping_ratio: f64,
    pub elastic_guard_yield_drift_m: f64,
    pub execution_backend: u32,
    pub fallback_count: u32,
    pub reserved: [u64; 2],
}

pub type SaModelIrNdthaAdaptFnV1 = unsafe extern "C" fn(
    handle: *const SaModelIrHandleV1,
    request: *const SaModelIrNdthaAdapterRequestV1,
    outputs: *const SaModelIrNdthaAdapterOutputsV1,
    result: *mut SaModelIrNdthaAdapterResultV1,
    error: *mut SaErrorBufferV1,
) -> SaStatusCodeV1;

#[cfg(test)]
mod tests {
    use super::{
        SaModelIrNdthaAdapterOutputsV1, SaModelIrNdthaAdapterRequestV1,
        SaModelIrNdthaAdapterResultV1,
    };
    use core::mem::{align_of, offset_of, size_of};

    #[test]
    fn rust_adapter_layout_matches_the_public_c_header_contract() {
        assert_eq!(size_of::<SaModelIrNdthaAdapterRequestV1>(), 304);
        assert_eq!(align_of::<SaModelIrNdthaAdapterRequestV1>(), 8);
        assert_eq!(offset_of!(SaModelIrNdthaAdapterRequestV1, element_id), 16);
        assert_eq!(
            offset_of!(SaModelIrNdthaAdapterRequestV1, damping_ratio),
            80
        );
        assert_eq!(offset_of!(SaModelIrNdthaAdapterRequestV1, config), 96);
        assert_eq!(
            offset_of!(SaModelIrNdthaAdapterRequestV1, acceleration_g),
            240
        );
        assert_eq!(offset_of!(SaModelIrNdthaAdapterRequestV1, reserved), 288);

        assert_eq!(size_of::<SaModelIrNdthaAdapterOutputsV1>(), 360);
        assert_eq!(align_of::<SaModelIrNdthaAdapterOutputsV1>(), 8);
        assert_eq!(
            offset_of!(SaModelIrNdthaAdapterOutputsV1, story_stiffness_n_per_m),
            8
        );
        assert_eq!(
            offset_of!(SaModelIrNdthaAdapterOutputsV1, floor_load_base_n),
            296
        );
        assert_eq!(offset_of!(SaModelIrNdthaAdapterOutputsV1, reserved), 344);

        assert_eq!(size_of::<SaModelIrNdthaAdapterResultV1>(), 136);
        assert_eq!(align_of::<SaModelIrNdthaAdapterResultV1>(), 8);
        assert_eq!(offset_of!(SaModelIrNdthaAdapterResultV1, element_index), 16);
        assert_eq!(
            offset_of!(SaModelIrNdthaAdapterResultV1, story_height_m),
            32
        );
        assert_eq!(
            offset_of!(SaModelIrNdthaAdapterResultV1, execution_backend),
            112
        );
        assert_eq!(offset_of!(SaModelIrNdthaAdapterResultV1, reserved), 120);
    }
}
