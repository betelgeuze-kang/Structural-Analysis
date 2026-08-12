#include "generalized_eigen.hpp"
#include "generalized_eigen_hip.hpp"

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
#include <vector>

namespace {

using structural::solver_cpu::DenseSymmetricMatrixView;
using structural::solver_cpu::SolverStatus;

struct OwnedDense {
    std::size_t order;
    std::vector<double> values;

    [[nodiscard]] DenseSymmetricMatrixView view() const { return {order, values}; }
};

struct ModalProfile {
    std::string name;
    OwnedDense stiffness;
    OwnedDense mass;
    std::vector<double> scale;
    std::uint32_t mode_count;
};

struct BucklingProfile {
    std::string name;
    OwnedDense stiffness;
    OwnedDense geometric;
    std::vector<double> scale;
    std::uint32_t mode_count;
};

struct AggregateReceipt {
    bool initialized {false};
    structural::hip::GeneralizedEigenExecutionReceipt identity {};
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

[[nodiscard]] OwnedDense diagonal(const std::initializer_list<double> values) {
    OwnedDense result {values.size(), std::vector<double>(values.size() * values.size(), 0.0)};
    std::size_t index = 0U;
    for (const auto value : values) {
        result.values[index * result.order + index] = value;
        ++index;
    }
    return result;
}

[[nodiscard]] std::vector<ModalProfile> modal_profiles() {
    return {
        {
            "modal_two",
            {2U, {2.0, -1.0, -1.0, 1.0}},
            diagonal({1.0, 1.0}),
            {},
            2U,
        },
        {
            "modal_scaled",
            {3U, {8.0, -2.0, 0.5, -2.0, 6.0, -1.0, 0.5, -1.0, 5.0}},
            {3U, {2.0, 0.2, 0.0, 0.2, 3.0, 0.1, 0.0, 0.1, 1.5}},
            {0.25, 1.0, 2.0},
            3U,
        },
        {
            "modal_rigid",
            diagonal({0.0, 4.0, 9.0}),
            diagonal({1.0, 1.0, 1.0}),
            {},
            2U,
        },
        {
            "modal_repeated",
            diagonal({4.0, 4.0, 9.0}),
            diagonal({1.0, 1.0, 1.0}),
            {},
            3U,
        },
    };
}

[[nodiscard]] std::vector<BucklingProfile> buckling_profiles() {
    return {
        {
            "buckling_singular",
            diagonal({6.0, 8.0, 10.0}),
            diagonal({3.0, 2.0, 0.0}),
            {},
            2U,
        },
        {
            "buckling_scaled",
            {3U, {7.0, -1.0, 0.5, -1.0, 9.0, -1.5, 0.5, -1.5, 6.0}},
            {3U, {2.0, 0.2, 0.0, 0.2, 1.0, 0.1, 0.0, 0.1, 0.5}},
            {1.0, 0.2, 3.0},
            3U,
        },
        {
            "buckling_tiny",
            diagonal({1.0, 1.0}),
            diagonal({1.0e-15, 0.0}),
            {},
            1U,
        },
        {
            "buckling_repeated",
            diagonal({4.0, 4.0, 9.0}),
            diagonal({1.0, 1.0, 1.0}),
            {},
            3U,
        },
    };
}

void accumulate(
    AggregateReceipt& aggregate,
    const structural::hip::GeneralizedEigenExecutionReceipt& receipt) {
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
            "HIP generalized-eigen source identity drift");
        expect(
            receipt.device_library_sha256 == aggregate.identity.device_library_sha256,
            "HIP generalized-eigen device-library identity drift");
    }
    expect(receipt.h2d_transfer_count == 3U, "three generalized-eigen H2D inputs");
    expect(receipt.d2h_transfer_count == 1U, "only packed generalized-eigen result returns");
    expect(receipt.synchronization_count == 1U, "one final generalized-eigen synchronization");
    expect(receipt.kernel_launch_count == 1U, "one resident generalized-eigen kernel");
    expect(receipt.fallback_count == 0U, "generalized-eigen fallback must remain zero");
    expect(receipt.fp64 && receipt.deterministic, "deterministic FP64 policy");
    expect(receipt.device_resident_eigensolve, "eigensolve must remain device resident");
    expect(receipt.device_result_recovery, "result recovery must execute on device");
    expect(
        receipt.host_intermediate_state_transfer_count == 0U,
        "no generalized-eigen intermediate D2H transfer");
    expect(
        receipt.host_iteration_control_transfer_count == 0U,
        "no host eigensolver iteration control");
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

[[nodiscard]] double relative_error(const double expected, const double actual) {
    return std::abs(expected - actual)
        / std::max({1.0, std::abs(expected), std::abs(actual)});
}

[[nodiscard]] double compare_vector(
    const std::span<const double> expected,
    const std::span<const double> actual,
    const std::string_view profile) {
    expect(expected.size() == actual.size(), "CPU/HIP generalized-eigen vector length");
    double maximum = 0.0;
    for (std::size_t index = 0U; index < expected.size(); ++index) {
        const auto error = std::abs(expected[index] - actual[index]);
        if (!std::isfinite(actual[index]) || error > 2.0e-8) {
            std::cerr << profile << " vector mismatch at " << index
                      << " cpu=" << std::setprecision(17) << expected[index]
                      << " hip=" << actual[index] << " error=" << error << '\n';
            std::exit(EXIT_FAILURE);
        }
        maximum = std::max(maximum, error);
    }
    return maximum;
}

[[nodiscard]] bool same_modal_bits(
    const structural::solver_cpu::ModalEigenResult& left,
    const structural::solver_cpu::ModalEigenResult& right) {
    if (left.status != right.status || left.modes.size() != right.modes.size()
        || left.rigid_mode_count != right.rigid_mode_count
        || left.eigensolver_sweeps != right.eigensolver_sweeps
        || left.fallback_count != right.fallback_count) {
        return false;
    }
    const std::array left_result_metrics {
        left.mass_orthogonality_error_inf,
        left.stiffness_diagonalization_error_inf,
        left.stiffness_relative_symmetry_error,
        left.mass_relative_symmetry_error,
        left.stiffness_minimum_eigenvalue,
        left.mass_minimum_eigenvalue,
    };
    const std::array right_result_metrics {
        right.mass_orthogonality_error_inf,
        right.stiffness_diagonalization_error_inf,
        right.stiffness_relative_symmetry_error,
        right.mass_relative_symmetry_error,
        right.stiffness_minimum_eigenvalue,
        right.mass_minimum_eigenvalue,
    };
    if (std::memcmp(
            left_result_metrics.data(), right_result_metrics.data(),
            sizeof(left_result_metrics)) != 0) {
        return false;
    }
    for (std::size_t mode = 0U; mode < left.modes.size(); ++mode) {
        const std::array left_metrics {
            left.modes[mode].eigenvalue_rad2_per_s2,
            left.modes[mode].omega_rad_per_s,
            left.modes[mode].frequency_hz,
            left.modes[mode].period_s,
            left.modes[mode].generalized_mass,
            left.modes[mode].generalized_stiffness,
            left.modes[mode].residual_relative_inf,
        };
        const std::array right_metrics {
            right.modes[mode].eigenvalue_rad2_per_s2,
            right.modes[mode].omega_rad_per_s,
            right.modes[mode].frequency_hz,
            right.modes[mode].period_s,
            right.modes[mode].generalized_mass,
            right.modes[mode].generalized_stiffness,
            right.modes[mode].residual_relative_inf,
        };
        if (std::memcmp(left_metrics.data(), right_metrics.data(), sizeof(left_metrics)) != 0
            || left.modes[mode].mass_normalized_shape
                != right.modes[mode].mass_normalized_shape
            || left.modes[mode].max_component_normalized_shape
                != right.modes[mode].max_component_normalized_shape) {
            return false;
        }
    }
    return true;
}

[[nodiscard]] bool same_buckling_bits(
    const structural::solver_cpu::BucklingEigenResult& left,
    const structural::solver_cpu::BucklingEigenResult& right) {
    if (left.status != right.status || left.modes.size() != right.modes.size()
        || left.finite_positive_eigenvalue_count != right.finite_positive_eigenvalue_count
        || left.geometric_stiffness_positive_rank
            != right.geometric_stiffness_positive_rank
        || left.eigensolver_sweeps != right.eigensolver_sweeps
        || left.fallback_count != right.fallback_count) {
        return false;
    }
    const std::array left_result_metrics {
        left.critical_load_factor,
        left.stiffness_orthogonality_error_inf,
        left.geometric_diagonalization_error_inf,
        left.stiffness_relative_symmetry_error,
        left.geometric_stiffness_relative_symmetry_error,
        left.stiffness_minimum_eigenvalue,
        left.geometric_stiffness_minimum_eigenvalue,
    };
    const std::array right_result_metrics {
        right.critical_load_factor,
        right.stiffness_orthogonality_error_inf,
        right.geometric_diagonalization_error_inf,
        right.stiffness_relative_symmetry_error,
        right.geometric_stiffness_relative_symmetry_error,
        right.stiffness_minimum_eigenvalue,
        right.geometric_stiffness_minimum_eigenvalue,
    };
    if (std::memcmp(
            left_result_metrics.data(), right_result_metrics.data(),
            sizeof(left_result_metrics)) != 0) {
        return false;
    }
    for (std::size_t mode = 0U; mode < left.modes.size(); ++mode) {
        const std::array left_metrics {
            left.modes[mode].load_factor,
            left.modes[mode].generalized_elastic_stiffness,
            left.modes[mode].generalized_geometric_stiffness,
            left.modes[mode].residual_relative_inf,
        };
        const std::array right_metrics {
            right.modes[mode].load_factor,
            right.modes[mode].generalized_elastic_stiffness,
            right.modes[mode].generalized_geometric_stiffness,
            right.modes[mode].residual_relative_inf,
        };
        if (std::memcmp(left_metrics.data(), right_metrics.data(), sizeof(left_metrics)) != 0
            || left.modes[mode].stiffness_normalized_shape
                != right.modes[mode].stiffness_normalized_shape
            || left.modes[mode].max_component_normalized_shape
                != right.modes[mode].max_component_normalized_shape) {
            return false;
        }
    }
    return true;
}

template <typename Operation>
[[nodiscard]] bool throws_invalid(Operation&& operation) {
    try {
        operation();
    } catch (const std::invalid_argument&) {
        return true;
    }
    return false;
}

}  // namespace

int main() {
    auto modal_cases = modal_profiles();
    auto buckling_cases = buckling_profiles();
    AggregateReceipt aggregate;
    double maximum_eigenvalue_relative_error = 0.0;
    double maximum_shape_absolute_error = 0.0;
    double maximum_result_metric_absolute_error = 0.0;

    for (const auto& profile : modal_cases) {
        const auto config = structural::solver_cpu::default_modal_eigen_config(
            profile.mode_count);
        const auto cpu = structural::solver_cpu::solve_dense_modal_modes(
            profile.stiffness.view(), profile.mass.view(), profile.scale, config);
        const auto first = structural::hip::solve_dense_modal_modes_hip(
            profile.stiffness.view(), profile.mass.view(), profile.scale, config);
        const auto second = structural::hip::solve_dense_modal_modes_hip(
            profile.stiffness.view(), profile.mass.view(), profile.scale, config);
        expect(cpu.status == SolverStatus::converged, "CPU modal profile status");
        expect(first.result.status == cpu.status, "CPU/HIP modal status parity");
        expect(first.result.modes.size() == cpu.modes.size(), "CPU/HIP modal count parity");
        expect(first.result.rigid_mode_count == cpu.rigid_mode_count, "modal rigid count parity");
        expect(same_modal_bits(first.result, second.result), "HIP modal repeat is not bitwise");
        for (std::size_t mode = 0U; mode < cpu.modes.size(); ++mode) {
            maximum_eigenvalue_relative_error = std::max(
                maximum_eigenvalue_relative_error,
                relative_error(
                    cpu.modes[mode].eigenvalue_rad2_per_s2,
                    first.result.modes[mode].eigenvalue_rad2_per_s2));
            maximum_shape_absolute_error = std::max(
                maximum_shape_absolute_error,
                compare_vector(
                    cpu.modes[mode].mass_normalized_shape,
                    first.result.modes[mode].mass_normalized_shape,
                    profile.name));
            maximum_result_metric_absolute_error = std::max({
                maximum_result_metric_absolute_error,
                std::abs(
                    cpu.modes[mode].generalized_mass
                    - first.result.modes[mode].generalized_mass),
                std::abs(
                    cpu.modes[mode].generalized_stiffness
                    - first.result.modes[mode].generalized_stiffness),
                std::abs(
                    cpu.modes[mode].residual_relative_inf
                    - first.result.modes[mode].residual_relative_inf),
            });
        }
        maximum_result_metric_absolute_error = std::max({
            maximum_result_metric_absolute_error,
            std::abs(
                cpu.mass_orthogonality_error_inf
                - first.result.mass_orthogonality_error_inf),
            std::abs(
                cpu.stiffness_diagonalization_error_inf
                - first.result.stiffness_diagonalization_error_inf),
        });
        accumulate(aggregate, first.receipt);
        accumulate(aggregate, second.receipt);
    }

    for (const auto& profile : buckling_cases) {
        const auto config = structural::solver_cpu::default_buckling_eigen_config(
            profile.mode_count);
        const auto cpu = structural::solver_cpu::solve_dense_linear_buckling(
            profile.stiffness.view(), profile.geometric.view(), profile.scale, config);
        const auto first = structural::hip::solve_dense_linear_buckling_hip(
            profile.stiffness.view(), profile.geometric.view(), profile.scale, config);
        const auto second = structural::hip::solve_dense_linear_buckling_hip(
            profile.stiffness.view(), profile.geometric.view(), profile.scale, config);
        expect(cpu.status == SolverStatus::converged, "CPU buckling profile status");
        expect(first.result.status == cpu.status, "CPU/HIP buckling status parity");
        expect(first.result.modes.size() == cpu.modes.size(), "CPU/HIP buckling count parity");
        expect(
            first.result.finite_positive_eigenvalue_count
                == cpu.finite_positive_eigenvalue_count,
            "buckling finite positive count parity");
        expect(
            first.result.geometric_stiffness_positive_rank
                == cpu.geometric_stiffness_positive_rank,
            "buckling geometric rank parity");
        expect(
            same_buckling_bits(first.result, second.result),
            "HIP buckling repeat is not bitwise");
        for (std::size_t mode = 0U; mode < cpu.modes.size(); ++mode) {
            maximum_eigenvalue_relative_error = std::max(
                maximum_eigenvalue_relative_error,
                relative_error(
                    cpu.modes[mode].load_factor,
                    first.result.modes[mode].load_factor));
            maximum_shape_absolute_error = std::max(
                maximum_shape_absolute_error,
                compare_vector(
                    cpu.modes[mode].stiffness_normalized_shape,
                    first.result.modes[mode].stiffness_normalized_shape,
                    profile.name));
            maximum_result_metric_absolute_error = std::max({
                maximum_result_metric_absolute_error,
                std::abs(
                    cpu.modes[mode].generalized_elastic_stiffness
                    - first.result.modes[mode].generalized_elastic_stiffness),
                std::abs(
                    cpu.modes[mode].generalized_geometric_stiffness
                    - first.result.modes[mode].generalized_geometric_stiffness),
                std::abs(
                    cpu.modes[mode].residual_relative_inf
                    - first.result.modes[mode].residual_relative_inf),
            });
        }
        maximum_result_metric_absolute_error = std::max({
            maximum_result_metric_absolute_error,
            std::abs(
                cpu.stiffness_orthogonality_error_inf
                - first.result.stiffness_orthogonality_error_inf),
            std::abs(
                cpu.geometric_diagonalization_error_inf
                - first.result.geometric_diagonalization_error_inf),
        });
        accumulate(aggregate, first.receipt);
        accumulate(aggregate, second.receipt);
    }

    const OwnedDense nonconvergent_stiffness {
        3U,
        {5.0, -2.0, 1.0, -2.0, 4.0, -1.0, 1.0, -1.0, 3.0},
    };
    const auto nonconvergent_mass = diagonal({1.0, 2.0, 3.0});
    auto nonconvergent_config = structural::solver_cpu::default_modal_eigen_config(2U);
    nonconvergent_config.maximum_sweeps = 1U;
    nonconvergent_config.eigensolver_relative_tolerance = 1.0e-18;
    const auto cpu_nonconvergent = structural::solver_cpu::solve_dense_modal_modes(
        nonconvergent_stiffness.view(), nonconvergent_mass.view(), {}, nonconvergent_config);
    const auto hip_nonconvergent = structural::hip::solve_dense_modal_modes_hip(
        nonconvergent_stiffness.view(), nonconvergent_mass.view(), {}, nonconvergent_config);
    expect(cpu_nonconvergent.status == SolverStatus::nonconvergence, "CPU failure status");
    expect(
        hip_nonconvergent.result.status == cpu_nonconvergent.status,
        "CPU/HIP nonconvergence taxonomy parity");
    expect(hip_nonconvergent.result.modes.empty(), "HIP failure publishes no partial modes");
    accumulate(aggregate, hip_nonconvergent.receipt);

    auto residual_limit_config = structural::solver_cpu::default_modal_eigen_config(3U);
    residual_limit_config.orthogonality_tolerance = 0.0;
    const auto cpu_residual_limit = structural::solver_cpu::solve_dense_modal_modes(
        modal_cases[1].stiffness.view(),
        modal_cases[1].mass.view(),
        modal_cases[1].scale,
        residual_limit_config);
    const auto hip_residual_limit = structural::hip::solve_dense_modal_modes_hip(
        modal_cases[1].stiffness.view(),
        modal_cases[1].mass.view(),
        modal_cases[1].scale,
        residual_limit_config);
    expect(cpu_residual_limit.status == SolverStatus::residual_limit, "CPU residual status");
    expect(
        hip_residual_limit.result.status == cpu_residual_limit.status,
        "CPU/HIP residual-limit taxonomy parity");
    expect(hip_residual_limit.result.modes.empty(), "residual failure publishes no modes");
    expect(hip_residual_limit.result.rigid_mode_count == 0U, "failure metadata is atomic");
    accumulate(aggregate, hip_residual_limit.receipt);

    const auto identity2 = diagonal({1.0, 1.0});
    const auto singular2 = diagonal({1.0, 0.0});
    const auto negative2 = diagonal({1.0, -1.0});
    const auto zero2 = diagonal({0.0, 0.0});
    const auto repeated3 = diagonal({4.0, 4.0, 9.0});
    const auto identity3 = diagonal({1.0, 1.0, 1.0});
    std::size_t contract_failure_count = 0U;
    const auto check_modal_contract = [&](const OwnedDense& stiffness,
                                          const OwnedDense& mass,
                                          const std::uint32_t count) {
        const auto config = structural::solver_cpu::default_modal_eigen_config(count);
        expect(
            throws_invalid([&] {
                static_cast<void>(structural::solver_cpu::solve_dense_modal_modes(
                    stiffness.view(), mass.view(), {}, config));
            }),
            "CPU modal contract profile must fail");
        expect(
            throws_invalid([&] {
                static_cast<void>(structural::hip::solve_dense_modal_modes_hip(
                    stiffness.view(), mass.view(), {}, config));
            }),
            "HIP modal contract profile must fail");
        ++contract_failure_count;
    };
    const auto check_buckling_contract = [&](const OwnedDense& stiffness,
                                             const OwnedDense& geometric,
                                             const std::uint32_t count) {
        const auto config = structural::solver_cpu::default_buckling_eigen_config(count);
        expect(
            throws_invalid([&] {
                static_cast<void>(structural::solver_cpu::solve_dense_linear_buckling(
                    stiffness.view(), geometric.view(), {}, config));
            }),
            "CPU buckling contract profile must fail");
        expect(
            throws_invalid([&] {
                static_cast<void>(structural::hip::solve_dense_linear_buckling_hip(
                    stiffness.view(), geometric.view(), {}, config));
            }),
            "HIP buckling contract profile must fail");
        ++contract_failure_count;
    };
    check_modal_contract(identity2, singular2, 1U);
    check_modal_contract(negative2, identity2, 1U);
    check_modal_contract(zero2, identity2, 1U);
    check_modal_contract(repeated3, identity3, 1U);
    check_buckling_contract(singular2, identity2, 1U);
    check_buckling_contract(identity2, negative2, 1U);
    check_buckling_contract(identity2, zero2, 1U);
    check_buckling_contract(repeated3, identity3, 1U);

    expect(maximum_eigenvalue_relative_error <= 2.0e-9, "eigenvalue parity tolerance");
    expect(maximum_shape_absolute_error <= 2.0e-8, "mode-shape parity tolerance");
    expect(maximum_result_metric_absolute_error <= 2.0e-8, "result metric parity tolerance");
    expect(contract_failure_count == 8U, "contract failure profile count");
    expect(aggregate.solve_count == 18U, "generalized-eigen receipt solve count");
    expect(aggregate.h2d_transfer_count == 54U, "aggregate H2D count");
    expect(aggregate.d2h_transfer_count == 18U, "aggregate D2H count");
    expect(aggregate.synchronization_count == 18U, "aggregate synchronization count");
    expect(aggregate.kernel_launch_count == 18U, "aggregate kernel count");
    expect(aggregate.fallback_count == 0U, "aggregate fallback count");
    const auto& receipt = aggregate.identity;
    const auto runtime_architecture = receipt.architecture.substr(
        0U, receipt.architecture.find(':'));
    expect(receipt.device_id >= 0, "generalized-eigen HIP device id");
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
              << "{\"schema_version\":\"native-generalized-eigen-hip-receipt.v1\","
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
              << ",\"profile_count\":8,\"modal_profile_count\":4"
              << ",\"buckling_profile_count\":4,\"deterministic_repeat_count\":8"
              << ",\"numerical_failure_profile_count\":2"
              << ",\"contract_failure_profile_count\":" << contract_failure_count
              << ",\"solve_count\":" << aggregate.solve_count
              << ",\"max_eigenvalue_relative_error\":"
              << maximum_eigenvalue_relative_error
              << ",\"max_shape_absolute_error\":" << maximum_shape_absolute_error
              << ",\"max_result_metric_absolute_error\":"
              << maximum_result_metric_absolute_error
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
              << ",\"device_resident_eigensolve\":true,\"device_result_recovery\":true"
              << ",\"host_intermediate_state_transfer_count\":0"
              << ",\"host_iteration_control_transfer_count\":0"
              << ",\"numerical_status_parity\":true,\"contract_failure_parity\":true"
              << ",\"parity_pass\":true}\n";
    return EXIT_SUCCESS;
}
