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
    emit_integer(
        "model_assembly.constrained_dofs", std::span {result.constrained_dof_indices});
    emit(
        "model_assembly.constrained_internal_force", result.constrained_internal_force);
    emit(
        "model_assembly.constrained_external_load", result.constrained_external_load);
    emit("model_assembly.reactions", result.reactions);
    emit("model_assembly.frame_recovery", result.element_recovery[0].values);
    emit("model_assembly.truss_recovery", result.element_recovery[1].values);
    const auto combination = structural::assembly::assemble_model_ir_linear_reference(
        model, "combo", displacement, direction);
    emit("model_assembly.combination_external_load", combination.external_load);
    emit(
        "model_assembly.combination_equilibrium_residual",
        combination.equilibrium_residual);
    emit("model_assembly.combination_reactions", combination.reactions);
    structural::tests::ModelIrAssemblyFixture member_load_fixture;
    member_load_fixture.enable_linear_combination();
    const std::array<sa_member_distributed_load_descriptor_v1, 1> member_loads {{
        {
            SA_ABI_V1_1,
            static_cast<std::uint32_t>(
                sizeof(sa_member_distributed_load_descriptor_v1)),
            structural::tests::entity("ml0", 0U),
            structural::tests::text("lp"),
            structural::tests::text("e0"),
            SA_MEMBER_LOAD_INITIAL_MEMBER_LOCAL,
            SA_MEMBER_LOAD_UNIFORM_FULL_SPAN,
            {2.0, -3.0, 5.0},
        },
    }};
    member_load_fixture.descriptor.member_distributed_loads = member_loads.data();
    member_load_fixture.descriptor.member_distributed_load_count = member_loads.size();
    const structural::model_ir::Model member_load_model(member_load_fixture.descriptor);
    const auto member_load = structural::assembly::assemble_model_ir_linear_reference(
        member_load_model, "lp", displacement, direction);
    emit("model_assembly.member_load_external_load", member_load.external_load);
    emit(
        "model_assembly.member_load_constrained_external_load",
        member_load.constrained_external_load);
    emit("model_assembly.member_load_reactions", member_load.reactions);
    emit(
        "model_assembly.member_load_frame_recovery",
        member_load.element_recovery[0].values);
    const auto member_load_combination =
        structural::assembly::assemble_model_ir_linear_reference(
            member_load_model, "combo", displacement, direction);
    emit(
        "model_assembly.member_load_combination_external_load",
        member_load_combination.external_load);
    emit(
        "model_assembly.member_load_combination_reactions",
        member_load_combination.reactions);
    emit(
        "model_assembly.member_load_combination_frame_recovery",
        member_load_combination.element_recovery[0].values);
    const std::array<sa_dof_v1, 1> member_release_i {{SA_DOF_RY}};
    const std::array<sa_dof_v1, 1> member_release_j {{SA_DOF_RZ}};
    structural::tests::ModelIrAssemblyFixture member_offset_release_baseline_fixture;
    member_offset_release_baseline_fixture.elements[0].offset_i_global_m[1] = 0.2;
    member_offset_release_baseline_fixture.elements[0].offset_j_global_m[1] = -0.1;
    member_offset_release_baseline_fixture.elements[0].offset_j_global_m[2] = 0.1;
    member_offset_release_baseline_fixture.elements[0].releases_i = member_release_i.data();
    member_offset_release_baseline_fixture.elements[0].releases_i_count =
        member_release_i.size();
    member_offset_release_baseline_fixture.elements[0].releases_j = member_release_j.data();
    member_offset_release_baseline_fixture.elements[0].releases_j_count =
        member_release_j.size();
    const structural::model_ir::Model member_offset_release_baseline_model(
        member_offset_release_baseline_fixture.descriptor);
    const auto member_offset_release_baseline =
        structural::assembly::assemble_model_ir_linear_reference(
            member_offset_release_baseline_model, "lp", displacement, direction);
    structural::tests::ModelIrAssemblyFixture member_offset_release_fixture;
    member_offset_release_fixture.elements[0].offset_i_global_m[1] = 0.2;
    member_offset_release_fixture.elements[0].offset_j_global_m[1] = -0.1;
    member_offset_release_fixture.elements[0].offset_j_global_m[2] = 0.1;
    member_offset_release_fixture.elements[0].releases_i = member_release_i.data();
    member_offset_release_fixture.elements[0].releases_i_count = member_release_i.size();
    member_offset_release_fixture.elements[0].releases_j = member_release_j.data();
    member_offset_release_fixture.elements[0].releases_j_count = member_release_j.size();
    member_offset_release_fixture.descriptor.member_distributed_loads = member_loads.data();
    member_offset_release_fixture.descriptor.member_distributed_load_count = member_loads.size();
    const structural::model_ir::Model member_offset_release_model(
        member_offset_release_fixture.descriptor);
    const auto member_offset_release =
        structural::assembly::assemble_model_ir_linear_reference(
            member_offset_release_model, "lp", displacement, direction);
    std::array<double, 7> member_offset_release_external_delta {};
    for (std::size_t index = 0U; index < member_offset_release_external_delta.size(); ++index) {
        member_offset_release_external_delta[index] =
            member_offset_release.external_load[index]
            - member_offset_release_baseline.external_load[index];
    }
    std::array<double, 11> member_offset_release_constrained_delta {};
    std::array<double, 11> member_offset_release_reaction_delta {};
    for (std::size_t index = 0U; index < member_offset_release_constrained_delta.size(); ++index) {
        member_offset_release_constrained_delta[index] =
            member_offset_release.constrained_external_load[index]
            - member_offset_release_baseline.constrained_external_load[index];
        member_offset_release_reaction_delta[index] =
            member_offset_release.reactions[index]
            - member_offset_release_baseline.reactions[index];
    }
    std::array<double, 12> member_offset_release_recovery_delta {};
    for (std::size_t index = 0U; index < member_offset_release_recovery_delta.size(); ++index) {
        member_offset_release_recovery_delta[index] =
            member_offset_release.element_recovery[0].values[index]
            - member_offset_release_baseline.element_recovery[0].values[index];
    }
    emit(
        "model_assembly.member_load_offset_release_external_delta",
        member_offset_release_external_delta);
    emit(
        "model_assembly.member_load_offset_release_constrained_external_delta",
        member_offset_release_constrained_delta);
    emit(
        "model_assembly.member_load_offset_release_reaction_delta",
        member_offset_release_reaction_delta);
    emit(
        "model_assembly.member_load_offset_release_recovery_delta",
        member_offset_release_recovery_delta);
    structural::tests::ModelIrAssemblyFixture self_weight_fixture;
    self_weight_fixture.load_patterns[0].self_weight[2] = -1.0;
    self_weight_fixture.enable_linear_combination();
    const structural::model_ir::Model self_weight_model(self_weight_fixture.descriptor);
    const auto self_weight = structural::assembly::assemble_model_ir_linear_reference(
        self_weight_model, "lp", displacement, direction);
    emit("model_assembly.self_weight_external_load", self_weight.external_load);
    emit(
        "model_assembly.self_weight_equilibrium_residual",
        self_weight.equilibrium_residual);
    emit("model_assembly.self_weight_reactions", self_weight.reactions);
    const auto self_weight_combination =
        structural::assembly::assemble_model_ir_linear_reference(
            self_weight_model, "combo", displacement, direction);
    emit(
        "model_assembly.self_weight_combination_external_load",
        self_weight_combination.external_load);
    emit(
        "model_assembly.self_weight_combination_equilibrium_residual",
        self_weight_combination.equilibrium_residual);
    emit(
        "model_assembly.self_weight_combination_reactions",
        self_weight_combination.reactions);
    structural::tests::ModelIrAssemblyFixture direct_terms_fixture;
    direct_terms_fixture.enable_three_pattern_linear_combination();
    const structural::model_ir::Model direct_terms_model(direct_terms_fixture.descriptor);
    const auto direct_terms = structural::assembly::assemble_model_ir_linear_reference(
        direct_terms_model, "combo", displacement, direction);
    emit("model_assembly.direct_terms_external_load", direct_terms.external_load);
    emit(
        "model_assembly.direct_terms_equilibrium_residual",
        direct_terms.equilibrium_residual);
    emit("model_assembly.direct_terms_reactions", direct_terms.reactions);
    structural::tests::ModelIrAssemblyFixture nested_fixture;
    nested_fixture.enable_nested_linear_combination();
    const structural::model_ir::Model nested_model(nested_fixture.descriptor);
    const auto nested = structural::assembly::assemble_model_ir_linear_reference(
        nested_model, "combo_nested", displacement, direction);
    emit("model_assembly.nested_combination_external_load", nested.external_load);
    emit(
        "model_assembly.nested_combination_equilibrium_residual",
        nested.equilibrium_residual);
    emit("model_assembly.nested_combination_reactions", nested.reactions);
    structural::tests::ModelIrAssemblyFixture prescribed_fixture;
    const std::array<sa_prescribed_value_v1, 1> prescribed_values {{
        {SA_DOF_UX, 0U, 0.001},
    }};
    prescribed_fixture.constraints[0].prescribed_values = prescribed_values.data();
    prescribed_fixture.constraints[0].prescribed_value_count = prescribed_values.size();
    const structural::model_ir::Model prescribed_model(prescribed_fixture.descriptor);
    std::array<double, 18> prescribed_displacement {};
    prescribed_displacement[0] = 0.001;
    const std::array<double, 18> zero_direction {};
    const auto prescribed = structural::assembly::assemble_model_ir_linear_reference(
        prescribed_model, "lp", prescribed_displacement, zero_direction);
    emit(
        "model_assembly.prescribed_initial_internal_force",
        prescribed.operator_result.residual);
    std::array<double, 7> prescribed_effective_rhs {};
    for (std::size_t index = 0U; index < prescribed_effective_rhs.size(); ++index) {
        prescribed_effective_rhs[index] =
            prescribed.external_load[index] - prescribed.operator_result.residual[index];
    }
    emit("model_assembly.prescribed_effective_rhs", prescribed_effective_rhs);
    emit(
        "model_assembly.prescribed_constrained_internal_force",
        prescribed.constrained_internal_force);
    emit("model_assembly.prescribed_initial_reactions", prescribed.reactions);
    structural::tests::ModelIrAssemblyFixture buckling_fixture;
    buckling_fixture.descriptor.node_count = 2U;
    buckling_fixture.descriptor.section_count = 1U;
    buckling_fixture.descriptor.element_count = 1U;
    buckling_fixture.descriptor.constraint_count = 1U;
    buckling_fixture.elements[0].local_axis_rotation_rad = 0.0;
    buckling_fixture.nodal_loads[0].components_si[0] = -10.0;
    buckling_fixture.nodal_loads[0].components_si[1] = 0.0;
    buckling_fixture.load_patterns[0].nodal_load_count = 1U;
    const structural::model_ir::Model buckling_model(buckling_fixture.descriptor);
    std::array<double, 12> buckling_equilibrium {};
    buckling_equilibrium[6] = -10.0;
    const auto buckling =
        structural::assembly::assemble_model_ir_linear_buckling_reference(
            buckling_model, "lp", buckling_equilibrium);
    emit_integer(
        "model_assembly.buckling_active_dofs",
        std::span {buckling.operator_result.active_dof_indices});
    emit_integer(
        "model_assembly.buckling_row_offsets",
        std::span {buckling.operator_result.row_offsets});
    emit_integer(
        "model_assembly.buckling_column_indices",
        std::span {buckling.operator_result.column_indices});
    emit(
        "model_assembly.buckling_geometric_stiffness",
        buckling.operator_result.tangent);
    const std::array<std::uint64_t, 1> buckling_stable_indices {
        buckling.frame_prestress[0].stable_index,
    };
    const std::array<double, 1> buckling_axial_compression {
        buckling.frame_prestress[0].axial_compression_n,
    };
    const std::array<double, 1> buckling_equilibrium_residual {
        buckling.equilibrium_residual_inf_n,
    };
    emit_integer(
        "model_assembly.buckling_frame_stable_indices",
        std::span<const std::uint64_t> {
            buckling_stable_indices.data(), buckling_stable_indices.size()});
    emit("model_assembly.buckling_frame_axial_compression", buckling_axial_compression);
    emit("model_assembly.buckling_equilibrium_residual_inf", buckling_equilibrium_residual);
    return 0;
}
