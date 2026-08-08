#include <hip/hip_runtime.h>

#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

constexpr int kBlockSize = 256;
constexpr std::int64_t kPointCount = 4096;

struct State {
  double plastic_strain;
  double backstress_mpa;
  double accumulated_plastic_strain;
  double dissipated_energy_density_mj_per_m3;
};

struct Response {
  double stress_mpa;
  double tangent_mpa;
  double plastic_increment;
  double trial_yield_mpa;
  double final_yield_mpa;
  double yielded;
};

void check_hip(hipError_t status, const char* where) {
  if (status != hipSuccess) {
    throw std::runtime_error(std::string(where) + ":" + hipGetErrorString(status));
  }
}

__device__ void integrate(double strain, const State& accepted, State* trial,
                          Response* response) {
  constexpr double elastic = 200000.0;
  constexpr double yield_stress = 250.0;
  constexpr double isotropic = 3000.0;
  constexpr double kinematic = 5000.0;
  constexpr double tolerance = 1.0e-10;
  const double elastic_trial = strain - accepted.plastic_strain;
  const double trial_stress = elastic * elastic_trial;
  const double relative_trial = trial_stress - accepted.backstress_mpa;
  const double yield_radius =
      yield_stress + isotropic * accepted.accumulated_plastic_strain;
  const double trial_yield = fabs(relative_trial) - yield_radius;
  State next = accepted;
  double stress = trial_stress;
  double tangent = elastic;
  double increment = 0.0;
  double yielded = 0.0;
  if (trial_yield > tolerance) {
    const double direction = relative_trial >= 0.0 ? 1.0 : -1.0;
    increment = trial_yield / (elastic + isotropic + kinematic);
    next.plastic_strain += increment * direction;
    next.backstress_mpa += kinematic * increment * direction;
    next.accumulated_plastic_strain += increment;
    next.dissipated_energy_density_mj_per_m3 += yield_stress * increment;
    stress = trial_stress - elastic * increment * direction;
    tangent = elastic * (isotropic + kinematic) /
              (elastic + isotropic + kinematic);
    yielded = 1.0;
  }
  const double final_yield = fabs(stress - next.backstress_mpa) -
      (yield_stress + isotropic * next.accumulated_plastic_strain);
  *trial = next;
  *response = Response{stress, tangent, increment, trial_yield,
                       final_yield, yielded};
}

__global__ void initialize_kernel(State* accepted, double* commit_strain,
                                  double* rollback_strain) {
  const std::int64_t i =
      static_cast<std::int64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (i >= kPointCount) return;
  accepted[i] = State{0.0, 0.0, 0.0, 0.0};
  const double phase = static_cast<double>(i % 257) / 256.0;
  commit_strain[i] = 0.001 + 0.003 * phase;
  rollback_strain[i] = -0.0035 + 0.001 * phase;
}

__global__ void integrate_kernel(const State* accepted, const double* strain,
                                 State* trial, Response* response) {
  const std::int64_t i =
      static_cast<std::int64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (i < kPointCount) integrate(strain[i], accepted[i], &trial[i], &response[i]);
}

__global__ void copy_state_kernel(const State* source, State* destination) {
  const std::int64_t i =
      static_cast<std::int64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (i < kPointCount) destination[i] = source[i];
}

template <typename T>
T* allocate(std::size_t count, std::uint64_t* bytes) {
  T* result = nullptr;
  check_hip(hipMalloc(reinterpret_cast<void**>(&result), count * sizeof(T)),
            "hipMalloc");
  *bytes += static_cast<std::uint64_t>(count * sizeof(T));
  return result;
}

template <typename T>
void write_binary(const char* path, const std::vector<T>& values) {
  std::ofstream output(path, std::ios::binary | std::ios::trunc);
  output.write(reinterpret_cast<const char*>(values.data()),
               static_cast<std::streamsize>(values.size() * sizeof(T)));
  if (!output) throw std::runtime_error("material_output_write_failed");
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc != 7) {
      throw std::runtime_error(
          "usage:material committed.bin commit_response.bin rejected_trial.bin "
          "rejected_response.bin rollback.bin strains.bin");
    }
    int device_index = 0;
    check_hip(hipGetDevice(&device_index), "hipGetDevice");
    hipDeviceProp_t properties{};
    check_hip(hipGetDeviceProperties(&properties, device_index),
              "hipGetDeviceProperties");
    hipStream_t stream = nullptr;
    check_hip(hipStreamCreate(&stream), "hipStreamCreate");
    std::uint64_t allocated_bytes = 0;
    const auto started = std::chrono::steady_clock::now();
    State* d_accepted = allocate<State>(kPointCount, &allocated_bytes);
    State* d_commit_trial = allocate<State>(kPointCount, &allocated_bytes);
    State* d_rejected_trial = allocate<State>(kPointCount, &allocated_bytes);
    State* d_rollback = allocate<State>(kPointCount, &allocated_bytes);
    Response* d_commit_response = allocate<Response>(kPointCount, &allocated_bytes);
    Response* d_rejected_response = allocate<Response>(kPointCount, &allocated_bytes);
    double* d_commit_strain = allocate<double>(kPointCount, &allocated_bytes);
    double* d_rollback_strain = allocate<double>(kPointCount, &allocated_bytes);
    const int grid = static_cast<int>((kPointCount + kBlockSize - 1) / kBlockSize);
    hipLaunchKernelGGL(initialize_kernel, dim3(grid), dim3(kBlockSize), 0, stream,
                       d_accepted, d_commit_strain, d_rollback_strain);
    hipLaunchKernelGGL(integrate_kernel, dim3(grid), dim3(kBlockSize), 0, stream,
                       d_accepted, d_commit_strain, d_commit_trial,
                       d_commit_response);
    hipLaunchKernelGGL(copy_state_kernel, dim3(grid), dim3(kBlockSize), 0, stream,
                       d_commit_trial, d_accepted);
    hipLaunchKernelGGL(integrate_kernel, dim3(grid), dim3(kBlockSize), 0, stream,
                       d_accepted, d_rollback_strain, d_rejected_trial,
                       d_rejected_response);
    hipLaunchKernelGGL(copy_state_kernel, dim3(grid), dim3(kBlockSize), 0, stream,
                       d_accepted, d_rollback);
    check_hip(hipGetLastError(), "material_lifecycle_kernel");

    std::vector<State> committed(kPointCount), rejected(kPointCount), rollback(kPointCount);
    std::vector<Response> commit_response(kPointCount), rejected_response(kPointCount);
    std::vector<double> strains(static_cast<std::size_t>(kPointCount) * 2U);
    const auto state_bytes = static_cast<std::size_t>(kPointCount) * sizeof(State);
    const auto response_bytes = static_cast<std::size_t>(kPointCount) * sizeof(Response);
    const auto strain_bytes = static_cast<std::size_t>(kPointCount) * sizeof(double);
    check_hip(hipMemcpyAsync(committed.data(), d_accepted, state_bytes,
                             hipMemcpyDeviceToHost, stream), "committed_d2h");
    check_hip(hipMemcpyAsync(commit_response.data(), d_commit_response, response_bytes,
                             hipMemcpyDeviceToHost, stream), "commit_response_d2h");
    check_hip(hipMemcpyAsync(rejected.data(), d_rejected_trial, state_bytes,
                             hipMemcpyDeviceToHost, stream), "rejected_d2h");
    check_hip(hipMemcpyAsync(rejected_response.data(), d_rejected_response,
                             response_bytes, hipMemcpyDeviceToHost, stream),
              "rejected_response_d2h");
    check_hip(hipMemcpyAsync(rollback.data(), d_rollback, state_bytes,
                             hipMemcpyDeviceToHost, stream), "rollback_d2h");
    check_hip(hipMemcpyAsync(strains.data(), d_commit_strain, strain_bytes,
                             hipMemcpyDeviceToHost, stream), "commit_strain_d2h");
    check_hip(hipMemcpyAsync(strains.data() + kPointCount, d_rollback_strain,
                             strain_bytes, hipMemcpyDeviceToHost, stream),
              "rollback_strain_d2h");
    check_hip(hipStreamSynchronize(stream), "hipStreamSynchronize");
    const double wall_ms = std::chrono::duration<double, std::milli>(
        std::chrono::steady_clock::now() - started).count();
    write_binary(argv[1], committed); write_binary(argv[2], commit_response);
    write_binary(argv[3], rejected); write_binary(argv[4], rejected_response);
    write_binary(argv[5], rollback); write_binary(argv[6], strains);
    const std::uint64_t d2h_bytes = 3U * state_bytes + 2U * response_bytes +
                                    2U * strain_bytes;
    std::cout << std::setprecision(17)
              << "{\"schema_version\":\"engine-v2-stateful-steel-material-lifecycle-output.v1\""
              << ",\"status\":\"ok\",\"cpu_backend\":false,\"device_name\":\""
              << properties.name << "\",\"gcn_arch_name\":\"" << properties.gcnArchName
              << "\",\"integration_point_count\":" << kPointCount
              << ",\"kernel_invocation_count\":5,\"trial_count\":2"
              << ",\"commit_count\":1,\"rollback_count\":1"
              << ",\"mid_lifecycle_d2h_transfer_count\":0"
              << ",\"final_d2h_transfer_count\":7,\"h2d_bytes\":0"
              << ",\"d2h_bytes\":" << d2h_bytes
              << ",\"tracked_peak_device_allocation_bytes\":" << allocated_bytes
              << ",\"device_lifecycle_wall_time_ms\":" << wall_ms << "}\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "engine_v2_stateful_material_error:" << error.what() << '\n';
    return 2;
  }
}
