#include <hip/hip_runtime.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

constexpr std::array<char, 8> kMagic = {'E', 'V', '2', 'H', 'I', 'P', '0', '1'};

void check_hip(hipError_t status, const char* where) {
  if (status != hipSuccess) {
    throw std::runtime_error(std::string(where) + ":" + hipGetErrorString(status));
  }
}

template <typename T>
void read_vector(std::ifstream& input, std::vector<T>& values) {
  input.read(reinterpret_cast<char*>(values.data()),
             static_cast<std::streamsize>(values.size() * sizeof(T)));
  if (!input) {
    throw std::runtime_error("fixture_truncated");
  }
}

template <typename T>
void read_scalar(std::ifstream& input, T& value) {
  input.read(reinterpret_cast<char*>(&value), static_cast<std::streamsize>(sizeof(T)));
  if (!input) {
    throw std::runtime_error("fixture_truncated");
  }
}

template <typename T>
T* allocate_and_copy(const std::vector<T>& host, hipStream_t stream) {
  T* device = nullptr;
  check_hip(hipMalloc(&device, host.size() * sizeof(T)), "hipMalloc");
  check_hip(hipMemcpyAsync(device, host.data(), host.size() * sizeof(T),
                           hipMemcpyHostToDevice, stream),
            "hipMemcpyAsync_h2d");
  return device;
}

__global__ void csr_spmv_kernel(std::int64_t n, const std::int64_t* row_ptr,
                                const std::int32_t* columns, const double* values,
                                const double* x, double* output) {
  const std::int64_t row =
      static_cast<std::int64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (row >= n) {
    return;
  }
  double sum = 0.0;
  for (std::int64_t position = row_ptr[row]; position < row_ptr[row + 1]; ++position) {
    sum += values[position] * x[columns[position]];
  }
  output[row] = sum;
}

__global__ void dot_kernel(std::int64_t n, const double* x, const double* y,
                           double* output) {
  if (blockIdx.x != 0 || threadIdx.x != 0) {
    return;
  }
  double sum = 0.0;
  for (std::int64_t index = 0; index < n; ++index) {
    sum += x[index] * y[index];
  }
  output[0] = sum;
}

__global__ void norm_kernel(std::int64_t n, const double* x, double* output) {
  if (blockIdx.x != 0 || threadIdx.x != 0) {
    return;
  }
  double squared = 0.0;
  double infinity = 0.0;
  for (std::int64_t index = 0; index < n; ++index) {
    squared += x[index] * x[index];
    infinity = fmax(infinity, fabs(x[index]));
  }
  output[0] = sqrt(squared);
  output[1] = infinity;
}

__global__ void preconditioner_kernel(std::int64_t n, const double* inverse_diagonal,
                                      const double* x, double* output) {
  const std::int64_t index =
      static_cast<std::int64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index < n) {
    output[index] = inverse_diagonal[index] * x[index];
  }
}

__global__ void axpy_kernel(std::int64_t n, double alpha, const double* x,
                            const double* y, double* output) {
  const std::int64_t index =
      static_cast<std::int64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index < n) {
    output[index] = alpha * x[index] + y[index];
  }
}

__global__ void update_kernel(std::int64_t n, double alpha, const double* solution,
                              const double* direction, double* output) {
  const std::int64_t index =
      static_cast<std::int64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index < n) {
    output[index] = solution[index] + alpha * direction[index];
  }
}

void print_vector(const std::vector<double>& values) {
  std::cout << '[';
  for (std::size_t index = 0; index < values.size(); ++index) {
    if (index != 0) {
      std::cout << ',';
    }
    std::cout << values[index];
  }
  std::cout << ']';
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc != 2) {
      throw std::runtime_error("usage:engine_v2_primitive_parity fixture.bin");
    }
    std::ifstream input(argv[1], std::ios::binary);
    if (!input) {
      throw std::runtime_error("fixture_open_failed");
    }
    std::array<char, 8> magic{};
    input.read(magic.data(), static_cast<std::streamsize>(magic.size()));
    if (!input || magic != kMagic) {
      throw std::runtime_error("fixture_magic_invalid");
    }
    std::uint64_t n_unsigned = 0;
    std::uint64_t nnz_unsigned = 0;
    double axpy_alpha = 0.0;
    double update_alpha = 0.0;
    read_scalar(input, n_unsigned);
    read_scalar(input, nnz_unsigned);
    read_scalar(input, axpy_alpha);
    read_scalar(input, update_alpha);
    if (n_unsigned == 0 || n_unsigned > 1000000 || nnz_unsigned > 100000000) {
      throw std::runtime_error("fixture_dimensions_invalid");
    }
    const auto n = static_cast<std::int64_t>(n_unsigned);
    const auto nnz = static_cast<std::int64_t>(nnz_unsigned);
    std::vector<std::int64_t> row_ptr(static_cast<std::size_t>(n + 1));
    std::vector<std::int32_t> columns(static_cast<std::size_t>(nnz));
    std::vector<double> values(static_cast<std::size_t>(nnz));
    std::vector<double> x(static_cast<std::size_t>(n));
    std::vector<double> y(static_cast<std::size_t>(n));
    std::vector<double> scale(static_cast<std::size_t>(n));
    std::vector<double> inverse_diagonal(static_cast<std::size_t>(n));
    std::vector<double> solution(static_cast<std::size_t>(n));
    std::vector<double> direction(static_cast<std::size_t>(n));
    read_vector(input, row_ptr);
    read_vector(input, columns);
    read_vector(input, values);
    read_vector(input, x);
    read_vector(input, y);
    read_vector(input, scale);
    read_vector(input, inverse_diagonal);
    read_vector(input, solution);
    read_vector(input, direction);
    if (input.peek() != std::ifstream::traits_type::eof() || row_ptr.front() != 0 ||
        row_ptr.back() != nnz ||
        !std::is_sorted(row_ptr.begin(), row_ptr.end())) {
      throw std::runtime_error("fixture_csr_invalid");
    }
    for (const auto column : columns) {
      if (column < 0 || column >= n) {
        throw std::runtime_error("fixture_column_invalid");
      }
    }
    for (std::int64_t row = 0; row < n; ++row) {
      int diagonal_count = 0;
      double diagonal = 0.0;
      for (std::int64_t position = row_ptr[row];
           position < row_ptr[row + 1]; ++position) {
        if (columns[position] == row) {
          ++diagonal_count;
          diagonal = values[position];
        }
      }
      const double scaled_diagonal = diagonal / scale[row];
      const double expected_inverse = 1.0 / scaled_diagonal;
      if (diagonal_count != 1 || !std::isfinite(scaled_diagonal) ||
          scaled_diagonal <= 0.0 || !std::isfinite(expected_inverse) ||
          inverse_diagonal[row] != expected_inverse) {
        throw std::runtime_error("fixture_preconditioner_binding_invalid");
      }
    }

    int device_index = 0;
    check_hip(hipGetDevice(&device_index), "hipGetDevice");
    hipDeviceProp_t properties{};
    check_hip(hipGetDeviceProperties(&properties, device_index),
              "hipGetDeviceProperties");
    hipStream_t stream = nullptr;
    check_hip(hipStreamCreate(&stream), "hipStreamCreate");

    auto* d_row_ptr = allocate_and_copy(row_ptr, stream);
    auto* d_columns = allocate_and_copy(columns, stream);
    auto* d_values = allocate_and_copy(values, stream);
    auto* d_x = allocate_and_copy(x, stream);
    auto* d_y = allocate_and_copy(y, stream);
    auto* d_inverse_diagonal = allocate_and_copy(inverse_diagonal, stream);
    auto* d_solution = allocate_and_copy(solution, stream);
    auto* d_direction = allocate_and_copy(direction, stream);
    double* d_spmv = nullptr;
    double* d_dot = nullptr;
    double* d_norms = nullptr;
    double* d_preconditioned = nullptr;
    double* d_axpy = nullptr;
    double* d_update = nullptr;
    check_hip(hipMalloc(&d_spmv, static_cast<std::size_t>(n) * sizeof(double)),
              "hipMalloc_spmv");
    check_hip(hipMalloc(&d_dot, sizeof(double)), "hipMalloc_dot");
    check_hip(hipMalloc(&d_norms, 2 * sizeof(double)), "hipMalloc_norms");
    check_hip(
        hipMalloc(&d_preconditioned, static_cast<std::size_t>(n) * sizeof(double)),
        "hipMalloc_preconditioned");
    check_hip(hipMalloc(&d_axpy, static_cast<std::size_t>(n) * sizeof(double)),
              "hipMalloc_axpy");
    check_hip(hipMalloc(&d_update, static_cast<std::size_t>(n) * sizeof(double)),
              "hipMalloc_update");

    const int block_size = 128;
    const int grid_size = static_cast<int>((n + block_size - 1) / block_size);
    hipLaunchKernelGGL(csr_spmv_kernel, dim3(grid_size), dim3(block_size), 0, stream,
                       n, d_row_ptr, d_columns, d_values, d_x, d_spmv);
    check_hip(hipGetLastError(), "csr_spmv_kernel");
    hipLaunchKernelGGL(dot_kernel, dim3(1), dim3(1), 0, stream, n, d_x, d_y, d_dot);
    check_hip(hipGetLastError(), "dot_kernel");
    hipLaunchKernelGGL(norm_kernel, dim3(1), dim3(1), 0, stream, n, d_x, d_norms);
    check_hip(hipGetLastError(), "norm_kernel");
    hipLaunchKernelGGL(preconditioner_kernel, dim3(grid_size), dim3(block_size), 0,
                       stream, n, d_inverse_diagonal, d_x, d_preconditioned);
    check_hip(hipGetLastError(), "preconditioner_kernel");
    hipLaunchKernelGGL(axpy_kernel, dim3(grid_size), dim3(block_size), 0, stream, n,
                       axpy_alpha, d_x, d_y, d_axpy);
    check_hip(hipGetLastError(), "axpy_kernel");
    hipLaunchKernelGGL(update_kernel, dim3(grid_size), dim3(block_size), 0, stream, n,
                       update_alpha, d_solution, d_direction, d_update);
    check_hip(hipGetLastError(), "update_kernel");

    std::vector<double> spmv(static_cast<std::size_t>(n));
    std::vector<double> dot(1);
    std::vector<double> norms(2);
    std::vector<double> preconditioned(static_cast<std::size_t>(n));
    std::vector<double> axpy(static_cast<std::size_t>(n));
    std::vector<double> update(static_cast<std::size_t>(n));
    check_hip(hipMemcpyAsync(spmv.data(), d_spmv, spmv.size() * sizeof(double),
                             hipMemcpyDeviceToHost, stream),
              "hipMemcpyAsync_spmv");
    check_hip(hipMemcpyAsync(dot.data(), d_dot, sizeof(double), hipMemcpyDeviceToHost,
                             stream),
              "hipMemcpyAsync_dot");
    check_hip(hipMemcpyAsync(norms.data(), d_norms, norms.size() * sizeof(double),
                             hipMemcpyDeviceToHost, stream),
              "hipMemcpyAsync_norms");
    check_hip(hipMemcpyAsync(preconditioned.data(), d_preconditioned,
                             preconditioned.size() * sizeof(double),
                             hipMemcpyDeviceToHost, stream),
              "hipMemcpyAsync_preconditioned");
    check_hip(hipMemcpyAsync(axpy.data(), d_axpy, axpy.size() * sizeof(double),
                             hipMemcpyDeviceToHost, stream),
              "hipMemcpyAsync_axpy");
    check_hip(hipMemcpyAsync(update.data(), d_update, update.size() * sizeof(double),
                             hipMemcpyDeviceToHost, stream),
              "hipMemcpyAsync_update");
    check_hip(hipStreamSynchronize(stream), "hipStreamSynchronize");

    std::cout << std::setprecision(17);
    std::cout << "{\"schema_version\":\"engine-v2-hip-primitive-output.v1\","
              << "\"runtime_status\":\"success\",\"runtime_status_code\":0,"
              << "\"backend\":\"amd_rocm_hip\",\"cpu_backend\":false,"
              << "\"same_stream_ordering\":true,"
              << "\"blocking_d2h_synchronization_count\":1,"
              << "\"kernel_invocation_count\":6,"
              << "\"production_full_recurrence_claim\":false,"
              << "\"preconditioner_profile\":"
                 "\"operator_derived_left_scaled_jacobi_right.v1\","
              << "\"reduction_profile\":\"single_thread_ascending_index_fp64_probe.v1\","
              << "\"device_index\":" << device_index << ','
              << "\"device_name\":\"" << properties.name << "\","
              << "\"gcn_arch_name\":\"" << properties.gcnArchName << "\","
              << "\"fixture_dimension\":" << n << ','
              << "\"fixture_nnz\":" << nnz << ','
              << "\"operations\":{\"spmv\":";
    print_vector(spmv);
    std::cout << ",\"dot\":" << dot[0] << ",\"l2_norm\":" << norms[0]
              << ",\"linf_norm\":" << norms[1]
              << ",\"preconditioner_apply\":";
    print_vector(preconditioned);
    std::cout << ",\"axpy\":";
    print_vector(axpy);
    std::cout << ",\"solution_update\":";
    print_vector(update);
    std::cout << "}}\n";

    check_hip(hipFree(d_row_ptr), "hipFree_row_ptr");
    check_hip(hipFree(d_columns), "hipFree_columns");
    check_hip(hipFree(d_values), "hipFree_values");
    check_hip(hipFree(d_x), "hipFree_x");
    check_hip(hipFree(d_y), "hipFree_y");
    check_hip(hipFree(d_inverse_diagonal), "hipFree_inverse_diagonal");
    check_hip(hipFree(d_solution), "hipFree_solution");
    check_hip(hipFree(d_direction), "hipFree_direction");
    check_hip(hipFree(d_spmv), "hipFree_spmv");
    check_hip(hipFree(d_dot), "hipFree_dot");
    check_hip(hipFree(d_norms), "hipFree_norms");
    check_hip(hipFree(d_preconditioned), "hipFree_preconditioned");
    check_hip(hipFree(d_axpy), "hipFree_axpy");
    check_hip(hipFree(d_update), "hipFree_update");
    check_hip(hipStreamDestroy(stream), "hipStreamDestroy");
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "{\"schema_version\":\"engine-v2-hip-primitive-output.v1\","
              << "\"runtime_status\":\"error\",\"runtime_status_code\":1,"
              << "\"error\":\"" << error.what() << "\"}\n";
    return 1;
  }
}
