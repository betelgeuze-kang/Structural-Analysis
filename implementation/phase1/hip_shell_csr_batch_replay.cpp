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

__global__ void shell_csr_batch_kernel(
    const long long* row_ptr,
    const long long* col_idx,
    const double* values,
    const double* states,
    double* out,
    long long n_rows,
    long long n_dof,
    long long batch_size) {
  long long idx = static_cast<long long>(blockIdx.x) * blockDim.x + threadIdx.x;
  long long total = batch_size * n_rows;
  if (idx >= total) {
    return;
  }
  long long row = idx % n_rows;
  long long batch = idx / n_rows;
  const double* u = states + batch * n_dof;
  double sum = 0.0;
  for (long long k = row_ptr[row]; k < row_ptr[row + 1]; ++k) {
    sum += values[k] * u[col_idx[k]];
  }
  out[batch * n_rows + row] = sum;
}

struct Args {
  std::string row_ptr_path;
  std::string col_idx_path;
  std::string values_path;
  std::string states_path;
  std::string output_path;
  long long n_rows = 0;
  long long n_dof = 0;
  long long nnz = 0;
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
    if (key == "--row-ptr") {
      args.row_ptr_path = next();
    } else if (key == "--col-idx") {
      args.col_idx_path = next();
    } else if (key == "--values") {
      args.values_path = next();
    } else if (key == "--states") {
      args.states_path = next();
    } else if (key == "--output") {
      args.output_path = next();
    } else if (key == "--n-rows") {
      args.n_rows = std::stoll(next());
    } else if (key == "--n-dof") {
      args.n_dof = std::stoll(next());
    } else if (key == "--nnz") {
      args.nnz = std::stoll(next());
    } else if (key == "--batch-size") {
      args.batch_size = std::stoll(next());
    } else if (key == "--reps") {
      args.reps = std::max(1, std::stoi(next()));
    } else {
      throw std::runtime_error("unknown argument: " + key);
    }
  }
  if (args.row_ptr_path.empty() || args.col_idx_path.empty() || args.values_path.empty() ||
      args.states_path.empty() || args.output_path.empty() || args.n_rows <= 0 ||
      args.n_dof <= 0 || args.nnz <= 0 || args.batch_size <= 0) {
    throw std::runtime_error("missing required arguments");
  }
  return args;
}

int main(int argc, char** argv) {
  try {
    Args args = parse_args(argc, argv);
    auto h_row_ptr = read_binary<long long>(args.row_ptr_path, static_cast<size_t>(args.n_rows + 1));
    auto h_col_idx = read_binary<long long>(args.col_idx_path, static_cast<size_t>(args.nnz));
    auto h_values = read_binary<double>(args.values_path, static_cast<size_t>(args.nnz));
    size_t state_count = static_cast<size_t>(args.batch_size) * static_cast<size_t>(args.n_dof);
    size_t out_count = static_cast<size_t>(args.batch_size) * static_cast<size_t>(args.n_rows);
    auto h_states = read_binary<double>(args.states_path, state_count);
    std::vector<double> h_out(out_count, 0.0);

    int device_count = 0;
    hipError_t device_count_status = hipGetDeviceCount(&device_count);
    bool device_count_query_ok = device_count_status == hipSuccess;
    if (device_count_query_ok && device_count <= 0) {
      throw std::runtime_error("hipGetDeviceCount returned zero devices");
    }
    hipError_t set_device_status = hipSetDevice(0);
    bool set_device_ok = set_device_status == hipSuccess;
    hipDeviceProp_t device_props{};
    bool device_props_ok = false;
    if (set_device_ok) {
      check_hip(hipGetDeviceProperties(&device_props, 0), "hipGetDeviceProperties(0)");
      device_props_ok = true;
    }

    long long* d_row_ptr = nullptr;
    long long* d_col_idx = nullptr;
    double* d_values = nullptr;
    double* d_states = nullptr;
    double* d_out = nullptr;
    check_hip(hipMalloc(&d_row_ptr, h_row_ptr.size() * sizeof(long long)), "hipMalloc row_ptr");
    check_hip(hipMalloc(&d_col_idx, h_col_idx.size() * sizeof(long long)), "hipMalloc col_idx");
    check_hip(hipMalloc(&d_values, h_values.size() * sizeof(double)), "hipMalloc values");
    check_hip(hipMalloc(&d_states, h_states.size() * sizeof(double)), "hipMalloc states");
    check_hip(hipMalloc(&d_out, h_out.size() * sizeof(double)), "hipMalloc output");
    check_hip(hipMemcpy(d_row_ptr, h_row_ptr.data(), h_row_ptr.size() * sizeof(long long), hipMemcpyHostToDevice), "copy row_ptr");
    check_hip(hipMemcpy(d_col_idx, h_col_idx.data(), h_col_idx.size() * sizeof(long long), hipMemcpyHostToDevice), "copy col_idx");
    check_hip(hipMemcpy(d_values, h_values.data(), h_values.size() * sizeof(double), hipMemcpyHostToDevice), "copy values");
    check_hip(hipMemcpy(d_states, h_states.data(), h_states.size() * sizeof(double), hipMemcpyHostToDevice), "copy states");

    hipEvent_t start, stop;
    check_hip(hipEventCreate(&start), "event create start");
    check_hip(hipEventCreate(&stop), "event create stop");
    int block = 256;
    long long total = args.batch_size * args.n_rows;
    int grid = static_cast<int>((total + block - 1LL) / block);
    check_hip(hipDeviceSynchronize(), "device synchronize before");
    check_hip(hipEventRecord(start), "event record start");
    for (int rep = 0; rep < args.reps; ++rep) {
      hipLaunchKernelGGL(
          shell_csr_batch_kernel,
          dim3(grid),
          dim3(block),
          0,
          0,
          d_row_ptr,
          d_col_idx,
          d_values,
          d_states,
          d_out,
          args.n_rows,
          args.n_dof,
          args.batch_size);
      check_hip(hipGetLastError(), "launch shell_csr_batch_kernel");
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
              << "\"backend\":\"native_hip_shell_csr_batch\","
              << "\"n_rows\":" << args.n_rows << ","
              << "\"n_dof\":" << args.n_dof << ","
              << "\"nnz\":" << args.nnz << ","
              << "\"batch_size\":" << args.batch_size << ","
              << "\"reps\":" << args.reps << ","
              << "\"device_count\":" << device_count << ","
              << "\"device_count_query_ok\":" << (device_count_query_ok ? "true" : "false") << ","
              << "\"device_count_query_error\":\""
              << (device_count_query_ok ? "" : hipGetErrorString(device_count_status)) << "\","
              << "\"set_device_ok\":" << (set_device_ok ? "true" : "false") << ","
              << "\"set_device_error\":\""
              << (set_device_ok ? "" : hipGetErrorString(set_device_status)) << "\","
              << "\"device_props_ok\":" << (device_props_ok ? "true" : "false") << ","
              << "\"device_name\":\"" << (device_props_ok ? device_props.name : "") << "\","
              << "\"kernel_elapsed_ms_total\":" << elapsed_ms << ","
              << "\"kernel_elapsed_ms_mean\":" << (elapsed_ms / static_cast<float>(args.reps)) << ","
              << "\"output_abs_sum\":" << static_cast<double>(output_abs_sum) << ","
              << "\"output_max_abs\":" << static_cast<double>(output_max_abs)
              << "}\n";

    (void)hipEventDestroy(start);
    (void)hipEventDestroy(stop);
    (void)hipFree(d_row_ptr);
    (void)hipFree(d_col_idx);
    (void)hipFree(d_values);
    (void)hipFree(d_states);
    (void)hipFree(d_out);
    return 0;
  } catch (const std::exception& exc) {
    std::cerr << "{\"ok\":false,\"error\":\"" << exc.what() << "\"}\n";
    return 1;
  }
}
