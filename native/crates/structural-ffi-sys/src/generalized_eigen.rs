//! Raw bounded dense generalized-eigen CPU operations introduced by C ABI v1.9.

use crate::{SaBufferViewV1, SaErrorBufferV1, SaMutBufferViewV1, SaStatusCodeV1};

pub const SA_ABI_V1_9: u32 = 0x0001_0009;
pub const SA_CAPABILITY_GENERALIZED_EIGEN_CPU: u64 = 1 << 10;
pub const SA_GENERALIZED_EIGEN_MAX_ORDER: u64 = 128;
pub const SA_GENERALIZED_EIGEN_MAX_SWEEPS: u32 = 4096;

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaDenseSymmetricMatrixV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub order: u64,
    pub values: SaBufferViewV1,
    pub reserved: [u64; 2],
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaGeneralizedEigenConfigV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub mode_count: u32,
    pub maximum_sweeps: u32,
    pub flags: u32,
    pub reserved_u32: u32,
    pub symmetry_relative_tolerance: f64,
    pub positive_semidefinite_relative_tolerance: f64,
    pub mode_relative_tolerance: f64,
    pub cluster_relative_tolerance: f64,
    pub residual_relative_tolerance: f64,
    pub orthogonality_tolerance: f64,
    pub eigensolver_relative_tolerance: f64,
    pub reserved: [u64; 2],
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaModalOutputsV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub eigenvalue_rad2_per_s2: SaMutBufferViewV1,
    pub omega_rad_per_s: SaMutBufferViewV1,
    pub frequency_hz: SaMutBufferViewV1,
    pub period_s: SaMutBufferViewV1,
    pub mass_normalized_mode_shapes: SaMutBufferViewV1,
    pub generalized_mass: SaMutBufferViewV1,
    pub generalized_stiffness: SaMutBufferViewV1,
    pub residual_relative_inf: SaMutBufferViewV1,
    pub reserved: [u64; 2],
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaModalResultV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub solver_status: u32,
    pub rigid_mode_count: u32,
    pub eigensolver_sweeps: u32,
    pub reserved_u32: u32,
    pub mass_orthogonality_error_inf: f64,
    pub stiffness_diagonalization_error_inf: f64,
    pub stiffness_relative_symmetry_error: f64,
    pub mass_relative_symmetry_error: f64,
    pub stiffness_minimum_eigenvalue: f64,
    pub mass_minimum_eigenvalue: f64,
    pub output_mode_count: u64,
    pub output_shape_length: u64,
    pub execution_backend: u32,
    pub fallback_count: u32,
    pub reserved: [u64; 2],
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaBucklingOutputsV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub load_factor: SaMutBufferViewV1,
    pub stiffness_normalized_mode_shapes: SaMutBufferViewV1,
    pub generalized_elastic_stiffness: SaMutBufferViewV1,
    pub generalized_geometric_stiffness: SaMutBufferViewV1,
    pub residual_relative_inf: SaMutBufferViewV1,
    pub reserved: [u64; 2],
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaBucklingResultV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub solver_status: u32,
    pub finite_positive_eigenvalue_count: u32,
    pub geometric_stiffness_positive_rank: u32,
    pub eigensolver_sweeps: u32,
    pub critical_load_factor: f64,
    pub stiffness_orthogonality_error_inf: f64,
    pub geometric_diagonalization_error_inf: f64,
    pub stiffness_relative_symmetry_error: f64,
    pub geometric_stiffness_relative_symmetry_error: f64,
    pub stiffness_minimum_eigenvalue: f64,
    pub geometric_stiffness_minimum_eigenvalue: f64,
    pub output_mode_count: u64,
    pub output_shape_length: u64,
    pub execution_backend: u32,
    pub fallback_count: u32,
    pub reserved: [u64; 2],
}

pub type SaModalSolveFnV1 = unsafe extern "C" fn(
    config: *const SaGeneralizedEigenConfigV1,
    stiffness: *const SaDenseSymmetricMatrixV1,
    mass: *const SaDenseSymmetricMatrixV1,
    coordinate_recovery_scale: *const SaBufferViewV1,
    outputs: *const SaModalOutputsV1,
    result: *mut SaModalResultV1,
    error: *mut SaErrorBufferV1,
) -> SaStatusCodeV1;

pub type SaBucklingSolveFnV1 = unsafe extern "C" fn(
    config: *const SaGeneralizedEigenConfigV1,
    stiffness: *const SaDenseSymmetricMatrixV1,
    geometric_stiffness_per_unit_load: *const SaDenseSymmetricMatrixV1,
    coordinate_recovery_scale: *const SaBufferViewV1,
    outputs: *const SaBucklingOutputsV1,
    result: *mut SaBucklingResultV1,
    error: *mut SaErrorBufferV1,
) -> SaStatusCodeV1;

#[cfg(test)]
mod tests {
    use super::{
        SaBucklingOutputsV1, SaBucklingResultV1, SaDenseSymmetricMatrixV1,
        SaGeneralizedEigenConfigV1, SaModalOutputsV1, SaModalResultV1,
    };
    use core::mem::{align_of, offset_of, size_of};

    #[test]
    fn rust_generalized_eigen_layout_matches_the_public_c_header_contract() {
        assert_eq!(size_of::<SaDenseSymmetricMatrixV1>(), 80);
        assert_eq!(align_of::<SaDenseSymmetricMatrixV1>(), 8);
        assert_eq!(offset_of!(SaDenseSymmetricMatrixV1, values), 16);
        assert_eq!(offset_of!(SaDenseSymmetricMatrixV1, reserved), 64);
        assert_eq!(size_of::<SaGeneralizedEigenConfigV1>(), 96);
        assert_eq!(
            offset_of!(SaGeneralizedEigenConfigV1, symmetry_relative_tolerance),
            24
        );
        assert_eq!(offset_of!(SaGeneralizedEigenConfigV1, reserved), 80);
        assert_eq!(size_of::<SaModalOutputsV1>(), 408);
        assert_eq!(offset_of!(SaModalOutputsV1, eigenvalue_rad2_per_s2), 8);
        assert_eq!(
            offset_of!(SaModalOutputsV1, mass_normalized_mode_shapes),
            200
        );
        assert_eq!(offset_of!(SaModalOutputsV1, reserved), 392);
        assert_eq!(size_of::<SaModalResultV1>(), 112);
        assert_eq!(
            offset_of!(SaModalResultV1, mass_orthogonality_error_inf),
            24
        );
        assert_eq!(offset_of!(SaModalResultV1, output_mode_count), 72);
        assert_eq!(offset_of!(SaModalResultV1, reserved), 96);
        assert_eq!(size_of::<SaBucklingOutputsV1>(), 264);
        assert_eq!(offset_of!(SaBucklingOutputsV1, load_factor), 8);
        assert_eq!(offset_of!(SaBucklingOutputsV1, residual_relative_inf), 200);
        assert_eq!(offset_of!(SaBucklingOutputsV1, reserved), 248);
        assert_eq!(size_of::<SaBucklingResultV1>(), 120);
        assert_eq!(offset_of!(SaBucklingResultV1, critical_load_factor), 24);
        assert_eq!(offset_of!(SaBucklingResultV1, output_mode_count), 80);
        assert_eq!(offset_of!(SaBucklingResultV1, reserved), 104);
    }
}
