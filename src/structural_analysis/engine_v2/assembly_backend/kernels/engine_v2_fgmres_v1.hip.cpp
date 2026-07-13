#pragma clang fp contract(off)

// engine-v2-fgmres-interface-v1: sha256:a22419521132fa3d31c853b8468415893b56b95c18a1c45270059b4c4308f42f

#if defined(__BYTE_ORDER__) && defined(__ORDER_LITTLE_ENDIAN__) && \
    (__BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__)
#error "Engine v2 FGMRES solve-record ABI requires little-endian device code"
#endif

namespace {

constexpr int kBlockSize = 256;
constexpr int kRecurrenceAbiVersion = 1;
constexpr int kHeaderBytes = 192;
constexpr int kRestartBytes = 72;
constexpr int kMaximumRestartDimension = 16;
constexpr int kMaximumIterations = 4096;

constexpr int kErrorInvalidControlOrGeometry = 1;
constexpr int kErrorCsrStructure = 2;
constexpr int kErrorNonfiniteInput = 4;
constexpr int kErrorArithmeticOverflow = 8;
constexpr int kErrorRecordAbi = 16;
constexpr int kErrorJacobi = 32;

constexpr int kTerminalNotTerminal = 0;
constexpr int kTerminalConverged = 1;
constexpr int kTerminalMaxIterations = 2;
constexpr int kTerminalStagnated = 3;
constexpr int kTerminalDiverged = 4;
constexpr int kTerminalArnoldiBreakdown = 5;
constexpr int kTerminalNumericalFailure = 6;

constexpr int kTerminationNone = 0;
constexpr int kTerminationConvergedInitial = 1;
constexpr int kTerminationConvergedHappyBreakdown = 2;
constexpr int kTerminationConvergedTrueResidual = 3;
constexpr int kTerminationConvergedRestart = 4;
constexpr int kTerminationMaxIterations = 10;
constexpr int kTerminationTrueResidualStagnated = 20;
constexpr int kTerminationTrueResidualDiverged = 21;
constexpr int kTerminationTriangularFactorBreakdown = 30;
constexpr int kTerminationInvariantSubspaceBreakdown = 31;
constexpr int kTerminationInvalidControl = 40;
constexpr int kTerminationNonfiniteArithmetic = 41;
constexpr int kTerminationOperatorFailed = 42;
constexpr int kTerminationOrthogonalizationFailed = 43;
constexpr int kTerminationGivensRotationFailed = 44;
constexpr int kTerminationTriangularSolveFailed = 45;
constexpr int kTerminationTrueResidualReplayFailed = 46;
constexpr int kTerminationRestartStateFailed = 47;

constexpr int kRestartHintNone = 0;
constexpr int kRestartHintRestartCompleted = 1;
constexpr int kRestartHintConvergedHappyBreakdown = 2;
constexpr int kRestartHintConvergedTrueResidual = 3;
constexpr int kRestartHintInvariantBreakdown = 4;
constexpr int kRestartHintTriangularBreakdown = 5;

constexpr int kRestartFlagTrueResidualReplayed = 1;
constexpr int kRestartFlagSolverL2Passed = 2;
constexpr int kRestartFlagAuthoritativeLinfPassed = 4;
constexpr int kRestartFlagHappyBreakdown = 8;
constexpr int kRestartFlagInvariantBreakdown = 16;
constexpr int kRestartFlagStagnationPlateau = 32;
constexpr int kRestartFlagTinyUpdate = 64;
constexpr int kRestartFlagDivergence = 128;

constexpr int kControlInitialTrueResidual = 0;
constexpr int kControlCandidateTrueResidual = 1;
constexpr int kControlMaxIterationsFinalize = 2;

constexpr int kOffsetAbiVersion = 0;
constexpr int kOffsetActive = 4;
constexpr int kOffsetTerminalStatus = 8;
constexpr int kOffsetTerminationCode = 12;
constexpr int kOffsetDeviceErrorBits = 16;
constexpr int kOffsetScheduledIterations = 20;
constexpr int kOffsetEffectiveIterations = 24;
constexpr int kOffsetScheduledRestarts = 28;
constexpr int kOffsetEffectiveRestarts = 32;
constexpr int kOffsetEffectiveArnoldiDimension = 36;
constexpr int kOffsetHappyBreakdownCount = 40;
constexpr int kOffsetStagnationCheckpointCount = 44;
constexpr int kOffsetFalseConvergenceCount = 48;
constexpr int kOffsetOperatorApplyCount = 52;
constexpr int kOffsetPreconditionerApplyCount = 56;
constexpr int kOffsetRestartDimension = 60;

constexpr int kOffsetRhsL2 = 64;
constexpr int kOffsetRhsLinf = 72;
constexpr int kOffsetSolverToleranceL2 = 80;
constexpr int kOffsetAuthoritativeTolerance = 88;
constexpr int kOffsetInitialResidualL2 = 96;
constexpr int kOffsetFinalResidualL2 = 104;
constexpr int kOffsetFinalResidualLinf = 112;
constexpr int kOffsetFinalScaledResidual = 120;
constexpr int kOffsetPreviousCheckpointResidualL2 = 128;
constexpr int kOffsetSolutionUpdateL2 = 136;
constexpr int kOffsetSolutionScaleL2 = 144;
constexpr int kOffsetEstimatedResidualL2 = 152;
constexpr int kOffsetArnoldiWorkL2 = 160;
constexpr int kOffsetArnoldiBreakdownThreshold = 168;
constexpr int kOffsetTriangularScale = 176;
constexpr int kOffsetReservedF64 = 184;

constexpr int kRestartOffsetIndex = 0;
constexpr int kRestartOffsetStartIteration = 4;
constexpr int kRestartOffsetEndIteration = 8;
constexpr int kRestartOffsetArnoldiStepCount = 12;
constexpr int kRestartOffsetReorthogonalizationCount = 16;
constexpr int kRestartOffsetTerminationHint = 20;
constexpr int kRestartOffsetFlags = 24;
constexpr int kRestartOffsetReservedI32 = 28;
constexpr int kRestartOffsetEstimatedResidualL2 = 32;
constexpr int kRestartOffsetTrueResidualL2 = 40;
constexpr int kRestartOffsetTrueResidualLinf = 48;
constexpr int kRestartOffsetScaledTrueResidual = 56;
constexpr int kRestartOffsetSolutionUpdateL2 = 64;

__device__ __forceinline__ bool engine_v2_fgmres_isfinite(double value) {
  return isfinite(value);
}

__device__ __forceinline__ double engine_v2_fgmres_exact_zero(double value) {
  return value == 0.0 ? 0.0 : value;
}

__device__ __forceinline__ unsigned int engine_v2_fgmres_vector_grid(
    int count) {
  const unsigned long long promoted_count =
      static_cast<unsigned long long>(count);
  return static_cast<unsigned int>(
      (promoted_count + static_cast<unsigned long long>(kBlockSize) - 1u) /
      static_cast<unsigned long long>(kBlockSize));
}

__device__ __forceinline__ void engine_v2_store_u32_le(
    unsigned char* bytes,
    int offset,
    unsigned int value) {
  bytes[offset] = static_cast<unsigned char>(value & 0xffu);
  bytes[offset + 1] = static_cast<unsigned char>((value >> 8u) & 0xffu);
  bytes[offset + 2] = static_cast<unsigned char>((value >> 16u) & 0xffu);
  bytes[offset + 3] = static_cast<unsigned char>((value >> 24u) & 0xffu);
}

__device__ __forceinline__ unsigned int engine_v2_load_u32_le(
    const unsigned char* bytes,
    int offset) {
  return static_cast<unsigned int>(bytes[offset]) |
      (static_cast<unsigned int>(bytes[offset + 1]) << 8u) |
      (static_cast<unsigned int>(bytes[offset + 2]) << 16u) |
      (static_cast<unsigned int>(bytes[offset + 3]) << 24u);
}

__device__ __forceinline__ void engine_v2_store_i32_le(
    unsigned char* bytes,
    int offset,
    int value) {
  engine_v2_store_u32_le(bytes, offset, static_cast<unsigned int>(value));
}

__device__ __forceinline__ int engine_v2_load_i32_le(
    const unsigned char* bytes,
    int offset) {
  return static_cast<int>(engine_v2_load_u32_le(bytes, offset));
}

union EngineV2F64Bits {
  double value;
  unsigned long long bits;
};

__device__ __forceinline__ void engine_v2_store_f64_le(
    unsigned char* bytes,
    int offset,
    double value) {
  EngineV2F64Bits packed;
  packed.value = engine_v2_fgmres_exact_zero(value);
  for (int byte = 0; byte < 8; ++byte) {
    bytes[offset + byte] = static_cast<unsigned char>(
        (packed.bits >> static_cast<unsigned int>(8 * byte)) & 0xffu);
  }
}

__device__ __forceinline__ double engine_v2_load_f64_le(
    const unsigned char* bytes,
    int offset) {
  EngineV2F64Bits packed;
  packed.bits = 0u;
  for (int byte = 0; byte < 8; ++byte) {
    packed.bits |= static_cast<unsigned long long>(bytes[offset + byte])
        << static_cast<unsigned int>(8 * byte);
  }
  return packed.value;
}

__device__ __forceinline__ bool engine_v2_record_active(
    const unsigned char* record) {
  return engine_v2_load_i32_le(record, kOffsetActive) == 1;
}

__device__ __forceinline__ bool engine_v2_record_abi_valid(
    const unsigned char* record) {
  return engine_v2_load_i32_le(record, kOffsetAbiVersion) ==
      kRecurrenceAbiVersion;
}

__device__ __forceinline__ void engine_v2_record_error(
    unsigned char* record,
    int error_bit) {
  atomicOr(
      reinterpret_cast<unsigned int*>(record + kOffsetDeviceErrorBits),
      static_cast<unsigned int>(error_bit));
}

__device__ __forceinline__ void engine_v2_terminal_failure(
    unsigned char* record,
    int error_bit,
    int termination_code) {
  engine_v2_record_error(record, error_bit);
  atomicExch(reinterpret_cast<int*>(record + kOffsetActive), 0);
  atomicExch(
      reinterpret_cast<int*>(record + kOffsetTerminalStatus),
      kTerminalNumericalFailure);
  atomicExch(
      reinterpret_cast<int*>(record + kOffsetTerminationCode),
      termination_code);
}

__device__ __forceinline__ bool engine_v2_record_abi_or_fail(
    unsigned char* record) {
  if (engine_v2_record_abi_valid(record)) {
    return true;
  }
  if (blockIdx.x == 0u && threadIdx.x == 0u) {
    engine_v2_terminal_failure(
        record, kErrorRecordAbi, kTerminationInvalidControl);
  }
  return false;
}

__device__ __forceinline__ void engine_v2_increment_record_i32(
    unsigned char* record,
    int offset) {
  const int previous = engine_v2_load_i32_le(record, offset);
  engine_v2_store_i32_le(record, offset, previous + 1);
}

}  // namespace

extern "C" __global__ void engine_v2_fgmres_record_initialize_v1(
    int restart_dimension,
    int max_iterations,
    int maximum_restart_count,
    double absolute_tolerance,
    double relative_tolerance,
    double authoritative_tolerance,
    const double* rhs_l2,
    const double* rhs_linf,
    unsigned char* solve_record) {
  if (blockDim.x != kBlockSize || gridDim.x != 1u) {
    return;
  }
  const bool restart_extent_valid = maximum_restart_count >= 0 &&
      maximum_restart_count <= kMaximumIterations;
  const int record_bytes = restart_extent_valid
      ? kHeaderBytes + kRestartBytes * maximum_restart_count
      : kHeaderBytes;
  if (restart_extent_valid) {
    for (int offset = static_cast<int>(threadIdx.x); offset < record_bytes;
         offset += kBlockSize) {
      solve_record[offset] = 0u;
    }
  }
  __syncthreads();
  if (threadIdx.x != 0u) {
    return;
  }

  engine_v2_store_i32_le(
      solve_record, kOffsetAbiVersion, kRecurrenceAbiVersion);
  const bool dimensions_valid = restart_dimension >= 1 &&
      restart_dimension <= kMaximumRestartDimension && max_iterations >= 0 &&
      max_iterations <= kMaximumIterations && restart_extent_valid;
  const int expected_restarts = !dimensions_valid
      ? -1
      : (max_iterations == 0
             ? 0
             : (max_iterations + restart_dimension - 1) /
                   restart_dimension);
  const double checked_rhs_l2 = rhs_l2[0];
  const double checked_rhs_linf = rhs_linf[0];
  const bool valid = dimensions_valid &&
      maximum_restart_count == expected_restarts &&
      engine_v2_fgmres_isfinite(absolute_tolerance) &&
      absolute_tolerance >= 0.0 &&
      engine_v2_fgmres_isfinite(relative_tolerance) &&
      relative_tolerance >= 0.0 &&
      engine_v2_fgmres_isfinite(authoritative_tolerance) &&
      authoritative_tolerance >= 0.0 &&
      engine_v2_fgmres_isfinite(checked_rhs_l2) && checked_rhs_l2 >= 0.0 &&
      engine_v2_fgmres_isfinite(checked_rhs_linf) && checked_rhs_linf >= 0.0;
  if (!valid) {
    engine_v2_store_i32_le(solve_record, kOffsetActive, 0);
    engine_v2_store_i32_le(
        solve_record, kOffsetTerminalStatus, kTerminalNumericalFailure);
    engine_v2_store_i32_le(
        solve_record, kOffsetTerminationCode, kTerminationInvalidControl);
    engine_v2_store_i32_le(
        solve_record,
        kOffsetDeviceErrorBits,
        kErrorInvalidControlOrGeometry);
    return;
  }

  const double solver_tolerance = fmax(
      absolute_tolerance, relative_tolerance * checked_rhs_l2);
  if (!engine_v2_fgmres_isfinite(solver_tolerance)) {
    engine_v2_store_i32_le(solve_record, kOffsetActive, 0);
    engine_v2_store_i32_le(
        solve_record, kOffsetTerminalStatus, kTerminalNumericalFailure);
    engine_v2_store_i32_le(
        solve_record, kOffsetTerminationCode, kTerminationNonfiniteArithmetic);
    engine_v2_store_i32_le(
        solve_record, kOffsetDeviceErrorBits, kErrorArithmeticOverflow);
    return;
  }
  engine_v2_store_i32_le(solve_record, kOffsetActive, 1);
  engine_v2_store_i32_le(
      solve_record, kOffsetTerminalStatus, kTerminalNotTerminal);
  engine_v2_store_i32_le(
      solve_record, kOffsetTerminationCode, kTerminationNone);
  engine_v2_store_i32_le(
      solve_record, kOffsetScheduledIterations, max_iterations);
  engine_v2_store_i32_le(
      solve_record, kOffsetScheduledRestarts, maximum_restart_count);
  engine_v2_store_i32_le(
      solve_record, kOffsetRestartDimension, restart_dimension);
  engine_v2_store_f64_le(solve_record, kOffsetRhsL2, checked_rhs_l2);
  engine_v2_store_f64_le(solve_record, kOffsetRhsLinf, checked_rhs_linf);
  engine_v2_store_f64_le(
      solve_record, kOffsetSolverToleranceL2, solver_tolerance);
  engine_v2_store_f64_le(
      solve_record, kOffsetAuthoritativeTolerance, authoritative_tolerance);
}

extern "C" __global__ void engine_v2_fgmres_csr_spmv_v1(
    int n,
    int nnz,
    const int* row_ptr,
    const int* column_indices,
    const double* values,
    const double* input,
    double* output,
    unsigned char* solve_record) {
  if (!engine_v2_record_abi_or_fail(solve_record) ||
      !engine_v2_record_active(solve_record)) {
    return;
  }
  if (blockDim.x != kBlockSize || n <= 0 || nnz <= 0 || nnz < n ||
      gridDim.x != engine_v2_fgmres_vector_grid(n)) {
    if (blockIdx.x == 0u && threadIdx.x == 0u) {
      engine_v2_terminal_failure(
          solve_record,
          kErrorInvalidControlOrGeometry,
          kTerminationOperatorFailed);
    }
    return;
  }
  if (blockIdx.x == 0u && threadIdx.x == 0u) {
    engine_v2_increment_record_i32(
        solve_record, kOffsetOperatorApplyCount);
  }
  const unsigned long long row =
      static_cast<unsigned long long>(blockIdx.x) *
          static_cast<unsigned long long>(blockDim.x) +
      static_cast<unsigned long long>(threadIdx.x);
  if (row >= static_cast<unsigned long long>(n)) {
    return;
  }
  const int begin = row_ptr[row];
  const int end = row_ptr[row + 1u];
  if (begin < 0 || end < begin || end > nnz) {
    output[row] = 0.0;
    engine_v2_terminal_failure(
        solve_record, kErrorCsrStructure, kTerminationOperatorFailed);
    return;
  }
  double sum = 0.0;
  for (int position = begin; position < end; ++position) {
    const int column = column_indices[position];
    const double matrix_value = values[position];
    if (column < 0 || column >= n ||
        !engine_v2_fgmres_isfinite(matrix_value) ||
        !engine_v2_fgmres_isfinite(input[column])) {
      output[row] = 0.0;
      engine_v2_terminal_failure(
          solve_record,
          column < 0 || column >= n ? kErrorCsrStructure
                                    : kErrorNonfiniteInput,
          kTerminationOperatorFailed);
      return;
    }
    const double product = matrix_value * input[column];
    const double updated = sum + product;
    if (!engine_v2_fgmres_isfinite(product) ||
        !engine_v2_fgmres_isfinite(updated)) {
      output[row] = 0.0;
      engine_v2_terminal_failure(
          solve_record, kErrorArithmeticOverflow, kTerminationOperatorFailed);
      return;
    }
    sum = updated;
  }
  output[row] = engine_v2_fgmres_exact_zero(sum);
}

extern "C" __global__ void engine_v2_fgmres_residual_v1(
    int n,
    const double* rhs,
    const double* operator_value,
    double* residual,
    unsigned char* solve_record) {
  if (!engine_v2_record_abi_or_fail(solve_record) ||
      !engine_v2_record_active(solve_record)) {
    return;
  }
  if (blockDim.x != kBlockSize || n <= 0 ||
      gridDim.x != engine_v2_fgmres_vector_grid(n)) {
    if (blockIdx.x == 0u && threadIdx.x == 0u) {
      engine_v2_terminal_failure(
          solve_record,
          kErrorInvalidControlOrGeometry,
          kTerminationOperatorFailed);
    }
    return;
  }
  const unsigned long long index =
      static_cast<unsigned long long>(blockIdx.x) *
          static_cast<unsigned long long>(blockDim.x) +
      static_cast<unsigned long long>(threadIdx.x);
  if (index >= static_cast<unsigned long long>(n)) {
    return;
  }
  const double left = rhs[index];
  const double right = operator_value[index];
  const double value = left - right;
  if (!engine_v2_fgmres_isfinite(left) ||
      !engine_v2_fgmres_isfinite(right)) {
    residual[index] = 0.0;
    engine_v2_terminal_failure(
        solve_record, kErrorNonfiniteInput, kTerminationOperatorFailed);
    return;
  }
  if (!engine_v2_fgmres_isfinite(value)) {
    residual[index] = 0.0;
    engine_v2_terminal_failure(
        solve_record, kErrorArithmeticOverflow, kTerminationOperatorFailed);
    return;
  }
  residual[index] = engine_v2_fgmres_exact_zero(value);
}

extern "C" __global__ void engine_v2_fgmres_copy_scale_v1(
    int n,
    double scale,
    const double* input,
    double* output,
    unsigned char* solve_record) {
  if (!engine_v2_record_abi_or_fail(solve_record) ||
      !engine_v2_record_active(solve_record)) {
    return;
  }
  if (blockDim.x != kBlockSize || n <= 0 ||
      gridDim.x != engine_v2_fgmres_vector_grid(n) ||
      !engine_v2_fgmres_isfinite(scale)) {
    if (blockIdx.x == 0u && threadIdx.x == 0u) {
      engine_v2_terminal_failure(
          solve_record,
          kErrorInvalidControlOrGeometry,
          kTerminationRestartStateFailed);
    }
    return;
  }
  const unsigned long long index =
      static_cast<unsigned long long>(blockIdx.x) *
          static_cast<unsigned long long>(blockDim.x) +
      static_cast<unsigned long long>(threadIdx.x);
  if (index >= static_cast<unsigned long long>(n)) {
    return;
  }
  const double input_value = input[index];
  const double result = scale * input_value;
  if (!engine_v2_fgmres_isfinite(input_value)) {
    output[index] = 0.0;
    engine_v2_terminal_failure(
        solve_record, kErrorNonfiniteInput, kTerminationRestartStateFailed);
    return;
  }
  if (!engine_v2_fgmres_isfinite(result)) {
    output[index] = 0.0;
    engine_v2_terminal_failure(
        solve_record, kErrorArithmeticOverflow, kTerminationRestartStateFailed);
    return;
  }
  output[index] = engine_v2_fgmres_exact_zero(result);
}

extern "C" __global__ void engine_v2_fgmres_apply_jacobi_v1(
    int n,
    const double* inverse_diagonal,
    const double* input,
    double* output,
    unsigned char* solve_record) {
  if (!engine_v2_record_abi_or_fail(solve_record) ||
      !engine_v2_record_active(solve_record)) {
    return;
  }
  if (blockDim.x != kBlockSize || n <= 0 ||
      gridDim.x != engine_v2_fgmres_vector_grid(n)) {
    if (blockIdx.x == 0u && threadIdx.x == 0u) {
      engine_v2_terminal_failure(
          solve_record,
          kErrorInvalidControlOrGeometry,
          kTerminationRestartStateFailed);
    }
    return;
  }
  if (blockIdx.x == 0u && threadIdx.x == 0u) {
    engine_v2_increment_record_i32(
        solve_record, kOffsetPreconditionerApplyCount);
  }
  const unsigned long long index =
      static_cast<unsigned long long>(blockIdx.x) *
          static_cast<unsigned long long>(blockDim.x) +
      static_cast<unsigned long long>(threadIdx.x);
  if (index >= static_cast<unsigned long long>(n)) {
    return;
  }
  const double inverse = inverse_diagonal[index];
  const double input_value = input[index];
  const double result = inverse * input_value;
  if (!engine_v2_fgmres_isfinite(inverse) || !(inverse > 0.0)) {
    output[index] = 0.0;
    engine_v2_terminal_failure(
        solve_record, kErrorJacobi, kTerminationRestartStateFailed);
    return;
  }
  if (!engine_v2_fgmres_isfinite(input_value)) {
    output[index] = 0.0;
    engine_v2_terminal_failure(
        solve_record, kErrorNonfiniteInput, kTerminationRestartStateFailed);
    return;
  }
  if (!engine_v2_fgmres_isfinite(result)) {
    output[index] = 0.0;
    engine_v2_terminal_failure(
        solve_record, kErrorArithmeticOverflow, kTerminationRestartStateFailed);
    return;
  }
  output[index] = engine_v2_fgmres_exact_zero(result);
}

extern "C" __global__ void engine_v2_fgmres_control_terminal_v1(
    int control_mode,
    const double* residual_l2,
    const double* residual_linf,
    unsigned char* solve_record) {
  if (blockDim.x != kBlockSize || gridDim.x != 1u || threadIdx.x != 0u) {
    return;
  }
  if (!engine_v2_record_abi_or_fail(solve_record) ||
      !engine_v2_record_active(solve_record)) {
    return;
  }
  if (control_mode < kControlInitialTrueResidual ||
      control_mode > kControlMaxIterationsFinalize) {
    engine_v2_terminal_failure(
        solve_record,
        kErrorInvalidControlOrGeometry,
        kTerminationInvalidControl);
    return;
  }
  if (control_mode == kControlMaxIterationsFinalize) {
    if (engine_v2_load_i32_le(
            solve_record, kOffsetEffectiveIterations) !=
        engine_v2_load_i32_le(
            solve_record, kOffsetScheduledIterations)) {
      engine_v2_terminal_failure(
          solve_record,
          kErrorInvalidControlOrGeometry,
          kTerminationInvalidControl);
      return;
    }
    engine_v2_store_i32_le(solve_record, kOffsetActive, 0);
    engine_v2_store_i32_le(
        solve_record, kOffsetTerminalStatus, kTerminalMaxIterations);
    engine_v2_store_i32_le(
        solve_record, kOffsetTerminationCode, kTerminationMaxIterations);
    return;
  }
  const double checked_l2 = residual_l2[0];
  const double checked_linf = residual_linf[0];
  const double rhs_linf = engine_v2_load_f64_le(solve_record, kOffsetRhsLinf);
  const double scaled = checked_linf / fmax(1.0, rhs_linf);
  if (!engine_v2_fgmres_isfinite(checked_l2) || checked_l2 < 0.0 ||
      !engine_v2_fgmres_isfinite(checked_linf) || checked_linf < 0.0 ||
      !engine_v2_fgmres_isfinite(scaled)) {
    engine_v2_terminal_failure(
        solve_record,
        kErrorNonfiniteInput,
        kTerminationNonfiniteArithmetic);
    return;
  }
  engine_v2_store_f64_le(solve_record, kOffsetFinalResidualL2, checked_l2);
  engine_v2_store_f64_le(solve_record, kOffsetFinalResidualLinf, checked_linf);
  engine_v2_store_f64_le(solve_record, kOffsetFinalScaledResidual, scaled);
  if (control_mode == kControlInitialTrueResidual) {
    engine_v2_store_f64_le(
        solve_record, kOffsetInitialResidualL2, checked_l2);
    engine_v2_store_f64_le(
        solve_record, kOffsetPreviousCheckpointResidualL2, checked_l2);
  }
  const bool solver_pass = checked_l2 <=
      engine_v2_load_f64_le(solve_record, kOffsetSolverToleranceL2);
  const bool authoritative_pass = scaled <=
      engine_v2_load_f64_le(
          solve_record, kOffsetAuthoritativeTolerance);
  if (solver_pass && authoritative_pass) {
    engine_v2_store_i32_le(solve_record, kOffsetActive, 0);
    engine_v2_store_i32_le(
        solve_record, kOffsetTerminalStatus, kTerminalConverged);
    engine_v2_store_i32_le(
        solve_record,
        kOffsetTerminationCode,
        control_mode == kControlInitialTrueResidual
            ? kTerminationConvergedInitial
            : kTerminationConvergedTrueResidual);
    return;
  }
  if (control_mode == kControlInitialTrueResidual &&
      engine_v2_load_i32_le(solve_record, kOffsetScheduledIterations) == 0) {
    engine_v2_store_i32_le(solve_record, kOffsetActive, 0);
    engine_v2_store_i32_le(
        solve_record, kOffsetTerminalStatus, kTerminalMaxIterations);
    engine_v2_store_i32_le(
        solve_record, kOffsetTerminationCode, kTerminationMaxIterations);
  }
}

extern "C" __global__ void engine_v2_fgmres_record_restart_v1(
    int restart_index,
    int start_iteration,
    int end_iteration,
    int arnoldi_step_count,
    int reorthogonalization_count,
    int termination_hint,
    int flags,
    double estimated_residual_l2,
    double true_residual_l2,
    double true_residual_linf,
    double scaled_true_residual,
    double solution_update_l2,
    unsigned char* solve_record) {
  if (blockDim.x != kBlockSize || gridDim.x != 1u || threadIdx.x != 0u) {
    return;
  }
  if (!engine_v2_record_abi_or_fail(solve_record) ||
      !engine_v2_record_active(solve_record)) {
    return;
  }
  const int scheduled_restarts =
      engine_v2_load_i32_le(solve_record, kOffsetScheduledRestarts);
  const int scheduled_iterations =
      engine_v2_load_i32_le(solve_record, kOffsetScheduledIterations);
  const int restart_dimension =
      engine_v2_load_i32_le(solve_record, kOffsetRestartDimension);
  const int previous_restart =
      engine_v2_load_i32_le(solve_record, kOffsetEffectiveRestarts);
  const int previous_iteration =
      engine_v2_load_i32_le(solve_record, kOffsetEffectiveIterations);
  const bool scalar_values_valid =
      engine_v2_fgmres_isfinite(estimated_residual_l2) &&
      estimated_residual_l2 >= 0.0 &&
      engine_v2_fgmres_isfinite(true_residual_l2) &&
      true_residual_l2 >= 0.0 &&
      engine_v2_fgmres_isfinite(true_residual_linf) &&
      true_residual_linf >= 0.0 &&
      engine_v2_fgmres_isfinite(scaled_true_residual) &&
      scaled_true_residual >= 0.0 &&
      engine_v2_fgmres_isfinite(solution_update_l2) &&
      solution_update_l2 >= 0.0;
  const double recomputed_scaled = true_residual_linf /
      fmax(1.0, engine_v2_load_f64_le(solve_record, kOffsetRhsLinf));
  const bool solver_pass = true_residual_l2 <=
      engine_v2_load_f64_le(solve_record, kOffsetSolverToleranceL2);
  const bool authoritative_pass = recomputed_scaled <=
      engine_v2_load_f64_le(solve_record, kOffsetAuthoritativeTolerance);
  const bool flag_solver_pass =
      (flags & kRestartFlagSolverL2Passed) != 0;
  const bool flag_authoritative_pass =
      (flags & kRestartFlagAuthoritativeLinfPassed) != 0;
  const bool flag_happy = (flags & kRestartFlagHappyBreakdown) != 0;
  const bool flag_invariant =
      (flags & kRestartFlagInvariantBreakdown) != 0;
  const bool unsupported_terminal_flags =
      (flags & (kRestartFlagStagnationPlateau |
                kRestartFlagDivergence)) != 0;
  const bool gate_flags_valid =
      (flags & kRestartFlagTrueResidualReplayed) != 0 &&
      flag_solver_pass == solver_pass &&
      flag_authoritative_pass == authoritative_pass &&
      !(flag_happy && flag_invariant) && !unsupported_terminal_flags;
  const bool both_gates_pass = solver_pass && authoritative_pass;
  const bool hint_valid =
      (termination_hint == kRestartHintRestartCompleted &&
       !flag_happy && !flag_invariant) ||
      (termination_hint == kRestartHintConvergedHappyBreakdown &&
       both_gates_pass && flag_happy && !flag_invariant) ||
      (termination_hint == kRestartHintConvergedTrueResidual &&
       both_gates_pass && !flag_happy && !flag_invariant) ||
      (termination_hint == kRestartHintInvariantBreakdown &&
       !both_gates_pass && flag_invariant && !flag_happy) ||
      (termination_hint == kRestartHintTriangularBreakdown &&
       !both_gates_pass && !flag_happy && !flag_invariant);
  const int remaining_iterations = scheduled_iterations - start_iteration;
  const int expected_normal_steps = remaining_iterations < restart_dimension
      ? remaining_iterations
      : restart_dimension;
  if (restart_dimension < 1 ||
      restart_dimension > kMaximumRestartDimension ||
      restart_index != previous_restart + 1 ||
      restart_index > scheduled_restarts ||
      start_iteration != previous_iteration || end_iteration < start_iteration ||
      end_iteration > scheduled_iterations || arnoldi_step_count < 1 ||
      arnoldi_step_count != end_iteration - start_iteration ||
      arnoldi_step_count > restart_dimension ||
      reorthogonalization_count < 0 ||
      reorthogonalization_count > arnoldi_step_count || flags < 0 ||
      flags > 255 || !scalar_values_valid ||
      !engine_v2_fgmres_isfinite(recomputed_scaled) ||
      scaled_true_residual != recomputed_scaled || !gate_flags_valid ||
      !hint_valid ||
      (termination_hint == kRestartHintRestartCompleted &&
       arnoldi_step_count != expected_normal_steps)) {
    engine_v2_terminal_failure(
        solve_record,
        kErrorInvalidControlOrGeometry,
        kTerminationRestartStateFailed);
    return;
  }
  const int base = kHeaderBytes + (restart_index - 1) * kRestartBytes;
  engine_v2_store_i32_le(
      solve_record, base + kRestartOffsetIndex, restart_index);
  engine_v2_store_i32_le(
      solve_record, base + kRestartOffsetStartIteration, start_iteration);
  engine_v2_store_i32_le(
      solve_record, base + kRestartOffsetEndIteration, end_iteration);
  engine_v2_store_i32_le(
      solve_record, base + kRestartOffsetArnoldiStepCount, arnoldi_step_count);
  engine_v2_store_i32_le(
      solve_record,
      base + kRestartOffsetReorthogonalizationCount,
      reorthogonalization_count);
  engine_v2_store_i32_le(
      solve_record, base + kRestartOffsetTerminationHint, termination_hint);
  engine_v2_store_i32_le(
      solve_record, base + kRestartOffsetFlags, flags);
  engine_v2_store_f64_le(
      solve_record,
      base + kRestartOffsetEstimatedResidualL2,
      estimated_residual_l2);
  engine_v2_store_f64_le(
      solve_record, base + kRestartOffsetTrueResidualL2, true_residual_l2);
  engine_v2_store_f64_le(
      solve_record,
      base + kRestartOffsetTrueResidualLinf,
      true_residual_linf);
  engine_v2_store_f64_le(
      solve_record,
      base + kRestartOffsetScaledTrueResidual,
      scaled_true_residual);
  engine_v2_store_f64_le(
      solve_record,
      base + kRestartOffsetSolutionUpdateL2,
      solution_update_l2);
  engine_v2_store_i32_le(
      solve_record, kOffsetEffectiveIterations, end_iteration);
  engine_v2_store_i32_le(
      solve_record, kOffsetEffectiveRestarts, restart_index);
  engine_v2_store_i32_le(
      solve_record, kOffsetEffectiveArnoldiDimension, arnoldi_step_count);
  engine_v2_store_f64_le(
      solve_record, kOffsetEstimatedResidualL2, estimated_residual_l2);
  engine_v2_store_f64_le(
      solve_record, kOffsetFinalResidualL2, true_residual_l2);
  engine_v2_store_f64_le(
      solve_record, kOffsetFinalResidualLinf, true_residual_linf);
  engine_v2_store_f64_le(
      solve_record, kOffsetFinalScaledResidual, scaled_true_residual);
  engine_v2_store_f64_le(
      solve_record, kOffsetSolutionUpdateL2, solution_update_l2);
  if ((termination_hint == kRestartHintRestartCompleted && both_gates_pass) ||
      termination_hint == kRestartHintConvergedHappyBreakdown ||
      termination_hint == kRestartHintConvergedTrueResidual) {
    engine_v2_store_i32_le(solve_record, kOffsetActive, 0);
    engine_v2_store_i32_le(
        solve_record, kOffsetTerminalStatus, kTerminalConverged);
    engine_v2_store_i32_le(
        solve_record,
        kOffsetTerminationCode,
        termination_hint == kRestartHintConvergedHappyBreakdown
            ? kTerminationConvergedHappyBreakdown
            : (termination_hint == kRestartHintConvergedTrueResidual
                   ? kTerminationConvergedTrueResidual
                   : kTerminationConvergedRestart));
  }
}
