#include <hip/hip_runtime.h>

#include <array>
#include <algorithm>
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

namespace composition {
#define ENGINE_V2_MGT_PRECONDITIONED_JVP_NO_MAIN
#include "engine_v2_mgt_preconditioned_jvp.hip.cpp"
#undef ENGINE_V2_MGT_PRECONDITIONED_JVP_NO_MAIN
}  // namespace composition

namespace {

constexpr int kBlockSize = 256;
constexpr int kRestart = 6;
constexpr const char* kOutputVersion = "engine-v2-mgt-fgmres-output.v1";

void check_hip(hipError_t status, const char* where) {
  if (status != hipSuccess) {
    throw std::runtime_error(std::string(where) + ":" + hipGetErrorString(status));
  }
}

__global__ void initialize_basis_kernel(std::int64_t n, const double* rhs_kn,
                                        double reference_force_n, double* basis,
                                        double* beta) {
  if (blockIdx.x == 0 && threadIdx.x == 0) {
    double sum = 0.0;
    for (std::int64_t i = 0; i < n; ++i) {
      const double value = rhs_kn[i] * 1000.0 / reference_force_n;
      basis[i] = value;
      sum += value * value;
    }
    beta[0] = sqrt(sum);
    for (std::int64_t i = 0; i < n; ++i) basis[i] /= beta[0];
  }
}

__global__ void preconditioner_rhs_kernel(std::int64_t n, const double* basis,
                                          double reference_force_n,
                                          double* rhs_kn) {
  const std::int64_t i = static_cast<std::int64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (i < n) rhs_kn[i] = basis[i] * reference_force_n / 1000.0;
}

__global__ void scale_action_kernel(std::int64_t n, double reference_force_n,
                                    double* action_n) {
  const std::int64_t i = static_cast<std::int64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (i < n) action_n[i] /= reference_force_n;
}

__global__ void dot_kernel(std::int64_t n, const double* left, const double* right,
                           double* scalar) {
  if (blockIdx.x == 0 && threadIdx.x == 0) {
    double sum = 0.0;
    for (std::int64_t i = 0; i < n; ++i) sum += left[i] * right[i];
    scalar[0] = sum;
  }
}

__global__ void h_accumulate_kernel(double* h, int row, int column,
                                    const double* scalar) {
  if (blockIdx.x == 0 && threadIdx.x == 0) h[column * (kRestart + 1) + row] += scalar[0];
}

__global__ void axpy_kernel(std::int64_t n, double* target, const double* basis,
                            const double* scalar) {
  const std::int64_t i = static_cast<std::int64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (i < n) target[i] -= scalar[0] * basis[i];
}

__global__ void norm_and_store_kernel(std::int64_t n, const double* vector,
                                      double* h, int row, int column,
                                      double* scalar) {
  if (blockIdx.x == 0 && threadIdx.x == 0) {
    double sum = 0.0;
    for (std::int64_t i = 0; i < n; ++i) sum += vector[i] * vector[i];
    scalar[0] = sqrt(sum);
    h[column * (kRestart + 1) + row] = scalar[0];
  }
}

__global__ void normalize_kernel(std::int64_t n, const double* input,
                                 const double* norm, double* output) {
  const std::int64_t i = static_cast<std::int64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (i < n) output[i] = input[i] / norm[0];
}

__global__ void givens_kernel(double* h, double* g, double* cosine,
                              double* sine, double* residual_history, int column) {
  if (blockIdx.x != 0 || threadIdx.x != 0) return;
  for (int i = 0; i < column; ++i) {
    double& upper = h[column * (kRestart + 1) + i];
    double& lower = h[column * (kRestart + 1) + i + 1];
    const double rotated_upper = cosine[i] * upper + sine[i] * lower;
    lower = -sine[i] * upper + cosine[i] * lower;
    upper = rotated_upper;
  }
  double& diagonal = h[column * (kRestart + 1) + column];
  double& subdiagonal = h[column * (kRestart + 1) + column + 1];
  const double magnitude = hypot(diagonal, subdiagonal);
  cosine[column] = diagonal / magnitude;
  sine[column] = subdiagonal / magnitude;
  diagonal = magnitude;
  subdiagonal = 0.0;
  const double next = -sine[column] * g[column];
  g[column] = cosine[column] * g[column];
  g[column + 1] = next;
  residual_history[column] = fabs(next);
}

__global__ void backsolve_kernel(const double* h, const double* g, double* y) {
  if (blockIdx.x != 0 || threadIdx.x != 0) return;
  for (int row = kRestart - 1; row >= 0; --row) {
    double value = g[row];
    for (int column = row + 1; column < kRestart; ++column) {
      value -= h[column * (kRestart + 1) + row] * y[column];
    }
    y[row] = value / h[row * (kRestart + 1) + row];
  }
}

__global__ void combine_solution_kernel(std::int64_t n, const double* z,
                                        const double* y, double* solution) {
  const std::int64_t i = static_cast<std::int64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (i < n) {
    double value = 0.0;
    for (int column = 0; column < kRestart; ++column) value += z[column * n + i] * y[column];
    solution[i] = value;
  }
}

__global__ void physical_residual_kernel(std::int64_t n, const double* rhs_kn,
                                         const double* action_n, double* residual_n) {
  const std::int64_t i = static_cast<std::int64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (i < n) residual_n[i] = rhs_kn[i] * 1000.0 - action_n[i];
}

__global__ void residual_metrics_kernel(std::int64_t n, const double* residual_n,
                                        double reference_force_n, double* metrics) {
  if (blockIdx.x != 0 || threadIdx.x != 0) return;
  double sum = 0.0;
  double maximum = 0.0;
  for (std::int64_t i = 0; i < n; ++i) {
    sum += residual_n[i] * residual_n[i];
    maximum = fmax(maximum, fabs(residual_n[i]));
  }
  metrics[0] = sqrt(sum);
  metrics[1] = maximum;
  metrics[2] = sqrt(sum) / reference_force_n;
  metrics[3] = maximum / reference_force_n;
}

template <typename T>
T* allocate(std::size_t count, std::uint64_t* bytes) {
  T* result = nullptr;
  check_hip(hipMalloc(reinterpret_cast<void**>(&result), count * sizeof(T)), "hipMalloc");
  *bytes += static_cast<std::uint64_t>(count * sizeof(T));
  return result;
}

void write_vector(const char* path, const std::vector<double>& values) {
  std::ofstream output(path, std::ios::binary | std::ios::trunc);
  output.write(reinterpret_cast<const char*>(values.data()),
               static_cast<std::streamsize>(values.size() * sizeof(double)));
  if (!output) throw std::runtime_error("output_write_failed");
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc != 6) throw std::runtime_error("usage:fgmres sparse.bin tangent.bin reference_force_n solution.bin residual.bin");
    const composition::SparseFixture sparse = composition::read_sparse_fixture(argv[1]);
    const composition::tangent_component::Fixture tangent = composition::tangent_component::read_fixture(argv[2]);
    const double reference_force_n = std::stod(argv[3]);
    if (sparse.dimension != static_cast<std::int64_t>(tangent.equation_count) ||
        tangent.load_factor != 1.0 || !(reference_force_n >= 1.0) || !std::isfinite(reference_force_n)) {
      throw std::runtime_error("fgmres_fixture_binding_invalid");
    }
    int device_index = 0;
    check_hip(hipGetDevice(&device_index), "hipGetDevice");
    hipDeviceProp_t properties{};
    check_hip(hipGetDeviceProperties(&properties, device_index), "hipGetDeviceProperties");
    hipStream_t stream = nullptr;
    check_hip(hipStreamCreate(&stream), "hipStreamCreate");
    const auto started = std::chrono::steady_clock::now();
    std::uint64_t h2d_bytes = 0;
    std::uint64_t allocated_bytes = 0;
    auto copy = [&](const auto& host) { return composition::allocate_and_copy(host, stream, &h2d_bytes, &allocated_bytes); };

    auto* d_lrp = copy(sparse.lower_row_ptr); auto* d_lci = copy(sparse.lower_columns); auto* d_lv = copy(sparse.lower_values);
    auto* d_urp = copy(sparse.upper_row_ptr); auto* d_uci = copy(sparse.upper_columns); auto* d_uv = copy(sparse.upper_values);
    auto* d_rp = copy(sparse.row_permutation); auto* d_cp = copy(sparse.column_permutation);
    auto* d_llr = copy(sparse.lower_level_rows); auto* d_ulr = copy(sparse.upper_level_rows);
    auto* d_original_rhs_kn = copy(sparse.right_hand_side_kn);
    double* d_rhs_kn = allocate<double>(sparse.dimension, &allocated_bytes);
    double* d_permuted = allocate<double>(sparse.dimension, &allocated_bytes);
    double* d_lower = allocate<double>(sparse.dimension, &allocated_bytes);
    double* d_upper = allocate<double>(sparse.dimension, &allocated_bytes);
    double* d_basis = allocate<double>((kRestart + 1) * sparse.dimension, &allocated_bytes);
    double* d_z = allocate<double>(kRestart * sparse.dimension, &allocated_bytes);
    double* d_work = allocate<double>(sparse.dimension, &allocated_bytes);
    double* d_solution = allocate<double>(sparse.dimension, &allocated_bytes);
    double* d_residual = allocate<double>(sparse.dimension, &allocated_bytes);
    double* d_h = allocate<double>((kRestart + 1) * kRestart, &allocated_bytes);
    double* d_g = allocate<double>(kRestart + 1, &allocated_bytes);
    double* d_c = allocate<double>(kRestart, &allocated_bytes);
    double* d_s = allocate<double>(kRestart, &allocated_bytes);
    double* d_y = allocate<double>(kRestart, &allocated_bytes);
    double* d_scalar = allocate<double>(1, &allocated_bytes);
    double* d_history = allocate<double>(kRestart, &allocated_bytes);
    double* d_metrics = allocate<double>(4, &allocated_bytes);

    composition::tangent_component::DeviceFixture dt{
      static_cast<std::int64_t>(tangent.equation_count), tangent.load_factor,
      copy(tangent.reference_row_pointer), copy(tangent.reference_column_indices), copy(tangent.reference_values),
      copy(tangent.background_displacements), copy(tangent.frame_dofs), copy(tangent.frame_delta),
      copy(tangent.geometry_dofs), copy(tangent.geometry_relative), copy(tangent.geometry_reference_chords),
      copy(tangent.geometry_reference_lengths), copy(tangent.geometry_axial_stiffness), copy(tangent.global_to_free),
      copy(tangent.frame_incidence_pointer), copy(tangent.frame_incidence_element), copy(tangent.frame_incidence_local_dof),
      copy(tangent.geometry_incidence_pointer), copy(tangent.geometry_incidence_element), copy(tangent.geometry_incidence_local_dof),
      copy(tangent.free_displacements), nullptr};

    const int grid = static_cast<int>((sparse.dimension + kBlockSize - 1) / kBlockSize);
    const int sparse_grid = static_cast<int>((sparse.dimension + 127) / 128);
    const std::size_t vector_bytes = static_cast<std::size_t>(sparse.dimension) * sizeof(double);
    check_hip(hipMemsetAsync(d_h, 0, (kRestart + 1) * kRestart * sizeof(double), stream), "memset_h");
    check_hip(hipMemsetAsync(d_g, 0, (kRestart + 1) * sizeof(double), stream), "memset_g");
    hipLaunchKernelGGL(initialize_basis_kernel, dim3(1), dim3(1), 0, stream, sparse.dimension,
                       d_original_rhs_kn, reference_force_n, d_basis, d_g);
    std::int64_t sparse_kernels = 0;
    std::int64_t vector_kernels = 1;
    for (int iteration = 0; iteration < kRestart; ++iteration) {
      const double* vj = d_basis + static_cast<std::int64_t>(iteration) * sparse.dimension;
      double* zj = d_z + static_cast<std::int64_t>(iteration) * sparse.dimension;
      hipLaunchKernelGGL(preconditioner_rhs_kernel, dim3(grid), dim3(kBlockSize), 0, stream,
                         sparse.dimension, vj, reference_force_n, d_rhs_kn);
      check_hip(hipMemsetAsync(d_lower, 0, vector_bytes, stream), "memset_lower");
      check_hip(hipMemsetAsync(d_upper, 0, vector_bytes, stream), "memset_upper");
      hipLaunchKernelGGL(composition::sparse_component::permute_rhs_kernel, dim3(sparse_grid), dim3(128), 0, stream,
                         sparse.dimension, d_rp, d_rhs_kn, d_permuted); ++sparse_kernels;
      for (std::int64_t level = 0; level < sparse.lower_levels; ++level) {
        const auto start = sparse.lower_level_ptr[level]; const auto size = sparse.lower_level_ptr[level + 1] - start;
        hipLaunchKernelGGL(composition::sparse_component::lower_level_kernel,
          dim3(static_cast<unsigned int>((size + 127) / 128)), dim3(128), 0, stream,
          d_lrp, d_lci, d_lv, d_llr, start, size, d_permuted, d_lower); ++sparse_kernels;
      }
      for (std::int64_t level = 0; level < sparse.upper_levels; ++level) {
        const auto start = sparse.upper_level_ptr[level]; const auto size = sparse.upper_level_ptr[level + 1] - start;
        hipLaunchKernelGGL(composition::sparse_component::upper_level_kernel,
          dim3(static_cast<unsigned int>((size + 127) / 128)), dim3(128), 0, stream,
          d_urp, d_uci, d_uv, d_ulr, start, size, d_lower, d_upper); ++sparse_kernels;
      }
      hipLaunchKernelGGL(composition::sparse_component::column_permutation_kernel, dim3(sparse_grid), dim3(128), 0, stream,
                         sparse.dimension, d_cp, d_upper, zj); ++sparse_kernels;
      dt.free_direction = zj;
      hipLaunchKernelGGL(composition::tangent_component::current_tangent_action_kernel,
                         dim3(grid), dim3(kBlockSize), 0, stream, dt, d_work);
      hipLaunchKernelGGL(scale_action_kernel, dim3(grid), dim3(kBlockSize), 0, stream,
                         sparse.dimension, reference_force_n, d_work); vector_kernels += 3;
      for (int pass = 0; pass < 2; ++pass) {
        for (int row = 0; row <= iteration; ++row) {
          const double* vi = d_basis + static_cast<std::int64_t>(row) * sparse.dimension;
          hipLaunchKernelGGL(dot_kernel, dim3(1), dim3(1), 0, stream, sparse.dimension, vi, d_work, d_scalar);
          hipLaunchKernelGGL(h_accumulate_kernel, dim3(1), dim3(1), 0, stream, d_h, row, iteration, d_scalar);
          hipLaunchKernelGGL(axpy_kernel, dim3(grid), dim3(kBlockSize), 0, stream, sparse.dimension, d_work, vi, d_scalar);
          vector_kernels += 3;
        }
      }
      hipLaunchKernelGGL(norm_and_store_kernel, dim3(1), dim3(1), 0, stream, sparse.dimension, d_work, d_h,
                         iteration + 1, iteration, d_scalar);
      hipLaunchKernelGGL(normalize_kernel, dim3(grid), dim3(kBlockSize), 0, stream, sparse.dimension, d_work, d_scalar,
                         d_basis + static_cast<std::int64_t>(iteration + 1) * sparse.dimension);
      hipLaunchKernelGGL(givens_kernel, dim3(1), dim3(1), 0, stream, d_h, d_g, d_c, d_s, d_history, iteration);
      vector_kernels += 3;
    }
    hipLaunchKernelGGL(backsolve_kernel, dim3(1), dim3(1), 0, stream, d_h, d_g, d_y);
    hipLaunchKernelGGL(combine_solution_kernel, dim3(grid), dim3(kBlockSize), 0, stream,
                       sparse.dimension, d_z, d_y, d_solution);
    dt.free_direction = d_solution;
    hipLaunchKernelGGL(composition::tangent_component::current_tangent_action_kernel,
                       dim3(grid), dim3(kBlockSize), 0, stream, dt, d_work);
    hipLaunchKernelGGL(physical_residual_kernel, dim3(grid), dim3(kBlockSize), 0, stream,
                       sparse.dimension, d_original_rhs_kn, d_work, d_residual);
    hipLaunchKernelGGL(residual_metrics_kernel, dim3(1), dim3(1), 0, stream,
                       sparse.dimension, d_residual, reference_force_n, d_metrics);
    vector_kernels += 5;

    std::vector<double> solution(sparse.dimension), residual(sparse.dimension), history(kRestart), metrics(4);
    check_hip(hipMemcpyAsync(solution.data(), d_solution, vector_bytes, hipMemcpyDeviceToHost, stream), "solution_d2h");
    check_hip(hipMemcpyAsync(residual.data(), d_residual, vector_bytes, hipMemcpyDeviceToHost, stream), "residual_d2h");
    check_hip(hipMemcpyAsync(history.data(), d_history, kRestart * sizeof(double), hipMemcpyDeviceToHost, stream), "history_d2h");
    check_hip(hipMemcpyAsync(metrics.data(), d_metrics, 4 * sizeof(double), hipMemcpyDeviceToHost, stream), "metrics_d2h");
    check_hip(hipStreamSynchronize(stream), "hipStreamSynchronize");
    const double wall_ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - started).count();
    write_vector(argv[4], solution); write_vector(argv[5], residual);
    std::cout << std::setprecision(17) << "{\"schema_version\":\"" << kOutputVersion
      << "\",\"status\":\"ok\",\"cpu_backend\":false,\"device_name\":\""
      << composition::tangent_component::json_escape(properties.name) << "\",\"gcn_arch_name\":\""
      << composition::tangent_component::json_escape(properties.gcnArchName) << "\",\"equation_count\":" << sparse.dimension
      << ",\"restart\":" << kRestart << ",\"krylov_iterations\":" << kRestart
      << ",\"preconditioner_apply_count\":" << kRestart << ",\"matvec_count\":" << kRestart + 1
      << ",\"sparse_kernel_invocation_count\":" << sparse_kernels
      << ",\"vector_kernel_invocation_count\":" << vector_kernels
      << ",\"mid_iteration_d2h_transfer_count\":0,\"final_d2h_transfer_count\":4"
      << ",\"h2d_bytes\":" << h2d_bytes << ",\"d2h_bytes\":" << 2 * vector_bytes + (kRestart + 4) * sizeof(double)
      << ",\"tracked_peak_device_allocation_bytes\":" << allocated_bytes
      << ",\"reference_force_n\":" << reference_force_n
      << ",\"physical_residual_l2_n\":" << metrics[0] << ",\"physical_residual_inf_n\":" << metrics[1]
      << ",\"scaled_residual_l2\":" << metrics[2] << ",\"scaled_residual_inf\":" << metrics[3]
      << ",\"device_lifecycle_wall_time_ms\":" << wall_ms << ",\"estimated_residual_history\":[";
    for (int i = 0; i < kRestart; ++i) { if (i) std::cout << ','; std::cout << history[i]; }
    std::cout << "]}\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "engine_v2_mgt_fgmres_error:" << error.what() << '\n';
    return 2;
  }
}
