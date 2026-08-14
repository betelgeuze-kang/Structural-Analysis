#include "model_ir_assembly.hpp"

#include "model_ir_assembly_fixture.hpp"

#include <iomanip>
#include <iostream>
#include <span>
#include <string_view>

namespace {

void emit(const std::string_view name, const std::span<const double> values) {
    std::cout << name << std::setprecision(17);
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

}  // namespace

int main() {
    structural::tests::ModelIrAssemblyFixture fixture;
    fixture.enable_linear_combination();
    const structural::model_ir::Model model(fixture.descriptor);
    const auto displacement = structural::tests::assembly_displacement();
    const auto direction = structural::tests::assembly_direction();
    const auto result = structural::assembly::assemble_model_ir_linear_reference(
        model, "lp", displacement, direction);
    emit_integer("model_assembly.active_dofs", std::span {result.operator_result.active_dof_indices});
    emit_integer("model_assembly.row_offsets", std::span {result.operator_result.row_offsets});
    emit_integer("model_assembly.column_indices", std::span {result.operator_result.column_indices});
    emit("model_assembly.tangent", result.operator_result.tangent);
    emit("model_assembly.consistent_mass", result.operator_result.consistent_mass);
    emit("model_assembly.internal_force", result.operator_result.residual);
    emit("model_assembly.external_load", result.external_load);
    emit("model_assembly.equilibrium_residual", result.equilibrium_residual);
    emit("model_assembly.jvp", result.operator_result.jvp);
    emit("model_assembly.frame_recovery", result.element_recovery[0].values);
    emit("model_assembly.truss_recovery", result.element_recovery[1].values);
    const auto combination = structural::assembly::assemble_model_ir_linear_reference(
        model, "combo", displacement, direction);
    emit("model_assembly.combination_external_load", combination.external_load);
    emit(
        "model_assembly.combination_equilibrium_residual",
        combination.equilibrium_residual);
    structural::tests::ModelIrAssemblyFixture direct_terms_fixture;
    direct_terms_fixture.enable_three_pattern_linear_combination();
    const structural::model_ir::Model direct_terms_model(direct_terms_fixture.descriptor);
    const auto direct_terms = structural::assembly::assemble_model_ir_linear_reference(
        direct_terms_model, "combo", displacement, direction);
    emit("model_assembly.direct_terms_external_load", direct_terms.external_load);
    emit(
        "model_assembly.direct_terms_equilibrium_residual",
        direct_terms.equilibrium_residual);
    return 0;
}
