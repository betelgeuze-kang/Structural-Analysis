//! Raw bounded canonical-CSR sparse linear operation introduced by C ABI v1.8.

use crate::{SaBufferViewV1, SaErrorBufferV1, SaMutBufferViewV1, SaStatusCodeV1};

pub const SA_ABI_V1_8: u32 = 0x0001_0008;
pub const SA_CAPABILITY_SPARSE_LINEAR_CPU: u64 = 1 << 9;
pub const SA_SPARSE_LINEAR_MAX_ORDER: u64 = 1_000_000;
pub const SA_SPARSE_LINEAR_MAX_NONZEROS: u64 = 100_000_000;

pub const SA_SOLVER_CONVERGED: u32 = 0;
pub const SA_SOLVER_INVALID_INPUT: u32 = 1;
pub const SA_SOLVER_SINGULARITY: u32 = 2;
pub const SA_SOLVER_INDEFINITE_OPERATOR: u32 = 3;
pub const SA_SOLVER_NONCONVERGENCE: u32 = 4;
pub const SA_SOLVER_INCREMENT_LIMIT: u32 = 5;
pub const SA_SOLVER_RESIDUAL_LIMIT: u32 = 6;
pub const SA_SOLVER_CANCELLED: u32 = 7;
pub const SA_SOLVER_CHECKPOINT_MISMATCH: u32 = 8;
pub const SA_SOLVER_BACKEND_UNAVAILABLE: u32 = 9;

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaSparseCsrMatrixV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub order: u64,
    pub row_offsets: SaBufferViewV1,
    pub column_indices: SaBufferViewV1,
    pub values: SaBufferViewV1,
    pub reserved: [u64; 2],
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaSparseLinearConfigV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub max_iterations: u32,
    pub flags: u32,
    pub absolute_residual_tolerance: f64,
    pub relative_residual_tolerance: f64,
    pub maximum_increment: f64,
    pub reserved: [u64; 2],
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct SaSparseLinearResultV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub solver_status: u32,
    pub iterations: u32,
    pub initial_residual_inf: f64,
    pub final_residual_inf: f64,
    pub final_residual_l2: f64,
    pub last_increment_inf: f64,
    pub output_length: u64,
    pub execution_backend: u32,
    pub fallback_count: u32,
    pub reserved: [u64; 2],
}

pub type SaSparseLinearSolveFnV1 = unsafe extern "C" fn(
    config: *const SaSparseLinearConfigV1,
    matrix: *const SaSparseCsrMatrixV1,
    right_hand_side: *const SaBufferViewV1,
    initial_guess: *const SaBufferViewV1,
    solution: *const SaMutBufferViewV1,
    result: *mut SaSparseLinearResultV1,
    error: *mut SaErrorBufferV1,
) -> SaStatusCodeV1;

#[cfg(test)]
mod tests {
    use super::{SaSparseCsrMatrixV1, SaSparseLinearConfigV1, SaSparseLinearResultV1};
    use core::mem::{align_of, offset_of, size_of};

    #[test]
    fn rust_sparse_linear_layout_matches_the_public_c_header_contract() {
        assert_eq!(size_of::<SaSparseCsrMatrixV1>(), 176);
        assert_eq!(align_of::<SaSparseCsrMatrixV1>(), 8);
        assert_eq!(offset_of!(SaSparseCsrMatrixV1, row_offsets), 16);
        assert_eq!(offset_of!(SaSparseCsrMatrixV1, reserved), 160);
        assert_eq!(size_of::<SaSparseLinearConfigV1>(), 56);
        assert_eq!(
            offset_of!(SaSparseLinearConfigV1, absolute_residual_tolerance),
            16
        );
        assert_eq!(offset_of!(SaSparseLinearConfigV1, reserved), 40);
        assert_eq!(size_of::<SaSparseLinearResultV1>(), 80);
        assert_eq!(offset_of!(SaSparseLinearResultV1, initial_residual_inf), 16);
        assert_eq!(offset_of!(SaSparseLinearResultV1, output_length), 48);
        assert_eq!(offset_of!(SaSparseLinearResultV1, reserved), 64);
    }
}
