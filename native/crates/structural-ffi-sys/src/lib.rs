//! Raw C ABI v1 declarations.

#[cfg(not(all(target_pointer_width = "64", target_endian = "little")))]
compile_error!("structural C ABI v1 requires a 64-bit little-endian target");

use core::ffi::{c_char, c_void};

pub mod legacy_runtime_v3;
mod model_ir;
pub use model_ir::*;
mod nonlinear_static;
pub use nonlinear_static::*;
mod nonlinear_ndtha;
pub use nonlinear_ndtha::*;
mod track;
pub use track::*;

pub type SaStatusCodeV1 = u32;

pub const SA_ABI_V1_0: u32 = 0x0001_0000;
pub const SA_ABI_V1_CURRENT: u32 = SA_ABI_V1_5;
pub const SA_OK: SaStatusCodeV1 = 0;
pub const SA_ERR_INVALID_ARGUMENT: SaStatusCodeV1 = 1000;
pub const SA_ERR_ABI_VERSION_MISMATCH: SaStatusCodeV1 = 1001;
pub const SA_ERR_STRUCT_SIZE: SaStatusCodeV1 = 1002;
pub const SA_ERR_BUFFER_TOO_SMALL: SaStatusCodeV1 = 1003;
pub const SA_ERR_SCHEMA_INVALID: SaStatusCodeV1 = 1100;
pub const SA_ERR_SEMANTIC_INVALID: SaStatusCodeV1 = 1101;
pub const SA_ERR_ANALYSIS_NOT_READY: SaStatusCodeV1 = 1102;
pub const SA_ERR_UNSUPPORTED: SaStatusCodeV1 = 1200;
pub const SA_ERR_STATE_CONFLICT: SaStatusCodeV1 = 1300;
pub const SA_ERR_CHECKPOINT_MISMATCH: SaStatusCodeV1 = 1301;
pub const SA_ERR_BACKEND_UNAVAILABLE: SaStatusCodeV1 = 1400;
pub const SA_ERR_DEVICE_MISMATCH: SaStatusCodeV1 = 1401;
pub const SA_ERR_FALLBACK_FORBIDDEN: SaStatusCodeV1 = 1402;
pub const SA_ERR_CANCELLED: SaStatusCodeV1 = 1500;
pub const SA_ERR_NONCONVERGENCE: SaStatusCodeV1 = 1600;
pub const SA_ERR_INTERNAL: SaStatusCodeV1 = 1900;

pub const SA_ELEMENT_TYPE_F64: u32 = 1;
pub const SA_ELEMENT_TYPE_U64: u32 = 2;
pub const SA_ELEMENT_TYPE_I32: u32 = 3;
pub const SA_ELEMENT_TYPE_U8: u32 = 4;
pub const SA_ELEMENT_TYPE_U32: u32 = 5;
pub const SA_MEMORY_SPACE_HOST: u32 = 0;
pub const SA_MEMORY_SPACE_DEVICE: u32 = 1;
pub const SA_CAPABILITY_BUFFER_VALIDATION: u64 = 1;

#[repr(C)]
#[derive(Clone, Copy, Debug, Default)]
pub struct SaHeaderV1 {
    pub abi_version: u32,
    pub struct_size: u32,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaBufferViewV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub data: *const c_void,
    pub length: u64,
    pub stride_bytes: u64,
    pub element_type: u32,
    pub memory_space: u32,
    pub device_id: i32,
    pub flags: u32,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaErrorBufferV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub data: *mut c_char,
    pub capacity: u64,
    pub required: u64,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaApiRequestV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub flags: u64,
    pub reserved: [u64; 3],
}

pub type SaValidateBufferViewFnV1 = unsafe extern "C" fn(
    view: *const SaBufferViewV1,
    error: *mut SaErrorBufferV1,
) -> SaStatusCodeV1;

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaApiV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub capabilities: u64,
    pub validate_buffer_view: Option<SaValidateBufferViewFnV1>,
    pub model_ir_create: Option<SaModelIrCreateFnV1>,
    pub model_ir_destroy: Option<SaModelIrDestroyFnV1>,
    pub model_ir_validation_report_size: Option<SaModelIrValidationReportSizeFnV1>,
    pub model_ir_validation_report_write: Option<SaModelIrValidationReportWriteFnV1>,
    pub model_ir_snapshot_size: Option<SaModelIrSnapshotSizeFnV1>,
    pub model_ir_snapshot_write: Option<SaModelIrSnapshotWriteFnV1>,
    pub track_point_load_solve: Option<SaTrackPointLoadSolveFnV1>,
    pub nonlinear_static_solve: Option<SaNonlinearStaticSolveFnV1>,
    pub nonlinear_ndtha_solve: Option<SaNonlinearNdthaSolveFnV1>,
    pub nonlinear_ndtha_advance: Option<SaNonlinearNdthaAdvanceFnV1>,
    pub reserved: [*const c_void; 3],
}

impl Default for SaApiV1 {
    fn default() -> Self {
        Self {
            abi_version: 0,
            struct_size: u32::try_from(core::mem::size_of::<Self>()).unwrap_or(u32::MAX),
            capabilities: 0,
            validate_buffer_view: None,
            model_ir_create: None,
            model_ir_destroy: None,
            model_ir_validation_report_size: None,
            model_ir_validation_report_write: None,
            model_ir_snapshot_size: None,
            model_ir_snapshot_write: None,
            track_point_load_solve: None,
            nonlinear_static_solve: None,
            nonlinear_ndtha_solve: None,
            nonlinear_ndtha_advance: None,
            reserved: [core::ptr::null(); 3],
        }
    }
}

extern "C" {
    pub fn sa_get_api_v1(
        request: *const SaApiRequestV1,
        out_api: *mut SaApiV1,
        error: *mut SaErrorBufferV1,
    ) -> SaStatusCodeV1;
}

#[cfg(test)]
mod tests {
    use super::{
        SaApiRequestV1, SaApiV1, SaBufferViewV1, SaErrorBufferV1, SaHeaderV1, SA_ERR_NONCONVERGENCE,
    };
    use core::mem::{align_of, offset_of, size_of};

    #[test]
    fn rust_layout_matches_the_public_c_header_contract() {
        assert_eq!(size_of::<SaHeaderV1>(), 8);
        assert_eq!(align_of::<SaHeaderV1>(), 4);
        assert_eq!(size_of::<SaBufferViewV1>(), 48);
        assert_eq!(offset_of!(SaBufferViewV1, data), 8);
        assert_eq!(offset_of!(SaBufferViewV1, length), 16);
        assert_eq!(offset_of!(SaBufferViewV1, flags), 44);
        assert_eq!(size_of::<SaErrorBufferV1>(), 32);
        assert_eq!(offset_of!(SaErrorBufferV1, required), 24);
        assert_eq!(size_of::<SaApiRequestV1>(), 40);
        assert_eq!(offset_of!(SaApiRequestV1, reserved), 16);
        assert_eq!(size_of::<SaApiV1>(), 128);
        assert_eq!(offset_of!(SaApiV1, validate_buffer_view), 16);
        assert_eq!(offset_of!(SaApiV1, model_ir_create), 24);
        assert_eq!(offset_of!(SaApiV1, model_ir_snapshot_write), 64);
        assert_eq!(offset_of!(SaApiV1, track_point_load_solve), 72);
        assert_eq!(offset_of!(SaApiV1, nonlinear_static_solve), 80);
        assert_eq!(offset_of!(SaApiV1, nonlinear_ndtha_solve), 88);
        assert_eq!(offset_of!(SaApiV1, nonlinear_ndtha_advance), 96);
        assert_eq!(offset_of!(SaApiV1, reserved), 104);
        assert_eq!(SA_ERR_NONCONVERGENCE, 1600);
    }
}
