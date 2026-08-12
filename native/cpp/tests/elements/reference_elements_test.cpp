#include "reference_elements.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdlib>
#include <functional>
#include <iostream>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <string_view>

namespace {

void expect(const bool condition, const std::string_view message) {
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(EXIT_FAILURE);
    }
}

void expect_near(
    const double actual,
    const double expected,
    const double tolerance,
    const std::string_view message) {
    expect(std::abs(actual - expected) <= tolerance, message);
}

void expect_throws(const std::function<void()>& operation, const std::string_view message) {
    try {
        operation();
    } catch (const std::exception&) {
        return;
    }
    expect(false, message);
}

void expect_symmetric(const std::vector<double>& matrix, const std::size_t size) {
    for (std::size_t row = 0U; row < size; ++row) {
        for (std::size_t column = 0U; column < size; ++column) {
            expect_near(
                matrix[row * size + column],
                matrix[column * size + row],
                1.0E-12,
                "matrix must be symmetric");
        }
    }
}

}  // namespace

int main() {
    const structural::materials::ElasticIsotropic material {200.0, 0.25, 1000.0};
    const std::array<double, 6> truss_displacement {0.0, 0.0, 0.0, 0.002, 0.0, 0.0};
    const std::array<double, 6> truss_direction {0.0, 0.0, 0.0, 1.0, 0.0, 0.0};
    const auto truss = structural::elements::evaluate_truss3d({
        {0.0, 0.0, 0.0},
        {2.0, 0.0, 0.0},
        material,
        0.01,
        truss_displacement,
        truss_direction,
    });
    expect(truss.dof_count == 6U, "truss DOF count");
    expect_near(truss.tangent[0], 1.0, 1.0E-15, "truss axial stiffness");
    expect_near(truss.tangent[3], -1.0, 1.0E-15, "truss coupling stiffness");
    expect_near(truss.residual[0], -0.002, 1.0E-15, "truss residual i");
    expect_near(truss.residual[3], 0.002, 1.0E-15, "truss residual j");
    expect_near(truss.recovery[0], 0.001, 1.0E-15, "truss strain recovery");
    expect_near(truss.recovery[1], 0.2, 1.0E-15, "truss stress recovery");
    expect_near(truss.recovery[2], 0.002, 1.0E-15, "truss force recovery");
    expect_near(truss.consistent_mass[0], 20.0 / 3.0, 1.0E-14, "truss mass diagonal");
    expect_near(truss.consistent_mass[3], 10.0 / 3.0, 1.0E-14, "truss mass coupling");
    expect_symmetric(truss.tangent, 6U);
    expect_symmetric(truss.consistent_mass, 6U);

    const std::array<double, 12> frame_displacement {
        0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
        0.001, 0.002, -0.003, 0.004, -0.005, 0.006,
    };
    const std::array<double, 12> frame_direction {
        1.0, 2.0, 3.0, 4.0, 5.0, 6.0,
        7.0, 8.0, 9.0, 10.0, 11.0, 12.0,
    };
    const auto frame = structural::elements::evaluate_frame3d({
        {0.0, 0.0, 0.0},
        {2.0, 0.0, 0.0},
        material,
        0.01,
        2.0E-5,
        3.0E-5,
        4.0E-5,
        0.0,
        frame_displacement,
        frame_direction,
    });
    expect(frame.dof_count == 12U, "frame DOF count");
    expect_near(frame.tangent[0], 1.0, 1.0E-15, "frame axial stiffness");
    expect_near(frame.tangent[1U * 12U + 1U], 0.009, 1.0E-15, "frame z-bending stiffness");
    expect_near(frame.tangent[2U * 12U + 2U], 0.006, 1.0E-15, "frame y-bending stiffness");
    expect_near(frame.tangent[3U * 12U + 3U], 0.0016, 1.0E-15, "frame torsion stiffness");
    expect_symmetric(frame.tangent, 12U);
    expect_symmetric(frame.consistent_mass, 12U);
    expect(frame.recovery.size() == 12U, "frame local end-force recovery size");

    const std::array<double, 9> shell_displacement {
        0.0, 0.0, 0.0,
        0.002, 0.0, 0.0,
        0.0, 0.001, 0.0,
    };
    const std::array<double, 9> shell_direction {
        0.0, 0.0, 1.0,
        0.0, 0.0, 2.0,
        0.0, 0.0, 3.0,
    };
    const auto shell = structural::elements::evaluate_shell3_membrane({
        {{{0.0, 0.0, 0.0}, {2.0, 0.0, 0.0}, {0.0, 1.0, 0.0}}},
        material,
        0.1,
        shell_displacement,
        shell_direction,
    });
    expect(shell.dof_count == 9U, "shell DOF count");
    expect_near(shell.recovery[0], 0.001, 1.0E-15, "shell eps_x");
    expect_near(shell.recovery[1], 0.001, 1.0E-15, "shell eps_y");
    expect_near(shell.recovery[2], 0.0, 1.0E-15, "shell gamma_xy");
    expect_near(shell.recovery[3], 0.26666666666666666, 1.0E-15, "shell sigma_x");
    expect_near(shell.recovery[4], 0.26666666666666666, 1.0E-15, "shell sigma_y");
    expect_near(shell.recovery[5], 0.0, 1.0E-15, "shell tau_xy");
    expect(std::all_of(shell.jvp.begin(), shell.jvp.end(), [](const double value) {
        return value == 0.0;
    }), "normal-direction shell JVP must be zero for membrane-only profile");
    expect_symmetric(shell.tangent, 9U);
    expect_symmetric(shell.consistent_mass, 9U);

    expect_throws(
        [&material, &truss_displacement, &truss_direction] {
            static_cast<void>(structural::elements::evaluate_truss3d({
                {0.0, 0.0, 0.0},
                {0.0, 0.0, 0.0},
                material,
                0.01,
                truss_displacement,
                truss_direction,
            }));
        },
        "zero-length truss must fail");
    expect_throws(
        [&truss_displacement, &truss_direction] {
            static_cast<void>(structural::elements::evaluate_truss3d({
                {0.0, 0.0, 0.0},
                {2.0, 0.0, 0.0},
                {std::numeric_limits<double>::max(), 0.25, 1000.0},
                std::numeric_limits<double>::max(),
                truss_displacement,
                truss_direction,
            }));
        },
        "non-finite element response must fail");
    return EXIT_SUCCESS;
}
