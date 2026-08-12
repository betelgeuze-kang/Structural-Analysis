#include "nonlinear_ndtha.hpp"
#include "nonlinear_ndtha_hip.hpp"

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
    structural::solver_cpu::NonlinearNdthaConfig config;
    std::vector<double> stiffness;
    std::vector<double> height;
    std::vector<double> axial;
    std::vector<double> yield_drift;
    std::vector<double> mass;
    std::vector<double> damping;
    std::vector<double> floor_load;
    std::vector<double> acceleration_g;

    [[nodiscard]] structural::solver_cpu::NonlinearNdthaInputs inputs() const {
        return {
            stiffness, height, axial, yield_drift, mass, damping, floor_load, acceleration_g,
        };
    }
};

struct AggregateReceipt {
    bool initialized {false};
    structural::hip::NonlinearNdthaExecutionReceipt identity {};
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
    std::uint64_t host_step_control_transfer_count {0U};
    std::size_t solve_count {0U};
};

void expect(const bool condition, const std::string_view message) {
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(EXIT_FAILURE);
    }
}

[[nodiscard]] std::vector<Profile> profiles() {
    const std::vector<double> stiffness {80'000'000.0, 70'000'000.0, 60'000'000.0};
    const std::vector<double> height {3.0, 3.2, 2.8};
    const std::vector<double> axial {2'000'000.0, 1'500'000.0, 1'000'000.0};
    const std::vector<double> yield_drift {0.001, 0.0012, 0.0008};
    const std::vector<double> mass {12'000.0, 10'000.0, 8'000.0};
    const std::vector<double> damping {1'200.0, 1'000.0, 800.0};
    const std::vector<double> acceleration {0.0, 0.2, -0.15, 0.35, -0.25, 0.1};
    return {
        {
            "elastic_pdelta",
            {2U, 3U, 0.01, 0.25, 0.5, 1.0e-5, 16U, 0.82, 0.6, 120U, 0.5, 0.03125, 0.2, 1.0, 10.0},
            {100'000'000.0, 90'000'000.0},
            {3.0, 3.0},
            {1'000'000.0, 800'000.0},
            {0.02, 0.02},
            {10'000.0, 8'000.0},
            {1'000.0, 900.0},
            {10'000.0, 8'000.0},
            {0.0, 0.01, -0.005},
        },
        {
            "one_story_elastic",
            {1U, 5U, 0.02, 0.3025, 0.6, 1.0e-7, 16U, 0.82, 0.2, 120U, 0.5, 0.03125, 0.2, 0.0, 20.0},
            {50'000'000.0},
            {3.2},
            {0.0},
            {0.01},
            {5'000.0},
            {250.0},
            {200'000.0},
            {0.0, 0.05, -0.03, 0.08, -0.02},
        },
        {
            "plastic_backtrack",
            {3U, 6U, 0.1, 0.25, 0.5, 1.0e-6, 16U, 0.82, 0.6, 120U, 0.5, 0.03125, 0.04, 1.0, 100.0},
            stiffness,
            height,
            axial,
            yield_drift,
            mass,
            damping,
            {5'000'000.0, 4'000'000.0, 3'000'000.0},
            acceleration,
        },
        {
            "adaptive_retry",
            {3U, 6U, 0.1, 0.25, 0.5, 1.0e-4, 16U, 0.82, 0.6, 8U, 0.5, 0.03125, 0.04, 1.0, 100.0},
            stiffness,
            height,
            axial,
            yield_drift,
            mass,
            damping,
            {1'000'000.0, 800'000.0, 600'000.0},
            acceleration,
        },
        {
            "collapse",
            {3U, 6U, 0.1, 0.25, 0.5, 1.0e-6, 16U, 0.82, 0.6, 120U, 0.5, 0.03125, 0.04, 1.0, 0.5},
            stiffness,
            height,
            axial,
            yield_drift,
            mass,
            damping,
            {5'000'000.0, 4'000'000.0, 3'000'000.0},
            acceleration,
        },
    };
}

template <typename T>
[[nodiscard]] bool same_vector_bits(const std::vector<T>& left, const std::vector<T>& right) {
    return left.size() == right.size() &&
           std::memcmp(left.data(), right.data(), left.size() * sizeof(T)) == 0;
}

[[nodiscard]] bool same_result_bits(const structural::solver_cpu::NonlinearNdthaResult& left,
                                    const structural::solver_cpu::NonlinearNdthaResult& right) {
    const std::array left_scalars {
        left.collapse_time_s,
        left.collapse_drift_ratio_pct,
        left.collapse_top_displacement_m,
        left.max_drift_ratio_pct,
        left.avg_step_iterations,
        left.residual_top_displacement_m,
        left.residual_drift_ratio_pct,
    };
    const std::array right_scalars {
        right.collapse_time_s,
        right.collapse_drift_ratio_pct,
        right.collapse_top_displacement_m,
        right.max_drift_ratio_pct,
        right.avg_step_iterations,
        right.residual_top_displacement_m,
        right.residual_drift_ratio_pct,
    };
    return left.converged_all_steps == right.converged_all_steps &&
           left.collapsed == right.collapsed && left.collapse_step == right.collapse_step &&
           left.step_count_completed == right.step_count_completed &&
           left.max_plastic_story_count == right.max_plastic_story_count &&
           left.total_line_search_backtracks == right.total_line_search_backtracks &&
           std::memcmp(left_scalars.data(), right_scalars.data(), sizeof(left_scalars)) == 0 &&
           same_vector_bits(left.response.top_displacement_m, right.response.top_displacement_m) &&
           same_vector_bits(left.response.drift_ratio_pct, right.response.drift_ratio_pct) &&
           same_vector_bits(left.response.base_shear_kn, right.response.base_shear_kn) &&
           same_vector_bits(left.response.core_drift_pct, right.response.core_drift_pct) &&
           same_vector_bits(left.response.core_shear_kn, right.response.core_shear_kn) &&
           same_vector_bits(left.response.step_converged, right.response.step_converged) &&
           same_vector_bits(left.response.step_iterations, right.response.step_iterations) &&
           same_vector_bits(left.response.step_plastic_story_count,
                            right.response.step_plastic_story_count) &&
           same_vector_bits(left.response.step_residual_inf, right.response.step_residual_inf) &&
           same_vector_bits(left.response.story_drift_envelope_pct,
                            right.response.story_drift_envelope_pct) &&
           same_vector_bits(left.response.final_story_drift_pct,
                            right.response.final_story_drift_pct);
}

void compare_vector(const std::vector<double>& cpu, const std::vector<double>& device,
                    double& maximum_error) {
    expect(cpu.size() == device.size(), "CPU/HIP NDTHA response length mismatch");
    for (std::size_t index = 0U; index < cpu.size(); ++index) {
        maximum_error = std::max(maximum_error, std::abs(cpu[index] - device[index]));
    }
}

void compare_results(const structural::solver_cpu::NonlinearNdthaResult& cpu,
                     const structural::solver_cpu::NonlinearNdthaResult& device,
                     double& maximum_response_error, double& maximum_summary_error) {
    expect(cpu.converged_all_steps == device.converged_all_steps, "convergence mismatch");
    expect(cpu.collapsed == device.collapsed, "collapse status mismatch");
    expect(cpu.collapse_step == device.collapse_step, "collapse step mismatch");
    expect(cpu.step_count_completed == device.step_count_completed, "step count mismatch");
    expect(cpu.max_plastic_story_count == device.max_plastic_story_count,
           "plastic-story count mismatch");
    expect(cpu.total_line_search_backtracks == device.total_line_search_backtracks,
           "line-search count mismatch");
    expect(cpu.response.step_converged == device.response.step_converged,
           "per-step convergence mismatch");
    expect(cpu.response.step_iterations == device.response.step_iterations,
           "adaptive iteration mismatch");
    expect(cpu.response.step_plastic_story_count == device.response.step_plastic_story_count,
           "per-step plastic-story mismatch");
    const std::array cpu_summary {
        cpu.collapse_time_s,          cpu.collapse_drift_ratio_pct, cpu.collapse_top_displacement_m,
        cpu.max_drift_ratio_pct,      cpu.avg_step_iterations,      cpu.residual_top_displacement_m,
        cpu.residual_drift_ratio_pct,
    };
    const std::array device_summary {
        device.collapse_time_s,
        device.collapse_drift_ratio_pct,
        device.collapse_top_displacement_m,
        device.max_drift_ratio_pct,
        device.avg_step_iterations,
        device.residual_top_displacement_m,
        device.residual_drift_ratio_pct,
    };
    for (std::size_t index = 0U; index < cpu_summary.size(); ++index) {
        maximum_summary_error =
            std::max(maximum_summary_error, std::abs(cpu_summary[index] - device_summary[index]));
    }
    compare_vector(cpu.response.top_displacement_m, device.response.top_displacement_m,
                   maximum_response_error);
    compare_vector(cpu.response.drift_ratio_pct, device.response.drift_ratio_pct,
                   maximum_response_error);
    compare_vector(cpu.response.base_shear_kn, device.response.base_shear_kn,
                   maximum_response_error);
    compare_vector(cpu.response.core_drift_pct, device.response.core_drift_pct,
                   maximum_response_error);
    compare_vector(cpu.response.core_shear_kn, device.response.core_shear_kn,
                   maximum_response_error);
    compare_vector(cpu.response.step_residual_inf, device.response.step_residual_inf,
                   maximum_response_error);
    compare_vector(cpu.response.story_drift_envelope_pct, device.response.story_drift_envelope_pct,
                   maximum_response_error);
    compare_vector(cpu.response.final_story_drift_pct, device.response.final_story_drift_pct,
                   maximum_response_error);
}

void accumulate(AggregateReceipt& aggregate,
                const structural::hip::NonlinearNdthaExecutionReceipt& receipt) {
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
        expect(receipt.kernel_source_sha256 == aggregate.identity.kernel_source_sha256,
               "HIP source identity drift");
        expect(receipt.device_library_sha256 == aggregate.identity.device_library_sha256,
               "HIP device library identity drift");
    }
    expect(receipt.h2d_transfer_count == 9U, "nine model/record H2D transfers");
    expect(receipt.d2h_transfer_count == 12U, "only terminal NDTHA results return");
    expect(receipt.synchronization_count == 1U, "one final HIP synchronization");
    expect(receipt.kernel_launch_count == 1U, "one resident Newmark/Newton kernel");
    expect(receipt.fallback_count == 0U, "HIP nonlinear-NDTHA fallback must stay zero");
    expect(receipt.fp64 && receipt.deterministic, "HIP deterministic FP64 policy");
    expect(receipt.device_resident_model, "model buffers must remain resident");
    expect(receipt.device_resident_step_state, "step state must remain resident");
    expect(receipt.device_resident_newmark_newton, "Newmark/Newton state must remain resident");
    expect(receipt.device_resident_tangent_solve, "tangent solve must remain resident");
    expect(receipt.device_result_recovery, "result recovery must execute on device");
    expect(receipt.host_intermediate_state_transfer_count == 0U,
           "no intermediate NDTHA state transfer");
    expect(receipt.host_iteration_control_transfer_count == 0U, "no host Newton iteration control");
    expect(receipt.host_step_control_transfer_count == 0U, "no host time-step control");
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
    aggregate.host_step_control_transfer_count += receipt.host_step_control_transfer_count;
    ++aggregate.solve_count;
}

} // namespace

int main() {
    auto cases = profiles();
    AggregateReceipt aggregate;
    double maximum_response_absolute_error = 0.0;
    double maximum_summary_absolute_error = 0.0;

    for (const auto& profile : cases) {
        const auto cpu =
            structural::solver_cpu::solve_nonlinear_ndtha(profile.config, profile.inputs());
        const auto first =
            structural::hip::solve_nonlinear_ndtha_hip(profile.config, profile.inputs());
        const auto second =
            structural::hip::solve_nonlinear_ndtha_hip(profile.config, profile.inputs());
        compare_results(cpu, first.result, maximum_response_absolute_error,
                        maximum_summary_absolute_error);
        expect(same_result_bits(first.result, second.result), "HIP repeat is not bitwise");
        accumulate(aggregate, first.receipt);
        accumulate(aggregate, second.receipt);
    }
    expect(cases[2].config.newton_max_iter == 120U, "plastic fixture changed");

    auto exhausted_config = cases.front().config;
    exhausted_config.max_step_iterations = 1U;
    exhausted_config.newton_max_iter = 1U;
    exhausted_config.tolerance = 1.0e-30;
    const auto cpu_exhausted =
        structural::solver_cpu::solve_nonlinear_ndtha(exhausted_config, cases.front().inputs());
    const auto hip_exhausted =
        structural::hip::solve_nonlinear_ndtha_hip(exhausted_config, cases.front().inputs());
    expect(!cpu_exhausted.converged_all_steps, "CPU nonconvergence profile changed");
    compare_results(cpu_exhausted, hip_exhausted.result, maximum_response_absolute_error,
                    maximum_summary_absolute_error);
    accumulate(aggregate, hip_exhausted.receipt);

    bool oversized_rejected = false;
    auto oversized_config = cases.front().config;
    oversized_config.newton_max_iter = 1'001U;
    try {
        static_cast<void>(
            structural::hip::solve_nonlinear_ndtha_hip(oversized_config, cases.front().inputs()));
    } catch (const std::invalid_argument&) {
        oversized_rejected = true;
    }
    expect(oversized_rejected, "HIP nonlinear-NDTHA bounded domain must fail before execution");

    expect(maximum_response_absolute_error <= 2.0e-6, "CPU/HIP response tolerance");
    expect(maximum_summary_absolute_error <= 2.0e-6, "CPU/HIP summary tolerance");
    expect(aggregate.solve_count == 11U, "HIP nonlinear-NDTHA solve count");
    expect(aggregate.h2d_transfer_count == 99U, "aggregate H2D transfer count");
    expect(aggregate.d2h_transfer_count == 132U, "aggregate D2H transfer count");
    expect(aggregate.synchronization_count == 11U, "aggregate synchronization count");
    expect(aggregate.kernel_launch_count == 11U, "aggregate kernel launch count");
    expect(aggregate.fallback_count == 0U, "aggregate fallback count");

    const auto& receipt = aggregate.identity;
    const auto runtime_architecture =
        receipt.architecture.substr(0U, receipt.architecture.find(':'));
    expect(receipt.device_id >= 0, "HIP nonlinear-NDTHA device id");
    expect(!receipt.device_name.empty() && !runtime_architecture.empty(), "device identity");
    expect(receipt.runtime_version > 0 && receipt.driver_version > 0, "ROCm versions");
    expect(!receipt.compiler_version.empty(), "HIP compiler identity");
    expect(receipt.compiled_architectures.find(runtime_architecture) != std::string::npos,
           "runtime architecture is not compiled");
    expect(receipt.kernel_source_sha256.size() == 64U, "kernel source SHA-256");
    expect(receipt.device_library_sha256.size() == 64U, "device-library SHA-256");
    expect(aggregate.h2d_bytes > 0U && aggregate.d2h_bytes > 0U, "transfer bytes");
    expect(aggregate.peak_device_buffer_bytes > 0U, "resident device buffer bytes");
    expect(receipt.vram_total_bytes > aggregate.peak_device_buffer_bytes, "visible VRAM");
    expect(receipt.vram_free_before_bytes <= receipt.vram_total_bytes &&
               receipt.vram_free_after_alloc_bytes <= receipt.vram_total_bytes,
           "VRAM counters");

    std::cout << std::setprecision(17)
              << "{\"schema_version\":\"native-nonlinear-ndtha-hip-receipt.v1\","
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
              << ",\"max_response_absolute_error\":" << maximum_response_absolute_error
              << ",\"max_summary_absolute_error\":" << maximum_summary_absolute_error
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
              << ",\"device_resident_step_state\":true"
              << ",\"device_resident_newmark_newton\":true"
              << ",\"device_resident_tangent_solve\":true"
              << ",\"device_result_recovery\":true"
              << ",\"host_intermediate_state_transfer_count\":0"
              << ",\"host_iteration_control_transfer_count\":0"
              << ",\"host_step_control_transfer_count\":0"
              << ",\"iteration_parity\":true,\"numerical_status_parity\":true"
              << ",\"parity_pass\":true}\n";
    return EXIT_SUCCESS;
}
