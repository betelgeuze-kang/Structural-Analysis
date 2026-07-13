#pragma clang fp contract(off)

namespace {

constexpr int kBlockSize = 256;

constexpr int kErrorInvalidCountOrGeometry = 1;
constexpr int kErrorFreeDofBounds = 2;
constexpr int kErrorReducedValueIndexBounds = 3;
constexpr int kErrorReducedCsrSegment = 4;
constexpr int kErrorReducedColumnBounds = 5;
constexpr int kErrorGlobalToFreeBounds = 6;
constexpr int kErrorNonfinite = 7;

__device__ __forceinline__ void engine_v2_record_free_space_error(
    int* error_flag,
    int code) {
  atomicCAS(error_flag, 0, code);
}

__device__ __forceinline__ bool engine_v2_free_space_isfinite(double value) {
  return isfinite(value);
}

__device__ __forceinline__ double engine_v2_free_space_exact_zero(
    double value) {
  return value == 0.0 ? 0.0 : value;
}

}  // namespace

extern "C" __global__ void engine_v2_free_space_materialize_v1(
    int global_dof_count,
    int full_nnz_count,
    int free_dof_count,
    int reduced_nnz_count,
    const int* free_dofs,
    const int* reduced_global_value_indices,
    const double* full_csr_values,
    const double* full_state,
    const double* full_load,
    double* reduced_csr_values,
    double* reduced_state,
    double* reduced_load,
    int* error_flag) {
  if (blockDim.x != kBlockSize || global_dof_count <= 0 ||
      full_nnz_count <= 0 || free_dof_count <= 0 ||
      reduced_nnz_count <= 0 || free_dof_count > global_dof_count ||
      reduced_nnz_count > full_nnz_count) {
    if (blockIdx.x == 0u && threadIdx.x == 0u) {
      engine_v2_record_free_space_error(
          error_flag, kErrorInvalidCountOrGeometry);
    }
    return;
  }

  const unsigned long long index =
      static_cast<unsigned long long>(blockIdx.x) *
          static_cast<unsigned long long>(blockDim.x) +
      static_cast<unsigned long long>(threadIdx.x);

  if (index < static_cast<unsigned long long>(reduced_nnz_count)) {
    const int full_index = reduced_global_value_indices[index];
    if (full_index < 0 || full_index >= full_nnz_count) {
      reduced_csr_values[index] = 0.0;
      engine_v2_record_free_space_error(
          error_flag, kErrorReducedValueIndexBounds);
    } else {
      const double value = full_csr_values[full_index];
      if (!engine_v2_free_space_isfinite(value)) {
        reduced_csr_values[index] = 0.0;
        engine_v2_record_free_space_error(error_flag, kErrorNonfinite);
      } else {
        reduced_csr_values[index] =
            engine_v2_free_space_exact_zero(value);
      }
    }
  }

  if (index < static_cast<unsigned long long>(free_dof_count)) {
    const int global_index = free_dofs[index];
    if (global_index < 0 || global_index >= global_dof_count) {
      reduced_state[index] = 0.0;
      reduced_load[index] = 0.0;
      engine_v2_record_free_space_error(error_flag, kErrorFreeDofBounds);
    } else {
      const double state = full_state[global_index];
      const double load = full_load[global_index];
      if (!engine_v2_free_space_isfinite(state) ||
          !engine_v2_free_space_isfinite(load)) {
        reduced_state[index] = 0.0;
        reduced_load[index] = 0.0;
        engine_v2_record_free_space_error(error_flag, kErrorNonfinite);
      } else {
        reduced_state[index] = engine_v2_free_space_exact_zero(state);
        reduced_load[index] = engine_v2_free_space_exact_zero(load);
      }
    }
  }
}

extern "C" __global__ void engine_v2_free_space_residual_direction_v1(
    int global_dof_count,
    int free_dof_count,
    int reduced_nnz_count,
    const int* global_to_free,
    const int* reduced_row_ptr,
    const int* reduced_column_indices,
    const double* reduced_csr_values,
    const double* reduced_state,
    const double* reduced_load,
    double* reduced_direction,
    double* reduced_residual,
    double* full_direction,
    int* error_flag) {
  if (blockDim.x != kBlockSize || global_dof_count <= 0 ||
      free_dof_count <= 0 || reduced_nnz_count <= 0 ||
      free_dof_count > global_dof_count) {
    if (blockIdx.x == 0u && threadIdx.x == 0u) {
      engine_v2_record_free_space_error(
          error_flag, kErrorInvalidCountOrGeometry);
    }
    return;
  }

  const unsigned long long global_index =
      static_cast<unsigned long long>(blockIdx.x) *
          static_cast<unsigned long long>(blockDim.x) +
      static_cast<unsigned long long>(threadIdx.x);
  if (global_index >= static_cast<unsigned long long>(global_dof_count)) {
    return;
  }

  const int reduced_row = global_to_free[global_index];
  if (reduced_row == -1) {
    full_direction[global_index] = 0.0;
    return;
  }
  if (reduced_row < 0 || reduced_row >= free_dof_count) {
    full_direction[global_index] = 0.0;
    engine_v2_record_free_space_error(
        error_flag, kErrorGlobalToFreeBounds);
    return;
  }

  const int row_begin = reduced_row_ptr[reduced_row];
  const int row_end = reduced_row_ptr[reduced_row + 1];
  if (row_begin < 0 || row_end < row_begin || row_end > reduced_nnz_count) {
    reduced_direction[reduced_row] = 0.0;
    reduced_residual[reduced_row] = 0.0;
    full_direction[global_index] = 0.0;
    engine_v2_record_free_space_error(error_flag, kErrorReducedCsrSegment);
    return;
  }

  double internal_force = 0.0;
  bool valid = true;
  for (int position = row_begin; position < row_end; ++position) {
    const int column = reduced_column_indices[position];
    if (column < 0 || column >= free_dof_count) {
      valid = false;
      engine_v2_record_free_space_error(
          error_flag, kErrorReducedColumnBounds);
      break;
    }
    const double coefficient = reduced_csr_values[position];
    const double state = reduced_state[column];
    if (!engine_v2_free_space_isfinite(coefficient) ||
        !engine_v2_free_space_isfinite(state)) {
      valid = false;
      engine_v2_record_free_space_error(error_flag, kErrorNonfinite);
      break;
    }
    internal_force += coefficient * state;
    if (!engine_v2_free_space_isfinite(internal_force)) {
      valid = false;
      engine_v2_record_free_space_error(error_flag, kErrorNonfinite);
      break;
    }
  }

  const double load = reduced_load[reduced_row];
  const double residual = load - internal_force;
  if (!valid || !engine_v2_free_space_isfinite(load) ||
      !engine_v2_free_space_isfinite(residual)) {
    reduced_direction[reduced_row] = 0.0;
    reduced_residual[reduced_row] = 0.0;
    full_direction[global_index] = 0.0;
    engine_v2_record_free_space_error(error_flag, kErrorNonfinite);
    return;
  }

  const double normalized_residual =
      engine_v2_free_space_exact_zero(residual);
  reduced_direction[reduced_row] = normalized_residual;
  reduced_residual[reduced_row] = normalized_residual;
  full_direction[global_index] = normalized_residual;
}

extern "C" __global__ void engine_v2_free_space_gather_jvp_v1(
    int global_dof_count,
    int free_dof_count,
    const int* free_dofs,
    const double* full_jvp,
    double* reduced_jvp,
    int* error_flag) {
  if (blockDim.x != kBlockSize || global_dof_count <= 0 ||
      free_dof_count <= 0 || free_dof_count > global_dof_count) {
    if (blockIdx.x == 0u && threadIdx.x == 0u) {
      engine_v2_record_free_space_error(
          error_flag, kErrorInvalidCountOrGeometry);
    }
    return;
  }

  const unsigned long long index =
      static_cast<unsigned long long>(blockIdx.x) *
          static_cast<unsigned long long>(blockDim.x) +
      static_cast<unsigned long long>(threadIdx.x);
  if (index >= static_cast<unsigned long long>(free_dof_count)) {
    return;
  }

  const int global_index = free_dofs[index];
  if (global_index < 0 || global_index >= global_dof_count) {
    reduced_jvp[index] = 0.0;
    engine_v2_record_free_space_error(error_flag, kErrorFreeDofBounds);
    return;
  }
  const double value = full_jvp[global_index];
  if (!engine_v2_free_space_isfinite(value)) {
    reduced_jvp[index] = 0.0;
    engine_v2_record_free_space_error(error_flag, kErrorNonfinite);
    return;
  }
  reduced_jvp[index] = engine_v2_free_space_exact_zero(value);
}
