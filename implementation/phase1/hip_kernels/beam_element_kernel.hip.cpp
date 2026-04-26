#include <hip/hip_runtime.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <vector>

// Minimal beam-element style kernel smoke:
// computes curvature, moment, shear, and strain-energy like quantities.
__global__ void beam_element_kernel(
    const float* u_i,
    const float* u_j,
    const float* ei,
    const float* length,
    float* moment,
    float* shear,
    float* strain_energy,
    int n
) {
  int idx = blockIdx.x * blockDim.x + threadIdx.x;
  if (idx >= n) {
    return;
  }
  float L = fmaxf(length[idx], 1.0e-4f);
  float du = u_j[idx] - u_i[idx];
  float curv = du / L;
  float m = ei[idx] * curv;
  float v = 12.0f * ei[idx] * du / (L * L * L);
  float e = 0.5f * m * curv * L;
  moment[idx] = m;
  shear[idx] = v;
  strain_energy[idx] = fmaxf(e, 0.0f);
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

  std::vector<float> h_ui(static_cast<size_t>(n));
  std::vector<float> h_uj(static_cast<size_t>(n));
  std::vector<float> h_ei(static_cast<size_t>(n));
  std::vector<float> h_l(static_cast<size_t>(n));
  std::vector<float> h_m(static_cast<size_t>(n), 0.0f);
  std::vector<float> h_v(static_cast<size_t>(n), 0.0f);
  std::vector<float> h_e(static_cast<size_t>(n), 0.0f);

  for (int i = 0; i < n; ++i) {
    float x = static_cast<float>(i % 4096) / 4096.0f;
    h_ui[static_cast<size_t>(i)] = 0.0025f * x;
    h_uj[static_cast<size_t>(i)] = 0.0035f * x + 0.0005f;
    h_ei[static_cast<size_t>(i)] = 8.0e7f + 2.0e6f * x;
    h_l[static_cast<size_t>(i)] = 2.5f + 0.25f * x;
  }

  float *d_ui = nullptr, *d_uj = nullptr, *d_ei = nullptr, *d_l = nullptr;
  float *d_m = nullptr, *d_v = nullptr, *d_e = nullptr;
  size_t bytes = static_cast<size_t>(n) * sizeof(float);

  auto alloc_ok = hipMalloc(&d_ui, bytes) == hipSuccess &&
                  hipMalloc(&d_uj, bytes) == hipSuccess &&
                  hipMalloc(&d_ei, bytes) == hipSuccess &&
                  hipMalloc(&d_l, bytes) == hipSuccess &&
                  hipMalloc(&d_m, bytes) == hipSuccess &&
                  hipMalloc(&d_v, bytes) == hipSuccess &&
                  hipMalloc(&d_e, bytes) == hipSuccess;
  if (!alloc_ok) {
    std::cerr << "{\"ok\":false,\"error\":\"hipMalloc_failed\"}\n";
    return 2;
  }

  auto h2d_ok =
      hipMemcpy(d_ui, h_ui.data(), bytes, hipMemcpyHostToDevice) == hipSuccess &&
      hipMemcpy(d_uj, h_uj.data(), bytes, hipMemcpyHostToDevice) == hipSuccess &&
      hipMemcpy(d_ei, h_ei.data(), bytes, hipMemcpyHostToDevice) == hipSuccess &&
      hipMemcpy(d_l, h_l.data(), bytes, hipMemcpyHostToDevice) == hipSuccess;
  if (!h2d_ok) {
    std::cerr << "{\"ok\":false,\"error\":\"hipMemcpy_h2d_failed\"}\n";
    return 3;
  }

  int block = 256;
  int grid = (n + block - 1) / block;
  hipEvent_t ev_start, ev_stop;
  hipEventCreate(&ev_start);
  hipEventCreate(&ev_stop);

  hipDeviceSynchronize();
  hipEventRecord(ev_start);
  for (int r = 0; r < reps; ++r) {
    hipLaunchKernelGGL(
        beam_element_kernel,
        dim3(grid),
        dim3(block),
        0,
        0,
        d_ui,
        d_uj,
        d_ei,
        d_l,
        d_m,
        d_v,
        d_e,
        n);
  }
  hipEventRecord(ev_stop);
  hipEventSynchronize(ev_stop);

  float elapsed_ms = 0.0f;
  hipEventElapsedTime(&elapsed_ms, ev_start, ev_stop);
  hipDeviceSynchronize();

  auto d2h_ok =
      hipMemcpy(h_m.data(), d_m, bytes, hipMemcpyDeviceToHost) == hipSuccess &&
      hipMemcpy(h_v.data(), d_v, bytes, hipMemcpyDeviceToHost) == hipSuccess &&
      hipMemcpy(h_e.data(), d_e, bytes, hipMemcpyDeviceToHost) == hipSuccess;
  if (!d2h_ok) {
    std::cerr << "{\"ok\":false,\"error\":\"hipMemcpy_d2h_failed\"}\n";
    return 4;
  }

  long double sum_m = 0.0L;
  long double sum_v = 0.0L;
  long double sum_e = 0.0L;
  long double max_abs_m = 0.0L;
  long double max_abs_v = 0.0L;
  long double max_abs_e = 0.0L;
  for (int i = 0; i < n; ++i) {
    long double m = static_cast<long double>(h_m[static_cast<size_t>(i)]);
    long double v = static_cast<long double>(h_v[static_cast<size_t>(i)]);
    long double e = static_cast<long double>(h_e[static_cast<size_t>(i)]);
    sum_m += m;
    sum_v += v;
    sum_e += e;
    max_abs_m = std::max(max_abs_m, std::abs(m));
    max_abs_v = std::max(max_abs_v, std::abs(v));
    max_abs_e = std::max(max_abs_e, std::abs(e));
  }

  bool finite_ok = std::isfinite(static_cast<double>(sum_m)) &&
                   std::isfinite(static_cast<double>(sum_v)) &&
                   std::isfinite(static_cast<double>(sum_e)) &&
                   std::isfinite(static_cast<double>(max_abs_m)) &&
                   std::isfinite(static_cast<double>(max_abs_v)) &&
                   std::isfinite(static_cast<double>(max_abs_e));
  bool nontrivial_ok = (max_abs_m > 1e-8L) && (max_abs_v > 1e-8L) && (max_abs_e > 1e-12L);
  bool ok = finite_ok && nontrivial_ok;

  // Approximate bytes moved per rep: 4 reads + 3 writes.
  long double moved_bytes = static_cast<long double>(reps) * static_cast<long double>(bytes) * 7.0L;
  long double seconds = std::max(1e-9L, static_cast<long double>(elapsed_ms) / 1000.0L);
  long double gbps = moved_bytes / seconds / 1e9L;

  std::cout << std::fixed << std::setprecision(6)
            << "{"
            << "\"ok\":" << (ok ? "true" : "false") << ","
            << "\"kernel\":\"beam_element\","
            << "\"n\":" << n << ","
            << "\"reps\":" << reps << ","
            << "\"elapsed_ms\":" << elapsed_ms << ","
            << "\"bandwidth_gbps\":" << static_cast<double>(gbps) << ","
            << "\"sum_moment\":" << static_cast<double>(sum_m) << ","
            << "\"sum_shear\":" << static_cast<double>(sum_v) << ","
            << "\"sum_energy\":" << static_cast<double>(sum_e) << ","
            << "\"max_abs_moment\":" << static_cast<double>(max_abs_m) << ","
            << "\"max_abs_shear\":" << static_cast<double>(max_abs_v) << ","
            << "\"max_abs_energy\":" << static_cast<double>(max_abs_e)
            << "}\n";

  hipEventDestroy(ev_start);
  hipEventDestroy(ev_stop);
  hipFree(d_ui);
  hipFree(d_uj);
  hipFree(d_ei);
  hipFree(d_l);
  hipFree(d_m);
  hipFree(d_v);
  hipFree(d_e);
  return ok ? 0 : 5;
}

