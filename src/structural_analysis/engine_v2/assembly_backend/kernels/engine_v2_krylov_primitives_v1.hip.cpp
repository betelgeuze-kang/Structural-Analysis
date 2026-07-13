#pragma clang fp contract(off)

namespace {

constexpr int kBlockSize = 256;
constexpr int kReductionValuesPerBlock = 512;

constexpr int kErrorInvalidCountOrGeometry = 1 << 0;
constexpr int kErrorCsrStructure = 1 << 1;
constexpr int kErrorJacobiDiagonal = 1 << 2;
constexpr int kErrorNonfiniteInput = 1 << 3;
constexpr int kErrorArithmeticOverflow = 1 << 4;
constexpr int kErrorInvalidLassqPair = 1 << 5;

__device__ __forceinline__ void engine_v2_record_krylov_error(
    int* error_flag,
    int bit) {
  atomicOr(
      reinterpret_cast<unsigned int*>(error_flag),
      static_cast<unsigned int>(bit));
}

__device__ __forceinline__ bool engine_v2_krylov_isfinite(double value) {
  return isfinite(value);
}

__device__ __forceinline__ double engine_v2_krylov_exact_zero(
    double value) {
  return value == 0.0 ? 0.0 : value;
}

__device__ __forceinline__ unsigned int engine_v2_vector_grid(int count) {
  const unsigned long long promoted_count =
      static_cast<unsigned long long>(count);
  return static_cast<unsigned int>(
      (promoted_count + static_cast<unsigned long long>(kBlockSize) - 1u) /
      static_cast<unsigned long long>(kBlockSize));
}

__device__ __forceinline__ unsigned int engine_v2_reduction_grid(int count) {
  const unsigned long long promoted_count =
      static_cast<unsigned long long>(count);
  return static_cast<unsigned int>(
      (promoted_count +
       static_cast<unsigned long long>(kReductionValuesPerBlock) - 1u) /
      static_cast<unsigned long long>(kReductionValuesPerBlock));
}

struct EngineV2LassqPair {
  double scale;
  double ssq;
};

__device__ __forceinline__ EngineV2LassqPair engine_v2_lassq_zero_pair() {
  EngineV2LassqPair result;
  result.scale = 0.0;
  result.ssq = 1.0;
  return result;
}

__device__ __forceinline__ bool engine_v2_lassq_pair_valid(
    EngineV2LassqPair value) {
  if (!engine_v2_krylov_isfinite(value.scale) ||
      !engine_v2_krylov_isfinite(value.ssq) || value.scale < 0.0 ||
      value.ssq < 1.0) {
    return false;
  }
  if (value.scale == 0.0 && value.ssq != 1.0) {
    return false;
  }
  return true;
}

__device__ __forceinline__ EngineV2LassqPair engine_v2_lassq_value_pair(
    double value) {
  EngineV2LassqPair result = engine_v2_lassq_zero_pair();
  const double magnitude = fabs(value);
  if (magnitude != 0.0) {
    result.scale = magnitude;
    result.ssq = 1.0;
  }
  return result;
}

__device__ __forceinline__ bool engine_v2_lassq_merge(
    EngineV2LassqPair left,
    EngineV2LassqPair right,
    EngineV2LassqPair* output) {
  if (!engine_v2_lassq_pair_valid(left) ||
      !engine_v2_lassq_pair_valid(right)) {
    *output = engine_v2_lassq_zero_pair();
    return false;
  }
  if (left.scale == 0.0) {
    *output = right;
    return true;
  }
  if (right.scale == 0.0) {
    *output = left;
    return true;
  }

  EngineV2LassqPair result;
  if (left.scale >= right.scale) {
    const double ratio = right.scale / left.scale;
    const double contribution = right.ssq * ratio * ratio;
    result.scale = left.scale;
    result.ssq = left.ssq + contribution;
  } else {
    const double ratio = left.scale / right.scale;
    const double contribution = left.ssq * ratio * ratio;
    result.scale = right.scale;
    result.ssq = right.ssq + contribution;
  }
  if (!engine_v2_lassq_pair_valid(result)) {
    *output = engine_v2_lassq_zero_pair();
    return false;
  }
  result.scale = engine_v2_krylov_exact_zero(result.scale);
  *output = result;
  return true;
}

}  // namespace

extern "C" __global__ void prepare_positive_jacobi(
    int n,
    int nnz,
    const int* row_ptr,
    const int* column_indices,
    const double* values,
    double* inverse_diagonal,
    int* error_flag) {
  if (blockDim.x != kBlockSize || n <= 0 || nnz <= 0 || nnz < n ||
      gridDim.x != engine_v2_vector_grid(n)) {
    if (blockIdx.x == 0u && threadIdx.x == 0u) {
      engine_v2_record_krylov_error(
          error_flag, kErrorInvalidCountOrGeometry);
    }
    return;
  }

  const unsigned long long row =
      static_cast<unsigned long long>(blockIdx.x) *
          static_cast<unsigned long long>(blockDim.x) +
      static_cast<unsigned long long>(threadIdx.x);
  if (row >= static_cast<unsigned long long>(n)) {
    return;
  }

  const int row_begin = row_ptr[row];
  const int row_end = row_ptr[row + 1u];
  if (row_begin < 0 || row_end < row_begin || row_end > nnz) {
    inverse_diagonal[row] = 0.0;
    engine_v2_record_krylov_error(error_flag, kErrorCsrStructure);
    return;
  }

  int diagonal_count = 0;
  double diagonal = 0.0;
  bool valid = true;
  for (int position = row_begin; position < row_end; ++position) {
    const int column = column_indices[position];
    const double value = values[position];
    if (column < 0 || column >= n) {
      valid = false;
      engine_v2_record_krylov_error(error_flag, kErrorCsrStructure);
    }
    if (!engine_v2_krylov_isfinite(value)) {
      valid = false;
      engine_v2_record_krylov_error(error_flag, kErrorNonfiniteInput);
    }
    if (column == static_cast<int>(row)) {
      ++diagonal_count;
      diagonal = value;
    }
  }
  if (!valid || diagonal_count != 1 ||
      !engine_v2_krylov_isfinite(diagonal) || !(diagonal > 0.0)) {
    inverse_diagonal[row] = 0.0;
    engine_v2_record_krylov_error(error_flag, kErrorJacobiDiagonal);
    return;
  }

  const double reciprocal = 1.0 / diagonal;
  if (!engine_v2_krylov_isfinite(reciprocal) || !(reciprocal > 0.0)) {
    inverse_diagonal[row] = 0.0;
    engine_v2_record_krylov_error(error_flag, kErrorArithmeticOverflow);
    return;
  }
  inverse_diagonal[row] = reciprocal;
}

extern "C" __global__ void fill(
    int n,
    double value,
    double* output,
    int* error_flag) {
  if (blockDim.x != kBlockSize || n <= 0 ||
      gridDim.x != engine_v2_vector_grid(n)) {
    if (blockIdx.x == 0u && threadIdx.x == 0u) {
      engine_v2_record_krylov_error(
          error_flag, kErrorInvalidCountOrGeometry);
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
  if (!engine_v2_krylov_isfinite(value)) {
    output[index] = 0.0;
    engine_v2_record_krylov_error(error_flag, kErrorNonfiniteInput);
    return;
  }
  output[index] = engine_v2_krylov_exact_zero(value);
}

extern "C" __global__ void affine(
    int n,
    double alpha,
    const double* x,
    double beta,
    const double* y,
    double* output,
    int* error_flag) {
  if (blockDim.x != kBlockSize || n <= 0 ||
      gridDim.x != engine_v2_vector_grid(n)) {
    if (blockIdx.x == 0u && threadIdx.x == 0u) {
      engine_v2_record_krylov_error(
          error_flag, kErrorInvalidCountOrGeometry);
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

  const double x_value = x[index];
  const double y_value = y[index];
  if (!engine_v2_krylov_isfinite(alpha) ||
      !engine_v2_krylov_isfinite(beta) ||
      !engine_v2_krylov_isfinite(x_value) ||
      !engine_v2_krylov_isfinite(y_value)) {
    output[index] = 0.0;
    engine_v2_record_krylov_error(error_flag, kErrorNonfiniteInput);
    return;
  }
  const double left = alpha * x_value;
  const double right = beta * y_value;
  const double result = left + right;
  if (!engine_v2_krylov_isfinite(left) ||
      !engine_v2_krylov_isfinite(right) ||
      !engine_v2_krylov_isfinite(result)) {
    output[index] = 0.0;
    engine_v2_record_krylov_error(error_flag, kErrorArithmeticOverflow);
    return;
  }
  output[index] = engine_v2_krylov_exact_zero(result);
}

extern "C" __global__ void apply_jacobi(
    int n,
    const double* inverse_diagonal,
    const double* x,
    double* output,
    int* error_flag) {
  if (blockDim.x != kBlockSize || n <= 0 ||
      gridDim.x != engine_v2_vector_grid(n)) {
    if (blockIdx.x == 0u && threadIdx.x == 0u) {
      engine_v2_record_krylov_error(
          error_flag, kErrorInvalidCountOrGeometry);
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
  const double inverse = inverse_diagonal[index];
  const double value = x[index];
  if (!engine_v2_krylov_isfinite(inverse) || !(inverse > 0.0) ||
      !engine_v2_krylov_isfinite(value)) {
    output[index] = 0.0;
    engine_v2_record_krylov_error(error_flag, kErrorNonfiniteInput);
    return;
  }
  const double result = inverse * value;
  if (!engine_v2_krylov_isfinite(result)) {
    output[index] = 0.0;
    engine_v2_record_krylov_error(error_flag, kErrorArithmeticOverflow);
    return;
  }
  output[index] = engine_v2_krylov_exact_zero(result);
}

extern "C" __global__ void dot_stage(
    int n,
    const double* x,
    const double* y,
    double* partial,
    int* error_flag) {
  __shared__ double shared_values[kBlockSize];
  __shared__ int shared_valid[kBlockSize];

  if (blockDim.x != kBlockSize || n <= 0 ||
      gridDim.x != engine_v2_reduction_grid(n)) {
    if (blockIdx.x == 0u && threadIdx.x == 0u) {
      engine_v2_record_krylov_error(
          error_flag, kErrorInvalidCountOrGeometry);
    }
    return;
  }
  const unsigned int lane = threadIdx.x;
  const unsigned long long segment_begin =
      static_cast<unsigned long long>(blockIdx.x) *
      static_cast<unsigned long long>(kReductionValuesPerBlock);
  const unsigned long long first = segment_begin + lane;
  const unsigned long long second = first + kBlockSize;

  double accumulator = 0.0;
  bool valid = true;
  if (first < static_cast<unsigned long long>(n)) {
    const double x_value = x[first];
    const double y_value = y[first];
    if (!engine_v2_krylov_isfinite(x_value) ||
        !engine_v2_krylov_isfinite(y_value)) {
      valid = false;
      engine_v2_record_krylov_error(error_flag, kErrorNonfiniteInput);
    } else {
      accumulator = x_value * y_value;
      if (!engine_v2_krylov_isfinite(accumulator)) {
        valid = false;
        accumulator = 0.0;
        engine_v2_record_krylov_error(
            error_flag, kErrorArithmeticOverflow);
      }
    }
  }
  if (second < static_cast<unsigned long long>(n)) {
    const double x_value = x[second];
    const double y_value = y[second];
    if (!engine_v2_krylov_isfinite(x_value) ||
        !engine_v2_krylov_isfinite(y_value)) {
      valid = false;
      engine_v2_record_krylov_error(error_flag, kErrorNonfiniteInput);
    } else {
      const double product = x_value * y_value;
      const double sum = accumulator + product;
      if (!engine_v2_krylov_isfinite(product) ||
          !engine_v2_krylov_isfinite(sum)) {
        valid = false;
        accumulator = 0.0;
        engine_v2_record_krylov_error(
            error_flag, kErrorArithmeticOverflow);
      } else {
        accumulator = sum;
      }
    }
  }
  shared_values[lane] = accumulator;
  shared_valid[lane] = valid ? 1 : 0;
  __syncthreads();

  for (unsigned int offset = kBlockSize / 2; offset > 0u; offset >>= 1u) {
    if (lane < offset) {
      const bool pair_valid =
          shared_valid[lane] != 0 && shared_valid[lane + offset] != 0;
      const double sum = shared_values[lane] + shared_values[lane + offset];
      if (!pair_valid || !engine_v2_krylov_isfinite(sum)) {
        shared_values[lane] = 0.0;
        shared_valid[lane] = 0;
        if (pair_valid) {
          engine_v2_record_krylov_error(
              error_flag, kErrorArithmeticOverflow);
        }
      } else {
        shared_values[lane] = sum;
        shared_valid[lane] = 1;
      }
    }
    __syncthreads();
  }
  if (lane == 0u) {
    partial[blockIdx.x] = shared_valid[0] != 0
        ? engine_v2_krylov_exact_zero(shared_values[0])
        : 0.0;
  }
}

extern "C" __global__ void sum_stage(
    int n,
    const double* input,
    double* partial,
    int* error_flag) {
  __shared__ double shared_values[kBlockSize];
  __shared__ int shared_valid[kBlockSize];

  if (blockDim.x != kBlockSize || n <= 0 ||
      gridDim.x != engine_v2_reduction_grid(n)) {
    if (blockIdx.x == 0u && threadIdx.x == 0u) {
      engine_v2_record_krylov_error(
          error_flag, kErrorInvalidCountOrGeometry);
    }
    return;
  }
  const unsigned int lane = threadIdx.x;
  const unsigned long long segment_begin =
      static_cast<unsigned long long>(blockIdx.x) *
      static_cast<unsigned long long>(kReductionValuesPerBlock);
  const unsigned long long first = segment_begin + lane;
  const unsigned long long second = first + kBlockSize;
  double accumulator = 0.0;
  bool valid = true;
  if (first < static_cast<unsigned long long>(n)) {
    accumulator = input[first];
    if (!engine_v2_krylov_isfinite(accumulator)) {
      accumulator = 0.0;
      valid = false;
      engine_v2_record_krylov_error(error_flag, kErrorNonfiniteInput);
    }
  }
  if (second < static_cast<unsigned long long>(n)) {
    const double value = input[second];
    const double sum = accumulator + value;
    if (!engine_v2_krylov_isfinite(value)) {
      valid = false;
      accumulator = 0.0;
      engine_v2_record_krylov_error(error_flag, kErrorNonfiniteInput);
    } else if (!engine_v2_krylov_isfinite(sum)) {
      valid = false;
      accumulator = 0.0;
      engine_v2_record_krylov_error(
          error_flag, kErrorArithmeticOverflow);
    } else {
      accumulator = sum;
    }
  }
  shared_values[lane] = accumulator;
  shared_valid[lane] = valid ? 1 : 0;
  __syncthreads();
  for (unsigned int offset = kBlockSize / 2; offset > 0u; offset >>= 1u) {
    if (lane < offset) {
      const bool pair_valid =
          shared_valid[lane] != 0 && shared_valid[lane + offset] != 0;
      const double sum = shared_values[lane] + shared_values[lane + offset];
      if (!pair_valid || !engine_v2_krylov_isfinite(sum)) {
        shared_values[lane] = 0.0;
        shared_valid[lane] = 0;
        if (pair_valid) {
          engine_v2_record_krylov_error(
              error_flag, kErrorArithmeticOverflow);
        }
      } else {
        shared_values[lane] = sum;
        shared_valid[lane] = 1;
      }
    }
    __syncthreads();
  }
  if (lane == 0u) {
    partial[blockIdx.x] = shared_valid[0] != 0
        ? engine_v2_krylov_exact_zero(shared_values[0])
        : 0.0;
  }
}

extern "C" __global__ void lassq_stage(
    int n,
    const double* x,
    double* partial_pairs,
    int* error_flag) {
  __shared__ double shared_scale[kBlockSize];
  __shared__ double shared_ssq[kBlockSize];
  __shared__ int shared_valid[kBlockSize];

  if (blockDim.x != kBlockSize || n <= 0 ||
      gridDim.x != engine_v2_reduction_grid(n)) {
    if (blockIdx.x == 0u && threadIdx.x == 0u) {
      engine_v2_record_krylov_error(
          error_flag, kErrorInvalidCountOrGeometry);
    }
    return;
  }
  const unsigned int lane = threadIdx.x;
  const unsigned long long segment_begin =
      static_cast<unsigned long long>(blockIdx.x) *
      static_cast<unsigned long long>(kReductionValuesPerBlock);
  const unsigned long long first = segment_begin + lane;
  const unsigned long long second = first + kBlockSize;
  EngineV2LassqPair accumulator = engine_v2_lassq_zero_pair();
  bool valid = true;

  if (first < static_cast<unsigned long long>(n)) {
    const double value = x[first];
    if (!engine_v2_krylov_isfinite(value)) {
      valid = false;
      engine_v2_record_krylov_error(error_flag, kErrorNonfiniteInput);
    } else {
      accumulator = engine_v2_lassq_value_pair(value);
    }
  }
  if (second < static_cast<unsigned long long>(n)) {
    const double value = x[second];
    if (!engine_v2_krylov_isfinite(value)) {
      valid = false;
      engine_v2_record_krylov_error(error_flag, kErrorNonfiniteInput);
    } else {
      EngineV2LassqPair merged;
      if (!engine_v2_lassq_merge(
              accumulator, engine_v2_lassq_value_pair(value), &merged)) {
        valid = false;
        engine_v2_record_krylov_error(
            error_flag, kErrorArithmeticOverflow);
      }
      accumulator = merged;
    }
  }
  shared_scale[lane] = accumulator.scale;
  shared_ssq[lane] = accumulator.ssq;
  shared_valid[lane] = valid ? 1 : 0;
  __syncthreads();

  for (unsigned int offset = kBlockSize / 2; offset > 0u; offset >>= 1u) {
    if (lane < offset) {
      EngineV2LassqPair left;
      left.scale = shared_scale[lane];
      left.ssq = shared_ssq[lane];
      EngineV2LassqPair right;
      right.scale = shared_scale[lane + offset];
      right.ssq = shared_ssq[lane + offset];
      EngineV2LassqPair merged;
      const bool pair_valid =
          shared_valid[lane] != 0 && shared_valid[lane + offset] != 0;
      const bool merge_valid =
          pair_valid && engine_v2_lassq_merge(left, right, &merged);
      if (!merge_valid) {
        merged = engine_v2_lassq_zero_pair();
        if (pair_valid) {
          engine_v2_record_krylov_error(
              error_flag, kErrorArithmeticOverflow);
        }
      }
      shared_scale[lane] = merged.scale;
      shared_ssq[lane] = merged.ssq;
      shared_valid[lane] = merge_valid ? 1 : 0;
    }
    __syncthreads();
  }
  if (lane == 0u) {
    const unsigned long long output =
        static_cast<unsigned long long>(blockIdx.x) * 2u;
    if (shared_valid[0] != 0) {
      partial_pairs[output] =
          engine_v2_krylov_exact_zero(shared_scale[0]);
      partial_pairs[output + 1u] = shared_ssq[0];
    } else {
      partial_pairs[output] = 0.0;
      partial_pairs[output + 1u] = 1.0;
    }
  }
}

extern "C" __global__ void lassq_combine_stage(
    int n,
    const double* input_pairs,
    double* output_pairs,
    int* error_flag) {
  __shared__ double shared_scale[kBlockSize];
  __shared__ double shared_ssq[kBlockSize];
  __shared__ int shared_valid[kBlockSize];

  if (blockDim.x != kBlockSize || n <= 0 ||
      gridDim.x != engine_v2_reduction_grid(n)) {
    if (blockIdx.x == 0u && threadIdx.x == 0u) {
      engine_v2_record_krylov_error(
          error_flag, kErrorInvalidCountOrGeometry);
    }
    return;
  }
  const unsigned int lane = threadIdx.x;
  const unsigned long long segment_begin =
      static_cast<unsigned long long>(blockIdx.x) *
      static_cast<unsigned long long>(kReductionValuesPerBlock);
  const unsigned long long first = segment_begin + lane;
  const unsigned long long second = first + kBlockSize;
  EngineV2LassqPair accumulator = engine_v2_lassq_zero_pair();
  bool valid = true;

  if (first < static_cast<unsigned long long>(n)) {
    accumulator.scale = input_pairs[2u * first];
    accumulator.ssq = input_pairs[2u * first + 1u];
    if (!engine_v2_lassq_pair_valid(accumulator)) {
      accumulator = engine_v2_lassq_zero_pair();
      valid = false;
      engine_v2_record_krylov_error(error_flag, kErrorInvalidLassqPair);
    }
  }
  if (second < static_cast<unsigned long long>(n)) {
    EngineV2LassqPair right;
    right.scale = input_pairs[2u * second];
    right.ssq = input_pairs[2u * second + 1u];
    EngineV2LassqPair merged;
    if (!engine_v2_lassq_pair_valid(right)) {
      valid = false;
      engine_v2_record_krylov_error(error_flag, kErrorInvalidLassqPair);
    } else if (!engine_v2_lassq_merge(accumulator, right, &merged)) {
      valid = false;
      engine_v2_record_krylov_error(
          error_flag, kErrorArithmeticOverflow);
    } else {
      accumulator = merged;
    }
  }
  shared_scale[lane] = accumulator.scale;
  shared_ssq[lane] = accumulator.ssq;
  shared_valid[lane] = valid ? 1 : 0;
  __syncthreads();

  for (unsigned int offset = kBlockSize / 2; offset > 0u; offset >>= 1u) {
    if (lane < offset) {
      EngineV2LassqPair left;
      left.scale = shared_scale[lane];
      left.ssq = shared_ssq[lane];
      EngineV2LassqPair right;
      right.scale = shared_scale[lane + offset];
      right.ssq = shared_ssq[lane + offset];
      EngineV2LassqPair merged;
      const bool pair_valid =
          shared_valid[lane] != 0 && shared_valid[lane + offset] != 0;
      const bool merge_valid =
          pair_valid && engine_v2_lassq_merge(left, right, &merged);
      if (!merge_valid) {
        merged = engine_v2_lassq_zero_pair();
        if (pair_valid) {
          engine_v2_record_krylov_error(
              error_flag, kErrorArithmeticOverflow);
        }
      }
      shared_scale[lane] = merged.scale;
      shared_ssq[lane] = merged.ssq;
      shared_valid[lane] = merge_valid ? 1 : 0;
    }
    __syncthreads();
  }
  if (lane == 0u) {
    const unsigned long long output =
        static_cast<unsigned long long>(blockIdx.x) * 2u;
    if (shared_valid[0] != 0) {
      output_pairs[output] =
          engine_v2_krylov_exact_zero(shared_scale[0]);
      output_pairs[output + 1u] = shared_ssq[0];
    } else {
      output_pairs[output] = 0.0;
      output_pairs[output + 1u] = 1.0;
    }
  }
}

extern "C" __global__ void lassq_finalize(
    const double* pair,
    double* norm,
    int* error_flag) {
  if (blockDim.x != kBlockSize || gridDim.x != 1u) {
    if (blockIdx.x == 0u && threadIdx.x == 0u) {
      engine_v2_record_krylov_error(
          error_flag, kErrorInvalidCountOrGeometry);
    }
    return;
  }
  if (threadIdx.x != 0u) {
    return;
  }
  EngineV2LassqPair value;
  value.scale = pair[0];
  value.ssq = pair[1];
  if (!engine_v2_lassq_pair_valid(value)) {
    norm[0] = 0.0;
    engine_v2_record_krylov_error(error_flag, kErrorInvalidLassqPair);
    return;
  }
  if (value.scale == 0.0) {
    norm[0] = 0.0;
    return;
  }
  const double result = value.scale * sqrt(value.ssq);
  if (!engine_v2_krylov_isfinite(result)) {
    norm[0] = 0.0;
    engine_v2_record_krylov_error(
        error_flag, kErrorArithmeticOverflow);
    return;
  }
  norm[0] = engine_v2_krylov_exact_zero(result);
}
