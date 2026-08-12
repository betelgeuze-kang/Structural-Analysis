#include "generalized_eigen.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdlib>
#include <functional>
#include <iostream>
#include <limits>
#include <span>
#include <stdexcept>
#include <string_view>
#include <vector>

namespace {

using structural::solver_cpu::DenseSymmetricMatrixView;
using structural::solver_cpu::SolverStatus;

void expect(const bool condition, const std::string_view message) {
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(EXIT_FAILURE);
    }
}

void expect_throws(const std::function<void()>& operation, const std::string_view message) {
    try {
        operation();
    } catch (const std::invalid_argument&) {
        return;
    }
    expect(false, message);
}

[[nodiscard]] bool nearly_equal(
    const double left,
    const double right,
    const double tolerance = 5.0e-11) {
    return std::abs(left - right)
        <= tolerance * std::max({1.0, std::abs(left), std::abs(right)});
}

struct OwnedDense {
    std::size_t order;
    std::vector<double> values;

    [[nodiscard]] DenseSymmetricMatrixView view() const {
        return {order, values};
    }
};

[[nodiscard]] OwnedDense diagonal(const std::initializer_list<double> values) {
    const std::size_t order = values.size();
    OwnedDense result {order, std::vector<double>(order * order, 0.0)};
    std::size_t index = 0U;
    for (const double value : values) {
        result.values[index * order + index] = value;
        ++index;
    }
    return result;
}

[[nodiscard]] bool modal_closed_form_rigid_scaling_and_repeat_are_exact() {
    const OwnedDense stiffness {2U, {2.0, -1.0, -1.0, 1.0}};
    const OwnedDense mass {2U, {1.0, 0.0, 0.0, 1.0}};
    const auto config = structural::solver_cpu::default_modal_eigen_config(2U);
    const auto first = structural::solver_cpu::solve_dense_modal_modes(
        stiffness.view(), mass.view(), {}, config);
    const auto second = structural::solver_cpu::solve_dense_modal_modes(
        stiffness.view(), mass.view(), {}, config);
    const double root_five = std::sqrt(5.0);
    expect(first.status == SolverStatus::converged, "modal solve status");
    expect(first.modes.size() == 2U, "modal mode count");
    expect(nearly_equal(
        first.modes[0].eigenvalue_rad2_per_s2, (3.0 - root_five) / 2.0),
        "modal first closed-form eigenvalue");
    expect(nearly_equal(
        first.modes[1].eigenvalue_rad2_per_s2, (3.0 + root_five) / 2.0),
        "modal second closed-form eigenvalue");
    expect(first.mass_orthogonality_error_inf <= 1.0e-12, "modal mass orthogonality");
    expect(first.stiffness_diagonalization_error_inf <= 1.0e-12,
           "modal stiffness diagonalization");
    expect(first.fallback_count == 0U, "modal fallback must be zero");
    expect(first.modes[0].mass_normalized_shape == second.modes[0].mass_normalized_shape,
           "modal shape bitwise repeat");
    expect(first.modes[0].eigenvalue_rad2_per_s2
               == second.modes[0].eigenvalue_rad2_per_s2,
           "modal eigenvalue bitwise repeat");

    const auto rigid_stiffness = diagonal({0.0, 4.0});
    const auto rigid = structural::solver_cpu::solve_dense_modal_modes(
        rigid_stiffness.view(), mass.view(), {},
        structural::solver_cpu::default_modal_eigen_config(1U));
    expect(rigid.status == SolverStatus::converged, "rigid modal solve status");
    expect(rigid.rigid_mode_count == 1U, "rigid modal count");
    expect(nearly_equal(rigid.modes[0].eigenvalue_rad2_per_s2, 4.0),
           "rigid modal positive mode");

    const OwnedDense scaled_stiffness {2U, {4.0, -1.0, -1.0, 9.0}};
    const OwnedDense scaled_mass {2U, {2.0, 0.0, 0.0, 3.0}};
    const std::array<double, 2> recovery_scale {1.0, 0.125};
    const auto unscaled = structural::solver_cpu::solve_dense_modal_modes(
        scaled_stiffness.view(), scaled_mass.view(), {}, config);
    const auto scaled = structural::solver_cpu::solve_dense_modal_modes(
        scaled_stiffness.view(), scaled_mass.view(), recovery_scale, config);
    expect(scaled.status == SolverStatus::converged, "scaled modal solve status");
    for (std::size_t index = 0U; index < 2U; ++index) {
        expect(nearly_equal(
            scaled.modes[index].eigenvalue_rad2_per_s2,
            unscaled.modes[index].eigenvalue_rad2_per_s2,
            2.0e-10), "scaled modal eigenvalue recovery");
        for (std::size_t row = 0U; row < 2U; ++row) {
            expect(nearly_equal(
                scaled.modes[index].mass_normalized_shape[row],
                unscaled.modes[index].mass_normalized_shape[row],
                2.0e-10), "scaled modal physical shape recovery");
        }
    }
    return true;
}

[[nodiscard]] bool repeated_eigenspaces_are_coordinate_axis_canonical() {
    const auto stiffness = diagonal({4.0, 4.0, 9.0});
    const auto identity = diagonal({1.0, 1.0, 1.0});
    const auto modal = structural::solver_cpu::solve_dense_modal_modes(
        stiffness.view(), identity.view(), {},
        structural::solver_cpu::default_modal_eigen_config(3U));
    expect(modal.status == SolverStatus::converged, "repeated modal solve status");
    for (std::size_t mode = 0U; mode < 3U; ++mode) {
        for (std::size_t coordinate = 0U; coordinate < 3U; ++coordinate) {
            expect(modal.modes[mode].mass_normalized_shape[coordinate]
                       == (mode == coordinate ? 1.0 : 0.0),
                   "repeated modal coordinate basis");
        }
    }
    const auto buckling = structural::solver_cpu::solve_dense_linear_buckling(
        stiffness.view(), identity.view(), {},
        structural::solver_cpu::default_buckling_eigen_config(3U));
    expect(buckling.status == SolverStatus::converged, "repeated buckling solve status");
    for (std::size_t mode = 0U; mode < 3U; ++mode) {
        for (std::size_t coordinate = 0U; coordinate < 3U; ++coordinate) {
            expect(buckling.modes[mode].max_component_normalized_shape[coordinate]
                       == (mode == coordinate ? 1.0 : 0.0),
                   "repeated buckling coordinate basis");
        }
    }
    expect_throws(
        [&] {
            static_cast<void>(structural::solver_cpu::solve_dense_modal_modes(
                stiffness.view(), identity.view(), {},
                structural::solver_cpu::default_modal_eigen_config(1U)));
        },
        "modal repeated cluster cut must fail closed");
    expect_throws(
        [&] {
            static_cast<void>(structural::solver_cpu::solve_dense_linear_buckling(
                stiffness.view(), identity.view(), {},
                structural::solver_cpu::default_buckling_eigen_config(1U)));
        },
        "buckling repeated cluster cut must fail closed");
    return true;
}

[[nodiscard]] bool buckling_filters_infinite_modes_and_recovers_scaling() {
    const auto stiffness = diagonal({6.0, 8.0, 10.0});
    const auto geometric = diagonal({3.0, 2.0, 0.0});
    const auto result = structural::solver_cpu::solve_dense_linear_buckling(
        stiffness.view(), geometric.view(), {},
        structural::solver_cpu::default_buckling_eigen_config(2U));
    expect(result.status == SolverStatus::converged, "buckling solve status");
    expect(result.modes.size() == 2U, "buckling mode count");
    expect(result.finite_positive_eigenvalue_count == 2U,
           "buckling finite positive count");
    expect(result.geometric_stiffness_positive_rank == 2U,
           "buckling geometric rank");
    expect(nearly_equal(result.critical_load_factor, 2.0), "buckling critical factor");
    expect(nearly_equal(result.modes[1].load_factor, 4.0), "buckling second factor");
    expect(result.stiffness_orthogonality_error_inf <= 1.0e-12,
           "buckling stiffness orthogonality");
    expect(result.geometric_diagonalization_error_inf <= 1.0e-12,
           "buckling geometric diagonalization");
    expect(result.fallback_count == 0U, "buckling fallback must be zero");

    const OwnedDense coupled_stiffness {2U, {6.0, -1.0, -1.0, 10.0}};
    const OwnedDense coupled_geometric {2U, {2.0, 0.0, 0.0, 1.0}};
    const std::array<double, 2> recovery_scale {1.0, 0.2};
    const auto config = structural::solver_cpu::default_buckling_eigen_config(2U);
    const auto unscaled = structural::solver_cpu::solve_dense_linear_buckling(
        coupled_stiffness.view(), coupled_geometric.view(), {}, config);
    const auto scaled = structural::solver_cpu::solve_dense_linear_buckling(
        coupled_stiffness.view(), coupled_geometric.view(), recovery_scale, config);
    expect(scaled.status == SolverStatus::converged, "scaled buckling solve status");
    for (std::size_t index = 0U; index < 2U; ++index) {
        expect(nearly_equal(
            scaled.modes[index].load_factor,
            unscaled.modes[index].load_factor,
            2.0e-10), "scaled buckling factor recovery");
        for (std::size_t row = 0U; row < 2U; ++row) {
            expect(nearly_equal(
                scaled.modes[index].stiffness_normalized_shape[row],
                unscaled.modes[index].stiffness_normalized_shape[row],
                2.0e-10), "scaled buckling physical shape recovery");
        }
    }
    return true;
}

[[nodiscard]] bool strict_matrix_and_configuration_validation_fails_closed() {
    const auto identity = diagonal({1.0, 1.0});
    const auto singular = diagonal({1.0, 0.0});
    const auto negative = diagonal({1.0, -1.0});
    const OwnedDense asymmetric {2U, {1.0, 0.1, 0.0, 1.0}};
    const OwnedDense nonfinite {
        2U,
        {1.0, 0.0, 0.0, std::numeric_limits<double>::quiet_NaN()},
    };
    expect_throws(
        [&] {
            static_cast<void>(structural::solver_cpu::solve_dense_modal_modes(
                identity.view(), singular.view(), {},
                structural::solver_cpu::default_modal_eigen_config(1U)));
        },
        "singular modal mass must fail closed");
    expect_throws(
        [&] {
            static_cast<void>(structural::solver_cpu::solve_dense_modal_modes(
                negative.view(), identity.view(), {},
                structural::solver_cpu::default_modal_eigen_config(1U)));
        },
        "indefinite modal stiffness must fail closed");
    expect_throws(
        [&] {
            static_cast<void>(structural::solver_cpu::solve_dense_linear_buckling(
                singular.view(), identity.view(), {},
                structural::solver_cpu::default_buckling_eigen_config(1U)));
        },
        "singular elastic stiffness must fail closed");
    expect_throws(
        [&] {
            static_cast<void>(structural::solver_cpu::solve_dense_linear_buckling(
                identity.view(), negative.view(), {},
                structural::solver_cpu::default_buckling_eigen_config(1U)));
        },
        "indefinite geometric stiffness must fail closed");
    expect_throws(
        [&] {
            static_cast<void>(structural::solver_cpu::solve_dense_modal_modes(
                asymmetric.view(), identity.view(), {},
                structural::solver_cpu::default_modal_eigen_config(1U)));
        },
        "asymmetric stiffness must fail closed");
    expect_throws(
        [&] {
            static_cast<void>(structural::solver_cpu::solve_dense_modal_modes(
                nonfinite.view(), identity.view(), {},
                structural::solver_cpu::default_modal_eigen_config(1U)));
        },
        "non-finite stiffness must fail closed");
    const std::array<double, 2> invalid_scale {1.0, 0.0};
    expect_throws(
        [&] {
            static_cast<void>(structural::solver_cpu::solve_dense_modal_modes(
                identity.view(), identity.view(), invalid_scale,
                structural::solver_cpu::default_modal_eigen_config(1U)));
        },
        "invalid coordinate scale must fail closed");
    auto invalid_config = structural::solver_cpu::default_modal_eigen_config(1U);
    invalid_config.residual_relative_tolerance = -1.0;
    expect_throws(
        [&] {
            static_cast<void>(structural::solver_cpu::solve_dense_modal_modes(
                identity.view(), identity.view(), {}, invalid_config));
        },
        "invalid tolerance must fail closed");
    invalid_config = structural::solver_cpu::default_modal_eigen_config(1U);
    invalid_config.maximum_sweeps = 4'097U;
    expect_throws(
        [&] {
            static_cast<void>(structural::solver_cpu::solve_dense_modal_modes(
                identity.view(), identity.view(), {}, invalid_config));
        },
        "unbounded sweep request must fail closed");
    return true;
}

[[nodiscard]] bool numerical_nonconvergence_has_stable_status_and_no_partial_modes() {
    const OwnedDense stiffness {
        3U,
        {5.0, -2.0, 1.0, -2.0, 4.0, -1.0, 1.0, -1.0, 3.0},
    };
    const auto mass = diagonal({1.0, 2.0, 3.0});
    auto config = structural::solver_cpu::default_modal_eigen_config(2U);
    config.maximum_sweeps = 1U;
    config.eigensolver_relative_tolerance = 1.0e-18;
    const auto result = structural::solver_cpu::solve_dense_modal_modes(
        stiffness.view(), mass.view(), {}, config);
    expect(result.status == SolverStatus::nonconvergence,
           "generalized eigen nonconvergence status");
    expect(result.modes.empty(), "nonconvergence must not publish partial modes");
    expect(result.fallback_count == 0U, "nonconvergence fallback count");
    return true;
}

}  // namespace

int main() {
    static_cast<void>(modal_closed_form_rigid_scaling_and_repeat_are_exact());
    static_cast<void>(repeated_eigenspaces_are_coordinate_axis_canonical());
    static_cast<void>(buckling_filters_infinite_modes_and_recovers_scaling());
    static_cast<void>(strict_matrix_and_configuration_validation_fails_closed());
    static_cast<void>(numerical_nonconvergence_has_stable_status_and_no_partial_modes());
    return EXIT_SUCCESS;
}
