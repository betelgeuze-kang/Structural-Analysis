#include "dense_assembly.hpp"
#include "materials.hpp"
#include "reference_elements.hpp"

#include <array>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <span>
#include <string>
#include <string_view>

namespace {

void emit(const std::string_view name, const std::span<const double> values) {
    std::cout << name;
    std::cout << std::setprecision(17);
    for (const auto value : values) {
        std::cout << '|' << value;
    }
    std::cout << '\n';
}

template <typename Integer>
void emit_integer(const std::string_view name, const std::span<const Integer> values) {
    std::cout << name;
    for (const auto value : values) {
        std::cout << '|' << value;
    }
    std::cout << '\n';
}

void emit_response(
    const std::string_view prefix,
    const structural::elements::ElementOperatorResponse& response) {
    emit(std::string(prefix) + ".tangent", response.tangent);
    emit(std::string(prefix) + ".consistent_mass", response.consistent_mass);
    emit(std::string(prefix) + ".residual", response.residual);
    emit(std::string(prefix) + ".jvp", response.jvp);
    emit(std::string(prefix) + ".recovery", response.recovery);
}

}  // namespace

int main() {
    const structural::materials::ElasticIsotropic material {200.0, 0.25, 1000.0};
    const std::array<double, 1> shear {material.shear_modulus_pa()};
    emit("material.shear_modulus", shear);
    structural::materials::BilinearUniaxialPoint point({200.0, 2.0, 0.1});
    const auto plastic = point.trial(0.02, 1U);
    const std::array<double, 7> plastic_values {
        plastic.strain,
        plastic.stress_pa,
        plastic.tangent_pa,
        plastic.plastic_strain,
        plastic.accumulated_plastic_strain,
        plastic.yielded ? 1.0 : 0.0,
        static_cast<double>(plastic.epoch),
    };
    emit("material.plastic_trial", plastic_values);
    point.commit(1U);
    const std::array<double, 3> committed {
        static_cast<double>(point.committed_epoch()),
        point.committed_plastic_strain(),
        point.committed_accumulated_plastic_strain(),
    };
    emit("material.committed", committed);

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
    emit_response("truss", truss);

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
    emit_response("frame", frame);

    const std::array<double, 12> rotated_frame_displacement {
        0.001, -0.002, 0.003, -0.004, 0.005, -0.006,
        0.007, -0.008, 0.009, -0.010, 0.011, -0.012,
    };
    const std::array<double, 12> rotated_frame_direction {
        -6.0, 5.0, -4.0, 3.0, -2.0, 1.0,
        0.5, -1.5, 2.5, -3.5, 4.5, -5.5,
    };
    const auto rotated_frame = structural::elements::evaluate_frame3d({
        {1.0, -2.0, 0.5},
        {3.0, 1.0, 4.5},
        material,
        0.01,
        2.0E-5,
        3.0E-5,
        4.0E-5,
        0.37,
        rotated_frame_displacement,
        rotated_frame_direction,
    });
    emit_response("frame_rotated", rotated_frame);

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
    emit_response("shell", shell);

    const std::array<double, 9> rotated_shell_displacement {
        0.001, -0.002, 0.003,
        -0.004, 0.005, -0.006,
        0.007, -0.008, 0.009,
    };
    const std::array<double, 9> rotated_shell_direction {
        -1.0, 2.0, -3.0,
        4.0, -5.0, 6.0,
        -7.0, 8.0, -9.0,
    };
    const auto rotated_shell = structural::elements::evaluate_shell3_membrane({
        {{{1.0, -1.0, 0.5}, {3.0, 0.0, 2.5}, {0.0, 1.0, 3.5}}},
        material,
        0.1,
        rotated_shell_displacement,
        rotated_shell_direction,
    });
    emit_response("shell_rotated", rotated_shell);

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
    const auto assembly = structural::assembly::assemble_dense_deterministic(3U, contributions);
    emit("assembly.tangent", assembly.tangent);
    emit("assembly.consistent_mass", assembly.consistent_mass);
    emit("assembly.residual", assembly.residual);
    emit("assembly.jvp", assembly.jvp);

    const std::array<std::uint32_t, 2> dofs_c {2U, 3U};
    const std::array<double, 4> tangent_c {5.0, -5.0, -5.0, 5.0};
    const std::array<double, 4> mass_c {10.0, 4.0, 4.0, 10.0};
    const std::array<double, 2> residual_c {7.0, -7.0};
    const std::array<double, 2> jvp_c {11.0, -11.0};
    const std::array csr_contributions {
        contributions[0],
        contributions[1],
        structural::assembly::DenseElementContribution {
            30U, dofs_c, tangent_c, mass_c, residual_c, jvp_c},
    };
    const std::array<std::uint32_t, 1> constrained_dofs {0U};
    const auto csr = structural::assembly::assemble_reduced_csr_deterministic(
        4U, csr_contributions, constrained_dofs);
    emit_integer("assembly_csr.active_dofs", std::span {csr.active_dof_indices});
    emit_integer("assembly_csr.row_offsets", std::span {csr.row_offsets});
    emit_integer("assembly_csr.column_indices", std::span {csr.column_indices});
    emit("assembly_csr.tangent", csr.tangent);
    emit("assembly_csr.consistent_mass", csr.consistent_mass);
    emit("assembly_csr.residual", csr.residual);
    emit("assembly_csr.jvp", csr.jvp);
    return EXIT_SUCCESS;
}
