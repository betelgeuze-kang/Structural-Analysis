#include <hip/hip_runtime.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <exception>
#include <stdexcept>
#include <string>

__global__ void frame_force_batch_kernel(
    const long long* dofs,
    const double* stiffness,
    const double* states,
    double* frame_out,
    long long element_count,
    long long n_dof,
    long long batch_size) {
  long long idx = static_cast<long long>(blockIdx.x) * blockDim.x + threadIdx.x;
  long long total = batch_size * element_count * 12LL;
  if (idx >= total) {
    return;
  }
  long long local_i = idx % 12LL;
  long long elem = (idx / 12LL) % element_count;
  long long batch = idx / (12LL * element_count);
  long long dof_out = dofs[elem * 12LL + local_i];
  double sum = 0.0;
  const double* k = stiffness + elem * 144LL + local_i * 12LL;
  const long long* elem_dofs = dofs + elem * 12LL;
  const double* u = states + batch * n_dof;
  for (long long j = 0; j < 12LL; ++j) {
    sum += k[j] * u[elem_dofs[j]];
  }
  atomicAdd(frame_out + batch * n_dof + dof_out, sum);
}

__global__ void full_residual_batch_kernel(
    const double* frame_out,
    const long long* shell_row_ptr,
    const long long* shell_col_idx,
    const double* shell_values,
    const long long* spring_row_ptr,
    const long long* spring_col_idx,
    const double* spring_values,
    const double* states,
    const double* f_ext,
    const long long* free_dofs,
    double* residual_out,
    long long n_dof,
    long long free_count,
    long long batch_size) {
  long long idx = static_cast<long long>(blockIdx.x) * blockDim.x + threadIdx.x;
  long long total = batch_size * free_count;
  if (idx >= total) {
    return;
  }
  long long free_i = idx % free_count;
  long long batch = idx / free_count;
  long long row = free_dofs[free_i];
  const double* u = states + batch * n_dof;

  double shell_sum = 0.0;
  for (long long k = shell_row_ptr[row]; k < shell_row_ptr[row + 1LL]; ++k) {
    shell_sum += shell_values[k] * u[shell_col_idx[k]];
  }
  double spring_sum = 0.0;
  for (long long k = spring_row_ptr[row]; k < spring_row_ptr[row + 1LL]; ++k) {
    spring_sum += spring_values[k] * u[spring_col_idx[k]];
  }
  residual_out[idx] = frame_out[batch * n_dof + row] + shell_sum + spring_sum - f_ext[row];
}

extern "C" {
struct MgtHipFullResidualFfiStatus {
  int code;
  long long frame_element_count;
  long long n_dof;
  long long free_count;
  long long shell_nnz;
  long long spring_nnz;
  long long batch_size;
  int reps;
  int device_id;
  int eval_buffers_reused;
  int operator_buffers_device_resident;
  double kernel_elapsed_ms_total;
  double kernel_elapsed_ms_mean;
  double output_abs_sum;
  double output_max_abs;
};
}

struct DeviceBuffers {
  long long* d_frame_dofs = nullptr;
  double* d_frame_stiffness = nullptr;
  long long* d_shell_row_ptr = nullptr;
  long long* d_shell_col_idx = nullptr;
  double* d_shell_values = nullptr;
  long long* d_spring_row_ptr = nullptr;
  long long* d_spring_col_idx = nullptr;
  double* d_spring_values = nullptr;
  double* d_f_ext = nullptr;
  long long* d_free = nullptr;
  double* d_states = nullptr;
  double* d_frame_out = nullptr;
  double* d_residual_out = nullptr;
  size_t state_capacity = 0;
  size_t output_capacity = 0;
};

struct MgtHipFullResidualHandle {
  DeviceBuffers d;
  long long frame_element_count = 0;
  long long n_dof = 0;
  long long shell_nnz = 0;
  long long spring_nnz = 0;
  long long free_count = 0;
  int device_id = 0;
  std::string device_name;
};

thread_local std::string g_last_error;

void set_last_error(const std::string& value) {
  g_last_error = value;
}

void check_hip(hipError_t status, const char* where) {
  if (status != hipSuccess) {
    throw std::runtime_error(std::string(where) + ": " + hipGetErrorString(status));
  }
}

void clear_status(MgtHipFullResidualFfiStatus* status) {
  if (status != nullptr) {
    std::memset(status, 0, sizeof(MgtHipFullResidualFfiStatus));
  }
}

void fill_common_status(
    const MgtHipFullResidualHandle* handle,
    MgtHipFullResidualFfiStatus* status,
    int code) {
  if (status == nullptr) {
    return;
  }
  status->code = code;
  if (handle != nullptr) {
    status->frame_element_count = handle->frame_element_count;
    status->n_dof = handle->n_dof;
    status->free_count = handle->free_count;
    status->shell_nnz = handle->shell_nnz;
    status->spring_nnz = handle->spring_nnz;
    status->device_id = handle->device_id;
    status->operator_buffers_device_resident = 1;
  }
}

void free_eval_buffers(DeviceBuffers& d) {
  (void)hipFree(d.d_states);
  (void)hipFree(d.d_frame_out);
  (void)hipFree(d.d_residual_out);
  d.d_states = nullptr;
  d.d_frame_out = nullptr;
  d.d_residual_out = nullptr;
  d.state_capacity = 0;
  d.output_capacity = 0;
}

void free_all(DeviceBuffers& d) {
  free_eval_buffers(d);
  (void)hipFree(d.d_frame_dofs);
  (void)hipFree(d.d_frame_stiffness);
  (void)hipFree(d.d_shell_row_ptr);
  (void)hipFree(d.d_shell_col_idx);
  (void)hipFree(d.d_shell_values);
  (void)hipFree(d.d_spring_row_ptr);
  (void)hipFree(d.d_spring_col_idx);
  (void)hipFree(d.d_spring_values);
  (void)hipFree(d.d_f_ext);
  (void)hipFree(d.d_free);
  d = DeviceBuffers{};
}

template <typename T>
void alloc_copy(T** dst, const T* src, size_t count, const char* name) {
  *dst = nullptr;
  if (count == 0) {
    return;
  }
  if (src == nullptr) {
    throw std::runtime_error(std::string(name) + " pointer is null");
  }
  check_hip(hipMalloc(dst, count * sizeof(T)), name);
  check_hip(hipMemcpy(*dst, src, count * sizeof(T), hipMemcpyHostToDevice), name);
}

bool ensure_eval_buffers(DeviceBuffers& d, size_t state_count, size_t output_count) {
  if (state_count <= d.state_capacity && output_count <= d.output_capacity) {
    return true;
  }
  free_eval_buffers(d);
  check_hip(hipMalloc(&d.d_states, state_count * sizeof(double)), "hipMalloc states");
  check_hip(hipMalloc(&d.d_frame_out, state_count * sizeof(double)), "hipMalloc frame_out");
  check_hip(hipMalloc(&d.d_residual_out, output_count * sizeof(double)), "hipMalloc residual_out");
  d.state_capacity = state_count;
  d.output_capacity = output_count;
  return false;
}

extern "C" const char* mgt_hip_full_residual_last_error() {
  return g_last_error.c_str();
}

extern "C" int mgt_hip_full_residual_device_name(
    void* raw_handle,
    char* buffer,
    size_t buffer_len) {
  if (raw_handle == nullptr || buffer == nullptr || buffer_len == 0) {
    return -1;
  }
  auto* handle = reinterpret_cast<MgtHipFullResidualHandle*>(raw_handle);
  std::snprintf(buffer, buffer_len, "%s", handle->device_name.c_str());
  return 0;
}

extern "C" int mgt_hip_full_residual_create(
    void** out_handle,
    const long long* frame_dofs,
    const double* frame_stiffness,
    const long long* shell_row_ptr,
    const long long* shell_col_idx,
    const double* shell_values,
    const long long* spring_row_ptr,
    const long long* spring_col_idx,
    const double* spring_values,
    const double* f_ext,
    const long long* free_dofs,
    long long frame_element_count,
    long long n_dof,
    long long shell_nnz,
    long long spring_nnz,
    long long free_count,
    MgtHipFullResidualFfiStatus* status) {
  clear_status(status);
  if (out_handle == nullptr) {
    set_last_error("out_handle pointer is null");
    return -1;
  }
  *out_handle = nullptr;
  auto* handle = new MgtHipFullResidualHandle();
  try {
    if (frame_element_count <= 0 || n_dof <= 0 || shell_nnz < 0 || spring_nnz < 0 ||
        free_count <= 0) {
      throw std::runtime_error("invalid operator dimensions");
    }
    int device_count = 0;
    hipError_t device_status = hipGetDeviceCount(&device_count);
    if (device_status != hipSuccess || device_count <= 0) {
      throw std::runtime_error(std::string("hipGetDeviceCount failed: ") + hipGetErrorString(device_status));
    }
    check_hip(hipSetDevice(0), "hipSetDevice(0)");
    hipDeviceProp_t device_props{};
    check_hip(hipGetDeviceProperties(&device_props, 0), "hipGetDeviceProperties(0)");
    handle->device_id = 0;
    handle->device_name = std::string(device_props.name);
    handle->frame_element_count = frame_element_count;
    handle->n_dof = n_dof;
    handle->shell_nnz = shell_nnz;
    handle->spring_nnz = spring_nnz;
    handle->free_count = free_count;

    alloc_copy(&handle->d.d_frame_dofs, frame_dofs, static_cast<size_t>(frame_element_count) * 12ULL, "frame_dofs");
    alloc_copy(&handle->d.d_frame_stiffness, frame_stiffness, static_cast<size_t>(frame_element_count) * 144ULL, "frame_stiffness");
    alloc_copy(&handle->d.d_shell_row_ptr, shell_row_ptr, static_cast<size_t>(n_dof + 1LL), "shell_row_ptr");
    alloc_copy(&handle->d.d_shell_col_idx, shell_col_idx, static_cast<size_t>(shell_nnz), "shell_col_idx");
    alloc_copy(&handle->d.d_shell_values, shell_values, static_cast<size_t>(shell_nnz), "shell_values");
    alloc_copy(&handle->d.d_spring_row_ptr, spring_row_ptr, static_cast<size_t>(n_dof + 1LL), "spring_row_ptr");
    alloc_copy(&handle->d.d_spring_col_idx, spring_col_idx, static_cast<size_t>(spring_nnz), "spring_col_idx");
    alloc_copy(&handle->d.d_spring_values, spring_values, static_cast<size_t>(spring_nnz), "spring_values");
    alloc_copy(&handle->d.d_f_ext, f_ext, static_cast<size_t>(n_dof), "f_ext");
    alloc_copy(&handle->d.d_free, free_dofs, static_cast<size_t>(free_count), "free_dofs");
    *out_handle = handle;
    fill_common_status(handle, status, 0);
    set_last_error("");
    return 0;
  } catch (const std::exception& exc) {
    set_last_error(exc.what());
    fill_common_status(handle, status, -2);
    free_all(handle->d);
    delete handle;
    return -2;
  }
}

extern "C" int mgt_hip_full_residual_eval(
    void* raw_handle,
    const double* states,
    long long batch_size,
    int reps,
    double* residual_out,
    MgtHipFullResidualFfiStatus* status) {
  clear_status(status);
  auto* handle = reinterpret_cast<MgtHipFullResidualHandle*>(raw_handle);
  try {
    if (handle == nullptr) {
      throw std::runtime_error("handle pointer is null");
    }
    if (states == nullptr || residual_out == nullptr) {
      throw std::runtime_error("state or output pointer is null");
    }
    if (batch_size <= 0) {
      throw std::runtime_error("batch_size must be positive");
    }
    reps = std::max(1, reps);
    size_t state_count = static_cast<size_t>(batch_size) * static_cast<size_t>(handle->n_dof);
    size_t output_count = static_cast<size_t>(batch_size) * static_cast<size_t>(handle->free_count);
    bool eval_buffers_reused = ensure_eval_buffers(handle->d, state_count, output_count);
    check_hip(hipMemcpy(handle->d.d_states, states, state_count * sizeof(double), hipMemcpyHostToDevice), "copy states");

    hipEvent_t start = nullptr;
    hipEvent_t stop = nullptr;
    check_hip(hipEventCreate(&start), "event create start");
    check_hip(hipEventCreate(&stop), "event create stop");
    int block = 256;
    long long frame_total = batch_size * handle->frame_element_count * 12LL;
    long long residual_total = batch_size * handle->free_count;
    int frame_grid = static_cast<int>((frame_total + block - 1LL) / block);
    int residual_grid = static_cast<int>((residual_total + block - 1LL) / block);
    check_hip(hipDeviceSynchronize(), "device synchronize before");
    check_hip(hipEventRecord(start), "event record start");
    for (int rep = 0; rep < reps; ++rep) {
      check_hip(hipMemset(handle->d.d_frame_out, 0, state_count * sizeof(double)), "memset frame_out");
      hipLaunchKernelGGL(
          frame_force_batch_kernel,
          dim3(frame_grid),
          dim3(block),
          0,
          0,
          handle->d.d_frame_dofs,
          handle->d.d_frame_stiffness,
          handle->d.d_states,
          handle->d.d_frame_out,
          handle->frame_element_count,
          handle->n_dof,
          batch_size);
      check_hip(hipGetLastError(), "launch frame_force_batch_kernel");
      hipLaunchKernelGGL(
          full_residual_batch_kernel,
          dim3(residual_grid),
          dim3(block),
          0,
          0,
          handle->d.d_frame_out,
          handle->d.d_shell_row_ptr,
          handle->d.d_shell_col_idx,
          handle->d.d_shell_values,
          handle->d.d_spring_row_ptr,
          handle->d.d_spring_col_idx,
          handle->d.d_spring_values,
          handle->d.d_states,
          handle->d.d_f_ext,
          handle->d.d_free,
          handle->d.d_residual_out,
          handle->n_dof,
          handle->free_count,
          batch_size);
      check_hip(hipGetLastError(), "launch full_residual_batch_kernel");
    }
    check_hip(hipEventRecord(stop), "event record stop");
    check_hip(hipEventSynchronize(stop), "event synchronize stop");
    float elapsed_ms = 0.0f;
    check_hip(hipEventElapsedTime(&elapsed_ms, start, stop), "event elapsed");
    check_hip(hipMemcpy(residual_out, handle->d.d_residual_out, output_count * sizeof(double), hipMemcpyDeviceToHost), "copy residual_out");
    (void)hipEventDestroy(start);
    (void)hipEventDestroy(stop);

    long double output_abs_sum = 0.0L;
    long double output_max_abs = 0.0L;
    for (size_t i = 0; i < output_count; ++i) {
      long double abs_value = std::abs(static_cast<long double>(residual_out[i]));
      output_abs_sum += abs_value;
      output_max_abs = std::max(output_max_abs, abs_value);
    }
    fill_common_status(handle, status, 0);
    if (status != nullptr) {
      status->batch_size = batch_size;
      status->reps = reps;
      status->eval_buffers_reused = eval_buffers_reused ? 1 : 0;
      status->kernel_elapsed_ms_total = static_cast<double>(elapsed_ms);
      status->kernel_elapsed_ms_mean = static_cast<double>(elapsed_ms) / static_cast<double>(reps);
      status->output_abs_sum = static_cast<double>(output_abs_sum);
      status->output_max_abs = static_cast<double>(output_max_abs);
    }
    set_last_error("");
    return 0;
  } catch (const std::exception& exc) {
    set_last_error(exc.what());
    fill_common_status(handle, status, -3);
    return -3;
  }
}

extern "C" int mgt_hip_full_residual_destroy(void* raw_handle) {
  auto* handle = reinterpret_cast<MgtHipFullResidualHandle*>(raw_handle);
  if (handle == nullptr) {
    return 0;
  }
  free_all(handle->d);
  delete handle;
  return 0;
}
