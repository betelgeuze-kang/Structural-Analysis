//! Raw bounded typed-ModelIR linear assembly operation introduced by C ABI v1.13.

use crate::{
    SaBufferViewV1, SaErrorBufferV1, SaModelIrHandleV1, SaMutBufferViewV1, SaStatusCodeV1,
    SaStringViewV1,
};

pub const SA_ABI_V1_13: u32 = 0x0001_000d;
pub const SA_CAPABILITY_MODEL_IR_LINEAR_ASSEMBLY_CPU: u64 = 1 << 14;
pub const SA_MODEL_IR_LINEAR_MAX_GLOBAL_DOF_COUNT: u64 = 1_000_000;
pub const SA_MODEL_IR_LINEAR_MAX_STRUCTURAL_ENTRIES: u64 = 100_000_000;
pub const SA_MODEL_IR_LINEAR_MAX_RECOVERY_RECORD_COUNT: u64 = 1_000_000;

#[repr(C)]
#[derive(Clone, Copy, Debug, Default)]
pub struct SaModelIrLinearAssemblySizesV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub global_dof_count: u64,
    pub active_dof_count: u64,
    pub row_offset_count: u64,
    pub structural_entry_count: u64,
    pub recovery_record_count: u64,
    pub recovery_offset_count: u64,
    pub recovery_value_count: u64,
    pub model_identity_length: u64,
    pub reserved: [u64; 2],
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaModelIrLinearAssemblyConfigV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub load_pattern_id: SaStringViewV1,
    pub displacement: SaBufferViewV1,
    pub direction: SaBufferViewV1,
    pub flags: u64,
    pub reserved: [u64; 2],
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaModelIrLinearAssemblyOutputsV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub active_dof_indices: SaMutBufferViewV1,
    pub row_offsets: SaMutBufferViewV1,
    pub column_indices: SaMutBufferViewV1,
    pub tangent: SaMutBufferViewV1,
    pub consistent_mass: SaMutBufferViewV1,
    pub internal_force: SaMutBufferViewV1,
    pub external_load: SaMutBufferViewV1,
    pub equilibrium_residual: SaMutBufferViewV1,
    pub jvp: SaMutBufferViewV1,
    pub recovery_stable_indices: SaMutBufferViewV1,
    pub recovery_element_types: SaMutBufferViewV1,
    pub recovery_offsets: SaMutBufferViewV1,
    pub recovery_values: SaMutBufferViewV1,
    pub model_content_hash: SaMutBufferViewV1,
    pub model_semantic_hash: SaMutBufferViewV1,
    pub model_provenance_hash: SaMutBufferViewV1,
    pub reserved: [u64; 2],
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Default)]
pub struct SaModelIrLinearAssemblyResultV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub global_dof_count: u64,
    pub active_dof_count: u64,
    pub row_offset_count: u64,
    pub structural_entry_count: u64,
    pub recovery_record_count: u64,
    pub recovery_value_count: u64,
    pub load_pattern_index: u64,
    pub execution_backend: u32,
    pub fallback_count: u32,
    pub reserved: [u64; 2],
}

pub type SaModelIrLinearAssemblySizesFnV1 = unsafe extern "C" fn(
    handle: *const SaModelIrHandleV1,
    sizes: *mut SaModelIrLinearAssemblySizesV1,
    error: *mut SaErrorBufferV1,
) -> SaStatusCodeV1;

pub type SaModelIrLinearAssembleFnV1 = unsafe extern "C" fn(
    handle: *const SaModelIrHandleV1,
    config: *const SaModelIrLinearAssemblyConfigV1,
    outputs: *const SaModelIrLinearAssemblyOutputsV1,
    result: *mut SaModelIrLinearAssemblyResultV1,
    error: *mut SaErrorBufferV1,
) -> SaStatusCodeV1;

#[cfg(test)]
mod tests {
    use super::{
        SaModelIrLinearAssemblyConfigV1, SaModelIrLinearAssemblyOutputsV1,
        SaModelIrLinearAssemblyResultV1, SaModelIrLinearAssemblySizesV1,
        SA_MODEL_IR_LINEAR_MAX_GLOBAL_DOF_COUNT, SA_MODEL_IR_LINEAR_MAX_RECOVERY_RECORD_COUNT,
        SA_MODEL_IR_LINEAR_MAX_STRUCTURAL_ENTRIES,
    };
    use core::mem::{align_of, offset_of, size_of};

    #[test]
    fn rust_model_ir_linear_assembly_layout_matches_the_public_c_header_contract() {
        assert_eq!(SA_MODEL_IR_LINEAR_MAX_GLOBAL_DOF_COUNT, 1_000_000);
        assert_eq!(SA_MODEL_IR_LINEAR_MAX_STRUCTURAL_ENTRIES, 100_000_000);
        assert_eq!(SA_MODEL_IR_LINEAR_MAX_RECOVERY_RECORD_COUNT, 1_000_000);
        assert_eq!(size_of::<SaModelIrLinearAssemblySizesV1>(), 88);
        assert_eq!(align_of::<SaModelIrLinearAssemblySizesV1>(), 8);
        assert_eq!(
            offset_of!(SaModelIrLinearAssemblySizesV1, global_dof_count),
            8
        );
        assert_eq!(offset_of!(SaModelIrLinearAssemblySizesV1, reserved), 72);

        assert_eq!(size_of::<SaModelIrLinearAssemblyConfigV1>(), 144);
        assert_eq!(
            offset_of!(SaModelIrLinearAssemblyConfigV1, load_pattern_id),
            8
        );
        assert_eq!(
            offset_of!(SaModelIrLinearAssemblyConfigV1, displacement),
            24
        );
        assert_eq!(offset_of!(SaModelIrLinearAssemblyConfigV1, direction), 72);
        assert_eq!(offset_of!(SaModelIrLinearAssemblyConfigV1, flags), 120);
        assert_eq!(offset_of!(SaModelIrLinearAssemblyConfigV1, reserved), 128);

        assert_eq!(size_of::<SaModelIrLinearAssemblyOutputsV1>(), 792);
        assert_eq!(
            offset_of!(SaModelIrLinearAssemblyOutputsV1, active_dof_indices),
            8
        );
        assert_eq!(offset_of!(SaModelIrLinearAssemblyOutputsV1, tangent), 152);
        assert_eq!(
            offset_of!(SaModelIrLinearAssemblyOutputsV1, recovery_stable_indices),
            440
        );
        assert_eq!(
            offset_of!(SaModelIrLinearAssemblyOutputsV1, model_content_hash),
            632
        );
        assert_eq!(offset_of!(SaModelIrLinearAssemblyOutputsV1, reserved), 776);

        assert_eq!(size_of::<SaModelIrLinearAssemblyResultV1>(), 88);
        assert_eq!(
            offset_of!(SaModelIrLinearAssemblyResultV1, global_dof_count),
            8
        );
        assert_eq!(
            offset_of!(SaModelIrLinearAssemblyResultV1, load_pattern_index),
            56
        );
        assert_eq!(
            offset_of!(SaModelIrLinearAssemblyResultV1, execution_backend),
            64
        );
        assert_eq!(offset_of!(SaModelIrLinearAssemblyResultV1, reserved), 72);
    }
}
