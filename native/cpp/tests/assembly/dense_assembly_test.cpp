#include "dense_assembly.hpp"

#include <array>
#include <cmath>
#include <cstdlib>
#include <functional>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string_view>
#include <vector>

namespace {

void expect(const bool condition, const std::string_view message) {
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(EXIT_FAILURE);
    }
}

void expect_throws(const std::function<void()>& operation, const std::string_view message) {
    try {
        operation();
    } catch (const std::exception&) {
        return;
    }
    expect(false, message);
}

}  // namespace

int main() {
    const std::array<std::uint32_t, 2> dofs_a {1U, 2U};
    const std::array<std::uint32_t, 2> dofs_b {0U, 1U};
    const std::array<double, 4> tangent_a {4.0, -4.0, -4.0, 4.0};
    const std::array<double, 4> tangent_b {3.0, -3.0, -3.0, 3.0};
    const std::array<double, 4> mass_a {2.0, 1.0, 1.0, 2.0};
    const std::array<double, 4> mass_b {6.0, 3.0, 3.0, 6.0};
    const std::array<double, 2> residual_a {8.0, -8.0};
    const std::array<double, 2> residual_b {6.0, -6.0};
    const std::array<double, 2> jvp_a {12.0, -12.0};
    const std::array<double, 2> jvp_b {9.0, -9.0};
    const std::array contributions {
        structural::assembly::DenseElementContribution {
            20U, dofs_a, tangent_a, mass_a, residual_a, jvp_a},
        structural::assembly::DenseElementContribution {
            10U, dofs_b, tangent_b, mass_b, residual_b, jvp_b},
    };
    const auto result = structural::assembly::assemble_dense_deterministic(3U, contributions);
    const std::vector<double> expected_tangent {
        3.0, -3.0, 0.0,
        -3.0, 7.0, -4.0,
        0.0, -4.0, 4.0,
    };
    const std::vector<double> expected_mass {
        6.0, 3.0, 0.0,
        3.0, 8.0, 1.0,
        0.0, 1.0, 2.0,
    };
    expect(result.tangent == expected_tangent, "deterministic tangent assembly");
    expect(result.consistent_mass == expected_mass, "deterministic mass assembly");
    expect(result.residual == std::vector<double>({6.0, 2.0, -8.0}), "residual assembly");
    expect(result.jvp == std::vector<double>({9.0, 3.0, -12.0}), "JVP assembly");

    const std::array duplicate_indices {
        contributions[0],
        structural::assembly::DenseElementContribution {
            20U, dofs_b, tangent_b, mass_b, residual_b, jvp_b},
    };
    expect_throws(
        [&duplicate_indices] {
            static_cast<void>(
                structural::assembly::assemble_dense_deterministic(3U, duplicate_indices));
        },
        "duplicate stable element index must fail");
    const std::array<std::uint32_t, 2> invalid_dofs {0U, 3U};
    const std::array invalid {
        structural::assembly::DenseElementContribution {
            1U, invalid_dofs, tangent_b, mass_b, residual_b, jvp_b},
    };
    expect_throws(
        [&invalid] {
            static_cast<void>(structural::assembly::assemble_dense_deterministic(3U, invalid));
        },
        "out-of-range DOF must fail");
    const std::array<std::uint32_t, 2> duplicate_dofs {1U, 1U};
    const std::array duplicate_dof_contribution {
        structural::assembly::DenseElementContribution {
            1U, duplicate_dofs, tangent_b, mass_b, residual_b, jvp_b},
    };
    expect_throws(
        [&duplicate_dof_contribution] {
            static_cast<void>(structural::assembly::assemble_dense_deterministic(
                3U, duplicate_dof_contribution));
        },
        "duplicate local DOF must fail");
    const std::array<double, 3> wrong_shape {1.0, 2.0, 3.0};
    const std::array wrong_shape_contribution {
        structural::assembly::DenseElementContribution {
            1U, dofs_b, wrong_shape, mass_b, residual_b, jvp_b},
    };
    expect_throws(
        [&wrong_shape_contribution] {
            static_cast<void>(structural::assembly::assemble_dense_deterministic(
                3U, wrong_shape_contribution));
        },
        "local matrix shape mismatch must fail");
    expect_throws(
        [] {
            static_cast<void>(structural::assembly::assemble_dense_deterministic(4097U, {}));
        },
        "dense allocation beyond the bounded matrix domain must fail");
    const std::array<double, 1> maximum {std::numeric_limits<double>::max()};
    const std::array<std::uint32_t, 1> one_dof {0U};
    const std::array overflowing {
        structural::assembly::DenseElementContribution {
            1U, one_dof, maximum, maximum, maximum, maximum},
        structural::assembly::DenseElementContribution {
            2U, one_dof, maximum, maximum, maximum, maximum},
    };
    expect_throws(
        [&overflowing] {
            static_cast<void>(structural::assembly::assemble_dense_deterministic(1U, overflowing));
        },
        "non-finite deterministic accumulation must fail");
    return EXIT_SUCCESS;
}
