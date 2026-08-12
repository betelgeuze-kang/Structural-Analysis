//! Raw ABI v1.12 product-backend selector and bounded full-residual context.

use crate::{SaBufferViewV1, SaErrorBufferV1, SaMutBufferViewV1, SaStatusCodeV1};
use core::ffi::c_char;

pub const SA_ABI_V1_12: u32 = 0x0001_000c;
pub const SA_CAPABILITY_BACKEND_SELECTOR: u64 = 1 << 13;
pub const SA_BACKEND_CAPABILITY_FULL_RESIDUAL: u64 = 1;
pub const SA_FULL_RESIDUAL_EVAL_BUFFERS_REUSED: u32 = 1;
pub const SA_FULL_RESIDUAL_OPERATOR_DEVICE_RESIDENT: u32 = 2;
pub const SA_FULL_RESIDUAL_FP64: u32 = 4;
pub const SA_FULL_RESIDUAL_DETERMINISTIC: u32 = 8;

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaBackendRequestV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub execution_backend: u32,
    pub device_id: i32,
    pub flags: u64,
    pub reserved: [u64; 2],
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaFullResidualOperatorV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub frame_dofs: SaBufferViewV1,
    pub frame_stiffness: SaBufferViewV1,
    pub shell_row_offsets: SaBufferViewV1,
    pub shell_column_indices: SaBufferViewV1,
    pub shell_values: SaBufferViewV1,
    pub spring_row_offsets: SaBufferViewV1,
    pub spring_column_indices: SaBufferViewV1,
    pub spring_values: SaBufferViewV1,
    pub external_force: SaBufferViewV1,
    pub free_dofs: SaBufferViewV1,
    pub frame_element_count: u64,
    pub order: u64,
    pub shell_nonzeros: u64,
    pub spring_nonzeros: u64,
    pub free_dof_count: u64,
    pub reserved: [u64; 2],
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaFullResidualEvalConfigV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub batch_size: u64,
    pub repetitions: u32,
    pub flags: u32,
    pub reserved: [u64; 2],
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Default)]
pub struct SaFullResidualStatusV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub solver_status: u32,
    pub execution_backend: u32,
    pub fallback_count: u32,
    pub flags: u32,
    pub device_id: i32,
    pub reserved_u32: u32,
    pub frame_element_count: u64,
    pub order: u64,
    pub free_dof_count: u64,
    pub shell_nonzeros: u64,
    pub spring_nonzeros: u64,
    pub batch_size: u64,
    pub repetitions: u32,
    pub reserved_repetitions: u32,
    pub h2d_bytes: u64,
    pub d2h_bytes: u64,
    pub h2d_transfer_count: u64,
    pub d2h_transfer_count: u64,
    pub synchronization_count: u64,
    pub kernel_launch_count: u64,
    pub device_buffer_bytes: u64,
    pub vram_total_bytes: u64,
    pub vram_free_before_bytes: u64,
    pub vram_free_after_bytes: u64,
    pub kernel_elapsed_ms_total: f64,
    pub kernel_elapsed_ms_mean: f64,
    pub output_abs_sum: f64,
    pub output_max_abs: f64,
    pub reserved: [u64; 2],
}

#[repr(C)]
pub struct SaFullResidualContextV1 {
    _private: [u8; 0],
}

pub type SaFullResidualCreateFnV1 = unsafe extern "C" fn(
    operator_descriptor: *const SaFullResidualOperatorV1,
    out_context: *mut *mut SaFullResidualContextV1,
    status: *mut SaFullResidualStatusV1,
    error: *mut SaErrorBufferV1,
) -> SaStatusCodeV1;

pub type SaFullResidualEvaluateFnV1 = unsafe extern "C" fn(
    context: *mut SaFullResidualContextV1,
    config: *const SaFullResidualEvalConfigV1,
    states: *const SaBufferViewV1,
    residual: *const SaMutBufferViewV1,
    status: *mut SaFullResidualStatusV1,
    error: *mut SaErrorBufferV1,
) -> SaStatusCodeV1;

pub type SaFullResidualDestroyFnV1 = unsafe extern "C" fn(
    context: *mut SaFullResidualContextV1,
    error: *mut SaErrorBufferV1,
) -> SaStatusCodeV1;

pub type SaFullResidualDeviceNameSizeFnV1 = unsafe extern "C" fn(
    context: *const SaFullResidualContextV1,
    out_size: *mut u64,
    error: *mut SaErrorBufferV1,
) -> SaStatusCodeV1;

pub type SaFullResidualDeviceNameWriteFnV1 = unsafe extern "C" fn(
    context: *const SaFullResidualContextV1,
    output: *mut c_char,
    capacity: u64,
    error: *mut SaErrorBufferV1,
) -> SaStatusCodeV1;

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaBackendApiV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub execution_backend: u32,
    pub device_id: i32,
    pub capabilities: u64,
    pub full_residual_create: Option<SaFullResidualCreateFnV1>,
    pub full_residual_evaluate: Option<SaFullResidualEvaluateFnV1>,
    pub full_residual_destroy: Option<SaFullResidualDestroyFnV1>,
    pub full_residual_device_name_size: Option<SaFullResidualDeviceNameSizeFnV1>,
    pub full_residual_device_name_write: Option<SaFullResidualDeviceNameWriteFnV1>,
    pub reserved: [u64; 2],
}

impl Default for SaBackendApiV1 {
    fn default() -> Self {
        Self {
            abi_version: 0,
            struct_size: u32::try_from(core::mem::size_of::<Self>()).unwrap_or(u32::MAX),
            execution_backend: 0,
            device_id: 0,
            capabilities: 0,
            full_residual_create: None,
            full_residual_evaluate: None,
            full_residual_destroy: None,
            full_residual_device_name_size: None,
            full_residual_device_name_write: None,
            reserved: [0; 2],
        }
    }
}

pub type SaBackendGetApiFnV1 = unsafe extern "C" fn(
    request: *const SaBackendRequestV1,
    out_api: *mut SaBackendApiV1,
    error: *mut SaErrorBufferV1,
) -> SaStatusCodeV1;
