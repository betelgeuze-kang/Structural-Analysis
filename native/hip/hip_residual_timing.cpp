// Optional timing adapter over the existing fixed-operator HIP residual kernels.
// No protected MGT input, material Newton execution or engineering authority.
#include "../../implementation/phase1/hip_full_residual_ffi.cpp"
#include <chrono>

namespace {
using Clock = std::chrono::steady_clock;
double milliseconds(Clock::time_point a, Clock::time_point b) {
  return std::chrono::duration<double, std::milli>(b - a).count();
}
}

extern "C" {
struct StructuralHipDeviceInfo {
  char name[256];
  char architecture[256];
  unsigned long long global_memory_bytes;
  int multiprocessors;
  int clock_khz;
  int driver_version;
  int runtime_version;
};

int structural_hip_residual_device_info(StructuralHipDeviceInfo* info) {
  if (!info) return -1;
  try {
    std::memset(info, 0, sizeof(*info));
    hipDeviceProp_t properties{};
    check_hip(hipGetDeviceProperties(&properties, 0), "device properties");
    std::snprintf(info->name, sizeof(info->name), "%s", properties.name);
    std::snprintf(info->architecture, sizeof(info->architecture), "%s", properties.gcnArchName);
    info->global_memory_bytes = properties.totalGlobalMem;
    info->multiprocessors = properties.multiProcessorCount;
    info->clock_khz = properties.clockRate;
    check_hip(hipDriverGetVersion(&info->driver_version), "driver version");
    check_hip(hipRuntimeGetVersion(&info->runtime_version), "runtime version");
    return 0;
  } catch (const std::exception& error) {
    set_last_error(error.what());
    return -2;
  }
}

// phase_ms: allocation/reuse, H2D, device kernel, host dispatch+kernel+wait,
// D2H, total resident evaluation. The device interval includes zeroing outputs.
int structural_hip_residual_timed_eval(
    void* raw_handle, const double* states, long long batch_size,
    double* residual_out, double* phase_ms) {
  auto* handle = reinterpret_cast<MgtHipFullResidualHandle*>(raw_handle);
  hipEvent_t start = nullptr, stop = nullptr;
  try {
    if (!handle || !states || !residual_out || !phase_ms || batch_size <= 0)
      throw std::runtime_error("invalid timed evaluation arguments");
    check_hip(hipEventCreate(&start), "event create start");
    check_hip(hipEventCreate(&stop), "event create stop");
    auto total_start = Clock::now();
    size_t state_count = static_cast<size_t>(batch_size) * handle->n_dof;
    size_t output_count = static_cast<size_t>(batch_size) * handle->free_count;
    ensure_eval_buffers(handle->d, state_count, output_count);
    auto allocation_end = Clock::now();
    check_hip(hipMemcpy(handle->d.d_states, states, state_count * sizeof(double), hipMemcpyHostToDevice), "copy states");
    auto transfer_end = Clock::now();
    check_hip(hipEventRecord(start), "event start");
    check_hip(hipMemset(handle->d.d_frame_out, 0, state_count * sizeof(double)), "zero frame output");
    constexpr int block = 256;
    long long frame_total = batch_size * handle->frame_element_count * 12LL;
    long long residual_total = batch_size * handle->free_count;
    hipLaunchKernelGGL(frame_force_batch_kernel,
      dim3((frame_total + block - 1) / block), dim3(block), 0, 0,
      handle->d.d_frame_dofs, handle->d.d_frame_stiffness, handle->d.d_states,
      handle->d.d_frame_out, handle->frame_element_count, handle->n_dof, batch_size);
    check_hip(hipGetLastError(), "frame kernel");
    hipLaunchKernelGGL(full_residual_batch_kernel,
      dim3((residual_total + block - 1) / block), dim3(block), 0, 0,
      handle->d.d_frame_out, handle->d.d_shell_row_ptr, handle->d.d_shell_col_idx,
      handle->d.d_shell_values, handle->d.d_spring_row_ptr,
      handle->d.d_spring_col_idx, handle->d.d_spring_values,
      handle->d.d_states, handle->d.d_f_ext, handle->d.d_free,
      handle->d.d_residual_out, handle->n_dof, handle->free_count, batch_size);
    check_hip(hipGetLastError(), "residual kernel");
    check_hip(hipEventRecord(stop), "event stop");
    check_hip(hipEventSynchronize(stop), "kernel wait");
    float device_ms = 0;
    check_hip(hipEventElapsedTime(&device_ms, start, stop), "kernel elapsed");
    auto kernel_end = Clock::now();
    check_hip(hipMemcpy(residual_out, handle->d.d_residual_out,
      output_count * sizeof(double), hipMemcpyDeviceToHost), "copy residual");
    auto total_end = Clock::now();
    phase_ms[0] = milliseconds(total_start, allocation_end);
    phase_ms[1] = milliseconds(allocation_end, transfer_end);
    phase_ms[2] = device_ms;
    phase_ms[3] = milliseconds(transfer_end, kernel_end);
    phase_ms[4] = milliseconds(kernel_end, total_end);
    phase_ms[5] = milliseconds(total_start, total_end);
    hipEventDestroy(start); hipEventDestroy(stop);
    return 0;
  } catch (const std::exception& error) {
    if (start) hipEventDestroy(start);
    if (stop) hipEventDestroy(stop);
    set_last_error(error.what());
    return -2;
  }
}
}
