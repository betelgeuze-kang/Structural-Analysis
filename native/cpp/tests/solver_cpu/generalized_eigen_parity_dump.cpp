#include "generalized_eigen.hpp"

#include <array>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <span>
#include <string>
#include <string_view>
#include <vector>

namespace {

using structural::solver_cpu::DenseSymmetricMatrixView;

void emit(const std::string_view name, const std::span<const double> values) {
    std::cout << name << std::setprecision(17);
    for (const double value : values) {
        std::cout << '|' << value;
    }
    std::cout << '\n';
}

void emit_modal(
    const std::string_view name,
    const DenseSymmetricMatrixView stiffness,
    const DenseSymmetricMatrixView mass,
    const std::span<const double> scale,
    const std::uint32_t mode_count) {
    const auto result = structural::solver_cpu::solve_dense_modal_modes(
        stiffness,
        mass,
        scale,
        structural::solver_cpu::default_modal_eigen_config(mode_count));
    std::vector<double> eigenvalues;
    eigenvalues.reserve(result.modes.size());
    for (std::size_t mode = 0U; mode < result.modes.size(); ++mode) {
        eigenvalues.push_back(result.modes[mode].eigenvalue_rad2_per_s2);
        emit(
            std::string(name) + ".mode" + std::to_string(mode),
            result.modes[mode].mass_normalized_shape);
        const std::array<double, 4> mode_metrics {
            result.modes[mode].generalized_mass,
            result.modes[mode].generalized_stiffness,
            result.modes[mode].residual_relative_inf,
            result.modes[mode].frequency_hz,
        };
        emit(
            std::string(name) + ".mode_metrics" + std::to_string(mode),
            mode_metrics);
    }
    emit(std::string(name) + ".values", eigenvalues);
    const std::array<double, 7> metrics {
        static_cast<double>(result.status),
        static_cast<double>(result.rigid_mode_count),
        result.mass_orthogonality_error_inf,
        result.stiffness_diagonalization_error_inf,
        result.stiffness_relative_symmetry_error,
        result.mass_relative_symmetry_error,
        static_cast<double>(result.fallback_count),
    };
    emit(std::string(name) + ".metrics", metrics);
}

void emit_buckling(
    const std::string_view name,
    const DenseSymmetricMatrixView stiffness,
    const DenseSymmetricMatrixView geometric,
    const std::span<const double> scale,
    const std::uint32_t mode_count) {
    const auto result = structural::solver_cpu::solve_dense_linear_buckling(
        stiffness,
        geometric,
        scale,
        structural::solver_cpu::default_buckling_eigen_config(mode_count));
    std::vector<double> values;
    values.reserve(result.modes.size());
    for (std::size_t mode = 0U; mode < result.modes.size(); ++mode) {
        values.push_back(result.modes[mode].load_factor);
        emit(
            std::string(name) + ".mode" + std::to_string(mode),
            result.modes[mode].stiffness_normalized_shape);
        const std::array<double, 3> mode_metrics {
            result.modes[mode].generalized_elastic_stiffness,
            result.modes[mode].generalized_geometric_stiffness,
            result.modes[mode].residual_relative_inf,
        };
        emit(
            std::string(name) + ".mode_metrics" + std::to_string(mode),
            mode_metrics);
    }
    emit(std::string(name) + ".values", values);
    const std::array<double, 8> metrics {
        static_cast<double>(result.status),
        static_cast<double>(result.finite_positive_eigenvalue_count),
        static_cast<double>(result.geometric_stiffness_positive_rank),
        result.critical_load_factor,
        result.stiffness_orthogonality_error_inf,
        result.geometric_diagonalization_error_inf,
        result.geometric_stiffness_relative_symmetry_error,
        static_cast<double>(result.fallback_count),
    };
    emit(std::string(name) + ".metrics", metrics);
}

}  // namespace

int main() {
    const std::array<double, 4> modal_two_k {2.0, -1.0, -1.0, 1.0};
    const std::array<double, 4> identity_two {1.0, 0.0, 0.0, 1.0};
    emit_modal(
        "modal_two",
        {2U, modal_two_k},
        {2U, identity_two},
        {},
        2U);

    const std::array<double, 9> modal_scaled_k {
        8.0, -2.0, 0.5,
        -2.0, 6.0, -1.0,
        0.5, -1.0, 5.0,
    };
    const std::array<double, 9> modal_scaled_m {
        2.0, 0.2, 0.0,
        0.2, 3.0, 0.1,
        0.0, 0.1, 1.5,
    };
    const std::array<double, 3> modal_scale {0.25, 1.0, 2.0};
    emit_modal(
        "modal_scaled",
        {3U, modal_scaled_k},
        {3U, modal_scaled_m},
        modal_scale,
        3U);

    const std::array<double, 9> modal_rigid_k {
        0.0, 0.0, 0.0,
        0.0, 4.0, 0.0,
        0.0, 0.0, 9.0,
    };
    const std::array<double, 9> identity_three {
        1.0, 0.0, 0.0,
        0.0, 1.0, 0.0,
        0.0, 0.0, 1.0,
    };
    emit_modal(
        "modal_rigid",
        {3U, modal_rigid_k},
        {3U, identity_three},
        {},
        2U);

    const std::array<double, 9> buckling_singular_k {
        6.0, 0.0, 0.0,
        0.0, 8.0, 0.0,
        0.0, 0.0, 10.0,
    };
    const std::array<double, 9> buckling_singular_kg {
        3.0, 0.0, 0.0,
        0.0, 2.0, 0.0,
        0.0, 0.0, 0.0,
    };
    emit_buckling(
        "buckling_singular",
        {3U, buckling_singular_k},
        {3U, buckling_singular_kg},
        {},
        2U);

    const std::array<double, 9> buckling_scaled_k {
        7.0, -1.0, 0.5,
        -1.0, 9.0, -1.5,
        0.5, -1.5, 6.0,
    };
    const std::array<double, 9> buckling_scaled_kg {
        2.0, 0.2, 0.0,
        0.2, 1.0, 0.1,
        0.0, 0.1, 0.5,
    };
    const std::array<double, 3> buckling_scale {1.0, 0.2, 3.0};
    emit_buckling(
        "buckling_scaled",
        {3U, buckling_scaled_k},
        {3U, buckling_scaled_kg},
        buckling_scale,
        3U);

    const std::array<double, 4> tiny_geometric {1.0e-15, 0.0, 0.0, 0.0};
    emit_buckling(
        "buckling_tiny",
        {2U, identity_two},
        {2U, tiny_geometric},
        {},
        1U);
    return EXIT_SUCCESS;
}
