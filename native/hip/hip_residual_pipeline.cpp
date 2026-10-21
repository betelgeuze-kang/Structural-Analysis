// Fixed-linear-operator sequence probe. No nonlinear material/RC solver routing.
// Reuse v1 operator allocation and kernel definitions; new work is device state
// evolution between residual evaluations, followed by one final state/result read.
#include "hip_residual_timing.cpp"
#include <limits>

__global__ void structural_fixed_operator_update(
    double* states, const double* residual, const long long* free_dofs,
    long long n_dof, long long free_count, long long batch, double omega) {
  const long long index = static_cast<long long>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= batch * free_count) return;
  const long long row = index % free_count;
  const long long item = index / free_count;
  states[item * n_dof + free_dofs[row]] -= omega * residual[index];
}

extern "C" int structural_hip_fixed_residual_sequence_v1(
    void* raw_handle, const double* initial_states, long long batch,
    int steps, double omega, double* final_states, double* final_residual,
    double* phase_ms) {
  auto* handle = reinterpret_cast<MgtHipFullResidualHandle*>(raw_handle);
  hipEvent_t start = nullptr, stop = nullptr;
  try {
    if (!handle || !initial_states || !final_states || !final_residual ||
        !phase_ms || batch < 1 || batch > 64 || steps < 1 || steps > 128 ||
        !std::isfinite(omega) || omega <= 0.0 || omega > 1.0 ||
        handle->n_dof < 12 || handle->n_dof > 196608 ||
        handle->free_count > handle->n_dof ||
        handle->frame_element_count > handle->n_dof)
      throw std::runtime_error("invalid bounded fixed-operator sequence arguments");
    const size_t state_count = static_cast<size_t>(batch) * handle->n_dof;
    const size_t output_count = static_cast<size_t>(batch) * handle->free_count;
    const auto overlaps = [](const void* a, size_t na, const void* b, size_t nb) {
      const auto x = reinterpret_cast<std::uintptr_t>(a);
      const auto y = reinterpret_cast<std::uintptr_t>(b);
      const auto maximum = std::numeric_limits<std::uintptr_t>::max();
      return x > maximum - na || y > maximum - nb ||
          (x < y + nb && y < x + na);
    };
    const double* buffers[] = {initial_states, final_states, final_residual, phase_ms};
    for (const double* p : buffers)
      if (reinterpret_cast<std::uintptr_t>(p) % alignof(double))
        throw std::runtime_error("unaligned fixed-operator sequence buffer");
    if (overlaps(initial_states, state_count * 8, final_states, state_count * 8) ||
        overlaps(initial_states, state_count * 8, final_residual, output_count * 8) ||
        overlaps(final_states, state_count * 8, final_residual, output_count * 8) ||
        overlaps(phase_ms, 6 * 8, initial_states, state_count * 8) ||
        overlaps(phase_ms, 6 * 8, final_states, state_count * 8) ||
        overlaps(phase_ms, 6 * 8, final_residual, output_count * 8))
      throw std::runtime_error("overlapping fixed-operator sequence buffers");
    check_hip(hipEventCreate(&start), "sequence event start create");
    check_hip(hipEventCreate(&stop), "sequence event stop create");
    const auto total_start = Clock::now();
    ensure_eval_buffers(handle->d, state_count, output_count);
    const auto allocation_end = Clock::now();
    check_hip(hipMemcpy(handle->d.d_states, initial_states,
        state_count * sizeof(double), hipMemcpyHostToDevice), "sequence initial H2D");
    const auto h2d_end = Clock::now();
    constexpr int block = 256;
    const dim3 frame_grid((batch * handle->frame_element_count * 12LL + block - 1) / block);
    const dim3 residual_grid((batch * handle->free_count + block - 1) / block);
    check_hip(hipEventRecord(start), "sequence event start");
    for (int step = 0; step <= steps; ++step) {
      check_hip(hipMemset(handle->d.d_frame_out, 0,
          state_count * sizeof(double)), "sequence zero frame");
      hipLaunchKernelGGL(frame_force_batch_kernel, frame_grid, dim3(block), 0, 0,
          handle->d.d_frame_dofs, handle->d.d_frame_stiffness, handle->d.d_states,
          handle->d.d_frame_out, handle->frame_element_count, handle->n_dof, batch);
      check_hip(hipGetLastError(), "sequence frame kernel");
      hipLaunchKernelGGL(full_residual_batch_kernel, residual_grid, dim3(block), 0, 0,
          handle->d.d_frame_out, handle->d.d_shell_row_ptr, handle->d.d_shell_col_idx,
          handle->d.d_shell_values, handle->d.d_spring_row_ptr,
          handle->d.d_spring_col_idx, handle->d.d_spring_values,
          handle->d.d_states, handle->d.d_f_ext, handle->d.d_free,
          handle->d.d_residual_out, handle->n_dof, handle->free_count, batch);
      check_hip(hipGetLastError(), "sequence residual kernel");
      if (step < steps) {
        hipLaunchKernelGGL(structural_fixed_operator_update, residual_grid, dim3(block), 0, 0,
            handle->d.d_states, handle->d.d_residual_out, handle->d.d_free,
            handle->n_dof, handle->free_count, batch, omega);
        check_hip(hipGetLastError(), "sequence update kernel");
      }
    }
    check_hip(hipEventRecord(stop), "sequence event stop");
    check_hip(hipEventSynchronize(stop), "sequence final wait");
    float device_ms = 0;
    check_hip(hipEventElapsedTime(&device_ms, start, stop), "sequence device time");
    const auto kernel_end = Clock::now();
    check_hip(hipMemcpy(final_states, handle->d.d_states,
        state_count * sizeof(double), hipMemcpyDeviceToHost), "sequence final state D2H");
    check_hip(hipMemcpy(final_residual, handle->d.d_residual_out,
        output_count * sizeof(double), hipMemcpyDeviceToHost), "sequence final residual D2H");
    const auto total_end = Clock::now();
    phase_ms[0] = milliseconds(total_start, allocation_end);
    phase_ms[1] = milliseconds(allocation_end, h2d_end);
    phase_ms[2] = device_ms;
    phase_ms[3] = milliseconds(h2d_end, kernel_end);
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
