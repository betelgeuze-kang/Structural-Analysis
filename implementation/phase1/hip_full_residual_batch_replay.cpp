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

struct Args {
  std::string frame_dofs_path;
  std::string frame_stiffness_path;
  std::string shell_row_ptr_path;
  std::string shell_col_idx_path;
  std::string shell_values_path;
  std::string spring_row_ptr_path;
  std::string spring_col_idx_path;
  std::string spring_values_path;
  std::string states_path;
  std::string f_ext_path;
  std::string free_path;
  std::string output_path;
  long long frame_element_count = 0;
  long long n_dof = 0;
  long long shell_nnz = 0;
  long long spring_nnz = 0;
  long long free_count = 0;
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
    if (key == "--frame-dofs") {
      args.frame_dofs_path = next();
    } else if (key == "--frame-stiffness") {
      args.frame_stiffness_path = next();
    } else if (key == "--shell-row-ptr") {
      args.shell_row_ptr_path = next();
    } else if (key == "--shell-col-idx") {
      args.shell_col_idx_path = next();
    } else if (key == "--shell-values") {
      args.shell_values_path = next();
    } else if (key == "--spring-row-ptr") {
      args.spring_row_ptr_path = next();
    } else if (key == "--spring-col-idx") {
      args.spring_col_idx_path = next();
    } else if (key == "--spring-values") {
      args.spring_values_path = next();
    } else if (key == "--states") {
      args.states_path = next();
    } else if (key == "--f-ext") {
      args.f_ext_path = next();
    } else if (key == "--free") {
      args.free_path = next();
    } else if (key == "--output") {
      args.output_path = next();
    } else if (key == "--frame-element-count") {
      args.frame_element_count = std::stoll(next());
    } else if (key == "--n-dof") {
      args.n_dof = std::stoll(next());
    } else if (key == "--shell-nnz") {
      args.shell_nnz = std::stoll(next());
    } else if (key == "--spring-nnz") {
      args.spring_nnz = std::stoll(next());
    } else if (key == "--free-count") {
      args.free_count = std::stoll(next());
    } else if (key == "--batch-size") {
      args.batch_size = std::stoll(next());
    } else if (key == "--reps") {
      args.reps = std::max(1, std::stoi(next()));
    } else {
      throw std::runtime_error("unknown argument: " + key);
    }
  }
  bool missing_paths =
      args.frame_dofs_path.empty() || args.frame_stiffness_path.empty() ||
      args.shell_row_ptr_path.empty() || args.shell_col_idx_path.empty() ||
      args.shell_values_path.empty() || args.spring_row_ptr_path.empty() ||
      args.spring_col_idx_path.empty() || args.spring_values_path.empty() ||
      args.states_path.empty() || args.f_ext_path.empty() || args.free_path.empty() ||
      args.output_path.empty();
  if (missing_paths || args.frame_element_count <= 0 || args.n_dof <= 0 ||
      args.shell_nnz <= 0 || args.spring_nnz < 0 || args.free_count <= 0 ||
      args.batch_size <= 0) {
    throw std::runtime_error("missing required arguments");
  }
  return args;
}

int main(int argc, char** argv) {
  long long* d_frame_dofs = nullptr;
  double* d_frame_stiffness = nullptr;
  long long* d_shell_row_ptr = nullptr;
  long long* d_shell_col_idx = nullptr;
  double* d_shell_values = nullptr;
  long long* d_spring_row_ptr = nullptr;
  long long* d_spring_col_idx = nullptr;
  double* d_spring_values = nullptr;
  double* d_states = nullptr;
  double* d_f_ext = nullptr;
  long long* d_free = nullptr;
  double* d_frame_out = nullptr;
  double* d_residual_out = nullptr;
  hipEvent_t start = nullptr;
  hipEvent_t stop = nullptr;

  try {
    Args args = parse_args(argc, argv);
    size_t frame_dof_count = static_cast<size_t>(args.frame_element_count) * 12ULL;
    size_t frame_stiffness_count = static_cast<size_t>(args.frame_element_count) * 144ULL;
    size_t shell_row_ptr_count = static_cast<size_t>(args.n_dof + 1LL);
    size_t spring_row_ptr_count = static_cast<size_t>(args.n_dof + 1LL);
    size_t state_count = static_cast<size_t>(args.batch_size) * static_cast<size_t>(args.n_dof);
    size_t output_count = static_cast<size_t>(args.batch_size) * static_cast<size_t>(args.free_count);

    auto h_frame_dofs = read_binary<long long>(args.frame_dofs_path, frame_dof_count);
    auto h_frame_stiffness = read_binary<double>(args.frame_stiffness_path, frame_stiffness_count);
    auto h_shell_row_ptr = read_binary<long long>(args.shell_row_ptr_path, shell_row_ptr_count);
    auto h_shell_col_idx = read_binary<long long>(args.shell_col_idx_path, static_cast<size_t>(args.shell_nnz));
    auto h_shell_values = read_binary<double>(args.shell_values_path, static_cast<size_t>(args.shell_nnz));
    auto h_spring_row_ptr = read_binary<long long>(args.spring_row_ptr_path, spring_row_ptr_count);
    auto h_spring_col_idx = read_binary<long long>(args.spring_col_idx_path, static_cast<size_t>(args.spring_nnz));
    auto h_spring_values = read_binary<double>(args.spring_values_path, static_cast<size_t>(args.spring_nnz));
    auto h_states = read_binary<double>(args.states_path, state_count);
    auto h_f_ext = read_binary<double>(args.f_ext_path, static_cast<size_t>(args.n_dof));
    auto h_free = read_binary<long long>(args.free_path, static_cast<size_t>(args.free_count));
    std::vector<double> h_residual_out(output_count, 0.0);

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

    check_hip(hipMalloc(&d_frame_dofs, h_frame_dofs.size() * sizeof(long long)), "hipMalloc frame_dofs");
    check_hip(hipMalloc(&d_frame_stiffness, h_frame_stiffness.size() * sizeof(double)), "hipMalloc frame_stiffness");
    check_hip(hipMalloc(&d_shell_row_ptr, h_shell_row_ptr.size() * sizeof(long long)), "hipMalloc shell_row_ptr");
    check_hip(hipMalloc(&d_shell_col_idx, h_shell_col_idx.size() * sizeof(long long)), "hipMalloc shell_col_idx");
    check_hip(hipMalloc(&d_shell_values, h_shell_values.size() * sizeof(double)), "hipMalloc shell_values");
    check_hip(hipMalloc(&d_spring_row_ptr, h_spring_row_ptr.size() * sizeof(long long)), "hipMalloc spring_row_ptr");
    check_hip(hipMalloc(&d_spring_col_idx, h_spring_col_idx.size() * sizeof(long long)), "hipMalloc spring_col_idx");
    check_hip(hipMalloc(&d_spring_values, h_spring_values.size() * sizeof(double)), "hipMalloc spring_values");
    check_hip(hipMalloc(&d_states, h_states.size() * sizeof(double)), "hipMalloc states");
    check_hip(hipMalloc(&d_f_ext, h_f_ext.size() * sizeof(double)), "hipMalloc f_ext");
    check_hip(hipMalloc(&d_free, h_free.size() * sizeof(long long)), "hipMalloc free");
    check_hip(hipMalloc(&d_frame_out, state_count * sizeof(double)), "hipMalloc frame_out");
    check_hip(hipMalloc(&d_residual_out, h_residual_out.size() * sizeof(double)), "hipMalloc residual_out");

    check_hip(hipMemcpy(d_frame_dofs, h_frame_dofs.data(), h_frame_dofs.size() * sizeof(long long), hipMemcpyHostToDevice), "copy frame_dofs");
    check_hip(hipMemcpy(d_frame_stiffness, h_frame_stiffness.data(), h_frame_stiffness.size() * sizeof(double), hipMemcpyHostToDevice), "copy frame_stiffness");
    check_hip(hipMemcpy(d_shell_row_ptr, h_shell_row_ptr.data(), h_shell_row_ptr.size() * sizeof(long long), hipMemcpyHostToDevice), "copy shell_row_ptr");
    check_hip(hipMemcpy(d_shell_col_idx, h_shell_col_idx.data(), h_shell_col_idx.size() * sizeof(long long), hipMemcpyHostToDevice), "copy shell_col_idx");
    check_hip(hipMemcpy(d_shell_values, h_shell_values.data(), h_shell_values.size() * sizeof(double), hipMemcpyHostToDevice), "copy shell_values");
    check_hip(hipMemcpy(d_spring_row_ptr, h_spring_row_ptr.data(), h_spring_row_ptr.size() * sizeof(long long), hipMemcpyHostToDevice), "copy spring_row_ptr");
    check_hip(hipMemcpy(d_spring_col_idx, h_spring_col_idx.data(), h_spring_col_idx.size() * sizeof(long long), hipMemcpyHostToDevice), "copy spring_col_idx");
    check_hip(hipMemcpy(d_spring_values, h_spring_values.data(), h_spring_values.size() * sizeof(double), hipMemcpyHostToDevice), "copy spring_values");
    check_hip(hipMemcpy(d_states, h_states.data(), h_states.size() * sizeof(double), hipMemcpyHostToDevice), "copy states");
    check_hip(hipMemcpy(d_f_ext, h_f_ext.data(), h_f_ext.size() * sizeof(double), hipMemcpyHostToDevice), "copy f_ext");
    check_hip(hipMemcpy(d_free, h_free.data(), h_free.size() * sizeof(long long), hipMemcpyHostToDevice), "copy free");

    check_hip(hipEventCreate(&start), "event create start");
    check_hip(hipEventCreate(&stop), "event create stop");
    int block = 256;
    long long frame_total = args.batch_size * args.frame_element_count * 12LL;
    long long residual_total = args.batch_size * args.free_count;
    int frame_grid = static_cast<int>((frame_total + block - 1LL) / block);
    int residual_grid = static_cast<int>((residual_total + block - 1LL) / block);
    check_hip(hipDeviceSynchronize(), "device synchronize before");
    check_hip(hipEventRecord(start), "event record start");
    for (int rep = 0; rep < args.reps; ++rep) {
      check_hip(hipMemset(d_frame_out, 0, state_count * sizeof(double)), "memset frame_out");
      hipLaunchKernelGGL(
          frame_force_batch_kernel,
          dim3(frame_grid),
          dim3(block),
          0,
          0,
          d_frame_dofs,
          d_frame_stiffness,
          d_states,
          d_frame_out,
          args.frame_element_count,
          args.n_dof,
          args.batch_size);
      check_hip(hipGetLastError(), "launch frame_force_batch_kernel");
      hipLaunchKernelGGL(
          full_residual_batch_kernel,
          dim3(residual_grid),
          dim3(block),
          0,
          0,
          d_frame_out,
          d_shell_row_ptr,
          d_shell_col_idx,
          d_shell_values,
          d_spring_row_ptr,
          d_spring_col_idx,
          d_spring_values,
          d_states,
          d_f_ext,
          d_free,
          d_residual_out,
          args.n_dof,
          args.free_count,
          args.batch_size);
      check_hip(hipGetLastError(), "launch full_residual_batch_kernel");
    }
    check_hip(hipEventRecord(stop), "event record stop");
    check_hip(hipEventSynchronize(stop), "event synchronize stop");
    float elapsed_ms = 0.0f;
    check_hip(hipEventElapsedTime(&elapsed_ms, start, stop), "event elapsed");
    check_hip(hipMemcpy(h_residual_out.data(), d_residual_out, h_residual_out.size() * sizeof(double), hipMemcpyDeviceToHost), "copy residual_out");
    write_binary(args.output_path, h_residual_out);

    long double output_abs_sum = 0.0L;
    long double output_max_abs = 0.0L;
    for (double value : h_residual_out) {
      long double abs_value = std::abs(static_cast<long double>(value));
      output_abs_sum += abs_value;
      output_max_abs = std::max(output_max_abs, abs_value);
    }
    std::cout << std::fixed << std::setprecision(9)
              << "{"
              << "\"ok\":true,"
              << "\"backend\":\"native_hip_full_residual_batch\","
              << "\"frame_element_count\":" << args.frame_element_count << ","
              << "\"n_dof\":" << args.n_dof << ","
              << "\"free_count\":" << args.free_count << ","
              << "\"shell_nnz\":" << args.shell_nnz << ","
              << "\"spring_nnz\":" << args.spring_nnz << ","
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
    (void)hipFree(d_frame_dofs);
    (void)hipFree(d_frame_stiffness);
    (void)hipFree(d_shell_row_ptr);
    (void)hipFree(d_shell_col_idx);
    (void)hipFree(d_shell_values);
    (void)hipFree(d_spring_row_ptr);
    (void)hipFree(d_spring_col_idx);
    (void)hipFree(d_spring_values);
    (void)hipFree(d_states);
    (void)hipFree(d_f_ext);
    (void)hipFree(d_free);
    (void)hipFree(d_frame_out);
    (void)hipFree(d_residual_out);
    return 0;
  } catch (const std::exception& exc) {
    std::cerr << "{\"ok\":false,\"error\":\"" << exc.what() << "\"}\n";
    (void)hipEventDestroy(start);
    (void)hipEventDestroy(stop);
    (void)hipFree(d_frame_dofs);
    (void)hipFree(d_frame_stiffness);
    (void)hipFree(d_shell_row_ptr);
    (void)hipFree(d_shell_col_idx);
    (void)hipFree(d_shell_values);
    (void)hipFree(d_spring_row_ptr);
    (void)hipFree(d_spring_col_idx);
    (void)hipFree(d_spring_values);
    (void)hipFree(d_states);
    (void)hipFree(d_f_ext);
    (void)hipFree(d_free);
    (void)hipFree(d_frame_out);
    (void)hipFree(d_residual_out);
    return 1;
  }
}
