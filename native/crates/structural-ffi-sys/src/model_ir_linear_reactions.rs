//! Raw bounded typed-ModelIR constrained-reaction operation introduced by C ABI v1.14.

use crate::{
    SaBufferViewV1, SaErrorBufferV1, SaModelIrHandleV1, SaMutBufferViewV1, SaStatusCodeV1,
    SaStringViewV1,
};

pub const SA_ABI_V1_14: u32 = 0x0001_000e;
pub const SA_CAPABILITY_MODEL_IR_LINEAR_REACTIONS_CPU: u64 = 1 << 15;

#[repr(C)]
#[derive(Clone, Copy, Debug, Default)]
pub struct SaModelIrLinearReactionSizesV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub global_dof_count: u64,
    pub constrained_dof_count: u64,
    pub model_identity_length: u64,
    pub reserved: [u64; 3],
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaModelIrLinearReactionConfigV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub load_pattern_id: SaStringViewV1,
    pub displacement: SaBufferViewV1,
    pub flags: u64,
    pub reserved: [u64; 2],
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaModelIrLinearReactionOutputsV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub constrained_dof_indices: SaMutBufferViewV1,
    pub constrained_internal_force: SaMutBufferViewV1,
    pub constrained_external_load: SaMutBufferViewV1,
    pub reactions: SaMutBufferViewV1,
    pub model_content_hash: SaMutBufferViewV1,
    pub model_semantic_hash: SaMutBufferViewV1,
    pub model_provenance_hash: SaMutBufferViewV1,
    pub reserved: [u64; 2],
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Default)]
pub struct SaModelIrLinearReactionResultV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub global_dof_count: u64,
    pub constrained_dof_count: u64,
    pub load_pattern_index: u64,
    pub execution_backend: u32,
    pub fallback_count: u32,
    pub reserved: [u64; 2],
}

pub type SaModelIrLinearReactionSizesFnV1 = unsafe extern "C" fn(
    handle: *const SaModelIrHandleV1,
    sizes: *mut SaModelIrLinearReactionSizesV1,
    error: *mut SaErrorBufferV1,
) -> SaStatusCodeV1;

pub type SaModelIrLinearReactionsFnV1 = unsafe extern "C" fn(
    handle: *const SaModelIrHandleV1,
    config: *const SaModelIrLinearReactionConfigV1,
    outputs: *const SaModelIrLinearReactionOutputsV1,
    result: *mut SaModelIrLinearReactionResultV1,
    error: *mut SaErrorBufferV1,
) -> SaStatusCodeV1;

#[cfg(test)]
mod tests {
    use super::{
        SaModelIrLinearReactionConfigV1, SaModelIrLinearReactionOutputsV1,
        SaModelIrLinearReactionResultV1, SaModelIrLinearReactionSizesV1,
    };
    use core::mem::{align_of, offset_of, size_of};

    #[test]
    fn rust_model_ir_linear_reaction_layout_matches_the_public_c_header_contract() {
        assert_eq!(size_of::<SaModelIrLinearReactionSizesV1>(), 56);
        assert_eq!(align_of::<SaModelIrLinearReactionSizesV1>(), 8);
        assert_eq!(
            offset_of!(SaModelIrLinearReactionSizesV1, global_dof_count),
            8
        );
        assert_eq!(offset_of!(SaModelIrLinearReactionSizesV1, reserved), 32);

        assert_eq!(size_of::<SaModelIrLinearReactionConfigV1>(), 96);
        assert_eq!(
            offset_of!(SaModelIrLinearReactionConfigV1, load_pattern_id),
            8
        );
        assert_eq!(
            offset_of!(SaModelIrLinearReactionConfigV1, displacement),
            24
        );
        assert_eq!(offset_of!(SaModelIrLinearReactionConfigV1, flags), 72);
        assert_eq!(offset_of!(SaModelIrLinearReactionConfigV1, reserved), 80);

        assert_eq!(size_of::<SaModelIrLinearReactionOutputsV1>(), 360);
        assert_eq!(
            offset_of!(SaModelIrLinearReactionOutputsV1, constrained_dof_indices),
            8
        );
        assert_eq!(
            offset_of!(SaModelIrLinearReactionOutputsV1, model_content_hash),
            200
        );
        assert_eq!(offset_of!(SaModelIrLinearReactionOutputsV1, reserved), 344);

        assert_eq!(size_of::<SaModelIrLinearReactionResultV1>(), 56);
        assert_eq!(
            offset_of!(SaModelIrLinearReactionResultV1, global_dof_count),
            8
        );
        assert_eq!(
            offset_of!(SaModelIrLinearReactionResultV1, execution_backend),
            32
        );
        assert_eq!(offset_of!(SaModelIrLinearReactionResultV1, reserved), 40);
    }
}
