#include <hip/hip_runtime.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>

#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace {

constexpr std::array<char, 8> kMagic = {'E', 'V', '2', 'S', 'L', 'U', '0', '1'};
constexpr const char* kOutputVersion =
    "engine-v2-hip-sparse-lu-apply-output.v1";
constexpr const char* kFixtureValidationOutputVersion =
    "engine-v2-hip-sparse-lu-fixture-validation-output.v1";
constexpr const char* kExecutionProfile =
    "same_stream_level_scheduled_csr_forward_backward.v1";
constexpr const char* kAccumulationProfile =
    "ascending_column_sequential_fp64.v1";

void check_hip(hipError_t status, const char* where) {
  if (status != hipSuccess) {
    throw std::runtime_error(std::string(where) + ":" + hipGetErrorString(status));
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
void read_vector(std::ifstream& input, std::vector<T>& values) {
  input.read(reinterpret_cast<char*>(values.data()),
             static_cast<std::streamsize>(values.size() * sizeof(T)));
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

void validate_permutation(const std::vector<std::int64_t>& values,
                          std::int64_t dimension, const char* label) {
  std::vector<std::int64_t> ordered(values);
  std::sort(ordered.begin(), ordered.end());
  for (std::int64_t index = 0; index < dimension; ++index) {
    if (ordered[static_cast<std::size_t>(index)] != index) {
      throw std::runtime_error(std::string(label) + "_invalid");
    }
  }
}

void validate_triangular(const std::vector<std::int64_t>& row_ptr,
                         const std::vector<std::int64_t>& columns,
                         const std::vector<double>& values, std::int64_t dimension,
                         bool lower) {
  if (row_ptr.front() != 0 || row_ptr.back() != static_cast<std::int64_t>(columns.size()) ||
      !std::is_sorted(row_ptr.begin(), row_ptr.end()) ||
      columns.size() != values.size()) {
    throw std::runtime_error("fixture_csr_invalid");
  }
  for (std::int64_t row = 0; row < dimension; ++row) {
    const auto start = row_ptr[static_cast<std::size_t>(row)];
    const auto stop = row_ptr[static_cast<std::size_t>(row + 1)];
    if (stop <= start) {
      throw std::runtime_error("fixture_empty_row");
    }
    std::int64_t previous = -1;
    for (auto position = start; position < stop; ++position) {
      const auto column = columns[static_cast<std::size_t>(position)];
      const auto value = values[static_cast<std::size_t>(position)];
      if (column < 0 || column >= dimension || column <= previous ||
          !std::isfinite(value)) {
        throw std::runtime_error("fixture_triangular_entry_invalid");
      }
      previous = column;
    }
    if (lower) {
      if (columns[static_cast<std::size_t>(stop - 1)] != row ||
          values[static_cast<std::size_t>(stop - 1)] != 1.0) {
        throw std::runtime_error("fixture_lower_diagonal_invalid");
      }
    } else if (columns[static_cast<std::size_t>(start)] != row ||
               values[static_cast<std::size_t>(start)] == 0.0) {
      throw std::runtime_error("fixture_upper_diagonal_invalid");
    }
  }
}

void validate_schedule(const std::vector<std::int64_t>& row_ptr,
                       const std::vector<std::int64_t>& columns,
                       const std::vector<std::int64_t>& level_ptr,
                       const std::vector<std::int64_t>& level_rows,
                       std::int64_t dimension, bool lower) {
  if (level_ptr.front() != 0 || level_ptr.back() != dimension ||
      level_rows.size() != static_cast<std::size_t>(dimension)) {
    throw std::runtime_error("fixture_level_schedule_invalid");
  }
  for (std::size_t index = 1; index < level_ptr.size(); ++index) {
    if (level_ptr[index] <= level_ptr[index - 1]) {
      throw std::runtime_error("fixture_level_pointer_invalid");
    }
  }
  validate_permutation(level_rows, dimension, "fixture_level_rows");
  std::vector<std::int64_t> row_level(static_cast<std::size_t>(dimension), -1);
  for (std::size_t level = 0; level + 1 < level_ptr.size(); ++level) {
    const auto start = level_ptr[level];
    const auto stop = level_ptr[level + 1];
    std::int64_t previous = -1;
    for (auto offset = start; offset < stop; ++offset) {
      const auto row = level_rows[static_cast<std::size_t>(offset)];
      if (row <= previous) {
        throw std::runtime_error("fixture_level_row_order_invalid");
      }
      row_level[static_cast<std::size_t>(row)] = static_cast<std::int64_t>(level);
      previous = row;
    }
  }
  for (std::int64_t row = 0; row < dimension; ++row) {
    auto start = row_ptr[static_cast<std::size_t>(row)];
    auto stop = row_ptr[static_cast<std::size_t>(row + 1)];
    if (lower) {
      --stop;
    } else {
      ++start;
    }
    for (auto position = start; position < stop; ++position) {
      const auto dependency = columns[static_cast<std::size_t>(position)];
      if (row_level[static_cast<std::size_t>(dependency)] >=
          row_level[static_cast<std::size_t>(row)]) {
        throw std::runtime_error("fixture_level_dependency_invalid");
      }
    }
  }
}

__global__ void permute_rhs_kernel(std::int64_t dimension,
                                   const std::int64_t* row_permutation,
                                   const double* right_hand_side_kn,
                                   double* permuted_right_hand_side_n) {
  const auto index = static_cast<std::int64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index < dimension) {
    permuted_right_hand_side_n[row_permutation[index]] =
        right_hand_side_kn[index] * 1000.0;
  }
}

__global__ void lower_level_kernel(const std::int64_t* row_ptr,
                                   const std::int64_t* columns,
                                   const double* values,
                                   const std::int64_t* level_rows,
                                   std::int64_t level_start,
                                   std::int64_t level_size,
                                   const double* right_hand_side,
                                   double* solution) {
  const auto offset = static_cast<std::int64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (offset >= level_size) {
    return;
  }
  const auto row = level_rows[level_start + offset];
  const auto start = row_ptr[row];
  const auto stop = row_ptr[row + 1];
  double tail = 0.0;
  for (auto position = start; position < stop - 1; ++position) {
    const double product = values[position] * solution[columns[position]];
    tail = tail + product;
  }
  solution[row] = right_hand_side[row] - tail;
}

__global__ void upper_level_kernel(const std::int64_t* row_ptr,
                                   const std::int64_t* columns,
                                   const double* values,
                                   const std::int64_t* level_rows,
                                   std::int64_t level_start,
                                   std::int64_t level_size,
                                   const double* right_hand_side,
                                   double* solution) {
  const auto offset = static_cast<std::int64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (offset >= level_size) {
    return;
  }
  const auto row = level_rows[level_start + offset];
  const auto start = row_ptr[row];
  const auto stop = row_ptr[row + 1];
  double tail = 0.0;
  for (auto position = start + 1; position < stop; ++position) {
    const double product = values[position] * solution[columns[position]];
    tail = tail + product;
  }
  solution[row] = (right_hand_side[row] - tail) / values[start];
}

__global__ void column_permutation_kernel(std::int64_t dimension,
                                          const std::int64_t* column_permutation,
                                          const double* upper_solution,
                                          double* output) {
  const auto index = static_cast<std::int64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index < dimension) {
    output[index] = upper_solution[column_permutation[index]];
  }
}

std::string json_escape(const std::string& value) {
  std::string result;
  for (const char character : value) {
    if (character == '\\' || character == '"') {
      result.push_back('\\');
    }
    result.push_back(character);
  }
  return result;
}

void print_solution(const std::vector<double>& values) {
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
    bool validate_fixture_only = false;
    const char* fixture_path = nullptr;
    if (argc == 2) {
      fixture_path = argv[1];
    } else if (argc == 3 &&
               std::string(argv[1]) == "--validate-fixture-only") {
      validate_fixture_only = true;
      fixture_path = argv[2];
    } else {
      throw std::runtime_error(
          "usage:engine_v2_sparse_lu_apply [--validate-fixture-only] "
          "fixture.bin");
    }
    std::ifstream input(fixture_path, std::ios::binary);
    if (!input) {
      throw std::runtime_error("fixture_open_failed");
    }
    std::array<char, 8> magic{};
    input.read(magic.data(), static_cast<std::streamsize>(magic.size()));
    if (!input || magic != kMagic) {
      throw std::runtime_error("fixture_magic_invalid");
    }
    std::uint64_t dimension_unsigned = 0;
    std::uint64_t lower_nnz_unsigned = 0;
    std::uint64_t upper_nnz_unsigned = 0;
    std::uint64_t lower_levels_unsigned = 0;
    std::uint64_t upper_levels_unsigned = 0;
    read_scalar(input, dimension_unsigned);
    read_scalar(input, lower_nnz_unsigned);
    read_scalar(input, upper_nnz_unsigned);
    read_scalar(input, lower_levels_unsigned);
    read_scalar(input, upper_levels_unsigned);
    if (dimension_unsigned == 0 || dimension_unsigned > 1000000 ||
        lower_nnz_unsigned < dimension_unsigned ||
        upper_nnz_unsigned < dimension_unsigned ||
        lower_nnz_unsigned > 200000000 || upper_nnz_unsigned > 200000000 ||
        lower_levels_unsigned == 0 || lower_levels_unsigned > dimension_unsigned ||
        upper_levels_unsigned == 0 || upper_levels_unsigned > dimension_unsigned) {
      throw std::runtime_error("fixture_dimensions_invalid");
    }
    const auto dimension = static_cast<std::int64_t>(dimension_unsigned);
    const auto lower_nnz = static_cast<std::int64_t>(lower_nnz_unsigned);
    const auto upper_nnz = static_cast<std::int64_t>(upper_nnz_unsigned);
    const auto lower_levels = static_cast<std::int64_t>(lower_levels_unsigned);
    const auto upper_levels = static_cast<std::int64_t>(upper_levels_unsigned);

    std::vector<std::int64_t> lower_row_ptr(static_cast<std::size_t>(dimension + 1));
    std::vector<std::int64_t> lower_columns(static_cast<std::size_t>(lower_nnz));
    std::vector<double> lower_values(static_cast<std::size_t>(lower_nnz));
    std::vector<std::int64_t> upper_row_ptr(static_cast<std::size_t>(dimension + 1));
    std::vector<std::int64_t> upper_columns(static_cast<std::size_t>(upper_nnz));
    std::vector<double> upper_values(static_cast<std::size_t>(upper_nnz));
    std::vector<std::int64_t> row_permutation(static_cast<std::size_t>(dimension));
    std::vector<std::int64_t> column_permutation(static_cast<std::size_t>(dimension));
    std::vector<std::int64_t> lower_level_ptr(static_cast<std::size_t>(lower_levels + 1));
    std::vector<std::int64_t> lower_level_rows(static_cast<std::size_t>(dimension));
    std::vector<std::int64_t> upper_level_ptr(static_cast<std::size_t>(upper_levels + 1));
    std::vector<std::int64_t> upper_level_rows(static_cast<std::size_t>(dimension));
    std::vector<double> right_hand_side_kn(static_cast<std::size_t>(dimension));
    read_vector(input, lower_row_ptr);
    read_vector(input, lower_columns);
    read_vector(input, lower_values);
    read_vector(input, upper_row_ptr);
    read_vector(input, upper_columns);
    read_vector(input, upper_values);
    read_vector(input, row_permutation);
    read_vector(input, column_permutation);
    read_vector(input, lower_level_ptr);
    read_vector(input, lower_level_rows);
    read_vector(input, upper_level_ptr);
    read_vector(input, upper_level_rows);
    read_vector(input, right_hand_side_kn);
    if (input.peek() != std::ifstream::traits_type::eof() ||
        !std::all_of(right_hand_side_kn.begin(), right_hand_side_kn.end(),
                     [](double value) { return std::isfinite(value); })) {
      throw std::runtime_error("fixture_payload_invalid");
    }
    validate_triangular(lower_row_ptr, lower_columns, lower_values, dimension, true);
    validate_triangular(upper_row_ptr, upper_columns, upper_values, dimension, false);
    validate_permutation(row_permutation, dimension, "fixture_row_permutation");
    validate_permutation(column_permutation, dimension,
                         "fixture_column_permutation");
    validate_schedule(lower_row_ptr, lower_columns, lower_level_ptr,
                      lower_level_rows, dimension, true);
    validate_schedule(upper_row_ptr, upper_columns, upper_level_ptr,
                      upper_level_rows, dimension, false);

    const auto fixture_byte_length =
        static_cast<std::uint64_t>(48) +
        static_cast<std::uint64_t>(lower_row_ptr.size() * sizeof(std::int64_t)) +
        static_cast<std::uint64_t>(lower_columns.size() * sizeof(std::int64_t)) +
        static_cast<std::uint64_t>(lower_values.size() * sizeof(double)) +
        static_cast<std::uint64_t>(upper_row_ptr.size() * sizeof(std::int64_t)) +
        static_cast<std::uint64_t>(upper_columns.size() * sizeof(std::int64_t)) +
        static_cast<std::uint64_t>(upper_values.size() * sizeof(double)) +
        static_cast<std::uint64_t>(row_permutation.size() * sizeof(std::int64_t)) +
        static_cast<std::uint64_t>(column_permutation.size() * sizeof(std::int64_t)) +
        static_cast<std::uint64_t>(lower_level_ptr.size() * sizeof(std::int64_t)) +
        static_cast<std::uint64_t>(lower_level_rows.size() * sizeof(std::int64_t)) +
        static_cast<std::uint64_t>(upper_level_ptr.size() * sizeof(std::int64_t)) +
        static_cast<std::uint64_t>(upper_level_rows.size() * sizeof(std::int64_t)) +
        static_cast<std::uint64_t>(right_hand_side_kn.size() * sizeof(double));
    if (validate_fixture_only) {
      std::cout << "{\"schema_version\":\""
                << kFixtureValidationOutputVersion
                << "\",\"status\":\"ok\""
                << ",\"mode\":\"host_fixture_validation_only\""
                << ",\"actual_hardware\":false"
                << ",\"hip_runtime_api_call_count\":0"
                << ",\"dimension\":" << dimension
                << ",\"lower_nnz\":" << lower_nnz
                << ",\"upper_nnz\":" << upper_nnz
                << ",\"lower_level_count\":" << lower_levels
                << ",\"upper_level_count\":" << upper_levels
                << ",\"expected_kernel_invocation_count\":"
                << lower_levels + upper_levels + 2
                << ",\"fixture_byte_length\":" << fixture_byte_length
                << "}\n";
      return 0;
    }

    int device_index = 0;
    check_hip(hipGetDevice(&device_index), "hipGetDevice");
    hipDeviceProp_t properties{};
    check_hip(hipGetDeviceProperties(&properties, device_index),
              "hipGetDeviceProperties");
    hipStream_t stream = nullptr;
    check_hip(hipStreamCreate(&stream), "hipStreamCreate");

    auto* d_lower_row_ptr = allocate_and_copy(lower_row_ptr, stream);
    auto* d_lower_columns = allocate_and_copy(lower_columns, stream);
    auto* d_lower_values = allocate_and_copy(lower_values, stream);
    auto* d_upper_row_ptr = allocate_and_copy(upper_row_ptr, stream);
    auto* d_upper_columns = allocate_and_copy(upper_columns, stream);
    auto* d_upper_values = allocate_and_copy(upper_values, stream);
    auto* d_row_permutation = allocate_and_copy(row_permutation, stream);
    auto* d_column_permutation = allocate_and_copy(column_permutation, stream);
    auto* d_lower_level_rows = allocate_and_copy(lower_level_rows, stream);
    auto* d_upper_level_rows = allocate_and_copy(upper_level_rows, stream);
    auto* d_right_hand_side_kn = allocate_and_copy(right_hand_side_kn, stream);
    double* d_permuted_rhs_n = nullptr;
    double* d_lower_solution = nullptr;
    double* d_upper_solution = nullptr;
    double* d_output = nullptr;
    const auto vector_bytes = static_cast<std::size_t>(dimension) * sizeof(double);
    check_hip(hipMalloc(&d_permuted_rhs_n, vector_bytes), "hipMalloc_permuted_rhs");
    check_hip(hipMalloc(&d_lower_solution, vector_bytes), "hipMalloc_lower_solution");
    check_hip(hipMalloc(&d_upper_solution, vector_bytes), "hipMalloc_upper_solution");
    check_hip(hipMalloc(&d_output, vector_bytes), "hipMalloc_output");
    check_hip(hipMemsetAsync(d_lower_solution, 0, vector_bytes, stream),
              "hipMemsetAsync_lower");
    check_hip(hipMemsetAsync(d_upper_solution, 0, vector_bytes, stream),
              "hipMemsetAsync_upper");

    constexpr int block_size = 128;
    const int vector_grid = static_cast<int>((dimension + block_size - 1) / block_size);
    hipLaunchKernelGGL(permute_rhs_kernel, dim3(vector_grid), dim3(block_size), 0,
                       stream, dimension, d_row_permutation, d_right_hand_side_kn,
                       d_permuted_rhs_n);
    check_hip(hipGetLastError(), "permute_rhs_kernel");
    std::int64_t kernel_invocations = 1;
    for (std::int64_t level = 0; level < lower_levels; ++level) {
      const auto start = lower_level_ptr[static_cast<std::size_t>(level)];
      const auto size = lower_level_ptr[static_cast<std::size_t>(level + 1)] - start;
      const int grid = static_cast<int>((size + block_size - 1) / block_size);
      hipLaunchKernelGGL(lower_level_kernel, dim3(grid), dim3(block_size), 0, stream,
                         d_lower_row_ptr, d_lower_columns, d_lower_values,
                         d_lower_level_rows, start, size, d_permuted_rhs_n,
                         d_lower_solution);
      check_hip(hipGetLastError(), "lower_level_kernel");
      ++kernel_invocations;
    }
    for (std::int64_t level = 0; level < upper_levels; ++level) {
      const auto start = upper_level_ptr[static_cast<std::size_t>(level)];
      const auto size = upper_level_ptr[static_cast<std::size_t>(level + 1)] - start;
      const int grid = static_cast<int>((size + block_size - 1) / block_size);
      hipLaunchKernelGGL(upper_level_kernel, dim3(grid), dim3(block_size), 0, stream,
                         d_upper_row_ptr, d_upper_columns, d_upper_values,
                         d_upper_level_rows, start, size, d_lower_solution,
                         d_upper_solution);
      check_hip(hipGetLastError(), "upper_level_kernel");
      ++kernel_invocations;
    }
    hipLaunchKernelGGL(column_permutation_kernel, dim3(vector_grid),
                       dim3(block_size), 0, stream, dimension,
                       d_column_permutation, d_upper_solution, d_output);
    check_hip(hipGetLastError(), "column_permutation_kernel");
    ++kernel_invocations;

    std::vector<double> output(static_cast<std::size_t>(dimension));
    check_hip(hipMemcpyAsync(output.data(), d_output, vector_bytes,
                             hipMemcpyDeviceToHost, stream),
              "hipMemcpyAsync_d2h");
    check_hip(hipStreamSynchronize(stream), "hipStreamSynchronize");

    std::cout << std::setprecision(17);
    std::cout << "{\"schema_version\":\"" << kOutputVersion
              << "\",\"status\":\"ok\",\"cpu_backend\":false"
              << ",\"device_name\":\"" << json_escape(properties.name)
              << "\",\"gcn_arch_name\":\""
              << json_escape(properties.gcnArchName)
              << "\",\"execution_profile\":\"" << kExecutionProfile
              << "\",\"accumulation_profile\":\"" << kAccumulationProfile
              << "\",\"dimension\":" << dimension
              << ",\"lower_level_count\":" << lower_levels
              << ",\"upper_level_count\":" << upper_levels
              << ",\"kernel_invocation_count\":" << kernel_invocations
              << ",\"mid_apply_d2h_transfer_count\":0"
              << ",\"blocking_d2h_synchronization_count\":1"
              << ",\"solution_m\":";
    print_solution(output);
    std::cout << "}\n";

    check_hip(hipFree(d_lower_row_ptr), "hipFree_lower_row_ptr");
    check_hip(hipFree(d_lower_columns), "hipFree_lower_columns");
    check_hip(hipFree(d_lower_values), "hipFree_lower_values");
    check_hip(hipFree(d_upper_row_ptr), "hipFree_upper_row_ptr");
    check_hip(hipFree(d_upper_columns), "hipFree_upper_columns");
    check_hip(hipFree(d_upper_values), "hipFree_upper_values");
    check_hip(hipFree(d_row_permutation), "hipFree_row_permutation");
    check_hip(hipFree(d_column_permutation), "hipFree_column_permutation");
    check_hip(hipFree(d_lower_level_rows), "hipFree_lower_level_rows");
    check_hip(hipFree(d_upper_level_rows), "hipFree_upper_level_rows");
    check_hip(hipFree(d_right_hand_side_kn), "hipFree_right_hand_side");
    check_hip(hipFree(d_permuted_rhs_n), "hipFree_permuted_rhs");
    check_hip(hipFree(d_lower_solution), "hipFree_lower_solution");
    check_hip(hipFree(d_upper_solution), "hipFree_upper_solution");
    check_hip(hipFree(d_output), "hipFree_output");
    check_hip(hipStreamDestroy(stream), "hipStreamDestroy");
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
