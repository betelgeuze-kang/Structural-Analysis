#include <hip/hip_runtime.h>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

// Reuse the source-of-record parsers, validation functions, and kernels while
// keeping their standalone entry points available under component namespaces.
namespace sparse_component {
#define main engine_v2_sparse_lu_component_main
#include "engine_v2_sparse_lu_apply.hip.cpp"
#undef main
}  // namespace sparse_component

namespace tangent_component {
#define main engine_v2_current_tangent_component_main
#include "engine_v2_current_tangent_operator.hip.cpp"
#undef main
}  // namespace tangent_component

namespace {

constexpr std::array<char, 8> kSparseMagic = {'E', 'V', '2', 'S', 'L', 'U', '0', '1'};
constexpr const char* kOutputVersion = "engine-v2-mgt-preconditioned-jvp-output.v1";
constexpr int kSparseBlockSize = 128;
constexpr int kTangentBlockSize = 256;

void check_hip(hipError_t status, const char* where) {
  if (status != hipSuccess) {
    throw std::runtime_error(std::string(where) + ":" + hipGetErrorString(status));
  }
}

template <typename T>
void read_scalar(std::ifstream& input, T& value) {
  input.read(reinterpret_cast<char*>(&value), static_cast<std::streamsize>(sizeof(T)));
  if (!input) {
    throw std::runtime_error("sparse_fixture_truncated");
  }
}

template <typename T>
void read_vector(std::ifstream& input, std::vector<T>& values) {
  input.read(reinterpret_cast<char*>(values.data()),
             static_cast<std::streamsize>(values.size() * sizeof(T)));
  if (!input) {
    throw std::runtime_error("sparse_fixture_truncated");
  }
}

struct SparseFixture {
  std::int64_t dimension{};
  std::int64_t lower_nnz{};
  std::int64_t upper_nnz{};
  std::int64_t lower_levels{};
  std::int64_t upper_levels{};
  std::uint64_t fixture_byte_length{};
  std::vector<std::int64_t> lower_row_ptr;
  std::vector<std::int64_t> lower_columns;
  std::vector<double> lower_values;
  std::vector<std::int64_t> upper_row_ptr;
  std::vector<std::int64_t> upper_columns;
  std::vector<double> upper_values;
  std::vector<std::int64_t> row_permutation;
  std::vector<std::int64_t> column_permutation;
  std::vector<std::int64_t> lower_level_ptr;
  std::vector<std::int64_t> lower_level_rows;
  std::vector<std::int64_t> upper_level_ptr;
  std::vector<std::int64_t> upper_level_rows;
  std::vector<double> right_hand_side_kn;
};

SparseFixture read_sparse_fixture(const char* path) {
  std::ifstream input(path, std::ios::binary | std::ios::ate);
  if (!input) {
    throw std::runtime_error("sparse_fixture_open_failed");
  }
  const auto file_end = input.tellg();
  if (file_end < 0) {
    throw std::runtime_error("sparse_fixture_size_invalid");
  }
  input.seekg(0, std::ios::beg);
  std::array<char, 8> magic{};
  input.read(magic.data(), static_cast<std::streamsize>(magic.size()));
  if (!input || magic != kSparseMagic) {
    throw std::runtime_error("sparse_fixture_magic_invalid");
  }
  std::uint64_t dimension = 0;
  std::uint64_t lower_nnz = 0;
  std::uint64_t upper_nnz = 0;
  std::uint64_t lower_levels = 0;
  std::uint64_t upper_levels = 0;
  read_scalar(input, dimension);
  read_scalar(input, lower_nnz);
  read_scalar(input, upper_nnz);
  read_scalar(input, lower_levels);
  read_scalar(input, upper_levels);
  if (dimension == 0 || dimension > 1000000 || lower_nnz < dimension ||
      upper_nnz < dimension || lower_nnz > 200000000 ||
      upper_nnz > 200000000 || lower_levels == 0 ||
      lower_levels > dimension || upper_levels == 0 || upper_levels > dimension) {
    throw std::runtime_error("sparse_fixture_dimensions_invalid");
  }
  SparseFixture fixture;
  fixture.dimension = static_cast<std::int64_t>(dimension);
  fixture.lower_nnz = static_cast<std::int64_t>(lower_nnz);
  fixture.upper_nnz = static_cast<std::int64_t>(upper_nnz);
  fixture.lower_levels = static_cast<std::int64_t>(lower_levels);
  fixture.upper_levels = static_cast<std::int64_t>(upper_levels);
  fixture.fixture_byte_length = static_cast<std::uint64_t>(file_end);
  fixture.lower_row_ptr.resize(static_cast<std::size_t>(dimension + 1));
  fixture.lower_columns.resize(static_cast<std::size_t>(lower_nnz));
  fixture.lower_values.resize(static_cast<std::size_t>(lower_nnz));
  fixture.upper_row_ptr.resize(static_cast<std::size_t>(dimension + 1));
  fixture.upper_columns.resize(static_cast<std::size_t>(upper_nnz));
  fixture.upper_values.resize(static_cast<std::size_t>(upper_nnz));
  fixture.row_permutation.resize(static_cast<std::size_t>(dimension));
  fixture.column_permutation.resize(static_cast<std::size_t>(dimension));
  fixture.lower_level_ptr.resize(static_cast<std::size_t>(lower_levels + 1));
  fixture.lower_level_rows.resize(static_cast<std::size_t>(dimension));
  fixture.upper_level_ptr.resize(static_cast<std::size_t>(upper_levels + 1));
  fixture.upper_level_rows.resize(static_cast<std::size_t>(dimension));
  fixture.right_hand_side_kn.resize(static_cast<std::size_t>(dimension));
  read_vector(input, fixture.lower_row_ptr);
  read_vector(input, fixture.lower_columns);
  read_vector(input, fixture.lower_values);
  read_vector(input, fixture.upper_row_ptr);
  read_vector(input, fixture.upper_columns);
  read_vector(input, fixture.upper_values);
  read_vector(input, fixture.row_permutation);
  read_vector(input, fixture.column_permutation);
  read_vector(input, fixture.lower_level_ptr);
  read_vector(input, fixture.lower_level_rows);
  read_vector(input, fixture.upper_level_ptr);
  read_vector(input, fixture.upper_level_rows);
  read_vector(input, fixture.right_hand_side_kn);
  if (input.peek() != std::ifstream::traits_type::eof() ||
      !std::all_of(fixture.right_hand_side_kn.begin(),
                   fixture.right_hand_side_kn.end(),
                   [](double value) { return std::isfinite(value); })) {
    throw std::runtime_error("sparse_fixture_payload_invalid");
  }
  sparse_component::validate_triangular(
      fixture.lower_row_ptr, fixture.lower_columns, fixture.lower_values,
      fixture.dimension, true);
  sparse_component::validate_triangular(
      fixture.upper_row_ptr, fixture.upper_columns, fixture.upper_values,
      fixture.dimension, false);
  sparse_component::validate_permutation(
      fixture.row_permutation, fixture.dimension, "sparse_row_permutation");
  sparse_component::validate_permutation(
      fixture.column_permutation, fixture.dimension, "sparse_column_permutation");
  sparse_component::validate_schedule(
      fixture.lower_row_ptr, fixture.lower_columns, fixture.lower_level_ptr,
      fixture.lower_level_rows, fixture.dimension, true);
  sparse_component::validate_schedule(
      fixture.upper_row_ptr, fixture.upper_columns, fixture.upper_level_ptr,
      fixture.upper_level_rows, fixture.dimension, false);
  return fixture;
}

template <typename T>
T* allocate_and_copy(const std::vector<T>& host, hipStream_t stream,
                     std::uint64_t* h2d_bytes,
                     std::uint64_t* allocated_bytes) {
  if (host.empty()) {
    return nullptr;
  }
  T* device = nullptr;
  const auto bytes = host.size() * sizeof(T);
  check_hip(hipMalloc(reinterpret_cast<void**>(&device), bytes), "hipMalloc");
  check_hip(hipMemcpyAsync(device, host.data(), bytes, hipMemcpyHostToDevice, stream),
            "hipMemcpyAsync_h2d");
  *h2d_bytes += static_cast<std::uint64_t>(bytes);
  *allocated_bytes += static_cast<std::uint64_t>(bytes);
  return device;
}

double* allocate_vector(std::int64_t dimension, std::uint64_t* allocated_bytes) {
  double* result = nullptr;
  const auto bytes = static_cast<std::size_t>(dimension) * sizeof(double);
  check_hip(hipMalloc(reinterpret_cast<void**>(&result), bytes), "hipMalloc_vector");
  *allocated_bytes += static_cast<std::uint64_t>(bytes);
  return result;
}

void free_device(void* pointer) {
  if (pointer != nullptr) {
    check_hip(hipFree(pointer), "hipFree");
  }
}

void print_vector(const std::vector<double>& values) {
  std::cout << '[';
  for (std::size_t index = 0; index < values.size(); ++index) {
    if (index != 0U) std::cout << ',';
    std::cout << values[index];
  }
  std::cout << ']';
}

}  // namespace

#ifndef ENGINE_V2_MGT_PRECONDITIONED_JVP_NO_MAIN
int main(int argc, char** argv) {
  try {
    if (argc != 3) {
      throw std::runtime_error(
          "usage:engine_v2_mgt_preconditioned_jvp sparse_lu_fixture.bin "
          "current_tangent_fixture.bin");
    }
    const SparseFixture sparse = read_sparse_fixture(argv[1]);
    const tangent_component::Fixture tangent = tangent_component::read_fixture(argv[2]);
    if (sparse.dimension != static_cast<std::int64_t>(tangent.equation_count) ||
        tangent.load_factor != 1.0) {
      throw std::runtime_error("composite_fixture_binding_invalid");
    }
    int device_index = 0;
    check_hip(hipGetDevice(&device_index), "hipGetDevice");
    hipDeviceProp_t properties{};
    check_hip(hipGetDeviceProperties(&properties, device_index),
              "hipGetDeviceProperties");
    hipStream_t stream = nullptr;
    check_hip(hipStreamCreate(&stream), "hipStreamCreate");
    const auto lifecycle_started = std::chrono::steady_clock::now();
    std::uint64_t h2d_bytes = 0;
    std::uint64_t allocated_bytes = 0;

    auto* d_lower_row_ptr = allocate_and_copy(sparse.lower_row_ptr, stream, &h2d_bytes, &allocated_bytes);
    auto* d_lower_columns = allocate_and_copy(sparse.lower_columns, stream, &h2d_bytes, &allocated_bytes);
    auto* d_lower_values = allocate_and_copy(sparse.lower_values, stream, &h2d_bytes, &allocated_bytes);
    auto* d_upper_row_ptr = allocate_and_copy(sparse.upper_row_ptr, stream, &h2d_bytes, &allocated_bytes);
    auto* d_upper_columns = allocate_and_copy(sparse.upper_columns, stream, &h2d_bytes, &allocated_bytes);
    auto* d_upper_values = allocate_and_copy(sparse.upper_values, stream, &h2d_bytes, &allocated_bytes);
    auto* d_row_permutation = allocate_and_copy(sparse.row_permutation, stream, &h2d_bytes, &allocated_bytes);
    auto* d_column_permutation = allocate_and_copy(sparse.column_permutation, stream, &h2d_bytes, &allocated_bytes);
    auto* d_lower_level_rows = allocate_and_copy(sparse.lower_level_rows, stream, &h2d_bytes, &allocated_bytes);
    auto* d_upper_level_rows = allocate_and_copy(sparse.upper_level_rows, stream, &h2d_bytes, &allocated_bytes);
    auto* d_rhs_kn = allocate_and_copy(sparse.right_hand_side_kn, stream, &h2d_bytes, &allocated_bytes);
    double* d_permuted_rhs_n = allocate_vector(sparse.dimension, &allocated_bytes);
    double* d_lower_solution = allocate_vector(sparse.dimension, &allocated_bytes);
    double* d_upper_solution = allocate_vector(sparse.dimension, &allocated_bytes);
    double* d_preconditioned_direction = allocate_vector(sparse.dimension, &allocated_bytes);

    tangent_component::DeviceFixture device_tangent{
        static_cast<std::int64_t>(tangent.equation_count), tangent.load_factor,
        allocate_and_copy(tangent.reference_row_pointer, stream, &h2d_bytes, &allocated_bytes),
        allocate_and_copy(tangent.reference_column_indices, stream, &h2d_bytes, &allocated_bytes),
        allocate_and_copy(tangent.reference_values, stream, &h2d_bytes, &allocated_bytes),
        allocate_and_copy(tangent.background_displacements, stream, &h2d_bytes, &allocated_bytes),
        allocate_and_copy(tangent.frame_dofs, stream, &h2d_bytes, &allocated_bytes),
        allocate_and_copy(tangent.frame_delta, stream, &h2d_bytes, &allocated_bytes),
        allocate_and_copy(tangent.geometry_dofs, stream, &h2d_bytes, &allocated_bytes),
        allocate_and_copy(tangent.geometry_relative, stream, &h2d_bytes, &allocated_bytes),
        allocate_and_copy(tangent.geometry_reference_chords, stream, &h2d_bytes, &allocated_bytes),
        allocate_and_copy(tangent.geometry_reference_lengths, stream, &h2d_bytes, &allocated_bytes),
        allocate_and_copy(tangent.geometry_axial_stiffness, stream, &h2d_bytes, &allocated_bytes),
        allocate_and_copy(tangent.global_to_free, stream, &h2d_bytes, &allocated_bytes),
        allocate_and_copy(tangent.frame_incidence_pointer, stream, &h2d_bytes, &allocated_bytes),
        allocate_and_copy(tangent.frame_incidence_element, stream, &h2d_bytes, &allocated_bytes),
        allocate_and_copy(tangent.frame_incidence_local_dof, stream, &h2d_bytes, &allocated_bytes),
        allocate_and_copy(tangent.geometry_incidence_pointer, stream, &h2d_bytes, &allocated_bytes),
        allocate_and_copy(tangent.geometry_incidence_element, stream, &h2d_bytes, &allocated_bytes),
        allocate_and_copy(tangent.geometry_incidence_local_dof, stream, &h2d_bytes, &allocated_bytes),
        allocate_and_copy(tangent.free_displacements, stream, &h2d_bytes, &allocated_bytes),
        d_preconditioned_direction};
    double* d_action = allocate_vector(sparse.dimension, &allocated_bytes);
    const auto vector_bytes = static_cast<std::size_t>(sparse.dimension) * sizeof(double);
    check_hip(hipMemsetAsync(d_lower_solution, 0, vector_bytes, stream), "hipMemsetAsync_lower");
    check_hip(hipMemsetAsync(d_upper_solution, 0, vector_bytes, stream), "hipMemsetAsync_upper");

    const int sparse_grid = static_cast<int>((sparse.dimension + kSparseBlockSize - 1) / kSparseBlockSize);
    hipLaunchKernelGGL(sparse_component::permute_rhs_kernel, dim3(sparse_grid),
                       dim3(kSparseBlockSize), 0, stream, sparse.dimension,
                       d_row_permutation, d_rhs_kn, d_permuted_rhs_n);
    check_hip(hipGetLastError(), "permute_rhs_kernel");
    std::int64_t sparse_kernel_count = 1;
    for (std::int64_t level = 0; level < sparse.lower_levels; ++level) {
      const auto start = sparse.lower_level_ptr[static_cast<std::size_t>(level)];
      const auto size = sparse.lower_level_ptr[static_cast<std::size_t>(level + 1)] - start;
      const int grid = static_cast<int>((size + kSparseBlockSize - 1) / kSparseBlockSize);
      hipLaunchKernelGGL(sparse_component::lower_level_kernel, dim3(grid),
                         dim3(kSparseBlockSize), 0, stream, d_lower_row_ptr,
                         d_lower_columns, d_lower_values, d_lower_level_rows,
                         start, size, d_permuted_rhs_n, d_lower_solution);
      check_hip(hipGetLastError(), "lower_level_kernel");
      ++sparse_kernel_count;
    }
    for (std::int64_t level = 0; level < sparse.upper_levels; ++level) {
      const auto start = sparse.upper_level_ptr[static_cast<std::size_t>(level)];
      const auto size = sparse.upper_level_ptr[static_cast<std::size_t>(level + 1)] - start;
      const int grid = static_cast<int>((size + kSparseBlockSize - 1) / kSparseBlockSize);
      hipLaunchKernelGGL(sparse_component::upper_level_kernel, dim3(grid),
                         dim3(kSparseBlockSize), 0, stream, d_upper_row_ptr,
                         d_upper_columns, d_upper_values, d_upper_level_rows,
                         start, size, d_lower_solution, d_upper_solution);
      check_hip(hipGetLastError(), "upper_level_kernel");
      ++sparse_kernel_count;
    }
    hipLaunchKernelGGL(sparse_component::column_permutation_kernel,
                       dim3(sparse_grid), dim3(kSparseBlockSize), 0, stream,
                       sparse.dimension, d_column_permutation, d_upper_solution,
                       d_preconditioned_direction);
    check_hip(hipGetLastError(), "column_permutation_kernel");
    ++sparse_kernel_count;

    const auto tangent_grid = static_cast<unsigned int>(
        (tangent.equation_count + static_cast<std::size_t>(kTangentBlockSize) - 1U) /
        static_cast<std::size_t>(kTangentBlockSize));
    hipLaunchKernelGGL(tangent_component::current_tangent_action_kernel,
                       dim3(tangent_grid), dim3(kTangentBlockSize), 0, stream,
                       device_tangent, d_action);
    check_hip(hipGetLastError(), "current_tangent_action_kernel");

    std::vector<double> preconditioned_direction(static_cast<std::size_t>(sparse.dimension));
    std::vector<double> action(static_cast<std::size_t>(sparse.dimension));
    check_hip(hipMemcpyAsync(preconditioned_direction.data(),
                             d_preconditioned_direction, vector_bytes,
                             hipMemcpyDeviceToHost, stream), "hipMemcpyAsync_direction_d2h");
    check_hip(hipMemcpyAsync(action.data(), d_action, vector_bytes,
                             hipMemcpyDeviceToHost, stream), "hipMemcpyAsync_action_d2h");
    check_hip(hipStreamSynchronize(stream), "hipStreamSynchronize");
    const auto lifecycle_finished = std::chrono::steady_clock::now();
    const double lifecycle_ms = std::chrono::duration<double, std::milli>(
        lifecycle_finished - lifecycle_started).count();

    std::cout << std::setprecision(17)
              << "{\"schema_version\":\"" << kOutputVersion
              << "\",\"status\":\"ok\",\"cpu_backend\":false,\"device_name\":\""
              << tangent_component::json_escape(properties.name)
              << "\",\"gcn_arch_name\":\""
              << tangent_component::json_escape(properties.gcnArchName)
              << "\",\"equation_count\":" << sparse.dimension
              << ",\"preconditioner_kernel_invocation_count\":" << sparse_kernel_count
              << ",\"current_tangent_kernel_invocation_count\":1"
              << ",\"total_kernel_invocation_count\":" << sparse_kernel_count + 1
              << ",\"preconditioner_apply_count\":1,\"matvec_count\":1"
              << ",\"persistent_factor_buffers\":true,\"persistent_operator_buffers\":true"
              << ",\"single_stream_composition\":true,\"mid_composition_d2h_transfer_count\":0"
              << ",\"final_d2h_transfer_count\":2,\"h2d_bytes\":" << h2d_bytes
              << ",\"d2h_bytes\":" << 2U * vector_bytes
              << ",\"tracked_peak_device_allocation_bytes\":" << allocated_bytes
              << ",\"device_lifecycle_wall_time_ms\":" << lifecycle_ms
              << ",\"preconditioned_direction_m\":";
    print_vector(preconditioned_direction);
    std::cout << ",\"jvp_action_n\":";
    print_vector(action);
    std::cout << "}\n";

    free_device(d_lower_row_ptr); free_device(d_lower_columns); free_device(d_lower_values);
    free_device(d_upper_row_ptr); free_device(d_upper_columns); free_device(d_upper_values);
    free_device(d_row_permutation); free_device(d_column_permutation);
    free_device(d_lower_level_rows); free_device(d_upper_level_rows); free_device(d_rhs_kn);
    free_device(d_permuted_rhs_n); free_device(d_lower_solution); free_device(d_upper_solution);
    free_device(d_preconditioned_direction); free_device(d_action);
    free_device(const_cast<std::int64_t*>(device_tangent.reference_row_pointer));
    free_device(const_cast<std::int64_t*>(device_tangent.reference_column_indices));
    free_device(const_cast<double*>(device_tangent.reference_values));
    free_device(const_cast<double*>(device_tangent.background_displacements));
    free_device(const_cast<std::int64_t*>(device_tangent.frame_dofs));
    free_device(const_cast<double*>(device_tangent.frame_delta));
    free_device(const_cast<std::int64_t*>(device_tangent.geometry_dofs));
    free_device(const_cast<double*>(device_tangent.geometry_relative));
    free_device(const_cast<double*>(device_tangent.geometry_reference_chords));
    free_device(const_cast<double*>(device_tangent.geometry_reference_lengths));
    free_device(const_cast<double*>(device_tangent.geometry_axial_stiffness));
    free_device(const_cast<std::int64_t*>(device_tangent.global_to_free));
    free_device(const_cast<std::int64_t*>(device_tangent.frame_incidence_pointer));
    free_device(const_cast<std::int64_t*>(device_tangent.frame_incidence_element));
    free_device(const_cast<std::int64_t*>(device_tangent.frame_incidence_local_dof));
    free_device(const_cast<std::int64_t*>(device_tangent.geometry_incidence_pointer));
    free_device(const_cast<std::int64_t*>(device_tangent.geometry_incidence_element));
    free_device(const_cast<std::int64_t*>(device_tangent.geometry_incidence_local_dof));
    free_device(const_cast<double*>(device_tangent.free_displacements));
    check_hip(hipStreamDestroy(stream), "hipStreamDestroy");
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
#endif
