#include <hip/hip_runtime.h>

#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <vector>

__global__ void axpy_kernel(float* y, const float* x, float a, int n) {
  int i = blockIdx.x * blockDim.x + threadIdx.x;
  if (i < n) {
    y[i] = a * x[i] + y[i];
  }
}

int main(int argc, char** argv) {
  int n = 1 << 20;
  int reps = 20;
  if (argc >= 2) {
    n = std::max(1, std::atoi(argv[1]));
  }
  if (argc >= 3) {
    reps = std::max(1, std::atoi(argv[2]));
  }

  std::vector<float> hx(static_cast<size_t>(n), 1.25f);
  std::vector<float> hy(static_cast<size_t>(n), 0.75f);
  float* dx = nullptr;
  float* dy = nullptr;
  size_t bytes = static_cast<size_t>(n) * sizeof(float);

  if (hipMalloc(&dx, bytes) != hipSuccess || hipMalloc(&dy, bytes) != hipSuccess) {
    std::cerr << "{\"ok\":false,\"error\":\"hipMalloc_failed\"}\n";
    return 2;
  }
  if (hipMemcpy(dx, hx.data(), bytes, hipMemcpyHostToDevice) != hipSuccess ||
      hipMemcpy(dy, hy.data(), bytes, hipMemcpyHostToDevice) != hipSuccess) {
    std::cerr << "{\"ok\":false,\"error\":\"hipMemcpy_h2d_failed\"}\n";
    hipFree(dx);
    hipFree(dy);
    return 3;
  }

  int block = 256;
  int grid = (n + block - 1) / block;
  float a = 1.1f;

  hipEvent_t ev_start, ev_stop;
  hipEventCreate(&ev_start);
  hipEventCreate(&ev_stop);

  hipDeviceSynchronize();
  hipEventRecord(ev_start);
  for (int r = 0; r < reps; ++r) {
    hipLaunchKernelGGL(axpy_kernel, dim3(grid), dim3(block), 0, 0, dy, dx, a, n);
  }
  hipEventRecord(ev_stop);
  hipEventSynchronize(ev_stop);

  float elapsed_ms = 0.0f;
  hipEventElapsedTime(&elapsed_ms, ev_start, ev_stop);
  hipDeviceSynchronize();

  if (hipMemcpy(hy.data(), dy, bytes, hipMemcpyDeviceToHost) != hipSuccess) {
    std::cerr << "{\"ok\":false,\"error\":\"hipMemcpy_d2h_failed\"}\n";
    hipFree(dx);
    hipFree(dy);
    return 4;
  }

  long double checksum = 0.0;
  for (int i = 0; i < n; ++i) {
    checksum += static_cast<long double>(hy[static_cast<size_t>(i)]);
  }
  const long double expected = static_cast<long double>(n) * (0.75L + static_cast<long double>(reps) * 1.1L * 1.25L);
  const long double rel_err = std::abs(checksum - expected) / std::max(1.0L, std::abs(expected));
  bool ok = (rel_err <= 1e-5L);

  // Approximate bandwidth: read x + read/write y => 3 arrays per rep.
  long double moved_bytes = static_cast<long double>(reps) * static_cast<long double>(bytes) * 3.0L;
  long double seconds = std::max(1e-9L, static_cast<long double>(elapsed_ms) / 1000.0L);
  long double gbps = moved_bytes / seconds / 1e9L;

  std::cout << std::fixed << std::setprecision(6)
            << "{"
            << "\"ok\":" << (ok ? "true" : "false") << ","
            << "\"n\":" << n << ","
            << "\"reps\":" << reps << ","
            << "\"elapsed_ms\":" << elapsed_ms << ","
            << "\"bandwidth_gbps\":" << static_cast<double>(gbps) << ","
            << "\"checksum\":" << static_cast<double>(checksum) << ","
            << "\"relative_error\":" << static_cast<double>(rel_err)
            << "}\n";

  hipEventDestroy(ev_start);
  hipEventDestroy(ev_stop);
  hipFree(dx);
  hipFree(dy);
  return ok ? 0 : 5;
}
