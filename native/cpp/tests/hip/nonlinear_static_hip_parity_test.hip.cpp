#include "nonlinear_static.hpp"
#include "nonlinear_static_hip.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace {

struct Profile {
    std::string name;
    structural::solver_cpu::NonlinearStaticConfig config;
    std::vector<double> stiffness;
    std::vector<double> height;
    std::vector<double> axial;
    std::vector<double> yield_drift;
    std::vector<double> floor_load;

    [[nodiscard]] structural::solver_cpu::NonlinearStaticInputs inputs() const {
        return {stiffness, height, axial, yield_drift, floor_load};
    }
};

struct AggregateReceipt {
    bool initialized {false};
    structural::hip::NonlinearStaticExecutionReceipt identity {};
    std::uint64_t h2d_bytes {0U};
    std::uint64_t d2h_bytes {0U};
    std::uint64_t h2d_transfer_count {0U};
    std::uint64_t d2h_transfer_count {0U};
    std::uint64_t synchronization_count {0U};
    std::uint64_t kernel_launch_count {0U};
    std::uint64_t peak_device_buffer_bytes {0U};
    std::uint32_t fallback_count {0U};
    std::uint64_t host_intermediate_state_transfer_count {0U};
    std::uint64_t host_iteration_control_transfer_count {0U};
    std::size_t solve_count {0U};
};

void expect(const bool condition, const std::string_view message) {
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(EXIT_FAILURE);
    }
}

[[nodiscard]] std::vector<Profile> profiles() {
    return {
        {
            "one_story_elastic",
            {1U, 1.0e-9, 60U, 0.04, 0.5, 0.03125, 0.0},
            {20'000'000.0},
            {3.0},
            {0.0},
            {0.02},
            {5'000.0},
        },
        {
            "one_story_pdelta_backtrack",
            {1U, 1.0e-9, 60U, 0.05, 0.5, 0.03125, 1.0},
            {10'000'000.0},
            {3.0},
            {15'000'000.0},
            {0.01},
            {10'000.0},
        },
        {
            "elastic_pdelta",
            {3U, 1.0e-7, 60U, 0.04, 0.5, 0.03125, 1.0},
            {100'000'000.0, 90'000'000.0, 80'000'000.0},
            {3.0, 3.0, 3.0},
            {1'000'000.0, 800'000.0, 600'000.0},
            {0.02, 0.02, 0.02},
            {10'000.0, 8'000.0, 6'000.0},
        },
        {
            "plastic",
            {3U, 1.0e-8, 60U, 0.1, 0.5, 0.03125, 0.0},
            {10'000'000.0, 8'000'000.0, 6'000'000.0},
            {3.0, 3.2, 3.4},
            {0.0, 0.0, 0.0},
            {0.001, 0.0012, 0.0015},
            {20'000.0, 15'000.0, 10'000.0},
        },
        {
            "mixed_sign",
            {3U, 1.0e-8, 60U, 0.08, 0.5, 0.03125, 0.0},
            {12'000'000.0, 9'000'000.0, 7'000'000.0},
            {3.0, 3.0, 3.0},
            {0.0, 0.0, 0.0},
            {0.001, 0.001, 0.001},
            {20'000.0, -35'000.0, 25'000.0},
        },
    };
}

[[nodiscard]] bool same_result_bits(
    const structural::solver_cpu::NonlinearStaticResult& left,
    const structural::solver_cpu::NonlinearStaticResult& right) {
    const std::array left_metrics {
        left.residual_inf,
        left.residual_l2,
        left.max_abs_displacement_m,
        left.top_displacement_m,
        left.base_shear_kn,
    };
    const std::array right_metrics {
        right.residual_inf,
        right.residual_l2,
        right.max_abs_displacement_m,
        right.top_displacement_m,
        right.base_shear_kn,
    };
    return left.converged == right.converged && left.iterations == right.iterations
        && left.plastic_story_count == right.plastic_story_count
        && left.line_search_backtracks == right.line_search_backtracks
        && left.displacement_m.size() == right.displacement_m.size()
        && std::memcmp(
               left_metrics.data(), right_metrics.data(), sizeof(left_metrics)) == 0
        && std::memcmp(
               left.displacement_m.data(),
               right.displacement_m.data(),
               left.displacement_m.size() * sizeof(double)) == 0;
}

void accumulate(
    AggregateReceipt& aggregate,
    const structural::hip::NonlinearStaticExecutionReceipt& receipt) {
    if (!aggregate.initialized) {
        aggregate.identity = receipt;
        aggregate.initialized = true;
    } else {
        expect(receipt.device_id == aggregate.identity.device_id, "HIP device id drift");
        expect(receipt.device_name == aggregate.identity.device_name, "HIP device name drift");
        expect(receipt.architecture == aggregate.identity.architecture, "HIP architecture drift");
        expect(receipt.runtime_version == aggregate.identity.runtime_version, "runtime drift");
        expect(receipt.driver_version == aggregate.identity.driver_version, "driver drift");
        expect(receipt.compiler_version == aggregate.identity.compiler_version, "compiler drift");
        expect(
            receipt.kernel_source_sha256 == aggregate.identity.kernel_source_sha256,
            "HIP source identity drift");
        expect(
            receipt.device_library_sha256 == aggregate.identity.device_library_sha256,
            "HIP device library identity drift");
    }
    expect(receipt.h2d_transfer_count == 5U, "one H2D transfer per model input");
    expect(receipt.d2h_transfer_count == 2U, "only terminal result and displacement return");
    expect(receipt.synchronization_count == 1U, "one final HIP synchronization");
    expect(receipt.kernel_launch_count == 1U, "one resident Newton kernel");
    expect(receipt.fallback_count == 0U, "HIP nonlinear-static fallback must stay zero");
    expect(receipt.fp64 && receipt.deterministic, "HIP deterministic FP64 policy");
    expect(receipt.device_resident_model, "model buffers must remain resident");
    expect(receipt.device_resident_newton_state, "Newton state must remain resident");
    expect(receipt.device_resident_tangent_solve, "tangent solve must remain resident");
    expect(receipt.device_result_recovery, "result recovery must execute on device");
    expect(
        receipt.host_intermediate_state_transfer_count == 0U,
        "no intermediate Newton state transfer");
    expect(
        receipt.host_iteration_control_transfer_count == 0U,
        "no host Newton iteration control");
    aggregate.h2d_bytes += receipt.h2d_bytes;
    aggregate.d2h_bytes += receipt.d2h_bytes;
    aggregate.h2d_transfer_count += receipt.h2d_transfer_count;
    aggregate.d2h_transfer_count += receipt.d2h_transfer_count;
    aggregate.synchronization_count += receipt.synchronization_count;
    aggregate.kernel_launch_count += receipt.kernel_launch_count;
    aggregate.peak_device_buffer_bytes =
        std::max(aggregate.peak_device_buffer_bytes, receipt.device_buffer_bytes);
    aggregate.fallback_count += receipt.fallback_count;
    aggregate.host_intermediate_state_transfer_count +=
        receipt.host_intermediate_state_transfer_count;
    aggregate.host_iteration_control_transfer_count +=
        receipt.host_iteration_control_transfer_count;
    ++aggregate.solve_count;
}

}  // namespace

int main() {
    auto cases = profiles();
    AggregateReceipt aggregate;
    double maximum_displacement_absolute_error = 0.0;
    double maximum_residual_absolute_error = 0.0;
    double maximum_recovery_absolute_error = 0.0;

    for (const auto& profile : cases) {
        const auto cpu = structural::solver_cpu::solve_nonlinear_static(
            profile.config, profile.inputs());
        const auto first = structural::hip::solve_nonlinear_static_hip(
            profile.config, profile.inputs());
        const auto second = structural::hip::solve_nonlinear_static_hip(
            profile.config, profile.inputs());
        expect(cpu.converged, "CPU nonlinear-static profile changed");
        expect(first.result.converged == cpu.converged, "CPU/HIP convergence mismatch");
        expect(first.result.iterations == cpu.iterations, "CPU/HIP iteration mismatch");
        expect(
            first.result.plastic_story_count == cpu.plastic_story_count,
            "CPU/HIP plastic-story mismatch");
        expect(
            first.result.line_search_backtracks == cpu.line_search_backtracks,
            "CPU/HIP line-search mismatch");
        expect(same_result_bits(first.result, second.result), "HIP repeat is not bitwise");
        expect(
            first.result.displacement_m.size() == cpu.displacement_m.size(),
            "CPU/HIP displacement length mismatch");
        for (std::size_t index = 0U; index < cpu.displacement_m.size(); ++index) {
            maximum_displacement_absolute_error = std::max(
                maximum_displacement_absolute_error,
                std::abs(cpu.displacement_m[index] - first.result.displacement_m[index]));
        }
        maximum_residual_absolute_error = std::max({
            maximum_residual_absolute_error,
            std::abs(cpu.residual_inf - first.result.residual_inf),
            std::abs(cpu.residual_l2 - first.result.residual_l2),
        });
        maximum_recovery_absolute_error = std::max({
            maximum_recovery_absolute_error,
            std::abs(
                cpu.max_abs_displacement_m - first.result.max_abs_displacement_m),
            std::abs(cpu.top_displacement_m - first.result.top_displacement_m),
            std::abs(cpu.base_shear_kn - first.result.base_shear_kn),
        });
        accumulate(aggregate, first.receipt);
        accumulate(aggregate, second.receipt);
    }

    auto exhausted_config = cases[2].config;
    exhausted_config.max_iter = 1U;
    const auto cpu_exhausted = structural::solver_cpu::solve_nonlinear_static(
        exhausted_config, cases[2].inputs());
    const auto hip_exhausted = structural::hip::solve_nonlinear_static_hip(
        exhausted_config, cases[2].inputs());
    expect(!cpu_exhausted.converged, "CPU nonconvergence profile changed");
    expect(!hip_exhausted.result.converged, "HIP nonconvergence taxonomy mismatch");
    expect(
        hip_exhausted.result.iterations == cpu_exhausted.iterations,
        "CPU/HIP nonconvergence iteration mismatch");
    accumulate(aggregate, hip_exhausted.receipt);

    bool oversized_rejected = false;
    auto oversized_config = cases.front().config;
    oversized_config.max_iter = 10'001U;
    try {
        static_cast<void>(structural::hip::solve_nonlinear_static_hip(
            oversized_config, cases.front().inputs()));
    } catch (const std::invalid_argument&) {
        oversized_rejected = true;
    }
    expect(oversized_rejected, "HIP nonlinear-static bounded domain must fail before execution");

    expect(
        maximum_displacement_absolute_error <= 5.0e-11,
        "CPU/HIP displacement tolerance");
    expect(maximum_residual_absolute_error <= 2.0e-7, "CPU/HIP residual tolerance");
    expect(maximum_recovery_absolute_error <= 2.0e-8, "CPU/HIP recovery tolerance");
    expect(aggregate.solve_count == 11U, "HIP nonlinear-static solve count");
    expect(aggregate.h2d_transfer_count == 55U, "aggregate H2D transfer count");
    expect(aggregate.d2h_transfer_count == 22U, "aggregate D2H transfer count");
    expect(aggregate.synchronization_count == 11U, "aggregate synchronization count");
    expect(aggregate.kernel_launch_count == 11U, "aggregate kernel launch count");
    expect(aggregate.fallback_count == 0U, "aggregate fallback count");

    const auto& receipt = aggregate.identity;
    const auto runtime_architecture = receipt.architecture.substr(
        0U, receipt.architecture.find(':'));
    expect(receipt.device_id >= 0, "HIP nonlinear-static device id");
    expect(!receipt.device_name.empty() && !runtime_architecture.empty(), "device identity");
    expect(receipt.runtime_version > 0 && receipt.driver_version > 0, "ROCm versions");
    expect(!receipt.compiler_version.empty(), "HIP compiler identity");
    expect(
        receipt.compiled_architectures.find(runtime_architecture) != std::string::npos,
        "runtime architecture is not compiled");
    expect(receipt.kernel_source_sha256.size() == 64U, "kernel source SHA-256");
    expect(receipt.device_library_sha256.size() == 64U, "device-library SHA-256");
    expect(aggregate.h2d_bytes > 0U && aggregate.d2h_bytes > 0U, "transfer bytes");
    expect(aggregate.peak_device_buffer_bytes > 0U, "resident device buffer bytes");
    expect(receipt.vram_total_bytes > aggregate.peak_device_buffer_bytes, "visible VRAM");
    expect(
        receipt.vram_free_before_bytes <= receipt.vram_total_bytes
            && receipt.vram_free_after_alloc_bytes <= receipt.vram_total_bytes,
        "VRAM counters");

    std::cout << std::setprecision(17)
              << "{\"schema_version\":\"native-nonlinear-static-hip-receipt.v1\","
              << "\"backend\":\"amd_rocm_hip\",\"device_id\":" << receipt.device_id
              << ",\"device_name\":" << std::quoted(receipt.device_name)
              << ",\"architecture\":" << std::quoted(receipt.architecture)
              << ",\"runtime_version\":" << receipt.runtime_version
              << ",\"driver_version\":" << receipt.driver_version
              << ",\"compiler_version\":" << std::quoted(receipt.compiler_version)
              << ",\"compiled_architectures\":" << std::quoted(receipt.compiled_architectures)
              << ",\"kernel_source_sha256\":" << std::quoted(receipt.kernel_source_sha256)
              << ",\"device_library_sha256\":" << std::quoted(receipt.device_library_sha256)
              << ",\"execution_profile\":" << std::quoted(receipt.execution_profile)
              << ",\"profile_count\":5,\"deterministic_repeat_count\":5"
              << ",\"numerical_failure_profile_count\":1"
              << ",\"solve_count\":" << aggregate.solve_count
              << ",\"max_displacement_absolute_error\":"
              << maximum_displacement_absolute_error
              << ",\"max_residual_absolute_error\":" << maximum_residual_absolute_error
              << ",\"max_recovery_absolute_error\":" << maximum_recovery_absolute_error
              << ",\"h2d_bytes\":" << aggregate.h2d_bytes
              << ",\"d2h_bytes\":" << aggregate.d2h_bytes
              << ",\"h2d_transfer_count\":" << aggregate.h2d_transfer_count
              << ",\"d2h_transfer_count\":" << aggregate.d2h_transfer_count
              << ",\"synchronization_count\":" << aggregate.synchronization_count
              << ",\"kernel_launch_count\":" << aggregate.kernel_launch_count
              << ",\"peak_device_buffer_bytes\":" << aggregate.peak_device_buffer_bytes
              << ",\"vram_total_bytes\":" << receipt.vram_total_bytes
              << ",\"vram_free_before_bytes\":" << receipt.vram_free_before_bytes
              << ",\"vram_free_after_alloc_bytes\":" << receipt.vram_free_after_alloc_bytes
              << ",\"fallback_count\":0,\"fp64\":true,\"deterministic\":true"
              << ",\"device_resident_model\":true"
              << ",\"device_resident_newton_state\":true"
              << ",\"device_resident_tangent_solve\":true"
              << ",\"device_result_recovery\":true"
              << ",\"host_intermediate_state_transfer_count\":0"
              << ",\"host_iteration_control_transfer_count\":0"
              << ",\"iteration_parity\":true,\"numerical_status_parity\":true"
              << ",\"parity_pass\":true}\n";
    return EXIT_SUCCESS;
}
