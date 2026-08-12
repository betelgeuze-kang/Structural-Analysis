#include "sparse_linear.hpp"
#include "sparse_linear_hip.hpp"

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

struct OwnedCsr {
    std::size_t order;
    std::vector<std::uint64_t> rows;
    std::vector<std::uint32_t> columns;
    std::vector<double> values;

    [[nodiscard]] structural::solver_cpu::CsrMatrixView view() const {
        return {order, rows, columns, values};
    }
};

struct Profile {
    std::string name;
    OwnedCsr matrix;
    std::vector<double> right_hand_side;
};

struct AggregateReceipt {
    bool initialized {false};
    structural::hip::SparseLinearExecutionReceipt identity {};
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
    const OwnedCsr five {
        5U,
        {0U, 2U, 5U, 8U, 11U, 13U},
        {0U, 1U, 0U, 1U, 2U, 1U, 2U, 3U, 2U, 3U, 4U, 3U, 4U},
        {4.0, -1.0, -1.0, 4.0, -1.0, -1.0, 4.0, -1.0,
         -1.0, 3.0, -1.0, -1.0, 2.0},
    };
    return {
        {"spd5", five, {6.0, -12.0, 18.0, -20.0, 14.0}},
        {
            "irregular6",
            {
                6U,
                {0U, 3U, 7U, 10U, 13U, 17U, 20U},
                {
                    0U, 1U, 4U,
                    0U, 1U, 2U, 5U,
                    1U, 2U, 3U,
                    2U, 3U, 4U,
                    0U, 3U, 4U, 5U,
                    1U, 4U, 5U,
                },
                {
                    10.0, 2.0, 1.0,
                    2.0, 9.0, -1.0, 1.0,
                    -1.0, 8.0, 2.0,
                    2.0, 7.0, -1.0,
                    1.0, -1.0, 6.0, 1.0,
                    1.0, 1.0, 5.0,
                },
            },
            {9.0, -10.5, 6.0, 17.5, -9.0, 10.5},
        },
        {
            "scaled4",
            {4U, {0U, 1U, 2U, 3U, 4U}, {0U, 1U, 2U, 3U},
             {1.0e-6, 2.0e-2, 3.0e2, 4.0e6}},
            {2.0e-6, -6.0e-2, 1.2e3, -2.0e7},
        },
        {"zero5", five, std::vector<double>(5U, 0.0)},
    };
}

[[nodiscard]] bool same_result_bits(
    const structural::solver_cpu::SparseLinearResult& left,
    const structural::solver_cpu::SparseLinearResult& right) {
    const std::array left_metrics {
        left.initial_residual_inf,
        left.final_residual_inf,
        left.final_residual_l2,
        left.last_increment_inf,
    };
    const std::array right_metrics {
        right.initial_residual_inf,
        right.final_residual_inf,
        right.final_residual_l2,
        right.last_increment_inf,
    };
    return left.status == right.status && left.iterations == right.iterations
        && left.fallback_count == right.fallback_count
        && left.solution.size() == right.solution.size()
        && std::memcmp(
               left.solution.data(),
               right.solution.data(),
               left.solution.size() * sizeof(double)) == 0
        && std::memcmp(left_metrics.data(), right_metrics.data(), sizeof(left_metrics)) == 0;
}

void accumulate(
    AggregateReceipt& aggregate,
    const structural::hip::SparseLinearExecutionReceipt& receipt,
    const std::uint64_t expected_h2d_transfer_count = 4U) {
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
    expect(
        receipt.h2d_transfer_count == expected_h2d_transfer_count,
        "one H2D transfer per populated sparse input buffer");
    expect(receipt.d2h_transfer_count == 2U, "only final result and solution return to host");
    expect(receipt.synchronization_count == 1U, "one final HIP synchronization");
    expect(receipt.kernel_launch_count == 1U, "one resident PCG execution kernel");
    expect(receipt.fallback_count == 0U, "HIP sparse fallback must stay zero");
    expect(receipt.fp64 && receipt.deterministic, "HIP deterministic FP64 policy");
    expect(receipt.device_resident_iterations, "PCG iteration state must remain resident");
    expect(
        receipt.host_intermediate_state_transfer_count == 0U,
        "no intermediate vector transfer");
    expect(
        receipt.host_iteration_control_transfer_count == 0U,
        "no host iteration-control transfer");
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

[[nodiscard]] double compare_solution(
    const std::span<const double> cpu,
    const std::span<const double> device,
    const std::string_view profile) {
    expect(cpu.size() == device.size(), "CPU/HIP sparse solution length mismatch");
    double maximum = 0.0;
    for (std::size_t index = 0U; index < cpu.size(); ++index) {
        const auto error = std::abs(cpu[index] - device[index]);
        const auto tolerance = 2.0e-11 + 2.0e-11 * std::abs(cpu[index]);
        if (!std::isfinite(device[index]) || error > tolerance) {
            std::cerr << profile << " solution mismatch at " << index
                      << " cpu=" << std::setprecision(17) << cpu[index]
                      << " hip=" << device[index] << " error=" << error
                      << " tolerance=" << tolerance << '\n';
            std::exit(EXIT_FAILURE);
        }
        maximum = std::max(maximum, error);
    }
    return maximum;
}

[[nodiscard]] double residual_error(
    const Profile& profile,
    const std::span<const double> cpu_solution,
    const std::span<const double> device_solution) {
    std::vector<double> cpu_product(profile.matrix.order, 0.0);
    std::vector<double> device_product(profile.matrix.order, 0.0);
    structural::solver_cpu::csr_matvec(profile.matrix.view(), cpu_solution, cpu_product);
    structural::solver_cpu::csr_matvec(profile.matrix.view(), device_solution, device_product);
    double maximum = 0.0;
    for (std::size_t index = 0U; index < profile.matrix.order; ++index) {
        const auto cpu_residual = profile.right_hand_side[index] - cpu_product[index];
        const auto device_residual = profile.right_hand_side[index] - device_product[index];
        maximum = std::max(maximum, std::abs(cpu_residual - device_residual));
    }
    return maximum;
}

[[nodiscard]] double metric_error(
    const structural::solver_cpu::SparseLinearResult& cpu,
    const structural::solver_cpu::SparseLinearResult& device) {
    const std::array cpu_metrics {
        cpu.initial_residual_inf,
        cpu.final_residual_inf,
        cpu.final_residual_l2,
        cpu.last_increment_inf,
    };
    const std::array device_metrics {
        device.initial_residual_inf,
        device.final_residual_inf,
        device.final_residual_l2,
        device.last_increment_inf,
    };
    double maximum = 0.0;
    for (std::size_t index = 0U; index < cpu_metrics.size(); ++index) {
        maximum = std::max(maximum, std::abs(cpu_metrics[index] - device_metrics[index]));
    }
    return maximum;
}

void check_failure_status(
    AggregateReceipt& aggregate,
    const OwnedCsr& matrix,
    const std::span<const double> right_hand_side,
    const structural::solver_cpu::SparseLinearConfig& config,
    const structural::solver_cpu::SolverStatus expected) {
    const auto cpu = structural::solver_cpu::solve_sparse_spd_pcg(
        matrix.view(), right_hand_side, {}, config);
    const auto device = structural::hip::solve_sparse_spd_pcg_hip(
        matrix.view(), right_hand_side, {}, config);
    expect(cpu.status == expected, "CPU failure profile status changed");
    expect(device.result.status == cpu.status, "CPU/HIP failure taxonomy mismatch");
    expect(device.result.iterations == cpu.iterations, "CPU/HIP failure iteration mismatch");
    expect(device.result.fallback_count == 0U, "failure path introduced fallback");
    accumulate(aggregate, device.receipt);
}

}  // namespace

int main() {
    const structural::solver_cpu::SparseLinearConfig config {200U, 1.0e-13, 1.0e-13, 0.0};
    auto cases = profiles();
    AggregateReceipt aggregate;
    double max_solution_absolute_error = 0.0;
    double max_true_residual_absolute_error = 0.0;
    double max_metric_absolute_error = 0.0;

    for (const auto& profile : cases) {
        const auto cpu = structural::solver_cpu::solve_sparse_spd_pcg(
            profile.matrix.view(), profile.right_hand_side, {}, config);
        const auto first = structural::hip::solve_sparse_spd_pcg_hip(
            profile.matrix.view(), profile.right_hand_side, {}, config);
        const auto second = structural::hip::solve_sparse_spd_pcg_hip(
            profile.matrix.view(), profile.right_hand_side, {}, config);
        expect(cpu.status == structural::solver_cpu::SolverStatus::converged, "CPU profile status");
        expect(first.result.status == cpu.status, "CPU/HIP sparse status mismatch");
        expect(first.result.iterations == cpu.iterations, "CPU/HIP sparse iteration mismatch");
        expect(same_result_bits(first.result, second.result), "HIP sparse repeat is not bitwise");
        max_solution_absolute_error = std::max(
            max_solution_absolute_error,
            compare_solution(cpu.solution, first.result.solution, profile.name));
        max_true_residual_absolute_error = std::max(
            max_true_residual_absolute_error,
            residual_error(profile, cpu.solution, first.result.solution));
        max_metric_absolute_error =
            std::max(max_metric_absolute_error, metric_error(cpu, first.result));
        accumulate(aggregate, first.receipt);
        accumulate(aggregate, second.receipt);
    }

    const auto exact_initial_cpu = structural::solver_cpu::solve_sparse_spd_pcg(
        cases.front().matrix.view(),
        cases.front().right_hand_side,
        {},
        config);
    const auto exact_initial = structural::hip::solve_sparse_spd_pcg_hip(
        cases.front().matrix.view(),
        cases.front().right_hand_side,
        exact_initial_cpu.solution,
        config);
    expect(exact_initial.result.status == structural::solver_cpu::SolverStatus::converged,
           "HIP exact initial guess status");
    expect(exact_initial.result.iterations == 0U, "HIP exact initial guess iteration count");
    max_solution_absolute_error = std::max(
        max_solution_absolute_error,
        compare_solution(
            exact_initial_cpu.solution,
            exact_initial.result.solution,
            "exact_initial_spd5"));
    accumulate(aggregate, exact_initial.receipt, 5U);

    auto singular = cases.front().matrix;
    singular.values[0] = 0.0;
    check_failure_status(
        aggregate,
        singular,
        cases.front().right_hand_side,
        config,
        structural::solver_cpu::SolverStatus::singularity);
    auto indefinite = cases.front().matrix;
    indefinite.values[0] = -4.0;
    check_failure_status(
        aggregate,
        indefinite,
        cases.front().right_hand_side,
        config,
        structural::solver_cpu::SolverStatus::indefinite_operator);
    auto exhausted = config;
    exhausted.max_iterations = 1U;
    check_failure_status(
        aggregate,
        cases.front().matrix,
        cases.front().right_hand_side,
        exhausted,
        structural::solver_cpu::SolverStatus::nonconvergence);
    auto limited = config;
    limited.maximum_increment = 1.0e-20;
    check_failure_status(
        aggregate,
        cases.front().matrix,
        cases.front().right_hand_side,
        limited,
        structural::solver_cpu::SolverStatus::increment_limit);

    expect(max_solution_absolute_error <= 2.0e-11, "CPU/HIP solution tolerance");
    expect(max_true_residual_absolute_error <= 2.0e-11, "CPU/HIP residual tolerance");
    expect(max_metric_absolute_error <= 2.0e-10, "CPU/HIP metric tolerance");
    bool oversized_rejected = false;
    auto oversized = config;
    oversized.max_iterations = 10'001U;
    try {
        static_cast<void>(structural::hip::solve_sparse_spd_pcg_hip(
            cases.front().matrix.view(), cases.front().right_hand_side, {}, oversized));
    } catch (const std::invalid_argument&) {
        oversized_rejected = true;
    }
    expect(oversized_rejected, "HIP sparse bounded iteration domain must fail before execution");

    expect(aggregate.solve_count == 13U, "HIP sparse solve profile count");
    expect(aggregate.h2d_transfer_count == 53U, "aggregate H2D transfer count");
    expect(aggregate.d2h_transfer_count == 26U, "aggregate D2H transfer count");
    expect(aggregate.synchronization_count == 13U, "aggregate synchronization count");
    expect(aggregate.kernel_launch_count == 13U, "aggregate kernel launch count");
    const auto& receipt = aggregate.identity;
    const auto runtime_architecture = receipt.architecture.substr(
        0U, receipt.architecture.find(':'));
    expect(receipt.device_id >= 0, "HIP sparse device id");
    expect(!receipt.device_name.empty() && !runtime_architecture.empty(), "HIP sparse identity");
    expect(receipt.runtime_version > 0 && receipt.driver_version > 0, "ROCm versions");
    expect(!receipt.compiler_version.empty(), "HIP sparse compiler identity");
    expect(
        receipt.compiled_architectures.find(runtime_architecture) != std::string::npos,
        "HIP sparse runtime architecture is not compiled");
    expect(receipt.kernel_source_sha256.size() == 64U, "HIP sparse source SHA-256");
    expect(receipt.device_library_sha256.size() == 64U, "HIP sparse device-library SHA-256");
    expect(aggregate.h2d_bytes > 0U && aggregate.d2h_bytes > 0U, "HIP sparse byte counters");
    expect(aggregate.peak_device_buffer_bytes > 0U, "HIP sparse resident buffer bytes");
    expect(receipt.vram_total_bytes > aggregate.peak_device_buffer_bytes, "HIP sparse VRAM");
    expect(
        receipt.vram_free_before_bytes <= receipt.vram_total_bytes
            && receipt.vram_free_after_alloc_bytes <= receipt.vram_total_bytes,
        "HIP sparse VRAM counters");

    std::cout << std::setprecision(17)
              << "{\"schema_version\":\"native-sparse-linear-hip-receipt.v1\","
              << "\"backend\":\"amd_rocm_hip\",\"device_id\":" << receipt.device_id
              << ",\"device_name\":" << std::quoted(receipt.device_name)
              << ",\"architecture\":" << std::quoted(receipt.architecture)
              << ",\"runtime_version\":" << receipt.runtime_version
              << ",\"driver_version\":" << receipt.driver_version
              << ",\"compiler_version\":" << std::quoted(receipt.compiler_version)
              << ",\"compiled_architectures\":" << std::quoted(receipt.compiled_architectures)
              << ",\"kernel_source_sha256\":" << std::quoted(receipt.kernel_source_sha256)
              << ",\"device_library_sha256\":" << std::quoted(receipt.device_library_sha256)
              << ",\"reduction_profile\":" << std::quoted(receipt.reduction_profile)
              << ",\"profile_count\":4,\"exact_initial_profile_count\":1"
              << ",\"failure_profile_count\":4"
              << ",\"solve_count\":" << aggregate.solve_count
              << ",\"max_solution_absolute_error\":" << max_solution_absolute_error
              << ",\"max_true_residual_absolute_error\":"
              << max_true_residual_absolute_error
              << ",\"max_metric_absolute_error\":" << max_metric_absolute_error
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
              << ",\"device_resident_iterations\":true"
              << ",\"host_intermediate_state_transfer_count\":0"
              << ",\"host_iteration_control_transfer_count\":0"
              << ",\"iteration_parity\":true,\"numerical_status_parity\":true"
              << ",\"parity_pass\":true}\n";
    return EXIT_SUCCESS;
}
