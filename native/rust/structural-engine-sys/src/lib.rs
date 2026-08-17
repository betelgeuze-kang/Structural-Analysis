#![deny(unsafe_op_in_unsafe_fn)]

use core::ffi::{c_char, c_int};

pub const ABI_VERSION_MAJOR: u32 = 1;
pub const ABI_VERSION_MINOR: u32 = 0;

pub const CAPABILITY_CPU_REFERENCE: u64 = 1 << 0;
pub const CAPABILITY_HIP_BACKEND: u64 = 1 << 1;
pub const CAPABILITY_CHECKPOINT: u64 = 1 << 2;
pub const CAPABILITY_RESULT_IR: u64 = 1 << 3;

pub const EXECUTION_MODE_AUDITED: u32 = 0;
pub const EXECUTION_MODE_PERFORMANCE: u32 = 1;

#[repr(i32)]
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Status {
    Ok = 0,
    InvalidArgument = 1,
    AbiMismatch = 2,
    Unsupported = 3,
    OutOfMemory = 4,
    BufferTooSmall = 5,
    InternalError = 6,
}

impl Status {
    pub fn from_raw(value: c_int) -> Option<Self> {
        match value {
            0 => Some(Self::Ok),
            1 => Some(Self::InvalidArgument),
            2 => Some(Self::AbiMismatch),
            3 => Some(Self::Unsupported),
            4 => Some(Self::OutOfMemory),
            5 => Some(Self::BufferTooSmall),
            6 => Some(Self::InternalError),
            _ => None,
        }
    }
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct ApiInfo {
    pub struct_size: u32,
    pub abi_version_major: u32,
    pub abi_version_minor: u32,
    pub reserved_u32: u32,
    pub capability_bits: u64,
    pub implementation_name: *const c_char,
}

impl Default for ApiInfo {
    fn default() -> Self {
        Self {
            struct_size: core::mem::size_of::<Self>() as u32,
            abi_version_major: 0,
            abi_version_minor: 0,
            reserved_u32: 0,
            capability_bits: 0,
            implementation_name: core::ptr::null(),
        }
    }
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct EngineConfig {
    pub struct_size: u32,
    pub abi_version_major: u32,
    pub abi_version_minor: u32,
    pub execution_mode: u32,
    pub requested_device_index: i32,
    pub reserved_u32: [u32; 3],
}

impl Default for EngineConfig {
    fn default() -> Self {
        Self {
            struct_size: core::mem::size_of::<Self>() as u32,
            abi_version_major: ABI_VERSION_MAJOR,
            abi_version_minor: ABI_VERSION_MINOR,
            execution_mode: EXECUTION_MODE_AUDITED,
            requested_device_index: -1,
            reserved_u32: [0; 3],
        }
    }
}

#[repr(C)]
pub struct Engine {
    _private: [u8; 0],
}

#[cfg(feature = "native-link")]
#[link(name = "structural_engine_c_api", kind = "static")]
extern "C" {
    pub fn sa_get_api_info(out_info: *mut ApiInfo) -> c_int;
    pub fn sa_engine_create(config: *const EngineConfig, out_engine: *mut *mut Engine) -> c_int;
    pub fn sa_engine_destroy(engine: *mut Engine);
    pub fn sa_engine_capabilities(engine: *const Engine, out_capabilities: *mut u64) -> c_int;
    pub fn sa_engine_last_error(
        engine: *const Engine,
        buffer: *mut c_char,
        buffer_capacity: usize,
        out_required_size: *mut usize,
    ) -> c_int;
}
