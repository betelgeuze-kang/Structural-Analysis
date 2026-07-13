#pragma clang fp contract(off)

extern "C" __global__ void engine_v2_csr_residual_jvp_v1(
    const int row_count,
    const int* __restrict__ row_ptr,
    const int* __restrict__ column_indices,
    const double* __restrict__ values,
    const double* __restrict__ state,
    const double* __restrict__ load,
    const double* __restrict__ direction,
    double* __restrict__ residual_out,
    double* __restrict__ jvp_out) {
  const int row = static_cast<int>(blockIdx.x * blockDim.x + threadIdx.x);
  if (row >= row_count) {
    return;
  }

  double state_product = 0.0;
  double direction_product = 0.0;
  const int row_begin = row_ptr[row];
  const int row_end = row_ptr[row + 1];
  for (int entry = row_begin; entry < row_end; ++entry) {
    const int column = column_indices[entry];
    const double coefficient = values[entry];
    state_product += coefficient * state[column];
    direction_product += coefficient * direction[column];
  }

  residual_out[row] = state_product - load[row];
  jvp_out[row] = direction_product;
}
