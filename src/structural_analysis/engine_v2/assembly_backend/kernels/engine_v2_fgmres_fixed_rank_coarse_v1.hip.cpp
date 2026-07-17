// Fixed-rank coarse right-preconditioner application ABI v1.
//
// The caller owns and validates every pointer/extent, uploads Z/AZ/L once,
// and enqueues the four symbols below on the same FGMRES stream.  No kernel
// performs allocation, host transfer, synchronization, or CSR traversal.

constexpr int kCoarseBlockSize = 256;
constexpr int kCoarseMaximumRank = 16;

constexpr unsigned int kErrorInvalidGeometry = 1u << 0;
constexpr unsigned int kErrorNonfiniteInput = 1u << 1;
constexpr unsigned int kErrorNonpositiveFactor = 1u << 2;
constexpr unsigned int kErrorNonfiniteArithmetic = 1u << 3;

__device__ __forceinline__ bool engine_v2_coarse_isfinite(double value) {
  return isfinite(value);
}

__device__ __forceinline__ double engine_v2_coarse_exact_zero(double value) {
  return value == 0.0 ? 0.0 : value;
}

__device__ __forceinline__ double engine_v2_coarse_canonical_nan() {
  return __longlong_as_double(0x7ff8000000000000ull);
}

extern "C" __global__ void
engine_v2_fgmres_fixed_rank_coarse_prepare_v1(
    int free_dof_count,
    int retained_rank,
    int restart_dimension,
    int logical_index,
    double* coarse_rhs,
    double* coarse_coefficients,
    unsigned int* coarse_status) {
  if (gridDim.x != 1u || blockDim.x != 1u || threadIdx.x != 0u) {
    return;
  }
  *coarse_status = 0u;
  if (free_dof_count <= 0 || retained_rank <= 0 ||
      retained_rank > kCoarseMaximumRank || restart_dimension <= 0 ||
      logical_index < 0 || logical_index >= restart_dimension) {
    *coarse_status = kErrorInvalidGeometry;
    return;
  }
  for (int index = 0; index < retained_rank; ++index) {
    coarse_rhs[index] = 0.0;
    coarse_coefficients[index] = 0.0;
  }
}

extern "C" __global__ void engine_v2_fgmres_fixed_rank_coarse_dot_v1(
    int free_dof_count,
    int retained_rank,
    int restart_dimension,
    int logical_index,
    const double* basis_v,
    const double* coarse_physical_basis_z,
    double* coarse_rhs,
    unsigned int* coarse_status) {
  __shared__ double shared_sum[kCoarseBlockSize];
  __shared__ unsigned int shared_error[kCoarseBlockSize];
  __shared__ unsigned int shared_gate;
  const int lane = static_cast<int>(threadIdx.x);
  const int mode = static_cast<int>(blockIdx.x);
  if (blockDim.x != kCoarseBlockSize || gridDim.x != retained_rank ||
      free_dof_count <= 0 || retained_rank <= 0 ||
      retained_rank > kCoarseMaximumRank || restart_dimension <= 0 ||
      logical_index < 0 || logical_index >= restart_dimension || mode < 0 ||
      mode >= retained_rank) {
    if (lane == 0) {
      atomicOr(coarse_status, kErrorInvalidGeometry);
    }
    return;
  }
  if (lane == 0) {
    shared_gate = *coarse_status;
  }
  __syncthreads();
  if (shared_gate != 0u) {
    return;
  }
  double accumulator = 0.0;
  unsigned int error = 0u;
  const unsigned long long input_offset =
      static_cast<unsigned long long>(logical_index) *
      static_cast<unsigned long long>(free_dof_count);
  for (int row = lane; row < free_dof_count; row += kCoarseBlockSize) {
    const double residual = basis_v[input_offset + row];
    const double basis = coarse_physical_basis_z[
        static_cast<unsigned long long>(row) * retained_rank + mode];
    if (!engine_v2_coarse_isfinite(residual) ||
        !engine_v2_coarse_isfinite(basis)) {
      error |= kErrorNonfiniteInput;
      continue;
    }
    const double product = basis * residual;
    const double updated = accumulator + product;
    if (!engine_v2_coarse_isfinite(product) ||
        !engine_v2_coarse_isfinite(updated)) {
      error |= kErrorNonfiniteArithmetic;
      continue;
    }
    accumulator = updated;
  }
  shared_sum[lane] = accumulator;
  shared_error[lane] = error;
  __syncthreads();
  for (int stride = kCoarseBlockSize / 2; stride > 0; stride >>= 1) {
    if (lane < stride) {
      const double updated = shared_sum[lane] + shared_sum[lane + stride];
      shared_error[lane] |= shared_error[lane + stride];
      if (!engine_v2_coarse_isfinite(updated)) {
        shared_error[lane] |= kErrorNonfiniteArithmetic;
      } else {
        shared_sum[lane] = updated;
      }
    }
    __syncthreads();
  }
  if (lane == 0) {
    if (shared_error[0] != 0u) {
      atomicOr(coarse_status, shared_error[0]);
      coarse_rhs[mode] = 0.0;
    } else {
      coarse_rhs[mode] = engine_v2_coarse_exact_zero(shared_sum[0]);
    }
  }
}

extern "C" __global__ void engine_v2_fgmres_fixed_rank_coarse_solve_v1(
    int retained_rank,
    const double* coarse_cholesky_l,
    const double* coarse_rhs,
    double* coarse_coefficients,
    unsigned int* coarse_status) {
  if (gridDim.x != 1u || blockDim.x != 1u || threadIdx.x != 0u) {
    return;
  }
  if (retained_rank <= 0 || retained_rank > kCoarseMaximumRank) {
    atomicOr(coarse_status, kErrorInvalidGeometry);
    return;
  }
  if (*coarse_status != 0u) {
    return;
  }
  double forward[kCoarseMaximumRank];
  double result[kCoarseMaximumRank];
  unsigned int error = 0u;
  for (int row = 0; row < retained_rank; ++row) {
    const double rhs = coarse_rhs[row];
    const double pivot = coarse_cholesky_l[row * retained_rank + row];
    if (!engine_v2_coarse_isfinite(rhs) ||
        !engine_v2_coarse_isfinite(pivot)) {
      error |= kErrorNonfiniteInput;
      break;
    }
    if (pivot <= 0.0) {
      error |= kErrorNonpositiveFactor;
      break;
    }
    double numerator = rhs;
    for (int column = 0; column < row; ++column) {
      const double factor =
          coarse_cholesky_l[row * retained_rank + column];
      const double product = factor * forward[column];
      const double updated = numerator - product;
      if (!engine_v2_coarse_isfinite(factor) ||
          !engine_v2_coarse_isfinite(product) ||
          !engine_v2_coarse_isfinite(updated)) {
        error |= kErrorNonfiniteArithmetic;
        break;
      }
      numerator = updated;
    }
    if (error != 0u) {
      break;
    }
    const double value = numerator / pivot;
    if (!engine_v2_coarse_isfinite(value)) {
      error |= kErrorNonfiniteArithmetic;
      break;
    }
    forward[row] = value;
  }
  for (int row = retained_rank - 1; row >= 0 && error == 0u; --row) {
    const double pivot = coarse_cholesky_l[row * retained_rank + row];
    if (!engine_v2_coarse_isfinite(pivot) || pivot <= 0.0) {
      error |= !engine_v2_coarse_isfinite(pivot)
          ? kErrorNonfiniteInput
          : kErrorNonpositiveFactor;
      break;
    }
    double numerator = forward[row];
    for (int column = row + 1; column < retained_rank; ++column) {
      const double factor =
          coarse_cholesky_l[column * retained_rank + row];
      const double product = factor * result[column];
      const double updated = numerator - product;
      if (!engine_v2_coarse_isfinite(factor) ||
          !engine_v2_coarse_isfinite(product) ||
          !engine_v2_coarse_isfinite(updated)) {
        error |= kErrorNonfiniteArithmetic;
        break;
      }
      numerator = updated;
    }
    if (error != 0u) {
      break;
    }
    const double value = numerator / pivot;
    if (!engine_v2_coarse_isfinite(value)) {
      error |= kErrorNonfiniteArithmetic;
      break;
    }
    result[row] = value;
  }
  if (error != 0u) {
    atomicOr(coarse_status, error);
    for (int index = 0; index < retained_rank; ++index) {
      coarse_coefficients[index] = 0.0;
    }
    return;
  }
  for (int index = 0; index < retained_rank; ++index) {
    coarse_coefficients[index] =
        engine_v2_coarse_exact_zero(result[index]);
  }
}

extern "C" __global__ void engine_v2_fgmres_fixed_rank_coarse_apply_v1(
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
      (static_cast<unsigned int>(free_dof_count) + kCoarseBlockSize - 1u) /
      kCoarseBlockSize;
  if (blockDim.x != kCoarseBlockSize ||
      gridDim.x != expected_grid || free_dof_count <= 0 ||
      retained_rank <= 0 || retained_rank > kCoarseMaximumRank ||
      restart_dimension <= 0 || logical_index < 0 ||
      logical_index >= restart_dimension) {
    if (row == 0) {
      atomicOr(coarse_status, kErrorInvalidGeometry);
    }
    return;
  }
  if (row >= free_dof_count) {
    return;
  }
  const unsigned long long vector_offset =
      static_cast<unsigned long long>(logical_index) *
      static_cast<unsigned long long>(free_dof_count);
  if (*coarse_status != 0u) {
    preconditioned_basis_z[vector_offset + row] =
        engine_v2_coarse_canonical_nan();
    return;
  }
  const double residual = basis_v[vector_offset + row];
  const double inverse = jacobi_inverse[row];
  if (!engine_v2_coarse_isfinite(residual) ||
      !engine_v2_coarse_isfinite(inverse) || inverse <= 0.0) {
    atomicOr(
        coarse_status,
        !engine_v2_coarse_isfinite(residual) ||
                !engine_v2_coarse_isfinite(inverse)
            ? kErrorNonfiniteInput
            : kErrorNonpositiveFactor);
    preconditioned_basis_z[vector_offset + row] =
        engine_v2_coarse_canonical_nan();
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
    if (!engine_v2_coarse_isfinite(coefficient) ||
        !engine_v2_coarse_isfinite(basis) ||
        !engine_v2_coarse_isfinite(image)) {
      error |= kErrorNonfiniteInput;
      break;
    }
    const double basis_product = coefficient * basis;
    const double image_product = coefficient * image;
    const double updated_correction = coarse_correction + basis_product;
    const double updated_image = coarse_image + image_product;
    if (!engine_v2_coarse_isfinite(basis_product) ||
        !engine_v2_coarse_isfinite(image_product) ||
        !engine_v2_coarse_isfinite(updated_correction) ||
        !engine_v2_coarse_isfinite(updated_image)) {
      error |= kErrorNonfiniteArithmetic;
      break;
    }
    coarse_correction = updated_correction;
    coarse_image = updated_image;
  }
  const double smoothed = inverse * (residual - coarse_image);
  const double output = coarse_correction + smoothed;
  if (error != 0u || !engine_v2_coarse_isfinite(smoothed) ||
      !engine_v2_coarse_isfinite(output)) {
    atomicOr(
        coarse_status,
        error != 0u ? error : kErrorNonfiniteArithmetic);
    preconditioned_basis_z[vector_offset + row] =
        engine_v2_coarse_canonical_nan();
    return;
  }
  preconditioned_basis_z[vector_offset + row] =
      engine_v2_coarse_exact_zero(output);
}
