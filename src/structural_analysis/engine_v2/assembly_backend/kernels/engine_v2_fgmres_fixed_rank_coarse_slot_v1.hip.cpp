// Typed fixed-rank coarse preconditioner slot supplement v1.
//
// This source is compiled only after the frozen recurrence-v2 source and the
// frozen fixed-rank coarse-v1 source in one HIPRTC translation unit.  It
// therefore reuses their exact device ABI helpers without changing either
// historical source.  The gate replaces one logical APPLY_JACOBI_INDEXED row:
// it admits the same recurrence coordinate, claims the same schedule epoch,
// initializes the coarse workspace, and is followed by the retained v1 dot
// and solve kernels plus the slot-aware apply kernel below.

constexpr unsigned int kCoarseSlotGateFailure = 1u << 4;
constexpr unsigned int kCoarseSlotInactive = 1u << 31;

extern "C" __global__ void
engine_v2_fgmres_fixed_rank_coarse_slot_gate_v1(
    int expected_schedule_epoch,
    int expected_restart,
    int expected_column,
    int free_dof_count,
    int retained_rank,
    int restart_dimension,
    int logical_index,
    double* coarse_rhs,
    double* coarse_coefficients,
    unsigned int* coarse_status,
    unsigned char* control_state_base,
    unsigned char* solve_record_base) {
  if (gridDim.x != 1u || blockDim.x != 1u || blockIdx.x != 0u ||
      threadIdx.x != 0u) {
    return;
  }
  *coarse_status = 0u;
  if (free_dof_count <= 0 || retained_rank <= 0 ||
      retained_rank > engine_v2_coarse_v1::kCoarseMaximumRank ||
      restart_dimension <= 0 ||
      restart_dimension > kMaximumRestartDimension || expected_restart < 1 ||
      expected_column < 0 || expected_column >= restart_dimension ||
      logical_index != expected_column) {
    *coarse_status =
        engine_v2_coarse_v1::kErrorInvalidGeometry |
        kCoarseSlotGateFailure;
    engine_v2_terminal_failure(
        control_state_base,
        solve_record_base,
        kErrorInvalidControlOrGeometry,
        kFailureOriginVector,
        kTerminationInvalidInputOrControl);
    return;
  }
  if (!engine_v2_abi_state_valid(control_state_base, solve_record_base)) {
    *coarse_status = kCoarseSlotGateFailure;
    engine_v2_terminal_failure(
        control_state_base,
        solve_record_base,
        kErrorRecordAbi,
        kFailureOriginVector,
        kTerminationInvalidInputOrControl);
    return;
  }
  if (!engine_v2_record_active(solve_record_base)) {
    *coarse_status = kCoarseSlotInactive;
    return;
  }

  const int stages = engine_v2_reduction_stage_count(free_dof_count);
  const int stored_restart_dimension = engine_v2_load_i32_le(
      control_state_base, kControlOffsetRestartDimension);
  const int maximum_restart_count = engine_v2_load_i32_le(
      control_state_base, kControlOffsetMaximumRestartCount);
  const bool recurrence_coordinate =
      engine_v2_global_column_coordinate_valid(
          expected_restart,
          expected_column,
          stored_restart_dimension,
          maximum_restart_count);
  const int column_base = recurrence_coordinate
      ? engine_v2_global_column_schedule_base(
            stages,
            stored_restart_dimension,
            expected_restart,
            expected_column)
      : -1;
  const int cycle_start_iteration = engine_v2_load_i32_le(
      control_state_base, kControlOffsetCycleStartIteration);
  const int column_iteration = cycle_start_iteration + expected_column;
  const int false_convergence_count = engine_v2_load_i32_le(
      solve_record_base, kRecordOffsetFalseConvergenceCount);
  const int operator_before_arnoldi = recurrence_coordinate
      ? 1 + column_iteration + expected_restart - 1 +
            false_convergence_count
      : -1;
  const bool admission_valid = recurrence_coordinate &&
      restart_dimension == stored_restart_dimension &&
      expected_schedule_epoch == column_base &&
      engine_v2_common_state_valid(
          control_state_base,
          solve_record_base,
          free_dof_count,
          expected_restart,
          expected_column) &&
      engine_v2_predecessor_validation_empty(control_state_base) &&
      engine_v2_load_i32_le(control_state_base, kControlOffsetPhase) ==
          kPhaseArnoldi &&
      engine_v2_load_i32_le(
          solve_record_base, kRecordOffsetEffectiveIterations) ==
          column_iteration &&
      engine_v2_load_i32_le(
          solve_record_base, kRecordOffsetPreconditionerApplyCount) ==
          column_iteration &&
      engine_v2_load_i32_le(
          solve_record_base, kRecordOffsetOperatorApplyCount) ==
          operator_before_arnoldi;
  if (!admission_valid) {
    *coarse_status = kCoarseSlotGateFailure;
    engine_v2_terminal_failure(
        control_state_base,
        solve_record_base,
        kErrorInvalidControlOrGeometry,
        kFailureOriginVector,
        kTerminationInvalidInputOrControl);
    return;
  }
  if (!engine_v2_claim_schedule_or_fail(
          control_state_base,
          solve_record_base,
          expected_schedule_epoch,
          kFailureOriginVector)) {
    *coarse_status = kCoarseSlotGateFailure;
    return;
  }
  for (int index = 0; index < retained_rank; ++index) {
    coarse_rhs[index] = 0.0;
    coarse_coefficients[index] = 0.0;
  }
}

extern "C" __global__ void
engine_v2_fgmres_fixed_rank_coarse_slot_apply_v1(
    int free_dof_count,
    int retained_rank,
    int restart_dimension,
    int logical_index,
    const double* jacobi_inverse,
    const double* basis_v,
    double* preconditioned_basis_z,
    const double* coarse_physical_basis_z,
    const double* coarse_operator_basis_az,
    const double* coarse_coefficients,
    unsigned int* coarse_status) {
  const int row = static_cast<int>(
      blockIdx.x * static_cast<unsigned int>(blockDim.x) + threadIdx.x);
  const unsigned int expected_grid =
      (static_cast<unsigned int>(free_dof_count) +
       engine_v2_coarse_v1::kCoarseBlockSize - 1u) /
      engine_v2_coarse_v1::kCoarseBlockSize;
  if (blockDim.x != engine_v2_coarse_v1::kCoarseBlockSize ||
      gridDim.x != expected_grid ||
      free_dof_count <= 0 || retained_rank <= 0 ||
      retained_rank > engine_v2_coarse_v1::kCoarseMaximumRank ||
      restart_dimension <= 0 ||
      logical_index < 0 || logical_index >= restart_dimension) {
    if (row == 0) {
      atomicOr(
          coarse_status,
          engine_v2_coarse_v1::kErrorInvalidGeometry);
    }
    return;
  }
  if (row >= free_dof_count) {
    return;
  }
  const unsigned int status = *coarse_status;
  if ((status & kCoarseSlotInactive) != 0u) {
    return;
  }
  const unsigned long long vector_offset =
      static_cast<unsigned long long>(logical_index) *
      static_cast<unsigned long long>(free_dof_count);
  if (status != 0u) {
    preconditioned_basis_z[vector_offset + row] =
        engine_v2_coarse_v1::engine_v2_coarse_canonical_nan();
    return;
  }
  const double residual = basis_v[vector_offset + row];
  const double inverse = jacobi_inverse[row];
  if (!engine_v2_coarse_v1::engine_v2_coarse_isfinite(residual) ||
      !engine_v2_coarse_v1::engine_v2_coarse_isfinite(inverse) ||
      inverse <= 0.0) {
    atomicOr(
        coarse_status,
        !engine_v2_coarse_v1::engine_v2_coarse_isfinite(residual) ||
                !engine_v2_coarse_v1::engine_v2_coarse_isfinite(inverse)
            ? engine_v2_coarse_v1::kErrorNonfiniteInput
            : engine_v2_coarse_v1::kErrorNonpositiveFactor);
    preconditioned_basis_z[vector_offset + row] =
        engine_v2_coarse_v1::engine_v2_coarse_canonical_nan();
    return;
  }
  double coarse_correction = 0.0;
  double coarse_image = 0.0;
  unsigned int error = 0u;
  for (int mode = 0; mode < retained_rank; ++mode) {
    const unsigned long long offset =
        static_cast<unsigned long long>(row) * retained_rank + mode;
    const double coefficient = coarse_coefficients[mode];
    const double basis = coarse_physical_basis_z[offset];
    const double image = coarse_operator_basis_az[offset];
    if (!engine_v2_coarse_v1::engine_v2_coarse_isfinite(coefficient) ||
        !engine_v2_coarse_v1::engine_v2_coarse_isfinite(basis) ||
        !engine_v2_coarse_v1::engine_v2_coarse_isfinite(image)) {
      error |= engine_v2_coarse_v1::kErrorNonfiniteInput;
      break;
    }
    const double basis_product = coefficient * basis;
    const double image_product = coefficient * image;
    const double updated_correction = coarse_correction + basis_product;
    const double updated_image = coarse_image + image_product;
    if (!engine_v2_coarse_v1::engine_v2_coarse_isfinite(basis_product) ||
        !engine_v2_coarse_v1::engine_v2_coarse_isfinite(image_product) ||
        !engine_v2_coarse_v1::engine_v2_coarse_isfinite(updated_correction) ||
        !engine_v2_coarse_v1::engine_v2_coarse_isfinite(updated_image)) {
      error |= engine_v2_coarse_v1::kErrorNonfiniteArithmetic;
      break;
    }
    coarse_correction = updated_correction;
    coarse_image = updated_image;
  }
  const double smoothed = inverse * (residual - coarse_image);
  const double output = coarse_correction + smoothed;
  if (error != 0u ||
      !engine_v2_coarse_v1::engine_v2_coarse_isfinite(smoothed) ||
      !engine_v2_coarse_v1::engine_v2_coarse_isfinite(output)) {
    atomicOr(
        coarse_status,
        error != 0u
            ? error
            : engine_v2_coarse_v1::kErrorNonfiniteArithmetic);
    preconditioned_basis_z[vector_offset + row] =
        engine_v2_coarse_v1::engine_v2_coarse_canonical_nan();
    return;
  }
  preconditioned_basis_z[vector_offset + row] =
      engine_v2_coarse_v1::engine_v2_coarse_exact_zero(output);
}
