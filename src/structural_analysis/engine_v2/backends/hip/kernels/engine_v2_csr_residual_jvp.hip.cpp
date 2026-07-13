// Engine v2 canonical-CSR residual/JVP kernel ABI v1.
//
// The host wrapper accepts caller-owned device views and a caller-owned HIP
// stream.  Resource lifetime and command ordering intentionally remain outside
// this artifact.

#include <hip/hip_runtime.h>

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <limits>

#ifndef ENGINE_V2_HIP_CSR_TARGETS
#error "ENGINE_V2_HIP_CSR_TARGETS must be an explicit string literal"
#endif

namespace {

constexpr std::uint32_t kAbiVersion = 1U;
constexpr std::uint32_t kBlockSize = 256U;
constexpr std::uint32_t kDtypeI32Le = 1U;
constexpr std::uint32_t kDtypeF64Le = 2U;
constexpr std::size_t kLastErrorBytes = 256U;

constexpr std::int32_t kStatusNullRequest = -1001;
constexpr std::int32_t kStatusAbiMismatch = -1002;
constexpr std::int32_t kStatusStructSizeMismatch = -1003;
constexpr std::int32_t kStatusCountInvalid = -1004;
constexpr std::int32_t kStatusBufferViewInvalid = -1005;
constexpr std::int32_t kStatusStreamInvalid = -1006;
constexpr std::int32_t kStatusHipLaunchBase = -2000;

struct EngineV2BufferViewV1 {
  std::uint32_t abi_version;
  std::uint32_t struct_size;
  void* pointer;
  std::uint64_t byte_length;
  std::uint32_t dtype;
  std::uint32_t rank;
  std::int64_t shape[2];
  std::int64_t strides[2];
};

struct EngineV2CanonicalCsrV1 {
  std::uint32_t abi_version;
  std::uint32_t struct_size;
  std::int32_t dof_count;
  std::int32_t nnz_count;
  EngineV2BufferViewV1 row_ptr;
  EngineV2BufferViewV1 column_indices;
  EngineV2BufferViewV1 values;
};

struct EngineV2ResidualJvpRequestV1 {
  std::uint32_t abi_version;
  std::uint32_t struct_size;
  EngineV2CanonicalCsrV1 csr;
  EngineV2BufferViewV1 load;
  EngineV2BufferViewV1 state;
  EngineV2BufferViewV1 direction;
  EngineV2BufferViewV1 residual_out;
  EngineV2BufferViewV1 jvp_out;
  hipStream_t stream;
};

thread_local char g_last_error[kLastErrorBytes] = {0};

void set_last_error(const char* message) noexcept {
  if (message == nullptr) {
    g_last_error[0] = '\0';
    return;
  }
  std::snprintf(g_last_error, kLastErrorBytes, "%s", message);
  g_last_error[kLastErrorBytes - 1U] = '\0';
}

std::int32_t fail(std::int32_t status, const char* message) noexcept {
  set_last_error(message);
  return status;
}

bool checked_bytes(std::int64_t count, std::uint64_t item_size,
                   std::uint64_t* result) noexcept {
  if (count < 0 || result == nullptr) {
    return false;
  }
  const auto unsigned_count = static_cast<std::uint64_t>(count);
  if (unsigned_count >
      std::numeric_limits<std::uint64_t>::max() / item_size) {
    return false;
  }
  *result = unsigned_count * item_size;
  return true;
}

bool valid_vector_view(const EngineV2BufferViewV1& view,
                       std::uint32_t dtype, std::int64_t element_count,
                       std::uint64_t item_size) noexcept {
  std::uint64_t expected_bytes = 0U;
  if (!checked_bytes(element_count, item_size, &expected_bytes)) {
    return false;
  }
  return view.abi_version == kAbiVersion &&
         view.struct_size == sizeof(EngineV2BufferViewV1) &&
         view.pointer != nullptr && view.byte_length == expected_bytes &&
         view.dtype == dtype && view.rank == 1U &&
         view.shape[0] == element_count && view.shape[1] == 0 &&
         view.strides[0] == static_cast<std::int64_t>(item_size) &&
         view.strides[1] == 0;
}

__global__ void canonical_csr_residual_jvp_kernel(
    std::int32_t row_count, const std::int32_t* row_ptr,
    const std::int32_t* column_indices, const double* values,
    const double* state, const double* direction, const double* load,
    double* residual_out, double* jvp_out) {
  const auto row = static_cast<std::int32_t>(
      blockIdx.x * blockDim.x + threadIdx.x);
  if (row >= row_count) {
    return;
  }

  double state_product = 0.0;
  double direction_product = 0.0;
  const std::int32_t begin = row_ptr[row];
  const std::int32_t end = row_ptr[row + 1];
  for (std::int32_t item = begin; item < end; ++item) {
    const std::int32_t column = column_indices[item];
    const double coefficient = values[item];
    state_product += coefficient * state[column];
    direction_product += coefficient * direction[column];
  }
  residual_out[row] = state_product - load[row];
  jvp_out[row] = direction_product;
}

}  // namespace

extern "C" std::uint32_t engine_v2_hip_csr_abi_version() noexcept {
  return kAbiVersion;
}

extern "C" std::uint32_t engine_v2_hip_csr_block_size() noexcept {
  return kBlockSize;
}

extern "C" const char* engine_v2_hip_csr_targets() noexcept {
  return ENGINE_V2_HIP_CSR_TARGETS;
}

extern "C" std::uint32_t engine_v2_hip_csr_buffer_view_size() noexcept {
  return static_cast<std::uint32_t>(sizeof(EngineV2BufferViewV1));
}

extern "C" std::uint32_t engine_v2_hip_csr_canonical_csr_size() noexcept {
  return static_cast<std::uint32_t>(sizeof(EngineV2CanonicalCsrV1));
}

extern "C" std::uint32_t
engine_v2_hip_csr_residual_jvp_request_size() noexcept {
  return static_cast<std::uint32_t>(sizeof(EngineV2ResidualJvpRequestV1));
}

extern "C" std::int32_t engine_v2_hip_csr_last_error(
    char* output, std::uint32_t capacity) noexcept {
  if (output == nullptr || capacity == 0U) {
    return 0;
  }
  const std::size_t bounded_capacity =
      capacity < kLastErrorBytes ? capacity : kLastErrorBytes;
  std::size_t message_length = 0U;
  while (message_length < kLastErrorBytes - 1U &&
         g_last_error[message_length] != '\0') {
    ++message_length;
  }
  const std::size_t copy_length =
      message_length < bounded_capacity - 1U ? message_length
                                            : bounded_capacity - 1U;
  std::memcpy(output, g_last_error, copy_length);
  output[copy_length] = '\0';
  return static_cast<std::int32_t>(copy_length);
}

extern "C" std::int32_t engine_v2_hip_csr_launch(
    const EngineV2ResidualJvpRequestV1* request) noexcept {
  set_last_error(nullptr);
  if (request == nullptr) {
    return fail(kStatusNullRequest, "request pointer is null");
  }
  if (request->abi_version != kAbiVersion ||
      request->csr.abi_version != kAbiVersion) {
    return fail(kStatusAbiMismatch, "descriptor ABI version mismatch");
  }
  if (request->struct_size != sizeof(EngineV2ResidualJvpRequestV1) ||
      request->csr.struct_size != sizeof(EngineV2CanonicalCsrV1)) {
    return fail(kStatusStructSizeMismatch, "descriptor struct size mismatch");
  }
  const std::int32_t dof_count = request->csr.dof_count;
  const std::int32_t nnz_count = request->csr.nnz_count;
  if (dof_count <= 0 || nnz_count <= 0 ||
      dof_count == std::numeric_limits<std::int32_t>::max()) {
    return fail(kStatusCountInvalid, "CSR dof or nnz count is invalid");
  }
  if (!valid_vector_view(request->csr.row_ptr, kDtypeI32Le,
                         static_cast<std::int64_t>(dof_count) + 1, 4U) ||
      !valid_vector_view(request->csr.column_indices, kDtypeI32Le, nnz_count,
                         4U) ||
      !valid_vector_view(request->csr.values, kDtypeF64Le, nnz_count, 8U) ||
      !valid_vector_view(request->load, kDtypeF64Le, dof_count, 8U) ||
      !valid_vector_view(request->state, kDtypeF64Le, dof_count, 8U) ||
      !valid_vector_view(request->direction, kDtypeF64Le, dof_count, 8U) ||
      !valid_vector_view(request->residual_out, kDtypeF64Le, dof_count, 8U) ||
      !valid_vector_view(request->jvp_out, kDtypeF64Le, dof_count, 8U)) {
    return fail(kStatusBufferViewInvalid, "buffer view contract is invalid");
  }
  if (request->stream == nullptr) {
    return fail(kStatusStreamInvalid, "caller-owned stream is null");
  }

  const auto grid_size = static_cast<std::uint32_t>(
      (static_cast<std::uint64_t>(dof_count) + kBlockSize - 1U) /
      kBlockSize);
  hipLaunchKernelGGL(
      canonical_csr_residual_jvp_kernel, dim3(grid_size), dim3(kBlockSize), 0,
      request->stream, dof_count,
      static_cast<const std::int32_t*>(request->csr.row_ptr.pointer),
      static_cast<const std::int32_t*>(request->csr.column_indices.pointer),
      static_cast<const double*>(request->csr.values.pointer),
      static_cast<const double*>(request->state.pointer),
      static_cast<const double*>(request->direction.pointer),
      static_cast<const double*>(request->load.pointer),
      static_cast<double*>(request->residual_out.pointer),
      static_cast<double*>(request->jvp_out.pointer));

  const hipError_t launch_status = hipGetLastError();
  if (launch_status != hipSuccess) {
    set_last_error(hipGetErrorString(launch_status));
    return kStatusHipLaunchBase - static_cast<std::int32_t>(launch_status);
  }
  return 0;
}
