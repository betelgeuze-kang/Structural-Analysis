#include <hip/hip_runtime.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

__global__ void frame_force_batch_kernel(
    const long long* dofs,
    const double* stiffness,
    const double* states,
    double* out,
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
  atomicAdd(out + batch * n_dof + dof_out, sum);
}

struct Args {
  std::string dofs_path;
  std::string stiffness_path;
  std::string states_path;
  std::string output_path;
  long long element_count = 0;
  long long n_dof = 0;
  long long batch_size = 0;
  int reps = 20;
};

void check_hip(hipError_t status, const char* where) {
  if (status != hipSuccess) {
    throw std::runtime_error(std::string(where) + ": " + hipGetErrorString(status));
  }
}

template <typename T>
std::vector<T> read_binary(const std::string& path, size_t expected_count) {
  std::ifstream in(path, std::ios::binary);
  if (!in) {
    throw std::runtime_error("failed to open input: " + path);
  }
  std::vector<T> values(expected_count);
  in.read(reinterpret_cast<char*>(values.data()), static_cast<std::streamsize>(values.size() * sizeof(T)));
  if (in.gcount() != static_cast<std::streamsize>(values.size() * sizeof(T))) {
    throw std::runtime_error("input size mismatch: " + path);
  }
  return values;
}

template <typename T>
void write_binary(const std::string& path, const std::vector<T>& values) {
  std::ofstream out(path, std::ios::binary);
  if (!out) {
    throw std::runtime_error("failed to open output: " + path);
  }
  out.write(reinterpret_cast<const char*>(values.data()), static_cast<std::streamsize>(values.size() * sizeof(T)));
  if (!out) {
    throw std::runtime_error("failed to write output: " + path);
  }
}

Args parse_args(int argc, char** argv) {
  Args args;
  for (int i = 1; i < argc; ++i) {
    std::string key(argv[i]);
    auto next = [&]() -> std::string {
      if (i + 1 >= argc) {
        throw std::runtime_error("missing value for " + key);
      }
      return std::string(argv[++i]);
    };
    if (key == "--dofs") {
      args.dofs_path = next();
    } else if (key == "--stiffness") {
      args.stiffness_path = next();
    } else if (key == "--states") {
      args.states_path = next();
    } else if (key == "--output") {
      args.output_path = next();
    } else if (key == "--element-count") {
      args.element_count = std::stoll(next());
    } else if (key == "--n-dof") {
      args.n_dof = std::stoll(next());
    } else if (key == "--batch-size") {
      args.batch_size = std::stoll(next());
    } else if (key == "--reps") {
      args.reps = std::max(1, std::stoi(next()));
    } else {
      throw std::runtime_error("unknown argument: " + key);
    }
  }
  if (args.dofs_path.empty() || args.stiffness_path.empty() || args.states_path.empty() ||
      args.output_path.empty() || args.element_count <= 0 || args.n_dof <= 0 ||
      args.batch_size <= 0) {
    throw std::runtime_error("missing required arguments");
  }
  return args;
}

int main(int argc, char** argv) {
  try {
    Args args = parse_args(argc, argv);
    size_t dof_count = static_cast<size_t>(args.element_count) * 12ULL;
    size_t stiffness_count = static_cast<size_t>(args.element_count) * 144ULL;
    size_t state_count = static_cast<size_t>(args.batch_size) * static_cast<size_t>(args.n_dof);
    auto h_dofs = read_binary<long long>(args.dofs_path, dof_count);
    auto h_stiffness = read_binary<double>(args.stiffness_path, stiffness_count);
    auto h_states = read_binary<double>(args.states_path, state_count);
    std::vector<double> h_out(state_count, 0.0);

    int device_count = 0;
    check_hip(hipGetDeviceCount(&device_count), "hipGetDeviceCount");
    if (device_count <= 0) {
      throw std::runtime_error("hipGetDeviceCount returned zero devices");
    }
    check_hip(hipSetDevice(0), "hipSetDevice(0)");
    hipDeviceProp_t device_props{};
    check_hip(hipGetDeviceProperties(&device_props, 0), "hipGetDeviceProperties(0)");

    long long* d_dofs = nullptr;
    double* d_stiffness = nullptr;
    double* d_states = nullptr;
    double* d_out = nullptr;
    check_hip(hipMalloc(&d_dofs, h_dofs.size() * sizeof(long long)), "hipMalloc dofs");
    check_hip(hipMalloc(&d_stiffness, h_stiffness.size() * sizeof(double)), "hipMalloc stiffness");
    check_hip(hipMalloc(&d_states, h_states.size() * sizeof(double)), "hipMalloc states");
    check_hip(hipMalloc(&d_out, h_out.size() * sizeof(double)), "hipMalloc output");
    check_hip(hipMemcpy(d_dofs, h_dofs.data(), h_dofs.size() * sizeof(long long), hipMemcpyHostToDevice), "copy dofs");
    check_hip(hipMemcpy(d_stiffness, h_stiffness.data(), h_stiffness.size() * sizeof(double), hipMemcpyHostToDevice), "copy stiffness");
    check_hip(hipMemcpy(d_states, h_states.data(), h_states.size() * sizeof(double), hipMemcpyHostToDevice), "copy states");

    hipEvent_t start, stop;
    check_hip(hipEventCreate(&start), "event create start");
    check_hip(hipEventCreate(&stop), "event create stop");
    int block = 256;
    long long total = args.batch_size * args.element_count * 12LL;
    int grid = static_cast<int>((total + block - 1LL) / block);
    check_hip(hipDeviceSynchronize(), "device synchronize before");
    check_hip(hipEventRecord(start), "event record start");
    for (int rep = 0; rep < args.reps; ++rep) {
      check_hip(hipMemset(d_out, 0, h_out.size() * sizeof(double)), "memset output");
      hipLaunchKernelGGL(
          frame_force_batch_kernel,
          dim3(grid),
          dim3(block),
          0,
          0,
          d_dofs,
          d_stiffness,
          d_states,
          d_out,
          args.element_count,
          args.n_dof,
          args.batch_size);
      check_hip(hipGetLastError(), "launch frame_force_batch_kernel");
    }
    check_hip(hipEventRecord(stop), "event record stop");
    check_hip(hipEventSynchronize(stop), "event synchronize stop");
    float elapsed_ms = 0.0f;
    check_hip(hipEventElapsedTime(&elapsed_ms, start, stop), "event elapsed");
    check_hip(hipMemcpy(h_out.data(), d_out, h_out.size() * sizeof(double), hipMemcpyDeviceToHost), "copy output");
    write_binary(args.output_path, h_out);

    long double output_abs_sum = 0.0L;
    long double output_max_abs = 0.0L;
    for (double value : h_out) {
      long double abs_value = std::abs(static_cast<long double>(value));
      output_abs_sum += abs_value;
      output_max_abs = std::max(output_max_abs, abs_value);
    }
    std::cout << std::fixed << std::setprecision(9)
              << "{"
              << "\"ok\":true,"
              << "\"backend\":\"native_hip_frame_force_batch\","
              << "\"element_count\":" << args.element_count << ","
              << "\"n_dof\":" << args.n_dof << ","
              << "\"batch_size\":" << args.batch_size << ","
              << "\"reps\":" << args.reps << ","
              << "\"device_count\":" << device_count << ","
              << "\"device_name\":\"" << device_props.name << "\","
              << "\"kernel_elapsed_ms_total\":" << elapsed_ms << ","
              << "\"kernel_elapsed_ms_mean\":" << (elapsed_ms / static_cast<float>(args.reps)) << ","
              << "\"output_abs_sum\":" << static_cast<double>(output_abs_sum) << ","
              << "\"output_max_abs\":" << static_cast<double>(output_max_abs)
              << "}\n";

    (void)hipEventDestroy(start);
    (void)hipEventDestroy(stop);
    (void)hipFree(d_dofs);
    (void)hipFree(d_stiffness);
    (void)hipFree(d_states);
    (void)hipFree(d_out);
    return 0;
  } catch (const std::exception& exc) {
    std::cerr << "{\"ok\":false,\"error\":\"" << exc.what() << "\"}\n";
    return 1;
  }
}
