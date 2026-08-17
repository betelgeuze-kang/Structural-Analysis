#![deny(unsafe_op_in_unsafe_fn)]

use core::ffi::c_char;

pub const ABI_VERSION_MAJOR: u32 = 1;
pub const ABI_VERSION_MINOR: u32 = 1;

pub const CAPABILITY_CPU_REFERENCE: u64 = 1 << 0;
pub const CAPABILITY_HIP_BACKEND: u64 = 1 << 1;
pub const CAPABILITY_CHECKPOINT: u64 = 1 << 2;
pub const CAPABILITY_RESULT_IR: u64 = 1 << 3;
pub const CAPABILITY_LINEAR_FRAME3D: u64 = 1 << 4;

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
    SingularSystem = 7,
}

impl Status {
    pub fn from_raw(value: i32) -> Option<Self> {
        match value {
            0 => Some(Self::Ok),
            1 => Some(Self::InvalidArgument),
            2 => Some(Self::AbiMismatch),
            3 => Some(Self::Unsupported),
            4 => Some(Self::OutOfMemory),
            5 => Some(Self::BufferTooSmall),
            6 => Some(Self::InternalError),
            7 => Some(Self::SingularSystem),
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
#[derive(Clone, Copy, Debug, Default)]
pub struct LinearFrame3DNode {
    pub struct_size: u32,
    pub reserved_u32: u32,
    pub x_m: f64,
    pub y_m: f64,
    pub z_m: f64,
}

impl LinearFrame3DNode {
    pub fn new(x_m: f64, y_m: f64, z_m: f64) -> Self {
        Self {
            struct_size: core::mem::size_of::<Self>() as u32,
            reserved_u32: 0,
            x_m,
            y_m,
            z_m,
        }
    }
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Default)]
pub struct LinearFrame3DSection {
    pub struct_size: u32,
    pub reserved_u32: u32,
    pub area_m2: f64,
    pub elastic_modulus_kn_per_m2: f64,
    pub shear_modulus_kn_per_m2: f64,
    pub iy_m4: f64,
    pub iz_m4: f64,
    pub j_m4: f64,
    pub effective_shear_area_y_m2: f64,
    pub effective_shear_area_z_m2: f64,
}

impl LinearFrame3DSection {
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        area_m2: f64,
        elastic_modulus_kn_per_m2: f64,
        shear_modulus_kn_per_m2: f64,
        iy_m4: f64,
        iz_m4: f64,
        j_m4: f64,
        effective_shear_area_y_m2: f64,
        effective_shear_area_z_m2: f64,
    ) -> Self {
        Self {
            struct_size: core::mem::size_of::<Self>() as u32,
            reserved_u32: 0,
            area_m2,
            elastic_modulus_kn_per_m2,
            shear_modulus_kn_per_m2,
            iy_m4,
            iz_m4,
            j_m4,
            effective_shear_area_y_m2,
            effective_shear_area_z_m2,
        }
    }
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Default)]
pub struct LinearFrame3DMember {
    pub struct_size: u32,
    pub node_i: u32,
    pub node_j: u32,
    pub section_index: u32,
    pub reserved_u32: [u32; 2],
    pub local_axis_roll_deg: f64,
}

impl LinearFrame3DMember {
    pub fn new(node_i: u32, node_j: u32, section_index: u32) -> Self {
        Self {
            struct_size: core::mem::size_of::<Self>() as u32,
            node_i,
            node_j,
            section_index,
            reserved_u32: [0; 2],
            local_axis_roll_deg: 0.0,
        }
    }
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct LinearFrame3DModelInput {
    pub struct_size: u32,
    pub abi_version_major: u32,
    pub abi_version_minor: u32,
    pub reserved_u32: u32,
    pub nodes: *const LinearFrame3DNode,
    pub node_count: usize,
    pub sections: *const LinearFrame3DSection,
    pub section_count: usize,
    pub members: *const LinearFrame3DMember,
    pub member_count: usize,
    pub restrained_dofs: *const u32,
    pub restrained_dof_count: usize,
}

impl Default for LinearFrame3DModelInput {
    fn default() -> Self {
        Self {
            struct_size: core::mem::size_of::<Self>() as u32,
            abi_version_major: ABI_VERSION_MAJOR,
            abi_version_minor: ABI_VERSION_MINOR,
            reserved_u32: 0,
            nodes: core::ptr::null(),
            node_count: 0,
            sections: core::ptr::null(),
            section_count: 0,
            members: core::ptr::null(),
            member_count: 0,
            restrained_dofs: core::ptr::null(),
            restrained_dof_count: 0,
        }
    }
}

#[repr(C)]
#[derive(Debug)]
pub struct LinearFrame3DResultBuffers {
    pub struct_size: u32,
    pub reserved_u32: u32,
    pub displacements: *mut f64,
    pub displacement_count: usize,
    pub reactions: *mut f64,
    pub reaction_count: usize,
    pub member_end_forces: *mut f64,
    pub member_end_force_count: usize,
}

impl Default for LinearFrame3DResultBuffers {
    fn default() -> Self {
        Self {
            struct_size: core::mem::size_of::<Self>() as u32,
            reserved_u32: 0,
            displacements: core::ptr::null_mut(),
            displacement_count: 0,
            reactions: core::ptr::null_mut(),
            reaction_count: 0,
            member_end_forces: core::ptr::null_mut(),
            member_end_force_count: 0,
        }
    }
}

#[repr(C)]
pub struct Engine {
    _private: [u8; 0],
}

#[repr(C)]
pub struct LinearFrame3DModel {
    _private: [u8; 0],
}

#[cfg(feature = "native-link")]
#[link(name = "structural_engine_c_api", kind = "static")]
extern "C" {
    pub fn sa_get_api_info(out_info: *mut ApiInfo) -> i32;
    pub fn sa_engine_create(config: *const EngineConfig, out_engine: *mut *mut Engine) -> i32;
    pub fn sa_engine_destroy(engine: *mut Engine);
    pub fn sa_engine_capabilities(engine: *const Engine, out_capabilities: *mut u64) -> i32;
    pub fn sa_engine_last_error(
        engine: *const Engine,
        buffer: *mut c_char,
        buffer_capacity: usize,
        out_required_size: *mut usize,
    ) -> i32;
    pub fn sa_linear_frame3d_model_compile(
        engine: *const Engine,
        input: *const LinearFrame3DModelInput,
        out_model: *mut *mut LinearFrame3DModel,
    ) -> i32;
    pub fn sa_linear_frame3d_model_destroy(model: *mut LinearFrame3DModel);
    pub fn sa_linear_frame3d_model_sizes(
        model: *const LinearFrame3DModel,
        out_dof_count: *mut usize,
        out_member_end_force_count: *mut usize,
    ) -> i32;
    pub fn sa_linear_frame3d_solve(
        model: *const LinearFrame3DModel,
        load_vector_kn: *const f64,
        load_count: usize,
        out_result: *mut LinearFrame3DResultBuffers,
    ) -> i32;
}
