//! Raw bounded linear `Frame3D` declarations from ABI v1.2 and its v1.3 load-case extension.

use super::{SaErrorBufferV1, SaStatusCodeV1, SA_ABI_V1_2};

#[repr(C)]
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct SaLinearFrame3dNodeV1 {
    pub struct_size: u32,
    pub reserved_u32: u32,
    pub x_m: f64,
    pub y_m: f64,
    pub z_m: f64,
}

impl SaLinearFrame3dNodeV1 {
    #[must_use]
    pub fn new(x_m: f64, y_m: f64, z_m: f64) -> Self {
        Self {
            struct_size: abi_size::<Self>(),
            reserved_u32: 0,
            x_m,
            y_m,
            z_m,
        }
    }
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct SaLinearFrame3dSectionV1 {
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

impl SaLinearFrame3dSectionV1 {
    #[allow(clippy::similar_names, clippy::too_many_arguments)]
    #[must_use]
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
            struct_size: abi_size::<Self>(),
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
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct SaLinearFrame3dMemberV1 {
    pub struct_size: u32,
    pub node_i: u32,
    pub node_j: u32,
    pub section_index: u32,
    pub reserved_u32: [u32; 2],
    pub local_axis_roll_deg: f64,
}

impl SaLinearFrame3dMemberV1 {
    #[must_use]
    pub fn new(node_i: u32, node_j: u32, section_index: u32) -> Self {
        Self {
            struct_size: abi_size::<Self>(),
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
pub struct SaLinearFrame3dModelInputV1 {
    pub struct_size: u32,
    pub abi_version_major: u32,
    pub abi_version_minor: u32,
    pub reserved_u32: u32,
    pub nodes: *const SaLinearFrame3dNodeV1,
    pub node_count: u64,
    pub sections: *const SaLinearFrame3dSectionV1,
    pub section_count: u64,
    pub members: *const SaLinearFrame3dMemberV1,
    pub member_count: u64,
    pub restrained_dofs: *const u32,
    pub restrained_dof_count: u64,
}

impl Default for SaLinearFrame3dModelInputV1 {
    fn default() -> Self {
        Self {
            struct_size: abi_size::<Self>(),
            abi_version_major: SA_ABI_V1_2 >> 16,
            abi_version_minor: SA_ABI_V1_2 & 0xffff,
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
pub struct SaLinearFrame3dResultBuffersV1 {
    pub struct_size: u32,
    pub reserved_u32: u32,
    pub displacements: *mut f64,
    pub displacement_count: u64,
    pub reactions: *mut f64,
    pub reaction_count: u64,
    pub member_end_forces: *mut f64,
    pub member_end_force_count: u64,
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct SaLinearFrame3dUniformMemberLoadV1 {
    pub struct_size: u32,
    pub member_index: u32,
    pub reserved_u32: [u32; 2],
    pub components_kn_per_m: [f64; 3],
}

impl SaLinearFrame3dUniformMemberLoadV1 {
    #[must_use]
    pub fn new(member_index: u32, components_kn_per_m: [f64; 3]) -> Self {
        Self {
            struct_size: abi_size::<Self>(),
            member_index,
            reserved_u32: [0; 2],
            components_kn_per_m,
        }
    }
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaLinearFrame3dLoadCaseV1 {
    pub struct_size: u32,
    pub reserved_u32: u32,
    pub nodal_load_vector_kn: *const f64,
    pub nodal_load_count: u64,
    pub uniform_member_loads: *const SaLinearFrame3dUniformMemberLoadV1,
    pub uniform_member_load_count: u64,
}

impl Default for SaLinearFrame3dLoadCaseV1 {
    fn default() -> Self {
        Self {
            struct_size: abi_size::<Self>(),
            reserved_u32: 0,
            nodal_load_vector_kn: core::ptr::null(),
            nodal_load_count: 0,
            uniform_member_loads: core::ptr::null(),
            uniform_member_load_count: 0,
        }
    }
}

impl Default for SaLinearFrame3dResultBuffersV1 {
    fn default() -> Self {
        Self {
            struct_size: abi_size::<Self>(),
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
pub struct SaLinearFrame3dModelV1 {
    _private: [u8; 0],
}

pub type SaLinearFrame3dModelCompileFnV1 = unsafe extern "C" fn(
    input: *const SaLinearFrame3dModelInputV1,
    out_model: *mut *mut SaLinearFrame3dModelV1,
    error: *mut SaErrorBufferV1,
) -> SaStatusCodeV1;

pub type SaLinearFrame3dModelDestroyFnV1 = unsafe extern "C" fn(
    model: *mut SaLinearFrame3dModelV1,
    error: *mut SaErrorBufferV1,
) -> SaStatusCodeV1;

pub type SaLinearFrame3dModelSizesFnV1 = unsafe extern "C" fn(
    model: *const SaLinearFrame3dModelV1,
    out_dof_count: *mut u64,
    out_member_end_force_count: *mut u64,
    error: *mut SaErrorBufferV1,
) -> SaStatusCodeV1;

pub type SaLinearFrame3dSolveFnV1 = unsafe extern "C" fn(
    model: *const SaLinearFrame3dModelV1,
    load_vector_kn: *const f64,
    load_count: u64,
    out_result: *mut SaLinearFrame3dResultBuffersV1,
    error: *mut SaErrorBufferV1,
) -> SaStatusCodeV1;

pub type SaLinearFrame3dSolveLoadCaseFnV1 = unsafe extern "C" fn(
    model: *const SaLinearFrame3dModelV1,
    load_case: *const SaLinearFrame3dLoadCaseV1,
    out_result: *mut SaLinearFrame3dResultBuffersV1,
    error: *mut SaErrorBufferV1,
) -> SaStatusCodeV1;

fn abi_size<T>() -> u32 {
    u32::try_from(core::mem::size_of::<T>()).unwrap_or(u32::MAX)
}

#[cfg(test)]
mod tests {
    use super::*;
    use core::mem::{offset_of, size_of};

    #[test]
    fn frame3d_layout_matches_public_c_header() {
        assert_eq!(size_of::<SaLinearFrame3dNodeV1>(), 32);
        assert_eq!(size_of::<SaLinearFrame3dSectionV1>(), 72);
        assert_eq!(size_of::<SaLinearFrame3dMemberV1>(), 32);
        assert_eq!(offset_of!(SaLinearFrame3dMemberV1, local_axis_roll_deg), 24);
        assert_eq!(size_of::<SaLinearFrame3dModelInputV1>(), 80);
        assert_eq!(offset_of!(SaLinearFrame3dModelInputV1, nodes), 16);
        assert_eq!(
            offset_of!(SaLinearFrame3dModelInputV1, restrained_dof_count),
            72
        );
        assert_eq!(size_of::<SaLinearFrame3dResultBuffersV1>(), 56);
        assert_eq!(
            offset_of!(SaLinearFrame3dResultBuffersV1, member_end_forces),
            40
        );
        assert_eq!(size_of::<SaLinearFrame3dUniformMemberLoadV1>(), 40);
        assert_eq!(
            offset_of!(SaLinearFrame3dUniformMemberLoadV1, components_kn_per_m),
            16
        );
        assert_eq!(size_of::<SaLinearFrame3dLoadCaseV1>(), 40);
        assert_eq!(
            offset_of!(SaLinearFrame3dLoadCaseV1, uniform_member_loads),
            24
        );
    }
}
