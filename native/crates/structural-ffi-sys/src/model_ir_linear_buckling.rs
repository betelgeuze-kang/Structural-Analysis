//! Raw bounded typed-ModelIR `Frame3D` prestress geometric assembly introduced by C ABI v1.15.

use crate::{
    SaBufferViewV1, SaErrorBufferV1, SaModelIrHandleV1, SaMutBufferViewV1, SaStatusCodeV1,
    SaStringViewV1,
};

pub const SA_ABI_V1_15: u32 = 0x0001_000f;
pub const SA_CAPABILITY_MODEL_IR_LINEAR_BUCKLING_ASSEMBLY_CPU: u64 = 1 << 16;

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaModelIrLinearBucklingAssemblyConfigV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub load_pattern_id: SaStringViewV1,
    pub equilibrium_displacement: SaBufferViewV1,
    pub flags: u64,
    pub reserved: [u64; 2],
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaModelIrLinearBucklingAssemblyOutputsV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub active_dof_indices: SaMutBufferViewV1,
    pub row_offsets: SaMutBufferViewV1,
    pub column_indices: SaMutBufferViewV1,
    pub geometric_stiffness: SaMutBufferViewV1,
    pub frame_stable_indices: SaMutBufferViewV1,
    pub frame_axial_compression_n: SaMutBufferViewV1,
    pub model_content_hash: SaMutBufferViewV1,
    pub model_semantic_hash: SaMutBufferViewV1,
    pub model_provenance_hash: SaMutBufferViewV1,
    pub reserved: [u64; 2],
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Default)]
pub struct SaModelIrLinearBucklingAssemblyResultV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub global_dof_count: u64,
    pub active_dof_count: u64,
    pub structural_entry_count: u64,
    pub frame_prestress_count: u64,
    pub load_pattern_index: u64,
    pub equilibrium_residual_inf_n: f64,
    pub execution_backend: u32,
    pub fallback_count: u32,
    pub reserved: [u64; 2],
}

pub type SaModelIrLinearBucklingAssembleFnV1 = unsafe extern "C" fn(
    handle: *const SaModelIrHandleV1,
    config: *const SaModelIrLinearBucklingAssemblyConfigV1,
    outputs: *const SaModelIrLinearBucklingAssemblyOutputsV1,
    result: *mut SaModelIrLinearBucklingAssemblyResultV1,
    error: *mut SaErrorBufferV1,
) -> SaStatusCodeV1;

#[cfg(test)]
mod tests {
    use super::{
        SaModelIrLinearBucklingAssemblyConfigV1, SaModelIrLinearBucklingAssemblyOutputsV1,
        SaModelIrLinearBucklingAssemblyResultV1,
    };
    use core::mem::{align_of, offset_of, size_of};

    #[test]
    fn rust_model_ir_buckling_layout_matches_the_public_c_header_contract() {
        assert_eq!(size_of::<SaModelIrLinearBucklingAssemblyConfigV1>(), 96);
        assert_eq!(align_of::<SaModelIrLinearBucklingAssemblyConfigV1>(), 8);
        assert_eq!(
            offset_of!(
                SaModelIrLinearBucklingAssemblyConfigV1,
                equilibrium_displacement
            ),
            24
        );
        assert_eq!(
            offset_of!(SaModelIrLinearBucklingAssemblyConfigV1, flags),
            72
        );

        assert_eq!(size_of::<SaModelIrLinearBucklingAssemblyOutputsV1>(), 456);
        assert_eq!(
            offset_of!(SaModelIrLinearBucklingAssemblyOutputsV1, active_dof_indices),
            8
        );
        assert_eq!(
            offset_of!(
                SaModelIrLinearBucklingAssemblyOutputsV1,
                frame_stable_indices
            ),
            200
        );
        assert_eq!(
            offset_of!(SaModelIrLinearBucklingAssemblyOutputsV1, model_content_hash),
            296
        );
        assert_eq!(
            offset_of!(SaModelIrLinearBucklingAssemblyOutputsV1, reserved),
            440
        );

        assert_eq!(size_of::<SaModelIrLinearBucklingAssemblyResultV1>(), 80);
        assert_eq!(
            offset_of!(
                SaModelIrLinearBucklingAssemblyResultV1,
                equilibrium_residual_inf_n
            ),
            48
        );
        assert_eq!(
            offset_of!(SaModelIrLinearBucklingAssemblyResultV1, execution_backend),
            56
        );
        assert_eq!(
            offset_of!(SaModelIrLinearBucklingAssemblyResultV1, reserved),
            64
        );
    }
}
